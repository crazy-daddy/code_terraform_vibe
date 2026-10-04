"""Stub tests for the shared fluid-input glue: production.discover_fluid_sources(),
fluid_routing.discover_ranked(), fluid_routing.port_starved() and the ensure_*_logged() wrappers."""
import unittest

from harness import StubTestCase, production, fluid_routing, TreeConsole
from game_stubs import FluidPort


class DiscoverFluidSourcesTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.remote = self.world.add_outpost("remote")

    def test_viable_sources_own_outpost_first(self):
        self.world.add_building("water_pump_1", self.remote, "water_pump")
        self.world.add_tank("tank_water", self.world.home, fluid="water", level=10)
        self.world.add_tank("tank_oil", self.world.home, fluid="oil", level=10)
        self.world.add_building("water_pump_2", self.world.home, "water_pump")
        ids = production.discover_fluid_sources("water_in", "home")
        self.assertEqual(set(ids[:2]), {"tank_water", "water_pump_2"})
        self.assertEqual(ids[2:], ["water_pump_1"])

    def test_type_ids_override(self):
        self.world.add_building("water_pump_1", self.world.home, "water_pump")
        self.world.add_tank("tank_water", self.world.home, fluid="water", level=10)
        self.assertEqual(production.discover_fluid_sources("water_in", "home", ("water_pump",)), ["water_pump_1"])

    def test_no_sources(self):
        self.assertEqual(production.discover_fluid_sources("oil_in", "home"), [])


class DiscoverRankedTests(StubTestCase):
    def test_tiers_keep_order_and_rank_own_outpost_first_within_each(self):
        remote = self.world.add_outpost("remote")
        self.world.add_tank("oil_far", remote, fluid="oil", level=5)
        self.world.add_tank("oil_near", self.world.home, fluid="oil", level=5)
        self.world.add_tank("water_tank", self.world.home, fluid="water", level=5)
        self.world.add_building("oil_pump_1", self.world.home, "oil_pump")
        tiers = (("liquid_tank", "oil"), ("oil_pump", None))
        self.assertEqual(fluid_routing.discover_ranked(tiers, "home"), ["oil_near", "oil_far", "oil_pump_1"])


class PortStarvedTests(StubTestCase):
    def test_no_flow_with_room_is_starved(self):
        self.assertTrue(fluid_routing.port_starved(FluidPort(self.world, level=10)))

    def test_full_port_is_not_starved(self):
        self.assertFalse(fluid_routing.port_starved(FluidPort(self.world, level=100)))

    def test_flowing_port_is_not_starved(self):
        port = FluidPort(self.world, level=10)
        port.flow = 0.5
        self.assertFalse(fluid_routing.port_starved(port))


class FakeRouter:
    """Router whose ensure()/ensure_connection() fire the given callbacks, then return `event`."""

    def __init__(self, event, fire=()):
        self.event = event
        self.fire = fire
        self.blacklist = fluid_routing.PerEntryBlacklist(100)

    def ensure(self, port, curr_tick, is_starved=False, on_dropped=None, on_connect_notice=None):
        for args in self.fire:
            assert on_dropped is not None
            on_dropped(*args)
        return self.event

    def ensure_connection(self, port, curr_tick, is_stalled, on_blacklisted=None, on_connect_notice=None):
        for args in self.fire:
            assert on_blacklisted is not None
            on_blacklisted(*args)
        return self.event


class EnsureLoggedTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.log = TreeConsole(module="test")
        self.log.console = self.world.console

    def text(self):
        return self.debug_log()

    def test_input_connected_and_dropped_lines(self):
        router = FakeRouter(fluid_routing.FluidInputEvent("connected", "tank_1"), fire=[("tank_0", "starved")])
        event = fluid_routing.ensure_input_logged(router, object(), 5, True, self.log, "fab_1", "water_in", "No water.")
        self.assertEqual(event.kind, "connected")
        self.assertIn("[fab_1] Dropping water_in source 'tank_0': starved. Picking another.", self.text())
        self.assertIn("[fab_1] Connected water_in -> 'tank_1'.", self.text())

    def test_input_not_found_uses_caller_text_or_nothing(self):
        router = FakeRouter(fluid_routing.FluidInputEvent("not_found"))
        fluid_routing.ensure_input_logged(router, object(), 5, False, self.log, "fab_1", "water_in", "No water source.")
        fluid_routing.ensure_input_logged(router, object(), 5, False, self.log, "fab_2", "water_in")
        self.assertIn("[fab_1] No water source.", self.text())
        self.assertNotIn("fab_2", self.text())

    def test_output_blacklisted_and_connected_lines(self):
        event = fluid_routing.FluidOutputEvent("connected", "gas_tank_2", 0.25)
        router = FakeRouter(event, fire=[("gas_tank_1",)])
        fluid_routing.ensure_output_logged(router, object(), 5, True, self.log, "cap_1", "steam_out", "reported stalled")
        self.assertIn("[cap_1] 'gas_tank_1' reported stalled. Blacklisting and picking a different target.", self.text())
        self.assertIn("[cap_1] Connected steam_out -> 'gas_tank_2' (25% full).", self.text())


if __name__ == "__main__":
    unittest.main()
