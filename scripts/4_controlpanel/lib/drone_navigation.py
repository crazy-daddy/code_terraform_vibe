# Drone mixin: thin wrappers around go_to()/go_to_station()/go_to_drill(),
# arrival polling, and stalled/scrambled detection.
#
# Drones are NOT vehicles in the game API sense -- no .drive/.nav, no
# terrain/stall handling of their own, route-based (go_to(x, y),
# go_to_station(name), go_to_drill(name)) rather than a blocking
# set_target()/set_throttle() drive loop. This mirrors
# vehicle_navigation.py's RESPONSIBILITIES (point-to-point travel,
# battery-floor enforcement, arrival confirmation, claim-heartbeat renewal
# mid-leg) without reusing any of its NavModule-specific implementation.

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from drone import DroneController

STRANDED_STATUSES = ("stalled_no_battery", "scrambled")


class DroneNavigationMixin:
    """
    Navigation/arrival polling mixed into DroneController. Depends on
    DroneEnergyMixin for battery-floor checks and DroneClaimsMixin for claim
    heartbeat renewal during a flight leg.
    """

    @property
    def _host(self) -> "DroneController":
        return self  # type: ignore[return-value]

    def position(self):
        """Returns (x, y) tuple of the drone's current coordinates."""
        try:
            pos = self._host.drone.position()
            return (float(pos.x), float(pos.y))
        except Exception:
            return getattr(self, "home_coords", (0.0, 0.0))

    def distance_between(self, p1, p2):
        dx = p1[0] - p2[0]
        dy = p1[1] - p2[1]
        return (dx * dx + dy * dy) ** 0.5

    def distance_to(self, x, y):
        return self.distance_between(self.position(), (x, y))

    def status(self):
        try:
            return self._host.drone.status()
        except Exception:
            return "idle"

    def is_stranded(self):
        """
        True while stalled_no_battery or scrambled -- both require
        drone_service rescue, unlike a ground vehicle's self-recoverable
        multi-stop recharge routing. Drones have no drive_with_recharge()
        equivalent: go_to() is a single fire-and-forget flight leg, so
        there's no self-recovery path from either state.
        """
        return self.status() in STRANDED_STATUSES

    def current_station(self):
        try:
            return self._host.drone.current_station()
        except Exception:
            return ""

    def current_drill(self):
        try:
            return self._host.drone.current_drill()
        except Exception:
            return ""

    def is_at(self, coords, precision=1.5):
        return self.distance_between(self.position(), coords) <= precision

    def flight_timeout_ticks(self, distance, throttle, safety_multiplier=2.0, min_ticks=1500):
        """
        Real-time timeout budget for a flight leg, mirroring
        vehicle_navigation.py's drive_timeout_ticks() but at drone cruise
        speed (300 m/h at throttle 1.0, linear in throttle -- no Sport Nav
        equivalent for drones).
        """
        speed_m_per_hour = 300.0 * max(throttle, self._host.MIN_SPEEDMODE_THROTTLE)
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

    def fly_to(self, target_x, target_y, precision=1.5, timeout_ticks=None):
        """
        Flies to (target_x, target_y) via go_to(), polling position()/battery
        each cycle. Unlike drive_to()'s NavModule throttle loop, go_to() is a
        single fire-and-forget command -- there's no per-cycle set_throttle()
        to reissue, just a route to confirm and a battery floor to enforce.
        Also detects a mid-flight rescue/scramble (is_stranded()) and bails
        out immediately, since only drone_service can recover from those.
        """
        target_coords = (float(target_x), float(target_y))
        self._host.log.trace(f"[{self._host.name}] fly_to({target_x:.1f}, {target_y:.1f}) entry from {self.position()}.")
        if self.is_at(target_coords, precision=precision):
            self._host.log.trace(f"[{self._host.name}] fly_to() exit: already at destination.")
            return True

        throttle = self._host.select_cruise_throttle(target_coords)
        distance = self.distance_to(target_x, target_y)
        if timeout_ticks is None:
            timeout_ticks = self.flight_timeout_ticks(distance, throttle)
        self._host.log.debug(f"[{self._host.name}] fly_to() leg: distance={distance:.1f}m, throttle={throttle*100:.0f}%, timeout_ticks={timeout_ticks}.")

        nearest_service, _ = self._host.get_nearest_drone_service()
        is_flying_to_service = self.distance_between(target_coords, nearest_service) <= 3.0

        self._host.log.print(f"[{self._host.name}] Flying to ({target_x:.1f}, {target_y:.1f}) at {throttle*100:.0f}% throttle (cruise_throttle={self._host.cruise_throttle*100:.0f}%).")
        res = self._host.drone.go_to(target_x, target_y)
        if res.status != "ok":
            self._host.log.level("warn").print(f"[{self._host.name}] go_to({target_x:.1f}, {target_y:.1f}) rejected: {res.status} - {res.message}")
            self._host.log.trace(f"[{self._host.name}] fly_to() exit: go_to() rejected ({res.status}).")
            return False
        # go_to() only sets the route -- throttle is a separate axis that
        # resets to 0 on the prior stop/completion/error, so it must be
        # (re)issued here or the drone will sit at the waypoint forever.
        self._host.drone.set_throttle(throttle)

        ticks = 0
        while ticks < timeout_ticks:
            sleep(1.0)
            ticks += 10

            if self.is_stranded():
                self._host.log.level("warn").print(f"[{self._host.name}] Drone {self.status()} mid-flight; awaiting drone_service rescue.")
                self._host.log.trace(f"[{self._host.name}] fly_to() exit: stranded ({self.status()}) after {ticks} ticks.")
                return False

            if self._host.current_target_key:
                self._host.refresh_biosite_claim(self._host.current_target_key)

            if self.is_at(target_coords, precision=precision):
                self._host.log.trace(f"[{self._host.name}] fly_to() exit: arrived after {ticks} ticks.")
                return True

            if ticks % 100 == 0:
                remaining = self.distance_to(target_x, target_y)
                self._host.log.debug(f"[{self._host.name}] fly_to() arrival-poll retry: {remaining:.1f}m remaining after {ticks}/{timeout_ticks} ticks.")

            # Skipped when flying to the drone_service itself -- arriving
            # there IS the recovery, so this must never abort the very trip
            # meant to reach safety (same reasoning as drive_to()'s
            # is_driving_to_station guard in vehicle_navigation.py).
            if not is_flying_to_service:
                curr_wh, _, _ = self._host.get_battery()
                energy_needed = self._host.energy_needed_to_return_now()
                if curr_wh <= energy_needed:
                    self._host.log.level("warn").print(f"[{self._host.name}] Battery threshold reached ({curr_wh:.1f} Wh left, {energy_needed:.1f} Wh required to reach nearest drone_service). Aborting flight.")
                    self._host.log.trace(f"[{self._host.name}] fly_to() exit: aborted on low battery after {ticks} ticks.")
                    return False

        self._host.log.level("warn").print(f"[{self._host.name}] Flight to ({target_x:.1f}, {target_y:.1f}) timed out after {timeout_ticks} ticks.")
        self._host.log.trace(f"[{self._host.name}] fly_to() exit: timed out after {ticks} ticks.")
        return False

    def fly_to_station(self, name, target_coords=None, timeout_ticks=1500):
        """
        Flies to a named Drone Depot/Drone Service Station via
        go_to_station(), confirming arrival via current_station() equal to
        the destination id (drone.md: the authoritative arrival check, even
        when go_to_station() was called with a display name).

        target_coords, when the caller already resolved them (e.g. from
        get_nearest_drone_service()/get_nearest_drone_depot()), feeds
        select_cruise_throttle()'s energy-safe cap -- a depot run isn't
        necessarily a power-safe "coming home" leg, so it still deserves the
        same reserve check as any other fly_to(). Falls back to the plain
        cruise_throttle baseline when coords aren't known.
        """
        if not name:
            return False
        self._host.log.trace(f"[{self._host.name}] fly_to_station('{name}') entry.")
        res = self._host.drone.go_to_station(name)
        if res.status != "ok":
            self._host.log.level("warn").print(f"[{self._host.name}] go_to_station('{name}') rejected: {res.status} - {res.message}")
            self._host.log.trace(f"[{self._host.name}] fly_to_station('{name}') exit: rejected ({res.status}).")
            return False
        if target_coords is not None:
            throttle = self._host.select_cruise_throttle(target_coords)
        else:
            throttle = min(self._host.cruise_throttle, self._host.MAX_SPEEDMODE_THROTTLE)
        self._host.drone.set_throttle(throttle)

        ticks = 0
        while ticks < timeout_ticks:
            sleep(1.0)
            ticks += 10
            if self.is_stranded():
                self._host.log.trace(f"[{self._host.name}] fly_to_station('{name}') exit: stranded ({self.status()}) after {ticks} ticks.")
                return False
            if self.current_station():
                self._host.log.trace(f"[{self._host.name}] fly_to_station('{name}') exit: docked after {ticks} ticks.")
                return True
            if ticks % 100 == 0:
                self._host.log.debug(f"[{self._host.name}] fly_to_station('{name}') arrival-poll retry: still not docked after {ticks}/{timeout_ticks} ticks.")

        self._host.log.level("warn").print(f"[{self._host.name}] go_to_station('{name}') timed out after {timeout_ticks} ticks.")
        self._host.log.trace(f"[{self._host.name}] fly_to_station('{name}') exit: timed out after {ticks} ticks.")
        return False

    def leave_station(self):
        """
        Releases the current station berth via undock() -- keeps exact
        position/cargo/modules and costs no flight energy (drone.md), unlike
        re-issuing a fly_to() to the same coordinates. Call this once a
        Drone Depot visit's unload is done, even with no follow-up task
        queued yet, so the bay frees up immediately for another drone
        waiting in "waiting_bay" rather than sitting occupied until this
        drone's next fly_to()/go_to_station() call happens to move it.
        No-op (and silent) if already undocked ("not_docked") or if an
        active Drone Service Station charge/rescue job still holds control
        ("busy") -- undock() must not interrupt those (drone.md).
        """
        station_id = self.current_station()
        if not station_id:
            return False
        try:
            res = self._host.drone.undock()
        except Exception as e:
            self._host.log.debug(f"[{self._host.name}] leave_station(): undock() call failed: {e}")
            return False
        if res.status == "ok":
            self._host.log.debug(f"[{self._host.name}] Left station berth '{station_id}' to free the bay.")
            return True
        if res.status not in ("not_docked", "busy"):
            self._host.log.level("warn").print(f"[{self._host.name}] undock() notice: {res.status} - {res.message}")
        return False

    def fly_to_drill(self, name, target_coords=None, timeout_ticks=1500):
        """
        Flies to a named field Mining Drill via go_to_drill(), for a future
        ore-hauler drone role (not used by scout/miner this pass). Same
        target_coords/select_cruise_throttle() contract as fly_to_station().
        """
        if not name:
            return False
        self._host.log.trace(f"[{self._host.name}] fly_to_drill('{name}') entry.")
        res = self._host.drone.go_to_drill(name)
        if res.status != "ok":
            self._host.log.level("warn").print(f"[{self._host.name}] go_to_drill('{name}') rejected: {res.status} - {res.message}")
            self._host.log.trace(f"[{self._host.name}] fly_to_drill('{name}') exit: rejected ({res.status}).")
            return False
        if target_coords is not None:
            throttle = self._host.select_cruise_throttle(target_coords)
        else:
            throttle = min(self._host.cruise_throttle, self._host.MAX_SPEEDMODE_THROTTLE)
        self._host.drone.set_throttle(throttle)

        ticks = 0
        while ticks < timeout_ticks:
            sleep(1.0)
            ticks += 10
            if self.is_stranded():
                self._host.log.trace(f"[{self._host.name}] fly_to_drill('{name}') exit: stranded ({self.status()}) after {ticks} ticks.")
                return False
            if self.current_drill():
                self._host.log.trace(f"[{self._host.name}] fly_to_drill('{name}') exit: arrived after {ticks} ticks.")
                return True
            if ticks % 100 == 0:
                self._host.log.debug(f"[{self._host.name}] fly_to_drill('{name}') arrival-poll retry: still not arrived after {ticks}/{timeout_ticks} ticks.")

        self._host.log.level("warn").print(f"[{self._host.name}] go_to_drill('{name}') timed out after {timeout_ticks} ticks.")
        self._host.log.trace(f"[{self._host.name}] fly_to_drill('{name}') exit: timed out after {ticks} ticks.")
        return False
