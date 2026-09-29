"""Stub tests for lib/smelter.py SmelterController, at home and at a remote outpost."""
import unittest

from harness import StubTestCase, smelter


def run_steps(controller, n):
    for _ in range(n):
        controller.step()


class HomeSmelterTests(StubTestCase):
    def test_sets_recipe_and_loads_ore_from_home_warehouse(self):
        w = self.world
        w.add_fabricator("fabricator_1", w.home)
        w.add_warehouse("wh1", w.home, {"iron_ore": 100})
        s = w.add_smelter("smelter_1", w.home)
        run_steps(smelter.SmelterController(s), 3)
        self.assertEqual(s.recipe, "smelt_iron_ingot")
        self.assertGreater(s.input_buffer.get("iron_ore", 0), 0)
        self.assertEqual(s.input.connect_log[0], "inventory")

    def test_drains_output_to_inventory(self):
        w = self.world
        s = w.add_smelter("smelter_1", w.home)
        s.output_buffer["iron_ingot"] = 7
        smelter.SmelterController(s).drain_output()
        self.assertEqual(w.inventory.count("iron_ingot"), 7)

    def test_fair_share_splits_scarce_ore_between_home_peers(self):
        w = self.world
        w.add_fabricator("fabricator_1", w.home)
        w.add_warehouse("wh1", w.home, {"iron_ore": 12})
        a = w.add_smelter("smelter_1", w.home)
        b = w.add_smelter("smelter_2", w.home)
        a.recipe = b.recipe = "smelt_iron_ingot"
        ca, cb = smelter.SmelterController(a), smelter.SmelterController(b)
        ca.step()
        cb.step()
        self.assertEqual(a.input_buffer.get("iron_ore", 0), 6)
        self.assertEqual(b.input_buffer.get("iron_ore", 0), 6)

    def test_recover_input_goes_to_inventory(self):
        w = self.world
        s = w.add_smelter("smelter_1", w.home)
        s.input_buffer["iron_ore"] = 9
        self.assertTrue(smelter.SmelterController(s).recover_input())
        self.assertEqual(w.inventory.count("iron_ore"), 9)


class RemoteSmelterTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        self.remote = w.add_outpost("outpost_2")
        w.add_fabricator("fabricator_1", w.home)

    def test_connects_ports_to_local_warehouse(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote, {"iron_ore": 40})
        s = w.add_smelter("smelter_2", self.remote)
        smelter.SmelterController(s).ensure_connections()
        self.assertEqual(s.input.connected_id(), "wh_remote")
        self.assertEqual(s.output.connected_id(), "wh_remote")
        self.assertNotIn("inventory", s.input.connect_log + s.output.connect_log)

    def test_warns_once_without_local_warehouse(self):
        s = self.world.add_smelter("smelter_2", self.remote)
        controller = smelter.SmelterController(s)
        run_steps(controller, 3)
        self.assertEqual(self.world.console.text("warn").count("No Warehouse at outpost 'outpost_2'"), 1)
        self.assertIsNone(s.input.connected_id())

    def test_loads_only_local_ore(self):
        w = self.world
        w.add_warehouse("wh_home", w.home, {"iron_ore": 100})
        w.add_warehouse("wh_remote", self.remote, {"iron_ore": 8})
        s = w.add_smelter("smelter_2", self.remote)
        run_steps(smelter.SmelterController(s), 4)
        self.assertEqual(s.recipe, "smelt_iron_ingot")
        self.assertEqual(s.input_buffer.get("iron_ore", 0), 8)
        self.assertEqual(w.stock("iron_ore", w.home), 100)

    def test_idles_when_ore_is_only_at_home(self):
        w = self.world
        w.add_warehouse("wh_home", w.home, {"iron_ore": 100})
        w.add_warehouse("wh_remote", self.remote)
        s = w.add_smelter("smelter_2", self.remote)
        controller = smelter.SmelterController(s)
        run_steps(controller, 2)
        self.assertEqual(s.recipe, "")
        self.assertEqual(controller._select_miss_reason, "no_ore")

    def test_dock_reserve_does_not_apply_off_home(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote, {"iron_ore": 8})
        s = w.add_smelter("smelter_2", self.remote)
        controller = smelter.SmelterController(s)
        cache = smelter.SourceCache()
        self.assertEqual(controller.available_ore("iron_ore", cache, {"iron_ore": 50}), 8)
        home = w.add_smelter("smelter_1", w.home)
        w.add_warehouse("wh_home", w.home, {"iron_ore": 60})
        self.assertEqual(smelter.SmelterController(home).available_ore("iron_ore", cache, {"iron_ore": 50}), 10)

    def test_drains_output_to_local_warehouse(self):
        w = self.world
        wh = w.add_warehouse("wh_remote", self.remote)
        s = w.add_smelter("smelter_2", self.remote)
        s.output_buffer["iron_ingot"] = 12
        moved = smelter.SmelterController(s).drain_output()
        self.assertEqual(moved, 12)
        self.assertEqual(wh.count("iron_ingot"), 12)
        self.assertEqual(w.inventory.count("iron_ingot"), 0)

    def test_recover_input_goes_to_local_warehouse(self):
        w = self.world
        wh = w.add_warehouse("wh_remote", self.remote)
        s = w.add_smelter("smelter_2", self.remote)
        s.input_buffer["silicon"] = 5
        self.assertTrue(smelter.SmelterController(s).recover_input())
        self.assertEqual(wh.count("silicon"), 5)

    def test_fair_share_counts_only_same_outpost_peers(self):
        w = self.world
        w.add_warehouse("wh_home", w.home, {"iron_ore": 100})
        w.add_warehouse("wh_remote", self.remote, {"iron_ore": 6})
        home = w.add_smelter("smelter_1", w.home)
        remote = w.add_smelter("smelter_2", self.remote)
        home.recipe = remote.recipe = "smelt_iron_ingot"
        home.input_buffer["iron_ore"] = 30
        # Scarce local ore (6) is not split with the home peer's buffer:
        # the remote Smelter may take all of it.
        smelter.SmelterController(remote).step()
        self.assertEqual(remote.input_buffer.get("iron_ore", 0), 6)


if __name__ == "__main__":
    unittest.main()
