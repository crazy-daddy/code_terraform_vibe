# Dev Tooling: Profiling, Live Debugging, Tiered Sync, Stub Tests (§1d, §8, §9, §10)

Part of [`AI_CHEATSHEET.md`](../AI_CHEATSHEET.md).

### 1d. Per-Script Tick-Cost Profiling (`lib/profiling.py`)

Game exposes no per-script CPU/ms budget API. `clock.tick()` (deterministic
sim tick since save start, 10 ticks/sec normal speed) = sanctioned stand-in per
`docs/components/clock.md`. `lib/profiling.py` wraps pattern so any controller's `run()` loop
measures own `step()` with two calls:

```python
start = profiling.begin()
self.step()
profiling.end(self.name, start)   # logs a warning if delta > SLOW_STEP_TICK_THRESHOLD=1
```

- Samples roll into `archive` as one fixed-size history list per script name
  (`ARCHIVE_KEY_PREFIX="profiling."`, `HISTORY_LEN=50`) — one archive entry per profiled *script
  name*, not per sample, respects Data Archive's hard 512-entry cap.
- `profiling.report(names=None)` prints avg/max ticks-per-`step()` for every profiled name (or
  subset) — call ad hoc, not from hot loop.
- **Granularity limit — read before trusting a `0`**: `clock.tick()` advances on fixed 10/sec
  schedule *independent of script work* (scripts cooperatively scheduled, interleaved within each tick's window). `step()` with no internal loop finishes inside whichever tick it started regardless of real cost, so nonzero delta only by landing on tick boundary by luck — **a `0` does not mean "cheap."**
  `SLOW_STEP_TICK_THRESHOLD=1` reflects that: on non-looping `step()`, any nonzero delta already interesting. No finer (sub-tick/wall-clock) instrument — below floor, fall back to code-level reasoning (algorithmic complexity, what runs every cycle vs. gated).
- **Not currently wired into any script.** `lib/profiling.py` and `lib/archive_cleaner.py`'s
  cleanup of it kept for future script suspected of real bulk per-call work.
- **Storage shape & cleanup**: each archive entry `{"history": [...], "last_tick": N}`.
  `lib/archive_cleaner.py`'s `clean_profiling()` purges entry whose `last_tick` not advanced
  in `PROFILING_STALE_TICKS=6000` (10 sim minutes, "instrumentation removed"), always purges
  legacy bare-list entries. Runs in
  `ArchiveCleaner.run()`'s normal sweep.

## 🐞 8. Live Debugging via External IDE

Game exposes real Debug Adapter Protocol (DAP) integration against actual running game interpreter, not simulation: breakpoints, conditions, logpoints, call stacks, locals, watches, hover inspection, Step Over/Into/Out. Setup + full details:
`C:\Users\Adrian\AppData\Roaming\io.codeterraform.game\external-ide\README.txt`.

- **VS Code** (supported path, extension already installed this save): open script, set breakpoint, press **F5**. Idle script starts running; already-running script attaches without restart. **Shift+F5** or closing debug session disconnects but leaves script running in game. Use **Stop Script in Game** to actually stop. Watches/Debug Console **read-only** (can't execute world actions or assign variables). Edited main-script code needs **Run Script in Game** before re-attaching; edited Libraries need re-applying in game.
- **Any other DAP-capable editor**: launch
  `node "C:\Users\Adrian\AppData\Roaming\io.codeterraform.game\external-ide\server\debug-adapter.cjs"`
  (Node.js 20+, stdio transport). `launch` = attach-and-run idle script; `attach` = inspect already-running one. Set `workspace` to this save's scripts directory, `script` to target file.
- **Non-debug editor tooling** (LSP-only, no execution): `external-ide\server\server.cjs --stdio`. Per-editor docs (neovim/Helix/Sublime) in README. PyCharm needs generic LSP plugin; its own Python checker doesn't know game's owner globals/runtime rules.
- Console output mirrors to `external-ide\logs\all.log` (plus one file per script). Useful to tail even without debugger.
- **`devtools/dap_client.py`**: minimal DAP client for driving debug session from script instead of VS Code. Needs Node.js 20+; this save's copy at `C:\Program Files\nodejs\node.exe`, not on default shell `PATH`. Invoke by full path, or `export PATH="/c/Program Files/nodejs:$PATH"` for current shell session only (shell state doesn't persist between tool calls here). Vendored into `devtools/` (not imported from the standalone `early_game_runner/` project). `devtools/scripts_sync.py` only consumer. `DapClient` = low-level stdio transport (Content-Length framing, background reader thread). `run_session(workspace, script, breakpoints,
  mode, on_stopped, wait_timeout)` wraps full initialize → attach/launch → setBreakpoints → configurationDone → wait-for-`stopped` → callback → continue → disconnect sequence in one call.
  Also runnable directly: `python devtools/dap_client.py --workspace <dir> --script <path> --break
  <file.py>:<line> [--mode attach|launch]`. Prints stack trace + top-frame locals at first hit, then resumes and disconnects.
  - **`launch` starts idle scripts without breakpoints**: `dap_client.launch_script(workspace, script)`
    (or CLI `python devtools/dap_client.py --workspace <dir> --script <path> --launch`) sends `initialize` →
    `launch` → `configurationDone` with no breakpoints set, triggering `{ action: "start", runIfIdle: true }`
    in `debug-adapter.cjs`. It then cleanly disconnects with `terminateDebuggee=False`, leaving the freshly-started
    script running in the live game.
  - **Does NOT force-restart already-running script**: `runIfIdle: true` is exactly that:
    a script already running just gets attached-to (per `debug-adapter.cjs`'s own `configurationDoneRequest`),
    its old in-memory code untouched. There is no `supportsRestartRequest` capability advertised by
    `initialize`, and the base `DebugSession`'s `restartRequest`/DAP `restart` is an unimplemented no-op
    stub in the concrete session class too.
  - **General external-command channel** (`.codeterraform/command.json`/`command-result.json`/
    `command.lock`, distinct from the debug bridge's own `debug-command.json`/`debug-result.json`) is what
    "Run Script in Game"/"Create Library in Game"/etc. (VS Code commands in `extension.cjs`, not
    `debug-adapter.cjs`) use. Request:
    `{"version":1,"requestId":"<uuid>","issuedAt":<epoch_ms>,"session":{"id":..., "generation":1} (read
    live from codeterraform-workspace.json),"action":"run","scriptId":"<script id>","source":"<full
    script text>"}`, written via the same atomic-write + `command.lock` (staleness >30s, `wx`-create,
    35s acquire budget) protocol as the debug bridge's `H.send()`, then polled from `command-result.json`
    for `{"requestId":..., "ok": bool}` (10s timeout). `"action":"run"` force-restarts an already-running
    script with its own new code.
  - **No external way to apply a changed `lib/` module.** The game caches an imported library
    independently of the importing script, so restarting the importer runs the stale copy. Only the
    in-game Script Editor's **"Apply & restart all"** button invalidates that cache, and it has no
    external hook (not in `debug-adapter.cjs`, `extension.cjs` commands, or the command channel).
    **Net effect**: `devtools/scripts_sync.py` restarts pushed scripts over this channel, but **cannot**
    make a running script pick up a changed `lib/` module. What the game runs per Library is visible:
    `context.libraryScripts[*].deployedSource` in `codeterraform-workspace.json` (`libs_awaiting_apply()`).
- **Automated Script Deployment (`early_game_runner/auto_deploy.py`)**:
  - Auto-bridges newly placed/deployed hardware (via in-game `computer.deploy(...)`) to host-side Python controller scripts.
  - **Dual-Channel Monitoring**:
    - Watches `logs/all.log` for explicit `[DEPLOY]` lines with arbitrary parameter assignments (e.g. `[DEPLOY] machine_id=pioneer_5 template=pioneer_hauler HOME_BASE="outpost_3"`).
    - Periodically scans `codeterraform-workspace.json` for newly registered machines whose script slots are idle and unpopulated.
  - **Template Directory (`early_game_runner/templates/`)**:
    - Stores modular templates (e.g., `solar.py`, `heater.py`, `smelter.py`, `pioneer_hauler.py`).
    - Supports flexible parameter substitution: `${PARAM:default_value}` or `{PARAM}`.
    - Built-in variables automatically injected: `MACHINE_ID`, `TYPE_ID`, `LOCATION_ID`.
  - **CLI Modes**:
    - `python early_game_runner/auto_deploy.py --scan`: One-shot scan and deploy for all unscripted idle machines.
    - `python early_game_runner/auto_deploy.py --scan --dry-run`: Preview generated script code and parameters without modifying disk or launching.
    - `python early_game_runner/auto_deploy.py --daemon`: Continuous background watcher loop.
    - `python early_game_runner/auto_deploy.py --deploy <machine_id> [--template <name>] [--param KEY=VALUE ...]`: Targeted single-machine deployment.

**Before starting any debug session (F5/`launch`/`attach`) or using **Run Script in Game**:
If running user's main save (save_mtzkzly3_4ww80o): ask user first, every time. Never assume standing permission from prior yes.** Debug session runs against live save with real effects: script that spends credits, moves vehicle, fires drill, etc. does so for real, no sandbox. Pausing at breakpoint can also leave machine mid-action in state player didn't intend. Treat like any other action with real-save side effects per project's risk-awareness rules, not routine read-only inspection.
Other (throwaway) saves: can be more liberal, especially when developing auto-play tools like `early_game_runner/auto_deploy.py`, `early_game_runner/early_game.py`, etc.

## 🧬 9. Dev Workflow: Tiered `scripts/` + `devtools/scripts_sync.py`

Repo (`C:\Users\Adrian\Code_Terraform`) = dev root, separate from live save folder (`%APPDATA%\io.codeterraform.game\save_*_scripts`). Source of truth: `scripts/<tier>/<category>/<name>.py`. `devtools/scripts_sync.py` (adapted from `inspirations/vakermit/bin/ct_sync.py`) pushes it into the save folder's numbered script slots and mirrors `lib/`. One direction only: no pull from the game. Full mechanics (push/restart, renumbering, `_unmatched/` staging) in tool's module docstring. This section covers project-specific tiering layer on top.

**Tier list**: not hardcoded. `discover_tiers()`/`tier_number()` in `scripts_sync.py` scan `scripts/` for `<N>_<anything>` dirs, sort by `N` ascending (numeric, so `10_x` after `9_x`, not between `1_x`/`2_x`). Only number matters, rest of name free text. Numbers may skip. Add `scripts/6_derp/` (or `scripts/3_inbetween/` between two existing tiers) with own `.criteria` → picked up automatically, no code change. Dir starting with digit but not plain `<int>_...` (`1N3_DERP`), or two dirs claiming same number (`10_hi`/`10_ho`) → raise `TierNamingError`, no silent guessing. Each tier gated by `.criteria` file at root (absent for `0_cold_boot`, always-active baseline). Current tiers:

| Tier | `.criteria` | Unlocks (tech id / `research_*` id) |
| :--- | :--- | :--- |
| `0_cold_boot` | *(none — baseline)* | — |
| `1_early` | `{"tech": ["ship_computer"]}` | `research_computer` |
| `2_libunlock` | `{"tech": ["shared_library"]}` | `research_shared_library` |
| `3_archiveunlock` | `{"tech": ["data_archive_unlock"]}` | `research_data_archive` |
| `4_controlpanel` | `{"tech": ["custom_panels_unlock"]}` | `research_custom_panels` |
| `5_steampower` | `{"buildings": {"thermal_cap": 2, "steam_turbine": 5}}` | built steam power (no tech gate) |
| `6_seeds` | `{"buildings": {"seed_maker": 1}}` | deployed Seed Maker (`research_seed_maker`, Biomass 500) |
| `7_miningdrills` | `{"buildings_any": {"mining_drill": 1, "mining_drill_industrial": 1, "mining_drill_heavy": 1}}` | first deployed Mining Drill of any variant (standard / Industrial / Heavy) |
| `8_planting` | `{"plant_recipes": 15}` | all 15 seed recipes discovered (`state.planet.plants.discoveredRecipes`); needs `7_miningdrills` met too (ascending chain) |

`.criteria` keys use save file's own **tech ids** (from `state.unlockedTech`), not `research_*` ids from `docs/database/research_catalog.md`. Table above = mapping. Supported keys: `"tech": [id, ...]` (all must be present), `"outpost_count": N` (`len(state.planet.outposts) >= N`). `"plant_recipes": N` (`len(state.planet.plants.discoveredRecipes) >= N`). `"buildings": {typeId: N, ...}` (each type's count in `state.machines[*].typeId` >= N; finished machines only; pending `constructionBlueprints` and `isUnderConstruction` machines not counted). `"buildings_any": {typeId: N, ...}` (OR-group: at least one listed type's count >= N; used for "any Mining Drill variant"). Map-deployed buildings (drills included) appear in `state.machines` like any other machine, so both building keys see them; entries still `isUnderConstruction` are **not** counted (only finished deployments). TP-threshold criteria not supported (no TP field known in save state).

**Active-tier resolution**: fully automatic, per-save. `scripts_sync.py` derives sibling save-state file from save-scripts dir name (`save_X_scripts/` → `save_X.json`, one level up), reads `state.unlockedTech` / `state.planet.outposts` **read-only**, walks numerically sorted tier list evaluating `.criteria` until one fails. Highest passing tier = active. No hint file, no manual bookkeeping. `--force-tier NAME` overrides for one run, persists nothing. **Assumes monotonic unlocks**: walk stops at first tier whose `.criteria` unmet, so ancestor criteria implicitly required. Out-of-order save (higher tier's `.criteria` satisfied before lower one's) not handled specially. Not expected (techs never "unlearned"), but assumption flagged.

**No duplicate files across tiers**: for given `category/base_name` (incl. `lib` category), resolver walks from active tier down to `0_cold_boot`, uses first file found. Higher tier needs own copy only when behavior genuinely diverges.

**lib/ from `2_libunlock` on = every module of every tier** (`lib_chain()`, `LIB_UNLOCK_TIER_NUMBER = 2`): after the active tier's chain, the resolver also walks every HIGHER tier (ascending). A module defined at or below the active tier resolves through the normal chain, so a higher tier's override of an existing module stays gated (today only `5_steampower/lib/power.py`). A module that only exists in a higher tier is deployed anyway (idle until its machines exist) — so entrypoints never need a per-tier copy just to import a newer lib (e.g. the Mixer gate idles inside the single `automation_panel.py`). Pyright's `.pyright-resolved/lib` uses the same chain.

**Library registration hook** (`register_new_libraries()`, runs after every lib mirror in `once`/`watch`; standalone `python devtools/scripts_sync.py register-libs [--dry-run]`): a file written into the save's `lib/` is **not** seen by the game until it is registered as a Library (manually: Computer → Library → + New, same name — the game then picks up the file on disk). The hook does the same as VS Code's **Import File as Game Library**: `action: "create-library"` with `name` (module stem) and `source` over the external-command channel (§8: `.codeterraform/command.json` + `command.lock` + `command-result.json`, `session` from `codeterraform-workspace.json`), for every deployed module missing from `context.libraryScripts`. Needs the game running with the save open; otherwise it warns and the next sync retries. `duplicate_name` counts as already registered. Source limit 200,000 chars (`interpreter.maxSourceLength`). It only registers new modules; applying a *changed* registered lib still needs the in-game "Apply & restart all" (§8).

**Global (untiered) categories**: category dir directly under `scripts/` (sibling of tier dirs, e.g. `scripts/contract/`) not gated by any `.criteria`. Always included, merged on top of active tier resolution (`list_global_categories`/`resolve_global_category` in `scripts_sync.py`). Contracts live here: genuinely tech-independent, self-contained (no imports), available from very first save, not tied to any progression tier.

**`panel` = role-matched slot type** (`ROLE_MATCHED` in `scripts_sync.py`). Sources at `scripts/4_controlpanel/control_panel/<role>_panel.py`: separate, genuinely different hand-authored Control Room cards (§7), not interchangeable template copies. The game picks `panel_N` slot numbers per save and can't rename them, so a live slot is paired with its source by role (`role_for_slot()`), in this order: (1) `# ct-panel: <role>` marker in the slot's code (`_panel` suffix optional; every source carries it on line 1, so every filled slot has it); (2) slot's first comment line equal to a source's first comment line after the marker (bridges slots filled before markers existed); (3) an **empty** slot takes the one role no other `panel_*` slot holds yet. Several unpaired roles → skipped with a warning; type `# ct-panel: <role>` into the slot in game to choose. A marker naming no source is reported, not guessed past. Role-matched slots are never staged to `_unmatched/`. A role source is any resolved script whose stem ends in `_panel`.

**Pyright/IntelliSense**: `pyrightconfig.json`'s `extraPaths` point at `.pyright-resolved/lib` (regenerate with `python devtools/scripts_sync.py resolve-preview`, gitignored) plus live save folder for game-API stubs. Modules that only exist in a higher tier resolve too from `2_libunlock` on (`lib_chain()`); only a higher tier's *override* of an existing module needs `resolve-preview --force-tier <name>` to preview. Game's own in-editor syntax highlighting/autocomplete (tied to `codeterraform-workspace.json`) doesn't apply to source outside save folder at all → check deployed copy in save folder when needed.

**Push + restart** (`once`/`watch`, `sync_file()`): every save slot with a match is overwritten with its resolved source (placeholders rendered, own id renumbered) whenever the two differ; old copy backed up to `devtools/.sync-backups/`. In-game edits to a matched slot are therefore reverted — edit in `scripts/`. A slot with code and no match is left alone; an empty one with no match is staged to `scripts/_unmatched/`. After a write, `restart_in_game()` sends `"action": "run"` (§8) with the new source if the slot's workspace `status` is `running` or the slot was just filled from empty; retries `RESTART_RETRY_DELAYS_S = (0.5, 1.0, 2.0)` (~3.5s) while the game hasn't registered a new slot yet. **No restart when the script reaches an unapplied lib**: `libs_awaiting_apply()` = resolved `lib/` modules whose source differs from the game's `deployedSource` (or with no Library yet); `libs_reached()` walks the script's import closure (`lib_dependency_closure()`, `ast`-parsed). A hit is still pushed, reported as needing in-game **Apply & restart all** (restarting it would run new script code against the stale cached lib). `report_unapplied_libs()` prints the full list of affected save scripts once per change (`watch` re-checks every 5 s, so an in-game Apply clears it). `--no-restart` pushes only. `status` shows per slot: up to date / would fill / would push, and blocking libs. Restarts are operator-invoked automation (the operator runs the tool), not Claude starting a live session; CLAUDE.md's Live Debugging rule binds Claude's own actions, so Claude still asks before running `once`/`watch` without `--no-restart`.

**Parameterized templates** (`${VAR}` / `${VAR:default}` in source script; same syntax as `early_game_runner/auto_deploy.py`'s placeholder substitution — keep identical): `sync_file()` detects via `find_placeholders()`, resolves each per save slot from: retired push-hauler `DESTINATION_OUTPOST_ID` re-homing (`rehome_retired_destination()`, §2f; beats the slot code and cache) → value the slot's current code holds at the placeholder's position (`infer_placeholders()`: template line → regex, placeholder → capture; an in-game edit wins and overwrites the cached answer) → cached answer (used when the template line changed so inference misses) → template default if the slot already has code (code predating a placeholder never set it) → interactive prompt (`typer.prompt`, blocking) for an empty slot. E.g. `scripts/4_controlpanel/pioneer/pioneer.py`'s `HOME_BASE`/`CRUISE_THROTTLE`, asked once per slot (`pioneer_2.py`, `pioneer_3.py`, ... each independently) so operator sets where each specific Pioneer goes. Answers cached in `devtools/.sync-backups/script_params.json` (gitignored, keyed by `<save dir name>/<slot filename>`) → re-filling same slot doesn't re-ask. `--dry-run` never prompts or caches. Blocks under `watch` too, no skipping: filesystem observer runs on own thread, queues further events into `Watcher.pending`/`repo_due` while main thread waits on `input()`. Nothing lost, only delayed until answered (or `Ctrl-C`, still raises cleanly through `input()`). **Fleet-upgrade replacement drones never prompt** (`upgrade_fill_for()`/`inherit_placeholders()`): a `drone_*` slot named in `fleet.upgrade.lineage`, or a new drone slot whose machine `typeId` matches the single `announced`/`swapping` swap's `target_kind`, is filled with the old slot's cached answers → the old drone's archived `params` → template defaults, in every mode . Read from the save file (`read_save_state()` also returns `machine_types` and `fleet_upgrade`). A new `drone_*` slot whose machine isn't in the save yet is **held** (autosave lag) and retried every 5 s by `watch` (`HELD_SLOTS`); `once` reports it and fills on a later run. Wrong `typeId` (hand-deployed) → normal prompt. **COMMISSION card deploys never prompt either** (§2k-2): a `drone_*` slot whose `fleet.upgrade.lineage` entry has `job` (no `from`) is filled from its `params` (`HOME_DEPOT`); a `pioneer_*` slot named in `fleet.commission.lineage` gets `HOME_BASE` = its `home_base` (`commission_fill_for()`; `read_save_state()` also returns `fleet_commission`). A new `pioneer_*` slot is held only while the save predates its machine and a Pioneer job is `deploying`.

## 🧪 10. Stub Tests (`tests/`)

Offline `unittest` suite for the production modules (`production.py`, `storage.py`, `smelter.py`, `fabricator.py`, `supply_dock.py`, `site_supply.py`, `site_plan.py`), no game needed. Run from repo root: `python -m unittest discover -s tests` (stdlib only).

- `tests/game_stubs.py`: fake world (`World`): outposts (`OutpostRef`, `.is_home` bool, `buildings(type_id)`), home Inventory, Warehouses, Smelters, Fabricators (recipes, input/output buffers, `running` flag), Supply Docks and Earth Orders (`add_supply_dock()`, `add_order()`, `orders` service; nothing ships), notebook (`transaction()`), clock, console. Port locality per docs: `"inventory"` connects at home only, a remote port reaches only its own outpost's storage (`"not_local"` otherwise). Nothing crafts by itself; a test sets buffers/stock/`running` and calls a controller method.
- `tests/harness.py`: installs `get_component`/`sleep` builtins, puts every tier's `lib/` on `sys.path` like the sync resolver's `lib_chain()`: `TEST_TIER = 4` down to 0 first, then higher tiers ascending (so a tier-5-only module like `site_supply.py` imports), resets module state per test (`archive.archive.notebook`, `storage._recent_busy`, `swallow` dedupe, module `TreeConsole`s). `StubTestCase` fails any test during which `swallowed()` reported a bug-class exception.
- Test files per module (`test_production.py`, `test_smelter.py`, `test_fabricator.py`, `test_site_supply.py`, `test_factory_sites.py` for per-site targets, the site plan, consumer hauling, stranded ore eviction and remote docks), home and remote-outpost cases.
- Pyright: `pyrightconfig.json` has a `tests` environment resolving lib imports via `.pyright-resolved/lib`, falling back to `scripts/4_controlpanel/lib`.
