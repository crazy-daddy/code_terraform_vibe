"""Tests for lib/item_tiers.py (shared tier ladders) and the blacklist's sonar retry rule."""
import glob
import os
import re
import unittest

import harness  # noqa: F401  (puts the tiered lib/ dirs on sys.path)
import item_tiers as it
import vehicle_claims
from game_stubs import MountSlot, Pioneer, SonarModule, World

DATABASE_GLOB = os.path.join(harness.REPO_ROOT, "docs", "database", "*.md")

# Ladder -> pattern every id of that family in docs/database/ fully matches.
FAMILIES = (
    ("SONAR_TIERS", r"sonar_module(_[a-z]+)?"),
    ("DRILL_TIERS", r"drill_module(_[a-z]+)?"),
    ("BATTERY_HOLDER_TIERS", r"battery_holder_[a-z]+"),
    ("CARGO_RACK_TIERS", r"cargo_rack_[a-z]+"),
    ("PORTABLE_BATTERY_TIERS", r"([a-z]+_)?portable_battery"),
    ("PORTABLE_BIN_TIERS", r"([a-z]+_)?portable_bin"),
    ("DRONE_CHASSIS_TIERS", r"drone_(?!station|service)[a-z]+"),
    ("CARGO_POD_TIERS", r"cargo_pod_[a-z]+"),
    ("OIL_TANK_TIERS", r"oil_tank_[a-z]+"),
    ("DEPOT_KIT_TIERS", r"drone_station_kit(_[a-z]+)?"),
)


def documented_ids():
    """Item ids from every '##### Name `id`' heading in docs/database/."""
    ids = set()
    for path in glob.glob(DATABASE_GLOB):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                match = re.match(r"#####\s.*`([a-z0-9_]+)`\s*$", line)
                if match:
                    ids.add(match.group(1))
    return ids


class LadderDocsTests(unittest.TestCase):
    def test_every_ladder_lists_exactly_the_documented_family(self):
        ids = documented_ids()
        for name, pattern in FAMILIES:
            with self.subTest(ladder=name):
                family = {i for i in ids if re.fullmatch(pattern, i)}
                self.assertEqual(set(getattr(it, name)), family)

    def test_depot_types_pair_with_kits(self):
        self.assertEqual(it.DEPOT_TYPE_TIERS, [k.replace("_kit", "") for k in it.DEPOT_KIT_TIERS])
        self.assertEqual(it.DEPOT_KIT_FOR_TYPE["drone_station_medium"], "drone_station_kit_medium")


class HelperTests(unittest.TestCase):
    def test_tier_rank_puts_unknown_values_below_every_tier(self):
        self.assertEqual(it.tier_rank(it.SONAR_TIERS, "sonar_module"), 0)
        self.assertEqual(it.tier_rank(it.SONAR_TIERS, "sonar_module_seismic"), 3)
        self.assertEqual(it.tier_rank(it.SONAR_TIERS, "deep"), -1)
        self.assertEqual(it.tier_rank(it.SONAR_TIERS, None), -1)

    def test_best_mounted_picks_the_highest_ladder_entry(self):
        slots = [MountSlot(0, "universal", "nav_module"), MountSlot(1, "universal", "sonar_module_wide"),
                 MountSlot(2, "universal", None)]
        self.assertEqual(it.best_mounted(slots, it.SONAR_TIERS), "sonar_module_wide")
        self.assertIsNone(it.best_mounted(slots, it.DRILL_TIERS))
        self.assertIsNone(it.best_mounted(None, it.SONAR_TIERS))

    def test_short_name(self):
        self.assertEqual(it.short_name("sonar_module"), "basic")
        self.assertEqual(it.short_name("sonar_module_deep"), "deep")
        self.assertEqual(it.short_name("drill_module_heavy"), "heavy")
        self.assertEqual(it.short_name("wide"), "wide")


class Host(vehicle_claims.VehicleClaimsMixin):
    def __init__(self, vehicle):
        self.vehicle = vehicle


class SonarRetryTests(unittest.TestCase):
    def host(self, sonar_id, hardness_limit=2, range_m=50.0):
        pioneer = Pioneer(World(), "pioneer_1", None, slots=[MountSlot(0, "universal", "nav_module"),
                                                             MountSlot(1, "universal", sonar_id)])
        # setattr: a Pioneer stub has no sonar unless a test mounts one (hasattr picks the role).
        setattr(pioneer, "sonar", SonarModule(it.short_name(sonar_id), hardness_limit, range_m))
        return Host(pioneer)

    def entry(self, tier, hardness_limit=2, range_m=50.0):
        return {"reason": "tier_too_low", "scanner_type": "sonar", "scanner_tier": tier,
                "hardness_limit": hardness_limit, "range": range_m}

    def test_same_sonar_does_not_retry(self):
        ok, _ = self.host("sonar_module_wide").can_attempt_target("site_1", self.entry("sonar_module_wide"))
        self.assertFalse(ok)

    def test_better_sonar_retries(self):
        ok, why = self.host("sonar_module_deep").can_attempt_target("site_1", self.entry("sonar_module_wide"))
        self.assertTrue(ok)
        self.assertEqual(why, "upgraded_sonar_deep")

    def test_legacy_tier_name_retries_once(self):
        ok, _ = self.host("sonar_module_wide").can_attempt_target("site_1", self.entry("wide"))
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
