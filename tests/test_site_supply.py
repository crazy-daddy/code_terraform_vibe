"""Stub tests for per-site recipe claims (E2), the global ore stock target (E3)
and lib/site_supply.py site requests (E4)."""

import unittest
from unittest import mock

import priority
import production_sites
from game_stubs import FABRICATOR_RECIPES, Journal, Recipe, Site
from harness import (
    SEGMENT_ORDER,
    StubTestCase,
    disable_ingot_buffer,
    fabricator,
    home_order,
    logistics_requests,
    outpost_mining,
    production,
    site_supply,
    smelter,
    storage,
)


def site_requests(world, outpost_id):
    requests = logistics_requests.active_requests(world.clock.now).get(outpost_id, {})
    return {
        item_id: (logistics_requests.request_target(e), logistics_requests.tier_level(e, priority.NEED))
        for item_id, e in requests.items()
        if e.get("by") == site_supply.SITE_SUPPLY_REQUESTER
    }


def request_ladder(world, outpost_id, item_id):
    entry = logistics_requests.active_requests(world.clock.now).get(outpost_id, {}).get(item_id) or {}
    return logistics_requests.request_levels(entry) if entry else []


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
    def test_bin_default_unseeded_before_warehouses(self):
        w = self.world
        self.assertEqual(outpost_mining.ore_stock_target("iron_ore"), storage.BIN_STOCK_TARGET)
        self.assertIsNone(w.notebook.get(outpost_mining.ORE_STOCK_TARGETS_KEY))
        w.research.unlocked.add("research_warehouse")
        self.assertEqual(outpost_mining.ore_stock_target("iron_ore"), storage.WAREHOUSE_STOCK_TARGET)
        self.assertEqual(
            w.notebook.get(outpost_mining.ORE_STOCK_TARGETS_KEY), {"iron_ore": storage.WAREHOUSE_STOCK_TARGET}
        )

    def test_seeds_default_once_and_keeps_edits(self):
        w = self.world
        w.research.unlocked.add("research_warehouse")
        self.assertEqual(outpost_mining.ore_stock_target("iron_ore"), storage.WAREHOUSE_STOCK_TARGET)
        self.assertEqual(
            w.notebook.get(outpost_mining.ORE_STOCK_TARGETS_KEY), {"iron_ore": storage.WAREHOUSE_STOCK_TARGET}
        )
        w.notebook.set(outpost_mining.ORE_STOCK_TARGETS_KEY, {"iron_ore": 500})
        self.assertEqual(outpost_mining.ore_stock_target("iron_ore"), 500)
        self.assertEqual(outpost_mining.ore_stock_target("silicon"), storage.WAREHOUSE_STOCK_TARGET)
        self.assertEqual(
            w.notebook.get(outpost_mining.ORE_STOCK_TARGETS_KEY),
            {"iron_ore": 500, "silicon": storage.WAREHOUSE_STOCK_TARGET},
        )


class RemoteIngotNettingTests(StubTestCase):
    def setUp(self):
        super().setUp()
        home_order(SEGMENT_ORDER)

    def test_remote_ingots_net_smelter_demand(self):
        w = self.world
        remote = w.add_outpost("outpost_2")
        w.add_smelter("smelter_1", w.home)
        w.add_fabricator("fabricator_1", w.home)
        w.add_warehouse("wh_remote", remote, {"iron_ingot": 30})
        self.assertEqual(priority.ladder_total(production.get_smelter_demands()["iron_ingot"]), 20)

    def test_smelter_output_nets_smelter_demand(self):
        w = self.world
        smelter_1 = w.add_smelter("smelter_1", w.home)
        w.add_fabricator("fabricator_1", w.home)
        w.add_warehouse("wh_home", w.home, {"iron_ingot": 30})
        # Ingots in the output slot and a running craft are made: not smelted again.
        smelter_1.output_buffer["iron_ingot"] = 12
        smelter_1.recipe = "smelt_iron_ingot"
        smelter_1.running = True
        self.assertEqual(priority.ladder_total(production.get_smelter_demands()["iron_ingot"]), 7)


class SiteSupplyTests(StubTestCase):
    def setUp(self):
        super().setUp()
        home_order(SEGMENT_ORDER)
        self.world.research.unlocked.add("research_warehouse")
        self.remote = self.world.add_outpost("outpost_2")
        disable_ingot_buffer(self.world)
        # site stock alone; ConstructionStockTests covers the construction stock
        self.world.notebook.set(site_supply.CONSTRUCTION_STOCK_KEY, {})

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

    @mock.patch.dict(site_supply.SITE_STOCK_TARGETS, clear=True)
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
        self.assertEqual(
            site_requests(w, "outpost_2").get("tar"), (site_supply.SITE_STOCK_TARGETS["fabricator"]["tar"], 0)
        )

    def test_home_fab_site_stocks_tar_like_any_site(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote, {"tar": 5000}, capacity=100000)
        w.add_fabricator("fabricator_1", w.home)
        self.publish()
        self.assertEqual(
            site_requests(w, w.home.id).get("tar"), (site_supply.SITE_STOCK_TARGETS["fabricator"]["tar"], 0)
        )

    def test_refiner_site_stocks_tar_with_need_floor(self):
        w = self.world
        w.add_warehouse("wh_home", w.home, {"tar": 5000}, capacity=100000)
        w.add_building("refiner_1", self.remote, "refiner")
        self.publish()
        self.assertEqual(
            site_requests(w, "outpost_2").get("tar"),
            (site_supply.SITE_STOCK_TARGETS["refiner"]["tar"], site_supply.SITE_STOCK_NEED["refiner"]["tar"]),
        )

    def test_fuel_assembler_site_stocks_and_orders_lead_plates(self):
        w = self.world
        w.add_building("fuel_assembler_1", self.remote, "fuel_assembler")
        w.add_fabricator(
            "fabricator_1", w.home, FABRICATOR_RECIPES + [Recipe("craft_lead_plate", {"lead_ingot": 2}, "lead_plate")]
        )
        target = site_supply.SITE_STOCK_TARGETS["fuel_assembler"]["lead_plate"]
        self.publish()
        # requested before any is built: the backlog order crafts it
        self.assertEqual(site_requests(w, "outpost_2").get("lead_plate"), (target, 0))
        self.assertEqual(
            production.get_orders()[site_supply.SITE_STOCK_REQUESTER], {"lead_plate": [[target, priority.STOCK]]}
        )

    def test_refiner_tar_ordered_and_not_pulled_home(self):
        w = self.world
        w.add_building("refiner_1", self.remote, "refiner")
        w.add_fabricator("fabricator_1", w.home, FABRICATOR_RECIPES + [Recipe("craft_tar", {}, "tar")])
        self.publish()
        need = site_supply.SITE_STOCK_NEED["refiner"]["tar"]
        self.assertEqual(
            site_requests(w, "outpost_2").get("tar"), (site_supply.SITE_STOCK_TARGETS["refiner"]["tar"], need)
        )
        tar_order = production.get_orders()[site_supply.SITE_STOCK_REQUESTER]["tar"]
        self.assertEqual(tar_order[0], [need, priority.NEED])
        self.assertGreaterEqual(
            sum(units for units, _prio in tar_order), site_supply.SITE_STOCK_TARGETS["refiner"]["tar"]
        )
        _roots, consumers, _outputs = production.fabricator_root_targets(production.SourceCache())
        self.assertNotIn(w.home.id, consumers.get("tar", {}))

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
        self.assertEqual(requests["iron_ore"], (storage.WAREHOUSE_STOCK_TARGET, 12))
        # Other ores the Smelter can refine: buffer tier only.
        self.assertEqual(requests["silicon"], (storage.WAREHOUSE_STOCK_TARGET, 0))

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
        self.assertEqual(
            site_requests(w, "outpost_2"),
            {
                "iron_ore": (storage.WAREHOUSE_STOCK_TARGET, 0),
                "silicon": (storage.WAREHOUSE_STOCK_TARGET, 0),
                "titanium": (storage.WAREHOUSE_STOCK_TARGET, 0),
            },
        )

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

    def test_dock_ingot_order_charges_ore_to_assigned_smelting_site(self):
        w = self.world
        w.add_smelter("smelter_2", self.remote)
        w.add_warehouse("wh_remote", self.remote, {"iron_ingot": 30})
        w.add_supply_dock("supply_dock_1", w.home).order = w.add_order("o1", {"iron_ingot": 150})
        with mock.patch.object(site_supply, "assigned_ores_by_outpost", lambda: {"outpost_2": {"iron_ore"}}):
            self.publish()
        self.assertEqual(
            request_ladder(w, "outpost_2", "iron_ore"),
            [[priority.ORDER, 120], [priority.STOCK, storage.WAREHOUSE_STOCK_TARGET]],
        )
        # The charge is the ore request's ORDER level on top of the ore buffer.
        self.assertEqual(site_requests(w, "outpost_2")["iron_ore"], (storage.WAREHOUSE_STOCK_TARGET, 120))

    def test_dock_ingot_order_nets_ore_and_ingots_inside_smelters(self):
        w = self.world
        smelter_2 = w.add_smelter("smelter_2", self.remote)
        w.add_warehouse("wh_remote", self.remote, {"iron_ingot": 30})
        # 10 ingots in the output slot, one running craft, 15 ore loaded: 26 more ingots coming.
        smelter_2.output_buffer["iron_ingot"] = 10
        smelter_2.recipe = "smelt_iron_ingot"
        smelter_2.running = True
        smelter_2.input_buffer["iron_ore"] = 15
        w.add_supply_dock("supply_dock_1", w.home).order = w.add_order("o1", {"iron_ingot": 150})
        with mock.patch.object(site_supply, "assigned_ores_by_outpost", lambda: {"outpost_2": {"iron_ore"}}):
            self.publish()
        self.assertEqual(
            request_ladder(w, "outpost_2", "iron_ore"),
            [[priority.ORDER, 94], [priority.STOCK, storage.WAREHOUSE_STOCK_TARGET]],
        )

    def test_dock_ingot_order_without_assigned_ore_charges_nothing(self):
        w = self.world
        w.add_smelter("smelter_2", self.remote)
        w.add_warehouse("wh_remote", self.remote)
        w.add_supply_dock("supply_dock_1", w.home).order = w.add_order("o1", {"iron_ingot": 150})
        self.publish()
        self.assertEqual(request_ladder(w, "outpost_2", "iron_ore"), [[priority.STOCK, storage.WAREHOUSE_STOCK_TARGET]])

    def test_dock_raw_ore_order_charges_owing_dock_site(self):
        w = self.world
        third = w.add_outpost("outpost_3")
        w.add_warehouse("wh_remote", self.remote, {"titanium": 16})
        w.add_supply_dock("supply_dock_2", third).order = w.add_order("o1", {"titanium": 100})
        with mock.patch.object(
            site_supply, "assigned_ores_by_outpost", lambda: {"outpost_2": {"titanium"}, "outpost_3": {"titanium"}}
        ):
            self.publish()
        self.assertEqual(request_ladder(w, "outpost_3", "titanium"), [[priority.ORDER, 100]])

    def test_dock_raw_ore_order_requests_ore_at_the_dock_site(self):
        w = self.world
        w.inventory.add("titanium", 10)
        w.add_supply_dock("supply_dock_1", w.home).order = w.add_order("spire_intake_3", {"titanium": 60})
        self.publish()
        # Need level = owed, with no Smelter at home and no titanium anywhere else.
        self.assertEqual(site_requests(w, w.home.id)["titanium"], (60, 60))

    def test_dock_raw_ore_order_falls_back_to_assigned_site(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote)
        w.add_supply_dock("supply_dock_1", w.home).order = w.add_order("o1", {"titanium": 100})
        with mock.patch.object(site_supply, "assigned_ores_by_outpost", lambda: {"outpost_2": {"titanium"}}):
            self.publish()
        self.assertEqual(request_ladder(w, "outpost_2", "titanium"), [[priority.ORDER, 100]])

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
        w.clock.now += logistics_requests.REPUBLISH_TICKS
        self.publish()
        self.assertEqual(w.notebook.data[logistics_requests.REQUESTS_KEY]["outpost_2"]["iron_ore"]["tick"], w.clock.now)

    def _forage_fab(self, outpost):
        recipe = Recipe(
            "craft_reinforced_biopolymer", {"forage": 6, "gas_pipe_segment": 1}, "reinforced_biopolymer", output_count=4
        )
        self.world.add_fabricator("fabricator_2", outpost, FABRICATOR_RECIPES + [recipe])
        patcher = mock.patch.object(
            production_sites,
            "get_fabricator_active_recipe",
            lambda fabricator, cache=None: (recipe, 50, priority.UPGRADE),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_remote_fab_site_requests_raw_input_free_at_home(self):
        w = self.world
        w.add_warehouse("wh_home", w.home, {"forage": 5000}, capacity=100000)
        w.add_warehouse("wh_remote", self.remote, {"forage": 40})
        self._forage_fab(self.remote)
        self.publish()
        requests = site_requests(w, "outpost_2")
        # 50 crafts x 6 = 300 staged need, 40 local: pull 260, need tier.
        self.assertEqual(requests["forage"], (site_supply.SITE_STOCK_TARGETS["fabricator"]["forage"], 300))
        # A Fabricator-made input is the ship plan's job, not a raw input.
        self.assertNotIn("gas_pipe_segment", requests)

    def test_raw_input_capped_by_free_elsewhere(self):
        w = self.world
        w.add_warehouse("wh_home", w.home, {"forage": 100}, capacity=100000)
        self._forage_fab(self.remote)
        self.publish()
        self.assertEqual(
            site_requests(w, "outpost_2")["forage"], (site_supply.SITE_STOCK_TARGETS["fabricator"]["forage"], 100)
        )

    def test_no_raw_input_anywhere_no_request(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote)
        self._forage_fab(self.remote)
        self.publish()
        # only the buffer-tier stockpile, no need-tier pull
        self.assertEqual(
            site_requests(w, "outpost_2").get("forage"), (site_supply.SITE_STOCK_TARGETS["fabricator"]["forage"], 0)
        )

    def test_fab_site_stocks_forage_buffer(self):
        w = self.world
        w.add_warehouse("wh_home", w.home, {"forage": 5000}, capacity=100000)
        w.add_fabricator("fabricator_2", self.remote)
        self.publish()
        self.assertEqual(
            site_requests(w, "outpost_2").get("forage"), (site_supply.SITE_STOCK_TARGETS["fabricator"]["forage"], 0)
        )


class ConstructionStockTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.remote = self.world.add_outpost("outpost_2")
        disable_ingot_buffer(self.world)
        self.world.services["journal"] = Journal(
            [Site("water")] * 7
            + [
                Site("water", machine="wp1"),
                Site("thermal"),
                Site("exotic", medium="gas"),
                Site("exotic", machine="cap9", medium="liquid"),
                Site("mineral"),
            ]
        )

    def test_untapped_kits_capped(self):
        targets, needs = site_supply.construction_stock_targets(production.SourceCache())
        self.assertEqual(targets["water_pump"], site_supply.CONSTRUCTION_KIT_CAP)
        self.assertEqual(targets["thermal_cap_kit"], 1)
        self.assertEqual(targets["exotic_gas_cap_kit"], 1)
        self.assertNotIn("exotic_spring_tap_kit", targets)
        self.assertNotIn("power_line_bridge", targets)
        self.assertEqual(targets["liquid_pipe_segment"], 25)
        self.assertEqual(needs, {"gas_pipe_segment": 5, "liquid_pipe_segment": 5, "power_line_segment": 5})

    def test_seeds_defaults_once_and_keeps_edits(self):
        w = self.world
        self.assertEqual(site_supply.construction_stock_levels()["gas_pipe_bridge"], (2, 0))
        self.assertEqual(
            w.notebook.data[site_supply.CONSTRUCTION_STOCK_KEY]["gas_pipe_segment"], {"target": 25, "need": 5}
        )
        w.notebook.set(site_supply.CONSTRUCTION_STOCK_KEY, {"gas_pipe_segment": {"target": 40, "need": 60}})
        self.assertEqual(site_supply.construction_stock_levels(), {"gas_pipe_segment": (40, 40)})

    def test_mining_drill_phase_raises_unedited_stock(self):
        w = self.world
        self.assertEqual(site_supply.construction_stock_levels()["gas_pipe_segment"], (25, 5))
        with mock.patch.object(site_supply, "upgrade_phase_reached", return_value=True):
            self.assertEqual(site_supply.construction_stock_levels()["gas_pipe_segment"], (100, 10))
            self.assertEqual(site_supply.construction_stock_levels()["liquid_pipe_bridge"], (5, 0))
            w.notebook.set(site_supply.CONSTRUCTION_STOCK_KEY, {"gas_pipe_segment": {"target": 25, "need": 5}})
            self.assertEqual(site_supply.construction_stock_levels(), {"gas_pipe_segment": (25, 5)})  # edited: kept

    def test_no_exotic_kits_once_wildlife_complete(self):
        self.world.notebook.data["wildlife.plan"] = {"complete": True}
        targets, _needs = site_supply.construction_stock_targets(production.SourceCache())
        self.assertNotIn("exotic_gas_cap_kit", targets)
        self.assertEqual(targets["thermal_cap_kit"], 1)

    def test_backlog_order_for_craftable_items_only(self):
        w = self.world
        w.add_fabricator(
            "fabricator_1",
            w.home,
            FABRICATOR_RECIPES + [Recipe("craft_thermal_cap_kit", {"iron_ingot": 2}, "thermal_cap_kit")],
        )
        site_supply.publish_site_requests(w.clock.now)
        order = production.get_orders()[site_supply.CONSTRUCTION_STOCK_REQUESTER]
        self.assertEqual(order.get("thermal_cap_kit"), [[1, priority.STOCK]])
        self.assertEqual(order.get("gas_pipe_segment"), [[5, priority.NEED], [20, priority.STOCK]])
        self.assertNotIn("water_pump", order)  # no Fabricator recipe for it here
        self.assertNotIn("gas_pipe_bridge", order)  # no Fabricator recipe for it here

    def test_constructor_home_requests_the_stock(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote, {"liquid_pipe_segment": 30})
        site_supply.publish_site_requests(w.clock.now)
        self.assertEqual(site_requests(w, "home").get("liquid_pipe_segment"), (25, 5))
        self.assertNotIn("liquid_pipe_segment", site_requests(w, "outpost_2"))


if __name__ == "__main__":
    unittest.main()
