"""Guard: every game service our code requests by a literal id
(`get_component("clock")`) is faked by tests/game_stubs.World, or listed in
KNOWN_GAPS. A new service in scripts/ or autoplay/ fails here until it gets a
shared fake (with contract-test coverage) or a deliberate KNOWN_GAPS entry; a
gap that gains a fake must leave the list.
"""
import ast
import functools
import os
import re
import unittest

from game_stubs import World

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_DIRS = ("scripts", "autoplay")

# Literal machine / outpost ids (battery_1, outpost_home) are not services.
NOT_SERVICE = re.compile(r"_\d+$|^outpost_(?!network$)")

# Services requested by our code with no shared fake yet.
KNOWN_GAPS = {
    "transmitter", "nocturna", "research", "markers", "item_catalog", "atmosphere",
    "thermometer", "plants_sensor", "pressure_sensor", "oxygen_sensor", "biomass_sensor",
}


@functools.cache
def requested_services():
    """{service id: first "path:line" requesting it} over SOURCE_DIRS."""
    found = {}
    for top in SOURCE_DIRS:
        for folder, _, files in os.walk(os.path.join(ROOT, top)):
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(folder, name)
                with open(path, encoding="utf-8") as handle:
                    tree = ast.parse(handle.read(), path)
                for node in ast.walk(tree):
                    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "get_component"):
                        continue
                    arg = node.args[0] if node.args else None
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and not NOT_SERVICE.search(arg.value):
                        found.setdefault(arg.value, f"{os.path.relpath(path, ROOT)}:{node.lineno}")
    return found


class ServiceCoverageTests(unittest.TestCase):
    def test_requested_services_are_faked_or_known_gaps(self):
        world = World()
        services = requested_services()
        missing = sorted(f"{s} ({where})" for s, where in services.items() if world.get_component(s) is None and s not in KNOWN_GAPS)
        self.assertEqual(missing, [], "add a fake to game_stubs.World or list the service in KNOWN_GAPS")

    def test_known_gaps_are_current(self):
        world = World()
        services = requested_services()
        faked = sorted(s for s in KNOWN_GAPS if world.get_component(s) is not None)
        self.assertEqual(faked, [], "these gaps have a fake now: drop them from KNOWN_GAPS")
        unused = sorted(KNOWN_GAPS - set(services))
        self.assertEqual(unused, [], "no code requests these any more: drop them from KNOWN_GAPS")


if __name__ == "__main__":
    unittest.main()
