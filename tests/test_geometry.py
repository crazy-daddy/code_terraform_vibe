"""Tests for scripts/4_controlpanel/lib/geometry.py."""

import unittest

import harness  # noqa: F401  (puts the lib/ folders on sys.path)
from geometry import dist, distance


class DistTest(unittest.TestCase):
    def test_dist_matches_pythagoras(self):
        self.assertEqual(dist(0, 0, 3, 4), 5.0)

    def test_dist_agrees_with_distance(self):
        self.assertEqual(dist(1.5, -2, -4, 7), distance((1.5, -2), (-4, 7)))


if __name__ == "__main__":
    unittest.main()
