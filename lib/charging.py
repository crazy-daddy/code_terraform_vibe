# Shared Library for Vehicle Charging Station & Fleet Rescue Management
# Manages docked vehicle fast-charging, queue optimization, and automated rescue
# drone dispatch for stranded or critically low-battery vehicles in the field.
from archive import archive

class ChargingStationController:
    """
    Automates a Vehicle Charging Station.
    - Manages charging queues for docked vehicles (Rovers, Pioneers).
    - Monitors the entire fleet via get_component("fleet").
    - Detects stranded vehicles or low-battery vehicles in the field and auto-dispatches the rescue drone.
    - Broadcasts fleet charge status and rescue events via popup toasts (notify).
    """
    RETURN_WH_PER_METER = 0.08
    RETURN_SAFETY_MARGIN = 1.35
    RETURN_EMERGENCY_RESERVE_WH = 8.0
    RESCUE_EXTRA_RESERVE_WH = 8.0

    def __init__(self, station, target_charge_level=1.0):
        self.station = station
        self.name = getattr(station, "id", "vehicle_charging_station")
        self.target_charge_level = target_charge_level
        self.fleet = get_component("fleet")
        self.power = get_component("power_control")

        self.last_rescued_vehicle = None
        self.return_commands = set()

    def charging_station_coords(self):
        """Returns known charging-station coordinates, nearest first when available."""
        coords = []
        network = get_component("outpost_network")
        if network and hasattr(network, "outposts"):
            try:
                for outpost in network.outposts():
                    for building in outpost.buildings("charging_station"):
                        position = getattr(building, "position", None)
                        if position:
                            coords.append((position.x, position.y))
            except Exception:
                pass

        station_outpost = getattr(self.station, "outpost", None)
        position = getattr(station_outpost, "position", None)
        if position:
            fallback = (position.x, position.y)
            if fallback not in coords:
                coords.append(fallback)
        return coords

    def rescue_target_level(self, vehicle_ref):
        """Calculates charge needed to reach the nearest station with safety reserve."""
        capacity = getattr(vehicle_ref, "battery_capacity", None)
        current_wh = getattr(vehicle_ref, "battery_wh", 0.0)
        if not capacity:
            try:
                vehicle = get_component(vehicle_ref.id)
                capacity = vehicle.battery.capacity()
                current_wh = vehicle.battery.wh()
            except Exception:
                capacity = None
        if not capacity or capacity <= 0:
            return 1.0

        stations = self.charging_station_coords()
        if not stations:
            return 1.0

        distance = min(
            ((vehicle_ref.x - x) ** 2 + (vehicle_ref.y - y) ** 2) ** 0.5
            for x, y in stations
        )
        wh_per_meter = archive.get("fleet.wh_per_meter", self.RETURN_WH_PER_METER)
        return_wh = (
            distance * wh_per_meter * self.RETURN_SAFETY_MARGIN
            + self.RETURN_EMERGENCY_RESERVE_WH
            + self.RESCUE_EXTRA_RESERVE_WH
        )
        target_wh = max(current_wh, return_wh)
        return min(1.0, target_wh / capacity)

    def nearest_station_coords(self, vehicle_ref):
        """Returns the closest known charging station to a fleet snapshot."""
        stations = self.charging_station_coords()
        if not stations:
            return None
        return min(
            stations,
            key=lambda point: ((vehicle_ref.x - point[0]) ** 2 + (vehicle_ref.y - point[1]) ** 2) ** 0.5,
        )

    def order_return_to_station(self, vehicle_ref):
        """Redirects a low-charge vehicle home before requesting rescue."""
        target = self.nearest_station_coords(vehicle_ref)
        if not target:
            return False
        try:
            vehicle = get_component(vehicle_ref.id)
            if not hasattr(vehicle, "nav"):
                return False
            set_res = vehicle.nav.set_target(target[0], target[1])
            throttle_res = vehicle.nav.set_throttle(0.35) if set_res.status == "ok" else set_res
            if set_res.status == "ok" and throttle_res.status == "ok":
                if vehicle_ref.id not in self.return_commands:
                    print(f"[{self.name}] {vehicle_ref.name} low on charge; returning to nearest charging station at {target} before rescue.")
                    self.return_commands.add(vehicle_ref.id)
                return True
        except Exception:
            pass
        return False

    def is_station_powered(self):
        """Verifies whether this charging station currently has grid power."""
        if self.power and hasattr(self.power, "is_powered"):
            try:
                return self.power.is_powered(self.name)
            except Exception:
                pass
        return True

    def manage_docked_vehicles(self):
        """Inspects all docked vehicles and ensures they are actively charging up to target level."""
        docked_ids = self.station.get_docked()
        if not docked_ids:
            return

        active_bays = self.station.get_active()
        queued = self.station.get_queue()

        for v_id in docked_ids:
            try:
                v = get_component(v_id)
                if not v or not hasattr(v, "battery"):
                    continue

                lvl = v.battery.level()
                wh = v.battery.wh()

                # If vehicle is below target and not active or queued, queue it for charging
                if lvl < (self.target_charge_level - 0.02):
                    if v_id not in active_bays and v_id not in queued:
                        res = self.station.charge(v_id, self.target_charge_level)
                        if res.status in ["ok", "charging", "queued"]:
                            print(f"[{self.name}] Queued docked vehicle {v_id} ({lvl*100:.0f}%, {wh:.1f} Wh) for charge.")
                        elif res.status != "target_reached":
                            print(f"[{self.name}] Charge queue notice for {v_id}: {res.status} - {res.message}")
            except Exception as e:
                pass

    def manage_fleet_rescues(self):
        """
        Monitors all vehicles in the field.
        If any rover or pioneer is stranded, stalled, or critically low on battery,
        and not already docked or being rescued, dispatch the rescue drone!
        """
        if self.station.is_rescuing():
            target_name = self.station.get_rescue_target()
            if target_name and target_name != self.last_rescued_vehicle:
                self.last_rescued_vehicle = target_name
                print(f"[{self.name}] Rescue drone currently in field assisting: {target_name}.")
            return

        self.last_rescued_vehicle = None

        if not self.fleet:
            return

        # Check all owned ground vehicles
        try:
            vehicles = self.fleet.vehicles()
        except Exception:
            return

        for v_ref in vehicles:
            v_id = v_ref.id
            v_name = v_ref.name
            v_status = v_ref.status
            v_lvl = v_ref.battery_level
            v_wh = v_ref.battery_wh
            is_docked = v_ref.is_docked
            is_rescued = v_ref.is_being_rescued or v_ref.rescue_status != "none"

            # Do not rescue docked vehicles or those already being rescued
            if is_docked or is_rescued:
                continue

            # First redirect a vehicle below its safe return target. Rescue is
            # reserved for a stranded vehicle or one with almost no usable power.
            is_stranded = v_status in ["stranded", "stalled_no_battery"]
            target_level = self.rescue_target_level(v_ref)
            is_barely_operational = v_lvl <= 0.05

            if v_lvl < target_level and not is_stranded and not is_barely_operational:
                if self.order_return_to_station(v_ref):
                    continue

            is_critical = is_barely_operational

            if is_stranded or is_critical:
                reason = "STRANDED" if is_stranded else f"CRITICAL BATTERY ({v_lvl*100:.0f}%, {v_wh:.1f} Wh)"
                print(f"[{self.name}] Emergency! Vehicle {v_name} ({v_id}) in distress: {reason} at ({v_ref.x:.1f}, {v_ref.y:.1f}).")

                try:
                    notify(f"[RESCUE DISPATCH] Sending rescue drone to {v_name} ({reason})!", level="warn", duration_seconds=10.0)
                except Exception:
                    pass

                # Dispatch rescue drone
                res = self.station.dispatch_rescue(v_id, target_level)
                if res.status == "ok":
                    print(f"[{self.name}] Rescue drone launched to {v_id}; target charge {target_level*100:.0f}% for safe station return.")
                    self.last_rescued_vehicle = v_id
                    break
                elif res.status == "already_dispatched":
                    break
                else:
                    print(f"[{self.name}] Dispatch rejection: {res.status} - {res.message}")

    def step(self):
        """Single supervision cycle for dock charging and field rescue."""
        if not self.is_station_powered():
            sleep(2.0)
            return

        self.manage_docked_vehicles()
        self.manage_fleet_rescues()

    def run(self, poll_interval=1.5):
        """Continuous supervision loop."""
        bay_count = getattr(self.station, "get_bay_count", lambda: 1)()
        bay_rate = getattr(self.station, "get_bay_rate", lambda: 30)()
        print(f"Charging Station ({self.name}) online via Shared Library ({bay_count} bay(s), {bay_count * bay_rate} W max pool).")
        while True:
            try:
                self.step()
            except Exception as e:
                print(f"[{self.name}] Error in supervision cycle: {e}")
            sleep(poll_interval)
