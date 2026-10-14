# devtools

Host-side tools. They run on desktop Python or Node, not in the game, so the game interpreter rules in `CODE_GUIDES.md` don't apply here. Each tool documents itself: run `python <tool> -h` (the help is the file's docstring), or read the header comment of an in-game script or a `.mjs` file. Fuller notes, with caveats, are in [dev_workflow.md](../docs/cheatsheet/dev_workflow.md) §9–10c.

Run every command from the repo root. Tools that import `scripts_sync` (it needs `typer` and `watchdog`) run with `.venv/Scripts/python.exe`; plain `python` is enough for the rest.

## Top level: deploy and shared helpers

| File | What it does | Quick start |
|---|---|---|
| [scripts_sync.py](scripts_sync.py) | Deploys the tiered `scripts/` tree into a save's script slots and `lib/`. The only tool that writes into a save. | `.venv/Scripts/python.exe devtools/scripts_sync.py watch` (also `status`, `once`, `resolve-preview`, `apply-libs`, `hold`/`release`) |
| [early_game.py](early_game.py) | Fresh-save driver loaded by `scripts_sync.py watch --early`: onboarding steps, idle starts, speedrun advice. | not run directly |
| [self_typing.py](self_typing.py) | Typed `self` for Pyright in game scripts; `scripts_sync` also uses it to write the `user_stubs.py` block. | `python devtools/self_typing.py apply [--dry-run]` |
| [savefile.py](savefile.py) | Reads a save, plain or gzip (`simulation/headless/savefile.mjs` is the JS version). | library |

Gitignored state: `.sync-backups/` (sync backups, session holds, seed-swap backups), `.decision-runs/` (recorder runs when `internals/` is absent).

## play/: alongside a running game

| File | What it does | Quick start |
|---|---|---|
| [game_speed.py](play/game_speed.py) | Starts the game with WebView2 remote debugging and toggles sim speed with a hotkey. | `python devtools/play/game_speed.py --fast 10` |
| [dap_client.py](play/dap_client.py) | Minimal Debug Adapter Protocol client that runs a debug session from a script. Pauses real gameplay: ask before you use it on the main save. | `python devtools/play/dap_client.py --workspace <save_scripts> --script <slot>.py` |
| [decision_recorder.py](play/decision_recorder.py) | Records a manual run: polls the save, diffs each write and logs your decisions. | `python devtools/play/decision_recorder.py` |
| [save_diff.py](play/save_diff.py) | Diffs and annotates consecutive saves of a recorded run. | `python devtools/play/save_diff.py RUN_DIR --out DIR` |
| [swap_seed.py](play/swap_seed.py) | Changes a very young save's world seed and regenerates what the seed decides. Dry run unless `--apply`. | `python devtools/play/swap_seed.py --save PATH --seed N` |

## code_scan/: clean-code scans over `scripts/`

| File | What it does | Quick start |
|---|---|---|
| [clean_code_scan.py](code_scan/clean_code_scan.py) | One entry point for both scans. | `python devtools/code_scan/clean_code_scan.py {clones,features} -h` |
| [clone_scan.py](code_scan/clone_scan.py) | Near-duplicate functions, candidates for one shared helper. Reviewed keeps go in `clone_scan_ignore.txt`. | `... clean_code_scan.py clones` |
| [feature_scan.py](code_scan/feature_scan.py) | Code that a supported interpreter feature would simplify (`@dataclass`, `match`, `TypedDict`, ...). Reviewed keeps go in `feature_scan_ignore.txt`. | `... clean_code_scan.py features --summary` |
| [scan_common.py](code_scan/scan_common.py) | Shared file discovery and ignore-file parsing. | library |

## perf/: interpreter steps and timing

| File | What it does | Quick start |
|---|---|---|
| [step_profile.py](perf/step_profile.py) | Counts the opcodes of one lib code path on the synthetic sample world. Use it to size `run_atomic` chunks. | `python devtools/perf/step_profile.py --list` |
| [tick_profile.py](perf/tick_profile.py) | Times lib functions in game ticks inside a headless run of a real save, gated on one call (default: each demand refresh task). | `.venv/Scripts/python.exe devtools/perf/tick_profile.py --save SAVE --out DIR` |
| [log_block_timing.py](perf/log_block_timing.py) | Times every TreeConsole block from the newest save's script logs. | `python devtools/perf/log_block_timing.py --top 20` |
| [repeat_read_scan.py](perf/repeat_read_scan.py) | Static scan for game reads repeated inside loops, ranked by log timing. | `python devtools/perf/repeat_read_scan.py --no-logs` |
| [panel_benchmark.py](perf/panel_benchmark.py) | In-game interpreter benchmark. Paste it into a `control_panel` slot. Results: `docs/BENCHMARK.md`. | in game |
| [console_multiline_test.py](perf/console_multiline_test.py) | In-game probe for console multi-line output and string/collection limits. | in game |

## simulation/: offline game models

Models of the game that run outside it: the real simworker run headless, and analytic models built from game constants.

| File | What it does | Quick start |
|---|---|---|
| [headless/](simulation/headless/) | The decompiled simworker run in Node at full CPU speed (`run.mjs`, `simhost.mjs`; reference: [docs/headless/](../docs/headless/README.md)), stand-in scenarios for focused runs (`standins.mjs`, `scenario.mjs`, `scenarios/`), plus seed tools (`field`, `recipes`, `sources`, `seedscan`, `seedconfirm`), the Harvester model and its route policies, the build-order policy, and `ore_outpost` (best spot for a Pioneer-fed Smelter/Fabricator outpost; the mineral sites are the same in every world). Needs Node ≥ 20 and `internals/`. | `node devtools/simulation/headless/run.mjs --save SAVE --hours 4 --out DIR` |
| [buildorder_search.py](simulation/buildorder_search.py) | Early-game build-order search on the headless sim (Pareto front). `buildorder_model.py` is its Terraform Index surrogate. | `python devtools/simulation/buildorder_search.py --save CHECKPOINT` |
| [seed_quality.py](simulation/seed_quality.py) | Scores what a world seed decides: Seed Maker recipes and life-form supply; exports the model for `seedscan.mjs`. | `python devtools/simulation/seed_quality.py recipes --seeds 1-20000` |
| [scan_stop_eval.py](simulation/scan_stop_eval.py) | How often the sonar scan-stop pairing method misses a contact, on real world layouts. | `python devtools/simulation/scan_stop_eval.py --seeds 1-50` |
| [wildlife_optimizer.py](simulation/wildlife_optimizer.py) | Solves the wildlife revival and Insight schedule offline (feeds `WILDLIFE_SCHEDULES`). | `python devtools/simulation/wildlife_optimizer.py --habitats 16` |
| [plants_wildlife_timeline.py](simulation/plants_wildlife_timeline.py) | Rough time model: Plants to the Wildlife unlock, then Plants and Wildlife sharing Forage. | `python devtools/simulation/plants_wildlife_timeline.py` |

Gitignored state: `headless/.cache/` (checkpoints, search runs, seed models).

## game_update/: after a new game build

Run these in the order given in [VERSIONCHANGE_TODO.md](../VERSIONCHANGE_TODO.md).

| File | What it does | Quick start |
|---|---|---|
| [split_docs_manual.py](game_update/split_docs_manual.py) | Splits a new in-game DOCS Manual export into `docs/`. | `python devtools/game_update/split_docs_manual.py` |
| [extract_game_spec.py](game_update/extract_game_spec.py) | Extracts API contracts and data tables into `tests/game_spec.json` (uses `extract_game_spec.js`). | `python devtools/game_update/extract_game_spec.py` |
| [simworker_diff.py](game_update/simworker_diff.py) | Diffs two decompiled simworker builds, ignoring minifier renames. | `python devtools/game_update/simworker_diff.py` |
| [build_docs/](game_update/build_docs/) | Optional: dumps docs and assets straight from the game executable into `docs/extracted/`. | `python devtools/game_update/build_docs/build_docs.py "<game dir>" docs/extracted` |

Gitignored state: `.simworker-diff/` (diff reports).

## Adding a tool

Put it in the folder that matches its purpose. Start the file with a docstring that says what it does and gives a few example command lines, and pass `description=__doc__` to argparse so `-h` shows that docstring. Add a row above. Add an entry in dev_workflow.md only for caveats that don't fit the docstring.
