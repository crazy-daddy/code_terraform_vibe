import unittest

from harness import StubTestCase
import script_census
from script_census import allowance, census_if_due, count_running, machine_refs, snapshot, CENSUS_TICK_INTERVAL
from machine_activity import record


class ScriptCensusTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        for machine_id, type_id in {"smelter_1": "smelter", "fabricator_1": "fabricator", "solar_1": "solar_generator"}.items():
            w.add_building(machine_id, w.home, type_id)
        w.run_control.running.update({"smelter_1", "solar_1"})
        script_census.last_census_tick = None
        script_census.highest_found.update({"panel": 0, "automation": 0})

    def test_counts_running_machine_scripts(self):
        self.assertEqual(count_running(), (2, 4))

    def test_allowance_matches_game_split(self):
        self.assertEqual(allowance(20), 1000)
        self.assertEqual(allowance(165), 303)
        self.assertEqual(allowance(0), 1000)

    def test_logs_once_per_interval(self):
        census_if_due(1000)
        census_if_due(1000 + CENSUS_TICK_INTERVAL - 1)
        census_if_due(1000 + CENSUS_TICK_INTERVAL)
        lines = [line for line in self.debug_log().splitlines() if "scripts running: " in line]
        self.assertEqual(len(lines), 2)
        self.assertIn("scripts running: 2 of 4 machines (incl. 0 panel/automation scripts", lines[0])

    def test_counts_poi_extractors_and_harvester(self):
        w = self.world
        for machine_id, type_id in {"thermal_cap_1": "thermal_cap", "water_pump_1": "water_pump", "oil_pump_1": "oil_pump", "exotic_gas_cap_1": "exotic_gas_cap", "exotic_spring_tap_1": "exotic_spring_tap"}.items():
            w.add_building(machine_id, None, type_id)
        w.add_grid("grid_1", ["thermal_cap_1", "water_pump_1", "oil_pump_1", "exotic_gas_cap_1", "exotic_spring_tap_1", "smelter_1"])
        w.run_control.running.update({"thermal_cap_1", "exotic_spring_tap_1", "harvester_1"})
        ids = {row[0] for row in machine_refs()}
        self.assertTrue({"thermal_cap_1", "water_pump_1", "oil_pump_1", "exotic_gas_cap_1", "exotic_spring_tap_1", "harvester_1"} <= ids)
        self.assertEqual(count_running(), (5, 9))

    def test_panels_and_automations_count_but_are_not_machines(self):
        self.world.run_control.running.update({"panel_1", "panel_20", "automation_2"})
        result = snapshot()
        assert result is not None
        rows, running, ui = result
        self.assertEqual(ui, {"panel_1", "panel_20", "automation_2"})
        self.assertEqual(running, {"smelter_1", "solar_1"})
        self.assertFalse({"panel_1", "automation_2"} & {row[0] for row in rows})
        self.assertEqual(count_running(), (5, 4))
        census_if_due(1000)
        self.assertIn("scripts running: 5 of 4 machines (incl. 3 panel/automation scripts", self.debug_log())

    def test_probe_range_follows_highest_panel_found(self):
        self.world.run_control.running.add("panel_40")
        snapshot()
        self.assertEqual(script_census.highest_found["panel"], 40)
        self.assertIn("panel_80", script_census.ui_script_ids())
        self.assertNotIn("panel_81", script_census.ui_script_ids())

    def test_machine_activity_ignores_panels_and_tracks_extractors(self):
        w = self.world
        w.add_building("oil_pump_1", None, "oil_pump")
        w.add_grid("grid_1", ["oil_pump_1"])
        w.run_control.running.update({"oil_pump_1", "panel_1"})
        state = record(snapshot(), 1000)
        self.assertEqual(state["machines"]["oil_pump_1"]["g"], "oil_pump")
        self.assertNotIn("panel_1", state["machines"])
        self.assertNotIn("panel", state["groups"])


if __name__ == "__main__":
    unittest.main()
