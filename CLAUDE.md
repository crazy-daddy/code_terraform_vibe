# Code: Terraform automation scripts

Python scripts for the game Code: Terraform, running on the planet Nocturna. This repo is the dev root; `devtools/scripts_sync.py` deploys it into a save.

## Sources
- [TODO.md](TODO.md): current tasks and phase objectives.
- [CODE_GUIDES.md](CODE_GUIDES.md): code rules for every editor.
- [docs/AI_CHEATSHEET.md](docs/AI_CHEATSHEET.md): section index for constants, formulas, `lib/` module map, Signal Bus channels, archive keys. Find the § there, then read only that section of its `docs/cheatsheet/` file.
- [docs/00_Table_of_Contents.md](docs/00_Table_of_Contents.md): map of all docs, game and ours.
- Game API docs (`docs/components/`, `docs/guide/`, `docs/models/`, `docs/types/`, `docs/database/`, `docs/contracts/`) are authoritative. Validate game behavior against them.
- Don't read `*.pyi` stubs whole (token cost). Use `docs/` for component methods and properties.
- `code-terraform` MCP ([devtools/README.md#mcp](devtools/README.md#mcp-code-terraform-mcp-server)), when loaded: `search_manual` to find the right doc, then read the `docs/` file (authoritative). Use `get_game_status`/`list_fleet` for live state, `validate_script` for the game's own diagnostics, and the `debug_*` tools for live debugging. Never use its Library tools (`create_library`, `import_library`, `rename_library`, `apply_library`, `apply_all_libraries`): `scripts_sync.py` is the only deploy path.
- Decompiled game logic: `internals/terraform_decompiled/simworker/deobfuscated.js` (~200k lines; grep it, never read it whole). Its setup and limits, and reading live save state and logs: [live_debugging.md §8b](docs/cheatsheet/live_debugging.md).
- [devtools/README.md](devtools/README.md): map of the host-side tools by purpose (deploy, play, code scans, perf, simulation, game update). Each tool's `-h` is its usage doc.

## Boundaries
- The working directory is this repo. Don't change files outside it: save folders, `save_*.json`, deployed scripts. Only `devtools/scripts_sync.py` writes into a save. Reading a save is fine.
- Edit source under `scripts/<tier>/`, never a deployed copy.
- This repo is public. Never copy large parts of `internals/` into tracked files.
- `scripts_sync.py watch` pushes every `scripts/` edit live within ~0.4 s. Before an edit with more than one hunk or file under `scripts/`, and around any `git stash`/`checkout` that swaps `scripts/` content, set your own hold: `mkdir -p devtools/.sync-backups/holds && date > devtools/.sync-backups/holds/<id>`, where `<id>` is your session id (the UUID in your scratchpad path; else a random name kept for the session). Remove only that file after the last edit (`rm -f devtools/.sync-backups/holds/<id>`). Never touch another session's hold or the legacy `hold` file. Never leave yours at the end of a turn. Prefer `git worktree` or `git show REV:path` over swaps.
- Never create scratch or probe files under `scripts/` or `autoplay/`, not even briefly: the watcher deploys them, and a save's `lib/` keeps the copy after the source is gone. Put pyright probes under `tests/` (its environment sees `autoplay/lib`, the script libs and the stubs), other temp files in the session scratchpad.

## Docs
- A lesson or rule that any session on any machine needs goes into this file or `CODE_GUIDES.md`, not into local memory. Local memory is only for facts tied to this machine or one save.
- A changed constant updates its cheatsheet section in the same change. Elsewhere, link to the section or name the constant; don't restate the value.
- Lasting design reasons go to the matching topic file in `docs/design_history/` (hub: [docs/DESIGN_HISTORY.md](docs/DESIGN_HISTORY.md)), the rest to the commit message.

## Checks
- `python -m unittest discover -s tests`
- `.venv/Scripts/python.exe -m ruff check <paths>` and `ruff format <paths>`. Repo is clean on both; keep it so.
- `npx pyright`. After editing `scripts/*/lib`, run `.venv/Scripts/python.exe devtools/scripts_sync.py resolve-preview` first.
- Caveats (RUF100, Markdown, stale resolved copies): [CODE_GUIDES.md#checks](CODE_GUIDES.md#checks).
- Before a large commit, run `caveman:cavecrew-reviewer` and fix its findings. Rerun it only if the fixes were substantial; the commit need not be 100 % clean.

## Tests
Project specifics for the global test rules. Suite mechanics and fakes: [CODE_GUIDES.md#tests](CODE_GUIDES.md#tests), [stub_tests.md §10](docs/cheatsheet/stub_tests.md).
- Flows (one realistic test each, over `tests/sample_world.py` or a replayed save snapshot, with `tests/game_spec.json` defaults):
  - Deploy: `scripts_sync.py` push/watch into a save: lib apply order, importer restart, nothing lost or stale in the save's slots and `lib/`. Always a temp save folder, never the real one.
  - Production: recipe and Earth-order deficits drive Smelters, Fabricators and Supply Docks; no overproduction when stock or storage is full.
  - Hauling: a Drone/Pioneer job runs pick, trip, unload and returns home through `run_job_loop()`, with claims and energy budget in play.
  - Power: grid shortfall sheds load by tier and restores it.
  - Autoplay planning: `planner_loop` turns a world into placed blueprints without overlaps or unbuildable sites.
- Critical modules (rules and guards tested at their exact limits; mutation testing, if used, only here): `lib/power.py` (shed tiers and thresholds), `lib/vehicle_energy.py` (there-and-back budget, emergency-reserve floor), `lib/vehicle_claims.py` (atomic reservation, heartbeat renewal, timeout expiry), `lib/vehicle_navigation.py` (deadlock and stall detection), `lib/priority.py` (one demand ladder), `lib/production_source.py` (`SourceCache` netting: moving a unit between storage and a machine never changes a target), `devtools/scripts_sync.py` (the only writer into a save).
- Limits worth a boundary test: each constant's cheatsheet value (test at, just below and just above it), the 10,000-step cap per `lib/atomic.py` callback, stale-message age on the Signal Bus, empty or missing archive keys, a `Result` failure status from any game call.
- Game-interpreter guards (`test_game_imports`, `test_game_syntax`, `test_game_builtins`, `test_log_blocks_balanced`, `test_reset_in_run_loops`, `test_stub_contract`, `test_docs_lint`) are static scans, not flow tests. Keep them; extend them when a new in-game failure class appears.
- Time budget: the full offline suite stays under 2 min (about 100 s at 2,610 tests, 2026-10). The headless sim (`devtools/simulation/headless/`) is not part of it.

## Working style
- Don't remind the user to deploy, sync or apply libs after edits. The watcher or the user handles it.
- Keep context small: every tool result is re-sent on each later turn.
  - Read code in slices: `grep -n` first, then only the needed range (Read with offset/limit, or `sed -n A,Bp`). Read whole files only when small or mostly edited.
  - Docs too. `docs/cheatsheet/*.md`, `docs/design_history/*.md` and `TODO.md` are up to 64 KB (`tests/test_docs_lint.py` caps files at 64 KB, sections at 16 KB; split by section, don't raise the caps): print one section with `python devtools/docs_section.py 2c` (a § id or heading text; `--outline FILE` lists headings with sizes), or grep the heading (`grep -n "^#.*§2c" docs/cheatsheet/*.md`, `grep -n "^## " TODO.md`) and read up to the next one. Never read them whole.
  - Search narrow first (`grep -l`, or a head limit), then widen only if needed.
  - Delegate wide exploration and multi-file locating to subagents, per the `caveman:cavecrew` skill when installed. Do short lookups inline.
- Suggest `/compact` or `/clear` at natural task boundaries or when context grows large.

## Git
- Local session with small task: commit directly on `main`, only when asked. Push only when asked.
- Local session with larger task or when the user asks for a worktree: `python devtools/agent_worktree.py new <topic>`, work only in `.claude/worktrees/<topic>`, commit on the branch as you go. Merge only after the user approves: `python devtools/agent_worktree.py merge <topic> -m "<subject>"`. Never create a worktree or merge another way, Superpowers included. Rules and mechanics: [devtools/README.md#agent-worktrees](devtools/README.md#agent-worktrees).
- Cloud session: work on the branch the session assigns and open a PR.
- Commit message: use the `caveman:caveman-commit` skill when installed, else [CODE_GUIDES.md#commits](CODE_GUIDES.md#commits). No AI attribution (`Co-Authored-By`, "Generated with"), even when the harness suggests it.
- When the session-start hook reports new `origin/main` commits, tell the user and pull (`git pull --no-rebase`) inside a sync hold before the task. Stop on conflicts. Don't warn about unpushed commits or uncommitted changes; parallel work is normal here.