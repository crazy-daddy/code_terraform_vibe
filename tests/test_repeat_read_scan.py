"""devtools/repeat_read_scan.py: loop depth, invariant reads, callee cost and atomic marking."""
import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "devtools"))

import repeat_read_scan as rrs  # noqa: E402

SOURCE = """
def helper(store):
    return store.stacks()

def per_item(items, store):
    for item in items:
        store.count(item)
        get_component("archive")
        helper(store)

def pure(stores):
    return [s.stacks() for s in stores]

def run(stores):
    run_atomic(pure, stores)
"""


def build(source):
    tree = ast.parse(source)
    functions = [rrs.Function("lib/sample.py", None, n) for n in tree.body if isinstance(n, ast.FunctionDef)]
    nested = []
    for func in list(functions):
        rrs.Scanner(func, nested).run()
    return rrs.Graph(functions + nested)


class RepeatReadScanTest(unittest.TestCase):
    def setUp(self):
        self.graph = build(SOURCE)
        self.rows = {(r["site"].func.name, r["site"].name): r for r in rrs.hits(self.graph)}

    def test_invariant_only_for_reads_without_loop_names(self):
        self.assertFalse(self.rows[("per_item", "count")]["site"].invariant)
        self.assertTrue(self.rows[("per_item", "get_component")]["site"].invariant)
        self.assertFalse(self.rows[("per_item", "helper")]["site"].invariant)

    def test_callee_cost_and_loop_factor(self):
        row = self.rows[("per_item", "helper")]
        self.assertEqual(row["site"].weight, rrs.WEIGHTS["stacks"])
        self.assertEqual(row["score"], rrs.WEIGHTS["stacks"] * rrs.LOOP_N)

    def test_atomic_target_discounted(self):
        row = self.rows[("pure", "stacks")]
        self.assertTrue(row["atomic"])
        self.assertAlmostEqual(row["score"], rrs.WEIGHTS["stacks"] * rrs.LOOP_N * rrs.ATOMIC_FACTOR)

    def test_tier_files_prefers_highest_tier(self):
        files = rrs.tier_files()
        tiers = [int(os.path.relpath(p, rrs.SCRIPTS).split("_")[0]) for p in files.values()]
        self.assertTrue(files)
        self.assertIn("lib/tree_console.py", files)
        self.assertEqual(max(tiers), max(int(d.split("_")[0]) for d in os.listdir(rrs.SCRIPTS) if d[0].isdigit()))


if __name__ == "__main__":
    unittest.main()
