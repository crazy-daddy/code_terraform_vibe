"""Stub tests for per-site demand and order trees (E6: production site targets,
lib/site_plan.py, consumer hauling), the role switch drain (E5:
stranded ore eviction) and Supply Docks at fab outposts (E7)."""
import unittest
from unittest import mock

from harness import StubTestCase, home_order, production, fabricator, logistics_requests, site_supply, site_plan, supply_dock
from game_stubs import Recipe, Store
import fleet_status


def requests_by(world, outpost_id, requester):
    requests = logistics_requests.active_requests(world.clock.now).get(outpost_id, {})
    return {item_id: (e["target"], logistics_requests.request_min(e)) for item_id, e in requests.items() if e.get("by") == requester}


def only_target(world, item_id, qty):
    home_order({item_id: qty})


class SiteTargetTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.remote = self.world.add_outpost("outpost_2")

    def test_site_stock_counts_only_for_its_own_trees(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote, {"gas_pipe_segment": 4})
        f1 = w.add_fabricator("fabricator_1", w.home)
        f2 = w.add_fabricator("fabricator_2", self.remote)
        f1.recipe = f2.recipe = "craft_gas_pipe_segment"
        only_target(w, "gas_pipe_segment", 10)
        w.notebook.set(production.SITE_PLAN_KEY, {"gas_pipe_segment": ["outpost_2"]})
        # 6 left network-wide, all at outpost_2 on top of its 4 local pipes.
        self.assertEqual(production.get_site_fabricator_targets("outpost_2"), {"gas_pipe_segment": 10})
        self.assertEqual(production.get_site_fabricator_targets("home"), {})
        self.assertEqual(production.get_fabricator_active_recipe(f2)[1], 6)
        self.assertEqual(production.get_fabricator_active_recipe(f1)[1], 0)

    def test_site_targets_shared_while_fresh(self):
        w = self.world
        w.add_fabricator("fabricator_1", w.home)
        w.add_fabricator("fabricator_2", self.remote)
        only_target(w, "gas_pipe_segment", 10)
        w.notebook.set(production.SITE_PLAN_KEY, {"gas_pipe_segment": ["outpost_2"]})
        self.assertEqual(production.get_site_fabricator_targets("outpost_2"), {"gas_pipe_segment": 10})
        only_target(w, "gas_pipe_segment", 20)
        # Another script within SITE_TARGETS_FRESH_TICKS reuses the shared result.
        self.assertEqual(production.get_site_fabricator_targets("outpost_2"), {"gas_pipe_segment": 10})
        # Another script holds the lease: the stale result is used, not computed again.
        w.clock.now += production.SITE_TARGETS_FRESH_TICKS + 1
        shared = w.notebook.data[production.SITE_TARGETS_KEY]
        shared["outpost_2"]["lease"] = w.clock.now - 1
        self.assertEqual(production.get_site_fabricator_targets("outpost_2"), {"gas_pipe_segment": 10})
        # Lease expired: recomputed and shared again.
        w.clock.now += production.SITE_TARGETS_LEASE_TICKS + 1
        self.assertEqual(production.get_site_fabricator_targets("outpost_2"), {"gas_pipe_segment": 20})
        self.assertNotIn("lease", w.notebook.data[production.SITE_TARGETS_KEY]["outpost_2"])
        # A changed site plan is not served from the old result.
        w.notebook.set(production.SITE_PLAN_KEY, {"gas_pipe_segment": ["home"]})
        self.assertEqual(production.get_site_fabricator_targets("outpost_2"), {})

    def test_home_only_uses_global_targets(self):
        w = self.world
        w.add_fabricator("fabricator_1", w.home)
        w.notebook.set(production.SITE_PLAN_KEY, {"gas_pipe_segment": ["outpost_2"]})
        self.assertEqual(production.get_site_fabricator_targets("home"), production.get_fabricator_targets())

    def test_choose_recipe_skips_roots_planned_elsewhere(self):
        w = self.world
        w.inventory.add("iron_ingot", 100)
        f1 = w.add_fabricator("fabricator_1", w.home)
        w.add_fabricator("fabricator_2", self.remote)
        only_target(w, "gas_pipe_segment", 10)
        w.notebook.set(production.SITE_PLAN_KEY, {"gas_pipe_segment": ["outpost_2"]})
        self.assertIsNone(fabricator.FabricatorController(f1).choose_recipe())
        w.notebook.set(production.SITE_PLAN_KEY, {"gas_pipe_segment": ["home"]})
        recipe = fabricator.FabricatorController(f1).choose_recipe()
        self.assertEqual(getattr(recipe, "id", None), "craft_gas_pipe_segment")


class SitePlanTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.remote = self.world.add_outpost("outpost_2")

    def test_small_root_one_site_large_root_split(self):
        w = self.world
        w.add_fabricator("fabricator_1", w.home)
        w.add_fabricator("fabricator_2", self.remote)
        only_target(w, "gas_pipe_segment", 10)
        self.assertEqual(site_plan.plan_sites(), {"gas_pipe_segment": ["home"]})
        w.notebook.set(production.SITE_PLAN_KEY, {})
        only_target(w, "gas_pipe_segment", 50)
        self.assertEqual(site_plan.plan_sites(), {"gas_pipe_segment": ["home", "outpost_2"]})

    def test_dock_order_builds_at_the_dock_site(self):
        w = self.world
        w.add_fabricator("fabricator_1", w.home)
        w.add_fabricator("fabricator_2", self.remote)
        only_target(w, "gas_pipe_segment", 0)
        w.add_supply_dock("supply_dock_2", self.remote).order = w.add_order("o1", {"steel_plate": 5})
        self.assertEqual(site_plan.plan_sites(), {"steel_plate": ["outpost_2"]})

    def test_sticky_until_built_and_dead_sites_dropped(self):
        w = self.world
        w.add_fabricator("fabricator_1", w.home)
        w.add_fabricator("fabricator_2", self.remote)
        w.add_fabricator("fabricator_3", w.add_outpost("outpost_3"))
        only_target(w, "gas_pipe_segment", 10)
        w.notebook.set(production.SITE_PLAN_KEY, {"gas_pipe_segment": ["outpost_3", "outpost_2"]})
        self.assertEqual(site_plan.plan_sites(), {"gas_pipe_segment": ["outpost_3", "outpost_2"]})
        del w.components["fabricator_3"]
        self.assertEqual(site_plan.plan_sites(), {"gas_pipe_segment": ["outpost_2"]})
        w.add_warehouse("wh_remote", self.remote, {"gas_pipe_segment": 10})
        self.assertEqual(site_plan.plan_sites(), {})
        self.assertEqual(w.notebook.data[production.SITE_PLAN_KEY], {})

    def test_cleared_with_fabricators_at_home_only(self):
        w = self.world
        w.add_fabricator("fabricator_1", w.home)
        w.notebook.set(production.SITE_PLAN_KEY, {"gas_pipe_segment": ["outpost_2"]})
        self.assertEqual(site_plan.plan_sites(), {})
        self.assertEqual(w.notebook.data[production.SITE_PLAN_KEY], {})


class ConsumerHaulingTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.remote = self.world.add_outpost("outpost_2")
        # blueprint-material hauling alone; the construction stock and the site stockpiles have their own tests (test_site_supply.py)
        self.world.notebook.set(site_supply.CONSTRUCTION_STOCK_KEY, {})
        patcher = mock.patch.dict(site_supply.SITE_STOCK_TARGETS, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def publish(self):
        return site_supply.publish_site_requests(self.world.clock.now)

    def test_home_pulls_roots_built_at_a_fab_site(self):
        w = self.world
        w.inventory.add("gas_pipe_segment", 3)
        w.add_warehouse("wh_remote", self.remote, {"gas_pipe_segment": 5})
        w.add_fabricator("fabricator_2", self.remote)
        only_target(w, "gas_pipe_segment", 10)
        self.publish()
        # Home consumes 10, holds 3: pulls all 5 free at the fab site.
        self.assertEqual(requests_by(w, "home", site_supply.SITE_SUPPLY_REQUESTER), {"gas_pipe_segment": (8, 8)})

    def test_dock_site_pulls_order_items(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote)
        w.add_warehouse("wh_home", w.home)
        w.add_fabricator("fabricator_1", w.home)
        w.inventory.add("steel_plate", 9)
        only_target(w, "gas_pipe_segment", 0)
        w.add_supply_dock("supply_dock_2", self.remote).order = w.add_order("o1", {"steel_plate": 5})
        self.publish()
        self.assertEqual(requests_by(w, "outpost_2", site_supply.SITE_SUPPLY_REQUESTER), {"steel_plate": (5, 5)})

    def test_nothing_pulled_with_every_fabricator_at_home(self):
        w = self.world
        w.add_fabricator("fabricator_1", w.home)
        w.add_warehouse("wh_remote", self.remote, {"gas_pipe_segment": 5})
        only_target(w, "gas_pipe_segment", 10)
        self.publish()
        self.assertEqual(w.notebook.get(logistics_requests.REQUESTS_KEY, {}), {})

    def test_builder_site_pulls_blueprint_material_from_any_outpost(self):
        w = self.world
        w.add_warehouse("wh_home", w.home, {"liquid_pipe_bridge": 1})
        w.add_warehouse("wh_remote", self.remote)
        w.add_fabricator("fabricator_2", self.remote)
        only_target(w, "gas_pipe_segment", 0)
        w.notebook.set(fleet_status.FLEET_STATUS_KEY, {"pioneer_2": {"role": "constructor", "home": "outpost_2", "tick": 1}})
        w.add_blueprint("liquid_bridge_blueprint_9", "liquid_pipe_bridge")
        self.publish()
        # Home has no Smelter/Fabricator, still a source for blueprint material.
        self.assertEqual(requests_by(w, "outpost_2", site_supply.SITE_SUPPLY_REQUESTER), {"liquid_pipe_bridge": (1, 1)})
        self.assertEqual(requests_by(w, "home", site_supply.SITE_SUPPLY_REQUESTER), {})

    def test_blueprint_material_stays_at_builder_site(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote, {"liquid_pipe_bridge": 1})
        w.add_fabricator("fabricator_2", self.remote)
        only_target(w, "gas_pipe_segment", 0)
        w.notebook.set(fleet_status.FLEET_STATUS_KEY, {"pioneer_2": {"role": "constructor", "home": "outpost_2", "tick": 1}})
        w.add_blueprint("liquid_bridge_blueprint_9", "liquid_pipe_bridge")
        self.publish()
        self.assertEqual(w.notebook.get(logistics_requests.REQUESTS_KEY, {}), {})

    def test_settled_blueprint_material_is_urgent(self):
        w = self.world
        w.add_warehouse("wh_home", w.home, {"liquid_pipe_bridge": 1})
        w.add_warehouse("wh_remote", self.remote)
        w.add_fabricator("fabricator_2", self.remote)
        only_target(w, "gas_pipe_segment", 0)
        w.notebook.set(fleet_status.FLEET_STATUS_KEY, {"pioneer_2": {"role": "constructor", "home": "outpost_2", "tick": 1}})
        w.add_blueprint("liquid_bridge_blueprint_9", "liquid_pipe_bridge")
        self.publish()
        self.assertEqual(logistics_requests.urgent_items("outpost_2", w.clock.now), {"liquid_pipe_bridge"})

    def test_blueprint_material_still_to_build_is_not_urgent(self):
        w = self.world
        w.add_warehouse("wh_home", w.home, {"liquid_pipe_bridge": 1})
        w.add_warehouse("wh_remote", self.remote)
        bridge = Recipe("craft_liquid_pipe_bridge", {"liquid_pipe_segment": 2}, "liquid_pipe_bridge", duration_game_hours=0.1)
        w.add_fabricator("fabricator_2", self.remote, [bridge])
        only_target(w, "gas_pipe_segment", 0)
        w.notebook.set(fleet_status.FLEET_STATUS_KEY, {"pioneer_2": {"role": "constructor", "home": "outpost_2", "tick": 1}})
        w.add_blueprint("bp_1", "liquid_pipe_bridge")
        w.add_blueprint("bp_2", "liquid_pipe_bridge")
        self.publish()
        # One of two exists, one is still to build: wait for the batch.
        self.assertEqual(requests_by(w, "outpost_2", site_supply.SITE_SUPPLY_REQUESTER)["liquid_pipe_bridge"], (1, 1))
        self.assertEqual(logistics_requests.urgent_items("outpost_2", w.clock.now), set())

    def test_manual_transit_order_is_urgent_at_home(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote, {"lead_cask": 2})
        w.add_fabricator("fabricator_2", self.remote)
        only_target(w, "gas_pipe_segment", 0)
        w.notebook.set(production.MANUAL_TRANSIT_KEY, {"lead_cask": {"units": 2, "base": 0}})
        self.publish()
        self.assertIn("lead_cask", logistics_requests.urgent_items(w.home.id, w.clock.now))


class StrandedOreTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.remote = self.world.add_outpost("outpost_2")

    def publish(self):
        return site_supply.publish_site_requests(self.world.clock.now)

    def test_ore_left_by_removed_smelters_is_evicted_after_a_while(self):
        w = self.world
        wh = w.add_warehouse("wh_remote", self.remote, {"iron_ore": 30})
        w.add_smelter("smelter_2", self.remote)
        self.publish()
        self.assertIn("iron_ore", requests_by(w, "outpost_2", site_supply.SITE_SUPPLY_REQUESTER))
        del w.components["smelter_2"]
        self.publish()
        self.assertEqual(requests_by(w, "outpost_2", site_supply.SITE_SUPPLY_REQUESTER), {})
        self.assertEqual(w.notebook.data[site_supply.STRANDED_KEY], {"outpost_2": {"iron_ore": w.clock.now}})
        self.assertEqual(requests_by(w, "home", site_supply.EVICT_REQUESTER), {})
        w.clock.now += site_supply.EVICT_AFTER_TICKS
        self.publish()
        self.assertEqual(requests_by(w, "home", site_supply.EVICT_REQUESTER), {"iron_ore": (30, 30)})
        wh.remove("iron_ore", 30)
        w.inventory.add("iron_ore", 30)
        self.publish()
        self.assertEqual(requests_by(w, "home", site_supply.EVICT_REQUESTER), {})
        self.assertEqual(w.notebook.data[site_supply.STRANDED_KEY], {})

    def test_ore_requested_there_is_not_stranded(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote, {"iron_ore": 30})
        logistics_requests.set_requests("outpost_2", "someone", {"iron_ore": (50, 30)}, w.clock.now)
        self.publish()
        self.assertEqual(w.notebook.data.get(site_supply.STRANDED_KEY, {}), {})

    def test_home_ore_without_home_smelter_goes_to_smelting_site(self):
        w = self.world
        w.inventory.add("iron_ore", 5000)
        w.add_warehouse("wh_remote", self.remote)
        w.add_smelter("smelter_2", self.remote)
        target = site_supply.ore_stock_target("iron_ore")
        self.publish()
        self.assertEqual(w.notebook.data[site_supply.STRANDED_KEY], {"home": {"iron_ore": w.clock.now}})
        self.assertEqual(requests_by(w, "outpost_2", site_supply.SITE_SUPPLY_REQUESTER)["iron_ore"], (target, 0))
        w.clock.now += site_supply.EVICT_AFTER_TICKS
        self.publish()
        self.assertEqual(requests_by(w, "outpost_2", site_supply.SITE_SUPPLY_REQUESTER)["iron_ore"], (5000, 0))
        self.assertEqual(requests_by(w, "home", site_supply.EVICT_REQUESTER), {})

    def test_home_ore_kept_with_home_smelter(self):
        w = self.world
        w.inventory.add("iron_ore", 5000)
        w.add_smelter("smelter_1", w.home)
        w.add_smelter("smelter_2", self.remote)
        self.publish()
        self.assertEqual(w.notebook.data.get(site_supply.STRANDED_KEY, {}), {})

    def test_remote_ore_goes_to_smelting_site_without_home_smelter(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote, {"iron_ore": 30})
        smelt = w.add_outpost("outpost_3")
        w.add_smelter("smelter_3", smelt)
        self.publish()
        w.clock.now += site_supply.EVICT_AFTER_TICKS
        self.publish()
        target = max(site_supply.ore_stock_target("iron_ore"), 30)
        self.assertEqual(requests_by(w, "outpost_3", site_supply.SITE_SUPPLY_REQUESTER)["iron_ore"][0], target)
        self.assertEqual(requests_by(w, "home", site_supply.EVICT_REQUESTER), {})

    def test_ore_a_dock_order_consumes_there_is_not_stranded(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote, {"iron_ore": 30})
        w.add_supply_dock("supply_dock_2", self.remote).order = w.add_order("o1", {"iron_ore": 20})
        self.publish()
        self.assertEqual(w.notebook.data.get(site_supply.STRANDED_KEY, {}), {})


class _Info:
    def __init__(self, category):
        self.category = category


class _Catalog:
    CATEGORIES = {"iron_ingot": "refined", "glass": "refined", "steel_plate": "crafted", "gas_pipe_segment": "crafted",
                  "battery_pack": "crafted", "bracket_kit": "construction_kit", "tar": "crafted"}

    def lookup(self, item_id):
        category = self.CATEGORIES.get(item_id)
        return _Info(category) if category else None


class StrandedGoodsTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.world.services["item_catalog"] = _Catalog()
        self.fab = self.world.add_outpost("outpost_2")
        self.world.add_warehouse("wh_fab", self.fab, capacity=100000)
        self.world.add_fabricator("fabricator_2", self.fab)

    def publish(self):
        return site_supply.publish_site_requests(self.world.clock.now)

    def test_home_ingots_and_intermediates_go_to_fab_site(self):
        w = self.world
        w.add_warehouse("wh_home", w.home, {"iron_ingot": 40, "glass": 7}, capacity=100000)
        self.publish()
        self.assertEqual(w.notebook.data[site_supply.STRANDED_KEY], {"home": {"glass": w.clock.now, "iron_ingot": w.clock.now}})
        w.clock.now += site_supply.EVICT_AFTER_TICKS
        self.publish()
        wants = requests_by(w, "outpost_2", site_supply.SITE_SUPPLY_REQUESTER)
        self.assertEqual(wants["iron_ingot"], (40, 0))
        self.assertEqual(wants["glass"], (7, 0))
        self.assertEqual(requests_by(w, "home", site_supply.EVICT_REQUESTER), {})

    def test_deployables_constructor_items_and_held_goods_stay_home(self):
        w = self.world
        w.components["fabricator_2"]._recipes.append(Recipe("craft_fertilizer", {"tar": 1, "glass": 1}, "fertilizer"))
        w.add_warehouse("wh_home", w.home, {"gas_pipe_segment": 12, "battery_pack": 3, "tar": 500}, capacity=100000)
        self.publish()
        self.assertEqual(w.notebook.data.get(site_supply.STRANDED_KEY, {}), {})

    def test_requested_goods_are_not_stranded(self):
        w = self.world
        w.add_warehouse("wh_home", w.home, {"iron_ingot": 40}, capacity=100000)
        logistics_requests.set_requests("home", "someone", {"iron_ingot": (50, 40)}, w.clock.now)
        self.publish()
        self.assertEqual(w.notebook.data.get(site_supply.STRANDED_KEY, {}), {})

    def test_home_fabricator_keeps_goods(self):
        w = self.world
        w.add_warehouse("wh_home", w.home, {"iron_ingot": 40}, capacity=100000)
        w.add_fabricator("fabricator_1", w.home)
        self.publish()
        self.assertEqual(w.notebook.data.get(site_supply.STRANDED_KEY, {}), {})

    def test_no_catalog_evicts_nothing(self):
        w = self.world
        del w.services["item_catalog"]
        w.add_warehouse("wh_home", w.home, {"iron_ingot": 40}, capacity=100000)
        self.publish()
        self.assertEqual(w.notebook.data.get(site_supply.STRANDED_KEY, {}), {})


class HomeOreRequestTests(StubTestCase):
    def test_home_requests_ore_only_with_home_smelter(self):
        w = self.world
        w.add_smelter("smelter_2", w.add_outpost("outpost_2"))
        site_supply.publish_site_requests(w.clock.now)
        self.assertNotIn("iron_ore", requests_by(w, w.home.id, site_supply.SITE_SUPPLY_REQUESTER))
        w.add_smelter("smelter_1", w.home)
        w.clock.now += site_supply.REPUBLISH_TICKS
        site_supply.publish_site_requests(w.clock.now)
        self.assertGreater(requests_by(w, w.home.id, site_supply.SITE_SUPPLY_REQUESTER)["iron_ore"][0], 0)


class RemoteSupplyDockTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.remote = self.world.add_outpost("outpost_2")
        self.world.add_smelter("smelter_1", self.world.home)
        self.world.add_fabricator("fabricator_1", self.world.home)

    def test_discovery_is_network_wide(self):
        w = self.world
        w.add_supply_dock("supply_dock_1", w.home)
        w.add_supply_dock("supply_dock_2", self.remote)
        self.assertEqual(sorted(production.discover_supply_dock_ids()), ["supply_dock_1", "supply_dock_2"])

    def test_remote_dock_loads_only_local_stock(self):
        w = self.world
        w.inventory.add("gas_pipe_segment", 100)
        w.add_warehouse("wh_remote", self.remote, {"gas_pipe_segment": 3})
        dock = w.add_supply_dock("supply_dock_2", self.remote)
        dock.order = w.add_order("o1", {"gas_pipe_segment": 5})
        supply_dock.SupplyDockController(dock).step()
        self.assertEqual(dock.input.connected_id(), "wh_remote")
        self.assertEqual(dock.count("gas_pipe_segment"), 3)
        self.assertEqual(w.inventory.count("gas_pipe_segment"), 100)

    def test_remote_dock_drains_to_local_warehouse(self):
        w = self.world
        wh = w.add_warehouse("wh_remote", self.remote)
        dock = w.add_supply_dock("supply_dock_2", self.remote)
        dock.input_buffer["glass"] = 4
        supply_dock.SupplyDockController(dock).drain_dock_cargo()
        self.assertEqual(wh.count("glass"), 4)
        self.assertEqual(dock.total(), 0)

    def test_planner_prefers_order_stocked_at_the_dock_site(self):
        w = self.world
        # Both fully stocked at home (equal priority); only o2's items sit at the dock site.
        w.inventory.add("steel_plate", 5)
        w.inventory.add("gas_pipe_segment", 5)
        w.add_warehouse("wh_remote", self.remote, {"gas_pipe_segment": 5})
        w.add_fabricator("fabricator_2", self.remote)
        w.add_supply_dock("supply_dock_2", self.remote)
        w.add_order("o1", {"steel_plate": 5})
        w.add_order("o2", {"gas_pipe_segment": 5})
        self.assertEqual(supply_dock.plan_dock_assignments(), {"supply_dock_2": "o2"})

    def test_planner_joins_order_stocked_at_the_dock_site(self):
        # Another outpost's dock already holds o_high; local stock beats spreading across outposts.
        w = self.world
        w.inventory.add("steel_plate", 5)
        w.inventory.add("gas_pipe_segment", 5)
        w.add_warehouse("wh_remote", self.remote, {"steel_plate": 5})
        w.add_fabricator("fabricator_1", w.home)
        w.add_fabricator("fabricator_2", self.remote)
        home_dock = w.add_supply_dock("supply_dock_1", w.home)
        w.add_supply_dock("supply_dock_2", self.remote)
        home_dock.order = w.add_order("o_high", {"steel_plate": 5})
        home_dock.order.reward_kind = "tech"
        w.add_order("o_low", {"gas_pipe_segment": 5})
        self.assertEqual(supply_dock.plan_dock_assignments(), {"supply_dock_1": "o_high", "supply_dock_2": "o_high"})

    def test_planner_spreads_docks_inside_one_outpost(self):
        w = self.world
        w.inventory.add("steel_plate", 5)
        w.inventory.add("gas_pipe_segment", 5)
        w.add_fabricator("fabricator_2", self.remote)
        w.add_supply_dock("supply_dock_2", self.remote)
        w.add_supply_dock("supply_dock_3", self.remote)
        w.add_order("o_high", {"steel_plate": 5}).reward_kind = "tech"
        w.add_order("o_low", {"gas_pipe_segment": 5})
        self.assertEqual(supply_dock.plan_dock_assignments(), {"supply_dock_2": "o_high", "supply_dock_3": "o_low"})

    def test_local_stock_promised_to_one_dock_is_not_counted_twice(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote, {"steel_plate": 5})
        order = w.add_order("o1", {"steel_plate": 5})
        rank, claim = supply_dock._local_supply(order, self.remote)
        self.assertEqual((rank, claim), (supply_dock.LOCAL_STOCK_STEPS, {"steel_plate": 5}))
        promised = {}
        supply_dock._promise(promised, self.remote, claim)
        self.assertEqual(supply_dock._local_supply(order, self.remote, promised=promised), (0, {}))

    def test_weekly_order_counts_local_stock_only_when_fully_covered(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote, {"steel_plate": 4})
        order = w.add_order("o_weekly", {"steel_plate": 5})
        order.kind = "weekly"
        self.assertEqual(supply_dock._local_supply(order, self.remote), (0, {}))
        order.requires = {"steel_plate": 4}
        self.assertEqual(supply_dock._local_supply(order, self.remote)[0], supply_dock.LOCAL_STOCK_STEPS)

    def test_planner_prioritizes_local_uranium_over_unstocked_tech_order(self):
        w = self.world
        _Cask(w, "lead_cask_1", w.home, material="raw_uranium", count=20)
        dock = w.add_supply_dock("supply_dock_1", w.home)
        o_tech = w.add_order("o_tech", {"advanced_circuit": 10})
        o_tech.reward_kind = "tech"
        w.add_fabricator("fabricator_1", w.home, recipes=[Recipe("craft_circuit", {}, "advanced_circuit")])
        o_uranium = w.add_order("o_uranium", {"raw_uranium": 20})
        self.assertEqual(supply_dock.plan_dock_assignments(), {"supply_dock_1": "o_uranium"})

    def test_controller_step_switches_empty_order_to_order_with_local_uranium(self):
        w = self.world
        _Cask(w, "lead_cask_1", w.home, material="raw_uranium", count=20)
        dock = w.add_supply_dock("supply_dock_1", w.home)
        o_tech = w.add_order("o_tech", {"advanced_circuit": 10})
        o_tech.reward_kind = "tech"
        w.add_fabricator("fabricator_1", w.home, recipes=[Recipe("craft_circuit", {}, "advanced_circuit")])
        dock.order = o_tech
        o_uranium = w.add_order("o_uranium", {"raw_uranium": 20})
        supply_dock.plan_dock_assignments()
        ctrl = supply_dock.SupplyDockController(dock)
        ctrl.step()
        self.assertEqual(getattr(dock.current_order(), "id", None), "o_uranium")

    def test_empty_dock_keeps_unstocked_order_without_cask_cargo(self):
        # The held order drives Fabricator demand (production._all_dock_orders()),
        # so an empty dock with nothing in a local cask must not drop it for a stocked order.
        w = self.world
        dock = w.add_supply_dock("supply_dock_1", w.home)
        o_tech = w.add_order("o_tech", {"advanced_circuit": 10})
        o_tech.reward_kind = "tech"
        w.add_fabricator("fabricator_1", w.home, recipes=[Recipe("craft_circuit", {}, "advanced_circuit")])
        dock.order = o_tech
        w.inventory.add("steel_plate", 5)
        w.add_order("o_steel", {"steel_plate": 5})
        self.assertEqual(supply_dock.plan_dock_assignments(), {"supply_dock_1": "o_tech"})

    def test_key_unlock_order_beats_a_stocked_order(self):
        w = self.world
        w.add_supply_dock("supply_dock_1", w.home)
        w.inventory.add("steel_plate", 5)
        w.add_order("o_steel", {"steel_plate": 5})
        w.inventory.add("iron_ingot", 10)
        w.add_order("helios_01", {"iron_ingot": 150})
        self.assertEqual(supply_dock.plan_dock_assignments(), {"supply_dock_1": "helios_01"})

    def test_empty_dock_leaves_its_order_for_a_key_order(self):
        w = self.world
        dock = w.add_supply_dock("supply_dock_1", w.home)
        w.inventory.add("steel_plate", 5)
        w.inventory.add("iron_ingot", 10)
        dock.order = w.add_order("o_steel", {"steel_plate": 5})
        w.add_order("helios_01", {"iron_ingot": 150})
        self.assertEqual(supply_dock.plan_dock_assignments(), {"supply_dock_1": "helios_01"})

    def test_loaded_dock_keeps_its_order_over_a_key_order(self):
        w = self.world
        dock = w.add_supply_dock("supply_dock_1", w.home)
        dock.order = w.add_order("o_steel", {"steel_plate": 5})
        dock.input_buffer["steel_plate"] = 2
        w.inventory.add("steel_plate", 3)
        w.inventory.add("iron_ingot", 10)
        w.add_order("helios_01", {"iron_ingot": 150})
        self.assertEqual(supply_dock.plan_dock_assignments(), {"supply_dock_1": "o_steel"})

    def test_hot_readiness_counts_cask_stock(self):
        w = self.world
        _Cask(w, "lead_cask_1", w.home, material="raw_uranium", count=10)
        order = w.add_order("o_uranium", {"raw_uranium": 20})
        self.assertEqual(supply_dock._order_readiness(order, {}), (10, 20))


class DockRoleTests(StubTestCase):
    """Dock site roles (lib/supply_dock.py DockRoles): Fabricator -> crafted
    items, Smelter or resource marker -> ore/ingots, Lead Cask -> hot items."""

    def setUp(self):
        super().setUp()
        self.nuclear = self.world.add_outpost("outpost_nuclear")
        self.world.add_smelter("smelter_1", self.world.home)
        self.world.add_fabricator("fabricator_1", self.world.home)
        self.world.inventory.add("steel_plate", 5)
        _Cask(self.world, "lead_cask_1", self.nuclear, material="fuel_rod", count=10)

    def test_nuclear_dock_skips_crafted_only_order(self):
        w = self.world
        w.add_supply_dock("supply_dock_nuclear", self.nuclear)
        w.add_order("o_steel", {"steel_plate": 5})
        self.assertEqual(supply_dock.plan_dock_assignments(), {"supply_dock_nuclear": None})

    def test_crafted_order_goes_to_the_fab_site_dock(self):
        w = self.world
        w.add_supply_dock("supply_dock_nuclear", self.nuclear)
        w.add_supply_dock("supply_dock_home", w.home)
        w.add_order("o_steel", {"steel_plate": 5})
        self.assertEqual(supply_dock.plan_dock_assignments(), {"supply_dock_nuclear": None, "supply_dock_home": "o_steel"})

    def test_nuclear_dock_takes_mixed_order_and_pulls_crafted_part(self):
        w = self.world
        w.add_warehouse("wh_nuclear", self.nuclear)
        w.add_warehouse("wh_home", w.home)
        dock = w.add_supply_dock("supply_dock_nuclear", self.nuclear)
        w.add_order("o_mixed", {"fuel_rod": 10, "steel_plate": 5})
        self.assertEqual(supply_dock.plan_dock_assignments(), {"supply_dock_nuclear": "o_mixed"})
        dock.order = w.services["orders"].orders["o_mixed"]
        site_supply.publish_site_requests(w.clock.now)
        self.assertEqual(requests_by(w, "outpost_nuclear", site_supply.SITE_SUPPLY_REQUESTER).get("steel_plate"), (5, 5))

    def test_empty_dock_releases_order_its_site_covers_nothing_of(self):
        w = self.world
        dock = w.add_supply_dock("supply_dock_nuclear", self.nuclear)
        dock.order = w.add_order("o_steel", {"steel_plate": 5})
        self.assertEqual(supply_dock.plan_dock_assignments(), {"supply_dock_nuclear": None})
        supply_dock.SupplyDockController(dock).step()
        self.assertIsNone(dock.current_order())

    def test_loaded_dock_keeps_off_role_order(self):
        w = self.world
        dock = w.add_supply_dock("supply_dock_nuclear", self.nuclear)
        dock.order = w.add_order("o_steel", {"steel_plate": 5})
        dock.input_buffer["steel_plate"] = 2
        self.assertEqual(supply_dock.plan_dock_assignments(), {"supply_dock_nuclear": "o_steel"})

    def test_order_without_role_bound_items_goes_anywhere(self):
        w = self.world
        w.add_supply_dock("supply_dock_nuclear", self.nuclear)
        w.inventory.add("biomass", 5)
        w.add_order("o_bio", {"biomass": 5})
        self.assertEqual(supply_dock.plan_dock_assignments(), {"supply_dock_nuclear": "o_bio"})

    def test_resource_marker_makes_a_mining_site_for_that_ore(self):
        w = self.world
        mine = w.add_outpost("outpost_mine")
        _Markers(w).add("resource.poi_1_1", "Iron Ore - Rich", "outpost_mine")
        w.add_warehouse("wh_mine", mine, {"iron_ore": 20})
        w.add_supply_dock("supply_dock_mine", mine)
        w.add_order("o_iron", {"iron_ore": 5})
        w.add_order("o_silicon", {"silicon": 5})
        # Network stock makes both orders fulfillable (can_fulfill_order()).
        w.inventory.add("iron_ore", 5)
        w.inventory.add("silicon", 5)
        self.assertEqual(supply_dock.plan_dock_assignments(), {"supply_dock_mine": "o_iron"})
        roles = supply_dock.DockRoles()
        self.assertFalse(roles.covers("silicon", mine))
        self.assertTrue(roles.covers("iron_ore", mine))

    def test_marker_mining_site_is_a_pull_source(self):
        w = self.world
        mine = w.add_outpost("outpost_mine")
        _Markers(w).add("resource.poi_1_1", "Iron Ore - Rich", "outpost_mine")
        w.add_warehouse("wh_mine", mine, {"iron_ore": 20})
        w.add_warehouse("wh_nuclear", self.nuclear)
        dock = w.add_supply_dock("supply_dock_nuclear", self.nuclear)
        dock.order = w.add_order("o_iron", {"iron_ore": 5})
        site_supply.publish_site_requests(w.clock.now)
        entry = logistics_requests.active_requests(w.clock.now).get("outpost_nuclear", {}).get("iron_ore")
        self.assertIsNotNone(entry)
        self.assertGreaterEqual(logistics_requests.request_min(entry), 5)

    def test_smelting_site_ore_request_keeps_dock_need(self):
        w = self.world
        w.add_warehouse("wh_home", w.home, {"iron_ore": 20})
        w.add_warehouse("wh_nuclear", self.nuclear)
        w.add_smelter("smelter_n", self.nuclear)
        dock = w.add_supply_dock("supply_dock_nuclear", self.nuclear)
        dock.order = w.add_order("o_iron", {"iron_ore": 5})
        site_supply.publish_site_requests(w.clock.now)
        entry = logistics_requests.active_requests(w.clock.now).get("outpost_nuclear", {}).get("iron_ore")
        self.assertGreaterEqual(logistics_requests.request_min(entry), 5)


class _Marker:
    def __init__(self, marker_id, label, note):
        self.id = marker_id
        self.label = label
        self.note = note


class _Markers:
    def __init__(self, world):
        self.items = {}
        world.components["markers"] = self

    def add(self, marker_id, label, note):
        self.items[marker_id] = _Marker(marker_id, label, note)

    def get(self, marker_id):
        return self.items.get(marker_id)

    def list(self, prefix=""):
        return [m for i, m in self.items.items() if i.startswith(prefix)]


class _Cask(Store):
    type_id = "lead_cask"

    def __init__(self, world, cask_id, outpost, material="", count=0, capacity=100):
        super().__init__(world, cask_id, "lead_cask", outpost, capacity=capacity, items={material: count} if material and count > 0 else {})
        self.id = cask_id
        world.components[cask_id] = self

    def material(self):
        m = [i for i, n in self.items.items() if n > 0]
        return m[0] if m else ""


if __name__ == "__main__":
    unittest.main()
