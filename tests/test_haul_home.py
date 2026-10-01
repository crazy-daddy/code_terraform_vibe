"""Stub tests for getting Inventory-only parts built at a remote fab site home:
loaded hauler cargo counts as network stock (logistics_requests.aboard_units(),
production.SourceCache.network_stock()) and an Inventory-only item unloads
straight into home Inventory (storage.best_unload_target())."""
import unittest

from harness import StubTestCase, production, storage, logistics_requests


class AboardStockTests(StubTestCase):
    def test_only_loaded_pickups_count_as_network_stock(self):
        w = self.world
        remote = w.add_outpost("outpost_2")
        w.add_warehouse("warehouse_2", remote, {"drone_small": 1})
        now = w.clock.now
        logistics_requests.reserve_pickup("pioneer_1", "home", "drone_small", 1, now, source_id="outpost_2")
        self.assertEqual(logistics_requests.aboard_units(now), {})
        self.assertEqual(production.SourceCache().network_stock("drone_small"), 1)

        # Loaded: the unit left the Warehouse and rides in cargo.
        w.components["warehouse_2"].items["drone_small"] = 0
        logistics_requests.reserve_pickup("pioneer_1", "home", "drone_small", 1, now, source_id="outpost_2", aboard=True)
        self.assertEqual(logistics_requests.aboard_units(now), {"drone_small": 1})
        self.assertEqual(production.SourceCache().network_stock("drone_small"), 1)
        self.assertEqual(production.root_remaining("drone_small", 1, production.SourceCache()), 0)

        logistics_requests.release_pickups("pioneer_1")
        self.assertEqual(logistics_requests.aboard_units(now), {})


class UnloadTargetTests(StubTestCase):
    def test_inventory_only_item_goes_to_inventory_at_home(self):
        w = self.world
        w.add_warehouse("warehouse_1", w.home)
        self.assertEqual(storage.best_unload_target("drone_small", 1, outpost=w.home), "inventory")
        self.assertEqual(storage.best_unload_target("iron_ingot", 1, outpost=w.home), "warehouse_1")

    def test_remote_outpost_keeps_warehouse(self):
        w = self.world
        remote = w.add_outpost("outpost_2")
        w.add_warehouse("warehouse_2", remote)
        self.assertEqual(storage.best_unload_target("drone_small", 1, outpost=remote), "warehouse_2")

    def test_full_inventory_falls_back_to_warehouse(self):
        w = self.world
        w.add_warehouse("warehouse_1", w.home)
        w.inventory.capacity_units = 0
        self.assertEqual(storage.best_unload_target("drone_small", 1, outpost=w.home), "warehouse_1")


if __name__ == "__main__":
    unittest.main()
