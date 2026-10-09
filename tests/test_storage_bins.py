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

    def test_fullest_latched_bin_first(self):
        self.world.add_storage_bin("storage_bin_low", self.remote, "glass", 100)
        self.world.add_storage_bin("storage_bin_high", self.remote, "glass", 300)
        self.assertEqual(storage.best_unload_target("glass", 10, outpost=self.remote), "storage_bin_high")

    def test_drain_tops_up_holder_before_opening_a_bin(self):
        self.world.add_storage_bin("storage_bin_iron", self.remote, "iron_ore", 480)
        self.world.add_storage_bin("storage_bin_empty", self.remote)
        fabricator = self.world.add_fabricator("fabricator_1", self.remote)
        fabricator.output_buffer["iron_ore"] = 50
        self.assertEqual(storage.drain_port_to_storage(fabricator.output, outpost=self.remote), 50)
        self.assertEqual(self.world.components["storage_bin_iron"].count("iron_ore"), 500)
        self.assertEqual(self.world.components["storage_bin_empty"].count("iron_ore"), 30)

    def test_no_top_up_when_a_holder_takes_the_whole_stack(self):
        self.world.add_storage_bin("storage_bin_full", self.remote, "iron_ore", 490)
        self.world.add_storage_bin("storage_bin_iron", self.remote, "iron_ore", 100)
        self.assertEqual(storage.top_up_target("iron_ore", 50, outpost=self.remote), (None, 0))

    def test_top_up_picks_fullest_bin_with_room(self):
        self.world.add_storage_bin("storage_bin_a", self.remote, "iron_ore", 470)
        self.world.add_storage_bin("storage_bin_b", self.remote, "iron_ore", 490)
        self.assertEqual(storage.top_up_target("iron_ore", 50, outpost=self.remote), ("storage_bin_b", 10))

    def test_consolidate_moves_small_bin_into_fullest(self):
        self.world.add_storage_bin("storage_bin_small", self.remote, "titanium_ingot", 2)
        self.world.add_storage_bin("storage_bin_mid", self.remote, "titanium_ingot", 300)
        self.world.add_storage_bin("storage_bin_big", self.remote, "titanium_ingot", 450)
        self.assertEqual(storage.consolidate_storage_bins([self.remote]), ("storage_bin_small", "storage_bin_big", "titanium_ingot", 2))
        self.assertEqual(self.world.components["storage_bin_small"].get_material(), "")
        self.assertEqual(self.world.components["storage_bin_big"].count("titanium_ingot"), 452)

    def test_consolidate_moves_one_chunk_per_call(self):
        self.world.add_storage_bin("storage_bin_small", self.remote, "silicon", 50)
        self.world.add_storage_bin("storage_bin_big", self.remote, "silicon", 400)
        result = storage.consolidate_storage_bins([self.remote])
        self.assertEqual(result, ("storage_bin_small", "storage_bin_big", "silicon", storage.BIN_CONSOLIDATE_CHUNK))
        self.assertEqual(self.world.components["storage_bin_small"].count("silicon"), 50 - storage.BIN_CONSOLIDATE_CHUNK)

    def test_consolidate_skips_stack_that_does_not_fit_whole(self):
        self.world.add_storage_bin("storage_bin_a", self.remote, "glass", 252)
        self.world.add_storage_bin("storage_bin_b", self.remote, "glass", 252)
        self.world.add_storage_bin("storage_bin_c", self.remote, "titanium", 101)
        self.world.add_storage_bin("storage_bin_d", self.remote, "titanium", 456)
        self.assertIsNone(storage.consolidate_storage_bins([self.remote]))

    def test_consolidate_skips_large_stacks(self):
        self.world.add_storage_bin("storage_bin_a", self.remote, "silicon", storage.BIN_CONSOLIDATE_MAX_UNITS + 1, capacity=2000)
        self.world.add_storage_bin("storage_bin_b", self.remote, "silicon", 300, capacity=2000)
        self.assertIsNone(storage.consolidate_storage_bins([self.remote]))

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



class SlotRoomTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.remote = self.world.add_outpost("outpost_2")

    def test_layout_reads_warehouse_slots_and_bins(self):
        self.world.add_warehouse("wh_1", self.remote, {"iron_ore": 2500}, capacity=6000)
        self.world.add_storage_bin("storage_bin_1", self.remote, "glass", 40)
        self.assertEqual(sorted(storage.slot_layout(self.remote)), [("", 0, 2000), ("glass", 40, 500), ("iron_ore", 500, 2000), ("iron_ore", 2000, 2000)])

    def test_fills_held_slots_or_the_planned_ones(self):
        layout = [("iron_ore", 500, 2000), ("", 0, 2000), ("", 0, 2000)]
        self.assertEqual(storage.slot_room("iron_ore", layout), 1500)
        # A 1800 target may fill its whole slot, a 2100 one a second slot.
        self.assertEqual(storage.slot_room("glass", layout, planned=1800), 2000)
        self.assertEqual(storage.slot_room("iron_ore", layout, planned=2100), 3500)

    def test_unplanned_item_gets_one_empty_slot_while_enough_stay_free(self):
        layout = [("iron_ore", 500, 2000), ("", 0, 2000)]
        self.assertEqual(storage.slot_room("glass", layout), 2000)
        self.assertEqual(storage.slot_room("glass", layout, keep_free=1), 0)
        self.assertEqual(storage.slot_room("glass", []), 0)



class InventoryRebalanceTests(StubTestCase):
    def test_no_warehouse_at_home_stays_quiet(self):
        self.world.inventory.add("gas_pipe_segment", 100)
        storage.rebalance_inventory_to_warehouses()
        self.assertNotIn("Could not clear", self.world.console.text("warn"))

if __name__ == "__main__":
    unittest.main()
