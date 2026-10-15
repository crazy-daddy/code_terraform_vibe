# Headless stand-ins: handoff after phase 13 (power `trim` refused stops, the open rows)

Written 2026-10-15 after phase 13 landed. Design reference: [docs/headless/standins.md](../headless/standins.md) (Modes table `trim` row), results in [docs/headless/ab_results.md](../headless/ab_results.md) "Phase 13". The operator's full plan is the local Claude plan file `plan-useful-speedy-features-nested-blossom.md` (not in the repo; it ends at phase 6, phases 7 to 13 came from the handoffs' "Open" items). Earlier notes: [done/headless_phase13_handoff.md](done/headless_phase13_handoff.md) and the ones it links.

## Where phase 13 left things

- `#stop` (`standins.mjs`) now reads the command result: the game's `script.stop` handler returns nothing on success and `{ok: false}` (or `{ok: false, status: "source_changed"}`) on a refusal, inside the envelope's `result`. Before, `if (r.ok)` counted every refusal as stopped, so the refused-stop branch of `#trimReeval` never ran outside the tests. The game refuses only for a bad script id or a stale `expectedSource`, and `#stop` sends no source, so no A/B row has hit it.
- First trim stop (`#trim`): an extra generator with a running slot that did not stop counts as kept (`kept`, `keptRated`), goes to `t.back` as a second-stop candidate with its running slots, and its stopped slots go to the pool at rating 0. Re-evaluation: a rating-0 entry (the stopped part of a generator still counted) no longer moves `kept` on restart or restop (`if (rating) n++`), so the `keepMin` guard counts generators, not slot groups.
- Tests: `test/standins.test.mjs` +3 (`step` through the refused-stop and dead-script branches; a refused first stop; a part-refused generator counted once). `fakeSim` takes `stopFails` (answers the game's refusal shape). 70 green with `node --test "devtools/simulation/headless/test/*.test.mjs"`; each new test fails with its fix reverted. Reviewed with `cavecrew-reviewer` (two rounds; both findings fixed, the third is open item 1).
- A/B on 1220, 1 h, a new real run (`scripts/` moved since phase 12) and three trimmed rows. `reevalTicks=300,quietWindows=6,stopMargin=1.25`: `8 / 7 / 117`, 4 ghosts at the end. `warmupTicks=10000` (default windows): keeps all 21 generators (7,357 W peak over 7,004 W rated), never stops one in the hour, `console.log` byte-identical to real. Same with `reevalTicks=600`: the floor does all the cutting, `12 / 25 / 43`, one restart refused (`turbine_4` `offline`). TP within 0.01 % at the end, no brownout.
- `spire_25`: every row, the real one included, books it at 0.417 h and ends with it complete; phase 12's 36-silicon shortfall does not come back. The phase 12 pair's first difference is the stopped turbines' missing log lines and `thermal_cap_3` venting at `gas_tank_16`, then `drone_9`'s partial unload at `drone_station_2` (tick 1,811,707), after which `drone_10` hauls the silicon `drone_9` hauled in the real run. Credits drift in both directions between rows: timing after the first stop, not a stand-in deficit.
- Docs: `standins.md` (`trim` row refusal sentence, phase table row 13), `ab_results.md` "Phase 13" and the open rows, TODO's headless block. Outputs in `out/ab13_*` (never commit `out/`).

## Open (optional)

1. A refused stop under `off`, `park`, `produce`, `cash` or `mover` only warns: the script keeps running next to the stand-in (`off` writes its stubs anyway), `this.stopped[g]` and the ghosts leave it out. Decide per mode whether a refusal fails setup or is recorded in `report()`, if a row ever logs `standins: script.stop ... {"ok":false}`.
2. `turbine_4` answered `offline` to `script.run` in the `reevalTicks=600` row: its slot stays a ghost for the rest of the run. Check whether a powered-off or unpowered generator should leave the pool (and the ghosts) instead.
3. Placement without a builder (design note in `standins.md`), if a logistics-off target ever needs blueprints built.
4. Record `--log-levels` next to a row that cites `[POWER]` lines (phase 6's `Night eval ... shed` lines did not appear in `ab7_*` to `ab13_*` under the default).

## Field report: stand-ins under a factory/parking target (2026-10-15)

From another session's parking A/B (fabricator/smelter backstop `WAKE_AFTER_TICKS` 1200 vs 3000, [event_driven_automation.md](event_driven_automation.md)). Save `internals/sample_saves/20261008_7e5e168/saves/1631_t2294802.json.gz` (late game, ~157 running scripts), `--hours 1 --report-every 10 --paid-debug --sticky-fluids`, three runs in parallel on one machine, the same `save_scripts.py` output for all three (`--scripts DIR --libs DIR/lib`). Stand-in scenario: `default: real`, `terraforming: scale`, `biomass: off`, `biolab: off` (`scale` collapsed 36 machines into 8 records, 28 undeployed; `biomass` stopped 9 scripts; no biolab scripts on the save). Outputs were in the session scratchpad, not `out/`.

| | real, 1200 | stand-ins, 1200 | stand-ins, 3000 |
| :--- | ---: | ---: | ---: |
| wall s | 1,399 | 1,172 | 1,160 |
| allowance at the end (`n` / ghosts / steps) | 159 / 0 / 314 | 125 / 37 / 308 | 103 / 37 / 357 |
| O2 gained | 13,189 | 11,294 (−14 %) | 11,294 |
| biomass gained | 16,538 | 6,538 | 6,538 |
| TP at the end | 789,559 | 788,160 | 788,256 |
| credits at the end | 622,563 | 615,063 | 607,063 |
| fabricator `Sent` units | 73 (`machine_frame` 30, `lead_plate` 22, `control_unit` 14, `mining_drill_kit` 7) | 27 (`lead_plate` 18, `control_unit` 9) | 18 (`lead_plate` 18) |
| smelter `Sent` units | 105 | 74 | 72 |
| errored / crashed | 0 / none | 0 / none | 0 / none |

Findings:

1. Speed: 16 % less wall time for 37 ghosts out of ~160 scripts. The game's script cost on this save sits in the groups that stay real (factory, orchestrator, logistics, plants, wildlife, power).
2. Fidelity for a factory target: the stand-in column with the same scripts as the real one lost `machine_frame` and `mining_drill_kit` entirely and 63 % of the fabricator output. That is a group boundary, not stand-in noise, but which one is not pinned down: the candidates are `scale`'s 28 undeployed terraformers (their kits leave the Inventory, so their upgrade and site-plan demand changes) and `biomass` off (essence and biomass items stop). `GROUPS[g].produces/consumes` lists neither `production.demand` input for terraforming nor biomass. O2 −14 % is far above phase 1/2's 0.3 % on the midlate save; the late save runs more O2 machines per record.
3. Consequence for the parking A/B: the stand-in pair was not usable; the target needs real against real.

Open (from this report):

5. Find which boundary takes the fabricator demand: rerun the stand-in column with `terraforming: scale` alone and with `biomass: off` alone on 1631, then name the boundary in `standins.md` (`produces/consumes`) and in ab_results.md.
6. The O2 gap under `scale` on a late save: compare per-record `minLevel` and the `stalled` warning with phase 2's midlate numbers before trusting `scale` there.

Pitfalls that still apply: `pass(t)` counts from the run's start, archive ages use `state.tickCount`; `reevalTicks` defaults to `warmupTicks`, so a long warm-up also lengthens every window (set both); `--only-scripts` pins `keep` and a stand-in skips kept slots; validate params for value before any side effect (the constructor, not `#setup`, for anything that must precede the archive seeds); the watcher does not cover `devtools/`; a group that is off or stood in has a boundary (`GROUPS[g].produces` / `consumes`) and the A/B gaps come from there first, name them in ab_results.md rather than tuning the stand-in; `final_save.json` is the raw state (no `state` wrapper) and is UTF-8; `run.mjs --hours` and `summary` hours are clock hours (36,000 ticks), planet-hours (250 ticks) are the construction and day-cycle unit; a generator's `generated` share is demand, not capacity, and `subnet.consumed` is demand, not served load; the stand-in's `standins:` lines go to the run's stdout, not `console.log`; a run deploys the repo's working-tree `scripts/`, so a commit or a parallel session's edit between two runs breaks the pair (check `diff -rq --strip-trailing-cr out/<a>/latest_scripts out/<b>/latest_scripts`, rerun the real column when it differs); `h.command` returns `{ok, result, error}` where `ok` only means dispatched, read `result.ok` for the game's answer; the `k=v` parser makes `null` the string `"null"`, leave a key out for its default.
