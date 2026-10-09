"""Tests for lib/scan_groups.py (scan stops scored by contacts covered per metre)."""
import os
import random
import sys
import unittest

import harness
import scan_groups as sg


def dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


class GeometryTests(unittest.TestCase):
    def test_circle_crossings_sit_at_reach_from_both_contacts(self):
        crossings = sg.circle_crossings((0, 0), (60, 0), 50.0)
        self.assertEqual(len(crossings), 2)
        for p in crossings:
            self.assertAlmostEqual(dist(p, (0, 0)), 50.0)
            self.assertAlmostEqual(dist(p, (60, 0)), 50.0)
        self.assertEqual(sg.circle_crossings((0, 0), (100, 0), 50.0), [(50.0, 0.0)])
        self.assertEqual(sg.circle_crossings((0, 0), (101, 0), 50.0), [])

    def test_crossing_covers_a_triple_no_contact_covers(self):
        # Contacts 90 apart, reach 50: no contact reaches both others, a crossing reaches all three.
        points = [(0, 0), (90, 0), (45, 60)]
        best = sg.plan_stops(points, 50.0, (0, 0))[0]
        self.assertEqual(sorted(best["members"]), [0, 1, 2])
        for p in points:
            self.assertLess(sum(1 for q in points if dist(p, q) <= 50.0), 3)


def exhaustive_best(points, reach, start, home, weights=None):
    """Best score over every contact and every crossing, no pruning: the reference for the plan."""
    weights = weights or [1] * len(points)
    kept = sorted(range(len(points)), key=lambda i: dist(start, points[i]) / weights[i])[:sg.MAX_CONTACTS]
    weight = {points[i]: weights[i] for i in kept}
    points = [points[i] for i in kept]
    cands = list(points)
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            cands += sg.circle_crossings(points[i], points[j], reach)
    reach2 = reach * reach + 1e-6
    best = 0.0
    for c in cands:
        members = [p for p in points if (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 <= reach2]
        stand = sg._pulled(c, members, start, reach2)
        best = max(best, sum(weight[m] for m in members) / sg.stop_cost(stand, start, home))
    return best


def ops(fn, *args):
    """CPython opcodes executed inside scan_groups while fn(*args) runs (pessimistic stand-in for game steps)."""
    total = [0]
    here = os.path.basename(sg.__file__)

    def tracer(frame, event, arg):
        frame.f_trace_opcodes = True
        if event == "opcode" and os.path.basename(frame.f_code.co_filename) == here:
            total[0] += 1
        return tracer

    previous = sys.gettrace()
    sys.settrace(tracer)
    try:
        fn(*args)
    finally:
        sys.settrace(previous)
    return total[0]


# (contacts, half-width of the square they lie in, reach): sparse to every contact within 2 * reach of all others.
LAYOUTS = [(40, 1500, 238.0), (40, 800, 238.0), (40, 300, 238.0), (20, 1500, 153.0), (30, 500, 42.0)]


class PlanTests(unittest.TestCase):
    def test_best_stop_matches_the_exhaustive_search(self):
        rng = random.Random(1)
        for n, size, reach in LAYOUTS:
            for _ in range(3):
                points = [(rng.uniform(-size, size), rng.uniform(-size, size)) for _ in range(n)]
                start = (rng.uniform(-size, size) / 2, rng.uniform(-size, size) / 2)
                best = sg.plan_stops(points, reach, start, (0.0, 0.0))[0]["score"]
                self.assertAlmostEqual(best, exhaustive_best(points, reach, start, (0.0, 0.0)), places=9)

    def test_weighted_best_stop_matches_the_exhaustive_search(self):
        rng = random.Random(3)
        for n, size, reach in LAYOUTS:
            for _ in range(3):
                points = [(rng.uniform(-size, size), rng.uniform(-size, size)) for _ in range(n)]
                weights = [rng.choice([1, 1, sg.OUTPOST_WEIGHT]) for _ in range(n)]
                start = (rng.uniform(-size, size) / 2, rng.uniform(-size, size) / 2)
                best = sg.plan_stops(points, reach, start, (0.0, 0.0), weights)[0]["score"]
                self.assertAlmostEqual(best, exhaustive_best(points, reach, start, (0.0, 0.0), weights), places=9)

    def test_every_plan_step_stays_under_the_atomic_budget(self):
        rng = random.Random(2)
        for n, size, reach in LAYOUTS:
            points = [(rng.uniform(-size, size), rng.uniform(-size, size)) for _ in range(n)]
            weights = [rng.choice([1, sg.OUTPOST_WEIGHT]) for _ in range(n)]
            state = sg.new_plan(points, reach, (0.0, 0.0), (0.0, 0.0), weights)
            steps = 0
            while True:
                result = [False]
                cost = ops(lambda: result.__setitem__(0, sg.plan_step(state)))
                self.assertLess(cost, sg.ATOMIC_STEP_BUDGET, f"{n} contacts in +-{size}, reach {reach}, phase {state['phase']}")
                steps += 1
                if result[0]:
                    break
            self.assertTrue(state["stops"])


class StopTests(unittest.TestCase):
    def test_single_contact_drives_only_up_to_reach(self):
        stops = sg.plan_stops([(100, 0)], 40.0, (0, 0))
        self.assertEqual(len(stops), 1)
        self.assertEqual(stops[0]["members"], [0])
        self.assertAlmostEqual(stops[0]["stand"][0], 60.0, places=3)
        self.assertAlmostEqual(stops[0]["stand"][1], 0.0)

    def test_contact_already_in_reach_stays_put(self):
        self.assertEqual(sg.plan_stops([(10, 0)], 40.0, (0, 0))[0]["stand"], (0, 0))

    def test_zero_reach_stands_on_the_contact(self):
        stand = sg.plan_stops([(30, 40)], 0.0, (0, 0))[0]["stand"]
        self.assertLess(dist(stand, (30, 40)), 0.01)

    def test_best_stop_covers_its_members(self):
        points = [(200, 0), (240, 30), (230, -30), (900, 900)]
        reach = 50.0
        best = sg.plan_stops(points, reach, (0, 0))[0]
        self.assertEqual(sorted(best["members"]), [0, 1, 2])
        for i in best["members"]:
            self.assertLessEqual(dist(best["stand"], points[i]), reach + 1e-6)

    def test_far_cluster_beats_near_single(self):
        # Nearest-first would take the single at 100 m; three contacts at ~200 m score higher.
        points = [(100, 0), (0, 200), (40, 220), (-40, 220)]
        best = sg.plan_stops(points, 50.0, (0, 0))[0]
        self.assertEqual(sorted(best["members"]), [1, 2, 3])

    def test_outpost_single_beats_equal_cluster(self):
        # Same three-contact cluster as above against a lone contact near an outpost at the same distance.
        points = [(0, -200), (0, 200), (40, 220), (-40, 220)]
        weights = [sg.OUTPOST_WEIGHT, 1, 1, 1]
        self.assertEqual(sg.plan_stops(points, 50.0, (0, 0))[0]["members"], [1, 2, 3])
        self.assertEqual(sg.plan_stops(points, 50.0, (0, 0), weights=weights)[0]["members"], [0])

    def test_near_single_beats_far_single(self):
        best = sg.plan_stops([(400, 0), (100, 0)], 50.0, (0, 0))[0]
        self.assertEqual(best["members"], [1])

    def test_home_weight_prefers_the_stop_toward_home(self):
        # Equal drive from the scout at (500, 0); home at the origin.
        points = [(300, 0), (700, 0)]
        self.assertEqual(sg.plan_stops(points, 50.0, (500, 0), home=(0, 0))[0]["members"], [0])
        self.assertEqual(sg.plan_stops(points, 50.0, (500, 0), home=(1000, 0))[0]["members"], [1])


if __name__ == "__main__":
    unittest.main()
