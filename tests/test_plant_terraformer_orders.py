"""Stub tests for the Plant Terraformer's Fabricator orders (lib/plant_terraformer.py)
and the Fabricator's backlog tier (lib/fabricator.py choose_recipe())."""
import unittest

from harness import StubTestCase, home_order, fabricator, production
from game_stubs import FABRICATOR_RECIPES, Recipe

import plant_terraformer
import plant_terraformer_demand


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
        need, backlog = plant_terraformer_demand.order_sizes(27 / 30.0, 6600, 3, 5750000)
        self.assertEqual((need, backlog), (27, 270))

    def test_capped_by_remaining_ladder(self):
        # 6,600 Forage left: one batch, 0.9 Mk II items.
        self.assertEqual(plant_terraformer_demand.order_sizes(27 / 30.0, 6600, 3, 6600), (1, 1))
        self.assertEqual(plant_terraformer_demand.order_sizes(27 / 30.0, 6600, 3, 0), (0, 0))


class ControllerOrderTests(StubTestCase):
    def controller(self, recipes):
        self.world.add_fabricator("fabricator_1", self.world.home, FABRICATOR_RECIPES + recipes)
        return plant_terraformer.PlantTerraformerController(_Terraformer())

    def test_orders_mk2_when_unlocked(self):
        c = self.controller(FERTILIZER_RECIPES)
        need, backlog = c.fabricator_orders(MK2_REQS, MK2_REQUIRED, 4, 1250000, 3)
        self.assertEqual(need, {"fertilizer_mk2": 27})
        self.assertEqual(backlog, {"fertilizer_mk2": 270})
        self.assertEqual(c.demand_targets(MK2_REQS, MK2_REQUIRED)["fertilizer_mk2"], 10)

    def test_falls_back_to_mk1(self):
        c = self.controller(FERTILIZER_RECIPES[:1])
        need, backlog = c.fabricator_orders(MK2_REQS, MK2_REQUIRED, 4, 1250000, 3)
        self.assertEqual(need, {"fertilizer": 81})
        self.assertEqual(backlog, {"fertilizer": 810})

    def test_accelerant_only_in_last_phase(self):
        c = self.controller(FERTILIZER_RECIPES)
        reqs = dict(MK2_REQS, growth_accelerant=1)
        need, _ = c.fabricator_orders(reqs, MK2_REQUIRED + ["growth_accelerant"], 5, 4500000, 3)
        self.assertEqual(need, {"fertilizer_mk2": 27, "growth_accelerant": 30})

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
        home_order({"steel_plate": 2})
        production.set_backlog_order("plant_terraformer", {"fertilizer_mk2": 20})

    def choose(self):
        recipe = fabricator.FabricatorController(self.fab).choose_recipe()
        return getattr(recipe, "output_item", None)

    def test_other_demand_beats_backlog(self):
        self.assertEqual(self.choose(), "steel_plate")

    def test_backlog_fills_idle_time(self):
        self.world.inventory.add("steel_plate", 2)
        self.assertEqual(self.choose(), "fertilizer_mk2")

    def test_bigger_unmet_need_wins_its_tier(self):
        production.set_upgrade_order("plant_terraformer", {"fertilizer_mk2": 6})
        self.assertEqual(self.choose(), "fertilizer_mk2")

    def test_met_need_leaves_rest_as_backlog(self):
        production.set_upgrade_order("plant_terraformer", {"fertilizer_mk2": 6})
        self.world.inventory.add("fertilizer_mk2", 6)
        self.assertEqual(self.choose(), "steel_plate")



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


# Full Mk II batch in the Growth Accelerant phase (plant_terraformer_guide.md).
ACCEL_REQS = {"forage": 6600, "water": 330, "salt": 14, "fertilizer_potency": 27, "growth_accelerant": 1}
ACCEL_REQUIRED = ["forage", "water", "salt", "fertilizer", "growth_accelerant"]


class _FeedTerraformer(_HomeTerraformer):
    def __init__(self, held):
        super().__init__()
        self.held = dict(held)
        self.enabled = True

    def is_enabled(self):
        return self.enabled

    def set_enabled(self, enabled):
        self.enabled = enabled

    def fertilizer_potency(self, item_id):
        return {"fertilizer_mk3": 50, "fertilizer_mk2": 30, "fertilizer": 10}[item_id]


class _IdleFeedTerraformer(_FeedTerraformer):
    """Between batches: no Forage loaded yet, in the Growth Accelerant phase."""

    def status(self):
        return "no_forage"

    def phase(self):
        return 5

    def required_inputs(self):
        return ACCEL_REQUIRED

    def batch_requirements(self):
        return ACCEL_REQS


class _LoadRecordingController(plant_terraformer.PlantTerraformerController):
    """Records each item_id _take() moves, in order."""

    def __init__(self, machine):
        super().__init__(machine)
        self.loads = []


class FeedOrderTests(StubTestCase):
    """A batch ending mid-load must not find a startable partial set in the holders."""

    def controller(self, held, stock, transfer_cap=None, cls=_FeedTerraformer):
        machine = cls(held)
        ctrl = _LoadRecordingController(machine)
        ctrl.onboard = lambda: dict(machine.held)
        ctrl.water_level = lambda: 330.0
        ctrl.available = lambda item_id, requests: stock.get(item_id, 0)

        def take(item_id, amount, requests):
            moved = max(min(amount, stock.get(item_id, 0), transfer_cap or amount), 0)
            if moved:
                machine.held[item_id] = machine.held.get(item_id, 0) + moved
                ctrl.loads.append(item_id)
            return moved

        ctrl._take = take
        return ctrl, machine

    def test_in_flight_loads_forage_before_support(self):
        stock = {"forage": 9000, "salt": 50, "fertilizer_mk2": 5, "growth_accelerant": 5}
        ctrl, machine = self.controller({}, stock)
        ctrl.feed(ACCEL_REQS, ACCEL_REQUIRED, True, {})
        self.assertEqual(ctrl.loads[0], "forage")
        self.assertEqual(machine.held["forage"], 6600)
        self.assertEqual(machine.held["growth_accelerant"], 1)

    def test_in_flight_holds_support_back_while_forage_short(self):
        stock = {"forage": 9000, "salt": 50, "fertilizer_mk2": 5, "growth_accelerant": 5}
        ctrl, machine = self.controller({}, stock, transfer_cap=2000)
        moved = ctrl.feed(ACCEL_REQS, ACCEL_REQUIRED, True, {})
        self.assertEqual(moved, {"forage": 2000})
        self.assertNotIn("growth_accelerant", machine.held)

    def test_in_flight_skips_forage_when_support_unreachable(self):
        stock = {"forage": 9000, "salt": 50, "fertilizer_mk2": 5}
        ctrl, machine = self.controller({}, stock)
        self.assertEqual(ctrl.feed(ACCEL_REQS, ACCEL_REQUIRED, True, {}), {})

    def test_idle_step_disables_before_loading(self):
        stock = {"forage": 200, "salt": 50, "fertilizer_mk2": 5, "growth_accelerant": 5}
        ctrl, machine = self.controller({"salt": 14, "fertilizer_mk2": 1, "growth_accelerant": 1}, stock,
                                        cls=_IdleFeedTerraformer)
        enabled_at_load = []
        feed = ctrl.feed
        ctrl.feed = lambda *args, **kwargs: enabled_at_load.append(machine.enabled) or feed(*args, **kwargs)
        ctrl.publish_requests = lambda *args, **kwargs: None
        ctrl.publish_fabricator_orders = lambda *args, **kwargs: None
        ctrl.ensure_water = lambda *args, **kwargs: None
        ctrl.step()
        self.assertEqual(enabled_at_load, [False])
        self.assertFalse(machine.enabled)


if __name__ == "__main__":
    unittest.main()
