"""lib/swallow.py safe_call: thunk read with a logged fallback."""

import unittest

import harness
from swallow import safe_call


def _boom():
    raise RuntimeError("offline")


class SafeCallTests(harness.StubTestCase):
    def test_returns_falsy_read_value(self):
        self.assertEqual(safe_call("test.where: read", lambda: 0, 7), 0)
        self.assertIsNone(safe_call("test.where: read", lambda: None, 7))

    def test_raise_returns_default_and_logs(self):
        self.assertEqual(safe_call("test.where: read", _boom, 0.5), 0.5)
        self.assertIn("[swallowed] test.where: read:", self.debug_log())


if __name__ == "__main__":
    unittest.main()
