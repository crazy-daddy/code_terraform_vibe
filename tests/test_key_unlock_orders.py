"""Tests for supply_dock.key_unlock_bonus(): key unlock orders and the look-ahead along a contractor's queue."""
import unittest
from types import SimpleNamespace as NS

import harness  # noqa: F401  (puts the tiered lib/ dirs on sys.path)
import supply_dock

WEIGHTS = {"spire_intake_2": 70, "helios_01": 100}


def order(order_id, contractor):
    return NS(id=order_id, contractor_id=contractor)


class KeyUnlockBonusTests(unittest.TestCase):
    def test_key_order_itself_gets_its_full_weight(self):
        bonus = supply_dock.key_unlock_bonus([order("helios_01", "helios")], [], WEIGHTS)
        self.assertEqual(bonus, {"helios_01": 100})

    def test_order_in_front_of_a_key_order_gets_a_share(self):
        current = [order("spire_intake_1", "spire"), order("vestibule_01", "vestibule")]
        upcoming = [order("vestibule_02", "vestibule"), order("spire_intake_2", "spire"), order("spire_intake_3", "spire")]
        bonus = supply_dock.key_unlock_bonus(current, upcoming, WEIGHTS)
        self.assertEqual(bonus, {"spire_intake_1": 35.0})

    def test_other_contractors_queue_does_not_count(self):
        bonus = supply_dock.key_unlock_bonus([order("vestibule_01", "vestibule")], [order("helios_01", "helios")], WEIGHTS)
        self.assertEqual(bonus, {})

    def test_default_table_covers_the_titanium_and_steam_path(self):
        for order_id in ("helios_01", "helios_02", "spire_intake_2"):
            self.assertIn(order_id, supply_dock.KEY_UNLOCK_ORDERS)


if __name__ == "__main__":
    unittest.main()
