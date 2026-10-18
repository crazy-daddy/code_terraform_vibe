# ct-panel: build_panel
# Control Room BUILD card: the building planner's proposals (autoplay/lib/building_plan.py,
# docs/plans/building_planner.md). Reads autoplay.build_proposals, which the
# infrastructure planner Automation writes; one list row per proposal (status,
# outpost, building and count, kit source or job progress, provider and why;
# outposts by display name as on the fleet cards). Approve / Reject act
# on the selected row; an approved proposal becomes building jobs on the planner's
# next pass (a FOCUS swap row: a pillar swap request). A blocked row (over the cap,
# a refused job) can only be rejected. The line above the list shows the
# atmosphere focus (autoplay.focus): the pillar to push, the mode and why.
#
# Recommended card size: 2 x 1 (also fits 2 x 2). Deployed only with
# `scripts_sync.py ... --include-autoplay`. New save: create an empty Custom Panel
# in-game -- see docs/cheatsheet/panels.md §7.

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from user_stubs import panel

from archive import archive
from building_ops import jobs
from building_plan import answer, load
from fleet_status import outpost_names
from focus_plan import FOCUS_KEY
from outpost_mining import HOME_OUTPOST_ID
from panel_pace import pace
from pillar_swap import PILLAR_LABELS
from swallow import swallowed

LIST_KEY = "build_list"
ROW_H = 22
BUTTON_W = 80
BUTTON_H = 22
BUTTON_GAP = 4
STATUS_ORDER = ("proposed", "approved", "queued", "rejected")
EMPTY_HINT = "the infrastructure planner lists new proposals here"
KIT_TEXT = {"inventory": "kit in Inventory", "available": "kit to buy/craft", None: "no kit"}


def place(outpost, names):
    """ " @ <name>" of an outpost id (display name as on the fleet cards), "" for None."""
    return f" @ {names.get(outpost, outpost)}" if outpost else ""


def note(e, build_jobs):
    """Bracket note: the block reason, a queued row's job progress, a deploy / upgrade's kit source, else ""."""
    if e.get("blocked"):
        return f"BLOCKED {e['blocked']}"
    if e.get("status") == "queued":
        ids = [job_id for job_id in e.get("jobs") or [] if job_id]
        waiting = sum(1 for job_id in ids if (build_jobs.get(job_id) or {}).get("state") == "kit")
        if waiting:
            return f"waiting for kit {waiting}/{len(ids)}"
        return f"{len(ids)} job(s) running" if ids else "running"
    if e.get("kind") in ("deploy", "upgrade"):
        return KIT_TEXT.get(e.get("kit_source"), "")
    return ""


def rows(proposals, build_jobs=None, names=None):
    """[(proposal_id, line)] open entries first (status order), then by id. build_jobs = building_ops.jobs(); names = {outpost id: name}."""
    build_jobs = build_jobs or {}
    names = names or {}
    out = []
    for pid, e in proposals.items():
        if not isinstance(e, dict):
            continue
        status = e.get("status") or "?"
        if e.get("kind") == "deploy":
            what = f"+{e.get('count', 1)} {e.get('type_id')}{place(e.get('outpost') or HOME_OUTPOST_ID, names)}"
        elif e.get("kind") == "swap":
            source, target = str(e.get("from")), str(e.get("to"))
            what = f"FOCUS swap {PILLAR_LABELS.get(source, source)} -> {PILLAR_LABELS.get(target, target)}"
        elif e.get("kind") == "upgrade":
            what = f"upgrade {e.get('machine_id')}{place(e.get('outpost'), names)} with {e.get('item_id')}"
        elif e.get("kind") == "fleet":
            what = f"fleet {e.get('fleet_kind')} {e.get('role')} {int(e.get('delta') or 0):+d}"
        else:
            what = f"retire {e.get('machine_id')}{place(e.get('outpost'), names)}"
        text = note(e, build_jobs)
        rank = STATUS_ORDER.index(status) if status in STATUS_ORDER else len(STATUS_ORDER)
        out.append((rank, pid, f"{status.upper()}  {what}  {f'[{text}]  ' if text else ''}{e.get('provider')}: {e.get('why')}"))
    return [(pid, line) for _rank, pid, line in sorted(out)]


def focus_line():
    """One line for autoplay.focus: pillar to push, mode, current generators, first reason."""
    focus = archive.get(FOCUS_KEY, {}) or {}
    if not isinstance(focus, dict) or not focus.get("mode"):
        return "focus: none yet"
    why = (focus.get("why") or [""])[0]
    if not focus.get("pillar"):
        return f"focus: none ({focus.get('mode')}): {why}"
    current = str(focus.get("current") or "none")
    pillar = str(focus["pillar"])
    return f"focus {PILLAR_LABELS.get(pillar, pillar)} ({focus.get('mode')}), generators on {PILLAR_LABELS.get(current, current)}: {why}"


while True:
    panel.clear()
    width = panel.width()
    height = panel.height()
    panel.card(8, 8, width - 16, height - 16, "BUILD")
    try:
        listed = rows(load(), jobs(), outpost_names())
    except Exception as error:
        swallowed("build_panel: load", error)
        listed = []
    try:
        panel.draw_text(24, 40, focus_line(), 11, "text-muted")
    except Exception as error:
        swallowed("build_panel: focus_line", error)
    top = 40 + ROW_H
    list_w = width - 48 - BUTTON_W - 8
    if not listed:
        # Empty state: no list frame and no buttons, just a centered note in the card body.
        mid = (top + height - 20) / 2
        for dy, text, size, color in ((-10, "No building proposals", 13, "text"), (10, EMPTY_HINT, 11, "text-muted")):
            panel.draw_text(max(24, (width - len(text) * size * 0.6) / 2), mid + dy, text, size, color)
        pace(panel)
        continue
    panel.list(LIST_KEY, 24, top, list_w, height - top - 20, [line for _pid, line in listed], ROW_H)
    selected = min(panel.get_selected(LIST_KEY) or 0, len(listed) - 1) if listed else None
    pid = listed[selected][0] if selected is not None else None
    bx = width - 24 - BUTTON_W
    if panel.button("build_approve", bx, top, BUTTON_W, BUTTON_H, "Approve") and pid:
        answer(pid, True)
    if panel.button("build_reject", bx, top + BUTTON_H + BUTTON_GAP, BUTTON_W, BUTTON_H, "Reject") and pid:
        answer(pid, False)
    pace(panel)
