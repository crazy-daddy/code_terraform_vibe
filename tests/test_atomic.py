"""Tests for lib/atomic.py: run_atomic result and disabled path, run_chunked looping until done, logging inside atomic calls."""

import atomic
import swallow
import tree_console
from harness import StubTestCase
from tree_console import TreeConsole


class AtomicTests(StubTestCase):
    def tearDown(self):
        atomic.ATOMIC_ENABLED = True
        super().tearDown()

    def test_run_chunked_loops_until_done(self):
        for enabled in (True, False):
            with self.subTest(atomic_enabled=enabled):
                atomic.ATOMIC_ENABLED = enabled
                calls = []

                def step(state, calls=calls):
                    state[0] += 1
                    calls.append(state[0])
                    return state[0] >= 4

                state = [0]
                atomic.run_chunked(step, state)
                self.assertEqual(calls, [1, 2, 3, 4])


class AtomicLoggingTests(StubTestCase):
    """Console writes inside run_atomic() are queued and written after it, in order (the stub console
    raises RuntimeError on print() inside a callback, as the game does)."""

    def setUp(self):
        super().setUp()
        self.log = TreeConsole(module="test_atomic")

    def tearDown(self):
        atomic.ATOMIC_ENABLED = True
        super().tearDown()

    def test_logging_inside_atomic_is_written_after(self):
        def work(n):
            self.log.print("info inside")
            self.log.debug("debug inside")
            self.log.level("warn").print("warn inside")
            return n * 2

        self.log.print("before")
        self.assertEqual(atomic.run_atomic(work, 3), 6)
        self.log.print("after")
        self.assertEqual(
            [msg.removeprefix("12:00:00 ") for _level, msg in self.world.console.lines],
            ["before", "info inside", "debug inside", "warn inside", "after"],
        )

    def test_queued_line_keeps_log_time(self):
        def work():
            self.log.print("inside")
            self.world.console.time_of_day = "13:00:00"

        atomic.run_atomic(work)
        self.assertEqual(self.world.console.lines, [("info", "12:00:00 inside")])

    def test_block_and_nested_atomic(self):
        def inner():
            self.log.debug("deep")

        def outer():
            self.log.start("plan", level="debug")
            self.log.debug("first")
            atomic.run_atomic(inner)
            self.log.end()

        atomic.run_atomic(outer)
        tree_console.flush_all()
        text = self.world.console.text()
        self.assertIn("plan", text)
        self.assertIn("deep", text)

    def test_exception_still_writes_queued_lines(self):
        def boom():
            self.log.print("before boom")
            raise ValueError("boom")

        with self.assertRaises(ValueError):
            atomic.run_atomic(boom)
        self.assertFalse(atomic.in_atomic())
        self.assertIn("before boom", self.world.console.text())

    def test_swallowed_inside_atomic(self):
        def work():
            swallow.swallowed("test_atomic.work: probe", RuntimeError("no"))

        atomic.run_atomic(work)
        self.assertIn("[swallowed] test_atomic.work: probe", self.world.console.text())
