# Code: Terraform automation scripts

Python scripts for the game Code: Terraform, running on the planet Nocturna. This repo is the dev root; `devtools/scripts_sync.py` deploys it into a save.

## Sources
- [TODO.md](TODO.md): current tasks and phase objectives.
- [CODE_GUIDES.md](CODE_GUIDES.md): code rules for every editor. Read the matching section before editing code.
- [docs/AI_CHEATSHEET.md](docs/AI_CHEATSHEET.md): constants, formulas, `lib/` module map, Signal Bus channels, archive keys. Read the hub's section index, then only the `docs/cheatsheet/` file you need.
- Game API docs ([docs/00_Table_of_Contents.md](docs/00_Table_of_Contents.md), `docs/components/`, `docs/guide/`, `docs/models/`) are authoritative. Validate game behavior against them.
- Don't read `*.pyi` stubs whole (token cost). Use `docs/` for component methods and properties.
- Decompiled game logic: `internals/terraform_decompiled/simworker/deobfuscated.js` (~200k lines; grep it, never read it whole). Setup and limits: [dev_workflow.md §8b](docs/cheatsheet/dev_workflow.md).
- Reading live save state and logs: [dev_workflow.md §8b](docs/cheatsheet/dev_workflow.md).

## Boundaries
- The working directory is this repo. Don't change files outside it: save folders, `save_*.json`, deployed scripts. Only `devtools/scripts_sync.py` writes into a save. Reading a save is fine.
- Edit source under `scripts/<tier>/`, never a deployed copy.
- This repo is public. Never copy large parts of `internals/` into tracked files.
- In the user's main save, ask every time before a debug session, "Run Script in Game", `scripts_sync.py --apply-libs`/`apply-libs`, or a sync that restarts scripts. Each runs real side effects in the live save. A previous yes doesn't carry over. In other (throwaway) saves, no need to ask. Local memory names the main save; when unsure which save is active, treat it as the main save.
- `scripts_sync.py watch` pushes every `scripts/` edit live within ~0.4 s. Before an edit with more than one hunk or file under `scripts/`, and around any `git stash`/`checkout` that swaps `scripts/` content, set your own hold: `mkdir -p devtools/.sync-backups/holds && date > devtools/.sync-backups/holds/<id>`, where `<id>` is your session id (the UUID in your scratchpad path; else a random name kept for the session). Remove only that file after the last edit (`rm -f devtools/.sync-backups/holds/<id>`). Never touch another session's hold or the legacy `hold` file. Never leave yours at the end of a turn. Prefer `git worktree` or `git show REV:path` over swaps.

## Docs
- A changed constant updates its cheatsheet section in the same change. Elsewhere, link to the section or name the constant; don't restate the value.
- Lasting design reasons go to [docs/DESIGN_HISTORY.md](docs/DESIGN_HISTORY.md), the rest to the commit message.

## Checks
- `python -m unittest discover -s tests`
- `npx pyright` (config: `pyrightconfig.json`)

## Git
- Local session: commit directly on `main`, only when asked. Push only when asked.
- Cloud session: work on the branch the session assigns and open a PR.
- Commit message: use the `caveman-commit` skill when installed, else [CODE_GUIDES.md#commits](CODE_GUIDES.md#commits). No AI attribution (`Co-Authored-By`, "Generated with"), even when the harness suggests it.
- When the session-start hook reports new `origin/main` commits, tell the user and pull (`git pull --no-rebase`) inside a sync hold before the task. Stop on conflicts. Don't warn about unpushed commits or uncommitted changes; parallel work is normal here.
