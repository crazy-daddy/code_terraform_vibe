"""Stub tests for the shared swap state machine (lib/building_swap_upgrade.py)
through its two users: Warehouse pair -> Large Warehouse (lib/warehouse_upgrade.py)
and Liquid Tanks -> Large Liquid Tank (lib/tank_upgrade.py)."""
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
        prices = {"warehouse": 5000, "large_warehouse": 60000, "liquid_tank": 1000, "bulk_liquid_reservoir": 15000}
        w.services.update({"shop": Shop(w, prices), "commander": Commander(cash.LEGACY_RESERVE * 10), "research": UnlockedResearch()})
        drone_upgrade.update_fleet_upgrade(lambda s: s.update({"phase_reached": True}))

    def swap(self, upgrader):
        return drone_upgrade.fleet_upgrade_state().get(upgrader.SWAP_KEY)

    def active(self, upgrader) -> dict:
        found = self.swap(upgrader)
        assert found is not None, f"no swap: {self.debug_log()}"
        return found


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
