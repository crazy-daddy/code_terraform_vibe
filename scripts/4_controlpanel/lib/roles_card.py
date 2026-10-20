# Roles view of the Control Room FLEET card (vehicles_panel.py): the Pioneer
# work queue. One row per role of fleet.role_demand (lib/role_demand.py) with
# its band, the Pioneers it wants, the role slots held and the keep floor; the
# detail pane lists the role's outposts by band and the Pioneers holding its
# slots. The Queue view lists fleet.missions (lib/mission_pool.py) entry by
# entry: kind, target, band, age, holders. Read-only: an idle Pioneer refits
# on its own (lib/pioneer_refit.py).

import mission_pool
from fleet_card import TAB_GAP, TAB_H, TAB_W, cell, roster, split, tabs
from fleet_claims_common import CLAIM_STALE_TICKS
from fleet_status import outpost_names
from game_clock import is_fresh, now_tick
from game_rules import TICKS_PER_REAL_HOUR
from priority import band_name
from role_demand import claimed_counts, claimed_outposts, read, read_claims
from vehicles_card import vehicle_id_of

ROLE_ORDER = ("hauler", "builder", "scout", "miner")
VIEWS = ("Roles", "Queue")


def ordered_roles(roles):
    """Role names of a role_demand.read()["roles"] value: highest band first, then ROLE_ORDER, unknown roles last."""
    rank = {role: i for i, role in enumerate(ROLE_ORDER)}
    return sorted(roles, key=lambda role: (-int((roles.get(role) or {}).get("band") or 0), rank.get(role, len(rank)), role))


def role_row(role, entry, claimed, open_count=None):
    """One roster row: role, band, claimed / wanted, keep floor and, given, the fleet.missions entries of its kind (held or not)."""
    band = int(entry.get("band") or 0)
    wanted = int(entry.get("wanted") or 0)
    keep = int(entry.get("keep") or 0)
    row = f"{cell(role, 8)} {cell(band_name(band) if band else '-', 8)} {claimed:>2} / {wanted:<2} keep {keep}"
    return row if open_count is None else f"{row}  missions {open_count}"


def open_counts(missions):
    """{role: entries of its kind (mission_pool.ROLE_KINDS) listed plus dropped} of a mission_pool.read() value."""
    dropped = missions.get("dropped") or {}
    out = {}
    for role, kind in mission_pool.ROLE_KINDS.items():
        listed = sum(1 for e in missions.get("entries") or [] if e.get("kind") == kind)
        out[role] = listed + int(dropped.get(kind) or 0)
    return out


def age_hours(entry, tick):
    """Real hours (normal speed) since the entry's "since" tick (0 when missing or ahead)."""
    since = entry.get("since")
    return max(0, tick - int(since)) / TICKS_PER_REAL_HOUR if isinstance(since, (int, float)) else 0.0


def entry_target(entry, names):
    """Short target of a fleet.missions entry: the outpost (haul), ore@outpost (mine), else the id after its kind."""
    outpost = entry.get("outpost")
    where = names.get(outpost, outpost) if outpost is not None else None
    kind = entry.get("kind")
    if kind == "haul" and where:
        return str(where)
    if kind == "mine" and where:
        return f"{entry.get('item')}@{where}"
    return str(entry.get("id") or "").split(":", 1)[-1]


def queue_row(entry, tick, names):
    """One Queue roster row: kind, target, band, age h, holders."""
    prio = int(entry.get("prio") or 0)
    holders = ", ".join(entry.get("holders") or []) or "-"
    return f"{cell(entry.get('kind'), 5)} {cell(entry_target(entry, names), 20)} {cell(band_name(prio) if prio else '-', 8)} {age_hours(entry, tick):>4.1f} h {holders}"


def outpost_rows(entry, by_outpost):
    """[(outpost_id, band, slots text)] of a role entry, highest band first; the miner entry's
    per-outpost "slots" add "held / wanted keep k" (by_outpost = claimed_outposts()) and their keep-only outposts."""
    bands = entry.get("outposts") or {}
    slots = entry.get("slots") or {}
    out = []
    for oid in set(bands) | set(slots):
        slot = slots.get(oid)
        text = f"{by_outpost.get(oid, 0)} / {int(slot.get('wanted') or 0)} keep {int(slot.get('keep') or 0)}" if isinstance(slot, dict) else ""
        out.append((oid, int(bands.get(oid) or 0), text))
    return sorted(out, key=lambda row: (-row[1], row[0]))


def slot_holders(claims, role, tick, names):
    """[(slot key, display name, age ticks)] of the fresh slots of `role`, by slot key."""
    out = []
    for key, claim in sorted(claims.items()):
        if isinstance(claim, dict) and claim.get("role") == role and is_fresh(claim, tick, CLAIM_STALE_TICKS):
            vehicle = str(claim.get("vehicle") or "")
            out.append((key, names.get(vehicle, vehicle), max(0, tick - int(claim.get("tick") or 0))))
    return out


def vehicle_names():
    """{vehicle id: display name} of the fleet; role slots hold the id."""
    fleet = get_component("fleet")
    out = {}
    for vehicle in fleet.vehicles() if fleet and hasattr(fleet, "vehicles") else []:
        vid = vehicle_id_of(vehicle)
        out[vid] = str(getattr(vehicle, "name", vid))
    return out


def draw_roles(panel, x, y, w, h):
    """Roles view in the content box (x, y, w, h)."""
    tick = now_tick("roles_card.draw_roles")
    demand = read(tick)
    roles = demand.get("roles") or {}
    missions = mission_pool.read(tick)
    view = tabs(panel, "roles_view", x, y, VIEWS)
    hint_x = x + len(VIEWS) * (TAB_W + TAB_GAP)
    list_y = y + TAB_H + 8
    list_h = y + h - list_y
    if view == 1:
        panel.label(hint_x, y + 8, "Open work: kind, target, band, age, holders", "muted")
        draw_queue(panel, missions, tick, x, list_y, w, list_h)
        return
    claims = read_claims()
    counts = claimed_counts(claims, tick)
    panel.label(hint_x, y + 8, "Role, band, slots held / wanted, keep floor, missions", "muted")
    if not roles:
        panel.label(x, list_y + 12, "No fresh role demand (the Automation publishes it)", "muted")
        return
    order = ordered_roles(roles)
    opened = open_counts(missions)
    list_w, dx, dw = split(x, w)
    index = roster(panel, "roles_list", x, list_y, list_w, list_h, [role_row(r, roles[r], counts.get(r, 0), opened.get(r)) for r in order])
    if index is None:
        return
    draw_role_detail(panel, order[index], roles[order[index]], claims, tick, dx, list_y, dw, list_h)


def draw_queue(panel, missions, tick, x, y, w, h):
    """Queue view: one row per fleet.missions entry (published order: band, oldest), the selected entry's detail beside it."""
    entries = missions.get("entries") or []
    if not entries:
        panel.label(x, y + 12, "No fresh mission index (the Automation publishes it with the role demand)", "muted")
        return
    names = outpost_names()
    dropped = missions.get("dropped") or {}
    list_w, dx, dw = split(x, w)
    list_h = h - (16 if dropped else 0)
    index = roster(panel, "missions_list", x, y, list_w, list_h, [queue_row(e, tick, names) for e in entries])
    if dropped:
        panel.draw_text(x, y + list_h + 4, "not listed: " + ", ".join(f"{kind} {n}" for kind, n in sorted(dropped.items())), 10, "text-muted")
    if index is not None:
        draw_entry_detail(panel, entries[index], tick, names, dx, y, dw, h)


def entry_lines(entry, tick, names):
    """Detail pane lines of one fleet.missions entry."""
    outpost = entry.get("outpost")
    lines = [f"since {age_hours(entry, tick):.1f} h (tick {entry.get('since')})"]
    if outpost is not None:
        lines.append(f"outpost {names.get(outpost, outpost)}")
    if entry.get("by"):
        lines.append(f"by {entry['by']}")
    if entry.get("item") or entry.get("units") is not None:
        lines.append(f"{entry.get('units') if entry.get('units') is not None else '?'} x {entry.get('item') or 'items'}")
    coords = entry.get("coords")
    if isinstance(coords, list) and len(coords) == 2 and all(isinstance(c, (int, float)) for c in coords):
        lines.append(f"at {coords[0]:.0f}, {coords[1]:.0f}")
    holders = entry.get("holders") or []
    lines.append(("held by " + ", ".join(holders)) if holders else "no holder")
    return lines


def draw_entry_detail(panel, entry, tick, names, x, y, w, h):
    prio = int(entry.get("prio") or 0)
    panel.draw_text(x, y + 8, str(entry.get("id")), 13, "text-bright")
    panel.draw_text(x + w - 70, y + 8, band_name(prio) if prio else "-", 10, "text-secondary")
    cy = y + 28
    for line in entry_lines(entry, tick, names):
        if cy > y + h - 12:
            return
        panel.draw_text(x, cy, line, 10, "text-value")
        cy += 13


def draw_role_detail(panel, role, entry, claims, tick, x, y, w, h):
    band = int(entry.get("band") or 0)
    panel.draw_text(x, y + 8, role, 13, "text-bright")
    panel.draw_text(x + w - 70, y + 8, band_name(band) if band else "no work", 10, "text-secondary")
    cy = y + 28
    bottom = y + h - 12
    names = outpost_names()
    for outpost_id, outpost_band, slots in outpost_rows(entry, claimed_outposts(claims, tick, role)):
        if cy > bottom:
            return
        panel.draw_text(x, cy, f"{cell(names.get(outpost_id, outpost_id), 18)} {cell(band_name(outpost_band) if outpost_band else '-', 8)} {slots}".rstrip(), 10, "text-value")
        cy += 13
    holders = slot_holders(claims, role, tick, vehicle_names())
    if cy + 6 <= bottom:
        panel.draw_text(x, cy + 6, f"slots held: {len(holders)}" if holders else "no slot held", 10, "text-muted")
        cy += 19
    for key, name, age in holders:
        if cy > bottom:
            return
        panel.draw_text(x, cy, f"{cell(name, 16)} {key}  {age // 600} min", 10, "text-value")
        cy += 13
