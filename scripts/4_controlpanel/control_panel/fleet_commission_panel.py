# ct-panel: fleet_commission_panel
# Control Room COMMISSION card: launch new Pioneers and drones. One button per
# role queues a job. Pure intent publish, same pattern as the other fleet
# cards: this card only writes fleet.commission, the headless
# control_room_automation.py runs lib/fleet_commission.py.
#
# Pioneer row (roles from lib/pioneer_commission.py PIONEER_PRESETS): the
# chassis and parts are bought and the Pioneer is always deployed at the home
# outpost, where it fits its own parts. The "home:" button cycles the outpost
# it then works for (its HOME_BASE); devtools/scripts_sync.py fills that into
# the new pioneer slot.
#
# Drone row (roles from lib/drone_commission.py DRONE_ROLES): the best
# craftable chassis and its preset modules are crafted by the Fabricator into
# Inventory, then deployed at the outpost the "at" button picks (only outposts
# with a Drone Depot are offered); that outpost becomes its HOME_DEPOT.
#
# Below the buttons: the coordinator's status line and the job queue, each
# job with a cancel button while nothing is deployed yet (or it is blocked).
#
# Recommended card size: 2 x 2 (1000x400). At one column each picker moves to
# its own row.
# New save: create an empty Custom Panel in-game -- see docs/cheatsheet/panels.md §7.

from pioneer_commission import PIONEER_PRESETS, commission_state, update_commission
from drone_commission import DRONE_ROLES
from drone_energy import DRONE_DEPOT_TYPE_IDS
from fleet_commission import queue_pioneer, queue_drone, cancel_job, job_kind, job_home_base, CANCELLABLE_STATES
from outpost_mining import HOME_OUTPOST_ID
from swallow import swallowed
from tree_console import TreeConsole

PIONEER_LABELS = [("hauler", "+ Hauler"), ("miner", "+ Miner"), ("scout", "+ Scout"), ("constructor", "+ Builder")]
DRONE_LABELS = [("hauler", "+ Hauler"), ("miner", "+ Miner")]
STATE_COLORS = {"queued": "text-muted", "buying": "accent", "crafting": "accent", "deploying": "accent", "attach": "warning", "fitting": "accent", "blocked": "error"}
ROW_LABEL_W = 64
BUTTON_W = 92
BUTTON_H = 26
PICKER_W = 206
ROW_H = 28
# Panel loop iterations between outpost list refreshes.
OUTPOST_REFRESH_LOOPS = 100


def read_outposts():
    """([(id, name, is_home)] of every outpost, the same for those with a Drone Depot), home first."""
    try:
        network = get_component("outpost_network")
        refs = list(network.outposts()) if network else []
    except Exception as error:
        swallowed("fleet_commission_panel.read_outposts: network.outposts", error)
        refs = []
    found, with_depot = [], []
    for ref in refs:
        entry = (getattr(ref, "id", ""), getattr(ref, "name", "") or getattr(ref, "id", ""), bool(getattr(ref, "is_home", False)))
        if not entry[0]:
            log.debug(f"read_outposts: skip ref without id: {ref!r}")
            continue
        found.append(entry)
        try:
            types = [getattr(b, "type_id", "") for b in ref.buildings()]
            has_depot = len([t for t in types if t in DRONE_DEPOT_TYPE_IDS]) > 0
            log.trace(f"read_outposts: {entry} depot={has_depot} buildings={types}")
            if has_depot:
                with_depot.append(entry)
        except Exception as error:
            swallowed("fleet_commission_panel.read_outposts: outpost.buildings", error)
    order = lambda o: (not o[2], o[0])
    found.sort(key=order)
    with_depot.sort(key=order)
    if not found:
        log.debug(f"read_outposts: none found, fallback to {HOME_OUTPOST_ID} only (home picker cannot cycle)")
    seen = (found, [o[0] for o in with_depot])
    if _last_outposts.get("seen") != seen:
        _last_outposts["seen"] = seen
        log.debug(f"read_outposts: {len(refs)} refs, outposts={found} with_depot={seen[1]}")
    return found or [(HOME_OUTPOST_ID, "home", True)], with_depot


def picker(button_id, x, y, prefix, choices, state_key, state):
    """
    Button cycling state[state_key] through choices [(id, name, is_home)]
    (None stored for home). Returns the picked outpost id (None = home), or
    False when there is nothing to pick.
    """
    if not choices:
        panel.draw_text(x, y + 17, f"{prefix} no Drone Depot", 10, "text-muted")
        return False
    stored = state.get(state_key)
    matches = [i for i, c in enumerate(choices) if (c[0] == stored if stored else c[2])]
    match = matches[0] if matches else None
    index = 0 if match is None else match
    _, name, _ = choices[index]
    seen = (stored, match, len(choices))
    if _last_pick.get(state_key) != seen:
        _last_pick[state_key] = seen
        note = " (no match, show index 0)" if match is None else ""
        log.debug(f"picker {state_key}: stored={stored!r} index={index}/{len(choices)} -> {choices[index]}{note}")
    if panel.button(button_id, x, y, PICKER_W, BUTTON_H, f"{prefix} {name}"[:28]):
        nxt = choices[(index + 1) % len(choices)]
        value = None if nxt[2] else nxt[0]
        log.debug(f"picker {state_key}: click at index {index}, write {value!r} (next {nxt})")

        def write(s):
            log.trace(f"picker {state_key}: transaction saw {s.get(state_key)!r}, set {value!r}")
            s[state_key] = value

        try:
            update_commission(write)
        except Exception as error:
            swallowed(f"fleet_commission_panel.picker: update_commission {state_key}", error)
        log.debug(f"picker {state_key}: archive now {commission_state().get(state_key)!r}")
    picked = choices[index]
    return None if picked[2] else picked[0]


def role_row(y, title, labels, id_prefix, allowed, on_click):
    panel.draw_text(24, y + 17, title, 11, "text-secondary")
    for index, (role, label) in enumerate([r for r in labels if r[0] in allowed]):
        if panel.button(f"{id_prefix}_{role}", 24 + ROW_LABEL_W + index * (BUTTON_W + 8), y, BUTTON_W, BUTTON_H, label):
            on_click(role)


def order_pioneer(role, home_base):
    job_id = queue_pioneer(role, home_base)
    log.print(f"[COMMISSION] Ordered {job_id}: Pioneer '{role}' working for '{home_base or HOME_OUTPOST_ID}'.")


def order_drone(role, outpost_id):
    job_id = queue_drone(role, outpost_id)
    log.print(f"[COMMISSION] Ordered {job_id}: drone '{role}' at '{outpost_id or HOME_OUTPOST_ID}'.")


def cancel_order(job):
    dropped = cancel_job(job.get("id"))
    outcome = "cancelled" if dropped else "not cancelled (already past cancellable states)"
    log.print(f"[COMMISSION] {job.get('id')} ({job.get('role')}, {job.get('state')}) {outcome}.")


log = TreeConsole(module="fleet_commission_panel")
# state_key -> (stored, match, choice count) last logged, so the picker logs on change, not every frame.
_last_pick = {}
# "seen" -> (outposts, depot outpost ids) last logged by read_outposts().
_last_outposts = {}
# Every widget on this card is a momentary button (state lives in fleet.commission), so stored keys hold
# nothing worth keeping; drop them so the card stays under its 512-key limit.
panel.clear_inputs()
outposts, depot_outposts = read_outposts()
loops = 0

while True:
    loops += 1
    log.flush()
    if loops % OUTPOST_REFRESH_LOOPS == 0:
        outposts, depot_outposts = read_outposts()

    panel.clear()
    width = panel.width()
    height = panel.height()
    panel.card(8, 8, width - 16, height - 16, "COMMISSION")
    wide = width >= 900
    state = commission_state()
    picker_x = width - PICKER_W - 24 if wide else 24 + ROW_LABEL_W
    # Wide: role buttons and picker share a row. Narrow: picker on the next row.
    picker_dy = 0 if wide else 34
    section_h = 34 + picker_dy

    # Pioneers: deployed at home, working for the picked HOME_BASE.
    y = 44
    home_base = picker("commission_home", picker_x, y + picker_dy, "home:", outposts, "target_home", state) or None
    role_row(y, "Pioneer", PIONEER_LABELS, "commission", PIONEER_PRESETS, lambda role: order_pioneer(role, home_base))

    # Drones: crafted into Inventory, then deployed at the picked outpost.
    y += section_h
    drone_outpost = picker("commission_drone_outpost", picker_x, y + picker_dy, "at", depot_outposts, "drone_outpost", state)
    if drone_outpost is not False:
        role_row(y, "Drone", DRONE_LABELS, "commission_drone", DRONE_ROLES, lambda role: order_drone(role, drone_outpost))
    else:
        panel.draw_text(24, y + 17, "Drone", 11, "text-secondary")

    status_y = y + section_h + 14
    panel.draw_text(24, status_y, str(state.get("status", "idle"))[: int((width - 48) // 6)], 10, "text-secondary")

    jobs = [j for j in state.get("jobs") or [] if isinstance(j, dict)]
    top = status_y + 14
    max_rows = max(0, (height - top - 16) // ROW_H)
    if not jobs and top + 20 <= height:
        panel.label(24, top + 4, "Nothing queued", "muted")
    for index, job in enumerate(jobs[:max_rows]):
        row_y = top + index * ROW_H
        job_state = str(job.get("state", "?"))
        panel.pill(24, row_y + 2, job_state.upper(), STATE_COLORS.get(job_state, "text-muted"))
        detail = job.get("reason") if job_state == "blocked" else job.get("new_id")
        if job_kind(job) == "drone":
            what = f"drone {job.get('role')} @ {job.get('outpost') or 'home'}"
        else:
            what = f"{job.get('role')} for {job_home_base(job) or 'home'}"
        line = f"{job.get('id')} {what}" + (f" - {detail}" if detail else "")
        panel.draw_text(120, row_y + 16, line[: int((width - 220) // 6)], 10, "text-value")
        if job_state in CANCELLABLE_STATES and panel.button(f"commission_cancel_{index}", width - 100, row_y, 76, 22, "cancel"):
            cancel_order(job)
    if len(jobs) > max_rows > 0:
        panel.draw_text(width - 200, status_y, f"+{len(jobs) - max_rows} more", 10, "text-muted")
