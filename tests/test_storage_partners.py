"""storage.best_unload_target() keeps an ore and its Smelter product in
separate Warehouses without spreading one item across many."""
import unittest

from harness import StubTestCase, storage, smelter


class PartnerPlacementTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.home = self.world.home

    def test_single_warehouse_still_consolidates_next_to_partner(self):
        self.world.add_warehouse("wh_a", self.home, {"iron_ore": 50, "iron_ingot": 50})
        self.assertEqual(storage.best_unload_target("iron_ore", 1, outpost=self.home), "wh_a")

    def test_clean_holder_beats_clashing_holder(self):
        self.world.add_warehouse("wh_mixed", self.home, {"iron_ore": 50, "iron_ingot": 50})
        self.world.add_warehouse("wh_clean", self.home, {"iron_ore": 900})
        self.assertEqual(storage.best_unload_target("iron_ore", 1, outpost=self.home), "wh_clean")

    def test_splits_once_then_sticks_to_the_new_stack(self):
        mixed = self.world.add_warehouse("wh_mixed", self.home, {"iron_ore": 50, "iron_ingot": 50})
        self.world.add_warehouse("wh_b", self.home, {"seeds": 10})
        self.world.add_warehouse("wh_c", self.home)
        first = storage.best_unload_target("iron_ore", 1, outpost=self.home)
        self.assertNotEqual(first, "wh_mixed")
        self.world.components[first].add("iron_ore", 10)
        mixed.busy = True  # busy state must not move the next pick
        for _ in range(3):
            self.assertEqual(storage.best_unload_target("iron_ore", 1, outpost=self.home), first)

    def test_no_clean_room_consolidates_onto_clashing_holder(self):
        self.world.add_warehouse("wh_mixed", self.home, {"iron_ore": 50, "iron_ingot": 50})
        self.world.add_warehouse("wh_full", self.home, {"seeds": 1000})
        self.world.add_warehouse("wh_ingot", self.home, {"iron_ingot": 10})
        self.assertEqual(storage.best_unload_target("iron_ore", 1, outpost=self.home), "wh_mixed")

    def test_new_stack_avoids_partner(self):
        self.world.add_warehouse("wh_ingot", self.home, {"iron_ingot": 10})
        self.world.add_warehouse("wh_other", self.home, {"seeds": 500})
        self.assertEqual(storage.best_unload_target("iron_ore", 1, outpost=self.home), "wh_other")

    def test_hot_item_prefers_cold_neighbours(self):
        self.world.add_warehouse("wh_silicon", self.home, {"silicon": 10})
        self.world.add_warehouse("wh_neutronium", self.home, {"neutronium": 10})
        self.assertEqual(storage.best_unload_target("iron_ore", 1, outpost=self.home), "wh_neutronium")

    def test_unlisted_item_keeps_least_full_pick(self):
        self.world.add_warehouse("wh_ore", self.home, {"iron_ore": 10})
        self.world.add_warehouse("wh_fuller", self.home, {"seeds": 500})
        self.assertEqual(storage.best_unload_target("fertilizer", 1, outpost=self.home), "wh_ore")

    def test_biggest_holder_wins_over_colder_neighbours(self):
        self.world.add_warehouse("wh_small", self.home, {"glass": 95, "titanium_ingot": 400}, capacity=10000)
        self.world.add_warehouse("wh_main", self.home, {"glass": 900, "iron_ingot": 400, "iron_ore": 400}, capacity=10000)
        self.assertEqual(storage.best_unload_target("glass", 1, outpost=self.home), "wh_main")

    def test_heat_order(self):
        self.assertGreater(storage.item_heat("iron_ingot"), storage.item_heat("neutronium_bar"))
        self.assertEqual(storage.item_heat("iron_ore"), storage.item_heat("iron_ingot"))
        self.assertEqual(storage.item_heat("seeds"), 0)
        self.assertEqual(storage.recipe_partners("glass"), {"silicon"})


class HomeSmelterStorageFirstTests(StubTestCase):
    def test_home_output_goes_to_warehouse_away_from_ore(self):
        w = self.world
        w.add_warehouse("wh_ore", w.home, {"iron_ore": 100})
        clean = w.add_warehouse("wh_clean", w.home)
        s = w.add_smelter("smelter_1", w.home)
        s.output_buffer["iron_ingot"] = 7
        self.assertEqual(smelter.SmelterController(s).drain_output(), 7)
        self.assertEqual(clean.count("iron_ingot"), 7)
        self.assertEqual(w.inventory.count("iron_ingot"), 0)

    def test_home_output_falls_back_to_inventory_when_warehouses_full(self):
        w = self.world
        w.add_warehouse("wh_full", w.home, {"seeds": 1000})
        s = w.add_smelter("smelter_1", w.home)
        s.output_buffer["iron_ingot"] = 7
        self.assertEqual(smelter.SmelterController(s).drain_output(), 7)
        self.assertEqual(w.inventory.count("iron_ingot"), 7)

    def test_home_recover_input_goes_to_warehouse(self):
        w = self.world
        wh = w.add_warehouse("wh_1", w.home)
        s = w.add_smelter("smelter_1", w.home)
        s.input_buffer["iron_ore"] = 9
        self.assertTrue(smelter.SmelterController(s).recover_input())
        self.assertEqual(wh.count("iron_ore"), 9)


if __name__ == "__main__":
    unittest.main()
