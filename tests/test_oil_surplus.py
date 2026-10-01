"""Oil Generator surplus base load (5_steampower lib/oil_generator.py) and fluid_routing.fluid_reserve_fraction()."""
import unittest

import harness
import oil_generator
import fluid_routing


class _Generator:
    id = "oil_generator_1"


class SurplusHysteresisTests(harness.StubTestCase):
    def controller(self):
        return oil_generator.OilGeneratorController(_Generator())

    def test_starts_at_start_fraction_and_holds_to_stop_fraction(self):
        c = self.controller()
        self.assertFalse(c.update_surplus(oil_generator.OIL_SURPLUS_START_FRACTION - 0.01))
        self.assertTrue(c.update_surplus(oil_generator.OIL_SURPLUS_START_FRACTION))
        self.assertTrue(c.update_surplus(oil_generator.OIL_SURPLUS_STOP_FRACTION))
        self.assertFalse(c.update_surplus(oil_generator.OIL_SURPLUS_STOP_FRACTION - 0.01))

    def test_no_oil_tank_means_no_surplus(self):
        c = self.controller()
        c.surplus = True
        self.assertFalse(c.update_surplus(None))

    def test_surplus_throttle_carries_consumption(self):
        c = self.controller()

        class Grid:
            consumed = 800.0
        self.assertAlmostEqual(c.surplus_throttle(Grid(), 1.0, 2), 800.0 / 2 / oil_generator.OIL_GENERATOR_RATED_W)
        self.assertAlmostEqual(c.surplus_throttle(Grid(), 0.5, 2), (800.0 + oil_generator.OIL_RECHARGE_W) / 2 / oil_generator.OIL_GENERATOR_RATED_W)


class ReserveFractionTests(harness.StubTestCase):
    def test_no_tank_is_none(self):
        self.assertIsNone(fluid_routing.fluid_reserve_fraction("oil"))


if __name__ == "__main__":
    unittest.main()
