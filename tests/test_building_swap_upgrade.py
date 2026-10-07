"""Stub tests for the shared swap state machine (lib/building_swap_upgrade.py)
through its users: Warehouse pair -> Large Warehouse and four Storage Bins ->
Warehouse (lib/warehouse_upgrade.py), and Liquid Tanks -> Large Liquid Tank (lib/tank_upgrade.py)."""
import unittest

from harness import StubTestCase
from game_stubs import Commander, Shop
import building_swap_upgrade
import drone_upgrade
import fluid_routing
import cash
import tank_upgrade
import warehouse_upgrade


class UnlockedResearch:
    """`research` with every project unlocked."""

    def is_unlocked(self, research_id):
        return True


class SwapTestCase(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        self.outpost = w.add_outpost("outpost_2")
        prices = {"storage_bin": 120, "warehouse": 5000, "large_warehouse": 60000, "liquid_tank": 1000, "bulk_liquid_reservoir": 15000}
        w.services.update({"shop": Shop(w, prices), "commander": Commander(cash.LEGACY_RESERVE * 10), "research": UnlockedResearch()})
        drone_upgrade.update_fleet_upgrade(lambda s: s.update({"phase_reached": True}))

    def swap(self, upgrader):
        return drone_upgrade.fleet_upgrade_state().get(upgrader.SWAP_KEY)

    def active(self, upgrader) -> dict:
        found = self.swap(upgrader)
        assert found is not None, f"no swap: {self.debug_log()}"
        return found


class BinSwapTests(SwapTestCase):
    def new_warehouses(self):
        return [c for c in self.world.components.values() if getattr(c, "type_id", "") == "warehouse"]

    def bins_left(self):
        return sorted(i for i in self.world.components if i.startswith("storage_bin_"))

    def test_same_material_bins_share_one_slot(self):
        w = self.world
        for n in range(1, 5):
            w.add_storage_bin(f"storage_bin_{n}", self.outpost, "iron_ore", 100 * n)
        w.add_storage_bin("storage_bin_5", self.outpost, "silicon", 40)
        w.add_storage_bin("storage_bin_6", self.outpost)  # empty: stays
        upgrader = warehouse_upgrade.BinUpgrader()
        upgrader.step()
        self.assertEqual(self.active(upgrader)["old_ids"], ["storage_bin_1", "storage_bin_2", "storage_bin_3", "storage_bin_4", "storage_bin_5"], self.debug_log())
        status = upgrader.step()  # buy -> deploy -> drain, back to back
        self.assertIn("done", status, self.debug_log())
        self.assertIsNone(self.swap(upgrader))
        new = self.new_warehouses()
        self.assertEqual(len(new), 1)
        self.assertEqual(new[0].items, {"iron_ore": 1000, "silicon": 40})
        self.assertEqual(self.bins_left(), ["storage_bin_6"])
        self.assertEqual(w.services["shop"].sold, {"storage_bin": 5})

    def test_material_past_one_slot_opens_a_second(self):
        w = self.world
        for n in range(1, 7):
            w.add_storage_bin(f"storage_bin_{n}", self.outpost, "iron_ore", 450)
        upgrader = warehouse_upgrade.BinUpgrader()
        self.assertEqual(upgrader._bin_plan(self.outpost), [f"storage_bin_{n}" for n in range(1, 7)])

    def test_quarter_full_bins_fill_one_slot(self):
        w = self.world
        for n in range(1, 9):
            w.add_storage_bin(f"storage_bin_{n}", self.outpost, "iron_ore", 250)
        for n, item in enumerate(["cobalt", "lead_ore", "silicon", "titanium", "rare_earth"], 9):
            w.add_storage_bin(f"storage_bin_{n}", self.outpost, item, 100)
        upgrader = warehouse_upgrade.BinUpgrader()
        plan = upgrader._bin_plan(self.outpost)
        # 8 iron bins = 2000 units = one slot; 4 slots left for 5 single bins
        self.assertEqual(len(plan), 12, plan)
        self.assertTrue(all(f"storage_bin_{n}" in plan for n in range(1, 9)), plan)

    def test_drain_follows_storage_routing(self):
        w = self.world
        w.add_warehouse("warehouse_old", self.outpost, items={"iron_ore": 10}, capacity=20000)
        for n in range(1, 5):
            w.add_storage_bin(f"storage_bin_{n}", self.outpost, "iron_ore", 50)
        upgrader = warehouse_upgrade.BinUpgrader()
        upgrader.step()
        self.assertIn("done", upgrader.step(), self.debug_log())
        self.assertEqual(w.components["warehouse_old"].items, {"iron_ore": 210})  # existing stack first
        self.assertEqual(self.bins_left(), [])

    def test_starts_before_mining_drills(self):
        w = self.world
        drone_upgrade.update_fleet_upgrade(lambda s: s.update({"phase_reached": False}))
        for n in range(1, 5):
            w.add_storage_bin(f"storage_bin_{n}", self.outpost, "iron_ore", 10)
        upgrader = warehouse_upgrade.BinUpgrader()
        upgrader.step()
        self.assertIsNotNone(self.swap(upgrader), self.debug_log())
        self.assertEqual(warehouse_upgrade.WarehouseUpgrader().step(), "waiting for mining drills")

    def test_three_bins_are_kept(self):
        w = self.world
        for n in range(1, 4):
            w.add_storage_bin(f"storage_bin_{n}", self.outpost, "iron_ore", 10)
        w.add_storage_bin("storage_bin_4", self.outpost)  # empty bins don't count
        upgrader = warehouse_upgrade.BinUpgrader()
        self.assertEqual(upgrader.step(), "storage bins up to date")
        self.assertIsNone(self.swap(upgrader))


class WarehouseSwapTests(SwapTestCase):
    def test_buys_deploys_drains_and_sells(self):
        w = self.world
        w.add_warehouse("warehouse_1", self.outpost, items={"iron_ore": 30})
        w.add_warehouse("warehouse_2", self.outpost, items={"copper_ore": 10})
        upgrader = warehouse_upgrade.WarehouseUpgrader()
        upgrader.step()  # picks the pair
        self.assertEqual(self.active(upgrader)["old_ids"], ["warehouse_2", "warehouse_1"], self.debug_log())
        status = upgrader.step()  # buy -> deploy -> drain, back to back
        self.assertIn("done", status, self.debug_log())
        self.assertIsNone(self.swap(upgrader))
        large = [c for c in w.components.values() if getattr(c, "type_id", "") == "large_warehouse"]
        self.assertEqual(len(large), 1)
        self.assertEqual(large[0].items, {"iron_ore": 30, "copper_ore": 10})
        self.assertNotIn("warehouse_1", w.components)
        self.assertEqual(w.services["shop"].sold, {"warehouse": 2})

    def test_fatal_deploy_blocks_swap(self):
        w = self.world
        w.add_warehouse("warehouse_1", self.outpost)
        w.add_warehouse("warehouse_2", self.outpost)
        w.computer.forced_status = "deploy_limit"
        upgrader = warehouse_upgrade.WarehouseUpgrader()
        upgrader.step()
        status = upgrader.step()
        self.assertIn("blocked", status, self.debug_log())
        self.assertEqual(self.active(upgrader)["reason"], "deploy_limit")
        self.assertIn("blocked (deploy_limit)", upgrader.step())

    def test_repeated_undeploy_refusal_blocks_after_max_attempts(self):
        w = self.world
        w.add_warehouse("warehouse_1", self.outpost)
        w.add_warehouse("warehouse_2", self.outpost)
        upgrader = warehouse_upgrade.WarehouseUpgrader()
        upgrader.step()
        w.inventory.add("large_warehouse", 1)
        upgrader._patch(state="deploying", known=[])
        upgrader._advance_once(self.active(upgrader))  # deploy only
        w.computer.forced_status = "busy"
        for _ in range(building_swap_upgrade.MAX_ATTEMPTS):
            upgrader.step()
        self.assertEqual(self.active(upgrader)["state"], "blocked", self.debug_log())

    def test_transient_block_resumes_drain(self):
        w = self.world
        w.add_warehouse("warehouse_1", self.outpost)
        w.add_warehouse("warehouse_2", self.outpost)
        upgrader = warehouse_upgrade.WarehouseUpgrader()
        upgrader.step()
        upgrader.step()  # whole swap done
        self.assertIsNone(self.swap(upgrader))
        upgrader._begin("outpost_2", ["gone_1"], state="blocked", reason="inventory_full", new_id="large_warehouse_1")
        self.assertIn("done", upgrader.step(), self.debug_log())


class TankSwapTests(SwapTestCase):
    def test_retires_tanks_and_removes_them_once_empty(self):
        w = self.world
        for n in (1, 2, 3):
            w.add_tank(f"liquid_tank_{n}", self.outpost, fluid="water", level=10.0 * n)
        upgrader = tank_upgrade.TankUpgrader()
        upgrader.step()
        swap = self.active(upgrader)
        self.assertEqual((swap["liquid"], swap["old_ids"]), ("water", ["liquid_tank_1", "liquid_tank_2", "liquid_tank_3"]), self.debug_log())
        upgrader.step()  # buy -> deploy -> first drain check
        swap = self.active(upgrader)
        self.assertEqual(swap["state"], "draining", self.debug_log())
        new_id = swap["new_id"]
        assignments = fluid_routing.get_tank_assignments()
        self.assertEqual(assignments[new_id], "water")
        self.assertEqual(assignments["liquid_tank_1"], fluid_routing.RETIRING_ASSIGNMENT)
        self.assertEqual(w.components[new_id].liquid_in.connected_id(), "liquid_tank_1")
        for n in (1, 2, 3):
            w.components[f"liquid_tank_{n}"]._level = 0.0
        for _ in range(4):
            upgrader.step()
        self.assertIsNone(self.swap(upgrader), self.debug_log())
        self.assertNotIn("liquid_tank_2", w.components)
        self.assertEqual(w.services["shop"].sold, {"liquid_tank": 3})
        self.assertNotIn("liquid_tank_1", fluid_routing.get_tank_assignments())


if __name__ == "__main__":
    unittest.main()
