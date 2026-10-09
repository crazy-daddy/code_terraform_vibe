"""Automated moves into home Inventory keep storage.INVENTORY_FREE_SLOTS_KEEP
slots empty (storage.inventory_room())."""
import unittest

from harness import StubTestCase, storage


class InventoryReserveTests(StubTestCase):
    def setUp(self):
        super().setUp()
        # 10 slots of 10 units; 55 iron_ore uses 6 (one partial with 5 room).
        self.inventory = self.world.inventory
        self.inventory.capacity_units = 100
        self.inventory.items = {"iron_ore": 55}

    def test_room_leaves_reserve_slots_empty(self):
        self.assertEqual(storage.INVENTORY_FREE_SLOTS_KEEP, 4)
        self.assertEqual(storage.inventory_room("iron_ore"), 5)
        self.assertEqual(storage.inventory_room("iron_ore", keep=0), 45)

    def test_partial_stack_room_stays_usable_below_reserve(self):
        self.inventory.items = {"iron_ore": 75}  # 8 slots used, 2 empty, 5 partial room
        self.assertEqual(storage.inventory_room("iron_ore"), 5)

    def test_no_inventory_fallback_into_reserve(self):
        self.assertIsNone(storage.best_unload_target("silicon", 10, outpost=self.world.home))
        self.assertEqual(storage.best_unload_target("iron_ore", 5, outpost=self.world.home), "inventory")

    def test_inventory_only_item_goes_to_warehouse_when_reserve_reached(self):
        self.world.add_warehouse("warehouse_1", self.world.home)
        self.inventory.items = {"iron_ore": 60}
        self.assertEqual(storage.best_unload_target("drone_small", 1, outpost=self.world.home), "warehouse_1")


if __name__ == "__main__":
    unittest.main()
