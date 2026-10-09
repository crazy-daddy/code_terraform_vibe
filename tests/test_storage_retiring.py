"""Retiring stores (storage.RETIRING_STORES_KEY): a store a building swap is
emptying gets no deliveries, but stays a source; the Warehouse swap marks its
old Warehouses while deploying/draining and releases them otherwise."""
import unittest

from harness import StubTestCase, storage
from game_stubs import Commander, Shop
import building_swap_upgrade
import cash
import drone_upgrade
import warehouse_upgrade


class RetiringFilterTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.remote = self.world.add_outpost("outpost_2")

    def test_unload_skips_retiring_holder(self):
        self.world.add_warehouse("wh_old", self.remote, {"iron_ore": 50})
        self.world.add_warehouse("wh_new", self.remote)
        self.assertEqual(storage.best_unload_target("iron_ore", 1, outpost=self.remote), "wh_old")
        storage.set_retiring_stores("test", ["wh_old"])
        self.assertEqual(storage.best_unload_target("iron_ore", 1, outpost=self.remote), "wh_new")

    def test_only_retiring_store_gives_no_target(self):
        self.world.add_warehouse("wh_old", self.remote)
        storage.set_retiring_stores("test", ["wh_old"])
        self.assertIsNone(storage.best_unload_target("iron_ore", 1, outpost=self.remote))

    def test_retiring_store_still_counts_as_stock(self):
        self.world.add_warehouse("wh_old", self.remote, {"iron_ore": 50})
        storage.set_retiring_stores("test", ["wh_old"])
        self.assertEqual(storage.total_stock("iron_ore", self.remote), 50)

    def test_top_up_skips_retiring_bin(self):
        self.world.add_storage_bin("storage_bin_1", self.remote, "silicon", 450)
        self.assertEqual(storage.top_up_target("silicon", 100, self.remote), ("storage_bin_1", 50))
        storage.set_retiring_stores("test", ["storage_bin_1"])
        self.assertEqual(storage.top_up_target("silicon", 100, self.remote), (None, 0))

    def test_consolidation_skips_retiring_target(self):
        self.world.add_storage_bin("storage_bin_small", self.remote, "silicon", 2)
        self.world.add_storage_bin("storage_bin_big", self.remote, "silicon", 400)
        storage.set_retiring_stores("test", ["storage_bin_big"])
        self.assertIsNone(storage.consolidate_storage_bins([self.remote]))

    def test_port_rests_on_a_staying_warehouse(self):
        self.world.add_warehouse("wh_a", self.remote)
        self.world.add_warehouse("wh_b", self.remote)
        storage.set_retiring_stores("test", ["wh_a"])
        self.assertEqual(storage.local_port_target(self.remote), "wh_b")

    def test_owner_set_replaces_only_its_own_entries(self):
        storage.set_retiring_stores("a", ["wh_1", "wh_2"])
        storage.set_retiring_stores("b", ["wh_3"])
        storage.set_retiring_stores("a", ["wh_2"])
        self.assertEqual(sorted(storage.retiring_store_ids()), ["wh_2", "wh_3"])
        storage.set_retiring_stores("a", [])
        self.assertEqual(storage.retiring_store_ids(), ("wh_3",))


class UnlockedResearch:
    def is_unlocked(self, research_id):
        return True


class SwapMarksRetiringTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        self.outpost = w.add_outpost("outpost_2")
        prices = {"warehouse": 5000, "large_warehouse": 60000}
        w.services.update({"shop": Shop(w, prices), "commander": Commander(cash.LEGACY_RESERVE * 10), "research": UnlockedResearch()})
        drone_upgrade.update_fleet_upgrade(lambda s: s.update({"phase_reached": True}))
        w.add_warehouse("warehouse_1", self.outpost, items={"iron_ore": 30})
        w.add_warehouse("warehouse_2", self.outpost)
        self.upgrader = warehouse_upgrade.WarehouseUpgrader()

    def test_marked_only_while_deploying_or_draining(self):
        self.upgrader.step()  # picks the pair: buying
        self.assertEqual(storage.retiring_store_ids(), ())
        for state in building_swap_upgrade.RETIRING_STATES:
            self.upgrader._patch(state=state, removed=["warehouse_2"])
            self.upgrader._sync_retiring(self.upgrader._swap())
            self.assertEqual(storage.retiring_store_ids(), ("warehouse_1",), state)
        self.upgrader._patch(state="blocked")
        self.upgrader._sync_retiring(self.upgrader._swap())
        self.assertEqual(storage.retiring_store_ids(), ())

    def test_released_after_the_swap(self):
        self.upgrader.step()
        self.assertIn("done", self.upgrader.step(), self.debug_log())
        self.upgrader.step()
        self.assertEqual(storage.retiring_store_ids(), ())
        large = [c for c in self.world.components.values() if getattr(c, "type_id", "") == "large_warehouse"]
        self.assertEqual(large[0].items, {"iron_ore": 30})


if __name__ == "__main__":
    unittest.main()
