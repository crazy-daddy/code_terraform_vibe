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


if __name__ == "__main__":
    unittest.main()
