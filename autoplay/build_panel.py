# ct-panel: build_panel
# Control Room BUILD card: the building planner's proposals (autoplay/lib/building_plan.py,
# docs/plans/building_planner.md). Reads autoplay.build_proposals, which the
# infrastructure planner Automation writes; one list row per proposal (status,
# outpost, building and count, kit source, provider and why). Approve / Reject act
# on the selected row; an approved proposal becomes building jobs on the planner's
# next pass. A blocked row (over the cap, a refused job) can only be rejected.
#
# Recommended card size: 2 x 1 (also fits 2 x 2). Deployed only with
# `scripts_sync.py ... --include-autoplay`. New save: create an empty Custom Panel
# in-game -- see docs/cheatsheet/panels.md §7.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import panel

from building_plan import load, answer
from swallow import swallowed

LIST_KEY = "build_list"
ROW_H = 22
BUTTON_W = 80
BUTTON_H = 22
BUTTON_GAP = 4
STATUS_ORDER = ("proposed", "approved", "queued", "rejected")
KIT_TEXT = {"inventory": "kit in Inventory", "available": "kit to buy/craft", None: "no kit"}


def rows(proposals):
    """[(proposal_id, line)] open entries first (status order), then by id."""
    out = []
    for pid, e in proposals.items():
        if not isinstance(e, dict):
            continue
        status = e.get("status") or "?"
        if e.get("kind") == "deploy":
            what = f"+{e.get('count', 1)} {e.get('type_id')} at {e.get('outpost')}"
        else:
            what = f"retire {e.get('machine_id')}"
        note = f"BLOCKED {e['blocked']}" if e.get("blocked") else KIT_TEXT.get(e.get("kit_source"), "")
        rank = STATUS_ORDER.index(status) if status in STATUS_ORDER else len(STATUS_ORDER)
        out.append((rank, pid, f"{status.upper()}  {what}  [{note}]  {e.get('provider')}: {e.get('why')}"))
    return [(pid, line) for _rank, pid, line in sorted(out)]


while True:
    panel.clear()
    width = panel.width()
    height = panel.height()
    panel.card(8, 8, width - 16, height - 16, "BUILD")
    try:
        listed = rows(load())
    except Exception as error:
        swallowed("build_panel: load", error)
        listed = []
    top = 40
    list_w = width - 48 - BUTTON_W - 8
    if not listed:
        panel.draw_text(24, top, "no building proposals", 11, "text-muted")
    panel.list(LIST_KEY, 24, top, list_w, height - top - 20, [line for _pid, line in listed], ROW_H)
    selected = min(panel.get_selected(LIST_KEY) or 0, len(listed) - 1) if listed else None
    pid = listed[selected][0] if selected is not None else None
    bx = width - 24 - BUTTON_W
    if panel.button("build_approve", bx, top, BUTTON_W, BUTTON_H, "Approve") and pid:
        answer(pid, True)
    if panel.button("build_reject", bx, top + BUTTON_H + BUTTON_GAP, BUTTON_W, BUTTON_H, "Reject") and pid:
        answer(pid, False)
