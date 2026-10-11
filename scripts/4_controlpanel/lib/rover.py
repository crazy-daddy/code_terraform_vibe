# Shared Library for Expedition Rover Automation
# Inherits from VehicleController (lib/vehicle.py): the Rover's own linear
# travel-energy model and its loadout fitting. run() is
# run_job_loop(MineJob(self, RoverTargets())): expeditions to unscanned POIs
# and mineral sites for home demand (lib/job_mine.py).

from vehicle import VehicleController
from pioneer_commission import LoadoutFittingMixin
from vehicle_energy import ROVER_WH_PER_METER_PER_THROTTLE
from job_mine import MineJob, RoverTargets

# Modules a Rover needs. A fresh chassis is bare and mount() is self-only, so
# the Rover mounts them from Inventory at start (lib/early_buyer.py buys them).
# A kind counts as mounted at any tier (drill_module_industrial is a drill_module).
ROVER_LOADOUT = ("nav_module", "sonar_module", "drill_module")


class RoverController(VehicleController, LoadoutFittingMixin):
    """
    Automated Expedition & Mining Controller for the Rover chassis.
    Specializes VehicleController's travel-energy model; run() runs the
    MineJob expedition role (lib/job_mine.py).
    """
    def __init__(self, vehicle: "Rover | Pioneer", home_base=None):
        super().__init__(vehicle, home_base=home_base)
        self.role = "rover"

    def wh_per_meter_at_throttle(self, throttle, cargo_units=None):
        """
        Rover's own developer-confirmed travel model (see lib/vehicle_energy.py
        module docstring): Wh/meter = ROVER_WH_PER_METER_PER_THROTTLE * throttle,
        flat -- independent of active modules, cargo load, or Sport Nav
        multipliers (Pioneer's throttle^1.5 power/speed model in the base
        VehicleEnergyMixin doesn't apply here). Overriding this single method
        is enough: minimum_wh_per_meter(), calculate_trip_energy(),
        energy_needed_to_return_now()/_comfortably(), and energy_wh_for_leg()
        all call through it rather than duplicating the formula.
        """
        if throttle <= 0:
            return 0.0
        return ROVER_WH_PER_METER_PER_THROTTLE * throttle

    def max_safe_throttle_for_leg(self, target_coords, curr_wh=None):
        """
        Rover equivalent of VehicleEnergyMixin.max_safe_throttle_for_leg(),
        re-solved for Rover's own linear-in-throttle Wh/m model instead of
        Pioneer's sqrt(throttle) one:
            leg_wh(t) = distance * ROVER_WH_PER_METER_PER_THROTTLE * t
            leg_wh(t) * SAFETY_MARGIN_MULTIPLIER <= available_for_leg
            => t <= available_for_leg / (distance * ROVER_WH_PER_METER_PER_THROTTLE * SAFETY_MARGIN_MULTIPLIER)
        (Pioneer's version instead solves via sqrt because its power term is
        throttle^1.5 against a throttle^1 speed term -- see its docstring.)
        """
        distance = self.distance_to(target_coords[0], target_coords[1])
        if distance <= 0:
            return self.MAX_SPEEDMODE_THROTTLE

        if curr_wh is None:
            curr_wh, _, _ = self.get_battery()
        nearest_cs, _ = self.get_nearest_charging_station(from_coords=target_coords)
        reserve_needed = (self.distance_between(target_coords, nearest_cs) * self.minimum_wh_per_meter() * self.SAFETY_MARGIN_MULTIPLIER) + self.MIN_EMERGENCY_RESERVE_WH
        available_for_leg = curr_wh - reserve_needed
        if available_for_leg <= 0:
            return 0.0

        denom = distance * ROVER_WH_PER_METER_PER_THROTTLE * self.SAFETY_MARGIN_MULTIPLIER
        if denom <= 0:
            return self.MAX_SPEEDMODE_THROTTLE

        return max(0.0, min(self.MAX_SPEEDMODE_THROTTLE, available_for_leg / denom))

    def fit_rover_loadout(self):
        """Mounts the ROVER_LOADOUT kinds with no module mounted; blocks until they are in."""
        mounted = [s.module_id for s in self._slots() if s.module_id]
        missing = [m for m in ROVER_LOADOUT if not any(x.startswith(m) for x in mounted)]
        if missing:
            self.fit_loadout({"modules": missing}, "Rover loadout")

    def run(self):
        """Fits the Rover loadout, then runs expeditions forever (MineJob with RoverTargets)."""
        self.fit_rover_loadout()
        self.run_job_loop(MineJob(self, RoverTargets()))
