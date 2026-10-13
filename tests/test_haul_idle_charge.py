"""job_haul.HaulJob.idle(): a hauler idle HAUL_IDLE_CHARGE_TICKS in a row docks at a drone_service."""

import unittest
from types import SimpleNamespace

import harness  # noqa: F401  (sets up the script lib path)
from drone_hauler import HAUL_IDLE_CHARGE_TICKS, DroneHaulerMixin
from job_haul import HaulJob


class _Host(DroneHaulerMixin):
    name = "hauler_1"
    LAUNCH_MIN_SOC = 0.80

    def __init__(self, frac=0.9, docked=False):
        self.tick = 0
        self.frac = frac
        self.docked = docked
        self.services = []
        self.hovered = 0
        self.log = SimpleNamespace(debug=lambda message: None)

    def get_current_tick(self):
        return self.tick

    def get_battery(self):
        return self.frac * 100, 100, self.frac

    def docked_at_service(self):
        return self.docked

    def go_to_nearest_service(self, reason):
        self.services.append(reason)
        return True

    def hover_wait(self, state, target_desc=None):
        self.hovered += 1

    def publish_telemetry(self, state, target=None):
        pass


class HaulIdleChargeTests(unittest.TestCase):
    def _idle_for(self, host, ticks):
        job = HaulJob(host)
        job.idle()
        host.tick += ticks
        job.idle()
        return job

    def test_short_idle_hovers(self):
        host = _Host()
        self._idle_for(host, HAUL_IDLE_CHARGE_TICKS - 1)
        self.assertEqual(host.services, [])
        self.assertEqual(host.hovered, 2)

    def test_long_idle_goes_to_charge(self):
        host = _Host()
        self._idle_for(host, HAUL_IDLE_CHARGE_TICKS)
        self.assertEqual(len(host.services), 1)

    def test_full_tank_keeps_hovering(self):
        host = _Host(frac=0.99)
        self._idle_for(host, HAUL_IDLE_CHARGE_TICKS)
        self.assertEqual(host.services, [])

    def test_job_resets_streak(self):
        host = _Host()
        job = HaulJob(host)
        job.idle()
        host.tick += HAUL_IDLE_CHARGE_TICKS
        job.idle_since = None  # pick() found a job meanwhile
        job.idle()
        self.assertEqual(host.services, [])


if __name__ == "__main__":
    unittest.main()
