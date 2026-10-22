"""Shared constants have one owner module; the others import it."""

import ast
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_DIRS = ("scripts", "autoplay")


def _trees():
    for top in SOURCE_DIRS:
        for folder, _, files in os.walk(os.path.join(ROOT, top)):
            for name in files:
                if name.endswith(".py"):
                    path = os.path.join(folder, name)
                    with open(path, encoding="utf-8") as handle:
                        yield name, ast.parse(handle.read(), path)


class ConstantOwnerTests(unittest.TestCase):
    def test_string_literal_owners(self):
        owners = {"survey.unsupported_targets": "unsupported_markers.py"}
        found = {value: set() for value in owners}
        for name, tree in _trees():
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and node.value in found:
                    found[node.value].add(name)
        for value, owner in owners.items():
            self.assertEqual(found[value], {owner}, value)

    def test_assignment_owners(self):
        owners = {"TRANSIENT_UNDEPLOY_STATUSES": "pillar_swap.py"}
        found = {constant: set() for constant in owners}
        for name, tree in _trees():
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id in found:
                            found[target.id].add(name)
        for constant, owner in owners.items():
            self.assertEqual(found[constant], {owner}, constant)


if __name__ == "__main__":
    unittest.main()
