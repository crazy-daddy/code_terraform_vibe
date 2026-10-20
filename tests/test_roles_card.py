"""Stub tests for lib/roles_card.py: the FLEET card Roles tab rows."""

import unittest

import harness  # noqa: F401  # sets the lib sys.path
import roles_card
from fleet_claims_common import CLAIM_STALE_TICKS
from priority import BUILD, NONE, ORDER, STOCK


class RowTests(unittest.TestCase):
    def test_roles_order_by_band_then_fixed_order(self):
        roles = {
            "miner": {"band": NONE},
            "scout": {"band": STOCK},
            "hauler": {"band": ORDER},
            "builder": {"band": BUILD},
            "odd": {},
        }
        self.assertEqual(roles_card.ordered_roles(roles), ["builder", "hauler", "scout", "miner", "odd"])

    def test_row_shows_band_slots_and_keep(self):
        row = roles_card.role_row("hauler", {"band": ORDER, "wanted": 3, "keep": 1}, 2)
        self.assertIn(" 2 / 3 ", row)
        self.assertTrue(row.endswith("keep 1"))
        self.assertNotIn("none", roles_card.role_row("miner", {}, 0))

    def test_slot_holders_fresh_only_with_names(self):
        tick = 10 * CLAIM_STALE_TICKS
        claims = {
            "hauler:0": {"vehicle": "v1", "role": "hauler", "tick": tick - 600},
            "hauler:1": {"vehicle": "v2", "role": "hauler", "tick": tick - 2 * CLAIM_STALE_TICKS},
            "scout:0": {"vehicle": "v3", "role": "scout", "tick": tick},
        }
        self.assertEqual(
            roles_card.slot_holders(claims, "hauler", tick, {"v1": "H_hauler_1"}), [("hauler:0", "H_hauler_1", 600)]
        )


if __name__ == "__main__":
    unittest.main()
