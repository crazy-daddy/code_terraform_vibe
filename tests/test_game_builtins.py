"""
Every builtin called in scripts/ must exist inside the game.

The game's interpreter ships a subset of CPython's builtins: `id`, `frozenset`,
`open`, `eval`, ... raise NameError in game while CPython tests pass. The
game's builtin list comes from the "Built-in Functions" section of
docs/guide/builtins_and_commands.md, split from the in-game DOCS Manual.
"""
import ast
import builtins
import os
import re
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
AUTOPLAY_DIR = os.path.join(REPO_ROOT, "autoplay")
REFERENCE_FILE = os.path.join(REPO_ROOT, "docs", "guide", "builtins_and_commands.md")


def _game_builtins():
    with open(REFERENCE_FILE, encoding="utf-8") as handle:
        return set(re.findall(r"^#+ `(\w+)", handle.read(), re.M))


def _missing_builtins():
    game = _game_builtins()
    return {n for n in dir(builtins)
            if not n.startswith("_") and not n[0].isupper() and callable(getattr(builtins, n)) and n not in game}


class GameBuiltinsTests(unittest.TestCase):
    def test_scripts_call_only_game_builtins(self):
        missing = _missing_builtins()
        bad = []
        for root, _dirs, files in [w for top in (SCRIPTS_DIR, AUTOPLAY_DIR) for w in os.walk(top)]:
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(root, name)
                with open(path, encoding="utf-8") as handle:
                    tree = ast.parse(handle.read())
                defined = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
                defined |= {a.asname or a.name for n in ast.walk(tree)
                            if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
                for node in ast.walk(tree):
                    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                            and node.func.id in missing and node.func.id not in defined):
                        bad.append(f"{os.path.relpath(path, SCRIPTS_DIR)}:{node.lineno}: {node.func.id}()")
        self.assertEqual(bad, [], "\n" + "\n".join(bad))


if __name__ == "__main__":
    unittest.main()
