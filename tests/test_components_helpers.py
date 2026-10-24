"""lib/components.py guarded reads: research_unlocked / all_research_unlocked, outposts(), per-outpost lookups, sensor_value."""

import unittest

import harness
from components import (
    all_research_unlocked,
    building_ids_at,
    components_at,
    home_outpost,
    outpost_by_id,
    outposts,
    research_unlocked,
    sensor_value,
)
from game_stubs import OutpostNetwork, Research
from production_core import _all_outposts
from production_sites import outpost_by_site_id
from storage_expand import StorageExpander
from warehouse_upgrade import WarehouseUpgrader


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


class _RaisingOutpost:
    id = "outpost_bad"

    def buildings(self, type_id=None):
        raise RuntimeError("buildings offline")


class PerOutpostLookupTests(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        self.out = self.world.add_outpost("outpost_2")
        self.world.add_building("b2", self.out, "habitat")
        self.world.add_building("b1", self.out, "habitat")
        self.world.add_building("w1", self.out, "waste_processor")
        self.world.add_building("", self.out, "habitat")

    def test_building_ids_at_sorted_drops_empty(self):
        self.assertEqual(building_ids_at(self.out, "habitat"), ["b1", "b2"])

    def test_building_ids_at_raise_reads_empty(self):
        self.assertEqual(building_ids_at(_RaisingOutpost(), "habitat", "test.where"), [])
        self.assertIn("[swallowed] test.where:", self.debug_log())

    def test_building_ids_at_none_outpost_reads_empty(self):
        self.assertEqual(building_ids_at(None, "habitat"), [])

    def test_outpost_by_id_finds_ref(self):
        self.assertEqual(getattr(outpost_by_id("outpost_2"), "id", None), "outpost_2")

    def test_outpost_by_id_unknown_is_none(self):
        self.assertIsNone(outpost_by_id("nope"))

    def test_components_at_resolves_components(self):
        found = components_at(self.out, "waste_processor")
        self.assertEqual([c.id for c in found], ["w1"])

    def test_components_at_drops_unresolved(self):
        del self.world.components["b1"]
        self.assertEqual([c.id for c in components_at(self.out, "habitat")], ["b2", ""])

    def test_components_at_none_outpost_reads_empty(self):
        self.assertEqual(components_at(None, "habitat"), [])

    def test_components_at_raise_reads_empty(self):
        self.assertEqual(components_at(_RaisingOutpost(), "habitat", "test.where"), [])
        self.assertIn("[swallowed] test.where:", self.debug_log())


class SensorValueTests(harness.StubTestCase):
    def test_sensor_value_reads_float(self):
        self.world.add_wildlife_sensor(7)
        self.assertEqual(sensor_value("wildlife_sensor", "test.where"), 7.0)

    def test_sensor_value_missing_sensor_is_none(self):
        del self.world.services["wildlife_sensor"]
        self.assertIsNone(sensor_value("wildlife_sensor", "test.where"))

    def test_sensor_value_raise_is_none(self):
        self.world.add_wildlife_sensor(7).broken = True
        self.assertIsNone(sensor_value("wildlife_sensor", "test.where"))
        self.assertIn("[swallowed] test.where:", self.debug_log())


class OutpostBySiteIdTests(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        self.world.add_outpost("outpost_2")

    def test_network_readable_finds_site(self):
        self.assertEqual(getattr(outpost_by_site_id("outpost_2"), "id", None), "outpost_2")
        self.assertIsNone(outpost_by_site_id("nope"))

    def test_network_unreadable_resolves_home_id(self):
        home = home_outpost()
        self.world.services["outpost_network"] = _RaisingNetwork(self.world)
        self.assertEqual(getattr(outpost_by_site_id(getattr(home, "id", "")), "id", None), getattr(home, "id", ""))

    def test_network_unreadable_other_id_is_none(self):
        self.world.services["outpost_network"] = _RaisingNetwork(self.world)
        self.assertIsNone(outpost_by_site_id("outpost_2"))


if __name__ == "__main__":
    unittest.main()
