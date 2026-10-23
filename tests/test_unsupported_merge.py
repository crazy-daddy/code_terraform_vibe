"""unsupported_markers.merge_unsupported: the one fold of the shared scan
blacklist over the two retired per-role keys, read by the fleet
(VehicleClaimsMixin.get_unsupported_targets) and persisted by archive_cleaner."""

import unittest

import harness
import vehicle_claims
from archive import archive
from unsupported_markers import (
    LEGACY_PIONEER_SONAR_KEY,
    LEGACY_ROVER_UNSUPPORTED_KEY,
    SURVEY_UNSUPPORTED_KEY,
    key_tile,
    merge_unsupported,
)


class MergeUnsupportedTests(unittest.TestCase):
    def test_legacy_pioneer_key_becomes_canonical(self):
        entry = {"reason": "hardness"}
        merged, migrated = merge_unsupported({}, {}, {"3:4": entry})
        self.assertEqual(merged, {"poi_3_4": entry})
        self.assertNotIn("3:4", merged)
        self.assertEqual(migrated, 1)

    def test_rover_wins_over_pioneer_on_collision(self):
        rover = {"reason": "rover"}
        merged, _ = merge_unsupported({}, {"poi_3_4": rover}, {"3:4": {"reason": "pioneer"}})
        self.assertIs(merged["poi_3_4"], rover)

    def test_shared_wins_over_legacy(self):
        shared = {"reason": "shared"}
        merged, _ = merge_unsupported(
            {"poi_3_4": shared}, {"poi_3_4": {"reason": "rover"}}, {"3:4": {"reason": "pioneer"}}
        )
        self.assertIs(merged["poi_3_4"], shared)

    def test_non_dict_inputs_ignored(self):
        self.assertEqual(merge_unsupported([1], None, "x"), ({}, 0))

    def test_pioneer_key_without_coords_kept(self):
        entry = {"reason": "hardness"}
        self.assertEqual(merge_unsupported({}, {}, {"a:b": entry}), ({"a:b": entry}, 0))

    def test_key_tile_rounds_both_key_forms(self):
        self.assertEqual(key_tile("poi_3.4_4.6"), (3, 5))
        self.assertEqual(key_tile("3:4"), (3, 4))
        self.assertIsNone(key_tile("site_7"))


class _Host(vehicle_claims.VehicleClaimsMixin):
    pass


class FleetViewTests(harness.StubTestCase):
    def test_fleet_view_matches_cleaner(self):
        shared = {"poi_1_1": {"reason": "shared"}}
        rover = {"poi_3_4": {"reason": "rover"}, "site_9": {"reason": "rover"}}
        pioneer = {"3:4": {"reason": "pioneer"}, "5:6": {"reason": "pioneer"}}
        archive.set(SURVEY_UNSUPPORTED_KEY, shared)
        archive.set(LEGACY_ROVER_UNSUPPORTED_KEY, rover)
        archive.set(LEGACY_PIONEER_SONAR_KEY, pioneer)
        targets = _Host().get_unsupported_targets()
        self.assertEqual(targets, merge_unsupported(shared, rover, pioneer)[0])
        self.assertNotIn("5:6", targets)
        self.assertIn("poi_5_6", targets)


if __name__ == "__main__":
    unittest.main()
