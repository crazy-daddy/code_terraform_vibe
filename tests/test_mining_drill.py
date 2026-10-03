import unittest

from harness import StubTestCase
from game_stubs import Building, Slot
import mining_drill


class _Drill(Building):
    name = "Drill 1"

    def __init__(self, world, drill_id, outpost):
        super().__init__(world, drill_id, outpost)
        self.output = Slot(self, self.output_buffer, 500)

    def drill_rate(self):
        return 200.0


class PublishAllDrillsTests(StubTestCase):
    def setUp(self):
        super().setUp()
        mining_drill._CONTROLLERS.clear()
        drill = self.world.add_building("mining_drill_heavy_1", self.world.home, "mining_drill_heavy", _Drill)
        drill.output_buffer["iron_ore"] = 400
        self.world.add_grid("mining_drill_heavy_1", ["mining_drill_heavy_1"])

    def test_publishes_grid_drills_centrally(self):
        self.assertEqual(mining_drill.publish_all_drills(), 1)
        entry = self.world.notebook.data["drill.status"]["mining_drill_heavy_1"]
        self.assertEqual(entry["type"], "mining_drill_heavy")
        self.assertEqual((entry["count"], entry["state"], entry["near_full"]), (400, "drilling", True))

    def test_near_full_warning_once_across_passes(self):
        mining_drill.publish_all_drills()
        mining_drill.publish_all_drills()
        warnings = [m for level, m in self.world.console.lines if level == "warn" and "Schedule a pickup" in m]
        self.assertEqual(len(warnings), 1, self.debug_log())


if __name__ == "__main__":
    unittest.main()
