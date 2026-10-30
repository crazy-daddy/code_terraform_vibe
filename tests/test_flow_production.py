"""Production flow on the medium sample world: Earth-order deficits drive the
Supply Docks and Fabricators; stock at target drives nothing.

Each pass runs what the game's controllers run every poll: the central dock
plan, every Supply Dock, every Fabricator and every Smelter. Asserted from the
outside: recipes set, inputs and order goods moved out of storage (and only
moved, never created), and nothing crafted that no order needs.
"""

import unittest
from collections import Counter

import sample_world
from game_stubs import Store
from harness import StubTestCase, fabricator, smelter, supply_dock

PASSES = 3
STOCKED_UNITS = 1000  # per item: above every order line and stock-target ladder in the sample world


class ProductionFlowTest(StubTestCase):
    def setUp(self):
        super().setUp()
        self.sample = sample_world.build_sample_world("medium")
        self.world = self.sample.world  # tearDown checks this world's console for swallowed bugs
        self.stores = [c for c in self.world.components.values() if isinstance(c, Store)] + [self.world.inventory]
        self.orders = self.world.services["orders"].orders

    def _run(self):
        s = self.sample
        controllers = (
            [supply_dock.SupplyDockController(d) for d in s.docks]
            + [fabricator.FabricatorController(f) for f in s.fabricators]
            + [smelter.SmelterController(x) for x in s.smelters]
        )
        for _ in range(PASSES):
            supply_dock.plan_dock_assignments(self.world.get_component("clock"))
            for controller in controllers:
                controller.step()

    def _holdings(self):
        """Units of each item in storage, machine buffers and dock cargo."""
        total = Counter()
        for store in self.stores:
            for item in sample_world.ALL_ITEMS:
                total[item] += store.count(item)
        for machine in self.sample.fabricators + self.sample.smelters:
            total.update(machine.input_buffer)
            total.update(machine.output_buffer)
        for dock in self.sample.docks:
            for item in sample_world.ALL_ITEMS:
                total[item] += dock.count(item)
        return +total

    def _order_tree(self):
        """Every item an active order needs, directly or through the recipes."""
        recipes = {r.output_item: r for r in self.sample.fabricator_recipes + self.sample.smelter_recipes}
        todo = [item for order in self.orders.values() for item in order.requires]
        tree = set()
        while todo:
            item = todo.pop()
            if item not in tree:
                tree.add(item)
                todo.extend(recipes[item].inputs if item in recipes else ())
        return tree

    def test_order_deficit_starts_fabricators_and_loads_docks(self):
        for order in self.orders.values():
            for item in order.requires:
                for store in self.stores:
                    if store.count(item):
                        store.remove(item, store.count(item))
        before = self._holdings()
        self._run()

        crafting = {f.id: f for f in self.sample.fabricators if f.recipe}
        self.assertGreaterEqual(len(crafting), 3, "order deficits started too few Fabricators")
        recipes = {r.id: r for r in self.sample.fabricator_recipes}
        tree = self._order_tree()
        for fab in crafting.values():
            recipe = recipes[fab.recipe]
            self.assertIn(recipe.output_item, tree, f"{fab.id} crafts {recipe.output_item}, which no order needs")
            self.assertLessEqual(set(fab.input_buffer), set(recipe.inputs), fab.id)
        self.assertTrue(any(f.input_buffer for f in crafting.values()), "no Fabricator loaded its inputs")
        for dock in self.sample.docks:
            order = dock.current_order()
            self.assertIsNotNone(order, f"{dock.id} took no order")
            assert order is not None
            cargo = {item for item in sample_world.ALL_ITEMS if dock.count(item)}
            self.assertLessEqual(cargo, set(order.requires), dock.id)
        self.assertEqual(self._holdings(), before, "units created or lost between storage, machines and docks")

    def test_stock_at_target_starts_nothing(self):
        for item in sample_world.ALL_ITEMS:
            self.world.inventory.add(item, STOCKED_UNITS)
            self.assertGreaterEqual(self.world.inventory.count(item), STOCKED_UNITS, item)
        self._run()
        for machine in self.sample.fabricators + self.sample.smelters:
            self.assertFalse(machine.recipe, f"{machine.id} started {machine.recipe} with every target met")
            self.assertEqual(dict(machine.input_buffer), {}, machine.id)
            self.assertFalse(machine.running, machine.id)


if __name__ == "__main__":
    unittest.main()
