"""devtools/code_scan/size_scan.py: Ruff diagnostics map to stable function ids, long files hit."""

import os
import sys
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


if __name__ == "__main__":
    unittest.main()
