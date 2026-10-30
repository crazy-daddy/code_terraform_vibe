"""Stub tests for lib/smelter.py SmelterController, at home and at a remote outpost."""

import unittest
from unittest import mock

import production_demand_record
import recipe_claims
from game_stubs import Recipe
from harness import SEGMENT_ORDER, StubTestCase, home_order, production, smelter
from priority import MANUAL, NEED, ORDER


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

    def test_recipe_switch_loads_ore_in_same_step(self):
        w = self.world
        w.add_fabricator("fabricator_1", w.home)
        w.add_warehouse("wh1", w.home, {"iron_ore": 100})
        s = w.add_smelter("smelter_1", w.home)
        active = smelter.SmelterController(s).step()
        self.assertEqual(s.recipe, "smelt_iron_ingot")
        self.assertGreater(s.input_buffer.get("iron_ore", 0), 0)
        self.assertTrue(active)

    def test_running_smelter_with_half_full_buffer_skips_take(self):
        w = self.world
        w.add_fabricator("fabricator_1", w.home)
        w.add_warehouse("wh1", w.home, {"iron_ore": 100})
        s = w.add_smelter("smelter_1", w.home)
        c = smelter.SmelterController(s)
        c.step()
        s.running = True
        prefill = smelter.craft_prefill_units(s.list_recipes()[0], "iron_ore", smelter.SMELTER_PREFILL_SECONDS)
        s.input_buffer["iron_ore"] = prefill // 2 + 1
        before = dict(s.input_buffer)
        self.assertTrue(c.step())
        self.assertEqual(s.input_buffer, before)

    def test_prefill_scales_with_mk_tier(self):
        # The game's Recipe already includes the machine's tier; no second division.
        s = self.world.add_smelter("smelter_1", self.world.home)
        base = smelter.craft_prefill_units(s.list_recipes()[0], "iron_ore", 60)
        s.installed_tier = 2
        self.assertEqual(production.machine_speed(s), 2)
        self.assertEqual(smelter.craft_prefill_units(s.list_recipes()[0], "iron_ore", 60), 2 * base)
        s.installed_tier = 3
        self.assertEqual(production.machine_speed(s), 4)
        self.assertEqual(smelter.craft_prefill_units(s.list_recipes()[0], "iron_ore", 60), 4 * base)

    def test_craft_seconds_normalizes_source_tier(self):
        recipe = Recipe("smelt_iron_ingot", {"iron_ore": 1}, "iron_ingot", duration_game_hours=0.5)
        base = production.craft_seconds(recipe)
        # Read from a Mk III machine (0.5 h = 2 h / 4), run on Mk II: 2 h / 2.
        self.assertEqual(production.craft_seconds(recipe, 2, 4), 2 * base)
        self.assertEqual(production.craft_seconds(recipe, 4, 4), base)

    def test_claim_recipe_skips_archive_within_refresh_window(self):
        s = self.world.add_smelter("smelter_1", self.world.home)
        c = smelter.SmelterController(s)
        self.assertTrue(c.claim_recipe("smelt_iron_ingot"))
        calls = []
        real = smelter.archive.transaction
        smelter.archive.transaction = lambda *a, **k: calls.append(a) or real(*a, **k)
        try:
            self.assertTrue(c.claim_recipe("smelt_iron_ingot"))
            self.assertEqual(calls, [])
            c.release_recipe("smelt_iron_ingot")
            self.assertEqual(len(calls), 1)
            claims = smelter.archive.get(c.RECIPE_CLAIMS_KEY, {}) or {}
            self.assertFalse(any("smelt_iron_ingot" in site for site in claims.values()))
        finally:
            smelter.archive.transaction = real

    def test_idle_step_reports_inactive(self):
        s = self.world.add_smelter("smelter_1", self.world.home)
        self.assertFalse(smelter.SmelterController(s).step())


class NextSleepTests(StubTestCase):
    def test_recipe_machines_poll_fast_when_active(self):
        w = self.world
        w.add_fabricator("fabricator_1", w.home)
        controller = smelter.SmelterController(w.add_smelter("smelter_1", w.home))
        mixin = recipe_claims.RecipeClaimMixin
        for result, failed, active in ((True, False, True), (None, True, True), (None, False, False)):
            delay = controller.next_sleep(result, failed)
            self.assertEqual(delay, mixin.ACTIVE_POLL_SECONDS if active else mixin.IDLE_POLL_SECONDS)


class PlanFeedTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        w.add_fabricator("fabricator_1", w.home)
        w.add_warehouse("wh1", w.home, {"iron_ore": 500})
        self.smelter = w.add_smelter("smelter_1", w.home)
        home_order({"iron_ingot": 10})
        self.c = smelter.SmelterController(self.smelter)

    def replans(self, advance=0):
        """True when a step after `advance` ticks recomputed the plan."""
        self.world.clock.now += advance
        before = self.c._plan
        self.c.step()
        return self.c._plan is not before

    def test_feed_step_renews_held_claim(self):
        self.c.step()
        recipe_id = self.c._plan["recipe"].id
        self.assertIn(recipe_id, self.c._claim_ticks)
        self.assertFalse(self.replans(recipe_claims.RECIPE_CLAIM_STALE_TICKS + 1))
        site = next(iter(smelter.archive.get(self.c.RECIPE_CLAIMS_KEY, {}).values()))
        self.assertEqual(site[recipe_id]["tick"], self.world.clock.now)

    def test_feed_step_runs_no_cascade(self):
        self.c.step()
        loaded = self.smelter.input_buffer.get("iron_ore", 0)
        self.assertGreater(loaded, 0)
        self.world.clock.now += 5
        with mock.patch.object(smelter, "get_smelter_demands") as cascade:
            self.c.step()
        cascade.assert_not_called()
        self.assertGreaterEqual(self.smelter.input_buffer.get("iron_ore", 0), loaded)

    def test_plan_reads_a_fresh_record_without_the_cascade(self):
        w = self.world
        home_id = production.home_outpost_id()
        record = production_demand_record.new_record(
            {}, {}, smelter_network={"iron_ingot": [[600, 10]]}, smelter_sites={home_id: ({}, {})}
        )
        production_demand_record.publish_record(record, now=w.clock.now)
        with mock.patch.object(smelter, "get_smelter_demands") as cascade:
            self.c.step()
        cascade.assert_not_called()
        self.assertEqual(self.smelter.recipe, "smelt_iron_ingot")

    def test_plan_walks_when_the_record_does_not_know_this_site(self):
        w = self.world
        record = production_demand_record.new_record({}, {}, smelter_network={"iron_ingot": [[600, 10]]})
        production_demand_record.publish_record(record, now=w.clock.now)
        with mock.patch.object(smelter, "get_smelter_demands", return_value={"iron_ingot": [[600, 10]]}) as cascade:
            self.c.step()
        cascade.assert_called_once()

    def test_plan_without_a_record_walks_and_publishes_nothing(self):
        with mock.patch.object(smelter, "get_smelter_demands", return_value={"iron_ingot": [[600, 10]]}) as cascade:
            self.c.step()
        cascade.assert_called_once()
        self.assertEqual(
            production_demand_record.read_record(now=self.world.clock.now), (None, production_demand_record.MISSING)
        )

    def test_plan_due_on_backstop(self):
        self.c.step()
        self.assertFalse(self.replans(smelter.PLAN_BACKSTOP_TICKS - 10))
        self.assertTrue(self.replans(10))

    def test_plan_due_on_new_demand_record(self):
        self.c.step()
        self.assertFalse(self.replans(1))
        self.world.notebook.set(production_demand_record.DEMAND_TICK_KEY, self.world.clock.now + 1)
        self.assertTrue(self.replans(1))

    def test_plan_due_when_recipe_cleared(self):
        self.c.step()
        self.smelter.recipe = ""
        self.assertTrue(self.replans(1))
        self.assertEqual(self.smelter.recipe, "smelt_iron_ingot")

    def test_plan_due_when_output_blocked(self):
        self.c.step()
        self.assertFalse(self.replans(1))
        self.smelter.output_buffer["iron_ingot"] = 50
        self.c.drain_output = lambda: 0
        self.assertTrue(self.replans(1))

    def test_plan_due_when_demand_exhausted(self):
        self.c.step()
        self.c._plan["demands"]["iron_ingot"] = []
        self.assertTrue(self.c.plan_due(self.world.clock.now + 1))

    def test_plan_due_after_no_ore_or_idle(self):
        self.c.step()
        self.assertFalse(self.c.plan_due(self.world.clock.now + 1))
        self.c._last_outcome = "no_ore"
        self.assertTrue(self.c.plan_due(self.world.clock.now + 1))
        self.c._last_outcome = None
        self.c._last_idle = True
        self.assertTrue(self.c.plan_due(self.world.clock.now + 1))

    def test_feed_nets_planned_demand_by_drained_output(self):
        self.c.step()
        self.assertEqual(self.c._plan["demands"]["iron_ingot"][0][1], 10)
        self.smelter.input_buffer.clear()
        self.smelter.output_buffer["iron_ingot"] = 6
        self.world.clock.now += 1
        self.c.step()
        self.assertEqual(self.c._plan["made"], 6)
        self.assertEqual(self.c._plan["demands"]["iron_ingot"][0][1], 10)
        self.assertIn("demand_qty=4 ", self.debug_log())


class PublishWantTests(StubTestCase):
    def test_empty_want_pops_only_its_own_entry(self):
        w = self.world
        controller = smelter.SmelterController(w.add_smelter("smelter_1", w.home))
        w.notebook.set(
            smelter.SMELTER_WANTS_KEY,
            {
                "smelter_1": {"site": "home", "ore": "iron_ore", "fill_to": 5, "prio": 1, "tick": 1},
                "other": {"tick": 0},
            },
        )
        controller._want = None
        controller._want_published = ("iron_ore", 5, 1)
        controller.publish_want()
        self.assertEqual(w.notebook.get(smelter.SMELTER_WANTS_KEY), {"other": {"tick": 0}})
        self.assertIsNone(controller._want_published)


class RemoteSmelterTests(StubTestCase):
    def setUp(self):
        super().setUp()
        home_order(SEGMENT_ORDER)
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
        self.assertEqual(s.input.connected_id(), "")

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

    def test_dock_reserve_applies_at_the_docks_outpost_only(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote, {"iron_ore": 60})
        w.add_warehouse("wh_home", w.home, {"iron_ore": 60})
        w.add_order("ore_order", {"iron_ore": 50})
        w.add_supply_dock("supply_dock_2", self.remote).set_order("ore_order")
        remote_ctl = smelter.SmelterController(w.add_smelter("smelter_2", self.remote))
        home_ctl = smelter.SmelterController(w.add_smelter("smelter_1", w.home))
        cache = smelter.SourceCache()
        self.assertEqual(production.dock_remaining_requirements("outpost_2"), {"iron_ore": 50})
        self.assertEqual(production.dock_remaining_requirements(home_ctl.site_id()), {})
        self.assertEqual(remote_ctl.available_ore("iron_ore", cache, remote_ctl.dock_holds()), 10)
        self.assertEqual(home_ctl.available_ore("iron_ore", cache, home_ctl.dock_holds()), 60)

    def test_dock_reserve_yields_to_demand_that_outranks_the_order(self):
        w = self.world
        w.add_warehouse("wh_remote", self.remote, {"iron_ore": 60})
        w.add_order("ore_order", {"iron_ore": 50})
        w.add_supply_dock("supply_dock_2", self.remote).set_order("ore_order")
        ctl = smelter.SmelterController(w.add_smelter("smelter_2", self.remote))
        cache = smelter.SourceCache()
        holds = ctl.dock_holds()
        self.assertEqual(holds, {"iron_ore": (50, ORDER)})
        self.assertEqual(ctl.available_ore("iron_ore", cache, holds, NEED), 10)
        self.assertEqual(ctl.available_ore("iron_ore", cache, holds, ORDER), 10)
        self.assertEqual(ctl.available_ore("iron_ore", cache, holds, MANUAL), 60)

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
