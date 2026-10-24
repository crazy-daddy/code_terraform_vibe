"""scripts/0_cold_boot/power/solar.py is_tech_unlocked: asks for the given id only, research looked up per call."""

import ast
import os
import unittest

from game_stubs import Research

SOLAR = os.path.join(os.path.dirname(__file__), "..", "scripts", "0_cold_boot", "power", "solar.py")


def _is_tech_unlocked(components, swallowed_log):
    """The script's is_tech_unlocked, compiled alone with a fake get_component and _swallowed."""
    with open(SOLAR, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "is_tech_unlocked")
    ns = {"get_component": components.get, "_swallowed": lambda where, error: swallowed_log.append(where)}
    exec(compile(ast.Module([node], []), SOLAR, "exec"), ns)  # noqa: S102 -- our own script
    return ns["is_tech_unlocked"]


class _AskedResearch(Research):
    """Research that records each id it is asked about."""

    def __init__(self):
        super().__init__()
        self.asked = []

    def is_unlocked(self, research_id):
        self.asked.append(research_id)
        return super().is_unlocked(research_id)


class _RaisingResearch(Research):
    def is_unlocked(self, research_id):
        raise RuntimeError("research offline")


class IsTechUnlockedTests(unittest.TestCase):
    def test_asks_only_for_the_given_id(self):
        research = _AskedResearch()
        research.unlocked.add("computer_unlock")
        check = _is_tech_unlocked({"research": research}, [])
        self.assertFalse(check("research_computer"))
        self.assertEqual(research.asked, ["research_computer"])

    def test_unlocked_id_reads_true(self):
        research = Research()
        research.unlocked.add("research_computer")
        check = _is_tech_unlocked({"research": research}, [])
        self.assertTrue(check("research_computer"))

    def test_research_is_looked_up_per_call(self):
        components = {}
        check = _is_tech_unlocked(components, [])
        self.assertFalse(check("research_computer"))
        research = Research()
        research.unlocked.add("research_computer")
        components["research"] = research
        self.assertTrue(check("research_computer"))

    def test_raise_reads_false_and_is_swallowed(self):
        log = []
        check = _is_tech_unlocked({"research": _RaisingResearch()}, log)
        self.assertFalse(check("research_computer"))
        self.assertEqual(log, ["solar.is_tech_unlocked: research.is_unlocked"])
