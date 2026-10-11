# ct-panel: orders_panel
# Control Room ORDERS card: every active Earth order with its priority and the
# operator override (lib/supply_dock.py order_rows()/set_order_override(); ladder in
# lib/priority.py). Holds no ranking logic:
#   - one selectable list, most urgent first: "<prio> <band> <name> -- needs: ... --
#     docks: ..." plus " [override]" when the operator pinned a prio;
#   - +10 / -10 / Top / Reset beside the list act on the selected row. A click shows
#     in the row at once (the dock planner republishes the prio on its own cadence).
#
# Recommended card size: 2 x 1 (a 2 x 2 shows more rows).
# New save: create an empty Custom Panel in-game -- see docs/cheatsheet/panels.md §7.

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from user_stubs import panel

from game_clock import now_tick
from priority import BLOCKER, band_name, clamp
from supply_dock import order_overrides, order_rows, set_order_override
from swallow import swallowed

LIST_KEY = "orders_list"
ROW_H = 22
BUTTON_W = 70
BUTTON_H = 22
BUTTON_GAP = 2
READ_EVERY_TICKS = 20  # ~2 s of game time between order_rows() reads
STEP = 10
TOP_PRIO = BLOCKER - 1  # just under BLOCKER


def effective_prio(row, overrides):
    """The prio the row shows: the operator override when set, else the published one."""
    override = overrides.get(row["id"])
    return override if override is not None else row.get("prio")


def fmt_items(items):
    return ", ".join(f"{item} {n}" for item, n in sorted(items.items())) or "-"


def row_text(row, overrides):
    prio = effective_prio(row, overrides)
    has_override = row["id"] in overrides
    band = band_name(prio) if has_override else row.get("band", "-")
    text = f"{'-' if prio is None else prio} {band} {row['name']} -- needs: {fmt_items(row.get('needs') or {})} -- docks: {', '.join(str(d) for d in row.get('docks') or []) or '-'}"
    return text + " [override]" if has_override else text


rows = []
overrides = {}
read_tick = None
selected_id = None

while True:
    panel.clear()
    width = panel.width()
    height = panel.height()
    panel.card(8, 8, width - 16, height - 16, "ORDERS")

    tick = now_tick()
    if read_tick is None or tick - read_tick >= READ_EVERY_TICKS:
        read_tick = tick
        try:
            rows = order_rows()
            overrides = order_overrides()
        except Exception as error:
            swallowed("orders_panel: order_rows", error)
        if selected_id is not None:
            ids = [r["id"] for r in rows]
            if selected_id in ids:
                panel.set_selected(LIST_KEY, ids.index(selected_id))

    top = 40
    items = [row_text(r, overrides) for r in rows]
    list_h = height - top - 20
    list_w = width - 48 - BUTTON_W - 8
    if items:
        panel.list(LIST_KEY, 24, top, list_w, list_h, items, ROW_H)
        index = min(panel.get_selected(LIST_KEY) or 0, len(rows) - 1)
        row = rows[index]
        selected_id = row["id"]
    else:
        panel.draw_text(24, top + 4, "no active orders", 12, "text-muted")
        row = None

    bx = width - 24 - BUTTON_W
    base = effective_prio(row, overrides) if row is not None else None
    buttons = [
        ("up", "+10", None if base is None else clamp(base + STEP)),
        ("down", "-10", None if base is None else clamp(base - STEP)),
        ("top", "Top", TOP_PRIO),
        ("reset", "Reset", None),
    ]
    for slot, (key, label, value) in enumerate(buttons):
        y = top + slot * (BUTTON_H + BUTTON_GAP)
        if panel.button(f"orders_{key}", bx, y, BUTTON_W, BUTTON_H, label) and row is not None:
            if key != "reset" and value is None:
                continue
            try:
                set_order_override(row["id"], value)
                if value is None:
                    overrides.pop(row["id"], None)
                else:
                    overrides[row["id"]] = value
            except Exception as error:
                swallowed("orders_panel: set_order_override", error)
