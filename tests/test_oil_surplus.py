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

    def test_surplus_throttle_burns_inflow_at_target_fill(self):
        c = self.controller()
        c.oil_tons = (oil_generator.OIL_SURPLUS_TARGET_FRACTION * 1000.0, 1000.0)
        c.oil_inflow_tph = 8.0  # one generator at full throttle

        class Grid:
            consumed = 5000.0
        self.assertAlmostEqual(c.surplus_throttle(Grid(), 1.0, 2), 0.5)

    def test_surplus_throttle_corrects_toward_target(self):
        c = self.controller()
        c.oil_tons = (100.0, 100.0)
        c.oil_inflow_tph = 0.0
        correction = (100.0 - oil_generator.OIL_SURPLUS_TARGET_FRACTION * 100.0) / oil_generator.OIL_SURPLUS_CORRECT_HOURS

        class Grid:
            consumed = 5000.0
        expected = correction / oil_generator.OIL_FULL_BURN_TPH
        self.assertAlmostEqual(c.surplus_throttle(Grid(), 1.0, 1), expected)
        c.oil_tons = (50.0, 100.0)
        self.assertEqual(c.surplus_throttle(Grid(), 1.0, 1), 0.0)

    def test_surplus_throttle_capped_at_consumption(self):
        c = self.controller()
        c.oil_tons = (800.0, 1000.0)
        c.oil_inflow_tph = 80.0

        class Grid:
            consumed = 800.0
        self.assertAlmostEqual(c.surplus_throttle(Grid(), 1.0, 2), 800.0 / 2 / oil_generator.OIL_GENERATOR_RATED_W)
        self.assertAlmostEqual(c.surplus_throttle(Grid(), 0.5, 2), (800.0 + oil_generator.OIL_RECHARGE_W) / 2 / oil_generator.OIL_GENERATOR_RATED_W)

    def test_inflow_is_tank_rate_plus_burn(self):
        c = self.controller()
        c.oil_tons, c.oil_fill_tick = (500.0, 1000.0), 0
        c.update_inflow((498.0, 1000.0), 4.0, oil_generator.TICKS_PER_GAME_HOUR)
        self.assertAlmostEqual(c.oil_inflow_tph, 2.0)
        c.oil_tons, c.oil_fill_tick = (498.0, 1000.0), oil_generator.TICKS_PER_GAME_HOUR
        c.update_inflow((508.0, 1000.0), 0.0, 2 * oil_generator.TICKS_PER_GAME_HOUR)
        self.assertAlmostEqual(c.oil_inflow_tph, 2.0 + oil_generator.OIL_INFLOW_EMA_ALPHA * 8.0)

    def test_capacity_change_skips_inflow_sample(self):
        c = self.controller()
        c.oil_tons, c.oil_fill_tick = (500.0, 1000.0), 0
        c.update_inflow((900.0, 2000.0), 0.0, oil_generator.TICKS_PER_GAME_HOUR)
        self.assertIsNone(c.oil_inflow_tph)


class ReserveFractionTests(harness.StubTestCase):
    def test_no_tank_is_none(self):
        self.assertIsNone(fluid_routing.fluid_reserve_fraction("oil"))


if __name__ == "__main__":
    unittest.main()
