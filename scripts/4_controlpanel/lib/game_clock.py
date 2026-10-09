"""
Game clock reads.

now_tick() is the one place that reads clock.tick() (docs/components/clock.md)
with the CODE_GUIDES.md#errors fallback. The clock is looked up on every call
(one get_component() call) rather than cached, so a test that swaps the
injected world also swaps the clock.
"""
from swallow import swallowed


def now_tick(where="game_clock.now_tick"):
    """Current simulation tick; 0 without a readable clock. `where` labels a swallowed error."""
    try:
        clock = get_component("clock")
        return clock.tick() if clock else 0
    except Exception as error:
        swallowed(where, error)
        return 0


def is_fresh(entry, curr_tick, stale_ticks):
    """True when `entry` is a dict stamped ("tick") less than stale_ticks before curr_tick.
    A non-dict or a missing stamp is stale. A stamp at or after curr_tick is fresh, so
    with no readable clock (curr_tick 0) every stamped entry still holds."""
    if not isinstance(entry, dict):
        return False
    stamp = entry.get("tick")
    return stamp is not None and curr_tick - stamp < stale_ticks
