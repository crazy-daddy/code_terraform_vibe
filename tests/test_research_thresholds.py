"""research_thresholds.py (generated) matches docs/database/research_catalog.md, and the extractor parses it."""

import os
import sys
import unittest

import harness  # noqa: F401 (side effect: installs game builtins and lib paths)
import research_thresholds as rt

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "devtools", "game_update"))

import extract_research  # noqa: E402


class ResearchThresholdsTest(unittest.TestCase):
    def test_module_matches_catalog(self):
        with open(extract_research.CATALOG, encoding="utf-8") as handle:
            rows = extract_research.parse(handle.read())
        self.assertEqual(len(rows), len(rt.THRESHOLDS))
        for research_id, _name, pillar, value, tech in rows:
            self.assertEqual(rt.THRESHOLDS[research_id], (pillar, value, tech), research_id)
        self.assertEqual(tuple(row[0] for row in rows), rt.ORDER)
        self.assertEqual({row[4]: row[0] for row in rows}, rt.TECH_TO_RESEARCH)
        with open(extract_research.MODULE, encoding="utf-8") as handle:
            self.assertEqual(
                handle.read(),
                extract_research.render(rows),
                "regenerate: python devtools/game_update/extract_research.py",
            )

    def test_known_entries(self):
        self.assertEqual(rt.THRESHOLDS["research_custom_panels"], ("tp", 150000, "custom_panels_unlock"))
        self.assertEqual(rt.THRESHOLDS["research_wildlife"], ("plants", 2250000, "wildlife_unlock"))
        self.assertEqual(rt.THRESHOLDS["research_rover"], ("pressure", 0.11, "rover_unlock"))
        self.assertEqual(rt.THRESHOLDS["research_hydrology_survey"][:2], ("pressure", 18))

    def test_parse_rejects_unknown_pillar(self):
        text = "##### X `research_x`\n| Threshold | Humidity 5 |\n| Tech id | x_unlock |\n"
        with self.assertRaises(ValueError):
            extract_research.parse(text)

    def test_parse_rejects_duplicates_and_odd_headings(self):
        entry = "##### X `research_x`\n| Threshold | Oxygen 5 |\n| Tech id | x_unlock |\n"
        with self.assertRaises(ValueError):
            extract_research.parse(entry + entry)
        with self.assertRaises(ValueError):
            extract_research.parse(entry + "| Threshold | Oxygen 6 |\n")
        with self.assertRaises(ValueError):
            extract_research.parse(entry + "##### `research_y` Odd\n| Threshold | Oxygen 7 |\n| Tech id | y_unlock |\n")

    def test_parse_rejects_incomplete_entry(self):
        text = "##### X `research_x`\n| Threshold | Oxygen 5 |\n"
        with self.assertRaises(ValueError):
            extract_research.parse(text)


if __name__ == "__main__":
    unittest.main()
