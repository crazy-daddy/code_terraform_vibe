"""lib/status_warning.py: one log line per start and clear, the script status in between."""
from harness import StubTestCase
from status_warning import StatusWarning
from tree_console import TreeConsole


class StatusWarningTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.log = TreeConsole(module="status_warning_test")

    def lines(self):
        self.log.flush()
        return [message for _level, message in self.world.console.lines]

    def test_logs_once_while_active_and_clears_with_duration(self):
        warning = StatusWarning(self.log, "pump_1", "Stall")
        for _ in range(3):
            warning.update(True, "Stalled: nothing downstream.")
        self.assertEqual(self.world.status, ("[pump_1] Stalled: nothing downstream.", "warn"))
        self.assertEqual(self.lines(), ["[pump_1] Stalled: nothing downstream."])
        self.world.clock.now += 450
        warning.update(False)
        warning.update(False)
        self.assertIsNone(self.world.status)
        self.assertEqual(self.lines()[1:], ["[pump_1] Stall cleared after 45 s (since tick 1000)."])

    def test_message_change_refreshes_status_without_logging(self):
        warning = StatusWarning(self.log, "cap_1", "Relief venting")
        warning.update(True, "venting 10%")
        warning.update(True, "venting 40%")
        self.assertEqual(self.world.status, ("[cap_1] venting 40%", "warn"))
        self.assertEqual(len(self.lines()), 1)

    def test_warnings_of_one_script_share_the_status(self):
        stall = StatusWarning(self.log, "cap_1", "Stall")
        relief = StatusWarning(self.log, "cap_1", "Relief venting", level="error")
        stall.update(True, "stalled")
        relief.update(True, "venting")
        self.assertEqual(self.world.status, ("[cap_1] stalled | [cap_1] venting", "error"))
        relief.update(False)
        self.assertEqual(self.world.status, ("[cap_1] stalled", "warn"))

    def test_status_text_capped_at_game_limit(self):
        StatusWarning(self.log, "m", "Long").update(True, "x" * 300)
        status = self.world.status
        assert status is not None
        self.assertEqual(len(status[0]), 240)
