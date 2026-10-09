"""Route planner helpers shared by drone_haul_plan.py and vehicle_cargo.py (logistics_requests.source_useful(), route_atomic_ok())."""
import random
import unittest

from harness import StubTestCase, logistics_requests
import sample_world
import drone_haul_plan
import vehicle_cargo


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


def _with_host(mixin):
    cls = type("Test" + mixin.__name__, (mixin,), {"_host": property(lambda self: self._test_host)})
    obj = cls.__new__(cls)
    obj._test_host = _Host()
    return obj


class SourceUsefulTests(StubTestCase):
    def test_matches_any_plan_take(self):
        rnd = random.Random(7)
        items = ["a", "b", "c", "d"]
        for _ in range(3000):
            source = {"available": {i: rnd.choice([0, 1, 5]) for i in rnd.sample(items, rnd.randint(0, 4))}}
            if rnd.random() < 0.5:
                source["tiers"] = {logistics_requests.NEED: dict(source["available"]), logistics_requests.BUFFER: {i: rnd.choice([0, 2]) for i in source["available"]}}
            left = {logistics_requests.NEED: {i: rnd.choice([0, 3]) for i in items}, logistics_requests.BUFFER: {i: rnd.choice([0, 4]) for i in items}}
            cap = rnd.choice([0, 1, 10])
            expected = any(sum(logistics_requests.plan_take(source, i, left, cap).values()) > 0 for i in source["available"])
            self.assertEqual(logistics_requests.source_useful(source, left, cap), expected)


class RouteAtomicTests(StubTestCase):
    def test_bound_counts_sources_and_fullest_source(self):
        per_source, per_item = logistics_requests.ROUTE_COST_PER_SOURCE, logistics_requests.ROUTE_COST_PER_ITEM
        fits = (logistics_requests.ROUTE_ATOMIC_MAX_COST - per_item) // per_source
        self.assertTrue(logistics_requests.route_atomic_ok([{"available": {"a": 1}}] * fits))
        self.assertFalse(logistics_requests.route_atomic_ok([{"available": {"a": 1}}] * (fits + 1)))
        self.assertTrue(logistics_requests.route_atomic_ok([]))

    def test_atomic_and_direct_candidates_agree(self):
        dests, sources = sample_world.route_scenario("small", seed=4)
        hauler = _with_host(drone_haul_plan.DroneHaulPlanMixin)
        room = {i: 200 for s in sources for i in s["available"]}
        services = [{"coords": (0.0, 0.0)}]
        rates = hauler._fuel_rates()
        for first in sources:
            direct = hauler._haul_candidate(dests[0], sources, 400, (0.0, 0.0), first, room, services, rates)
            atomic = drone_haul_plan.run_atomic(hauler._haul_candidate, dests[0], sources, 400, (0.0, 0.0), first, room, services, rates)
            self.assertEqual(direct, atomic)

    def test_pull_chain_checks_are_capped(self):
        rnd = random.Random(2)
        sources = [{"id": f"s{k}", "coords": (rnd.uniform(-900, 900), rnd.uniform(-900, 900)), "available": {"ore": 5}} for k in range(40)]
        puller = _with_host(vehicle_cargo.VehicleCargoMixin)
        candidate = puller._pull_candidate(sources[0], sources, {logistics_requests.NEED: {"ore": 1000}}, 10000, (0.0, 0.0), (5.0, 5.0))
        self.assertLessEqual(candidate["chain_checks"].count("direct="), vehicle_cargo.PULL_CHAIN_NOTES_MAX)
        self.assertIn("more", candidate["chain_checks"])


if __name__ == "__main__":
    unittest.main()
