# ct-panel: vehicles_panel
# Control Room FLEET card with three tabs, each a shared view from lib/:
#   Ground     - lib/vehicles_card.py: cruise throttle, drone yield, counts
#                per activity, vehicle roster + detail pane (recall, retire,
#                Sport Nav request).
#   Drones     - lib/drones_card.py: cruise throttle, auto-upgrade switch, drone
#                roster + detail pane (recall, retire).
#   Commission - lib/commission_card.py: role buttons, outpost pickers, job queue.
# Every control is a pure intent publish (archive writes); each vehicle's,
# drone's or the Automation's own script acts on it.
#
# The roster is a panel.list(): wheel to scroll, click a row to show that
# unit in the detail pane. The active tab and the selected rows are stored
# with the card, so they survive a script restart.
#
# Recommended card size: 2 x 2 (1000x400). 2 x 1 works with a 3-row roster.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import panel

from fleet_card import tabs, CONTENT_X, CONTENT_Y, CONTENT_BOTTOM_PAD, TAB_H
from vehicles_card import draw_ground
from drones_card import draw_drones
from commission_card import CommissionView
from tree_console import reset_all, flush_all

TAB_LABELS = ["Ground", "Drones", "Commission"]

commission = CommissionView()

while True:
    reset_all()
    flush_all()
    panel.clear()
    width = panel.width()
    height = panel.height()
    panel.card(8, 8, width - 16, height - 16, "FLEET")  # card() already renders its own title bar text

    tab = tabs(panel, "fleet_tab", CONTENT_X, CONTENT_Y, TAB_LABELS)
    x = CONTENT_X
    y = CONTENT_Y + TAB_H + 10
    w = width - 2 * CONTENT_X
    h = height - CONTENT_BOTTOM_PAD - y
    if tab == 1:
        draw_drones(panel, x, y, w, h)
    elif tab == 2:
        commission.draw(panel, x, y, w, h)
    else:
        draw_ground(panel, x, y, w, h)
