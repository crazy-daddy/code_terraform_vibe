"""Stub tests for the nearest-station arbitration shared by the Vehicle Charging
Station and Drone Service Station controllers (lib/station_controller.py)."""
import unittest

from harness import StubTestCase
import charging
import drone_service


class Pos:
    def __init__(self, x, y):
        self.x = x
        self.y = y


def ref(station_id, x, y):
    return {"id": station_id, "coords": (x, y)}


class AssessStationsTests(StubTestCase):
    def setUp(self):
        super().setUp()
        outpost = self.world.add_outpost("outpost_2")
        self.stations = [
            charging.ChargingStationController(self.world.add_building("cs_1", outpost, "charging_station")),
            drone_service.DroneServiceController(self.world.add_building("ds_1", outpost, "drone_service_station")),
        ]

    def test_nearest_station_owns_unit(self):
        for controller in self.stations:
            me = controller.name
            mine, distance, coords = controller.assess_stations(Pos(1, 0), [ref(me, 0, 0), ref("other", 10, 0)], True)
            self.assertEqual((mine, distance, coords), (True, 1.0, (0, 0)))
            mine, _, coords = controller.assess_stations(Pos(9, 0), [ref(me, 0, 0), ref("other", 10, 0)], True)
            self.assertEqual((mine, coords), (False, (10, 0)))

    def test_tie_unknown_position_and_absent_station(self):
        for controller in self.stations:
            me = controller.name
            self.assertTrue(controller.assess_stations(Pos(5, 0), [ref(me, 0, 0), ref("other", 10, 0)], True)[0])
            self.assertTrue(controller.assess_stations(Pos(5, 0), [ref("other", 10, 0)], False)[0])
            self.assertFalse(controller.assess_stations(Pos(5, 0), [ref("other", 10, 0)], True)[0])
            self.assertEqual(controller.assess_stations(Pos(5, 0), [], False), (True, None, None))


if __name__ == "__main__":
    unittest.main()
