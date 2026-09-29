"""
Stub test harness: loads the tiered `scripts/<tier>/lib` modules outside the
game against a fake world (tests/game_stubs.py).

The game injects `get_component()` and `sleep()` as builtins and resolves
`from production import ...` against the save's flat `lib/` folder. This
module does the same: it installs the builtins, puts every tier's `lib/` on
sys.path (highest tier up to TEST_TIER first, like devtools/scripts_sync.py's
resolver), and resets per-module state between tests.

Run from the repo root: `python -m unittest discover -s tests`.
"""
import builtins
import os
import re
import sys
import unittest

# No __pycache__ inside scripts/<tier>/lib (the sync tool mirrors that folder).
sys.dont_write_bytecode = True

from game_stubs import World  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
# Highest tier whose lib/ copies the tests load; lower tiers fill the gaps.
TEST_TIER = 4


def _tier_lib_dirs(max_tier):
    tiers = []
    for name in os.listdir(SCRIPTS_DIR):
        match = re.match(r"^(\d+)_", name)
        lib_dir = os.path.join(SCRIPTS_DIR, name, "lib")
        if match and int(match.group(1)) <= max_tier and os.path.isdir(lib_dir):
            tiers.append((int(match.group(1)), lib_dir))
    return [lib_dir for _n, lib_dir in sorted(tiers, reverse=True)]


def _install_builtins(world):
    builtins.get_component = world.get_component  # type: ignore[attr-defined]
    builtins.sleep = lambda _seconds: None  # type: ignore[attr-defined]


_LIB_DIRS = _tier_lib_dirs(TEST_TIER)
for _lib_dir in reversed(_LIB_DIRS):
    if _lib_dir not in sys.path:
        sys.path.insert(0, _lib_dir)

# Module-level singletons (archive.archive, each module's TreeConsole) bind to
# get_component() at import time, so a world must exist before the imports.
_install_builtins(World())
import archive  # noqa: E402
import production  # noqa: E402
import storage  # noqa: E402
import swallow  # noqa: E402
import smelter  # noqa: E402
import fabricator  # noqa: E402
from tree_console import TreeConsole  # noqa: E402

LIB_MODULES = (archive, production, storage, swallow, smelter, fabricator)


def _reset_module_state(world):
    archive.archive.notebook = world.notebook
    swallow._STATE["console"] = None
    swallow._LAST.clear()
    swallow._WARNED.clear()
    storage._recent_busy.clear()
    production._WARNED_UNKNOWN_MANUAL_ITEMS.clear()
    for module in list(sys.modules.values()):
        module_file = getattr(module, "__file__", None) or ""
        if not any(module_file.startswith(lib_dir) for lib_dir in _LIB_DIRS):
            continue
        for value in list(vars(module).values()):
            if isinstance(value, TreeConsole):
                value.console = world.console


class StubTestCase(unittest.TestCase):
    """Fresh fake world per test. Fails a test whose run hit a
    `swallowed()` bug-class exception (TypeError, AttributeError, ...), since
    a broad except would otherwise hide a bug in our own call."""

    def setUp(self):
        self.world = World()
        _install_builtins(self.world)
        _reset_module_state(self.world)

    def tearDown(self):
        bugs = [msg for level, msg in self.world.console.lines if level == "warn" and "likely a code bug" in msg]
        if bugs:
            self.fail("swallowed bug-class exception(s):\n" + "\n".join(bugs))

    def debug_log(self):
        """Every console line so far, for failure messages."""
        return self.world.console.text()
