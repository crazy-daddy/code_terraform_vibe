# ct-panel: cash_panel
# Control Room CASH card: the cash manager's view (lib/cash.py, docs/AI_CHEATSHEET.md
# §2l). Reads cash.budget, which the headless orchestrator_automation.py writes every
# storage pass, and draws nothing of its own logic:
#   - top row: balance, floor, measured income/h and reagent burn/h, the Earth
#     Order pipeline (campaign rewards still to earn, weekly board);
#   - one selectable list, a row per consumer kind: fixed reagent rows first ("="),
#     then capital kinds numbered in priority order. A non-idle row leads with its
#     BUYING/WAIT state, next cost, planned total and ETA; an idle row is just "-".
#     The ^ / v / top / bottom buttons beside the list reorder the selected capital
#     row (cash.budget["priority"]); the selection follows the moved row.
#   - 2 x 1 drops the header notes to fit; the list scrolls with the wheel.
#
# Recommended card size: 2 x 2 (also fits 2 x 1).
# New save: create an empty Custom Panel in-game -- see docs/cheatsheet/panels.md §7.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import panel

from cash import budget, priority_order, move_priority, set_priority, kind_of, is_operating, OPERATING, CONSUMER_LABELS
from swallow import swallowed

LIST_KEY = "cash_list"
ROW_H = 22
BUTTON_W = 70
BUTTON_H = 22
BUTTON_GAP = 2
COMPACT_H = 300   # card heights below this use the one-line header


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


def row_text(kind, cost, planned, eta, held, count, rank):
    """List line for one kind: rank marker ("=" for a fixed reagent row), state, name, amounts."""
    name = str(CONSUMER_LABELS.get(kind, kind)) + (f" x{count}" if count > 1 else "")
    mark = "=" if is_operating(kind) else f"{rank}."
    if count == 0:
        return f"{mark}  -  {name}"
    state = "BUYING" if held else "WAIT"
    return f"{mark}  {state}  {name}: next {fmt_cr(cost)}, planned {fmt_cr(planned)}, {fmt_eta(eta)}"


def move_selected(kind, step):
    """Moves kind one place (step +-1) with move_priority, or to the top/bottom (step "top"/"bottom") in one write."""
    if step in ("top", "bottom"):
        order = [k for k in priority_order() if k != kind]
        set_priority([kind] + order if step == "top" else order + [kind])
    else:
        move_priority(kind, step)


while True:
    panel.clear()
    width = panel.width()
    height = panel.height()
    compact = height < COMPACT_H
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
        if compact:
            panel.label(x, 34, caption, "caption")
            panel.label(x, 52, f"{value}  {note}", "value")
        else:
            panel.label(x, 42, caption, "caption")
            panel.label(x, 66, value, "value")
            panel.label(x, 88, note, "muted")

    top = 78 if compact else 110
    if not compact:
        panel.draw_text(24, top, f"planned {fmt_cr(state.get('planned', 0))} cr", 10, "text-secondary")
        top += 8
    rows = kind_rows(state)
    kinds = [r[0] for r in rows]
    items = []
    rank = 0
    for row in rows:
        if not is_operating(row[0]):
            rank += 1
        items.append(row_text(row[0], row[1], row[2], row[3], row[4], row[5], rank))
    list_h = height - top - 20
    list_w = width - 48 - BUTTON_W - 8
    panel.list(LIST_KEY, 24, top, list_w, list_h, items, ROW_H)
    # By row number, not text: row text changes with every amount.
    selected = min(panel.get_selected(LIST_KEY) or 0, len(items) - 1) if items else None
    kind = kinds[selected] if selected is not None else None
    movable = kind is not None and not is_operating(kind)

    bx = width - 24 - BUTTON_W
    steps = [("top", "top", "top"), ("up", -1, "^"), ("down", 1, "v"), ("bottom", "bottom", "bottom")]
    for slot, (key, step, label) in enumerate(steps):
        y = top + slot * (BUTTON_H + BUTTON_GAP)
        if panel.button(f"cash_{key}", bx, y, BUTTON_W, BUTTON_H, label) and movable:
            move_selected(kind, step)
            # Selection follows the moved kind: its new row in the rebuilt order.
            try:
                after = [r[0] for r in kind_rows(budget())]
                panel.set_selected(LIST_KEY, after.index(kind))
            except Exception as error:
                swallowed("cash_panel: reselect", error)
    if kind is not None and not movable:
        panel.draw_text(bx, top + 4 * (BUTTON_H + BUTTON_GAP) + 10, "fixed row", 10, "text-muted")
