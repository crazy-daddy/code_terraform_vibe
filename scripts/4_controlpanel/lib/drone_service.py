# Shared Library for Drone Service Station (charging/rescue) Management.
# Structural mirror of lib/charging.py's ChargingStationController: docked
# charge queue, fleet-wide stranded/scrambled detection via fleet.drones(),
# rescue dispatch, multi-station nearest-station coordination, power-gating.
# Engine-aware: electric drones are charge()d, heli drones refuel()ed from
# oil_in; floors/targets use each drone's own fuel unit (Wh / t Oil, see
# lib/drone_energy.py ENGINE_PROFILES).
#
# order_return_to_service() calls get_component(drone_id).go_to() from this
# station's script. The game blocks that remote write (PermissionError, see
# docs/AI_CHEATSHEET.md "Remote writes are blocked"), so the nudge does
# nothing and swallowed() records it; same for lib/charging.py's
# order_return_to_station() (nav.set_target()). Rescue dispatch is this
# station's own call and works. See TODO.md.

from drone_energy import discover_drone_services, drone_rescue_energy_per_meter, service_has_oil_feed, heli_capable_services, HELI_MIN_EMERGENCY_RESERVE_T
from tree_console import TreeConsole, flush_all, reset_all
from swallow import swallowed
from script_parking import ParkRequester, parked_ids, parked_nearest, wake_for_visit
from version_guard import validate_game_version

STRANDED_STATUSES = ("stalled_no_battery", "stalled_no_oil", "scrambled")


class DroneServiceController:
    """
    Automates a Drone Service Station.
    - Manages charging queues for docked electric drones.
    - Monitors the entire drone fleet via get_component("fleet").
    - Detects stranded/scrambled drones or low-battery drones in the field
      and auto-dispatches the recovery vehicle, or proactively nudges a
      low-battery field drone home before it needs a full rescue.
    """
    RETURN_SAFETY_MARGIN = 1.05
    # Smaller than ChargingStationController's 8.0 Wh reserves -- electric
    # drone batteries are much smaller than a Rover/Pioneer's (see
    # lib/drone_energy.py's MIN_EMERGENCY_RESERVE_WH note).
    RETURN_EMERGENCY_RESERVE_WH = 2.0
    RESCUE_EXTRA_RESERVE_WH = 2.0
    # Heli equivalents in tons of Oil (tanks are 30/75/150 t).
    RETURN_EMERGENCY_RESERVE_T = HELI_MIN_EMERGENCY_RESERVE_T / 2.0
    RESCUE_EXTRA_RESERVE_T = HELI_MIN_EMERGENCY_RESERVE_T / 2.0
    # Poll cadence: ACTIVE while this station has work (bays charging or queued,
    # a rescue under way, a drone it is responsible for stranded/below floor/
    # heading home); IDLE otherwise.
    ACTIVE_POLL_SECONDS = 1.5
    IDLE_POLL_SECONDS = 5.0

    def __init__(self, station, target_charge_level=1.0):
        self.station = station
        self.name = getattr(station, "id", "drone_service_station")
        self.target_charge_level = target_charge_level
        self.fleet = get_component("fleet")
        self.power = get_component("power_control")
        self.last_rescued_drone = None
        self.nudge_commands = set()
        self._oil_warned = False
        self.log = TreeConsole(module="drone_service")
        self.parker = ParkRequester(self.name, "drone_service_station")

    def all_station_refs(self):
        return discover_drone_services()

    def station_refs_for(self, drone_ref):
        """Stations that can serve drone_ref: all for electric, oil-holding ones for heli (heli_capable_services(), dry skipped)."""
        refs = self.all_station_refs()
        if getattr(drone_ref, "engine", "") == "heli":
            refs, _tier = heli_capable_services(refs)
        return refs

    def my_coords(self):
        for r in self.all_station_refs():
            if r["id"] == self.name:
                return r["coords"]
        return None

    def station_coords(self, drone_ref=None):
        refs = self.station_refs_for(drone_ref) if drone_ref is not None else self.all_station_refs()
        return [r["coords"] for r in refs]

    def is_nearest_station_to(self, drone_ref):
        """
        True when this station is the closest known drone_service_station to
        drone_ref. Every deployed station runs its own independent copy of
        this script and polls the same fleet snapshot, so without this
        check every station within range would dispatch its own recovery
        vehicle to the same stranded drone (mirrors
        ChargingStationController.is_nearest_station_to()). For a heli only
        stations holding oil compete (a dry one never claims it, since its
        rescue would carry the drone into a refuel queue with no oil).
        """
        my_pos = self.my_coords()
        if my_pos is None:
            return True
        candidates = self.station_refs_for(drone_ref)
        if not any(ref["id"] == self.name for ref in candidates):
            return False
        my_dist = ((drone_ref.x - my_pos[0]) ** 2 + (drone_ref.y - my_pos[1]) ** 2) ** 0.5
        for ref in candidates:
            if ref["id"] == self.name:
                continue
            other_dist = ((drone_ref.x - ref["coords"][0]) ** 2 + (drone_ref.y - ref["coords"][1]) ** 2) ** 0.5
            if other_dist < my_dist:
                return False
        return True

    def nearest_service_coords(self, drone_ref):
        stations = self.station_coords(drone_ref)
        if not stations:
            return None
        return min(stations, key=lambda point: ((drone_ref.x - point[0]) ** 2 + (drone_ref.y - point[1]) ** 2) ** 0.5)

    @staticmethod
    def fuel_of(drone_ref):
        """(current, capacity, fraction) from a DroneRef in its own unit: Wh (electric) or t Oil (heli)."""
        if drone_ref.engine == "heli":
            return (drone_ref.oil_tons or 0.0, drone_ref.oil_capacity or 0.0, drone_ref.oil_level or 0.0)
        return (drone_ref.battery_wh or 0.0, drone_ref.battery_capacity or 0.0, drone_ref.battery_level or 0.0)

    def return_floor_wh(self, drone_ref, distance=None):
        """
        Fuel (Wh, or t Oil for heli) a drone needs on board right now to
        safely self-navigate to the nearest drone_service -- mirrors
        ChargingStationController's own return_floor_wh(), but the drone
        model needs no drone object at all (drone_rescue_energy_per_meter()
        is a flat per-engine constant, unlike the ground-vehicle model's
        per-chassis/module/cargo terms). distance: metres to the nearest
        serving station when the caller already has it (None = look up).
        """
        if distance is None:
            stations = self.station_coords(drone_ref)
            if not stations:
                return 0.0
            distance = min(((drone_ref.x - x) ** 2 + (drone_ref.y - y) ** 2) ** 0.5 for x, y in stations)
        reserve = self.RETURN_EMERGENCY_RESERVE_T if drone_ref.engine == "heli" else self.RETURN_EMERGENCY_RESERVE_WH
        return (distance * drone_rescue_energy_per_meter(drone_ref.engine) * self.RETURN_SAFETY_MARGIN) + reserve

    def rescue_target_level(self, drone_ref, floor=None):
        """Charge/refuel target for a rescue: enough to reach the nearest station with a safety reserve. floor: precomputed return_floor_wh()."""
        current, capacity, _ = self.fuel_of(drone_ref)
        if not capacity or capacity <= 0:
            return 1.0
        extra = self.RESCUE_EXTRA_RESERVE_T if drone_ref.engine == "heli" else self.RESCUE_EXTRA_RESERVE_WH
        if floor is None:
            floor = self.return_floor_wh(drone_ref)
        target = max(current, floor + extra)
        return min(1.0, target / capacity)

    def assess_stations(self, drone_ref, candidates, self_known):
        """
        One pass over candidate stations: (is_mine, nearest_distance, nearest_coords).
        is_mine matches is_nearest_station_to(): True when this station's own
        position is unknown, False when it is not among the candidates (a dry
        station for a heli), otherwise True unless another candidate is strictly closer.
        nearest_* are None when there are no candidates.
        """
        x = drone_ref.x
        y = drone_ref.y
        best = None
        best_coords = None
        mine = None
        for ref in candidates:
            coords = ref["coords"]
            dist_sq = (x - coords[0]) ** 2 + (y - coords[1]) ** 2
            if ref["id"] == self.name:
                mine = dist_sq
            if best is None or dist_sq < best:
                best = dist_sq
                best_coords = coords
        if not self_known:
            is_mine = True
        elif mine is None:
            is_mine = False
        else:
            is_mine = mine <= best
        return is_mine, (None if best is None else best ** 0.5), best_coords

    def order_return_to_service(self, drone_ref, target=None):
        """
        Proactively nudges a low-charge field drone toward the nearest
        drone_service before it needs a full rescue -- mirrors
        ChargingStationController.order_return_to_station() (see module
        docstring for why the cross-script go_to() call is expected to
        work). Issued once per low-fuel episode (nudge_commands, cleared
        when the drone docks or is rescued): every go_to() costs a minimal
        burn even for a 0 m leg, and re-issuing it each poll would
        also keep overriding the drone's own route.
        """
        if drone_ref.id in self.nudge_commands:
            return True
        if target is None:
            target = self.nearest_service_coords(drone_ref)
        if not target:
            return False
        try:
            drone = get_component(drone_ref.id)
            if not hasattr(drone, "go_to"):
                return False
            res = drone.go_to(target[0], target[1])
            if res.status == "ok":
                self.log.print(f"[{self.name}] {drone_ref.name} low on fuel; nudging home to drone_service at {target}.")
                self.nudge_commands.add(drone_ref.id)
                return True
        except Exception as error:
            swallowed("drone_service.DroneServiceController.order_return_to_service: get_component", error)
        return False

    def is_station_powered(self):
        if self.power and hasattr(self.power, "is_powered"):
            try:
                return self.power.is_powered(self.name)
            except Exception as error:
                swallowed("drone_service.DroneServiceController.is_station_powered: self.power.is_powered", error)
        return True

    def _queue_service(self, d_id, heli, lvl):
        """charge() an electric / refuel() a heli docked drone; logs the outcome."""
        verb = "refuel" if heli else "charge"
        res = self.station.refuel(d_id, self.target_charge_level) if heli else self.station.charge(d_id, self.target_charge_level)
        if res.status in ("charging", "refueling", "queued"):
            self.log.print(f"[{self.name}] Queued docked drone {d_id} ({lvl*100:.0f}%) for {verb}.")
            if heli:
                self._oil_warned = False
        elif res.status == "no_oil":
            if not self._oil_warned:
                hint = "oil_in wired but source dry" if service_has_oil_feed(self.name) else "oil_in not wired -- connect it to an Oil Pump/tank"
                self.log.level("warn").print(f"[{self.name}] Cannot refuel heli {d_id}: no oil ({hint}).")
                self._oil_warned = True
        elif res.status != "target_reached":
            self.log.level("warn").print(f"[{self.name}] {verb.capitalize()} queue notice for {d_id}: {res.status} - {res.message}")

    def manage_docked_drones(self):
        """Queues docked drones below target level: charge() for electric, refuel() for heli. True while bays are active or queued."""
        self.log.start(f"[{self.name}] manage_docked_drones()", level="debug")
        self.log.trace("manage_docked_drones() entry.")
        try:
            docked_ids = self.station.get_docked()
        except Exception as error:
            swallowed("drone_service.DroneServiceController.manage_docked_drones: self.station.get_docked", error)
            self.log.end()
            return False
        if not docked_ids:
            self.log.trace("no docked drones this cycle.")
            self.log.end()
            return False

        active_bays = self.station.get_active()
        queued = self.station.get_queue()
        busy = bool(active_bays) or bool(queued)

        for d_id in docked_ids:
            try:
                d = get_component(d_id)
                if not d:
                    continue
                # Probe, not hasattr(): drones expose both .battery and
                # .oil_tank; the wrong powertrain's methods raise ReferenceError.
                heli = False
                try:
                    lvl = d.battery.percent()
                except Exception:
                    try:
                        lvl = d.oil_tank.percent()
                        heli = True
                    except Exception:
                        self.log.debug(f"Docked drone {d_id} has no readable battery or oil tank; skipping.")
                        continue
                if lvl < (self.target_charge_level - 0.02):
                    if d_id not in active_bays and d_id not in queued:
                        self._queue_service(d_id, heli, lvl)
                        busy = True
                    else:
                        self.log.debug(f"Docked drone {d_id} ({lvl*100:.0f}%) below target but already active/queued; not re-queuing.")
                elif self.log.verbose:
                    self.log.trace(f"Docked drone {d_id} at {lvl*100:.0f}%, at or above target {self.target_charge_level*100:.0f}%; no charge needed.")
            except Exception as error:
                swallowed("drone_service.DroneServiceController.manage_docked_drones: get_component", error)
        self.log.trace(f"manage_docked_drones() exit: {len(docked_ids)} docked drone(s) evaluated.")
        self.log.end()
        return busy

    def _dispatch_rescue(self, d_ref, is_stranded, v_wh, target_level, floor):
        """Announces distress and dispatches the recovery vehicle; True when the loop over drones should stop."""
        unit = "t Oil" if d_ref.engine == "heli" else "Wh"
        reason = "STRANDED/SCRAMBLED" if is_stranded else f"CRITICAL FUEL ({v_wh:.1f} {unit}, below {floor:.1f} {unit} return floor)"
        self.log.start(f"[{self.name}] Rescue {d_ref.name}")
        self.log.level("warn").print(f"[{self.name}] Emergency! Drone {d_ref.name} ({d_ref.id}) in distress: {reason} at ({d_ref.x:.1f}, {d_ref.y:.1f}).")
        try:
            notify(f"[RESCUE DISPATCH] Sending recovery vehicle to {d_ref.name} ({reason})!", level="warn", duration_seconds=10.0)
        except Exception as error:
            swallowed("drone_service.DroneServiceController.manage_fleet_rescues: notify", error)

        res = self.station.dispatch_rescue(d_ref.id, target_level)
        if res.status == "ok":
            self.log.print(f"[{self.name}] Rescue dispatched to {d_ref.id}; target charge {target_level*100:.0f}%.")
            self.last_rescued_drone = d_ref.id
            self.log.end("dispatched")
            return True
        if res.status == "already_dispatched":
            self.log.debug(f"[{self.name}] Rescue for {d_ref.id} already dispatched; not re-issuing.")
            self.log.end("already dispatched")
            return True
        self.log.level("warn").print(f"[{self.name}] Dispatch rejection: {res.status} - {res.message}")
        self.log.end(f"rejected ({res.status})")
        return False

    def manage_fleet_rescues(self):
        """
        Monitors every owned drone (electric and heli). Redirects a low-charge field
        drone home before it needs rescue; dispatches the recovery vehicle
        for anything stranded/scrambled or already below its own return
        floor. Only the nearest serving station does the fuel/floor work for a
        drone. True while a rescue is in progress or a drone this station is
        responsible for is stranded, below floor or heading home.
        """
        self.log.start(f"[{self.name}] manage_fleet_rescues", level="debug")
        self.log.trace("manage_fleet_rescues() entry.")
        if self.station.is_rescuing():
            target_name = self.station.get_rescue_target()
            if target_name and target_name != self.last_rescued_drone:
                self.last_rescued_drone = target_name
                self.log.print(f"[{self.name}] Recovery vehicle currently in field assisting: {target_name}.")
            self.log.end()
            return True

        self.last_rescued_drone = None
        if not self.fleet:
            self.log.end()
            return False

        try:
            drones = self.fleet.drones()
        except Exception as error:
            swallowed("drone_service.DroneServiceController.manage_fleet_rescues: self.fleet.drones", error)
            self.log.end()
            return False

        # Parked stations take no responsibility; see ChargingStationController.manage_fleet_rescues().
        refs = self.all_station_refs()
        parked = parked_ids("drone_service_station")
        parked.discard(self.name)  # running, so awake whatever the archive says
        self_known = any(r["id"] == self.name for r in refs)
        heli_refs = None
        busy = False
        for d_ref in drones:
            engine = d_ref.engine
            if engine not in ("electric", "heli"):
                continue  # no thruster mounted yet
            if d_ref.is_docked or d_ref.is_being_rescued or d_ref.rescue_status != "none":
                self.nudge_commands.discard(d_ref.id)
                continue

            if engine == "heli":
                if heli_refs is None:
                    heli_refs, _tier = heli_capable_services(refs)
                candidates = heli_refs
            else:
                candidates = refs
            awake = [r for r in candidates if r["id"] not in parked] if parked else candidates
            is_mine, distance, nearest = self.assess_stations(d_ref, awake, self_known)
            if not is_mine:
                self.nudge_commands.discard(d_ref.id)
                continue

            is_stranded = d_ref.status in STRANDED_STATUSES
            v_wh, _, v_lvl = self.fuel_of(d_ref)
            floor = 0.0 if distance is None else self.return_floor_wh(d_ref, distance)
            target_level = self.rescue_target_level(d_ref, floor)
            is_below_floor = v_wh <= floor

            if parked and (is_stranded or is_below_floor or v_lvl < target_level):
                handoff = parked_nearest(d_ref, candidates, parked, distance)
                if handoff:
                    busy = True
                    wake_for_visit(handoff, f"{d_ref.name} needs its nearest station")
                    self.log.print(f"[{self.name}] {d_ref.name} ({v_lvl*100:.0f}%) is nearest to parked '{handoff}'; woke it to take over.")
                    continue

            if v_lvl < target_level and not is_stranded and not is_below_floor:
                busy = True
                self.log.debug(f"{d_ref.name}: level {v_lvl*100:.0f}% below rescue target {target_level*100:.0f}%, not yet stranded/below-floor; nudging home.")
                if self.order_return_to_service(d_ref, nearest):
                    continue

            if is_stranded or is_below_floor:
                busy = True
                if self._dispatch_rescue(d_ref, is_stranded, v_wh, target_level, floor):
                    break
        self.log.trace(f"manage_fleet_rescues() exit: {len(drones)} drone(s) evaluated.")
        self.log.end()
        return busy

    def step(self):
        """One supervision cycle; returns True while this station has work (poll fast)."""
        if not self.is_station_powered():
            self.parker.update(False)
            return False
        docked_busy = self.manage_docked_drones()
        rescue_busy = self.manage_fleet_rescues()
        busy = docked_busy or rescue_busy
        self.parker.update(not busy)
        return busy

    def run(self, poll_interval=ACTIVE_POLL_SECONDS, idle_poll_seconds=IDLE_POLL_SECONDS):
        bay_count = getattr(self.station, "get_bay_count", lambda: 1)()
        self.log.print(f"Drone Service Station ({self.name}) online via Shared Library ({bay_count} bay(s)).")
        validate_game_version()
        while True:
            reset_all()
            busy = False
            try:
                busy = self.step()
            except Exception as e:
                self.log.level("error").print(f"[{self.name}] Error in supervision cycle: {e}")
            flush_all()
            sleep(poll_interval if busy else idle_poll_seconds)
