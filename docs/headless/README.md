# Headless simulator

The decompiled game simulation (`internals/`, private submodule) run in Node at full CPU speed: all systems, the Python interpreter and its step budget, no UI, no wall clock. Tooling lives in [`devtools/simulation/headless/`](../../devtools/simulation/headless/). This folder is the reference for running it, for the stand-ins that make focused runs fast, and for the patches it applies to the simworker.

| Page | What it covers |
| :--- | :--- |
| [scenarios.md](scenarios.md) | `--scenario FILE`: which subsystem runs real, stands in, or is off; item flows; archive seeds; the old flags as sugar; `summary.json` fields. |
| [standins.md](standins.md) | How each stand-in works, its boundary (what it must feed and drain), the state shapes it touches, the virtual script count, and what each phase has delivered so far. |
| [anchors.md](anchors.md) | How the harness patches the simworker (stable-string anchors, warn-and-disable), and the checks to run after a game update. |
| [ab_results.md](ab_results.md) | A/B tables: a stand-in ships only with its row (fidelity and speed against the real run). |
| [../plans/headless_sim.md](../plans/headless_sim.md) | Findings from the first port (what runs, what does not), speed tables, the passive-machine parking A/B. |
| [../cheatsheet/dev_workflow.md §10b](../cheatsheet/dev_workflow.md) | The `run.mjs` flag list and `simhost.mjs` API summary. |

## Quick start

```
node devtools/simulation/headless/run.mjs --save SAVE --hours 1 --out out/run1
node devtools/simulation/headless/run.mjs --save SAVE --scenario devtools/simulation/headless/scenarios/plants_only.json --hours 1 --out out/plants
node devtools/simulation/headless/run.mjs --save SAVE --standin power=trim --standin terraforming=park --hours 1
node --test "devtools/simulation/headless/test/*.test.mjs"
```

`SAVE` is a `save_<id>.json` or `.json.gz`. The sample saves in `internals/sample_saves/` are the usual start points: `20261007_c5f9ebf/saves/` (20 checkpoints of one run, day 1 to 59, `KEEP.md` says why each was kept), `20261008_7e5e168/saves/` (218 saves of a second run with `log.md`), and `save_mtzkzly3_4ww80o.midlate_2026-10-05.json` (the main save, mid-late). `run.mjs --save` runs the repo's current scripts in the save's slots by default; `--as-saved` runs the save's own.

## Files

| File | Role |
| :--- | :--- |
| `run.mjs` | CLI: load, run, report, deploy templates, build-order policy, scenario. |
| `simhost.mjs` | Loads and patches the simworker; the `Sim` class (`load`, `tick`, `setScript`, `setArchive`, `getArchive`, `undeploy`, ...). |
| `standins.mjs` | Machine-type registry, subsystem groups, modes, the virtual script count, power `trim`. |
| `scenario.mjs` | Scenario file loading, flag merging, validation. |
| `stacks.mjs` | Item stores in raw state (Inventory, Warehouses, Depots) and the producer/consumer flows. |
| `passive.mjs` | `Parker`: passive-machine parking (heaters, O2, pressure) with wake triggers. |
| `policy.mjs` | Early-game build-order policy for new-game runs. |
| `scenarios/` | Checked-in scenario files. |
| `standins/` | Level-1 Python stand-in scripts (phase 1; deployed with `sim.setScript`, never under `scripts/`). |
| `test/` | Node unit tests (`node --test`), no simworker needed except the anchor check. |
