"""
Shared run loop and small helpers for single-machine controllers.

MachineController.run() is the loop every machine script ends in: one
online line, the game-version check, then per pass reset_all() (an escaped
exception must not leave the log indented), step() inside a guard that logs
the exception, next_sleep(), flush_all() and sleep(). A subclass sets LABEL
and its poll attributes and overrides next_sleep() when its step() result
needs more than the default reading.
"""
from typing import TYPE_CHECKING

from tree_console import flush_all, reset_all
from version_guard import validate_game_version
from game_clock import now_tick
from swallow import swallowed

if TYPE_CHECKING:
    from typing import Any
    from tree_console import TreeConsole
    from script_parking import ParkRequester


def port_counts(port, where):
    """{item_id: units} held in a port's stacks; {} when unreadable. `where` labels a swallowed error."""
    out = {}
    if not port or not hasattr(port, "stacks"):
        return out
    try:
        for stack in port.stacks():
            if stack.count > 0:
                out[stack.id] = out.get(stack.id, 0) + stack.count
    except Exception as error:
        swallowed(where, error)
    return out


class MachineController:
    LABEL: str = "Machine"  # "<LABEL> exception: ..." in the error line
    STEP_DELAY: bool = False  # step() returns the seconds to sleep
    POLL_S: float = 5.0     # sleep when step() gives no delay
    ERROR_POLL_S: "float | None" = None  # sleep after step() raised; None = POLL_S
    PARK_IDLE_S: "float | None" = None   # set: a delay equal to this counts as idle for self.parker

    if TYPE_CHECKING:
        name: str
        log: "TreeConsole"

        def step(self) -> "Any": ...

    def online_message(self):
        return f"{self.LABEL} ({self.name}) online."

    def error_label(self) -> str:
        return self.LABEL

    def get_current_tick(self):
        return now_tick()

    def next_sleep(self, result, failed) -> "float | None":
        """
        Seconds to sleep after a pass, or None to end the script. result is
        step()'s return value (None when it raised; failed is then True). A
        number is the delay; anything else sleeps POLL_S. With PARK_IDLE_S set,
        the parker hears whether the delay is the idle one.
        """
        if failed:
            delay = self.POLL_S if self.ERROR_POLL_S is None else self.ERROR_POLL_S
        elif self.STEP_DELAY and isinstance(result, (int, float)) and not isinstance(result, bool):
            delay = result
        else:
            delay = self.POLL_S
        if self.PARK_IDLE_S is not None:
            parker: "ParkRequester | None" = getattr(self, "parker", None)
            if parker is not None:
                parker.update(delay == self.PARK_IDLE_S)
        return delay

    def run(self):
        self.log.print(self.online_message())
        validate_game_version()
        while True:
            reset_all()
            result = None
            failed = False
            try:
                result = self.step()
            except Exception as error:
                failed = True
                self.log.level("error").print(f"[{self.name}] {self.error_label()} exception: {error}")
            delay = self.next_sleep(result, failed)
            if delay is None:
                flush_all()
                return
            flush_all()
            sleep(delay)
