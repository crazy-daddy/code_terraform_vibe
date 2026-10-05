# Headless simulation for integration tests

Goal: test the automation over hours of game time (first target: the early game runner from the 10k TP Ship Computer unlock to the 150k TP migration) without playing those hours in game. Tool: [`devtools/headless/`](../../devtools/headless/), usage in [dev_workflow.md §10b](../cheatsheet/dev_workflow.md).

## Findings (2026-10-05, simworker in `internals/` at 7507d06)

- **The simworker runs in Node 22 unchanged.** Its worker bootstrap only starts inside a Web Worker (`process === undefined` check), so importing it as an ES module is side-effect free. A small shim appended at run time exposes the sim core, the state factory and loader, the serializer (minified names found by stable strings, see dev_workflow §10b) and builds the same `SimHost` + command registry the worker builds (`GCe`), minus the message port and `setInterval` clock.
- **Everything is real**: all 27 systems, the Python interpreter, the scheduler with its step budget (`stepsPerTick`, `totalStepsPerTick`, top-level loop yields one iteration per tick), the collection limits, `get_component()` and the command protocol (`script.create`/`setSource`/`run`, `sim.load`/`sim.new`). The early templates of the earlygame runner run against it as they do in game.
- **Saves load as-is**: `sim.load` takes the `save_<id>.json` text; scripts that were running resume. Same seed, same inputs give a byte-identical state (checked over 5,000 ticks).
- **Script console**: lines reach the UI only through the presentation path, which the headless host skips; the harness taps the scheduler's `emitScript*` methods.
- **Not covered**: anything outside the sim worker. The earlygame orchestrator (`early_game.py`) talks to the game through `codeterraform-workspace.json` and `.codeterraform/command.json`, which the UI process writes; the harness replaces its deploy loop with an in-process one (`--deploy-templates`, same typeId → template map). Rover/Pioneer module mounting and the 150k migration are not ported. Onboarding and the intro contracts need clicks in the UI, so a run starts from a save taken at 10k TP, not from a new game.

## Speed (this container, one core)

| Case | Ticks / s | × real time at 1× |
| :--- | ---: | ---: |
| New game, no scripts | ~14,000 | ~1,400 |
| New game, early templates deployed (2 running) | ~6,000 | ~600 |
| 1 script using its full 1,000 steps/tick | ~1,300 | ~130 |
| 4 scripts at full budget (4,000 steps/tick) | ~410 | ~41 |

The interpreter runs ~1.6 M steps per wall second. The per-tick cap is 50,000 steps for the whole base (§1d-1), so a base whose scripts use the whole cap runs at ~33 ticks/s, about the game's own 3× maximum. Headless speed is therefore set by **steps actually executed per tick** (sleeping scripts cost nothing) plus system cost, which grows with machine count. On the new game the systems split as: ScriptScheduler 40 %, AchievementSystem 21 %, FlowTransport 21 %, Power 5 %, rest small (`--profile`). 

### Uploaded saves (2026-10-05)

| Save | Machines / running scripts | Ticks / s | × real time |
| :--- | ---: | ---: | ---: |
| Early, 31k TP | 33 / 23 | ~770 | ~77 |
| Late, 887k TP, as saved | 274 / 141 | ~3.4 | 0.34 |
| Late, debug flags off, oil reservoir buffered | 274 / 146 | ~13 | ~1.3 |

Two costs in the late save are game-side, so they likely slow the real game the same way (inferred, not measured in game):
- **Debug flags**: 4 scripts and 11 libraries have `debug` on; the scheduler then builds a debug snapshot at every step boundary. Clearing them took the scheduler from 148 to 60 ms per tick.
- **Fluid network rebuilds**: `bulk_liquid_reservoir_9` (oil, outpost_4) runs at 48 in / 48 out with ~0.2 of 1,000 stored. Its level crosses zero inside every tick, which changes the fluid-network signature (`gx()`), so `Ex()` rebuilds every network's analysis twice per tick (121 misses in 132 calls). Raising its level to 500 took FlowTransport from 142 to 13 ms per tick. Keeping that reservoir buffered (consumer a little slower than supply) avoids it; filled by hand it ran dry again within ~2 game minutes. Mechanism and advice: [gameknowledge/fluids.md](../gameknowledge/fluids.md); headless runs use `--sticky-fluids`.

What is left is the scripts: ~54 ms per tick for ~14,000 steps (3.8 µs per step, API calls and allocation, against ~0.6 µs for plain arithmetic). By type: fabricator 8.0 ms (7 scripts), heater 8.0 (16), panel 6.5 (7), o2gen 5.5 (21), smelter 4.5 (5), drone 4.1 (8), crop_automator 3.7 (7), pressure 3.0 (13). Heater + o2gen + pressure (50 scripts) take 16.5 ms, 31 % of script time: flattening them (option 5) gives about 1.5×, the rest is the planners under test.

Heater cost (2026-10-05, measured by swapping `heater_9` for probe loops that each call one part of `HeatController.step()`): ~2,500 steps per 2 s poll, of which ~2,400 are the Mk III steam guard (`Mk3FluidFeed._update_guard`). It walks all 245 `grid.members` to find the 27 steam Gas Tanks (`power.grid_steam_tank_ids`, ~1,450 steps) and then reads every tank (`power.steam_pool`, ~800). The fluid input router costs ~300, the console flush ~240, rods and thermal state under 70. So it is Python scanning in our script, not the game's fluid code, and it costs the same steps in game. All 16 heaters measure the same grid every poll. Fix candidates (in the game scripts, not this PR): cache the tank ids and rescan rarely, and measure the pool every few game minutes instead of every poll (the 50 %/70 % hysteresis does not need 2 s resolution).

## Simplifications for later phases, cheapest first

1. **Checkpoints and parallel runs.** Save the state at phase boundaries (`final_save.json`) and start each test from its checkpoint; independent runs go one per core. No fidelity cost.
2. **Drop bookkeeping systems** the tests don't read: AchievementSystem is off by default (21 % above; same TP and credits after 0.25 h of the early save with and without it). CameraObservation and Transmission can be added with `--skip-systems`.
3. **Sleep skipping.** When every script is waiting at least k ticks, run the systems for those k ticks without touching the scheduler, or as one call with `dt × k` for systems that integrate smoothly (atmosphere, plants, wildlife, research rates). Script behavior stays exact; `dt × k` needs an A/B check per system against the 1-tick run, since buffers, cycle completions and battery limits can overshoot within a big step.
4. **Slow systems at a lower rate**: run Atmosphere/Plant/Wildlife/Biomass every n ticks with `dt × n`. Same A/B check.
5. **Script stand-ins.** For a test that targets one subsystem, replace unrelated scripts with cheap models (a fixed recipe loop instead of the full planner). Lower fidelity, so only for focused tests.
6. **Interpreter cost**: profile one late save with `node --cpu-prof`; a hot path there is a game-side cost we cannot change, but it also tells which script patterns (API calls, comprehensions) dominate, which feeds back into script optimization like `step_profile.py` does.

Options 3 to 5 trade fidelity for speed and must report which were on, so a test result says what it verified.

## Passive machines (`--park`, `passive.mjs`)

Heater, O2 and pressure scripts stay in the scheduler as `waiting` (still counted in the step split, setpoints held) and run a real loop pass only on a trigger: O2 waste ≥ 50; pressure gauge in the sync window while unsynced, or a gauge wrap; heaters every 20 s; any of them on a power or tier change, an input port under half full, or after one game minute.

A/B on the late save, 20 game minutes, both with `--sticky-fluids`:

| | Full | Parked |
| :--- | ---: | ---: |
| TP gained | 712 | 710 |
| Heat gained | 1,672.0 | 1,658.0 (−0.8 %) |
| Pressure, O2 gained | 62.337, 2,013.98 | identical |
| Script errors | 0 | 0 |
| × real time | 1.36 | 1.69 |

Remaining cost: scripts ~50 ms/tick (fabricators, panels, drones, smelters, the planners under test), FlowTransport ~13 ms/tick, CameraObservation ~2 ms/tick.

## Next steps

1. The owner saves a game at 10k TP and puts the `save_<id>.json` where tests can read it (it holds the save's scripts, so not in this public repo; the private `internals/` repo or the project files).
2. Run `--save <it> --deploy-templates <earlygame>/templates/early --until-tp 150000 --profile` and check the time to 150k, the crash list and the system profile.
3. Turn the run into an assertion test (milestone TP by game hour, no crashed scripts), then profile a late-game save to pick among the simplifications.
