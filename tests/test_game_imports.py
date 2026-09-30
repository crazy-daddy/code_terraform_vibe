"""
Every import in scripts/ must exist inside the game.

The game's interpreter has no CPython standard library: only the modules in
GAME_MODULES resolve (the game's module registry, decompiled simworker; see
docs/cheatsheet/dev_workflow.md §10). Anything else is one of our own lib/
modules or raises ModuleNotFoundError in game, while CPython tests pass happily
(`math`, `operator`, `collections`, `itertools`, ...). Imports under
`if TYPE_CHECKING:` never run and are skipped.
"""
import ast
import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")

# Executable modules, plus the type-only ones the game erases and the special ones.
GAME_MODULES = {
    "random", "functools", "re", "dataclasses", "enum", "json", "heapq", "traceback",
    "typing", "collections.abc", "types", "user_stubs",
    "builtins", "__builtins__", "__future__",
}


def _lib_modules():
    names = set()
    for tier in os.listdir(SCRIPTS_DIR):
        lib_dir = os.path.join(SCRIPTS_DIR, tier, "lib")
        if os.path.isdir(lib_dir):
            names.update(f[:-3] for f in os.listdir(lib_dir) if f.endswith(".py"))
    return names


def _is_type_checking(test):
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or \
        (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")


def _imports(tree):
    """(module, line) for every import that runs (not under `if TYPE_CHECKING:`)."""
    skip = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_type_checking(node.test):
            for child in node.body:
                skip.update(id(n) for n in ast.walk(child))
    for node in ast.walk(tree):
        if id(node) in skip:
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            yield node.module, node.lineno


class GameImportTests(unittest.TestCase):
    def test_scripts_import_only_game_modules_and_our_libs(self):
        libs = _lib_modules()
        bad = []
        for root, _dirs, files in os.walk(SCRIPTS_DIR):
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(root, name)
                with open(path, encoding="utf-8") as handle:
                    try:
                        tree = ast.parse(handle.read())
                    except SyntaxError:
                        continue  # not ours to judge here
                for module, line in _imports(tree):
                    if module in GAME_MODULES or module.split(".")[0] in libs:
                        continue
                    bad.append(f"{os.path.relpath(path, REPO_ROOT)}:{line}: import {module}")
        self.assertEqual(bad, [], "modules the game doesn't have:\n" + "\n".join(bad))


if __name__ == "__main__":
    unittest.main()
