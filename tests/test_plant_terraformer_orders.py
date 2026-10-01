"""Stub tests for the Plant Terraformer's Fabricator orders (8_planting/lib/plant_terraformer.py)
and the Fabricator's backlog tier (lib/fabricator.py choose_recipe())."""
import unittest

from harness import StubTestCase, fabricator, production
from game_stubs import FABRICATOR_RECIPES, Recipe

import plant_terraformer


FERTILIZER_RECIPES = [
    Recipe("craft_fertilizer", {"iron_ingot": 1}, "fertilizer", output_count=2),
    Recipe("craft_fertilizer_mk2", {"iron_ingot": 1}, "fertilizer_mk2", output_count=2),
]

# Full Mk II batch in the Fertilizer phase (plant_terraformer_guide.md).
MK2_REQS = {"forage": 6600, "water": 330, "salt": 14, "fertilizer_potency": 27}
MK2_REQUIRED = ["forage", "water", "salt", "fertilizer"]


class _Terraformer:
    id = "plant_terraformer_1"
    outpost = None

    def fertilizer_potency(self, item_id):
        return {"fertilizer_mk3": 50, "fertilizer_mk2": 30, "fertilizer": 10}[item_id]


class OrderSizeTests(unittest.TestCase):
    def test_remaining_forage_counts_later_bands(self):
        self.assertEqual(plant_terraformer.remaining_forage(4, 1250000, 4), 1250000 + 4500000)
        self.assertEqual(plant_terraformer.remaining_forage(5, 300000, 4), 900000)
        self.assertEqual(plant_terraformer.remaining_forage(4, 1000, 5), 4500000)
        self.assertEqual(plant_terraformer.remaining_forage(6, 0, 4), 0)

    def test_mk2_fleet_of_three(self):
        need, backlog = plant_terraformer.order_sizes(27 / 30.0, 6600, 3, 5750000)
        self.assertEqual((need, backlog), (6, 22))

    def test_capped_by_remaining_ladder(self):
        # 6,600 Forage left: one batch, 0.9 Mk II items.
        self.assertEqual(plant_terraformer.order_sizes(27 / 30.0, 6600, 3, 6600), (1, 1))
        self.assertEqual(plant_terraformer.order_sizes(27 / 30.0, 6600, 3, 0), (0, 0))


class ControllerOrderTests(StubTestCase):
    def controller(self, recipes):
        self.world.add_fabricator("fabricator_1", self.world.home, FABRICATOR_RECIPES + recipes)
        return plant_terraformer.PlantTerraformerController(_Terraformer())

    def test_orders_mk2_when_unlocked(self):
        c = self.controller(FERTILIZER_RECIPES)
        need, backlog = c.fabricator_orders(MK2_REQS, MK2_REQUIRED, 4, 1250000, 3)
        self.assertEqual(need, {"fertilizer_mk2": 6})
        self.assertEqual(backlog, {"fertilizer_mk2": 22})
        self.assertEqual(c.demand_targets(MK2_REQS, MK2_REQUIRED)["fertilizer_mk2"], 2)

    def test_falls_back_to_mk1(self):
        c = self.controller(FERTILIZER_RECIPES[:1])
        need, backlog = c.fabricator_orders(MK2_REQS, MK2_REQUIRED, 4, 1250000, 3)
        self.assertEqual(need, {"fertilizer": 17})
        self.assertEqual(backlog, {"fertilizer": 65})

    def test_accelerant_only_in_last_phase(self):
        c = self.controller(FERTILIZER_RECIPES)
        reqs = dict(MK2_REQS, growth_accelerant=1)
        need, _ = c.fabricator_orders(reqs, MK2_REQUIRED + ["growth_accelerant"], 5, 4500000, 3)
        self.assertEqual(need, {"fertilizer_mk2": 6, "growth_accelerant": 6})

    def test_publish_and_withdraw(self):
        c = self.controller(FERTILIZER_RECIPES)
        c.publish_fabricator_orders({"fertilizer_mk2": 6}, {"fertilizer_mk2": 22})
        self.assertEqual(production.get_upgrade_orders(), {"fertilizer_mk2": 6})
        self.assertEqual(production.get_backlog_orders(), {"fertilizer_mk2": 22})
        c.publish_fabricator_orders({}, {})
        self.assertEqual(production.get_upgrade_orders(), {})
        self.assertEqual(production.get_backlog_orders(), {})


class BacklogTierTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        w.inventory.add("iron_ingot", 100)
        self.fab = w.add_fabricator("fabricator_1", w.home, FABRICATOR_RECIPES + FERTILIZER_RECIPES)
        w.notebook.set(production.FABRICATOR_STOCK_TARGETS_KEY, {"steel_plate": 2})
        production.set_backlog_order("plant_terraformer", {"fertilizer_mk2": 20})

    def choose(self):
        recipe = fabricator.FabricatorController(self.fab).choose_recipe()
        return getattr(recipe, "output_item", None)

    def test_other_demand_beats_backlog(self):
        self.assertEqual(self.choose(), "steel_plate")

    def test_backlog_fills_idle_time(self):
        self.world.inventory.add("steel_plate", 2)
        self.assertEqual(self.choose(), "fertilizer_mk2")

    def test_unmet_need_ranks_above_stock_targets(self):
        production.set_upgrade_order("plant_terraformer", {"fertilizer_mk2": 6})
        self.assertEqual(self.choose(), "fertilizer_mk2")

    def test_met_need_leaves_rest_as_backlog(self):
        production.set_upgrade_order("plant_terraformer", {"fertilizer_mk2": 6})
        self.world.inventory.add("fertilizer_mk2", 6)
        self.assertEqual(self.choose(), "steel_plate")


if __name__ == "__main__":
    unittest.main()


class _Outpost:
    def __init__(self, outpost_id, is_home):
        self.id = outpost_id
        self.is_home = is_home


class _HomeTerraformer:
    id = "plant_terraformer_1"

    def __init__(self):
        self.outpost = _Outpost("outpost_home", True)


class WildlifeForageReserveTests(StubTestCase):
    def controller(self, machine, stock):
        ctrl = plant_terraformer.PlantTerraformerController(machine)
        ctrl.local_stock = lambda item_id: stock
        return ctrl

    def test_home_leaves_feed_maker_forage(self):
        self.world.notebook.data["wildlife.plan"] = {"forage_reserve": 1500}
        ctrl = self.controller(_HomeTerraformer(), 4000)
        self.assertEqual(ctrl.available("forage", {}), 2500)
        self.assertEqual(ctrl.available("salt", {}), 4000)

    def test_reserve_above_stock_leaves_nothing(self):
        self.world.notebook.data["wildlife.plan"] = {"forage_reserve": 5000}
        self.assertEqual(self.controller(_HomeTerraformer(), 4000).available("forage", {}), 0)

    def test_remote_terraformer_ignores_reserve(self):
        self.world.notebook.data["wildlife.plan"] = {"forage_reserve": 1500}
        machine = _HomeTerraformer()
        machine.outpost = _Outpost("outpost_2", False)
        self.assertEqual(self.controller(machine, 4000).available("forage", {}), 4000)
