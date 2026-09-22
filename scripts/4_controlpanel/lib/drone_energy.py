# Drone mixin: drone-specific linear Wh/meter energy model, round-trip trip
# budgeting, and drone_service/drone_depot discovery. Mirrors
# vehicle_energy.py's "there-and-back" safety-margin + hard emergency-reserve
# floor pattern, but with a DIFFERENT (simpler, linear) travel model and TWO
# distinct "home" endpoints -- drone_service (power) and drone_depot (cargo)
# -- rather than ground vehicles' single combined base/charging-station pair.
#
# Game-confirmed constants (docs/components/drone.md): full throttle = 5 Wh/h
# burn, 300 m/h speed; both scale with throttle (speed linear, burn
# quadratic) -- collapsing to a flat linear Wh/meter model, structurally like
# Rover's own flat model (lib/vehicle_energy.py's ROVER_WH_PER_METER_PER_THROTTLE),
# just a different constant. Treat the drone's own range_remaining() as
# ground truth; this formula is for PLANNING only (trip feasibility, throttle
# selection), verified against the drone's live battery before committing.
# Scan/extract themselves cost no extra travel Wh in the documented model
# (hovering at throttle 0 costs 0), so there's deliberately no scan/extract
# term in calculate_trip_energy() below, unlike VehicleEnergyMixin's sonar/
# mining budget terms.

from archive import archive
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from drone import DroneController

DRONE_SERVICE_TYPE_ID = "drone_service_station"
DRONE_DEPOT_TYPE_ID = "drone_depot"

# 5.0 Wh/h at 300 m/h full-throttle burn -> flat Wh/meter-per-throttle rate.
DRONE_WH_PER_METER_PER_THROTTLE = 5.0 / 300.0  # ~0.01667 Wh/m at throttle 1.0
MIN_SPEEDMODE_THROTTLE = 0.10
MAX_SPEEDMODE_THROTTLE = 1.0
SAFETY_MARGIN_MULTIPLIER = 1.05

# Smaller than VehicleEnergyMixin.MIN_EMERGENCY_RESERVE_WH=8.0 -- electric
# drone batteries are much smaller than a Rover/Pioneer's, so an 8 Wh floor
# would eat a large fraction of total capacity. Tune here and update
# docs/AI_CHEATSHEET.md's drone energy-budgeting section in the same change.
MIN_EMERGENCY_RESERVE_WH = 4.0

DEFAULT_CRUISE_THROTTLE_KEY = "drone.default_cruise_throttle"
DEFAULT_CRUISE_THROTTLE_FALLBACK = 0.5


def drone_wh_per_meter_at_throttle(throttle):
    """
    Standalone: linear Wh/meter for ANY electric drone at the given
    throttle -- no drone object needed, since the documented model has no
    per-drone/cargo/module term (unlike Pioneer's travel formula), just one
    flat rate for every electric drone.
    """
    if throttle <= 0:
        return 0.0
    return DRONE_WH_PER_METER_PER_THROTTLE * throttle


def drone_rescue_wh_per_meter():
    """
    Worst-case-safe Wh/meter for rescue/return budgeting, at the speedmode
    throttle floor -- mirrors vehicle_energy.py's rescue_wh_per_meter_for(),
    but needs no drone object at all since the model is a flat per-throttle
    rate with no vehicle-specific terms.
    """
    return drone_wh_per_meter_at_throttle(MIN_SPEEDMODE_THROTTLE)


def _extract_coords(pos):
    if pos is None:
        return None
    if isinstance(pos, (tuple, list)) and len(pos) >= 2:
        return (float(pos[0]), float(pos[1]))
    x = getattr(pos, "x", None)
    y = getattr(pos, "y", None)
    if x is not None and y is not None:
        return (float(x), float(y))
    return None


def discover_drone_buildings(type_id):
    """
    Standalone: every deployed building of type_id (drone_service_station or
    drone_depot) across every owned outpost, as
    [{"id": str, "coords": (x, y), "outpost": OutpostRef|None}, ...]. Mirrors
    vehicle_energy.py's get_all_charging_stations() discovery shape, but
    module-level so both DroneEnergyMixin and lib/drone_service.py's own
    station-side nearest-station arbitration (mirroring charging.py's
    is_nearest_station_to()) can share one implementation.
    """
    refs = []
    found_ids = set()
    network = get_component("outpost_network")
    if network and hasattr(network, "outposts"):
        try:
            outposts = network.outposts()
        except Exception:
            outposts = []
        for outpost in outposts:
            if not hasattr(outpost, "buildings"):
                continue
            try:
                buildings = outpost.buildings(type_id)
            except Exception:
                continue
            for b in buildings:
                b_id = getattr(b, "id", "")
                if not b_id or b_id in found_ids:
                    continue
                pos = _extract_coords(getattr(b, "position", None))
                if not pos:
                    continue
                found_ids.add(b_id)
                refs.append({"id": b_id, "coords": pos, "outpost": getattr(b, "outpost", None)})
    return refs


def discover_drone_services():
    return discover_drone_buildings(DRONE_SERVICE_TYPE_ID)


def discover_drone_depots():
    return discover_drone_buildings(DRONE_DEPOT_TYPE_ID)


class DroneEnergyMixin:
    """
    Battery telemetry, linear travel Wh/meter model, and drone_service/
    drone_depot discovery, mixed into DroneController. Depends on
    DroneNavigationMixin for position()/distance_between().
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

    def get_battery(self):
        """
        Returns (current_wh, capacity_wh, fraction 0-1). Electric drones only
        this pass -- .battery raises ReferenceError on a heli drone (see
        drone.md); DroneController is only ever constructed for an electric
        DroneRef this pass (heli support deferred, see the module docstring
        in lib/drone.py).
        """
        try:
            wh = self._host.drone.battery.level()
            cap = self._host.drone.battery.capacity()
            lvl = self._host.drone.battery.percent()
            return wh, cap, lvl
        except Exception:
            return 0.0, 100.0, 0.0

    def wh_per_meter_at_throttle(self, throttle):
        return drone_wh_per_meter_at_throttle(throttle)

    def minimum_wh_per_meter(self):
        return self.wh_per_meter_at_throttle(self.MIN_SPEEDMODE_THROTTLE)

    def energy_wh_for_leg(self, distance_m, throttle):
        if distance_m <= 0 or throttle <= 0:
            return 0.0
        return distance_m * self.wh_per_meter_at_throttle(throttle)

    def get_all_drone_services(self):
        return discover_drone_services()

    def get_all_drone_depots(self):
        return discover_drone_depots()

    def get_nearest_drone_service(self, from_coords=None):
        """
        Returns (coords, station_info_dict) for the nearest drone_service_station
        -- this drone's power "home". Falls back to (0.0, 0.0)/{} when none is
        deployed yet, EXCEPT it prefers self.home_coords if already resolved
        (getattr default avoids an AttributeError during DroneController.__init__,
        before self.home_coords is assigned).
        """
        ref_coords = from_coords if from_coords is not None else self._host.position()
        stations = self.get_all_drone_services()
        if not stations:
            fallback = getattr(self, "home_coords", (0.0, 0.0))
            self._host.log.trace(f"[{self._host.name}] get_nearest_drone_service: no drone_service_station deployed yet; falling back to home_coords {fallback}.")
            return fallback, {"id": "", "coords": fallback}
        best = min(stations, key=lambda st: self._host.distance_between(ref_coords, st["coords"]))
        self._host.log.trace(f"[{self._host.name}] get_nearest_drone_service: {len(stations)} candidate(s) from {ref_coords}, nearest '{best.get('id')}' at {best['coords']} ({self._host.distance_between(ref_coords, best['coords']):.1f}m).")
        return best["coords"], best

    def get_nearest_drone_depot(self, from_coords=None):
        """
        Returns (coords, depot_info_dict) for the nearest drone_depot -- this
        drone's cargo "home", a DISTINCT endpoint from get_nearest_drone_service()
        (see module docstring). Same fallback shape as get_nearest_drone_service().
        """
        ref_coords = from_coords if from_coords is not None else self._host.position()
        depots = self.get_all_drone_depots()
        if not depots:
            fallback = getattr(self, "home_coords", (0.0, 0.0))
            self._host.log.trace(f"[{self._host.name}] get_nearest_drone_depot: no drone_depot deployed yet; falling back to home_coords {fallback}.")
            return fallback, {"id": "", "coords": fallback}
        best = min(depots, key=lambda d: self._host.distance_between(ref_coords, d["coords"]))
        self._host.log.trace(f"[{self._host.name}] get_nearest_drone_depot: {len(depots)} candidate(s) from {ref_coords}, nearest '{best.get('id')}' at {best['coords']} ({self._host.distance_between(ref_coords, best['coords']):.1f}m).")
        return best["coords"], best

    def return_floor_wh(self, from_coords=None):
        """
        Wh needed on board right now to safely reach the nearest drone_service
        (power home) at the speedmode throttle floor -- the hard survival
        floor, mirroring vehicle_energy.py's energy_needed_to_return_now().
        """
        pos = from_coords if from_coords is not None else self._host.position()
        nearest, _ = self.get_nearest_drone_service(from_coords=pos)
        dist = self._host.distance_between(pos, nearest)
        drive_wh = dist * self.minimum_wh_per_meter()
        return (drive_wh * self.SAFETY_MARGIN_MULTIPLIER) + self.MIN_EMERGENCY_RESERVE_WH

    def energy_needed_to_return_now(self):
        return self.return_floor_wh()

    def energy_needed_to_return_comfortably(self):
        """
        Same as return_floor_wh() but at self.cruise_throttle rather than the
        speedmode floor -- the proactive "time to head back" trigger for field
        loops, not the hard abort (mirrors VehicleEnergyMixin's own
        floor-vs-comfortable distinction).
        """
        pos = self._host.position()
        nearest, _ = self.get_nearest_drone_service(from_coords=pos)
        dist = self._host.distance_between(pos, nearest)
        drive_wh = dist * self.wh_per_meter_at_throttle(self._host.cruise_throttle)
        return (drive_wh * self.SAFETY_MARGIN_MULTIPLIER) + self.MIN_EMERGENCY_RESERVE_WH

    def calculate_trip_energy(self, target_coords, wh_per_meter=None):
        """
        Round-trip budget: outbound flight to target_coords + return flight
        from target_coords to the nearest drone_service (power home, NOT
        necessarily the nearest drone_depot -- see module docstring),
        buffered by SAFETY_MARGIN_MULTIPLIER plus a hard
        MIN_EMERGENCY_RESERVE_WH floor. No scan/extract term (see module
        docstring).
        """
        current_pos = self._host.position()
        dist_outbound = self._host.distance_between(current_pos, target_coords)
        nearest_service, _ = self.get_nearest_drone_service(from_coords=target_coords)
        dist_inbound = self._host.distance_between(target_coords, nearest_service)

        rate = wh_per_meter if wh_per_meter is not None else self.wh_per_meter_at_throttle(self._host.cruise_throttle)
        drive_out_wh = dist_outbound * rate
        drive_home_wh = dist_inbound * rate
        net_wh = drive_out_wh + drive_home_wh
        buffered_wh = net_wh * self.SAFETY_MARGIN_MULTIPLIER
        total_required_wh = buffered_wh + self.MIN_EMERGENCY_RESERVE_WH

        curr_wh, cap_wh, lvl = self.get_battery()
        is_achievable = curr_wh >= total_required_wh
        self._host.log.trace(
            f"[{self._host.name}] calculate_trip_energy to {target_coords}: "
            f"out={drive_out_wh:.2f}Wh ({dist_outbound:.1f}m), home={drive_home_wh:.2f}Wh ({dist_inbound:.1f}m to '{nearest_service}'), "
            f"buffered={buffered_wh:.2f}Wh (x{self.SAFETY_MARGIN_MULTIPLIER}), reserve={self.MIN_EMERGENCY_RESERVE_WH:.1f}Wh, "
            f"total_required={total_required_wh:.2f}Wh, current={curr_wh:.2f}Wh -> achievable={is_achievable}."
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
            leg_wh(t) = distance * DRONE_WH_PER_METER_PER_THROTTLE * t
            leg_wh(t) * SAFETY_MARGIN_MULTIPLIER <= available_for_leg
            => t <= available_for_leg / (distance * DRONE_WH_PER_METER_PER_THROTTLE * SAFETY_MARGIN_MULTIPLIER)
        """
        distance = self._host.distance_between(self._host.position(), target_coords)
        if distance <= 0:
            return self.MAX_SPEEDMODE_THROTTLE

        curr_wh, _, _ = self.get_battery()
        nearest_service, _ = self.get_nearest_drone_service(from_coords=target_coords)
        reserve_needed = (self._host.distance_between(target_coords, nearest_service) * self.minimum_wh_per_meter() * self.SAFETY_MARGIN_MULTIPLIER) + self.MIN_EMERGENCY_RESERVE_WH
        available_for_leg = curr_wh - reserve_needed
        if available_for_leg <= 0:
            self._host.log.debug(f"[{self._host.name}] max_safe_throttle_for_leg to {target_coords}: no energy available for leg (current={curr_wh:.2f}Wh, reserve_needed={reserve_needed:.2f}Wh); throttle=0%.")
            return 0.0

        denom = distance * self.DRONE_WH_PER_METER_PER_THROTTLE * self.SAFETY_MARGIN_MULTIPLIER
        if denom <= 0:
            return self.MAX_SPEEDMODE_THROTTLE
        throttle = max(0.0, min(self.MAX_SPEEDMODE_THROTTLE, available_for_leg / denom))
        self._host.log.debug(f"[{self._host.name}] max_safe_throttle_for_leg to {target_coords}: distance={distance:.1f}m, available={available_for_leg:.2f}Wh, reserve_needed={reserve_needed:.2f}Wh -> max_safe_throttle={throttle*100:.0f}%.")
        return throttle

    def select_cruise_throttle(self, target_coords):
        baseline = min(self._host.cruise_throttle, self.MAX_SPEEDMODE_THROTTLE)
        max_safe = self.max_safe_throttle_for_leg(target_coords)
        if max_safe >= baseline:
            self._host.log.debug(f"[{self._host.name}] select_cruise_throttle: baseline {baseline*100:.0f}% is within safe max ({max_safe*100:.0f}%); using baseline.")
            return baseline
        throttle = max(self.MIN_SPEEDMODE_THROTTLE, min(baseline, max_safe))
        self._host.log.debug(f"[{self._host.name}] select_cruise_throttle: baseline {baseline*100:.0f}% exceeds safe max ({max_safe*100:.0f}%); capping to {throttle*100:.0f}%.")
        return throttle
