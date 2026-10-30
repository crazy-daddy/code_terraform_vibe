"""Vehicle energy budget at its exact limits, on the real VehicleEnergyMixin.

Bug caught: a trip budget that drops the return leg or forgets the
MIN_EMERGENCY_RESERVE_WH floor sends a vehicle out on a battery that cannot
bring it home (stranded, needs a paid rescue).
"""

import unittest

from game_stubs import Cargo, VehicleBattery
from harness import StubTestCase
from vehicle_host import make_vehicle

TARGET = (100.0, 0.0)  # 100 m out from the home slot at (0, 0), 100 m back


class _EnergyCase(StubTestCase):
    def setUp(self):
        super().setUp()
        self.ctl, self.pioneer = make_vehicle(self.world)

    def set_battery(self, wh):
        self.pioneer.battery = VehicleBattery(1000.0, wh)

    def rate(self, cargo_units=0):
        return self.ctl.wh_per_meter_at_throttle(self.ctl.cruise_throttle, cargo_units=cargo_units)


class TripEnergyBoundaryTests(_EnergyCase):
    def needed_wh(self):
        """There-and-back drive with the safety margin, plus the emergency reserve."""
        drive_wh = 100.0 * self.rate() + 100.0 * self.rate()
        return drive_wh * self.ctl.SAFETY_MARGIN_MULTIPLIER + self.ctl.MIN_EMERGENCY_RESERVE_WH

    def trip(self):
        return self.ctl.calculate_trip_energy(TARGET, planned_scans=0)

    def test_total_counts_both_legs_and_reserve(self):
        self.assertAlmostEqual(self.trip()["total_required_wh"], self.needed_wh(), places=9)

    def test_battery_exactly_at_budget_is_achievable(self):
        self.set_battery(self.needed_wh())
        self.assertTrue(self.trip()["is_achievable"])

    def test_battery_1wh_below_budget_is_refused(self):
        self.set_battery(self.needed_wh() - 1.0)
        self.assertFalse(self.trip()["is_achievable"])

    def test_battery_1wh_above_budget_is_achievable(self):
        self.set_battery(self.needed_wh() + 1.0)
        self.assertTrue(self.trip()["is_achievable"])

    def test_planned_ore_weighs_down_the_return_leg(self):
        units = 10
        trip = self.ctl.calculate_trip_energy(
            TARGET, planned_drill_units=units, planned_scans=0, mine_item_id="iron_ore"
        )
        self.assertAlmostEqual(trip["drive_home_wh"], 100.0 * self.rate(cargo_units=units), places=9)
        self.assertGreater(trip["drive_home_wh"], trip["drive_out_wh"])


class MaxMineableBoundaryTests(_EnergyCase):
    def trip_wh(self, units):
        return self.ctl.calculate_trip_energy(
            TARGET, planned_drill_units=units, planned_scans=0, mine_item_id="iron_ore"
        )["total_required_wh"]

    def mineable(self):
        return self.ctl.max_mineable_units(TARGET, "iron_ore")

    def test_no_units_when_only_the_bare_trip_fits(self):
        self.set_battery(self.trip_wh(0))
        self.assertEqual(self.mineable(), 0)

    def test_no_units_1wh_below_the_bare_trip(self):
        self.set_battery(self.trip_wh(0) - 1.0)
        self.assertEqual(self.mineable(), 0)

    def test_units_agree_with_trip_check_at_its_edge(self):
        n = 5
        self.set_battery(self.trip_wh(n))
        self.assertEqual(self.mineable(), n)
        self.set_battery(self.trip_wh(n) - 1.0)
        self.assertEqual(self.mineable(), n - 1)
        self.set_battery(self.trip_wh(n) + 1.0)
        self.assertEqual(self.mineable(), n)

    def test_mineable_count_passes_the_trip_check(self):
        self.set_battery(150.0)
        n = self.mineable()
        self.assertGreater(n, 0)
        self.assertLessEqual(self.trip_wh(n), 150.0)
        self.assertGreater(self.trip_wh(n + 1), 150.0)

    def test_capped_by_free_cargo(self):
        self.pioneer.cargo = Cargo(3)
        self.set_battery(1000.0)
        self.assertEqual(self.mineable(), 3)


class SafeThrottleBoundaryTests(_EnergyCase):
    def reserve_wh(self):
        """Crawl home from TARGET at the speedmode floor rate, margin and reserve included."""
        return self.ctl.energy_for_distance(100.0, self.ctl.minimum_wh_per_meter())

    def test_zero_throttle_when_battery_only_covers_the_way_home(self):
        self.assertEqual(self.ctl.max_safe_throttle_for_leg(TARGET, curr_wh=self.reserve_wh()), 0.0)

    def test_zero_throttle_1wh_below_the_way_home(self):
        self.assertEqual(self.ctl.max_safe_throttle_for_leg(TARGET, curr_wh=self.reserve_wh() - 1.0), 0.0)

    def test_throttle_keeps_the_return_reserve(self):
        curr_wh = self.reserve_wh() + 1.0
        throttle = self.ctl.max_safe_throttle_for_leg(TARGET, curr_wh=curr_wh)
        self.assertGreater(throttle, 0.0)
        out_wh = self.ctl.energy_wh_for_leg(100.0, throttle) * self.ctl.SAFETY_MARGIN_MULTIPLIER
        self.assertAlmostEqual(out_wh, 1.0, places=6)

    def test_full_throttle_on_a_big_battery(self):
        self.assertEqual(self.ctl.max_safe_throttle_for_leg(TARGET, curr_wh=10_000.0), self.ctl.MAX_SPEEDMODE_THROTTLE)


if __name__ == "__main__":
    unittest.main()
