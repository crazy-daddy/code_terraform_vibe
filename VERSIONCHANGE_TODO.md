# Version Change TODO (operator checklist)

Steps for the operator on each new game build. Run from the repo root in PowerShell with the venv
active. Older builds' adoption notes live in `<build>.md` at the repo root (e.g.
[3b1b03e.md](3b1b03e.md)).

Before you start: stop `scripts_sync.py watch`, or set a hold, so nothing pushes while the docs and
stubs change.

## 1. Changelog

- [x] Paste the game's changelog for the new build into the **Changelog** section at the bottom of
      this file.

## 2. DOCS Manual and split docs

- [x] Delete the old monolithic export: `Remove-Item docs\Code-Terraform-DOCS-Manual-*.md`
- [x] In game, export the DOCS Manual into `docs/` (file `Code-Terraform-DOCS-Manual-<build>.md`).
- [x] Refresh the stubs first, because the split also rebuilds `docs/models/` from them: start
      the game once on the new build (it rewrites the save's `__builtins__.pyi`), then run
      `.venv/Scripts/python.exe devtools/scripts_sync.py resolve-preview`.
- [x] Split it: `python devtools/game_update/split_docs_manual.py`
      Do **not** delete the split files (`docs/components/`, `docs/guide/`, ...) first: the
      script uses them as its routing template. Instead, read its routing report and check
      `git status docs/` for files it did not rewrite (a section the new manual dropped).
      An `UNROUTED` line is a new section with no file yet: create a stub with the matching
      header (component: `> **Category:** X | **Component Name:** Y`; guide: `## <Title>`;
      types: a `## <Name>` line in the right types file) and run the split again. Add new
      files to `docs/INDEX.md` and `docs/00_Table_of_Contents.md`.
## 3. Extracted docs, raw assets and decompiled simworker

- [x] Delete the old outputs so no file from the old build survives:
      `Remove-Item -Recurse -Force docs\extracted, internals\raw_assets, internals\terraform_decompiled\simworker`
- [x] Extract the docs bundle and dump the game assets (one run does both):
      `python devtools/game_update/build_docs/build_docs.py "C:\Steam\steamapps\common\CodeTerraform" docs/extracted --dump-assets internals/raw_assets`
      A `registry ... not found` error means the bundle's shape changed: ask Claude to adapt
      the patterns in `devtools/game_update/build_docs/build_docs.py` (tedious -> AI).
- [x] Deobfuscate the simworker. Its file name changes between builds (`simWorker-<hash>.js`
      up to 3b1b03e, `simWorkerEntry-<hash>.js` since e1986ce):
      `npx webcrack (Get-Item internals\raw_assets\assets\simWorker*.js).FullName -o internals/terraform_decompiled/simworker`
      Check that exactly one `simWorker*.js` exists, and that the output has `deobfuscated.js`.
- [x] Commit inside `internals/` (private repo), then bump the submodule pointer here.

## 4. Stubs and checks

- [x] `npx pyright` and `python -m unittest discover -s tests` (stubs refreshed in step 2).

## 5. Hand over to Claude

- [ ] Ask Claude to update the devtools that depend on the simworker and check each one against
      the new build (dev_workflow.md §10c): `extract_game_spec.py` (review the
      `tests/game_spec.json` diff), `headless/simhost.mjs`, `game_speed.py`, `seed_quality.py`,
      `headless/field.mjs`, `swap_seed.py`. Done when every §10c pass condition holds. Mostly
      pattern updates, fine for a cheaper model; it hands back anything a check can't settle.
- [ ] Ask Claude to walk through the changelog below and the docs diff for anything that affects
      our scripts, and to write the findings to `<new build>.md` at the repo root (same format as
      [3b1b03e.md](3b1b03e.md)).
- [ ] Some changes are NOT noted in the Changelog and thus require "discovery" in the code.
      Run `python devtools/game_update/simworker_diff.py` (after the `internals/` commit of step 3) and ask
      Claude to triage its report (`devtools/game_update/.simworker-diff/<old>_<new>.md`, dev_workflow.md
      §10c step 6) into the same `<new build>.md`.
- [ ] Clear the Changelog section below and all tickmarks above for the next build.

## Changelog
<!-- Paste the new build's changelog here. -->
Experimental v0.1.34

- On Linux the game starts from Steam again: v0.1.33 waited about a minute and closed before the main menu when Steam launched it.
- The play, pause and stop buttons and the window buttons (minimize, maximize, close) are drawn icons, the same size on every system; on Linux the stop button had become a small square.
- The game now runs on a new engine on Windows and Linux. On Linux the Planet Map, the simulation and typing in the editor are much faster, most of all with NVIDIA graphics.
- Saves, settings, window layouts, your scripts folder, Steam Cloud and achievements carry over, and saves stay compatible with v0.1.32: each version opens the other's saves.
- If an earlier version closed with unsaved script edits waiting to be recovered, open that version (the default branch) to recover them before you switch: this version does not see them.
- The Linux settings for graphics acceleration, frame pacing and audio device wake-up, the Windows settings for graphics acceleration and the picture after Alt+Tab, and the launch options behind them are gone, because the new engine does not have those problems.
- On Linux, typing Chinese, Japanese or Korean through IBus or Fcitx works in every text field, separate windows included.
- On Linux the Steam overlay does not open over the game; the screenshot key still adds screenshots to your Steam library.
- Storms on the horizon, light breaking through after a storm and distant dust storms in the camera feed take a fraction of the computer's effort they used to, and the thunderstorm on the horizon has a new, more natural look.
- A print inside an operator method such as `__add__` no longer makes the other side of the operation run twice, or forever.
- A class defined inside a function keeps all of its attributes when the script pauses inside the class.
- `itertools.starmap` works with rows that are generators, even when a row prints or runs for a while.
- When a Library fails while it is being imported, `tracebat_exc()` show the Library's own lines.
- `from __builtins__ import Counter` (and `deque`, `defaults the real collections classes, so `isinstance` works withthem.
- Ctrl-clicking a name from a built-in module such as `math [sic. Message by dev ends here]