# Headless simulation for integration tests

Goal: test the automation over hours of game time (first target: the early game runner from the 10k TP Ship Computer unlock to the 150k TP migration) without playing those hours in game. Tool: [`devtools/headless/`](../../devtools/headless/), usage in [dev_workflow.md §10b](../cheatsheet/dev_workflow.md).

## Findings (2026-10-05, simworker in `internals/` at 7507d06)

- **The simworker runs in Node 22 unchanged.** Its worker bootstrap only starts inside a Web Worker (`process === undefined` check), so importing it as an ES module is side-effect free. A small shim appended at run time exposes the sim core (`tCe`), the state factory and loader (`LB`, `Kpe`), the serializer (`qpe`) and builds the same `SimHost` + command registry the worker builds (`GCe`), minus the message port and `setInterval` clock.
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

The interpreter runs ~1.6 M steps per wall second. The per-tick cap is 50,000 steps for the whole base (§1d-1), so a base whose scripts use the whole cap runs at ~33 ticks/s, about the game's own 3× maximum. Headless speed is therefore set by **steps actually executed per tick** (sleeping scripts cost nothing) plus system cost, which grows with machine count. On the new game the systems split as: ScriptScheduler 40 %, AchievementSystem 21 %, FlowTransport 21 %, Power 5 %, rest small (`--profile`). A late-game save has not been profiled yet.

## Simplifications for later phases, cheapest first

1. **Checkpoints and parallel runs.** Save the state at phase boundaries (`final_save.json`) and start each test from its checkpoint; independent runs go one per core. No fidelity cost.
2. **Drop bookkeeping systems** the tests don't read: AchievementSystem (21 % above), CameraObservation, Transmission. Exact for production and scripts, as long as nothing under test reads achievements.
3. **Sleep skipping.** When every script is waiting at least k ticks, run the systems for those k ticks without touching the scheduler, or as one call with `dt × k` for systems that integrate smoothly (atmosphere, plants, wildlife, research rates). Script behavior stays exact; `dt × k` needs an A/B check per system against the 1-tick run, since buffers, cycle completions and battery limits can overshoot within a big step.
4. **Slow systems at a lower rate**: run Atmosphere/Plant/Wildlife/Biomass every n ticks with `dt × n`. Same A/B check.
5. **Script stand-ins.** For a test that targets one subsystem, replace unrelated scripts with cheap models (a fixed recipe loop instead of the full planner). Lower fidelity, so only for focused tests.
6. **Interpreter cost**: profile one late save with `node --cpu-prof`; a hot path there is a game-side cost we cannot change, but it also tells which script patterns (API calls, comprehensions) dominate, which feeds back into script optimization like `step_profile.py` does.

Options 3 to 5 trade fidelity for speed and must report which were on, so a test result says what it verified.

## Next steps

1. The owner saves a game at 10k TP and puts the `save_<id>.json` where tests can read it (it holds the save's scripts, so not in this public repo; the private `internals/` repo or the project files).
2. Run `--save <it> --deploy-templates <earlygame>/templates/early --until-tp 150000 --profile` and check the time to 150k, the crash list and the system profile.
3. Turn the run into an assertion test (milestone TP by game hour, no crashed scripts), then profile a late-game save to pick among the simplifications.
