# Shared Base Library for Surface Vehicle Automation (Rover & Pioneer)
# Provides navigation, dynamic energy accounting, fleet coordination,
# target reservation/claims, station recharging, and cargo offloading.
#
# The implementation is split by concern into focused mixins so no single
# file becomes a dumping ground; VehicleController composes them and stays
# the single import point for RoverController / PioneerController:
#   - vehicle_navigation.py: driving, stall recovery
#   - vehicle_energy.py: battery accounting, trip budgeting (station discovery: charging_stations.py)
#   - vehicle_charging.py: recharge_at_station, balance_dock, drive_with_recharge, return_to_base
#   - vehicle_claims.py: fleet-wide target claims, hardware-capability blacklist, sole writer of self.mission
#   - mission.py: Mission record (current job target); current_target* below are read-only views of it
#   - vehicle_cargo.py: cargo offload into Base Inventory
#   - vehicle_recall.py: recall return to base and decommission prep (unload, charge, strip and sell parts)
#   - vehicle_survey.py: sonar field work (scans, known-contact routes, spiral waypoints)
#   - vehicle_mining.py: mineral-site discovery, claiming and drill execution, capability-aware
#     (Rover's basic drill vs Pioneer's Industrial/Heavy drill); no loop
#   - job_base.py: Job, one role's state and step logic; run_job_loop() below runs it
#     (BuildJob in job_build.py, SurveyJob in job_survey.py, MineJob in job_mine.py)

from tree_console import TreeConsole, flush_all, reset_all
from version_guard import validate_game_version
from swallow import swallowed
from vehicle_navigation import VehicleNavigationMixin
from vehicle_energy import VehicleEnergyMixin
from vehicle_charging import VehicleChargingMixin
from vehicle_claims import VehicleClaimsMixin
from vehicle_cargo import VehicleCargoMixin
from vehicle_recall import VehicleRecallMixin
from vehicle_survey import VehicleSurveyMixin
from vehicle_mining import VehicleMiningMixin
from outpost_mining import HOME_OUTPOST_ID
from construction_plan import coords_of
from fleet_unit import FleetUnitMixin
from mission import Mission
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from job_base import Job


class VehicleController(
    VehicleNavigationMixin,
    VehicleEnergyMixin,
    VehicleChargingMixin,
    VehicleClaimsMixin,
    VehicleCargoMixin,
    VehicleRecallMixin,
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
        # The current job target (lib/mission.py); written only by
        # VehicleClaimsMixin.begin_mission/adopt_mission/end_mission.
        self.mission: "Mission | None" = None
        self.stockpile_empty_reason = ""  # why build_local_stockpile_candidates() found nothing (vehicle_mining.py)
        self.assigned_slot_coords = self.get_home_slot_coords()
        self.home_coords = self.assigned_slot_coords

        # Resume an in-progress mission left over from before a script reload,
        # if we still own that target's claim (see vehicle_claims.py).
        resumed = self.load_mission()
        if isinstance(resumed, Mission):
            self.log.print(f"[{self.name}] Resuming mission '{resumed.kind}' on target '{resumed.target_key}' after reload.")
            self.log.debug(f"[{self.name}] Recovered mission record: target={resumed.target!r}, saved_tick={resumed.tick}, current_tick={self.get_current_tick()}.")
            if resumed.kind == "mine":
                self.restore_yield_reservation_flag()
                self.log.debug(f"[{self.name}] Mission kind 'mine' -> restored yield reservation flag (reserved_yield={resumed.reserved_yield}).")
        else:
            self.log.debug(f"[{self.name}] No resumable mission found in archive; starting fresh from state 'INIT'.")

    @property
    def current_target(self):
        """The mission's target dict, None without a mission. Read-only: VehicleClaimsMixin.begin_mission/end_mission write self.mission."""
        return self.mission.target if self.mission is not None else None

    @current_target.setter
    def current_target(self, value):
        raise AttributeError("current_target is read-only; use begin_mission()/end_mission() (lib/vehicle_claims.py).")

    @property
    def current_target_key(self):
        """The mission's claim key, None without a mission. Read-only, see current_target."""
        return self.mission.target_key if self.mission is not None else None

    @current_target_key.setter
    def current_target_key(self, value):
        raise AttributeError("current_target_key is read-only; use begin_mission()/end_mission() (lib/vehicle_claims.py).")

    @property
    def current_target_reserved(self):
        """True while the mission holds a yield reservation. Read-only, see current_target."""
        return self.mission is not None and self.mission.reserved_yield

    @current_target_reserved.setter
    def current_target_reserved(self, value):
        raise AttributeError("current_target_reserved is read-only; use begin_mission()/end_mission() (lib/vehicle_claims.py).")

    def run_job_loop(self, job: "Job"):
        """
        Runs job forever (lib/job_base.py): one job.step() per cycle, or
        job.recall_delay while recalled. An exception brakes, lets the job
        release what it holds (job.on_error()) and retries after 5 s.
        next_job() may swap the job between cycles.
        """
        validate_game_version()
        job.announce()
        while True:
            reset_all()
            try:
                if self.handle_recall_if_active():
                    delay = job.recall_delay
                else:
                    delay = job.step()
            except Exception as e:
                self.log.level("error").print(f"[{self.name}] {job.name} job exception: {e}. Braking.")
                try:
                    self.vehicle.nav.brake()
                except Exception as error:
                    swallowed("vehicle.VehicleController.run_job_loop: self.vehicle.nav.brake", error)
                try:
                    job.on_error()
                except Exception as error:
                    swallowed("vehicle.VehicleController.run_job_loop: job.on_error", error)
                delay = 5.0
            following = self.next_job(job)
            if following is not job:
                job.on_leave()
                following.announce()
                job = following
            if delay:
                flush_all()
                sleep(delay)

    def next_job(self, job: "Job") -> "Job":
        """The job for the next cycle of run_job_loop(); default keeps job."""
        return job

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
