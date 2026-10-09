"""Stub tests for ship-before-craft (production.ship_units() / site ship plan,
lib/site_supply.py requests), per-site Smelter demand and the fluid-only
recipe switch in lib/fabricator.py."""
import unittest

from game_stubs import FluidPort, Recipe, FABRICATOR_RECIPES
from harness import StubTestCase, SEGMENT_ORDER, disable_ingot_buffer, home_order, production, smelter, fabricator, logistics_requests, site_supply, storage


VALVE = Recipe("craft_pressure_valve", {"iron_ingot": 1, "glass": 1}, "pressure_valve")
COOLANT = Recipe("craft_coolant_loop", {"pressure_valve": 2, "tar": 2}, "coolant_loop")
TAR = Recipe("craft_tar", {}, "tar", output_count=2, fluid_inputs={"oil_in": 5.0})
RECIPES = FABRICATOR_RECIPES + [VALVE, COOLANT, TAR]


def site_requests(world, outpost_id):
    requests = logistics_requests.active_requests(world.clock.now).get(outpost_id, {})
    return {item_id: (e["target"], logistics_requests.request_min(e)) for item_id, e in requests.items() if e.get("by") == site_supply.SITE_SUPPLY_REQUESTER}


class ShipBeforeCraftTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        self.remote = w.add_outpost("outpost_2")
        w.add_fabricator("fabricator_1", w.home, RECIPES)
        self.fab = w.add_fabricator("fabricator_2", self.remote, RECIPES)
        home_order({"coolant_loop": 5})
        w.notebook.set(production.SITE_PLAN_KEY, {"coolant_loop": ["outpost_2"]})

    def publish(self):
        return site_supply.publish_site_requests(self.world.clock.now)

    def test_spare_elsewhere_shared_cache_matches_fresh_cache(self):
        w = self.world
        third = w.add_outpost("outpost_3")
        w.add_fabricator("fabricator_3", third, RECIPES)
        w.inventory.add("tar", 40)
        w.add_warehouse("wh_remote", self.remote, {"tar": 7})
        w.add_warehouse("wh_third", third, {"tar": 5})
        shared = production.SourceCache()
        for site in ("outpost_2", "outpost_3", "home", "outpost_2"):
            fresh = production.site_spare_elsewhere("tar", site, production.SourceCache())
            self.assertEqual(production.site_spare_elsewhere("tar", site, shared), fresh)

    def test_network_stock_memo_matches_fresh_reads(self):
        w = self.world
        w.inventory.add("tar", 3)
        w.add_warehouse("wh_remote", self.remote, {"tar": 7})
        cache = production.SourceCache()
        first = cache.network_stock("tar")
        self.assertEqual(first, production.SourceCache().network_stock("tar"))
        self.assertEqual(cache.network_stock("tar"), first)

    def test_big_surplus_ships_instead_of_crafting(self):
        w = self.world
        w.inventory.add("tar", 1000)
        w.add_warehouse("wh_remote", self.remote)
        # 5 coolant loops need 10 tar; 1000 spare at home >= 10x -> ship all 10.
        self.assertEqual(production.get_site_ship_plan("outpost_2"), {"tar": 10})
        self.assertEqual(production.get_site_fabricator_targets("outpost_2").get("tar", 0), 0)
        self.publish()
        self.assertEqual(site_requests(w, "outpost_2")["tar"], (site_supply.SITE_STOCK_TARGETS["fabricator"]["tar"], 10))

    def test_fast_local_make_beats_small_spare(self):
        w = self.world
        w.inventory.add("pressure_valve", 15)  # 15 < 10 x 10 short
        w.add_warehouse("wh_remote", self.remote, {"iron_ingot": 50, "silicon": 50, "tar": 10})
        w.add_smelter("smelter_2", self.remote)
        # 10 valves + 10 glass at ~2 s per craft: well under SHIP_OVER_CRAFT_SECONDS.
        self.assertNotIn("pressure_valve", production.get_site_ship_plan("outpost_2"))
        self.assertEqual(production.get_site_fabricator_targets("outpost_2")["pressure_valve"], 10)

    def test_no_local_inputs_ships(self):
        w = self.world
        w.inventory.add("pressure_valve", 15)
        w.add_warehouse("wh_remote", self.remote, {"iron_ingot": 50, "tar": 10})
        # No local Smelter / silicon for the glass: can't make it here.
        self.assertEqual(production.get_site_ship_plan("outpost_2"), {"pressure_valve": 10})

    def test_slow_local_make_ships(self):
        w = self.world
        slow = Recipe("craft_pressure_valve", {"iron_ingot": 1, "glass": 1}, "pressure_valve", duration_game_hours=2.0)
        recipes = FABRICATOR_RECIPES + [slow, COOLANT, TAR]
        w.components["fabricator_1"]._recipes = list(recipes)
        self.fab._recipes = list(recipes)
        w.inventory.add("pressure_valve", 15)
        w.add_warehouse("wh_remote", self.remote, {"iron_ingot": 50, "glass": 50, "tar": 10})
        # 10 crafts x 50 s >= 300 s.
        self.assertEqual(production.get_site_ship_plan("outpost_2"), {"pressure_valve": 10})

    def test_mk3_fabricator_makes_slow_recipe_locally(self):
        w = self.world
        slow = Recipe("craft_pressure_valve", {"iron_ingot": 1, "glass": 1}, "pressure_valve", duration_game_hours=2.0)
        recipes = FABRICATOR_RECIPES + [slow, COOLANT, TAR]
        w.components["fabricator_1"]._recipes = list(recipes)
        self.fab._recipes = list(recipes)
        self.fab.installed_tier = 3
        w.inventory.add("pressure_valve", 15)
        w.add_warehouse("wh_remote", self.remote, {"iron_ingot": 50, "glass": 50, "tar": 10})
        # 10 crafts x 50 s / 4 (Mk III) < 300 s.
        self.assertEqual(production.get_site_ship_plan("outpost_2"), {})

    def test_in_flight_units_keep_the_request(self):
        w = self.world
        w.inventory.add("tar", 1000)
        w.add_warehouse("wh_remote", self.remote)
        self.publish()
        logistics_requests.reserve_pickup("drone_1", "outpost_2", "tar", 10, w.clock.now, source_id="home")
        self.assertEqual(production.get_site_ship_plan("outpost_2"), {})
        w.clock.now += site_supply.REPUBLISH_TICKS
        self.publish()
        self.assertEqual(site_requests(w, "outpost_2")["tar"], (site_supply.SITE_STOCK_TARGETS["fabricator"]["tar"], 10))


class IngotShipTests(StubTestCase):
    def setUp(self):
        super().setUp()
        home_order(SEGMENT_ORDER)

    def test_big_ingot_surplus_ahead_of_local_ore(self):
        w = self.world
        w.research.unlocked.add("research_warehouse")
        disable_ingot_buffer(w)
        remote = w.add_outpost("outpost_2")
        w.inventory.add("iron_ingot", 1000)
        w.add_warehouse("wh_remote", remote, {"iron_ore": 100})
        w.add_smelter("smelter_2", remote)
        f = w.add_fabricator("fabricator_2", remote)
        f.recipe = "craft_gas_pipe_segment"  # 10 crafts x 2 = 20 iron ingot
        site_supply.publish_site_requests(w.clock.now)
        requests = site_requests(w, "outpost_2")
        self.assertEqual(requests["iron_ingot"], (20, 20))
        self.assertEqual(requests["iron_ore"], (storage.WAREHOUSE_STOCK_TARGET, 100))  # local ore held, none extra


class SiteSmelterDemandTests(StubTestCase):
    def test_remote_smelter_sees_site_need_hidden_by_network_stock(self):
        w = self.world
        remote = w.add_outpost("outpost_2")
        w.inventory.add("glass", 1000)
        w.add_warehouse("wh_remote", remote, {"iron_ingot": 50, "silicon": 50})
        w.add_fabricator("fabricator_1", w.home)
        f = w.add_fabricator("fabricator_2", remote)
        f.recipe = "craft_power_line_segment"
        home_order({"power_line_segment": 10})
        w.notebook.set(production.SITE_PLAN_KEY, {"power_line_segment": ["outpost_2"]})
        cache = production.SourceCache()
        self.assertNotIn("glass", production.get_smelter_demands(cache))
        ctl = smelter.SmelterController(w.add_smelter("smelter_2", remote))
        self.assertEqual(ctl.demands(production.SourceCache())["glass"], 10)


def _tiers(units, need_units):
    return {logistics_requests.NEED: need_units, logistics_requests.BUFFER: units - need_units}


class HaulRankTests(unittest.TestCase):
    def test_need_throughput_beats_bigger_buffer_load(self):
        # drone_13 live: home->outpost_5 1500 units (10 need) over 134 m
        # vs outpost_4->outpost_5 1500 units (40 need, valves) over 1324 m.
        near = logistics_requests.haul_rank(_tiers(1500, 10), 134, 300)
        valves = logistics_requests.haul_rank(_tiers(1500, 40), 1324, 300)
        self.assertTrue(logistics_requests.rank_beats(valves, near))
        self.assertFalse(logistics_requests.rank_beats(near, valves))

    def test_any_need_beats_buffer_only(self):
        buffer_only = logistics_requests.haul_rank(_tiers(2000, 0), 50, 300)
        small_need = logistics_requests.haul_rank(_tiers(5, 5), 3000, 300)
        self.assertTrue(logistics_requests.rank_beats(small_need, buffer_only))

    def test_units_break_a_need_tie(self):
        a = logistics_requests.haul_rank(_tiers(100, 0), 100, 300)
        b = logistics_requests.haul_rank(_tiers(50, 0), 100, 300)
        self.assertTrue(logistics_requests.rank_beats(a, b))
        self.assertTrue(logistics_requests.rank_beats(b, None))

    def test_urgent_units_beat_need_rate(self):
        need_run = logistics_requests.haul_rank(_tiers(100, 100), 100, 300)
        blocker = logistics_requests.haul_rank(_tiers(1, 1), 2000, 300, urgent_units=1)
        self.assertTrue(logistics_requests.rank_beats(blocker, need_run))


class FluidOnlySwitchTests(StubTestCase):
    def test_met_fluid_only_recipe_switches_while_running(self):
        w = self.world
        w.inventory.add("tar", 500)
        f = w.add_fabricator("fabricator_1", w.home, RECIPES)
        f.recipe = "craft_tar"
        f.running = True
        oil_in = FluidPort(w, connected="oil_pump_1")
        setattr(f, "oil_in", oil_in)
        fabricator.FabricatorController(f).step()
        self.assertEqual(oil_in.connected_id(), "")
        self.assertNotEqual(f.recipe, "craft_tar")

    def tar_fab(self, oil_level):
        w = self.world
        home_order({"tar": 50})
        self.tank = w.add_tank("liquid_tank_1", w.home, fluid="oil", level=oil_level, capacity=100)
        f = w.add_fabricator("fabricator_1", w.home, RECIPES)
        f.recipe = "craft_tar"
        f.running = True
        self.oil_in = FluidPort(w, connected="liquid_tank_1")
        setattr(f, "oil_in", self.oil_in)
        return f, fabricator.FabricatorController(f)

    def test_low_oil_tanks_pause_fluid_only_recipe(self):
        f, c = self.tar_fab(fabricator.FLUID_ONLY_PAUSE_BELOW * 100 - 1)
        c.step()
        self.assertEqual(self.oil_in.connected_id(), "")
        self.assertNotEqual(f.recipe, "craft_tar")

    def test_paused_fluid_only_recipe_resumes_at_resume_fill(self):
        f, c = self.tar_fab(1)
        c.step()
        self.assertNotEqual(f.recipe, "craft_tar")
        f.running = False
        self.tank._level = (fabricator.FLUID_ONLY_PAUSE_BELOW + fabricator.FLUID_ONLY_RESUME_AT) / 2 * 100
        self.world.clock.now += fabricator.FLUID_ONLY_RESERVE_REFRESH_TICKS
        c.step()
        self.assertNotEqual(f.recipe, "craft_tar")
        self.tank._level = fabricator.FLUID_ONLY_RESUME_AT * 100
        self.world.clock.now += fabricator.FLUID_ONLY_RESERVE_REFRESH_TICKS
        c.step()
        self.assertEqual(f.recipe, "craft_tar")

    def test_buffered_oil_keeps_fluid_only_recipe(self):
        f, c = self.tar_fab(fabricator.FLUID_ONLY_PAUSE_BELOW * 100 + 1)
        c.step()
        self.assertEqual(f.recipe, "craft_tar")
        self.assertEqual(self.oil_in.connected_id(), "liquid_tank_1")


if __name__ == "__main__":
    unittest.main()
