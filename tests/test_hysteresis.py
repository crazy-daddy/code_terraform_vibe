"""Tests for lib/hysteresis.py HysteresisLatch: both threshold directions, per-call thresholds and
the three unknown-value modes."""
import unittest

from harness import StubTestCase
from hysteresis import HysteresisLatch


class HysteresisLatchTests(StubTestCase):
    def test_on_above(self):
        latch = HysteresisLatch(0.9, 0.7)
        self.assertEqual([latch.update(v) for v in (0.85, 0.9, 0.75, 0.7, 0.69, 0.85)], [None, "on", None, None, "off", None])

    def test_on_below(self):
        latch = HysteresisLatch(0.5, 0.7, on_above=False)
        self.assertEqual([latch.update(v) for v in (0.6, 0.49, 0.69, 0.7, 0.55)], [None, "on", None, "off", None])

    def test_per_call_thresholds(self):
        latch = HysteresisLatch(0.0, 0.0, on_above=False)
        self.assertEqual(latch.update(90, 100, 125), "on")
        self.assertIsNone(latch.update(120, 100, 125))
        self.assertEqual(latch.update(125, 100, 125), "off")

    def test_unknown_forces_or_keeps(self):
        forced_off = HysteresisLatch(0.9, 0.7, active=True)
        self.assertEqual(forced_off.update(None), "off")
        forced_on = HysteresisLatch(0.9, 0.7, unknown=True)
        self.assertEqual(forced_on.update(None), "on")
        kept = HysteresisLatch(0.9, 0.7, unknown=None, active=True)
        self.assertIsNone(kept.update(None))
        self.assertTrue(kept.active)


if __name__ == "__main__":
    unittest.main()
