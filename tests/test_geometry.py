"""Tests for scripts/4_controlpanel/lib/geometry.py."""

import unittest

import harness  # noqa: F401  (puts the lib/ folders on sys.path)
from geometry import ceil_int, dist, distance


class DistTest(unittest.TestCase):
    def test_dist_matches_pythagoras(self):
        self.assertEqual(dist(0, 0, 3, 4), 5.0)

    def test_dist_agrees_with_distance(self):
        self.assertEqual(dist(1.5, -2, -4, 7), distance((1.5, -2), (-4, 7)))


class CeilIntTest(unittest.TestCase):
    def test_ceil_int_rounds_up_including_negatives(self):
        self.assertEqual(ceil_int(2.0), 2)
        self.assertEqual(ceil_int(2.1), 3)
        self.assertEqual(ceil_int(0.0), 0)
        self.assertEqual(ceil_int(-1.5), -1)
        self.assertEqual(ceil_int(-2.0), -2)


if __name__ == "__main__":
    unittest.main()
