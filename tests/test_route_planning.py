"""Route planner helpers shared by drone_haul_plan.py and pull_plan.py (logistics_requests.source_useful(), route_atomic_ok())."""

import random
import unittest

import drone_haul_plan
import game_stubs
import priority
import pull_plan
import sample_world
from harness import StubTestCase, logistics_requests


class _Host:
    name = "test_vehicle"
    cruise_throttle = 0.7
    SAFETY_MARGIN_MULTIPLIER = 1.2

    def distance_between(self, p1, p2):
        return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5

    def wh_per_meter_at_throttle(self, _throttle):
        return 0.02

    def minimum_wh_per_meter(self):
        return 0.015

    def emergency_reserve(self):
        return 5.0


class SourceUsefulTests(StubTestCase):
    def test_matches_any_plan_take(self):
        rnd = random.Random(7)
        items = ["a", "b", "c", "d"]
        for _ in range(3000):
            source = {"available": {i: rnd.choice([0, 1, 5]) for i in rnd.sample(items, rnd.randint(0, 4))}}
            if rnd.random() < 0.5:
                source["tiers"] = {b: {} for b in priority.BANDS}
                source["tiers"][priority.NEED] = dict(source["available"])
                source["tiers"][priority.STOCK] = {i: rnd.choice([0, 2]) for i in source["available"]}
            left = logistics_requests.route_left(
                {
                    priority.NEED: {i: rnd.choice([0, 3]) for i in items},
                    priority.STOCK: {i: rnd.choice([0, 4]) for i in items},
                }
            )
            cap = rnd.choice([0, 1, 10])
            expected = any(
                sum(logistics_requests.plan_take(source, i, left, cap).values()) > 0 for i in source["available"]
            )
            self.assertEqual(logistics_requests.source_useful(source, left, cap), expected)


class PodPlanningTests(StubTestCase):
    def test_load_tops_up_own_pod_before_empty_ones(self):
        pods = [[100, None, 0], [100, None, 0], [250, None, 0]]
        drone_haul_plan.load_pods(pods, "a", 50)
        drone_haul_plan.load_pods(pods, "b", 120)
        drone_haul_plan.load_pods(pods, "a", 30)
        self.assertEqual(pods, [[100, "a", 80], [100, "b", 100], [250, "b", 20]])
        self.assertEqual(drone_haul_plan.pod_room(pods, "a"), 20)
        self.assertEqual(drone_haul_plan.pod_room(pods, "b"), 230)
        self.assertEqual(drone_haul_plan.pod_room(pods, "c"), 0)

    def test_no_stop_for_material_without_a_pod(self):
        dest = {
            "outpost_id": "dest",
            "coords": (1000.0, 0.0),
            "tiers": {priority.NEED: {"a": 150, "b": 100, "c": 100}},
            "deficits": {"a": 150, "b": 100, "c": 100},
        }
        sources = [
            {"kind": "drill", "id": "s_a", "coords": (100.0, 0.0), "available": {"a": 150}},
            {"kind": "drill", "id": "s_b", "coords": (200.0, 0.0), "available": {"b": 100}},
            {"kind": "drill", "id": "s_c", "coords": (300.0, 0.0), "available": {"c": 100}},
        ]
        # 300 units of room, but "a" latches two of the three pods: "c" has none left.
        route = drone_haul_plan.plan_route_for(dest, sources, 300, (0.0, 0.0), None, [100, 100, 100])
        self.assertEqual([(s["id"], loads) for s, loads in route], [("s_a", [("a", 150)]), ("s_b", [("b", 100)])])


class _PodHost(_Host):
    """_Host with two Small Cargo Pods mounted."""

    plated = False

    class drone:
        @staticmethod
        def modules():
            return [
                game_stubs.MountSlot(0, "cargo", "cargo_pod_small"),
                game_stubs.MountSlot(1, "cargo", "cargo_pod_small"),
            ]


class CandidateOrderTests(StubTestCase):
    def test_shortest_order_keeps_loads(self):
        far = {"id": "far", "coords": (300.0, 0.0)}
        near = {"id": "near", "coords": (100.0, 0.0)}
        route = [(far, [("a", 5)]), (near, [("b", 7)])]
        dest = {"outpost_id": "dest", "coords": (1000.0, 0.0)}
        dist = drone_haul_plan.distance_table((0.0, 0.0), dest, [far, near])
        ordered, meters = drone_haul_plan.shortest_order(route, dist, "dest")
        self.assertEqual([(s["id"], loads) for s, loads in ordered], [("near", [("b", 7)]), ("far", [("a", 5)])])
        self.assertAlmostEqual(meters, 1000.0)
        single, meters = drone_haul_plan.shortest_order(route[:1], dist, "dest")
        self.assertIs(single[0], route[0])
        self.assertAlmostEqual(meters, 1000.0)

    def test_first_source_already_visited_is_skipped(self):
        dest = {
            "outpost_id": "dest",
            "coords": (1000.0, 0.0),
            "tiers": {priority.NEED: {"a": 50, "b": 50}},
            "deficits": {"a": 50, "b": 50},
        }
        sources = [
            {"kind": "drill", "id": "s_a", "coords": (100.0, 0.0), "available": {"a": 50}},
            {"kind": "drill", "id": "s_b", "coords": (200.0, 0.0), "available": {"b": 50}},
        ]
        stats = {}
        out = list(drone_haul_plan.candidate_routes(_PodHost(), [dest], sources, 400, (0.0, 0.0), [], stats))
        self.assertEqual(len(out), 1)
        self.assertEqual([s["id"] for s, _l in out[0][1]["route"]], ["s_a", "s_b"])
        self.assertEqual((stats["atomic"] + stats["stepped"], stats["covered"]), (1, 1))


class RouteAtomicTests(StubTestCase):
    def test_bound_counts_sources_and_items_over_all_sources(self):
        lr = logistics_requests
        room = lr.ROUTE_ATOMIC_MAX_COST - lr.ROUTE_COST_BASE
        fits = room // (lr.ROUTE_COST_PER_SOURCE + lr.ROUTE_COST_PER_ITEM)
        self.assertTrue(lr.route_atomic_ok([{"available": {"a": 1}}] * fits))
        self.assertFalse(lr.route_atomic_ok([{"available": {"a": 1}}] * (fits + 1)))
        # Items add up over sources: one item each on many sources costs like many on one.
        many = (room - lr.ROUTE_COST_PER_SOURCE) // lr.ROUTE_COST_PER_ITEM + 1
        self.assertFalse(lr.route_atomic_ok([{"available": {f"i{k}": 1 for k in range(many)}}]))
        self.assertTrue(lr.route_atomic_ok([]))

    def test_haul_gate_charges_items_per_demand_tier(self):
        dhp = drone_haul_plan
        room = logistics_requests.ROUTE_ATOMIC_MAX_COST - dhp.HAUL_COST_BASE - dhp.HAUL_COST_PER_SOURCE
        items = room // dhp.HAUL_COST_PER_ITEM_TIER
        sources = [{"available": {f"i{k}": 1 for k in range(items)}}]
        one_tier = {"tiers": {priority.NEED: {"i0": 5}, priority.STOCK: {}}}
        two_tiers = {"tiers": {priority.NEED: {"i0": 5}, priority.STOCK: {"i1": 5}}}
        self.assertTrue(dhp.haul_atomic_ok(one_tier, sources))
        self.assertFalse(dhp.haul_atomic_ok(two_tiers, sources))

    def test_atomic_and_direct_candidates_agree(self):
        dests, sources = sample_world.route_scenario("small", seed=4)
        hauler = _Host()
        pods = [200, 200]
        services = [{"coords": (0.0, 0.0)}]
        rates = drone_haul_plan.fuel_rates(hauler)
        for first in sources:
            direct = drone_haul_plan.haul_candidate(dests[0], sources, 400, (0.0, 0.0), first, pods, services, rates)
            atomic = drone_haul_plan.run_atomic(
                drone_haul_plan.haul_candidate, dests[0], sources, 400, (0.0, 0.0), first, pods, services, rates
            )
            self.assertEqual(direct, atomic)

    def test_pull_chain_checks_are_capped(self):
        rnd = random.Random(2)
        sources = [
            {"id": f"s{k}", "coords": (rnd.uniform(-900, 900), rnd.uniform(-900, 900)), "available": {"ore": 5}}
            for k in range(40)
        ]
        candidate = pull_plan.pull_candidate(
            sources[0], sources, {priority.NEED: {"ore": 1000}}, 10000, (0.0, 0.0), (5.0, 5.0)
        )
        self.assertLessEqual(candidate["chain_checks"].count("direct="), pull_plan.PULL_CHAIN_NOTES_MAX)
        self.assertIn("more", candidate["chain_checks"])


if __name__ == "__main__":
    unittest.main()
