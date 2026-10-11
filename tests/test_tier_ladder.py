"""logistics_requests priority bands: a request's ladder drives the per-band
deficits and free stock, the planners walk the bands in order, and the
(need, buffer) adapters return the same bands."""
import unittest

import harness
import priority
from harness import StubTestCase
from harness import logistics_requests as lr


def _levels(*pairs):
    return {"levels": [list(p) for p in pairs]}


class TierLadderTests(StubTestCase):
    def test_deficits_stack_down_the_ladder(self):
        entry = {"levels": harness.request(100, 30)}
        self.assertEqual(lr.tier_deficits(entry, 10, 5), {priority.NEED: 15, priority.STOCK: 70})
        self.assertEqual(lr.tier_deficits(entry, 40, 0), {priority.STOCK: 60})
        self.assertEqual(lr.tier_deficits(entry, 120, 0), {})
        self.assertEqual(lr.tier_deficits({"levels": harness.request(50)}, 20, 0), {priority.NEED: 30})

    def test_free_keeps_per_tier(self):
        entry = {"levels": harness.request(100, 30), "keep": 60}
        free = lr.tier_free(entry, 150, 999)
        self.assertEqual((free[priority.NEED], free[priority.STOCK]), (90, 50))
        free = lr.tier_free(entry, 150, 70)
        self.assertEqual((free[priority.NEED], free[priority.STOCK]), (70, 50))
        free = lr.tier_free(None, 150, 999)
        self.assertEqual((free[priority.NEED], free[priority.STOCK]), (150, 150))
        self.assertEqual(sorted(free), sorted(priority.BANDS))

    def test_bands_stack_in_one_ladder(self):
        # UPGRADE 10, NEED up to 30, STOCK up to 100.
        entry = _levels((priority.UPGRADE, 10), (priority.NEED, 30), (priority.STOCK, 100))
        self.assertEqual(lr.tier_deficits(entry, 0, 0), {priority.UPGRADE: 10, priority.NEED: 20, priority.STOCK: 70})
        self.assertEqual(lr.tier_deficits(entry, 15, 0), {priority.NEED: 15, priority.STOCK: 70})
        free = lr.tier_free(entry, 150, 999)
        self.assertEqual(free[priority.UPGRADE], 140)
        self.assertEqual(free[priority.NEED], 120)
        self.assertEqual(free[priority.STOCK], 50)

    def test_planners_walk_the_bands(self):
        up, need, stock = priority.UPGRADE, priority.NEED, priority.STOCK
        # Each band takes only what its free stock leaves after the earlier bands.
        tiers = {b: {} for b in priority.BANDS}
        tiers[up], tiers[need], tiers[stock] = {"ore": 50}, {"ore": 30}, {"ore": 35}
        source = {"available": {"ore": 50}, "tiers": tiers}
        left = lr.route_left({up: {"ore": 10}, need: {"ore": 20}, stock: {"ore": 70}})
        self.assertEqual(lr.plan_take(source, "ore", left, 999), {up: 10, need: 20, stock: 5})
        self.assertEqual(lr.plan_take(source, "ore", left, 25), {up: 10, need: 15})
        self.assertTrue(lr.source_useful(source, lr.route_left({stock: {"ore": 1}}), 1))
        self.assertFalse(lr.source_useful(source, lr.route_left({need: {"iron": 5}}), 1))
        route = [({"id": "s1"}, [("ore", 45)])]
        served = lr.route_tier_units(left, route)
        self.assertEqual((served[up], served[need], served[stock]), (10, 20, 15))
        # A BLOCKER route outranks NEED, which outranks a bigger STOCK run.
        blocker_run = lr.haul_rank({priority.BLOCKER: 1}, 100, 0)
        need_run = lr.haul_rank({need: 10}, 100, 0)
        stock_run = lr.haul_rank({stock: 500}, 100, 0)
        self.assertEqual(len(blocker_run), 9)
        self.assertTrue(lr.rank_beats(blocker_run, need_run))
        self.assertTrue(lr.rank_beats(need_run, stock_run))
        self.assertFalse(lr.rank_beats(stock_run, need_run))
        self.assertEqual(lr.blocker_units({priority.BLOCKER: 3, need: 4}), 3)
        by_urgency = sorted(["b", "r", "n"], key=lambda i: lr.tier_rank(lr.route_left({need: {"n": 1}, up: {"r": 9}, stock: {"b": 99}}), i))
        self.assertEqual(by_urgency, ["r", "n", "b"])

    def test_fair_share_caps_fair_tiers_only(self):
        now = self.world.clock.now
        lr.set_requests("outpost_b", "fab", {"ore": (harness.request(100, 0), 0)}, now)
        deficits = {priority.NEED: {"ore": 30}, priority.STOCK: {"ore": 100}}
        sources = [{"id": "s1", "available": {"ore": 100}}, {"id": "outpost_a", "available": {"ore": 1000}}]
        capped = lr.fair_share_tiers("outpost_a", deficits, sources, now)
        self.assertEqual(capped[priority.NEED], {"ore": 30})
        self.assertEqual(capped[priority.STOCK], {"ore": 50})  # 100 supply split with outpost_b's buffer of 100

    def test_outpost_adapters_match_tier_dicts(self):
        w = self.world
        now = w.clock.now
        a = w.add_outpost("outpost_a")
        w.add_warehouse("wh_a", a, {"iron_ore": 70})
        lr.set_requests("outpost_a", "fab", {"iron_ore": (harness.request(100, 50), 0)}, now)
        lr.set_requests("home", "fab", {"iron_ore": (harness.request(80, 20), 0)}, now)
        tiers = lr.outpost_tier_deficits(w.home, now)
        self.assertEqual(tiers, {priority.NEED: {"iron_ore": 20}, priority.STOCK: {"iron_ore": 60}})
        self.assertEqual(lr.outpost_deficits_tiered(w.home, now), (tiers[priority.NEED], tiers[priority.STOCK]))
        free = lr.outpost_tier_free(a, ["iron_ore"], None, now)
        self.assertEqual(free[priority.NEED], {"iron_ore": 20})
        self.assertEqual(free[priority.STOCK], {})
        self.assertEqual(lr.outpost_free_tiers(a, ["iron_ore"], None, now), (free[priority.NEED], free[priority.STOCK]))


if __name__ == "__main__":
    unittest.main()
