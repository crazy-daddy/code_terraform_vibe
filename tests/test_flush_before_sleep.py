"""Every statement-level sleep() in tier 4+ scripts is preceded by flush_all(), so buffered debug lines
(lib/tree_console.py) are written out before the script yields."""
import ast
import glob
import os
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
TIERS = ("4_controlpanel", "5_steampower", "6_seeds", "7_miningdrills", "8_planting")
EXEMPT = ("tree_console.py", "swallow.py", "archive.py")


def sleep_statements(tree):
    for node in ast.walk(tree):
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name) and node.value.func.id == "sleep"):
            yield node.lineno


class FlushBeforeSleepTests(unittest.TestCase):
    def test_every_sleep_statement_flushes_first(self):
        missing = []
        for tier in TIERS:
            for path in sorted(glob.glob(os.path.join(ROOT, tier, "**", "*.py"), recursive=True)):
                if path.endswith(EXEMPT):
                    continue
                with open(path) as handle:
                    source = handle.read()
                lines = source.split("\n")
                for lineno in sleep_statements(ast.parse(source)):
                    if lines[lineno - 2].strip() != "flush_all()":
                        missing.append(f"{os.path.relpath(path, ROOT)}:{lineno}")
        self.assertEqual(missing, [], "sleep() without a preceding flush_all():\n" + "\n".join(missing))

    def test_files_that_flush_import_it(self):
        broken = []
        for tier in TIERS:
            for path in sorted(glob.glob(os.path.join(ROOT, tier, "**", "*.py"), recursive=True)):
                if path.endswith(EXEMPT):
                    continue
                with open(path) as handle:
                    source = handle.read()
                if "flush_all()" in source and "import" not in "".join(
                        line for line in source.split("\n") if line.startswith("from tree_console import") and "flush_all" in line):
                    broken.append(os.path.relpath(path, ROOT))
        self.assertEqual(broken, [], "flush_all() used without importing it:\n" + "\n".join(broken))


if __name__ == "__main__":
    unittest.main()
