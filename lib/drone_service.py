# Shared Library for Drone Service Station (charging/rescue) Management.
# Structural mirror of lib/charging.py's ChargingStationController: docked
# charge queue, fleet-wide stranded/scrambled detection via fleet.drones(),
# rescue dispatch, multi-station nearest-station coordination, power-gating.
# No refuel/oil branching this pass -- electric drones only (see lib/drone.py).
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

from drone_energy import discover_drone_services, drone_rescue_wh_per_meter
from tree_console import TreeConsole
from version_guard import validate_game_version

STRANDED_STATUSES = ("stalled_no_battery", "scrambled")


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

    def __init__(self, station, target_charge_level=1.0):
        self.station = station
        self.name = getattr(station, "id", "drone_service_station")
        self.target_charge_level = target_charge_level
        self.fleet = get_component("fleet")
        self.power = get_component("power_control")
        self.last_rescued_drone = None
        self.nudge_commands = set()
        self.log = TreeConsole(module="drone_service")

    def all_station_refs(self):
        return discover_drone_services()

    def my_coords(self):
        for r in self.all_station_refs():
            if r["id"] == self.name:
                return r["coords"]
        return None

    def station_coords(self):
        return [r["coords"] for r in self.all_station_refs()]

    def is_nearest_station_to(self, drone_ref):
        """
        True when this station is the closest known drone_service_station to
        drone_ref. Every deployed station runs its own independent copy of
        this script and polls the same fleet snapshot, so without this
        check every station within range would dispatch its own recovery
        vehicle to the same stranded drone (mirrors
        ChargingStationController.is_nearest_station_to()).
        """
        my_pos = self.my_coords()
        if my_pos is None:
            return True
        my_dist = ((drone_ref.x - my_pos[0]) ** 2 + (drone_ref.y - my_pos[1]) ** 2) ** 0.5
        for ref in self.all_station_refs():
            if ref["id"] == self.name:
                continue
            other_dist = ((drone_ref.x - ref["coords"][0]) ** 2 + (drone_ref.y - ref["coords"][1]) ** 2) ** 0.5
            if other_dist < my_dist:
                return False
        return True

    def nearest_service_coords(self, drone_ref):
        stations = self.station_coords()
        if not stations:
            return None
        return min(stations, key=lambda point: ((drone_ref.x - point[0]) ** 2 + (drone_ref.y - point[1]) ** 2) ** 0.5)

    def return_floor_wh(self, drone_ref):
        """
        Wh a drone needs on board right now to safely self-navigate to the
        nearest drone_service -- mirrors ChargingStationController's own
        return_floor_wh(), but the drone model needs no drone object at all
        (drone_rescue_wh_per_meter() is a flat constant, unlike the ground-
        vehicle model's per-chassis/module/cargo terms).
        """
        stations = self.station_coords()
        if not stations:
            return 0.0
        distance = min(((drone_ref.x - x) ** 2 + (drone_ref.y - y) ** 2) ** 0.5 for x, y in stations)
        return (distance * drone_rescue_wh_per_meter() * self.RETURN_SAFETY_MARGIN) + self.RETURN_EMERGENCY_RESERVE_WH

    def rescue_target_level(self, drone_ref):
        """Charge target for a rescue: enough to reach the nearest station with a safety reserve."""
        capacity = getattr(drone_ref, "battery_capacity", None)
        current_wh = getattr(drone_ref, "battery_wh", 0.0) or 0.0
        if not capacity or capacity <= 0:
            return 1.0
        return_wh = self.return_floor_wh(drone_ref) + self.RESCUE_EXTRA_RESERVE_WH
        target_wh = max(current_wh, return_wh)
        return min(1.0, target_wh / capacity)

    def order_return_to_service(self, drone_ref):
        """
        Proactively nudges a low-charge field drone toward the nearest
        drone_service before it needs a full rescue -- mirrors
        ChargingStationController.order_return_to_station() (see module
        docstring for why the cross-script go_to() call is expected to
        work).
        """
        target = self.nearest_service_coords(drone_ref)
        if not target:
            return False
        try:
            drone = get_component(drone_ref.id)
            if not hasattr(drone, "go_to"):
                return False
            res = drone.go_to(target[0], target[1])
            if res.status == "ok":
                if drone_ref.id not in self.nudge_commands:
                    self.log.print(f"[{self.name}] {drone_ref.name} low on charge; nudging home to drone_service at {target}.")
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

    def manage_docked_drones(self):
        """Queues docked electric drones below target charge level for charging."""
        try:
            docked_ids = self.station.get_docked()
        except Exception:
            return
        if not docked_ids:
            return

        active_bays = self.station.get_active()
        queued = self.station.get_queue()

        for d_id in docked_ids:
            try:
                d = get_component(d_id)
                if not d or not hasattr(d, "battery"):
                    continue  # heli drone -- refuel() branching is out of scope this pass
                lvl = d.battery.percent()
                if lvl < (self.target_charge_level - 0.02):
                    if d_id not in active_bays and d_id not in queued:
                        res = self.station.charge(d_id, self.target_charge_level)
                        if res.status in ("charging", "queued"):
                            self.log.print(f"[{self.name}] Queued docked drone {d_id} ({lvl*100:.0f}%) for charge.")
                        elif res.status != "target_reached":
                            self.log.level("warn").print(f"[{self.name}] Charge queue notice for {d_id}: {res.status} - {res.message}")
            except Exception:
                pass

    def manage_fleet_rescues(self):
        """
        Monitors every owned electric drone. Redirects a low-charge field
        drone home before it needs rescue; dispatches the recovery vehicle
        for anything stranded/scrambled or already below its own return
        floor.
        """
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
            if d_ref.engine != "electric":
                continue  # heli refuel-rescue is out of scope this pass
            if d_ref.is_docked or d_ref.is_being_rescued or d_ref.rescue_status != "none":
                continue

            is_stranded = d_ref.status in STRANDED_STATUSES
            v_wh = d_ref.battery_wh or 0.0
            target_level = self.rescue_target_level(d_ref)
            v_lvl = d_ref.battery_level or 0.0
            is_below_floor = v_wh <= self.return_floor_wh(d_ref)

            if v_lvl < target_level and not is_stranded and not is_below_floor:
                if self.order_return_to_service(d_ref):
                    continue

            if is_stranded or is_below_floor:
                if not self.is_nearest_station_to(d_ref):
                    continue

                reason = "STRANDED/SCRAMBLED" if is_stranded else f"CRITICAL BATTERY ({v_wh:.1f} Wh, below {self.return_floor_wh(d_ref):.1f} Wh return floor)"
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
                    break
                else:
                    self.log.level("warn").print(f"[{self.name}] Dispatch rejection: {res.status} - {res.message}")

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
