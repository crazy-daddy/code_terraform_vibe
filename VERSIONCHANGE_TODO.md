# Version Change TODO (operator checklist)

Steps for the operator on each new game build. Run from the repo root in PowerShell with the venv
active. Older builds' adoption notes live in `<build>.md` at the repo root (e.g.
[fe9a45c.md](fe9a45c.md)).

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

- [x] Ask Claude to update the devtools that depend on the simworker and check each one against
      the new build (dev_workflow.md §10c): `extract_game_spec.py` (review the
      `tests/game_spec.json` diff), `headless/simhost.mjs`, `game_speed.py`, `seed_quality.py`,
      `headless/field.mjs`, `swap_seed.py`. Done when every §10c pass condition holds. Mostly
      pattern updates, fine for a cheaper model; it hands back anything a check can't settle.
- [x] Ask Claude to walk through the changelog below and the docs diff for anything that affects
      our scripts, and to write the findings to `<new build>.md` at the repo root (same format as
      [fe9a45c.md](fe9a45c.md)).
- [x] Some changes are NOT noted in the Changelog and thus require "discovery" in the code.
      Run `python devtools/game_update/simworker_diff.py` (after the `internals/` commit of step 3) and ask
      Claude to triage its report (`devtools/game_update/.simworker-diff/<old>_<new>.md`, dev_workflow.md
      §10c step 6) into the same `<new build>.md`.
- [ ] Clear the Changelog section below and all tickmarks above for the next build.

## Changelog
<!-- Paste the new build's changelog here. -->
- Greek, Polish and Traditional Chinese can now be chosen in Settings under Language.
- On Linux, the game now starts when Steam is installed from the Snap Store on a Wayland desktop; it used to close about three seconds after Play without opening a window.
- On Windows, on PCs where the game closed at start without ever drawing anything, it now asks you to start it once more and then runs normally there.
- On Windows, clicks no longer go through the game to the window behind it while Razer Cortex is running.
- On Linux, closing a script by middle-clicking its tab no longer pastes your last selected text into another script; middle-click paste still works inside the editor and text boxes.
- On Windows, Shift+Tab outdents in the code editor instead of opening the Steam overlay, and F12 saves one screenshot instead of two.
- On Windows, the Steam overlay now stays off while one of Steam's keys is also a game key, as Steam's default Shift+Tab is. To use the overlay, give it another key in Steam; the Keybinds tab in Settings names the key and the game action that holds it.
- On Windows with the Steam overlay on, the overlay no longer vanishes or stops opening after a few uses, Steam's screenshot key saves a picture even when nothing on screen moves, and a closed overlay or a Steam notice no longer stays frozen over the game.
- On Windows with the Steam overlay on, full screen is now a borderless window, so Alt+Tab leaves the game reliably, and the game no longer closes now and then right at launch.
- On Linux, typing Chinese, Japanese or Korean through an input method other than IBus or Fcitx works again on installs where a Steam update had broken it.
- With external editing on, a script's file is the one named exactly like the script, capitals included: on Linux a file whose name differs only in capitals is no longer mixed up with it and the game tells you which one it uses, renaming a script only in capitals renames its file, and a new script or Library gets its file right away.
- PyCharm no longer lists every name twice in completion, Pyright and Pylance narrow types after checks such as `isinstance`, and the scripts folder now includes settings for the ty type checker.
- A function you pass to `sort`, `sorted`, `min`, `max`, `map`, `filter` or `heapq.nsmallest` no longer stops the script with "script execution stopped unexpectedly" when it unpacks one of your own objects with `*`, as in `distance(*target)`, and runs for a while.
- Sorting or searching your own objects with `sort`, `sorted`, `min`, `max`, `heapq`, `in` or `print` now spreads the calls to their comparison or `__repr__` methods over several ticks, so hundreds of objects no longer stop the script with "script exceeded step limit".
- Many smaller fixes make `Counter`, `deque`, `OrderedDict`, dictionaries, list searches, `functools.cache`, `heapq` and `itertools` behave as in Python when your own code they call prints, runs for a while, raises an error or changes the collection, and `x in iterator` now uses up the items it checks.
- `get_component("run_control")` used from the Playground now really starts and stops machine scripts; `start` and `stop` used to answer `ok` without doing anything. A copy waiting in Recovered edits no longer counts as `editor_busy`.
- Message values on the Computer's Signal Bus tab can be selected and copied again.
- Unsaved code recovered from an earlier session no longer interrupts you with a notice at load: it waits under Recovered edits in the Pause menu, which shows how many there are and puts the current text beside the recovered copy before you replace it.
- In a script's Variants tab, each variant has an actions menu, including the new Update outdated copies, which loads the variant's latest saved code on the machines still using an older copy of it.
- With Single editor window chosen in Settings, you can drag its script tabs into a new order, and the order is kept.
- The tabs of the Production and Storage pages, and the search and filters of Computer's Scripts tab, stay at the top while you scroll.
- The info button on Shop cards, a new one on Research cards, and a selected Inventory item show the ID your scripts use and links to the matching DOCS pages.
- Machine datasheets in DOCS now say exactly how much power a machine draws and when, idle included, and a page shared by several models, such as the drills, lists each model's figures.
- Battery holders from `self.battery.holders()` now have an `index`, the mounting slot to pass to `swap_batteries()`.
- In the Biology Lab, a geothermal order marks only the fragments that need splicing as Spliced; the others can be delivered raw, as delivery already allowed.
- The Vault Crab's Mandible Claw is now called Crab Pincer, and several recipe names now say Iron Ingot or Titanium Ingot where the recipe takes ingots.