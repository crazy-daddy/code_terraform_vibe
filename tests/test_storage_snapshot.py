"""storage.StorageSnapshot: one slots() read per store, shared by the storage
pass's sweeps; Warehouse stray folding and Inventory rebalance routing."""
import unittest

from harness import StubTestCase, storage


class StorageSnapshotTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.remote = self.world.add_outpost("outpost_2")

    def test_reads_each_store_once_until_touched(self):
        warehouse = self.world.add_warehouse("wh_1", self.remote, {"iron_ore": 100}, capacity=4000)
        snapshot = storage.StorageSnapshot()
        self.assertEqual(storage.slot_layout(self.remote, snapshot)[0], ("iron_ore", 100, 2000))
        warehouse.items["iron_ore"] = 300
        self.assertEqual(storage.slot_layout(self.remote, snapshot)[0], ("iron_ore", 100, 2000))
        snapshot.touched("wh_1")
        self.assertEqual(storage.slot_layout(self.remote, snapshot)[0], ("iron_ore", 300, 2000))

    def test_bin_consolidation_reads_bins_from_snapshot(self):
        self.world.add_storage_bin("storage_bin_small", self.remote, "glass", 5)
        self.world.add_storage_bin("storage_bin_big", self.remote, "glass", 300)
        snapshot = storage.StorageSnapshot()
        self.assertEqual(storage.consolidate_storage_bins([self.remote], snapshot), ("storage_bin_small", "storage_bin_big", "glass", 5))
        self.assertEqual(sorted(storage.slot_layout(self.remote, snapshot)), [("", 0, 500), ("glass", 305, 500)])


class WarehouseStrayTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.remote = self.world.add_outpost("outpost_2")

    def test_folds_stray_into_holder_when_slots_are_tight(self):
        self.world.add_warehouse("wh_main", self.remote, {"iron_ore": 1500, "silicon": 1000}, capacity=4000)
        self.world.add_warehouse("wh_side", self.remote, {"iron_ore": 50, "cobalt": 500}, capacity=4000)
        result = storage.consolidate_warehouse_strays([self.remote])
        self.assertEqual(result, ("wh_side", "wh_main", "iron_ore", storage.WAREHOUSE_STRAY_CHUNK))
        self.assertEqual(self.world.components["wh_main"].count("iron_ore"), 1500 + storage.WAREHOUSE_STRAY_CHUNK)

    def test_leaves_split_alone_while_a_slot_is_free(self):
        self.world.add_warehouse("wh_main", self.remote, {"iron_ore": 1500}, capacity=4000)
        self.world.add_warehouse("wh_side", self.remote, {"iron_ore": 50, "cobalt": 500}, capacity=4000)
        self.assertIsNone(storage.consolidate_warehouse_strays([self.remote]))

    def test_folds_stray_next_to_its_recipe_partner(self):
        self.world.add_warehouse("wh_main", self.remote, {"iron_ore": 1500}, capacity=10000)
        self.world.add_warehouse("wh_side", self.remote, {"iron_ore": 50, "iron_ingot": 300}, capacity=10000)
        result = storage.consolidate_warehouse_strays([self.remote])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result[:3], ("wh_side", "wh_main", "iron_ore"))

    def test_skips_large_second_stack(self):
        self.world.add_warehouse("wh_main", self.remote, {"iron_ore": 1500, "silicon": 1000}, capacity=4000)
        self.world.add_warehouse("wh_side", self.remote, {"iron_ore": storage.WAREHOUSE_STRAY_MAX_UNITS + 1, "cobalt": 500}, capacity=4000)
        self.assertIsNone(storage.consolidate_warehouse_strays([self.remote]))

    def test_skips_when_no_holder_has_room_for_the_whole_stray(self):
        self.world.add_warehouse("wh_main", self.remote, {"iron_ore": 1990, "silicon": 2000}, capacity=4000)
        self.world.add_warehouse("wh_side", self.remote, {"iron_ore": 50, "cobalt": 500}, capacity=4000)
        self.assertIsNone(storage.consolidate_warehouse_strays([self.remote]))

    def test_skips_recently_busy_source(self):
        self.world.add_warehouse("wh_main", self.remote, {"iron_ore": 1500, "silicon": 1000}, capacity=4000)
        self.world.add_warehouse("wh_side", self.remote, {"iron_ore": 50, "cobalt": 500}, capacity=4000)
        storage.mark_busy("wh_side")
        self.assertIsNone(storage.consolidate_warehouse_strays([self.remote]))


class RebalanceRoutingTests(StubTestCase):
    def test_inventory_overflow_joins_existing_holder(self):
        home = self.world.home
        self.world.add_warehouse("wh_empty", home, {}, capacity=10000)
        self.world.add_warehouse("wh_holder", home, {"glass": 500, "iron_ore": 3000}, capacity=10000)
        self.world.inventory.items["glass"] = 40
        storage.rebalance_inventory_to_warehouses()
        self.assertEqual(self.world.components["wh_holder"].count("glass"), 540)
        self.assertEqual(self.world.components["wh_empty"].count("glass"), 0)
        self.assertEqual(self.world.inventory.count("glass"), 0)


if __name__ == "__main__":
    unittest.main()
