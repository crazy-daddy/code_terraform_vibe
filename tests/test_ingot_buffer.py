"""Stub tests for the fab-site ingot buffer (production.fab_site_ingot_targets(),
smelter refill, site_supply ingot_wants()) and the Fabricator's direct
Smelter wake."""
import unittest

from harness import StubTestCase, production, smelter, fabricator, logistics_requests, site_supply
from script_parking import PARKED_KEY


class _Result:
    status = "ok"


class _PowerControl:
    def __init__(self):
        self.calls = []

    def set_powered(self, machine_id, on):
        self.calls.append((machine_id, on))
        return _Result()


def site_requests(world, outpost_id):
    requests = logistics_requests.active_requests(world.clock.now).get(outpost_id, {})
    return {item_id: (e["target"], logistics_requests.request_min(e)) for item_id, e in requests.items() if e.get("by") == site_supply.SITE_SUPPLY_REQUESTER}


def meet_stock_targets(world):
    """Inventory holds every default Fabricator stock target, so no real demand is left."""
    for item_id, units in production.DEFAULT_FABRICATOR_STOCK_TARGETS.items():
        world.inventory.add(item_id, units)


class IngotLevelTests(StubTestCase):
    def test_seeds_defaults_once_and_keeps_edits(self):
        w = self.world
        self.assertEqual(production.ingot_stock_levels(["iron_ingot"]), {"iron_ingot": (2000, 100)})
        w.notebook.set(production.INGOT_STOCK_TARGETS_KEY, {"iron_ingot": {"target": 300, "need": 40}})
        self.assertEqual(production.ingot_stock_levels(["iron_ingot", "glass"]), {"iron_ingot": (300, 40), "glass": (2000, 100)})
        self.assertEqual(w.notebook.data[production.INGOT_STOCK_TARGETS_KEY]["iron_ingot"], {"target": 300, "need": 40})

    def test_only_fab_sites_and_fabricator_inputs(self):
        w = self.world
        remote = w.add_outpost("outpost_2")
        w.add_smelter("smelter_1", w.home)
        cache = production.SourceCache()
        self.assertEqual(production.fab_site_ingot_targets(remote, cache), {})
        w.add_fabricator("fabricator_2", remote)
        targets = production.fab_site_ingot_targets(remote, production.SourceCache())
        # titanium_ingot is a Smelter output no stub Fabricator recipe takes.
        self.assertEqual(sorted(targets), ["glass", "iron_ingot"])


class SmelterRefillTests(StubTestCase):
    def test_idle_smelter_refills_fab_site_buffer(self):
        w = self.world
        meet_stock_targets(w)
        w.add_fabricator("fabricator_1", w.home)
        w.add_warehouse("wh1", w.home, {"silicon": 100})
        s = w.add_smelter("smelter_1", w.home)
        smelter.SmelterController(s).step()
        self.assertEqual(s.recipe, "smelt_glass")
        self.assertGreater(s.input_buffer.get("silicon", 0), 0)

    def test_no_refill_without_a_fabricator(self):
        w = self.world
        remote = w.add_outpost("outpost_2")
        meet_stock_targets(w)
        w.add_warehouse("wh_remote", remote, {"silicon": 100})
        s = w.add_smelter("smelter_2", remote)
        smelter.SmelterController(s).step()
        self.assertEqual(s.recipe, "")

    def test_real_demand_outranks_refill(self):
        w = self.world
        meet_stock_targets(w)
        f = w.add_fabricator("fabricator_1", w.home)
        f.recipe = "craft_steel_plate"
        w.notebook.set(production.MANUAL_ORDERS_KEY, {"steel_plate": 5})
        w.notebook.set(production.INGOT_STOCK_TARGETS_KEY, {"iron_ingot": {"target": 0, "need": 0}})
        w.add_warehouse("wh1", w.home, {"iron_ore": 100, "silicon": 100})
        s = w.add_smelter("smelter_1", w.home)
        smelter.SmelterController(s).step()
        self.assertEqual(s.recipe, "smelt_iron_ingot")


class IngotWantsTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.world.add_smelter("smelter_1", self.world.home)

    def test_fab_site_requests_buffer_with_need_tier(self):
        w = self.world
        remote = w.add_outpost("outpost_2")
        w.add_fabricator("fabricator_2", remote)
        site_supply.publish_site_requests(w.clock.now)
        requests = site_requests(w, "outpost_2")
        self.assertEqual(requests["iron_ingot"], (2000, 100))
        self.assertEqual(requests["glass"], (2000, 100))
        self.assertNotIn("titanium_ingot", requests)

    def test_buffer_raises_a_bigger_need_level(self):
        w = self.world
        remote = w.add_outpost("outpost_2")
        w.notebook.set(production.INGOT_STOCK_TARGETS_KEY, {"iron_ingot": {"target": 2000, "need": 5}, "glass": {"target": 0, "need": 0}})
        w.inventory.add("iron_ingot", 1000)
        f = w.add_fabricator("fabricator_2", remote)
        f.recipe = "craft_gas_pipe_segment"  # 10 crafts x 2 = 20 iron ingot
        site_supply.publish_site_requests(w.clock.now)
        requests = site_requests(w, "outpost_2")
        self.assertEqual(requests["iron_ingot"], (2000, 20))
        self.assertNotIn("glass", requests)

    def test_buffer_is_not_free_for_another_sites_buffer(self):
        w = self.world
        remote = w.add_outpost("outpost_2")
        w.add_fabricator("fabricator_2", remote)
        w.add_warehouse("wh_remote", remote, {"iron_ingot": 500})
        site_supply.publish_site_requests(w.clock.now)
        for_need, for_buffer = logistics_requests.outpost_free_tiers(remote, ["iron_ingot"], None, w.clock.now)
        self.assertEqual(for_need, {"iron_ingot": 400})
        self.assertEqual(for_buffer, {})


class FabricatorWakeTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.power = _PowerControl()
        self.world.services["power_control"] = self.power
        self.remote = self.world.add_outpost("outpost_2")
        self.world.add_smelter("smelter_2", self.remote)
        self.world.add_smelter("smelter_1", self.world.home)
        self.world.notebook.set(PARKED_KEY, {
            "smelter_2": {"kind": "smelter", "mode": "breaker", "since": 0},
            "smelter_1": {"kind": "smelter", "mode": "breaker", "since": 0},
        })
        self.ctl = fabricator.FabricatorController(self.world.add_fabricator("fabricator_2", self.remote))

    def test_wakes_parked_local_smelters_only(self):
        self.assertEqual(self.ctl.wake_local_smelters("iron_ingot"), ["smelter_2"])
        self.assertEqual(self.power.calls, [("smelter_2", True)])
        self.assertNotIn("smelter_2", self.world.notebook.data[PARKED_KEY])

    def test_throttled_per_item(self):
        self.ctl.wake_local_smelters("iron_ingot")
        self.world.notebook.set(PARKED_KEY, {"smelter_2": {"kind": "smelter", "mode": "breaker", "since": 0}})
        self.assertEqual(self.ctl.wake_local_smelters("iron_ingot"), [])
        self.world.clock.now += fabricator.SMELTER_WAKE_THROTTLE_TICKS
        self.assertEqual(self.ctl.wake_local_smelters("iron_ingot"), ["smelter_2"])

    def test_ignores_items_no_smelter_makes(self):
        self.assertEqual(self.ctl.wake_local_smelters("gas_pipe_segment"), [])
        self.assertEqual(self.power.calls, [])


if __name__ == "__main__":
    unittest.main()
