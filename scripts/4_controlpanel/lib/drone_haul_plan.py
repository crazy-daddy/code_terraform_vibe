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
#     outpost_tier_deficits() (net of in-flight logistics.pickups), read
#     from the tier snapshot (lib/logistics_snapshot.py) when it is FRESH. Tiers
#     are served in TIERS order (logistics_requests.plan_take(), haul_rank());
#     "fair" tiers are capped at the fair share of what the sources hold
#     (fair_share_tiers());
#   - planned units reserved per source (logistics.pickups "source").
#
# Heli yield: an electric hauler leaves a long or BLOCKER job to an idle heli
# that reaches it clearly sooner (yield_to_helis()) and plans its next-best
# job instead of waiting. A heli ranks with a time-based trip overhead
# (trip_overhead_m()), so short jobs stay with the electrics.
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
import logistics_snapshot
from archive import archive
from atomic import run_atomic, run_batched
from drone_energy import engine_profile
from priority import FAIR_BANDS
from swallow import swallowed
from tree_console import method_block

if TYPE_CHECKING:
    from drone import DroneController

# Drill stops chained into one trip, and a chained stop's max detour vs
# delivering first (same meaning as pull_plan.py's PULL_* constants).
HAUL_MAX_STOPS_PER_TRIP = 3
HAUL_CHAIN_MAX_DETOUR_RATIO = 0.75
# Job scoring = units / (route meters + this): a fixed per-trip cost so a
# tiny job next door doesn't always beat a full load a bit further out.
HAUL_TRIP_OVERHEAD_M = 300.0
# Next-ranked candidates kept with a plan: when another hauler reserved the
# winner's load meanwhile, job_haul tries these (one claim each) before a
# whole replan.
HAUL_CLAIM_ALTERNATES = 4
# distance_table() key of the drone's own position, and the most sources
# whose table one lib/atomic.py call builds (DISTANCE_TABLE_ATOMIC_MAX + 2
# points, pairs measured once; larger tables are built stepped).
START_KEY = "@start"
DISTANCE_TABLE_ATOMIC_MAX = 16
# Upper-bound CPython opcodes of one haul_candidate() given its destination's
# distance_table(): a base, per source (nearest sort, chain and usefulness
# checks), and per item of the HAUL_MAX_STOPS_PER_TRIP sources holding the
# most per demand tier the destination asks for (only a stop's items are
# ranked, taken and loaded; the planners walk only the tiers with demand,
# logistics_requests.route_left()). Items summed over every source charged
# each source's items as if all were stops: a 9-source outpost always
# planned stepped. Fitted with 1/0.85 margin over ~16k random and
# adversarial routes (1-12 sources, 1-14 items each, 1-9 tiers, 1-5 pods,
# skewed item counts, sources that free nothing; devtools/perf/step_profile.py's
# counter): candidates under the gate measured <= ~7,900 opcodes. A
# candidate runs as one lib/atomic.py call when the estimate is within
# logistics_requests.ROUTE_ATOMIC_MAX_COST. The Pioneer's pull planner keeps
# logistics_requests.route_atomic_ok().
HAUL_COST_BASE = 5900
HAUL_COST_PER_SOURCE = 80
HAUL_COST_PER_ITEM_TIER = 80
# Upper-bound CPython opcodes of one _dest_prep() (sources_for(),
# reachable_units(), cost terms) over the plan's sources: a base, per source
# and per item summed over all sources. Fitted on 400 random cases (1-30
# sources, 1-40 items each), max actual/estimate 0.98.
DEST_PREP_COST_BASE = 1500
DEST_PREP_COST_PER_SOURCE = 60
DEST_PREP_COST_PER_ITEM = 30
# _cap_fair_tiers(): rival request entries per lib/atomic.py call
# (tier_deficits() ~300-420 opcodes each; 20 peaked at 8.5k), and the
# upper-bound opcodes of one destination's capped tiers given the
# precomputed rivals (fitted on 300 random worlds, max actual/estimate 0.90).
FAIR_RIVAL_CHUNK = 10
FAIR_COST_BASE = 1000
FAIR_COST_PER_SOURCE_ITEM = 24
FAIR_COST_PER_DEFICIT_ITEM = 160
# Units per Cargo Pod (docs/models/storage_and_items.md DroneCargo.capacity();
# Shield Plating halves them). Each pod holds one material.
CARGO_POD_UNITS = {"cargo_pod_small": 100, "cargo_pod_medium": 250, "cargo_pod_large": 500}

# Idle heli haulers: {drone name: {"tick", "at": [x, y]}}, written by
# job_haul.HaulJob each plan that finds no job, dropped when it finds one.
# An entry older than HELI_FREE_STALE_TICKS doesn't count (the heli is busy
# refuelling, gone or stopped; idle helis replan every HaulJob.idle_delay, 5 s).
HELI_FREE_KEY = "drone.heli_free"
HELI_FREE_STALE_TICKS = 300
# A job without BLOCKER units yields only from this route length: the heli
# pays Oil per metre, and on a short trip its speed saves little.
HELI_YIELD_MIN_M = 1500.0
# Yield only when the heli's ETA (from where it hovers) is at most this
# share of the electric's ETA.
HELI_YIELD_ETA_RATIO = 0.75
# One electric yields one destination for at most this long, then takes it,
# so a free heli that never picks it (out of range, a better job) can't
# starve it; the yield is forgotten after HELI_YIELD_FORGET_TICKS.
HELI_YIELD_MAX_TICKS = 600
HELI_YIELD_FORGET_TICKS = 6000

# Failures in a row at one Depot/outpost before it goes on cooldown, and the
# cooldown (10 ticks/s -> 5 minutes).
STALL_MAX_ATTEMPTS = 3
STALL_COOLDOWN_TICKS = 3000


@dataclass
class HaulMemory:
    """One drone's in-memory planning state: stall counters and cooldowns by (kind, target_id), and the once-per-run warnings."""

    failures: dict = field(default_factory=dict)
    cooldowns: dict = field(default_factory=dict)
    heli_yields: dict = field(default_factory=dict)  # {dest outpost id: tick of the first yield to a heli}
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


def haul_destinations(drone: "DroneController", curr_tick, reads=None, layout=None, view=None):
    """
    Outposts with a Drone Depot and something missing, as dicts
    {"outpost", "outpost_id", "coords", "depots", "tiers" ({tier:
    {item_id: units}}), "deficits" (every tier summed)}.
    Destinations on stall
    cooldown are left out. `reads` (logistics_requests.PlanReads) and
    `layout` (depot_layout()) are the plan's shared reads. With `view`
    (logistics_snapshot.TierView) the tiers come from the snapshot record
    instead of a live outpost_tier_deficits().
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
            if drone.log.debugging:
                drone.log.debug(f"haul: '{outpost_id}' on stall cooldown; not a destination this cycle.")
            continue
        if view is not None:
            tiers = view.deficits(outpost_id)
        else:
            tiers = logistics_requests.outpost_tier_deficits(outpost, curr_tick, live=True, reads=reads)
        deficits = logistics_requests.sum_tiers(tiers)
        if deficits:
            dests.append({"outpost": outpost, "outpost_id": outpost_id, "coords": depots[0]["coords"], "depots": depots, "tiers": tiers, "deficits": deficits})
    _warn_if_home_has_no_depot(drone, outposts, depots_by_outpost, curr_tick, reads)
    if drone.log.debugging:
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
    if drone.log.debugging:
        drone.log.debug(f"[{drone.name}] haul: {len(sources)} drill(s) hold wanted items: " + ", ".join(f"{s['id']}={s['available']}" for s in sources))
    return sources


def outpost_sources(drone: "DroneController", items, curr_tick, reads=None, layout=None, tiers=logistics_requests.TIERS, view=None):
    """
    Drone Depot outposts holding free stock of `items` (Warehouses,
    Depot stockpiles, Inventory at home -- logistics_requests.
    outpost_tier_free(loader=LOADER_DRONE)), net of other haulers'
    reservations. "tiers" is what another outpost's demand may take per
    tier, "available" the most any tier may take. Outposts on stall
    cooldown are left out. `reads` and `layout` as in haul_destinations().
    Only the bands in `tiers` are computed (plan_haul_job(): the bands some
    destination misses; every reader of a source's tiers asks only for
    those). With `view` (logistics_snapshot.TierView) the free stock comes
    from the snapshot record instead of a live outpost_tier_free().
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
            if drone.log.debugging:
                drone.log.debug(f"haul: outpost '{outpost_id}' on stall cooldown; not a source this cycle.")
            continue
        if view is not None:
            free = view.free(outpost_id, item_ids, tiers)
        else:
            free = logistics_requests.outpost_tier_free(outpost, item_ids, None, curr_tick, exclude_vehicle=drone.name, loader=logistics_requests.LOADER_DRONE, reads=reads, tiers=tiers)
        available = logistics_requests.most_free(free)
        if available:
            sources.append({"kind": "outpost", "id": outpost_id, "coords": depots[0]["coords"], "available": available, "tiers": free, "depots": depots, "outpost": outpost})
    if drone.log.debugging:
        drone.log.debug(f"[{drone.name}] haul: {len(sources)} Depot outpost(s) hold wanted items: " + ", ".join(f"{s['id']}={s['available']}" for s in sources))
    drone.log.end()
    return sources


def shop_sources(drone: "DroneController", dests, curr_tick, reads, layout):
    """
    One Shop source per non-home destination with buyable deficits
    (logistics_requests.buyable_deficits(); remote Bio Lab reagents, see
    lib/outpost_reagents.py): a virtual stop at the home outpost's Drone
    Depots, "available" the whole buyable deficit, "for_dest" the
    destination (sources_for() offers it to that one only). The id
    SHOP_SOURCE_ID:<dest id> matches the Pioneer's (pull_plan.shop_source()),
    so claim_pickups() trims a drone and a Pioneer buying for the same
    outpost against each other. At the stop the drone buys into home
    Inventory and loads what the Depot stages (drone_hauler.load_at_depot()).
    None without a Shop or a Depot at home; sources on stall cooldown are
    left out. Listed after the real sources, so free stock wins a tie.
    """
    outposts, depots_by_outpost = layout
    home = next((o for o in outposts.values() if getattr(o, "is_home", False)), None)
    if home is None or not depots_by_outpost.get(home.id) or not get_component("shop"):
        return []
    sources = []
    for dest in dests:
        if dest["outpost_id"] == home.id:
            continue
        source_id = f"{logistics_requests.SHOP_SOURCE_ID}:{dest['outpost_id']}"
        if is_cooling(drone, "source", source_id, curr_tick):
            continue
        available = logistics_requests.sum_tiers(logistics_requests.buyable_deficits(dest["outpost"], dest["tiers"], curr_tick, reads.requests))
        if available:
            depots = depots_by_outpost[home.id]
            sources.append({"kind": "shop", "id": source_id, "for_dest": dest["outpost_id"], "coords": depots[0]["coords"], "available": available, "depots": depots, "outpost": home})
    if sources and drone.log.debugging:
        drone.log.debug(f"[{drone.name}] haul: Shop source(s) for buyable deficits: " + ", ".join(f"{s['id']}={s['available']}" for s in sources))
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
    legs = sum(geometry.distance(points[i], points[i + 1]) for i in range(len(points) - 1))
    return fuel_for_meters(legs, _nearest_service_dist(points[-1], services), rates)


def fuel_for_meters(meters, tail, rates):
    """route_fuel_for() from the route's length and `tail` (m from its last point to the nearest service). Pure."""
    per_m, floor_per_m, margin, reserve = rates
    return (meters * per_m + tail * floor_per_m) * margin + reserve


def distance_table(start, dest, sources):
    """
    {key: {key: m}} between the start (START_KEY), dest (its outpost_id) and
    every source (its id), each pair measured once. Built once per
    destination and shared by all its candidates: per-candidate distance
    math (chain checks, nearest stop, stop orders) was a third of a
    candidate's opcodes. Pure.
    """
    points = [(START_KEY, start), (dest["outpost_id"], dest["coords"])] + [(s["id"], s["coords"]) for s in sources]
    table = {key: {key: 0.0} for key, _c in points}
    for i in range(len(points)):
        a, a_coords = points[i]
        row = table[a]
        for j in range(i + 1, len(points)):
            b, b_coords = points[j]
            d = geometry.distance(a_coords, b_coords)
            row[b] = d
            table[b][a] = d
    return table


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


def pod_space(pods):
    """(units free in empty pods, {item_id: units free in its own pods}): pod_room(pods, i) == empty + own.get(i, 0), from one pass."""
    empty = 0
    own = {}
    for size, item, count in pods:
        if item is None:
            empty += size - count
        else:
            own[item] = own.get(item, 0) + size - count
    return empty, own


def load_pods(pods, item_id, units):
    """
    Plans `units` of item_id into `pods` (pod_room()) like a load: its own
    pods first, then empty ones in slot order. Returns the units of the
    empty pods it latched to item_id (pod_space()'s empty moves to own).
    """
    latched = 0
    for pod in pods:
        if units <= 0:
            break
        if pod[1] == item_id or pod[1] is None:
            n = min(units, pod[0] - pod[2])
            if n > 0:
                if pod[1] is None:
                    pod[1] = item_id
                    latched += pod[0] - pod[2]
                pod[2] += n
                units -= n
    return latched


def plan_route_for(dest, sources, capacity, start, first, pods, dist=None):
    """
    Greedy nearest-neighbour route for one destination, starting at
    `first` (else the nearest useful source): tiers in TIERS order
    ("fair" tiers fair-share capped), largest deficits first per stop, up
    to capacity / HAUL_MAX_STOPS_PER_TRIP, chained stops only when not
    "behind" the destination. `pods` (pod_sizes(), of the empty cargo)
    caps each item: one material per pod, so a stop whose materials find
    no free or matching pod is never planned. The live load corrects any
    over-optimism. Pure (no game calls, no logging): candidate_routes()
    runs it as a lib/atomic.py call. `dist` is distance_table() over these
    sources (built here when None). Returns [(source, [(item, n), ...]), ...].
    """
    if dist is None:
        dist = distance_table(start, dest, sources)
    dest_id = dest["outpost_id"]
    to_dest = dist[dest_id]
    left = logistics_requests.route_left(dest["tiers"])
    cap_left = capacity
    pos = START_KEY
    pool = [s for s in sources if s["id"] != dest_id]
    hold = [[size, None, 0] for size in pods]
    empty, own = pod_space(hold)
    route = []
    while pool and cap_left > 0 and len(route) < HAUL_MAX_STOPS_PER_TRIP:
        here = dist[pos]
        if not route and first is not None:
            ordered = [s for s in pool if s["id"] == first["id"]]
        else:
            # Nearest first: the first useful one is the stop, the rest go unchecked.
            ordered = sorted(pool, key=lambda s: here[s["id"]])
        source = None
        for s in ordered:
            if route:
                # A chained stop must not lie "behind" the destination.
                via_dest = here[dest_id] + to_dest[s["id"]]
                if via_dest <= 0 or here[s["id"]] > HAUL_CHAIN_MAX_DETOUR_RATIO * via_dest:
                    continue
            # Every item fits while an empty pod is left; else only those with room in their own pods.
            if logistics_requests.source_useful(s, left, cap_left, None if empty > 0 else own):
                source = s
                break
        if source is None:
            break
        pool = [s for s in pool if s["id"] != source["id"]]
        loads = []
        order = source["available"]
        if len(order) > 1:
            order = sorted(order, key=lambda i: logistics_requests.tier_rank(left, i))
        for item_id in order:
            cap = min(cap_left, empty + own.get(item_id, 0))
            if cap <= 0:
                continue
            takes = logistics_requests.plan_take(source, item_id, left, cap)
            amount = sum(takes.values())
            if amount <= 0:
                continue
            latched = load_pods(hold, item_id, amount)
            empty -= latched
            own[item_id] = own.get(item_id, 0) + latched - amount
            loads.append((item_id, amount))
            for tier, units in takes.items():
                left[tier][item_id] -= units
            cap_left -= amount
            if cap_left <= 0:
                break
        if loads:
            route.append((source, loads))
            pos = source["id"]
    return route


def _fair_dest_cost(dest, sources):
    """Upper-bound opcodes of one _cap_one() call (FAIR_COST_*)."""
    cost = FAIR_COST_BASE
    for tier in FAIR_BANDS:
        deficit = dest["tiers"].get(tier)
        if deficit:
            cost += FAIR_COST_PER_DEFICIT_ITEM * len(deficit) + FAIR_COST_PER_SOURCE_ITEM * sum([len(logistics_requests.source_tier(s, tier)) for s in sources])
    return cost


def _cap_one(dest, sources, curr_tick, reads, rivals):
    tiers = logistics_requests.fair_share_tiers(dest["outpost_id"], dest["tiers"], sources, curr_tick, reads, rivals)
    return tiers, logistics_requests.sum_tiers(tiers)


def _cap_fair_tiers(dests, sources, curr_tick, reads, view=None):
    """
    Caps each destination's "fair" tiers at its fair share of what the
    other sources hold (logistics_requests.fair_share_tiers()). Rival
    deficits are computed once per plan for every item a destination wants
    at a fair band (atomic slices of FAIR_RIVAL_CHUNK entries), or read
    from `view` (logistics_snapshot.TierView.rivals(): the record's
    deficits); then each destination with a fair band is capped in one
    lib/atomic.py call when _fair_dest_cost() fits ROUTE_ATOMIC_MAX_COST.
    Destinations without a fair band are left as they are.
    """
    fair = [d for d in dests if logistics_requests.has_fair_demand(d["tiers"])]
    if not fair:
        return
    wanted = set()
    for dest in fair:
        for tier in FAIR_BANDS:
            wanted.update(dest["tiers"].get(tier, {}))
    if view is not None:
        rivals = view.rivals(wanted)
    else:
        entries = logistics_requests.fair_rival_entries(reads.requests, wanted)
        # Group the pickups by destination outside the callbacks.
        reads.in_flight(None)
        rivals = logistics_requests.fair_rivals_index(run_batched(logistics_requests.fair_rival_bands, entries, FAIR_RIVAL_CHUNK, reads))
    for dest in fair:
        if _fair_dest_cost(dest, sources) <= logistics_requests.ROUTE_ATOMIC_MAX_COST:
            dest["tiers"], dest["deficits"] = run_atomic(_cap_one, dest, sources, curr_tick, reads, rivals)
        else:
            dest["tiers"], dest["deficits"] = _cap_one(dest, sources, curr_tick, reads, rivals)


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


def _orders(stops):
    """Every ordering of `stops` (no itertools in game)."""
    if len(stops) <= 1:
        return [stops]
    out = []
    for i in range(len(stops)):
        for rest in _orders(stops[:i] + stops[i + 1 :]):
            out.append([stops[i]] + rest)
    return out


def route_meters(route, dist, dest_id):
    """Meters of start -> `route`'s stops -> dest_id over distance_table() `dist`. Pure."""
    meters = 0.0
    pos = START_KEY
    for s, _l in route:
        meters += dist[pos][s["id"]]
        pos = s["id"]
    return meters + dist[pos][dest_id]


# shortest_order()'s stop orders past the given one, as _orders() lists them, for the usual stop counts.
_STOP_ORDERS = {2: ((1, 0),), 3: ((0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0))}


def shortest_order(route, dist, dest_id):
    """
    (`route` with its stops in the shortest start -> stops -> dest order,
    its meters), loads unchanged (their sum fits the cargo in any order).
    candidate_routes() skips a first stop an earlier route already visits,
    so the kept route must not keep the greedy order that its forced first
    stop gave it. Brute force over distance_table() `dist`: at most
    HAUL_MAX_STOPS_PER_TRIP stops. Pure.
    """
    best, best_m = route, route_meters(route, dist, dest_id)
    if len(route) < 2:
        return best, best_m
    indexes = _STOP_ORDERS.get(len(route))
    orders = _orders(list(route))[1:] if indexes is None else [[route[i] for i in idx] for idx in indexes]
    for order in orders:
        meters = route_meters(order, dist, dest_id)
        if meters < best_m:
            best, best_m = order, meters
    return best, best_m


def haul_candidate(dest, sources, capacity, start, first, pods, services, rates, dist=None, tail=None):
    """
    plan_route_for() plus its measures: {"route", "units", "tier_units"
    (logistics_requests.route_tier_units()), "meters", "fuel"} (fuel per route_fuel_for(), start -> stops -> dest).
    Pure; one lib/atomic.py call per candidate. `rates` is fuel_rates(), read beforehand;
    `dist` (distance_table()) and `tail` (dest to its nearest service) are built here when None.
    """
    if dist is None:
        dist = distance_table(start, dest, sources)
    if tail is None:
        tail = _nearest_service_dist(dest["coords"], services)
    route, meters = shortest_order(plan_route_for(dest, sources, capacity, start, first, pods, dist), dist, dest["outpost_id"])
    return {"route": route, "units": sum(n for _s, loads in route for _i, n in loads), "tier_units": logistics_requests.route_tier_units(dest["tiers"], route), "meters": meters, "fuel": fuel_for_meters(meters, tail, rates)}


def _haul_cost_terms(dest, sources):
    """(items of the HAUL_MAX_STOPS_PER_TRIP `sources` holding the most, demand tiers dest asks for) for haul_atomic_ok()."""
    sizes = sorted([len(s["available"]) for s in sources], reverse=True)
    return sum(sizes[:HAUL_MAX_STOPS_PER_TRIP]), max(1, len([t for t in dest["tiers"].values() if t]))


def haul_atomic_ok(dest, sources):
    """True when one haul_candidate() for dest over `sources` (its sources_for()) fits a lib/atomic.py call (HAUL_COST_*)."""
    items, tiers = _haul_cost_terms(dest, sources)
    return HAUL_COST_BASE + HAUL_COST_PER_SOURCE * len(sources) + HAUL_COST_PER_ITEM_TIER * items * tiers <= logistics_requests.ROUTE_ATOMIC_MAX_COST


def _dest_prep(dest, sources, services):
    """
    (dest_sources, items, tiers, atomic, tail, reachable) for one destination:
    sources_for(), _haul_cost_terms(), haul_atomic_ok(), the m from dest to
    its nearest service and reachable_units() over the cut sources (equal
    to it over all sources: the cut keeps every item dest misses). Pure.
    """
    dest_sources = sources_for(dest, sources)
    items, tiers = _haul_cost_terms(dest, dest_sources)
    return dest_sources, items, tiers, haul_atomic_ok(dest, dest_sources), _nearest_service_dist(dest["coords"], services), reachable_units(dest, dest_sources)


def candidate_routes(drone: "DroneController", dests, sources, capacity, start, services, stats=None):
    """
    (dest, haul_candidate()) for every destination x every useful first drill. Only
    trying the nearest drill first let a small nearby deficit (28 iron)
    hide a big one further out (2000 neutronium) whose drill is "behind"
    the destination, so never chainable -- same fix as the Pioneer's
    pull_plan.best_pull_route() trying every first stop. Scoring picks the winner.
    Each candidate is one lib/atomic.py call (one tick at most) when
    haul_atomic_ok() says it fits the callback cap.
    A first drill an earlier route to the same destination already visits
    is skipped: it mostly rebuilds that route in another order, and
    shortest_order() gives the kept one its best order. `stats` (a dict,
    optional) gets "atomic", "stepped" and "covered" counts and "over_cap"
    ([(dest id, sources, items of the fullest stops, tiers)] per destination too big for an atomic call).
    Sets each dest's "reachable" (reachable_units()) before its candidates.
    """
    if stats is None:
        stats = {}
    for key in ("atomic", "stepped", "covered"):
        stats.setdefault(key, 0)
    stats.setdefault("over_cap", [])
    pods = pod_sizes(drone)
    if pods is None:
        # Unreadable modules: one pod of the free capacity plans one material per trip.
        pods = [capacity]
    rates = fuel_rates(drone)
    prep_atomic = DEST_PREP_COST_BASE + DEST_PREP_COST_PER_SOURCE * len(sources) + DEST_PREP_COST_PER_ITEM * sum([len(s["available"]) for s in sources]) <= logistics_requests.ROUTE_ATOMIC_MAX_COST
    for dest in dests:
        if prep_atomic:
            dest_sources, items, tiers, atomic, tail, dest["reachable"] = run_atomic(_dest_prep, dest, sources, services)
        else:
            dest_sources, items, tiers, atomic, tail, dest["reachable"] = _dest_prep(dest, sources, services)
        if not atomic:
            stats["over_cap"].append((dest["outpost_id"], len(dest_sources), items, tiers))
        if len(dest_sources) <= DISTANCE_TABLE_ATOMIC_MAX:
            dist = run_atomic(distance_table, start, dest, dest_sources)
        else:
            dist = distance_table(start, dest, dest_sources)
        visited = set()
        for first in dest_sources:
            if first["id"] in visited:
                stats["covered"] += 1
                continue
            if atomic:
                stats["atomic"] += 1
                candidate = run_atomic(haul_candidate, dest, dest_sources, capacity, start, first, pods, services, rates, dist, tail)
            else:
                stats["stepped"] += 1
                candidate = haul_candidate(dest, dest_sources, capacity, start, first, pods, services, rates, dist, tail)
            visited.update(s["id"] for s, _l in candidate["route"])
            yield dest, candidate


def sources_for(dest, sources):
    """
    `sources` other than dest itself, each cut to the items dest still
    misses; a source left with none is dropped. plan_route_for() would
    take nothing else from them, and a network-wide item list (every
    destination's wants on one source) kept candidates out of a
    lib/atomic.py call (haul_atomic_ok()). The cut "available" also
    steers drone_hauler.stage_depot_for() to the Depot holding the load.
    A Shop source (shop_sources()) is kept only for its own destination.
    """
    out = []
    for s in sources:
        if s["id"] == dest["outpost_id"] or s.get("for_dest", dest["outpost_id"]) != dest["outpost_id"]:
            continue
        available = {i: u for i, u in s["available"].items() if dest["deficits"].get(i, 0) > 0}
        if available:
            out.append(dict(s, available=available))
    return out


@method_block(lambda drone, *_, **__: f"[{drone.name}] plan_haul_job")
def plan_haul_job(drone: "DroneController", curr_tick):
    """
    Best job network-wide, or None: for every destination, plan a route
    over drills and other Depot outposts and rank it by units per
    band down TIERS (BLOCKER first), per (route meters +
    trip_overhead_m()) (logistics_requests.haul_rank()). An electric
    drops the jobs an idle heli should fly (yield_to_helis()). A route
    carrying BLOCKER units skips logistics_requests.HAUL_MIN_LOAD_UNITS. Jobs not flyable even on a full tank are
    dropped; the caller refuels first when the chosen job needs more
    than is aboard.
    Returns {"dest", "route", "units", "wanted", "fuel", "seen", "rank",
    "meters", "blockers", "snapshot", "alternates"}: the HAUL_CLAIM_ALTERNATES next-ranked candidates (same
    keys, no "alternates") for job_haul to claim when this one is taken.
    "snapshot" is True when the plan read the tier snapshot (logistics_snapshot).
    """
    # Before any demand/stock read (see claim_pickups()); the drone plans
    # only with empty cargo, so its own leftovers from an abandoned plan go.
    seen = logistics_requests.planning_snapshot(drone.name)
    # Requests, pickups (planned against `seen`) and each outpost's stock, read once for the whole plan.
    reads = logistics_requests.PlanReads(curr_tick, seen)
    # Destination tiers, source free stock and fair-share rivals from the
    # tier snapshot when it is FRESH, else read live (_claim_route() then
    # trims a snapshot plan to the destination's live deficit).
    record, state = logistics_snapshot.read_snapshot(curr_tick)
    view = logistics_snapshot.TierView(record, reads, exclude_vehicle=drone.name) if state == logistics_snapshot.FRESH else None
    if state == logistics_snapshot.STALE and record is not None:
        drone.log.debug(f"[{drone.name}] haul: tier snapshot STALE ({curr_tick - record['tick']} ticks old); planning live.")
    layout = depot_layout(drone)
    dests = haul_destinations(drone, curr_tick, reads, layout, view)
    if not dests:
        return None
    items = set()
    for dest in dests:
        items.update(dest["deficits"].keys())
    # Bands some destination misses: the only ones a source's free stock is computed at.
    active = tuple(t for t in logistics_requests.TIERS if any(dest["tiers"].get(t) for dest in dests))
    sources = drill_sources(drone, items, curr_tick, reads) + outpost_sources(drone, items, curr_tick, reads, layout, active, view) + shop_sources(drone, dests, curr_tick, reads, layout)
    if not sources:
        return None
    _cap_fair_tiers(dests, sources, curr_tick, reads, view)

    try:
        capacity = drone.drone.cargo.capacity() - drone.drone.cargo.count()
    except Exception as error:
        swallowed("drone_haul_plan.plan_haul_job: drone.drone.cargo.capacity", error)
        capacity = 0
    if capacity <= 0:
        return None
    services = drone.get_all_drone_services()
    _, full_tank, _ = drone.get_battery()
    start = drone.position()

    overhead_m = trip_overhead_m(getattr(drone, "engine", ""))
    debugging = drone.log.debugging
    ranked = []
    stats = {}
    for dest, candidate in candidate_routes(drone, dests, sources, capacity, start, services, stats):
        route, units, tier_units, meters, fuel = (candidate["route"], candidate["units"], candidate["tier_units"], candidate["meters"], candidate["fuel"])
        blockers = logistics_requests.blocker_units(tier_units)
        # A BLOCKER load flies alone; nothing more arrives by waiting.
        wanted = logistics_requests.min_load_units(blockers, dest["reachable"])
        if not route or units < wanted or units <= 0:
            if debugging:
                drone.log.debug(f"haul: '{dest['outpost_id']}' via {[s['id'] for s, _l in route]}: {units} unit(s) < minimum {wanted}; skipped.")
            continue
        if fuel > full_tank:
            if debugging:
                drone.log.debug(f"haul: '{dest['outpost_id']}' needs {fuel:.1f} {drone.energy_unit()} > full tank {full_tank:.1f}; out of range.")
            continue
        rank = logistics_requests.haul_rank(tier_units, meters, overhead_m)
        if debugging:
            drone.log.debug(f"haul: candidate -> '{dest['outpost_id']}' via {[s['id'] for s, _l in route]}: {units} unit(s) ({tier_units}, {blockers} blocker), {meters:.0f} m, fuel {fuel:.1f} {drone.energy_unit()}, rank {logistics_requests.rank_text(rank)}.")
        ranked.append({"dest": dest, "route": route, "units": units, "wanted": wanted, "fuel": fuel, "seen": seen, "rank": rank, "meters": meters, "blockers": blockers, "snapshot": view is not None})
    if debugging:
        over_cap = ", ".join(f"{d} {n} src/{i} stop items/{t} tiers" for d, n, i, t in stats["over_cap"])
        drone.log.debug(f"haul: routes built {stats['atomic']} atomic, {stats['stepped']} stepped" + (f" (over cap: {over_cap})" if over_cap else "") + f", {stats['covered']} skipped as covered; {len(ranked)} candidate(s).")
    if ranked and getattr(drone, "engine", "") != "heli":
        helis = free_helis(curr_tick)
        if helis:
            ranked = yield_to_helis(drone, ranked, start, helis, curr_tick)
    if not ranked:
        return None
    ranked.sort(key=lambda c: c["rank"], reverse=True)
    best = ranked[0]
    best["alternates"] = ranked[1 : 1 + HAUL_CLAIM_ALTERNATES]
    return best


# ------------------------------------------------------------ heli yield


def trip_overhead_m(engine):
    """
    HAUL_TRIP_OVERHEAD_M in the engine's metres: the overhead stands for the
    docking and loading time, in which a heli flies speed-ratio times as far.
    So a heli ranks short jobs lower than an electric does.
    """
    return HAUL_TRIP_OVERHEAD_M * engine_profile(engine)["speed_m_per_h"] / engine_profile("electric")["speed_m_per_h"]


def free_helis(curr_tick):
    """[(x, y)] of the heli haulers idle within HELI_FREE_STALE_TICKS (HELI_FREE_KEY)."""
    entries = archive.get(HELI_FREE_KEY, {}) or {}
    if not isinstance(entries, dict):
        return []
    out = []
    for entry in entries.values():
        if isinstance(entry, dict) and curr_tick - entry.get("tick", -HELI_FREE_STALE_TICKS - 1) <= HELI_FREE_STALE_TICKS and entry.get("at"):
            out.append((float(entry["at"][0]), float(entry["at"][1])))
    return out


def heli_should_fly(candidate, start, helis):
    """
    True when one of the idle helis at `helis` should fly this electric
    `candidate` (plan_haul_job() dict): it carries BLOCKER units or spans
    HELI_YIELD_MIN_M, and the nearest heli's ETA (its flight to the first
    stop, then the same route) is at most HELI_YIELD_ETA_RATIO of the
    electric's from `start`. Pure.
    """
    meters = candidate["meters"]
    if not candidate["route"] or (candidate["blockers"] <= 0 and meters < HELI_YIELD_MIN_M):
        return False
    first = candidate["route"][0][0]["coords"]
    rest = meters - geometry.distance(start, first)
    heli_m = min(geometry.distance(at, first) for at in helis) + rest
    heli_eta = heli_m / engine_profile("heli")["speed_m_per_h"]
    electric_eta = meters / engine_profile("electric")["speed_m_per_h"]
    return heli_eta <= HELI_YIELD_ETA_RATIO * electric_eta


def yield_to_helis(drone: "DroneController", ranked, start, helis, curr_tick):
    """
    `ranked` without the candidates an idle heli should fly (heli_should_fly()).
    A destination is yielded for HELI_YIELD_MAX_TICKS at most
    (HaulMemory.heli_yields), then kept, so a heli that never takes it
    can't starve it.
    """
    yields = drone.haul_memory.heli_yields
    for dest_id in [d for d, t in yields.items() if curr_tick - t > HELI_YIELD_FORGET_TICKS]:
        del yields[dest_id]
    kept = []
    for candidate in ranked:
        dest_id = candidate["dest"]["outpost_id"]
        since = yields.get(dest_id, curr_tick)
        if curr_tick - since < HELI_YIELD_MAX_TICKS and heli_should_fly(candidate, start, helis):
            yields.setdefault(dest_id, curr_tick)
            if drone.log.debugging:
                drone.log.debug(f"haul: '{dest_id}' ({candidate['meters']:.0f} m, {candidate['blockers']} blocker) left to an idle heli.")
            continue
        kept.append(candidate)
    return kept


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
