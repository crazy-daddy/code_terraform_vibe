"""Stub tests for per-site demand and order trees (E6: production site targets,
lib/site_plan.py, consumer hauling), the role switch drain (E5:
stranded ore eviction) and Supply Docks at fab outposts (E7)."""

import unittest
from unittest import mock

import fleet_status
import game_stubs
import priority
import production_cascade
import production_demand
import production_demand_record
import production_sites
import storage
from game_stubs import Recipe, Store
from harness import (
    StubTestCase,
    fabricator,
    home_order,
    logistics_requests,
    production,
    request,
    site_plan,
    site_supply,
    supply_dock,
)


def requests_by(world, outpost_id, requester):
    requests = logistics_requests.active_requests(world.clock.now).get(outpost_id, {})
    return {
        item_id: (logistics_requests.request_target(e), logistics_requests.tier_level(e, priority.NEED))
        for item_id, e in requests.items()
        if e.get("by") == requester
    }


def is_urgent(entry):
    """True when a request entry carries a BLOCKER level."""
    return priority.ladder_level(logistics_requests.request_levels(entry), priority.BLOCKER) > 0


def urgent_items(world, outpost_id):
    requests = logistics_requests.active_requests(world.clock.now).get(outpost_id, {})
    return {item_id for item_id, e in requests.items() if is_urgent(e)}


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

    def test_unsourceable_input_stops_the_cascade(self):
        w = self.world
        bridge = Recipe(
            "craft_gas_pipe_bridge",
            {"gas_pipe_segment": 2, "pressure_valve": 1},
            "gas_pipe_bridge",
            duration_game_hours=0.1,
        )
        w.add_fabricator("fabricator_1", w.home, [bridge, *game_stubs.FABRICATOR_RECIPES])
        only_target(w, "gas_pipe_bridge", 3)
        store = w.add_warehouse("wh_home", w.home, {"iron_ingot": 20})
        # No Pressure Valve recipe or stock: the bridge is unbuildable, so no segments for it.
        self.assertNotIn("gas_pipe_segment", production.get_fabricator_targets())
        store.add("pressure_valve", 3)
        self.assertEqual(production.get_fabricator_targets(production.SourceCache()).get("gas_pipe_segment"), 6)

    def test_blueprint_seed_nets_constructor_cargo_not_hauler_loads(self):
        w = self.world
        w.add_blueprint("pipe_1", "gas_pipe_segment", 10)
        pioneer = w.add_pioneer("pioneer_1", w.home, cargo_capacity=100)
        pioneer.cargo.items["gas_pipe_segment"] = 4
        # Constructor load: not stock anywhere, so it comes off the demand.
        self.assertEqual(production.blueprint_required_items(), {"gas_pipe_segment": 6})
        # Hauler load: aboard_units() already counts it as stock.
        logistics_requests.reserve_pickup("pioneer_1", "home", "gas_pipe_segment", 4, w.clock.now, aboard=True)
        self.assertEqual(production.blueprint_required_items(), {"gas_pipe_segment": 10})

    def _seed_record(self, plan, ladders, have=None, now=None, ship=None):
        """Publishes a record whose outpost_2 entry is `ladders` (+ `have`), stamped `now`."""
        w = self.world
        record = production_demand_record.new_record(plan, {}, sites={"outpost_2": (ladders, ship or {}, have or {})})
        production_demand_record.publish_record(record, now=w.clock.now if now is None else now)

    def _site_world(self):
        w = self.world
        w.add_fabricator("fabricator_1", w.home)
        w.add_fabricator("fabricator_2", self.remote)
        only_target(w, "gas_pipe_segment", 10)
        plan = {"gas_pipe_segment": ["outpost_2"]}
        w.notebook.set(production.SITE_PLAN_KEY, plan)
        return plan

    def test_fresh_record_entry_is_used_not_recomputed(self):
        w = self.world
        plan = self._site_world()
        ladders = production.get_site_fabricator_ladders("outpost_2", reuse=False)
        self._seed_record(plan, ladders, ship={"pressure_valve": [2, priority.NEED]})
        only_target(w, "gas_pipe_segment", 20)
        cache = production.SourceCache()
        with mock.patch.object(production_sites, "_compute_site_fabricator_targets") as compute:
            self.assertEqual(production.get_site_fabricator_ladders("outpost_2", cache), ladders)
        compute.assert_not_called()
        self.assertEqual(cache._site_ship_plan["outpost_2"], {"pressure_valve": [2, priority.NEED]})
        self.assertEqual(production.get_site_fabricator_targets("outpost_2"), {"gas_pipe_segment": 10})

    def test_stale_record_is_still_used_never_recomputed(self):
        w = self.world
        plan = self._site_world()
        ladders = production.get_site_fabricator_ladders("outpost_2", reuse=False)
        self._seed_record(plan, ladders)
        only_target(w, "gas_pipe_segment", 20)
        w.clock.now += production_demand_record.DEMAND_FRESH_TICKS + 1
        with mock.patch.object(production_sites, "_compute_site_fabricator_targets") as compute:
            self.assertEqual(production.get_site_fabricator_targets("outpost_2"), {"gas_pipe_segment": 10})
        compute.assert_not_called()
        # Past DEMAND_MAX_STALE_TICKS the record is MISSING: computed locally, nothing published.
        w.clock.now += production_demand_record.DEMAND_MAX_STALE_TICKS
        self.assertEqual(production.get_site_fabricator_targets("outpost_2"), {"gas_pipe_segment": 20})
        self.assertNotEqual(w.notebook.data[production_demand_record.DEMAND_KEY]["tick"], w.clock.now)

    def test_missing_record_computes_locally_and_publishes_nothing(self):
        w = self.world
        self._site_world()
        self.assertEqual(production.get_site_fabricator_targets("outpost_2"), {"gas_pipe_segment": 10})
        self.assertNotIn(production_demand_record.DEMAND_KEY, w.notebook.data)
        self.assertEqual(production.get_site_fabricator_targets("outpost_2", reuse=False), {"gas_pipe_segment": 10})
        self.assertNotIn(production_demand_record.DEMAND_KEY, w.notebook.data)

    def test_site_missing_from_record_computes_locally(self):
        w = self.world
        plan = self._site_world()
        production_demand_record.publish_record(
            production_demand_record.new_record(plan, {}, sites={"other": ({}, {}, {})}), now=w.clock.now
        )
        self.assertEqual(production.get_site_fabricator_targets("outpost_2"), {"gas_pipe_segment": 10})

    def test_changed_site_plan_makes_record_missing(self):
        w = self.world
        plan = self._site_world()
        ladders = production.get_site_fabricator_ladders("outpost_2", reuse=False)
        self._seed_record(plan, ladders)
        self.assertEqual(production_demand_record.read_record(w.clock.now, plan)[1], production_demand_record.FRESH)
        other = {"gas_pipe_segment": ["home"]}
        w.notebook.set(production.SITE_PLAN_KEY, other)
        self.assertEqual(production_demand_record.read_record(w.clock.now, other)[1], production_demand_record.MISSING)
        self.assertEqual(production.get_site_fabricator_targets("outpost_2"), {})

    def test_record_net_consumed_roots(self):
        w = self.world
        store = w.add_warehouse("wh_remote", self.remote, {"gas_pipe_segment": 4})
        w.add_fabricator("fabricator_1", w.home)
        f2 = w.add_fabricator("fabricator_2", self.remote)
        f2.recipe = "craft_gas_pipe_segment"
        only_target(w, "gas_pipe_segment", 10)
        plan = {"gas_pipe_segment": ["outpost_2"]}
        w.notebook.set(production.SITE_PLAN_KEY, plan)
        self._seed_record(
            plan, production.get_site_fabricator_ladders("outpost_2", reuse=False), have={"gas_pipe_segment": 4}
        )
        self.assertEqual(production.get_site_fabricator_targets("outpost_2"), {"gas_pipe_segment": 10})
        # 3 units consumed (delivered) and the demand drops with them: the record's copy
        # comes down by 3 and matches a recompute, so no unit is crafted twice.
        store.remove("gas_pipe_segment", 3)
        only_target(w, "gas_pipe_segment", 7)
        self.assertEqual(production.get_site_fabricator_targets("outpost_2"), {"gas_pipe_segment": 7})
        self.assertEqual(production.get_fabricator_active_recipe(f2)[1], 6)
        self.assertEqual(production.get_site_fabricator_targets("outpost_2", reuse=False), {"gas_pipe_segment": 7})
        # Units arriving don't change the record's copy (10, have 4): only a recompute does.
        store.add("gas_pipe_segment", 5)
        self.assertEqual(production.get_site_fabricator_targets("outpost_2"), {"gas_pipe_segment": 10})

    def test_record_net_consumed_intermediates(self):
        w = self.world
        store = w.add_warehouse("wh_remote", self.remote, {"circuit_panel": 1})
        w.add_fabricator("fabricator_1", w.home)
        w.add_fabricator("fabricator_2", self.remote)
        plan = {"circuit_panel": ["outpost_2"]}
        w.notebook.set(production.SITE_PLAN_KEY, plan)
        targets = {"circuit_panel": [[600, 6]]}
        have = {"circuit_panel": 4}
        record = production_demand_record.new_record(plan, {}, sites={"outpost_2": (targets, {}, have)})
        production_demand_record.publish_record(record, now=w.clock.now)
        # 3 units drained since the record (4 then, 1 now): the intermediate's ladder comes down.
        self.assertEqual(production.get_site_fabricator_targets("outpost_2"), {"circuit_panel": 3})
        # A rise in stock (6 vs 4) leaves it where the record put it.
        store.add("circuit_panel", 5)
        self.assertEqual(production.get_site_fabricator_targets("outpost_2"), {"circuit_panel": 6})

    def test_recipe_depths_and_blueprint_demand_come_from_the_record(self):
        w = self.world
        record = production_demand_record.new_record(
            {}, {}, depths={"circuit_panel": 2}, blueprint={"gas_pipe_segment": 7}
        )
        production_demand_record.publish_record(record, now=w.clock.now)
        with mock.patch.object(production_cascade, "fabricator_root_targets") as roots:
            self.assertEqual(production.recipe_depths(production.SourceCache()), {"circuit_panel": 2})
        roots.assert_not_called()
        w.add_warehouse("wh_home", w.home, {"gas_pipe_segment": 3})
        with mock.patch.object(production_cascade, "blueprint_demand_items") as cascade:
            self.assertEqual(production.get_construction_material_reservations(), {"gas_pipe_segment": 3})
        cascade.assert_not_called()
        # The publishers compute both parts themselves: the record never feeds back into itself.
        self.assertEqual(production.compute_recipe_depths(production.SourceCache()), {})
        w.notebook.delete(production_demand_record.DEMAND_KEY)
        self.assertEqual(production.recipe_depths(production.SourceCache()), {})

    def test_smelter_demands_from_record(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote, {"iron_ingot": 5})
        record = production_demand_record.new_record(
            {},
            {},
            smelter_network={"iron_ingot": [[priority.NEED, 20]]},
            smelter_sites={"outpost_2": ({"iron_ingot": [[priority.NEED, 16]]}, {"iron_ingot": 5})},
        )
        # Nothing made since: the site ladder (16) stays under the network's 20.
        demands = production_demand.smelter_demands_from_record(record, self.remote, production.SourceCache())
        self.assertEqual(demands["iron_ingot"], [[priority.NEED, 20]])
        # 3 made since the record (stock 5 vs 2 then): a site ladder of 25 comes down to 22.
        record["smelter"]["sites"]["outpost_2"]["demands"]["iron_ingot"] = [[priority.NEED, 25]]
        record["smelter"]["sites"]["outpost_2"]["have"]["iron_ingot"] = 2
        demands = production_demand.smelter_demands_from_record(record, self.remote, production.SourceCache())
        self.assertEqual(demands["iron_ingot"], [[priority.NEED, 22]])
        # The network ladder is netted by the same local output: 20 - 3 = 17 beats the site's 13.
        record["smelter"]["sites"]["outpost_2"]["demands"]["iron_ingot"] = [[priority.NEED, 16]]
        demands = production_demand.smelter_demands_from_record(record, self.remote, production.SourceCache())
        self.assertEqual(demands["iron_ingot"], [[priority.NEED, 17]])
        # smelter_site_record() stores `have` for every Smelter output, demanded or not.
        w.add_smelter("smelter_2", self.remote)
        _demands, have = production_demand.smelter_site_record(self.remote, production.SourceCache())
        self.assertEqual(have.get("iron_ingot"), 5)
        self.assertIn("titanium_ingot", have)

    def _bridge_world(self, remote):
        """A gas_pipe_bridge order (2 segments + 1 valve each) at one fab site, segments in stock."""
        w = self.world
        bridge = Recipe(
            "craft_gas_pipe_bridge",
            {"gas_pipe_segment": 2, "pressure_valve": 1},
            "gas_pipe_bridge",
            duration_game_hours=0.1,
        )
        recipes = [bridge, *game_stubs.FABRICATOR_RECIPES]
        site = self.remote if remote else w.home
        assembler = w.add_fabricator("fabricator_1", site, recipes)
        maker = w.add_fabricator("fabricator_2", site, recipes)
        if remote:
            w.add_fabricator("fabricator_3", w.home, recipes)
            w.notebook.set(production.SITE_PLAN_KEY, {"gas_pipe_bridge": ["outpost_2"]})
        store = w.add_warehouse("wh_site", site, {"gas_pipe_segment": 10, "pressure_valve": 5})
        assembler.recipe = "craft_gas_pipe_bridge"
        maker.recipe = "craft_gas_pipe_segment"
        only_target(w, "gas_pipe_bridge", 5)
        return assembler, maker, store

    def _assert_staging_is_neutral(self, remote):
        assembler, maker, store = self._bridge_world(remote)
        site_id = "outpost_2" if remote else "home"
        self.assertEqual(production.get_fabricator_active_recipe(maker)[1], 0)
        # Loading 6 segments into the bridge Fabricator is no new segment shortfall.
        store.remove("gas_pipe_segment", 6)
        assembler.input_buffer["gas_pipe_segment"] = 6
        self.world.clock.now += production_demand_record.DEMAND_FRESH_TICKS + 1
        self.assertEqual(production.get_fabricator_active_recipe(maker)[1], 0)
        # A running bridge craft has used its 2 segments: 4 bridges left x 2 = 8 wanted,
        # 4 staged + 4 held -> still none to make, and the bridge target is unchanged.
        assembler.input_buffer["gas_pipe_segment"] = 4
        assembler.running = True
        self.world.clock.now += production_demand_record.DEMAND_FRESH_TICKS + 1
        self.assertEqual(production.get_fabricator_active_recipe(maker)[1], 0)
        self.assertEqual(production.get_site_fabricator_targets(site_id, reuse=False).get("gas_pipe_bridge"), 5)

    def test_staged_inputs_are_no_new_shortfall_at_home(self):
        self._assert_staging_is_neutral(remote=False)

    def test_staged_inputs_are_no_new_shortfall_at_a_site(self):
        self._assert_staging_is_neutral(remote=True)

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

    def test_home_pulls_roots_from_an_outpost_without_production(self):
        w = self.world
        w.add_fabricator("fabricator_1", w.home)
        w.add_warehouse("wh_remote", self.remote, {"gas_pipe_segment": 5})
        only_target(w, "gas_pipe_segment", 10)
        self.publish()
        # The 5 count toward the target wherever they sit, so home pulls them.
        self.assertEqual(requests_by(w, "home", site_supply.SITE_SUPPLY_REQUESTER), {"gas_pipe_segment": (5, 5)})

    def test_sited_order_is_consumed_at_its_site(self):
        w = self.world
        w.add_fabricator("fabricator_1", w.home)
        w.add_warehouse("wh_home", w.home, {"gas_pipe_segment": 5})
        w.add_warehouse("wh_remote", self.remote)
        only_target(w, "steel_plate", 0)
        production.set_order(
            supply_dock.KEY_AHEAD_REQUESTER, {"gas_pipe_segment": [5, priority.ORDER_AHEAD]}, site="outpost_2"
        )
        self.publish()
        # ORDER_AHEAD is below NEED: all 5 wanted, none needed.
        self.assertEqual(requests_by(w, "outpost_2", site_supply.SITE_SUPPLY_REQUESTER), {"gas_pipe_segment": (5, 0)})
        self.assertNotIn("gas_pipe_segment", requests_by(w, "home", site_supply.SITE_SUPPLY_REQUESTER))

    def test_no_consumer_site_and_site_requesters_leave_home_out(self):
        w = self.world
        w.add_fabricator("fabricator_1", w.home)
        w.add_warehouse("wh_remote", self.remote, {"gas_pipe_segment": 5, "machine_frame": 5})
        only_target(w, "steel_plate", 0)
        production.set_order(
            supply_dock.KEY_AHEAD_REQUESTER,
            {"gas_pipe_segment": [5, priority.ORDER_AHEAD]},
            site=production.NO_CONSUMER_SITE,
        )
        production.set_order("bio_caster", {"machine_frame": [5, priority.UPGRADE]})
        self.publish()
        home = requests_by(w, "home", site_supply.SITE_SUPPLY_REQUESTER)
        self.assertNotIn("gas_pipe_segment", home)
        self.assertNotIn("machine_frame", home)

    def test_builder_site_pulls_blueprint_material_from_any_outpost(self):
        w = self.world
        w.add_warehouse("wh_home", w.home, {"liquid_pipe_bridge": 1})
        w.add_warehouse("wh_remote", self.remote)
        w.add_fabricator("fabricator_2", self.remote)
        only_target(w, "gas_pipe_segment", 0)
        w.notebook.set(
            fleet_status.FLEET_STATUS_KEY, {"pioneer_2": {"role": "constructor", "home": "outpost_2", "tick": 1}}
        )
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
        w.notebook.set(
            fleet_status.FLEET_STATUS_KEY, {"pioneer_2": {"role": "constructor", "home": "outpost_2", "tick": 1}}
        )
        w.add_blueprint("liquid_bridge_blueprint_9", "liquid_pipe_bridge")
        self.publish()
        self.assertEqual(w.notebook.get(logistics_requests.REQUESTS_KEY, {}), {})

    def test_settled_blueprint_material_is_urgent(self):
        w = self.world
        w.add_warehouse("wh_home", w.home, {"liquid_pipe_bridge": 1})
        w.add_warehouse("wh_remote", self.remote)
        w.add_fabricator("fabricator_2", self.remote)
        only_target(w, "gas_pipe_segment", 0)
        w.notebook.set(
            fleet_status.FLEET_STATUS_KEY, {"pioneer_2": {"role": "constructor", "home": "outpost_2", "tick": 1}}
        )
        w.add_blueprint("liquid_bridge_blueprint_9", "liquid_pipe_bridge")
        self.publish()
        self.assertEqual(urgent_items(w, "outpost_2"), {"liquid_pipe_bridge"})

    def test_blueprint_material_still_to_build_is_not_urgent(self):
        w = self.world
        w.add_warehouse("wh_home", w.home, {"liquid_pipe_bridge": 1})
        w.add_warehouse("wh_remote", self.remote)
        bridge = Recipe(
            "craft_liquid_pipe_bridge", {"liquid_pipe_segment": 2}, "liquid_pipe_bridge", duration_game_hours=0.1
        )
        w.add_fabricator("fabricator_2", self.remote, [bridge])
        only_target(w, "gas_pipe_segment", 0)
        w.notebook.set(
            fleet_status.FLEET_STATUS_KEY, {"pioneer_2": {"role": "constructor", "home": "outpost_2", "tick": 1}}
        )
        w.add_blueprint("bp_1", "liquid_pipe_bridge")
        w.add_blueprint("bp_2", "liquid_pipe_bridge")
        self.publish()
        # One of two exists, one is still to build: wait for the batch.
        self.assertEqual(requests_by(w, "outpost_2", site_supply.SITE_SUPPLY_REQUESTER)["liquid_pipe_bridge"], (1, 1))
        self.assertEqual(urgent_items(w, "outpost_2"), set())

    def test_manual_transit_order_is_urgent_at_home(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote, {"lead_cask": 2})
        w.add_fabricator("fabricator_2", self.remote)
        only_target(w, "gas_pipe_segment", 0)
        w.notebook.set(production.MANUAL_TRANSIT_KEY, {"lead_cask": {"units": 2, "base": 0}})
        self.publish()
        self.assertIn("lead_cask", urgent_items(w, w.home.id))

    def reserve_world(self, home_units, home_fabricator=True):
        """Constructor at home keeping 5 steel plates as construction stock; a remote
        fab site with a Supply Dock whose order owes 3."""
        w = self.world
        w.notebook.set(site_supply.CONSTRUCTION_STOCK_KEY, {"steel_plate": {"target": 5, "need": 0}})
        w.add_warehouse("wh_home", w.home, {"steel_plate": home_units})
        w.add_warehouse("wh_remote", self.remote)
        if home_fabricator:
            w.add_fabricator("fabricator_1", w.home)
        w.add_fabricator("fabricator_2", self.remote)
        only_target(w, "gas_pipe_segment", 0)
        w.add_supply_dock("supply_dock_2", self.remote).order = w.add_order("o1", {"steel_plate": 3})
        # The second pass sees the reserve the first one published.
        self.publish()
        self.publish()

    def test_dock_order_builds_on_top_of_the_builder_reserve(self):
        w = self.world
        self.reserve_world(5)
        entry = logistics_requests.active_requests(w.clock.now)["home"]["steel_plate"]
        self.assertEqual(logistics_requests.request_keep(entry), 5)
        self.assertNotIn("steel_plate", requests_by(w, "outpost_2", site_supply.SITE_SUPPLY_REQUESTER))
        self.assertEqual(production.get_fabricator_targets()["steel_plate"], 8)

    def test_dock_order_takes_stock_above_the_builder_reserve(self):
        w = self.world
        self.reserve_world(7)
        self.assertEqual(requests_by(w, "outpost_2", site_supply.SITE_SUPPLY_REQUESTER)["steel_plate"], (2, 2))
        self.assertEqual(production.get_fabricator_targets()["steel_plate"], 8)

    def test_dock_order_takes_stock_above_the_reserve_at_a_home_without_production(self):
        w = self.world
        self.reserve_world(6, home_fabricator=False)
        # Home builds nothing; its one unit above the reserve counts toward the order, the dock site builds the other 2.
        self.assertEqual(production.get_site_fabricator_targets("outpost_2")["steel_plate"], 2)
        self.assertEqual(requests_by(w, "outpost_2", site_supply.SITE_SUPPLY_REQUESTER)["steel_plate"], (1, 1))


class StrandedOreTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.remote = self.world.add_outpost("outpost_2")

    def publish(self):
        return site_supply.publish_site_requests(self.world.clock.now)

    def add_storage_outpost(self, outpost_id="outpost_9"):
        w = self.world
        store = w.add_outpost(outpost_id)
        w.add_warehouse("wh_" + outpost_id, store, capacity=10000)
        w.add_drone_depot("depot_" + outpost_id, store)
        return store

    def test_ore_left_by_removed_smelters_goes_to_a_storage_outpost_after_a_while(self):
        w = self.world
        self.add_storage_outpost()
        wh = w.add_warehouse("wh_remote", self.remote, {"iron_ore": 30})
        w.add_smelter("smelter_2", self.remote)
        self.publish()
        self.assertIn("iron_ore", requests_by(w, "outpost_2", site_supply.SITE_SUPPLY_REQUESTER))
        del w.components["smelter_2"]
        self.publish()
        self.assertEqual(requests_by(w, "outpost_2", site_supply.SITE_SUPPLY_REQUESTER), {})
        self.assertEqual(w.notebook.data[site_supply.STRANDED_KEY], {"outpost_2": {"iron_ore": w.clock.now}})
        self.assertEqual(requests_by(w, "outpost_9", site_supply.SITE_SUPPLY_REQUESTER), {})
        w.clock.now += site_supply.EVICT_AFTER_TICKS
        self.publish()
        self.assertEqual(requests_by(w, "outpost_9", site_supply.SITE_SUPPLY_REQUESTER), {"iron_ore": (30, 0)})
        self.assertEqual(requests_by(w, "home", site_supply.EVICT_REQUESTER), {})
        wh.remove("iron_ore", 30)
        w.components["wh_outpost_9"].add("iron_ore", 30)
        self.publish()
        self.assertEqual(w.notebook.data[site_supply.STRANDED_KEY], {})

    def test_ore_without_a_user_or_storage_outpost_stays(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote, {"iron_ore": 30})
        self.publish()
        w.clock.now += site_supply.EVICT_AFTER_TICKS
        self.publish()
        self.assertEqual(w.notebook.data.get(site_supply.STRANDED_KEY, {}), {})
        requested = {i for items in logistics_requests.active_requests(w.clock.now).values() for i in items}
        self.assertNotIn("iron_ore", requested)

    def test_storage_outpost_needs_storage_a_depot_and_no_penalized_building(self):
        w = self.world
        store = self.add_storage_outpost()
        w.add_drone_depot("depot_remote", self.remote)
        w.add_warehouse("wh_remote", self.remote)
        w.add_smelter("smelter_2", self.remote)
        outposts = [w.home, self.remote, store]
        self.assertEqual([o.id for o in site_supply.storage_outposts(outposts)], ["outpost_9"])
        w.add_building("dock_9", store, "supply_dock")
        self.assertEqual(site_supply.storage_outposts(outposts), [])

    def test_ore_requested_there_is_not_stranded(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote, {"iron_ore": 30})
        logistics_requests.set_requests("outpost_2", "someone", {"iron_ore": (request(50, 30), 30)}, w.clock.now)
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
        # Up to the slot its ore target plans, filled to the stock target, not a second one; the rest stays home.
        self.assertEqual(
            requests_by(w, "outpost_2", site_supply.SITE_SUPPLY_REQUESTER)["iron_ore"],
            (storage.WAREHOUSE_STOCK_TARGET, 0),
        )
        self.assertEqual(requests_by(w, "home", site_supply.EVICT_REQUESTER), {})

    def test_eviction_leaves_staging_room_where_life_forms_are_mined(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote, {"iron_ore": 1000, "glass": 1000, "titanium": 1000}, capacity=10000)
        args = (self.remote, "cobalt", {}, w.clock.now, "home")
        self.assertEqual(site_supply.evict_room(*args), storage.WAREHOUSE_STOCK_TARGET)
        self.assertEqual(site_supply.evict_room(*args, staging=True), 0)
        fleet_status.publish(
            "drone_1", {"unit": "drone_1", "role": "miner", "home": self.remote.id, "tick": w.clock.now}
        )
        fleet_status.publish("drone_2", {"unit": "drone_2", "role": "hauler", "home": "home", "tick": w.clock.now})
        self.assertEqual(site_supply.lifeform_staging_sites(w.clock.now), {self.remote.id})

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
    CATEGORIES = {
        "iron_ingot": "refined",
        "glass": "refined",
        "steel_plate": "crafted",
        "gas_pipe_segment": "crafted",
        "battery_pack": "crafted",
        "bracket_kit": "construction_kit",
        "tar": "crafted",
    }

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
        self.assertEqual(
            w.notebook.data[site_supply.STRANDED_KEY], {"home": {"glass": w.clock.now, "iron_ingot": w.clock.now}}
        )
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
        logistics_requests.set_requests("home", "someone", {"iron_ingot": (request(50, 40), 40)}, w.clock.now)
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


class StrandedReagentTests(StubTestCase):
    def setUp(self):
        super().setUp()
        site_supply._labless_since = None
        self.remote = self.world.add_outpost("outpost_2")
        self.wh = self.world.add_warehouse("wh_remote", self.remote, {"enzyme_solution": 10, "iron_ingot": 5})

    def publish(self):
        return site_supply.publish_site_requests(self.world.clock.now)

    def add_lab(self, outpost):
        self.world.add_building("bio_lab_1", outpost, "bio_lab")

    def test_reagents_go_home_after_a_while_without_any_lab(self):
        w = self.world
        self.publish()
        self.assertEqual(w.notebook.data[site_supply.STRANDED_KEY], {"outpost_2": {"enzyme_solution": w.clock.now}})
        w.clock.now += site_supply.EVICT_AFTER_TICKS
        self.publish()
        self.assertEqual(requests_by(w, "home", site_supply.EVICT_REQUESTER), {"enzyme_solution": (10, 10)})

    def test_reagents_go_to_a_home_lab(self):
        w = self.world
        self.add_lab(w.home)
        w.clock.now += site_supply.EVICT_AFTER_TICKS
        self.publish()
        w.clock.now += site_supply.EVICT_AFTER_TICKS
        self.publish()
        self.assertEqual(requests_by(w, "home", site_supply.EVICT_REQUESTER), {"enzyme_solution": (10, 10)})

    def test_reagents_stay_as_free_stock_with_only_a_remote_lab(self):
        w = self.world
        self.add_lab(w.add_outpost("outpost_3"))
        self.publish()
        self.assertEqual(w.notebook.data.get(site_supply.STRANDED_KEY, {}), {})

    def test_requested_reagents_are_not_stranded(self):
        w = self.world
        logistics_requests.set_requests(
            "outpost_2", "bio_reagents", {"enzyme_solution": (request(10, 10), 10)}, w.clock.now
        )
        self.publish()
        self.assertEqual(w.notebook.data.get(site_supply.STRANDED_KEY, {}), {})

    def test_home_reagents_sold_after_a_while_without_any_lab(self):
        w = self.world
        w.add_warehouse("wh_home", w.home, {"enzyme_solution": 8, "iron_ingot": 5})
        w.inventory.add("enzyme_solution", 2)
        shop = w.services["shop"]
        site_supply.sell_stranded_reagents(w.clock.now)
        self.assertEqual(shop.sold, {})
        w.clock.now += site_supply.EVICT_AFTER_TICKS
        site_supply.sell_stranded_reagents(w.clock.now)
        self.assertEqual(shop.sold, {"enzyme_solution": 10})
        self.assertEqual(w.components["wh_home"].count("enzyme_solution"), 0)
        self.assertEqual(w.components["wh_home"].count("iron_ingot"), 5)
        self.assertEqual(self.wh.count("enzyme_solution"), 10)

    def test_home_reagents_kept_while_a_lab_exists(self):
        w = self.world
        self.add_lab(w.add_outpost("outpost_3"))
        w.inventory.add("enzyme_solution", 2)
        site_supply.sell_stranded_reagents(w.clock.now)
        w.clock.now += site_supply.EVICT_AFTER_TICKS
        site_supply.sell_stranded_reagents(w.clock.now)
        self.assertEqual(w.services["shop"].sold, {})


class StragglerTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.world.services["item_catalog"] = _Catalog()
        self.fab = self.world.add_outpost("outpost_2")
        self.world.add_fabricator("fabricator_2", self.fab)

    def publish(self):
        return site_supply.publish_site_requests(self.world.clock.now)

    def evict_entries(self):
        return logistics_requests.active_requests(self.world.clock.now).get("home", {})

    def test_small_leftover_without_a_storage_outpost_stays(self):
        w = self.world
        w.add_storage_bin("storage_bin_pipe", self.fab, "gas_pipe_segment", 3)
        w.add_storage_bin("storage_bin_plate", self.fab, "steel_plate", 10)
        self.publish()
        self.assertEqual(w.notebook.data[site_supply.STRANDED_KEY], {"outpost_2": {"gas_pipe_segment": w.clock.now}})
        w.clock.now += site_supply.EVICT_AFTER_TICKS
        self.publish()
        self.assertEqual(
            {i for i, e in self.evict_entries().items() if e.get("by") == site_supply.EVICT_REQUESTER}, set()
        )
        # Home is the Constructor's home: its construction stock request takes the pipes, flagged urgent.
        self.assertTrue(is_urgent(self.evict_entries()["gas_pipe_segment"]))

    def test_small_leftover_goes_to_a_storage_outpost_urgent(self):
        w = self.world
        store = w.add_outpost("outpost_9")
        w.add_warehouse("wh_store", store, capacity=10000)
        w.add_drone_depot("depot_store", store)
        w.add_storage_bin("storage_bin_plate", self.fab, "steel_plate", 10)
        self.publish()
        w.clock.now += site_supply.EVICT_AFTER_TICKS
        self.publish()
        entry = logistics_requests.active_requests(w.clock.now)["outpost_9"]["steel_plate"]
        self.assertEqual((logistics_requests.request_target(entry), is_urgent(entry)), (10, True))
        self.assertNotIn("steel_plate", self.evict_entries())

    def test_large_stock_is_no_straggler(self):
        w = self.world
        w.add_storage_bin("storage_bin_plate", self.fab, "steel_plate", site_supply.STRAGGLER_MAX_UNITS + 1)
        self.publish()
        self.assertEqual(w.notebook.data.get(site_supply.STRANDED_KEY, {}), {})

    def test_items_the_site_still_builds_with_stay(self):
        w = self.world
        w.add_storage_bin("storage_bin_plate", self.fab, "steel_plate", 10)
        with mock.patch.object(
            site_supply, "get_site_fabricator_targets", lambda site_id, cache=None: {"steel_plate": 20}
        ):
            self.publish()
        self.assertEqual(w.notebook.data.get(site_supply.STRANDED_KEY, {}), {})

    def test_constructor_items_go_to_the_constructor_home(self):
        w = self.world
        build = w.add_outpost("outpost_3")
        w.add_warehouse("wh_build", build)
        w.add_storage_bin("storage_bin_pipe", self.fab, "gas_pipe_segment", 3)
        with mock.patch.object(site_supply, "construction_site_id", lambda: "outpost_3"):
            self.publish()
            w.clock.now += site_supply.EVICT_AFTER_TICKS
            self.publish()
        entries = logistics_requests.active_requests(w.clock.now).get("outpost_3", {})
        self.assertTrue(is_urgent(entries["gas_pipe_segment"]))
        self.assertNotIn("gas_pipe_segment", self.evict_entries())

    def test_export_root_stays_while_a_local_fabricator_makes_it(self):
        w = self.world
        w.add_storage_bin("storage_bin_pipe", self.fab, "gas_pipe_segment", 3)
        w.components["fabricator_2"].output_buffer["gas_pipe_segment"] = 1
        self.publish()
        self.publish()
        self.assertEqual(w.notebook.data.get(site_supply.STRANDED_KEY, {}), {})

    def test_home_leftovers_stay(self):
        w = self.world
        w.add_warehouse("wh_home", w.home, {"steel_plate": 5}, capacity=100000)
        self.publish()
        self.assertEqual(w.notebook.data.get(site_supply.STRANDED_KEY, {}), {})


class HomeOreRequestTests(StubTestCase):
    def test_home_requests_ore_only_with_home_smelter(self):
        w = self.world
        w.add_smelter("smelter_2", w.add_outpost("outpost_2"))
        site_supply.publish_site_requests(w.clock.now)
        self.assertNotIn("iron_ore", requests_by(w, w.home.id, site_supply.SITE_SUPPLY_REQUESTER))
        w.add_smelter("smelter_1", w.home)
        w.clock.now += logistics_requests.REPUBLISH_TICKS
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
        cache = production.SourceCache()
        rank, claim = supply_dock._local_supply(order, self.remote, cache)
        self.assertEqual((rank, claim), (supply_dock.LOCAL_STOCK_STEPS, {"steel_plate": 5}))
        promised = {}
        supply_dock._promise(promised, self.remote, claim)
        self.assertEqual(supply_dock._local_supply(order, self.remote, cache, promised=promised), (0, {}))

    def test_weekly_order_counts_local_stock_only_when_fully_covered(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote, {"steel_plate": 4})
        order = w.add_order("o_weekly", {"steel_plate": 5})
        order.kind = "weekly"
        self.assertEqual(supply_dock._local_supply(order, self.remote, production.SourceCache()), (0, {}))
        order.requires = {"steel_plate": 4}
        self.assertEqual(
            supply_dock._local_supply(order, self.remote, production.SourceCache())[0], supply_dock.LOCAL_STOCK_STEPS
        )

    def test_dock_counts_depot_stock_like_the_fabricator(self):
        """Units in a Drone Depot are held stock for the dock's readiness, local
        supply and affinity, the same count Fabricator netting uses."""
        w = self.world
        w.add_warehouse("wh_remote", self.remote, {"steel_plate": 2})
        w.add_drone_depot("depot_remote", self.remote).output_buffer["steel_plate"] = 3
        w.add_drone_depot("depot_home", w.home).output_buffer["steel_plate"] = 5
        order = w.add_order("o1", {"steel_plate": 5})
        cache = production.SourceCache()
        self.assertEqual(
            supply_dock._local_supply(order, self.remote, cache), (supply_dock.LOCAL_STOCK_STEPS, {"steel_plate": 5})
        )
        self.assertEqual(supply_dock._dock_affinity(order, self.remote, cache), 5)
        self.assertEqual(supply_dock._order_readiness(order, {}, cache.held_stock), (5, 5))
        self.assertEqual(supply_dock._order_readiness(order, {}), (5, 5))

    def test_planner_prioritizes_local_uranium_over_unstocked_tech_order(self):
        w = self.world
        _Cask(w, "lead_cask_1", w.home, material="raw_uranium", count=20)
        w.add_supply_dock("supply_dock_1", w.home)
        o_tech = w.add_order("o_tech", {"advanced_circuit": 10})
        o_tech.reward_kind = "tech"
        w.add_fabricator("fabricator_1", w.home, recipes=[Recipe("craft_circuit", {}, "advanced_circuit")])
        w.add_order("o_uranium", {"raw_uranium": 20})
        self.assertEqual(supply_dock.plan_dock_assignments(), {"supply_dock_1": "o_uranium"})

    def test_controller_step_switches_empty_order_to_order_with_local_uranium(self):
        w = self.world
        _Cask(w, "lead_cask_1", w.home, material="raw_uranium", count=20)
        dock = w.add_supply_dock("supply_dock_1", w.home)
        o_tech = w.add_order("o_tech", {"advanced_circuit": 10})
        o_tech.reward_kind = "tech"
        w.add_fabricator("fabricator_1", w.home, recipes=[Recipe("craft_circuit", {}, "advanced_circuit")])
        dock.order = o_tech
        w.add_order("o_uranium", {"raw_uranium": 20})
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

    def test_second_dock_skips_a_bare_key_order_for_a_stocked_one(self):
        # One dock already drives helios_01's production chain; nothing of it is stocked yet.
        w = self.world
        w.add_supply_dock("supply_dock_1", w.home).order = w.add_order("helios_01", {"advanced_circuit": 150})
        w.add_supply_dock("supply_dock_2", w.home)
        w.inventory.add("steel_plate", 5)
        w.add_order("o_steel", {"steel_plate": 5})
        w.add_fabricator("fabricator_1", w.home, recipes=[Recipe("craft_circuit", {}, "advanced_circuit")])
        self.assertEqual(
            supply_dock.plan_dock_assignments(), {"supply_dock_1": "helios_01", "supply_dock_2": "o_steel"}
        )

    def test_second_dock_joins_a_key_order_stocked_at_its_site(self):
        w = self.world
        w.inventory.add("iron_ingot", 10)
        w.add_supply_dock("supply_dock_1", w.home).order = w.add_order("helios_01", {"iron_ingot": 150})
        w.add_warehouse("wh_remote", self.remote, {"iron_ingot": 100, "steel_plate": 5})
        w.add_fabricator("fabricator_2", self.remote)
        w.add_smelter("smelter_2", self.remote)
        w.add_supply_dock("supply_dock_2", self.remote)
        w.add_order("o_steel", {"steel_plate": 5})
        self.assertEqual(
            supply_dock.plan_dock_assignments(), {"supply_dock_1": "helios_01", "supply_dock_2": "helios_01"}
        )

    def test_empty_dock_keeps_its_order_when_another_dock_holds_the_bare_key_order(self):
        w = self.world
        w.add_supply_dock("supply_dock_1", w.home).order = w.add_order("helios_01", {"advanced_circuit": 150})
        w.add_fabricator("fabricator_1", w.home, recipes=[Recipe("craft_circuit", {}, "advanced_circuit")])
        w.inventory.add("steel_plate", 5)
        w.add_supply_dock("supply_dock_2", w.home).order = w.add_order("o_steel", {"steel_plate": 5})
        self.assertEqual(
            supply_dock.plan_dock_assignments(), {"supply_dock_1": "helios_01", "supply_dock_2": "o_steel"}
        )

    def test_planner_stocks_ahead_for_the_next_key_orders(self):
        w = self.world
        w.inventory.add("iron_ingot", 100)
        w.add_supply_dock("supply_dock_1", w.home).order = w.add_order("helios_01", {"iron_ingot": 150})
        upcoming = []
        for order_id, contractor, requires in (
            ("helios_02", "helios", {"iron_ingot": 300}),
            ("helios_03", "helios", {"titanium_ingot": 60}),
            ("spire_intake_2", "spire", {"gas_pipe_segment": 60, "ice": 75}),
        ):
            order = game_stubs.Order(order_id, requires)
            order.contractor_id = contractor
            order.status = "upcoming"
            upcoming.append(order)
        w.services["orders"].upcoming = upcoming
        supply_dock.plan_dock_assignments()
        # Only each contractor's next key order; raw ice has no recipe.
        self.assertEqual(
            production.get_orders()["key_unlock_ahead"],
            {"gas_pipe_segment": [[60, priority.ORDER_AHEAD]], "iron_ingot": [[300, priority.ORDER_AHEAD]]},
        )

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
        self.assertEqual(
            supply_dock.plan_dock_assignments(), {"supply_dock_nuclear": None, "supply_dock_home": "o_steel"}
        )

    def test_nuclear_dock_takes_mixed_order_and_pulls_crafted_part(self):
        w = self.world
        w.add_warehouse("wh_nuclear", self.nuclear)
        w.add_warehouse("wh_home", w.home)
        dock = w.add_supply_dock("supply_dock_nuclear", self.nuclear)
        w.add_order("o_mixed", {"fuel_rod": 10, "steel_plate": 5})
        self.assertEqual(supply_dock.plan_dock_assignments(), {"supply_dock_nuclear": "o_mixed"})
        dock.order = w.services["orders"].orders["o_mixed"]
        site_supply.publish_site_requests(w.clock.now)
        self.assertEqual(
            requests_by(w, "outpost_nuclear", site_supply.SITE_SUPPLY_REQUESTER).get("steel_plate"), (5, 5)
        )

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

    def test_key_ahead_site_is_the_dock_site_covering_the_order(self):
        w = self.world
        other = w.add_outpost("outpost_a")
        docks = {
            "supply_dock_nuclear": w.add_supply_dock("supply_dock_nuclear", self.nuclear),
            "supply_dock_a1": w.add_supply_dock("supply_dock_a1", other),
            "supply_dock_a2": w.add_supply_dock("supply_dock_a2", other),
            "supply_dock_home": w.add_supply_dock("supply_dock_home", w.home),
        }
        order = w.add_order("o_steel", {"steel_plate": 5})
        roles = supply_dock.DockRoles()
        # Only home has a Fabricator, so only its dock covers steel_plate.
        self.assertEqual(supply_dock.key_ahead_site([order], docks, roles), w.home.id)
        # No role-bound item: most docks wins.
        bio = w.add_order("o_bio", {"biomass": 5})
        self.assertEqual(supply_dock.key_ahead_site([bio], docks, roles), "outpost_a")
        self.assertEqual(supply_dock.key_ahead_site([order], {}, roles), production.NO_CONSUMER_SITE)

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
        self.assertGreaterEqual(logistics_requests.tier_level(entry, priority.NEED), 5)

    def test_smelting_site_ore_request_keeps_dock_need(self):
        w = self.world
        w.add_warehouse("wh_home", w.home, {"iron_ore": 20})
        w.add_warehouse("wh_nuclear", self.nuclear)
        w.add_smelter("smelter_n", self.nuclear)
        dock = w.add_supply_dock("supply_dock_nuclear", self.nuclear)
        dock.order = w.add_order("o_iron", {"iron_ore": 5})
        site_supply.publish_site_requests(w.clock.now)
        entry = logistics_requests.active_requests(w.clock.now).get("outpost_nuclear", {}).get("iron_ore")
        self.assertGreaterEqual(logistics_requests.tier_level(entry, priority.NEED), 5)


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
        super().__init__(
            world,
            cask_id,
            "lead_cask",
            outpost,
            capacity=capacity,
            items={material: count} if material and count > 0 else {},
        )
        self.id = cask_id
        world.components[cask_id] = self

    def material(self):
        m = [i for i, n in self.items.items() if n > 0]
        return m[0] if m else ""


if __name__ == "__main__":
    unittest.main()
