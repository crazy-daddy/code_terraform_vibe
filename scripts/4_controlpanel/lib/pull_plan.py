# Pull-hauler trip planning (layer 0 of the vehicle mixins,
# docs/plans/mixin_refactor/README.md): what the hauler's home outpost misses,
# where free stock of it sits (other outposts, field Mining Drills, Water
# Pump salt, the Shop for buyable requests), and the multi-stop route that
# fetches the most of it per metre. No driving, no loading: PullJob
# (lib/job_pull.py) runs the trip through VehicleCargoMixin.pull_from_source()
# (lib/vehicle_cargo.py). Functions that read the world or log take the
# vehicle as `host`; the chain math takes plain values.

import logistics_requests
import drill_sites
import pump_salt
from geometry import distance
from swallow import swallowed
from atomic import run_atomic
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vehicle import VehicleController

# Source outposts visited per trip (smallest load: logistics_requests.min_load_units()).
PULL_MAX_STOPS_PER_TRIP = 3
# A further stop is only chained onto a pull trip when driving there directly
# from the previous stop is at most this fraction of going via home instead
# (prev -> home -> next). Home lying on or near the chain leg means dropping
# the cargo off first costs (almost) nothing extra, so the stop is left for
# the next trip instead of driving straight past home.
PULL_CHAIN_MAX_DETOUR_RATIO = 0.75
# Candidate pull trips (one per possible first stop) are ranked by
# units / (round-trip m + this overhead), like the drone hauler's
# HAUL_TRIP_OVERHEAD_M, so a nearby source holding a 1-unit top-up can't
# shadow a farther one holding what's actually missing.
PULL_TRIP_OVERHEAD_M = 300
# Chain checks listed per candidate in the debug log (the game caps strings at 10,000 characters).
PULL_CHAIN_NOTES_MAX = 30
# A pickup leg that even a full battery could only drive below this throttle
# is refused (drive_with_recharge(min_throttle=...)) instead of crawling there
# at the speedmode floor for days; the source is then left out of planning
# for PULL_UNVIABLE_COOLDOWN_TICKS (30 minutes), e.g. until a charging
# station is built nearer to it.
PULL_MIN_LEG_THROTTLE = 0.3
PULL_UNVIABLE_COOLDOWN_TICKS = 18000


def pull_deficits_tiered(home_outpost, curr_tick):
    """
    {tier: {item_id: units}} home_outpost still misses: its live
    pull-request deficits (logistics_requests.outpost_tier_deficits(),
    already net of in-flight pickups). Home is no exception: its ore comes
    from its site supply requests (lib/site_supply.py) like any outpost's.
    """
    return logistics_requests.outpost_tier_deficits(home_outpost, curr_tick, live=True)


def pull_sources(host: "VehicleController", items, curr_tick, warned_drills):
    """
    Every place holding free stock of `items`, as dicts {"kind", "id",
    "coords", "available", "outpost"}: other outposts than host's home (plus
    "tiers", logistics_requests.outpost_tier_free(), computed live; Drone
    Depot stock pull_from_source() reaches after the stores) and field
    Mining Drills advertising in drill.status (lib/drill_sites.py), each
    net of what other haulers already reserved there. A drill on no
    surveyed site (drill_sites.drill_positions()) is skipped, warned about
    once (its id goes into the caller's `warned_drills` set).
    Water Pumps holding byproduct salt (lib/pump_salt.py) are added when
    salt is wanted, home pumps included. With the FLEET card's drone
    yield switch on, sources drone haulers can serve are dropped
    (logistics_requests.drone_served_source()). Requests and other
    haulers' reservations are read once for every source
    (logistics_requests.PlanReads).
    """
    host.log.start(f"[{host.name}] pull_sources", level="debug")
    home_id = getattr(host.home_outpost, "id", None)
    reads = logistics_requests.PlanReads(curr_tick)
    sources = []

    network = get_component("outpost_network")
    try:
        outposts = list(network.outposts()) if network else []
    except Exception as error:
        swallowed("pull_plan.pull_sources: network.outposts", error)
        outposts = []
    for outpost in outposts:
        if getattr(outpost, "id", None) == home_id or not hasattr(outpost, "coords"):
            continue
        free = logistics_requests.outpost_tier_free(outpost, items, None, curr_tick, exclude_vehicle=host.name, reads=reads)
        available = logistics_requests.most_free(free)
        if available:
            sources.append({"kind": "outpost", "id": outpost.id, "coords": outpost.coords(), "available": available, "tiers": free, "outpost": outpost})

    positions = drill_sites.drill_positions(curr_tick)
    for drill_id, entry in drill_sites.advertised_drills(curr_tick).items():
        taken = reads.reserved_from(drill_id, host.name)
        available = {}
        for item_id, units in (entry.get("items") or {}).items():
            free = units - taken.get(item_id, 0)
            if item_id in items and free > 0:
                available[item_id] = free
        if not available:
            continue
        coords = positions.get(drill_id)
        if not coords:
            if drill_id not in warned_drills:
                host.log.level("warn").print(f"[{host.name}] Drill '{drill_id}' holds {available} but stands on no surveyed mineral site; skipped.")
                warned_drills.add(drill_id)
            continue
        sources.append({"kind": "drill", "id": drill_id, "coords": coords, "available": available, "outpost": None})

    if pump_salt.SALT_ITEM_ID in items:
        for pump_id, entry in pump_salt.salt_sources(curr_tick).items():
            taken = reads.reserved_from(pump_id, host.name)
            free = entry["available"] - taken.get(pump_salt.SALT_ITEM_ID, 0)
            if free > 0:
                sources.append({"kind": "pump", "id": pump_id, "coords": entry["coords"], "available": {pump_salt.SALT_ITEM_ID: free}, "outpost": None})

    kept = []
    for src in sources:
        reason = logistics_requests.drone_served_source(src, host.home_outpost)
        if reason:
            host.log.debug(f"pull: skip {src['kind']}:{src['id']} ({reason}; drone yield on).")
        else:
            kept.append(src)
    sources = kept

    host.log.debug(f"[{host.name}] pull: {len(sources)} source(s) hold wanted items: " + ", ".join(f"{src['kind']}:{src['id']}={src['available']}" for src in sources))
    host.log.end()
    return sources


def drop_unviable_sources(sources, unviable, curr_tick):
    """
    sources minus those in `unviable` ({source_id: tick}, a pickup leg
    refused as too slow, VehicleCargoMixin.pull_from_source()). Entries
    older than PULL_UNVIABLE_COOLDOWN_TICKS are pruned from `unviable` first.
    """
    if not unviable:
        return sources
    for source_id, tick in list(unviable.items()):
        if curr_tick - tick >= PULL_UNVIABLE_COOLDOWN_TICKS:
            del unviable[source_id]
    return [src for src in sources if src["id"] not in unviable]


def shop_source(host: "VehicleController", deficits, curr_tick):
    """
    Virtual pull source for the Shop, or None: only for a hauler whose
    home is NOT the home outpost, and only for deficits whose request is
    flagged buyable (logistics_requests.buyable_deficits()). Sits at the
    home outpost's coords (Shop purchases land in home Inventory);
    "available" is the whole buyable deficit. The id is per destination
    (SHOP_SOURCE_ID:<home id>), so two haulers buying for different
    outposts never trim each other's shop legs in claim_pickups().
    """
    home = host.home_outpost
    if home is None or getattr(home, "is_home", True) or not get_component("shop"):
        return None
    available = logistics_requests.sum_tiers(logistics_requests.buyable_deficits(home, deficits, curr_tick))
    if not available:
        return None
    base = host.get_outpost_ref(None)
    if base is None or not hasattr(base, "coords"):
        return None
    host.log.debug(f"[{host.name}] pull: Shop source for buyable deficits {available}.")
    return {"kind": "shop", "id": f"{logistics_requests.SHOP_SOURCE_ID}:{getattr(home, 'id', None)}", "coords": base.coords(), "available": available, "outpost": base}


def route_sources(host: "VehicleController", deficits, curr_tick, unviable, warned_drills):
    """
    Pull sources for `deficits` ({tier: {item_id: units}}): pull_sources()
    minus drop_unviable_sources(), plus the Shop (shop_source(); listed
    last, so free stock at the home outpost wins a tie).
    """
    items = set(logistics_requests.sum_tiers(deficits))
    sources = pull_sources(host, list(items), curr_tick, warned_drills)
    viable = drop_unviable_sources(sources, unviable, curr_tick)
    if len(viable) < len(sources):
        host.log.debug(f"[{host.name}] pull: skipping source(s) too far for {PULL_MIN_LEG_THROTTLE*100:.0f}% throttle: {sorted(unviable)}.")
    shop = shop_source(host, deficits, curr_tick)
    if shop:
        viable.append(shop)
    return viable


def plan_pull_route(host: "VehicleController", deficits, capacity, curr_tick, unviable, warned_drills):
    """
    Multi-stop pickup plan for host's home outpost: route_sources(), then
    best_pull_route(). Returns (route, reachable) as best_pull_route().
    """
    sources = route_sources(host, deficits, curr_tick, unviable, warned_drills)
    return best_pull_route(host, deficits, sources, capacity, curr_tick)


def best_pull_route(host: "VehicleController", deficits, sources, capacity, curr_tick):
    """
    The best trip over `sources` from host's position for its home outpost,
    `deficits` as {tier: {item_id: units}} (pull_deficits_tiered()). "fair"
    tiers are first capped at home's fair share of what the sources hold
    (logistics_requests.fair_share_tiers()). Every source holding something
    wanted is tried as the first stop (pull_candidate()); the chain with
    the most units per band down TIERS (BLOCKER first), per (round-trip m +
    PULL_TRIP_OVERHEAD_M) wins (logistics_requests.haul_rank()). Returns
    (route, reachable): route is [(source, [(item_id, amount), ...]), ...],
    reachable the units of the (capped) deficits any source can cover at all.
    """
    home_id = getattr(host.home_outpost, "id", None)
    deficits = logistics_requests.fair_share_tiers(home_id, deficits, sources, curr_tick)
    supply_all = {}
    for src in sources:
        for item_id, units in src["available"].items():
            supply_all[item_id] = supply_all.get(item_id, 0) + units
    reachable = 0
    for item_id, units in logistics_requests.sum_tiers(deficits).items():
        reachable += min(units, supply_all.get(item_id, 0))

    home_coords = None
    try:
        home_coords = host.home_outpost.coords() if host.home_outpost else None
    except Exception as error:
        swallowed("pull_plan.best_pull_route: host.home_outpost.coords", error)
        home_coords = None
    start = host.get_position()

    best_route, best_rank = [], None
    atomic = logistics_requests.route_atomic_ok(sources)
    for first in sources:
        if atomic:
            candidate = run_atomic(pull_candidate, first, sources, deficits, capacity, start, home_coords)
        else:
            candidate = pull_candidate(first, sources, deficits, capacity, start, home_coords)
        if candidate["chain_checks"]:
            host.log.debug(f"[{host.name}] pull: via '{first['id']}', chain checks: {candidate['chain_checks']}.")
        route, units, tier_units, meters = candidate["route"], candidate["units"], candidate["tier_units"], candidate["meters"]
        if not route:
            continue
        rank = logistics_requests.haul_rank(tier_units, meters, PULL_TRIP_OVERHEAD_M)
        host.log.debug(f"[{host.name}] pull: candidate via '{first['id']}' -> {units} unit(s) ({tier_units}, {logistics_requests.blocker_units(tier_units)} blocker) over {meters:.0f}m ({len(route)} stop(s)), rank {logistics_requests.rank_text(rank)}.")
        if logistics_requests.rank_beats(rank, best_rank):
            best_route, best_rank = route, rank
    return best_route, reachable


def pull_candidate(first, sources, deficits, capacity, start, home_coords):
    """
    plan_pull_chain() from `first` plus its measures: {"route", "units",
    "tier_units" (logistics_requests.route_tier_units()), "meters"
    (start -> stops -> home), "chain_checks" (the chain decisions as one
    text, at most PULL_CHAIN_NOTES_MAX listed, "" when none)}. Pure; one
    lib/atomic.py call per candidate.
    """
    notes = []
    route = plan_pull_chain(first, sources, deficits, capacity, start, home_coords, notes)
    meters, pos = 0.0, start
    for source, _loads in route:
        meters += distance(pos, source["coords"])
        pos = source["coords"]
    meters += distance(pos, home_coords) if (route and home_coords is not None) else 0.0
    checks = "; ".join(f"'{source_id}' direct={direct:.0f}m vs via-home={via_home:.0f}m -> {'chain' if ok else 'skip (home is on the way; next trip)'}"
                       for source_id, direct, via_home, ok in notes[:PULL_CHAIN_NOTES_MAX])
    if len(notes) > PULL_CHAIN_NOTES_MAX:
        checks += f"; +{len(notes) - PULL_CHAIN_NOTES_MAX} more"
    return {"route": route,
            "units": sum(a for _src, loads in route for _i, a in loads),
            "tier_units": logistics_requests.route_tier_units(deficits, route),
            "meters": meters,
            "chain_checks": checks}


def plan_pull_chain(first, sources, deficits, capacity, start, home_coords, notes=None):
    """
    One candidate trip starting at `first`: from there the chain greedily
    visits the nearest (from the previous stop) remaining source, tiers in
    TIERS order (logistics_requests.plan_take()), then largest deficits,
    until capacity, PULL_MAX_STOPS_PER_TRIP or the deficits run out. Stops
    after the first must pass pull_chain_worthwhile() (no driving past
    home). Pure (no game calls, no logging): best_pull_route() runs it as a
    lib/atomic.py call. Each chain check is appended to `notes` as
    (source_id, direct m, via-home m, chained) for the caller to log.
    """
    left = logistics_requests.route_left(deficits)
    cap_left = capacity
    pos = start
    pending = list(sources)
    route = []
    while pending and cap_left > 0 and len(route) < PULL_MAX_STOPS_PER_TRIP:
        if not route:
            useful = [src for src in pending if src["id"] == first["id"] and logistics_requests.source_useful(src, left, cap_left)]
        else:
            useful = [src for src in pending if logistics_requests.source_useful(src, left, cap_left)]
            if home_coords is not None:
                useful = [src for src in useful if pull_chain_worthwhile(pos, src, home_coords, notes)]
        if not useful:
            break
        useful.sort(key=lambda src: distance(pos, src["coords"]))
        source = useful[0]
        pending = [src for src in pending if src["id"] != source["id"]]
        loads = []
        for item_id in sorted(source["available"].keys(), key=lambda i: logistics_requests.tier_rank(left, i)):
            takes = logistics_requests.plan_take(source, item_id, left, cap_left)
            amount = sum(takes.values())
            if amount <= 0:
                continue
            loads.append((item_id, amount))
            for tier, units in takes.items():
                left[tier][item_id] -= units
            cap_left -= amount
            if cap_left <= 0:
                break
        if loads:
            route.append((source, loads))
            pos = source["coords"]
    return route


def pull_chain_worthwhile(prev_coords, source, home_coords, notes=None):
    """
    True when chaining `source` straight after prev_coords beats
    dropping off at home first: direct leg <= PULL_CHAIN_MAX_DETOUR_RATIO
    * (prev -> home -> source). Rejects stops that lie "behind" home.
    Pure; the check is appended to `notes` (see plan_pull_chain()).
    """
    coords = source["coords"]
    direct = distance(prev_coords, coords)
    via_home = distance(prev_coords, home_coords) + distance(home_coords, coords)
    ok = via_home > 0 and direct <= PULL_CHAIN_MAX_DETOUR_RATIO * via_home
    if notes is not None:
        notes.append((source["id"], direct, via_home, ok))
    return ok
