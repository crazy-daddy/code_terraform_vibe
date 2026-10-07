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


class BiomeTests(unittest.TestCase):
    def test_biome_alone_settles_a_research_locked_contact(self):
        self.assertEqual(ci.inferred_kind(locked(), "geothermal"), "thermal")
        self.assertEqual(ci.inferred_kind(locked(), "coastal"), "water")
        self.assertEqual(ci.inferred_kind(locked(), "frozen"), "water")
        self.assertEqual(ci.inferred_kind(locked(), "volcanic"), "oil")
        self.assertEqual(ci.inferred_kind(locked(), "deep"), "exotic")

    def test_old_entry_without_research_record_uses_the_biome(self):
        self.assertEqual(ci.inferred_kind({"reason": "research_required"}, "geothermal"), "thermal")

    def test_biome_stored_on_the_entry_counts(self):
        self.assertEqual(ci.inferred_kind(dict(locked(), biome="volcanic")), "oil")

    def test_minerals_and_biomass_ignore_the_biome(self):
        self.assertEqual(ci.possible_kinds({"reason": "too_hard"}, "geothermal"), ("mineral",))
        self.assertEqual(ci.possible_kinds({"reason": "wrong_scanner"}, "deep"), ("biomass",))

    def test_conflicting_biome_keeps_the_research_view(self):
        self.assertEqual(ci.possible_kinds(locked(GEO, PETRO, EXO, DEEP_EXO), "geothermal"), ("water",))

    def test_needed_research_names_the_locked_one(self):
        self.assertEqual(ci.needed_research(locked(), "geothermal"), ["Geological Survey"])
        self.assertEqual(ci.needed_research(locked(EXO), "deep"), ["Deep Exotics"])
        self.assertEqual(ci.needed_research({"reason": "too_hard"}), [])


class WeightTests(unittest.TestCase):
    def test_uniform_over_what_is_left(self):
        self.assertEqual(ci.kind_weights(locked(PETRO, EXO, DEEP_EXO)), {"thermal": 0.5, "water": 0.5})

    def test_biome_leaves_one_kind(self):
        self.assertEqual(ci.kind_weights(locked(PETRO, EXO, DEEP_EXO), "geothermal"), {"thermal": 1.0})


class MarkerLabelTests(unittest.TestCase):
    def test_research_locked_marker_names_the_candidates(self):
        icon, _color, label, note = um.get_marker_style("research_required", locked(GEO))
        self.assertEqual(icon, "fluid")
        self.assertIn("water/oil/exotic?", label)
        self.assertIn("water, oil, exotic", note)

    def test_inferred_thermal_gets_the_power_icon(self):
        icon, _color, label, _note = um.get_marker_style("research_required", locked(HYDRO, PETRO, EXO, DEEP_EXO))
        self.assertEqual(icon, "power")
        self.assertEqual(label, "Thermal vent: needs Geological Survey")

    def test_geothermal_marker_names_thermal_and_thermal_cap(self):
        icon, _color, label, note = um.get_marker_style("research_required", {"reason": "research_required"}, "geothermal")
        self.assertEqual(icon, "power")
        self.assertEqual(label, "Thermal vent: needs Geological Survey")
        self.assertIn("Thermal Cap", note)

    def test_too_hard_marker_states_the_hardness_floor(self):
        _icon, _color, label, _note = um.get_marker_style("too_hard", {"reason": "too_hard", "hardness_limit": 1, "scanner_tier": "basic"})
        self.assertTrue(label.startswith("Mineral, hardness 2+"))


if __name__ == "__main__":
    unittest.main()
