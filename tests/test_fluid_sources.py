"""Stub tests for the shared fluid-input glue: production.discover_fluid_sources(),
fluid_routing.discover_ranked() (POI extractors, stock ranking), the stocked-source rebalance,
fluid_routing.port_starved() and the ensure_*_logged() wrappers."""
import unittest

from harness import StubTestCase, production, fluid_routing, TreeConsole
from game_stubs import FluidPort


class DiscoverFluidSourcesTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.remote = self.world.add_outpost("remote")

    def test_pumps_come_from_power_grids_not_outposts(self):
        self.world.add_extractor("water_pump_1", "water_pump")
        self.world.add_building("water_pump_9", self.world.home, "water_pump")  # outpost.buildings() hides it
        self.assertEqual(production.discover_fluid_sources("water_in", "home"), ["water_pump_1"])
        self.assertTrue(production.can_source_fluid("water_in"))

    def test_no_pump_and_no_tank_cannot_source(self):
        self.world.add_tank("tank_oil", self.world.home, fluid="oil", level=50)
        self.assertFalse(production.can_source_fluid("water_in"))

    def test_stocked_tanks_then_pumps_then_low_tanks(self):
        self.world.add_extractor("water_pump_1", "water_pump")
        self.world.add_tank("tank_low", self.world.home, fluid="water", level=2)
        self.world.add_tank("tank_far", self.remote, fluid="water", level=90)
        self.world.add_tank("tank_near", self.world.home, fluid="water", level=30)
        self.world.add_tank("tank_oil", self.world.home, fluid="oil", level=90)
        ids = production.discover_fluid_sources("water_in", "home")
        self.assertEqual(ids, ["tank_near", "tank_far", "water_pump_1", "tank_low"])

    def test_type_ids_override(self):
        self.world.add_extractor("water_pump_1", "water_pump")
        self.world.add_tank("tank_water", self.world.home, fluid="water", level=10)
        self.assertEqual(production.discover_fluid_sources("water_in", "home", ("water_pump",)), ["water_pump_1"])

    def test_no_sources(self):
        self.assertEqual(production.discover_fluid_sources("oil_in", "home"), [])


class DiscoverRankedTests(StubTestCase):
    def test_fuller_tank_first_within_own_outpost_then_remote(self):
        remote = self.world.add_outpost("remote")
        self.world.add_tank("oil_far", remote, fluid="oil", level=80)
        self.world.add_tank("oil_near", self.world.home, fluid="oil", level=10)
        self.world.add_tank("oil_near_full", self.world.home, fluid="oil", level=60)
        self.world.add_tank("water_tank", self.world.home, fluid="water", level=50)
        self.world.add_extractor("oil_pump_1", "oil_pump")
        tiers = (("liquid_tank", "oil"), ("oil_pump", None))
        self.assertEqual(fluid_routing.discover_ranked(tiers, "home"), ["oil_near_full", "oil_near", "oil_far", "oil_pump_1"])

    def test_assigned_empty_tank_ranks_last(self):
        self.world.add_tank("oil_empty", self.world.home)
        self.world.add_tank("oil_far", self.world.add_outpost("remote"), fluid="oil", level=5)
        self.world.add_extractor("oil_pump_1", "oil_pump")
        fluid_routing.archive.set(fluid_routing.TANK_ASSIGNMENTS_KEY, {"oil_empty": "oil"})
        tiers = (("liquid_tank", "oil"), ("oil_pump", None))
        self.assertEqual(fluid_routing.discover_ranked(tiers, "home"), ["oil_far", "oil_pump_1", "oil_empty"])

    def test_steam_tank_below_low_line_ranks_behind_caps(self):
        self.world.add_tank("steam_low", self.world.home, fluid="steam", level=5, type_id="gas_tank")
        self.world.add_tank("steam_tank", self.world.home, fluid="steam", level=2500, type_id="gas_tank")
        self.world.add_extractor("thermal_cap_1", "thermal_cap")
        ranked = fluid_routing.discover_ranked(fluid_routing.STEAM_SOURCE_TIERS, "home")
        self.assertEqual(ranked, ["steam_tank", "thermal_cap_1", "steam_low"])


class StockedSourceRebalanceTests(StubTestCase):
    """A healthy own link on a near-empty tank or a producer moves to a stocked tank."""

    def setUp(self):
        super().setUp()
        self.port = FluidPort(self.world, level=5, capacity=10)
        self.port.link_states = {}

    def router(self):
        return fluid_routing.FluidInputRouter(
            discover=lambda: fluid_routing.discover_ranked((("liquid_tank", "oil"), ("oil_pump", None)), "home"),
            rescan_interval_ticks=150, discovery_cache_interval_ticks=100, neutral_grace_steps=5, label="fab.oil_in")

    def test_low_tank_moves_to_stocked_tank(self):
        self.world.add_tank("oil_low", self.world.home, fluid="oil", level=2)
        self.world.add_tank("oil_full", self.world.add_outpost("remote"), fluid="oil", level=90)
        self.port.connect("oil_low")
        event = self.router().ensure(self.port, 1000)
        self.assertEqual((event.kind, event.source_id, event.rebalance), ("connected", "oil_full", True))
        self.assertEqual(self.port.connected_id(), "oil_full")

    def test_pump_moves_to_stocked_tank(self):
        self.world.add_extractor("oil_pump_1", "oil_pump")
        self.world.add_tank("oil_full", self.world.home, fluid="oil", level=50)
        self.port.connect("oil_pump_1")
        self.assertEqual(self.router().ensure(self.port, 1000).source_id, "oil_full")

    def test_stays_when_no_tank_reaches_switch_line(self):
        self.world.add_tank("oil_low", self.world.home, fluid="oil", level=2)
        self.world.add_tank("oil_some", self.world.home, fluid="oil", level=15)
        self.port.connect("oil_low")
        self.assertEqual(self.router().ensure(self.port, 1000).kind, "healthy")
        self.assertEqual(self.port.connected_id(), "oil_low")

    def test_stocked_source_stays(self):
        self.world.add_tank("oil_mid", self.world.home, fluid="oil", level=10)
        self.world.add_tank("oil_full", self.world.home, fluid="oil", level=90)
        self.port.connect("oil_mid")
        self.assertEqual(self.router().ensure(self.port, 1000).kind, "healthy")

    def test_checks_at_most_every_interval(self):
        self.world.add_tank("oil_low", self.world.home, fluid="oil", level=2)
        self.port.connect("oil_low")
        router = self.router()
        self.assertEqual(router.ensure(self.port, 1000).kind, "healthy")
        self.world.add_tank("oil_full", self.world.home, fluid="oil", level=90)
        router._cache.invalidate()
        interval = fluid_routing.SOURCE_REBALANCE_INTERVAL_TICKS
        self.assertEqual(router.ensure(self.port, 1000 + interval - 1).kind, "healthy")
        self.assertEqual(router.ensure(self.port, 1000 + interval).source_id, "oil_full")

    def test_broken_target_goes_back_and_is_blacklisted(self):
        self.world.add_tank("oil_low", self.world.home, fluid="oil", level=2)
        self.world.add_tank("oil_far", self.world.add_outpost("remote"), fluid="oil", level=90)
        self.port.link_states = {"oil_far": "unreachable"}
        self.port.connect("oil_low")
        router = self.router()
        self.assertEqual(router.ensure(self.port, 1000).kind, "healthy")
        self.assertEqual(self.port.connected_id(), "oil_low")
        self.assertTrue(router.blacklist.is_blacklisted("oil_far", 1001))


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
