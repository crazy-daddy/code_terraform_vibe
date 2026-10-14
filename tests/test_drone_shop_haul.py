"""Stub tests for hauler drone Shop pickups: drone_haul_plan.shop_sources(),
sources_for() and DroneHaulerMixin's Shop buy round."""

import unittest

import depot_stage
import drone_haul_plan
import harness
import priority
from drone_hauler import DroneHaulerMixin
from harness import StubTestCase, logistics_requests
from tree_console import TreeConsole

R = harness.request


class _Hauler(DroneHaulerMixin):
    def __init__(self, world, name="drone_1"):
        self.name = name
        self.log = TreeConsole(module="drone")
        self.haul_memory = drone_haul_plan.HaulMemory()
        self._world = world

    def get_current_tick(self):
        return 0


def _depot(depot_id, outpost, coords):
    return {"id": depot_id, "outpost_id": outpost.id, "coords": coords}


class ShopSourceTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.home = self.world.home
        self.remote = self.world.add_outpost("outpost_2")
        self.other = self.world.add_outpost("outpost_3")
        outposts = {o.id: o for o in (self.home, self.remote, self.other)}
        depots = {o.id: [_depot(f"depot_{o.id}", o, (i * 100.0, 0.0))] for i, o in enumerate(outposts.values())}
        self.layout = (outposts, depots)
        self.drone = _Hauler(self.world)

    def dest(self, outpost, items):
        return {
            "outpost": outpost,
            "outpost_id": outpost.id,
            "coords": (0.0, 0.0),
            "tiers": {priority.NEED: dict(items)},
            "deficits": dict(items),
        }

    def sources(self, dests):
        return drone_haul_plan.shop_sources(self.drone, dests, 0, logistics_requests.PlanReads(0), self.layout)

    def test_only_buyable_deficits_of_remote_destinations(self):
        logistics_requests.publish_requests(
            "outpost_2", "bio_reagents", {"protein_marker": (R(60), 0)}, 0, buyable=True
        )
        logistics_requests.publish_requests("outpost_3", "site", {"iron_ingot": (R(50), 0)}, 0)
        dests = [
            self.dest(self.remote, {"protein_marker": 60, "iron_ingot": 5}),
            self.dest(self.other, {"iron_ingot": 50}),
        ]
        sources = self.sources(dests)
        self.assertEqual([s["id"] for s in sources], ["shop:outpost_2"])
        shop = sources[0]
        self.assertEqual(shop["available"], {"protein_marker": 60})
        self.assertEqual(shop["for_dest"], "outpost_2")
        self.assertEqual(shop["depots"], self.layout[1][self.home.id])

    def test_home_destination_and_no_home_depot_get_none(self):
        logistics_requests.publish_requests(self.home.id, "x", {"protein_marker": (R(60), 0)}, 0, buyable=True)
        self.assertEqual(self.sources([self.dest(self.home, {"protein_marker": 60})]), [])
        logistics_requests.publish_requests(
            "outpost_2", "bio_reagents", {"protein_marker": (R(60), 0)}, 0, buyable=True
        )
        del self.layout[1][self.home.id]
        self.assertEqual(self.sources([self.dest(self.remote, {"protein_marker": 60})]), [])

    def test_sources_for_offers_a_shop_source_to_its_destination_only(self):
        shop = {"kind": "shop", "id": "shop:outpost_2", "for_dest": "outpost_2", "available": {"protein_marker": 60}}
        outpost = {"kind": "outpost", "id": "outpost_home", "available": {"protein_marker": 5}}
        mine = drone_haul_plan.sources_for(self.dest(self.remote, {"protein_marker": 60}), [outpost, shop])
        theirs = drone_haul_plan.sources_for(self.dest(self.other, {"protein_marker": 60}), [outpost, shop])
        self.assertEqual([s["id"] for s in mine], ["outpost_home", "shop:outpost_2"])
        self.assertEqual([s["id"] for s in theirs], ["outpost_home"])


class ShopBuyTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.world.services["shop"].prices = {"protein_marker": 5}
        self.world.services["commander"].credits = 1000000
        self.drone = _Hauler(self.world)

    def test_buys_missing_units_into_inventory_and_stages_them(self):
        remaining, moved, bought = {"protein_marker": 30}, {}, {}
        self.drone._buy_round(remaining, moved, bought, "depot_home")
        self.assertEqual(bought, {"protein_marker": 30})
        self.assertEqual(self.world.inventory.count("protein_marker"), 30)
        self.assertEqual(depot_stage.staged_for("depot_home", 0), {"protein_marker": 30})

    def test_bought_but_unloaded_units_are_not_bought_again(self):
        remaining, moved, bought = {"protein_marker": 20}, {"protein_marker": 10}, {"protein_marker": 30}
        self.drone._buy_round(remaining, moved, bought, "depot_home")
        self.assertEqual(bought, {"protein_marker": 30})
        self.assertEqual(self.world.inventory.count("protein_marker"), 0)
        self.assertIn("protein_marker", remaining)

    def test_unaffordable_item_with_nothing_pending_is_dropped(self):
        self.world.services["commander"].credits = 0
        remaining = {"protein_marker": 30}
        self.drone._buy_round(remaining, {}, {}, "depot_home")
        self.assertEqual(remaining, {})


if __name__ == "__main__":
    unittest.main()
