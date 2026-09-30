"""Tests for lib/atomic.py: run_atomic result and disabled path, run_chunked looping until done."""
import unittest

from harness import StubTestCase
import atomic


class AtomicTests(StubTestCase):
    def tearDown(self):
        atomic.ATOMIC_ENABLED = True
        super().tearDown()

    def test_run_atomic_returns_value(self):
        self.assertEqual(atomic.run_atomic(lambda a, b: a + b, 2, 3), 5)

    def test_run_atomic_disabled_calls_directly(self):
        atomic.ATOMIC_ENABLED = False
        self.assertEqual(atomic.run_atomic(lambda a: a * 2, 4), 8)

    def test_run_chunked_loops_until_done(self):
        calls = []

        def step(state):
            state[0] += 1
            calls.append(state[0])
            return state[0] >= 4

        state = [0]
        atomic.run_chunked(step, state)
        self.assertEqual(calls, [1, 2, 3, 4])

    def test_run_chunked_disabled(self):
        atomic.ATOMIC_ENABLED = False
        state = [0]
        atomic.run_chunked(lambda s: s.__setitem__(0, s[0] + 1) or s[0] >= 3, state)
        self.assertEqual(state, [3])
