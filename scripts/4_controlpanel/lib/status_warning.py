"""
Repeating machine warnings shown as the script status.

A condition a controller checks every poll (pump stalled, buffer full) logs
one warn line when it starts and one info line when it ends, with how long it
lasted. In between it shows as the script status (`set_status()`,
docs/guide/builtins_and_commands.md): `set_status()` and `clear_status()` cost
no game time, a console line costs 0.1 s (CODE_GUIDES.md#logging).

    self.stall_warning = StatusWarning(self.log, self.name, "Stalled")
    ...
    self.stall_warning.update(stalled, "Stalled: valve open but ...")

The status belongs to the script run, so every StatusWarning of one script
shares it: the active messages are joined with " | ", the most severe level
wins. A stopped or restarted script clears it (game behaviour); a new run
starts with no active warning, so the next stalled poll logs again.
"""
from typing import TYPE_CHECKING

from game_clock import now_tick
from swallow import swallowed

if TYPE_CHECKING:
    from tree_console import TreeConsole

TICKS_PER_SECOND = 10
STATUS_MAX_CHARS = 240  # set_status() raises ValueError above this
_LEVEL_RANK = {"info": 0, "warn": 1, "error": 2}

# {key: (message, level)} of this script run's active warnings, in start order.
_ACTIVE = {}
_SHOWN: "dict[str, tuple[str, str] | None]" = {"status": None}  # last (text, level) sent to set_status, None when cleared


def _publish():
    """Pushes the joined active messages to the script status; no call when nothing changed."""
    if _ACTIVE:
        entries = list(_ACTIVE.values())
        text = " | ".join(message for message, _level in entries)[:STATUS_MAX_CHARS]
        level = max((level for _message, level in entries), key=lambda name: _LEVEL_RANK.get(name, 0))
        shown = (text, level)
    else:
        shown = None
    if shown == _SHOWN["status"]:
        return
    try:
        if shown is None:
            clear_status()
        else:
            set_status(shown[0], shown[1])
        _SHOWN["status"] = shown
    except Exception as error:
        swallowed("status_warning._publish: set_status", error)


class StatusWarning:
    """One repeating warning: log on start and on clear, script status while active."""

    def __init__(self, log: "TreeConsole", name, label, level="warn"):
        self.log = log
        self.name = name
        self.label = label
        self.level = level
        self.key = f"{name}:{label}"
        self.since_tick = None  # tick the warning started; None while inactive

    @property
    def active(self):
        return self.since_tick is not None

    def update(self, active, message=""):
        """Feeds one poll. message (plain text, the machine name is added) is logged on the
        first active poll and refreshes the status on later ones."""
        if active:
            text = f"[{self.name}] {message}"
            if self.since_tick is None:
                self.since_tick = now_tick("status_warning.update: start")
                self.log.level(self.level).print(text)
            _ACTIVE[self.key] = (text, self.level)
            _publish()
            return
        if self.since_tick is None:
            return
        ticks = max(0, now_tick("status_warning.update: clear") - self.since_tick)
        self.log.print(f"[{self.name}] {self.label} cleared after {ticks / TICKS_PER_SECOND:.0f} s (since tick {self.since_tick}).")
        self.since_tick = None
        _ACTIVE.pop(self.key, None)
        _publish()
