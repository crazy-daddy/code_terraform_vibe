"""lib/fleet_status.py state classifier and its readers (fleet_unit intent, drone hauler presence)."""
import unittest

import fleet_status
import logistics_requests
from archive import archive
from harness import StubTestCase


class ClassifierTests(unittest.TestCase):
    def test_idle_covers_every_idle_prefix_and_ready_state(self):
        for state in ("IDLE", "IDLE_AT_BASE", "IDLE_NO_TARGETS", "IDLE_OUT_OF_RANGE", "READY_AT_BASE",
                      "READY_AT_DEPOT", "READY_AT_OUTPOST", "SURVEY_COMPLETE", "WAITING_AFTERMATH"):
            self.assertTrue(fleet_status.is_idle(state), state)

    def test_off_duty_is_idle_too(self):
        for state in fleet_status.OFF_DUTY_STATES:
            self.assertTrue(fleet_status.is_off_duty(state), state)
            self.assertTrue(fleet_status.is_idle(state), state)

    def test_working_states(self):
        for state in ("DELIVERING", "MINING", "BUILDING", "WAITING_DEPOT_BAY", None, ""):
            self.assertFalse(fleet_status.is_idle(state), state)
        self.assertFalse(fleet_status.is_off_duty("IDLE_AT_BASE"))


class DroneHaulerPresenceTests(StubTestCase):
    def test_off_duty_hauler_drone_is_not_present(self):
        tick = self.world.clock.now
        archive.set(fleet_status.FLEET_STATUS_KEY, {"drone_1": {"role": "hauler", "engine": "electric", "state": "RECALLED", "tick": tick}})
        self.assertFalse(logistics_requests.drone_haulers_present(tick))
        archive.set(fleet_status.FLEET_STATUS_KEY, {"drone_1": {"role": "hauler", "engine": "electric", "state": "IDLE_AT_BASE", "tick": tick}})
        self.assertTrue(logistics_requests.drone_haulers_present(tick))


if __name__ == "__main__":
    unittest.main()
