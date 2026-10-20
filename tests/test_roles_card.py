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


class QueueTests(unittest.TestCase):
    MISSIONS = {
        "entries": [
            {
                "id": "haul:outpost_1:3",
                "kind": "haul",
                "prio": ORDER,
                "outpost": "outpost_1",
                "item": "iron_ingot",
                "units": 40,
                "since": 0,
                "holders": ["H_1"],
            },
            {
                "id": "mine:outpost_2:iron_ore",
                "kind": "mine",
                "prio": STOCK,
                "outpost": "outpost_2",
                "item": "iron_ore",
                "since": 36000,
                "holders": [],
            },
            {
                "id": "build:cap_3",
                "kind": "build",
                "prio": BUILD,
                "outpost": None,
                "coords": [12.4, -3.6],
                "by": "pipe",
                "since": 72000,
                "holders": [],
            },
        ],
        "dropped": {"build": 2},
    }
    NAMES = {"outpost_1": "Base", "outpost_2": "Ridge"}

    def test_role_row_gains_open_count(self):
        counts = roles_card.open_counts(self.MISSIONS)
        self.assertEqual((counts["hauler"], counts["builder"], counts["miner"], counts["scout"]), (1, 3, 1, 0))
        self.assertTrue(roles_card.role_row("builder", {"band": BUILD}, 0, 3).endswith("  missions 3"))
        self.assertTrue(roles_card.role_row("builder", {"band": BUILD}, 0).endswith("keep 0"))

    def test_queue_row_kind_target_band_age_holders(self):
        haul, mine, build = (roles_card.queue_row(e, 72000, self.NAMES) for e in self.MISSIONS["entries"])
        self.assertTrue(haul.startswith("haul  Base "), haul)
        self.assertIn(" 2.0 h H_1", haul)
        self.assertIn("iron_ore@Ridge", mine)
        self.assertTrue(mine.endswith(" 1.0 h -"), mine)
        self.assertIn("cap_3", build)
        self.assertEqual(roles_card.age_hours({"since": None}, 100), 0.0)
        self.assertEqual(roles_card.age_hours({"since": 0}, 36000), 1.0)  # real hours, game_rules.TICKS_PER_REAL_HOUR

    def test_entry_lines(self):
        lines = roles_card.entry_lines(self.MISSIONS["entries"][2], 72000, self.NAMES)
        self.assertEqual(lines, ["since 0.0 h (tick 72000)", "by pipe", "at 12, -4", "no holder"])
        self.assertNotIn("at ", " ".join(roles_card.entry_lines({"coords": ["x", 1]}, 500, self.NAMES)))
        lines = roles_card.entry_lines(self.MISSIONS["entries"][0], 72000, self.NAMES)
        self.assertIn("outpost Base", lines)
        self.assertIn("40 x iron_ingot", lines)
        self.assertEqual(lines[-1], "held by H_1")


if __name__ == "__main__":
    unittest.main()
