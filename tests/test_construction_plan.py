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


def scan(jobs, cargo=None, claims=None, failed=None, tick=1000, priorities=None):
    return cp.scan_jobs(jobs, (0.0, 0.0), cargo or {}, claims or {}, "pioneer_1", tick, 600, failed or set(), priorities or {})


class ScanTests(unittest.TestCase):
    def test_matching_sorted_nearest_first(self):
        jobs = [Job(f"bp_{i}", 100 - i, 0) for i in range(70)]
        ids, open_rows, matching = scan(jobs, cargo={"pipe": 5})
        self.assertEqual(len(ids), 70)
        self.assertEqual(len(open_rows), 70)
        self.assertEqual([row["id"] for *_, row in matching][:3], ["bp_69", "bp_68", "bp_67"])

    def test_cargo_and_deconstruction(self):
        jobs = [Job("needs_3", 1, 0, count=3), Job("needs_1", 2, 0, count=1), Job("decon", 3, 0, item=None, count=0)]
        _, open_rows, matching = scan(jobs, cargo={"pipe": 2})
        self.assertEqual(len(open_rows), 3)
        self.assertEqual([row["id"] for *_, row in matching], ["needs_1", "decon"])

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
        self.assertEqual([row["id"] for *_, row in matching], ["near", "lost"])

    def test_priority_sorts_before_distance(self):
        jobs = [Job("near_ahead", 1, 0), Job("far_normal", 90, 0), Job("near_normal", 5, 0)]
        _, open_rows, matching = scan(jobs, cargo={"pipe": 9}, priorities={"near_ahead": 1, "gone": 1})
        self.assertEqual([row["id"] for *_, row in matching], ["near_normal", "far_normal", "near_ahead"])
        self.assertEqual({row["id"]: row["prio"] for row in open_rows}, {"near_ahead": 1, "far_normal": 0, "near_normal": 0})

    def test_top_priority_and_filter(self):
        _, open_rows, _ = scan([Job("a", 1, 0), Job("b", 2, 0)], priorities={"a": 1, "b": 1})
        self.assertEqual(cp.top_priority(open_rows), 1)
        self.assertEqual(cp.top_priority([]), cp.DEFAULT_PRIORITY)
        _, open_rows, _ = scan([Job("a", 1, 0), Job("b", 2, 0), Job("c", 3, 0)], priorities={"a": 1, "c": -1})
        self.assertEqual(cp.top_priority(open_rows), -1)
        self.assertEqual([row["id"] for row in cp.at_priority(open_rows, 0)], ["b"])

    def test_failed_high_priority_frees_lower(self):
        jobs = [Job("normal", 1, 0), Job("ahead", 2, 0)]
        _, open_rows, _ = scan(jobs, failed={"normal"}, priorities={"ahead": 1})
        self.assertEqual(cp.top_priority(open_rows), 1)

    def test_clean_and_stale_priorities(self):
        raw = {"a": 1, "b": "high", "c": True, "d": 0, "e": -2, "f": 1.5}
        self.assertEqual(cp.clean_priorities(raw), {"a": 1, "d": 0, "e": -2})
        self.assertEqual(cp.clean_priorities(None), {})
        self.assertEqual(cp.clean_priorities([1]), {})
        self.assertEqual(cp.stale_priorities({"a": 1, "b": 0}, {"b", "c"}), ["a"])

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


class LotTests(unittest.TestCase):
    def test_peer_lot_skipped_own_lot_first(self):
        jobs = [Job("near", 1, 0), Job("peer", 2, 0), Job("own_far", 50, 0)]
        _, open_rows, matching = cp.scan_jobs(jobs, (0.0, 0.0), {"pipe": 9}, {}, "pioneer_1", 1000, 600, set(), {}, {"peer"}, {"own_far"})
        self.assertEqual([row["id"] for row in open_rows], ["near", "own_far"])
        self.assertEqual([row["id"] for *_, row in matching], ["own_far", "near"])

    def test_clean_and_taken(self):
        raw = {"p1": {"ids": ["a", "b"], "tick": 5}, "p2": {"ids": ["c"]}, "bad": {"ids": "x"}, "junk": 3}
        lots = cp.clean_lots(raw)
        self.assertEqual(lots, {"p1": ["a", "b"], "p2": ["c"]})
        self.assertEqual(cp.taken_ids(lots, ["p2", "gone"]), {"c"})
        self.assertEqual(cp.clean_lots(None), {})

    def test_grow_lot_follows_chain_and_material(self):
        # A line of segments 10 m apart, listed out of order, plus other material and a far site.
        jobs = [Job(f"bp_{x}", x, 0, item="line", count=1) for x in (40, 0, 30, 10, 20)]
        jobs += [Job("pipe_near", 5, 0, item="pipe"), Job("far_site", 500, 0, item="line", count=1)]
        rows = scan(jobs)[1]
        seed = next(row for row in rows if row["id"] == "bp_0")
        self.assertEqual([row["id"] for row in cp.grow_lot(seed, rows, 3)], ["bp_0", "bp_10", "bp_20"])
        self.assertEqual([row["id"] for row in cp.grow_lot(seed, rows, 99)], ["bp_0", "bp_10", "bp_20", "bp_30", "bp_40", "far_site"])

    def test_grow_lot_splits_line_between_builders(self):
        rows = scan([Job(f"bp_{i}", i * 10, 0, item="line", count=1) for i in range(20)])[1]
        first = cp.grow_lot(rows[0], rows, 10)
        taken = {row["id"] for row in first}
        rest = [row for row in rows if row["id"] not in taken]
        second = cp.grow_lot(rest[0], rest, 10)
        self.assertEqual([row["id"] for row in second], [f"bp_{i}" for i in range(10, 20)])

    def test_grow_lot_many_rows_chunked(self):
        rows = scan([Job(f"bp_{i}", i, 0, item="line", count=1) for i in range(cp.LOT_STEP_VISITS * 3)])[1]
        lot = cp.grow_lot(rows[0], rows, 5)
        self.assertEqual([row["id"] for row in lot], ["bp_0", "bp_1", "bp_2", "bp_3", "bp_4"])

    def test_deconstruction_lot_counts_jobs(self):
        rows = scan([Job(f"d_{i}", i, 0, item=None, count=0) for i in range(5)] + [Job("line", 0.5, 0)])[1]
        self.assertEqual([row["id"] for row in cp.grow_lot(rows[0], rows, 3)], ["d_0", "d_1", "d_2"])

    def test_lot_prefix(self):
        rows = scan([Job("a", 0, 0, count=20), Job("b", 1, 0, count=20), Job("c", 2, 0, count=20)])[1]
        self.assertEqual([row["id"] for row in cp.lot_prefix(rows, 45)], ["a", "b"])
        self.assertEqual([row["id"] for row in cp.lot_prefix(rows, 5)], ["a"])


class BudgetTests(unittest.TestCase):
    """Each atomic call stays under ATOMIC_STEP_BUDGET at its worst input (the hard cap is 10,000 steps)."""

    def test_scan_slice_worst(self):
        jobs = [Job(f"blueprint_{i}", 10.0 + i, 5.0) for i in range(cp.JOB_CHUNK)]
        claims = {f"build_blueprint_{i}": {"vehicle": "pioneer_2", "tick": 1} for i in range(cp.JOB_CHUNK)}
        priorities = {f"blueprint_{i}": 1 for i in range(cp.JOB_CHUNK)}
        self.assertLess(ops(cp.scan_slice, jobs, (0.0, 0.0), {"pipe": 9}, claims, "pioneer_1", 1000, 600, set(), priorities, {"x"}, {"blueprint_1"}), cp.ATOMIC_STEP_BUDGET)

    def test_station_trip_wh_worst(self):
        rows = scan([Job(f"blueprint_{i}", 10.0 + i, 5.0) for i in range(cp.TRIP_CHUNK)])[1]
        stations = [(float(i), 0.0) for i in range(12)]
        self.assertLess(ops(cp.station_trip_wh, rows, stations, 0.1, 40.0, 0.25, 1.05, 8.0), cp.ATOMIC_STEP_BUDGET)

    def test_find_progress_worst(self):
        jobs = [Job(f"blueprint_{i}", 0, 0) for i in range(cp.PROGRESS_CHUNK)]
        self.assertLess(ops(cp.find_progress, jobs, "missing"), cp.ATOMIC_STEP_BUDGET)

    def test_grow_lot_step_worst(self):
        # Small candidate lists fit several whole passes (and appends) into one call, long ones a partial pass.
        for size in range(1, cp.LOT_STEP_VISITS * 2):
            rows = scan([Job(f"blueprint_{i}", 10.0 + i, 5.0, item="line") for i in range(size)])[1]
            state = cp.new_lot_state(rows[0], rows, 10 ** 6)
            self.assertLess(ops(cp.grow_lot_step, state), cp.ATOMIC_STEP_BUDGET, size)


if __name__ == "__main__":
    unittest.main()
