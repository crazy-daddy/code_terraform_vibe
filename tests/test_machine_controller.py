import unittest

import harness
import machine_controller
from game_stubs import Slot, Building
from machine_controller import MachineController, port_counts
from tree_console import TreeConsole


class _Parker:
    def __init__(self):
        self.calls = []

    def update(self, idle, *args):
        self.calls.append(idle)


class _Controller(MachineController):
    LABEL = "Test"

    def __init__(self, results):
        self.name = "m_1"
        self.log = TreeConsole(module="test_machine_controller")
        self.results = list(results)
        self.sleeps = []

    def step(self):
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def next_sleep(self, result, failed):
        delay = super().next_sleep(result, failed)
        self.sleeps.append(delay)
        return None if not self.results else delay


class NextSleepTests(harness.StubTestCase):
    def test_poll_unless_step_delay(self):
        c = _Controller([])
        c.POLL_S = 3.0
        self.assertEqual(MachineController.next_sleep(c, 7.0, False), 3.0)
        c.STEP_DELAY = True
        self.assertEqual(MachineController.next_sleep(c, 7.0, False), 7.0)
        self.assertEqual(MachineController.next_sleep(c, True, False), 3.0)
        c.ERROR_POLL_S = 9.0
        self.assertEqual(MachineController.next_sleep(c, None, True), 9.0)

    def test_park_idle(self):
        c = _Controller([])
        c.STEP_DELAY, c.PARK_IDLE_S = True, 30.0
        c.parker = _Parker()  # type: ignore[attr-defined]
        MachineController.next_sleep(c, 30.0, False)
        MachineController.next_sleep(c, 2.0, False)
        self.assertEqual(c.parker.calls, [True, False])  # type: ignore[attr-defined]


class RunTests(harness.StubTestCase):
    def test_run_logs_exception_and_keeps_going(self):
        original = machine_controller.validate_game_version
        machine_controller.validate_game_version = lambda: None
        self.addCleanup(setattr, machine_controller, "validate_game_version", original)
        c = _Controller([ValueError("boom"), None])
        c.run()
        self.assertEqual(c.sleeps, [5.0, 5.0])
        self.assertIn("[m_1] Test exception: boom", self.debug_log())


class PortCountsTests(harness.StubTestCase):
    def test_sums_stacks_and_handles_missing_port(self):
        owner = Building(self.world, "b_1", self.world.home)
        port = Slot(owner, {"iron_ore": 3, "glass": 0}, 50)
        self.assertEqual(port_counts(port, "test"), {"iron_ore": 3})
        self.assertEqual(port_counts(None, "test"), {})


if __name__ == "__main__":
    unittest.main()
