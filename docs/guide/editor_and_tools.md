# Guide: Editor & Tools

In-game and external editor tools, commands, variants, debugging, and controls.

---

## Code Editor

Each machine with a script slot has a code editor window. Open it by clicking `MANAGE` on the machine card.

### Tabs

- **Info**, task description, what this script should do
- **Code**, write your code here
- **Variants**, named versions you can reuse on matching machines (see below)
- **Notes**, free-text scratchpad for your own notes

### Title bar controls

- `▶` **Run** (`Shift+Enter`), execute the active variant
- `⏸` **Pause** (`F6`), pause or resume a running script
- `■` **Stop** (`Shift+F5`), stop the script completely and reset script-owned controls. Rover, Pioneer, and Drone movement cancels immediately.
- `∹` **Trace**, highlight where the script is parked each tick. A green bar marks the "resting" line, where execution was when the most recent tick ended. Honest about suspension points (for scripts with `sleep()` or `scan()`) and where the step limit tripped (for tight loops).
- `⊕` **Debug**, enable breakpoints, stepping, and the variable watch panel. See the Debug guide for the full flow. Off by default.
- `🔍` **Find**, search and replace within the script (`Ctrl+F`).

### Bottom bar

- **Duplicate Variant**, save the current code as a new named variant
- `🔊` **Mute**, mute this script's console output. Text gets a strikethrough when muted. Muted scripts don't print to the console; errors still show. Useful for silencing background scripts you're not actively working on.
- `⊞` **Dock**, switch to an IDE-style layout. The editor pins to the left, the console docks to the bottom-right, and the dashboard fills the remaining space. The sidebar hides automatically to maximize content area. Drag the dividers between panels to resize. Your dock layout is remembered between sessions. Click `Undock` to return to floating windows.
- `⤓` **Auto-min**, when enabled (green), the editor minimizes automatically when you run the script. Useful for watching the dashboard while your code executes.

### Navigating from code to DOCS

The editor can jump straight to matching DOCS entries while you write:

- **Hover over any method or function name**, a tooltip shows the signature, a one-line description, and the return type. Works on `self.X`, `self.X.Y`, top-level API calls (`get_component`, `sleep`, `print`), builtins (`len`, `range`, etc.), component methods accessed via `get_component(id).method`, and user-defined functions with docstrings.
- **`Cmd+click` (macOS) / `Ctrl+click` (Windows/Linux) on any method, function, component id, or variable**, opens DOCS and jumps directly to that entry, with the specific method highlighted for a second or two so you can see exactly where you landed. Works like "Go to Definition" in a professional IDE, but the target is the DOCS page since the game APIs don't have a source file.
- **Autocomplete as you type** (`Ctrl+Space` to force it), suggestions are type-aware. Move through the list with `↓` and `↑`, `Enter` inserts the highlighted one, and Tab takes the first match. Those three keys are yours to change in **Settings → Keybinds**, under Editor. After `self.` you'll see only the methods and sub-objects available on your machine. After `self.battery.` you'll see only the Battery sub-object's API. String arguments offer known-valid values (component ids, bin names, mineral ids) where available.
- **Parameter hints inside `(...)`**, as you type `self.drill.mine(`, a hint shows each parameter's name, type, and description.
- **`F2` to rename** a symbol (variable, user function, parameter). Renames every whole-word occurrence in the current script, skipping strings and comments. Reserved names (keywords, `self`, builtins) can't be renamed.

> Hover for signatures. Cmd/Ctrl+click opens the matching DOCS entry without leaving the editor.

### Commands tab

While a script runs, its **Commands** tab lets you send named commands with JSON arguments into the script's command mailbox, your script reads them with `self.next_command()` and decides how to react. Frequent commands can be saved as presets. See the **Script Commands** page for the full pattern.

### Variants

Named variants use layered catalogs. Exact-type variants belong to one precise machine type; compatible-family variants are shared only across tiers with the same scripting contract. **Main** is this machine's own fallback code and is never shared. Editing in the Code tab saves changes to the active variant. Changes to **Main** stay with this script; changes to a named variant update its shared catalog entry. Other scripts keep their loaded copies until you explicitly update them. Use **Duplicate Variant** to publish the current code as a new named variant and choose its scope when a compatible family exists. Click **Use** to load a catalog variant onto this machine. **Apply to all** copies the selected catalog version to either the exact type or every compatible family tier, according to the section that owns the variant, and always requires the same script slot. Main cannot be deleted. Tip: add a top-of-file `"""docstring"""` or first-line `#` comment and it will show as the variant's description. Open **Docstrings** for function hover docs and supported formatting.

### Saving

Your scripts auto-save every **30 seconds**. Press `Ctrl+S` to save and flush the current source immediately. All editor shortcuts, including undo, redo, comments, search, and run, can be changed in **Settings → Keybinds**.

Scripts run continuously if they contain a `while True:` loop. Otherwise they run once and complete.

### Reload behavior

A script saved as running starts again from the top when you load the game. Its local variables and current line are not restored. A paused script stays paused but also starts from the top when you resume it after loading; a stopped script stays stopped. Persistent world state and machine work remain where they were, so check current cargo, storage, and machine state before repeating actions. Use the **Data Archive** for script progress that must survive reloads.

The console window shows output from all unmuted scripts. Use `CLEAR` to empty it and `AUTO-SCROLL` to follow new output.

*Guide / Editor & Tools*

## Vim Mode

### Overview

Vim mode gives the in-game code editor vim keybindings. Turn it on in Settings → Editor → Keybindings → Vim. It is opt-in and affects ONLY the code editor, game menus, the map, and dashboard controls keep their normal keys.

### What works

The editor uses a vim-flavored keymap, so the everyday toolkit is there: normal / insert / visual modes, motions (`h` `j` `k` `l`, `w`, `b`, `e`, `gg`, `G`, `f`, `%`), operators (`d`, `c`, `y`, `p`) with counts and text objects, search (`/`, `?`, `n`, `N`), registers, marks, and undo / redo (`u`, `Ctrl-r`). It is vim-**flavored**, not a 100% feature-complete vim, most muscle memory carries over, but a few exotic commands and plugins will not.

### Save and quit

These ex-commands are wired to the game's real save and window controls:

- `:w`, save now. Flushes your script to disk immediately (it is auto-saved anyway, so this just makes the reflex real).
- `:wq` / `:x`, save, then close the editor window.
- `:q`, close the editor window. Your work is already saved.

### Bring your own vim

Prefer your actual vim setup? See the External Editor page, your scripts live as real files on disk that you can edit in any editor, full vim included, and the game picks up changes live.

*Guide / Editor & Tools*

## Script Commands

### Overview

Every machine script has a **command mailbox**, a small queue of named commands you send by hand while the script runs. Commands let you steer a running script without editing it: the script keeps its own logic and decides how to handle each request.

This is the player-to-script channel. For script-to-script coordination, use the **Signal Bus** instead.

### Saving reusable commands

Open a script's **Commands** tab. Add a command with a **Name** (the button label), a **Command** id (what your code checks for), and any **arguments** as simple key/value fields, no JSON.

Choose the command's **Availability**:

- **All machines of this type** makes the definition available on current and future machines of the same exact type.
- **All compatible family machines** appears when the machine registry declares a compatible family. It shares the definition across that family.
- **Only this machine** keeps instance-specific coordinates, target ids, or other one-off data local.

Then **Send** it once, or **Save** it as a reusable one-click command. Existing local commands have a **Share** action that moves them into an exact-type or compatible-family collection. Shared edits and deletion affect every matching machine.

A saved definition is reusable, but execution is always local: **Send** queues a fresh message only on the machine whose Commands tab is open. Pending queues and recent history are never copied or broadcast. They remain per machine.

Commands are defined in the tab, not in your script, and they do not belong to a script variant. Switching or copying a variant does not duplicate command definitions. Each machine's mailbox holds up to **40** pending commands; further sends are rejected until the script consumes or clears some.

### Reading commands in your script

Four methods are available on `self` in every machine script:

- `self.next_command()` consumes the oldest command and returns a `CommandResult`. `.status` is `"ok"` with the command in `.command`, or `"empty"` with `.command is None`.
- `self.peek_command()` reads the next `ScriptCommand` without consuming it, or `None` when the mailbox is empty.
- `self.command_count()` reports how many commands are waiting.
- `self.clear_commands()` drops everything and returns a `CountResult`; `.count` is exactly how many commands were removed.

A consumed command is a `ScriptCommand` in `CommandResult.command`, with `.name` (a string; your script decides what each name means) and `.args` (a dict; use `.args.get(key, default)` for optional arguments).

```
while True:
  next_result = self.next_command()
  if next_result.status == "ok":
    cmd = next_result.command
    if cmd.name == "goto":
      self.nav.set_target(cmd.args["x"], cmd.args["y"])
      self.nav.set_throttle(0.6)
    elif cmd.name == "stop":
      self.nav.brake()
```

> Commands are requests, not remote control. A script that never calls `next_command()` ignores its mailbox. Handling commands is part of the script's design, and unknown names should be ignored or reported with `print()`.

### Commands vs Signal Bus

- **Command mailbox**: you (the player) to one machine script, from the editor. Best for manual steering, testing a mode, or one-off orders.
- **Signal Bus** (`get_component("comms")`): script to script, on named channels. Best for automation that coordinates machines while you are away from the keyboard.

*Guide / Editor & Tools*

## Script Variants

Variants are named script snapshots you can reuse across a fleet without copying code by hand.

### Main and named variants

Every script starts with **Main**. Main is this machine's own fallback code; it is not shared and cannot be renamed or deleted.

A machine can expose two named catalogs:

- **Exact type**, specialized for that precise machine model or tier.
- **Compatible family**, shared only by models that expose the same scripting contract. Small, Medium, and Large Drones share Drone family variants, for example. A Water Pump and Oil Pump do not share merely because both extract fluids.

The Variants tab always lists exact-type variants first and compatible-family variants below them. Machines without an explicitly compatible family show only the exact-type catalog. When you save a variant on a compatible machine, you choose which catalog owns it.

### Editing the active variant

The Code tab edits whichever variant is active. Changes to **Main** stay with this script. Changes to a named variant update its shared catalog entry, while other scripts keep their loaded copies until you explicitly update them. An older loaded copy is marked **outdated**; click **Update** to load the latest catalog version, or **Keep mine** to save that copy as a separate named variant.

Use **Duplicate Variant** or **Create Variant from Selection…** to publish the current code as a new named catalog entry. Duplicate names across the visible catalogs are blocked so variant selection stays unambiguous.

### Use and Apply to all

**Use** loads a catalog variant into this machine's running code and makes it active here.

**Apply to all** respects the catalog that owns the variant. An exact-type variant targets that precise type. A family variant targets every explicitly compatible tier with the same script slot. If the selected named variant is active here and you edited it, **Apply to all** uses the updated catalog source.

When the applied source changes, a running target restarts automatically with the new code. A manually paused target stays paused, a power-paused target waits for power and then resumes, and a stopped target stays stopped. A target that already has the same source keeps its current evaluator without a restart.

Apply to all is a one-time copy, not a permanent shared link. Future edits to a named variant update its catalog entry but do not change other scripts' loaded copies. Use Apply to all again when you intentionally want those scripts to load the improved version. Changes to Main remain private to the script that owns it.

### Catalog changes

Renaming or deleting a named variant changes only its owning catalog. When a saved variant is deleted, scripts using it keep their current working code and lifecycle, then detach to Main. A running script keeps its evaluator, a paused script stays paused, and a stopped script stays stopped.

A top-of-file `"""docstring"""` or first-line `#` comment becomes the variant description shown in the list. Function docstrings are separate: they appear in hover and autocomplete, and the **Docstrings** page lists the supported formatting.

### Sharing real code

Compatible family sharing is explicit machine metadata, not a guess based on names or appearance. If different scripting contracts need common helper functions, put those helpers in a Library script and import them instead of forcing those machines into one variant family.

### Unassigned scripts

Undeploying or deconstructing a machine stops its script. Authored code stays in **Computer > Scripts > Unassigned**, with its notes, private Main, selected variant, and run history. **Current** shows assigned scripts by default; **All** includes both views.

Unassigned scripts cannot run. Use their actions menu to **Copy to machine**, **Copy to Playground**, or **Delete**. You can select several unassigned scripts for deletion. Deletion removes their private data but keeps shared machine variants.

**Copy to machine** uses a compatible machine slot and keeps its existing ID. It stops the target and preserves the previous code in Variants before replacing Main. Compatibility requires a recorded former machine type and slot; older unassigned scripts without that information can still be reviewed and copied to Playground.

**Copy to Playground** creates a new named document without replacing Scratch or running the code. The original script stays available with all its metadata. Copied code is unchanged, including machine IDs and `self` references.

Machine IDs are never recycled by deleting an unassigned script.

*Guide / Editor & Tools*

## Debug Mode

Debug mode adds breakpoints, uncaught-exception pauses, three-mode stepping, conditional breakpoints, logpoints, and a live variable watch panel to any script. It's off by default, toggle the `⊕ Debug` button in the editor's title bar to turn it on.

### What Debug mode gives you

- A **breakpoint gutter** that lets you click any line to pause execution there
- A **Watch panel** on the right showing current values of all local variables
- **Step Over**, **Step Into**, **Step Out**, and **Continue** controls when the script is halted
- A **Call Stack** section for jumping between function frames and inspecting each frame's locals
- A persistent **breakpoint list** in the Watch panel for jumping between breakpoints and editing their conditions / log messages

### Setting breakpoints

Click a line number's left gutter. A red dot appears on that line; the same line also shows up in the **Breakpoints** section of the Watch panel. Click the gutter again to remove, or click the `×` next to it in the Watch panel.

Breakpoints persist when you toggle Debug off and on, and across game sessions. The Debug button shows a small `·` when dormant breakpoints exist on a script that isn't in debug mode.

### Conditional breakpoints and logpoints

Click the `⋯` button next to a breakpoint in the Watch panel to edit it.

- **Condition**, a read-only Python expression. If set, the breakpoint halts **only when the condition is truthy**. Use variables, attributes, indexes, and arithmetic; function and method calls are blocked so debug expressions can never change the game. Example: `heat > 80`.
- **Log message**, a template with read-only `{expr}` placeholders. If set, the breakpoint **prints the message to the console and keeps running** instead of pausing. Like sprinkling `print()` without editing the script. `scan hit: {site.id}` prints the current site id on every hit.

You can combine them, a condition + log message will log only when the condition matches.

Breakpoint color cues: red = plain, yellow = conditional, accent = logpoint.

### When execution halts

A breakpoint pauses before the marked line runs. An uncaught exception pauses on the line that failed and shows the error message. In both cases the line gets an orange highlight. The **Watch panel** shows:

- **Paused at line N** or **Paused on exception at line N** header with debugger controls
- **Local variables** for the selected call-stack frame; dicts, lists, tuples, and sets show compact previews first and expand on click
- **Call Stack** rows you can click to jump to that frame and inspect that frame's locals
- **Breakpoints** list with jump-to, edit, and remove controls

### Step Over / Into / Out

Three step modes, following the industry standard:

- **Over (`↴`)**, runs the next statement. If it contains a function call, the call runs atomically (doesn't descend). Most-used step.
- **Into (`↡`)**, descends into the next function call. Stops on the first statement inside. Use when you want to debug a helper function.
- **Out (`↥`)**, runs until the current function returns. Use when you stepped Into something boring and want to bail back to the caller.
- **Continue (`⏵`)**, resumes until the next breakpoint or completion. From an uncaught exception pause, Continue lets the script fail normally and clears it.

### The world keeps running

Breakpoints and exception pauses pause **only the debugged script**. Everything else continues:

- The clock keeps ticking
- Other scripts on other machines keep running
- Atmosphere, power, and all systems tick normally
- The machine controlled by the paused script keeps its last-commanded state while paused. If the script errors, stops, or completes, script-owned controls reset; Rover, Pioneer, and Drone movement cancels.

This means time spent stepping through code advances the game world. If you're debugging a solar tracker and take two minutes to inspect variables, the sun has moved in that time. For scripts with strict timing, factor this in.

### Inspecting variables

The Watch panel updates live every tick when the script is running, or freezes at the current values when the script is halted.

- Numbers, strings, booleans show their values directly
- Dicts, lists, tuples, and sets show their size plus a shallow preview; nested values are abbreviated until expanded
- Small objects may show a short field preview; larger objects show their type first and expand on click
- The current line number is shown at the bottom of the panel

### Pinned Watch values are optional

You do not need to pin anything to inspect the current frame. When the script pauses, **Local variables** and **Call Stack** update automatically. Use **+ Pin** in Watch only when you want to keep a custom value or calculation visible across steps, such as `co2 / 10`, `self.waste()`, or `atmo.get_co2()`.

> The Watch panel samples variables at the script's last suspension point. For a script with `sleep(1)` at the end of each loop, that's the value at the moment `sleep()` was called. For a tight loop with no deliberate pauses, it's wherever the tick's step limit tripped.

### Isolation guarantee

Debug mode is a read-only-plus-pause tool. Enabling Debug on one script **cannot affect another script's behavior**. Breakpoints, exception pauses, step state, and watch inspection are stored per-script, turning debug on a heater script has zero impact on an oxygen generator script running in parallel.

*Guide / Editor & Tools*

## Control Room

The Control Room is a top-level page for **cards**: script-driven panels that draw live dashboards and can issue commands through shared game APIs. Open the **Control Room** page, click `+ New Card`, and a fresh panel script is bound to a canvas.

A panel script runs every game tick. The pattern is always the same:

```
while True:
  panel.clear()
  # ... call panel.draw_X(...) and panel.widget(...) here ...
```

Your script controls the layout, colors, data shown, and update cadence. The same read APIs you use from machine scripts work here too: `get_component(...)`, `clock.get_elevation()`, `orders.list_orders()`. Panels can read component state; they change the base only through shared authorities such as `power_control`, `shop`, `comms`, `inventory`, `atmosphere`, or `computer`.

### Common uses

Panels can read any component exposed to scripts. Common uses include:

- **Atmospheric history**, three progress bars for O₂ / N₂ / pressure with a 50-tick spark line below
- **Fleet status board**, one row per vehicle with a status dot, name, current activity, and battery bar
- **Sun-tracker monitor**, three gauges for sun elevation, panel tilt, and solar efficiency
- **Tank levels**, a bar chart showing every fluid buffer at the base, with net flow text below
- **Active order briefing**, wrapped text of the contractor's brief plus an iron-ingot icon and progress bar
- **Storage inventory**, every storage bin's icon, name, fill percent, and count

The data comes from existing APIs; panels provide a canvas and widgets for displaying it.

### The widget set

**Twenty-one named widgets** for common patterns:

- **Layout:** `card`, `divider`, `label`
- **Indicators:** `status_dot`, `toggle`, `pill`, `counter`
- **Bars:** `progress_bar`, `vertical_bar`, `bar_chart`
- **Curves:** `gauge`, `spark_line`
- **Interactive (the player clicks them):** `button`, `icon_button`, `switch`, `checkbox`, `slider`, `radio_group`, `combo`, `text_field`, `list`, read them each tick to act on the player's input

A radio group, a combo box and a list each take their choices as one list and store one value, so a five-way choice costs the card one saved key rather than five. `combo` and `text_field` open the game's own menu and a real text editor over the card, which is why they stay readable at any card size and why typing into a field has working selection, clipboard and input method.

**Fifteen primitives** for everything the named widgets don't cover:

- `draw_text` (with optional `wrap`), `draw_icon`
- `draw_rect` / `fill_rect`, `draw_circle` / `fill_circle`, `draw_line`
- `draw_polygon` / `fill_polygon`, `polyline`
- `clip_rect` / `clear_clip`
- `clear`, `width`, `height`

**Driving the widgets from code:** `set_switch`, `set_slider`, `set_selected` and `set_text` force a control to a value without waiting for a click; `forget` drops one stored value and `clear_inputs` drops them all. Stored keys are never swept for you, because a card that paints one page at a time would lose the other page's state, so a card is capped at 512 of them.

**Reading the player directly:** `mouse()` gives the cursor position on this card, `clicks()` hands you every click that missed a widget so you can hit-test your own drawing, and `capture_keys()` plus `keys()` give a focused card the keyboard. The cursor is sampled once per tick and the card repaints at the same rate, so anything you draw from `mouse()` follows the pointer about a frame behind: right for showing what is under it, wrong for anything that must track it exactly.

Every widget that takes a `color` parameter accepts theme tokens: `"accent"`, `"success"`, `"warning"`, `"error"`, `"text-bright"`, `"text-secondary"`, `"text-muted"`, `"text-value"`. Cards can also paint with **surface tokens**, bg-base, bg-surface, bg-panel, border, border-dim. Wrap a `card(x, y, w, h, title)` for the bordered+titled frame, fill zones with `fill_rect(x, y, w, h, "bg-surface")`, and a manage-style row is `status_dot` (green) + `draw_text` (name) + `button` (play/manage). Theme tokens resolve from the active theme whenever the script redraws the card.

See the **Panel** entry in the API reference (left sidebar) for the full method list with live previews of each widget.

### A complete working example

A fleet status panel:

```
rover = get_component("rover_1")
pioneer = get_component("pioneer_1")

while True:
  panel.clear()
  panel.label(12, 22, "FLEET", "caption")

  panel.status_dot(20, 50, 5, "running")
  panel.draw_text(38, 50, rover.name, 13)
  panel.progress_bar(360, 44, 110, 10, rover.battery.level(), "success")

  panel.status_dot(20, 80, 5, "running")
  panel.draw_text(38, 80, pioneer.name, 13)
  panel.progress_bar(360, 74, 110, 10, pioneer.battery.level(), "success")
```

No `sleep()` needed, the interpreter paces the loop automatically. The panel repaints every game tick.

### Watch for...

> Cards can command only through shared authorities. A card has no `self` over a machine, so a machine's own actions (`set_throttle`, `set_recipe`, `move_to`, `mine`) don't work from a card. It can still call shared authorities such as `power_control` (breakers), `shop` (buy/sell), `comms` (Signal Bus), `inventory`, `atmosphere`, and `computer` (deploy, undeploy, decommission, rename). Treat cards as trusted automation because they can change base state.

> The canvas does not auto-clear. Always call `panel.clear()` at the top of every loop iteration, or old paint will pile up under new paint and the panel will look smeared.

> Coordinates are in logical pixels. A 1×1 card is 500×200; two-column cards are 1000 pixels wide and two-row cards are 400 pixels high. CSS scales the visual to the screen, so use `panel.width()` / `panel.height()` when the script must adapt to the card's span.

### Limits

- **50 cards per save**, max. Past that, `+ New Card` is grayed out. Delete one to make room.
- **Board density**, choose 2-6 columns from the selector above the board. The untouched default uses 2 for ordinary workspaces, 4 for 4K-class workspaces, and 6 for sufficiently wide ultrawides. A manual choice persists.
- **Four card sizes**, 1×1, 2×1 (wide), 1×2 (tall), and 2×2 (big), selected directly from the card-size menu. The logical canvas scales with the span, so **draw relative to `width()` / `height()`** and your card reflows at any size.
- **One script per card.** Want separate concerns? Make multiple cards.

*Guide / Editor & Tools*

## External Editor

Your scripts are saved as `.py` files on disk. You can edit them in any text editor, VS Code, Sublime, Notepad++, or anything else.

Changes sync **live** in both directions, while the game is running:

- Edit in-game, the file updates on disk within ~half a second
- Edit externally, the game picks up your save within ~250ms and the in-game editor's buffer refreshes (cursor preserved as best it can)

If the operating system cannot watch the folder (Linux inotify limits, some network drives), the game rescans it every two seconds instead and says so once in its log. A file another program is still holding (an editor's own save, an on-access scanner on Windows) is retried for a moment before that pass gives up on it.

### Where the files live

Scripts for an active save sit in a folder named `<save_id>_scripts/` under your platform's app-data directory:

- **Windows:** `%APPDATA%\io.codeterraform.game\<save_id>_scripts\`
- **macOS:** `~/Library/Application Support/io.codeterraform.game/<save_id>_scripts/`
- **Linux:** `$XDG_DATA_HOME/io.codeterraform.game/<save_id>_scripts/` or `~/.local/share/io.codeterraform.game/<save_id>_scripts/`

`<save_id>` is auto-generated when you first create the save (something like `save_lk2j8x_a1b2c3`). It matches the `.json` save file beside the script folder; if you are unsure, sort the app-data folder by modified time and use the newest `save_..._scripts/` folder for the save you just opened.

Each machine or panel script uses the same filename shown in the in-game editor, such as `o2gen_1.py`, `solar_1.py`, or `rover_1.py`. Library scripts live in a `lib/` subfolder, named normally, a library called `sensors` is `lib/sensors.py`. The `.py` file contains only code; `codeterraform-scripts.json` is a small sync manifest that tracks safe filename aliases after renames. Files that used older generated names, such as `oxygen_gen_1.py`, remain tracked as safe aliases after migration; use the canonical id-named file going forward.

### Every file in the folder

- `<name>.py`: one file per machine, panel or contract script; `lib/<name>.py`: Library scripts.
- `user_stubs.py`: yours, never overwritten. Type aliases, TypedDicts and re-exported Library types declared here are read by the in-game editor and the extension.
- `logs/`: mirrored console output, `all.log` plus one file per script, rotated by size.
- `codeterraform-workspace.json`: the read-only analysis snapshot the language server reads. `codeterraform-scripts.json`: the sync manifest. Do not edit either.
- `CODE-TERRAFORM-IDE.txt`: the setup guide, with the exact language-server path on your machine and editor configurations.
- `*.pyi` and `pyrightconfig.codeterraform.json`: fallback stubs for generic Python editors (see below).
- `.codeterraform/`: transient files the editor and the game exchange while a command runs (Run, Stop, Library operations, debugging). Safe to ignore.
- `codeterraform-fleet.json`: the machine panel's data (owners, scripts and their status). Do not edit.
- `.vscode/settings.json`, `.zed/settings.json`, `.gitignore`: written once if missing and yours afterwards. The first folds the helper files under one collapsed row in VS Code's Explorer and hides the transient folder; the second makes the game's server Zed's Python server and formatter for this folder only; the third ignores everything machine-specific or regenerated, so `git init` here tracks your scripts, Libraries, `user_stubs.py` and your own configuration.
- `*.codeterraform-retired-<token>.bak`: recovery archives. The game keeps one whenever a file is renamed, deleted, replaced or in conflict, so an editor that writes through a stale handle can never lose code. They are yours to delete whenever you like; `*.codeterraform-write.bak` is the crash-safety copy of an atomic write and disappears by itself.
- Only each script's running source is a file. The **Variants** and **Notes** tabs live in the save, not in this folder, so named variants cannot be listed, switched or edited from outside the game.

### VS Code setup

Launch Code Terraform normally from Steam and open your save. In Settings > Editor > External Editor, choose **Set Up VS Code**. The game installs its bundled extension and opens the scripts folder. Later the button becomes **Open in VS Code** and also installs any updated client. VS Code must already be installed; the game never installs an editor or extension at startup. **Show Extension Package** remains available for custom setups. No Python or separate Node installation is needed for VS Code.

Install the extension once. It is a thin client: the game installs the language server that matches its own build under `external-ide/server/` in the app-data folder and records the path in each save's `codeterraform-workspace.json`, so the extension always launches the server that belongs to the game you are running. After a game update, open the save once and VS Code switches to the new server by itself. When the extension itself changes, use the same Settings button to update it.

Game files automatically use the **Code Terraform** language mode. Completion, diagnostics, hover, signature help and Go to Definition use the same analysis as the in-game editor, including each script's own `self` or `panel`. Other Python projects keep their Python tooling.

Save edits to sync them into the game. The VS Code Command Palette includes **Create Library in Game**, **Import File as Game Library**, **Rename Library and Update Imports**, **Run Script in Game** and **Stop Script in Game** under Code Terraform. Unknown files offer an Import action. Save files and resolve in-game source conflicts first. Rename updates game imports and saved variants through the normal game command. Attach and delete scripts in the game. No command runs host Python. Its status item reports context availability; click it to restart the service.

`codeterraform-workspace.json` contains a read-only analysis snapshot. Keep this save open to refresh owners, names and research. Offline analysis uses the most recent snapshot. If the folder was written by a different game build than the server in use, open the save in the game once to refresh both. Do not edit the generated context or the sync manifest.

### Debugging in the game

Keep this save open and the game unpaused. In VS Code, open a machine, panel, or contract script, set a breakpoint, and press F5. An idle script starts; a running script attaches without restarting. Breakpoints, conditions, logpoints, call stacks, locals, watches, hover inspection, and Step Over/Into/Out use the game's interpreter. Library breakpoints are reached through a script that imports that Library. Each session controls one script.

Shift+F5 or closing the debug session disconnects and leaves the script running. Use **Stop Script in Game** to stop it. Watches and the Debug Console accept read-only expressions; they cannot execute world actions or assign variables. Save your files first. To run changed main-script code, use **Run Script in Game** before attaching again. Apply edited Libraries in the game and resolve any source conflicts. If you enabled **Pause When Inactive**, turn it off when you want execution to continue while the game is minimized.

Other editors with a Debug Adapter Protocol client can launch `node /path/to/debug-adapter.cjs`. That file lives beside the installed `server.cjs`. Use a `launch` request to attach and run an idle script, or `attach` to inspect an existing runtime. Set `workspace` to this save's scripts directory and `script` to the script's file path. The adapter uses standard input/output. It needs Node.js 20 or later outside VS Code.

### Formatting with Ruff

Format Document, Format Selection and format on save work on game scripts in VS Code and in every other editor that uses the game's language server. The server is the formatter and Ruff is the engine: it runs the Ruff you already have (the VS Code Ruff extension's own binary, `ruff` on PATH, or a pipx, uv or cargo install) and hands back only the lines that changed, so your cursor and folds stay put. A `ruff.toml`, `.ruff.toml` or `pyproject.toml` in the scripts folder applies; without one you get Ruff's default, Black-compatible style. Nothing is downloaded: when Ruff is missing, the format action says how to get it, and in VS Code offers to install the Ruff extension. Ruff's own extension cannot format game files directly, because they use the Code Terraform language mode that keeps Pylance from flagging `self` and the game builtins.

### Coloring, rename, references and Outline

Game files get semantic coloring the way Python files do: variables, parameters, functions, classes, methods, properties, imported modules and the script's `self` or `panel`, all from the same analysis that answers completion. An identifier the analysis cannot place keeps its plain grammar color rather than a guessed one. Rename Symbol (F2 in VS Code) follows the same scoping rules as the in-game editor, refuses the same reserved names, and stays inside the one file; Find All References and the Outline, breadcrumbs and Go to Symbol views use the same source. Cross-file rename is not offered.

### The Machines panel in VS Code

The Code Terraform view in the activity bar lists this save's outposts and machines, each with its scripts and their live status (running, paused, error with the line, idle, unpowered), plus Panels, Contracts and Libraries. Click a script to open it; use the inline Run and Stop actions or the context menu's Debug. The panel reads `codeterraform-fleet.json`, which the game rewrites whenever a script starts, stops or fails, so it stays current while the save is open.

### Other editors

Any editor that speaks the Language Server Protocol (neovim, Helix, Sublime Text with the LSP package, Emacs with eglot or lsp-mode) can use the same language server. Node.js 20 or later is required outside VS Code. The game installs the server at:

- **Windows:** `%APPDATA%\io.codeterraform.game\external-ide\server\server.cjs`
- **macOS:** `~/Library/Application Support/io.codeterraform.game/external-ide/server/server.cjs`
- **Linux:** `~/.local/share/io.codeterraform.game/external-ide/server/server.cjs`

Launch it as `node <path> --stdio` with the scripts folder as the workspace root, one server per save; the root marker is `codeterraform-workspace.json`. The game rewrites the file on every launch, so a configured editor keeps working across game updates. `CODE-TERRAFORM-IDE.txt` in the scripts folder repeats these configurations with the exact path on your machine.

neovim (Neovim 0.11 or later, nvim-lspconfig):

```lua
vim.lsp.config("codeterraform", {
  cmd = { "node", "/path/to/server.cjs", "--stdio" },
  filetypes = { "python" },
  root_markers = { "codeterraform-workspace.json" },
})
vim.lsp.enable("codeterraform")
```

Helix (`languages.toml`; listing the server on `python` replaces Helix's default Python server for those files):

```toml
[language-server.codeterraform]
command = "node"
args = ["/path/to/server.cjs", "--stdio"]

[[language]]
name = "python"
roots = ["codeterraform-workspace.json"]
language-servers = ["codeterraform"]
```

Sublime Text (LSP package, `LSP.sublime-settings`):

```json
{
  "clients": {
    "codeterraform": {
      "enabled": true,
      "command": ["node", "/path/to/server.cjs", "--stdio"],
      "selector": "source.python"
    }
  }
}
```

On Windows, write the path with forward slashes inside these configurations.

### Zed

Zed has no one-click install for an extension outside its registry, so the game's extension is installed once from the source the game ships: install Rust with rustup (rustup.rs; Zed builds with the `cargo` your shell finds first, and rustup's carries the WebAssembly target), then in Zed run **zed: install dev extension** and choose `<app-data>/external-ide/zed/code-terraform` (**Open in Zed** in Settings > Editor > External Editor writes that folder, and **Show Extension Package** opens the folder beside it). Zed compiles it in a few seconds; after a game update, run the same command on the same folder again. The Settings row shows whether Zed lists the extension. Then open a save's scripts folder in Zed, or choose **Open in Zed**, and trust the folder when Zed asks. The extension reads `codeterraform-workspace.json` in the folder you opened and starts the game's installed server with Zed's own Node; the folder's `.zed/settings.json` makes that server Zed's Python server and formatter for this folder only.

### PyCharm

**Set Up PyCharm** in Settings > Editor > External Editor installs the game's own Code Terraform plugin, and the LSP4IJ plugin it builds on, into PyCharm and opens the scripts folder there. Close PyCharm first: its plugins can only change while it is not running, and the button says so if it is. Approve the third-party plugin once when PyCharm asks. Node.js 20 or later must be installed, because PyCharm supplies no Node and the language server and the debugger run on it; the setup says so when it is missing, and the executable can be set in PyCharm's **Settings > Tools > Code Terraform**. After that everything is in the editor. Completion, diagnostics, hover, signatures, definitions, rename, symbols, formatting through Ruff (install Ruff so it is on PATH) and semantic coloring come from the game's server, and PyCharm's own Python inspections stay off for game scripts, so `self` and the game builtins are never underlined. The **Code Terraform** tool window holds the Machines view, every script with its status and Run, Stop and Debug, and Game Output, the game's log with tracebacks linked to their lines; Run, Stop and Debug also sit in the gutter of every script. Debugging needs no configuration: Debug starts the game's debug adapter for that script, with breakpoints, stepping and variables in PyCharm's Debug tool window. The line under the button reports whether the plugin is installed and current; after a game update, Set Up PyCharm (with PyCharm closed) updates it. The **?** beside the button has the manual steps: LSP4IJ from the Marketplace, then **Install Plugin from Disk...** with the zip the game keeps under its app-data folder (**Show Extension Package** opens the folder that holds it).
## Fallback stubs

Generic editors can still use the generated `.pyi` files for partial API help; this fallback does not provide full game-aware analysis.

`pyrightconfig.codeterraform.json` is the generated fallback configuration. New `pyrightconfig.json` files extend it so you can add your own overrides. Byte-identical old generated defaults migrate automatically. Customized configurations are preserved; to adopt updated defaults, add `"extends": "./pyrightconfig.codeterraform.json"` to your config and retain the overrides you need. PyCharm does not read Pyright configuration; mark `lib/` as a Sources Root for its own Library import resolution.

`user_stubs.py` is player-owned and is never overwritten. Put type declarations there, not executable helpers: aliases such as `MineralId = Literal["iron_ore", "copper_ore"]`, TypedDicts and re-exported Library types. The in-game editor and the extension both read them, so a function typed with one of them completes and lints like any other, while the game treats every import from the file as a no-op. Settings > Editor > External Editor has **Freeze Stubs** and **Regenerate Stubs** controls. Freezing fallback stubs does not freeze the game-aware language service.

### Console output in your editor

The game mirrors visible console output into `<save_id>_scripts/logs/` from the first time you open the scripts folder or the extension package (Settings → Editor → External Editor keeps the toggle). `all.log` holds the combined console stream; script-specific files such as `rover_1.log` hold only that script's output. In VS Code the extension follows `all.log` live in its Output panel: choose **Code Terraform: Open Game Output**, or pick the Code Terraform channel in the Output view. Traceback locations in the channel and in the log files link to the script lines. Other editors can follow `logs/all.log` with their own tail. Logs append while the game runs and rotate by size, so noisy print loops do not grow forever. Use Clear Logs in settings when you want a fresh transcript.

### When edits collide

If an external edit collides with a dirty in-game buffer, the game first saves BOTH sources as distinct named recovery variants. It then asks you to choose **Use External** or **Keep In-Game** for the active source. Neither side is silently discarded: the version you do not activate remains available in the Variants tab. If both recovery variants cannot be created, the editor stays locked and no version is chosen. Free a variant slot if needed, then save the external file again to retry. A clean in-game buffer accepts an external change normally.

### Use cases

- Use game-aware language assistance in VS Code
- Version-control your scripts with git
- Share scripts with other players
- Write longer, more complex programs comfortably

*Guide / Editor & Tools*

## Keyboard Shortcuts

Every application-level keyboard shortcut the game uses. Click any customizable binding in the Keybinds settings tab to change it. For multi-line cursors, hold `Alt` (`Option` on macOS) and drag in the editor.

*Guide / Automation Systems*
