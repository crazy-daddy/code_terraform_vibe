"""Power Guard (lib/power.py, lib/power_solar.py): shed thresholds, grid power
phases, the solar night guard, and the Reactor phase's oil surplus cut-off."""

import unittest

import harness
import lead_cask
import oil_generator
import parking_client
import power
import script_parking
from game_stubs import Building


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


class OilWakeTests(_GridWorld):
    """A grid whose reserve drops below OIL_WAKE_RESERVE_FRACTION wakes its parked Oil Generators once."""

    def setUp(self):
        super().setUp()
        self.world.add_building("oil_generator_1", self.world.home, "oil_generator")
        self.ids.append("oil_generator_1")
        self.park()

    def park(self):
        self.world.power_control.set_powered("oil_generator_1", False)
        self.world.notebook.data[parking_client.PARKED_KEY] = {
            "oil_generator_1": {"kind": "oil_generator", "mode": "breaker", "since": 0}
        }
        self.world.power_control.calls.clear()

    def reserve(self, stored, capacity=1000.0):
        return self.world.add_grid("battery_1", self.ids, consumed=200.0, stored=stored, capacity=capacity)

    def test_drop_below_the_fraction_wakes_once(self):
        manager = power.PowerGridManager(self.reserve(800.0), clock=self.world.clock)
        manager.supervise_grid(self.reserve(800.0))
        self.assertFalse(manager.reserve_low)
        self.assertNotIn(("oil_generator_1", True), self.world.power_control.calls)
        manager.supervise_grid(self.reserve(300.0))
        self.assertTrue(manager.reserve_low)
        self.assertIn(("oil_generator_1", True), self.world.power_control.calls)
        self.assertNotIn("oil_generator_1", self.world.notebook.data[parking_client.PARKED_KEY])
        self.park()
        manager.supervise_grid(self.reserve(300.0))  # still low: no second wake, the full pass is the backstop
        self.assertNotIn(("oil_generator_1", True), self.world.power_control.calls)

    def test_a_recovered_reserve_arms_the_next_wake(self):
        manager = power.PowerGridManager(self.reserve(300.0), clock=self.world.clock)
        manager.supervise_grid(self.reserve(300.0))
        manager.supervise_grid(self.reserve(800.0))
        self.assertFalse(manager.reserve_low)
        self.park()
        manager.supervise_grid(self.reserve(300.0))
        self.assertIn(("oil_generator_1", True), self.world.power_control.calls)

    def test_wake_runs_before_the_no_storage_return(self):
        # no battery and no steam: nothing to measure counts as low, and the early return comes after the wake
        manager = power.PowerGridManager(self.reserve(0.0, capacity=0.0), clock=self.world.clock)
        manager.supervise_grid(self.reserve(0.0, capacity=0.0))
        self.assertTrue(manager.reserve_low)
        self.assertIn(("oil_generator_1", True), self.world.power_control.calls)

    def test_other_grids_generators_stay_parked(self):
        self.world.add_building("oil_generator_2", self.world.home, "oil_generator")
        self.world.power_control.set_powered("oil_generator_2", False)
        self.world.notebook.data[parking_client.PARKED_KEY]["oil_generator_2"] = {
            "kind": "oil_generator",
            "mode": "breaker",
            "since": 0,
        }
        self.world.power_control.calls.clear()
        manager = power.PowerGridManager(self.reserve(300.0), clock=self.world.clock)
        manager.supervise_grid(self.reserve(300.0))
        self.assertIn(("oil_generator_1", True), self.world.power_control.calls)
        self.assertNotIn(("oil_generator_2", True), self.world.power_control.calls)


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
        reason = parking._wake_reason(
            "oil_generator_1", entry, self.world.clock.now, members, set(), {}, True, None, {"battery_1"}
        )
        self.assertIsNone(reason)
        reason = parking._wake_reason(
            "oil_generator_1", entry, self.world.clock.now, members, set(), {}, True, None, set()
        )
        self.assertEqual(reason, "oil surplus")


class RodEmergencyTests(_GridWorld):
    """A Reactor out of Fuel Rods: tiers shed by reserve as usual, the Fuel Assemblers never."""

    def setUp(self):
        super().setUp()
        self.world.add_building("oil_generator_1", self.world.home, "oil_generator")
        self.world.add_building("fuel_assembler_1", self.world.home, "fuel_assembler")
        self.ids += ["oil_generator_1", "fuel_assembler_1"]
        self.add_reactor(0.0)

    def dry(self, level="error", hours=0.0):
        entry = {"outpost": self.world.home.id, "level": level, "hours": hours, "tick": self.world.clock.now}
        self.world.notebook.data["reactor.fuel"] = {"reactor_1": entry}

    def low_grid(self):
        return self.world.add_grid("battery_1", self.ids, consumed=200.0, stored=30.0, capacity=1000.0)

    def test_low_reserve_sheds_tier_but_not_the_assembler(self):
        self.dry()
        manager = power.PowerGridManager(self.grid(), clock=self.world.clock)
        manager.supervise_grid(self.low_grid())
        self.assertEqual(manager.phase, power.PHASE_OIL)
        self.assertFalse(self.heater_on(), self.debug_log())
        self.assertTrue(self.world.power_control.is_powered("fuel_assembler_1"))
        self.assertNotIn("fuel_assembler_1", manager.shedded_machines)

    def test_reserve_ok_sheds_nothing(self):
        self.dry()
        manager = power.PowerGridManager(self.grid(), clock=self.world.clock)
        manager.supervise_grid(self.grid())
        self.assertTrue(self.heater_on(), self.debug_log())

    def test_assembler_shed_without_emergency(self):
        manager = power.PowerGridManager(self.grid(), clock=self.world.clock)
        manager.supervise_grid(self.low_grid())
        self.assertFalse(self.world.power_control.is_powered("fuel_assembler_1"), self.debug_log())

    def test_powers_a_shed_assembler_back_on(self):
        manager = power.PowerGridManager(self.grid(), clock=self.world.clock)
        self.world.power_control.set_powered("fuel_assembler_1", False)
        manager.shedded_machines.add("fuel_assembler_1")
        self.dry(level="warn", hours=lead_cask.ROD_EMERGENCY_HOURS)
        manager.supervise_grid(self.grid())
        self.assertTrue(self.world.power_control.is_powered("fuel_assembler_1"), self.debug_log())
        self.assertNotIn("fuel_assembler_1", manager.shedded_machines)

    def test_warn_with_fuel_left_is_no_emergency(self):
        manager = power.PowerGridManager(self.grid(), clock=self.world.clock)
        self.dry(level="warn", hours=lead_cask.ROD_EMERGENCY_HOURS + 1)
        manager.supervise_grid(self.low_grid())
        self.assertFalse(self.world.power_control.is_powered("fuel_assembler_1"), self.debug_log())


if __name__ == "__main__":
    unittest.main()
