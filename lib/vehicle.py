# Shared Base Library for Surface Vehicle Automation (Rover & Pioneer)
# Provides navigation, dynamic energy accounting, fleet coordination,
# target reservation/claims, station recharging, and cargo offloading.
#
# The implementation is split by concern into focused mixins so no single
# file becomes a dumping ground; VehicleController composes them and stays
# the single import point for RoverController / PioneerController:
#   - vehicle_navigation.py: driving, stall recovery, multi-stop recharge routing
#   - vehicle_energy.py: battery accounting, trip budgeting, charging-station discovery
#   - vehicle_claims.py: fleet-wide target claims and hardware-capability blacklist
#   - vehicle_cargo.py: cargo offload into Base Inventory
#   - vehicle_survey.py: sonar/drill field work and the autonomous survey loop

from archive import archive
from vehicle_navigation import VehicleNavigationMixin
from vehicle_energy import VehicleEnergyMixin
from vehicle_claims import VehicleClaimsMixin
from vehicle_cargo import VehicleCargoMixin
from vehicle_survey import VehicleSurveyMixin


class VehicleController(
    VehicleNavigationMixin,
    VehicleEnergyMixin,
    VehicleClaimsMixin,
    VehicleCargoMixin,
    VehicleSurveyMixin,
):
    """
    Unified base controller for autonomous surface vehicles (Rover, Pioneer).
    Manages navigation, telemetry, battery thresholds, station charging,
    target claims, and modular tool operations. Behavior lives in the
    vehicle_*.py mixins above; this class just wires them together plus the
    small set of cross-cutting helpers (identity, coordinate parsing,
    telemetry) that every mixin relies on.
    """
    DEFAULT_CRUISE_THROTTLE = 0.5
    DEFAULT_SPEED_MPH = 25.0

    def __init__(self, vehicle, home_coords=(0, 0), cruise_throttle=0.5):
        self.vehicle = vehicle
        self.name = getattr(vehicle, "id", getattr(vehicle, "name", "vehicle"))
        self.home_coords = home_coords
        self.cruise_throttle = cruise_throttle

        # Each vehicle and module loadout gets its own calibration. Legacy
        # shared values are read only as a migration fallback.
        self.wh_per_meter = self.load_wh_per_meter()
        self.total_distance_driven = 0.0
        self.total_wh_spent_moving = 0.0

        # State tracking
        self.state = "INIT"
        self.current_target = None
        self.current_target_key = None
        self.assigned_slot_coords = self.get_home_slot_coords()

    def get_vehicle_index(self):
        """Extracts integer index from vehicle name (e.g. 'rover_1' -> 1, 'pioneer_2' -> 2)."""
        digits = ""
        for ch in str(self.name):
            if ch.isdigit():
                digits += ch
        if digits:
            try:
                return int(digits)
            except Exception:
                return 1
        return 1

    def get_rover_index(self):
        """Backward compatibility alias for rover index."""
        return self.get_vehicle_index()

    @staticmethod
    def extract_coords(pos):
        """Safely extracts (x, y) float tuple from tuple/list, dict, or Position object."""
        if pos is None:
            return None
        if isinstance(pos, (tuple, list)) and len(pos) >= 2:
            return (float(pos[0]), float(pos[1]))
        if isinstance(pos, dict) and "x" in pos and "y" in pos:
            return (float(pos["x"]), float(pos["y"]))
        x = getattr(pos, "x", None)
        y = getattr(pos, "y", None)
        if x is not None and y is not None:
            return (float(x), float(y))
        return None

    def get_current_tick(self):
        """Fetches current simulation tick from clock component if available."""
        clock = get_component("clock")
        if clock and hasattr(clock, "tick"):
            try:
                return clock.tick()
            except Exception:
                pass
        return 0

    def publish_telemetry(self, state, target_desc=None):
        """Publishes live vehicle status to Data Archive under a dedicated key."""
        self.state = state
        curr_wh, cap_wh, lvl = self.get_battery()
        pos = self.get_position()
        telemetry = {
            "name": self.name,
            "state": state,
            "x": round(pos[0], 1),
            "y": round(pos[1], 1),
            "wh": round(curr_wh, 1),
            "level": round(lvl, 2),
            "target": target_desc or (self.current_target["name"] if self.current_target else "none"),
            "tick": self.get_current_tick()
        }
        archive.set(f"fleet.status.{self.name}", telemetry)
        if str(self.name).startswith("rover"):
            archive.set(f"rover.status.{self.name}", telemetry)
