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
#   - vehicle_survey.py: sonar field work and the autonomous survey loop
#   - vehicle_mining.py: mineral-site discovery and drill execution, capability-aware
#     (Rover's basic drill vs Pioneer's Industrial/Heavy drill) so it's shared
#     rather than duplicated between rover.py and pioneer.py

from tree_console import TreeConsole
from vehicle_navigation import VehicleNavigationMixin
from vehicle_energy import VehicleEnergyMixin
from vehicle_claims import VehicleClaimsMixin
from vehicle_cargo import VehicleCargoMixin
from vehicle_survey import VehicleSurveyMixin
from vehicle_mining import VehicleMiningMixin
from outpost_mining import HOME_OUTPOST_ID
from construction_plan import coords_of
from fleet_unit import FleetUnitMixin


class VehicleController(
    VehicleNavigationMixin,
    VehicleEnergyMixin,
    VehicleClaimsMixin,
    VehicleCargoMixin,
    VehicleSurveyMixin,
    VehicleMiningMixin,
    FleetUnitMixin,
):
    """
    Unified base controller for autonomous surface vehicles (Rover, Pioneer).
    Manages navigation, telemetry, battery thresholds, station charging,
    target claims, and modular tool operations. Behavior lives in the
    vehicle_*.py mixins above; this class just wires them together plus the
    small set of cross-cutting helpers (identity, coordinate parsing,
    telemetry) that every mixin relies on.
    """
    DEFAULT_SPEED_MPH = 25.0

    def __init__(self, vehicle: "Rover | Pioneer", home_base=None):
        self.vehicle = vehicle
        self.name = getattr(vehicle, "id", getattr(vehicle, "name", "vehicle"))
        # home_base is an outpost id (None = the production/home outpost,
        # normalized below to the real HOME_OUTPOST_ID string so every
        # vehicle always has a concrete home_base -- e.g. vehicle_cargo.py's
        # haul-status logs print the actual outpost id instead of "None") --
        # this vehicle's "home" for is_at_base()/return_to_base()/charging
        # purposes can be any outpost, not just the production base (see
        # TODO.md Phase 3's stationed-mining role). Resolved to live objects
        # exactly ONCE here rather than re-walking outpost_network.outposts()
        # by id on every subsequent lookup (get_home_slot_coords(),
        # unload_cargo()'s destination outpost, etc. all read these cached
        # fields instead). self.home_base itself is kept only for identity
        # checks (e.g. vehicle_cargo.py's "am I home-based at all?" gate) --
        # anything that needs the outpost/station itself should use
        # self.home_outpost/self.home_charging_station.
        #
        # Trade-off: since this resolution only happens once, a charging
        # station built at this outpost *after* construction won't be picked
        # up until the next script reload/restart -- acceptable since actual
        # recharge routing (get_nearest_charging_station()) always does its
        # own fresh network-wide walk regardless; only the cached staging
        # position (assigned_slot_coords) could lag by that much.
        self.home_base = home_base if home_base is not None else HOME_OUTPOST_ID
        self.home_outpost = self.get_outpost_ref(home_base)
        self.home_charging_station = self.find_charging_station(self.home_outpost)
        # Fleet-wide default from the FLEET card's slider (see
        # default_cruise_throttle()/DEFAULT_CRUISE_THROTTLE_KEY in
        # vehicle_energy.py).
        self.cruise_throttle = self.default_cruise_throttle()

        # Travel energy uses the developer-confirmed exact power/speed model
        # (see lib/vehicle_energy.py), not an empirically-calibrated Wh/meter --
        # only construction progress energy still needs per-vehicle calibration
        # (no developer-confirmed formula for that one).
        self.wh_per_progress = self.load_wh_per_progress()
        self.total_distance_driven = 0.0
        self.total_wh_spent_moving = 0.0

        # Created once here (not per-call in vehicle_survey.py's scan_and_survey()/
        # unscanned_pois(), which both run every survey cycle) since TreeConsole.__init__
        # reads the console.log_levels archive dict -- see docs/AI_CHEATSHEET.md #0a.
        self.log = TreeConsole(module="vehicle")

        # State tracking
        self.state = "INIT"
        self.intent = None  # set_intent(); published in telemetry for the fleet cards
        self.role = None  # job designation ("hauler"/"miner"/...), set by the subclass run(); published for the fleet cards
        self.current_target = None
        self.current_target_key = None
        # True only while current_target_key holds a home-demand mine-type
        # mission with a live mining_reservations entry (see
        # VehicleMiningMixin.select_best_mining_target()) -- gates the refresh_yield()/
        # release_yield() calls in lib/vehicle_mining.py so they never fire for a
        # stockpile-path or survey/POI mission, which never reserve yield.
        self.current_target_reserved = False
        self.assigned_slot_coords = self.get_home_slot_coords()
        self.home_coords = self.assigned_slot_coords

        # Resume an in-progress mission left over from before a script reload,
        # if we still own that target's claim (see vehicle_claims.py).
        resumed = self.load_mission()
        if resumed:
            self.log.print(f"[{self.name}] Resuming mission '{resumed.get('kind')}' on target '{self.current_target_key}' after reload.")
            self.log.debug(f"[{self.name}] Recovered mission record: target={resumed.get('target')!r}, saved_tick={resumed.get('tick')}, current_tick={self.get_current_tick()}.")
            if resumed.get("kind") == "mine":
                self.restore_yield_reservation_flag()
                self.log.debug(f"[{self.name}] Mission kind 'mine' -> restored yield reservation flag (current_target_reserved={self.current_target_reserved}).")
        else:
            self.log.debug(f"[{self.name}] No resumable mission found in archive; starting fresh from state 'INIT'.")

    def get_vehicle_index(self):
        """Extracts integer index from vehicle name (e.g. 'rover_1' -> 1, 'pioneer_2' -> 2)."""
        self.log.start(f"[{self.name}] get_vehicle_index", level="debug")
        self.log.trace(f"get_vehicle_index() called on name={self.name!r}.")
        digits = ""
        for ch in str(self.name):
            if ch.isdigit():
                digits += ch
        if digits:
            try:
                index = int(digits)
                self.log.trace(f"get_vehicle_index() -> {index} (parsed digits {digits!r}).")
                self.log.end()
                return index
            except Exception:
                self.log.trace(f"get_vehicle_index() -> 1 (failed to parse digits {digits!r}).")
                self.log.end()
                return 1
        self.log.trace("get_vehicle_index() -> 1 (no digits found in name).")
        self.log.end()
        return 1

    @staticmethod
    def extract_coords(pos):
        """(x, y) floats from a tuple/list, dict or Position object, None if unreadable."""
        return coords_of(pos)

    def _telemetry_extra(self):
        pos = self.get_position()
        return {"x": round(pos[0], 1), "y": round(pos[1], 1), "home": self.home_base}
