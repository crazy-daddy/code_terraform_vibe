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
import fleet_status
from vehicle_navigation import VehicleNavigationMixin
from vehicle_energy import VehicleEnergyMixin
from vehicle_claims import VehicleClaimsMixin
from vehicle_cargo import VehicleCargoMixin
from vehicle_survey import VehicleSurveyMixin
from vehicle_mining import VehicleMiningMixin
from outpost_mining import HOME_OUTPOST_ID


class VehicleController(
    VehicleNavigationMixin,
    VehicleEnergyMixin,
    VehicleClaimsMixin,
    VehicleCargoMixin,
    VehicleSurveyMixin,
    VehicleMiningMixin,
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

    def __init__(self, vehicle, home_base=None, cruise_throttle=None):
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
        # None (the common case -- a thin entrypoint script passes nothing)
        # means "follow the fleet-wide archive default" (see
        # default_cruise_throttle()/DEFAULT_CRUISE_THROTTLE_KEY in
        # vehicle_energy.py), so raising that one archive value speeds up
        # every such vehicle at once. An explicit cruise_throttle here (e.g.
        # the demand-driven transporter role's cruise_throttle=1.0) always
        # overrides it regardless of the archive value.
        self.cruise_throttle = cruise_throttle if cruise_throttle is not None else self.default_cruise_throttle()

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
        self.log.trace(f"[{self.name}] get_vehicle_index() called on name={self.name!r}.")
        digits = ""
        for ch in str(self.name):
            if ch.isdigit():
                digits += ch
        if digits:
            try:
                index = int(digits)
                self.log.trace(f"[{self.name}] get_vehicle_index() -> {index} (parsed digits {digits!r}).")
                return index
            except Exception:
                self.log.trace(f"[{self.name}] get_vehicle_index() -> 1 (failed to parse digits {digits!r}).")
                return 1
        self.log.trace(f"[{self.name}] get_vehicle_index() -> 1 (no digits found in name).")
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
        """Publishes live vehicle status to the shared fleet.status archive dict (lib/fleet_status.py)."""
        self.log.trace(f"[{self.name}] publish_telemetry(state={state!r}, target_desc={target_desc!r}) called.")
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
        wrote = fleet_status.publish(self.name, telemetry)
        self.log.trace(f"[{self.name}] publish_telemetry() -> fleet.status[{self.name!r}] {'written' if wrote else 'unchanged, throttled'}: {telemetry}.")
