"""Lightning Rod reserve and the power source order (lib/power.py, lib/turbine_commit.py,
lib/oil_generator.py): bank-only full/top-up rules, rod Wh as runway, rod yield, no turbine
yield to last-resort oil, no steam surplus base load on a reactor grid."""

import unittest

import oil_generator
import power
import turbine_commit
from archive import archive
from harness import StubTestCase


def snapshot(bat_wh, bat_cap, rod_wh=0.0, rod_cap=0.0, steam_t=0.0, steam_cap=0.0):
    return {
        "bat_wh": bat_wh,
        "bat_cap": bat_cap,
        "rod_wh": rod_wh,
        "rod_cap": rod_cap,
        "steam_t": steam_t,
        "steam_cap": steam_cap,
        "tanks": 0,
    }


class ReserveTests(unittest.TestCase):
    def test_drained_rods_are_no_missing_reserve(self):
        # Full 10k Wh bank, 3 drained rods: still a full reserve.
        self.assertEqual(power.reserve_fraction(snapshot(10000.0, 10000.0, 0.0, 12000.0)), 1.0)

    def test_stored_rod_energy_is_runway(self):
        # Empty bank, rods holding 3,000 Wh: the combined reserve counts them in level and capacity.
        frac = power.reserve_fraction(snapshot(0.0, 10000.0, 3000.0, 12000.0))
        assert frac is not None
        self.assertAlmostEqual(frac, 3000.0 / 13000.0)

    def test_snapshot_without_rod_keys_still_reads(self):
        self.assertEqual(
            power.reserve_fraction({"bat_wh": 50.0, "bat_cap": 100.0, "steam_t": 0.0, "steam_cap": 0.0}), 0.5
        )


class RodYieldTests(unittest.TestCase):
    def test_yields_while_rods_hold_energy(self):
        self.assertTrue(power.rod_yield(snapshot(0.0, 10000.0, 12000.0, 12000.0)))

    def test_ends_below_the_rod_floor(self):
        rod_cap = 12000.0
        self.assertFalse(
            power.rod_yield(snapshot(10000.0, 10000.0, power.ROD_YIELD_MIN_FRACTION * rod_cap - 1.0, rod_cap))
        )

    def test_ends_below_the_combined_line(self):
        # Rods well above their floor, but a big bank nearly empty: the reserve is below the end line.
        now = snapshot(0.0, 100000.0, 4000.0, 4000.0)
        frac = power.reserve_fraction(now)
        assert frac is not None
        self.assertLess(frac, power.ROD_YIELD_END_FRACTION)
        self.assertFalse(power.rod_yield(now))

    def test_no_rods_no_yield(self):
        self.assertFalse(power.rod_yield(snapshot(0.0, 10000.0)))

    def test_yield_ends_before_any_load_is_shed(self):
        self.assertGreater(power.ROD_YIELD_END_FRACTION, power.EMERGENCY_SHED_FRACTIONS[0])


class RodNeedTests(unittest.TestCase):
    def test_rod_yield_parks_every_turbine(self):
        target, spare, reason = turbine_commit.turbine_needed(1000.0, 0.0, 0.0, 10000.0, 20, rod_yield=True)
        self.assertEqual((target, spare), (0, 0))
        self.assertIn("rod yield", reason)

    def test_rod_yield_keeps_the_steam_surplus_without_top_up(self):
        target, _, _ = turbine_commit.turbine_needed(
            1000.0, 0.0, 0.0, 10000.0, 20, all_on=False, surplus=True, rod_yield=True
        )
        self.assertEqual(target, 10 + 2)  # consumption only: ceil(1000 / 108) + spare, no 5,000 W top-up


class RodStepTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.world.add_tank("tank_full", self.world.home, "steam", 90.0, type_id="gas_tank", capacity=100.0)
        self.power = self.world.power_control
        self.ids = [f"turbine_{i}" for i in range(6)]
        for t in self.ids:
            self.world.add_turbine(t, self.world.home, 80, "tank_full", 108.0, False, 0.0)

    def grid(self, consumed=100.0, generated=648.0, stored=10000.0, capacity=10000.0, rod_wh=0.0, rod_cap=0.0):
        grid = self.world.add_grid(
            "grid_a", self.ids, consumed=consumed, generated=generated, stored=stored, capacity=capacity
        )
        grid.reserve_stored, grid.reserve_capacity = rod_wh, rod_cap
        return grid

    def test_drained_rods_do_not_hold_all_turbines_on(self):
        commit = turbine_commit.TurbineCommitment(self.power)
        commit.step(self.grid(rod_wh=0.0, rod_cap=12000.0), "grid_a")
        self.assertFalse(commit.all_on.active)
        self.assertEqual(sum(self.power.is_powered(t) for t in self.ids), 1 + 1)  # ceil(100 / 108) + spare

    def test_rod_yield_parks_turbines_and_releases_all_on(self):
        commit = turbine_commit.TurbineCommitment(self.power)
        grid = self.grid(stored=1000.0)
        commit.step(grid, "grid_a")
        self.assertTrue(commit.all_on.active)
        commit.step(grid, "grid_a", rod_yield=True)
        self.assertFalse(commit.all_on.active)
        self.assertFalse(any(self.power.is_powered(t) for t in self.ids))

    def test_turbines_do_not_yield_to_last_resort_oil(self):
        commit = turbine_commit.TurbineCommitment(self.power)
        # Six turbines at 108 W plus 500 W of oil: trickle oil covers most of 600 W, last-resort oil none.
        grid = self.grid(consumed=600.0, generated=648.0 + 500.0)
        commit.step(grid, "grid_a")
        trickle = sum(self.power.is_powered(t) for t in self.ids)
        commit.step(grid, "grid_a", resort_w=500.0)
        resort = sum(self.power.is_powered(t) for t in self.ids)
        self.assertLess(trickle, resort)

    def test_no_steam_surplus_on_a_reactor_grid(self):
        commit = turbine_commit.TurbineCommitment(self.power)
        commit.step(self.grid(), "grid_a", 0.99, reactor=True)
        self.assertFalse(commit.surplus.active)
        commit.step(self.grid(), "grid_a", 0.99)
        self.assertTrue(commit.surplus.active)


class _Generator:
    id = "oil_generator_1"


class OilRodTests(StubTestCase):
    def controller(self):
        return oil_generator.OilGeneratorController(_Generator())

    def test_last_resort_waits_during_rod_yield(self):
        controller = self.controller()
        self.assertEqual(controller.last_resort_throttle(0.05, 0.25, 500.0, 500.0, 1, rod_yield=True), 0.0)
        self.assertFalse(controller.burning)

    def test_last_resort_flips_publish_the_resort_key(self):
        controller = self.controller()
        self.assertGreater(controller.last_resort_throttle(0.05, 0.05, 500.0, 500.0, 1), 0.0)
        self.assertIn("oil_generator_1", archive.get(power.OIL_RESORT_KEY, {}))
        controller.last_resort_throttle(0.9, 0.9, 0.0, 0.0, 1)
        self.assertNotIn("oil_generator_1", archive.get(power.OIL_RESORT_KEY, {}))


if __name__ == "__main__":
    unittest.main()
