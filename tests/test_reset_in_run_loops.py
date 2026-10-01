"""Every `while True:` at module level or at the top level of a `run*` function in tier 4+ scripts begins
with `reset_all()` (lib/tree_console.py), so an exception that escaped a log block cannot leave later ticks
indented."""
import ast
import glob
import os
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
TIERS = ("4_controlpanel", "5_steampower", "6_seeds", "7_miningdrills", "8_planting", "9_wildlife", os.path.join("..", "autoplay"))


def is_forever(node):
    return isinstance(node, ast.While) and isinstance(node.test, ast.Constant) and node.test.value is True


def first_statement_resets(loop):
    first = loop.body[0]
    return (isinstance(first, ast.Expr) and isinstance(first.value, ast.Call)
            and isinstance(first.value.func, ast.Name) and first.value.func.id == "reset_all")


class ResetInRunLoopsTests(unittest.TestCase):
    def test_run_loops_reset_log_indent_each_tick(self):
        missing = []
        for tier in TIERS:
            for path in sorted(glob.glob(os.path.join(ROOT, tier, "**", "*.py"), recursive=True)):
                if path.endswith("tree_console.py"):
                    continue
                with open(path) as handle:
                    source = handle.read()
                if "tree_console" not in source:
                    continue
                tree = ast.parse(source)
                scopes = [("<module>", tree.body)]
                scopes += [(f"{fn.name}()", fn.body) for fn in ast.walk(tree)
                           if isinstance(fn, ast.FunctionDef) and fn.name.startswith("run")]
                for scope, body in scopes:
                    for node in body:
                        if is_forever(node) and not first_statement_resets(node):
                            missing.append(f"{os.path.relpath(path, ROOT)}:{node.lineno}: {scope}")
        self.assertEqual(missing, [], "\n" + "\n".join(missing))


if __name__ == "__main__":
    unittest.main()
