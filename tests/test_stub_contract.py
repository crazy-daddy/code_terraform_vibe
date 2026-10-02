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
    "Store": ["api.warehouse", "api.inventory", "api.passive_storage"],
    "LeadCask": ["api.lead_cask", "api.passive_storage"],
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
    "FluidPort": ["types.FluidPort"],
    "Tank": ["api.gas_tank", "api.liquid_tank"],
    "BatteryBank": ["api.battery"],
    "SteamTurbine": ["api.steam_turbine"],
    "PowerControl": ["api.power_control"],
    "RunControl": ["api.run_control"],
    "Comms": ["api.comms"],
    "Fleet": ["api.fleet"],
    "Computer": ["api.computer"],
    "Drone": ["api.drone"],
    "Pioneer": ["api.pioneer"],
    "Cargo": ["types.Cargo", "types.DroneCargo"],
    "VehicleBattery": ["types.Battery"],
    "DroneBattery": ["types.DroneBattery"],
    "DroneDepot": ["api.drone_station"],
    "Habitat": ["api.habitat"],
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
    "Position": ["types.Position"],
    "PowerGrid": ["types.PowerGrid"],
    "PowerGridMember": ["types.PowerGridMember"],
    "PowerSummary": ["types.PowerSummary"],
    "BroadcastInfo": ["types.BroadcastInfo"],
    "CommsMessage": ["types.CommsMessage"],
    "UnitRef": ["types.DroneRef", "types.VehicleRef", "types.MobileUnitRef"],
    "MountSlot": ["types.MountSlot"],
    "HabitatBonusNode": ["types.HabitatBonusNode"],
    "HabitatBonusTree": ["types.HabitatBonusTree"],
    "HabitatInsight": ["types.HabitatInsight"],
}
# Base classes and the world itself: checked through their subclasses, or not API.
NOT_API = {"World", "Building", "Machine", "MobileUnit", "PassiveStore"}
# Public test-only methods per stub class.
TEST_HELPERS = {
    "Store": {"add", "remove"},
    "LeadCask": {"add", "remove"},
    "Console": {"text"},
    "Comms": {"publish"},
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


class SharedFakeTests(unittest.TestCase):
    """The new fakes take their defaults from the spec and see each other."""

    def setUp(self):
        self.world = game_stubs.World()

    def test_spec_defaults(self):
        w = self.world
        self.assertEqual(w.add_battery("battery_1", w.home).get_capacity(), 500)
        self.assertEqual(w.add_tank("gas_tank_1", w.home, type_id="gas_tank").capacity(), 5000)
        self.assertEqual(w.add_drone_depot("drone_station_1", w.home).bay_count(), 1)
        recipe = game_stubs.spec_recipe("smelt_iron_ingot")
        assert recipe is not None
        self.assertEqual(recipe.duration_game_hours, 0.08)
        self.assertIn("smelt_iron_ingot", [r.id for r in game_stubs.spec_recipes("smelter")])

    def test_grid_members_and_power_switches(self):
        w = self.world
        w.add_battery("battery_1", w.home, charge=200.0)
        w.add_smelter("smelter_1", w.home)
        grid = w.add_grid("grid_a", ["battery_1", "smelter_1"], consumed=10.0, generated=4.0)
        power = w.power_control
        self.assertEqual((grid.stored, grid.capacity, grid.net), (200.0, 500, -6.0))
        self.assertEqual(power.set_powered("battery_1", False).status, "not_toggleable")
        self.assertEqual(power.set_powered("smelter_1", False).status, "ok")
        self.assertEqual([m.powered for m in grid.members], [True, False])
        self.assertIs(power.grid("smelter_1"), grid)

    def test_deploy_and_fleet_refs(self):
        w = self.world
        computer, fleet = w.computer, w.fleet
        self.assertEqual(computer.deploy("drone_small").status, "no_kit")
        w.inventory.add("drone_small", 1)
        result = computer.deploy("drone_small")
        self.assertEqual((result.status, result.machine_id), ("ok", "drone_1"))
        self.assertEqual([(r.id, r.kind, r.category) for r in fleet.drones()], [("drone_1", "drone_small", "drone")])
        self.assertEqual(w.home.buildings(), [])
        self.assertEqual(w.run_control.start("drone_1").status, "ok")
        self.assertEqual(computer.undeploy("drone_1").status, "ok")
        self.assertEqual(w.inventory.count("drone_small"), 1)

    def test_comms_broadcast_and_queue(self):
        comms = self.world.comms
        comms.publish("power.orders", {"tier": 2}, age_seconds=30.0)
        info = comms.latest_info("power.orders")
        assert info is not None
        self.assertEqual((info.value, info.age_seconds), ({"tier": 2}, 30.0))
        message_id = comms.send("jobs", "a").message_id
        self.assertEqual(comms.receive("jobs").packet.id, message_id)
        self.assertEqual(comms.receive("jobs").status, "empty")

    def test_lead_cask_transfers(self):
        w = self.world
        cask = w.add_lead_cask("lead_cask_1", w.home, "raw_uranium", 10)
        other = w.add_lead_cask("lead_cask_2", w.home, "fuel_rod", 1)
        w.add_warehouse("warehouse_1", w.home, {"iron_ore": 5})
        self.assertEqual(cask.capacity(), 100)
        self.assertEqual(cask.transfer_to("warehouse_1", "raw_uranium", 4).status, "hot_cargo_requires_cask")
        self.assertEqual(w.components["warehouse_1"].transfer_to("lead_cask_1", "iron_ore", 1).status, "cask_accepts_hot_only")
        self.assertEqual(cask.transfer_to("lead_cask_2", "raw_uranium", 4).status, "target_wrong_material")
        other.remove("fuel_rod", 1)
        result = cask.transfer_to("lead_cask_2", "raw_uranium", 4)
        self.assertEqual((result.status, result.moved, other.material()), ("ok", 4, "raw_uranium"))
        self.assertEqual(cask.count("raw_uranium"), 6)


if __name__ == "__main__":
    unittest.main()
