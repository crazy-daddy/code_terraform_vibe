# Console Logging & Swallowed Exceptions (§0a, §0b)

Part of [`AI_CHEATSHEET.md`](../AI_CHEATSHEET.md).

### §0a Structured Console Logging (`lib/tree_console.py` `TreeConsole`)

Console output: three detail levels, all same tree format:

- **Overview (info, always visible)** — major blocks + outcomes, beautified, skimmable, no opt-in needed.
- **Reasoning trail (debug, opt-in, written by default)** — the *why*: which branch decision took, candidates considered/rejected, computed threshold/estimate values. Hidden from normal ALL view (`docs/components/console.md`'s `console.debug()`), so no spam for non-opted players — reading with debug on should tell whole run story without in-game breakpoint/watch debugger (`§8`). Every console call costs 0.1 s of simulation time, shown or hidden (`docs/BENCHMARK.md`), so consecutive debug lines are buffered into one message (see *Buffering* below). Not for per-item work inside hot loops: that is `trace`.
- **Trace (opt-in per module, gated before reaching `console`)** — truly high-volume noise: method entry/exit, per-item loop detail. `TreeConsole.trace()` true no-op (no `console` call, no disk write) unless the module's level is `"trace"`. Hot loops and per-item detail belong here, not in `debug()`. When fires, still emits at **debug** level (not custom `"trace"` badge) — `docs/components/console.md`'s `console.print()` only treats `info`/`warn`/`error`/`debug` as filter-feeding; other strings = colored badge in normal ALL view, defeating opt-in gating.

**Log levels** — `console.log_levels` archive dict `{module_name: level}` sets lowest level each `TreeConsole(module=...)` writes: `"trace"` < `"debug"` < `"info"` < `"warn"` < `"error"`. Unlisted module takes `"*"` entry, else `"debug"` (all but trace). Missing dict seeded `{"*": "debug"}` by first `TreeConsole` constructed. Lines below level dropped before `console` (no 0.1 s cost); block header/END below level dropped too, lines inside keep own level. Custom badge levels count as info. Read once at construction — restart script after editing archive key via Data Archive Notebook, no per-tick re-check. `log.verbose` true when level is `"trace"`: gate costly trace-only detail on it. `log.debugging` true when level is `"debug"` or `"trace"`: gate costly debug-line formatting on it (`drone_haul_plan` planner lines). Headless simulation sets `{"*": "debug"}` and makes debug lines free (`--log-levels`, `--paid-debug`, `docs/cheatsheet/stub_tests.md` §10b). `module` must be passed explicitly (sandbox has no `inspect`/frame introspection); convention: `lib/` filename without extension (e.g. `"power"`, `"vehicle_energy"`).

`lib/tree_console.py`'s `TreeConsole` wraps `get_component("console")` with tree-drawn indentation (inspired by `inspirations/discord-panels/`) so levels read like call stack, not flat scroll:

```python
from tree_console import TreeConsole

# Create once in __init__ (or once before a run_*_loop()'s `while True:`), store as
# self.log — never re-construct per call/per tick, since __init__ reads the
# console.log_levels archive dict. Variable/attribute name is `log`, not `tree`
# (the tree-drawing is just formatting, `log` is what it's used for).
self.log = TreeConsole(module="power")  # default_level="info"; grabs get_component("console") itself

self.log.start("Creating tasks")                              # info: visible overview
for task_type in candidates:
    self.log.trace(f"Evaluating candidate {task_type.__name__}")  # trace: no-op unless "power" is "trace"
    self.log.debug(f"Considering {task_type.__name__}: score={score:.2f}")  # debug: reasoning trail
    self.log.print(f"Creating task {task_type.__name__}")      # info: outcome
self.log.end("Task creation success")

self.log.color("#FF0000").end("Task creation failed")          # one-off color override, next line only
self.log.level("warn").print("Battery below safety floor, aborting trip")  # one-off level override
```

- `start(msg)` / `end(msg)` open/close block, print `┏━`/`┗━` line, indent (`┃   ` per level) everything between — default level **info**.
- `print(msg)` logs one line at current indent, at `default_level` (info) unless overridden via `.level(...)`.
- `debug(msg)` = shorthand for `.level("debug").print(msg)` — in-depth opt-in reasoning trail, nested under info-level blocks. Written unless module level above `"debug"`.
- `trace(msg)` same shape at **debug** level (not custom `"trace"` badge — see above), but short-circuits before `console` unless `module=` passed to `TreeConsole(...)` is `"trace"` in `console.log_levels` (see **Log levels**). Use for method entry/exit + per-item loop noise wanted during active debugging only.
- **Convention**: one `TreeConsole` per controller instance, in `__init__` (or once before `run_*_loop()`'s `while True:` for bare function, not inside), stored as `self.log`/`log` — never re-construct per call/tick, since `__init__` reads `console.log_levels` archive dict. Name it `log` (not `tree` — tree-drawing just formatting, `log` names purpose).
- **Blocks**: one `start()`/`end()` pair per coherent unit of work (trip, order/recipe cycle, build/upgrade/commission, sweep, active tick phase); the `end()` message carries the outcome. Every `start()` is closed on every path (early `return`, error branch, `continue`/`break`), enforced statically by `tests/test_log_blocks_balanced.py` (per-branch depth must match; a loop body must be net zero). No block on idle ticks; no `with` (unsupported in-game) and no reliance on `finally` (a stopped script is killed without unwinding). Mixins log through `self._host.log`. An exception escaping a block leaves its indent open, so each top-level `run*` loop's first statement is `reset_all()` (`from tree_console import reset_all`; drops every instance's open blocks; `tests/test_reset_in_run_loops.py`). Polling loops nested inside a function must not call it.
- **Debug blocks**: `start(msg, level="debug")` … `end()` wraps a function's decision trail. The header is written only once a line is logged inside (an idle block prints nothing), `end()` writes `┗━ END <name>` when the header was shown (nothing otherwise; a message replaces `END <name>`), and the outermost debug `end()` does not flush the buffer (consecutive blocks share one `console.print`). Lines inside drop their own `function_name:` / `[name]` prefix, since the header names it. Convention: any function that can log two or more debug/trace lines in one call opens a debug block as its first statement (after the docstring) and closes it before every `return` (`_ret = expr; log.end(); return _ret` when the expression calls something). `step()`, `run*` loops and functions with their own info block are exempt. For a function with several returns, use a wrapped block (next bullet) or a public method that does `start` / `_impl()` / `end`. Blocks nest (outer headers are written first, once).
- **Wrapped blocks**: `log.run(label, fn, level="debug")` runs `fn()` inside `start(label, level=level)` … `end()` and returns its result, so the function needs no `end()` before each `return`. Decorators: `@method_block(name=None, level="debug")` (`from tree_console import method_block`) for methods, reads `self.log` at call time (mixins included, `self` is the host), runs unwrapped without one; `@log.block(name=None, level="debug")` for module-level functions with a module-level `log`. `name` = header text, or a callable taking the call's arguments (`self` first) for a dynamic header, e.g. `@method_block(lambda self, for_stage=False: f"[{self.name}] flush_surplus")`; default the function's name. A debug block still collapses and closes with `END <name>`; an info block closes with `END <name>`, since the wrapper has no outcome text (use manual `start`/`end(outcome)` when the outcome belongs in the END line). An exception escaping the wrapped block writes pending headers and held lines, closes the block and every block left open inside it with `┗━ END <name> !! <Type>: <message>`, and is raised again. `reset_all()` stays required in run loops for manual blocks. In use on every method whose debug block had 5+ bare `end()` exits (fleet commission/upgrade, drone/vehicle navigation, depot, turbine, fabricator, ...); `grep -rn method_block scripts/` lists them.
- **Collapsing**: a debug block that logs exactly one line is written as `name: message` (at that line's level) instead of header + line + END. The line carries the time it was logged, plus ` (+4m05s)` for the game time the block then took (omitted when 0). The first line is held back until a second line, a nested block, `end("msg")`, `flush()`, a line from another `TreeConsole` or `reset()` shows it must expand. `console.now()` is a normal cheap call (`docs/BENCHMARK.md`); only `print()`/`debug()`/`sleep()` cost 0.1 s.
- **Warn/error lines are not indented** (the console's own level badge precedes the message, so an indent would not line up); their block's `┏━`/`┗━` lines still frame them. `end()` at warn/error keeps its `┗━`.
- `color(c)` / `level(lvl)` set one-shot override (CSS color / `info`\|`warn`\|`error`\|`debug`\| custom) consumed by *next* `print`/`start`/`end`/`debug`/`trace` call only, then reset to instance default.
- **Buffering** (`tree_console._BUFFER`, one buffer for every `TreeConsole` in the script): `debug`/`trace` lines collect and are written as one multi-line `console.print`; info, `warn` and `error` print immediately after flushing pending debug lines, so order is kept. A run also flushes at a level/channel/color change or a different console object (instances built without `console=` share one cached `get_component("console")`, `_DEFAULT_CONSOLE`), when the outermost `start()`/`end()` block closes, at the size cap, and on `log.flush()` / `tree_console.flush_all()`. `swallowed()` flushes before it prints. Cap = half the interpreter string limit (read once from the `OverflowError` message), at most `MAX_BUFFER_CHARS=20000`, `FALLBACK_BUFFER_CHARS=4000` if unreadable; a longer single line is truncated. A script stopped from the UI is killed without unwinding (`finally` blocks do not run), so lines still buffered then are lost: call `flush_all()` before every `sleep()` and comms wait (`tests/test_flush_before_sleep.py` enforces it for tier 4+). `TreeConsole(buffered=False)` prints its debug lines immediately.
- Info/warn/error lines go through `console.print(..., timestamp=True)`. Buffered debug/trace lines are stamped by `TreeConsole` itself (`console.now()` when the line is logged, `"HH:MM:SS "` prefix) and printed without `timestamp`, so every line of a multi-line message has its own time; works with Console channel/level filters.
- **Inside atomic calls**: every console write goes through `atomic.console_print()`; inside a `lib/atomic.py` runner it is queued and written after the call (dev_workflow.md §1d-1), so pass the controller's `log` down and log as usual.
- Reserve plain `warn`/`error` for real status changes player should notice without debug output; `debug()`/`trace()` purely detail, never attention-needing.

### §0b No Silent `except Exception` (`lib/swallow.py` `swallowed()`)

Every broad handler that recovers (returns a default, `continue`s, keeps looping) calls `swallowed()` as its first line:

```python
from swallow import swallowed

try:
    count = port.count()
except Exception as error:
    swallowed("storage.crop_automator_forage: port.count", error)
    continue
```

- `where` = `"module.Class.function: call"`. Append ` #2`, ` #3` when one function has several sites calling the same thing. It is the dedupe key, so keep it unique per site.
- Every caught error → one **debug** line. Identical consecutive errors at one site are logged once, so a per-tick handler can't flood the log.
- "Code bug" types (`TypeError`, `AttributeError`, `NameError`, `KeyError`, `IndexError`, `ZeroDivisionError`) → also one **warn** per site per script run, visible without debug output on. Exception: `AttributeError` on `NoneType`, which is how a missing component (a `None` from `get_component()`) usually surfaces.
- `call_or(where, obj, method, default, *args)`: `obj.<method>(*args)`, else `default` when the method is missing, raises (swallowed as `"<where>: <method>"`) or returns `None`. Machine controllers wrap it in a one-line `_call(method, default, *args)` (Fuel Assembler, Feed Maker, Habitat, Refiner).
- Why: a broad except can't tell "game said no" from "our code is wrong" (e.g. a `TypeError` from a wrong API signature silently reads as "empty").
- **Allowed to stay silent** (with a comment saying why):
  - inside an `archive.transaction()` updater: any log call there rejects the transaction;
  - `swallowed()` itself;
  - narrow handlers that fully handle their case, e.g. `except (TypeError, ValueError)` around a `float()` parse with a fallback, or `except IndexError` as a loop escape.
- Tier `0_cold_boot` (no `lib/`) uses a local `_swallowed()` stand-in (debug only) defined in the script itself.
