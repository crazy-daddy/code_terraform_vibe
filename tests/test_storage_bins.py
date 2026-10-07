"""Storage Bins join Warehouse routing through storage.BinStore: one
material-locked slot, room only while empty or latched to the item."""
import unittest

from harness import StubTestCase, storage
import drone_depot


class StorageBinTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.remote = self.world.add_outpost("outpost_2")

    def test_remote_outpost_with_only_bins_gets_a_target(self):
        self.world.add_storage_bin("storage_bin_1", self.remote)
        self.assertEqual(storage.best_unload_target("iron_ore", 7, outpost=self.remote), "storage_bin_1")

    def test_bin_latched_to_other_item_has_no_room(self):
        self.world.add_storage_bin("storage_bin_1", self.remote, "silicon", 10)
        self.assertIsNone(storage.best_unload_target("iron_ore", 1, outpost=self.remote))

    def test_latched_bin_beats_empty_bin(self):
        self.world.add_storage_bin("storage_bin_empty", self.remote)
        self.world.add_storage_bin("storage_bin_iron", self.remote, "iron_ore", 100)
        self.assertEqual(storage.best_unload_target("iron_ore", 50, outpost=self.remote), "storage_bin_iron")

    def test_bin_without_room_for_min_amount_is_skipped(self):
        self.world.add_storage_bin("storage_bin_iron", self.remote, "iron_ore", 480)
        self.world.add_storage_bin("storage_bin_empty", self.remote)
        self.assertEqual(storage.best_unload_target("iron_ore", 50, outpost=self.remote), "storage_bin_empty")

    def test_clashing_warehouse_beats_opening_a_bin(self):
        self.world.add_warehouse("wh_mixed", self.remote, {"iron_ore": 50, "iron_ingot": 50})
        self.world.add_storage_bin("storage_bin_empty", self.remote)
        self.assertEqual(storage.best_unload_target("iron_ore", 1, outpost=self.remote), "wh_mixed")

    def test_new_warehouse_stack_beats_opening_a_bin(self):
        self.world.add_warehouse("wh_other", self.remote, {"seeds": 500})
        self.world.add_storage_bin("storage_bin_empty", self.remote)
        self.assertEqual(storage.best_unload_target("iron_ore", 1, outpost=self.remote), "wh_other")

    def test_latched_bin_beats_clashing_warehouse(self):
        self.world.add_warehouse("wh_mixed", self.remote, {"iron_ore": 50, "iron_ingot": 50})
        self.world.add_storage_bin("storage_bin_iron", self.remote, "iron_ore", 100)
        self.assertEqual(storage.best_unload_target("iron_ore", 1, outpost=self.remote), "storage_bin_iron")

    def test_busy_retry_never_opens_an_empty_bin(self):
        self.world.add_storage_bin("storage_bin_iron", self.remote, "iron_ore", 100)
        self.world.add_storage_bin("storage_bin_empty", self.remote)
        self.assertIsNone(storage.best_unload_target("iron_ore", 1, outpost=self.remote, exclude=["storage_bin_iron"]))

    def test_send_into_bin_moves_cargo(self):
        self.world.add_storage_bin("storage_bin_1", self.remote)
        fabricator = self.world.add_fabricator("fabricator_1", self.remote)
        fabricator.output_buffer["iron_ore"] = 7
        target = storage.best_unload_target("iron_ore", 7, outpost=self.remote)
        moved, status, _message = storage.send_stack(fabricator.output, "iron_ore", 7, target)
        self.assertEqual((moved, status), (7, "ok"))
        self.assertEqual(self.world.components["storage_bin_1"].get_material(), "iron_ore")

    def test_stock_reads_include_bins(self):
        self.world.add_storage_bin("storage_bin_1", self.remote, "iron_ore", 40)
        self.world.add_warehouse("wh_1", self.remote, {"iron_ore": 2})
        self.assertEqual(storage.warehouse_stock("iron_ore", outpost=self.remote), 42)
        self.assertEqual(storage.warehouse_stocks(["iron_ore"], outpost=self.remote), {"iron_ore": 42})

    def test_bin_store_slots_and_capacity(self):
        self.world.add_storage_bin("storage_bin_1", self.remote, "iron_ore", 40)
        self.world.add_storage_bin("storage_bin_2", self.remote)
        views = {b["id"]: b["component"] for b in storage.discover_storage_buildings(self.remote)}
        full, empty = views["storage_bin_1"], views["storage_bin_2"]
        self.assertEqual([(s.item, s.count, s.capacity) for s in full.slots()], [("iron_ore", 40, 500)])
        self.assertEqual([(s.item, s.count) for s in empty.slots()], [("", 0)])
        self.assertEqual((full.total(), full.capacity(), full.materials()), (40, 500, ["iron_ore"]))
        self.assertEqual(empty.materials(), [])

    def test_drone_buffer_keeps_empty_bin_free(self):
        self.world.add_storage_bin("storage_bin_1", self.remote)
        self.assertEqual(drone_depot.buffer_target("bio_sample", self.remote), (None, 0))


if __name__ == "__main__":
    unittest.main()
