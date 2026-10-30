"""devtools/code_scan/size_scan.py: stable hit ids, ignore-entry pins, drift, stale entries, --pin."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "devtools", "code_scan"))

import size_scan as ss

SOURCE = """
def top():
    pass

class Outer:
    @staticmethod
    def method():
        def inner():
            pass
"""

DIAGNOSTICS = [
    (2, "C901", "`top` is too complex (12 > 10)"),
    (2, "PLR0915", "Too many statements (60 > 50)"),
    (7, "PLR0912", "Too many branches (13 > 12)"),
    (8, "C901", "`inner` is too complex (11 > 10)"),
    (2, "E501", "Line too long (130 > 120)"),
]


class SizeScanTests(unittest.TestCase):
    def test_function_hits(self):
        hits = {h.id: h for h in ss.file_hits("lib/a.py", SOURCE, DIAGNOSTICS, max_lines=100)}
        self.assertEqual(set(hits), {"lib/a.py::top", "lib/a.py::Outer.method", "lib/a.py::Outer.method.inner"})
        self.assertEqual(hits["lib/a.py::top"].metrics, {"complexity": (12, 10), "statements": (60, 50)})
        self.assertEqual(hits["lib/a.py::top"].score, 1.2)

    def test_long_file(self):
        hits = ss.file_hits("lib/a.py", SOURCE, [], max_lines=5)
        self.assertEqual([h.id for h in hits], ["lib/a.py::<module>"])
        self.assertEqual(hits[0].metrics, {"lines": (9, 5)})


def function_hit(complexity=None, branches=None, statements=None, subject="fn"):
    values = {"complexity": (complexity, 10), "branches": (branches, 12), "statements": (statements, 50)}
    return ss.Hit("lib/a.py", 3, subject, {m: v for m, v in values.items() if v[0] is not None})


def file_hit(lines):
    return ss.Hit("lib/a.py", 1, ss.MODULE, {"lines": (lines, 1000)})


IGNORE = [
    "# header comment\r\n",
    "\r\n",
    "lib/a.py::fn  @22/17/56  # reason one\r\n",
    "lib/a.py::<module>  @1434  # long file\r\n",
    "lib/a.py::old  # unpinned\r\n",
    "lib/a.py::gone  @11/-/-  # stale\r\n",
]


class IgnorePinTests(unittest.TestCase):
    def test_parse(self):
        entries = ss.parse_entries(IGNORE)
        self.assertEqual(
            [(e.number, e.id) for e in entries],
            [(3, "lib/a.py::fn"), (4, "lib/a.py::<module>"), (5, "lib/a.py::old"), (6, "lib/a.py::gone")],
        )
        self.assertEqual(entries[0].pin, {"complexity": 22, "branches": 17, "statements": 56})
        self.assertEqual(entries[1].pin, {"lines": 1434})
        self.assertIsNone(entries[2].pin)
        self.assertEqual(entries[3].pin, {"complexity": 11, "branches": None, "statements": None})
        self.assertEqual(entries[3].pin_text, "11/-/-")

    def test_parse_rejects_bad_pin(self):
        bad = ("lib/a.py::fn  @22/17", "lib/a.py::<module>  @1/2/3", "lib/a.py::fn  @x/1/2", "lib/a.py::fn@22/17/56")
        for line in bad + ("lib/a.py::fn @", "lib/a.py::fn @ 22/17/56", "@1434"):
            with self.assertRaises(ValueError, msg=line):
                ss.parse_entries([line])

    def test_parse_rejects_duplicate(self):
        with self.assertRaisesRegex(ValueError, "already listed on line 1"):
            ss.parse_entries(["lib/a.py::fn  @22/17/56", "lib/a.py::fn"])

    def test_function_drift_edges(self):
        pin = {"complexity": 22, "branches": 17, "statements": 56}
        self.assertFalse(ss.grown(function_hit(25, 20, 61), pin))  # +3, +3, +5.6 allowed
        self.assertTrue(ss.grown(function_hit(26, 17, 56), pin))
        self.assertTrue(ss.grown(function_hit(22, 21, 56), pin))
        self.assertTrue(ss.grown(function_hit(22, 17, 62), pin))
        self.assertFalse(ss.grown(function_hit(statements=56), pin))  # metrics under their limit are not checked

    def test_dash_pin_counts_as_limit(self):
        pin = {"complexity": 11, "branches": None, "statements": None}
        self.assertFalse(ss.grown(function_hit(11, 15), pin))  # 12 + 3
        self.assertTrue(ss.grown(function_hit(11, 16), pin))
        self.assertFalse(ss.grown(function_hit(11, statements=55), pin))  # 50 + 5
        self.assertTrue(ss.grown(function_hit(11, statements=56), pin))

    def test_file_drift_edges(self):
        self.assertFalse(ss.grown(file_hit(1577), {"lines": 1434}))  # + 143.4
        self.assertTrue(ss.grown(file_hit(1578), {"lines": 1434}))
        self.assertFalse(ss.grown(file_hit(310), {"lines": 260}))  # + 50 floor
        self.assertTrue(ss.grown(file_hit(311), {"lines": 260}))

    def test_triage(self):
        grew = function_hit(30)
        hits = [grew, file_hit(1434), function_hit(12, subject="old"), function_hit(12, subject="new")]
        kept, ignored, grown, unpinned, stale = ss.triage(hits, ss.parse_entries(IGNORE))
        self.assertEqual([h.id for h in kept], ["lib/a.py::fn", "lib/a.py::new"])
        self.assertEqual(ignored, 2)
        self.assertEqual(grown, [grew])
        self.assertEqual(grew.note, "grew since review (22/17/56 -> 30/-/-)")
        self.assertEqual([e.id for e in unpinned], ["lib/a.py::old"])
        self.assertEqual([e.id for e in stale], ["lib/a.py::gone"])
        kept, ignored, *_ = ss.triage(hits, ss.parse_entries(IGNORE), suppress=False)
        self.assertEqual((len(kept), ignored), (4, 0))

    def test_pin_round_trip(self):
        hits = [function_hit(24, statements=58), file_hit(1500), function_hit(13, 14, subject="old")]
        lines, changed = ss.pin_lines(IGNORE, hits)
        self.assertEqual(changed, 3)
        self.assertEqual(
            lines,
            [
                "# header comment\r\n",
                "\r\n",
                "lib/a.py::fn  @24/-/58  # reason one\r\n",
                "lib/a.py::<module>  @1500  # long file\r\n",
                "lib/a.py::old  @13/14/-  # unpinned\r\n",
                "lib/a.py::gone  @11/-/-  # stale\r\n",
            ],
        )
        self.assertEqual(ss.pin_lines(lines, hits), (lines, 0))
        _kept, ignored, grown, unpinned, stale = ss.triage(hits, ss.parse_entries(lines))
        self.assertEqual((ignored, grown, unpinned, len(stale)), (3, [], [], 1))

    def test_pin_line_without_comment(self):
        self.assertEqual(ss.pin_lines(["lib/a.py::<module>"], [file_hit(1100)]), (["lib/a.py::<module>  @1100"], 1))

    def test_pin_file_keeps_crlf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "ignore.txt")
            with open(path, "wb") as f:
                f.write(b"# head\r\nlib/a.py::<module>  # long\r\n")
            self.assertEqual(ss.pin_file(path, [file_hit(1100)]), 1)
            with open(path, "rb") as f:
                self.assertEqual(f.read(), b"# head\r\nlib/a.py::<module>  @1100  # long\r\n")
            self.assertEqual(os.listdir(tmp), ["ignore.txt"])

    def test_report_lists_review_sections(self):
        grew = function_hit(30)
        kept, ignored, *review = ss.triage([grew, function_hit(12, subject="old")], ss.parse_entries(IGNORE))
        grown, unpinned, stale = review
        self.assertEqual((len(grown), len(unpinned), len(stale)), (1, 1, 2))
        text = ss.report(kept, False, ignored, review)
        for item in [*grown, *unpinned, *stale]:
            self.assertIn(item.id, text)
        # At custom limits a stale entry may only be stale there: still listed, but not advised for removal.
        custom = ss.report(kept, False, 0, review, True)
        self.assertIn("stale, remove", text)
        self.assertNotIn("stale, remove", custom)
        for item in stale:
            self.assertIn(item.id, custom)


if __name__ == "__main__":
    unittest.main()
