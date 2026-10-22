"""devtools/simulation/headless/save_scripts.py: slots of removed roles get an empty script."""

import sys
import unittest
from pathlib import Path

SIMULATION = Path(__file__).resolve().parent.parent / "devtools" / "simulation"
if str(SIMULATION) not in sys.path:
    sys.path.insert(0, str(SIMULATION))

from headless import save_scripts  # noqa: E402

FOUNDING_SLOT = (
    "# ct-automation: outpost_planner_automation\n"
    "# Outpost founding planner alone -- an Automation (Computer > Automations).\n"
    "from planner_loop import run_founding\n\n"
    "run_founding()\n"
)


class RetiredRoleTest(unittest.TestCase):
    def test_founding_planner_slot_is_emptied(self):
        # Its old code imports the whole planner chain against the current libs and
        # crashed at load on the step cap in tick_profile runs (save 0839, automation_3).
        body, note = save_scripts.slot_body("automation_3", FOUNDING_SLOT, {})
        self.assertEqual(body, save_scripts.RETIRED_BODY.format(role="outpost_planner_automation"))
        self.assertEqual(note, "retired role outpost_planner_automation")


if __name__ == "__main__":
    unittest.main()
