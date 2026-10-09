"""game_clock.is_fresh(): the one staleness rule for tick-stamped archive entries."""
import unittest

import harness  # noqa: F401  (puts the lib/ folders on sys.path)
from game_clock import is_fresh, TickCache


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


class TickCacheTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

    def compute(self, value="v"):
        def run():
            self.calls.append(value)
            return value
        return run

    def test_reuses_within_ttl_and_recomputes_at_ttl(self):
        cache = TickCache(10)
        cache.get(self.compute(), curr_tick=100)
        cache.get(self.compute(), curr_tick=109)
        self.assertEqual(len(self.calls), 1)
        cache.get(self.compute(), curr_tick=110)
        self.assertEqual(len(self.calls), 2)

    def test_recomputes_without_clock_or_when_clock_went_back(self):
        cache = TickCache(10)
        cache.get(self.compute(), curr_tick=100)
        cache.get(self.compute(), curr_tick=99)
        cache.get(self.compute(), curr_tick=0)
        cache.get(self.compute(), curr_tick=0)
        self.assertEqual(len(self.calls), 4)

    def test_keys_are_separate(self):
        cache = TickCache(10)
        self.assertEqual(cache.get(self.compute("a"), "a", 100), "a")
        self.assertEqual(cache.get(self.compute("b"), "b", 100), "b")
        self.assertEqual(cache.get(self.compute("x"), "a", 101), "a")

    def test_single_keeps_one_key(self):
        cache = TickCache(10, single=True)
        cache.get(self.compute("a"), "a", 100)
        cache.get(self.compute("b"), "b", 100)
        self.assertIsNone(cache.peek("a"))
        self.assertEqual(cache.get(self.compute("a2"), "a", 101), "a2")

    def test_none_keeps_previous_value(self):
        cache = TickCache(10)
        self.assertIsNone(cache.get(self.compute(None), curr_tick=100))
        cache.get(self.compute("v"), curr_tick=100)
        self.assertEqual(cache.get(self.compute(None), curr_tick=120), "v")
        cache.get(self.compute("w"), curr_tick=121)
        self.assertEqual(self.calls, [None, "v", None, "w"])

    def test_keep_empty_false_retries_empty(self):
        cache = TickCache(10, keep_empty=False)
        cache.get(self.compute({}), curr_tick=100)
        cache.get(self.compute({}), curr_tick=101)
        self.assertEqual(len(self.calls), 2)

    def test_invalidate_recomputes_and_peek_keeps_old(self):
        cache = TickCache(10)
        cache.get(self.compute("old"), curr_tick=100)
        cache.invalidate()
        self.assertEqual(cache.peek(), "old")
        self.assertEqual(cache.get(self.compute("new"), curr_tick=101), "new")


if __name__ == "__main__":
    unittest.main()
