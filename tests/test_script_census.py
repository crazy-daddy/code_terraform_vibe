import unittest

from harness import StubTestCase
import script_census
from script_census import allowance, census_if_due, count_running, CENSUS_TICK_INTERVAL


class ScriptCensusTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        for machine_id, type_id in {"smelter_1": "smelter", "fabricator_1": "fabricator", "solar_1": "solar_generator"}.items():
            w.add_building(machine_id, w.home, type_id)
        w.run_control.running.update({"smelter_1", "solar_1"})
        script_census.last_census_tick = None

    def test_counts_running_machine_scripts(self):
        self.assertEqual(count_running(), (2, 3))

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
        self.assertIn("scripts running: 2 of 3 machines, allowance 1000 steps/tick", lines[0])


if __name__ == "__main__":
    unittest.main()
