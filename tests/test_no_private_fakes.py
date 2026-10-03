"""Guard: tests extend the shared fakes in tests/game_stubs.py instead of
hand-rolling private copies.

A test file may not define a class (top-level or nested) named like a
game_stubs class, with or without leading underscores, unless one of its
bases is that class. `from game_stubs import X as Y` aliases count as X.
"""
import ast
import os
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
STUBS = "game_stubs"


def _parse(name):
    with open(os.path.join(TESTS_DIR, name), encoding="utf-8") as handle:
        return ast.parse(handle.read(), name)


def stub_classes():
    return {node.name for node in _parse(STUBS + ".py").body if isinstance(node, ast.ClassDef)}


def _stub_aliases(tree):
    """{local name: game_stubs name} for `from game_stubs import X [as Y]`."""
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == STUBS:
            for alias in node.names:
                aliases[alias.asname or alias.name] = alias.name
    return aliases


def _base_name(base, aliases):
    if isinstance(base, ast.Name):
        return aliases.get(base.id, base.id)
    if isinstance(base, ast.Attribute) and isinstance(base.value, ast.Name) and base.value.id == STUBS:
        return base.attr
    return None


def private_fakes(tree, stubs):
    """[(line, class name)] of classes in `tree` that shadow a game_stubs class without subclassing it."""
    aliases = _stub_aliases(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        stub = node.name.lstrip("_")
        if stub in stubs and stub not in {_base_name(base, aliases) for base in node.bases}:
            found.append((node.lineno, node.name))
    return found


class NoPrivateFakesTests(unittest.TestCase):
    def test_test_files_subclass_shared_fakes(self):
        stubs = stub_classes()
        bad = []
        for name in sorted(os.listdir(TESTS_DIR)):
            if name.startswith("test_") and name.endswith(".py"):
                bad += [f"{name}:{line} {cls}" for line, cls in private_fakes(_parse(name), stubs)]
        self.assertEqual(bad, [], "subclass or extend the game_stubs class instead of a private copy")

    def test_guard_spots_a_copy_and_accepts_a_subclass(self):
        tree = ast.parse("from game_stubs import Result as Base\n"
                         "class _Store: pass\n"
                         "class Result(Base): pass\n"
                         "class _Drone(game_stubs.Drone): pass\n"
                         "class Helper: pass\n")
        self.assertEqual(private_fakes(tree, {"Store", "Result", "Drone"}), [(2, "_Store")])


if __name__ == "__main__":
    unittest.main()
