import builtins
import unittest

import harness  # noqa: F401  (puts the script libs on sys.path)
import panel_pace
from game_stubs import Mouse, Panel


class PaceTests(unittest.TestCase):
    def setUp(self):
        self.slept = []
        self._sleep = getattr(builtins, "sleep", None)
        builtins.sleep = self.slept.append  # type: ignore[attr-defined]

    def tearDown(self):
        builtins.sleep = self._sleep  # type: ignore[attr-defined]

    def test_cursor_over_card_sleeps_one_tick(self):
        panel_pace.pace(Panel(over=True))
        self.assertEqual(self.slept, [panel_pace.ACTIVE_SLEEP_S])

    def test_cursor_elsewhere_sleeps_idle(self):
        panel_pace.pace(Panel(over=False))
        self.assertEqual(self.slept, [panel_pace.IDLE_SLEEP_S])

    def test_passed_reading_is_not_read_again(self):
        panel = Panel(over=False)
        panel_pace.pace(panel, Mouse(True))
        self.assertEqual(panel.reads, 0)
        self.assertEqual(self.slept, [panel_pace.ACTIVE_SLEEP_S])

    def test_unreadable_mouse_sleeps_idle(self):
        panel_pace.pace(Panel(fails=True))
        self.assertEqual(self.slept, [panel_pace.IDLE_SLEEP_S])


if __name__ == "__main__":
    unittest.main()
