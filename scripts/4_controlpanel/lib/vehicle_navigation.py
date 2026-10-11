import geometry
from swallow import swallowed
import game_clock
import game_rules
# Vehicle mixin: point-to-point driving, battery-floor enforcement, stall
# recovery and the direct drive to the nearest station. Shared by Rover and
# Pioneer via VehicleController (lib/vehicle.py); return_to_base is in
# lib/vehicle_charging.py because it routes through charging stations.


from typing import TYPE_CHECKING
from tree_console import flush_all, method_block

if TYPE_CHECKING:
    from vehicle import VehicleController

class VehicleNavigationMixin:
    """
    Navigation and driving behavior mixed into VehicleController. Depends on
    energy budgeting (VehicleEnergyMixin) for battery-floor checks and on
    self.vehicle.nav for the underlying NavModule.
    """

    @property
    def _host(self) -> "VehicleController":
        return self  # type: ignore[return-value]

    def get_position(self):
        """Returns (x, y) tuple of vehicle's current coordinates."""
        try:
            pos = self._host.vehicle.nav.get_position()
            return (pos.x, pos.y)
        except Exception as error:
            swallowed("vehicle_navigation.VehicleNavigationMixin.get_position: self._host.vehicle.nav.get_position", error)
            return self._host.assigned_slot_coords

    def distance_between(self, p1, p2):
        return geometry.distance(p1, p2)

    def distance_to(self, x, y):
        pos = self.get_position()
        return self.distance_between(pos, (x, y))

    def distance_to_home(self):
        return self.distance_to(self._host.assigned_slot_coords[0], self._host.assigned_slot_coords[1])

    def is_at_base(self, threshold=3.0):
        """
        True when parked at/near the assigned base staging slot. Loops use this
        to gate one-time-per-visit actions (top-off charging, restocking) so
        they only fire when actually at base, not mid-trip in the field.
        """
        return self.distance_to_home() <= threshold

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
        speed_m_per_hour = self._host._drive_speed_m_per_hour(max(throttle, self._host.MIN_SPEEDMODE_THROTTLE))
        if speed_m_per_hour <= 0 or distance <= 0:
            return min_ticks

        seconds_per_hour = game_clock.real_seconds_per_hour(where="vehicle_navigation.drive_timeout_ticks")
        expected_real_seconds = (distance / speed_m_per_hour) * seconds_per_hour * safety_multiplier
        return max(min_ticks, int(expected_real_seconds * game_rules.TICKS_PER_SECOND))

    def drive_to(self, target_x, target_y, precision=1.5, timeout_ticks=None):
        """
        Drives vehicle toward target coordinates while enforcing:
        1. Continuous round-trip battery floor check.
        2. Heartbeat claim renewal.
        3. Stall / obstacle detection.
        """
        self._host.log.start(f"[{self._host.name}] Drive leg to ({target_x:.1f}, {target_y:.1f})")
        arrived = self._drive_leg(target_x, target_y, precision, timeout_ticks)
        self._host.log.end(f"[{self._host.name}] Drive leg {'arrived' if arrived else 'aborted'}")
        return arrived

    @method_block(lambda self, *_, **__: f"[{self._host.name}] _drive_leg")
    def _drive_leg(self, target_x, target_y, precision, timeout_ticks):
        """Body of drive_to(); returns True on arrival within precision."""
        entry_tick = self._host.get_current_tick()
        self._host.log.trace(f"drive_to(target=({target_x:.1f}, {target_y:.1f}), precision={precision}, timeout_ticks={timeout_ticks}) called at tick {entry_tick}.")

        if not hasattr(self._host.vehicle, "nav"):
            self._host.log.level("error").print(f"[{self._host.name}] Error: No NavModule mounted!")
            return False

        start_pos = self.get_position()
        last_pos = start_pos
        stalled_cycles = 0
        stall_recoveries = 0

        # Pick this leg's throttle from self.cruise_throttle (the
        # archive-backed default_cruise_throttle()), capped
        # down only as far as needed for a safe return reserve.
        throttle = self._host.select_cruise_throttle(target_x, target_y)
        if timeout_ticks is None:
            timeout_ticks = self.drive_timeout_ticks(self.distance_between(start_pos, (target_x, target_y)), throttle)
        self._host.log.print(f"[{self._host.name}] Driving to ({target_x:.1f}, {target_y:.1f}) at {throttle*100:.0f}% throttle (cruise_throttle={self._host.cruise_throttle*100:.0f}%).")

        # Destination itself is a charging station/base slot: the return-reserve
        # abort check below must never apply here, or the vehicle could abort its
        # own rescue trip for "not enough energy to reach a charging station"
        # while already driving straight to one.
        nearest_cs, _ = self._host.get_nearest_charging_station()
        is_driving_to_station = (
            self.distance_between((target_x, target_y), nearest_cs) <= 3.0
            or self.distance_between((target_x, target_y), self._host.assigned_slot_coords) <= 3.0
        )

        # Set target and engage throttle
        res = self._host.vehicle.nav.set_target(target_x, target_y)
        if res.status != "ok":
            self._host.log.level("warn").print(f"[{self._host.name}] Nav set_target rejected: {res.status} - {res.message}")
            self._host.log.trace(f"drive_to() -> False (set_target rejected), elapsed {self._host.get_current_tick() - entry_tick} ticks.")
            return False

        t_res = self._host.vehicle.nav.set_throttle(throttle)
        if t_res.status != "ok":
            self._host.log.level("warn").print(f"[{self._host.name}] Nav set_throttle rejected: {t_res.status} - {t_res.message}")
            self._host.vehicle.nav.brake()
            self._host.log.trace(f"drive_to() -> False (set_throttle rejected), elapsed {self._host.get_current_tick() - entry_tick} ticks.")
            return False

        ticks = 0
        while ticks < timeout_ticks:
            flush_all()
            sleep(1.0)
            ticks += 10

            if hasattr(self._host.vehicle, "is_being_rescued") and self._host.vehicle.is_being_rescued():
                self._host.vehicle.nav.brake()
                self._host.log.level("warn").print(f"[{self._host.name}] Rescue in progress; navigation suspended.")
                self._host.log.trace(f"drive_to() -> False (rescue in progress), elapsed {self._host.get_current_tick() - entry_tick} ticks.")
                return False

            # Skipped when driving to the station/base itself, same reasoning as the
            # return-reserve check below -- recall must never block the trip home
            # it is asking for, or the vehicle deadlocks aborting its own recall.
            if self._host.is_recalled() and not is_driving_to_station:
                self._host.vehicle.nav.brake()
                self._host.log.level("warn").print(f"[{self._host.name}] Recall requested mid-trip; aborting to return to base.")
                self._host.log.trace(f"drive_to() -> False (recalled mid-trip), elapsed {self._host.get_current_tick() - entry_tick} ticks.")
                return False

            curr_pos = self.get_position()
            curr_wh, _, _ = self._host.get_battery()
            dist_remaining = self._host.vehicle.nav.get_distance_to(target_x, target_y) if hasattr(self._host.vehicle.nav, "get_distance_to") else self.distance_to(target_x, target_y)

            if self._host.current_target_key:
                self._host.refresh_claim(self._host.current_target_key)

            if dist_remaining <= precision:
                self._host.vehicle.nav.brake()
                self._host.log.trace(f"drive_to() -> True (arrived, {dist_remaining:.2f}m <= precision {precision}), elapsed {self._host.get_current_tick() - entry_tick} ticks.")
                return True

            # Skipped when the destination itself is the charging station/base slot
            # (or we're already essentially there) -- arriving there is the recovery,
            # so this must never abort the very trip meant to reach safety.
            if not is_driving_to_station and self.distance_between(curr_pos, nearest_cs) > 3.0:
                energy_needed = self._host.energy_needed_to_return_now()
                if curr_wh <= energy_needed:
                    self._host.log.level("warn").print(f"[{self._host.name}] Battery threshold reached ({curr_wh:.1f} Wh left, {energy_needed:.1f} Wh required to reach nearest station at {nearest_cs}). Aborting trip!")
                    self._host.vehicle.nav.brake()
                    self._host.log.trace(f"drive_to() -> False (battery abort), elapsed {self._host.get_current_tick() - entry_tick} ticks.")
                    return False

            # Stall detection: if vehicle hasn't moved >0.3m in 8 seconds. This
            # applies regardless of is_driving_to_station -- being stuck means
            # zero progress either way, and the throttle stays engaged (drawing
            # power the whole time per the speed/power model) even while stalled,
            # so an unbounded retry loop can drain the battery to nothing for no
            # progress, especially on a station-bound leg where the low-battery
            # abort above is deliberately skipped.
            step_dist = self.distance_between(last_pos, curr_pos)
            if step_dist < 0.3:
                stalled_cycles += 1
                self._host.log.debug(f"Stall check: moved {step_dist:.2f}m this cycle (< 0.3m threshold), stalled_cycles={stalled_cycles}/8, stall_recoveries={stall_recoveries}/3.")
                if stalled_cycles >= 8:
                    stall_recoveries += 1
                    if stall_recoveries > 3:
                        self._host.log.level("warn").print(f"[{self._host.name}] Stall recovery failed {stall_recoveries - 1} times at {curr_pos}; giving up to avoid draining the battery further.")
                        self._host.vehicle.nav.brake()
                        self._host.log.trace(f"drive_to() -> False (stall recovery exhausted), elapsed {self._host.get_current_tick() - entry_tick} ticks.")
                        return False
                    # Drop to the floor throttle on retry to minimize further drain
                    # while stuck (and sometimes a gentler approach clears the obstacle).
                    throttle = self._host.MIN_SPEEDMODE_THROTTLE
                    self._host.log.level("warn").print(f"[{self._host.name}] Vehicle appears stalled/stuck at {curr_pos}. Re-issuing drive command at {throttle*100:.0f}% throttle (attempt {stall_recoveries}/3).")
                    self._host.vehicle.nav.brake()
                    flush_all()
                    sleep(0.5)
                    self._host.vehicle.nav.set_target(target_x, target_y)
                    self._host.vehicle.nav.set_throttle(throttle)
                    stalled_cycles = 0
            else:
                if stalled_cycles > 0 or stall_recoveries > 0:
                    self._host.log.debug(f"Stall check: moved {step_dist:.2f}m this cycle, resetting stalled_cycles/stall_recoveries from {stalled_cycles}/{stall_recoveries} to 0/0.")
                stalled_cycles = 0
                stall_recoveries = 0

            last_pos = curr_pos

        self._host.log.level("warn").print(f"[{self._host.name}] Navigation timed out after {timeout_ticks} ticks.")
        self._host.vehicle.nav.brake()
        self._host.log.trace(f"drive_to() -> False (timed out after {timeout_ticks} ticks), elapsed {self._host.get_current_tick() - entry_tick} ticks.")
        return False

    def leg_too_slow(self, target_coords, min_throttle):
        """
        True when a direct leg to target_coords, even on a full battery,
        could only be driven below min_throttle (False when min_throttle is
        None). See drive_with_recharge().
        """
        if min_throttle is None:
            return False
        ceiling = self.full_battery_throttle(target_coords)
        if ceiling >= min_throttle:
            return False
        self._host.log.print(f"[{self._host.name}] Skipping ({target_coords[0]:.1f}, {target_coords[1]:.1f}): a full battery allows only {ceiling*100:.0f}% throttle there, below the {min_throttle*100:.0f}% minimum.")
        return True

    def full_battery_throttle(self, target_coords):
        """max_safe_throttle_for_leg() from here to target_coords on a full battery."""
        _, cap_wh, _ = self._host.get_battery()
        return self._host.max_safe_throttle_for_leg(target_coords, curr_wh=cap_wh)

    def return_to_nearest_station(self):
        """Drives to the nearest charging station in the network to recharge."""
        st_coords, st_info = self._host.get_nearest_charging_station()
        st_id = st_info.get("id", "charging_station")
        self._host.log.start(f"[{self._host.name}] Heading to nearest charging station '{st_id}' at {st_coords}")
        self._host.publish_telemetry("RETURNING_TO_STATION")
        reached = self.drive_to(st_coords[0], st_coords[1], precision=1.0)
        self._host.log.end(f"[{self._host.name}] {'Reached' if reached else 'Did not reach'} station '{st_id}'")
        return reached
