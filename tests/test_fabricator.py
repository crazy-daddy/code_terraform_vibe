"""Stub tests for lib/fabricator.py FabricatorController, at home and at a remote outpost."""
import unittest

from harness import StubTestCase, fabricator, production


def run_steps(controller, n):
    for _ in range(n):
        controller.step()


class HomeFabricatorTests(StubTestCase):
    def test_sets_recipe_and_loads_from_inventory(self):
        w = self.world
        w.inventory.add("iron_ingot", 50)
        f = w.add_fabricator("fabricator_1", w.home)
        run_steps(fabricator.FabricatorController(f), 2)
        self.assertEqual(f.recipe, "craft_gas_pipe_segment")
        self.assertEqual(f.input_buffer.get("iron_ingot"), 10)
        self.assertEqual(f.input.connect_log[0], "inventory")

    def test_drain_output_consumes_manual_order(self):
        w = self.world
        f = w.add_fabricator("fabricator_1", w.home)
        w.notebook.set(production.MANUAL_ORDERS_KEY, {"steel_plate": 5})
        f.output_buffer["steel_plate"] = 2
        fabricator.FabricatorController(f).drain_output()
        self.assertEqual(w.inventory.count("steel_plate"), 2)
        self.assertEqual(production.get_manual_orders(), {"steel_plate": 3})

    def test_eject_excess_to_home_storage(self):
        w = self.world
        f = w.add_fabricator("fabricator_1", w.home)
        f.input_buffer["glass"] = 4  # no recipe set: all of it is excess
        fabricator.FabricatorController(f).eject_excess_inputs(None, 0)
        self.assertEqual(w.inventory.count("glass"), 4)


class ClaimRefreshTests(StubTestCase):
    def test_fresh_own_claim_skips_archive_transaction(self):
        w = self.world
        f = w.add_fabricator("fabricator_1", w.home)
        controller = fabricator.FabricatorController(f)
        ticks = [1000]
        controller.get_current_tick = lambda: ticks[0]
        calls = []
        real = fabricator.archive.transaction
        fabricator.archive.transaction = lambda *a, **k: (calls.append(1), real(*a, **k))[1]
        try:
            self.assertTrue(controller.claim_recipe("craft_gas_pipe_segment"))
            self.assertEqual(len(calls), 1)
            ticks[0] += fabricator.CLAIM_REFRESH_TICKS - 1
            self.assertTrue(controller.claim_recipe("craft_gas_pipe_segment"))
            self.assertEqual(len(calls), 1)
            ticks[0] += 1
            self.assertTrue(controller.claim_recipe("craft_gas_pipe_segment"))
            self.assertEqual(len(calls), 2)
            controller.release_recipe("craft_gas_pipe_segment")
            self.assertNotIn("craft_gas_pipe_segment", controller._claim_ticks)
        finally:
            fabricator.archive.transaction = real


class RemoteFabricatorTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.remote = self.world.add_outpost("outpost_2")

    def test_connects_ports_to_local_warehouse(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote)
        f = w.add_fabricator("fabricator_2", self.remote)
        fabricator.FabricatorController(f).ensure_connection()
        self.assertEqual(f.input.connected_id(), "wh_remote")
        self.assertEqual(f.output.connected_id(), "wh_remote")
        self.assertNotIn("inventory", f.input.connect_log + f.output.connect_log)

    def test_loads_only_local_inputs(self):
        w = self.world
        w.inventory.add("iron_ingot", 100)
        w.add_warehouse("wh_remote", self.remote, {"iron_ingot": 6})
        f = w.add_fabricator("fabricator_2", self.remote)
        run_steps(fabricator.FabricatorController(f), 3)
        self.assertEqual(f.recipe, "craft_gas_pipe_segment")
        self.assertEqual(f.input_buffer.get("iron_ingot"), 6)
        self.assertEqual(w.inventory.count("iron_ingot"), 100)

    def test_drains_output_to_local_warehouse(self):
        w = self.world
        wh = w.add_warehouse("wh_remote", self.remote)
        f = w.add_fabricator("fabricator_2", self.remote)
        f.output_buffer["gas_pipe_segment"] = 3
        fabricator.FabricatorController(f).drain_output()
        self.assertEqual(wh.count("gas_pipe_segment"), 3)
        self.assertEqual(w.inventory.count("gas_pipe_segment"), 0)

    def test_eject_excess_to_local_warehouse(self):
        w = self.world
        wh = w.add_warehouse("wh_remote", self.remote)
        f = w.add_fabricator("fabricator_2", self.remote)
        f.input_buffer["glass"] = 4
        fabricator.FabricatorController(f).eject_excess_inputs(None, 0)
        self.assertEqual(wh.count("glass"), 4)
        self.assertEqual(w.inventory.count("glass"), 0)

    def test_eject_keeps_stock_without_local_room(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote, {"iron_ore": 10}, capacity=10)
        f = w.add_fabricator("fabricator_2", self.remote)
        f.input_buffer["glass"] = 4
        fabricator.FabricatorController(f).eject_excess_inputs(None, 0)
        self.assertEqual(f.input_buffer.get("glass"), 4)


if __name__ == "__main__":
    unittest.main()
