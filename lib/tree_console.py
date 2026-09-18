"""Indented, tree-drawn console logging shared across scripts.

Wraps the `console` component (docs/components/console.md) so both the
quick overview and the in-depth reasoning trail read like a call stack in
the Console tab instead of a flat scroll of unindented lines.

Two levels, same tree formatting:
- `print()`/`start()`/`end()` default to **info** — the beautified, always
  visible overview (major blocks, outcomes) a player can skim at a glance.
- `debug()` logs the deeper "why" (candidates considered, computed
  thresholds, per-item reasoning) at **debug** level, hidden from the ALL
  view unless the player opts into debug output.

See docs/AI_CHEATSHEET.md #0a for the usage pattern.
"""

_BRANCH = "┃   "  # "┃   "
_START = "┏━ "  # "┏━ "
_END = "┗━ "  # "┗━ "


class TreeConsole:
    def __init__(self, console: "Console | None" = None, default_level: str = "info") -> None:
        self.console = console if console is not None else get_component("console")
        self.default_level = default_level
        self._indent = 0
        self._pending_color = ""
        self._pending_level = ""

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
