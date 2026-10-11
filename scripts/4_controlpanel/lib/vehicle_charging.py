# Vehicle mixin: charging. Docks and charges at Vehicle Charging Stations
# (recharge_at_station, balance_dock), routes long drives through
# intermediate stations (drive_with_recharge, return_to_base) and the one-block
# "drive to the nearest station and charge" helper (recharge_at_nearest). Layer 3 of the
# vehicle mixins (docs/plans/mixin_refactor/README.md): it drives (navigation)
# and budgets (energy); station discovery is in lib/charging_stations.py.
# Shared by Rover and Pioneer via VehicleController (lib/vehicle.py).

from typing import TYPE_CHECKING

import charging_stations
from components import charging_station
from script_parking import wake_for_visit
from swallow import swallowed
from tree_console import flush_all, method_block

if TYPE_CHECKING:
    from vehicle import VehicleController


class VehicleChargingMixin:
    """
    Charging behavior mixed into VehicleController: park and charge at a
    station, balance docks inside an outpost, drive with intermediate
    recharge stops. Depends on VehicleEnergyMixin (battery, budgets,
    station wrappers) and VehicleNavigationMixin (drive_to, positions).
    """

    @property
    def _host(self) -> "VehicleController":
        return self  # type: ignore[return-value]

    def balance_dock(self):
        """
        Parked in an outpost with several charging stations: docks at the one
        with the fewest other vehicles per bay (ties: the current station,
        then id). Every station covers the whole outpost, so no driving is
        needed. Returns the station dict docked at, or None when not docked
        or the outpost has a single station.
        """
        current = self._host.current_station()
        stations = self._host.get_all_charging_stations()
        outpost = next((s.get("outpost") for s in stations if s["id"] == current), None)
        peers = [s for s in stations if outpost and s.get("outpost") == outpost]
        if len(peers) < 2:
            return None
        best = min(peers, key=lambda s: (charging_stations.station_load(s["component"], self._host.name), s["id"] != current, s["id"]))
        if best["id"] == current:
            return best
        try:
            status = self._host.vehicle.dock(best["id"]).status
        except Exception as error:
            swallowed("vehicle_charging.VehicleChargingMixin.balance_dock: vehicle.dock", error)
            return None
        if status != "ok":
            self._host.log.debug(f"[{self._host.name}] dock('{best['id']}'): {status}, staying at '{current}'.")
            return None
        self._host.log.print(f"[{self._host.name}] Docked at '{best['id']}' instead of busier '{current}'.")
        return best

    def recharge_at_station(self, target_level=1.0, station_coords=None, station_id=None):
        """
        Parks at Vehicle Charging Station / base staging slot and charges until target level.
        Cooperates with the station controller (charging_station_*.py) which handles hardware
        charge() calls locally.
        """
        curr_wh, _cap_wh, lvl = self._host.get_battery()
        if lvl >= target_level - 0.02:
            self._host.log.print(f"[{self._host.name}] Battery already charged ({lvl*100:.0f}%).")
            return True

        self._host.log.start(f"[{self._host.name}] Recharging ({lvl*100:.0f}% -> {target_level*100:.0f}%)")
        cs = None
        if station_coords is None:
            station_coords, st_info = self._host.get_nearest_charging_station()
            if not station_id:
                station_id = st_info.get("id")
            cs = st_info.get("component")
        else:
            station_coords = (float(station_coords[0]), float(station_coords[1]))
            if station_id:
                cs = charging_station(station_id)
            if not cs:
                for st in self._host.get_all_charging_stations():
                    if self._host.distance_between(st["coords"], station_coords) < 2.0:
                        cs = st.get("component")
                        if not station_id:
                            station_id = st.get("id")
                        break

        if not cs:
            if station_id:
                cs = charging_station(station_id)
            if not cs:
                stations = self._host.get_all_charging_stations()
                if stations:
                    fallback = stations[0]
                    cs = fallback.get("component")
                    if not station_id:
                        station_id = fallback.get("id")

        cs_coords = station_coords or self._host.home_coords
        # A parked station (lib/script_parking.py) is switched back on before we
        # drive there, and held awake while we wait below.
        if station_id and station_id != "home_slot":
            wake_for_visit(station_id, f"{self._host.name} coming to charge")
        self._host.log.debug(f"[{self._host.name}] recharge_at_station: station '{station_id or 'station'}' at {cs_coords}, controller {'found' if cs else 'missing'}.")

        if not self._host.current_station():
            # drive_to() already short-circuits instantly when already within
            # precision, so there's no need to special-case "close but not yet
            # registered docked" with a heavier self._host.return_to_base() detour
            # (which also drives to assigned_slot_coords, not necessarily
            # cs_coords, and releases the current target claim) -- just always
            # re-issue the drive command toward the actual station coords.
            dist_to_cs = self._host.distance_to(cs_coords[0], cs_coords[1])
            self._host.log.print(f"[{self._host.name}] Position is {dist_to_cs:.1f}m from charging station '{station_id or 'station'}'. Driving to docking pad...")
            self._host.drive_to(cs_coords[0], cs_coords[1], precision=1.0)

        if hasattr(self._host.vehicle, "nav"):
            try:
                self._host.vehicle.nav.brake()
            except Exception as error:
                swallowed("vehicle_charging.VehicleChargingMixin.recharge_at_station: self._host.vehicle.nav.brake", error)

        flush_all()
        sleep(0.5)
        # Charge where the game docked us, or at a less busy station in the same outpost.
        balanced = self._host.balance_dock()
        docked_id = balanced["id"] if balanced else self._host.current_station()
        if docked_id and docked_id != station_id:
            station_id = docked_id
            cs = balanced["component"] if balanced else (charging_station(docked_id) or cs)
            wake_for_visit(station_id, f"{self._host.name} coming to charge")
        self._host.publish_telemetry("CHARGING")
        self._host.log.print(f"[{self._host.name}] Docked at station '{station_id or 'station'}'. Waiting for charge ({lvl*100:.0f}% -> {target_level*100:.0f}%)...")

        wait_cycles = 0
        last_reported_lvl = lvl

        while True:
            curr_wh, _cap_wh, lvl = self._host.get_battery()
            if lvl >= target_level - 0.01:
                self._host.log.print(f"[{self._host.name}] Charging complete ({curr_wh:.1f} Wh, {lvl*100:.0f}%).")
                break

            if abs(lvl - last_reported_lvl) >= 0.10:
                self._host.log.print(f"[{self._host.name}] Charging in progress... ({lvl*100:.0f}%, {curr_wh:.1f} Wh)")
                last_reported_lvl = lvl

            wait_cycles += 1
            if wait_cycles % 5 == 0 and station_id and station_id != "home_slot":
                wake_for_visit(station_id, f"{self._host.name} waiting to charge")
            if wait_cycles % 5 == 0 and cs:
                try:
                    if not self._host.current_station():
                        self._host.log.level("warn").print(f"[{self._host.name}] Not yet registered in station dock area. Re-aligning to charging station ({cs_coords})...")
                        self._host.drive_to(cs_coords[0], cs_coords[1], precision=1.0)
                        if hasattr(self._host.vehicle, "nav"):
                            self._host.vehicle.nav.brake()
                    else:
                        get_active_fn = getattr(cs, "get_active", None)
                        get_queue_fn = getattr(cs, "get_queue", None)
                        active = get_active_fn() if get_active_fn else []
                        queued = get_queue_fn() if get_queue_fn else []
                        if self._host.name not in active and self._host.name not in queued:
                            st_script = f"{station_id}.py" if station_id and "charging_station" in station_id else "charging_station_1.py"
                            self._host.log.level("warn").print(f"[{self._host.name}] Advisory: Vehicle is docked, but charging station '{station_id}' has not queued it yet. Ensure '{st_script}' is running!")
                            try:
                                notify(f"[{self._host.name}] Docked and waiting. Ensure '{st_script}' is running!", level="info", duration_seconds=8.0)
                            except Exception as error:
                                swallowed("vehicle_charging.VehicleChargingMixin.recharge_at_station: notify", error)
                except Exception as error:
                    swallowed("vehicle_charging.VehicleChargingMixin.recharge_at_station: get_docked_fn", error)

            flush_all()
            sleep(2.0)

        self._host.log.end(f"[{self._host.name}] Recharge finished at {lvl*100:.0f}%.")
        return True

    @method_block(lambda self, *_, **__: f"[{self._host.name}] drive_with_recharge")
    def drive_with_recharge(self, target_x, target_y, precision=1.5, max_stops=5, min_throttle=None):
        """
        Drives to (target_x, target_y), planning intermediate stops at charging stations
        along the route if the direct trip exceeds available or single-charge battery range.
        min_throttle: refuse (False) a last leg that even a full battery could
        only drive below this throttle, instead of crawling there at the
        speedmode floor. None (default) always drives.
        """
        entry_tick = self._host.get_current_tick()
        self._host.log.trace(f"drive_with_recharge(target=({target_x:.1f}, {target_y:.1f}), precision={precision}, max_stops={max_stops}) called at tick {entry_tick}.")
        stops = 0
        while stops < max_stops:
            curr_pos = self._host.get_position()
            target_coords = (float(target_x), float(target_y))
            dist_to_target = self._host.distance_between(curr_pos, target_coords)

            if dist_to_target <= precision:
                self._host.log.trace(f"drive_with_recharge() -> True (already within precision, {stops} stops made), elapsed {self._host.get_current_tick() - entry_tick} ticks.")
                return True

            curr_wh, cap_wh, _ = self._host.get_battery()
            energy_to_target = self._host.energy_needed_to_reach(target_coords)
            nearest_cs_from_target, _ = self._host.get_nearest_charging_station(from_coords=target_coords)
            energy_target_to_cs = (self._host.distance_between(target_coords, nearest_cs_from_target) * self._host.wh_per_meter_at_throttle(self._host.cruise_throttle) * self._host.SAFETY_MARGIN_MULTIPLIER) + self._host.MIN_EMERGENCY_RESERVE_WH
            total_required = energy_to_target + energy_target_to_cs
            self._host.log.debug(f"{curr_wh:.1f} Wh on board vs {total_required:.1f} Wh required ({energy_to_target:.1f} Wh to target + {energy_target_to_cs:.1f} Wh target->nearest CS); direct trip {'feasible' if curr_wh >= total_required else 'NOT feasible'}.")

            if curr_wh >= total_required:
                reached = self._host.drive_to(target_x, target_y, precision=precision)
                self._host.log.trace(f"drive_with_recharge() -> {reached} (direct leg, {stops} stops made), elapsed {self._host.get_current_tick() - entry_tick} ticks.")
                return reached

            # Find an intermediate charging station closer to target that we can currently reach
            stations = self._host.get_all_charging_stations()
            best_station = None
            best_progress = 0.0
            self._host.log.debug(f"direct trip infeasible, evaluating {len(stations)} known charging station(s) as intermediate stops.")

            for st in stations:
                st_coords = st["coords"]
                st_id = st.get("id", "station")
                dist_to_st = self._host.distance_between(curr_pos, st_coords)
                if dist_to_st < 2.0:
                    self._host.log.debug(f"Candidate station '{st_id}': rejected, already at/near it ({dist_to_st:.1f}m < 2.0m).")
                    continue

                energy_to_st = (dist_to_st * self._host.wh_per_meter_at_throttle(self._host.cruise_throttle) * self._host.SAFETY_MARGIN_MULTIPLIER) + self._host.MIN_EMERGENCY_RESERVE_WH
                if curr_wh < energy_to_st:
                    self._host.log.debug(f"Candidate station '{st_id}': rejected, unreachable ({curr_wh:.1f} Wh < {energy_to_st:.1f} Wh needed for {dist_to_st:.1f}m).")
                    continue

                dist_st_to_target = self._host.distance_between(st_coords, target_coords)
                progress = dist_to_target - dist_st_to_target
                if progress > 3.0 and progress > best_progress:
                    self._host.log.debug(f"Candidate station '{st_id}': accepted, progress={progress:.1f}m toward target (best so far).")
                    best_progress = progress
                    best_station = st
                else:
                    self._host.log.debug(f"Candidate station '{st_id}': rejected, progress={progress:.1f}m does not beat best_progress={best_progress:.1f}m (or <= 3.0m threshold).")

            if best_station:
                st_coords = best_station["coords"]
                st_id = best_station.get("id", "station")
                self._host.log.print(f"[{self._host.name}] Destination ({target_x:.1f}, {target_y:.1f}) exceeds direct battery ({curr_wh:.1f} Wh < {total_required:.1f} Wh). Stopping at intermediate station '{st_id}' at {st_coords} to recharge.")
                reached = self._host.drive_to(st_coords[0], st_coords[1], precision=1.0)
                if not reached:
                    self._host.log.level("warn").print(f"[{self._host.name}] Failed to reach intermediate station '{st_id}'.")
                    self._host.log.trace(f"drive_with_recharge() -> False (failed to reach intermediate station), elapsed {self._host.get_current_tick() - entry_tick} ticks.")
                    return False
                self._host.recharge_at_station(target_level=1.0, station_coords=st_coords, station_id=best_station.get("id"))
                stops += 1
                continue
            else:
                nearest_cs, n_info = self._host.get_nearest_charging_station()
                dist_near_cs = self._host.distance_between(curr_pos, nearest_cs)
                self._host.log.debug(f"No viable intermediate station found; considering top-off at nearest station '{n_info.get('id', 'station')}' ({dist_near_cs:.1f}m away, battery {curr_wh:.1f}/{cap_wh:.1f} Wh).")
                if dist_near_cs > 2.0 and curr_wh < (cap_wh * 0.90):
                    self._host.log.print(f"[{self._host.name}] Topping off at nearest station '{n_info.get('id', 'station')}' before proceeding.")
                    reached = self._host.drive_to(nearest_cs[0], nearest_cs[1], precision=1.0)
                    if reached:
                        self._host.recharge_at_station(target_level=1.0, station_coords=nearest_cs)
                        stops += 1
                        continue

                if self._host.leg_too_slow(target_coords, min_throttle):
                    return False
                self._host.log.trace(f"drive_with_recharge() -> falling through to direct drive_to() (no station option available, {stops} stops made), elapsed {self._host.get_current_tick() - entry_tick} ticks.")
                return self._host.drive_to(target_x, target_y, precision=precision)

        if self._host.leg_too_slow((float(target_x), float(target_y)), min_throttle):
            return False
        self._host.log.debug(f"reached max_stops={max_stops}, attempting final direct drive_to() regardless of remaining budget.")
        return self._host.drive_to(target_x, target_y, precision=precision)

    def return_to_base(self):
        """Safely drives back to the vehicle's assigned base staging slot, using intermediate charging if needed."""
        self._host.publish_telemetry("RETURNING_HOME")
        slot_x, slot_y = self._host.get_home_slot_coords()
        self._host.assigned_slot_coords = (slot_x, slot_y)
        self._host.log.start(f"[{self._host.name}] Returning to base slot ({slot_x:.1f}, {slot_y:.1f})")
        reached = self.drive_with_recharge(slot_x, slot_y, precision=1.0)

        if self._host.mission is not None:
            self._host.release_target_claim(self._host.mission.target_key)

        self._host.log.end(f"[{self._host.name}] {'Back at base slot' if reached else 'Return to base incomplete'}")
        return reached

    def recharge_at_nearest(self, reason, outcome, station=None):
        """Drives to station (default: the nearest charging station) and charges to full, as one log block."""
        name = self._host.name
        self._host.log.start(f"[{name}] {reason}")
        if station is None:
            station, _ = self._host.get_nearest_charging_station()
        self._host.drive_to(station[0], station[1], precision=1.0)
        self._host.recharge_at_station(target_level=1.0, station_coords=station)
        self._host.log.end(f"[{name}] {outcome}")
