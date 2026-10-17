# Version Change TODO: Experimental v0.1.34 (manual build fe9a45c)

Temporary checklist for adopting the v0.1.34 changes (changelog:
`git show 78525d9:VERSIONCHANGE_TODO.md`). Fold open items into [TODO.md](TODO.md) or finish
them, then delete this file.

Most of this build is the engine switch. No changelog entry and no docs change requires a change
to the game scripts.

## 1. New engine: Electron instead of WebView2 (Tauri)

The install is now an Electron app: `code-terraform.exe` plus `resources/app/` (`dist/` holds the
frontend, `electron-dist/main.cjs` the main process). The sim bundle is
`dist/assets/simWorkerEntry-<hash>.js` (was `simWorker-<hash>.js`). The save folder
(`%APPDATA%\io.codeterraform.game`), `codeterraform-workspace.json` and `console/<save id>.json`
are still written by the new build.

- [x] `devtools/play/game_speed.py`: launches the exe with `--remote-debugging-port` on its own
      command line (the `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` variable no longer reaches the
      game). Electron's `/json/list` shows only the page, so the script attaches to the page,
      auto-attaches to its workers (flat sessions) and talks to the sim worker's session; a
      worker restart (save load) detaches the session and the script reattaches. The game starts
      detached from the script's console, because Electron quits on the Ctrl+C that ends the
      script. Live test 2026-10-16: hook, F9 and Ctrl+C (game keeps running) work.
- [x] dev_workflow.md §8a, devtools/README.md, AI_CHEATSHEET.md index: WebView2 → Chromium
      DevTools, current minified clock names.
- [x] `devtools/game_update/build_docs/build_docs.py`: reads the Electron `resources/app/dist/`
      folder (old Tauri exe still supported).
- [x] Live check of the IDE command channel (`.codeterraform/command.json`: `create-library`,
      `apply-library`) under the new engine, in a throwaway save: `scripts_sync.py` relies on it.
      The channel works; small applies answer in ~1 s.
- [x] `scripts_sync.py --apply-libs`: an apply of `script_parking` (205 importers) outlasted the
      20 s reply wait; the game finished it, but `scripts_sync` treated the game as unreachable
      and left `supply_dock`, `thermal_cap`, `fluid_plan` unapplied. Now an `unconfirmed` apply
      counts once the workspace file lists its `deployedSource` (`APPLY_CONFIRM_TIMEOUT_S`), and
      a stale `session_changed` reply is resent once (dev_workflow.md §9).
- [ ] Live check: the next large `--apply-libs` run applies every pending lib.

## 2. Simworker-dependent devtools (dev_workflow.md §10c)

All pass on fe9a45c without code changes except `game_speed.py` (section 1):
`extract_game_spec.py` (unresolved 0, coverage ok, only `game_version` changed; unit tests 1950
OK), headless (fresh saves of seeds 1-3 with no `[headless]` line, 82/82 node tests, every anchor
count 1, sample save `20261008_7e5e168/1631_t2294802` 0.5 h with latest scripts: no crash,
`errored` 0), `seed_quality.py` and `field.mjs` (`port matches`, seeds 1-3), `swap_seed.py`
(seed 1 → 2 round trip equals the fresh seed-2 save on all five fields).

## 3. Interpreter fixes: no script impact

Checked against `scripts/` and `autoplay/`; none of them use the affected constructs:

- Print inside an operator method (`__add__` etc.) no longer runs the other operand twice: we
  define no operator methods.
- A class defined inside a function keeps its attributes when the script pauses inside the
  class: we define no classes inside functions (`recipe_claims._ClaimHost` is a typing Protocol).
- `itertools.starmap` with generator rows works: we don't use `starmap`.
- `from __builtins__ import Counter` / `deque` (and probably `defaultdict`; the changelog text is
  cut off) now give the real collections classes, so `isinstance` works: we use none of them.
- A Library that fails during import shows its own lines in `traceback.format_exc()`: debugging
  aid only.
- Atomic callbacks (`lib/atomic.py`, dev_workflow.md §1d-1 "Callbacks run as one unit") still
  hold. Headless probe on fe9a45c: 1,000 arithmetic iterations take 7 ticks as a direct call and
  1 tick inside one `map()` callback.

## 4. Docs diff (split of the fe9a45c DOCS Manual)

- `re.Pattern.groupindex` is typed `dict[str, int]` (was `float`). Not used by our code.
- `docs/database/` recipe and research diffs only flip `*(Not yet unlocked)*` to `*(Unlocked)*`:
  that state comes from the save the manual was exported from, not from the build.
- `docs/00_Table_of_Contents.md` is regrouped; the file counts (90 components, 49 guides) match
  files that were already tracked. No component or guide file changed.

## 5. Not relevant here

Linux start, Linux overlay and IME fixes, drawn window buttons, removed graphics and audio
settings, cheaper storm rendering, unsaved-edit recovery from older versions (our scripts live
in the repo), Ctrl-click into built-in modules (editor only). Saves stay compatible with v0.1.32
in both directions.

## 6. Simworker diff (changes the changelog leaves out)

- [x] `simworker_diff.py` c6fbecb → fe9a45c: 16 changed, 3 added, 90 removed chunks, 0 number
      changes. No balance, recipe or machine change.

Matches the changelog (section 3): binary operators keep the evaluated right operand across a
pause (`evalBinaryOp`), class bodies restore their scope after a pause (`buildClassValue`),
`starmap` iterates each row, `from __builtins__ import` of a `collections` name resolves to
the real module, and a Library import error carries its traceback.

Not in the changelog:

- **Console focus**: a script start focuses the console only when the player starts it
  (Run button, recovering a paused script). Restarts after a Library apply and other internal
  starts no longer move the focus. UI only.
- **Number kinds in the API metadata**: return values are tagged `integer` or `float` (Vehicle
  Charging Station queue: `bay_index`/`queue_index` integer, `target_level`/`battery_wh`/
  `rate_w`/... float; `math.inf`/`pi`/`tau` float). It feeds the editor's type info and the
  docs (`re.Pattern.groupindex` → `int`, section 4). No runtime change.
- **Renderer crash recovery**: new notice "The engine that draws the game stopped, and the game
  restarted itself". After such a restart `game_speed.py` reattaches like after a save load.
- **`get_game_version()`** returns `fe9a45c`: `lib/version_guard.py` halts automation in game
  until the version is confirmed on `status_panel`'s AUTOMATION card (expected; headless
  confirms by itself).
- Removed: the graphics, frame pacing, audio wake-up and Alt+Tab settings (in the changelog);
  `presentation.refocusHiddenGraceMs`. Added: clipboard error texts in the editor's context
  menu.
