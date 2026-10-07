"""Stub tests for Supply Dock campaign order scoring (lib/supply_dock.py)."""
import unittest

from harness import supply_dock
from game_stubs import Order


def score(order, stock):
    return supply_dock._score_campaign_order(order, {}, lambda item_id: stock.get(item_id, 0), lambda item_id: 0)


class EarlyUnlockScoringTests(unittest.TestCase):
    def test_power_line_beats_gas_pipe_beats_liquid_pipe(self):
        # Liquid pipe order fully stocked, power line and gas pipe orders bare:
        # the fixed unlock order still wins over readiness.
        power = Order("vestibule_01", {"iron_ingot": 200}, reward_kind="recipe")
        gas = Order("helios_02", {"iron_ingot": 300}, reward_kind="recipe")
        liquid = Order("spire_intake_2", {"ice": 75}, reward_kind="recipe")
        stock = {"ice": 75}
        self.assertGreater(score(power, stock), score(gas, stock))
        self.assertGreater(score(gas, stock), score(liquid, stock))

    def test_other_unlocks_keep_readiness_ranking(self):
        ready = Order("helios_03", {"iron_ingot": 10}, reward_kind="recipe")
        bare = Order("spire_01", {"glass": 10}, reward_kind="recipe")
        self.assertGreater(score(ready, {"iron_ingot": 10}), score(bare, {"iron_ingot": 10}))


def queued(order_id, contractor):
    order = Order(order_id, {})
    order.contractor_id = contractor
    return order


class KeyUnlockLookAheadTests(unittest.TestCase):
    def test_order_in_front_of_a_key_order_gets_a_share(self):
        current = [queued("spire_intake_1", "spire"), queued("vestibule_02", "vestibule")]
        upcoming = [queued("vestibule_03", "vestibule"), queued("spire_intake_2", "spire")]
        bonus = supply_dock.key_unlock_bonus(current, upcoming)
        self.assertEqual(bonus, {"spire_intake_1": supply_dock.early_unlock_weight("spire_intake_2") / 2})

    def test_key_orders_and_other_queues_get_no_look_ahead(self):
        current = [queued("helios_01", "helios"), queued("vestibule_02", "vestibule")]
        upcoming = [queued("helios_02", "helios"), queued("spire_intake_2", "spire")]
        self.assertEqual(supply_dock.key_unlock_bonus(current, upcoming), {})

    def test_titanium_ingot_ranks_below_the_pipe_and_power_line_unlocks(self):
        weights = [supply_dock.early_unlock_weight(i) for i in ("vestibule_01", "helios_02", "spire_intake_2", "helios_01")]
        self.assertEqual(weights, sorted(weights, reverse=True))
        self.assertGreater(weights[-1], 0)


if __name__ == "__main__":
    unittest.main()
