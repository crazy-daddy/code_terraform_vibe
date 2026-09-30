# Drone role: floating freight hauler (field Mining Drills and Drone Depot
# outposts -> Drone Depots). Detected when a drone carries Cargo Pods but no
# bio module (see DroneController.detect_role()).
#
# "Floating": no home Depot. Every cycle the drone picks the best job
# network-wide -- which outpost (with a Drone Depot) needs what, and which
# drills or other Depot outposts hold it -- flies there, loads, delivers to
# that outpost's Depot, and moves on. It refuels at whichever
# drone_service_station is nearest when a job's fuel budget demands it, and
# hovers in place when there is nothing to do (never holds a bay while idle).
#
# Loading: cargo.load() works only at a docked Drone Depot or a field Mining
# Drill, cargo.unload() only into a docked Depot (drone.md, DroneCargo). A
# drill needs no staging. An outpost pickup asks the source Depot to pull the
# items out of local storage first (lib/depot_stage.py, fulfilled by
# lib/drone_depot.py fulfil_stage()) while the drone is on its way, then
# loads in rounds as the small stockpile refills.
#
# Demand and coordination are shared with the Pioneer pull hauler
# (lib/vehicle_cargo.py run_pull_loop()), so the two never both serve the
# same deficit:
#   - demand per outpost: logistics_requests.outpost_deficits_tiered() (net
#     of in-flight logistics.pickups), plus get_raw_material_demands() at
#     home (net of mining.reserved_yield) as need tier. Need is served first
#     (logistics_requests.haul_rank()); buffer deficits are capped at the fair
#     share of what the sources hold (fair_buffer_caps());
#   - planned units reserved per source (logistics.pickups "source") and, for
#     home-bound ore, debited from mining.reserved_yield.
# The Depot controller (lib/drone_depot.py drain_freight()) drains unloaded
# freight into local storage while the drone unloads in rounds.
#
# Stalls: a Depot where docking, loading or unloading fails
# STALL_MAX_ATTEMPTS times in a row goes on cooldown (in memory, per drone)
# for STALL_COOLDOWN_TICKS, so the drone moves on to other jobs and
# destinations instead of retrying the same one forever.

import logistics_requests
import mining_reservations
import depot_stage
import drill_sites
import fleet_intent
from archive import archive
from production import get_raw_material_demands
from drone_claims import MISSION_KEY
from swallow import swallowed
from atomic import run_atomic
from typing import TYPE_CHECKING
from tree_console import flush_all, reset_all

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
# Unloading into a small Depot stockpile happens in rounds while
# drone_depot.py drains it; give up (keep cargo, retry later) after this.
DEPOT_UNLOAD_TIMEOUT_S = 300.0
DEPOT_UNLOAD_RETRY_S = 2.0
# Waiting at a Depot whose bays are all taken.
DEPOT_BAY_WAIT_S = 60.0
# Loading at a source Depot happens in rounds while drone_depot.py stages
# more from storage; give up (keep what's aboard) after this.
DEPOT_LOAD_TIMEOUT_S = 120.0
# Docked at a Depot with no load/unload progress for this long -> leave the
# bay, hover, retry later.
DOCK_IDLE_MAX_S = 60.0
# Failures in a row at one Depot/outpost before it goes on cooldown, and the
# cooldown (10 ticks/s -> 5 minutes).
STALL_MAX_ATTEMPTS = 3
STALL_COOLDOWN_TICKS = 3000
# Refuel/charge wait at a drone_service before giving up for this cycle.
REFUEL_TIMEOUT_S = 900.0
REFUEL_FULL_LEVEL = 0.98
# Between jobs (no cargo aboard), below this charge the hauler docks at the
# nearest drone_service, where the LAUNCH_MIN_SOC launch floor holds it until
# topped up. Outpost buffers keep short, cheap jobs available nearly all the
# time, so without this trigger the per-job budget alone lets the hauler
# chain jobs down to the emergency reserve and never charge.
HAUL_RECHARGE_SOC = 0.30


class DroneHaulerMixin:

    @property
    def _host(self) -> "DroneController":
        return self  # type: ignore[return-value]

    # ------------------------------------------------------------ demand / sources

    def _outposts_by_id(self):
        network = get_component("outpost_network")
        try:
            return {o.id: o for o in network.outposts()} if network else {}
        except Exception as error:
            swallowed("drone_hauler.DroneHaulerMixin._outposts_by_id: network.outposts", error)
            return {}

    def _haul_destinations(self, curr_tick):
        """
        Outposts with a Drone Depot and something missing, as dicts
        {"outpost", "outpost_id", "coords", "depots", "need", "buffer",
        "deficits"} (deficits = need + buffer). Home adds raw-ore demand to
        the need tier (larger of request vs ore demand per item, never the
        sum -- both measure a target against the same stock). Destinations on
        stall cooldown are left out.
        """
        self._host.log.start(f"[{self._host.name}] _haul_destinations", level="debug")
        outposts = self._outposts_by_id()
        depots_by_outpost = {}
        for depot in self._host.get_all_drone_depots():
            depots_by_outpost.setdefault(depot.get("outpost_id"), []).append(depot)

        dests = []
        for outpost_id, depots in depots_by_outpost.items():
            outpost = outposts.get(outpost_id)
            if outpost is None:
                continue
            if self._cooling("dest", outpost_id, curr_tick):
                self._host.log.debug(f"haul: '{outpost_id}' on stall cooldown; not a destination this cycle.")
                continue
            need, buffer = logistics_requests.outpost_deficits_tiered(outpost, curr_tick, live=True)
            if getattr(outpost, "is_home", False):
                for item_id, units in get_raw_material_demands().items():
                    if units > need.get(item_id, 0) + buffer.get(item_id, 0):
                        need[item_id] = units
                        buffer.pop(item_id, None)
            need = {i: u for i, u in need.items() if u > 0}
            buffer = {i: u for i, u in buffer.items() if u > 0}
            if need or buffer:
                dests.append({"outpost": outpost, "outpost_id": outpost_id, "coords": depots[0]["coords"], "depots": depots,
                              "need": need, "buffer": buffer, "deficits": self._sum_tiers(need, buffer)})
        self._warn_if_home_has_no_depot(outposts, depots_by_outpost)
        self._host.log.debug(f"[{self._host.name}] haul: destinations with demand: " + (", ".join(f"{d['outpost_id']}=need {d['need']} buffer {d['buffer']}" for d in dests) or "none"))
        self._host.log.end()
        return dests

    @staticmethod
    def _sum_tiers(need, buffer):
        total = dict(need)
        for item_id, units in buffer.items():
            total[item_id] = total.get(item_id, 0) + units
        return total

    def _warn_if_home_has_no_depot(self, outposts, depots_by_outpost):
        """
        Home is only a haul destination if it owns a Drone Depot. A depot next
        to base but inside another outpost doesn't count, so raw-ore demand at
        home (e.g. the standing ore buffer) silently never becomes a job.
        Warns once per run, then keeps the reason in the debug trail.
        """
        home = next((o for o in outposts.values() if getattr(o, "is_home", False)), None)
        if home is None or home.id in depots_by_outpost:
            return
        raw = {i: u for i, u in get_raw_material_demands().items() if u > 0}
        if not raw:
            return
        if not getattr(self, "_home_no_depot_warned", False):
            self._host.log.level("warn").print(f"[{self._host.name}] '{home.id}' needs raw ore {raw} but has no Drone Depot; floating haulers can't deliver there. Depots found at: {sorted(k for k in depots_by_outpost if k) or 'none'}.")
            self._home_no_depot_warned = True
        self._host.log.debug(f"[{self._host.name}] haul: '{home.id}' skipped as destination (no Drone Depot) despite raw-ore demand {raw}.")

    def _drill_sources(self, items, curr_tick):
        """Advertised drills holding any of `items` with a known position, net of other haulers' reservations."""
        positions = drill_sites.known_positions()
        if not hasattr(self, "_unlocated_drills_warned"):
            self._unlocated_drills_warned = set()
        sources = []
        for drill_id, entry in drill_sites.advertised_drills(curr_tick).items():
            taken = logistics_requests.reserved_from(drill_id, curr_tick, exclude_vehicle=self._host.name)
            available = {}
            for item_id, units in (entry.get("items") or {}).items():
                free = int(units - taken.get(item_id, 0))
                if item_id in items and free > 0:
                    available[item_id] = free
            if not available:
                continue
            coords = drill_sites.position_of(drill_id, positions)
            if not coords:
                if drill_id not in self._unlocated_drills_warned:
                    self._host.log.level("warn").print(f"[{self._host.name}] Drill '{drill_id}' holds {available} but its position is unknown; seed drill.positions to include it.")
                    self._unlocated_drills_warned.add(drill_id)
                continue
            sources.append({"kind": "drill", "id": drill_id, "coords": (float(coords[0]), float(coords[1])), "available": available})
        self._host.log.debug(f"[{self._host.name}] haul: {len(sources)} drill(s) hold wanted items: " + ", ".join(f"{s['id']}={s['available']}" for s in sources))
        return sources

    def _outpost_sources(self, items, curr_tick):
        """
        Drone Depot outposts holding free stock of `items` (Warehouses,
        Depot stockpiles, Inventory at home -- logistics_requests.
        outpost_free_tiers(include_depots=True)), net of other haulers'
        reservations. "available" is what another outpost's need may take,
        "available_buffer" what a buffer top-up may take. Outposts on stall
        cooldown are left out.
        """
        self._host.log.start(f"[{self._host.name}] _outpost_sources", level="debug")
        outposts = self._outposts_by_id()
        depots_by_outpost = {}
        for depot in self._host.get_all_drone_depots():
            if depot.get("outpost_id"):
                depots_by_outpost.setdefault(depot["outpost_id"], []).append(depot)
        requests = logistics_requests.active_requests(curr_tick)
        sources = []
        for outpost_id, depots in depots_by_outpost.items():
            outpost = outposts.get(outpost_id)
            if outpost is None:
                continue
            if self._cooling("source", outpost_id, curr_tick):
                self._host.log.debug(f"haul: outpost '{outpost_id}' on stall cooldown; not a source this cycle.")
                continue
            for_need, for_buffer = logistics_requests.outpost_free_tiers(outpost, list(items), requests, curr_tick, exclude_vehicle=self._host.name, include_depots=True)
            if for_need:
                sources.append({"kind": "outpost", "id": outpost_id, "coords": depots[0]["coords"], "available": for_need,
                                "available_buffer": for_buffer, "depots": depots, "outpost": outpost})
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
        `first` (else the nearest useful source): need tier first, then the
        (fair-share capped) buffer tier, largest deficits first per stop, up
        to capacity / HAUL_MAX_STOPS_PER_TRIP, chained stops only when not
        "behind" the destination. Per-item room is `room` ({item_id: units},
        cargo.space_for() read before planning; one material per pod); the
        live load corrects any over-optimism. Pure (no game calls, no
        logging): _candidate_routes() runs it as a lib/atomic.py call.
        Returns [(source, [(item, n), ...]), ...].
        """
        need_left = dict(dest["need"])
        buffer_left = dict(dest["buffer"])
        cap_left = capacity
        pos = start
        pool = [s for s in sources if s["id"] != dest["outpost_id"]]
        route = []
        while pool and cap_left > 0 and len(route) < HAUL_MAX_STOPS_PER_TRIP:
            if route:
                useful = [s for s in pool if logistics_requests.source_useful(s, need_left, buffer_left, cap_left)
                          and self._chain_worthwhile(pos, s["coords"], dest["coords"])]
            elif first is not None:
                useful = [s for s in pool if s["id"] == first["id"] and logistics_requests.source_useful(s, need_left, buffer_left, cap_left)]
            else:
                useful = [s for s in pool if logistics_requests.source_useful(s, need_left, buffer_left, cap_left)]
            if not useful:
                break
            source = min(useful, key=lambda s: self._host.distance_between(pos, s["coords"]))
            pool = [s for s in pool if s["id"] != source["id"]]
            loads = []
            order = sorted(source["available"], key=lambda i: (-need_left.get(i, 0), -buffer_left.get(i, 0)))
            for item_id in order:
                need, buffer = logistics_requests.plan_take(source, item_id, need_left, buffer_left, min(cap_left, room.get(item_id, 0)))
                amount = need + buffer
                if amount <= 0:
                    continue
                loads.append((item_id, amount))
                need_left[item_id] = need_left.get(item_id, 0) - need
                buffer_left[item_id] = buffer_left.get(item_id, 0) - buffer
                cap_left -= amount
                if cap_left <= 0:
                    break
            if loads:
                route.append((source, loads))
                pos = source["coords"]
        return route

    @staticmethod
    def _need_units(dest, route):
        """Units of `route` that fill dest's need tier (planning takes need before buffer per item)."""
        planned = {}
        for _s, loads in route:
            for item_id, n in loads:
                planned[item_id] = planned.get(item_id, 0) + n
        return sum(min(n, dest["need"].get(i, 0)) for i, n in planned.items())

    def _cap_buffers(self, dests, sources, curr_tick):
        """Caps each destination's buffer tier at its fair share of what the other sources hold (fair_buffer_caps())."""
        for dest in dests:
            if not dest["buffer"]:
                continue
            supply = {}
            for s in sources:
                if s["id"] == dest["outpost_id"]:
                    continue
                for item_id, units in s.get("available_buffer", s["available"]).items():
                    if item_id in dest["buffer"]:
                        supply[item_id] = supply.get(item_id, 0) + units
            caps = logistics_requests.fair_buffer_caps(dest["outpost_id"], dest["buffer"], supply, curr_tick)
            dest["buffer"] = {i: u for i, u in caps.items() if u > 0}
            dest["deficits"] = self._sum_tiers(dest["need"], dest["buffer"])

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
            swallowed("drone_hauler.DroneHaulerMixin._item_room: self._host.drone.cargo.space_for", error)
            return 0

    def _haul_candidate(self, dest, sources, capacity, start, first, room, services, rates):
        """
        _plan_route_for() plus its measures: {"route", "units", "need_units",
        "meters", "fuel"} (fuel per _route_fuel(), start -> stops -> dest).
        Pure; one lib/atomic.py call per candidate.
        """
        route = self._plan_route_for(dest, sources, capacity, start, first, room)
        points = [start] + [s["coords"] for s, _l in route] + [dest["coords"]]
        return {"route": route,
                "units": sum(n for _s, loads in route for _i, n in loads),
                "need_units": self._need_units(dest, route),
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
        over drills and other Depot outposts and rank it by need-tier units,
        then all units, per (route meters + HAUL_TRIP_OVERHEAD_M)
        (logistics_requests.haul_rank()). Jobs not flyable even on a full tank are
        dropped; the caller refuels first when the chosen job needs more
        than is aboard.
        Returns {"dest", "route", "units", "fuel"}.
        """
        self._host.log.start(f"[{self._host.name}] _plan_haul_job", level="debug")
        seen = logistics_requests.pickups_snapshot()  # before any demand/stock read; see claim_pickups()
        dests = self._haul_destinations(curr_tick)
        if not dests:
            self._host.log.end()
            return None
        items = set()
        for dest in dests:
            items.update(dest["deficits"].keys())
        sources = self._drill_sources(items, curr_tick) + self._outpost_sources(items, curr_tick)
        if not sources:
            self._host.log.end()
            return None
        self._cap_buffers(dests, sources, curr_tick)

        try:
            capacity = self._host.drone.cargo.capacity() - self._host.drone.cargo.count()
        except Exception as error:
            swallowed("drone_hauler.DroneHaulerMixin._plan_haul_job: self._host.drone.cargo.capacity", error)
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
            route, units, need_units, meters, fuel = (candidate["route"], candidate["units"], candidate["need_units"],
                                                       candidate["meters"], candidate["fuel"])
            wanted = min(HAUL_MIN_LOAD_UNITS, reachable[dest["outpost_id"]])
            if not route or units < wanted or units <= 0:
                self._host.log.debug(f"haul: '{dest['outpost_id']}' via {[s['id'] for s, _l in route]}: {units} unit(s) < minimum {wanted}; skipped.")
                continue
            if fuel > full_tank:
                self._host.log.debug(f"haul: '{dest['outpost_id']}' needs {fuel:.1f} {self._host.energy_unit()} > full tank {full_tank:.1f}; out of range.")
                continue
            rank = logistics_requests.haul_rank(units, need_units, meters, HAUL_TRIP_OVERHEAD_M)
            self._host.log.debug(f"haul: candidate -> '{dest['outpost_id']}' via {[s['id'] for s, _l in route]}: {units} unit(s) ({need_units} need), {meters:.0f} m, fuel {fuel:.1f} {self._host.energy_unit()}, need rate {rank[0]:.4f}, rate {rank[1]:.3f}.")
            if logistics_requests.rank_beats(rank, best_rank):
                best, best_rank = {"dest": dest, "route": route, "units": units, "wanted": wanted, "fuel": fuel, "seen": seen}, rank
        self._host.log.end()
        return best

    # ------------------------------------------------------------ reservations / mission

    def _yield_key(self, item_id):
        return f"haul:{self._host.name}:{item_id}"

    def _reserve_yield(self, dest_outpost, totals, curr_tick):
        """Debits home-bound ore from raw-ore demand (mining.reserved_yield), like the pull hauler."""
        if not getattr(dest_outpost, "is_home", False):
            return
        for item_id, units in totals.items():
            if units > 0:
                mining_reservations.reserve_yield(self._host.name, self._yield_key(item_id), item_id, units, curr_tick)
            else:
                mining_reservations.release_yield(self._host.name, self._yield_key(item_id))

    def _release_all(self):
        logistics_requests.release_pickups(self._host.name)
        mining_reservations.release_yield(self._host.name)
        depot_stage.clear_stage(self._host.name)

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

    def _save_haul_mission(self, dest_outpost_id):
        # No target_key: load_mission() (biosite claims) ignores this record.
        archive.set_entry(MISSION_KEY, self._host.name, {"kind": "haul", "target_key": None, "dest": dest_outpost_id, "tick": self._host.get_current_tick()})

    def _saved_haul_dest(self):
        record = self._host._read_mission()
        if record and record.get("kind") == "haul":
            return record.get("dest")
        return None

    def _cargo_contents(self):
        try:
            return {i: int(n) for i, n in dict(self._host.drone.cargo.contents()).items() if n > 0}
        except Exception as error:
            swallowed("drone_hauler.DroneHaulerMixin._cargo_contents: dict(self._host.drone.cargo.contents()).items", error)
            return {}

    # ------------------------------------------------------------ service stations

    def _docked_at_service(self):
        station = self._host.current_station()
        return bool(station) and any(s["id"] == station for s in self._host.get_all_drone_services())

    def _idle(self, reason):
        """
        Nothing to do: stay docked if already at a drone_service, fly to one
        only below LAUNCH_MIN_SOC, else leave any Depot bay and hover in place.
        """
        if self._docked_at_service():
            self._host.publish_telemetry("IDLE", reason)
            return
        _, _, frac = self._host.get_battery()
        if frac < self._host.LAUNCH_MIN_SOC:
            self._host.publish_telemetry("IDLE", reason)
            self._go_to_nearest_service(f"{reason}, {frac*100:.0f}% charge")
            return
        self._host.log.debug(f"[{self._host.name}] {reason}; hovering in place ({frac*100:.0f}% charge).")
        self._host.hover_wait("IDLE", reason)

    def _go_to_nearest_service(self, reason):
        """Docks at the nearest (engine-suitable) drone_service unless already docked at one. False if none/unreachable."""
        if self._docked_at_service():
            return True
        coords, info = self._host.get_nearest_drone_service()
        service_id = info.get("id")
        if not service_id:
            self._host.log.level("warn").print(f"[{self._host.name}] {reason}, but no drone_service_station is deployed.")
            return False
        self._host.log.debug(f"[{self._host.name}] {reason}; heading to drone_service '{service_id}'.")
        return self._host.fly_to_station(service_id, target_coords=coords)

    def _refuel(self, needed, reason):
        """Refuels at a drone_service inside a log block; see _refuel_at_service()."""
        self._host.log.start(f"[{self._host.name}] Refuelling: {reason}")
        ok = self._refuel_at_service(needed, reason)
        self._host.log.end("refuelled" if ok else "not refuelled")
        return ok

    def _refuel_at_service(self, needed, reason):
        """
        Flies to the nearest drone_service and waits while its station
        script charges/refuels this drone, until full (REFUEL_FULL_LEVEL) or
        at least `needed` with the service job finished. False on timeout or
        when no service is reachable.
        """
        self._host.publish_telemetry("REFUELING", reason)
        if not self._go_to_nearest_service(reason):
            return False
        waited = 0.0
        warned_oil = False
        while waited < REFUEL_TIMEOUT_S:
            level, _cap, frac = self._host.get_battery()
            status = self._host.status()
            if frac >= REFUEL_FULL_LEVEL or (level >= needed and status not in ("charging", "refueling", "waiting_service")):
                self._host.log.debug(f"[{self._host.name}] Refuel done: {level:.1f} {self._host.energy_unit()} ({frac*100:.0f}%), status={status}.")
                return True
            if status == "waiting_oil" and not warned_oil:
                self._host.log.level("warn").print(f"[{self._host.name}] Service station has no oil; waiting.")
                warned_oil = True
            flush_all()
            sleep(2.0)
            waited += 2.0
        self._host.log.level("warn").print(f"[{self._host.name}] Refuel timed out after {REFUEL_TIMEOUT_S:.0f}s.")
        return False

    # ------------------------------------------------------------ legs

    def _load_at_drill(self, source, loads, dest_id, curr_tick):
        """Flies to one drill and loads; returns {item: moved}, or None if unreachable. Corrects reservations to what loaded."""
        self._host.log.start(f"[{self._host.name}] _load_at_drill", level="debug")
        self._host.publish_telemetry("OUTBOUND", f"pickup at drill '{source['id']}'")
        if not self._host.fly_to_drill(source["id"], target_coords=source["coords"]):
            self._host.log.level("warn").print(f"[{self._host.name}] Could not reach drill '{source['id']}'.")
            self._host.log.end()
            return None
        moved_by_item = {}
        for item_id, amount in loads:
            want = min(amount, self._item_room(item_id))
            moved = 0
            if want > 0:
                try:
                    res = self._host.drone.cargo.load(item_id, want)
                    moved = int(getattr(res, "moved", 0) or 0)
                    if res.status not in ("ok", "partial"):
                        self._host.log.debug(f"load {item_id} at '{source['id']}': {res.status} - {res.message}")
                except Exception as e:
                    self._host.log.debug(f"load {item_id} at '{source['id']}' raised: {e}")
            self._host.log.print(f"[{self._host.name}] Loaded {moved}/{amount}x {item_id} at drill '{source['id']}'.")
            logistics_requests.reserve_pickup(self._host.name, dest_id, item_id, moved, curr_tick, source_id=source["id"])
            moved_by_item[item_id] = moved_by_item.get(item_id, 0) + moved
        self._host.log.end()
        return moved_by_item

    def _dock_at_depot(self, candidates, prefer=None):
        """
        Docks at a free Depot among candidates (waiting up to DEPOT_BAY_WAIT_S
        in "waiting_bay"). Returns the depot dict, or None.
        """
        waited = 0.0
        while True:
            depot = self._host._pick_free_depot(candidates, prefer_id=prefer)
            prefer = depot["id"]
            if self._host.current_station() == depot["id"] or self._host.fly_to_station(depot["id"], target_coords=depot["coords"]):
                return depot
            if self._host.status() != "waiting_bay" or waited >= DEPOT_BAY_WAIT_S:
                self._host.log.level("warn").print(f"[{self._host.name}] Could not dock at Drone Depot '{depot['id']}' (status {self._host.status()}).")
                return None
            flush_all()
            sleep(DEPOT_UNLOAD_RETRY_S)
            waited += DEPOT_UNLOAD_RETRY_S

    def _stage_depot_for(self, source):
        """The Depot of an outpost source to load at: the one holding most of what's planned, else a free one."""
        if len(source["depots"]) == 1:
            return source["depots"][0]
        planned = [i for i in source["available"]]
        best, best_units = None, 0
        for depot in source["depots"]:
            comp = get_component(depot["id"])
            stock = logistics_requests.depot_stock(comp) if comp else {}
            units = sum(stock.get(i, 0) for i in planned)
            if units > best_units:
                best, best_units = depot, units
        return best or self._host._pick_free_depot(source["depots"])

    def _load_at_depot(self, source, loads, dest_id, curr_tick):
        """
        Docks at the source outpost's staged Depot and loads in rounds while
        drone_depot.py stages more from storage (the stage request shrinks
        to what is still missing after each round). Stops when done, after
        DOCK_IDLE_MAX_S without progress, or DEPOT_LOAD_TIMEOUT_S overall.
        Returns {item: moved}, or None if no Depot could be docked at.
        Corrects reservations to what loaded, clears the stage request and
        leaves the bay.
        """
        self._host.log.start(f"[{self._host.name}] _load_at_depot", level="debug")
        depot = getattr(self, "_leg_depots", {}).get(source["id"]) or self._stage_depot_for(source)
        self._host.publish_telemetry("OUTBOUND", f"pickup at Depot '{depot['id']}' ({source['id']})")
        docked = self._dock_at_depot(source["depots"], prefer=depot["id"])
        if docked is None:
            self._note_failure("source", source["id"], "could not dock")
            self._host.log.end()
            return None
        if docked["id"] != depot["id"]:
            for item_id, amount in loads:
                depot_stage.request_stage(depot["id"], self._host.name, item_id, 0, curr_tick)
                depot_stage.request_stage(docked["id"], self._host.name, item_id, amount, curr_tick)
            depot = docked

        remaining = {i: a for i, a in loads}
        moved_by_item = {}
        waited = idle = 0.0
        while remaining and waited < DEPOT_LOAD_TIMEOUT_S and idle < DOCK_IDLE_MAX_S:
            moved_round = 0
            for item_id in list(remaining.keys()):
                want = min(remaining[item_id], self._item_room(item_id))
                if want <= 0:
                    self._host.log.debug(f"load {item_id} at '{depot['id']}': no cargo room left for it.")
                    remaining.pop(item_id)
                    continue
                moved = 0
                try:
                    res = self._host.drone.cargo.load(item_id, want)
                    moved = int(getattr(res, "moved", 0) or 0)
                    if res.status not in ("ok", "partial"):
                        self._host.log.trace(f"load {item_id} at '{depot['id']}': {res.status} - {res.message}")
                except Exception as e:
                    self._host.log.debug(f"load {item_id} at '{depot['id']}' raised: {e}")
                if moved:
                    moved_round += moved
                    moved_by_item[item_id] = moved_by_item.get(item_id, 0) + moved
                    remaining[item_id] -= moved
                    depot_stage.request_stage(depot["id"], self._host.name, item_id, remaining[item_id], self._host.get_current_tick())
                    if remaining[item_id] <= 0:
                        remaining.pop(item_id)
            if not remaining:
                break
            idle = 0.0 if moved_round else idle + DEPOT_UNLOAD_RETRY_S
            flush_all()
            sleep(DEPOT_UNLOAD_RETRY_S)
            waited += DEPOT_UNLOAD_RETRY_S

        for item_id, amount in loads:
            logistics_requests.reserve_pickup(self._host.name, dest_id, item_id, moved_by_item.get(item_id, 0), curr_tick, source_id=source["id"])
        depot_stage.clear_stage(self._host.name, depot["id"])
        total = sum(moved_by_item.values())
        self._host.log.print(f"[{self._host.name}] Loaded {moved_by_item} at Depot '{depot['id']}' ({source['id']})" + (f"; {remaining} not staged in time." if remaining else "."))
        if total > 0:
            self._note_success("source", source["id"])
        else:
            self._note_failure("source", source["id"], "nothing loaded")
        self._host.leave_station()
        self._host.log.end()
        return moved_by_item

    def _pick_delivery_outpost(self, contents):
        """
        Where cargo already aboard goes (resume after a reload or a failed
        delivery): the saved mission's outpost if it still has a Depot, else
        the Depot outpost with the most demand for what's aboard, else home,
        else the nearest Depot.
        """
        depots = self._host.get_all_drone_depots()
        tick = self._host.get_current_tick()
        depot_outposts = {d.get("outpost_id") for d in depots if not self._cooling("dest", d.get("outpost_id"), tick)}
        saved = self._saved_haul_dest()
        if saved in depot_outposts:
            return saved
        best, best_units = None, 0
        for dest in self._haul_destinations(self._host.get_current_tick()):
            units = sum(min(n, dest["deficits"].get(i, 0)) for i, n in contents.items())
            if units > best_units:
                best, best_units = dest["outpost_id"], units
        if best:
            return best
        home = next((o for o in self._outposts_by_id().values() if getattr(o, "is_home", False)), None)
        if home is not None and home.id in depot_outposts:
            return home.id
        _, nearest = self._host.get_nearest_drone_depot()
        nearest_id = nearest.get("outpost_id") or None
        return nearest_id if nearest_id in depot_outposts else None

    def _deliver(self, dest_id):
        """
        Docks at a free Depot of dest_id and unloads in rounds while the
        Depot controller drains to storage. True when cargo is empty. Gives
        up after DOCK_IDLE_MAX_S without progress or DEPOT_UNLOAD_TIMEOUT_S
        overall: the cargo stays aboard (reservations and mission kept), the
        drone leaves the bay reporting WAITING_DEPOT_SPACE for that Depot
        (so it may flush surplus), and the failure counts towards dest_id's
        stall cooldown.
        """
        candidates = [d for d in self._host.get_all_drone_depots() if d.get("outpost_id") == dest_id]
        if not candidates:
            self._host.log.level("warn").print(f"[{self._host.name}] No Drone Depot at '{dest_id}' to deliver to.")
            return False

        self._host.publish_telemetry("DELIVERING", f"to '{dest_id}'")
        depot = self._dock_at_depot(candidates)
        if depot is None:
            self._note_failure("dest", dest_id, "could not dock")
            return False

        self._host.log.start(f"[{self._host.name}] Unloading at '{depot['id']}' ({dest_id})")
        delivered = {}
        waited = idle = 0.0
        while waited < DEPOT_UNLOAD_TIMEOUT_S and idle < DOCK_IDLE_MAX_S:
            contents = self._cargo_contents()
            if not contents:
                break
            moved_round = 0
            for item_id, count in contents.items():
                try:
                    res = self._host.drone.cargo.unload(item_id, count)
                    moved = int(getattr(res, "moved", 0) or 0)
                except Exception as e:
                    self._host.log.debug(f"[{self._host.name}] unload {item_id} raised: {e}")
                    moved = 0
                if moved:
                    delivered[item_id] = delivered.get(item_id, 0) + moved
                    moved_round += moved
            if moved_round == 0:
                self._host.log.trace(f"[{self._host.name}] Depot stockpile full; waiting for it to drain ({idle:.0f}s idle).")
                idle += DEPOT_UNLOAD_RETRY_S
            else:
                idle = 0.0
            flush_all()
            sleep(DEPOT_UNLOAD_RETRY_S)
            waited += DEPOT_UNLOAD_RETRY_S
        left = self._cargo_contents()
        self._host.log.end(f"[{self._host.name}] Delivered {delivered} to '{dest_id}'" + (f"; {left} still aboard (Depot not draining -- storage full or Depot script not running?)" if left else "."))
        if left:
            self._note_failure("dest", dest_id, f"Depot '{depot['id']}' took no more after {idle:.0f}s")
            self._host.hover_wait("WAITING_DEPOT_SPACE", depot["id"])
            return False

        self._note_success("dest", dest_id)
        self._release_all()
        self._host.clear_mission()
        self._host.set_intent(None)
        # Docked and empty: the one moment couple()/uncouple() can run.
        self._host.maintain_modules_at_depot()
        self._host.leave_station()
        self._host.log.debug(f"[{self._host.name}] Delivery to '{dest_id}' complete; reservations released.")
        return True

    # ------------------------------------------------------------ loop

    def _deliver_cargo_aboard(self, poll_interval):
        contents = self._cargo_contents()
        dest_id = self._pick_delivery_outpost(contents)
        if not dest_id:
            self._host.log.level("warn").print(f"[{self._host.name}] Cargo {contents} aboard but no Drone Depot to deliver to (all on stall cooldown or none deployed).")
            self._host.hover_wait("STUCK_WITH_CARGO")
            flush_all()
            sleep(poll_interval)
            return
        # Re-assert the debits from what's physically aboard (a restart may
        # have lost them; per-drill ones from the trip would double-count).
        curr_tick = self._host.get_current_tick()
        self._release_all()
        for item_id, units in contents.items():
            logistics_requests.reserve_pickup(self._host.name, dest_id, item_id, units, curr_tick)
        self._reserve_yield(self._outposts_by_id().get(dest_id), contents, curr_tick)
        self._save_haul_mission(dest_id)
        self._host.set_intent(fleet_intent.describe("hauling", contents, dest=dest_id, root=fleet_intent.haul_root(contents, dest_id, curr_tick)))
        services = self._host.get_all_drone_services()
        dest_coords = next((d["coords"] for d in self._host.get_all_drone_depots() if d.get("outpost_id") == dest_id), self._host.position())
        needed = self._route_fuel([self._host.position(), dest_coords], services)
        level, _, _ = self._host.get_battery()
        if level < needed and not self._refuel(needed, f"Low fuel for delivery ({level:.1f} < {needed:.1f} {self._host.energy_unit()})"):
            flush_all()
            sleep(poll_interval)
            return
        if not self._deliver(dest_id):
            if self._cooling("dest", dest_id, self._host.get_current_tick()):
                # Requeue at the back: forget the saved destination so the
                # next cycle picks the next-best one for this cargo.
                self._host.clear_mission()
            flush_all()
            sleep(poll_interval)

    def run_hauler_loop(self, poll_interval=5.0):
        """
        Floating hauler main loop: cargo aboard -> deliver; else plan the
        best job (_plan_haul_job()), refuel first if its budget needs it, fly
        the pickups, deliver; nothing to do -> hover in place (_idle()).
        """
        self._host.log.print(f"[{self._host.name}] Floating hauler online ({self._host.engine}, cargo capacity {self._host.cargo_capacity()}).")
        while True:
            reset_all()
            try:
                if self._host.handle_recall_if_active():
                    flush_all()
                    sleep(poll_interval)
                    continue
                if self._host.handle_upgrade_request_if_active():
                    flush_all()
                    sleep(poll_interval)
                    continue
                if self._host.is_stranded() or self._host.drone.is_being_rescued():
                    self._host.publish_telemetry("AWAITING_RESCUE")
                    flush_all()
                    sleep(poll_interval)
                    continue

                if self._cargo_contents():
                    self._deliver_cargo_aboard(poll_interval)
                    continue

                # Launch hysteresis only where it's free: already parked at a
                # service, let the station finish topping up first.
                _, _, frac = self._host.get_battery()
                if self._docked_at_service() and frac < self._host.LAUNCH_MIN_SOC:
                    self._host.log.debug(f"[{self._host.name}] At service with {frac*100:.0f}% < {self._host.LAUNCH_MIN_SOC*100:.0f}% launch floor; waiting for top-up.")
                    self._host.publish_telemetry("REFUELING", "launch floor")
                    flush_all()
                    sleep(poll_interval)
                    continue
                if frac < HAUL_RECHARGE_SOC:
                    self._host.publish_telemetry("REFUELING", "recharge floor")
                    if self._go_to_nearest_service(f"Charge {frac*100:.0f}% < {HAUL_RECHARGE_SOC*100:.0f}% recharge floor"):
                        flush_all()
                        sleep(poll_interval)
                        continue

                curr_tick = self._host.get_current_tick()
                job = self._plan_haul_job(curr_tick)
                if job is None:
                    self._idle("No haul job")
                    flush_all()
                    sleep(poll_interval)
                    continue

                level, _, _ = self._host.get_battery()
                if level < job["fuel"]:
                    self._refuel(job["fuel"], f"Job needs {job['fuel']:.1f} {self._host.energy_unit()}, have {level:.1f}")
                    continue  # re-plan from the service: demand may have moved meanwhile

                self._run_job(job, curr_tick)
            except Exception as error:
                self._host.log.level("error").print(f"[{self._host.name}] Hauler exception: {error}")
            flush_all()
            sleep(poll_interval)

    def _claim_route(self, job, curr_tick):
        """
        Reserves the planned route atomically (logistics_requests.claim_pickups()),
        trimmed by whatever other haulers reserved since planning. Returns the
        route with granted amounts, or None when too little is left to be
        worth the trip (then nothing stays reserved and the next cycle replans).
        """
        self._host.log.start(f"[{self._host.name}] _claim_route", level="debug")
        dest = job["dest"]
        dest_id = dest["outpost_id"]
        legs = [(source["id"], item_id, amount) for source, loads in job["route"] for item_id, amount in loads]
        granted = logistics_requests.claim_pickups(self._host.name, dest_id, legs, job.get("seen", {}), curr_tick)
        grant_by_leg = {(s, i): g for s, i, g in granted}
        route = []
        for source, loads in job["route"]:
            kept = [(i, grant_by_leg.get((source["id"], i), 0)) for i, _n in loads]
            kept = [(i, n) for i, n in kept if n > 0]
            if kept:
                route.append((source, kept))
        units = sum(n for _s, loads in route for _i, n in loads)
        wanted = job.get("wanted", min(HAUL_MIN_LOAD_UNITS, sum(dest["deficits"].values())))
        if units < job["units"]:
            self._host.log.debug(f"haul: another hauler reserved part of this job since planning; {job['units']} -> {units} unit(s).")
        if not route or units < wanted:
            self._host.log.debug(f"haul: {units} unit(s) left after claim < minimum {wanted}; dropping job, replanning next cycle.")
            logistics_requests.release_pickups(self._host.name)
            self._host.log.end()
            return None
        # Outpost pickups: have the source Depot stage the goods while the
        # drone flies there.
        self._leg_depots = {}
        tick = self._host.get_current_tick()
        for source, loads in route:
            if source.get("kind") != "outpost":
                continue
            depot = self._stage_depot_for(source)
            self._leg_depots[source["id"]] = depot
            for item_id, amount in loads:
                depot_stage.request_stage(depot["id"], self._host.name, item_id, amount, tick)
            self._host.log.debug(f"haul: staging {loads} at Depot '{depot['id']}' ({source['id']}).")
        self._host.log.end()
        return route

    def _run_job(self, job, curr_tick):
        dest = job["dest"]
        dest_id = dest["outpost_id"]
        route = self._claim_route(job, curr_tick)
        if not route:
            return
        planned = {}
        legs = []
        for source, loads in route:
            legs.append(source["id"] + " (" + ", ".join(f"{n}x {i}" for i, n in loads) + ")")
            for item_id, amount in loads:
                planned[item_id] = planned.get(item_id, 0) + amount
        self._reserve_yield(dest["outpost"], planned, curr_tick)
        self._save_haul_mission(dest_id)
        source_ids = [source["id"] for source, _loads in route]
        source_label = source_ids[0] + (f" +{len(source_ids) - 1}" if len(source_ids) > 1 else "")
        self._host.set_intent(fleet_intent.describe("hauling", planned, source_label, dest_id, fleet_intent.haul_root(planned, dest_id, curr_tick)))
        self._host.log.start(f"[{self._host.name}] Haul job -> '{dest_id}': " + " -> ".join(legs))

        loaded = {i: 0 for i in planned}
        for index, (source, loads) in enumerate(route):
            if source.get("kind") == "outpost":
                moved = self._load_at_depot(source, loads, dest_id, curr_tick)
            else:
                moved = self._load_at_drill(source, loads, dest_id, curr_tick)
            if moved is None:
                for later, later_loads in route[index:]:
                    for item_id, _n in later_loads:
                        logistics_requests.reserve_pickup(self._host.name, dest_id, item_id, 0, curr_tick, source_id=later["id"])
                break
            for item_id, n in moved.items():
                loaded[item_id] = loaded.get(item_id, 0) + n
        self._reserve_yield(dest["outpost"], loaded, curr_tick)
        total = sum(loaded.values())
        self._host.log.end(f"[{self._host.name}] Pickups done: {total} unit(s) aboard.")

        if total <= 0:
            self._release_all()
            self._host.clear_mission()
            self._host.set_intent(None)
            return
        self._deliver(dest_id)
