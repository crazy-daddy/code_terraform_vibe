# Vehicle mixin: point-to-point driving, battery-floor enforcement, stall
# recovery, and multi-stop recharge routing. Shared by Rover and Pioneer via
# VehicleController (lib/vehicle.py).


class VehicleNavigationMixin:
    """
    Navigation and driving behavior mixed into VehicleController. Depends on
    energy budgeting (VehicleEnergyMixin) for battery-floor checks and on
    self.vehicle.nav for the underlying NavModule.
    """

    def get_position(self):
        """Returns (x, y) tuple of vehicle's current coordinates."""
        try:
            pos = self.vehicle.nav.get_position()
            return (pos.x, pos.y)
        except Exception:
            return self.assigned_slot_coords

    def distance_between(self, p1, p2):
        dx = p1[0] - p2[0]
        dy = p1[1] - p2[1]
        return (dx * dx + dy * dy) ** 0.5

    def distance_to(self, x, y):
        pos = self.get_position()
        return self.distance_between(pos, (x, y))

    def distance_to_home(self):
        return self.distance_to(self.assigned_slot_coords[0], self.assigned_slot_coords[1])

    def drive_timeout_ticks(self, distance, throttle, safety_multiplier=2.0, min_ticks=3000):
        """
        Real-time navigation timeout budget for a leg of this distance at this
        throttle. sleep() (and this loop's tick counter) run in *real* seconds,
        scaled by the world-clock's day-length pacing (Clock.real_seconds_per_hour(),
        ~25 real sec/world-hour by default) -- not world-clock hours directly. A
        flat timeout was tuned for the old fixed ~50% cruise throttle; conserve
        mode can now drop to MIN_SPEEDMODE_THROTTLE (5x slower), so the budget
        must scale with the actual expected travel time, not a constant.
        """
        speed_m_per_hour = self._drive_speed_m_per_hour(max(throttle, self.MIN_SPEEDMODE_THROTTLE))
        if speed_m_per_hour <= 0 or distance <= 0:
            return min_ticks

        real_seconds_per_hour = 25.0  # default 10-min/day pacing fallback
        clock = get_component("clock")
        if clock and hasattr(clock, "real_seconds_per_hour"):
            try:
                real_seconds_per_hour = clock.real_seconds_per_hour()
            except Exception:
                pass

        expected_real_seconds = (distance / speed_m_per_hour) * real_seconds_per_hour * safety_multiplier
        return max(min_ticks, int(expected_real_seconds * 10))

    def drive_to(self, target_x, target_y, precision=1.5, timeout_ticks=None):
        """
        Drives vehicle toward target coordinates while enforcing:
        1. Continuous round-trip battery floor check.
        2. Heartbeat claim renewal.
        3. Dynamic wh_per_meter calibration.
        4. Stall / obstacle detection.
        """
        if not hasattr(self.vehicle, "nav"):
            print(f"[{self.name}] Error: No NavModule mounted!")
            return False

        start_wh, _, _ = self.get_battery()
        start_pos = self.get_position()
        last_pos = start_pos
        stalled_cycles = 0

        # Pick this leg's throttle from vehicle.speedmode (conserve/highspeed)
        throttle = self.select_cruise_throttle(target_x, target_y)
        if timeout_ticks is None:
            timeout_ticks = self.drive_timeout_ticks(self.distance_between(start_pos, (target_x, target_y)), throttle)
        print(f"[{self.name}] Driving to ({target_x:.1f}, {target_y:.1f}) at {throttle*100:.0f}% throttle ({self.get_speed_mode()} mode).")

        # Set target and engage throttle
        res = self.vehicle.nav.set_target(target_x, target_y)
        if res.status != "ok":
            print(f"[{self.name}] Nav set_target rejected: {res.status} - {res.message}")
            return False

        t_res = self.vehicle.nav.set_throttle(throttle)
        if t_res.status != "ok":
            print(f"[{self.name}] Nav set_throttle rejected: {t_res.status} - {t_res.message}")
            self.vehicle.nav.brake()
            return False

        ticks = 0
        while ticks < timeout_ticks:
            sleep(1.0)
            ticks += 10

            if hasattr(self.vehicle, "is_being_rescued") and self.vehicle.is_being_rescued():
                self.vehicle.nav.brake()
                print(f"[{self.name}] Rescue in progress; navigation suspended.")
                return False

            curr_pos = self.get_position()
            curr_wh, _, _ = self.get_battery()
            dist_remaining = self.vehicle.nav.get_distance_to(target_x, target_y) if hasattr(self.vehicle.nav, "get_distance_to") else self.distance_to(target_x, target_y)

            if self.current_target_key:
                self.refresh_claim(self.current_target_key)

            if dist_remaining <= precision:
                self.vehicle.nav.brake()
                total_dist = self.distance_between(start_pos, curr_pos)
                wh_used = start_wh - curr_wh
                self.calibrate_wh_per_meter(total_dist, wh_used)
                return True

            energy_needed = self.energy_needed_to_return_now()
            if curr_wh <= energy_needed:
                print(f"[{self.name}] Battery threshold reached ({curr_wh:.1f} Wh left, {energy_needed:.1f} Wh required to return). Aborting trip!")
                self.vehicle.nav.brake()
                return False
            nearest_cs, _ = self.get_nearest_charging_station()
            is_driving_to_station = (
                self.distance_between((target_x, target_y), nearest_cs) <= 3.0
                or self.distance_between((target_x, target_y), self.assigned_slot_coords) <= 3.0
            )
            dist_to_cs = self.distance_between(curr_pos, nearest_cs)
            if not is_driving_to_station and dist_to_cs > 3.0:
                energy_needed = self.energy_needed_to_return_now()
                if curr_wh <= energy_needed:
                    print(f"[{self.name}] Battery threshold reached ({curr_wh:.1f} Wh left, {energy_needed:.1f} Wh required to reach nearest station at {nearest_cs}). Aborting trip!")
                    self.vehicle.nav.brake()
                    return False

            # Stall detection: if vehicle hasn't moved >0.3m in 8 seconds
            step_dist = self.distance_between(last_pos, curr_pos)
            if step_dist < 0.3:
                stalled_cycles += 1
                if stalled_cycles >= 8:
                    print(f"[{self.name}] Vehicle appears stalled/stuck at {curr_pos}. Re-issuing drive command.")
                    self.vehicle.nav.brake()
                    sleep(0.5)
                    self.vehicle.nav.set_target(target_x, target_y)
                    self.vehicle.nav.set_throttle(throttle)
                    stalled_cycles = 0
            else:
                stalled_cycles = 0

            last_pos = curr_pos

        print(f"[{self.name}] Navigation timed out after {timeout_ticks} ticks.")
        self.vehicle.nav.brake()
        return False

    def drive_with_recharge(self, target_x, target_y, precision=1.5, max_stops=5):
        """
        Drives to (target_x, target_y), planning intermediate stops at charging stations
        along the route if the direct trip exceeds available or single-charge battery range.
        """
        stops = 0
        while stops < max_stops:
            curr_pos = self.get_position()
            target_coords = (float(target_x), float(target_y))
            dist_to_target = self.distance_between(curr_pos, target_coords)

            if dist_to_target <= precision:
                return True

            curr_wh, cap_wh, _ = self.get_battery()
            energy_to_target = self.energy_needed_to_reach(target_coords)
            nearest_cs_from_target, _ = self.get_nearest_charging_station(from_coords=target_coords)
            energy_target_to_cs = (self.distance_between(target_coords, nearest_cs_from_target) * self.wh_per_meter * self.SAFETY_MARGIN_MULTIPLIER) + self.MIN_EMERGENCY_RESERVE_WH
            total_required = energy_to_target + energy_target_to_cs

            if curr_wh >= total_required:
                reached = self.drive_to(target_x, target_y, precision=precision)
                return reached

            # Find an intermediate charging station closer to target that we can currently reach
            stations = self.get_all_charging_stations()
            best_station = None
            best_progress = 0.0

            for st in stations:
                st_coords = st["coords"]
                dist_to_st = self.distance_between(curr_pos, st_coords)
                if dist_to_st < 2.0:
                    continue

                energy_to_st = (dist_to_st * self.wh_per_meter * self.SAFETY_MARGIN_MULTIPLIER) + self.MIN_EMERGENCY_RESERVE_WH
                if curr_wh < energy_to_st:
                    continue

                dist_st_to_target = self.distance_between(st_coords, target_coords)
                progress = dist_to_target - dist_st_to_target
                if progress > 3.0 and progress > best_progress:
                    best_progress = progress
                    best_station = st

            if best_station:
                st_coords = best_station["coords"]
                st_id = best_station.get("id", "station")
                print(f"[{self.name}] Destination ({target_x:.1f}, {target_y:.1f}) exceeds direct battery ({curr_wh:.1f} Wh < {total_required:.1f} Wh). Stopping at intermediate station '{st_id}' at {st_coords} to recharge.")
                reached = self.drive_to(st_coords[0], st_coords[1], precision=1.0)
                if not reached:
                    print(f"[{self.name}] Failed to reach intermediate station '{st_id}'.")
                    return False
                self.recharge_at_station(target_level=1.0, station_coords=st_coords, station_id=best_station.get("id"))
                stops += 1
                continue
            else:
                nearest_cs, n_info = self.get_nearest_charging_station()
                dist_near_cs = self.distance_between(curr_pos, nearest_cs)
                if dist_near_cs > 2.0 and curr_wh < (cap_wh * 0.90):
                    print(f"[{self.name}] Topping off at nearest station '{n_info.get('id', 'station')}' before proceeding.")
                    reached = self.drive_to(nearest_cs[0], nearest_cs[1], precision=1.0)
                    if reached:
                        self.recharge_at_station(target_level=1.0, station_coords=nearest_cs)
                        stops += 1
                        continue

                return self.drive_to(target_x, target_y, precision=precision)

        return self.drive_to(target_x, target_y, precision=precision)

    def return_to_base(self):
        """Safely drives back to the vehicle's assigned base staging slot, using intermediate charging if needed."""
        self.publish_telemetry("RETURNING_HOME")
        slot_x, slot_y = self.get_home_slot_coords()
        self.assigned_slot_coords = (slot_x, slot_y)
        print(f"[{self.name}] Returning to base slot ({slot_x:.1f}, {slot_y:.1f})...")
        reached = self.drive_with_recharge(slot_x, slot_y, precision=1.0)

        if self.current_target_key:
            self.release_target_claim(self.current_target_key)

        return reached

    def return_to_nearest_station(self):
        """Drives to the nearest charging station in the network to recharge."""
        st_coords, st_info = self.get_nearest_charging_station()
        st_id = st_info.get("id", "charging_station")
        print(f"[{self.name}] Heading to nearest charging station '{st_id}' at {st_coords}...")
        self.publish_telemetry("RETURNING_TO_STATION")
        reached = self.drive_to(st_coords[0], st_coords[1], precision=1.0)
        return reached
