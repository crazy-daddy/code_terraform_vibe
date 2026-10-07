"""Stub tests for the early build order (lib/early_buyer.py) and the Rover's
own loadout fitting (lib/rover.py fit_rover_loadout())."""
import unittest

from harness import StubTestCase
from game_stubs import Commander, Shop
import early_buyer
import fleet_commission
import rover

PRICES = {
    "oxygen_generator": 100, "temp_heater": 100, "pressure_generator": 100,
    "battery": 10, "solar_generator": 10, "charging_station": 10, "rover": 10,
    "nav_module": 1, "sonar_module": 1, "drill_module": 1,
    "pioneer": 10, "battery_holder_small": 1, "portable_battery": 1, "portable_bin": 1,
}
VEHICLE_RESEARCH = ("research_rover", "research_deep_extraction", "research_charging_station")


class EarlyBuyerTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        w.services.update({"shop": Shop(w, PRICES), "commander": Commander(100000)})
        self.pillars = {"o2": 0.0, "pressure": 0.0, "heat": 0.0, "tp": 70000.0}
        self.buyer = early_buyer.EarlyBuyer()
        self.buyer.pillars = lambda: dict(self.pillars)

    def step(self):
        self.world.clock.now += early_buyer.EVAL_TICKS
        return self.buyer.step(self.world.clock.now)

    def count(self, type_id):
        return len(self.world.home.buildings(type_id))

    def test_fills_free_slots_with_active_pillar(self):
        self.pillars.update(o2=2.5, heat=5.0)  # stage 1: heaters
        self.step()
        self.assertEqual(self.count("battery"), 3)
        self.assertEqual(self.count("solar_generator"), 6)
        self.assertEqual(self.count("temp_heater"), 25 - 9)

    def test_next_stage_sells_other_pillars(self):
        self.pillars.update(o2=2.5, heat=5.0)
        self.step()
        self.pillars.update(heat=12.0)  # stage 2: oxygen
        self.step()
        self.assertEqual(self.count("temp_heater"), 0)
        self.assertEqual(self.count("oxygen_generator"), 25 - 9)

    def test_station_and_rovers_once_unlocked(self):
        self.pillars.update(o2=10.0, heat=12.0, pressure=0.2)
        self.step()
        self.assertEqual(self.count("charging_station"), 0)
        self.assertEqual(len(early_buyer.vehicles("rover")), 0)
        self.world.research.unlocked.update(VEHICLE_RESEARCH)
        self.step()
        self.assertEqual(self.count("charging_station"), 1)
        self.assertEqual(self.count("pressure_generator"), 25 - 10)
        self.assertEqual(len(early_buyer.vehicles("rover")), early_buyer.ROVERS)
        for item_id in early_buyer.ROVER_GEAR:
            self.assertEqual(self.world.inventory.count(item_id), early_buyer.ROVERS)

    def test_queues_one_scout_pioneer_at_pioneer_tp(self):
        self.world.research.unlocked.update(VEHICLE_RESEARCH)
        self.pillars.update(o2=10.0, heat=12.0, pressure=0.2)
        self.step()
        self.assertEqual(fleet_commission.commission_state().get("jobs") or [], [])
        self.pillars["tp"] = early_buyer.PIONEER_TP
        self.step()
        self.step()
        jobs = fleet_commission.commission_state().get("jobs") or []
        self.assertEqual([(j["kind"], j["role"]) for j in jobs], [("pioneer", "scout")])

    def test_scout_waits_while_preset_locked(self):
        self.world.research.unlocked.update(VEHICLE_RESEARCH)
        self.world.services["shop"].prices.pop("battery_holder_small")
        self.pillars.update(o2=10.0, heat=12.0, pressure=0.2, tp=early_buyer.PIONEER_TP)
        self.step()
        self.assertEqual(fleet_commission.commission_state().get("jobs") or [], [])

    def test_vehicles_only_leaves_buildings_alone(self):
        self.world.notebook.set(early_buyer.STATE_KEY, {"generators": False, "rovers": 1, "pioneer": False})
        self.world.research.unlocked.update(VEHICLE_RESEARCH)
        self.world.add_building("charging_station_1", self.world.home, "charging_station")
        self.pillars.update(o2=10.0, heat=12.0, pressure=0.2, tp=early_buyer.PIONEER_TP)
        self.step()
        self.assertEqual(self.count("pressure_generator"), 0)
        self.assertEqual(len(early_buyer.vehicles("rover")), 1)
        self.assertEqual(fleet_commission.commission_state().get("jobs") or [], [])

    def test_idle_for_good_after_control_room(self):
        self.world.research.unlocked.add(early_buyer.DONE_RESEARCH)
        self.assertEqual(self.step(), "early buyer done")
        self.world.research.unlocked.clear()
        self.pillars.update(o2=2.5, heat=5.0)
        self.assertEqual(self.step(), "early buyer done")
        self.assertEqual(self.count("temp_heater"), 0)


class RoverFittingTests(StubTestCase):
    def controller(self, unit):
        controller = rover.RoverController.__new__(rover.RoverController)
        controller.vehicle = unit
        controller.name = unit.id
        controller.log = early_buyer.log
        controller.publish_telemetry = lambda *args, **kwargs: None
        return controller

    def test_mounts_missing_kinds_from_inventory(self):
        unit = self.world.add_rover("rover_1")
        unit.slots[0].module_id = "drill_module_industrial"
        for item_id in rover.ROVER_LOADOUT:
            self.world.inventory.add(item_id, 1)
        self.controller(unit).fit_rover_loadout()
        self.assertEqual(sorted(s.module_id for s in unit.slots), ["drill_module_industrial", "nav_module", "sonar_module"])
        self.assertEqual(self.world.inventory.count("drill_module"), 1)


if __name__ == "__main__":
    unittest.main()
