"""Tier-5 Power Guard shed thresholds (5_steampower/lib/power.py). The harness puts
4_controlpanel's power.py first on sys.path, so the tier-5 file is loaded by path."""
import importlib.util
import os
import unittest

import harness

_PATH = os.path.join(harness.SCRIPTS_DIR, "5_steampower", "lib", "power.py")
_SPEC = importlib.util.spec_from_file_location("power_tier5", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
power5 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(power5)


class ShedThresholdTests(unittest.TestCase):
    def test_default_tiers_shed_progressively(self):
        tiers = len(power5.DEFAULT_SHEDDING_TIERS)
        self.assertEqual(tiers, 3)
        self.assertEqual(power5.tiers_to_shed(0.20, tiers), 0)
        self.assertEqual(power5.tiers_to_shed(0.08, tiers), 1)
        self.assertEqual(power5.tiers_to_shed(0.04, tiers), 2)
        self.assertEqual(power5.tiers_to_shed(0.01, tiers), 3)

    def test_habitats_shed_last_and_hard(self):
        self.assertEqual(power5.DEFAULT_SHEDDING_TIERS[-1], ["habitat_*"])
        self.assertNotIn("habitat_*", power5.SOFT_SHED_PATTERNS)
        self.assertIn("feed_maker_*", power5.SOFT_SHED_PATTERNS)
        self.assertIn("feed_maker_*", power5.DEFAULT_SHEDDING_TIERS[1])

    def test_fuel_assemblers_shed_first_and_hard(self):
        self.assertIn("fuel_assembler_*", power5.DEFAULT_SHEDDING_TIERS[0])
        self.assertNotIn("fuel_assembler_*", power5.SOFT_SHED_PATTERNS)

    def test_override_with_more_tiers_uses_last_threshold(self):
        self.assertEqual(power5.tiers_to_shed(0.01, 5), 5)
        self.assertEqual(power5.tiers_to_shed(0.03, 5), 2)


if __name__ == "__main__":
    unittest.main()
