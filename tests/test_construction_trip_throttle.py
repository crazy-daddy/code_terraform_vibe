"""BuildJob trip throttle: at a station, a far chain of cargo-served
jobs lowers cruise_throttle for the trip; away from a station the planned
throttle stays; back at a station without served jobs it returns to cruise."""
import unittest

import harness
import pioneer_construction
from job_build import BuildJob
from tree_console import TreeConsole
from vehicle_energy import VehicleEnergyMixin

STATION = (170.0, 80.0)


def _matching(*coords):
    return [(0, 1, 0.0, f"bp_{i}", {"id": f"bp_{i}", "coords": c, "progress": 0.0}) for i, c in enumerate(coords)]


class _Host(pioneer_construction.PioneerConstructionMixin):
    name = "pioneer_4"
    MIN_SPEEDMODE_THROTTLE = VehicleEnergyMixin.MIN_SPEEDMODE_THROTTLE
    SAFETY_MARGIN_MULTIPLIER = VehicleEnergyMixin.SAFETY_MARGIN_MULTIPLIER
    MIN_EMERGENCY_RESERVE_WH = VehicleEnergyMixin.MIN_EMERGENCY_RESERVE_WH

    def __init__(self, position=STATION, wh=200.0):
        self.log = TreeConsole()
        self.cruise_throttle = 0.5
        self.wh_per_progress = 0.0
        self.position = position
        self.wh = wh

    def get_nearest_charging_station(self, from_coords=None):
        return STATION, {"id": "charging_station_2"}

    def get_all_charging_stations(self):
        return [{"id": "charging_station_2", "coords": STATION}]

    def get_position(self):
        return self.position

    def distance_between(self, a, b):
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    def get_battery(self):
        return self.wh, 200.0, self.wh / 200.0

    def wh_per_meter_at_throttle(self, throttle, cargo_units=None):
        return 0.27 * throttle ** 0.5


FAR_CHAIN = [(680.0 + 10 * i, 55.0) for i in range(10)]


def _builder():
    """(host, BuildJob over it)."""
    host = _Host()
    return host, BuildJob(host)


class TripThrottleTests(harness.StubTestCase):
    def test_far_chain_lowers_throttle(self):
        host, job = _builder()
        job._plan_trip_throttle(_matching(*FAR_CHAIN))
        self.assertLess(host.cruise_throttle, 0.5)
        self.assertGreaterEqual(host.cruise_throttle, VehicleEnergyMixin.MIN_SPEEDMODE_THROTTLE)
        self.assertEqual(job.base_cruise_throttle, 0.5)
        self.assertFalse(hasattr(host, "base_cruise_throttle"))

    def test_near_job_keeps_cruise(self):
        host, job = _builder()
        job._plan_trip_throttle(_matching((200.0, 55.0)))
        self.assertEqual(host.cruise_throttle, 0.5)

    def test_field_keeps_trip_throttle_then_station_restores(self):
        host, job = _builder()
        job._plan_trip_throttle(_matching(*FAR_CHAIN))
        planned = host.cruise_throttle
        host.position = FAR_CHAIN[0]
        host.wh = 60.0
        job._plan_trip_throttle(_matching(*FAR_CHAIN[1:]))
        self.assertEqual(host.cruise_throttle, planned)
        host.position = STATION
        host.wh = 200.0
        job._plan_trip_throttle([])
        self.assertEqual(host.cruise_throttle, 0.5)


if __name__ == "__main__":
    unittest.main()
