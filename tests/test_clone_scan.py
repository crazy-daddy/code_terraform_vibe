"""devtools/code_scan/scan_common.py: scanned_files covers autoplay/ only on request."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "devtools", "code_scan"))

import scan_common


class ScannedFilesTests(unittest.TestCase):
    def test_scanned_files_adds_autoplay(self):
        with_autoplay = scan_common.scanned_files(include_autoplay=True)
        self.assertEqual(with_autoplay["autoplay/lib/outpost_plan.py"][1], None)
        self.assertFalse(any("__pycache__" in k for k in with_autoplay))
        self.assertFalse(any(k.startswith("autoplay/") for k in scan_common.scanned_files()))


if __name__ == "__main__":
    unittest.main()
