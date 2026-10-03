"""Stub tests for direct delivery: storage.push_to_targets() and producers
pushing output straight into a local consumer (Supply Dock) before storage."""
import unittest

from harness import StubTestCase, fabricator
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


if __name__ == "__main__":
    unittest.main()
