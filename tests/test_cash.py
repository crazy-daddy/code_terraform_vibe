"""Stub tests for lib/cash.py: floor, savings goal, holds, legacy fallback, income and burn rates, order pipeline."""
import unittest

from harness import StubTestCase
import cash


class CashTestCase(StubTestCase):
    def setUp(self):
        super().setUp()
        cash._prices.clear()
        self.commander = self.world.services["commander"]

    def set_credits(self, credits):
        self.commander.credits = credits

    def run_manager(self):
        return cash.CashManager().step(self.world.clock.now)


class GateTests(CashTestCase):
    def test_capital_keeps_min_floor_operating_does_not(self):
        self.set_credits(25000)
        self.run_manager()
        self.assertFalse(cash.can_spend("warehouse_upgrade", 10000))
        self.assertTrue(cash.can_spend("bio_reagents:bio_lab_1", 25000))

    def test_stale_manager_falls_back_to_legacy_reserve(self):
        self.set_credits(150000)
        self.run_manager()
        self.world.clock.now += cash.MANAGER_STALE_TICKS + 1
        self.assertFalse(cash.can_spend("tank_upgrade", 60000))
        self.assertTrue(cash.can_spend("tank_upgrade", 50000))

    def test_goal_blocks_lower_priority_unless_small(self):
        self.set_credits(35000)
        self.run_manager()
        self.assertFalse(cash.can_spend("crop_automator", 30000))  # free 15k: becomes the goal
        self.assertFalse(cash.can_spend("tank_upgrade", 15000))     # fits alone, but eats the goal
        self.assertTrue(cash.can_spend("pioneer_upgrade:pioneer_1", 2000))  # <= 10% of 30k
        self.assertTrue(cash.can_spend("bio_reagents", 5000))      # reagents ignore the goal

    def test_lower_priority_spends_when_goal_stays_affordable(self):
        self.set_credits(100000)
        self.run_manager()
        self.assertTrue(cash.can_spend("tank_upgrade", 15000))
        self.assertIn("tank_upgrade", cash.budget()["holds"])

    def test_hold_reserves_credits_until_spent(self):
        self.set_credits(60000)
        self.run_manager()
        self.assertTrue(cash.can_spend("crop_automator", 30000))
        self.assertFalse(cash.can_spend("warehouse_upgrade", 20000))  # 60k - 30k held - 20k floor
        self.set_credits(30000)
        cash.spent("crop_automator", 30000)
        state = cash.budget()
        self.assertNotIn("crop_automator", state["holds"])
        self.assertNotIn("crop_automator", state["asks"])
        self.assertEqual(state["spent"][-1][1:], ["crop_automator", 30000])

    def test_hold_expires(self):
        self.set_credits(60000)
        self.run_manager()
        self.assertTrue(cash.can_spend("crop_automator", 30000))
        self.world.clock.now += cash.HOLD_TICKS + 1
        self.run_manager()
        self.assertEqual(cash.budget()["holds"], {})
        self.assertFalse(cash.can_spend("warehouse_upgrade", 20000))  # automator is the goal again
        self.assertTrue(cash.can_spend("crop_automator", 30000))

    def test_priority_reorder(self):
        self.set_credits(35000)
        self.run_manager()
        cash.move_priority("tank_upgrade", -3)
        self.assertEqual(cash.priority_order()[0], "tank_upgrade")
        self.assertFalse(cash.can_spend("crop_automator", 30000))
        self.assertTrue(cash.can_spend("tank_upgrade", 15000))  # now above the automator

    def test_release_drops_ask(self):
        self.set_credits(0)
        self.run_manager()
        cash.can_spend("warehouse_upgrade", 60000, planned=120000)
        cash.release("warehouse_upgrade")
        self.assertEqual(cash.budget()["asks"], {})


class ManagerTests(CashTestCase):
    def test_income_and_burn_set_floor(self):
        clock = self.world.clock
        self.set_credits(10000)
        self.run_manager()
        clock.hours, clock.now = 1.0, clock.now + 100
        self.set_credits(5000)
        cash.spent("bio_reagents:bio_lab_1", 30000)
        self.run_manager()
        clock.hours, clock.now = 2.0, clock.now + 100
        self.set_credits(15000)
        self.run_manager()
        state = cash.budget()
        self.assertEqual(state["income_h"], 17500.0)  # (15k - 10k + 30k spent) / 2 h
        self.assertEqual(state["burn_h"], 15000.0)
        self.assertEqual(state["floor"], int(15000 * cash.FLOOR_HOURS))

    def test_no_rate_before_min_span(self):
        self.set_credits(10000)
        self.run_manager()
        state = cash.budget()
        self.assertIsNone(state["income_h"])
        self.assertEqual(state["floor"], cash.MIN_FLOOR)

    def test_order_pipeline(self):
        order = self.world.add_order("o1", {"iron_ingot": 100}, shipped={"iron_ingot": 25})
        order.reward_credits = 40000
        self.run_manager()
        self.assertEqual(cash.budget()["pipeline"], {"campaign": 30000, "campaign_shipped": 10000, "weekly": 0})

    def test_queue_eta_and_planned(self):
        clock = self.world.clock
        self.set_credits(20000)
        self.run_manager()
        clock.hours, clock.now = 2.0, clock.now + 100
        self.set_credits(30000)  # +5k/h
        cash.can_spend("crop_automator", 30000, planned=90000)
        state_line = self.run_manager()
        rows = cash.budget()["queue"]
        self.assertEqual(rows[0]["consumer"], "crop_automator")
        self.assertAlmostEqual(rows[0]["eta_h"], (30000 + cash.MIN_FLOOR - 30000) / 5000.0)
        self.assertEqual(cash.budget()["planned"], 90000)
        self.assertIn("1 ask(s)", state_line)

    def test_stale_ask_pruned(self):
        self.set_credits(0)
        self.run_manager()
        cash.can_spend("tank_upgrade", 15000)
        self.world.clock.now += cash.ASK_STALE_TICKS + 1
        self.run_manager()
        self.assertEqual(cash.budget()["asks"], {})


class ConsumerTests(CashTestCase):
    def test_shop_price_cached(self):
        self.world.services["shop"].prices = {"cryo_solvent": 12}
        self.assertEqual(cash.shop_price("cryo_solvent"), 12)
        self.world.services["shop"].prices = {}
        self.assertEqual(cash.shop_price("cryo_solvent"), 12)
        self.assertEqual(cash.shop_price("unknown", 7), 7)


if __name__ == "__main__":
    unittest.main()
