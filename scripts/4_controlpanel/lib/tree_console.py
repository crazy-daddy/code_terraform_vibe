"""Indented, tree-drawn console logging shared across scripts.

Adapted from the version by Discord user E̸̤̝̊̈l̶͙͎̓͠l̸̖̊͜ì̶̲ȍ̸̰t̶̯͓̾͗ 
(https://discord.com/channels/1498806997955514368/1550356674127069195/1550356674127069195)

Wraps the `console` component (docs/components/console.md) so both the
quick overview and the in-depth reasoning trail read like a call stack in
the Console tab instead of a flat scroll of unindented lines.

Three levels, same tree formatting:
- `print()`/`start()`/`end()` default to **info** — the beautified, always
  visible overview (major blocks, outcomes) a player can skim at a glance.
- `debug()` logs the deeper "why" (candidates considered, computed
  thresholds, per-item reasoning) at **debug** level, hidden from the ALL
  view unless the player opts into debug output. Every console call costs
  0.1 s of simulation time whether or not the line is displayed
  (docs/BENCHMARK.md), so consecutive debug/trace lines are buffered and
  written as one multi-line message; see "Buffering" below.
- `trace()` is for genuinely high-volume noise (method entry/exit, per-item
  loop detail) — a true no-op (no `console` call, no disk write) unless the
  module's level is `"trace"` (see "Log levels"). Still emits at
  **debug** level, not a custom `"trace"` badge — per
  docs/components/console.md, only `info`/`warn`/`error`/`debug` feed the
  WARNINGS/ERRORS/debug-opt-in filters; any other string is just a colored
  badge shown in the normal ALL view, which would defeat the point of
  gating this as opt-in output.

Log levels: the `console.log_levels` archive dict maps a `module` name to the
lowest level it writes: `"trace"` < `"debug"` < `"info"` < `"warn"` < `"error"`.
A module without an entry takes the `"*"` entry, else `"debug"` (everything but
trace). The first TreeConsole that finds no dict writes `{"*": "debug"}`, so the
key shows up in the Data Archive Notebook ready to edit. A line below the module's level is dropped before it reaches
`console`, and so is the header and END line of a block below it; lines logged
inside still follow their own level. Levels other than these five (custom
badges) count as info. Read once at construction, not per call: restart the
script after changing the archive key. Pass `module=` explicitly (the sandbox
has no `inspect`/frame introspection to auto-detect a caller), e.g.
`TreeConsole(module="power")`. The headless simulation sets `"*"` to `"debug"`
and makes debug lines free (dev_workflow.md §10b).

Debug blocks: `start(msg, level="debug")` opens a block whose header is written
only once something is logged inside it (an idle block prints nothing), and
`end()` writes `┗━ END <name>` when the header was written, nothing otherwise. Use them for a function's decision
trail so its lines sit indented under one header and drop their own
`function_name:` prefix.

Timestamps: buffered lines carry their own game time-of-day (`console.now()`), taken
when the line is logged, so every line of a multi-line message is stamped, not
just the first.

Collapsing: a debug block that logs exactly one line is written as a single
`name: message` line instead of header, line and END. The line carries the time the
message was logged and ends with the game time the block then took (` (+4m05s)`,
left off when no time passed). The first line is held back until a second line, a
nested block or the end shows which of the two forms is needed; `flush()`, a line
from another TreeConsole and `reset()` expand it first.

Buffering: debug lines (and trace lines that pass the gate) collect in one
module-level buffer shared by every TreeConsole in the script, so log order
is kept across modules. The buffer is written out as a single
`console.print` when
- a line at another level, channel or color is logged (info, warn and error
  print immediately, after flushing pending debug lines),
- the outermost `start()`/`end()` block closes,
- the next line would exceed the size cap (half the interpreter's string
  limit, at most `MAX_BUFFER_CHARS`), or
- `flush()` / `flush_all()` is called.
Lines still buffered when a script parks are not shown until the next flush,
and a script stopped from the UI or crashed is killed without unwinding
(`finally` blocks do not run), so they are lost: run loops call `log.flush()`
(`flush_all()`) before every `sleep()` and comms wait. `swallowed()`
flushes before it prints. `buffered=False` on a TreeConsole prints its debug
lines immediately.

Warn and error lines are written without the tree indent: the console prints its own
level badge in front of the message, so an indent behind it would not line up with
the block. Their block still shows around them.

Exceptions: an exception escaping a `start()`/`end()` pair leaves its indent open, so run loops call
`reset_all()` at the top of every tick (`tests/test_reset_in_run_loops.py`).

Wrapped blocks: `log.run(label, fn)` runs `fn()` inside a block and closes it on every return, so a function
with many exits needs no `end()` before each `return`. `@log.block()` (module-level `log`) and
`@method_block()` (methods, reads `self.log`) do the same as decorators. An exception escaping the block
closes it, and any block left open inside it, with `END <name> !! <Type>: <message>` and is raised again.
The log then shows where the error passed, and the indent is not left open.

Construct one instance per controller in `__init__` (or once before a
`run_*_loop()`'s `while True:`, never inside it) and store it as `self.log`/
`log` -- constructing it reads the `console.log_levels` archive dict, so
re-constructing per call or per tick defeats the point. Name it `log`, not
`tree` -- the tree-drawing is just formatting, `log` is what it's for.

See docs/AI_CHEATSHEET.md #0a for the usage pattern.
"""

import functools
import re
from typing import TYPE_CHECKING

from archive import archive
import swallow

if TYPE_CHECKING:
    from typing import Any, Callable, TypeVar
    F = TypeVar("F", bound=Callable[..., Any])

_BRANCH = "┃   "  # "┃   "
_START = "┏━ "  # "┏━ "
_END = "┗━ "  # "┗━ "

LOG_LEVELS_KEY = "console.log_levels"
DEFAULT_LOG_LEVEL = "debug"
_LEVEL_RANKS = {"trace": 0, "debug": 1, "info": 2, "warn": 3, "error": 4}
_INFO_RANK = 2  # custom badge levels

MAX_BUFFER_CHARS = 20000  # largest single console.print measured to render (docs/BENCHMARK.md)
FALLBACK_BUFFER_CHARS = 4000
_BUFFERED_LEVELS = ("debug",)
_UNINDENTED_LEVELS = ("warn", "error")  # the console puts its own badge in front of the line, so an indent would not line up
_PROBE_CHARS = 200000  # above the highest Advanced Scripting string limit (100,000)

# One buffer for every TreeConsole in the script. `key` is (level, channel, color) of the pending run.
_BUFFER = {"console": None, "key": None, "lines": [], "chars": 0, "cap": 0}

# Console component every TreeConsole without an explicit `console` shares. get_component() returns a new
# handle per call, and the buffer flushes when the console object changes, so separate lookups would split
# every interleaved run of lines from two modules into one console.print each.
_DEFAULT_CONSOLE: "dict[str, Console | None]" = {"console": None}

# TreeConsoles with a debug block that holds its first line back (see "Collapsing" in the module doc).
_HOLDING = []

# Every TreeConsole in the script, so reset_all() can drop indent leaked by an exception.
_INSTANCES = []


def _default_console():
    """The shared console component, looked up on first use."""
    if _DEFAULT_CONSOLE["console"] is None:
        _DEFAULT_CONSOLE["console"] = get_component("console")
    return _DEFAULT_CONSOLE["console"]


def _cap_from_error(message):
    """Buffer cap from an OverflowError message ("string length 200,000 exceeds the current limit of
    100,000."): half the limit, at most MAX_BUFFER_CHARS. FALLBACK_BUFFER_CHARS if it has no limit."""
    numbers = re.findall("[0-9][0-9,]*", message)
    if len(numbers) < 2:
        return FALLBACK_BUFFER_CHARS
    return min(int(numbers[1].replace(",", "")) // 2, MAX_BUFFER_CHARS)


def _buffer_cap():
    """Size cap for one buffered message, read once from the interpreter's string limit by building a
    string larger than any Advanced Scripting setting allows."""
    if _BUFFER["cap"] > 0:
        return _BUFFER["cap"]
    cap = MAX_BUFFER_CHARS
    try:
        len("x" * _PROBE_CHARS)
    except OverflowError as error:
        cap = _cap_from_error(str(error))
    _BUFFER["cap"] = max(cap, 200)
    return _BUFFER["cap"]


def flush_all():
    """Write the pending debug run as one console.print and empty the buffer. A block still holding its
    single line is expanded first, so the line is not lost if the script parks or is killed."""
    for log in list(_HOLDING):
        log._expand_held()
    lines = _BUFFER["lines"]
    if not lines:
        return
    level, channel, color = _BUFFER["key"]
    console = _BUFFER["console"]
    _BUFFER["lines"] = []
    _BUFFER["key"] = None
    _BUFFER["chars"] = 0
    _BUFFER["console"] = None
    console.print("\n".join(lines), level=level, channel=channel, color=color)


def _stamp(console):
    """Game time-of-day prefix ("HH:MM:SS "), or "" if the console has no `now()`."""
    if not hasattr(console, "now"):
        return ""
    try:
        return f"{console.now()} "
    except Exception as error:
        swallow.swallowed("tree_console._stamp: console.now", error)
        return ""


def reset_all():
    """Drop every open block on every TreeConsole. Run loops call it at the top of each tick: an exception
    that escapes a start()/end() pair leaves its indent open, so every later line would sit one level
    deeper. Never call it inside a block that is meant to stay open."""
    for log in _INSTANCES:
        log.reset()


def _seconds(stamp):
    """Seconds since midnight of an "HH:MM:SS " stamp, or -1 if it is not one."""
    parts = stamp.strip().split(":")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return -1
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])


def _elapsed(start_stamp, end_stamp):
    """" (+4m05s)" for the game time between two stamps, "" if unknown or no time passed."""
    first, last = _seconds(start_stamp), _seconds(end_stamp)
    if first < 0 or last < 0:
        return ""
    seconds = (last - first) % 86400
    if seconds == 0:
        return ""
    if seconds < 60:
        return f" (+{seconds}s)"
    return f" (+{seconds // 60}m{seconds % 60:02d}s)"


def _write(console, text, level, channel, color, buffered, stamp=""):
    if not buffered or level not in _BUFFERED_LEVELS:
        flush_all()
        if stamp:
            console.print(stamp + text, level=level, channel=channel, color=color)
        else:
            console.print(text, level=level, channel=channel, color=color, timestamp=True)
        return
    cap = _buffer_cap()
    text = (stamp or _stamp(console)) + text
    if len(text) > cap:
        text = text[: cap - 1] + "…"
    key = (level, channel, color)
    if _BUFFER["lines"] and (_BUFFER["key"] != key or _BUFFER["console"] is not console):
        flush_all()
    if _BUFFER["chars"] + len(text) + 1 > cap:
        flush_all()
    _BUFFER["console"] = console
    _BUFFER["key"] = key
    _BUFFER["lines"].append(text)
    _BUFFER["chars"] += len(text) + 1


swallow.set_flush_hook(flush_all)


def _block_label(name, fn, args, kwargs) -> str:
    """Block header for a wrapped call: `name(*args, **kwargs)` when it is callable, else `name`, else the
    function's name."""
    if callable(name):
        return str(name(*args, **kwargs))
    return name or getattr(fn, "__name__", "block")


def method_block(name=None, level: str = "debug") -> "Callable[[F], F]":
    """Decorator: run the method inside `self.log.run()`. `name` is the header text, or a callable that takes
    the method's arguments (`self` first) and returns it; default the method's name. Without a `self.log`
    the method runs unwrapped."""
    def decorate(fn: "F") -> "F":
        @functools.wraps(fn)
        def wrapped(self, *args, **kwargs):
            log = getattr(self, "log", None)
            if log is None:
                return fn(self, *args, **kwargs)
            label = _block_label(name, fn, (self,) + args, kwargs)
            return log.run(label, lambda: fn(self, *args, **kwargs), level)
        return wrapped  # type: ignore[return-value]
    return decorate


class TreeConsole:
    def __init__(
        self,
        console=None,  # the game Console, or any object with print(text, **kwargs)
        default_level: str = "info",
        module: str = "",
        buffered: bool = True,
    ) -> None:
        self.console = console if console is not None else _default_console()
        self.default_level = default_level
        self.buffered = buffered
        self._indent = 0
        # open blocks, outermost first: [level, header line, shown, channel, color, name, held first line]
        self._blocks = []
        self._pending_color = ""
        self._pending_level = ""

        levels = archive.get(LOG_LEVELS_KEY)
        if levels is None:
            levels = {"*": DEFAULT_LOG_LEVEL}
            archive.set(LOG_LEVELS_KEY, levels)
        levels = levels or {}
        self.module = module
        min_level = levels.get(module, levels.get("*", DEFAULT_LOG_LEVEL))
        self.min_rank = _LEVEL_RANKS.get(min_level, _LEVEL_RANKS[DEFAULT_LOG_LEVEL])
        self.verbose = self.min_rank == 0  # trace() writes; callers also gate costly trace detail on it
        _INSTANCES.append(self)

    def color(self, color: str) -> "TreeConsole":
        """Set the color for the *next* line only, then reset to default."""
        self._pending_color = color
        return self

    def level(self, level: str) -> "TreeConsole":
        """Set the level (info/warn/error/debug/custom) for the *next* line only."""
        self._pending_level = level
        return self

    def print(self, msg: str, channel: str = "") -> None:
        """Log one line at the current indent depth, at `default_level` (info) unless overridden."""
        self._emit(msg, channel)

    def debug(self, msg: str, channel: str = "") -> None:
        """Log one line at the current indent depth, always at debug level (in-depth reasoning)."""
        self._pending_level = "debug"
        self._emit(msg, channel)

    def trace(self, msg: str, channel: str = "") -> None:
        """Like `debug()` (same **debug** level -- console.print() only treats
        info/warn/error/debug as filter-feeding, everything else is a custom
        badge shown in the normal ALL view), but a true no-op (no disk write)
        unless this module's level is `"trace"` (see "Log levels"). For high-volume noise (method entry/exit, per-item loop detail)
        safe to sprinkle liberally without a runtime cost by default."""
        if not self.verbose:
            return
        self._pending_level = "debug"
        self._emit(msg, channel)

    def start(self, msg: str, channel: str = "", level: str = "") -> None:
        """Open a named block and indent everything logged until the matching `end()`. A block at
        `level` "debug" writes its header only when a line is first logged inside it."""
        block_level = level or self.default_level
        block = [block_level, self._prefix() + _START + msg, False, channel, self._pending_color, msg, None]
        self._pending_color = ""
        self._pending_level = ""
        self._blocks.append(block)
        self._indent += 1
        if block_level not in _BUFFERED_LEVELS:
            self._show_headers()

    def end(self, msg: str = "", channel: str = "") -> None:
        """Dedent and close the block opened by the matching `start()`. A debug block whose header was
        written closes with `END <name>` unless given a message; one that never wrote it closes silently."""
        self._indent = max(0, self._indent - 1)
        block = self._blocks.pop() if self._blocks else [self.default_level, "", True, "", "", "", None]
        if block[0] in _BUFFERED_LEVELS:
            if not block[2]:
                if block[6] is None:
                    return
                if not msg:
                    self._collapse(block)
                    return
                self._blocks.append(block)
                self._show_headers()
                self._blocks.pop()
            msg = msg or "END " + block[5]
        self._pending_level = self._pending_level or block[0]
        self._emit(_END + msg, channel or block[3], headers=False)
        if self._indent == 0 and block[0] not in _BUFFERED_LEVELS:
            flush_all()

    def run(self, label: str, fn, level: str = "debug"):
        """Run `fn()` inside a `start(label, level=level)` ... `end()` block and return its result. An
        exception closes the block (see `_fail()`) and is raised again."""
        self.start(label, level=level)
        depth = len(self._blocks)
        try:
            result = fn()
        except Exception as error:  # not recovered: raised again after closing the block
            self._fail(depth, error)
            raise error
        self.end("" if (level or self.default_level) in _BUFFERED_LEVELS else "END " + label)  # "" keeps collapsing
        return result

    def block(self, name=None, level: str = "debug") -> "Callable[[F], F]":
        """Decorator: run the function inside `run()`. `name` as in `method_block()`."""
        def decorate(fn: "F") -> "F":
            @functools.wraps(fn)
            def wrapped(*args, **kwargs):
                return self.run(_block_label(name, fn, args, kwargs), lambda: fn(*args, **kwargs), level)
            return wrapped  # type: ignore[return-value]
        return decorate

    def _fail(self, depth: int, error) -> None:
        """Close every block from `depth` (1 = outermost) inward with `END <name> !! <Type>: <message>`. Pending
        headers and held lines are written first, so the failure path shows even in an idle debug block."""
        self._show_headers()
        marker = f" !! {getattr(type(error), '__name__', 'Exception')}: {error}"
        while len(self._blocks) >= depth:
            self.end("END " + self._blocks[-1][5] + marker)

    def reset(self) -> None:
        """Drop this instance's open blocks (see `reset_all()`)."""
        self._expand_held()
        self._indent = 0
        self._blocks = []

    def flush(self) -> None:
        """Write any buffered debug lines now (call before `sleep()` in run loops)."""
        flush_all()

    def _shows(self, level: str) -> bool:
        return _LEVEL_RANKS.get(level, _INFO_RANK) >= self.min_rank

    def _prefix(self) -> str:
        return _BRANCH * self._indent

    def _show_headers(self, count=None) -> None:
        """Write the headers of blocks that have not shown theirs yet, outermost first (only the first
        `count` open blocks if given), each followed by the line it was holding back."""
        blocks = self._blocks if count is None else self._blocks[:count]
        entry = ""  # headers take the entry time of the held line, so stamps stay in order
        for block in blocks:
            if not block[2] and block[6] is not None:
                entry = block[6][3]
                break
        for depth, block in enumerate(blocks):
            if block[2]:
                continue
            block[2] = True
            if self._shows(block[0]):
                _write(self.console, block[1], block[0], block[3], block[4], self.buffered, entry)
            held = block[6]
            if held is not None:
                block[6] = None
                self._release_hold()
                prefix = "" if held[0] in _UNINDENTED_LEVELS else _BRANCH * (depth + 1)
                _write(self.console, prefix + held[4], held[0], held[1], held[2], self.buffered, held[3])

    def _release_hold(self) -> None:
        if self in _HOLDING:
            _HOLDING.remove(self)

    def _expand_held(self) -> None:
        """Write the header and held line of the block holding its first line back, if any."""
        for depth, block in enumerate(self._blocks):
            if block[6] is not None:
                self._show_headers(depth + 1)
                return

    def _collapse(self, block) -> None:
        """Write a block's single held line as `name: message (+elapsed)` at the block's own depth."""
        level, channel, color, stamp, msg = block[6]
        block[6] = None
        self._release_hold()
        prefix = "" if level in _UNINDENTED_LEVELS else self._prefix()
        text = prefix + block[5] + ": " + msg + _elapsed(stamp, _stamp(self.console))
        _write(self.console, text, level, channel, color, self.buffered, stamp)

    def _emit(self, msg: str, channel: str, headers: bool = True) -> None:
        if self.console is None:
            self._pending_color = ""
            self._pending_level = ""
            return
        level = self._pending_level or self.default_level
        color = self._pending_color
        self._pending_color = ""
        self._pending_level = ""
        if not self._shows(level):
            return
        for other in list(_HOLDING):
            if other is not self:
                other._expand_held()
        if headers:
            block = self._blocks[-1] if self._blocks else None
            if block is not None and block[0] in _BUFFERED_LEVELS and not block[2] and block[6] is None:
                self._show_headers(len(self._blocks) - 1)
                block[6] = (level, channel, color, _stamp(self.console), msg)
                _HOLDING.append(self)
                return
            self._show_headers()
        prefix = "" if headers and level in _UNINDENTED_LEVELS else self._prefix()
        _write(self.console, prefix + msg, level, channel, color, self.buffered)
