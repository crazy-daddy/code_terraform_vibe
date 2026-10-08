"""devtools/scan_stop_eval.py: failure classes of the pairing method's group middles."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "devtools"))
import scan_stop_eval as ev  # noqa: E402

R = 100.0


class EvalTests(unittest.TestCase):
    def test_pair_is_always_covered_by_its_middle(self):
        out = ev.evaluate([(0.0, 0.0), (190.0, 0.0)], R)
        self.assertEqual((out["groups"], out["failed"], out["missed"]), (1, 0, 0))

    def test_wide_equilateral_triple_has_no_single_stop(self):
        side = 1.9 * R
        out = ev.evaluate([(0.0, 0.0), (side, 0.0), (side / 2, side * 3 ** 0.5 / 2)], R)
        self.assertEqual((out["failed"], out["impossible"], out["fixable"]), (1, 1, 0))
        self.assertEqual(out["missed"], 3)

    def test_centroid_misses_what_the_enclosing_circle_centre_covers(self):
        # Two contacts close together pull the centroid away from the far one.
        points = [(0.0, 0.0), (5.0, 0.0), (190.0, 0.0)]
        centroid = ev.evaluate(points, R, "centroid")
        self.assertEqual((centroid["failed"], centroid["fixable"], centroid["missed"]), (1, 1, 1))
        self.assertEqual(ev.evaluate(points, R, "mec")["failed"], 0)

    def test_crossing_cover_takes_one_stop_for_a_coverable_triple(self):
        points = [(0.0, 0.0), (90.0, 0.0), (45.0, 60.0)]
        self.assertEqual(ev.crossing_cover(points, 50.0), 1)


if __name__ == "__main__":
    unittest.main()
