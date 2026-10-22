"""DroneNavigationMixin._fly_to_named(): the shared fly_to_station() / fly_to_drill() rule."""

import unittest

from drone import DroneController
from harness import StubTestCase
from parking_client import HOLDS_KEY
from tree_console import TreeConsole


class FlyToNamedTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.stub = self.world.add_drone("drone_1", self.world.home)
        self.d = DroneController.__new__(DroneController)
        self.d.drone, self.d.name, self.d.cruise_throttle = self.stub, "drone_1", 1.0
        self.d.log = TreeConsole(module="test")

    def test_already_docked_skips_route(self):
        self.stub.station = "depot_1"
        self.assertTrue(self.d.fly_to_station("depot_1", timeout_ticks=50))
        self.assertEqual(self.stub.routes, [])

    def test_station_routes_and_arrives(self):
        self.assertTrue(self.d.fly_to_station("depot_1", timeout_ticks=50))
        self.assertEqual(self.stub.routes, [("station", "depot_1")])

    def test_drill_routes_and_arrives(self):
        self.assertTrue(self.d.fly_to_drill("drill_1", timeout_ticks=50))
        self.assertEqual(self.stub.routes, [("drill", "drill_1")])
        self.assertEqual(self.d.current_drill(), "drill_1")

    def test_drill_route_wakes_nothing_station_route_holds(self):
        self.assertTrue(self.d.fly_to_drill("drill_1", timeout_ticks=50))
        self.assertNotIn("drill_1", self.world.notebook.data.get(HOLDS_KEY, {}))
        self.assertEqual(self.world.power_control.calls, [])
        self.assertTrue(self.d.fly_to_station("depot_1", timeout_ticks=50))
        self.assertIn("depot_1", self.world.notebook.data.get(HOLDS_KEY, {}))

    def test_refused_route_fails_both_kinds(self):
        self.stub.route_status = "station_not_found"
        self.assertFalse(self.d.fly_to_station("depot_1", timeout_ticks=50))
        self.stub.route_status = "drill_not_found"
        self.assertFalse(self.d.fly_to_drill("drill_1", timeout_ticks=50))
        self.assertEqual(self.stub.routes, [("station", "depot_1"), ("drill", "drill_1")])


if __name__ == "__main__":
    unittest.main()
