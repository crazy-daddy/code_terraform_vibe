"""devtools/perf/callback_steps.py: labels, slot peaks, the threshold check and the watch line."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "devtools", "perf"))

import callback_steps as cbs


def rec(script, fn, source, peak, before=0, inner=None, inner_source=None, count=1, limit=0, cap=10000):
    return {
        "script": script,
        "fn": fn,
        "source": source,
        "inner": inner,
        "innerSource": inner_source,
        "cap": cap,
        "count": count,
        "ownSum": (peak - before) * count,
        "ownMax": peak - before,
        "peak": peak,
        "peakBefore": before,
        "peakSource": source,
        "peakLine": 84,
        "limit": limit,
    }


LAMBDA = "run_atomic.<locals>.<lambda>"
RECORDS = [
    rec("drone_7", LAMBDA, "atomic", 3459, 358, "fair_rival_bands", "logistics_requests", count=4),
    rec("drone_7", LAMBDA, "atomic", 3591, 69, "distance_table", "drone_haul_plan", count=5),
    rec("drone_8", LAMBDA, "atomic", 3000, 100, "fair_rival_bands", "logistics_requests", count=2),
    rec(
        "automation_4",
        "set_requests.<locals>.updater",
        "logistics_requests",
        9200,
        300,
        "_fresh_items",
        "logistics_requests",
    ),
]


class LabelTest(unittest.TestCase):
    def test_atomic_lambda_is_named_by_its_fn(self):
        self.assertEqual(cbs.label(RECORDS[0]), "fair_rival_bands (logistics_requests, atomic)")

    def test_other_callbacks_keep_their_own_name(self):
        self.assertEqual(cbs.label(RECORDS[3]), "set_requests.<locals>.updater (logistics_requests)")

    def test_atomic_lambda_without_inner(self):
        self.assertEqual(cbs.label(rec("x", LAMBDA, "atomic", 5)), f"{LAMBDA} (atomic)")


class PeakTest(unittest.TestCase):
    def test_slot_records_highest_peak_first(self):
        slots = cbs.by_slot(RECORDS)
        self.assertEqual([r["inner"] for r in slots["drone_7"]], ["distance_table", "fair_rival_bands"])

    def test_threshold(self):
        slots = cbs.by_slot(RECORDS)
        self.assertEqual([name for name, _ in cbs.over(slots, 0.9)], ["automation_4"])
        self.assertEqual(cbs.over(slots, 0.95), [])

    def test_step_limit_fails_below_the_threshold(self):
        slots = cbs.by_slot([*RECORDS, rec("panel_7", "heavy", "roles", 500, limit=1)])
        self.assertEqual([name for name, _ in cbs.over(slots, 0.95)], ["panel_7"])


class WatchTest(unittest.TestCase):
    def test_reached(self):
        line = cbs.watch_line(RECORDS, "fair_rival_bands")
        self.assertIn("peak 3459 (34.6 % of the cap) in drone_7", line)
        self.assertIn("6 call(s) in 2 slot(s)", line)

    def test_qualified_names_match_bare(self):
        self.assertEqual(len(cbs.watched(RECORDS, "updater")), 1)

    def test_not_reached(self):
        self.assertEqual(cbs.watch_line(RECORDS, "nowhere"), "nowhere: not reached in this window")


class MainTest(unittest.TestCase):
    def test_records_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "callback_steps.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(RECORDS, f)
            with mock.patch("builtins.print") as printed:
                self.assertEqual(cbs.main(["--records", path]), 1)
                self.assertEqual(cbs.main(["--records", path, "--threshold", "0.95", "--slot", "drone_7"]), 0)
            out = "\n".join(str(c.args[0]) for c in printed.call_args_list)
            self.assertIn("fair_rival_bands: peak 3459", out)


if __name__ == "__main__":
    unittest.main()
