"""Stub tests for lib/fabricator.py FabricatorController, at home and at a remote outpost."""
import unittest

from harness import StubTestCase, fabricator, production
import recipe_claims
from game_stubs import Recipe


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

    def test_manual_order_builds_remaining_on_top_of_stock(self):
        w = self.world
        w.add_fabricator("fabricator_1", w.home)
        w.inventory.add("steel_plate", 9)
        w.notebook.set(production.MANUAL_ORDERS_KEY, {"steel_plate": 7})
        self.assertEqual(production.get_fabricator_targets().get("steel_plate"), 16)

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
            ticks[0] += recipe_claims.CLAIM_REFRESH_TICKS - 1
            self.assertTrue(controller.claim_recipe("craft_gas_pipe_segment"))
            self.assertEqual(len(calls), 1)
            ticks[0] += 1
            self.assertTrue(controller.claim_recipe("craft_gas_pipe_segment"))
            self.assertEqual(len(calls), 2)
            controller.release_recipe("craft_gas_pipe_segment")
            self.assertNotIn("craft_gas_pipe_segment", controller._claim_ticks)
        finally:
            fabricator.archive.transaction = real


class SourceMemoTests(StubTestCase):
    """can_source_item()/can_source_fluid() answer a repeat from the SourceCache memo without logging."""

    def _counting_log_start(self):
        calls = []
        real = production.log.start
        production.log.start = lambda *a, **k: (calls.append(a[0] if a else ""), real(*a, **k))[1]
        self.addCleanup(setattr, production.log, "start", real)
        return calls

    def test_repeat_item_and_fluid_checks_hit_memo_silently(self):
        self.world.inventory.add("iron_ingot", 5)
        cache = production.SourceCache()
        self.assertTrue(production.can_source_item("iron_ingot", cache))
        self.assertTrue(production.can_source_fluid("unmodelled_fluid", cache))
        calls = self._counting_log_start()
        for _ in range(3):
            self.assertTrue(production.can_source_item("iron_ingot", cache))
            self.assertTrue(production.can_source_fluid("unmodelled_fluid", cache))
        self.assertEqual(calls, [])

    def test_recipe_cycle_resolves_same_as_before(self):
        # a <- b <- a: neither has stock or a mineral site, so both stay unsourceable,
        # and the memoized answers match a fresh top-level check.
        cache = production.SourceCache()
        cache._sourcing_index = {
            "cyc_a": [Recipe("make_a", {"cyc_b": 1}, "cyc_a")],
            "cyc_b": [Recipe("make_b", {"cyc_a": 1}, "cyc_b")],
        }
        self.assertFalse(production.can_source_item("cyc_a", cache))
        self.assertFalse(production.can_source_item("cyc_b", cache))
        self.assertEqual(cache._item_stack, set())
        self.world.inventory.add("cyc_b", 1)
        fresh = production.SourceCache()
        fresh._sourcing_index = cache._sourcing_index
        self.assertTrue(production.can_source_item("cyc_a", fresh))
        self.assertTrue(production.can_source_item("cyc_a", fresh))


class ForeignClaimTests(StubTestCase):
    def test_choose_recipe_skips_claim_held_by_peer(self):
        w = self.world
        w.inventory.add("iron_ingot", 100)
        a = fabricator.FabricatorController(w.add_fabricator("fabricator_1", w.home))
        b = fabricator.FabricatorController(w.add_fabricator("fabricator_2", w.home))
        w.notebook.set(production.FABRICATOR_STOCK_TARGETS_KEY, {"gas_pipe_segment": 10})
        self.assertTrue(b.claim_recipe("craft_gas_pipe_segment"))
        self.assertEqual(a.foreign_claims("home"), {"craft_gas_pipe_segment": "fabricator_2"})
        self.assertEqual(b.foreign_claims("home"), {})
        tried = []
        real = a.claim_recipe
        a.claim_recipe = lambda recipe_id: (tried.append(recipe_id), real(recipe_id))[1]
        a.choose_recipe()
        self.assertNotIn("craft_gas_pipe_segment", tried)
        self.assertEqual(w.notebook.data[fabricator.RECIPE_CLAIMS_KEY]["home"]["craft_gas_pipe_segment"]["fabricator"], "fabricator_2")


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

    def test_manual_order_built_off_home_stays_wanted_at_home(self):
        w = self.world
        wh = w.add_warehouse("wh_remote", self.remote)
        f = w.add_fabricator("fabricator_2", self.remote)
        w.inventory.add("lead_cask", 1)
        w.notebook.set(production.MANUAL_ORDERS_KEY, {"lead_cask": 2})
        f.output_buffer["lead_cask"] = 2
        fabricator.FabricatorController(f).drain_output()
        self.assertEqual(production.get_manual_orders(), {})
        self.assertEqual(w.notebook.get(production.MANUAL_TRANSIT_KEY), {"lead_cask": {"units": 2, "base": 1}})
        _roots, consumers, _outputs = production.fabricator_root_targets(production.SourceCache())
        self.assertEqual(consumers["lead_cask"]["home"], 3)

        # One unit hauled home: one still wanted.
        wh.remove("lead_cask", 1)
        w.inventory.add("lead_cask", 1)
        production.reconcile_manual_transit()
        self.assertEqual(w.notebook.get(production.MANUAL_TRANSIT_KEY), {"lead_cask": {"units": 2, "base": 1}})

        wh.remove("lead_cask", 1)
        w.inventory.add("lead_cask", 1)
        production.reconcile_manual_transit()
        self.assertEqual(w.notebook.get(production.MANUAL_TRANSIT_KEY), {})
        self.assertEqual(production.manual_transit_wants(), {})

    def test_manual_order_built_at_home_records_no_transit(self):
        w = self.world
        f = w.add_fabricator("fabricator_1", w.home)
        w.notebook.set(production.MANUAL_ORDERS_KEY, {"lead_cask": 2})
        f.output_buffer["lead_cask"] = 2
        fabricator.FabricatorController(f).drain_output()
        self.assertEqual(production.get_manual_orders(), {})
        self.assertFalse(w.notebook.get(production.MANUAL_TRANSIT_KEY, {}))

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
