"""
Loop pacing for Control Room cards.

The game re-runs a card's loop every tick when it never sleeps, and a profile of
the live game put the cards at ~16 % of all script time: the cost is the Python
that gathers and formats each frame, not the drawing. sleep() commits the frame
first, so the card keeps showing it, and a button press stays queued until the
next frame's button() call answers it. Sleeping only delays the answer.

pace() sleeps one tick while the cursor is over the card (hover, drag, wheel and
clicks answer at once) and IDLE_SLEEP_S otherwise.
"""

from game_rules import TICKS_PER_SECOND
from swallow import swallowed
from tree_console import flush_all

ACTIVE_SLEEP_S = 1 / TICKS_PER_SECOND
IDLE_SLEEP_S = 1.0


def pace(panel, mouse=None):
    """Sleeps at the end of a card loop: ACTIVE_SLEEP_S while the cursor is over the card, else
    IDLE_SLEEP_S. A card that reads panel.mouse() itself passes that reading: mouse() hands out
    pressed/released only once, so a second read here could swallow them."""
    if mouse is None:
        try:
            mouse = panel.mouse()
        except Exception as error:
            swallowed("panel_pace.pace: panel.mouse", error)
    flush_all()
    sleep(ACTIVE_SLEEP_S if getattr(mouse, "over", False) else IDLE_SLEEP_S)
