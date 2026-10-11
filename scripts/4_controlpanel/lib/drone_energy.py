# Drone mixin: engine-aware (electric battery / heli oil) linear energy
# model, round-trip trip budgeting, and wrappers over drone_service/drone_depot
# discovery (lib/drone_depots.py). No flying: charging and refuelling trips are
# in lib/drone_charging.py.
# Mirrors vehicle_energy.py's "there-and-back" safety-margin + hard
# emergency-reserve floor pattern, but with a DIFFERENT (simpler, linear)
# travel model and TWO distinct "home" endpoints -- drone_service (power/oil)
# and drone_depot (cargo) -- rather than ground vehicles' single combined
# base/charging-station pair.
#
# Game-confirmed constants (docs/components/drone.md, equipment_modules.md):
#   electric: full throttle = 5 Wh/h burn, 300 m/h speed
#   heli:     full throttle = 5 t/h Oil burn, 900 m/h speed
# Both scale with throttle (speed linear, burn quadratic) -- collapsing to a
# flat linear energy-per-meter model per engine (ENGINE_PROFILES). Shield
# Plating raises burn 1.5x. "Energy" throughout this mixin means the
# drone's own fuel unit: Wh for electric, tons of Oil for heli -- every
# budget/floor below is in that unit, so callers never branch on engine.
# The engine is auto-detected per drone (detect_engine()). Treat the drone's
# own range_remaining() as ground truth; this formula is for PLANNING only
# (trip feasibility, throttle selection), verified against the drone's live
# fuel before committing. Scan/extract themselves cost no extra travel energy
# in the documented model (hovering at throttle 0 costs 0), so there's
# deliberately no scan/extract term in calculate_trip_energy() below, unlike
# VehicleEnergyMixin's sonar/mining budget terms.

from typing import TYPE_CHECKING

import drone_depots
from archive import archive
from swallow import swallowed

if TYPE_CHECKING:
    from drone import DroneController

# 5.0 Wh/h at 300 m/h full-throttle burn -> flat Wh/meter-per-throttle rate.
DRONE_WH_PER_METER_PER_THROTTLE = 5.0 / 300.0  # ~0.01667 Wh/m at throttle 1.0
# 5.0 t/h Oil at 900 m/h full-throttle burn -> flat t/meter-per-throttle rate.
HELI_T_PER_METER_PER_THROTTLE = 5.0 / 900.0  # ~0.00556 t/m (5.6 t/km) at throttle 1.0
# docs/components/drone.md is_plated(): Shield Plating raises burn 1.5x.
PLATING_BURN_MULTIPLIER = 1.5
MIN_SPEEDMODE_THROTTLE = 0.10
MAX_SPEEDMODE_THROTTLE = 1.0
SAFETY_MARGIN_MULTIPLIER = 1.05

# Smaller than VehicleEnergyMixin.MIN_EMERGENCY_RESERVE_WH=8.0 -- electric
# drone batteries are much smaller than a Rover/Pioneer's, so an 8 Wh floor
# would eat a large fraction of total capacity. Tune here and update
# docs/AI_CHEATSHEET.md's drone energy-budgeting section in the same change.
MIN_EMERGENCY_RESERVE_WH = 4.0
# Heli equivalent, in tons of Oil: ~0.9 km at full throttle, ~9 km at the
# speedmode floor. Oil tanks are 30/75/150 t, so this is a small slice.
HELI_MIN_EMERGENCY_RESERVE_T = 5.0

# Per-engine planning profile. "energy" = Wh (electric) or t Oil (heli).
ENGINE_PROFILES = {
    "electric": {"per_meter": DRONE_WH_PER_METER_PER_THROTTLE, "speed_m_per_h": 300.0, "reserve": MIN_EMERGENCY_RESERVE_WH, "unit": "Wh"},
    "heli": {"per_meter": HELI_T_PER_METER_PER_THROTTLE, "speed_m_per_h": 900.0, "reserve": HELI_MIN_EMERGENCY_RESERVE_T, "unit": "t"},
}
DEFAULT_ENGINE = "electric"

DEFAULT_CRUISE_THROTTLE_KEY = "drone.default_cruise_throttle"
DEFAULT_CRUISE_THROTTLE_FALLBACK = 0.5


def engine_profile(engine):
    """ENGINE_PROFILES entry for engine ("electric"/"heli"), electric for unknown/""."""
    return ENGINE_PROFILES.get(engine or DEFAULT_ENGINE, ENGINE_PROFILES[DEFAULT_ENGINE])


def drone_energy_per_meter_at_throttle(throttle, engine=DEFAULT_ENGINE, plated=False):
    """
    Standalone: linear energy/meter (Wh or t Oil, see ENGINE_PROFILES) for
    ANY drone of that engine at the given throttle -- no drone object
    needed, since the documented model has no per-drone/cargo term (unlike
    Pioneer's travel formula), just one flat rate per engine, times
    PLATING_BURN_MULTIPLIER with Shield Plating.
    """
    if throttle <= 0:
        return 0.0
    rate = engine_profile(engine)["per_meter"] * throttle
    return rate * PLATING_BURN_MULTIPLIER if plated else rate


def drone_wh_per_meter_at_throttle(throttle):
    """Electric-only shorthand for drone_energy_per_meter_at_throttle()."""
    return drone_energy_per_meter_at_throttle(throttle, "electric")


def drone_rescue_energy_per_meter(engine=DEFAULT_ENGINE):
    """
    Worst-case-safe energy/meter for rescue/return budgeting, at the
    speedmode throttle floor -- mirrors vehicle_energy.py's
    rescue_wh_per_meter_for(), but needs no drone object at all since the
    model is a flat per-throttle rate with no vehicle-specific terms.
    Plating unknown from a DroneRef, so assumed (conservative).
    """
    return drone_energy_per_meter_at_throttle(MIN_SPEEDMODE_THROTTLE, engine, plated=True)


def drone_rescue_wh_per_meter():
    """Electric-only shorthand for drone_rescue_energy_per_meter()."""
    return drone_rescue_energy_per_meter("electric")


class DroneEnergyMixin:
    """
    Battery telemetry, linear travel Wh/meter model, trip budgets and
    drone_service/drone_depot discovery wrappers, mixed into DroneController.
    Depends on DroneNavigationMixin for position()/distance_between().
    """

    @property
    def _host(self) -> "DroneController":
        return self  # type: ignore[return-value]

    DRONE_WH_PER_METER_PER_THROTTLE = DRONE_WH_PER_METER_PER_THROTTLE
    MIN_SPEEDMODE_THROTTLE = MIN_SPEEDMODE_THROTTLE
    MAX_SPEEDMODE_THROTTLE = MAX_SPEEDMODE_THROTTLE
    SAFETY_MARGIN_MULTIPLIER = SAFETY_MARGIN_MULTIPLIER
    MIN_EMERGENCY_RESERVE_WH = MIN_EMERGENCY_RESERVE_WH

    def default_cruise_throttle(self):
        value = archive.get(DEFAULT_CRUISE_THROTTLE_KEY, None)
        if value is None:
            return DEFAULT_CRUISE_THROTTLE_FALLBACK
        try:
            value = float(value)
        except (TypeError, ValueError):
            return DEFAULT_CRUISE_THROTTLE_FALLBACK
        return max(self.MIN_SPEEDMODE_THROTTLE, min(self.MAX_SPEEDMODE_THROTTLE, value))

    def detect_engine(self, known=None):
        """
        "electric" or "heli", auto-detected: this drone's own DroneRef.engine
        from fleet.drones() first, else a live probe -- .oil_tank/.battery
        methods raise ReferenceError on the other powertrain (drone.md).
        Falls back to DEFAULT_ENGINE when neither answers (no thruster
        mounted yet). known (an ENGINE_PROFILES key) skips detection: a bare
        replacement chassis has nothing to probe, so fit_loadout_if_new()
        passes its lineage's engine. Also caches Shield Plating (is_plated())
        for the burn multiplier. Re-run after a re-equip (DroneController.run()
        does). The only writer of host.engine and host.plated.
        """
        engine, source = "", None
        if known in ENGINE_PROFILES:
            engine, source = known, "caller (replacement lineage)"
        fleet = get_component("fleet") if not engine else None
        if fleet and hasattr(fleet, "drones"):
            try:
                for ref in fleet.drones():
                    if getattr(ref, "id", None) == self._host.name:
                        engine = getattr(ref, "engine", "") or ""
                        source = "fleet.drones()"
                        break
            except Exception as error:
                swallowed("drone_energy.DroneEnergyMixin.detect_engine: fleet.drones", error)
        if engine not in ENGINE_PROFILES:
            engine = ""
            for candidate, attr in (("heli", "oil_tank"), ("electric", "battery")):
                try:
                    getattr(self._host.drone, attr).capacity()
                    engine, source = candidate, f"{attr} probe"
                    break
                except Exception as error:
                    swallowed("drone_energy.DroneEnergyMixin.detect_engine: getattr(self._host.drone, attr).capacity", error)
                    continue
        if not engine:
            engine, source = DEFAULT_ENGINE, "fallback (no thruster/fuel module readable)"
        try:
            self._host.plated = bool(self._host.drone.is_plated())
        except Exception as error:
            swallowed("drone_energy.DroneEnergyMixin.detect_engine: self._host.drone.is_plated", error)
            self._host.plated = False
        self._host.engine = engine
        self._host.log.debug(f"[{self._host.name}] Engine detected: '{engine}' via {source}; plated={self._host.plated}.")
        return engine

    def energy_unit(self):
        return engine_profile(getattr(self._host, "engine", DEFAULT_ENGINE))["unit"]

    def emergency_reserve(self):
        """Hard reserve floor in this drone's fuel unit (MIN_EMERGENCY_RESERVE_WH / HELI_MIN_EMERGENCY_RESERVE_T)."""
        return engine_profile(getattr(self._host, "engine", DEFAULT_ENGINE))["reserve"]

    def flight_speed_m_per_h(self, throttle=1.0):
        return engine_profile(getattr(self._host, "engine", DEFAULT_ENGINE))["speed_m_per_h"] * throttle

    def get_battery(self):
        """
        Returns (current, capacity, fraction 0-1) of this drone's fuel store
        in its own unit: battery Wh (electric) or oil tank tons (heli).
        Named for its electric origin; every budget in this mixin uses the
        same unit (see module docstring). Unreadable reads as empty, so
        every gate fails safe toward refuelling.
        """
        store = "oil_tank" if getattr(self._host, "engine", DEFAULT_ENGINE) == "heli" else "battery"
        try:
            module = getattr(self._host.drone, store)
            return module.level(), module.capacity(), module.percent()
        except Exception as error:
            swallowed("drone_energy.DroneEnergyMixin.get_battery: module.level", error)
            return 0.0, 100.0, 0.0

    def wh_per_meter_at_throttle(self, throttle):
        """Energy/meter in this drone's fuel unit (engine + plating aware)."""
        return drone_energy_per_meter_at_throttle(throttle, getattr(self._host, "engine", DEFAULT_ENGINE), getattr(self._host, "plated", False))

    def minimum_wh_per_meter(self):
        return self.wh_per_meter_at_throttle(self.MIN_SPEEDMODE_THROTTLE)

    def energy_wh_for_leg(self, distance_m, throttle):
        if distance_m <= 0 or throttle <= 0:
            return 0.0
        return distance_m * self.wh_per_meter_at_throttle(throttle)

    # Depot/service discovery and home resolution live in lib/drone_depots.py;
    # these wrappers pass in what that module used to read from self.
    def get_all_drone_services(self):
        """Every drone_service_station, dry ones skipped for a heli (see drone_depots.services_for())."""
        return drone_depots.services_for(getattr(self._host, "engine", DEFAULT_ENGINE), self._host.name, self._host.log)

    def get_all_drone_depots(self):
        return drone_depots.discover_drone_depots()

    def _nearest(self, label, candidates, from_coords):
        """(coords, info) of the candidate nearest to from_coords (default: own position); see drone_depots.nearest().
        The home_coords getattr default covers DroneController.__init__, before home_coords is set."""
        ref_coords = from_coords if from_coords is not None else self._host.position()
        return drone_depots.nearest(label, candidates, ref_coords, getattr(self, "home_coords", (0.0, 0.0)), self._host.name, self._host.log)

    def get_nearest_drone_service(self, from_coords=None):
        """(coords, station_info) of the nearest drone_service_station -- this drone's power "home"."""
        return self._nearest("drone_service_station", self.get_all_drone_services(), from_coords)

    def get_nearest_drone_depot(self, from_coords=None):
        """(coords, depot_info) of the nearest drone_depot -- this drone's cargo "home", a DISTINCT
        endpoint from get_nearest_drone_service() (see module docstring)."""
        return self._nearest("drone_depot", self.get_all_drone_depots(), from_coords)

    def resolve_home_depot(self, home_depot=None):
        """Picks and pins this drone's home: (depot info, pool outpost id or None); see drone_depots.resolve_home().
        DroneController.resolve_home() stores both."""
        return drone_depots.resolve_home(self._host.name, self.get_all_drone_depots(), home_depot, self.get_nearest_drone_depot, self._host.log)

    def _home_depot_candidates(self):
        """Live depot dicts making up this drone's home (see drone_depots.home_candidates())."""
        return drone_depots.home_candidates(self.get_all_drone_depots(), getattr(self._host, "home_depot_pool", None), getattr(self._host, "home_depot", None))

    def _pick_free_depot(self, candidates, prefer_id=None):
        """Best depot of candidates for this trip (see drone_depots.pick_free_depot())."""
        return drone_depots.pick_free_depot(candidates, prefer_id, self._host.current_station(), self._host.position(), self._host.name, self._host.log)

    def get_home_depot(self, prefer_id=None):
        """
        Returns (coords, depot_info_dict) for the depot this drone should use
        now -- where it unloads and re-equips, regardless of which depot is
        nearest right now. With a pool home, re-picks per call so a drone
        never queues for a busy depot while a sibling in the same outpost
        is free (see _pick_free_depot()). Re-homes
        (DroneController.resolve_home()) when the home no longer has any
        depot. Same fallback shape as get_nearest_drone_depot() when no
        depot exists at all.
        """
        candidates = self._home_depot_candidates()
        if not candidates:
            if getattr(self._host, "home_depot", None):
                # resolve_home_depot() skips (and overwrites) the stale pin itself.
                self._host.log.level("warn").print(f"[{self._host.name}] Home Drone Depot no longer exists; re-homing.")
            self._host.resolve_home()
            candidates = self._home_depot_candidates()
        if candidates:
            depot = self._pick_free_depot(candidates, prefer_id=prefer_id)
            return depot["coords"], depot
        return self.get_nearest_drone_depot()

    def get_home_service(self):
        """
        Returns (coords, station_info_dict) for this drone's home
        drone_service: the one in the home depot's outpost (nearest to the
        depot if there are several), else the service nearest to the home
        depot. Falls back to get_nearest_drone_service() without a home
        depot. This is the PLANNING/charging target; the hard in-flight
        survival floor (return_floor_wh()) still uses the nearest service.
        """
        best = drone_depots.home_service(getattr(self._host, "home_depot", None), self.get_all_drone_services())
        if best is None:
            return self.get_nearest_drone_service()
        return best["coords"], best

    def wh_to_reach(self, target_coords, from_coords=None):
        """Reserve-inclusive Wh to reach target_coords at the speedmode throttle floor."""
        pos = from_coords if from_coords is not None else self._host.position()
        dist = self._host.distance_between(pos, target_coords)
        return (dist * self.minimum_wh_per_meter() * self.SAFETY_MARGIN_MULTIPLIER) + self.emergency_reserve()

    def return_floor_wh(self, from_coords=None):
        """
        Wh needed on board right now to safely reach the nearest drone_service
        (power home) at the speedmode throttle floor -- the hard survival
        floor, mirroring vehicle_energy.py's energy_needed_to_return_now().
        Deliberately the NEAREST service, not the home one: this is the
        in-flight abort threshold, where any charger is better than none.
        """
        pos = from_coords if from_coords is not None else self._host.position()
        nearest, _ = self.get_nearest_drone_service(from_coords=pos)
        return self.wh_to_reach(nearest, from_coords=pos)

    def energy_needed_to_return_now(self):
        return self.return_floor_wh()

    def energy_needed_to_return_comfortably(self):
        """
        Same as return_floor_wh() but at self.cruise_throttle rather than the
        speedmode floor -- the proactive "time to head back" trigger for field
        loops, not the hard abort (mirrors VehicleEnergyMixin's own
        floor-vs-comfortable distinction). Measured to the HOME service,
        since that's where DroneChargingMixin.return_to_service_for_charge()
        heads first.
        """
        pos = self._host.position()
        home_service, _ = self.get_home_service()
        dist = self._host.distance_between(pos, home_service)
        drive_wh = dist * self.wh_per_meter_at_throttle(self._host.cruise_throttle)
        return (drive_wh * self.SAFETY_MARGIN_MULTIPLIER) + self.emergency_reserve()

    def calculate_trip_energy(self, target_coords, wh_per_meter=None):
        """
        Round-trip budget: outbound flight to target_coords + return flight
        from target_coords to the home drone_service (get_home_service() --
        where the drone actually goes back to, not whichever service happens
        to be nearest the target),
        buffered by SAFETY_MARGIN_MULTIPLIER plus a hard
        MIN_EMERGENCY_RESERVE_WH floor. No scan/extract term (see module
        docstring).
        """
        current_pos = self._host.position()
        dist_outbound = self._host.distance_between(current_pos, target_coords)
        nearest_service, _ = self.get_home_service()
        dist_inbound = self._host.distance_between(target_coords, nearest_service)

        rate = wh_per_meter if wh_per_meter is not None else self.wh_per_meter_at_throttle(self._host.cruise_throttle)
        drive_out_wh = dist_outbound * rate
        drive_home_wh = dist_inbound * rate
        net_wh = drive_out_wh + drive_home_wh
        buffered_wh = net_wh * self.SAFETY_MARGIN_MULTIPLIER
        total_required_wh = buffered_wh + self.emergency_reserve()

        curr_wh, _cap_wh, _lvl = self.get_battery()
        is_achievable = curr_wh >= total_required_wh
        self._host.log.trace(
            f"[{self._host.name}] calculate_trip_energy to {target_coords}: "
            f"out={drive_out_wh:.2f} {self.energy_unit()} ({dist_outbound:.1f}m), home={drive_home_wh:.2f} {self.energy_unit()} ({dist_inbound:.1f}m to '{nearest_service}'), "
            f"buffered={buffered_wh:.2f} {self.energy_unit()} (x{self.SAFETY_MARGIN_MULTIPLIER}), reserve={self.emergency_reserve():.1f} {self.energy_unit()}, "
            f"total_required={total_required_wh:.2f} {self.energy_unit()}, current={curr_wh:.2f} {self.energy_unit()} -> achievable={is_achievable}."
        )
        return {
            "dist_outbound": dist_outbound,
            "dist_inbound": dist_inbound,
            "nearest_service_coords": nearest_service,
            "drive_out_wh": drive_out_wh,
            "drive_home_wh": drive_home_wh,
            "net_expedition_wh": net_wh,
            "total_required_wh": total_required_wh,
            "current_wh": curr_wh,
            "is_achievable": is_achievable,
        }

    def max_safe_throttle_for_leg(self, target_coords):
        """
        Highest throttle for which flying to target_coords still leaves a
        safe reserve to reach the nearest drone_service from there. Unlike
        Pioneer's sqrt(throttle) relationship (vehicle_energy.py), the
        drone's Wh/m is LINEAR in throttle, so the bound solves directly:
            leg(t) = distance * per_meter(1.0) * t
            leg(t) * SAFETY_MARGIN_MULTIPLIER <= available_for_leg
            => t <= available_for_leg / (distance * per_meter(1.0) * SAFETY_MARGIN_MULTIPLIER)
        """
        self._host.log.start(f"[{self._host.name}] max_safe_throttle_for_leg", level="debug")
        distance = self._host.distance_between(self._host.position(), target_coords)
        if distance <= 0:
            self._host.log.end()
            return self.MAX_SPEEDMODE_THROTTLE

        curr_wh, _, _ = self.get_battery()
        nearest_service, _ = self.get_nearest_drone_service(from_coords=target_coords)
        reserve_needed = (self._host.distance_between(target_coords, nearest_service) * self.minimum_wh_per_meter() * self.SAFETY_MARGIN_MULTIPLIER) + self.emergency_reserve()
        available_for_leg = curr_wh - reserve_needed
        if available_for_leg <= 0:
            self._host.log.debug(f"max_safe_throttle_for_leg to {target_coords}: no energy available for leg (current={curr_wh:.2f} {self.energy_unit()}, reserve_needed={reserve_needed:.2f} {self.energy_unit()}); throttle=0%.")
            self._host.log.end()
            return 0.0

        denom = distance * self.wh_per_meter_at_throttle(1.0) * self.SAFETY_MARGIN_MULTIPLIER
        if denom <= 0:
            self._host.log.end()
            return self.MAX_SPEEDMODE_THROTTLE
        throttle = max(0.0, min(self.MAX_SPEEDMODE_THROTTLE, available_for_leg / denom))
        self._host.log.debug(f"max_safe_throttle_for_leg to {target_coords}: distance={distance:.1f}m, available={available_for_leg:.2f} {self.energy_unit()}, reserve_needed={reserve_needed:.2f} {self.energy_unit()} -> max_safe_throttle={throttle * 100:.0f}%.")
        self._host.log.end()
        return throttle

    def select_cruise_throttle(self, target_coords):
        self._host.log.start(f"[{self._host.name}] select_cruise_throttle", level="debug")
        baseline = min(self._host.cruise_throttle, self.MAX_SPEEDMODE_THROTTLE)
        max_safe = self.max_safe_throttle_for_leg(target_coords)
        if max_safe >= baseline:
            self._host.log.debug(f"baseline {baseline * 100:.0f}% is within safe max ({max_safe * 100:.0f}%); using baseline.")
            self._host.log.end()
            return baseline
        throttle = max(self.MIN_SPEEDMODE_THROTTLE, min(baseline, max_safe))
        self._host.log.debug(f"baseline {baseline * 100:.0f}% exceeds safe max ({max_safe * 100:.0f}%); capping to {throttle * 100:.0f}%.")
        self._host.log.end()
        return throttle
