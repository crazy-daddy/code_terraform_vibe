import os
import random
import sys
import unittest

import harness  # noqa: F401  (puts the tiered lib/ folders on sys.path)
import harvester_pure as hp

SECTORS = [f"{r}{c}" for r in "ABCDEFGH" for c in range(1, 25)]
OPEN = ("empty", "unknown", "item")
TABLE = {"a": ["light"], "b": ["light", "water"], "c": ["light", "water", "salt"], "d": ["salt"]}


def ops(fn, *args):
    """CPython opcodes executed inside harvester_pure while fn(*args) runs (pessimistic stand-in for game steps)."""
    total = [0]
    here = os.path.basename(hp.__file__)

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


def reference_care(sector, row, table, salt_ok, kept):
    """The per-cell hand_care() rule the scan implements."""
    status, plant, _growth, light_h, water_h, salt_h, lit, watered, salted = row
    if status not in (hp.KEPT_STATUSES if sector in kept else hp.HAND_STATUSES) or not plant:
        return []
    hours = {"light": light_h, "water": water_h, "salt": salt_h}
    flags = {"light": lit, "water": watered, "salt": salted}
    out = []
    for kind in table.get(plant, ()):
        remaining = hours[kind] or 0
        if bool(flags[kind]) and remaining <= 0:
            continue
        if kind == "salt" and not salt_ok:
            continue
        out.append((kind, remaining))
    return out


def random_rows(rnd, n):
    rows = []
    for sector in rnd.sample(SECTORS, n):
        rows.append((sector, (rnd.choice(["growing", "stalled", "mature"]), rnd.choice(["a", "b", "c", "d", "e", None, ""]),
                              rnd.choice([0, 0.5, 0.8, 1.0, None]),
                              rnd.choice([0, 2.5, 30, None]), rnd.choice([0, 2.5, 30, None]), rnd.choice([0, 2.5, 30, None]),
                              rnd.random() < .5, rnd.random() < .5, rnd.random() < .5)))
    return rows


class ScanRowsTests(unittest.TestCase):
    def test_matches_the_per_cell_rule(self):
        rnd = random.Random(3)
        for salt_ok in (False, True):
            slots = hp.care_slots(TABLE, salt_ok)
            for _ in range(20):
                rows = random_rows(rnd, 60)
                kept = set(rnd.sample(SECTORS, 30))
                care, mature, stalled, productive = hp.scan_rows(rows, slots, kept)
                expected = {s: c for s, c in ((s, reference_care(s, v, TABLE, salt_ok, kept)) for s, v in rows) if c}
                self.assertEqual(care, expected)
                self.assertEqual(list(care), list(expected))
                self.assertEqual(mature, sum(1 for _, v in rows if v[0] == "mature"))
                self.assertEqual(stalled, sum(1 for _, v in rows if v[0] == "stalled"))
                self.assertEqual(productive, set(v[1] for _, v in rows if v[0] != "stalled" and v[1]))

    def test_chunks_add_up(self):
        rows = random_rows(random.Random(5), 100)
        slots = hp.care_slots(TABLE, True)
        whole = hp.scan_rows(rows, slots, set())
        parts = [hp.scan_rows(rows[i:i + 32], slots, set()) for i in range(0, len(rows), 32)]
        care = {}
        for part in parts:
            care.update(part[0])
        self.assertEqual(care, whole[0])
        self.assertEqual(sum(p[1] for p in parts), whole[1])
        self.assertEqual(sum(p[2] for p in parts), whole[2])


class DemandTests(unittest.TestCase):
    def test_due_targets(self):
        items = [("A1", [("light", 1.0), ("water", 9.0)]), ("A2", [("salt", 5.0)]), ("A3", [("light", 0)])]
        self.assertEqual(hp.due_targets(items, 4.0), {"A1": ["light"], "A3": ["light"]})

    def test_counts_keep_first_seen_order(self):
        items = [("A1", "x"), ("A2", "y"), ("A3", "x"), ("A4", "z")]
        seed_ids = {"x": "seed_x", "y": "seed_y", "z": "seed_z"}
        self.assertEqual(list(hp.rotation_counts(items, {"A2"}, seed_ids).items()), [("seed_x", 2), ("seed_z", 1)])
        statuses = {"A1": "growing", "A2": "empty", "A3": "item", "A4": "growing"}
        now = hp.needed_seeds(items, statuses, OPEN, {"A4"}, seed_ids)
        self.assertEqual(list(now.items()), [("seed_y", 1), ("seed_x", 1), ("seed_z", 1)])
        self.assertEqual(hp.merge_counts([{"a": 1, "b": 2}, {"b": 1, "c": 4}]), {"a": 1, "b": 3, "c": 4})

    def test_soon_needs_layout_species_and_maturity(self):
        rows = [("A1", ("mature", "x", 1.0, 0, 0, 0, False, False, False)),
                ("A2", ("growing", "x", 0.8, 0, 0, 0, False, False, False)),
                ("A3", ("growing", "x", 0.2, 0, 0, 0, False, False, False)),
                ("A4", ("mature", "y", 1.0, 0, 0, 0, False, False, False)),
                ("A5", ("mature", "x", 1.0, 0, 0, 0, False, False, False)),
                ("A6", ("growing", "x", None, 0, 0, 0, False, False, False))]
        active = {"A1": "x", "A2": "x", "A3": "x", "A4": "x", "A5": "x", "A6": "x"}
        self.assertEqual(hp.soon_sectors(rows, active, {"A5"}, 0.75), ["A1", "A2"])


class WorstCaseStepTests(unittest.TestCase):
    """Each atomic call stays under ATOMIC_STEP_BUDGET at its worst input (the hard cap is 10,000 steps)."""

    def test_scan_rows_chunk(self):
        slots = hp.care_slots(TABLE, True)
        for status in ("growing", "mature"):
            rows = [(s, (status, "c", 0.9, 5.0, 5.0, 5.0, False, False, False)) for s in SECTORS[:hp.ROW_CHUNK]]
            self.assertLess(ops(hp.scan_rows, rows, slots, set(SECTORS)), hp.ATOMIC_STEP_BUDGET)

    def test_due_chunk(self):
        items = [(s, [("light", 1.0), ("water", 2.0), ("salt", 3.0)]) for s in SECTORS[:hp.CARE_CHUNK]]
        self.assertLess(ops(hp.due_targets, items, 4.0), hp.ATOMIC_STEP_BUDGET)

    def test_soon_chunk(self):
        rows = [(s, ("mature", "x", 1.0, 5.0, 5.0, 5.0, False, False, False)) for s in SECTORS[:hp.SOON_CHUNK]]
        active = {s: "x" for s in SECTORS}
        self.assertLess(ops(hp.soon_sectors, rows, active, set(), 0.75), hp.ATOMIC_STEP_BUDGET)

    def test_item_chunks(self):
        items = [(s, "x") for s in SECTORS[:hp.ITEM_CHUNK]]
        seed_ids = {"x": "seed_x"}
        for status in ("empty", "growing"):
            statuses = {s: status for s in SECTORS}
            self.assertLess(ops(hp.needed_seeds, items, statuses, OPEN, set(SECTORS), seed_ids), hp.ATOMIC_STEP_BUDGET)
        self.assertLess(ops(hp.rotation_counts, items, set(), seed_ids), hp.ATOMIC_STEP_BUDGET)
        self.assertLess(ops(hp.seeded_items, items, set(SECTORS), set(SECTORS)), hp.ATOMIC_STEP_BUDGET)


if __name__ == "__main__":
    unittest.main()
