"""devtools/perf/import_steps.py: slot peaks, the threshold check and the import trees."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "devtools", "perf"))

import import_steps as ist


def rec(script, module, depth, before, after, error=None, cap=10000):
    return {
        "script": script,
        "module": module,
        "depth": depth,
        "before": before,
        "after": after,
        "cap": cap,
        "ok": error is None,
        "error": error,
    }


# Completion order, as simhost.mjs records it: a module after the modules it imports.
RECORDS = [
    rec("automation_4", "archive", 2, 10, 60),
    rec("automation_4", "storage", 3, 70, 770),
    rec("automation_4", "roles", 2, 60, 900),
    rec("automation_4", "outpost_plan", 1, 3, 9200),
    rec("automation_4", "building_plan", 1, 4, 800),
    rec("panel_1", "panel_lib", 1, 0, 500),
]


class PeakTest(unittest.TestCase):
    def test_peak_is_the_largest_outermost_after(self):
        peaks = ist.slot_peaks(RECORDS)
        self.assertEqual(peaks["automation_4"]["steps"], 9200)
        self.assertEqual(peaks["automation_4"]["module"], "outpost_plan")
        self.assertEqual(peaks["panel_1"]["steps"], 500)

    def test_lazy_load_counts_the_slice_steps_before_it(self):
        # A lazy import mid-slice: 6,000 steps spent before it, 3,500 in the body.
        records = RECORDS + [
            rec("automation_4", "wildlife_data", 2, 6100, 9000),
            rec("automation_4", "wildlife_common", 1, 6000, 9500),
        ]
        peak = ist.slot_peaks(records)["automation_4"]
        self.assertEqual((peak["steps"], peak["before"], peak["module"]), (9500, 6000, "wildlife_common"))
        self.assertEqual([name for name, _ in ist.over(ist.slot_peaks(records), 0.94)], ["automation_4"])

    def test_threshold(self):
        self.assertEqual([name for name, _ in ist.over(ist.slot_peaks(RECORDS), 0.9)], ["automation_4"])
        self.assertEqual([name for name, _ in ist.over(ist.slot_peaks(RECORDS), 0.95)], [])

    def test_nested_step_limit_fails_other_errors_do_not(self):
        records = [
            rec("drone_1", "heavy", 2, 50, 10001, "step_limit"),
            rec("drone_1", "drone", 1, 0, 10001, "step_limit"),
            rec("pump_1", "optional", 1, 0, 40, "ImportError"),
        ]
        peaks = ist.slot_peaks(records)
        self.assertEqual(peaks["drone_1"]["crashed"], ["heavy", "drone"])
        self.assertEqual(peaks["pump_1"]["raised"], ["optional"])
        self.assertEqual([name for name, _ in ist.over(peaks, 2.0)], ["drone_1"])

    def test_record_without_error_field(self):
        old = dict(RECORDS[-1], ok=False)
        del old["error"]
        self.assertEqual(ist.slot_peaks([old])["panel_1"]["raised"], ["panel_lib"])


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
                json.dump(RECORDS, f)
            with mock.patch("builtins.print"):
                self.assertEqual(ist.main(["--records", path]), 1)
                self.assertEqual(ist.main(["--records", path, "--threshold", "0.95"]), 0)


if __name__ == "__main__":
    unittest.main()
