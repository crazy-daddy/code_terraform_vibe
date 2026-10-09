"""Stub tests for the Drone Depot -> Smelter direct feed: Smelter wants
(production_core.SMELTER_WANTS_KEY) and lib/drone_depot.py drain_freight()."""
import unittest

from harness import StubTestCase, disable_ingot_buffer, home_order, production, smelter
from drone_depot import DroneDepotController
from production_core import SMELTER_WANTS_KEY


class DepotSmelterFeedTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        self.warehouse = w.add_warehouse("warehouse_1", w.home)
        self.depot = w.add_drone_depot("drone_station_1", w.home)
        self.smelter = w.add_smelter("smelter_1", w.home)
        self.smelter.recipe = "smelt_iron_ingot"
        self.depot.output_buffer.update({"iron_ore": 80, "silicon": 10})

    def want(self, fill_to, site="home", tick=None, smelter_id="smelter_1"):
        tick = self.world.services["clock"].now if tick is None else tick
        wants = dict(self.world.notebook.data.get(SMELTER_WANTS_KEY) or {})
        wants[smelter_id] = {"site": site, "ore": "iron_ore", "fill_to": fill_to, "tick": tick}
        self.world.notebook.set(SMELTER_WANTS_KEY, wants)

    def test_feeds_up_to_fill_to_then_stores_rest(self):
        self.want(12)
        self.smelter.input_buffer["iron_ore"] = 5
        self.assertEqual(DroneDepotController(self.depot).drain_freight(), 90)
        self.assertEqual(self.smelter.input_buffer["iron_ore"], 12)
        self.assertEqual(self.warehouse.count("iron_ore"), 73)
        self.assertEqual(self.warehouse.count("silicon"), 10)

    def test_no_want_stores_everything(self):
        DroneDepotController(self.depot).drain_freight()
        self.assertEqual(self.smelter.input_buffer, {})
        self.assertEqual(self.warehouse.count("iron_ore"), 80)

    def test_stale_or_foreign_site_want_ignored(self):
        self.want(12, tick=self.world.services["clock"].now - production.WANTS_STALE_TICKS)
        DroneDepotController(self.depot).drain_freight()
        self.assertEqual(self.smelter.input_buffer, {})
        self.want(12, site="outpost_2")
        DroneDepotController(self.depot).drain_freight()
        self.assertEqual(self.smelter.input_buffer, {})


class SmelterWantTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        disable_ingot_buffer(w)
        w.add_fabricator("fabricator_1", w.home)
        w.add_warehouse("wh1", w.home, {"iron_ore": 100})
        self.smelter = w.add_smelter("smelter_1", w.home)
        self.controller = smelter.SmelterController(self.smelter)

    def entry(self):
        return (self.world.notebook.data.get(SMELTER_WANTS_KEY) or {}).get("smelter_1")

    def test_want_capped_by_demand_share(self):
        home_order({"steel_plate": 1})
        self.controller.step()
        entry = self.entry()
        assert entry is not None
        recipe = self.smelter.find_recipe("smelt_iron_ingot")
        prefill = production.craft_prefill_units(recipe, "iron_ore", smelter.SMELTER_PREFILL_SECONDS)
        self.assertEqual(entry["ore"], "iron_ore")
        self.assertGreater(entry["fill_to"], 0)
        self.assertLessEqual(entry["fill_to"], prefill)

    def test_want_removed_once_demand_met(self):
        home_order({"steel_plate": 1})
        self.controller.step()
        self.assertIsNotNone(self.entry())
        home_order({})
        self.controller.step()
        self.assertIsNone(self.entry())


if __name__ == "__main__":
    unittest.main()
