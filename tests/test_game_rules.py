"""lib/game_rules.py: no imports, and the lists that must cover the same ids agree."""

import ast
import os
import unittest

import game_rules
import harness  # noqa: F401  (puts the lib/ folders on sys.path)
from contact_inference import BIOME_KINDS
from storage import ORE_HEAT_ORDER

GAME_RULES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "4_controlpanel", "lib", "game_rules.py"
)


class GameRulesTests(unittest.TestCase):
    def test_imports_nothing(self):
        with open(GAME_RULES_PATH, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
        self.assertEqual(imports, [])

    def test_game_hour(self):
        self.assertEqual(game_rules.SECONDS_PER_GAME_HOUR * 24, game_rules.DAY_CYCLE_DURATION_SECONDS)

    def test_every_ore_smelts(self):
        self.assertEqual(sorted(game_rules.SMELT_PRODUCTS), sorted(game_rules.RAW_ORE_ITEM_IDS))

    def test_heat_order_ranks_every_ore(self):
        self.assertEqual(sorted(ORE_HEAT_ORDER), sorted(game_rules.RAW_ORE_ITEM_IDS))

    def test_every_biome_has_its_fluid_kinds(self):
        self.assertEqual(sorted(BIOME_KINDS), sorted(game_rules.BIOMES))


if __name__ == "__main__":
    unittest.main()
