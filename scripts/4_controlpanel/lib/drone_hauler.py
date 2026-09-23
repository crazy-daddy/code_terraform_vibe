# Drone role: floating freight hauler (phase 1: field Mining Drills -> Drone
# Depots). Detected when a drone carries Cargo Pods but no bio module (see
# DroneController.detect_role()).
#
# "Floating": no home Depot. Every cycle the drone picks the best job
# network-wide -- which outpost (with a Drone Depot) needs what, and which
# field drills hold it -- flies there, loads straight from the drill(s),
# delivers to that outpost's Depot, and moves on. It refuels at whichever
# drone_service_station is nearest when a job's fuel budget demands it, and
# parks at the nearest one when there is nothing to do (never holds a Depot
# bay while idle).
#
# Why drills only for now: cargo.load() works only at a docked Drone Depot or
# a field Mining Drill, cargo.unload() only into a docked Depot (drone.md,
# DroneCargo). A drill needs no staging; an outpost pickup needs its Depot to
# pull the items out of storage first -- phase 2 (see TODO.md).
#
# Demand and coordination are shared with the Pioneer pull hauler
# (lib/vehicle_cargo.py run_pull_loop()), so the two never both serve the
# same deficit:
#   - demand per outpost: logistics_requests.outpost_deficits() (net of
#     in-flight logistics.pickups), plus get_raw_material_demands() at home
#     (net of mining.reserved_yield);
#   - planned units reserved per drill (logistics.pickups "source") and, for
#     home-bound ore, debited from mining.reserved_yield.
# The Depot controller (lib/drone_depot.py drain_freight()) drains unloaded
# freight into local storage while the drone unloads in rounds.

import logistics_requests
import mining_reservations
import drill_sites
from archive import archive
from production import get_raw_material_demands
from drone_claims import MISSION_KEY
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
# Unloading into a small Depot stockpile happens in rounds while
# drone_depot.py drains it; give up (keep cargo, retry later) after this.
DEPOT_UNLOAD_TIMEOUT_S = 300.0
DEPOT_UNLOAD_RETRY_S = 2.0
# Waiting at a Depot whose bays are all taken.
DEPOT_BAY_WAIT_S = 60.0
# Refuel/charge wait at a drone_service before giving up for this cycle.
REFUEL_TIMEOUT_S = 900.0
REFUEL_FULL_LEVEL = 0.98


class DroneHaulerMixin:

    @property
    def _host(self) -> "DroneController":
        return self  # type: ignore[return-value]

    # ------------------------------------------------------------ demand / sources

    def _outposts_by_id(self):
        network = get_component("outpost_network")
        try:
            return {o.id: o for o in network.outposts()} if network else {}
        except Exception:
            return {}

    def _haul_destinations(self, curr_tick):
        """
        Outposts with a Drone Depot and something missing, as dicts
        {"outpost", "outpost_id", "coords", "depots", "deficits"}. Home adds
        raw-ore demand (larger of request vs ore demand per item, never the
        sum -- both measure a target against the same stock).
        """
        outposts = self._outposts_by_id()
        depots_by_outpost = {}
        for depot in self._host.get_all_drone_depots():
            depots_by_outpost.setdefault(depot.get("outpost_id"), []).append(depot)

        dests = []
        for outpost_id, depots in depots_by_outpost.items():
            outpost = outposts.get(outpost_id)
            if outpost is None:
                continue
            deficits = logistics_requests.outpost_deficits(outpost, curr_tick, live=True)
            if getattr(outpost, "is_home", False):
                for item_id, units in get_raw_material_demands().items():
                    if units > deficits.get(item_id, 0):
                        deficits[item_id] = units
            deficits = {i: u for i, u in deficits.items() if u > 0}
            if deficits:
                dests.append({"outpost": outpost, "outpost_id": outpost_id, "coords": depots[0]["coords"], "depots": depots, "deficits": deficits})
        self._host.log.debug(f"[{self._host.name}] haul: destinations with demand: " + (", ".join(f"{d['outpost_id']}={d['deficits']}" for d in dests) or "none"))
        return dests

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
            sources.append({"id": drill_id, "coords": (float(coords[0]), float(coords[1])), "available": available})
        self._host.log.debug(f"[{self._host.name}] haul: {len(sources)} drill(s) hold wanted items: " + ", ".join(f"{s['id']}={s['available']}" for s in sources))
        return sources

    # ------------------------------------------------------------ planning

    def _nearest_service_dist(self, coords, services):
        if not services:
            return 0.0
        return min(self._host.distance_between(coords, s["coords"]) for s in services)

    def _route_fuel(self, points, services):
        """
        Fuel (Wh / t Oil) for flying `points` in order at cruise throttle,
        plus reaching the nearest drone_service from the last point at the
        speedmode floor, with safety margin and emergency reserve -- the
        floating hauler's "there-and-back": "back" is any service, not home.
        """
        legs = sum(self._host.distance_between(points[i], points[i + 1]) for i in range(len(points) - 1))
        tail = self._nearest_service_dist(points[-1], services)
        fuel = legs * self._host.wh_per_meter_at_throttle(self._host.cruise_throttle) + tail * self._host.minimum_wh_per_meter()
        return fuel * self._host.SAFETY_MARGIN_MULTIPLIER + self._host.emergency_reserve()

    def _chain_worthwhile(self, prev_coords, coords, dest_coords):
        direct = self._host.distance_between(prev_coords, coords)
        via_dest = self._host.distance_between(prev_coords, dest_coords) + self._host.distance_between(dest_coords, coords)
        return via_dest > 0 and direct <= HAUL_CHAIN_MAX_DETOUR_RATIO * via_dest

    def _plan_route_for(self, dest, sources, capacity, start):
        """
        Greedy nearest-neighbour drill route for one destination: largest
        deficits first per stop, up to capacity / HAUL_MAX_STOPS_PER_TRIP,
        chained stops only when not "behind" the destination. Per-item room
        is capped by cargo.space_for() (one material per pod); the live
        load corrects any over-optimism. Returns [(source, [(item, n), ...]), ...].
        """
        remaining = dict(dest["deficits"])
        cap_left = capacity
        pos = start
        pool = list(sources)
        route = []
        while pool and cap_left > 0 and len(route) < HAUL_MAX_STOPS_PER_TRIP:
            useful = [s for s in pool if any(remaining.get(i, 0) > 0 for i in s["available"])]
            if route:
                useful = [s for s in useful if self._chain_worthwhile(pos, s["coords"], dest["coords"])]
            if not useful:
                break
            source = min(useful, key=lambda s: self._host.distance_between(pos, s["coords"]))
            pool = [s for s in pool if s["id"] != source["id"]]
            loads = []
            for item_id in sorted(source["available"], key=lambda i: -remaining.get(i, 0)):
                room = min(cap_left, self._item_room(item_id))
                amount = min(remaining.get(item_id, 0), source["available"][item_id], room)
                if amount <= 0:
                    continue
                loads.append((item_id, amount))
                remaining[item_id] -= amount
                cap_left -= amount
                if cap_left <= 0:
                    break
            if loads:
                route.append((source, loads))
                pos = source["coords"]
        return route

    def _item_room(self, item_id):
        try:
            return int(self._host.drone.cargo.space_for(item_id))
        except Exception:
            return 0

    def _plan_haul_job(self, curr_tick):
        """
        Best job network-wide, or None: for every destination, plan a drill
        route and score units / (route meters + HAUL_TRIP_OVERHEAD_M). Jobs
        not flyable even on a full tank are dropped; the caller refuels
        first when the chosen job needs more than is aboard.
        Returns {"dest", "route", "units", "fuel"}.
        """
        dests = self._haul_destinations(curr_tick)
        if not dests:
            return None
        items = set()
        for dest in dests:
            items.update(dest["deficits"].keys())
        sources = self._drill_sources(items, curr_tick)
        if not sources:
            return None

        try:
            capacity = self._host.drone.cargo.capacity() - self._host.drone.cargo.count()
        except Exception:
            capacity = 0
        if capacity <= 0:
            return None
        services = self._host.get_all_drone_services()
        _, full_tank, _ = self._host.get_battery()
        start = self._host.position()

        best, best_score = None, 0.0
        for dest in dests:
            route = self._plan_route_for(dest, sources, capacity, start)
            units = sum(n for _s, loads in route for _i, n in loads)
            wanted = min(HAUL_MIN_LOAD_UNITS, sum(dest["deficits"].values()))
            if not route or units < wanted:
                self._host.log.debug(f"[{self._host.name}] haul: '{dest['outpost_id']}' plan {units} unit(s) < minimum {wanted}; skipped.")
                continue
            points = [start] + [s["coords"] for s, _l in route] + [dest["coords"]]
            meters = sum(self._host.distance_between(points[i], points[i + 1]) for i in range(len(points) - 1))
            fuel = self._route_fuel(points, services)
            if fuel > full_tank:
                self._host.log.debug(f"[{self._host.name}] haul: '{dest['outpost_id']}' needs {fuel:.1f} {self._host.energy_unit()} > full tank {full_tank:.1f}; out of range.")
                continue
            score = units / (meters + HAUL_TRIP_OVERHEAD_M)
            self._host.log.debug(f"[{self._host.name}] haul: candidate -> '{dest['outpost_id']}' via {[s['id'] for s, _l in route]}: {units} unit(s), {meters:.0f} m, fuel {fuel:.1f} {self._host.energy_unit()}, score {score:.3f}.")
            if score > best_score:
                best, best_score = {"dest": dest, "route": route, "units": units, "fuel": fuel}, score
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
        except Exception:
            return {}

    # ------------------------------------------------------------ service stations

    def _docked_at_service(self):
        station = self._host.current_station()
        return bool(station) and any(s["id"] == station for s in self._host.get_all_drone_services())

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
            sleep(2.0)
            waited += 2.0
        self._host.log.level("warn").print(f"[{self._host.name}] Refuel timed out after {REFUEL_TIMEOUT_S:.0f}s.")
        return False

    # ------------------------------------------------------------ legs

    def _load_at_drill(self, source, loads, dest_id, curr_tick):
        """Flies to one drill and loads; returns {item: moved}, or None if unreachable. Corrects reservations to what loaded."""
        self._host.publish_telemetry("OUTBOUND", f"pickup at drill '{source['id']}'")
        if not self._host.fly_to_drill(source["id"], target_coords=source["coords"]):
            self._host.log.level("warn").print(f"[{self._host.name}] Could not reach drill '{source['id']}'.")
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
                        self._host.log.debug(f"[{self._host.name}] load {item_id} at '{source['id']}': {res.status} - {res.message}")
                except Exception as e:
                    self._host.log.debug(f"[{self._host.name}] load {item_id} at '{source['id']}' raised: {e}")
            self._host.log.print(f"[{self._host.name}] Loaded {moved}/{amount}x {item_id} at drill '{source['id']}'.")
            logistics_requests.reserve_pickup(self._host.name, dest_id, item_id, moved, curr_tick, source_id=source["id"])
            moved_by_item[item_id] = moved_by_item.get(item_id, 0) + moved
        return moved_by_item

    def _pick_delivery_outpost(self, contents):
        """
        Where cargo already aboard goes (resume after a reload or a failed
        delivery): the saved mission's outpost if it still has a Depot, else
        the Depot outpost with the most demand for what's aboard, else home,
        else the nearest Depot.
        """
        depots = self._host.get_all_drone_depots()
        depot_outposts = {d.get("outpost_id") for d in depots}
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
        return nearest.get("outpost_id") or None

    def _deliver(self, dest_id):
        """
        Docks at a free Depot of dest_id and unloads in rounds while the
        Depot controller drains to storage. True when cargo is empty. On
        failure the cargo stays aboard (reservations and mission kept) and
        the next cycle retries.
        """
        candidates = [d for d in self._host.get_all_drone_depots() if d.get("outpost_id") == dest_id]
        if not candidates:
            self._host.log.level("warn").print(f"[{self._host.name}] No Drone Depot at '{dest_id}' to deliver to.")
            return False

        self._host.publish_telemetry("DELIVERING", f"to '{dest_id}'")
        waited = 0.0
        prefer = None
        while True:
            depot = self._host._pick_free_depot(candidates, prefer_id=prefer)
            prefer = depot["id"]
            if self._host.current_station() == depot["id"] or self._host.fly_to_station(depot["id"], target_coords=depot["coords"]):
                break
            if self._host.status() != "waiting_bay" or waited >= DEPOT_BAY_WAIT_S:
                self._host.log.level("warn").print(f"[{self._host.name}] Could not dock at a Drone Depot in '{dest_id}' (status {self._host.status()}).")
                return False
            sleep(DEPOT_UNLOAD_RETRY_S)
            waited += DEPOT_UNLOAD_RETRY_S

        self._host.log.start(f"[{self._host.name}] Unloading at '{depot['id']}' ({dest_id})")
        delivered = {}
        waited = 0.0
        while waited < DEPOT_UNLOAD_TIMEOUT_S:
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
                self._host.log.trace(f"[{self._host.name}] Depot stockpile full; waiting for it to drain ({waited:.0f}s).")
                sleep(DEPOT_UNLOAD_RETRY_S)
                waited += DEPOT_UNLOAD_RETRY_S
        left = self._cargo_contents()
        self._host.log.end(f"[{self._host.name}] Delivered {delivered} to '{dest_id}'" + (f"; {left} still aboard (Depot not draining -- storage full or Depot script not running?)" if left else "."))
        if left:
            self._host.leave_station()
            return False

        self._release_all()
        self._host.clear_mission()
        self._host.leave_station()
        self._host.log.debug(f"[{self._host.name}] Delivery to '{dest_id}' complete; reservations released.")
        return True

    # ------------------------------------------------------------ loop

    def _deliver_cargo_aboard(self, poll_interval):
        contents = self._cargo_contents()
        dest_id = self._pick_delivery_outpost(contents)
        if not dest_id:
            self._host.log.level("warn").print(f"[{self._host.name}] Cargo {contents} aboard but no Drone Depot to deliver to.")
            self._host.publish_telemetry("STUCK_WITH_CARGO")
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
        services = self._host.get_all_drone_services()
        dest_coords = next((d["coords"] for d in self._host.get_all_drone_depots() if d.get("outpost_id") == dest_id), self._host.position())
        needed = self._route_fuel([self._host.position(), dest_coords], services)
        level, _, _ = self._host.get_battery()
        if level < needed and not self._refuel(needed, f"Low fuel for delivery ({level:.1f} < {needed:.1f} {self._host.energy_unit()})"):
            sleep(poll_interval)
            return
        if not self._deliver(dest_id):
            sleep(poll_interval)

    def run_hauler_loop(self, poll_interval=5.0):
        """
        Floating hauler main loop: cargo aboard -> deliver; else plan the
        best drill job (_plan_haul_job()), refuel first if its budget needs
        it, fly the pickups, deliver; nothing to do -> park at the nearest
        drone_service (which also tops the drone up).
        """
        self._host.log.print(f"[{self._host.name}] Floating hauler online ({self._host.engine}, cargo capacity {self._host.cargo_capacity()}).")
        while True:
            try:
                if self._host.handle_recall_if_active():
                    sleep(poll_interval)
                    continue
                if self._host.is_stranded() or self._host.drone.is_being_rescued():
                    self._host.publish_telemetry("AWAITING_RESCUE")
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
                    sleep(poll_interval)
                    continue

                curr_tick = self._host.get_current_tick()
                job = self._plan_haul_job(curr_tick)
                if job is None:
                    self._host.publish_telemetry("IDLE", "no drill job")
                    self._go_to_nearest_service("No haul job")
                    sleep(poll_interval)
                    continue

                level, _, _ = self._host.get_battery()
                if level < job["fuel"]:
                    self._refuel(job["fuel"], f"Job needs {job['fuel']:.1f} {self._host.energy_unit()}, have {level:.1f}")
                    continue  # re-plan from the service: demand may have moved meanwhile

                self._run_job(job, curr_tick)
            except Exception as error:
                self._host.log.level("error").print(f"[{self._host.name}] Hauler exception: {error}")
            sleep(poll_interval)

    def _run_job(self, job, curr_tick):
        dest = job["dest"]
        dest_id = dest["outpost_id"]
        route = job["route"]
        planned = {}
        legs = []
        for source, loads in route:
            legs.append(source["id"] + " (" + ", ".join(f"{n}x {i}" for i, n in loads) + ")")
            for item_id, amount in loads:
                logistics_requests.reserve_pickup(self._host.name, dest_id, item_id, amount, curr_tick, source_id=source["id"])
                planned[item_id] = planned.get(item_id, 0) + amount
        self._reserve_yield(dest["outpost"], planned, curr_tick)
        self._save_haul_mission(dest_id)
        self._host.log.start(f"[{self._host.name}] Haul job -> '{dest_id}': " + " -> ".join(legs))

        loaded = {i: 0 for i in planned}
        for index, (source, loads) in enumerate(route):
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
            return
        self._deliver(dest_id)
