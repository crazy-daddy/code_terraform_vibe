"""Stub tests for lib/fluid_routing.py pipe-conflict handling: the router whose new connection
lands on a pipe already carrying another fluid disconnects, blacklists the source and reports it;
an "unreachable" source is blacklisted quietly."""
import builtins
import unittest

from harness import StubTestCase
import fluid_routing


class Conn:
    def __init__(self, machine_id, state, fluid):
        self.machine_id = machine_id
        self.state = state
        self.fluid = fluid


class FakePort:
    """FluidPort stub; states maps source id -> FluidConnection.state its link gets."""

    def __init__(self, states, fluid="oil"):
        self.states = states
        self.fluid = fluid
        self.declared = None
        self.disconnects = 0

    def connect(self, target_id):
        self.declared = target_id
        return type("R", (), {"status": "ok", "message": ""})()

    def disconnect(self):
        self.declared = None
        self.disconnects += 1
        return type("R", (), {"status": "ok", "message": ""})()

    def connected_id(self):
        return self.declared

    def connections(self):
        if not self.declared:
            return []
        state = self.states[self.declared]
        return [Conn(self.declared, state, None if state == "conflict" else self.fluid)]


class PipeConflictTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.notices = []
        builtins.notify = lambda text, **kw: self.notices.append(text)  # type: ignore[attr-defined]

    def router(self, candidates):
        return fluid_routing.FluidInputRouter(
            discover=lambda: list(candidates), rescan_interval_ticks=150,
            discovery_cache_interval_ticks=100, neutral_grace_steps=5, label="fabricator_10.oil_in")

    def test_newcomer_yields_conflict_and_moves_on(self):
        port = FakePort({"tank_10": "conflict", "tank_11": "ready"})
        router = self.router(["tank_10", "tank_11"])
        event = router.ensure(port, 100)
        self.assertEqual((event.kind, event.source_id), ("connected", "tank_11"))
        self.assertEqual(port.disconnects, 1)
        self.assertTrue(router.blacklist.is_blacklisted("tank_10", 100 + 2000))
        self.assertEqual(len(self.notices), 1)
        self.assertEqual(fluid_routing.active_pipe_conflicts(200), ["fabricator_10.oil_in x tank_10"])
        self.assertEqual(fluid_routing.active_pipe_conflicts(100 + fluid_routing.CONFLICT_BLACKLIST_TICKS), [])

    def test_only_conflict_leaves_port_disconnected(self):
        port = FakePort({"tank_10": "conflict"})
        event = self.router(["tank_10"]).ensure(port, 100)
        self.assertEqual(event.kind, "exhausted")
        self.assertIsNone(port.declared)

    def test_unreachable_is_quiet(self):
        port = FakePort({"tank_10": "unreachable", "tank_11": "ready"})
        event = self.router(["tank_10", "tank_11"]).ensure(port, 100)
        self.assertEqual(event.source_id, "tank_11")
        self.assertEqual(port.disconnects, 0)
        self.assertEqual(self.notices, [])
        self.assertEqual(fluid_routing.active_pipe_conflicts(100), [])

    def test_established_link_waits_before_yielding(self):
        port = FakePort({"tank_10": "ready"})
        router = self.router(["tank_10"])
        router.ensure(port, 100)
        self.assertEqual(router.ensure(port, 101).kind, "healthy")
        port.states["tank_10"] = "conflict"
        for step in range(fluid_routing.ESTABLISHED_CONFLICT_GRACE_STEPS - 1):
            self.assertEqual(router.ensure(port, 102 + step).kind, "pending")
        self.assertEqual(port.disconnects, 0)
        router.ensure(port, 200)
        self.assertEqual(port.disconnects, 1)
        self.assertEqual(len(self.notices), 1)


if __name__ == "__main__":
    unittest.main()
