# ct-panel: fleet_commission_panel
# Control Room COMMISSION card: launch new Pioneers. One button per role
# (lib/pioneer_commission.py PIONEER_PRESETS) queues a job; an outpost button
# cycles where it is deployed. Pure intent publish, same pattern as the other
# fleet cards: this card only writes fleet.commission, the headless
# automation_panel.py runs lib/fleet_commission.py, which buys the chassis and
# parts, deploys the chassis and waits for its script -- devtools/scripts_sync.py
# fills the new pioneer slot (and asks for HOME_BASE / DESTINATION_OUTPOST_ID).
# The Pioneer then fits its own parts.
#
# Below the buttons: the coordinator's status line and the job queue, each
# job with a cancel button while nothing is deployed yet (or it is blocked).
#
# Recommended card size: 2 x 1 (1000x200); 2 x 2 for a long queue. At one
# column the outpost button moves to its own row.
# New save: create an empty Custom Panel in-game -- see docs/cheatsheet/panels.md §7.

from pioneer_commission import PIONEER_PRESETS, commission_state, update_commission
from fleet_commission import queue_pioneer, cancel_job, CANCELLABLE_STATES
from outpost_mining import HOME_OUTPOST_ID
from swallow import swallowed

ROLE_LABELS = [("hauler", "+ Hauler"), ("miner", "+ Miner"), ("scout", "+ Scout"), ("constructor", "+ Builder")]
STATE_COLORS = {"queued": "text-muted", "buying": "accent", "deploying": "accent", "attach": "warning", "fitting": "accent", "blocked": "error"}
BUTTON_W = 100
BUTTON_H = 26
ROW_H = 28
# Panel loop iterations between outpost list refreshes.
OUTPOST_REFRESH_LOOPS = 100


def read_outposts():
    """[(id, name)] of every outpost, home first."""
    try:
        network = get_component("outpost_network")
        found = [(getattr(o, "id", ""), getattr(o, "name", "") or getattr(o, "id", "")) for o in network.outposts()] if network else []
    except Exception as error:
        swallowed("fleet_commission_panel.read_outposts: network.outposts", error)
        found = []
    found = [o for o in found if o[0]]
    found.sort(key=lambda o: (o[0] != HOME_OUTPOST_ID, o[0]))
    return found or [(HOME_OUTPOST_ID, "home")]


outposts = read_outposts()
loops = 0

while True:
    loops += 1
    if loops % OUTPOST_REFRESH_LOOPS == 0:
        outposts = read_outposts()

    panel.clear()
    width = panel.width()
    height = panel.height()
    panel.card(8, 8, width - 16, height - 16, "COMMISSION")
    wide = width >= 900
    state = commission_state()

    # Role buttons, one row.
    for index, (role, label) in enumerate(ROLE_LABELS):
        if role in PIONEER_PRESETS and panel.button(f"commission_{role}", 24 + index * (BUTTON_W + 8), 44, BUTTON_W, BUTTON_H, label):
            queue_pioneer(role, state.get("target_outpost") or HOME_OUTPOST_ID)

    # Outpost picker: right of the buttons when wide, else its own row.
    ids = [o[0] for o in outposts]
    target = state.get("target_outpost") or HOME_OUTPOST_ID
    target_name = next((o[1] for o in outposts if o[0] == target), target)
    picker_x, picker_y = (width - 230, 44) if wide else (24, 78)
    if panel.button("commission_outpost", picker_x, picker_y, 206, BUTTON_H, f"at {target_name}"[:28]):
        nxt = ids[(ids.index(target) + 1) % len(ids)] if target in ids else ids[0]
        update_commission(lambda s: s.update({"target_outpost": nxt}))

    status_y = 92 if wide else 126
    panel.draw_text(24, status_y, str(state.get("status", "idle"))[: int((width - 48) // 6)], 10, "text-secondary")

    jobs = [j for j in state.get("jobs") or [] if isinstance(j, dict)]
    top = status_y + 14
    max_rows = max(0, (height - top - 16) // ROW_H)
    if not jobs:
        panel.label(24, top + 4, "No Pioneers queued", "muted")
    for index, job in enumerate(jobs[:max_rows]):
        y = top + index * ROW_H
        job_state = str(job.get("state", "?"))
        panel.pill(24, y + 2, job_state.upper(), STATE_COLORS.get(job_state, "text-muted"))
        detail = job.get("reason") if job_state == "blocked" else job.get("new_id")
        line = f"{job.get('id')} {job.get('role')} @ {job.get('outpost') or HOME_OUTPOST_ID}" + (f" - {detail}" if detail else "")
        panel.draw_text(120, y + 16, line[: int((width - 220) // 6)], 10, "text-value")
        if job_state in CANCELLABLE_STATES and panel.button(f"commission_cancel_{job.get('id')}", width - 100, y, 76, 22, "cancel"):
            cancel_job(job.get("id"))
    if len(jobs) > max_rows > 0:
        panel.draw_text(width - 200, status_y, f"+{len(jobs) - max_rows} more", 10, "text-muted")
