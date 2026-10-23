"""lib/components.py guarded reads: research_unlocked / all_research_unlocked."""

import unittest

import harness
from components import all_research_unlocked, research_unlocked
from game_stubs import Research
from storage_expand import StorageExpander
from warehouse_upgrade import WarehouseUpgrader


class _RaisingResearch(Research):
    def is_unlocked(self, research_id):
        raise RuntimeError("research offline")


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
