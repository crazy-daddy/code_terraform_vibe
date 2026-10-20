# Version Change TODO (operator checklist)

Steps for the operator on each new game build. Run from the repo root in PowerShell with the venv
active. Older builds' adoption notes live in `<build>.md` at the repo root (e.g.
[9f7a682.md](9f7a682.md)).

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
      files to `docs/00_Table_of_Contents.md`.
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

- [x] Ask Claude to update the devtools that depend on the simworker and check each one against
      the new build (stub_tests.md §10c): `extract_game_spec.py` (review the
      `tests/game_spec.json` diff), `headless/simhost.mjs`, `game_speed.py`, `seed_quality.py`,
      `headless/field.mjs`, `swap_seed.py`. Done when every §10c pass condition holds. Mostly
      pattern updates, fine for a cheaper model; it hands back anything a check can't settle.
- [x] Ask Claude to walk through the changelog below and the docs diff for anything that affects
      our scripts, and to write the findings to `<new build>.md` at the repo root (same format as
      [9f7a682.md](9f7a682.md)).
- [x] Some changes are NOT noted in the Changelog and thus require "discovery" in the code.
      Run `python devtools/game_update/simworker_diff.py` (after the `internals/` commit of step 3) and ask
      Claude to triage its report (`devtools/game_update/.simworker-diff/<old>_<new>.md`, dev_workflow.md
      §10c step 6) into the same `<new build>.md`.
- [ ] Clear the Changelog section below and all tickmarks above for the next build.

## Changelog
<!-- Paste the new build's changelog here. -->
Experimental v0.1.36

- Thai, Ukrainian, Turkish, Czech, Hungarian and Spanish (Latin America) can now be chosen in Settings under Language.
- Mk IV Oxygen, Heat and Pressure Generators produce 2.5 times as much, so the last stretch of the atmosphere needs far fewer machines and far less uranium.
- A Fuel Rod now lasts its full rated life, 10 days in a Mk IV machine; rods used to run out a little early, in Reactors too.
- A Reactor's core now reaches the temperature its heat setting asks for instead of stopping a couple of degrees short.
- When you fix a Library and apply it, the scripts its error had stopped start again with the fixed code, and the result lists them.
- In the editor, completion and hovers work on a Library object's attribute typed with another class of the same Library, even when your script doesn't import that class.
- In the Biology Lab, `self.specimen` shows the fragment, name, rarity and recipe of a specimen whose fragment is already cataloged, as a Bio Collector's cargo does; `extract()` still needs `analyze()` first.
- The Computer's Scripts tab shows a script's `set_status` text as it changes, without a filter change.
- The Power page's sections fold, like those of the Production and Storage pages, and a folded section still shows how many machines it holds and when one needs you.
- Script tabs can show the name you gave a machine, Control Room card or automation instead of its file name: Settings > Editor > Script tab names.
- Settings > Editor > Code Font also lists the monospace fonts installed on your computer.
- The Settings window widens to fit its tabs, so the tab row no longer scrolls.
- On Windows, the colony keeps running while the game is minimized and another program is busy; such a game could stop its simulation and fail to save.
- In Greek, Shop and Inventory in the sidebar and the Language setting show their Greek names instead of leftover test text.
- On Linux, typing through an XIM input method works again on installs that Steam updated from v0.1.34.