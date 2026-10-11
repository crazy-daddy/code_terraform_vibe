# DroneJob: the Job contract (lib/job_base.py) with a drone's defaults, run
# by FleetUnitMixin.run_job_loop() (lib/fleet_unit.py) from
# DroneController.run(). hold(): a stranded or rescued drone waits for the
# drone_service. prepare(): answers a fleet-upgrade swap request. pick()
# records why it found no mission with defer(); idle() publishes that state
# and sleeps that delay. on_error(): releases every biosite claim and the
# mission. Subclasses: ScoutJob (lib/job_scout.py), BiositeJob
# (lib/job_biosite.py), HaulJob (lib/job_haul.py), AftermathJob
# (lib/job_aftermath.py).

from typing import TYPE_CHECKING

from job_base import Job
from swallow import swallowed
from tree_console import TreeConsole

if TYPE_CHECKING:
    from drone import DroneController


class DroneJob(Job):
    """
    One role of a drone. Same contract as Job; the host is a DroneController.
    poll_interval is the short sleep after a blocked cycle (charging, bay
    taken, unload deferred); idle_delay the sleep when nothing is left to do.
    """

    name = "drone"
    log_module = "drone"  # the role's console module (console.log_levels), as the old loops had
    poll_interval = 5.0
    recall_delay = 5.0
    idle_delay = 30.0

    def __init__(self, host):
        super().__init__(host)
        self.host: DroneController = host  # type: ignore[assignment]
        self.log = TreeConsole(module=self.log_module)
        # Set by defer() when pick() finds no mission: (telemetry state or None, delay).
        self.idle_state: tuple[str | None, float] | None = None

    def hold(self):
        """A stranded (stalled, scrambled) or rescued drone waits for the drone_service: STRANDED, poll_interval."""
        host = self.host
        if host.is_stranded() or self._being_rescued():
            self.log.level("warn").print(f"[{host.name}] {host.status()}; awaiting drone_service rescue.")
            host.publish_telemetry("STRANDED")
            return self.poll_interval
        return None

    def _being_rescued(self):
        rescued = getattr(self.host.drone, "is_being_rescued", None)
        if rescued is None:
            return False
        try:
            return bool(rescued()) if callable(rescued) else bool(rescued)
        except Exception as error:
            swallowed("drone_job.DroneJob._being_rescued: drone.is_being_rescued", error)
            return False

    def prepare(self):
        """Answers a chassis swap request (lib/drone_upgrade.py); parked for it: poll_interval. Subclasses extend."""
        if self.host.handle_upgrade_request_if_active():
            return self.poll_interval
        return None

    def defer(self, delay, state=None):
        """
        For pick(): no mission this cycle. idle() publishes state (when
        given; None when the caller already published) and returns delay.
        Returns None, so pick() can `return self.defer(...)`.
        """
        self.idle_state = (state, delay)

    def idle(self):
        """Publishes and sleeps what pick() recorded with defer(); IDLE_NO_TARGETS and idle_delay when it recorded nothing."""
        state, delay = self.idle_state or ("IDLE_NO_TARGETS", self.idle_delay)
        self.idle_state = None
        if state:
            self.host.publish_telemetry(state)
        return delay

    def charge_if_low(self):
        """
        Proactive return: below the comfortable return reserve the drone
        heads to its drone_service (return_to_service_for_charge()). True
        when it did (the caller sleeps poll_interval).
        """
        host = self.host
        curr_wh, _, _ = host.get_battery()
        if curr_wh <= host.energy_needed_to_return_comfortably():
            host.return_to_service_for_charge(self.log, f"Battery low ({curr_wh:.1f} {host.energy_unit()})")
            return True
        return False

    def top_up_if_unreachable(self, state, reason):
        """
        Candidates exist but none is reachable or claimable: publishes state
        and, below 98%, charges at the drone_service (a drone too low for any
        trip but above the return reserve would otherwise idle here forever).
        """
        host = self.host
        host.publish_telemetry(state)
        _, _, lvl = host.get_battery()
        if lvl < 0.98:
            host.return_to_service_for_charge(self.log, f"{reason} at {lvl * 100:.0f}% charge")

    def on_error(self):
        """Releases every biosite claim this drone holds, and with them the mission."""
        self.host.release_biosite_claim()
