# Drone hauler job planning as module functions (see docs/plans/mixin_refactor/
# followups.md) for the floating freight hauler (lib/drone_hauler.py). Every
# function takes the DroneController first. Reads network demand and supply,
# plans and scores candidate routes, and picks the best job (plan_haul_job()).
# Also keeps the per-drone stall memory (HaulMemory, DroneController.haul_memory)
# that drops failing Depots/outposts from planning for a while. Planning reads
# game state but never moves the drone or writes the archive; execution lives
# in lib/drone_hauler.py.
#
# Demand and coordination are shared with the Pioneer pull hauler
# (lib/job_pull.py PullJob), so the two never both serve the
# same deficit:
#   - demand per outpost, home included, per tier: logistics_requests.
#     outpost_tier_deficits() (net of in-flight logistics.pickups). Tiers
#     are served in TIERS order (logistics_requests.plan_take(), haul_rank());
#     "fair" tiers are capped at the fair share of what the sources hold
#     (fair_share_tiers());
#   - planned units reserved per source (logistics.pickups "source").
#
# Stalls: a Depot where docking, loading or unloading fails
# STALL_MAX_ATTEMPTS times in a row goes on cooldown (in memory, per drone)
# for STALL_COOLDOWN_TICKS, so the drone moves on to other jobs and
# destinations instead of retrying the same one forever.

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import drill_sites
import geometry
import logistics_requests
from atomic import run_atomic
from swallow import swallowed

if TYPE_CHECKING:
    from drone import DroneController

# Drill stops chained into one trip, and a chained stop's max detour vs
# delivering first (same meaning as pull_plan.py's PULL_* constants).
HAUL_MAX_STOPS_PER_TRIP = 3
HAUL_CHAIN_MAX_DETOUR_RATIO = 0.75
# Job scoring = units / (route meters + this): a fixed per-trip cost so a
# tiny job next door doesn't always beat a full load a bit further out.
HAUL_TRIP_OVERHEAD_M = 300.0
# Units per Cargo Pod (docs/models/storage_and_items.md DroneCargo.capacity();
# Shield Plating halves them). Each pod holds one material.
CARGO_POD_UNITS = {"cargo_pod_small": 100, "cargo_pod_medium": 250, "cargo_pod_large": 500}

# Failures in a row at one Depot/outpost before it goes on cooldown, and the
# cooldown (10 ticks/s -> 5 minutes).
STALL_MAX_ATTEMPTS = 3
STALL_COOLDOWN_TICKS = 3000


@dataclass
class HaulMemory:
    """One drone's in-memory planning state: stall counters and cooldowns by (kind, target_id), and the once-per-run warnings."""

    failures: dict = field(default_factory=dict)
    cooldowns: dict = field(default_factory=dict)
    home_no_depot_warned: bool = False
    unlocated_drills_warned: set = field(default_factory=set)


# ------------------------------------------------------------ demand / sources


def outposts_by_id():
    network = get_component("outpost_network")
    try:
        return {o.id: o for o in network.outposts()} if network else {}
    except Exception as error:
        swallowed("drone_haul_plan.outposts_by_id: network.outposts", error)
        return {}


def depot_layout(drone: "DroneController"):
    """({outpost_id: OutpostRef}, {outpost_id: [depot dicts]}): the network's outposts and its Drone Depots by outpost."""
    depots_by_outpost = {}
    for depot in drone.get_all_drone_depots():
        depots_by_outpost.setdefault(depot.get("outpost_id"), []).append(depot)
    return outposts_by_id(), depots_by_outpost


def haul_destinations(drone: "DroneController", curr_tick, reads=None, layout=None):
    """
    Outposts with a Drone Depot and something missing, as dicts
    {"outpost", "outpost_id", "coords", "depots", "tiers" ({tier:
    {item_id: units}}), "deficits" (every tier summed)}.
    Destinations on stall
    cooldown are left out. `reads` (logistics_requests.PlanReads) and
    `layout` (depot_layout()) are the plan's shared reads.
    """
    drone.log.start(f"[{drone.name}] haul_destinations", level="debug")
    if reads is None:
        reads = logistics_requests.PlanReads(curr_tick)
    outposts, depots_by_outpost = layout if layout is not None else depot_layout(drone)

    dests = []
    for outpost_id, depots in depots_by_outpost.items():
        outpost = outposts.get(outpost_id)
        if outpost is None:
            continue
        if is_cooling(drone, "dest", outpost_id, curr_tick):
            drone.log.debug(f"haul: '{outpost_id}' on stall cooldown; not a destination this cycle.")
            continue
        tiers = logistics_requests.outpost_tier_deficits(outpost, curr_tick, live=True, reads=reads)
        deficits = logistics_requests.sum_tiers(tiers)
        if deficits:
            dests.append({"outpost": outpost, "outpost_id": outpost_id, "coords": depots[0]["coords"], "depots": depots, "tiers": tiers, "deficits": deficits})
    _warn_if_home_has_no_depot(drone, outposts, depots_by_outpost, curr_tick, reads)
    drone.log.debug(f"[{drone.name}] haul: destinations with demand: " + (", ".join(f"{d['outpost_id']}={d['tiers']}" for d in dests) or "none"))
    drone.log.end()
    return dests


def _warn_if_home_has_no_depot(drone: "DroneController", outposts, depots_by_outpost, curr_tick, reads=None):
    """
    An outpost is only a haul destination if it owns a Drone Depot. A
    depot next to base but inside another outpost doesn't count, so home's
    requests silently never become a job. Warns once per run, then keeps
    the reason in the debug trail.
    """
    home = next((o for o in outposts.values() if getattr(o, "is_home", False)), None)
    if home is None or home.id in depots_by_outpost:
        return
    wanted = logistics_requests.sum_tiers(logistics_requests.outpost_tier_deficits(home, curr_tick, live=False, reads=reads))
    if not wanted:
        return
    if not drone.haul_memory.home_no_depot_warned:
        drone.log.level("warn").print(f"[{drone.name}] '{home.id}' requests {wanted} but has no Drone Depot; floating haulers can't deliver there. Depots found at: {sorted(k for k in depots_by_outpost if k) or 'none'}.")
        drone.haul_memory.home_no_depot_warned = True
    drone.log.debug(f"[{drone.name}] haul: '{home.id}' skipped as destination (no Drone Depot) despite requests {wanted}.")


def drill_sources(drone: "DroneController", items, curr_tick, reads=None):
    """Advertised drills holding any of `items` with a known position, net of other haulers' reservations (from `reads` when given)."""
    positions = drill_sites.drill_positions(curr_tick)
    warned = drone.haul_memory.unlocated_drills_warned
    sources = []
    for drill_id, entry in drill_sites.advertised_drills(curr_tick).items():
        if reads is not None:
            taken = reads.reserved_from(drill_id, drone.name)
        else:
            taken = logistics_requests.reserved_from(drill_id, curr_tick, exclude_vehicle=drone.name)
        available = {}
        for item_id, units in (entry.get("items") or {}).items():
            free = int(units - taken.get(item_id, 0))
            if item_id in items and free > 0:
                available[item_id] = free
        if not available:
            continue
        coords = positions.get(drill_id)
        if not coords:
            if drill_id not in warned:
                drone.log.level("warn").print(f"[{drone.name}] Drill '{drill_id}' holds {available} but stands on no surveyed mineral site; skipped.")
                warned.add(drill_id)
            continue
        sources.append({"kind": "drill", "id": drill_id, "coords": (float(coords[0]), float(coords[1])), "available": available})
    drone.log.debug(f"[{drone.name}] haul: {len(sources)} drill(s) hold wanted items: " + ", ".join(f"{s['id']}={s['available']}" for s in sources))
    return sources


def outpost_sources(drone: "DroneController", items, curr_tick, reads=None, layout=None):
    """
    Drone Depot outposts holding free stock of `items` (Warehouses,
    Depot stockpiles, Inventory at home -- logistics_requests.
    outpost_tier_free(loader=LOADER_DRONE)), net of other haulers'
    reservations. "tiers" is what another outpost's demand may take per
    tier, "available" the most any tier may take. Outposts on stall
    cooldown are left out. `reads` and `layout` as in haul_destinations().
    """
    drone.log.start(f"[{drone.name}] outpost_sources", level="debug")
    if reads is None:
        reads = logistics_requests.PlanReads(curr_tick)
    outposts, depots_by_outpost = layout if layout is not None else depot_layout(drone)
    item_ids = list(items)
    sources = []
    for outpost_id, depots in depots_by_outpost.items():
        if not outpost_id:
            continue
        outpost = outposts.get(outpost_id)
        if outpost is None:
            continue
        if is_cooling(drone, "source", outpost_id, curr_tick):
            drone.log.debug(f"haul: outpost '{outpost_id}' on stall cooldown; not a source this cycle.")
            continue
        free = logistics_requests.outpost_tier_free(outpost, item_ids, None, curr_tick, exclude_vehicle=drone.name, loader=logistics_requests.LOADER_DRONE, reads=reads)
        available = logistics_requests.most_free(free)
        if available:
            sources.append({"kind": "outpost", "id": outpost_id, "coords": depots[0]["coords"], "available": available, "tiers": free, "depots": depots, "outpost": outpost})
    drone.log.debug(f"[{drone.name}] haul: {len(sources)} Depot outpost(s) hold wanted items: " + ", ".join(f"{s['id']}={s['available']}" for s in sources))
    drone.log.end()
    return sources


# ------------------------------------------------------------ planning


def _nearest_service_dist(coords, services):
    if not services:
        return 0.0
    return min(geometry.distance(coords, s["coords"]) for s in services)


def fuel_rates(drone: "DroneController"):
    """(cruise per m, speedmode-floor per m, safety margin, emergency reserve) for route_fuel()."""
    return (drone.wh_per_meter_at_throttle(drone.cruise_throttle), drone.minimum_wh_per_meter(), drone.SAFETY_MARGIN_MULTIPLIER, drone.emergency_reserve())


def route_fuel(drone: "DroneController", points, services, rates=None):
    """route_fuel_for() with the drone's own rates (fuel_rates())."""
    return route_fuel_for(points, services, rates or fuel_rates(drone))


def route_fuel_for(points, services, rates):
    """
    Fuel (Wh / t Oil) for flying `points` in order at cruise throttle,
    plus reaching the nearest drone_service from the last point at the
    speedmode floor, with safety margin and emergency reserve -- the
    floating hauler's "there-and-back": "back" is any service, not home.
    Pure with `rates` (fuel_rates(), read beforehand).
    """
    per_m, floor_per_m, margin, reserve = rates
    legs = sum(geometry.distance(points[i], points[i + 1]) for i in range(len(points) - 1))
    tail = _nearest_service_dist(points[-1], services)
    fuel = legs * per_m + tail * floor_per_m
    return fuel * margin + reserve


def _chain_worthwhile(prev_coords, coords, dest_coords):
    direct = geometry.distance(prev_coords, coords)
    via_dest = geometry.distance(prev_coords, dest_coords) + geometry.distance(dest_coords, coords)
    return via_dest > 0 and direct <= HAUL_CHAIN_MAX_DETOUR_RATIO * via_dest


def pod_sizes(drone: "DroneController"):
    """Units of each mounted Cargo Pod in slot order (CARGO_POD_UNITS, halved when plated), or None if drone.modules() is unreadable."""
    try:
        modules = [slot.module_id for slot in sorted(drone.drone.modules(), key=lambda slot: int(slot.index))]
    except Exception as error:
        swallowed("drone_haul_plan.pod_sizes: drone.drone.modules", error)
        return None
    divisor = 2 if drone.plated else 1
    return [CARGO_POD_UNITS[m] // divisor for m in modules if m in CARGO_POD_UNITS]


def pod_room(pods, item_id):
    """Units of item_id that still fit in `pods` ([[units, item_id or None, count], ...]): its own pods' rest plus every empty pod."""
    return sum(size - count for size, item, count in pods if item is None or item == item_id)


def pod_rooms(pods, items):
    """{item_id: pod_room(pods, item_id)} for every item in `items`, from one pass over the pods (not one per item)."""
    empty = 0
    own = {}
    for size, item, count in pods:
        if item is None:
            empty += size - count
        else:
            own[item] = own.get(item, 0) + size - count
    return {item_id: empty + own.get(item_id, 0) for item_id in items}


def load_pods(pods, item_id, units):
    """Plans `units` of item_id into `pods` (pod_room()) like a load: its own pods first, then empty ones in slot order."""
    for pod in pods:
        if units <= 0:
            return
        if pod[1] == item_id or pod[1] is None:
            n = min(units, pod[0] - pod[2])
            if n > 0:
                pod[1] = item_id
                pod[2] += n
                units -= n


def plan_route_for(dest, sources, capacity, start, first, pods):
    """
    Greedy nearest-neighbour route for one destination, starting at
    `first` (else the nearest useful source): tiers in TIERS order
    ("fair" tiers fair-share capped), largest deficits first per stop, up
    to capacity / HAUL_MAX_STOPS_PER_TRIP, chained stops only when not
    "behind" the destination. `pods` (pod_sizes(), of the empty cargo)
    caps each item: one material per pod, so a stop whose materials find
    no free or matching pod is never planned. The live load corrects any
    over-optimism. Pure (no game calls, no logging): candidate_routes()
    runs it as a lib/atomic.py call. Returns [(source, [(item, n), ...]), ...].
    """
    left = logistics_requests.route_left(dest["tiers"])
    cap_left = capacity
    pos = start
    pool = [s for s in sources if s["id"] != dest["outpost_id"]]
    hold = [[size, None, 0] for size in pods]
    items = set()
    for s in pool:
        items.update(s["available"])
    room = pod_rooms(hold, items)
    route = []
    while pool and cap_left > 0 and len(route) < HAUL_MAX_STOPS_PER_TRIP:
        if route:
            useful = [s for s in pool if logistics_requests.source_useful(s, left, cap_left, room) and _chain_worthwhile(pos, s["coords"], dest["coords"])]
        elif first is not None:
            useful = [s for s in pool if s["id"] == first["id"] and logistics_requests.source_useful(s, left, cap_left, room)]
        else:
            useful = [s for s in pool if logistics_requests.source_useful(s, left, cap_left, room)]
        if not useful:
            break
        source = min(useful, key=lambda s: geometry.distance(pos, s["coords"]))
        pool = [s for s in pool if s["id"] != source["id"]]
        loads = []
        order = sorted(source["available"], key=lambda i: logistics_requests.tier_rank(left, i))
        for item_id in order:
            takes = logistics_requests.plan_take(source, item_id, left, min(cap_left, pod_room(hold, item_id)))
            amount = sum(takes.values())
            if amount <= 0:
                continue
            load_pods(hold, item_id, amount)
            loads.append((item_id, amount))
            for tier, units in takes.items():
                left[tier][item_id] -= units
            cap_left -= amount
            if cap_left <= 0:
                break
        if loads:
            route.append((source, loads))
            pos = source["coords"]
            room = pod_rooms(hold, items)
    return route


def _cap_fair_tiers(dests, sources, curr_tick, reads=None):
    """Caps each destination's "fair" tiers at its fair share of what the other sources hold (logistics_requests.fair_share_tiers())."""
    for dest in dests:
        dest["tiers"] = logistics_requests.fair_share_tiers(dest["outpost_id"], dest["tiers"], sources, curr_tick, reads)
        dest["deficits"] = logistics_requests.sum_tiers(dest["tiers"])


def reachable_units(dest, sources):
    """Units of dest's deficits that the sources (other than dest itself) can cover at all."""
    supply = {}
    for s in sources:
        if s["id"] == dest["outpost_id"]:
            continue
        for item_id, units in s["available"].items():
            supply[item_id] = supply.get(item_id, 0) + units
    return sum(min(u, supply.get(i, 0)) for i, u in dest["deficits"].items())


def item_room(drone: "DroneController", item_id):
    try:
        return int(drone.drone.cargo.space_for(item_id))
    except Exception as error:
        swallowed("drone_haul_plan.item_room: drone.drone.cargo.space_for", error)
        return 0


def haul_candidate(dest, sources, capacity, start, first, pods, services, rates):
    """
    plan_route_for() plus its measures: {"route", "units", "tier_units"
    (logistics_requests.route_tier_units()), "meters", "fuel"} (fuel per route_fuel_for(), start -> stops -> dest).
    Pure; one lib/atomic.py call per candidate. `rates` is fuel_rates(), read beforehand.
    """
    route = plan_route_for(dest, sources, capacity, start, first, pods)
    points = [start] + [s["coords"] for s, _l in route] + [dest["coords"]]
    return {"route": route, "units": sum(n for _s, loads in route for _i, n in loads), "tier_units": logistics_requests.route_tier_units(dest["tiers"], route), "meters": sum(geometry.distance(points[i], points[i + 1]) for i in range(len(points) - 1)), "fuel": route_fuel_for(points, services, rates)}


def candidate_routes(drone: "DroneController", dests, sources, capacity, start, services):
    """
    (dest, haul_candidate()) for every destination x every useful first drill. Only
    trying the nearest drill first let a small nearby deficit (28 iron)
    hide a big one further out (2000 neutronium) whose drill is "behind"
    the destination, so never chainable -- same fix as the Pioneer's
    pull_plan.best_pull_route() trying every first stop. Scoring picks the winner.
    Each candidate is one lib/atomic.py call (one tick at most) when
    logistics_requests.route_atomic_ok() says it fits the callback cap.
    """
    pods = pod_sizes(drone)
    if pods is None:
        # Unreadable modules: one pod of the free capacity plans one material per trip.
        pods = [capacity]
    rates = fuel_rates(drone)
    for dest in dests:
        dest_sources = sources_for(dest, sources)
        atomic = logistics_requests.route_atomic_ok(dest_sources, len(pods))
        for first in dest_sources:
            if atomic:
                yield dest, run_atomic(haul_candidate, dest, dest_sources, capacity, start, first, pods, services, rates)
            else:
                yield dest, haul_candidate(dest, dest_sources, capacity, start, first, pods, services, rates)


def sources_for(dest, sources):
    """
    `sources` other than dest itself, each cut to the items dest still
    misses; a source left with none is dropped. plan_route_for() would
    take nothing else from them, and a network-wide item list (every
    destination's wants on one source) kept candidates out of a
    lib/atomic.py call (route_atomic_ok()). The cut "available" also
    steers drone_hauler.stage_depot_for() to the Depot holding the load.
    """
    out = []
    for s in sources:
        if s["id"] == dest["outpost_id"]:
            continue
        available = {i: u for i, u in s["available"].items() if dest["deficits"].get(i, 0) > 0}
        if available:
            out.append(dict(s, available=available))
    return out


def plan_haul_job(drone: "DroneController", curr_tick):
    """
    Best job network-wide, or None: for every destination, plan a route
    over drills and other Depot outposts and rank it by units per
    band down TIERS (BLOCKER first), per (route meters +
    HAUL_TRIP_OVERHEAD_M) (logistics_requests.haul_rank()). A route
    carrying BLOCKER units skips logistics_requests.HAUL_MIN_LOAD_UNITS. Jobs not flyable even on a full tank are
    dropped; the caller refuels first when the chosen job needs more
    than is aboard.
    Returns {"dest", "route", "units", "fuel"}.
    """
    drone.log.start(f"[{drone.name}] plan_haul_job", level="debug")
    # Before any demand/stock read (see claim_pickups()); the drone plans
    # only with empty cargo, so its own leftovers from an abandoned plan go.
    seen = logistics_requests.planning_snapshot(drone.name)
    # Requests, pickups (planned against `seen`) and each outpost's stock, read once for the whole plan.
    reads = logistics_requests.PlanReads(curr_tick, seen)
    layout = depot_layout(drone)
    dests = haul_destinations(drone, curr_tick, reads, layout)
    if not dests:
        drone.log.end()
        return None
    items = set()
    for dest in dests:
        items.update(dest["deficits"].keys())
    sources = drill_sources(drone, items, curr_tick, reads) + outpost_sources(drone, items, curr_tick, reads, layout)
    if not sources:
        drone.log.end()
        return None
    _cap_fair_tiers(dests, sources, curr_tick, reads)

    try:
        capacity = drone.drone.cargo.capacity() - drone.drone.cargo.count()
    except Exception as error:
        swallowed("drone_haul_plan.plan_haul_job: drone.drone.cargo.capacity", error)
        capacity = 0
    if capacity <= 0:
        drone.log.end()
        return None
    services = drone.get_all_drone_services()
    _, full_tank, _ = drone.get_battery()
    start = drone.position()

    best, best_rank = None, None
    reachable = {dest["outpost_id"]: reachable_units(dest, sources) for dest in dests}
    for dest, candidate in candidate_routes(drone, dests, sources, capacity, start, services):
        route, units, tier_units, meters, fuel = (candidate["route"], candidate["units"], candidate["tier_units"], candidate["meters"], candidate["fuel"])
        blockers = logistics_requests.blocker_units(tier_units)
        # A BLOCKER load flies alone; nothing more arrives by waiting.
        wanted = logistics_requests.min_load_units(blockers, reachable[dest["outpost_id"]])
        if not route or units < wanted or units <= 0:
            drone.log.debug(f"haul: '{dest['outpost_id']}' via {[s['id'] for s, _l in route]}: {units} unit(s) < minimum {wanted}; skipped.")
            continue
        if fuel > full_tank:
            drone.log.debug(f"haul: '{dest['outpost_id']}' needs {fuel:.1f} {drone.energy_unit()} > full tank {full_tank:.1f}; out of range.")
            continue
        rank = logistics_requests.haul_rank(tier_units, meters, HAUL_TRIP_OVERHEAD_M)
        drone.log.debug(f"haul: candidate -> '{dest['outpost_id']}' via {[s['id'] for s, _l in route]}: {units} unit(s) ({tier_units}, {blockers} blocker), {meters:.0f} m, fuel {fuel:.1f} {drone.energy_unit()}, rank {logistics_requests.rank_text(rank)}.")
        if logistics_requests.rank_beats(rank, best_rank):
            best, best_rank = {"dest": dest, "route": route, "units": units, "wanted": wanted, "fuel": fuel, "seen": seen}, rank
    drone.log.end()
    return best


# ------------------------------------------------------------ stall cooldowns


def is_cooling(drone: "DroneController", kind, target_id, curr_tick):
    return curr_tick < drone.haul_memory.cooldowns.get((kind, target_id), 0)


def note_failure(drone: "DroneController", kind, target_id, reason):
    """Counts a failure at a destination/source; STALL_MAX_ATTEMPTS in a row puts it on cooldown."""
    memory = drone.haul_memory
    key = (kind, target_id)
    count = memory.failures.get(key, 0) + 1
    if count >= STALL_MAX_ATTEMPTS:
        memory.failures[key] = 0
        memory.cooldowns[key] = drone.get_current_tick() + STALL_COOLDOWN_TICKS
        drone.log.level("warn").print(f"[{drone.name}] {kind} '{target_id}' failed {count}x in a row ({reason}); skipping it for {STALL_COOLDOWN_TICKS} ticks.")
    else:
        memory.failures[key] = count
        drone.log.debug(f"[{drone.name}] {kind} '{target_id}' failure {count}/{STALL_MAX_ATTEMPTS}: {reason}.")


def note_success(drone: "DroneController", kind, target_id):
    drone.haul_memory.failures.pop((kind, target_id), None)
