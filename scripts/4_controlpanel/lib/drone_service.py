# Shared Library for Drone Service Station (charging/rescue) Management.
# Structural mirror of lib/charging.py's ChargingStationController: docked
# charge queue, fleet-wide stranded/scrambled detection via fleet.drones(),
# rescue dispatch, multi-station nearest-station coordination, power-gating.
# Engine-aware: electric drones are charge()d, heli drones refuel()ed from
# oil_in; floors/targets use each drone's own fuel unit (Wh / t Oil, see
# lib/drone_energy.py ENGINE_PROFILES).
#
# Open question flagged in the plan: whether a station script's cross-script
# drone.go_to() call actually works given drone.md's "(self only)" tag.
# Resolved by precedent already relied on in this codebase: nav_module.md
# tags NavModule.set_target()/set_throttle() "(self only)" too, yet
# lib/charging.py's order_return_to_station() already calls
# get_component(vehicle_ref.id).nav.set_target(...) successfully from a
# DIFFERENT script (the charging station's), and that behavior is production
# code, not a workaround. "(self only)" therefore documents the METHOD's
# intended caller convention, not an engine-enforced same-script restriction
# -- so order_return_to_service() below calls get_component(drone_id).go_to()
# the same way, mirroring order_return_to_station() exactly.

from drone_energy import discover_drone_services, drone_rescue_energy_per_meter, service_has_oil_feed, heli_capable_services, HELI_MIN_EMERGENCY_RESERVE_T
from tree_console import TreeConsole
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

    def return_floor_wh(self, drone_ref):
        """
        Fuel (Wh, or t Oil for heli) a drone needs on board right now to
        safely self-navigate to the nearest drone_service -- mirrors
        ChargingStationController's own return_floor_wh(), but the drone
        model needs no drone object at all (drone_rescue_energy_per_meter()
        is a flat per-engine constant, unlike the ground-vehicle model's
        per-chassis/module/cargo terms).
        """
        stations = self.station_coords(drone_ref)
        if not stations:
            return 0.0
        distance = min(((drone_ref.x - x) ** 2 + (drone_ref.y - y) ** 2) ** 0.5 for x, y in stations)
        reserve = self.RETURN_EMERGENCY_RESERVE_T if drone_ref.engine == "heli" else self.RETURN_EMERGENCY_RESERVE_WH
        return (distance * drone_rescue_energy_per_meter(drone_ref.engine) * self.RETURN_SAFETY_MARGIN) + reserve

    def rescue_target_level(self, drone_ref):
        """Charge/refuel target for a rescue: enough to reach the nearest station with a safety reserve."""
        current, capacity, _ = self.fuel_of(drone_ref)
        if not capacity or capacity <= 0:
            return 1.0
        extra = self.RESCUE_EXTRA_RESERVE_T if drone_ref.engine == "heli" else self.RESCUE_EXTRA_RESERVE_WH
        target = max(current, self.return_floor_wh(drone_ref) + extra)
        return min(1.0, target / capacity)

    def order_return_to_service(self, drone_ref):
        """
        Proactively nudges a low-charge field drone toward the nearest
        drone_service before it needs a full rescue -- mirrors
        ChargingStationController.order_return_to_station() (see module
        docstring for why the cross-script go_to() call is expected to
        work). Issued once per low-fuel episode (nudge_commands, cleared
        when the drone docks or is rescued): every go_to() costs a minimal
        burn even for a 0 m leg, and re-issuing it each 1.5 s cycle would
        also keep overriding the drone's own route.
        """
        if drone_ref.id in self.nudge_commands:
            return True
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
        except Exception:
            pass
        return False

    def is_station_powered(self):
        if self.power and hasattr(self.power, "is_powered"):
            try:
                return self.power.is_powered(self.name)
            except Exception:
                pass
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
        """Queues docked drones below target level: charge() for electric, refuel() for heli."""
        self.log.trace(f"[{self.name}] manage_docked_drones() entry.")
        try:
            docked_ids = self.station.get_docked()
        except Exception:
            return
        if not docked_ids:
            self.log.trace(f"[{self.name}] manage_docked_drones(): no docked drones this cycle.")
            return

        active_bays = self.station.get_active()
        queued = self.station.get_queue()

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
                        self.log.debug(f"[{self.name}] Docked drone {d_id} has no readable battery or oil tank; skipping.")
                        continue
                if lvl < (self.target_charge_level - 0.02):
                    if d_id not in active_bays and d_id not in queued:
                        self._queue_service(d_id, heli, lvl)
                    else:
                        self.log.debug(f"[{self.name}] Docked drone {d_id} ({lvl*100:.0f}%) below target but already active/queued; not re-queuing.")
                else:
                    self.log.trace(f"[{self.name}] Docked drone {d_id} at {lvl*100:.0f}%, at or above target {self.target_charge_level*100:.0f}%; no charge needed.")
            except Exception:
                pass
        self.log.trace(f"[{self.name}] manage_docked_drones() exit: {len(docked_ids)} docked drone(s) evaluated.")

    def manage_fleet_rescues(self):
        """
        Monitors every owned drone (electric and heli). Redirects a low-charge field
        drone home before it needs rescue; dispatches the recovery vehicle
        for anything stranded/scrambled or already below its own return
        floor.
        """
        self.log.trace(f"[{self.name}] manage_fleet_rescues() entry.")
        if self.station.is_rescuing():
            target_name = self.station.get_rescue_target()
            if target_name and target_name != self.last_rescued_drone:
                self.last_rescued_drone = target_name
                self.log.print(f"[{self.name}] Recovery vehicle currently in field assisting: {target_name}.")
            return

        self.last_rescued_drone = None
        if not self.fleet:
            return

        try:
            drones = self.fleet.drones()
        except Exception:
            return

        for d_ref in drones:
            if d_ref.engine not in ("electric", "heli"):
                continue  # no thruster mounted yet
            if d_ref.is_docked or d_ref.is_being_rescued or d_ref.rescue_status != "none":
                self.nudge_commands.discard(d_ref.id)
                continue

            is_stranded = d_ref.status in STRANDED_STATUSES
            v_wh, _, v_lvl = self.fuel_of(d_ref)
            target_level = self.rescue_target_level(d_ref)
            is_below_floor = v_wh <= self.return_floor_wh(d_ref)

            if v_lvl < target_level and not is_stranded and not is_below_floor:
                self.log.debug(f"[{self.name}] {d_ref.name}: level {v_lvl*100:.0f}% below rescue target {target_level*100:.0f}%, not yet stranded/below-floor; nudging home.")
                if self.order_return_to_service(d_ref):
                    continue

            if is_stranded or is_below_floor:
                if not self.is_nearest_station_to(d_ref):
                    self.log.debug(f"[{self.name}] {d_ref.name} in distress but a closer drone_service station exists; deferring dispatch to it.")
                    continue

                unit = "t Oil" if d_ref.engine == "heli" else "Wh"
                reason = "STRANDED/SCRAMBLED" if is_stranded else f"CRITICAL FUEL ({v_wh:.1f} {unit}, below {self.return_floor_wh(d_ref):.1f} {unit} return floor)"
                self.log.level("warn").print(f"[{self.name}] Emergency! Drone {d_ref.name} ({d_ref.id}) in distress: {reason} at ({d_ref.x:.1f}, {d_ref.y:.1f}).")
                try:
                    notify(f"[RESCUE DISPATCH] Sending recovery vehicle to {d_ref.name} ({reason})!", level="warn", duration_seconds=10.0)
                except Exception:
                    pass

                res = self.station.dispatch_rescue(d_ref.id, target_level)
                if res.status == "ok":
                    self.log.print(f"[{self.name}] Rescue dispatched to {d_ref.id}; target charge {target_level*100:.0f}%.")
                    self.last_rescued_drone = d_ref.id
                    break
                elif res.status == "already_dispatched":
                    self.log.debug(f"[{self.name}] Rescue for {d_ref.id} already dispatched; not re-issuing.")
                    break
                else:
                    self.log.level("warn").print(f"[{self.name}] Dispatch rejection: {res.status} - {res.message}")
        self.log.trace(f"[{self.name}] manage_fleet_rescues() exit: {len(drones)} drone(s) evaluated.")

    def step(self):
        if not self.is_station_powered():
            sleep(2.0)
            return
        self.manage_docked_drones()
        self.manage_fleet_rescues()

    def run(self, poll_interval=1.5):
        bay_count = getattr(self.station, "get_bay_count", lambda: 1)()
        self.log.print(f"Drone Service Station ({self.name}) online via Shared Library ({bay_count} bay(s)).")
        validate_game_version()
        while True:
            try:
                self.step()
            except Exception as e:
                self.log.level("error").print(f"[{self.name}] Error in supervision cycle: {e}")
            sleep(poll_interval)
