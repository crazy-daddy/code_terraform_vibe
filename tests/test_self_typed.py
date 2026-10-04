"""
Every game script that uses the injected `self` binds it to a typed name.

The game injects `self` (the machine a script runs on) as a global. Pyright
only knows its type through `from user_stubs import <name> as self` under
`if TYPE_CHECKING:`; devtools/self_typing.py adds that import and
scripts_sync.py generates the typed-`self` block of the save's user_stubs.py from the game's language server and
stubs. See docs/cheatsheet/dev_workflow.md.
"""
import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "devtools"))

import self_typing  # noqa: E402

SERVER_FRAGMENT = (
    '{id:qs,building:!0,nameKey:"machines.oxygen_generator.name",scriptPrefix:"o2gen"},'
    '{id:Jr,building:!0,nameKey:"machines.temp_heater.name",scriptPrefix:"heater"},'
    '{id:"drone_small",nameKey:"machines.drone_small.name",scriptPrefix:"drone"},'
    '{id:"drone_large",nameKey:"machines.drone_large.name",scriptPrefix:"drone"},'
    '{id:"mystery",nameKey:"machines.mystery_box.name",scriptPrefix:"mystery"},'
    '"machines.temp_heater.name":"Space Heater"'
)
BUILTINS_FRAGMENT = '''
class OxygenGenerator(Component):
    """Oxygen Generator: Draws CO2."""

class Heater(Component):
    """Space Heater: Warms the air."""

class DroneSmall(Component):
    """Small Drone: Flies."""

class DroneLarge(Component):
    """Large Drone: Flies far."""

class ColdBootContract(Contract):
    """self.contract (cold_boot)"""
'''


class SelfTypesGenerationTests(unittest.TestCase):
    def setUp(self):
        self.stub, self.unresolved = self_typing.build_self_types(SERVER_FRAGMENT, BUILTINS_FRAGMENT)

    def test_type_id_resolves_by_pascal_case(self):
        self.assertIn("o2gen: OxygenGenerator", self.stub)

    def test_names_are_bound_not_just_annotated(self):
        """The game's language server only exports names the module binds."""
        self.assertIn("o2gen: OxygenGenerator = ...\n", self.stub)

    def test_type_id_falls_back_to_display_name(self):
        self.assertIn("heater: Heater", self.stub)

    def test_prefix_on_several_types_is_a_union(self):
        self.assertIn("drone: DroneSmall | DroneLarge", self.stub)

    def test_unresolved_prefix_is_reported_not_emitted(self):
        self.assertEqual(self.unresolved, ["mystery"])
        self.assertNotIn("mystery:", self.stub)

    def test_contract_gets_its_own_script_class(self):
        self.assertIn("class _ColdBootContractScript(ContractScript):\n    contract: ColdBootContract", self.stub)
        self.assertIn("cold_boot: _ColdBootContractScript", self.stub)

    def test_overrides_are_emitted(self):
        for name, expr in self_typing.SELF_TYPE_OVERRIDES.items():
            self.assertIn("%s: %s" % (name, expr), self.stub)

    def test_component_export_only_when_defined(self):
        import_line = self.stub.splitlines()[1]
        self.assertNotIn("BatteryComponent", import_line)
        stub, _ = self_typing.build_self_types(
            SERVER_FRAGMENT, BUILTINS_FRAGMENT + '\nclass BatteryComponent(Component):\n    """Battery: Stores."""\n')
        self.assertIn("BatteryComponent", stub.splitlines()[1])

    def test_stub_is_valid_python(self):
        ast.parse(self.stub)

    def test_block_is_marked(self):
        self.assertTrue(self.stub.startswith(self_typing.BLOCK_BEGIN))
        self.assertTrue(self.stub.rstrip("\n").endswith(self_typing.BLOCK_END))


class MergeBlockTests(unittest.TestCase):
    BLOCK = "%s\nx: int\n%s\n" % (self_typing.BLOCK_BEGIN, self_typing.BLOCK_END)

    def test_appended_after_player_text(self):
        merged = self_typing.merge_block("# mine\nAlias = int\n", self.BLOCK)
        self.assertEqual(merged, "# mine\nAlias = int\n\n" + self.BLOCK)

    def test_replaces_only_the_block(self):
        old = "# mine\n\n%s\nold: str\n%s\nAfter = int\n" % (self_typing.BLOCK_BEGIN, self_typing.BLOCK_END)
        merged = self_typing.merge_block(old, self.BLOCK)
        self.assertEqual(merged, "# mine\n\n" + self.BLOCK + "After = int\n")

    def test_merging_twice_is_stable(self):
        once = self_typing.merge_block("# mine\n", self.BLOCK)
        self.assertEqual(self_typing.merge_block(once, self.BLOCK), once)


class AddDeclarationTests(unittest.TestCase):
    def test_inserted_after_header_comments(self):
        text = "# header\n# more\n\nx = self.get()\n"
        result = self_typing.add_declaration(text, "o2gen")
        self.assertEqual(
            result,
            "# header\n# more\n\nfrom typing import TYPE_CHECKING\nif TYPE_CHECKING:\n"
            "    from user_stubs import o2gen as self\n\nx = self.get()\n",
        )

    def test_keeps_crlf_line_endings(self):
        result = self_typing.add_declaration("# header\r\nx = self.get()\r\n", "o2gen")
        self.assertNotIn("\n", result.replace("\r\n", ""))

    def test_reuses_existing_type_checking_import(self):
        text = "from typing import TYPE_CHECKING\nx = self.get()\n"
        result = self_typing.add_declaration(text, "o2gen")
        self.assertEqual(result.count("import TYPE_CHECKING"), 1)
        self.assertEqual(self_typing.declared_self_type(ast.parse(result)), "o2gen")


class ScriptsDeclareSelfTests(unittest.TestCase):
    def test_every_script_using_self_declares_its_type(self):
        missing, wrong = [], []
        for path in self_typing.script_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            if not self_typing.uses_global_self(tree):
                continue
            declared = self_typing.declared_self_type(tree)
            relative = path.relative_to(self_typing.REPO)
            if declared is None:
                missing.append(str(relative))
            elif declared != self_typing.self_type_name(path):
                wrong.append("%s: %s, expected %s" % (relative, declared, self_typing.self_type_name(path)))
        self.assertEqual(missing, [], "run `python devtools/self_typing.py apply`")
        self.assertEqual(wrong, [])

    def test_every_declared_name_is_a_game_script_kind(self):
        """A script stem the game never uses as a slot prefix (say
        `mining_drill_industrial.py` for `mining_drill_ind_N` slots) is never
        paired by scripts_sync. Checked against the resolved user_stubs.py,
        so skipped where no save has been resolved."""
        generated = self_typing.REPO / ".pyright-resolved" / "stubs" / (self_typing.STUB_MODULE + ".py")
        if not generated.is_file():
            self.skipTest("no resolved user_stubs.py; run scripts_sync.py resolve-preview")
        known = {node.target.id for node in ast.parse(generated.read_text(encoding="utf-8")).body
                 if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)}
        unknown = []
        for path in self_typing.script_files():
            declared = self_typing.declared_self_type(ast.parse(path.read_text(encoding="utf-8")))
            if declared is not None and declared not in known:
                unknown.append("%s: %s" % (path.relative_to(self_typing.REPO), declared))
        self.assertEqual(unknown, [])

    def test_method_self_is_not_a_global_use(self):
        tree = ast.parse("class A:\n    def f(self):\n        return self.x\n")
        self.assertFalse(self_typing.uses_global_self(tree))


if __name__ == "__main__":
    unittest.main()
