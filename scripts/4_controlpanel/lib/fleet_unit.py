# Fleet unit mixin: the parts Drone and ground Vehicle controllers share --
# job intent, fleet.status telemetry, the operator recall flag, resumable
# mission records and the role loop run_job_loop(job) (lib/job_base.py).
# Navigation, energy and cargo stay per kind (flying vs driving, oil vs Wh).
# Each controller sets MISSION_KEY, LEGACY_MISSION_KEY_PREFIX and RECALL_KEY
# and implements _mission_claims(), _owns(), adopt_mission(),
# handle_recall_if_active() and _telemetry_extra().

from typing import TYPE_CHECKING

import fleet_claims_common as common
import fleet_status
from game_clock import now_tick
from mission import Mission
from script_parking import ParkRequester
from swallow import swallowed
from tree_console import flush_all, reset_all
from version_guard import validate_game_version

if TYPE_CHECKING:
    from drone import DroneController
    from job_base import Job
    from vehicle import VehicleController


class FleetUnitMixin:
    MISSION_KEY = ""
    LEGACY_MISSION_KEY_PREFIX = ""
    RECALL_KEY = ""
    # Script parking kind (lib/script_parking.py PAUSE_KINDS): an idle unit asks
    # the panel to pause its script. None never asks (Rovers).
    PARK_KIND = None
    _park_requester = None

    @property
    def _host(self) -> "DroneController | VehicleController":
        return self  # type: ignore[return-value]

    def get_current_tick(self):
        return now_tick()

    def run_job_loop(self, job: "Job"):
        """
        Runs job forever (lib/job_base.py): job.hold() first (a delay while
        the unit cannot act at all, e.g. a stranded drone), else one
        job.step() per cycle, or job.recall_delay while recalled. An
        exception stops the unit (stop_moving()), lets the job release what
        it holds (job.on_error()) and retries after 5 s. next_job() may swap
        the job between cycles.
        """
        host = self._host
        validate_game_version()
        job.announce()
        while True:
            reset_all()
            try:
                delay = job.hold()
                if delay is None:
                    if host.handle_recall_if_active():
                        delay = job.recall_delay
                    else:
                        delay = job.step()
            except Exception as e:
                host.log.level("error").print(f"[{host.name}] {job.name} job exception: {e}.")
                try:
                    self.stop_moving()
                except Exception as error:
                    swallowed("fleet_unit.FleetUnitMixin.run_job_loop: stop_moving", error)
                try:
                    job.on_error()
                except Exception as error:
                    swallowed("fleet_unit.FleetUnitMixin.run_job_loop: job.on_error", error)
                delay = 5.0
            try:
                self.park_update(job)
            except Exception as error:
                swallowed("fleet_unit.FleetUnitMixin.run_job_loop: park_update", error)
            following = self.next_job(job)
            if following is not job:
                job.on_leave()
                following.announce()
                job = following
            if delay:
                flush_all()
                sleep(delay)

    def park_update(self, job: "Job"):
        """Files or withdraws this unit's park request after a loop cycle (script_parking.ParkRequester)."""
        host = self._host
        if not self.PARK_KIND:
            return
        requester = self._park_requester
        if requester is None or requester.role != host.role:
            requester = self._park_requester = ParkRequester(host.name, self.PARK_KIND, host.role)
        requester.update(self.parkable(job))

    def parkable(self, job: "Job"):
        """True when the script may be paused: a no-work state ("IDLE*", SURVEY_COMPLETE; not
        READY_* or off duty), the job agrees (job.parkable()) and the unit is at a safe spot (park_spot_ok())."""
        state = self._host.state or ""
        return (state.startswith("IDLE") or state == "SURVEY_COMPLETE") and job.parkable() and self.park_spot_ok()

    def park_spot_ok(self) -> bool:
        """True where the unit may wait paused. Default: nowhere."""
        return False

    def next_job(self, job: "Job") -> "Job":
        """The job for the next cycle of run_job_loop(); default keeps job."""
        return job

    def stop_moving(self):
        """Stops the unit where it is after a job exception (run_job_loop()). Default: nothing; a vehicle brakes."""
        return

    def set_intent(self, text):
        """One-line job description (lib/fleet_intent.py describe()) carried
        by every publish_telemetry() until replaced, cleared (None) or an
        idle state (fleet_status.is_idle()) ends the job."""
        host = self._host
        if text != host.intent:
            host.log.debug(f"[{host.name}] intent: {text!r}.")
        host.intent = text

    def publish_telemetry(self, state, target_desc=None):
        """Publishes live status to the shared fleet.status archive dict (lib/fleet_status.py)."""
        host = self._host
        host.state = state
        if fleet_status.is_idle(state):
            host.intent = None
        curr_wh, _cap_wh, lvl = host.get_battery()
        target = host.current_target
        telemetry = {
            "name": host.name,
            "state": state,
            "wh": round(curr_wh, 1),
            "level": round(lvl, 2),
            "target": target_desc or (target.get("name") if target else "none"),
            "intent": host.intent,
            "role": host.role,
            "tick": host.get_current_tick(),
        }
        telemetry.update(host._telemetry_extra())
        wrote = fleet_status.publish(host.name, telemetry)
        host.log.trace(f"[{host.name}] publish_telemetry() -> fleet.status[{host.name!r}] {'written' if wrote else 'unchanged, throttled'}: {telemetry}.")

    def is_recalled(self):
        """
        True when the operator has set this unit's recall flag (the recall
        switch on the FLEET card, vehicles_panel.py). Checked every loop
        cycle -- see handle_recall_if_active() -- so an active mission is
        abandoned promptly rather than only at the next natural idle point.
        """
        return common.is_flagged(self.RECALL_KEY, self._host.name)

    def clear_mission(self):
        common.clear_mission(self.MISSION_KEY, self._host.name)

    def _read_mission(self) -> "dict | None":
        """This unit's stored mission record (legacy per-unit keys move in on first read)."""
        host = self._host
        return common.read_mission(self.MISSION_KEY, self.LEGACY_MISSION_KEY_PREFIX, host.name, host.log)

    def load_mission(self) -> "Mission | None":
        """
        Restores an in-progress target after a script reload, provided this
        unit still owns that target's claim (not reassigned or expired while
        the script was down). A mission without a target_key holds no claim
        (the drone hauler's "haul" delivery) and is restored as saved. The
        claims mixin's adopt_mission() sets host.mission. A drone's go_to()
        is cancelled by a script restart (drone.md), so for drones this
        restores which target to head back to; the flight leg is always
        re-issued. None when there was nothing to resume.
        """
        host = self._host
        record = self._read_mission()
        if record is None:
            return None
        target_key = record.get("target_key")
        if not target_key and not record.get("kind"):
            return None
        if target_key:
            claim = host._mission_claims().get(target_key)
            if not claim or not host._owns(claim):
                host.log.debug(f"[{host.name}] load_mission: saved mission for '{target_key}' found but its claim is no longer ours; discarding.")
                self.clear_mission()
                return None
        mission = Mission.from_record(record)
        host.adopt_mission(mission)
        return mission
