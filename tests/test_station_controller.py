"""Stub tests for the nearest-station arbitration shared by the Vehicle Charging
Station and Drone Service Station controllers (lib/station_controller.py)."""

import unittest

import charging
import drone_depots
import drone_service
from game_stubs import Building, FluidPort, RescueStation, Tank
from harness import StubTestCase


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


class ServiceStation(Building):
    def __init__(self, world, building_id, outpost):
        super().__init__(world, building_id, outpost)
        self.oil_in = FluidPort(world)


class DroneServiceOilFeedTests(StubTestCase):
    def setUp(self):
        super().setUp()
        outpost = self.world.add_outpost("outpost_6")
        self.world._place(Tank(self.world, "liquid_tank_1", outpost, "liquid_tank", "oil", 100.0, 100))
        station = self.world.add_building("ds_1", outpost, "drone_service_station", ServiceStation)
        self.port = station.oil_in
        self.controller = drone_service.DroneServiceController(station)

    def test_no_oil_link_before_heli_research(self):
        self.assertIsNone(self.controller.ensure_oil_feed())
        self.assertEqual(self.port.connect_log, [])

    def test_connects_oil_tank_once_researched(self):
        self.world.research.unlocked.add(drone_depots.HELI_RESEARCH_ID)
        event = self.controller.ensure_oil_feed()
        self.assertEqual(getattr(event, "kind", None), "connected")
        self.assertEqual(self.port.connected_id(), "liquid_tank_1")


class FleetRescueTests(StubTestCase):
    """manage_fleet_rescues(): the nearest station dispatches; docked, rescued and thrusterless units are skipped."""

    def setUp(self):
        super().setUp()
        self.outpost = self.world.add_outpost("outpost_3")

    def controller(self, cls, type_id):
        station = self.world.add_building("st_1", self.outpost, type_id, RescueStation)
        controller = cls(station)
        controller.all_station_refs = lambda: [ref("st_1", 0, 0), ref("other", 100, 0)]
        return controller, station

    def charger(self):
        return self.controller(charging.ChargingStationController, "charging_station")

    def service(self):
        return self.controller(drone_service.DroneServiceController, "drone_service_station")

    def test_stranded_vehicle_nearest_here_gets_rescue(self):
        controller, station = self.charger()
        self.world.add_pioneer("p_far", status="stranded", x=95.0)
        self.world.add_pioneer("p_1", status="stranded", x=5.0)
        self.assertTrue(controller.manage_fleet_rescues())
        self.assertEqual([unit for unit, _ in station.rescue_log], ["p_1"])
        self.assertTrue(0 < station.rescue_log[0][1] <= 1)

    def test_docked_or_rescued_vehicle_skipped(self):
        controller, station = self.charger()
        self.world.add_pioneer("p_docked", station="st_1", status="stranded", x=5.0)
        self.world.add_pioneer("p_rescued", status="stranded", x=5.0).rescue = "outbound"
        self.assertFalse(controller.manage_fleet_rescues())
        self.assertEqual(station.rescue_log, [])

    def test_stalled_electric_drone_gets_rescue_thrusterless_skipped(self):
        controller, station = self.service()
        self.world.add_drone("d_bare", self.outpost, engine="", status="stalled_no_battery", x=5.0)
        self.world.add_drone("d_1", self.outpost, status="stalled_no_battery", x=5.0)
        self.assertTrue(controller.manage_fleet_rescues())
        self.assertEqual([unit for unit, _ in station.rescue_log], ["d_1"])

    def test_rescue_under_way_stays_busy_without_dispatch(self):
        self.world.add_pioneer("p_1", status="stranded", x=5.0)
        self.world.add_drone("d_1", self.outpost, status="stalled_no_battery", x=5.0)
        for controller, station in (self.charger(), self.service()):
            station.rescue_target = "x_1"
            self.assertTrue(controller.manage_fleet_rescues())
            self.assertEqual(station.rescue_log, [])
