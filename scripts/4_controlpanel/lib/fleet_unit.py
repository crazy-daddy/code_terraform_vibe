# Fleet unit mixin: the parts Drone and ground Vehicle controllers share --
# job intent, fleet.status telemetry, the operator recall flag and resumable
# mission records. Navigation, energy and cargo stay per kind (flying vs
# driving, oil vs Wh). Each controller sets MISSION_KEY,
# LEGACY_MISSION_KEY_PREFIX and RECALL_KEY and implements _mission_claims(),
# _owns() and _telemetry_extra().

from typing import TYPE_CHECKING
import fleet_claims_common as common
import fleet_status
from game_clock import now_tick

if TYPE_CHECKING:
    from drone import DroneController
    from vehicle import VehicleController


class FleetUnitMixin:
    MISSION_KEY = ""
    LEGACY_MISSION_KEY_PREFIX = ""
    RECALL_KEY = ""

    @property
    def _host(self) -> "DroneController | VehicleController":
        return self  # type: ignore[return-value]

    def get_current_tick(self):
        return now_tick()

    def set_intent(self, text):
        """One-line job description (lib/fleet_intent.py describe()) carried
        by every publish_telemetry() until replaced, cleared (None) or an
        idle state (fleet_status.IDLE_STATES) ends the job."""
        host = self._host
        if text != host.intent:
            host.log.debug(f"[{host.name}] intent: {text!r}.")
        host.intent = text

    def publish_telemetry(self, state, target_desc=None):
        """Publishes live status to the shared fleet.status archive dict (lib/fleet_status.py)."""
        host = self._host
        host.state = state
        if state in fleet_status.IDLE_STATES:
            host.intent = None
        curr_wh, cap_wh, lvl = host.get_battery()
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

    def save_mission(self, kind, target):
        """
        Persists the in-progress target (and its kind) so a script reload
        mid-trip resumes toward the same destination. A drone's go_to() is
        cancelled by a script restart (drone.md), so for drones this restores
        which target to head back to; the flight leg is always re-issued.
        """
        host = self._host
        if not host.current_target_key:
            return
        common.save_mission(self.MISSION_KEY, host.name, host.current_target_key, kind, target, host.get_current_tick())

    def clear_mission(self):
        common.clear_mission(self.MISSION_KEY, self._host.name)

    def _read_mission(self) -> "dict | None":
        """This unit's stored mission record (legacy per-unit keys move in on first read)."""
        host = self._host
        return common.read_mission(self.MISSION_KEY, self.LEGACY_MISSION_KEY_PREFIX, host.name, host.log)

    def load_mission(self):
        """
        Restores an in-progress target after a script reload, provided this
        unit still owns that target's claim (not reassigned or expired while
        the script was down). Returns the mission record, or None if there was
        nothing to resume.
        """
        host = self._host
        record = self._read_mission()
        if record is None or not record.get("target_key"):
            return None
        target_key = record["target_key"]
        claim = host._mission_claims().get(target_key)
        if not claim or not host._owns(claim):
            host.log.debug(f"[{host.name}] load_mission: saved mission for '{target_key}' found but its claim is no longer ours; discarding.")
            self.clear_mission()
            return None
        host.current_target_key = target_key
        host.current_target = record.get("target")
        return record
