"""Tests for lib/construction_plan.py: job scan, station range check, progress lookup, and the worst atomic slice per function."""
import os
import sys
import unittest

import harness  # noqa: F401  (puts the tiered lib/ folders on sys.path)
import construction_plan as cp


class Pos:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class Job:
    def __init__(self, job_id, x, y, item: "str | None" = "pipe", count=1, progress=0.0, kind="pipe"):
        self.id = job_id
        self.position = Pos(x, y) if x is not None else None
        self.required_item = item
        self.required_count = count
        self.progress = progress
        self.kind = kind


def ops(fn, *args):
    """CPython opcodes executed inside construction_plan while fn(*args) runs (pessimistic stand-in for game steps)."""
    total = [0]
    here = os.path.basename(cp.__file__)

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


def scan(jobs, cargo=None, claims=None, failed=None, tick=1000):
    return cp.scan_jobs(jobs, (0.0, 0.0), cargo or {}, claims or {}, "pioneer_1", tick, 600, failed or set())


class ScanTests(unittest.TestCase):
    def test_matching_sorted_nearest_first(self):
        jobs = [Job(f"bp_{i}", 100 - i, 0) for i in range(70)]
        ids, open_rows, matching = scan(jobs, cargo={"pipe": 5})
        self.assertEqual(len(ids), 70)
        self.assertEqual(len(open_rows), 70)
        self.assertEqual([row["id"] for _, _, row in matching][:3], ["bp_69", "bp_68", "bp_67"])

    def test_cargo_and_deconstruction(self):
        jobs = [Job("needs_3", 1, 0, count=3), Job("needs_1", 2, 0, count=1), Job("decon", 3, 0, item=None, count=0)]
        _, open_rows, matching = scan(jobs, cargo={"pipe": 2})
        self.assertEqual(len(open_rows), 3)
        self.assertEqual([row["id"] for _, _, row in matching], ["needs_1", "decon"])

    def test_peer_claims_and_failed_skipped(self):
        jobs = [Job("mine", 1, 0), Job("peer_fresh", 2, 0), Job("peer_stale", 3, 0), Job("failed", 4, 0)]
        claims = {
            "build_mine": {"vehicle": "pioneer_1", "tick": 999},
            "build_peer_fresh": {"vehicle": "pioneer_2", "tick": 900},
            "build_peer_stale": {"vehicle": "pioneer_2", "tick": 100},
        }
        ids, open_rows, _ = scan(jobs, cargo={"pipe": 9}, claims=claims, failed={"failed"})
        self.assertEqual(ids, ["mine", "peer_fresh", "peer_stale", "failed"])
        self.assertEqual([row["id"] for row in open_rows], ["mine", "peer_stale"])

    def test_unknown_tick_keeps_peer_claim(self):
        _, open_rows, _ = scan([Job("peer", 1, 0)], claims={"build_peer": {"vehicle": "pioneer_2", "tick": 0}}, tick=0)
        self.assertEqual(open_rows, [])

    def test_no_coords_sorted_last(self):
        _, _, matching = scan([Job("lost", None, None), Job("near", 5, 0)], cargo={"pipe": 9})
        self.assertEqual([row["id"] for _, _, row in matching], ["near", "lost"])

    def test_station_trip_wh(self):
        rows = scan([Job("a", 30, 40, progress=0.9), Job("lost", None, None)])[1]
        trips = cp.station_trip_wh(rows, [(0.0, 0.0), (1000.0, 0.0)], 0.1, 40.0, 0.25, 1.05, 8.0)
        self.assertAlmostEqual(trips[0][1], ((2 * 50 * 0.1) + 0.1 * 40.0) * 1.05 + 8.0)
        self.assertIsNone(trips[1][1])

    def test_job_progress(self):
        jobs = [Job(f"bp_{i}", 0, 0, progress=i / 1000.0) for i in range(600)]
        self.assertEqual(cp.job_progress(jobs, "bp_513"), 0.513)
        self.assertIsNone(cp.job_progress(jobs, "missing"))

    def test_batch_count(self):
        rows = scan([Job("a", 1, 0, count=20), Job("b", 2, 0, count=20), Job("c", 3, 0, item="wire", count=5)])[1]
        self.assertEqual(cp.batch_count(rows, "pipe"), 40)
        self.assertEqual(cp.batch_count(rows, "pipe", max_limit=30), 30)

    def test_ids_needing(self):
        rows = [{"id": "a", "item": "pipe"}, {"id": "b", "item": "line"}, {"id": "c", "item": "pipe"}, {"id": "d", "item": None}]
        self.assertEqual(cp.ids_needing(rows, "pipe"), ["a", "c"])
        self.assertEqual(cp.ids_needing(rows, "bridge"), [])

    def test_peer_builders(self):
        status = {
            "me": {"role": "constructor", "home": "outpost_1", "state": "BUILDING", "tick": 1000},
            "peer": {"role": "constructor", "home": "outpost_1", "state": "BUILDING", "tick": 900},
            "other_home": {"role": "constructor", "home": "outpost_2", "state": "BUILDING", "tick": 1000},
            "miner": {"role": "miner", "home": "outpost_1", "state": "MINING", "tick": 1000},
            "stale": {"role": "constructor", "home": "outpost_1", "state": "BUILDING", "tick": 100},
            "recalled": {"role": "constructor", "home": "outpost_1", "state": "RECALLED", "tick": 1000},
            "junk": None,
        }
        self.assertEqual(cp.peer_builders(status, "me", "outpost_1", 1000, 500), ["peer"])
        self.assertEqual(cp.peer_builders(status, "me", "outpost_1", 0, 500), ["peer", "stale"])
        self.assertEqual(cp.peer_builders({}, "me", "outpost_1", 1000, 500), [])

    def test_fair_share(self):
        self.assertEqual(cp.fair_share(200, 200, 1), 200)
        self.assertEqual(cp.fair_share(200, 200, 2), 100)
        self.assertEqual(cp.fair_share(200, 201, 2), 101)
        self.assertEqual(cp.fair_share(40, 200, 2), 40)
        self.assertEqual(cp.fair_share(200, 0, 2), 0)


class BudgetTests(unittest.TestCase):
    """Each atomic call stays under ATOMIC_STEP_BUDGET at its worst input (the hard cap is 10,000 steps)."""

    def test_scan_slice_worst(self):
        jobs = [Job(f"blueprint_{i}", 10.0 + i, 5.0) for i in range(cp.JOB_CHUNK)]
        claims = {f"build_blueprint_{i}": {"vehicle": "pioneer_2", "tick": 1} for i in range(cp.JOB_CHUNK)}
        self.assertLess(ops(cp.scan_slice, jobs, (0.0, 0.0), {"pipe": 9}, claims, "pioneer_1", 1000, 600, set()), cp.ATOMIC_STEP_BUDGET)

    def test_station_trip_wh_worst(self):
        rows = scan([Job(f"blueprint_{i}", 10.0 + i, 5.0) for i in range(cp.TRIP_CHUNK)])[1]
        stations = [(float(i), 0.0) for i in range(12)]
        self.assertLess(ops(cp.station_trip_wh, rows, stations, 0.1, 40.0, 0.25, 1.05, 8.0), cp.ATOMIC_STEP_BUDGET)

    def test_find_progress_worst(self):
        jobs = [Job(f"blueprint_{i}", 0, 0) for i in range(cp.PROGRESS_CHUNK)]
        self.assertLess(ops(cp.find_progress, jobs, "missing"), cp.ATOMIC_STEP_BUDGET)


if __name__ == "__main__":
    unittest.main()
