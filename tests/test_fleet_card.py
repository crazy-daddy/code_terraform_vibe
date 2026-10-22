"""lib/fleet_card.py draw_detail_body(): the detail pane body shared by the FLEET card's drone and ground views."""

import unittest

import fleet_card
from game_stubs import Panel


class Unit:
    def __init__(self, status, is_docked=False):
        self.status = status
        self.is_docked = is_docked


ENTRY = {"role": "hauler", "base": "outpost_1", "intent": "carrying ore home"}
HEAD = ("ok", "Hauler 1", "SMALL", "text-muted")


class DetailBodyTests(unittest.TestCase):
    def draw(self, unit, flag, h):
        panel = Panel()
        controls_y = fleet_card.draw_detail_body(
            panel, unit, ENTRY, {"outpost_1": "North"}, HEAD, 0.5, flag, 0, 0, 200, h
        )
        return panel, controls_y

    def test_full_pane(self):
        panel, controls_y = self.draw(Unit("flying", is_docked=True), ("recalled", "warning"), 300)
        self.assertEqual(controls_y, 300 - fleet_card.BUTTON_H)
        texts = panel.texts()
        self.assertIn("flying - docked", texts)
        self.assertIn("hauler", texts)  # assignment
        self.assertIn("North", texts)
        self.assertIn("carrying ore home", texts)
        self.assertIn(("pill", (200 - 8 - len("recalled") * 7, 38, "recalled", "warning")), panel.calls)

    def test_compact_pane_skips_assignment(self):
        panel, _controls_y = self.draw(Unit("idle"), None, fleet_card.COMPACT_H - 1)
        texts = panel.texts()
        self.assertNotIn("hauler", texts)
        self.assertIn("carrying ore home", texts)
        self.assertEqual([args[2] for method, args in panel.calls if method == "pill"], ["SMALL"])


if __name__ == "__main__":
    unittest.main()
