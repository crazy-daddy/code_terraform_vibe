"""Stub tests for storage outpost expansion (lib/storage_expand.py)."""

import unittest
from unittest import mock

import cash
import drone_upgrade
import storage_expand
import warehouse_upgrade
from game_stubs import Commander, Shop
from harness import StubTestCase


class UnlockedResearch:
    """`research` with every project unlocked."""

    def is_unlocked(self, research_id):
        return True


class StorageExpandTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        self.store = w.add_outpost("outpost_9")
        self.warehouse = w.add_warehouse("wh_9", self.store, {"tar": 2000}, capacity=4000)  # 2 slots, 1 empty
        w.add_drone_depot("depot_9", self.store)
        self.shop = Shop(w, {"warehouse": 3000, "large_warehouse": 60000})
        w.services.update(
            {"shop": self.shop, "commander": Commander(cash.LEGACY_RESERVE * 10), "research": UnlockedResearch()}
        )
        self.expander = storage_expand.StorageExpander()

    def large_warehouses(self):
        return sorted(i for i, c in self.world.components.items() if getattr(c, "type_id", "") == "large_warehouse")

    def test_low_storage_outpost_gets_a_large_warehouse(self):
        summary = self.expander.step()
        self.assertIn("deployed Large Warehouse", summary, self.debug_log())
        self.assertEqual(len(self.large_warehouses()), 1)
        self.assertEqual(self.world.inventory.count("large_warehouse"), 0)
        self.assertTrue(self.expander.warning.active)
        self.assertEqual(self.expander.step(), storage_expand.IDLE_SUMMARY)
        self.assertFalse(self.expander.warning.active)

    def test_enough_empty_slots_buys_nothing(self):
        self.warehouse.capacity_units = 6000  # 3 slots, 2 empty
        self.assertEqual(self.expander.step(), storage_expand.IDLE_SUMMARY)
        self.assertEqual(self.large_warehouses(), [])

    def test_outpost_with_a_penalized_building_is_no_storage_outpost(self):
        self.world.add_smelter("smelter_9", self.store)
        self.assertEqual(self.expander.step(), storage_expand.IDLE_SUMMARY)
        self.assertEqual(self.large_warehouses(), [])

    def test_cash_manager_holds_back_the_buy(self):
        self.world.services["commander"].credits = 100
        self.assertIn("saving up", self.expander.step())
        self.assertEqual(self.large_warehouses(), [])

    def test_kit_of_a_running_swap_is_not_taken(self):
        self.world.inventory.add("large_warehouse", 1)
        swap_key = warehouse_upgrade.WarehouseUpgrader.SWAP_KEY
        drone_upgrade.update_fleet_upgrade(lambda s: s.update({swap_key: {"state": "deploying"}}))
        self.assertIn("deployed", self.expander.step(), self.debug_log())
        self.assertEqual(self.world.inventory.count("large_warehouse"), 1)  # bought its own

    def test_kit_in_inventory_is_deployed_without_a_buy(self):
        self.world.inventory.add("large_warehouse", 1)
        credits = self.world.services["commander"].credits
        self.assertIn("deployed", self.expander.step())
        self.assertEqual(self.world.services["commander"].credits, credits)

    def test_deploy_that_raises_settles_the_outpost_without_a_warn_line(self):
        w = self.world
        w.inventory.add("large_warehouse", 1)
        with mock.patch.object(w.computer, "deploy", side_effect=RuntimeError("boom")) as deploy:
            summary = self.expander.step()
        deploy.assert_called_once()
        self.assertIn("deploy error", summary)
        self.assertIn("outpost_9", self.expander.settled)
        self.assertEqual(w.inventory.count("large_warehouse"), 1)
        self.debug_log()  # flush the console
        self.assertEqual([m for level, m in w.console.lines if level == "warn" and "refused" in m], [])

    def test_outpost_waits_after_a_deploy(self):
        self.expander.step()
        self.world.add_warehouse("wh_9b", self.store, {"silicon": 2000}, capacity=2000)
        for component_id in self.large_warehouses():
            self.world.components[component_id].items = {"glass": 30000}
        storage_expand.forget_storage_discovery()
        self.assertIn("settling", self.expander.step(), self.debug_log())


if __name__ == "__main__":
    unittest.main()
