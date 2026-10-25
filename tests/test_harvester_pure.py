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
    """CPython opcodes executed inside fn's module while fn(*args) runs (pessimistic stand-in for game steps)."""
    total = [0]
    here = os.path.basename(fn.__code__.co_filename)

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
        rows.append(
            (
                sector,
                (
                    rnd.choice(["growing", "stalled", "mature"]),
                    rnd.choice(["a", "b", "c", "d", "e", None, ""]),
                    rnd.choice([0, 0.5, 0.8, 1.0, None]),
                    rnd.choice([0, 2.5, 30, None]),
                    rnd.choice([0, 2.5, 30, None]),
                    rnd.choice([0, 2.5, 30, None]),
                    rnd.random() < 0.5,
                    rnd.random() < 0.5,
                    rnd.random() < 0.5,
                ),
            )
        )
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
                self.assertEqual(productive, {v[1] for _, v in rows if v[0] != "stalled" and v[1]})

    def test_chunks_add_up(self):
        rows = random_rows(random.Random(5), 100)
        slots = hp.care_slots(TABLE, True)
        whole = hp.scan_rows(rows, slots, set())
        parts = [hp.scan_rows(rows[i : i + 32], slots, set()) for i in range(0, len(rows), 32)]
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
        rows = [
            ("A1", ("mature", "x", 1.0, 0, 0, 0, False, False, False)),
            ("A2", ("growing", "x", 0.8, 0, 0, 0, False, False, False)),
            ("A3", ("growing", "x", 0.2, 0, 0, 0, False, False, False)),
            ("A4", ("mature", "y", 1.0, 0, 0, 0, False, False, False)),
            ("A5", ("mature", "x", 1.0, 0, 0, 0, False, False, False)),
            ("A6", ("growing", "x", None, 0, 0, 0, False, False, False)),
        ]
        active = {"A1": "x", "A2": "x", "A3": "x", "A4": "x", "A5": "x", "A6": "x"}
        self.assertEqual(hp.soon_sectors(rows, active, {"A5"}, 0.75), ["A1", "A2"])


class WorstCaseStepTests(unittest.TestCase):
    """Each atomic call stays under ATOMIC_STEP_BUDGET at its worst input (the hard cap is 10,000 steps)."""

    def test_scan_rows_chunk(self):
        slots = hp.care_slots(TABLE, True)
        for status in ("growing", "mature"):
            rows = [(s, (status, "c", 0.9, 5.0, 5.0, 5.0, False, False, False)) for s in SECTORS[: hp.ROW_CHUNK]]
            self.assertLess(ops(hp.scan_rows, rows, slots, set(SECTORS)), hp.ATOMIC_STEP_BUDGET)

    def test_due_chunk(self):
        items = [(s, [("light", 1.0), ("water", 2.0), ("salt", 3.0)]) for s in SECTORS[: hp.CARE_CHUNK]]
        self.assertLess(ops(hp.due_targets, items, 4.0), hp.ATOMIC_STEP_BUDGET)

    def test_soon_chunk(self):
        rows = [(s, ("mature", "x", 1.0, 5.0, 5.0, 5.0, False, False, False)) for s in SECTORS[: hp.SOON_CHUNK]]
        active = {s: "x" for s in SECTORS}
        self.assertLess(ops(hp.soon_sectors, rows, active, set(), 0.75), hp.ATOMIC_STEP_BUDGET)

    def test_item_chunks(self):
        items = [(s, "x") for s in SECTORS[: hp.ITEM_CHUNK]]
        seed_ids = {"x": "seed_x"}
        for status in ("empty", "growing"):
            statuses = {s: status for s in SECTORS}
            self.assertLess(ops(hp.needed_seeds, items, statuses, OPEN, set(SECTORS), seed_ids), hp.ATOMIC_STEP_BUDGET)
        self.assertLess(ops(hp.rotation_counts, items, set(), seed_ids), hp.ATOMIC_STEP_BUDGET)
        self.assertLess(ops(hp.seeded_items, items, set(SECTORS), set(SECTORS)), hp.ATOMIC_STEP_BUDGET)


class _Cell:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)


class CellRowsTests(unittest.TestCase):
    def test_rows_follow_row_attrs_with_defaults(self):
        full = _Cell(**{a: i for i, a in enumerate(hp.ROW_ATTRS)})
        rows = hp.cell_rows([("A1", full), ("A2", _Cell())])
        self.assertEqual(rows[0], ("A1", tuple(range(len(hp.ROW_ATTRS)))))
        self.assertEqual(rows[1], ("A2", ("", None, 0, 0, 0, 0, False, False, False)))

    def test_read_chunk(self):
        cells = [(s, _Cell(**{a: 1 for a in hp.ROW_ATTRS})) for s in SECTORS[: hp.READ_CHUNK]]
        self.assertLess(ops(hp.cell_rows, cells), hp.ATOMIC_STEP_BUDGET)

    def test_cell_view_matches_per_cell_reads(self):
        plant = ("growing", "stalled", "mature")
        kinds = ["empty", "base", "growing", "item", "mature", "base", "stalled", None]
        items = [
            (s, _Cell(status=kinds[i % len(kinds)]) if kinds[i % len(kinds)] else _Cell())
            for i, s in enumerate(SECTORS[:20])
        ]
        statuses, planted, base = hp.cell_view(items, plant)
        self.assertEqual(statuses, {s: getattr(c, "status", None) for s, c in items})
        self.assertEqual(planted, {s: c for s, c in items if statuses[s] in plant})
        self.assertEqual(base, SECTORS[1])
        self.assertIsNone(hp.cell_view(items[:1], plant)[2])

    def test_view_chunk(self):
        cells = [(s, _Cell(status=("growing", "base")[i % 2])) for i, s in enumerate((SECTORS * 2)[: hp.VIEW_CHUNK])]
        self.assertLess(ops(hp.cell_view, cells, ("growing", "stalled", "mature")), hp.ATOMIC_STEP_BUDGET)

    def test_id_chunk(self):
        import harvesting

        cells = [_Cell(id=f"A{i}") for i in range(harvesting.ID_CHUNK)]
        self.assertEqual(harvesting._id_pairs(cells[:2]), [("A0", cells[0]), ("A1", cells[1])])
        self.assertLess(ops(harvesting._id_pairs, cells), hp.ATOMIC_STEP_BUDGET)


class MovedPureTests(unittest.TestCase):
    def test_care_kind_table_and_salt_usable(self):
        import field_layout

        rules = field_layout.rules_from_published({})
        table = hp.care_kind_table(rules)
        self.assertEqual(
            table, {sp: field_layout.care_kinds(rules, sp) for sp in rules if field_layout.care_kinds(rules, sp)}
        )
        self.assertFalse(hp.salt_usable({"a": ["light"]}, 5))
        self.assertFalse(hp.salt_usable({"a": ["salt"]}, 0))
        self.assertTrue(hp.salt_usable({"a": ["light", "salt"]}, 1))

    def test_combine_scans(self):
        parts = [({"A1": [("light", 1)]}, 1, 0, {"x"}), ({"A2": [("water", 2)]}, 2, 1, {"x", "y"})]
        scan = hp.combine_scans(parts, 5)
        self.assertEqual(
            scan,
            {
                "planted": 5,
                "mature": 3,
                "stalled": 1,
                "productive": 2,
                "care": {"A1": [("light", 1)], "A2": [("water", 2)]},
            },
        )

    def test_desired_chunks(self):
        import field_layout

        self.assertEqual(hp.desired_chunks("crowncap", 7, None, None), 7)
        rules = field_layout.rules_from_published({})
        self.assertEqual(
            hp.desired_chunks("grandbloom", 0, {}, rules), field_layout.chunks_for_demand(0.0, rules, "grandbloom")
        )


if __name__ == "__main__":
    unittest.main()
