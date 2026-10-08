"""Power Guard (lib/power.py, lib/power_solar.py): shed thresholds, grid power
phases, the solar night guard, and the Reactor phase's oil surplus cut-off."""
import unittest

import harness
from game_stubs import Building
import power
import oil_generator
import script_parking


class _Reactor(Building):
    """A Reactor building whose grid output the test sets."""

    output = 0.0

    def power_output(self):
        return self.output


class ShedThresholdTests(unittest.TestCase):
    def test_default_tiers_shed_progressively(self):
        tiers = len(power.DEFAULT_SHEDDING_TIERS)
        self.assertEqual(tiers, 3)
        self.assertEqual(power.tiers_to_shed(0.20, tiers), 0)
        self.assertEqual(power.tiers_to_shed(0.08, tiers), 1)
        self.assertEqual(power.tiers_to_shed(0.04, tiers), 2)
        self.assertEqual(power.tiers_to_shed(0.01, tiers), 3)

    def test_habitats_shed_last_and_hard(self):
        self.assertEqual(power.DEFAULT_SHEDDING_TIERS[-1], ["habitat_*"])
        self.assertNotIn("habitat_*", power.SOFT_SHED_PATTERNS)
        self.assertIn("feed_maker_*", power.SOFT_SHED_PATTERNS)
        self.assertIn("feed_maker_*", power.DEFAULT_SHEDDING_TIERS[1])
        self.assertIn("refiner_*", power.SOFT_SHED_PATTERNS)
        self.assertIn("refiner_*", power.DEFAULT_SHEDDING_TIERS[1])

    def test_fuel_assemblers_shed_first_and_hard(self):
        self.assertIn("fuel_assembler_*", power.DEFAULT_SHEDDING_TIERS[0])
        self.assertNotIn("fuel_assembler_*", power.SOFT_SHED_PATTERNS)

    def test_override_with_more_tiers_uses_last_threshold(self):
        self.assertEqual(power.tiers_to_shed(0.01, 5), 5)
        self.assertEqual(power.tiers_to_shed(0.03, 5), 2)


class _GridWorld(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        home = self.world.home
        self.world.add_battery("battery_1", home, charge=300.0, capacity=1000.0)
        self.world.add_building("solar_generator_1", home, "solar_generator")
        self.world.add_building("heater_1", home, "temp_heater")
        self.ids = ["battery_1", "solar_generator_1", "heater_1"]

    def grid(self, consumed=200.0, generated=0.0):
        return self.world.add_grid("battery_1", self.ids, consumed=consumed, generated=generated)

    def add_reactor(self, output):
        reactor = self.world.add_building("reactor_1", self.world.home, "reactor", cls=_Reactor)
        reactor.output = output
        self.ids.append("reactor_1")
        return reactor

    def heater_on(self):
        return self.world.power_control.is_powered("heater_1")


class GridPhaseTests(_GridWorld):
    def test_phase_follows_generator_mix(self):
        self.assertEqual(power.grid_phase(self.grid()), power.PHASE_SOLAR)
        self.world.add_turbine("steam_turbine_1", self.world.home)
        self.ids.append("steam_turbine_1")
        self.assertEqual(power.grid_phase(self.grid()), power.PHASE_STEAM)
        self.world.add_building("oil_generator_1", self.world.home, "oil_generator")
        self.ids.append("oil_generator_1")
        self.assertEqual(power.grid_phase(self.grid()), power.PHASE_OIL)
        self.add_reactor(4000.0)
        self.assertEqual(power.grid_phase(self.grid()), power.PHASE_REACTOR)
        self.assertTrue(power.reactor_carried(self.grid()))

    def test_idle_reactor_leaves_the_grid_to_oil(self):
        self.world.add_building("oil_generator_1", self.world.home, "oil_generator")
        self.ids.append("oil_generator_1")
        self.add_reactor(0.0)
        self.assertEqual(power.grid_phase(self.grid()), power.PHASE_OIL)
        self.assertFalse(power.reactor_carried(self.grid()))


class SolarNightGuardTests(_GridWorld):
    def test_sheds_at_night_and_restores_on_solar_surplus(self):
        clock = self.world.clock
        clock.elevation = 30.0
        manager = power.PowerGridManager(self.grid(), clock=clock)
        manager.supervise_grid(self.grid(), clock.elevation)
        self.assertEqual(manager.phase, power.PHASE_SOLAR)
        self.assertTrue(self.heater_on())

        clock.elevation, clock.hours = 0.0, 20.0
        manager.supervise_grid(self.grid(consumed=200.0), clock.elevation)
        self.assertFalse(self.heater_on(), self.debug_log())
        self.assertIn("heater_1", manager.shedded_machines)

        clock.elevation, clock.hours = 20.0, 30.0
        manager.supervise_grid(self.grid(consumed=50.0, generated=400.0), clock.elevation)
        self.assertTrue(self.heater_on(), self.debug_log())
        self.assertNotIn("heater_1", manager.shedded_machines)

    def test_night_restore_counts_the_shed_draw(self):
        # 150 W heater on a 300/1000 Wh battery: shed at sunset. The live draw then
        # falls to 20 W, which the battery would carry, but not with the heater back.
        self.world.components["heater_1"].power_draw = 150.0
        clock = self.world.clock
        clock.elevation = 30.0
        manager = power.PowerGridManager(self.grid(), clock=clock)
        manager.supervise_grid(self.grid(), clock.elevation)
        clock.elevation, clock.hours = 0.0, 20.0
        manager.supervise_grid(self.grid(consumed=170.0), clock.elevation)
        self.assertFalse(self.heater_on(), self.debug_log())
        clock.hours = 20.5
        manager.supervise_grid(self.grid(consumed=20.0), clock.elevation)
        self.assertFalse(self.heater_on(), self.debug_log())
        self.world.components["battery_1"].charge = 1000.0
        clock.hours = 28.0
        manager.supervise_grid(self.grid(consumed=20.0), clock.elevation)
        self.assertTrue(self.heater_on(), self.debug_log())

    def test_day_restore_waits_until_solar_or_battery_carries_the_shed_draw(self):
        self.world.components["heater_1"].power_draw = 150.0
        clock = self.world.clock
        clock.elevation = 30.0
        manager = power.PowerGridManager(self.grid(), clock=clock)
        manager.supervise_grid(self.grid(), clock.elevation)
        clock.elevation, clock.hours = 0.0, 20.0
        manager.supervise_grid(self.grid(consumed=170.0), clock.elevation)
        self.assertFalse(self.heater_on(), self.debug_log())
        # Dawn: 60 W of sun beats the 20 W live draw, not the 170 W with the heater;
        # 300 Wh can't bridge ~120 W to the morning peak (~3 h).
        clock.elevation, clock.hours = 5.0, 30.5
        manager.supervise_grid(self.grid(consumed=20.0, generated=60.0), clock.elevation)
        self.assertFalse(self.heater_on(), self.debug_log())
        clock.hours = 32.5
        manager.supervise_grid(self.grid(consumed=20.0, generated=200.0), clock.elevation)
        self.assertTrue(self.heater_on(), self.debug_log())

    def test_day_restore_on_a_battery_that_bridges_to_the_peak(self):
        self.world.components["heater_1"].power_draw = 150.0
        clock = self.world.clock
        clock.elevation = 30.0
        manager = power.PowerGridManager(self.grid(), clock=clock)
        manager.supervise_grid(self.grid(), clock.elevation)
        clock.elevation, clock.hours = 0.0, 20.0
        manager.supervise_grid(self.grid(consumed=170.0), clock.elevation)
        self.assertFalse(self.heater_on(), self.debug_log())
        self.world.components["battery_1"].charge = 1000.0
        clock.elevation, clock.hours = 5.0, 30.5
        manager.supervise_grid(self.grid(consumed=20.0, generated=60.0), clock.elevation)
        self.assertTrue(self.heater_on(), self.debug_log())

    def test_steam_grid_ignores_the_night(self):
        self.world.add_turbine("steam_turbine_1", self.world.home)
        self.ids.append("steam_turbine_1")
        clock = self.world.clock
        clock.elevation = 30.0
        manager = power.PowerGridManager(self.grid(), clock=clock)
        manager.supervise_grid(self.grid(), clock.elevation)
        clock.elevation, clock.hours = 0.0, 20.0
        manager.supervise_grid(self.grid(consumed=200.0), clock.elevation)
        self.assertEqual(manager.phase, power.PHASE_STEAM)
        self.assertIsNone(manager.solar_guard)
        self.assertTrue(self.heater_on())  # 30% combined reserve is above every shed line


class ReactorOilTests(_GridWorld):
    def setUp(self):
        super().setUp()
        self.world.add_building("oil_generator_1", self.world.home, "oil_generator")
        self.ids.append("oil_generator_1")

    def test_oil_surplus_base_load_stops_on_a_reactor_grid(self):
        self.add_reactor(4000.0)
        self.grid(consumed=1000.0, generated=4000.0)
        controller = oil_generator.OilGeneratorController(self.world.components["oil_generator_1"])
        controller.surplus = True
        self.assertEqual(controller.choose_throttle(), 0.0, self.debug_log())
        self.assertFalse(controller.surplus)

    def test_parking_skips_oil_surplus_wake_on_reactor_grids(self):
        self.add_reactor(4000.0)
        grid = self.grid()
        self.assertEqual(script_parking.ScriptParking._reactor_grids([grid]), {"battery_1"})
        members = {"oil_generator_1": ("battery_1", "oil_generator", False)}
        parking = script_parking.ScriptParking.__new__(script_parking.ScriptParking)
        entry = {"kind": "oil_generator", "since": self.world.clock.now}
        reason = parking._wake_reason("oil_generator_1", entry, self.world.clock.now, members, set(), {}, True, None, {"battery_1"})
        self.assertIsNone(reason)
        reason = parking._wake_reason("oil_generator_1", entry, self.world.clock.now, members, set(), {}, True, None, set())
        self.assertEqual(reason, "oil surplus")


if __name__ == "__main__":
    unittest.main()
