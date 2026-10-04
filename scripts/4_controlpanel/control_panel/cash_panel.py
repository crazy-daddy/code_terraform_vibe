# ct-panel: cash_panel
# Control Room CASH card: the cash manager's view (lib/cash.py, docs/AI_CHEATSHEET.md
# §2l). Reads cash.budget, which the headless control_room_automation.py writes every
# storage pass, and draws nothing of its own logic:
#   - top row: balance, floor, measured income/h and reagent burn/h, the Earth
#     Order pipeline (campaign rewards still to earn, weekly board);
#   - one row per consumer kind: reagents first, then capital kinds in
#     priority order, each with its next cost, planned total and ETA, and
#     up/down buttons that reorder the capital priority (cash.budget["priority"]).
#
# Recommended card size: 2 x 2.
# New save: create an empty Custom Panel in-game -- see docs/cheatsheet/panels.md §7.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import panel

from cash import budget, priority_order, move_priority, kind_of, is_operating, OPERATING, CONSUMER_LABELS
from swallow import swallowed

ROW_H = 26
BUTTON_W = 26


def fmt_cr(value):
    """12345 -> '12.3k', None -> '?'."""
    if value is None:
        return "?"
    value = float(value)
    if abs(value) >= 1000000:
        return f"{value / 1000000:.2f}M"
    if abs(value) >= 1000:
        return f"{value / 1000:.1f}k"
    return f"{value:.0f}"


def fmt_eta(hours):
    if hours is None:
        return "no income yet"
    if hours <= 0:
        return "now"
    if hours >= 48:
        return f"{hours / 24:.1f} d"
    return f"{hours:.1f} h"


def kind_rows(state):
    """[(kind, cost, planned, eta_h or None, held, count)] per consumer kind, operating first then capital by priority."""
    grouped = {}
    for row in state.get("queue") or []:
        kind = kind_of(str(row.get("consumer", "")))
        g = grouped.setdefault(kind, {"cost": 0, "planned": 0, "eta": 0.0, "held": False, "count": 0})
        g["cost"] += int(row.get("cost", 0))
        g["planned"] += int(row.get("planned", 0))
        g["held"] = g["held"] or bool(row.get("held"))
        g["count"] += 1
        eta = row.get("eta_h")
        g["eta"] = None if eta is None or g["eta"] is None else max(g["eta"], eta)
    kinds = list(OPERATING) + priority_order(state) + sorted(k for k in grouped if k not in OPERATING and k not in priority_order(state))
    rows = []
    for kind in kinds:
        g = grouped.get(kind)
        if g is None:
            rows.append((kind, 0, 0, 0.0, False, 0))
        else:
            rows.append((kind, g["cost"], g["planned"], g["eta"], g["held"], g["count"]))
    return rows


while True:
    panel.clear()
    width = panel.width()
    height = panel.height()
    panel.card(8, 8, width - 16, height - 16, "CASH")
    try:
        state = budget()
    except Exception as error:
        swallowed("cash_panel: budget", error)
        state = {}

    col_w = (width - 48) / 4
    pipeline = state.get("pipeline") or {}
    tops = [
        ("BALANCE", fmt_cr(state.get("balance")), f"floor {fmt_cr(state.get('floor'))}"),
        ("INCOME", f"{fmt_cr(state.get('income_h'))}/h", f"over {state.get('span_h', 0)} h"),
        ("REAGENTS", f"{fmt_cr(state.get('burn_h'))}/h", "burn"),
        ("ORDERS", fmt_cr(pipeline.get("campaign", 0) + pipeline.get("weekly", 0)), f"weekly {fmt_cr(pipeline.get('weekly', 0))}"),
    ]
    for index, (caption, value, note) in enumerate(tops):
        x = 24 + index * col_w
        panel.label(x, 42, caption, "caption")
        panel.label(x, 66, value, "value")
        panel.label(x, 88, note, "muted")

    top = 110
    panel.draw_text(24, top, f"planned {fmt_cr(state.get('planned', 0))} cr", 10, "text-secondary")
    max_rows = max(0, int((height - top - 24) // ROW_H))
    for index, (kind, cost, planned, eta, held, count) in enumerate(kind_rows(state)[:max_rows]):
        y = top + 12 + index * ROW_H
        name = str(CONSUMER_LABELS.get(kind, kind)) + (f" x{count}" if count > 1 else "")
        if count == 0:
            panel.pill(24, y + 2, "IDLE", "text-muted")
        elif held:
            panel.pill(24, y + 2, "BUYING", "accent")
        else:
            panel.pill(24, y + 2, "WAIT", "warning")
        detail = f"{name}: next {fmt_cr(cost)}, planned {fmt_cr(planned)}, {fmt_eta(eta)}" if count else name
        panel.draw_text(110, y + 16, detail[: int((width - 200) // 6)], 10, "text-value")
        if not is_operating(kind):
            if panel.button(f"cash_up_{kind}", width - 24 - 2 * BUTTON_W - 6, y, BUTTON_W, 22, "^"):
                move_priority(kind, -1)
            if panel.button(f"cash_down_{kind}", width - 24 - BUTTON_W, y, BUTTON_W, 22, "v"):
                move_priority(kind, 1)
