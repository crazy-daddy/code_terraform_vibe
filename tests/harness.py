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
    """sys.path order of every tier's lib/: max_tier down to 0 (a higher
    tier's copy overrides), then the higher tiers ascending, so modules that
    only exist there still import -- the same chain as scripts_sync's
    lib_chain()."""
    tiers = []
    for name in os.listdir(SCRIPTS_DIR):
        match = re.match(r"^(\d+)_", name)
        lib_dir = os.path.join(SCRIPTS_DIR, name, "lib")
        if match and os.path.isdir(lib_dir):
            tiers.append((int(match.group(1)), lib_dir))
    at_or_below = [lib_dir for n, lib_dir in sorted(tiers, reverse=True) if n <= max_tier]
    above = [lib_dir for n, lib_dir in sorted(tiers) if n > max_tier]
    return at_or_below + above


def _install_builtins(world):
    builtins.get_component = world.get_component  # type: ignore[attr-defined]
    builtins.sleep = lambda _seconds: None  # type: ignore[attr-defined]
    builtins.notify = lambda text, *_args, **_kwargs: world.notices.append(text)  # type: ignore[attr-defined]
    builtins.set_status = lambda message, level="info": setattr(world, "status", (message, level))  # type: ignore[attr-defined]
    builtins.clear_status = lambda: setattr(world, "status", None)  # type: ignore[attr-defined]


# autoplay/lib (the infrastructure planner) sits after every tier: it imports their modules, never the reverse.
_LIB_DIRS = _tier_lib_dirs(TEST_TIER) + [os.path.join(REPO_ROOT, "autoplay", "lib")]
for _lib_dir in reversed(_LIB_DIRS):
    if _lib_dir not in sys.path:
        sys.path.insert(0, _lib_dir)

# Module-level singletons (archive.archive, each module's TreeConsole) bind to
# get_component() at import time, so a world must exist before the imports.
_install_builtins(World())
import archive  # noqa: E402
import production  # noqa: E402
import production_core  # noqa: E402
import production_cascade  # noqa: E402
import storage  # noqa: E402
import status_warning  # noqa: E402
import swallow  # noqa: E402
import smelter  # noqa: E402
import fabricator  # noqa: E402
import outpost_mining  # noqa: E402
import logistics_requests  # noqa: E402
import site_supply  # noqa: E402
import site_plan  # noqa: E402
import supply_dock  # noqa: E402
import fluid_routing  # noqa: E402
import fleet_status  # noqa: E402
import tree_console  # noqa: E402
from tree_console import TreeConsole  # noqa: E402

LIB_MODULES = (archive, production, storage, swallow, smelter, fabricator, outpost_mining, logistics_requests, site_supply, site_plan, supply_dock)


def _reset_module_state(world):
    archive.archive.notebook = world.notebook
    swallow._STATE["console"] = None
    tree_console._BUFFER.update({"console": None, "key": None, "lines": [], "chars": 0, "cap": 0})
    tree_console._DEFAULT_CONSOLE["console"] = None
    swallow._LAST.clear()
    swallow._WARNED.clear()
    storage._recent_busy.clear()
    status_warning._ACTIVE.clear()  # one script run per test
    status_warning._SHOWN["status"] = None
    fleet_status._last_published.clear()  # else an identical publish in the next test is skipped
    storage._DISCOVERY.clear()
    storage._RETIRING.clear()
    storage._DISCOVERY.ttl_ticks = 0  # see production_core._DISCOVERY below
    storage._RETIRING.ttl_ticks = 0
    production_cascade._WARNED_UNKNOWN_MANUAL_ITEMS.clear()
    production_core._DISCOVERY.clear()
    production_cascade._RECIPE_INDEX.clear()
    fluid_routing._NETWORK_WALK.clear()
    fluid_routing._POI_WALK.clear()
    fluid_routing._POI_WALK.ttl_ticks = 0  # the stub clock stands still while tests add pumps
    fluid_routing._water_reserve_holds_at.cache_clear()  # keyed on the tick; a fresh world's clock repeats ticks
    production_core._DISCOVERY.ttl_ticks = 0  # the stub clock stands still while tests add buildings; DiscoveryMemoTests turns it on
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
        tree_console.flush_all()
        return self.world.console.text()


HOME_ORDER_REQUESTER = "test_home"
# A small standing segment demand at home, for tests that need some Fabricator
# work to cascade into ingots and ore.
SEGMENT_ORDER = {"gas_pipe_segment": 10, "power_line_segment": 10, "liquid_pipe_segment": 10}


def home_order(items):
    """Standing Fabricator demand consumed at home: an upgrade order under
    HOME_ORDER_REQUESTER, replacing any earlier home_order() call."""
    production.set_upgrade_order(HOME_ORDER_REQUESTER, items)


def disable_ingot_buffer(world):
    """Sets every stub Smelter output's fab-site ingot buffer to 0
    (production.INGOT_STOCK_TARGETS_KEY), for tests of the demand-driven
    ingot flow without the standing buffer."""
    from game_stubs import SMELTER_RECIPES
    world.notebook.set(production.INGOT_STOCK_TARGETS_KEY, {r.output_item: {"target": 0, "need": 0} for r in SMELTER_RECIPES})
