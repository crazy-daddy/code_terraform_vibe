"""logistics_requests tier ladder: TIER_RULES levels and keeps drive the per-tier
deficits and free stock, and the (need, buffer) adapters return the same tiers."""
import unittest
from unittest import mock

from harness import StubTestCase, logistics_requests as lr


class TierLadderTests(StubTestCase):
    def test_deficits_stack_down_the_ladder(self):
        entry = {"target": 100, "min": 30}
        self.assertEqual(lr.tier_deficits(entry, 10, 5), {lr.NEED: 15, lr.BUFFER: 70})
        self.assertEqual(lr.tier_deficits(entry, 40, 0), {lr.NEED: 0, lr.BUFFER: 60})
        self.assertEqual(lr.tier_deficits(entry, 120, 0), {lr.NEED: 0, lr.BUFFER: 0})
        self.assertEqual(lr.tier_deficits({"target": 50}, 20, 0), {lr.NEED: 30, lr.BUFFER: 0})

    def test_free_keeps_per_tier(self):
        entry = {"target": 100, "min": 30, "keep": 60}
        self.assertEqual(lr.tier_free(entry, 150, 999), {lr.NEED: 90, lr.BUFFER: 50})
        self.assertEqual(lr.tier_free(entry, 150, 70), {lr.NEED: 70, lr.BUFFER: 50})
        self.assertEqual(lr.tier_free(None, 150, 999), {lr.NEED: 150, lr.BUFFER: 150})

    def test_added_tier_is_one_rule(self):
        # A "reserve" tier between need and buffer: level 60, kept back up to 60.
        rules = dict(lr.TIER_RULES, reserve={"level": lambda e: 60, "keep": lambda e: 60})
        with mock.patch.object(lr, "TIERS", (lr.NEED, "reserve", lr.BUFFER)), mock.patch.object(lr, "TIER_RULES", rules):
            entry = {"target": 100, "min": 30}
            self.assertEqual(lr.tier_deficits(entry, 10, 0), {lr.NEED: 20, "reserve": 30, lr.BUFFER: 40})
            self.assertEqual(lr.tier_free(entry, 150, 999), {lr.NEED: 120, "reserve": 90, lr.BUFFER: 50})

    def test_outpost_adapters_match_tier_dicts(self):
        w = self.world
        now = w.clock.now
        a = w.add_outpost("outpost_a")
        w.add_warehouse("wh_a", a, {"iron_ore": 70})
        lr.set_requests("outpost_a", "fab", {"iron_ore": (100, 0, 50)}, now)
        lr.set_requests("home", "fab", {"iron_ore": (80, 0, 20)}, now)
        tiers = lr.outpost_tier_deficits(w.home, now)
        self.assertEqual(tiers, {lr.NEED: {"iron_ore": 20}, lr.BUFFER: {"iron_ore": 60}})
        self.assertEqual(lr.outpost_deficits_tiered(w.home, now), (tiers[lr.NEED], tiers[lr.BUFFER]))
        free = lr.outpost_tier_free(a, ["iron_ore"], None, now)
        self.assertEqual(free, {lr.NEED: {"iron_ore": 20}, lr.BUFFER: {}})
        self.assertEqual(lr.outpost_free_tiers(a, ["iron_ore"], None, now), (free[lr.NEED], free[lr.BUFFER]))


if __name__ == "__main__":
    unittest.main()
