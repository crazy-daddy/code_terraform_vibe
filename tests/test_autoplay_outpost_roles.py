"""Tests for the role catalog in autoplay/lib/autoplay_roles.py (outpost founding: observed roles, gaps, unlocks, slots)."""
import unittest

import harness
import autoplay_roles as roles


class CatalogTests(unittest.TestCase):
    def test_every_catalog_building_group_is_a_list_of_type_ids(self):
        for name in roles.ROLE_CATALOG:
            groups = roles._groups(name)
            self.assertTrue(groups, name)
            self.assertTrue(all(isinstance(t, str) for group in groups for t in group), name)

    def test_bio_chain_per_biome(self):
        self.assertEqual(roles._groups("bio_coastal")[-1], ["bio_luminizer"])
        self.assertEqual(roles._groups("bio_frozen"), [["bio_collector"], ["bio_lab"], ["bio_exchange"]])
        self.assertEqual(roles.role_flag("bio_deep", "biome"), "deep")
        self.assertTrue(roles.role_flag("bio_deep", "items"))
        self.assertEqual(roles.DEFAULT_ROLE_PRESETS["bio_volcanic"], roles.DEFAULT_ROLE_PRESETS["bio_caster"])

    def test_observed_needs_every_group_any_alternative(self):
        self.assertTrue(roles.observed("power", {"oil_generator": 1}))
        self.assertFalse(roles.observed("bio_coastal", {"bio_collector": 1, "bio_lab": 1, "bio_exchange": 1}))
        self.assertTrue(roles.observed("bio_coastal", {"bio_collector": 1, "bio_lab": 1, "bio_exchange": 1, "bio_luminizer": 1}))
        self.assertFalse(roles.observed("farm", {"warehouse": 3}))   # not in the catalog

    def test_observed_roles_skip_families(self):
        got = roles.observed_roles({"liquid_tank": 1, "refiner": 1, "warehouse": 1})
        self.assertIn("refinery", got)
        self.assertIn("storage", got)
        self.assertFalse([name for name in got if name.startswith(roles.FAMILY_PREFIXES)])

    def test_role_gaps_keep_designation_without_buildings(self):
        gaps = roles.role_gaps(["smelter", "liquifier_deep", "farm"], {"smelter": 1})
        self.assertEqual(gaps["missing"], ["liquifier_deep"])
        self.assertEqual(gaps["extra"], [])

    def test_role_gaps_extra_ignores_buildings_a_designated_role_covers(self):
        gaps = roles.role_gaps("mining", {"warehouse": 2, "fabricator": 1})
        self.assertEqual(gaps["missing"], [])
        self.assertEqual(gaps["extra"], ["factory"])   # storage shares mining's Warehouses

    def test_unlocked_by_available_kits(self):
        self.assertFalse(roles.unlocked("drone_depot", {"drone_station"}))
        self.assertTrue(roles.unlocked("drone_depot", {"drone_station_kit_medium"}))
        self.assertFalse(roles.unlocked("bio_geothermal", {"bio_collector", "bio_lab", "bio_exchange"}))
        self.assertTrue(roles.unlocked("farm", set()))

    def test_biome_ok_and_locks(self):
        self.assertTrue(roles.biome_ok("smelter", "deep"))
        self.assertFalse(roles.biome_ok("bio_coastal", "deep"))
        self.assertEqual(roles.biome_locks(["bio_coastal", "weather_coastal", "smelter"]), ["coastal"])
        self.assertEqual(roles.biome_locks(["bio_coastal", "liquifier_deep"]), ["coastal", "deep"])

    def test_bundle_slots_shared_groups_once(self):
        self.assertEqual(roles.bundle_slots(["bio_volcanic", "bio_caster"]), (4, 4))
        self.assertEqual(roles.bundle_slots(["mining", "storage", "drone_depot", "weather_frozen"]), (3, 0))
        self.assertEqual(roles.bundle_slots(["smelter", "drone_depot"]), (2, 1))


if __name__ == "__main__":
    unittest.main()
