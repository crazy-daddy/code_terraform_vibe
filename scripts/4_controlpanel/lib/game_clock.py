"""
Game clock reads. The fixed time rules (ticks per second, game hour length)
live in game_rules.

now_tick() is the one place that reads clock.tick() (docs/components/clock.md)
with the CODE_GUIDES.md#errors fallback. The clock is looked up on every call
(one get_component() call) rather than cached, so a test that swaps the
injected world also swaps the clock.
"""

from typing import TYPE_CHECKING

from game_rules import SECONDS_PER_GAME_HOUR
from swallow import swallowed

if TYPE_CHECKING:
    from typing import Callable, TypeVar

    T = TypeVar("T")


def real_seconds_per_hour(clock=None, where="game_clock.real_seconds_per_hour"):
    """Real seconds per world-clock hour from clock.real_seconds_per_hour() (`clock` or the
    clock component); SECONDS_PER_GAME_HOUR when unreadable or not positive."""
    try:
        clock = clock if clock is not None else get_component("clock")
        reader = getattr(clock, "real_seconds_per_hour", None) if clock is not None else None
        seconds = float(reader()) if reader is not None else 0.0
        if seconds > 0:
            return seconds
    except Exception as error:
        swallowed(where, error)
    return SECONDS_PER_GAME_HOUR


def now_tick(where="game_clock.now_tick"):
    """Current simulation tick; 0 without a readable clock. `where` labels a swallowed error."""
    try:
        clock = get_component("clock")
        return clock.tick() if clock else 0
    except Exception as error:
        swallowed(where, error)
        return 0


def now_hours(default: "float | T" = 0.0, where="game_clock.now_hours") -> "float | T":
    """Elapsed game hours from clock.elapsed_game_hours(); `default` without a readable clock.
    `where` labels a swallowed error."""
    try:
        clock = get_component("clock")
        return float(clock.elapsed_game_hours()) if clock and hasattr(clock, "elapsed_game_hours") else default
    except Exception as error:
        swallowed(where, error)
        return default


def is_fresh(entry, curr_tick, stale_ticks):
    """True when `entry` is a dict stamped ("tick") less than stale_ticks before curr_tick.
    A non-dict or a missing stamp is stale. A stamp at or after curr_tick is fresh, so
    with no readable clock (curr_tick 0) every stamped entry still holds."""
    if not isinstance(entry, dict):
        return False
    stamp = entry.get("tick")
    return stamp is not None and curr_tick - stamp < stale_ticks


class TickCache:
    """
    Values recomputed at most every ttl_ticks simulation ticks, one per key.

    get() reuses a value younger than ttl_ticks and recomputes it when it is
    missing or invalidated, at curr_tick 0 (no readable clock: a stale value
    is the failure a cache must never cause), when the clock went backwards,
    or, with keep_empty=False, when the cached value is empty. compute()
    returning None means "unreadable": the previous value stays and the next
    get() tries again. single=True keeps one entry, so a key that is a
    signature of the inputs (counts, layout size) replaces the old entry.
    Values are shared between callers: treat them as read-only.
    """

    def __init__(self, ttl_ticks, keep_empty=True, single=False):
        self.ttl_ticks = ttl_ticks
        self.keep_empty = keep_empty
        self.single = single
        self._entries: dict = {}  # {key: (tick or None when invalidated, value)}

    def get(self, compute: "Callable[[], T]", key=None, curr_tick=None) -> "T":
        now = now_tick() if curr_tick is None else curr_tick
        entry = self._entries.get(key)
        if entry is not None and entry[0] is not None and now != 0 and 0 <= now - entry[0] < self.ttl_ticks and (self.keep_empty or entry[1]):
            return entry[1]
        value = compute()
        if value is None:
            if entry is not None:
                return entry[1]
        else:
            if self.single:
                self._entries.clear()
            self._entries[key] = (now, value)
        return value

    def peek(self, key=None):
        """Last value stored for key, however old; None when there is none."""
        entry = self._entries.get(key)
        return entry[1] if entry is not None else None

    def invalidate(self, key=None):
        """Next get(key) recomputes; the old value stays readable through peek()."""
        entry = self._entries.get(key)
        if entry is not None:
            self._entries[key] = (None, entry[1])

    def clear(self):
        self._entries.clear()
