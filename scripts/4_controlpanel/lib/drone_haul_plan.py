# Drone hauler mixin: job planning for the floating freight hauler
# (lib/drone_hauler.py). Reads network demand and supply, plans and scores
# candidate routes, and picks the best job (_plan_haul_job()). Also keeps
# the per-drone stall memory that drops failing Depots/outposts from
# planning for a while. Planning reads game state but never moves the drone
# or writes the archive; execution lives in lib/drone_hauler.py.
#
# Demand and coordination are shared with the Pioneer pull hauler
# (lib/vehicle_cargo.py run_pull_loop()), so the two never both serve the
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

import logistics_requests
import drill_sites
from swallow import swallowed
from atomic import run_atomic
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from drone import DroneController

# Drill stops chained into one trip, and a chained stop's max detour vs
# delivering first (same meaning as vehicle_cargo.py's PULL_* constants).
HAUL_MAX_STOPS_PER_TRIP = 3
HAUL_CHAIN_MAX_DETOUR_RATIO = 0.75
# Smallest load worth a flight (or the whole outstanding deficit, if smaller).
HAUL_MIN_LOAD_UNITS = 50
# Job scoring = units / (route meters + this): a fixed per-trip cost so a
# tiny job next door doesn't always beat a full load a bit further out.
HAUL_TRIP_OVERHEAD_M = 300.0

# Failures in a row at one Depot/outpost before it goes on cooldown, and the
# cooldown (10 ticks/s -> 5 minutes).
STALL_MAX_ATTEMPTS = 3
STALL_COOLDOWN_TICKS = 3000


class DroneHaulPlanMixin:

    @property
    def _host(self) -> "DroneController":
        return self  # type: ignore[return-value]

    # ------------------------------------------------------------ demand / sources

    def _outposts_by_id(self):
        network = get_component("outpost_network")
        try:
            return {o.id: o for o in network.outposts()} if network else {}
        except Exception as error:
            swallowed("drone_haul_plan.DroneHaulPlanMixin._outposts_by_id: network.outposts", error)
            return {}

    def _depot_layout(self):
        """({outpost_id: OutpostRef}, {outpost_id: [depot dicts]}): the network's outposts and its Drone Depots by outpost."""
        depots_by_outpost = {}
        for depot in self._host.get_all_drone_depots():
            depots_by_outpost.setdefault(depot.get("outpost_id"), []).append(depot)
        return self._outposts_by_id(), depots_by_outpost

    def _haul_destinations(self, curr_tick, reads=None, layout=None):
        """
        Outposts with a Drone Depot and something missing, as dicts
        {"outpost", "outpost_id", "coords", "depots", "tiers" ({tier:
        {item_id: units}}), "deficits" (every tier summed), "urgent"}.
        Destinations on stall
        cooldown are left out. `reads` (logistics_requests.PlanReads) and
        `layout` (_depot_layout()) are the plan's shared reads.
        """
        self._host.log.start(f"[{self._host.name}] _haul_destinations", level="debug")
        if reads is None:
            reads = logistics_requests.PlanReads(curr_tick)
        outposts, depots_by_outpost = layout if layout is not None else self._depot_layout()

        dests = []
        requests = reads.requests
        for outpost_id, depots in depots_by_outpost.items():
            outpost = outposts.get(outpost_id)
            if outpost is None:
                continue
            if self._cooling("dest", outpost_id, curr_tick):
                self._host.log.debug(f"haul: '{outpost_id}' on stall cooldown; not a destination this cycle.")
                continue
            tiers = logistics_requests.outpost_tier_deficits(outpost, curr_tick, live=True, reads=reads)
            deficits = logistics_requests.sum_tiers(tiers)
            if deficits:
                first_tier = tiers[logistics_requests.TIERS[0]]
                urgent = {i for i, e in requests.get(outpost_id, {}).items() if e.get("urgent") and i in first_tier}
                dests.append({"outpost": outpost, "outpost_id": outpost_id, "coords": depots[0]["coords"], "depots": depots,
                              "tiers": tiers, "deficits": deficits, "urgent": urgent})
        self._warn_if_home_has_no_depot(outposts, depots_by_outpost, curr_tick, reads)
        self._host.log.debug(f"[{self._host.name}] haul: destinations with demand: " + (", ".join(f"{d['outpost_id']}={d['tiers']}" for d in dests) or "none"))
        self._host.log.end()
        return dests

    def _warn_if_home_has_no_depot(self, outposts, depots_by_outpost, curr_tick, reads=None):
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
        if not getattr(self, "_home_no_depot_warned", False):
            self._host.log.level("warn").print(f"[{self._host.name}] '{home.id}' requests {wanted} but has no Drone Depot; floating haulers can't deliver there. Depots found at: {sorted(k for k in depots_by_outpost if k) or 'none'}.")
            self._home_no_depot_warned = True
        self._host.log.debug(f"[{self._host.name}] haul: '{home.id}' skipped as destination (no Drone Depot) despite requests {wanted}.")

    def _drill_sources(self, items, curr_tick, reads=None):
        """Advertised drills holding any of `items` with a known position, net of other haulers' reservations (from `reads` when given)."""
        positions = drill_sites.drill_positions(curr_tick)
        if not hasattr(self, "_unlocated_drills_warned"):
            self._unlocated_drills_warned = set()
        sources = []
        for drill_id, entry in drill_sites.advertised_drills(curr_tick).items():
            if reads is not None:
                taken = reads.reserved_from(drill_id, self._host.name)
            else:
                taken = logistics_requests.reserved_from(drill_id, curr_tick, exclude_vehicle=self._host.name)
            available = {}
            for item_id, units in (entry.get("items") or {}).items():
                free = int(units - taken.get(item_id, 0))
                if item_id in items and free > 0:
                    available[item_id] = free
            if not available:
                continue
            coords = positions.get(drill_id)
            if not coords:
                if drill_id not in self._unlocated_drills_warned:
                    self._host.log.level("warn").print(f"[{self._host.name}] Drill '{drill_id}' holds {available} but stands on no surveyed mineral site; skipped.")
                    self._unlocated_drills_warned.add(drill_id)
                continue
            sources.append({"kind": "drill", "id": drill_id, "coords": (float(coords[0]), float(coords[1])), "available": available})
        self._host.log.debug(f"[{self._host.name}] haul: {len(sources)} drill(s) hold wanted items: " + ", ".join(f"{s['id']}={s['available']}" for s in sources))
        return sources

    def _outpost_sources(self, items, curr_tick, reads=None, layout=None):
        """
        Drone Depot outposts holding free stock of `items` (Warehouses,
        Depot stockpiles, Inventory at home -- logistics_requests.
        outpost_tier_free(loader=LOADER_DRONE)), net of other haulers'
        reservations. "tiers" is what another outpost's demand may take per
        tier, "available" the most any tier may take. Outposts on stall
        cooldown are left out. `reads` and `layout` as in _haul_destinations().
        """
        self._host.log.start(f"[{self._host.name}] _outpost_sources", level="debug")
        if reads is None:
            reads = logistics_requests.PlanReads(curr_tick)
        outposts, depots_by_outpost = layout if layout is not None else self._depot_layout()
        item_ids = list(items)
        sources = []
        for outpost_id, depots in depots_by_outpost.items():
            if not outpost_id:
                continue
            outpost = outposts.get(outpost_id)
            if outpost is None:
                continue
            if self._cooling("source", outpost_id, curr_tick):
                self._host.log.debug(f"haul: outpost '{outpost_id}' on stall cooldown; not a source this cycle.")
                continue
            free = logistics_requests.outpost_tier_free(outpost, item_ids, None, curr_tick, exclude_vehicle=self._host.name, loader=logistics_requests.LOADER_DRONE, reads=reads)
            available = logistics_requests.most_free(free)
            if available:
                sources.append({"kind": "outpost", "id": outpost_id, "coords": depots[0]["coords"], "available": available,
                                "tiers": free, "depots": depots, "outpost": outpost})
        self._host.log.debug(f"[{self._host.name}] haul: {len(sources)} Depot outpost(s) hold wanted items: " + ", ".join(f"{s['id']}={s['available']}" for s in sources))
        self._host.log.end()
        return sources

    # ------------------------------------------------------------ planning

    def _nearest_service_dist(self, coords, services):
        if not services:
            return 0.0
        return min(self._host.distance_between(coords, s["coords"]) for s in services)

    def _fuel_rates(self):
        """(cruise per m, speedmode-floor per m, safety margin, emergency reserve) for _route_fuel()."""
        return (self._host.wh_per_meter_at_throttle(self._host.cruise_throttle), self._host.minimum_wh_per_meter(),
                self._host.SAFETY_MARGIN_MULTIPLIER, self._host.emergency_reserve())

    def _route_fuel(self, points, services, rates=None):
        """
        Fuel (Wh / t Oil) for flying `points` in order at cruise throttle,
        plus reaching the nearest drone_service from the last point at the
        speedmode floor, with safety margin and emergency reserve -- the
        floating hauler's "there-and-back": "back" is any service, not home.
        Pure with `rates` (_fuel_rates(), read beforehand).
        """
        per_m, floor_per_m, margin, reserve = rates or self._fuel_rates()
        legs = sum(self._host.distance_between(points[i], points[i + 1]) for i in range(len(points) - 1))
        tail = self._nearest_service_dist(points[-1], services)
        fuel = legs * per_m + tail * floor_per_m
        return fuel * margin + reserve

    def _chain_worthwhile(self, prev_coords, coords, dest_coords):
        direct = self._host.distance_between(prev_coords, coords)
        via_dest = self._host.distance_between(prev_coords, dest_coords) + self._host.distance_between(dest_coords, coords)
        return via_dest > 0 and direct <= HAUL_CHAIN_MAX_DETOUR_RATIO * via_dest

    def _plan_route_for(self, dest, sources, capacity, start, first, room):
        """
        Greedy nearest-neighbour route for one destination, starting at
        `first` (else the nearest useful source): tiers in TIERS order
        ("fair" tiers fair-share capped), largest deficits first per stop, up
        to capacity / HAUL_MAX_STOPS_PER_TRIP, chained stops only when not
        "behind" the destination. Per-item room is `room` ({item_id: units},
        cargo.space_for() read before planning; one material per pod); the
        live load corrects any over-optimism. Pure (no game calls, no
        logging): _candidate_routes() runs it as a lib/atomic.py call.
        Returns [(source, [(item, n), ...]), ...].
        """
        left = logistics_requests.route_left(dest["tiers"])
        cap_left = capacity
        pos = start
        pool = [s for s in sources if s["id"] != dest["outpost_id"]]
        route = []
        while pool and cap_left > 0 and len(route) < HAUL_MAX_STOPS_PER_TRIP:
            if route:
                useful = [s for s in pool if logistics_requests.source_useful(s, left, cap_left)
                          and self._chain_worthwhile(pos, s["coords"], dest["coords"])]
            elif first is not None:
                useful = [s for s in pool if s["id"] == first["id"] and logistics_requests.source_useful(s, left, cap_left)]
            else:
                useful = [s for s in pool if logistics_requests.source_useful(s, left, cap_left)]
            if not useful:
                break
            source = min(useful, key=lambda s: self._host.distance_between(pos, s["coords"]))
            pool = [s for s in pool if s["id"] != source["id"]]
            loads = []
            order = sorted(source["available"], key=lambda i: logistics_requests.tier_rank(left, i))
            for item_id in order:
                takes = logistics_requests.plan_take(source, item_id, left, min(cap_left, room.get(item_id, 0)))
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

    @staticmethod
    def _cap_fair_tiers(dests, sources, curr_tick, reads=None):
        """Caps each destination's "fair" tiers at its fair share of what the other sources hold (logistics_requests.fair_share_tiers())."""
        for dest in dests:
            dest["tiers"] = logistics_requests.fair_share_tiers(dest["outpost_id"], dest["tiers"], sources, curr_tick, reads)
            dest["deficits"] = logistics_requests.sum_tiers(dest["tiers"])

    @staticmethod
    def _reachable(dest, sources):
        """Units of dest's deficits that the sources (other than dest itself) can cover at all."""
        supply = {}
        for s in sources:
            if s["id"] == dest["outpost_id"]:
                continue
            for item_id, units in s["available"].items():
                supply[item_id] = supply.get(item_id, 0) + units
        return sum(min(u, supply.get(i, 0)) for i, u in dest["deficits"].items())

    def _item_room(self, item_id):
        try:
            return int(self._host.drone.cargo.space_for(item_id))
        except Exception as error:
            swallowed("drone_haul_plan.DroneHaulPlanMixin._item_room: self._host.drone.cargo.space_for", error)
            return 0

    def _haul_candidate(self, dest, sources, capacity, start, first, room, services, rates):
        """
        _plan_route_for() plus its measures: {"route", "units", "tier_units"
        (logistics_requests.route_tier_units()), "meters", "fuel"} (fuel per _route_fuel(), start -> stops -> dest).
        Pure; one lib/atomic.py call per candidate.
        """
        route = self._plan_route_for(dest, sources, capacity, start, first, room)
        points = [start] + [s["coords"] for s, _l in route] + [dest["coords"]]
        return {"route": route,
                "units": sum(n for _s, loads in route for _i, n in loads),
                "tier_units": logistics_requests.route_tier_units(dest["tiers"], route),
                "meters": sum(self._host.distance_between(points[i], points[i + 1]) for i in range(len(points) - 1)),
                "fuel": self._route_fuel(points, services, rates)}

    def _candidate_routes(self, dests, sources, capacity, start, services):
        """
        (dest, _haul_candidate()) for every destination x every useful first drill. Only
        trying the nearest drill first let a small nearby deficit (28 iron)
        hide a big one further out (2000 neutronium) whose drill is "behind"
        the destination, so never chainable -- same fix as the Pioneer's
        _plan_pull_route() trying every first stop. Scoring picks the winner.
        Each candidate is one lib/atomic.py call (one tick at most) when
        logistics_requests.route_atomic_ok() says it fits the callback cap.
        """
        items = set()
        for s in sources:
            items.update(s["available"])
        room = {item_id: self._item_room(item_id) for item_id in items}
        rates = self._fuel_rates()
        atomic = logistics_requests.route_atomic_ok(sources)
        for dest in dests:
            firsts = [s for s in sources if s["id"] != dest["outpost_id"] and any(dest["deficits"].get(i, 0) > 0 for i in s["available"])]
            for first in firsts:
                if atomic:
                    yield dest, run_atomic(self._haul_candidate, dest, sources, capacity, start, first, room, services, rates)
                else:
                    yield dest, self._haul_candidate(dest, sources, capacity, start, first, room, services, rates)

    def _plan_haul_job(self, curr_tick):
        """
        Best job network-wide, or None: for every destination, plan a route
        over drills and other Depot outposts and rank it by urgent units,
        then units per tier down TIERS, per (route meters +
        HAUL_TRIP_OVERHEAD_M) (logistics_requests.haul_rank()). A route
        carrying an urgent item skips HAUL_MIN_LOAD_UNITS. Jobs not flyable even on a full tank are
        dropped; the caller refuels first when the chosen job needs more
        than is aboard.
        Returns {"dest", "route", "units", "fuel"}.
        """
        self._host.log.start(f"[{self._host.name}] _plan_haul_job", level="debug")
        seen = logistics_requests.pickups_snapshot()  # before any demand/stock read; see claim_pickups()
        # Requests, pickups (planned against `seen`) and each outpost's stock, read once for the whole plan.
        reads = logistics_requests.PlanReads(curr_tick, seen)
        layout = self._depot_layout()
        dests = self._haul_destinations(curr_tick, reads, layout)
        if not dests:
            self._host.log.end()
            return None
        items = set()
        for dest in dests:
            items.update(dest["deficits"].keys())
        sources = self._drill_sources(items, curr_tick, reads) + self._outpost_sources(items, curr_tick, reads, layout)
        if not sources:
            self._host.log.end()
            return None
        self._cap_fair_tiers(dests, sources, curr_tick, reads)

        try:
            capacity = self._host.drone.cargo.capacity() - self._host.drone.cargo.count()
        except Exception as error:
            swallowed("drone_haul_plan.DroneHaulPlanMixin._plan_haul_job: self._host.drone.cargo.capacity", error)
            capacity = 0
        if capacity <= 0:
            self._host.log.end()
            return None
        services = self._host.get_all_drone_services()
        _, full_tank, _ = self._host.get_battery()
        start = self._host.position()

        best, best_rank = None, None
        reachable = {dest["outpost_id"]: self._reachable(dest, sources) for dest in dests}
        for dest, candidate in self._candidate_routes(dests, sources, capacity, start, services):
            route, units, tier_units, meters, fuel = (candidate["route"], candidate["units"], candidate["tier_units"],
                                                       candidate["meters"], candidate["fuel"])
            urgent = logistics_requests.urgent_units(route, dest.get("urgent", ()))
            # An urgent blocker flies alone; nothing more arrives by waiting.
            wanted = 1 if urgent > 0 else min(HAUL_MIN_LOAD_UNITS, reachable[dest["outpost_id"]])
            if not route or units < wanted or units <= 0:
                self._host.log.debug(f"haul: '{dest['outpost_id']}' via {[s['id'] for s, _l in route]}: {units} unit(s) < minimum {wanted}; skipped.")
                continue
            if fuel > full_tank:
                self._host.log.debug(f"haul: '{dest['outpost_id']}' needs {fuel:.1f} {self._host.energy_unit()} > full tank {full_tank:.1f}; out of range.")
                continue
            rank = logistics_requests.haul_rank(tier_units, meters, HAUL_TRIP_OVERHEAD_M, urgent)
            self._host.log.debug(f"haul: candidate -> '{dest['outpost_id']}' via {[s['id'] for s, _l in route]}: {units} unit(s) ({tier_units}, {urgent} urgent), {meters:.0f} m, fuel {fuel:.1f} {self._host.energy_unit()}, rank {logistics_requests.rank_text(rank)}.")
            if logistics_requests.rank_beats(rank, best_rank):
                best, best_rank = {"dest": dest, "route": route, "units": units, "wanted": wanted, "fuel": fuel, "seen": seen}, rank
        self._host.log.end()
        return best

    # ------------------------------------------------------------ stall cooldowns

    def _cooling(self, kind, target_id, curr_tick):
        until = getattr(self, "_stall_cooldowns", {}).get((kind, target_id), 0)
        return curr_tick < until

    def _note_failure(self, kind, target_id, reason):
        """Counts a failure at a destination/source; STALL_MAX_ATTEMPTS in a row puts it on cooldown."""
        if not hasattr(self, "_stall_failures"):
            self._stall_failures = {}
            self._stall_cooldowns = {}
        key = (kind, target_id)
        count = self._stall_failures.get(key, 0) + 1
        if count >= STALL_MAX_ATTEMPTS:
            self._stall_failures[key] = 0
            self._stall_cooldowns[key] = self._host.get_current_tick() + STALL_COOLDOWN_TICKS
            self._host.log.level("warn").print(f"[{self._host.name}] {kind} '{target_id}' failed {count}x in a row ({reason}); skipping it for {STALL_COOLDOWN_TICKS} ticks.")
        else:
            self._stall_failures[key] = count
            self._host.log.debug(f"[{self._host.name}] {kind} '{target_id}' failure {count}/{STALL_MAX_ATTEMPTS}: {reason}.")

    def _note_success(self, kind, target_id):
        if hasattr(self, "_stall_failures"):
            self._stall_failures.pop((kind, target_id), None)
