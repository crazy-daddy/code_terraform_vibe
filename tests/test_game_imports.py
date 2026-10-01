"""
Every import in scripts/ must exist inside the game.

The game's interpreter has no CPython standard library: only the modules in
GAME_MODULES resolve (the game's module registry, decompiled simworker; see
docs/cheatsheet/dev_workflow.md §10). Anything else is one of our own lib/
modules or raises ModuleNotFoundError in game, while CPython tests pass happily
(`time`, `copy`, `os`, `sys`, ...). Imports under
`if TYPE_CHECKING:` never run and are skipped.
"""
import ast
import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
AUTOPLAY_DIR = os.path.join(REPO_ROOT, "autoplay")

# Executable modules, plus the type-only ones the game erases and the special ones.
GAME_MODULES = {
    "random", "functools", "re", "dataclasses", "enum", "json", "heapq", "traceback",
    "math", "itertools", "operator", "string", "collections",
    "typing", "collections.abc", "types", "user_stubs",
    "builtins", "__builtins__", "__future__",
}


def _lib_modules():
    names = set()
    for tier in os.listdir(SCRIPTS_DIR):
        lib_dir = os.path.join(SCRIPTS_DIR, tier, "lib")
        if os.path.isdir(lib_dir):
            names.update(f[:-3] for f in os.listdir(lib_dir) if f.endswith(".py"))
    autoplay_lib = os.path.join(AUTOPLAY_DIR, "lib")
    if os.path.isdir(autoplay_lib):
        names.update(f[:-3] for f in os.listdir(autoplay_lib) if f.endswith(".py"))
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
        for root, _dirs, files in [w for top in (SCRIPTS_DIR, AUTOPLAY_DIR) for w in os.walk(top)]:
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

    def test_no_import_cycles_between_lib_modules(self):
        """
        A module-level import cycle between lib modules breaks in game: a module
        re-entered mid-load is handed over half-initialized, so `from X import NAME`
        raises ImportError when NAME is defined below X's own imports (seen live:
        storage -> script_parking -> power -> turbine_commit -> script_parking).
        Checked on the highest tier's copy of each module (what a top-tier save runs),
        which the stub tests (TEST_TIER = 4) don't load. Import inside the function
        that needs the module to break a cycle.
        """
        files = {}
        tiers = sorted((int(name.split("_", 1)[0]), name) for name in os.listdir(SCRIPTS_DIR)
                       if name.split("_", 1)[0].isdigit() and os.path.isdir(os.path.join(SCRIPTS_DIR, name, "lib")))
        for _tier, name in tiers:  # a higher tier's copy overrides
            lib_dir = os.path.join(SCRIPTS_DIR, name, "lib")
            for f in os.listdir(lib_dir):
                if f.endswith(".py"):
                    files[f[:-3]] = os.path.join(lib_dir, f)
        graph = {}
        for module, path in files.items():
            with open(path, encoding="utf-8") as handle:
                graph[module] = sorted({m.split(".")[0] for m in _module_level_imports(ast.parse(handle.read()).body)} & set(files))
        cycles = set()

        def walk(node, stack):
            for target in graph[node]:
                if target in stack:
                    cycle = tuple(stack[stack.index(target):])
                    first = cycle.index(min(cycle))
                    cycles.add(cycle[first:] + cycle[:first])
                elif len(stack) < 12:
                    walk(target, stack + [target])

        for module in sorted(graph):
            walk(module, [module])
        self.assertEqual(sorted(" -> ".join(c + (c[0],)) for c in cycles), [])


def _module_level_imports(body):
    """Modules imported when a module body runs: top level, inside top-level if/try, not under TYPE_CHECKING."""
    for node in body:
        if isinstance(node, ast.If):
            if not _is_type_checking(node.test):
                yield from _module_level_imports(node.body)
                yield from _module_level_imports(node.orelse)
        elif isinstance(node, ast.Try):
            yield from _module_level_imports(node.body)
            yield from _module_level_imports(node.orelse)
            yield from _module_level_imports(node.finalbody)
            for handler in node.handlers:
                yield from _module_level_imports(handler.body)
        elif isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            yield node.module


if __name__ == "__main__":
    unittest.main()
