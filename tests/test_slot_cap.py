"""Stub tests for the material-slot cap on multi-material stockpiles: a
machine's input holds only so many distinct materials (per type,
game_stubs.MATERIAL_SLOTS), and take() of a new one past that answers
"slots_full" even with unit room left. storage.hit_slot_cap() spots it in a
take_item() report and storage.eject_unneeded() frees slots; the Feed Maker
and Crop Automator recover with them."""
import unittest

from game_stubs import MATERIAL_SLOTS, Building, CropAutomator, Slot
from harness import StubTestCase, storage

from crop_automator import CropAutomatorController


class StockpileBuilding(Building):
    """Plain Building with a roomy input stockpile, so only the material-slot cap limits it."""

    def __init__(self, world, building_id, outpost):
        super().__init__(world, building_id, outpost)
        self.input = Slot(self, self.input_buffer, 100000)


class SlotCapTests(StubTestCase):
    def machine(self, type_id, held):
        building = self.world.add_building(f"{type_id}_1", self.world.home, type_id, StockpileBuilding)
        building.input_buffer.update(held)
        return building

    def test_every_capped_type_rejects_a_new_material_when_full(self):
        for type_id, cap in MATERIAL_SLOTS.items():
            with self.subTest(type_id=type_id):
                held = {f"held_{i}": 1 for i in range(cap)}
                building = self.machine(type_id, held)
                self.world.inventory.add("new_item", 5)
                self.world.inventory.add("held_0", 5)
                report = {}
                self.assertEqual(storage.take_item(building.input, "new_item", 5, report=report), 0)
                self.assertTrue(storage.hit_slot_cap(report))
                self.assertEqual(storage.take_item(building.input, "held_0", 5), 5)

    def test_free_slot_takes_a_new_material(self):
        building = self.machine("fabricator", {f"held_{i}": 1 for i in range(MATERIAL_SLOTS["fabricator"] - 1)})
        self.world.inventory.add("new_item", 5)
        report = {}
        self.assertEqual(storage.take_item(building.input, "new_item", 5, report=report), 5)
        self.assertFalse(storage.hit_slot_cap(report))

    def test_eject_unneeded_frees_slots_and_keeps_wanted(self):
        building = self.machine("feed_maker", {"forage": 100, "keep_me": 1, "stray_a": 1, "stray_b": 2})
        ejected = storage.eject_unneeded(building.input, {"forage", "keep_me"}, "inventory")
        self.assertEqual(sorted(ejected), ["stray_a:ok", "stray_b:ok"])
        self.assertEqual(building.input_buffer, {"forage": 100, "keep_me": 1})
        self.assertEqual(self.world.inventory.count("stray_b"), 2)


class CropAutomatorSeedSlotTests(StubTestCase):
    def test_unused_seeds_ejected_fertilizer_kept(self):
        machine = self.world.add_building("ca_1", self.world.home, "crop_automator", cls=CropAutomator)
        cap = MATERIAL_SLOTS["crop_automator"]
        stale = {f"seed_old_{i}": 3 for i in range(cap - 2)}
        machine.input_buffer.update(stale, seed_crowncap=4, fertilizer=10)
        ctrl = CropAutomatorController(machine)
        ctrl.eject_unused_seeds(["B1", "B2"], {"B1": "crowncap", "B2": "crowncap"}, {})
        self.assertEqual(machine.input_buffer, {"seed_crowncap": 4, "fertilizer": 10})
        self.assertEqual(self.world.inventory.count("seed_old_0"), 3)


if __name__ == "__main__":
    unittest.main()
