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
- [x] Split it: `python devtools/split_docs_manual.py`
      Do **not** delete the split files (`docs/components/`, `docs/guide/`, ...) first: the
      script uses them as its routing template. Instead, read its routing report and check
      `git status docs/` for files it did not rewrite (a section the new manual dropped).
      An `UNROUTED` line is a new section with no file yet: create a stub with the matching
      header (component: `> **Category:** X | **Component Name:** Y`; guide: `## <Title>`;
      types: a `## <Name>` line in the right types file) and run the split again. Add new
      files to `docs/INDEX.md` and `docs/00_Table_of_Contents.md`.
## 3. Extracted docs, raw assets and decompiled simworker

- [ ] Delete the old outputs so no file from the old build survives:
      `Remove-Item -Recurse -Force docs\extracted, internals\raw_assets, internals\terraform_decompiled\simworker`
- [ ] Extract the docs bundle and dump the game assets (one run does both):
      `python devtools/build_docs/build_docs.py "C:\Steam\steamapps\common\CodeTerraform" docs/extracted --dump-assets internals/raw_assets`
      A `registry ... not found` error means the bundle's shape changed: ask Claude to adapt
      the patterns in `devtools/build_docs/build_docs.py` (tedious -> AI).
- [ ] Deobfuscate the simworker. Its file name changes between builds (`simWorker-<hash>.js`
      up to 3b1b03e, `simWorkerEntry-<hash>.js` since e1986ce):
      `npx webcrack (Get-Item internals\raw_assets\assets\simWorker*.js).FullName -o internals/terraform_decompiled/simworker`
      Check that exactly one `simWorker*.js` exists, and that the output has `deobfuscated.js`.
- [ ] Commit inside `internals/` (private repo), then bump the submodule pointer here.

## 4. Stubs and checks

- [ ] `npx pyright` and `python -m unittest discover -s tests` (stubs refreshed in step 2).

## 5. Hand over to Claude

- [ ] Ask Claude to update the devtools that depend on the simworker and check each one against
      the new build (dev_workflow.md §10c): `extract_game_spec.py` (review the
      `tests/game_spec.json` diff), `headless/simhost.mjs`, `game_speed.py`, `seed_quality.py`,
      `headless/field.mjs`, `swap_seed.py`.
- [ ] Ask Claude to walk through the changelog below and the docs diff for anything that affects
      our scripts, and to write the findings to `<new build>.md` at the repo root (same format as
      [3b1b03e.md](3b1b03e.md)).
- [ ] Clear the Changelog section below for the next build.

## Changelog
Experimental v0.1.30

- Important: once you open a save in this version, v0.1.29 and the default branch can no longer load it, so back up your save before switching if you might go back.
- The game is now available in Italian; choose it in Settings > Language. Many names in the other languages were also made consistent, so items, machines and buttons are called the same everywhere.
- New research: the Battery Charger charges loose Portable and Heavy Portable Batteries from the local grid and swaps them with a parked Pioneer, and its Mk II upgrade adds storage and a second charging bay.
- New research: Industrial Machinery Mk II and Mk III add Smelter and Fabricator upgrade packs, and Advanced Oil Extraction adds the Oil Pump Mk II pack and the Seismic Sonar.
- The Heat Generator Mk II pack research now unlocks at 40 heat units instead of 80.
- Saves are much smaller and autosaves are faster: console history is now kept in its own file next to the save instead of inside it.
- A long save or world load on a slower PC no longer ends the session, and a full disk is now named in the save error.
- On Linux, changing a setting no longer makes every later save fail.
- Scripts can show a short status message on their machine with set_status(message, level), clear it with clear_status(), and read any script's status with get_status_report().
- All your scripts can now open as tabs in one script editor window, which you can float, pop out into its own window or dock into the game.
- Typing in the editor no longer lags on large saves, and suggestions update after construction, pipes, power lines or wildlife change.
- Go to Definition now has Go Back, and jumping to code that is off screen centres it.
- The editor warns when a name you define hides a built-in or a game type.
- Mining sites and drills are linked for scripts through has_drill, drill_id and site.
- Vim mode can run startup commands set in Settings, such as mapping jk to leave insert mode.
- VS Code language tooling is now optional for each scripts folder.
- Separate editor windows now use your user_stubs.py for suggestions and checks.
- The Computer tabs are arranged in two full-width rows with icons, and the main menu has a Discord button.
- computer.deploy("pioneer", outpost) now places the vehicle at that outpost instead of outside it.
- unload_reagents() now moves whatever fits into the Bio Lab output instead of refusing until the output is empty.
- The autocomplete documentation box no longer flickers between two positions, and editor popups follow their window when it moves.
- Peek, Shop search inside a category, and each dashboard page's scroll position now behave as expected.
- A saved Signal Bus template can be sent from its own row.
- DOCS supports the mouse back and forward buttons, no longer shows a sell price for items the game will not buy, and says which machine settings reset when their script stops.
- Clicking Load Game again while saves are loading no longer restarts the list.
<!-- Paste the new build's changelog here. -->
