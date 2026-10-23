"""lib/components.py guarded reads: research_unlocked / all_research_unlocked, outposts()."""

import unittest

import harness
from components import all_research_unlocked, home_outpost, outposts, research_unlocked
from game_stubs import OutpostNetwork, Research
from production_core import _all_outposts
from storage_expand import StorageExpander
from warehouse_upgrade import WarehouseUpgrader
from weather_signals import discover_stations


class _RaisingResearch(Research):
    def is_unlocked(self, research_id):
        raise RuntimeError("research offline")


class _RaisingNetwork(OutpostNetwork):
    def outposts(self):
        raise RuntimeError("network offline")


class OutpostsTests(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        self.world.add_outpost("outpost_2")

    def raise_on_outposts(self):
        self.world.services["outpost_network"] = _RaisingNetwork(self.world)

    def test_outposts_lists_network(self):
        self.assertEqual(sorted(o.id for o in outposts()), sorted(self.world.outposts))

    def test_outposts_missing_network_reads_empty(self):
        del self.world.services["outpost_network"]
        self.assertEqual(outposts(), [])

    def test_outposts_raise_reads_empty(self):
        self.raise_on_outposts()
        self.assertEqual(outposts(), [])
        self.assertIn("[swallowed] components.outposts: network.outposts:", self.debug_log())

    def test_production_core_falls_back_to_home(self):
        home = home_outpost()
        self.raise_on_outposts()
        self.assertEqual(_all_outposts(), [home])

    def test_weather_stations_survive_network_raise(self):
        self.raise_on_outposts()
        self.assertEqual(discover_stations(), [])


class ResearchUnlockedTests(harness.StubTestCase):
    def test_research_unlocked_reads_stub(self):
        self.world.research.unlocked.add("research_a")
        self.assertTrue(research_unlocked("research_a"))
        self.assertFalse(research_unlocked("research_b"))

    def test_research_unlocked_missing_component_reads_false(self):
        del self.world.services["research"]
        self.assertFalse(research_unlocked("research_a"))

    def test_research_unlocked_raise_reads_false(self):
        self.world.services["research"] = _RaisingResearch()
        self.assertFalse(research_unlocked("research_a", "test.where"))
        self.assertIn("[swallowed] test.where:", self.debug_log())

    def test_all_research_unlocked(self):
        self.world.research.unlocked.update({"research_a", "research_b"})
        self.assertTrue(all_research_unlocked(["research_a", "research_b"]))
        self.assertFalse(all_research_unlocked(["research_a", "research_c"]))
        self.assertFalse(all_research_unlocked([]))

    def test_large_unlocked_falls_back_to_inventory(self):
        # The two "researched OR one in inventory" gates keep the inventory branch.
        upgrader = WarehouseUpgrader()
        expander = StorageExpander()
        self.assertFalse(upgrader._large_unlocked())
        self.assertFalse(expander._unlocked("large_warehouse", "research_high_bay_warehousing"))
        self.world.inventory.add("large_warehouse", 1)
        self.assertTrue(upgrader._large_unlocked())
        self.assertTrue(expander._unlocked("large_warehouse", "research_high_bay_warehousing"))


if __name__ == "__main__":
    unittest.main()
