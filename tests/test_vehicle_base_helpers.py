"""Vehicle base helpers shared by the role mixins: energy_for_distance()
(vehicle_energy), brake_if_able() (vehicle_navigation) and
drive_to_nearest_station() (vehicle_charging)."""

import unittest
from types import SimpleNamespace

import harness  # noqa: F401 (side effect: installs game builtins and lib paths)
import vehicle_charging
import vehicle_energy
import vehicle_navigation


class _Host(
    vehicle_energy.VehicleEnergyMixin, vehicle_navigation.VehicleNavigationMixin, vehicle_charging.VehicleChargingMixin
):
    SAFETY_MARGIN_MULTIPLIER = 1.5
    MIN_EMERGENCY_RESERVE_WH = 8.0
    cruise_throttle = 0.6

    def __init__(self, vehicle=None, reachable=True):
        self.vehicle = vehicle or SimpleNamespace()
        self.reachable = reachable
        self.drives = []

    def wh_per_meter_at_throttle(self, throttle, cargo_units=None):
        return throttle

    def get_nearest_charging_station(self, from_coords=None):
        return (3.0, 4.0), "cs_1"

    def drive_to(self, target_x, target_y, precision=1.5, timeout_ticks=None):
        self.drives.append((target_x, target_y, precision))
        return self.reachable


class _Nav:
    def __init__(self, fail=False):
        self.fail = fail
        self.brakes = 0

    def brake(self):
        self.brakes += 1
        if self.fail:
            raise RuntimeError("unpowered")


class EnergyForDistanceTests(unittest.TestCase):
    def test_cruise_rate_margin_and_reserve(self):
        self.assertAlmostEqual(_Host().energy_for_distance(10.0), 10.0 * 0.6 * 1.5 + 8.0)

    def test_explicit_rate(self):
        self.assertAlmostEqual(_Host().energy_for_distance(10.0, 0.2), 10.0 * 0.2 * 1.5 + 8.0)


class BrakeIfAbleTests(unittest.TestCase):
    def test_no_nav_is_a_no_op(self):
        _Host().brake_if_able("test")

    def test_brakes(self):
        nav = _Nav()
        _Host(SimpleNamespace(nav=nav)).brake_if_able("test")
        self.assertEqual(nav.brakes, 1)

    def test_failing_brake_is_swallowed(self):
        nav = _Nav(fail=True)
        _Host(SimpleNamespace(nav=nav)).brake_if_able("test")
        self.assertEqual(nav.brakes, 1)


class DriveToNearestStationTests(unittest.TestCase):
    def test_returns_station_when_reached(self):
        host = _Host()
        self.assertEqual(host.drive_to_nearest_station(), (3.0, 4.0))
        self.assertEqual(host.drives, [(3.0, 4.0, 1.0)])

    def test_none_when_drive_fails(self):
        self.assertIsNone(_Host(reachable=False).drive_to_nearest_station())


if __name__ == "__main__":
    unittest.main()
