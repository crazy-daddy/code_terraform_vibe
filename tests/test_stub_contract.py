"""Contract test: tests/game_stubs.py against the real game API in
tests/game_spec.json (devtools/extract_game_spec.py).

Each stub class maps to the spec components (`api`) or object types
(`types`) it fakes. For every public method: it exists in a mapped entry,
its parameter names match the real ones by position, and every literal
status in a `Result("...")` it returns is one of the real method's
outcomes. Value types (stacks, recipes, orders, ...) also check their
public attributes. Test-only helpers (leading `_`, or listed in
TEST_HELPERS / TEST_STATE) are exempt.
"""
import ast
import inspect
import json
import os
import textwrap
import unittest

import game_stubs

SPEC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "game_spec.json")

# stub class -> spec entries ("api.<component>" or "types.<Type>") it fakes.
COMPONENTS = {
    "Store": ["api.warehouse", "api.inventory"],
    "Smelter": ["api.smelter"],
    "Fabricator": ["api.fabricator"],
    "SupplyDock": ["api.supply_dock"],
    "Orders": ["api.orders"],
    "Notebook": ["api.notebook"],
    "Clock": ["api.clock"],
    "Commander": ["api.commander"],
    "Shop": ["api.shop"],
    "Console": ["api.console"],
    "OutpostNetwork": ["api.outpost_network"],
    "Journal": ["api.journal"],
    "ConstructionBlueprints": ["api.construction_blueprint"],
    "Slot": ["types.InputSlot", "types.OutputSlot"],
    "OutpostRef": ["types.OutpostRef"],
}
VALUE_TYPES = {
    "Result": ["types.ActionResult", "types.TransferResult"],
    "Stack": ["types.ItemStack"],
    "Recipe": ["types.Recipe"],
    "BuildingRef": ["types.BuildingRef"],
    "OutpostRef": ["types.OutpostRef"],
    "Order": ["types.Order"],
    "DockSlot": ["types.DockSlot"],
    "ShopItem": ["types.ShopItem"],
    "Construction": ["types.Construction"],
}
# Base classes and the world itself: checked through their subclasses, or not API.
NOT_API = {"World", "Building", "Machine"}
# Public test-only methods per stub class.
TEST_HELPERS = {
    "Store": {"add", "remove"},
    "Console": {"text"},
}
# Public test-only attributes per value type.
TEST_STATE = {}


def _load_spec():
    with open(SPEC_PATH, encoding="utf-8") as f:
        return json.load(f)


def _entries(spec, refs):
    return [(ref, spec[ref.split(".", 1)[0]][ref.split(".", 1)[1]]) for ref in refs]


def _stub_classes():
    return {name: cls for name, cls in vars(game_stubs).items() if inspect.isclass(cls) and cls.__module__ == game_stubs.__name__}


def _public_methods(cls):
    """{name: function} for public methods on cls and its stub bases."""
    methods = {}
    for klass in reversed(cls.__mro__):
        if klass is object:
            continue
        for name, value in vars(klass).items():
            if inspect.isfunction(value) and not name.startswith("_"):
                methods[name] = value
    return methods


def _param_names(func):
    """Positional parameter names after self, without *args/**kwargs."""
    params = list(inspect.signature(func).parameters.values())[1:]
    return [p.name for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]


def _result_statuses(func):
    """Literal statuses in `Result(...)` calls' first argument (string
    constants, including both branches of a conditional expression)."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    statuses = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Result":
            status = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "status"), None)
            if status is None:
                statuses.add("ok")  # Result()'s default status
                continue
            for sub in ast.walk(status):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    statuses.add(sub.value)
    return statuses


def _init_attributes(cls):
    """Public `self.<name> = ...` targets in cls.__init__."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(cls.__init__)))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store) and isinstance(node.value, ast.Name) and node.value.id == "self":
            if not node.attr.startswith("_"):
                names.add(node.attr)
    return names


class StubContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = _load_spec()

    def test_every_stub_class_is_mapped(self):
        unmapped = sorted(set(_stub_classes()) - set(COMPONENTS) - set(VALUE_TYPES) - NOT_API)
        self.assertEqual(unmapped, [], "map each new stub class in COMPONENTS / VALUE_TYPES (or NOT_API)")

    def test_mapped_entries_exist(self):
        for refs in list(COMPONENTS.values()) + list(VALUE_TYPES.values()):
            for ref in refs:
                section, name = ref.split(".", 1)
                self.assertIn(name, self.spec[section], ref)

    def test_methods_params_and_statuses(self):
        problems = []
        classes = _stub_classes()
        for class_name, refs in COMPONENTS.items():
            entries = _entries(self.spec, refs)
            helpers = TEST_HELPERS.get(class_name, set())
            for method_name, func in sorted(_public_methods(classes[class_name]).items()):
                if method_name in helpers:
                    continue
                where = f"{class_name}.{method_name}"
                matches = [(ref, entry[method_name]) for ref, entry in entries if method_name in entry]
                if not matches:
                    problems.append(f"{where}: no such method in {refs}")
                    continue
                methods = [(ref, m) for ref, m in matches if not m.get("property")]
                if not methods:
                    problems.append(f"{where}: a property in the game, not a method")
                    continue
                params = _param_names(func)
                if not any(params == [p["name"] for p in m.get("params", [])][: len(params)] for _ref, m in methods):
                    real = {ref: [p["name"] for p in m.get("params", [])] for ref, m in methods}
                    problems.append(f"{where}{tuple(params)}: real parameters are {real}")
                statuses = _result_statuses(func)
                outcomes = set()
                for _ref, m in methods:
                    outcomes.update(m.get("outcomes") or [])
                if statuses and not outcomes:
                    problems.append(f"{where}: returns Result {sorted(statuses)} but the game method has no outcome contract")
                elif statuses - outcomes:
                    problems.append(f"{where}: statuses {sorted(statuses - outcomes)} not in {sorted(outcomes)}")
        self.assertEqual(problems, [], "\n" + "\n".join(problems))

    def test_value_type_attributes(self):
        problems = []
        classes = _stub_classes()
        for class_name, refs in VALUE_TYPES.items():
            fields = set()
            for _ref, entry in _entries(self.spec, refs):
                fields.update(entry)
            extra = _init_attributes(classes[class_name]) - fields - TEST_STATE.get(class_name, set())
            if extra:
                problems.append(f"{class_name}: attributes {sorted(extra)} not in {refs}")
        self.assertEqual(problems, [], "\n" + "\n".join(problems))

    def test_status_collector_sees_literals(self):
        statuses = _result_statuses(game_stubs.Slot.take)
        self.assertTrue({"no_connection", "buffer_full", "ok", "partial", "source_empty"} <= statuses, statuses)


if __name__ == "__main__":
    unittest.main()
