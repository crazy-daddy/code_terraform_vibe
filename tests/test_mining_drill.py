import unittest

from harness import StubTestCase
import mining_drill


class _Stack:
    id = "iron_ore"
    count = 400


class _Port:
    def count(self):
        return 400

    def capacity(self):
        return 500

    def stacks(self):
        return [_Stack()]


class _Drill:
    id = "mining_drill_heavy_1"
    name = "Drill 1"
    output = _Port()

    def drill_rate(self):
        return 200.0


class _Member:
    id = "mining_drill_heavy_1"
    type_id = "mining_drill_heavy"


class _Grid:
    members = [_Member()]


class _PowerControl:
    def grids(self):
        return [_Grid()]


class PublishAllDrillsTests(StubTestCase):
    def setUp(self):
        super().setUp()
        mining_drill._CONTROLLERS.clear()
        self.world.components["power_control"] = _PowerControl()
        self.world.components["mining_drill_heavy_1"] = _Drill()

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
