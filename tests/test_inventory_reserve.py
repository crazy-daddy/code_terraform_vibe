"""Automated moves into home Inventory keep storage.INVENTORY_FREE_SLOTS_KEEP
slots empty (storage.inventory_room())."""

import unittest

import drone_upgrade
import storage_sweeps
import storage_unload
from game_stubs import Recipe
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

    def test_non_stackable_item_reserves_one_unit_per_slot(self):
        # A construction kit takes one slot per unit: space_for() == empty slots.
        self.inventory.space_for = lambda item_id, properties=None: (
            self.inventory.get_size() - self.inventory.get_used()
        )
        self.assertEqual(storage.inventory_room("drone_station_kit"), 0)  # 4 empty slots, all reserved
        self.inventory.items = {"iron_ore": 25}  # 3 slots used, 7 empty
        self.assertEqual(storage.inventory_room("drone_station_kit"), 3)

    def test_no_inventory_fallback_into_reserve(self):
        self.assertIsNone(storage_unload.best_unload_target("silicon", 10, outpost=self.world.home))
        self.assertEqual(storage_unload.best_unload_target("iron_ore", 5, outpost=self.world.home), "inventory")

    def test_inventory_only_item_goes_to_warehouse_when_reserve_reached(self):
        self.world.add_warehouse("warehouse_1", self.world.home)
        self.inventory.items = {"iron_ore": 60}
        self.assertEqual(storage_unload.best_unload_target("drone_small", 1, outpost=self.world.home), "warehouse_1")


class FleetPartKeepTests(StubTestCase):
    """Home Inventory holds a fleet part only up to storage.FLEET_PART_KEEP;
    the surplus waits in a Warehouse."""

    def setUp(self):
        super().setUp()
        self.inventory = self.world.inventory
        self.inventory.capacity_units = 600
        self.warehouse = self.world.add_warehouse("warehouse_1", self.world.home)

    def test_keep_covers_largest_loadout(self):
        for loadouts in drone_upgrade.FIT_LOADOUTS.values():
            for modules in loadouts.values():
                for category in set(modules):
                    self.assertLessEqual(modules.count(category), storage.FLEET_MODULE_KEEP)

    def test_part_at_keep_unloads_to_warehouse(self):
        self.assertEqual(storage_unload.best_unload_target("drone_large", 1, outpost=self.world.home), "inventory")
        self.inventory.items = {"drone_large": 1}
        self.assertEqual(storage_unload.best_unload_target("drone_large", 1, outpost=self.world.home), "warehouse_1")

    def test_park_moves_surplus_and_reclaim_tops_up(self):
        self.inventory.items = {"cargo_pod_large": 7, "drone_medium": 2, "iron_ore": 5}
        self.assertEqual(storage_sweeps.park_surplus_fleet_parts(), 4)
        self.assertEqual(
            self.inventory.items, {"cargo_pod_large": storage.FLEET_MODULE_KEEP, "drone_medium": 1, "iron_ore": 5}
        )
        self.assertEqual(self.warehouse.items, {"cargo_pod_large": 3, "drone_medium": 1})
        self.inventory.items = {"cargo_pod_large": 1, "drone_medium": 1, "iron_ore": 5}
        storage_sweeps.reclaim_inventory_only_items_from_warehouses()
        self.assertEqual(self.inventory.items["cargo_pod_large"], 4)
        self.assertEqual(self.inventory.items["drone_medium"], 1)
        self.assertEqual(self.warehouse.items, {"drone_medium": 1})

    def test_tier_below_best_craftable_keeps_none(self):
        self.world.add_fabricator(
            "fabricator_1",
            self.world.home,
            [
                Recipe(f"craft_{item}", {"iron_ingot": 1}, item)
                for item in ("drone_medium", "drone_large", "cargo_pod_medium")
            ],
        )
        self.assertEqual(storage.fleet_part_keep("drone_medium"), 0)
        self.assertEqual(storage.fleet_part_keep("drone_large"), 1)
        self.assertEqual(storage.fleet_part_keep("cargo_pod_small"), 0)
        self.assertEqual(storage.fleet_part_keep("cargo_pod_large"), storage.FLEET_MODULE_KEEP)  # no tier above it
        self.assertEqual(storage.fleet_part_keep("battery_pack"), storage.FLEET_MODULE_KEEP)
        self.inventory.items = {"drone_medium": 1, "drone_large": 1, "iron_ore": 5}
        self.assertEqual(storage_sweeps.park_surplus_fleet_parts(), 1)
        self.assertEqual(self.inventory.items, {"drone_large": 1, "iron_ore": 5})
        self.assertEqual(self.warehouse.items, {"drone_medium": 1})
        storage_sweeps.reclaim_inventory_only_items_from_warehouses()
        self.assertEqual(self.warehouse.items, {"drone_medium": 1})


if __name__ == "__main__":
    unittest.main()
