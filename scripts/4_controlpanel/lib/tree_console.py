"""Indented, tree-drawn console logging shared across scripts.

Wraps the `console` component (docs/components/console.md) so both the
quick overview and the in-depth reasoning trail read like a call stack in
the Console tab instead of a flat scroll of unindented lines.

Three levels, same tree formatting:
- `print()`/`start()`/`end()` default to **info** — the beautified, always
  visible overview (major blocks, outcomes) a player can skim at a glance.
- `debug()` logs the deeper "why" (candidates considered, computed
  thresholds, per-item reasoning) at **debug** level, hidden from the ALL
  view unless the player opts into debug output. Cheap enough to leave on
  everywhere.
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

Construct one instance per controller in `__init__` (or once before a
`run_*_loop()`'s `while True:`, never inside it) and store it as `self.log`/
`log` -- constructing it reads the `console.log_levels` archive dict, so
re-constructing per call or per tick defeats the point. Name it `log`, not
`tree` -- the tree-drawing is just formatting, `log` is what it's for.

See docs/AI_CHEATSHEET.md #0a for the usage pattern.
"""

from archive import archive

_BRANCH = "┃   "  # "┃   "
_START = "┏━ "  # "┏━ "
_END = "┗━ "  # "┗━ "

LOG_LEVELS_KEY = "console.log_levels"


class TreeConsole:
    def __init__(
        self,
        console: "Console | None" = None,
        default_level: str = "info",
        module: str = "",
    ) -> None:
        self.console = console if console is not None else get_component("console")
        self.default_level = default_level
        self._indent = 0
        self._pending_color = ""
        self._pending_level = ""

        levels = archive.get(LOG_LEVELS_KEY, {}) or {}
        self.module = module
        self.verbose = levels.get(module, "normal") == "verbose"

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

    def start(self, msg: str, channel: str = "") -> None:
        """Open a named block and indent everything logged until the matching `end()`."""
        self.print(_START + msg, channel)
        self._indent += 1

    def end(self, msg: str, channel: str = "") -> None:
        """Dedent and close the block opened by the matching `start()`."""
        self._indent = max(0, self._indent - 1)
        self.print(_END + msg, channel)

    def _emit(self, msg: str, channel: str) -> None:
        if self.console is None:
            return
        prefix = _BRANCH * self._indent
        level = self._pending_level or self.default_level
        color = self._pending_color
        self.console.print(prefix + msg, level=level, channel=channel, color=color, timestamp=True)
        self._pending_color = ""
        self._pending_level = ""
