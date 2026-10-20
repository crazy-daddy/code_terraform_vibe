# Role demand and role slots: the shared state behind dynamic Pioneer roles
# (docs/cheatsheet/fleet_lifecycle.md §2f-1).
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
#     drones  = (hauler only) drones carry the freight: drone yield on and a hauler
#               drone flying; Pioneer haulers only fetch pump salt (SALT_HAULERS)
#     slots   = (miner only) {outpost_id: {"wanted", "keep"}}: miners are counted per
#               outpost, each holds a slot of its base (claim_slot(outpost=))
#   fleet.role_claims = {"<role>:<i>" | "miner:<outpost>:<i>": {"vehicle": name, "role": role, "tick": t, "outpost"?: id}}
#   fleet.missions: the entry-level index of the same work (lib/mission_pool.py), written by publish()

import construction_lots
import construction_plan
import fleet_claims_common as common
import fleet_status
import mission_pool
from archive import archive
from game_clock import is_fresh
from logistics_requests import PlanReads, drone_haulers_present, drone_yield_enabled, outpost_tier_deficits
from outpost_flow import founded_outposts, nearest_outpost
from outpost_mining import mineable_ores_by_outpost, ore_bands
from priority import BANDS, BUILD, NEED, NONE, STOCK, blueprint_prio
from production_core import discover_smelter_ids
from survey_requests import read_requests, read_scout_work
from swallow import swallowed

ROLE_DEMAND_KEY = "fleet.role_demand"
ROLE_CLAIMS_KEY = "fleet.role_claims"

# Haulers kept without any deficit: one for salt and the odd request.
KEEP_HAULERS = 1
# Builders the open construction jobs can use at most.
MAX_BUILDERS = 2
# Builders kept without any construction job: one stands by for the next blueprint.
KEEP_BUILDERS = 1
# Pioneer haulers once drones carry the freight: drones can't load pump salt.
# = autoplay build_providers.SALT_PIONEER_HAULERS (the planner sells haulers above it).
SALT_HAULERS = 2
# Miners kept per outpost with a Smelter even without ore need: one refills the ore buffers.
KEEP_MINERS = 1
# Miners one outpost's NEED ores can use at most (autoplay commissions up to
# build_providers.MAX_MINERS_PER_OUTPOST).
MINER_SLOTS_PER_OUTPOST = 4
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


def hauler_demand(deficits, drones=False):
    """
    Hauler entry from {outpost_id: {band: {item_id: units}}} (the outposts'
    pull deficits): band = the highest top band, wanted = outposts at that
    band (at least 1 while any deficit is open). With `drones` (drones carry
    the freight) wanted is capped at SALT_HAULERS: the deficits count
    drone-servable sources too.
    """
    outposts = {}
    for oid, tiers in deficits.items():
        band = top_band(tiers or {})
        if band > NONE:
            outposts[str(oid)] = band
    band = max(outposts.values()) if outposts else NONE
    wanted = sum(1 for b in outposts.values() if b == band) if outposts else 0
    if drones:
        wanted = min(wanted, SALT_HAULERS)
    return {"band": band, "wanted": wanted, "keep": KEEP_HAULERS, "outposts": outposts, "drones": bool(drones)}


def builder_demand(job_outposts):
    """Builder entry from the open (not held) construction jobs' nearest outpost ids (None when unknown)."""
    if not job_outposts:
        return {"band": NONE, "wanted": 0, "keep": KEEP_BUILDERS, "outposts": {}}
    outposts = {str(oid): BUILD for oid in job_outposts if oid is not None}
    return {"band": BUILD, "wanted": min(len(job_outposts), MAX_BUILDERS), "keep": KEEP_BUILDERS, "outposts": outposts}


def scout_demand(requests, pois, sites, scannable=0):
    """
    Scout entry: NEED while a survey request is open, STOCK for other known
    contacts or sites, else none. keep 1 while there is work or any
    `scannable` POI (unscanned, not biomass; blocked or out of reach too) is
    left: one scout stands by until the survey is complete.
    """
    if requests:
        band = NEED
    elif pois or sites:
        band = STOCK
    else:
        band = NONE
    open_work = 1 if band > NONE else 0
    return {"band": band, "wanted": open_work, "keep": 1 if open_work or scannable else 0, "outposts": {}}


def miner_bands(deficits, reach):
    """
    {outpost_id: {band: {ore: units}}}: each outpost's raw-ore deficit
    (outpost_mining.ore_bands()) in reach of its stationed miners, every ore
    while no miner has published a reach there. Outposts without one left out.
    """
    out = {}
    for oid in deficits:
        known = reach.get(oid)
        bands = {}
        for band, items in ore_bands(deficits.get(oid) or {}).items():
            items = {ore: units for ore, units in items.items() if known is None or ore in known}
            if items:
                bands[band] = items
        if bands:
            out[oid] = bands
    return out


def miner_demand(deficits, reach, smelting, bands_by=None):
    """
    Miner entry from {outpost_id: {band: {item_id: units}}} (the outposts'
    deficits), reach = {outpost_id: ores its stationed miners reach}
    (outpost_mining.mineable_ores_by_outpost()) and the outposts with a
    Smelter. Per outpost: band = top band of its raw-ore deficit in reach,
    wanted = its NEED ores in reach (cap MINER_SLOTS_PER_OUTPOST; STOCK ore
    alone wants none, the keep floor refills buffers), keep = KEEP_MINERS
    with a Smelter. An outpost no miner has published a reach for counts
    every ore but wants at most 1: that miner publishes the reach.
    bands_by = miner_bands(deficits, reach) when the caller has it.
    """
    bands_by = bands_by if bands_by is not None else miner_bands(deficits, reach)
    outposts, slots = {}, {}
    for oid in sorted(set(deficits) | set(smelting), key=str):
        known = reach.get(oid)
        bands = bands_by.get(oid) or {}
        band = top_band(bands)
        need = {ore for b, items in bands.items() if b >= NEED for ore in items}
        wanted = min(len(need), MINER_SLOTS_PER_OUTPOST if known is not None else 1)
        keep = KEEP_MINERS if oid in smelting else 0
        if band > NONE:
            outposts[str(oid)] = band
        if wanted or keep:
            slots[str(oid)] = {"wanted": wanted, "keep": keep}
    return {
        "band": max(outposts.values()) if outposts else NONE,
        "wanted": sum(s["wanted"] for s in slots.values()),
        "keep": sum(s["keep"] for s in slots.values()),
        "outposts": outposts,
        "slots": slots,
    }


def _network_outposts():
    network = get_component("outpost_network")
    try:
        return [o for o in (network.outposts() if network else []) if getattr(o, "id", None) is not None]
    except Exception as error:
        swallowed("role_demand._network_outposts: network.outposts", error)
        return []


def _open_jobs(curr_tick, founded):
    """
    (job id, kind, nearest founded outpost id, coords, prio) of every pending
    or paused construction job whose kind is not held; outpost and coords
    None when unknown, prio = priority.blueprint_prio().
    """
    bp = get_component("construction_blueprint")
    held = construction_lots.read_hold(curr_tick)
    planned = archive.get(construction_plan.PLANNED_KEY, {})
    planned = set(planned) if isinstance(planned, dict) else set()
    priorities = construction_lots.read_priorities()
    out = []
    for getter in ("pending_constructions", "paused_constructions"):
        jobs, _ok = construction_lots.read_jobs(bp, getter)
        for job in jobs:
            kind = getattr(job, "kind", None)
            if kind in held:
                continue
            job_id = getattr(job, "id", None)
            coords = construction_plan.coords_of(getattr(job, "position", None))
            prio = blueprint_prio(job_id in planned, priorities.get(job_id, construction_plan.DEFAULT_PRIORITY))
            out.append((job_id, kind, nearest_outpost(coords, founded) if coords else None, coords, prio))
    return out


def compute(curr_tick, reads=None):
    """
    The fleet.role_demand value now, plus "parts": the intermediates the
    mission pool indexes (mission_pool.build()). `reads`
    (logistics_requests.PlanReads) is built here when omitted.
    """
    reads = reads if reads is not None else PlanReads(curr_tick)
    outposts = _network_outposts()
    founded = founded_outposts()
    deficits = {o.id: outpost_tier_deficits(o, curr_tick, reads=reads) for o in outposts}
    pois, sites, scannable = read_scout_work()
    survey = read_requests()
    smelting = [o.id for o in outposts if discover_smelter_ids(o)]
    jobs = _open_jobs(curr_tick, founded)
    reach = mineable_ores_by_outpost(curr_tick)
    bands_by = miner_bands(deficits, reach)
    return {
        "tick": curr_tick,
        "roles": {
            "hauler": hauler_demand(deficits, drones=drone_yield_enabled() and drone_haulers_present(curr_tick)),
            "builder": builder_demand([job[2] for job in jobs]),
            "scout": scout_demand(survey, pois, sites, scannable),
            "miner": miner_demand(deficits, reach, set(smelting), bands_by),
        },
        "parts": {
            "deficits": deficits,
            "requests": reads.requests,
            "pickups": reads.pickups,
            "jobs": jobs,
            "survey": survey,
            "scout": (pois, sites),
            "miner_bands": bands_by,
            "founded": founded,
        },
    }


def publish(curr_tick, reads=None):
    """
    Writes compute() to fleet.role_demand and its mission index to
    fleet.missions (mission_pool.publish()), and drops stale role slots.
    Returns the value written.
    """
    common.drop_stale_claims(ROLE_CLAIMS_KEY, curr_tick, common.CLAIM_STALE_TICKS)
    drop_gone(fleet_status.get_all())
    value = compute(curr_tick, reads)
    if not archive.set(ROLE_DEMAND_KEY, stored(value)):
        raise RuntimeError(f"{ROLE_DEMAND_KEY} write refused")  # shows as "Role demand error" on the AUTOMATION card
    mission_pool.publish(curr_tick, value["parts"])
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


def fresh_claims(claims, tick):
    """
    The fresh claims of a fleet.role_claims value, one per vehicle: its newest
    (highest tick, then key). A Pioneer mid-refit holds its old slot and the
    new one; it counts under the new role only, so a second idle Pioneer of
    the old role sees the floor the first one already leaves.
    """
    newest = {}
    for key, claim in sorted(claims.items()):
        if isinstance(claim, dict) and is_fresh(claim, tick, common.CLAIM_STALE_TICKS):
            vehicle = claim.get("vehicle")
            if vehicle not in newest or int(claim.get("tick") or 0) >= int(newest[vehicle].get("tick") or 0):
                newest[vehicle] = claim
    return list(newest.values())


def claimed_counts(claims, tick):
    """{role: fresh slots held} of a fleet.role_claims value, one per vehicle (fresh_claims())."""
    counts = {}
    for claim in fresh_claims(claims, tick):
        role = claim.get("role")
        counts[role] = counts.get(role, 0) + 1
    return counts


def claimed_outposts(claims, tick, role="miner"):
    """{outpost_id: fresh slots of `role` held there} of a fleet.role_claims value (slots claimed with an outpost), one per vehicle."""
    counts = {}
    for claim in fresh_claims(claims, tick):
        if claim.get("role") == role and claim.get("outpost") is not None:
            counts[claim["outpost"]] = counts.get(claim["outpost"], 0) + 1
    return counts


def held_slot(claims, role, name):
    """The key of the slot of `role` that `name` holds, else None."""
    return next((k for k, c in sorted(claims.items()) if isinstance(c, dict) and c.get("vehicle") == name and c.get("role") == role), None)


def current_work(current, roles, outpost=None):
    """(band, wanted, keep) of role `current`'s work; a miner's (outpost given) at that outpost (miner entry "slots")."""
    entry = roles.get(current) or {}
    if current == "miner" and outpost is not None:
        slot = (entry.get("slots") or {}).get(outpost) or {}
        return int((entry.get("outposts") or {}).get(outpost) or NONE), int(slot.get("wanted") or 0), int(slot.get("keep") or 0)
    return int(entry.get("band") or NONE), int(entry.get("wanted") or 0), int(entry.get("keep") or 0)


def miner_target(roles, by_outpost, above=NONE, outpost=None):
    """
    (outpost_id, wanted) of the outpost a miner should go to: band above
    `above` (any band when `above` is NONE), more slots wanted than held
    (by_outpost = claimed_outposts()), not `outpost` (the miner's own base).
    Highest band first, then most open slots, then id. None without one.
    """
    entry = roles.get("miner") or {}
    bands = entry.get("outposts") or {}
    best = None
    for oid, slot in (entry.get("slots") or {}).items():
        wanted, band = int((slot or {}).get("wanted") or 0), int(bands.get(oid) or NONE)
        open_slots = wanted - by_outpost.get(oid, 0)
        if oid == outpost or open_slots <= 0 or not (band > above or above == NONE):
            continue
        rank = (-band, -open_slots, oid)
        if best is None or rank < best[0]:
            best = (rank, oid, wanted)
    return (best[1], best[2]) if best else None


def switch_candidates(current, roles, claimed, outpost=None, by_outpost=None):
    """
    [(role, wanted)] an idle Pioneer of role `current` may refit to, best
    band first. roles = fleet.role_demand["roles"], claimed = claimed_counts().
    Miners count per outpost: `outpost` = this Pioneer's base when it is a
    miner, by_outpost = claimed_outposts(); a miner's band, wanted and keep
    are its outpost's (current_work()), and "miner" qualifies through
    miner_target(), for a miner too (re-station to a needier outpost).
    None while `current` is at or under its keep floor. Otherwise a role
    qualifies with a band above the current role's (any band when the
    current role has no work) and more wanted than claimed. A Pioneer whose
    role has no work at all may also join the haulers, over their wanted
    count and with no hauler demand at all: hauler is the fallback role
    (refit, never sell; autoplay sells haulers above MAX_PIONEER_HAULERS).
    It then claims any slot below MAX_ROLE_SLOTS. Once drones carry the
    freight (hauler entry "drones") the fallback only fills the
    SALT_HAULERS slots, and builders don't take it: autoplay sells the
    builders above the keep floor instead.
    """
    by_outpost = by_outpost or {}
    per_outpost = current == "miner" and outpost is not None
    band, wanted_here, keep = current_work(current, roles, outpost if per_outpost else None)
    if (by_outpost.get(outpost, 0) if per_outpost else claimed.get(current, 0)) <= keep:
        return []
    no_work = band == NONE and not wanted_here
    out = []
    for role, other in roles.items():
        if not isinstance(other, dict) or (role == current and not per_outpost):
            continue
        if role == "miner":
            target = miner_target(roles, by_outpost, band, outpost if per_outpost else None)
            if target is not None:
                out.append((int((other.get("outposts") or {}).get(target[0]) or NONE), role, target[1]))
            continue
        other_band, wanted = int(other.get("band") or NONE), int(other.get("wanted") or 0)
        if wanted > 0 and (other_band > band or band == NONE) and wanted > claimed.get(role, 0):
            out.append((other_band, role, wanted))
        elif role == "hauler" and no_work and not other.get("drones"):
            out.append((other_band, role, MAX_ROLE_SLOTS))
        elif role == "hauler" and no_work and current != "builder" and claimed.get(role, 0) < SALT_HAULERS:
            out.append((other_band, role, SALT_HAULERS))
    out.sort(key=lambda c: (-c[0], c[1]))
    return [(role, wanted) for _, role, wanted in out]


def claim_slot(role, name, tick, wanted, log=None, outpost=None):
    """
    Claims a free "<role>:<i>" slot for `name`, i < wanted; with `outpost`
    (miners) a "<role>:<outpost>:<i>" slot recording the outpost. A slot
    `name` already holds for `role` is kept, a miner's only at the same
    outpost (the caller releases the old one). Returns the key, None when
    every slot under `wanted` is held by another Pioneer.
    """
    claims = read_claims()
    own = held_slot(claims, role, name)
    if own is not None and (claims.get(own) or {}).get("outpost") == outpost:
        refresh_slot(own, name, tick)
        return own
    notes = []
    record = {"vehicle": name, "role": role, "tick": tick}
    prefix = f"{role}:"
    if outpost is not None:
        record["outpost"] = outpost
        prefix = f"{role}:{outpost}:"
    won = None
    for i in range(max(0, int(wanted))):
        key = f"{prefix}{i}"
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
