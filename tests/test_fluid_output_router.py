"""Stub tests for lib/fluid_routing.py FluidOutputRouter discovery caching: the network walk is
reused for NETWORK_WALK_INTERVAL_TICKS while eligibility and fill stay live, and the target choice
matches a least-full-first sort over the same fill data."""
import builtins
import unittest

from harness import StubTestCase
from game_stubs import FluidPort, Tank
import fluid_routing


class RemovableTank(Tank):
    """Tank whose handle raises once the building is gone, like a stale component."""
    removed = False

    def fluid(self):
        if self.removed:
            raise RuntimeError("building not found")
        return super().fluid()

    def fill_pct(self):
        if self.removed:
            raise RuntimeError("building not found")
        return super().fill_pct()


class FluidOutputRouterCacheTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.walks = 0
        real = fluid_routing.discover_network_buildings

        def counting(type_ids, *args, **kwargs):
            if type_ids == ("gas_tank",):
                self.walks += 1
            return real(type_ids, *args, **kwargs)
        fluid_routing.discover_network_buildings = counting
        self.addCleanup(setattr, fluid_routing, "discover_network_buildings", real)
        self.port = FluidPort(self.world)
        self.world.clock.now = 1000
        builtins.notify = lambda text, **kw: None  # type: ignore[attr-defined]

    def tank[T: Tank](self, tank_id, level, fluid="steam", cls: type[T] = Tank) -> T:
        return self.world._place(cls(self.world, tank_id, self.world.home, "gas_tank", fluid, level, 100))

    def router(self):
        return fluid_routing.FluidOutputRouter(
            type_ids="gas_tank", rebalance_fill_fraction=0.98, connection_grace_ticks=2,
            rescan_interval_ticks=300, discovery_cache_interval_ticks=100, fluid_id="steam", label="cap.steam_out")

    def ensure(self, router, tick, stalled=False):
        self.world.clock.now = tick
        return router.ensure_connection(self.port, tick, stalled)

    def test_least_full_first_with_ties_in_discovery_order(self):
        for tank_id, level in (("gas_tank_1", 60), ("gas_tank_2", 30), ("gas_tank_3", 30), ("gas_tank_4", 90)):
            self.tank(tank_id, level)
        event = self.ensure(self.router(), 1000)
        self.assertEqual((event.kind, event.target_id, event.fill_pct), ("connected", "gas_tank_2", 0.3))

    def test_full_current_moves_to_next_in_sorted_order(self):
        self.tank("gas_tank_1", 100)
        self.tank("gas_tank_2", 100)
        self.tank("gas_tank_3", 100)
        router = self.router()
        self.assertEqual(self.ensure(router, 1000).target_id, "gas_tank_1")
        self.assertEqual(self.ensure(router, 1001).target_id, "gas_tank_2")
        self.assertEqual(self.ensure(router, 1002).target_id, "gas_tank_1")

    def test_walk_reused_until_interval(self):
        self.tank("gas_tank_1", 100)
        self.tank("gas_tank_2", 100)
        router = self.router()
        for tick in range(1000, 1000 + fluid_routing.NETWORK_WALK_INTERVAL_TICKS, 50):
            self.ensure(router, tick)
        self.assertEqual(self.walks, 1)
        self.tank("gas_tank_3", 0, fluid="")
        self.world.notebook.set(fluid_routing.TANK_ASSIGNMENTS_KEY, {"gas_tank_3": "steam"})
        event = self.ensure(router, 1000 + fluid_routing.NETWORK_WALK_INTERVAL_TICKS)
        self.assertEqual(self.walks, 2)
        self.assertEqual(event.target_id, "gas_tank_3")

    def test_assignment_change_seen_without_new_walk(self):
        self.tank("gas_tank_1", 100)
        self.tank("gas_tank_2", 0, fluid="")
        router = self.router()
        self.assertEqual(self.ensure(router, 1000).target_id, "gas_tank_1")
        self.assertEqual(self.ensure(router, 1001).kind, "exhausted")
        self.world.notebook.set(fluid_routing.TANK_ASSIGNMENTS_KEY, {"gas_tank_2": "steam"})
        event = self.ensure(router, 1100)
        self.assertEqual(event.target_id, "gas_tank_2")
        self.assertEqual(self.walks, 1)

    def test_routers_share_the_walk(self):
        self.tank("gas_tank_1", 100)
        self.tank("gas_tank_2", 50)
        self.ensure(self.router(), 1000)
        self.port = FluidPort(self.world)
        self.assertEqual(self.ensure(self.router(), 1001).target_id, "gas_tank_2")
        self.assertEqual(self.walks, 1)

    def test_removed_tank_triggers_new_walk(self):
        self.tank("gas_tank_1", 100)
        gone = self.tank("gas_tank_2", 50, cls=RemovableTank)
        router = self.router()
        self.assertEqual(self.ensure(router, 1000).target_id, "gas_tank_2")
        del self.world.components["gas_tank_2"]
        gone.removed = True
        event = self.ensure(router, 1100)
        self.assertEqual(event.target_id, "gas_tank_1")
        self.assertEqual(self.walks, 2)

    def test_connect_not_found_drops_walk(self):
        self.tank("gas_tank_1", 100)
        self.tank("gas_tank_2", 50)
        router = self.router()
        self.ensure(router, 1000)
        self.port = FluidPort(self.world)
        router = self.router()
        del self.world.components["gas_tank_2"]
        notices = []
        event = router.ensure_connection(self.port, 1001, False, on_connect_notice=lambda t, s, m: notices.append((t, s)))
        self.assertEqual(notices, [("gas_tank_2", "not_found")])
        self.assertEqual(event.target_id, "gas_tank_1")
        self.ensure(router, 1002)
        self.assertEqual(self.walks, 2)

    def test_healthy_connection_skips_discovery(self):
        self.tank("gas_tank_1", 10)
        router = self.router()
        self.ensure(router, 1000)
        for tick in range(1001, 3000, 100):
            self.assertEqual(self.ensure(router, tick).kind, "healthy")
        self.assertEqual(self.walks, 1)

    def test_retiring_current_tank_is_left(self):
        self.tank("gas_tank_1", 10)
        self.tank("gas_tank_2", 20)
        router = self.router()
        self.assertEqual(self.ensure(router, 1000).target_id, "gas_tank_1")
        self.world.notebook.set(fluid_routing.TANK_ASSIGNMENTS_KEY, {"gas_tank_1": fluid_routing.RETIRING_ASSIGNMENT})
        self.assertEqual(self.ensure(router, 1001).target_id, "gas_tank_2")


class PerEntryBlacklistTests(StubTestCase):
    def test_expired_entry_is_dropped(self):
        blacklist = fluid_routing.PerEntryBlacklist(100)
        blacklist.blacklist("a", 10)
        blacklist.blacklist("b", 50)
        self.assertEqual(blacklist.filter_reachable(["a", "b", "c"], 120), ["a", "c"])
        self.assertNotIn("a", blacklist._blacklisted_at)
        self.assertTrue(blacklist.is_blacklisted("b", 120))
        self.assertEqual(blacklist.filter_reachable(["a", "b"], 0), ["a"])


if __name__ == "__main__":
    unittest.main()
