"""devtools/perf/import_steps.py: slot peaks, the threshold check and the import trees."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "devtools", "perf"))

import import_steps as ist


def rec(script, module, depth, before, after, ok=True, cap=10000):
    return {"script": script, "module": module, "depth": depth, "before": before, "after": after, "cap": cap, "ok": ok}


# Completion order, as simhost.mjs records it: a module after the modules it imports.
RECORDS = [
    rec("automation_4", "archive", 2, 10, 60),
    rec("automation_4", "storage", 3, 70, 770),
    rec("automation_4", "roles", 2, 60, 900),
    rec("automation_4", "outpost_plan", 1, 3, 9200),
    rec("automation_4", "building_plan", 1, 4, 800),
    rec("panel_1", "panel_lib", 1, 0, 500),
    rec("drone_1", "drone", 1, 0, 300, ok=False),
]


class PeakTest(unittest.TestCase):
    def test_peak_is_the_largest_top_level_after(self):
        peaks = ist.slot_peaks(RECORDS)
        self.assertEqual(peaks["automation_4"]["steps"], 9200)
        self.assertEqual(peaks["automation_4"]["module"], "outpost_plan")
        self.assertEqual(peaks["panel_1"]["steps"], 500)

    def test_over_threshold_and_crashes_fail(self):
        bad = [name for name, _ in ist.over(ist.slot_peaks(RECORDS), 0.9)]
        self.assertEqual(bad, ["automation_4", "drone_1"])
        self.assertEqual([name for name, _ in ist.over(ist.slot_peaks(RECORDS[:-1]), 0.95)], [])


class TreeTest(unittest.TestCase):
    def test_children_and_own_steps(self):
        roots = ist.import_trees(RECORDS, "automation_4")
        self.assertEqual([r["module"] for r in roots], ["outpost_plan", "building_plan"])
        plan = roots[0]
        self.assertEqual([c["module"] for c in plan["children"]], ["archive", "roles"])
        roles = plan["children"][1]
        self.assertEqual(roles["exclusive"], 840 - 700)
        self.assertEqual(plan["exclusive"], 9197 - 50 - 840)


class MainTest(unittest.TestCase):
    def test_records_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "import_steps.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(RECORDS[:-1], f)
            with mock.patch("builtins.print"):
                self.assertEqual(ist.main(["--records", path]), 1)
                self.assertEqual(ist.main(["--records", path, "--threshold", "0.95"]), 0)


if __name__ == "__main__":
    unittest.main()
