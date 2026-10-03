"""Stub tests for the shared fluid-source discovery: production.discover_fluid_sources() and
fluid_routing.discover_ranked()."""
import unittest

from harness import StubTestCase, production, fluid_routing


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


if __name__ == "__main__":
    unittest.main()
