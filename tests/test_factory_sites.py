"""Stub tests for per-site demand and order trees (E6: production site targets,
5_steampower lib/site_plan.py, consumer hauling), the role switch drain (E5:
stranded ore eviction) and Supply Docks at fab outposts (E7)."""
import unittest

from harness import StubTestCase, production, fabricator, logistics_requests, site_supply, site_plan, supply_dock


def requests_by(world, outpost_id, requester):
    requests = logistics_requests.active_requests(world.clock.now).get(outpost_id, {})
    return {item_id: (e["target"], logistics_requests.request_min(e)) for item_id, e in requests.items() if e.get("by") == requester}


def only_target(world, item_id, qty):
    world.notebook.set(production.FABRICATOR_STOCK_TARGETS_KEY, {item_id: qty})


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
        w.add_supply_dock("supply_dock_2", self.remote)
        w.add_order("o1", {"steel_plate": 5})
        w.add_order("o2", {"gas_pipe_segment": 5})
        self.assertEqual(supply_dock.plan_dock_assignments(), {"supply_dock_2": "o2"})


if __name__ == "__main__":
    unittest.main()
