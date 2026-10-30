"""Priority ladders end to end: inheritance down a recipe tree, top-down stock
netting, Fabricator/Smelter band selection, hauler ranking, dock overrides and
site supply bands (lib/priority.py and its readers)."""

import itertools
import unittest
from types import SimpleNamespace
from unittest import mock

import construction_plan
import priority
import production_cascade
import production_core
import production_demand
import production_docks
from game_stubs import FABRICATOR_RECIPES, Recipe
from harness import (
    StubTestCase,
    fabricator,
    home_order,
    logistics_requests,
    production,
    site_supply,
    smelter,
    supply_dock,
)


def top_prio(levels):
    return levels[0][0]


def chain_world(world):
    """Home with a Fabricator (widget <- steel_plate <- iron_ingot) and a Smelter (iron_ore -> iron_ingot)."""
    widget = Recipe("craft_widget", {"steel_plate": 1}, "widget", duration_game_hours=0.1)
    machine = world.add_fabricator("fabricator_1", world.home, FABRICATOR_RECIPES + [widget])
    world.add_smelter("smelter_1", world.home)
    return machine


def dock_order(world, order_id, requires, prio):
    world.add_supply_dock("supply_dock_1", world.home).order = world.add_order(order_id, requires)
    world.notebook.set(production_docks.ORDER_PRIO_KEY, {order_id: prio})


class InheritanceTests(StubTestCase):
    def test_manual_root_lifts_intermediate_and_ingot(self):
        w = self.world
        chain_world(w)
        w.inventory.add("iron_ore", 100)
        home_order({"widget": 2}, prio=priority.MANUAL)
        cache = production.SourceCache()
        ladders = production_cascade.fabricator_target_ladders(cache)
        self.assertEqual(top_prio(ladders["steel_plate"]), priority.MANUAL)
        depths = production_cascade.recipe_depths(cache)
        self.assertEqual((depths["widget"], depths["steel_plate"]), (0, 1))
        demands = production_demand.get_smelter_demands(cache)
        self.assertEqual(top_prio(demands["iron_ingot"]), priority.MANUAL)


class NettingTests(StubTestCase):
    def test_stock_covers_the_order_level_first(self):
        w = self.world
        chain_world(w)
        dock_order(w, "o1", {"steel_plate": 10}, 650)
        home_order({"steel_plate": 100}, prio=priority.STOCK)
        ladder = production_cascade.fabricator_target_ladders(production.SourceCache())["steel_plate"]
        self.assertEqual(ladder, [[650, 10], [priority.STOCK, 100]])
        self.assertEqual(priority.ladder_deficits(ladder, 12), [(priority.STOCK, 88)])


class BacklogIntermediateTests(StubTestCase):
    def test_stock_intermediate_of_order_root_ranks_order_band(self):
        w = self.world
        machine = chain_world(w)
        w.inventory.add("iron_ingot", 100)
        dock_order(w, "o1", {"widget": 2}, 640)
        production.set_order("site_stock", {"steel_plate": [3, priority.STOCK]})
        controller = fabricator.FabricatorController(machine)
        cache = production.SourceCache()
        recipe = controller.choose_recipe(cache)
        assert recipe is not None
        self.assertEqual(recipe.output_item, "steel_plate")
        reason = controller.target_reason("steel_plate", cache)
        self.assertIn("order", reason)
        self.assertIn("640", reason)


class StickyBandTests(StubTestCase):
    """Current gas_pipe_segment (10 at NEED) against a bigger widget shortfall (20)."""

    def setUp(self):
        super().setUp()
        w = self.world
        widget = Recipe("craft_widget", {"glass": 1}, "widget", duration_game_hours=0.1)
        self.machine = w.add_fabricator("fabricator_1", w.home, [FABRICATOR_RECIPES[0], widget])
        w.add_smelter("smelter_1", w.home)
        w.inventory.add("iron_ore", 50)
        w.inventory.add("glass", 30)
        production.set_order("test_gas", {"gas_pipe_segment": [10, priority.NEED]})
        self.machine.recipe = "craft_gas_pipe_segment"
        self.controller = fabricator.FabricatorController(self.machine)

    def chosen(self):
        recipe = self.controller.choose_recipe()
        assert recipe is not None
        return recipe.id

    def test_same_band_bigger_shortfall_keeps_current(self):
        self.world.inventory.add("iron_ingot", 100)
        production.set_order("test_widget", {"widget": [20, priority.NEED]})
        self.assertEqual(self.chosen(), "craft_gas_pipe_segment")

    def test_higher_band_switches(self):
        self.world.inventory.add("iron_ingot", 100)
        production.set_order("test_widget", {"widget": [20, priority.UPGRADE]})
        self.assertEqual(self.chosen(), "craft_widget")

    def test_starved_current_yields_to_same_band(self):
        production.set_order("test_widget", {"widget": [20, priority.NEED]})
        self.assertEqual(self.chosen(), "craft_widget")


class SmelterBandTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        w.inventory.add("iron_ore", 100)
        w.inventory.add("silicon", 100)
        self.machine = w.add_smelter("smelter_1", w.home)
        self.controller = smelter.SmelterController(self.machine)
        self.cache = production.SourceCache()
        self.demands = {"iron_ingot": [[priority.ORDER_AHEAD, 500]], "glass": [[600, 5], [priority.ORDER_AHEAD, 505]]}

    def test_highest_band_wins_over_bigger_look_ahead(self):
        recipe, ore, _refilling, _demands = self.controller.select_recipe(None, self.demands, self.cache, {})
        assert recipe is not None
        self.assertEqual((recipe.id, ore), ("smelt_glass", "silicon"))

    def test_order_ahead_never_raises_the_share(self):
        recipe, ore, refilling, demands = self.controller.select_recipe(None, self.demands, self.cache, {})
        seen = []
        self.controller.log_outcome = lambda reason, **detail: seen.append(detail)
        self.controller.load_ore(recipe, ore, demands, self.cache, {}, refilling, False)
        self.assertEqual(priority.ladder_level(demands["glass"], priority.ORDER), 5)
        self.assertEqual(seen[-1]["demand"], 5)


class HaulRankTests(StubTestCase):
    def test_four_bands_rank_in_order(self):
        ranks = [
            logistics_requests.haul_rank({band: units}, 100, 0)
            for band, units in (
                (priority.BLOCKER, 1),
                (priority.ORDER, 50),
                (priority.NEED, 200),
                (priority.STOCK, 1000),
            )
        ]
        for better, worse in itertools.pairwise(ranks):
            self.assertTrue(logistics_requests.rank_beats(better, worse))
            self.assertFalse(logistics_requests.rank_beats(worse, better))

    def test_blocker_units_ignore_other_bands(self):
        self.assertEqual(logistics_requests.blocker_units({priority.BLOCKER: 1, priority.STOCK: 9}), 1)


class DockOverrideTests(StubTestCase):
    def test_dock_order_prios_reads_the_given_key(self):
        self.world.notebook.set(supply_dock.PRIORITY_OVERRIDE_KEY, {"o1": 850, "bad": "x"})
        self.world.notebook.set(production_docks.ORDER_PRIO_KEY, {"o2": 300})
        self.assertEqual(production_docks.dock_order_prios(supply_dock.PRIORITY_OVERRIDE_KEY), {"o1": 850})
        self.assertEqual(production_docks.dock_order_prios(), {"o2": 300})
        self.world.notebook.set(supply_dock.PRIORITY_OVERRIDE_KEY, "junk")
        self.assertEqual(production_docks.dock_order_prios(supply_dock.PRIORITY_OVERRIDE_KEY), {})

    def test_override_wins_over_score(self):
        order = SimpleNamespace(id="o1")
        self.world.notebook.set(supply_dock.PRIORITY_OVERRIDE_KEY, {"o1": 850})
        overrides = supply_dock.order_overrides()
        self.assertEqual(supply_dock._order_prio(order, 5, overrides), 850)
        self.assertEqual(supply_dock._order_prio(SimpleNamespace(id="o2"), 0, overrides), priority.ORDER)

    def test_publish_writes_prios_and_drops_stale_override(self):
        w = self.world
        w.notebook.set(supply_dock.PRIORITY_OVERRIDE_KEY, {"o1": 850, "gone": 300})
        candidates = [{"order": SimpleNamespace(id="o1"), "prio": 850}]
        supply_dock.publish_order_prios(candidates, supply_dock.order_overrides())
        self.assertEqual(w.notebook.get(production_docks.ORDER_PRIO_KEY), {"o1": 850})
        self.assertEqual(supply_dock.order_overrides(), {"o1": 850})

    def test_dock_order_root_carries_the_override(self):
        w = self.world
        chain_world(w)
        dock_order(w, "o1", {"steel_plate": 4}, 850)
        roots, _consumers, _outputs = production_cascade.fabricator_root_targets(production.SourceCache())
        self.assertEqual(top_prio(roots["steel_plate"]), 850)


class SiteSupplyBandTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        self.remote = w.add_outpost("outpost_2")
        w.research.unlocked.add("research_warehouse")
        w.notebook.set(site_supply.CONSTRUCTION_STOCK_KEY, {})
        self.enterContext(mock.patch.object(production_core, "constructor_base", lambda: "outpost_2"))
        w.add_warehouse("wh_remote", self.remote)
        w.add_fabricator("fabricator_2", self.remote)

    def builder_ladder(self):
        _roots, consumers, _outputs = production_cascade.fabricator_root_targets(production.SourceCache())
        return consumers["liquid_pipe_bridge"]["outpost_2"]

    def test_settled_blueprint_item_is_blocker_at_builder(self):
        w = self.world
        w.add_warehouse("wh_home", w.home, {"liquid_pipe_bridge": 1})
        home_order({"gas_pipe_segment": 0})
        w.add_blueprint("bp_1", "liquid_pipe_bridge")
        site_supply.publish_site_requests(w.clock.now)
        entry = logistics_requests.active_requests(w.clock.now)["outpost_2"]["liquid_pipe_bridge"]
        self.assertGreater(priority.ladder_level(logistics_requests.request_levels(entry), priority.BLOCKER), 0)

    def test_plan_ahead_blueprint_is_build_ahead_band(self):
        w = self.world
        w.add_blueprint("bp_1", "liquid_pipe_bridge")
        w.notebook.set(construction_plan.PLANNED_KEY, {"bp_1": 1})
        w.notebook.set(construction_plan.PRIORITY_KEY, {"bp_1": 1})
        self.assertEqual(priority.band(top_prio(self.builder_ladder())), priority.BUILD_AHEAD)

    def test_operator_blueprint_is_manual_band(self):
        self.world.add_blueprint("bp_1", "liquid_pipe_bridge")
        self.assertEqual(priority.band(top_prio(self.builder_ladder())), priority.MANUAL)


class RaiseTargetTests(StubTestCase):
    def test_max_folds_levels_and_traces_the_source(self):
        targets = {"gear": [(priority.MANUAL, 5)]}
        with mock.patch.object(production_cascade.log, "trace") as trace:
            production_cascade._raise_target(targets, "gear", [(priority.MANUAL, 3), (priority.BUILD, 9)], "order book")
        self.assertEqual(
            targets["gear"], priority.ladder_max([(priority.MANUAL, 5)], [(priority.MANUAL, 3), (priority.BUILD, 9)])
        )
        trace.assert_called_once_with(f"get_fabricator_targets: order book raises target for gear -> {targets['gear']}")


if __name__ == "__main__":
    unittest.main()
