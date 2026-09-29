"""Stub tests for lib/production.py demand, discovery and peer helpers."""
import unittest

from harness import StubTestCase, production


class DiscoveryTests(StubTestCase):
    def test_discovery_walks_every_outpost(self):
        w = self.world
        remote = w.add_outpost("outpost_2")
        w.add_smelter("smelter_1", w.home)
        w.add_smelter("smelter_2", remote)
        w.add_fabricator("fabricator_1", w.home)
        w.add_fabricator("fabricator_2", remote)
        self.assertEqual(production.discover_smelter_ids(), ["smelter_1", "smelter_2"])
        self.assertEqual(production.discover_fabricator_ids(), ["fabricator_1", "fabricator_2"])
        self.assertEqual(production.discover_smelter_ids(remote), ["smelter_2"])
        self.assertEqual(production.discover_fabricator_ids(w.home), ["fabricator_1"])

    def test_supply_docks_stay_home_only(self):
        w = self.world
        remote = w.add_outpost("outpost_2")
        w.add_warehouse("dock_like", remote)  # any building; docks use their own type id
        self.assertEqual(production.discover_supply_dock_ids(), [])

    def test_machine_outpost_id(self):
        w = self.world
        remote = w.add_outpost("outpost_2")
        s = w.add_smelter("smelter_2", remote)
        self.assertEqual(production.machine_outpost_id(s), "outpost_2")
        self.assertIsNone(production.machine_outpost_id(object()))


class SmelterDemandTests(StubTestCase):
    def test_default_stock_targets_cascade_to_ingots(self):
        # Defaults: 10 gas pipe (2 iron), 10 power line (1 iron + 1 glass),
        # 10 liquid pipe (2 iron) -> 50 iron ingot, 10 glass.
        self.world.add_fabricator("fabricator_1", self.world.home)
        self.world.add_smelter("smelter_1", self.world.home)
        demands = production.get_smelter_demands()
        self.assertEqual(demands, {"iron_ingot": 50, "glass": 10})

    def test_nets_stock_and_fabricator_stockpiles(self):
        w = self.world
        w.add_smelter("smelter_1", w.home)
        f = w.add_fabricator("fabricator_1", w.home)
        w.inventory.add("iron_ingot", 20)
        f.input_buffer["iron_ingot"] = 5
        self.assertEqual(production.get_smelter_demands()["iron_ingot"], 25)

    def test_remote_fabricator_stockpile_counts(self):
        w = self.world
        remote = w.add_outpost("outpost_2")
        w.add_smelter("smelter_1", w.home)
        w.add_fabricator("fabricator_1", w.home)
        f2 = w.add_fabricator("fabricator_2", remote)
        f2.input_buffer["iron_ingot"] = 7
        self.assertEqual(production.get_smelter_demands()["iron_ingot"], 43)


class PeerTests(StubTestCase):
    def test_smelter_peers_network_and_outpost_scope(self):
        w = self.world
        remote = w.add_outpost("outpost_2")
        a = w.add_smelter("smelter_1", w.home)
        b = w.add_smelter("smelter_2", w.home)
        c = w.add_smelter("smelter_3", remote)
        for machine, buffered in ((a, 4), (b, 6), (c, 10)):
            machine.recipe = "smelt_iron_ingot"
            machine.input_buffer["iron_ore"] = buffered
        self.assertEqual(production.smelter_recipe_peers("smelt_iron_ingot"), (3, 20))
        self.assertEqual(production.smelter_recipe_peers("smelt_iron_ingot", "home"), (2, 10))
        self.assertEqual(production.smelter_recipe_peers("smelt_iron_ingot", "outpost_2"), (1, 10))
        self.assertEqual(production.smelter_recipe_peers("smelt_glass", "home"), (1, 0))

    def test_fabricator_split_follows_site_plan(self):
        w = self.world
        remote = w.add_outpost("outpost_2")
        f1 = w.add_fabricator("fabricator_1", w.home)
        f2 = w.add_fabricator("fabricator_2", remote)
        f1.recipe = f2.recipe = "craft_gas_pipe_segment"
        # 10 gas pipe wanted, unplanned: built where it is consumed (home).
        shares = [production.get_fabricator_active_recipe(f)[1] for f in (f1, f2)]
        self.assertEqual(shares, [10, 0])
        # Planned at both sites: split by Fabricator count, first listed gets the remainder.
        w.notebook.set(production.SITE_PLAN_KEY, {"gas_pipe_segment": ["outpost_2", "home"]})
        shares = [production.get_fabricator_active_recipe(f)[1] for f in (f1, f2)]
        self.assertEqual(shares, [5, 5])

    def test_pipeline_counts_remote_output_and_running_craft(self):
        w = self.world
        remote = w.add_outpost("outpost_2")
        f1 = w.add_fabricator("fabricator_1", w.home)
        f2 = w.add_fabricator("fabricator_2", remote)
        f1.output_buffer["gas_pipe_segment"] = 2
        f2.output_buffer["gas_pipe_segment"] = 3
        f2.recipe = "craft_gas_pipe_segment"
        f2.running = True
        self.assertEqual(production.get_fabricator_pipeline(), {"gas_pipe_segment": 6})

    def test_material_demands_include_remote_active_recipe(self):
        w = self.world
        remote = w.add_outpost("outpost_2")
        w.add_fabricator("fabricator_1", w.home)
        f2 = w.add_fabricator("fabricator_2", remote)
        f2.recipe = "craft_steel_plate"
        production.set_upgrade_order("field_keeper", {"steel_plate": 4})
        w.notebook.set(production.SITE_PLAN_KEY, {"steel_plate": ["outpost_2"]})
        demands = production.get_material_demands()
        self.assertEqual(demands.get("iron_ingot"), 12)


class SourceCacheTests(StubTestCase):
    def test_local_stock_scopes_to_outpost(self):
        w = self.world
        remote = w.add_outpost("outpost_2")
        w.inventory.add("iron_ore", 5)
        w.add_warehouse("wh_home", w.home, {"iron_ore": 10})
        w.add_warehouse("wh_remote", remote, {"iron_ore": 30})
        w.add_warehouse("wh_remote_2", remote, {"iron_ore": 3, "silicon": 2})
        cache = production.SourceCache()
        self.assertEqual(cache.stock("iron_ore"), 15)
        self.assertEqual(cache.local_stock("iron_ore", w.home), 15)
        self.assertEqual(cache.local_stock("iron_ore", None), 15)
        self.assertEqual(cache.local_stock("iron_ore", remote), 33)
        self.assertEqual(cache.local_stock("silicon", remote), 2)


if __name__ == "__main__":
    unittest.main()
