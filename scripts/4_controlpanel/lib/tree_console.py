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
  caller's `module` name is listed as `"verbose"` in the `console.log_levels`
  archive dict (default `"normal"`). Checked once at construction, not
  per-call — restart the script after changing the archive key. Pass
  `module=` explicitly (the sandbox has no `inspect`/frame introspection to
  auto-detect a caller), e.g. `TreeConsole(module="power")`. Still emits at
  **debug** level, not a custom `"trace"` badge — per
  docs/components/console.md, only `info`/`warn`/`error`/`debug` feed the
  WARNINGS/ERRORS/debug-opt-in filters; any other string is just a colored
  badge shown in the normal ALL view, which would defeat the point of
  gating this as opt-in output.

Debug blocks: `start(msg, level="debug")` opens a block whose header is written
only once something is logged inside it (an idle block prints nothing), and
`end()` writes `┗━ END <name>` when the header was written, nothing otherwise. Use them for a function's decision
trail so its lines sit indented under one header and drop their own
`function_name:` prefix.

Timestamps: buffered lines carry their own game time-of-day (`console.now()`), taken
when the line is logged, so every line of a multi-line message is stamped, not
just the first.

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

Exceptions: an exception escaping a `start()`/`end()` pair leaves its indent open, so run loops call
`reset_all()` at the top of every tick (`tests/test_reset_in_run_loops.py`).

Construct one instance per controller in `__init__` (or once before a
`run_*_loop()`'s `while True:`, never inside it) and store it as `self.log`/
`log` -- constructing it reads the `console.log_levels` archive dict, so
re-constructing per call or per tick defeats the point. Name it `log`, not
`tree` -- the tree-drawing is just formatting, `log` is what it's for.

See docs/AI_CHEATSHEET.md #0a for the usage pattern.
"""

import re

from archive import archive
import swallow

_BRANCH = "┃   "  # "┃   "
_START = "┏━ "  # "┏━ "
_END = "┗━ "  # "┗━ "

LOG_LEVELS_KEY = "console.log_levels"

MAX_BUFFER_CHARS = 20000  # largest single console.print measured to render (docs/BENCHMARK.md)
FALLBACK_BUFFER_CHARS = 4000
_BUFFERED_LEVELS = ("debug",)
_PROBE_CHARS = 200000  # above the highest Advanced Scripting string limit (100,000)

# One buffer for every TreeConsole in the script. `key` is (level, channel, color) of the pending run.
_BUFFER = {"console": None, "key": None, "lines": [], "chars": 0, "cap": 0}

# Every TreeConsole in the script, so reset_all() can drop indent leaked by an exception.
_INSTANCES = []


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
    """Write the pending debug run as one console.print and empty the buffer."""
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


def _write(console, text, level, channel, color, buffered):
    if not buffered or level not in _BUFFERED_LEVELS:
        flush_all()
        console.print(text, level=level, channel=channel, color=color, timestamp=True)
        return
    cap = _buffer_cap()
    text = _stamp(console) + text
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


class TreeConsole:
    def __init__(
        self,
        console: "Console | None" = None,
        default_level: str = "info",
        module: str = "",
        buffered: bool = True,
    ) -> None:
        self.console = console if console is not None else get_component("console")
        self.default_level = default_level
        self.buffered = buffered
        self._indent = 0
        self._blocks = []  # open blocks, outermost first: [level, header line, shown, channel, color, name]
        self._pending_color = ""
        self._pending_level = ""

        levels = archive.get(LOG_LEVELS_KEY, {}) or {}
        self.module = module
        self.verbose = levels.get(module, "normal") == "verbose"
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
        unless this module is `"verbose"` in the `console.log_levels` archive
        dict. For high-volume noise (method entry/exit, per-item loop detail)
        safe to sprinkle liberally without a runtime cost by default."""
        if not self.verbose:
            return
        self._pending_level = "debug"
        self._emit(msg, channel)

    def start(self, msg: str, channel: str = "", level: str = "") -> None:
        """Open a named block and indent everything logged until the matching `end()`. A block at
        `level` "debug" writes its header only when a line is first logged inside it."""
        block_level = level or self.default_level
        block = [block_level, self._prefix() + _START + msg, False, channel, self._pending_color, msg]
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
        block = self._blocks.pop() if self._blocks else [self.default_level, "", True, "", "", ""]
        if block[0] in _BUFFERED_LEVELS:
            if not block[2]:
                return
            msg = msg or "END " + block[5]
        self._pending_level = self._pending_level or block[0]
        self._emit(_END + msg, channel or block[3], headers=False)
        if self._indent == 0 and block[0] not in _BUFFERED_LEVELS:
            flush_all()

    def reset(self) -> None:
        """Drop this instance's open blocks (see `reset_all()`)."""
        self._indent = 0
        self._blocks = []

    def flush(self) -> None:
        """Write any buffered debug lines now (call before `sleep()` in run loops)."""
        flush_all()

    def _prefix(self) -> str:
        return _BRANCH * self._indent

    def _show_headers(self) -> None:
        """Write the headers of blocks that have not shown theirs yet, outermost first."""
        for block in self._blocks:
            if block[2]:
                continue
            block[2] = True
            _write(self.console, block[1], block[0], block[3], block[4], self.buffered)

    def _emit(self, msg: str, channel: str, headers: bool = True) -> None:
        if self.console is None:
            self._pending_color = ""
            self._pending_level = ""
            return
        level = self._pending_level or self.default_level
        color = self._pending_color
        self._pending_color = ""
        self._pending_level = ""
        if headers:
            self._show_headers()
        _write(self.console, self._prefix() + msg, level, channel, color, self.buffered)
