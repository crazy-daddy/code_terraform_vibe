# Role demand and role slots: the shared state behind dynamic Pioneer roles
# (docs/cheatsheet/vehicles_drones.md §2f-1).
#
# The Automation (orchestrator_automation.py) publishes how much work each
# Pioneer role has, every ROLE_DEMAND_TICK_INTERVAL; an idle Pioneer reads it
# in PioneerController.next_job() and refits to a role that wants more
# vehicles (lib/pioneer_refit.py). A role slot is a claim on "<role>:<i>": a
# Pioneer holds one slot of its role, so the count of fresh slots of a role is
# how many Pioneers work it, and two idle Pioneers never take one opening.
#
# Archive (CODE_GUIDES.md#archive, archive_ipc.md):
#   fleet.role_demand = {"tick": t, "roles": [{"role", "band", "wanted", "keep", "outposts": {outpost_id: band}}]}
#     a list, not a dict keyed by role: a role name is free text, and the Data
#     Archive refuses some names as dictionary keys (CODE_GUIDES.md#archive);
#     read() returns the {role: entry} form compute() builds
#     band    = highest priority band (lib/priority.py) of the role's open work, 0 = none
#     wanted  = Pioneers the work can use now
#     keep    = Pioneers the role keeps even without work (a refit away stops there)
#   fleet.role_claims = {"<role>:<i>": {"vehicle": name, "role": role, "tick": t}}

import construction_lots
import construction_plan
import fleet_claims_common as common
import fleet_status
from archive import archive
from game_clock import is_fresh
from logistics_requests import PlanReads, outpost_tier_deficits
from outpost_flow import founded_outposts, nearest_outpost
from priority import BANDS, BUILD, NEED, NONE, STOCK
from production_core import discover_smelter_ids
from survey_requests import read_requests, read_scout_work
from swallow import swallowed

ROLE_DEMAND_KEY = "fleet.role_demand"
ROLE_CLAIMS_KEY = "fleet.role_claims"

# Haulers kept without any deficit: one for salt and the odd request.
KEEP_HAULERS = 1
# Builders the open construction jobs can use at most.
MAX_BUILDERS = 2
# Slot indices a running Pioneer may hold for its role at start (PioneerController.run()):
# every Pioneer of a role holds one, so the fresh count is the role's head count.
MAX_ROLE_SLOTS = 16
# A Pioneer renews its slot this often (PioneerController.next_job()); a slot older than
# fleet_claims_common.CLAIM_STALE_TICKS is free for anyone and dropped by publish().
ROLE_SLOT_REFRESH_TICKS = 3000
# A fleet.role_demand older than this is ignored (read()): the Automation stopped publishing.
ROLE_DEMAND_STALE_TICKS = 3000


def top_band(tiers):
    """Highest band of {band: {item_id: units}} with units left, NONE when none."""
    for band in BANDS:
        if any(units > 0 for units in (tiers.get(band) or {}).values()):
            return band
    return NONE


def hauler_demand(deficits):
    """
    Hauler entry from {outpost_id: {band: {item_id: units}}} (the outposts'
    pull deficits): band = the highest top band, wanted = outposts at that
    band (at least 1 while any deficit is open).
    """
    outposts = {}
    for oid, tiers in deficits.items():
        band = top_band(tiers or {})
        if band > NONE:
            outposts[str(oid)] = band
    band = max(outposts.values()) if outposts else NONE
    wanted = sum(1 for b in outposts.values() if b == band) if outposts else 0
    return {"band": band, "wanted": wanted, "keep": KEEP_HAULERS, "outposts": outposts}


def builder_demand(job_outposts):
    """Builder entry from the open (not held) construction jobs' nearest outpost ids (None when unknown)."""
    if not job_outposts:
        return {"band": NONE, "wanted": 0, "keep": 0, "outposts": {}}
    outposts = {str(oid): BUILD for oid in job_outposts if oid is not None}
    return {"band": BUILD, "wanted": min(len(job_outposts), MAX_BUILDERS), "keep": 1, "outposts": outposts}


def scout_demand(requests, pois, sites):
    """Scout entry: NEED while a survey request is open, STOCK for other known contacts or sites, else none."""
    if requests:
        band = NEED
    elif pois or sites:
        band = STOCK
    else:
        band = NONE
    open_work = 1 if band > NONE else 0
    return {"band": band, "wanted": open_work, "keep": open_work, "outposts": {}}


def miner_demand(smelter_outposts):
    """Miner entry: no refit into miners yet; keep one per founded outpost with a Smelter."""
    return {"band": NONE, "wanted": 0, "keep": len(smelter_outposts), "outposts": {}}


def _network_outposts():
    network = get_component("outpost_network")
    try:
        return [o for o in (network.outposts() if network else []) if getattr(o, "id", None) is not None]
    except Exception as error:
        swallowed("role_demand._network_outposts: network.outposts", error)
        return []


def _open_job_outposts(curr_tick, founded):
    """Nearest founded outpost id of every pending or paused construction job whose kind is not held."""
    bp = get_component("construction_blueprint")
    held = construction_lots.read_hold(curr_tick)
    out = []
    for getter in ("pending_constructions", "paused_constructions"):
        jobs, _ok = construction_lots.read_jobs(bp, getter)
        for job in jobs:
            if getattr(job, "kind", None) in held:
                continue
            coords = construction_plan.coords_of(getattr(job, "position", None))
            out.append(nearest_outpost(coords, founded) if coords else None)
    return out


def compute(curr_tick, reads=None):
    """The fleet.role_demand value now. `reads` (logistics_requests.PlanReads) is built here when omitted."""
    reads = reads if reads is not None else PlanReads(curr_tick)
    outposts = _network_outposts()
    founded = founded_outposts()
    deficits = {o.id: outpost_tier_deficits(o, curr_tick, reads=reads) for o in outposts}
    pois, sites = read_scout_work()
    smelting = [o.id for o in outposts if discover_smelter_ids(o)]
    return {
        "tick": curr_tick,
        "roles": {
            "hauler": hauler_demand(deficits),
            "builder": builder_demand(_open_job_outposts(curr_tick, founded)),
            "scout": scout_demand(read_requests(), pois, sites),
            "miner": miner_demand(smelting),
        },
    }


def publish(curr_tick, reads=None):
    """Writes compute() to fleet.role_demand and drops stale role slots. Returns the value written."""
    common.drop_stale_claims(ROLE_CLAIMS_KEY, curr_tick, common.CLAIM_STALE_TICKS)
    drop_gone(fleet_status.get_all())
    value = compute(curr_tick, reads)
    if not archive.set(ROLE_DEMAND_KEY, stored(value)):
        raise RuntimeError(f"{ROLE_DEMAND_KEY} write refused")  # shows as "Role demand error" on the AUTOMATION card
    return value


def drop_gone(statuses):
    """Drops the slots of Pioneers without a fleet.status entry (sold or gone; the archive cleaner prunes those).
    Skipped while fleet.status reads empty."""
    if not statuses:
        return
    common.release_claims(ROLE_CLAIMS_KEY, None, lambda c: c.get("vehicle") not in statuses)


def stored(value):
    """compute()'s {"tick", "roles": {role: entry}} as fleet.role_demand stores it: roles as a list of entries carrying "role"."""
    return {"tick": value.get("tick"), "roles": [dict(entry, role=role) for role, entry in value.get("roles", {}).items()]}


def read(tick=None):
    """
    fleet.role_demand as {"tick", "roles": {role: entry}} ({"roles": {}} when
    missing, malformed or, given tick, older than ROLE_DEMAND_STALE_TICKS).
    """
    value = archive.get(ROLE_DEMAND_KEY, {})
    if not isinstance(value, dict) or not isinstance(value.get("roles"), list):
        return {"roles": {}}
    if tick is not None and not is_fresh(value, tick, ROLE_DEMAND_STALE_TICKS):
        return {"roles": {}}
    roles = {e["role"]: {k: v for k, v in e.items() if k != "role"} for e in value["roles"] if isinstance(e, dict) and isinstance(e.get("role"), str)}
    return {"tick": value.get("tick"), "roles": roles}


def read_claims():
    claims = archive.get(ROLE_CLAIMS_KEY, {})
    return claims if isinstance(claims, dict) else {}


def claimed_counts(claims, tick):
    """{role: fresh slots held} of a fleet.role_claims value."""
    counts = {}
    for claim in claims.values():
        if isinstance(claim, dict) and is_fresh(claim, tick, common.CLAIM_STALE_TICKS):
            role = claim.get("role")
            counts[role] = counts.get(role, 0) + 1
    return counts


def held_slot(claims, role, name):
    """The key of the slot of `role` that `name` holds, else None."""
    return next((k for k, c in sorted(claims.items()) if isinstance(c, dict) and c.get("vehicle") == name and c.get("role") == role), None)


def switch_candidates(current, roles, claimed):
    """
    [(role, wanted)] an idle Pioneer of role `current` may refit to, best
    band first. roles = fleet.role_demand["roles"], claimed = claimed_counts().
    None while `current` is at or under its keep floor. Otherwise a role
    qualifies with a band above the current role's (any band when the
    current role has no work) and more wanted than claimed. A Pioneer whose
    role has no work at all may also join the haulers while they have any,
    over their wanted count (refit, never sell): it then claims any slot
    below MAX_ROLE_SLOTS.
    """
    entry = roles.get(current) or {}
    band = int(entry.get("band") or NONE)
    if claimed.get(current, 0) <= int(entry.get("keep") or 0):
        return []
    no_work = band == NONE and not entry.get("wanted")
    out = []
    for role, other in roles.items():
        if role == current or not isinstance(other, dict):
            continue
        other_band, wanted = int(other.get("band") or NONE), int(other.get("wanted") or 0)
        if wanted <= 0:
            continue
        if (other_band > band or band == NONE) and wanted > claimed.get(role, 0):
            out.append((other_band, role, wanted))
        elif role == "hauler" and no_work:
            out.append((other_band, role, MAX_ROLE_SLOTS))
    out.sort(key=lambda c: (-c[0], c[1]))
    return [(role, wanted) for _, role, wanted in out]


def claim_slot(role, name, tick, wanted, log=None):
    """
    Claims a free "<role>:<i>" slot for `name`, i < wanted; a slot `name`
    already holds for `role` is kept. Returns the key, None when every slot
    under `wanted` is held by another Pioneer.
    """
    own = held_slot(read_claims(), role, name)
    if own is not None:
        refresh_slot(own, name, tick)
        return own
    notes = []
    record = {"vehicle": name, "role": role, "tick": tick}
    won = None
    for i in range(max(0, int(wanted))):
        key = f"{role}:{i}"
        if common.try_claim(ROLE_CLAIMS_KEY, key, name, lambda c: c.get("vehicle"), record, tick, common.CLAIM_STALE_TICKS, notes):
            won = key
            break
    if log is not None:
        for note in notes:
            log.trace(note)
    return won


def refresh_slot(key, name, tick):
    """Renews the heartbeat of slot `key` when `name` holds it."""
    if key:
        common.refresh_claim(ROLE_CLAIMS_KEY, key, lambda c: c.get("vehicle") == name, tick)


def release_slot(key, name):
    """Drops slot `key` when `name` holds it."""
    if key:
        common.release_claims(ROLE_CLAIMS_KEY, key, lambda c: c.get("vehicle") == name)
