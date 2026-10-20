# Live Debugging via External IDE (§8, §8a, §8b)

Part of [`AI_CHEATSHEET.md`](../AI_CHEATSHEET.md). External IDE debugging, fast-forwarding the simulation, reading live state, logs and decompiled logic. Split from [`dev_workflow.md`](dev_workflow.md).

## §8 Live Debugging via External IDE

Game exposes real Debug Adapter Protocol (DAP) integration against actual running game interpreter, not simulation: breakpoints, conditions, logpoints, call stacks, locals, watches, hover inspection, Step Over/Into/Out. Setup + full details:
`%APPDATA%\io.codeterraform.game\external-ide\README.txt`.

- **VS Code** (supported path, extension already installed this save): open script, set breakpoint, press **F5**. Idle script starts running; already-running script attaches without restart. **Shift+F5** or closing debug session disconnects but leaves script running in game. Use **Stop Script in Game** to actually stop. Watches/Debug Console **read-only** (can't execute world actions or assign variables). Edited main-script code needs **Run Script in Game** before re-attaching; edited Libraries need re-applying in game.
- **Any other DAP-capable editor**: launch
  `node "%APPDATA%\io.codeterraform.game\external-ide\server\debug-adapter.cjs"`
  (Node.js 20+, stdio transport). `launch` = attach-and-run idle script; `attach` = inspect already-running one. Set `workspace` to this save's scripts directory, `script` to target file.
- **Non-debug editor tooling** (LSP-only, no execution): `external-ide\server\server.cjs --stdio`. Per-editor docs (neovim/Helix/Sublime) in README. PyCharm needs generic LSP plugin; its own Python checker doesn't know game's owner globals/runtime rules.
- Console output mirrors to `external-ide\logs\all.log` (plus one file per script). Useful to tail even without debugger.
- **`devtools/play/dap_client.py`**: minimal DAP client for driving debug session from script instead of VS Code. Needs Node.js 20+; this save's copy at `C:\Program Files\nodejs\node.exe`, not on default shell `PATH`. Invoke by full path, or `export PATH="/c/Program Files/nodejs:$PATH"` for current shell session only (shell state doesn't persist between tool calls here). `devtools/scripts_sync.py` only consumer. `DapClient` = low-level stdio transport (Content-Length framing, background reader thread). `run_session(workspace, script, breakpoints,
  mode, on_stopped, wait_timeout)` wraps full initialize → attach/launch → setBreakpoints → configurationDone → wait-for-`stopped` → callback → continue → disconnect sequence in one call.
  Also runnable directly: `python devtools/play/dap_client.py --workspace <dir> --script <path> --break
  <file.py>:<line> [--mode attach|launch]`. Prints stack trace + top-frame locals at first hit, then resumes and disconnects.
  - **`launch` starts idle scripts without breakpoints**: `dap_client.launch_script(workspace, script)`
    (or CLI `python devtools/play/dap_client.py --workspace <dir> --script <path> --launch`) sends `initialize` →
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
  - **Applying a changed `lib/` module**: the game caches an imported library independently of the
    importing script, so restarting the importer runs the stale copy; only an apply swaps the cache.
    Command channel actions: `"apply-library"` `{scriptId: <library id>, source}` (`source` must equal the
    game's saved source for that Library, else `source_changed`) and `"apply-all-libraries"` (every Library
    whose saved source differs from its deployed one, one after another in the game's registration
    order). Each applied Library at once restarts every running script that imports it, directly or
    through other libraries; a script stopped in `error` is not restarted. The restarted script resolves
    its other imports against each Library's deployed source, so applying an importer before the library
    it imports a new name from stops its importers with `ImportError: cannot import name ...`; a later
    apply does not revive them. `scripts_sync.py` therefore applies imported libraries first
    (`apply_order()`). The result carries `libraryApply: {applied, affected, restartFailed, notApplied}`;
    other reasons: `research_required`, `not_found`, `already_applied`, `target_changed`, `compile_error`,
    `nothing_pending`, `not_applied`.
    What the game runs per Library: `context.libraryScripts[*].deployedSource` in
    `codeterraform-workspace.json` (`libs_awaiting_apply()`); its saved copy is `.source`.

**Debug sessions (F5/`launch`/`attach`) and **Run Script in Game** have real effects:** they run against the live save, no sandbox. A script that spends credits, moves a vehicle or fires a drill does so for real, and pausing at a breakpoint can leave a machine mid-action.

### §8a Fast-Forwarding the Simulation (Chromium DevTools)

The in-game speed tops out at 3× (`game.maxGameSpeed`). Faster testing works by shortening the sim worker's tick timer from DevTools. Nothing on disk changes, and the patch is gone after a game restart.

**Clock mechanics** (`internals/terraform_decompiled/simworker/deobfuscated.js`, search `= setInterval(`; minified names change every build):
- The sim runs in a Web Worker (`simWorkerEntry-*.js`) inside Electron, in a renderer child process. Cheat Engine's speedhack hooks the main exe, so it never reaches the sim's timers.
- `u = setInterval(l, 1000 / game.tickRate)` (100 ms) drives the loop. Each callback `l` runs `c` ticks. `c` is the in-game speed (1–3, from `sim.setSpeed`). The loop stops early when a tick requests a presentation flush.
- The sim never reads wall-clock time. Game time, `sleep()`, and interpreter step budgets all count ticks, so firing ticks faster keeps script behavior identical.
- `m()` re-arms the interval on every resume and after every save barrier. It looks up the global `setInterval` each time.

**Scripted:** `python devtools/play/game_speed.py [--fast N]` attaches to a running game that has the debug port, launches the game with it when none runs, or exits with a warning when the game runs without it; sets a never-pausing conditional breakpoint in the tick callback whose condition re-arms the timer at `tick interval / factor`, and toggles the factor 1 ↔ N with F9 (global hotkey). No pause/resume needed; it re-applies after the game re-arms the timer. A paused game shows no effect until resumed. The manual steps below do the same by hand.

**Steps:**
1. With the game closed, start `code-terraform.exe --remote-debugging-port=9222` (or put the switch in the Steam launch options). If `http://localhost:9222/json` responds while the game runs, it worked.
2. Start the game. Open `edge://inspect`, add `localhost:9222` under *Configure*, and inspect the game page.
3. In the DevTools console, select the `simWorkerEntry-…` context in the context dropdown, then run:
   ```js
   const _si = setInterval;
   globalThis.setInterval = (fn, ms, ...a) => _si(fn, ms / 10, ...a);  // 10x
   ```
4. Pause and resume in the game so `m()` re-arms the timer at 10 ms. Combined with in-game speed 3, this gives up to 30×.
5. To revert, run `globalThis.setInterval = _si`, then pause and resume.

Alternative: set a breakpoint in the tick callback and raise `c` in the Scope pane. This scales worse because of the early stop on flush.

**Limits:** Real CPU time per tick (all scripts' step budgets) caps the speed-up; a slow tick makes the timer run back-to-back. `isBackpressured()` skips ticks while the UI is behind on snapshots. This runs against the live save (real effects, see above).

### §8b Reading Live State, Logs and Decompiled Logic

Reading a save folder is fine; writing there is only for `devtools/scripts_sync.py` (§9).

- **Active save**: the newest `save_*_scripts` dir by mtime under `%APPDATA%\io.codeterraform.game\`, as `scripts_sync.py`'s `latest_save_dir()` resolves it. Its state file is the sibling `save_<id>.json` (strip `_scripts`, `_state_path_for()`). Re-resolve it every time; the user may have started a new save.
- **Script logs**: `<save>\logs\all.log` plus one log per script (`automation_1.log`, ...), rotated as `<name>.1.log` … `<name>.4.log` (~1 MB each, `.4` oldest). They reach back hours of game time. The save JSON holds no console history since e1986ce (own file), so read these logs. Line format: `[<wall ISO time>] [<level>] [<script>.py] [tick=<flush tick>] HH:MM:SS <text>`. `tick=` is when the TreeConsole buffer flushed; the per-line in-game `HH:MM:SS` is the accurate timing signal (about 14.4 game seconds per tick).
- **Decompiled game logic**: `internals/terraform_decompiled/simworker/deobfuscated.js` (~200k lines; grep, never read whole). Use it to understand how a mechanic works (scheduler, interpreter limits, what a method really does), never to decide what scripts do (CODE_GUIDES.md#portability). Anchors: creature table `const ak = [...]` (id → rarity), fragment table `const rk = [...]`, Habitat outcome contracts `` B(`habitat.<action>`, [...]) ``.
  - `internals/` is a submodule of a private repo; clones skip it. Fetch: `git -c submodule.internals.update=checkout submodule update --init internals`. An auth error means no access: say so and work from `docs/`.
  - The repo is public: never copy large parts of the decompiled code into tracked files.
- **Game language server**: `%APPDATA%\io.codeterraform.game\external-ide\server\server.cjs`. Machine definitions carry `nameKey: "machines.<type_id>.name"` and `scriptPrefix`.
