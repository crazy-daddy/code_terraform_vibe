"""Tests for lib/contact_inference.py (what an unresolved sonar contact can still be) and its marker labels."""
import unittest

import harness  # noqa: F401  (puts the tiered lib/ dirs on sys.path)
import contact_inference as ci
import unsupported_markers as um

GEO = "research_geological_survey"
HYDRO = "research_hydrology_survey"
PETRO = "research_petroleum_survey"
EXO = "research_exotic_husbandry"
DEEP_EXO = "research_deep_exotics"


def locked(*unlocked):
    return {"reason": "research_required", "unlocked_scan_researches": list(unlocked)}


class PossibleKindsTests(unittest.TestCase):
    def test_reason_alone_fixes_the_kind(self):
        self.assertEqual(ci.possible_kinds({"reason": "wrong_scanner"}), ("biomass",))
        self.assertEqual(ci.possible_kinds({"reason": "too_hard"}), ("mineral",))
        self.assertEqual(ci.possible_kinds({"reason": "tier_too_low"}), ("oil",))

    def test_unrelated_reasons_say_nothing(self):
        self.assertEqual(ci.possible_kinds({"reason": "depleted"}), ())
        self.assertEqual(ci.possible_kinds("junk"), ())
        self.assertEqual(ci.kind_weights({"reason": "out_of_range"}), {})

    def test_research_required_drops_kinds_whose_research_was_unlocked(self):
        self.assertEqual(ci.possible_kinds(locked()), ci.ALL_TECH_KINDS)
        self.assertEqual(ci.possible_kinds(locked(GEO)), ("water", "oil", "exotic"))
        self.assertEqual(ci.possible_kinds(locked(GEO, HYDRO, PETRO)), ("exotic",))
        self.assertEqual(ci.inferred_kind(locked(HYDRO, PETRO, EXO, DEEP_EXO)), "thermal")

    def test_exotic_stays_possible_until_both_exotic_researches(self):
        self.assertIn("exotic", ci.possible_kinds(locked(GEO, HYDRO, PETRO, EXO)))
        self.assertEqual(ci.inferred_kind(locked(GEO, HYDRO, PETRO, EXO)), "exotic")

    def test_missing_or_inconsistent_record_assumes_nothing(self):
        self.assertEqual(ci.possible_kinds({"reason": "research_required"}), ci.ALL_TECH_KINDS)
        self.assertEqual(ci.possible_kinds(locked(GEO, HYDRO, PETRO, EXO, DEEP_EXO)), ci.ALL_TECH_KINDS)

    def test_min_hardness_is_one_above_the_tool_limit(self):
        self.assertEqual(ci.min_hardness({"reason": "too_hard", "hardness_limit": 1}), 2)
        self.assertEqual(ci.min_hardness({"reason": "too_hard", "hardness_limit": 3.0}), 4)
        self.assertIsNone(ci.min_hardness(locked()))


class WeightTests(unittest.TestCase):
    def test_uniform_without_a_biome_prior(self):
        weights = ci.kind_weights(locked(PETRO, EXO, DEEP_EXO))
        self.assertEqual(weights, {"thermal": 0.5, "water": 0.5})

    def test_geothermal_biome_favours_thermal(self):
        weights = ci.kind_weights(locked(PETRO, EXO, DEEP_EXO), "geothermal")
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertGreater(weights["thermal"], 0.75)

    def test_prior_never_revives_an_eliminated_kind(self):
        self.assertEqual(ci.kind_weights(locked(GEO, PETRO, EXO, DEEP_EXO), "geothermal"), {"water": 1.0})


class MarkerLabelTests(unittest.TestCase):
    def test_research_locked_marker_names_the_candidates(self):
        icon, _color, label, note = um.get_marker_style("research_required", locked(GEO))
        self.assertEqual(icon, "fluid")
        self.assertIn("water/oil/exotic?", label)
        self.assertIn("water, oil, exotic", note)

    def test_inferred_thermal_gets_the_power_icon(self):
        icon, _color, label, _note = um.get_marker_style("research_required", locked(HYDRO, PETRO, EXO, DEEP_EXO))
        self.assertEqual(icon, "power")
        self.assertIn("Thermal site", label)

    def test_too_hard_marker_states_the_hardness_floor(self):
        _icon, _color, label, _note = um.get_marker_style("too_hard", {"reason": "too_hard", "hardness_limit": 1, "scanner_tier": "basic"})
        self.assertTrue(label.startswith("Mineral, hardness 2+"))


if __name__ == "__main__":
    unittest.main()
