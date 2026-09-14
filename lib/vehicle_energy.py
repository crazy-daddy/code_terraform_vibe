# Vehicle mixin: battery accounting, round-trip energy budgeting, and
# charging-station discovery/docking. Shared by Rover and Pioneer via
# VehicleController (lib/vehicle.py).

from archive import archive

CHARGING_STATION_TYPE_ID = "vehicle_charging_station"

SPEEDMODE_KEY = "vehicle.speedmode"
SPEEDMODE_CONSERVE = "conserve"
SPEEDMODE_HIGHSPEED = "highspeed"


class VehicleEnergyMixin:
    """
    Battery telemetry, empirically-calibrated Wh/meter energy costs, and
    outpost-aware charging-station discovery, mixed into VehicleController.
    """
    WH_PER_METER_DEFAULT = 0.08
    SONAR_WH_BUDGET = 2.0
    MINE_WH_PER_UNIT = 2.5
    SAFETY_MARGIN_MULTIPLIER = 1.35
    MIN_EMERGENCY_RESERVE_WH = 8.0

    # Wh to take a Constructor Module job from 0% to 100% progress. Uncalibrated
    # starting assumption (like WH_PER_METER_DEFAULT) -- calibrate_wh_per_progress()
    # refines it per-vehicle from observed execute() calls once real samples exist.
    CONSTRUCTION_WH_PER_PROGRESS_DEFAULT = 40.0

    # Speed/power model behind the vehicle.speedmode throttle selection below:
    #   speed (m per game-hour) = DRIVE_SPEED_M_PER_HOUR_PER_THROTTLE * throttle
    #   power (watts)           = DRIVE_POWER_W_PER_THROTTLE_SQUARED * throttle^2
    DRIVE_SPEED_M_PER_HOUR_PER_THROTTLE = 100.0
    DRIVE_POWER_W_PER_THROTTLE_SQUARED = 20.0
    MIN_SPEEDMODE_THROTTLE = 0.10
    MAX_SPEEDMODE_THROTTLE = 1.0

    def calibration_key(self):
        return f"vehicle.wh_per_meter:{self.name}"

    def load_wh_per_meter(self):
        value = archive.get(self.calibration_key(), None)
        if value is None:
            value = archive.get("fleet.wh_per_meter", None)
        if value is None and str(self.name).startswith("rover"):
            value = archive.get("rover.wh_per_meter", None)
        return value if value is not None else self.WH_PER_METER_DEFAULT

    def construction_calibration_key(self):
        return f"vehicle.wh_per_progress:{self.name}"

    def load_wh_per_progress(self):
        value = archive.get(self.construction_calibration_key(), None)
        if value is None:
            value = archive.get("fleet.wh_per_progress", None)
        return value if value is not None else self.CONSTRUCTION_WH_PER_PROGRESS_DEFAULT

    def calibrate_wh_per_progress(self, delta_progress, delta_wh):
        """Dynamically calibrates actual Wh per 100% construction progress from observed execute() calls."""
        if delta_progress > 0.01 and delta_wh > 0.1:
            observed_wh_per_progress = delta_wh / delta_progress
            if 1.0 <= observed_wh_per_progress <= 500.0:
                base_val = self.wh_per_progress if self.wh_per_progress is not None else self.CONSTRUCTION_WH_PER_PROGRESS_DEFAULT
                self.wh_per_progress = (base_val * 0.70) + (observed_wh_per_progress * 0.30)
                archive.set(self.construction_calibration_key(), self.wh_per_progress)

    def get_battery(self):
        """Returns (current_wh, capacity_wh, fraction 0-1)."""
        try:
            wh = self.vehicle.battery.wh()
            cap = self.vehicle.battery.capacity()
            lvl = self.vehicle.battery.level()
            return wh, cap, lvl
        except Exception:
            return 0.0, 100.0, 0.0

    def minimum_wh_per_meter(self):
        """
        Best-case Wh/meter at the speedmode throttle floor (MIN_SPEEDMODE_THROTTLE),
        derived from the same speed/power model as select_cruise_throttle(). This is
        the true lower bound for a "permanently unreachable" verdict: conserve mode
        can always throttle down this far to stretch a tight budget, so a hard
        infeasibility check must rate distances against this, not the calibrated
        self.wh_per_meter (which reflects a *typical* cruise throttle, not the floor).
        """
        return self._drive_power_watts(self.MIN_SPEEDMODE_THROTTLE) / self._drive_speed_m_per_hour(self.MIN_SPEEDMODE_THROTTLE)

    def calculate_trip_energy(self, target_coords, planned_drill_units=0, planned_scans=1, planned_construction_progress=0.0, wh_per_meter=None):
        """
        Accurately calculates total energy required for a round-trip expedition:
        1. Energy to drive to target: dist_to_target * wh_per_meter
        2. Energy to scan & survey: planned_scans * SONAR_WH_BUDGET
        3. Energy to mine: planned_drill_units * MINE_WH_PER_UNIT
        4. Energy to build: planned_construction_progress * wh_per_progress
        5. Energy to drive to nearest charging station from target: dist_target_to_nearest_cs * wh_per_meter
        6. Safety buffer (35% margin) + hard emergency floor (8 Wh)

        wh_per_meter overrides the calibrated per-vehicle rate for the drive legs --
        pass self.minimum_wh_per_meter() to test best-case feasibility at the
        speedmode throttle floor rather than typical cruising cost. Defaults to
        the calibrated self.wh_per_meter.
        """
        rate = wh_per_meter if wh_per_meter is not None else self.wh_per_meter
        current_pos = self.get_position()
        dist_outbound = self.distance_between(current_pos, target_coords)
        nearest_cs_from_target, _ = self.get_nearest_charging_station(from_coords=target_coords)
        dist_inbound = self.distance_between(target_coords, nearest_cs_from_target)

        drive_out_wh = dist_outbound * rate
        drive_home_wh = dist_inbound * rate
        sonar_wh = planned_scans * self.SONAR_WH_BUDGET
        mining_wh = planned_drill_units * self.MINE_WH_PER_UNIT
        construction_wh = planned_construction_progress * self.wh_per_progress

        net_expedition_wh = drive_out_wh + drive_home_wh + sonar_wh + mining_wh + construction_wh
        buffered_expedition_wh = net_expedition_wh * self.SAFETY_MARGIN_MULTIPLIER
        total_required_wh = buffered_expedition_wh + self.MIN_EMERGENCY_RESERVE_WH

        curr_wh, cap_wh, lvl = self.get_battery()

        return {
            "dist_outbound": dist_outbound,
            "dist_inbound": dist_inbound,
            "nearest_cs_coords": nearest_cs_from_target,
            "drive_out_wh": drive_out_wh,
            "drive_home_wh": drive_home_wh,
            "sonar_wh": sonar_wh,
            "mining_wh": mining_wh,
            "construction_wh": construction_wh,
            "net_expedition_wh": net_expedition_wh,
            "total_required_wh": total_required_wh,
            "current_wh": curr_wh,
            "is_achievable": curr_wh >= total_required_wh
        }

    def energy_needed_to_reach(self, target_coords):
        """Calculates minimum energy required to reach target coordinates with safety buffer."""
        dist = self.distance_between(self.get_position(), target_coords)
        drive_wh = dist * self.wh_per_meter
        return (drive_wh * self.SAFETY_MARGIN_MULTIPLIER) + self.MIN_EMERGENCY_RESERVE_WH

    def energy_needed_to_reach_base(self):
        """Calculates energy required to drive back to home base staging slot."""
        return self.energy_needed_to_reach(self.assigned_slot_coords)

    def energy_needed_to_return_now(self):
        """
        Calculates minimum energy strictly required to drive to the nearest charging
        station right now. This is the true floor (uses minimum_wh_per_meter(), the
        speedmode throttle-floor rate) -- conserve mode can always crawl home at
        MIN_SPEEDMODE_THROTTLE to stretch a tight budget, so a panic/abort-safety
        check must not assume the typical calibrated self.wh_per_meter cost.
        """
        nearest_cs, _ = self.get_nearest_charging_station()
        dist_cs = self.distance_between(self.get_position(), nearest_cs)
        drive_wh = dist_cs * self.minimum_wh_per_meter()
        return (drive_wh * self.SAFETY_MARGIN_MULTIPLIER) + self.MIN_EMERGENCY_RESERVE_WH

    def calibrate_wh_per_meter(self, delta_dist, delta_wh):
        """Dynamically calibrates actual Wh/meter based on empirical driving performance."""
        if delta_dist > 5.0 and delta_wh > 0.1:
            observed_wh_per_m = delta_wh / delta_dist
            if 0.02 <= observed_wh_per_m <= 0.30:
                base_val = self.wh_per_meter if self.wh_per_meter is not None else self.WH_PER_METER_DEFAULT
                self.wh_per_meter = (base_val * 0.70) + (observed_wh_per_m * 0.30)
                archive.set(self.calibration_key(), self.wh_per_meter)

    def get_speed_mode(self):
        """Reads the fleet-wide vehicle.speedmode archive flag ("conserve" or "highspeed")."""
        mode = archive.get(SPEEDMODE_KEY, SPEEDMODE_CONSERVE)
        return mode if mode in (SPEEDMODE_CONSERVE, SPEEDMODE_HIGHSPEED) else SPEEDMODE_CONSERVE

    def _drive_speed_m_per_hour(self, throttle):
        """speed = 100 x throttle meters per game-hour."""
        return self.DRIVE_SPEED_M_PER_HOUR_PER_THROTTLE * throttle

    def _drive_power_watts(self, throttle):
        """power draw = 20 x throttle^2 watts."""
        return self.DRIVE_POWER_W_PER_THROTTLE_SQUARED * (throttle ** 2)

    def energy_wh_for_leg(self, distance_m, throttle):
        """Energy to cover distance_m at a constant throttle, from the speed/power model."""
        if distance_m <= 0 or throttle <= 0:
            return 0.0
        hours = distance_m / self._drive_speed_m_per_hour(throttle)
        return self._drive_power_watts(throttle) * hours

    def max_safe_throttle_for_leg(self, target_coords):
        """
        Highest throttle for which driving to target_coords still leaves enough
        charge (per the calibrated Wh/meter safety model) to reach the nearest
        charging station from there afterward. Returns 0.0 if even the slowest
        throttle would not leave a safe reserve.
        """
        distance = self.distance_to(target_coords[0], target_coords[1])
        if distance <= 0:
            return self.MAX_SPEEDMODE_THROTTLE

        curr_wh, _, _ = self.get_battery()
        nearest_cs, _ = self.get_nearest_charging_station(from_coords=target_coords)
        reserve_needed = (self.distance_between(target_coords, nearest_cs) * self.wh_per_meter * self.SAFETY_MARGIN_MULTIPLIER) + self.MIN_EMERGENCY_RESERVE_WH
        available_for_leg = curr_wh - reserve_needed
        if available_for_leg <= 0:
            return 0.0

        # energy_wh_for_leg(distance, t) reduces to (power_coeff / speed_coeff) * t * distance
        wh_per_throttle_unit = (self.DRIVE_POWER_W_PER_THROTTLE_SQUARED / self.DRIVE_SPEED_M_PER_HOUR_PER_THROTTLE) * distance
        if wh_per_throttle_unit <= 0:
            return self.MAX_SPEEDMODE_THROTTLE
        return max(0.0, min(self.MAX_SPEEDMODE_THROTTLE, available_for_leg / wh_per_throttle_unit))

    def select_cruise_throttle(self, target_x, target_y):
        """
        Picks this leg's driving throttle from the vehicle.speedmode archive flag:
        - "conserve" (default): self.cruise_throttle (50% by default) unless that
          would not leave a safe reserve to reach a charging station from the
          destination, in which case throttle down to whatever is safe (10% floor).
        - "highspeed": the highest throttle (up to 100%) that still leaves a safe
          reserve, so the task finishes as fast as the battery allows.
        """
        mode = self.get_speed_mode()
        max_safe = self.max_safe_throttle_for_leg((target_x, target_y))

        if mode == SPEEDMODE_HIGHSPEED:
            return max(self.MIN_SPEEDMODE_THROTTLE, min(self.MAX_SPEEDMODE_THROTTLE, max_safe))

        baseline = min(self.cruise_throttle, self.MAX_SPEEDMODE_THROTTLE)
        if max_safe >= baseline:
            return baseline
        return max(self.MIN_SPEEDMODE_THROTTLE, min(baseline, max_safe))

    def get_all_charging_stations(self):
        """
        Discovers every deployed Vehicle Charging Station across all owned outposts
        (outpost_network.outposts() already includes home), filtered by exact
        type_id so any number of stations is found regardless of id numbering.
        Returns a list of dicts: [{"id": str, "coords": (float, float), "component": obj}]
        """
        stations = []
        found_ids = set()

        outpost_net = get_component("outpost_network")
        if outpost_net and hasattr(outpost_net, "outposts"):
            try:
                outposts = outpost_net.outposts()
            except Exception:
                outposts = []

            for op in outposts:
                if not hasattr(op, "buildings"):
                    continue
                try:
                    buildings = op.buildings(CHARGING_STATION_TYPE_ID)
                except Exception:
                    continue
                for b in buildings:
                    b_id = getattr(b, "id", "")
                    if not b_id or b_id in found_ids:
                        continue
                    pos = self.extract_coords(getattr(b, "position", None))
                    if not pos:
                        continue
                    found_ids.add(b_id)
                    stations.append({
                        "id": b_id,
                        "coords": pos,
                        "component": get_component(b_id) or b
                    })

        return stations

    def get_nearest_charging_station(self, from_coords=None):
        """
        Returns the closest known charging station tuple: (coords, station_info_dict).
        If no station is detected, falls back to (self.home_coords, {}).
        """
        ref_coords = from_coords if from_coords is not None else self.get_position()
        stations = self.get_all_charging_stations()
        if not stations:
            fallback = self.get_charging_station_coords() or self.home_coords
            return fallback, {"id": "home_slot", "coords": fallback, "component": None}

        best_station = min(
            stations,
            key=lambda st: self.distance_between(ref_coords, st["coords"])
        )
        return best_station["coords"], best_station

    def get_charging_station_coords(self):
        """Locates the primary base charging station's exact position if available."""
        outpost_net = get_component("outpost_network")
        if outpost_net and hasattr(outpost_net, "home"):
            try:
                home = outpost_net.home()
                if home and hasattr(home, "buildings"):
                    for b in home.buildings(CHARGING_STATION_TYPE_ID):
                        pos = self.extract_coords(getattr(b, "position", None))
                        if pos:
                            return pos
            except Exception:
                pass
        return None

    def get_home_slot_coords(self):
        """
        Calculates the base / charging station staging coordinates for this vehicle.
        All vehicles dock within the ~2m common service area of base & charging station.
        """
        cs_pos = self.get_charging_station_coords()
        if cs_pos:
            return cs_pos
        return self.home_coords

    def recharge_at_station(self, target_level=1.0, station_coords=None, station_id=None):
        """
        Parks at Vehicle Charging Station / base staging slot and charges until target level.
        Cooperates with the station controller (charging_station_*.py) which handles hardware
        charge() calls locally.
        """
        curr_wh, cap_wh, lvl = self.get_battery()
        if lvl >= target_level - 0.02:
            print(f"[{self.name}] Battery already charged ({lvl*100:.0f}%).")
            return True

        cs = None
        if station_coords is None:
            station_coords, st_info = self.get_nearest_charging_station()
            if not station_id:
                station_id = st_info.get("id")
            cs = st_info.get("component")
        else:
            station_coords = (float(station_coords[0]), float(station_coords[1]))
            if station_id:
                cs = get_component(station_id)
            if not cs:
                for st in self.get_all_charging_stations():
                    if self.distance_between(st["coords"], station_coords) < 2.0:
                        cs = st.get("component")
                        if not station_id:
                            station_id = st.get("id")
                        break

        if not cs:
            if station_id:
                cs = get_component(station_id)
            if not cs:
                stations = self.get_all_charging_stations()
                if stations:
                    fallback = stations[0]
                    cs = fallback.get("component")
                    if not station_id:
                        station_id = fallback.get("id")

        cs_coords = station_coords or self.get_charging_station_coords() or self.home_coords

        # Verify whether vehicle is actually inside the station's docked set
        is_docked = False
        if cs and hasattr(cs, "get_docked"):
            try:
                docked_fn = getattr(cs, "get_docked")
                is_docked = self.name in docked_fn()
            except Exception:
                pass

        if not is_docked:
            dist_to_cs = self.distance_to(cs_coords[0], cs_coords[1])
            if dist_to_cs > 1.2:
                print(f"[{self.name}] Position is {dist_to_cs:.1f}m from charging station '{station_id or 'station'}'. Driving to docking pad...")
                self.drive_to(cs_coords[0], cs_coords[1], precision=1.0)
            else:
                self.return_to_base()
                self.drive_to(cs_coords[0], cs_coords[1], precision=1.0)

        if hasattr(self.vehicle, "nav"):
            try:
                self.vehicle.nav.brake()
            except Exception:
                pass

        sleep(0.5)
        self.publish_telemetry("CHARGING")
        print(f"[{self.name}] Docked at station '{station_id or 'station'}'. Waiting for charge ({lvl*100:.0f}% -> {target_level*100:.0f}%)...")

        wait_cycles = 0
        last_reported_lvl = lvl

        while True:
            curr_wh, cap_wh, lvl = self.get_battery()
            if lvl >= target_level - 0.01:
                print(f"[{self.name}] Charging complete ({curr_wh:.1f} Wh, {lvl*100:.0f}%).")
                break

            if abs(lvl - last_reported_lvl) >= 0.10:
                print(f"[{self.name}] Charging in progress... ({lvl*100:.0f}%, {curr_wh:.1f} Wh)")
                last_reported_lvl = lvl

            wait_cycles += 1
            if wait_cycles % 5 == 0 and cs:
                try:
                    get_docked_fn = getattr(cs, "get_docked", None)
                    docked = get_docked_fn() if get_docked_fn else []
                    if self.name not in docked:
                        print(f"[{self.name}] Not yet registered in station dock area. Re-aligning to charging station ({cs_coords})...")
                        self.drive_to(cs_coords[0], cs_coords[1], precision=1.0)
                        if hasattr(self.vehicle, "nav"):
                            self.vehicle.nav.brake()
                    else:
                        get_active_fn = getattr(cs, "get_active", None)
                        get_queue_fn = getattr(cs, "get_queue", None)
                        active = get_active_fn() if get_active_fn else []
                        queued = get_queue_fn() if get_queue_fn else []
                        if self.name not in active and self.name not in queued:
                            st_script = f"{station_id}.py" if station_id and "charging_station" in station_id else "charging_station_1.py"
                            print(f"[{self.name}] Advisory: Vehicle is docked, but charging station '{station_id}' has not queued it yet. Ensure '{st_script}' is running!")
                            try:
                                notify(f"[{self.name}] Docked and waiting. Ensure '{st_script}' is running!", level="info", duration_seconds=8.0)
                            except Exception:
                                pass
                except Exception:
                    pass

            sleep(2.0)

        return True
