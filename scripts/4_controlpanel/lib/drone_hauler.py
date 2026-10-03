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
# Planning (demand, sources, route scoring, stall cooldowns) lives in
# lib/drone_haul_plan.py DroneHaulPlanMixin; this mixin flies the job it
# picks: claim, load, deliver, refuel, idle.
#
# The Depot controller (lib/drone_depot.py drain_freight()) drains unloaded
# freight into local storage while the drone unloads in rounds.
#
# Between haul jobs the hauler also collects Storm Glass aftermaths
# (lib/drone_weather.py try_aftermath_pickup()) and delivers the glass like
# any other cargo aboard.

import logistics_requests
import depot_stage
import fleet_intent
from archive import archive
from drone_claims import MISSION_KEY
from drone_haul_plan import HAUL_MIN_LOAD_UNITS
from swallow import swallowed
from script_parking import wake_for_visit
from typing import TYPE_CHECKING
from tree_console import flush_all, reset_all

if TYPE_CHECKING:
    from drone import DroneController

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

    # ------------------------------------------------------------ reservations / mission

    def _release_all(self):
        logistics_requests.release_pickups(self._host.name)
        depot_stage.clear_stage(self._host.name)

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
        wake_for_visit(service_id, f"{self._host.name} refuelling")
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
            if int(waited) % 30 == 0:
                wake_for_visit(self._host.current_station(), f"{self._host.name} refuelling")
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
            want = min(amount, self._host._item_room(item_id))
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
            logistics_requests.reserve_pickup(self._host.name, dest_id, item_id, moved, curr_tick, source_id=source["id"], aboard=True)
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
            self._host._note_failure("source", source["id"], "could not dock")
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
                want = min(remaining[item_id], self._host._item_room(item_id))
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
            logistics_requests.reserve_pickup(self._host.name, dest_id, item_id, moved_by_item.get(item_id, 0), curr_tick, source_id=source["id"], aboard=True)
        depot_stage.clear_stage(self._host.name, depot["id"])
        total = sum(moved_by_item.values())
        self._host.log.print(f"[{self._host.name}] Loaded {moved_by_item} at Depot '{depot['id']}' ({source['id']})" + (f"; {remaining} not staged in time." if remaining else "."))
        if total > 0:
            self._host._note_success("source", source["id"])
        else:
            self._host._note_failure("source", source["id"], "nothing loaded")
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
        depot_outposts = {d.get("outpost_id") for d in depots if not self._host._cooling("dest", d.get("outpost_id"), tick)}
        saved = self._saved_haul_dest()
        if saved in depot_outposts:
            return saved
        best, best_units = None, 0
        for dest in self._host._haul_destinations(self._host.get_current_tick()):
            units = sum(min(n, dest["deficits"].get(i, 0)) for i, n in contents.items())
            if units > best_units:
                best, best_units = dest["outpost_id"], units
        if best:
            return best
        home = next((o for o in self._host._outposts_by_id().values() if getattr(o, "is_home", False)), None)
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
            self._host._note_failure("dest", dest_id, "could not dock")
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
            self._host._note_failure("dest", dest_id, f"Depot '{depot['id']}' took no more after {idle:.0f}s")
            self._host.hover_wait("WAITING_DEPOT_SPACE", depot["id"])
            return False

        self._host._note_success("dest", dest_id)
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
            logistics_requests.reserve_pickup(self._host.name, dest_id, item_id, units, curr_tick, aboard=True)
        self._save_haul_mission(dest_id)
        self._host.set_intent(fleet_intent.describe("hauling", contents, dest=dest_id, root=fleet_intent.haul_root(contents, dest_id, curr_tick)))
        services = self._host.get_all_drone_services()
        dest_coords = next((d["coords"] for d in self._host.get_all_drone_depots() if d.get("outpost_id") == dest_id), self._host.position())
        needed = self._host._route_fuel([self._host.position(), dest_coords], services)
        level, _, _ = self._host.get_battery()
        if level < needed and not self._refuel(needed, f"Low fuel for delivery ({level:.1f} < {needed:.1f} {self._host.energy_unit()})"):
            flush_all()
            sleep(poll_interval)
            return
        if not self._deliver(dest_id):
            if self._host._cooling("dest", dest_id, self._host.get_current_tick()):
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

                # Storm Glass aftermaths (lib/drone_weather.py): one about to
                # expire beats a haul job; any other only fills idle time.
                if self._host.try_aftermath_pickup(urgent_only=True):
                    continue
                curr_tick = self._host.get_current_tick()
                job = self._host._plan_haul_job(curr_tick)
                if job is None:
                    if self._host.try_aftermath_pickup(urgent_only=False):
                        continue
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
        total = sum(loaded.values())
        self._host.log.end(f"[{self._host.name}] Pickups done: {total} unit(s) aboard.")

        if total <= 0:
            self._release_all()
            self._host.clear_mission()
            self._host.set_intent(None)
            return
        self._deliver(dest_id)
