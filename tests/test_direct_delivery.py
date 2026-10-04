"""Stub tests for direct delivery: storage.push_to_targets() and producers
pushing output straight into a local consumer (Supply Dock) before storage."""
import unittest

from harness import StubTestCase, fabricator, production, smelter
import storage


class PushToTargetsTests(StubTestCase):
    def test_fills_targets_in_order_within_caps(self):
        w = self.world
        f = w.add_fabricator("fabricator_1", w.home)
        dock_a = w.add_supply_dock("supply_dock_1", w.home)
        dock_b = w.add_supply_dock("supply_dock_2", w.home)
        order = w.add_order("order_1", {"steel_plate": 20})
        dock_a.order = order
        dock_b.order = order
        f.output_buffer["steel_plate"] = 10
        delivered = storage.push_to_targets(f.output, "steel_plate", 10, [("supply_dock_1", 4), ("supply_dock_2", 20)])
        self.assertEqual(delivered, [("supply_dock_1", 4), ("supply_dock_2", 6)])
        self.assertEqual(f.output_buffer, {})

    def test_busy_full_and_remote_targets_fall_through(self):
        w = self.world
        remote = w.add_outpost("outpost_2")
        f = w.add_fabricator("fabricator_1", w.home)
        busy = w.add_supply_dock("supply_dock_1", w.home)
        busy.input_busy = True
        full = w.add_supply_dock("supply_dock_2", w.home)  # no order: takes nothing
        far = w.add_supply_dock("supply_dock_3", remote)
        busy.order = far.order = w.add_order("order_1", {"steel_plate": 20})
        f.output_buffer["steel_plate"] = 5
        targets = [("supply_dock_1", 5), ("supply_dock_2", 5), ("supply_dock_3", 5)]
        self.assertEqual(storage.push_to_targets(f.output, "steel_plate", 5, targets), [])
        self.assertEqual(f.output_buffer, {"steel_plate": 5})
        self.assertEqual(full.total(), 0)


class FabricatorDockDrainTests(StubTestCase):
    def test_owed_units_go_to_local_dock_rest_to_warehouse(self):
        w = self.world
        warehouse = w.add_warehouse("warehouse_1", w.home)
        f = w.add_fabricator("fabricator_1", w.home)
        dock = w.add_supply_dock("supply_dock_1", w.home)
        dock.order = w.add_order("order_1", {"steel_plate": 10}, shipped={"steel_plate": 7})
        f.output_buffer["steel_plate"] = 5
        self.assertTrue(fabricator.FabricatorController(f).drain_output())
        self.assertEqual(dock.count("steel_plate"), 3)
        self.assertEqual(warehouse.count("steel_plate"), 2)
        self.assertEqual(w.inventory.count("steel_plate"), 0)

    def test_inventory_only_item_stays_in_inventory(self):
        w = self.world
        warehouse = w.add_warehouse("warehouse_1", w.home)
        f = w.add_fabricator("fabricator_1", w.home)
        f.output_buffer["drone_small"] = 2
        fabricator.FabricatorController(f).drain_output()
        self.assertEqual(w.inventory.count("drone_small"), 2)
        self.assertEqual(warehouse.count("drone_small"), 0)

    def test_dock_at_other_outpost_ignored(self):
        w = self.world
        remote = w.add_outpost("outpost_2")
        warehouse = w.add_warehouse("warehouse_1", w.home)
        f = w.add_fabricator("fabricator_1", w.home)
        dock = w.add_supply_dock("supply_dock_1", remote)
        dock.order = w.add_order("order_1", {"steel_plate": 10})
        f.output_buffer["steel_plate"] = 5
        fabricator.FabricatorController(f).drain_output()
        self.assertEqual(dock.count("steel_plate"), 0)
        self.assertEqual(warehouse.count("steel_plate"), 5)

    def test_blueprint_demand_ships_only_the_surplus(self):
        w = self.world
        warehouse = w.add_warehouse("warehouse_1", w.home, items={"steel_plate": 2})
        f = w.add_fabricator("fabricator_1", w.home)
        dock = w.add_supply_dock("supply_dock_1", w.home)
        dock.order = w.add_order("order_1", {"steel_plate": 10})
        w.add_blueprint("job_1", "steel_plate", 5)
        f.output_buffer["steel_plate"] = 5
        fabricator.FabricatorController(f).drain_output()
        self.assertEqual(dock.count("steel_plate"), 2)  # 2 stock + 5 new - 5 for the blueprint
        self.assertEqual(warehouse.count("steel_plate"), 5)


class FabricatorWantsTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        w.notebook.set(production.FABRICATOR_STOCK_TARGETS_KEY, {"steel_plate": 30})
        self.fab = w.add_fabricator("fabricator_1", w.home)
        self.controller = fabricator.FabricatorController(self.fab)

    def wants(self):
        return (self.world.notebook.data.get(production.FABRICATOR_WANTS_KEY) or {}).get("fabricator_1")

    def test_publishes_short_input_up_to_prefill(self):
        self.world.inventory.add("iron_ingot", 2)
        self.controller.step()  # sets the recipe
        self.controller.step()  # takes the 2 in stock, wants the rest of its prefill window
        cap = production.craft_prefill_units(self.fab.find_recipe("craft_steel_plate"), "iron_ingot")
        self.assertEqual(self.fab.input_buffer.get("iron_ingot"), 2)
        wants = self.wants()
        assert wants is not None
        self.assertEqual(wants["wants"], {"iron_ingot": cap - 2})
        self.assertEqual(wants["site"], "home")

    def test_entry_removed_once_nothing_is_short(self):
        self.world.inventory.add("iron_ingot", 2)
        self.controller.step()
        self.controller.step()
        self.assertIsNotNone(self.wants())
        self.world.notebook.set(production.FABRICATOR_STOCK_TARGETS_KEY, {})
        self.controller.step()
        self.assertIsNone(self.wants())


class SmelterToFabricatorTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        self.warehouse = w.add_warehouse("warehouse_1", w.home)
        self.fab = w.add_fabricator("fabricator_1", w.home)
        self.smelter = w.add_smelter("smelter_1", w.home)
        self.controller = smelter.SmelterController(self.smelter)

    def want(self, units, site="home", tick=None):
        tick = self.world.services["clock"].now if tick is None else tick
        self.world.notebook.set(production.FABRICATOR_WANTS_KEY, {"fabricator_1": {"site": site, "wants": {"iron_ingot": units}, "tick": tick}})

    def test_fabricator_want_filled_before_storage(self):
        self.want(6)
        self.smelter.output_buffer["iron_ingot"] = 10
        self.assertEqual(self.controller.drain_output(), 10)
        self.assertEqual(self.fab.input_buffer.get("iron_ingot"), 6)
        self.assertEqual(self.warehouse.count("iron_ingot"), 4)

    def test_same_want_not_pushed_twice(self):
        self.want(6)
        self.smelter.output_buffer["iron_ingot"] = 4
        self.controller.drain_output()
        self.smelter.output_buffer["iron_ingot"] = 4
        self.controller.drain_output()
        self.assertEqual(self.fab.input_buffer.get("iron_ingot"), 6)
        self.assertEqual(self.warehouse.count("iron_ingot"), 2)

    def test_stale_or_other_site_want_ignored(self):
        self.want(6, tick=self.world.services["clock"].now - production.WANTS_STALE_TICKS)
        self.smelter.output_buffer["iron_ingot"] = 3
        self.controller.drain_output()
        self.want(6, site="outpost_2")
        self.smelter.output_buffer["iron_ingot"] = 3
        self.controller.drain_output()
        self.assertEqual(self.fab.input_buffer.get("iron_ingot", 0), 0)
        self.assertEqual(self.warehouse.count("iron_ingot"), 6)

    def test_dock_after_fabricator(self):
        self.want(2)
        dock = self.world.add_supply_dock("supply_dock_1", self.world.home)
        dock.order = self.world.add_order("order_1", {"iron_ingot": 3})
        self.smelter.output_buffer["iron_ingot"] = 10
        self.controller.drain_output()
        self.assertEqual((self.fab.input_buffer.get("iron_ingot"), dock.count("iron_ingot"), self.warehouse.count("iron_ingot")), (2, 3, 5))


if __name__ == "__main__":
    unittest.main()
