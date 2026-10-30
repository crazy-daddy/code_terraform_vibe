"""SourceCache netting (lib/production_source.py) on the small sample world.

A home order for a part keeps its ingot short. Moving units between home
storage and a home machine or a home Drone Depot is not production: the Smelter
demands (netted against network_have()) and what Fabricator netting counts on
hand at home (fab_have(), fabricator.py's top_deficit() input) must read the
same before and after; cargo loaded aboard a hauler still counts network-wide.
Bug caught: a unit counted in two places (the shortfall vanishes: stall) or in
none (a new shortfall: overproduction).
"""

import unittest

import harness
import logistics_requests
import production_demand
import production_source
import sample_world

UNITS = 5
ORDERED = 500  # far above any stock, so the part and its ingot stay short


class SourceNettingTests(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        self.sample = sample_world.build_sample_world("small")
        self.world = self.sample.world  # tearDown checks this world's console for swallowed bugs
        self.home = self.world.home
        self.home_fab = next(f for f in self.sample.fabricators if f.outpost is self.home)
        self.home_smelter = next(s for s in self.sample.smelters if s.outpost is self.home)
        self.item, self.part = self._ordered_part()
        harness.home_order({self.part: ORDERED})

    def _ordered_part(self):
        """(ingot, part): a part crafted from an ingot home Inventory holds at least UNITS of."""
        for recipe in self.sample.fabricator_recipes:
            if recipe.output_item not in sample_world.PARTS:
                continue
            for item_id in recipe.inputs:
                if item_id in sample_world.INGOTS and self.world.inventory.count(item_id) >= UNITS:
                    return item_id, recipe.output_item
        self.fail("sample world has no part crafted from a stocked ingot")

    def smelter_demands(self):
        demands = production_demand.get_smelter_demands(production_source.SourceCache())
        return {item_id: production_demand.ladder_total(levels) for item_id, levels in demands.items()}

    def snapshot(self):
        cache = production_source.SourceCache()
        home_have = {item_id: cache.fab_have(item_id, self.home) for item_id in (self.item, self.part)}
        return self.smelter_demands(), home_have

    def take_from_inventory(self, item_id=None):
        self.world.inventory.remove(item_id or self.item, UNITS)

    def test_units_leaving_the_network_change_both_counts(self):
        """Control: the snapshot sees stock, so the equalities below are not vacuous."""
        before_demands, before_have = self.snapshot()
        self.assertGreater(before_demands.get(self.item, 0), 0)
        self.take_from_inventory()
        after_demands, after_have = self.snapshot()
        self.assertEqual(after_demands[self.item], before_demands[self.item] + UNITS)
        self.assertEqual(after_have[self.item], before_have[self.item] - UNITS)

    def test_inventory_to_fabricator_stockpile(self):
        before = self.snapshot()
        self.take_from_inventory()
        self.home_fab.input_buffer[self.item] = self.home_fab.input_buffer.get(self.item, 0) + UNITS
        self.assertEqual(self.snapshot(), before)

    def test_inventory_to_smelter_input(self):
        before = self.snapshot()
        self.take_from_inventory()
        self.home_smelter.input_buffer[self.item] = self.home_smelter.input_buffer.get(self.item, 0) + UNITS
        self.assertEqual(self.snapshot(), before)

    def test_smelter_output_to_inventory(self):
        self.take_from_inventory()
        self.home_smelter.output_buffer[self.item] = self.home_smelter.output_buffer.get(self.item, 0) + UNITS
        before = self.snapshot()
        self.home_smelter.output_buffer[self.item] -= UNITS
        self.world.inventory.add(self.item, UNITS)
        self.assertEqual(self.snapshot(), before)

    def test_fabricator_output_to_inventory(self):
        self.home_fab.output_buffer[self.part] = self.home_fab.output_buffer.get(self.part, 0) + UNITS
        before = self.snapshot()
        self.home_fab.output_buffer[self.part] -= UNITS
        self.world.inventory.add(self.part, UNITS)
        self.assertEqual(self.snapshot(), before)

    def test_inventory_to_home_drone_depot(self):
        depot = self.world.add_drone_depot("drone_station_home", self.home)
        before = self.snapshot()
        self.take_from_inventory()
        depot.output_buffer[self.item] = depot.output_buffer.get(self.item, 0) + UNITS
        self.assertEqual(self.snapshot(), before)

    def test_inventory_to_hauler_cargo_keeps_smelter_demands(self):
        before_demands, before_have = self.snapshot()
        before_network = production_source.SourceCache().network_have(self.item)
        self.take_from_inventory()
        remote = self.sample.remotes[0].id
        hauler = self.sample.drones[0].id  # a drone the sample world really has
        logistics_requests.reserve_pickup(
            hauler, remote, self.item, UNITS, self.world.clock.now, source_id=self.home.id, aboard=True
        )
        after_demands, after_have = self.snapshot()
        # Network-wide the cargo still counts: no new Smelter shortfall.
        self.assertEqual(after_demands, before_demands)
        self.assertEqual(production_source.SourceCache().network_have(self.item), before_network)
        # At home it is gone: bound for a remote outpost, not on hand for home crafts.
        self.assertEqual(after_have[self.item], before_have[self.item] - UNITS)
        self.assertEqual(after_have[self.part], before_have[self.part])


if __name__ == "__main__":
    unittest.main()
