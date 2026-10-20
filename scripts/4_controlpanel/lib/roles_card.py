# Roles view of the Control Room FLEET card (vehicles_panel.py): the Pioneer
# work queue. One row per role of fleet.role_demand (lib/role_demand.py) with
# its band, the Pioneers it wants, the role slots held and the keep floor; the
# detail pane lists the role's outposts by band and the Pioneers holding its
# slots. Read-only: an idle Pioneer refits on its own (lib/pioneer_refit.py).

from fleet_card import cell, roster, split
from fleet_claims_common import CLAIM_STALE_TICKS
from fleet_status import outpost_names
from game_clock import is_fresh, now_tick
from priority import band_name
from role_demand import claimed_counts, claimed_outposts, read, read_claims
from vehicles_card import vehicle_id_of

ROLE_ORDER = ("hauler", "builder", "scout", "miner")


def ordered_roles(roles):
    """Role names of a role_demand.read()["roles"] value: highest band first, then ROLE_ORDER, unknown roles last."""
    rank = {role: i for i, role in enumerate(ROLE_ORDER)}
    return sorted(roles, key=lambda role: (-int((roles.get(role) or {}).get("band") or 0), rank.get(role, len(rank)), role))


def role_row(role, entry, claimed):
    """One roster row: role, band, claimed / wanted, keep floor."""
    band = int(entry.get("band") or 0)
    wanted = int(entry.get("wanted") or 0)
    keep = int(entry.get("keep") or 0)
    return f"{cell(role, 8)} {cell(band_name(band) if band else '-', 8)} {claimed:>2} / {wanted:<2} keep {keep}"


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
    claims = read_claims()
    counts = claimed_counts(claims, tick)
    panel.label(x, y + 8, "Pioneer work queue: role, band, slots held / wanted, keep floor", "muted")
    list_y = y + 28
    list_h = y + h - list_y
    if not roles:
        panel.label(x, list_y + 12, "No fresh role demand (the Automation publishes it)", "muted")
        return
    order = ordered_roles(roles)
    list_w, dx, dw = split(x, w)
    index = roster(panel, "roles_list", x, list_y, list_w, list_h, [role_row(r, roles[r], counts.get(r, 0)) for r in order])
    if index is None:
        return
    draw_role_detail(panel, order[index], roles[order[index]], claims, tick, dx, list_y, dw, list_h)


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
