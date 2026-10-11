"""Stub tests for lib/drone_kit_stock.py: one Depot / Service Station kit
in stock while an outpost lacks that building."""
import unittest

from harness import StubTestCase, production
from game_stubs import Recipe
import drone_kit_stock
import priority

KIT = [[1, priority.UPGRADE]]

DEPOT_RECIPE = Recipe("craft_drone_station_kit", {}, "drone_station_kit")
SERVICE_RECIPE = Recipe("craft_drone_service_station_kit", {}, "drone_service_station_kit")


class DroneKitStockTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.remote = self.world.add_outpost("outpost_2")

    def publish(self, recipes):
        self.world.add_fabricator("fabricator_1", self.world.home, recipes=recipes)
        drone_kit_stock.publish_drone_kit_order(production.SourceCache())
        return production.get_orders().get(drone_kit_stock.REQUESTER, {})

    def test_orders_one_kit_of_each_unlocked_kind(self):
        self.assertEqual(self.publish([DEPOT_RECIPE, SERVICE_RECIPE]), {"drone_station_kit": KIT, "drone_service_station_kit": KIT})

    def test_locked_kit_is_not_ordered(self):
        self.assertEqual(self.publish([SERVICE_RECIPE]), {"drone_service_station_kit": KIT})

    def test_no_order_once_every_outpost_has_both(self):
        w = self.world
        for outpost in (w.home, self.remote):
            w.add_drone_depot(f"depot_{outpost.id}", outpost, type_id="drone_station_medium")
            w.add_building(f"service_{outpost.id}", outpost, "drone_service_station")
        self.assertEqual(self.publish([DEPOT_RECIPE, SERVICE_RECIPE]), {})

    def test_one_outpost_without_a_depot_keeps_the_depot_order(self):
        w = self.world
        w.add_drone_depot("depot_home", w.home)
        for outpost in (w.home, self.remote):
            w.add_building(f"service_{outpost.id}", outpost, "drone_service_station")
        self.assertEqual(self.publish([DEPOT_RECIPE, SERVICE_RECIPE]), {"drone_station_kit": KIT})


if __name__ == "__main__":
    unittest.main()
