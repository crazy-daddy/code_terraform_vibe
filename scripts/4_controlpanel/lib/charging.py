# Shared Library for Vehicle Charging Station & Fleet Rescue Management
# Manages docked vehicle fast-charging, queue optimization, and automated rescue
# drone dispatch for stranded or critically low-battery vehicles in the field.
import geometry
from charging_stations import all_stations
from station_controller import StationController
from swallow import swallowed
from vehicle_energy import rescue_wh_per_meter_for


class ChargingStationController(StationController):
    """
    Automates a Vehicle Charging Station.
    - Manages charging queues for docked vehicles (Rovers, Pioneers).
    - Monitors the entire fleet via get_component("fleet").
    - Detects stranded vehicles or low-battery vehicles in the field and auto-dispatches the rescue drone.
    - Broadcasts fleet charge status and rescue events via popup toasts (notify).
    """

    MODULE = "charging"
    PARK_KIND = "charging_station"
    DEFAULT_NAME = "vehicle_charging_station"
    RETURN_EMERGENCY_RESERVE_WH = 8.0
    RESCUE_EXTRA_RESERVE_WH = 8.0
    RESCUER = "Rescue drone"
    RESCUE_STATUSES = ("stranded", "stalled_no_battery")

    def all_station_refs(self):
        """
        Returns [{"id": str, "coords": (x, y)}, ...] for every deployed charging
        station. BuildingRef.position is a plain (x, y) tuple, but OutpostRef.position
        is a *method* (returns a Position snapshot) -- OutpostRef.x/.y are the plain
        floats to use instead. Treating OutpostRef.position as a tuple raises
        "'native_fn' object has no attribute 'x'" every cycle.
        """
        refs = []

        try:
            refs = [{"id": s["id"], "coords": s["coords"]} for s in all_stations()]
        except Exception as error:
            swallowed("charging.ChargingStationController.all_station_refs: all_stations", error)

        if not any(r["id"] == self.name for r in refs):
            station_outpost = getattr(self.station, "outpost", None)
            if station_outpost is not None:
                x = getattr(station_outpost, "x", None)
                y = getattr(station_outpost, "y", None)
                if x is not None and y is not None:
                    refs.append({"id": self.name, "coords": (float(x), float(y))})
        return refs

    def charging_station_coords(self):
        """Returns known charging-station coordinates, nearest first when available."""
        return [r["coords"] for r in self.all_station_refs()]

    def return_floor_wh(self, unit_ref, distance=None):
        """
        Wh a vehicle needs on board right now to safely self-navigate to the
        nearest known charging station -- the same floor drive_to()'s own hard
        abort (energy_needed_to_return_now()) enforces from the vehicle's own
        side. Falling below this means the vehicle can no longer reach a
        station under its own power and genuinely needs a rescue, regardless
        of what fraction of its (not necessarily known here) capacity that
        represents -- a fixed battery-level percentage doesn't track a
        per-vehicle, per-distance floor like this does. distance: metres to
        the nearest station when the caller already has it (None = look up).
        """
        if distance is None:
            stations = self.charging_station_coords()
            if not stations:
                return 0.0
            distance = min(geometry.distance((unit_ref.x, unit_ref.y), s) for s in stations)

        vehicle = None
        try:
            vehicle = get_component(unit_ref.id)
        except Exception as error:
            swallowed("charging.ChargingStationController.return_floor_wh: get_component", error)
            vehicle = None

        # Rescue is a last-resort case, so rate the leg at the speedmode throttle
        # floor (cheapest possible Wh/m) -- rescue_wh_per_meter_for() already
        # handles the "vehicle unreachable" fallback internally.
        wh_per_meter = rescue_wh_per_meter_for(vehicle)
        return (distance * wh_per_meter * self.RETURN_SAFETY_MARGIN) + self.RETURN_EMERGENCY_RESERVE_WH

    def rescue_target_level(self, unit_ref, floor=None):
        """Calculates charge needed to reach the nearest station with safety reserve. floor: precomputed return_floor_wh()."""
        capacity = getattr(unit_ref, "battery_capacity", None)
        current_wh = getattr(unit_ref, "battery_wh", 0.0)
        if not capacity:
            try:
                vehicle = get_component(unit_ref.id)
                capacity = vehicle.battery.capacity()
                current_wh = vehicle.battery.wh()
            except Exception as error:
                swallowed("charging.ChargingStationController.rescue_target_level: get_component", error)
                capacity = None
        if not capacity or capacity <= 0:
            return 1.0

        if floor is None:
            floor = self.return_floor_wh(unit_ref)
        target_wh = max(current_wh, floor + self.RESCUE_EXTRA_RESERVE_WH)
        return min(1.0, target_wh / capacity)

    def manage_docked(self):
        """Inspects all docked vehicles and ensures they are actively charging up to target level. True while bays are active or queued."""
        docked_ids = self.station.get_docked()
        if not docked_ids:
            return False

        active_bays = self.station.get_active()
        queued = self.station.get_queue()
        busy = bool(active_bays) or bool(queued)

        for v_id in docked_ids:
            try:
                battery = getattr(get_component(v_id), "battery", None)
                if battery is None:
                    continue

                lvl = battery.level()
                wh = battery.wh()

                # If vehicle is below target and not active or queued, queue it for charging
                if lvl < (self.target_charge_level - 0.02):
                    if v_id not in active_bays and v_id not in queued:
                        res = self.station.charge(v_id, self.target_charge_level)
                        busy = True
                        if res.status in ["ok", "charging", "queued"]:
                            self.log.print(f"[{self.name}] Queued docked vehicle {v_id} ({lvl * 100:.0f}%, {wh:.1f} Wh) for charge.")
                        elif res.status != "target_reached":
                            self.log.level("warn").print(f"[{self.name}] Charge queue notice for {v_id}: {res.status} - {res.message}")
            except Exception as e:
                swallowed("charging.ChargingStationController.manage_docked: get_component", e)
        return busy

    # ---------- rescue hooks (StationController.manage_fleet_rescues)

    def rescue_units(self, fleet):
        return fleet.vehicles()

    def rescue_fuel(self, unit_ref):
        return unit_ref.battery_wh, unit_ref.battery_level

    def _dispatch_rescue(self, unit_ref, is_stranded, wh, target_level, floor):
        """Announces distress and dispatches the rescue drone; True when the loop over vehicles should stop."""
        v_id, v_name, v_lvl = unit_ref.id, unit_ref.name, unit_ref.battery_level
        reason = "STRANDED" if is_stranded else f"CRITICAL BATTERY ({v_lvl * 100:.0f}%, {wh:.1f} Wh, below {floor:.1f} Wh return floor)"
        self.log.start(f"[{self.name}] Rescue {v_name} ({v_id})")
        self.log.level("warn").print(f"[{self.name}] Emergency! Vehicle {v_name} ({v_id}) in distress: {reason} at ({unit_ref.x:.1f}, {unit_ref.y:.1f}).")

        notify(f"[RESCUE DISPATCH] Sending rescue drone to {v_name} ({reason})!", level="warn", duration_seconds=10.0)

        self.log.debug(f"[{self.name}] {v_id} selected for rescue this cycle ({reason}); only one drone dispatch is attempted per step(), any other distressed vehicle waits for the next cycle.")
        res = self.station.dispatch_rescue(v_id, target_level)
        if res.status == "ok":
            self.log.print(f"[{self.name}] Rescue drone launched to {v_id}; target charge {target_level * 100:.0f}% for safe station return.")
            self.last_rescued = v_id
            self.log.end(f"[{self.name}] Rescue dispatched to {v_id}")
            return True
        if res.status == "already_dispatched":
            self.log.end(f"[{self.name}] Rescue already dispatched for {v_id}")
            return True
        self.log.level("warn").print(f"[{self.name}] Dispatch rejection: {res.status} - {res.message}")
        self.log.end(f"[{self.name}] Rescue dispatch rejected for {v_id}")
        return False

    def online_message(self):
        bay_count = getattr(self.station, "get_bay_count", lambda: 1)()
        bay_rate = getattr(self.station, "get_bay_rate", lambda: 30)()
        return f"Charging Station ({self.name}) online via Shared Library ({bay_count} bay(s), {bay_count * bay_rate} W max pool)."
