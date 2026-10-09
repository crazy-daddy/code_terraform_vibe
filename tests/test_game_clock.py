"""game_clock.is_fresh(): the one staleness rule for tick-stamped archive entries."""
import unittest

import harness  # noqa: F401  (puts the lib/ folders on sys.path)
from game_clock import is_fresh


class IsFreshTests(unittest.TestCase):
    def test_younger_than_window_is_fresh(self):
        self.assertTrue(is_fresh({"tick": 100}, 159, 60))

    def test_window_edge_is_stale(self):
        self.assertFalse(is_fresh({"tick": 100}, 160, 60))

    def test_non_dict_is_stale(self):
        for entry in (None, 5, "x", [("tick", 100)]):
            self.assertFalse(is_fresh(entry, 120, 60))

    def test_missing_or_none_stamp_is_stale(self):
        self.assertFalse(is_fresh({}, 10, 60))
        self.assertFalse(is_fresh({"tick": None}, 10, 60))

    def test_stamp_zero_counts(self):
        self.assertTrue(is_fresh({"tick": 0}, 10, 60))

    def test_no_clock_keeps_stamped_entries(self):
        self.assertTrue(is_fresh({"tick": 500}, 0, 60))
        self.assertFalse(is_fresh({}, 0, 60))


if __name__ == "__main__":
    unittest.main()
