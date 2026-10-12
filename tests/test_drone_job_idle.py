"""drone_job.DroneJob.idle(): an idle drone frees its Drone Depot bay.

2026-10-12: an idle bio miner held the home Depot's only bay, so a FLEET
Commission deploy there kept failing with drone_station_full."""

import unittest
from types import SimpleNamespace

import harness  # noqa: F401  (sets up the script lib path)
from drone_job import DroneJob


class _Host:
    name = "drone_1"

    def __init__(self, station="drone_station_1", service=False, cargo=0):
        self.drone = SimpleNamespace()
        self.station = station
        self.service = service
        self.cargo = cargo
        self.left = 0
        self.published = []

    def current_station(self):
        return self.station

    def docked_at_service(self):
        return self.service

    def cargo_count(self):
        return self.cargo

    def leave_station(self):
        self.left += 1
        self.station = ""
        return True

    def publish_telemetry(self, state, target=None):
        self.published.append(state)


class IdleReleasesDepotBayTests(unittest.TestCase):
    def _idle(self, host):
        job = DroneJob(host)
        job.defer(30.0, "IDLE_NO_TARGETS")
        self.assertEqual(job.idle(), 30.0)
        self.assertEqual(host.published, ["IDLE_NO_TARGETS"])
        return host.left

    def test_empty_drone_leaves_depot_bay(self):
        self.assertEqual(self._idle(_Host()), 1)

    def test_drone_service_berth_kept(self):
        self.assertEqual(self._idle(_Host(service=True)), 0)

    def test_cargo_aboard_keeps_bay(self):
        self.assertEqual(self._idle(_Host(cargo=5)), 0)

    def test_undocked_drone_untouched(self):
        self.assertEqual(self._idle(_Host(station="")), 0)


if __name__ == "__main__":
    unittest.main()
