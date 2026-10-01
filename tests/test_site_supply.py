"""Stub tests for per-site recipe claims (E2), the global ore stock target (E3)
and 5_steampower lib/site_supply.py site requests (E4)."""
import unittest

from harness import StubTestCase, production, smelter, fabricator, outpost_mining, logistics_requests, site_supply
from game_stubs import Recipe, FABRICATOR_RECIPES


class _Building:
    """A plain building with only a type and an outpost (e.g. a Fuel Assembler)."""

    def __init__(self, building_id, type_id, outpost):
        self.id = building_id
        self.type_id = type_id
        self.outpost = outpost


def site_requests(world, outpost_id):
    requests = logistics_requests.active_requests(world.clock.now).get(outpost_id, {})
    return {item_id: (e["target"], logistics_requests.request_min(e)) for item_id, e in requests.items() if e.get("by") == site_supply.SITE_SUPPLY_REQUESTER}


class RecipeClaimTests(StubTestCase):
    def test_home_and_remote_smelters_claim_same_recipe(self):
        w = self.world
        remote = w.add_outpost("outpost_2")
        home_ctl = smelter.SmelterController(w.add_smelter("smelter_1", w.home))
        remote_ctl = smelter.SmelterController(w.add_smelter("smelter_2", remote))
        self.assertTrue(home_ctl.claim_recipe("smelt_iron_ingot"))
        self.assertTrue(remote_ctl.claim_recipe("smelt_iron_ingot"))
        claims = w.notebook.data[smelter.RECIPE_CLAIMS_KEY]
        self.assertEqual(claims["home"]["smelt_iron_ingot"]["smelter"], "smelter_1")
        self.assertEqual(claims["outpost_2"]["smelt_iron_ingot"]["smelter"], "smelter_2")

    def test_same_outpost_peer_is_blocked(self):
        w = self.world
        a = fabricator.FabricatorController(w.add_fabricator("fabricator_1", w.home))
        b = fabricator.FabricatorController(w.add_fabricator("fabricator_2", w.home))
        self.assertTrue(a.claim_recipe("craft_gas_pipe_segment"))
        self.assertFalse(b.claim_recipe("craft_gas_pipe_segment"))

    def test_flat_claims_dropped_and_empty_site_pruned(self):
        w = self.world
        w.notebook.set(smelter.RECIPE_CLAIMS_KEY, {"smelt_glass": {"smelter": "old", "tick": 999}})
        ctl = smelter.SmelterController(w.add_smelter("smelter_1", w.home))
        self.assertTrue(ctl.claim_recipe("smelt_glass"))
        ctl.release_recipe("smelt_glass")
        self.assertEqual(w.notebook.get(smelter.RECIPE_CLAIMS_KEY), {})


class OreStockTargetTests(StubTestCase):
    def test_seeds_default_once_and_keeps_edits(self):
        w = self.world
        self.assertEqual(outpost_mining.ore_stock_target("iron_ore"), 2000)
        self.assertEqual(w.notebook.get(outpost_mining.ORE_STOCK_TARGETS_KEY), {"iron_ore": 2000})
        w.notebook.set(outpost_mining.ORE_STOCK_TARGETS_KEY, {"iron_ore": 500})
        self.assertEqual(outpost_mining.ore_stock_target("iron_ore"), 500)
        self.assertEqual(outpost_mining.ore_stock_target("silicon"), 2000)
        self.assertEqual(w.notebook.get(outpost_mining.ORE_STOCK_TARGETS_KEY), {"iron_ore": 500, "silicon": 2000})


class RemoteIngotNettingTests(StubTestCase):
    def test_remote_ingots_net_smelter_demand(self):
        w = self.world
        remote = w.add_outpost("outpost_2")
        w.add_smelter("smelter_1", w.home)
        w.add_fabricator("fabricator_1", w.home)
        w.add_warehouse("wh_remote", remote, {"iron_ingot": 30})
        self.assertEqual(production.get_smelter_demands()["iron_ingot"], 20)


class SiteSupplyTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.remote = self.world.add_outpost("outpost_2")

    def publish(self):
        return site_supply.publish_site_requests(self.world.clock.now)

    def test_home_smelting_site_requests_ore_like_any_site(self):
        w = self.world
        w.add_smelter("smelter_1", w.home)
        f = w.add_fabricator("fabricator_1", w.home)
        f.recipe = "craft_gas_pipe_segment"
        w.inventory.add("iron_ore", 50)
        self.publish()
        # 20 ingots needed, 50 ore at home: no ingot request, ore buffered to its stock target.
        requests = site_requests(w, w.home.id)
        self.assertNotIn("iron_ingot", requests)
        self.assertEqual(requests["iron_ore"], (outpost_mining.ore_stock_target("iron_ore"), 50))

    def test_fab_only_site_requests_all_of_d_as_ingots(self):
        w = self.world
        w.add_smelter("smelter_1", w.home)
        w.add_warehouse("wh_remote", self.remote, {"iron_ingot": 4})
        f = w.add_fabricator("fabricator_2", self.remote)
        f.recipe = "craft_gas_pipe_segment"  # 10 crafts x 2 = 20 iron ingot
        self.publish()
        # D = 20 - 4 local; no local Smelter, so all 16 as ingots on top of the 4 held.
        self.assertEqual(site_requests(w, "outpost_2"), {"iron_ingot": (20, 20)})

    def test_remote_fab_site_stocks_tar_free_at_home(self):
        w = self.world
        w.add_warehouse("wh_home", w.home, {"tar": 5000}, capacity=100000)
        w.add_fabricator("fabricator_2", self.remote)
        self.publish()
        self.assertEqual(site_requests(w, "outpost_2").get("tar"), (site_supply.SITE_STOCK_TARGETS["fabricator"]["tar"], 0))

    def test_home_fab_site_stocks_tar_like_any_site(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote, {"tar": 5000}, capacity=100000)
        w.add_fabricator("fabricator_1", w.home)
        self.publish()
        self.assertEqual(site_requests(w, w.home.id).get("tar"), (site_supply.SITE_STOCK_TARGETS["fabricator"]["tar"], 0))

    def test_fuel_assembler_site_stocks_and_orders_lead_plates(self):
        w = self.world
        w.components["fuel_assembler_1"] = _Building("fuel_assembler_1", "fuel_assembler", self.remote)
        w.add_fabricator("fabricator_1", w.home, FABRICATOR_RECIPES + [Recipe("craft_lead_plate", {"lead_ingot": 2}, "lead_plate")])
        target = site_supply.SITE_STOCK_TARGETS["fuel_assembler"]["lead_plate"]
        self.publish()
        self.assertNotIn("lead_plate", site_requests(w, "outpost_2"))  # none built anywhere yet
        self.assertEqual(production.get_backlog_orders(), {"lead_plate": target})
        w.add_warehouse("wh_home", w.home, {"lead_plate": 50}, capacity=100000)
        w.clock.now += site_supply.REPUBLISH_TICKS
        self.publish()
        self.assertEqual(site_requests(w, "outpost_2").get("lead_plate"), (target, 0))

    def test_smelt_and_fab_site_splits_ingots_and_ore(self):
        w = self.world
        w.inventory.add("iron_ingot", 8)  # free at home
        w.add_warehouse("wh_remote", self.remote, {"iron_ore": 5})
        w.add_smelter("smelter_2", self.remote)
        f = w.add_fabricator("fabricator_2", self.remote)
        f.recipe = "craft_gas_pipe_segment"
        self.publish()
        requests = site_requests(w, "outpost_2")
        # D = 20 - 0 ingots - 5 ore = 15: 8 as remote ingots, 7 as extra ore.
        self.assertEqual(requests["iron_ingot"], (8, 8))
        self.assertEqual(requests["iron_ore"], (2000, 12))
        # Other ores the Smelter can refine: buffer tier only.
        self.assertEqual(requests["silicon"], (2000, 0))

    def test_in_flight_counts_toward_d(self):
        w = self.world
        w.inventory.add("iron_ingot", 100)
        w.add_smelter("smelter_1", w.home)
        w.add_warehouse("wh_remote", self.remote)
        f = w.add_fabricator("fabricator_2", self.remote)
        f.recipe = "craft_gas_pipe_segment"
        logistics_requests.reserve_pickup("pioneer_1", "outpost_2", "iron_ingot", 15, w.clock.now, source_id="home")
        self.publish()
        # 15 in flight + 5 more = 20.
        self.assertEqual(site_requests(w, "outpost_2")["iron_ingot"], (20, 20))

    def test_smelt_only_site_requests_buffer(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote)
        w.add_smelter("smelter_2", self.remote)
        self.publish()
        self.assertEqual(site_requests(w, "outpost_2"), {"iron_ore": (2000, 0), "silicon": (2000, 0), "titanium": (2000, 0)})

    def test_home_pulls_remote_ingots(self):
        w = self.world
        f = w.add_fabricator("fabricator_1", w.home)
        f.recipe = "craft_gas_pipe_segment"
        w.add_smelter("smelter_1", w.home)
        w.add_smelter("smelter_2", self.remote)
        w.add_warehouse("wh_remote", self.remote, {"iron_ingot": 12})
        self.publish()
        # Home D = 20, all 12 free remote ingots requested; the other 8 as home ore need.
        requests = site_requests(w, w.home.id)
        self.assertEqual(requests["iron_ingot"], (12, 12))
        self.assertEqual(requests["iron_ore"], (outpost_mining.ore_stock_target("iron_ore"), 8))

    def test_withdrawn_when_machines_leave(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote)
        w.add_smelter("smelter_2", self.remote)
        self.publish()
        self.assertTrue(site_requests(w, "outpost_2"))
        del w.components["smelter_2"]
        self.publish()
        self.assertEqual(site_requests(w, "outpost_2"), {})

    def test_unchanged_request_not_rewritten(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote)
        w.add_smelter("smelter_2", self.remote)
        self.publish()
        first_tick = w.notebook.data[logistics_requests.REQUESTS_KEY]["outpost_2"]["iron_ore"]["tick"]
        w.clock.now += 100
        self.publish()
        self.assertEqual(w.notebook.data[logistics_requests.REQUESTS_KEY]["outpost_2"]["iron_ore"]["tick"], first_tick)
        w.clock.now += site_supply.REPUBLISH_TICKS
        self.publish()
        self.assertEqual(w.notebook.data[logistics_requests.REQUESTS_KEY]["outpost_2"]["iron_ore"]["tick"], w.clock.now)


if __name__ == "__main__":
    unittest.main()
