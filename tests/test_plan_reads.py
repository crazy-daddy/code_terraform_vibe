"""logistics_requests.PlanReads: one planning pass reads requests, pickups and
each outpost's stock once, and gives the same answers as the per-call reads
(outpost_deficits_tiered(), outpost_free_tiers(), fair_tier_caps())."""
import unittest

from harness import StubTestCase, logistics_requests
from tree_console import TreeConsole
import drone_haul_plan


class PlanReadsTests(StubTestCase):
    def _world(self):
        w = self.world
        now = w.clock.now
        a = w.add_outpost("outpost_a")
        b = w.add_outpost("outpost_b")
        w.add_warehouse("wh_home", w.home, {"iron_ore": 40, "copper_ore": 5})
        w.add_warehouse("wh_a", a, {"iron_ore": 300, "copper_ore": 120, "salt": 7})
        w.add_warehouse("wh_b", b, {"copper_ore": 30})
        depot_a = w.add_drone_depot("depot_a", a)
        depot_a.output_buffer["iron_ore"] = 25
        w.add_drone_depot("depot_b", b)
        w.inventory.items["copper_ore"] = 11
        logistics_requests.set_requests("home", "smelter", {"iron_ore": (200, 0, 80), "copper_ore": (60, 0)}, now)
        logistics_requests.set_requests("outpost_a", "fab", {"iron_ore": (100, 0, 50), "copper_ore": (50, 0, 10)}, now)
        logistics_requests.set_requests("outpost_b", "fab", {"iron_ore": (90, 0, 20), "copper_ore": (40, 30, 10)}, now)
        logistics_requests.reserve_pickup("drone_2", "home", "iron_ore", 30, now, source_id="outpost_a")
        logistics_requests.reserve_pickup("drone_3", "outpost_b", "copper_ore", 15, now, source_id="outpost_a", aboard=True)
        logistics_requests.reserve_pickup("drone_1", "outpost_b", "iron_ore", 9, now, source_id="outpost_a")
        return now, [w.home, a, b]

    def test_same_answers_as_per_call_reads(self):
        now, outposts = self._world()
        reads = logistics_requests.PlanReads(now)
        items = ["iron_ore", "copper_ore"]
        for outpost in outposts:
            for live in (True, False):
                self.assertEqual(logistics_requests.outpost_deficits_tiered(outpost, now, live=live, reads=reads),
                                 logistics_requests.outpost_deficits_tiered(outpost, now, live=live))
            for vehicle in ("drone_1", None):
                for loader in (logistics_requests.LOADER_DRONE, logistics_requests.LOADER_VEHICLE):
                    self.assertEqual(
                        logistics_requests.outpost_free_tiers(outpost, items, None, now, exclude_vehicle=vehicle, loader=loader, reads=reads),
                        logistics_requests.outpost_free_tiers(outpost, items, None, now, exclude_vehicle=vehicle, loader=loader))
            # An item no request names is read on demand.
            self.assertEqual(
                logistics_requests.outpost_free_tiers(outpost, ["salt"], None, now, loader=logistics_requests.LOADER_DRONE, reads=reads),
                logistics_requests.outpost_free_tiers(outpost, ["salt"], None, now, loader=logistics_requests.LOADER_DRONE))
            self.assertEqual(reads.in_flight(outpost.id), logistics_requests.in_flight(outpost.id, now))
            self.assertEqual(reads.reserved_from(outpost.id, "drone_1"), logistics_requests.reserved_from(outpost.id, now, exclude_vehicle="drone_1"))
            buffer = {"iron_ore": 60, "copper_ore": 25}
            supply = {"iron_ore": 50, "copper_ore": 10}
            self.assertEqual(logistics_requests.fair_tier_caps(outpost.id, logistics_requests.BUFFER, buffer, supply, now, reads=reads),
                             logistics_requests.fair_tier_caps(outpost.id, logistics_requests.BUFFER, buffer, supply, now))

    def test_stock_read_once_per_outpost(self):
        now, outposts = self._world()
        warehouse = self.world.components["wh_a"]
        calls = []
        original = warehouse.stacks
        warehouse.stacks = lambda: calls.append(1) or original()
        reads = logistics_requests.PlanReads(now)
        a = outposts[1]
        logistics_requests.outpost_deficits_tiered(a, now, live=True, reads=reads)
        logistics_requests.outpost_free_tiers(a, ["iron_ore", "copper_ore"], None, now, exclude_vehicle="drone_1", loader=logistics_requests.LOADER_DRONE, reads=reads)
        logistics_requests.outpost_free_tiers(a, ["copper_ore"], None, now, loader=logistics_requests.LOADER_DRONE, reads=reads)
        self.assertEqual(len(calls), 1)

    def test_pickups_snapshot_is_what_planning_sees(self):
        now, outposts = self._world()
        seen = logistics_requests.pickups_snapshot()
        reads = logistics_requests.PlanReads(now, seen)
        # Reserved after `seen`: claim_pickups() trims for it, so planning must not count it too.
        logistics_requests.reserve_pickup("drone_4", "outpost_b", "iron_ore", 50, now, source_id="outpost_a")
        self.assertEqual(reads.in_flight("outpost_b"), {"iron_ore": 9, "copper_ore": 15})
        self.assertEqual(reads.reserved_from("outpost_a", "drone_1"), {"iron_ore": 30, "copper_ore": 15})


class _HaulerHost:
    name = "drone_1"

    def __init__(self, depots):
        self.log = TreeConsole(module="test_plan_reads")
        self._depots = depots

    def get_all_drone_depots(self):
        return list(self._depots)


def _hauler(depots):
    cls = type("TestHauler", (drone_haul_plan.DroneHaulPlanMixin,), {"_host": property(lambda self: self._test_host)})
    obj = cls.__new__(cls)
    setattr(obj, "_test_host", _HaulerHost(depots))
    return obj


class HaulerPlanReadsTests(StubTestCase):
    _world = PlanReadsTests._world

    def test_hauler_demand_and_sources_share_one_read(self):
        now, _outposts = self._world()
        hauler = _hauler([{"id": "depot_a", "outpost_id": "outpost_a", "coords": (100.0, 0.0)},
                          {"id": "depot_b", "outpost_id": "outpost_b", "coords": (0.0, 100.0)}])
        items = {"iron_ore", "copper_ore"}
        dests_alone = hauler._haul_destinations(now)
        sources_alone = hauler._outpost_sources(items, now)
        self.assertEqual(sorted(d["outpost_id"] for d in dests_alone), ["outpost_b"])
        self.assertEqual(sorted(s["id"] for s in sources_alone), ["outpost_a", "outpost_b"])

        calls = []
        for wh_id in ("wh_a", "wh_b"):
            warehouse = self.world.components[wh_id]
            warehouse.stacks = (lambda original: lambda: calls.append(1) or original())(warehouse.stacks)
        reads = logistics_requests.PlanReads(now, logistics_requests.pickups_snapshot())
        layout = hauler._depot_layout()
        self.assertEqual(hauler._haul_destinations(now, reads, layout), dests_alone)
        self.assertEqual(hauler._outpost_sources(items, now, reads, layout), sources_alone)
        self.assertEqual(len(calls), 2)  # outpost_b is destination and source: one stacks() per Warehouse, not 3


if __name__ == "__main__":
    unittest.main()
