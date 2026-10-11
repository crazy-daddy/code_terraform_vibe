# Job base class: one role's per-role state and step logic, bound to the
# unit that runs it (docs/plans/mixin_refactor/README.md, "The loop and the
# job contract"). FleetUnitMixin.run_job_loop(job) (lib/fleet_unit.py) owns
# the loop plumbing: hold, recall, exception handling, sleep. A job calls the
# unit's abilities through self.host and never stores its own state on the
# host. The defaults below are the ground vehicle's; drone jobs derive from
# DroneJob (lib/drone_job.py). Subclasses: BuildJob (lib/job_build.py),
# SurveyJob (lib/job_survey.py), MineJob (lib/job_mine.py), PullJob
# (lib/job_pull.py); drones: ScoutJob, BiositeJob, HaulJob, AftermathJob
# (lib/job_scout.py, lib/job_biosite.py, lib/job_haul.py, lib/job_aftermath.py).

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mission import Mission
    from vehicle import VehicleController


class Job:
    """
    One role of a vehicle. run_job_loop() calls hold() first (a delay while
    the unit cannot act at all; None to go on), then step() once per cycle
    and sleeps the seconds it returns (0 or None: next cycle at once).

    step() default: prepare() (None to go on, else a delay to return), then
    pick() for the next Mission (None: idle()), then execute(mission).
    A job may override step() wholesale instead (BuildJob does).
    """

    name = "job"
    recall_delay = 5.0  # sleep while the vehicle is recalled
    idle_delay = 10.0  # sleep when pick() finds no work

    def __init__(self, host):
        # Typed on the attribute, not the parameter: Pyright resolves a
        # controller's `Job(self)` against the .pyright-resolved copies, where
        # the controller is a different class than the source file's self.
        self.host: VehicleController = host

    def announce(self):
        """Logs the job going online; once per run_job_loop(), and again after a job swap."""
        self.host.log.print(f"[{self.host.name}] online: {self.name} job.")

    def hold(self) -> "float | None":
        """
        Checked before the recall flag: a delay while the unit cannot act at
        all (a drone awaiting rescue), None to go on with recall and step().
        Default: never holds.
        """
        return None

    def step(self):
        """One cycle; returns the seconds to sleep before the next."""
        delay = self.prepare()
        if delay is not None:
            return delay
        mission = self.pick()
        if mission is None:
            return self.idle()
        return self.execute(mission)

    def prepare(self) -> "float | None":
        """
        Readiness at base before picking work: tops the battery off below 95%
        when the home outpost has its own Charging Station, then runs the
        Pioneer's idle upgrade cycle when the host has one, then
        prepare_cargo(). Returns None to go on with pick(), else a delay.
        """
        host = self.host
        if host.is_at_base():
            _, _, level = host.get_battery()
            if level < 0.95 and host.home_charging_station is not None:
                host.log.print(f"[{host.name}] Battery at {level * 100:.0f}%. Recharging to 100% before launch...")
                host.recharge_at_station(target_level=1.0)
            upgrade_cycle = getattr(host, "handle_upgrade_cycle_if_idle", None)
            if upgrade_cycle is not None:
                upgrade_cycle()
        return self.prepare_cargo()

    def prepare_cargo(self) -> "float | None":
        """
        Hook for cargo already aboard before picking work (a resumed mission's
        cargo_matches_target()/cargo_full_for_resume(), unload otherwise).
        None to go on, else a delay. Default: nothing to do.
        """
        return None

    def pick(self) -> "Mission | None":
        """The next Mission to execute, None when there is no work. The only place a job obtains work."""
        raise NotImplementedError

    def execute(self, mission: "Mission"):
        """Carries mission out; returns the seconds to sleep."""
        raise NotImplementedError

    def idle(self):
        """No work: parks at the home slot as IDLE_AT_BASE; returns idle_delay."""
        if self.host.distance_to_home() > 3.0:
            self.host.return_to_base()
        self.host.publish_telemetry("IDLE_AT_BASE")
        return self.idle_delay

    def on_error(self):
        """After step() raised (the loop already braked): releases what the job holds. Default: the mission."""
        self.host.end_mission()

    def on_leave(self):
        """Before run_job_loop() switches to another job (next_job()): releases what this job holds. Default: the mission."""
        self.host.end_mission()
