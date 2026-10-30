"""Power Guard (lib/power.py) at its exact reserve thresholds.

A steam-phase home grid with one load per default shed tier: heater_1 (tier 1,
hard), smelter_1 (tier 2, soft: flagged in the archive, power stays on) and
habitat_1 (tier 3, hard). Bugs caught: an off-by-one at a shed or restore
fraction (a tier sheds early, late, or flaps), and a failed set_powered()
recorded as done, so the load is never shed or never powered back.
"""

import unittest

import harness
import parking_client
import power
from archive import archive
from game_stubs import PowerControl, Result

CAPACITY_WH = 1000.0
SHED_TIER_1, SHED_TIER_2, SHED_TIER_3 = (f * CAPACITY_WH for f in power.EMERGENCY_SHED_FRACTIONS)
RESTORE_WH = power.EMERGENCY_RESTORE_FRACTION * CAPACITY_WH


class _FlakyPowerControl(PowerControl):
    """power_control whose next `failures` set_powered() calls answer under_construction."""

    failures = 0

    def set_powered(self, machine_id, on):
        if self.failures > 0:
            self.failures -= 1
            self.calls.append((machine_id, on))
            return Result("under_construction")
        return super().set_powered(machine_id, on)


class PowerGuardLimitTests(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        self.power_control = _FlakyPowerControl(self.world)
        self.world.power_control = self.power_control
        self.world.services["power_control"] = self.power_control
        home = self.world.home
        self.world.add_battery("battery_1", home, capacity=CAPACITY_WH)
        self.world.add_turbine("steam_turbine_1", home)
        self.world.add_building("heater_1", home, "temp_heater")
        self.world.add_smelter("smelter_1", home)
        self.world.add_building("habitat_1", home, "habitat")
        self.ids = ["battery_1", "steam_turbine_1", "heater_1", "smelter_1", "habitat_1"]
        self.manager = power.PowerGridManager(self.grid(CAPACITY_WH), clock=self.world.clock)
        # Guard: one shed fraction per default tier, and a steam-phase grid.
        self.assertEqual(len(power.DEFAULT_SHEDDING_TIERS), len(power.EMERGENCY_SHED_FRACTIONS))
        self.assertEqual(power.grid_phase(self.grid(CAPACITY_WH)), power.PHASE_STEAM)

    def grid(self, stored_wh):
        return self.world.add_grid("battery_1", self.ids, consumed=200.0, stored=stored_wh, capacity=CAPACITY_WH)

    def supervise(self, stored_wh):
        self.manager.supervise_grid(self.grid(stored_wh))

    def shed(self):
        """Loads the guard holds shed, as published for the machine scripts."""
        return set(archive.get(parking_client.SHEDDED_KEY, []) or [])

    def powered(self, machine_id):
        return self.power_control.is_powered(machine_id)

    def test_falling_reserve_sheds_tier_by_tier_strictly_below_each_fraction(self):
        steps = [
            (SHED_TIER_1 + 1, set()),
            (SHED_TIER_1, set()),
            (SHED_TIER_1 - 1, {"heater_1"}),
            (SHED_TIER_2 + 1, {"heater_1"}),
            (SHED_TIER_2, {"heater_1"}),
            (SHED_TIER_2 - 1, {"heater_1", "smelter_1"}),
            (SHED_TIER_3 + 1, {"heater_1", "smelter_1"}),
            (SHED_TIER_3, {"heater_1", "smelter_1"}),
            (SHED_TIER_3 - 1, {"heater_1", "smelter_1", "habitat_1"}),
        ]
        for stored_wh, expected in steps:
            self.supervise(stored_wh)
            with self.subTest(stored_wh=stored_wh):
                self.assertEqual(self.shed(), expected)
                self.assertEqual(self.powered("heater_1"), "heater_1" not in expected)
                self.assertEqual(self.powered("habitat_1"), "habitat_1" not in expected)
                self.assertTrue(self.powered("smelter_1"))  # soft shed: flagged only

    def test_rising_reserve_restores_only_at_the_restore_fraction(self):
        self.supervise(SHED_TIER_3 - 1)
        self.assertEqual(self.shed(), {"heater_1", "smelter_1", "habitat_1"})
        self.supervise(RESTORE_WH - 1)
        self.assertEqual(self.shed(), {"heater_1", "smelter_1", "habitat_1"})
        self.assertFalse(self.powered("heater_1"))
        self.supervise(RESTORE_WH)
        self.assertEqual(self.shed(), set())
        self.assertTrue(self.powered("heater_1"))
        self.assertTrue(self.powered("habitat_1"))

    def test_failed_power_off_is_retried_next_cycle(self):
        self.power_control.failures = 1
        self.supervise(SHED_TIER_1 - 1)
        self.assertTrue(self.powered("heater_1"))
        self.assertNotIn("heater_1", self.shed())
        self.supervise(SHED_TIER_1 - 1)
        self.assertFalse(self.powered("heater_1"))
        self.assertIn("heater_1", self.shed())

    def test_failed_power_on_is_retried_next_cycle(self):
        self.supervise(SHED_TIER_1 - 1)
        self.power_control.failures = 1
        self.supervise(RESTORE_WH)
        self.assertFalse(self.powered("heater_1"))
        self.assertIn("heater_1", self.shed())
        self.supervise(RESTORE_WH)
        self.assertTrue(self.powered("heater_1"))
        self.assertNotIn("heater_1", self.shed())


if __name__ == "__main__":
    unittest.main()
