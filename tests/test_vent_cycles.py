"""Stub tests for the thermal vent cycle log (lib/vent_cycles.py): phase
lengths timed from flips, error bars on late polls and gaps, Deep-survey
values taking over, pruning of vents gone from the journal."""
import unittest

from harness import StubTestCase
from game_stubs import Site

import vent_cycles


def hold(entry, phase, start, end, step=10.0):
    """Steady polls of an unchanged phase from start to end (as the Automation would, well inside
    MAX_SAME_PHASE_GAP_HOURS)."""
    hours = start
    while hours < end:
        vent_cycles.observe(entry, phase, hours)
        hours += step
    vent_cycles.observe(entry, phase, end)


class ObserveTests(unittest.TestCase):
    def test_full_cycle_records_both_lengths(self):
        entry = {}
        vent_cycles.observe(entry, "active", 0.0)
        vent_cycles.observe(entry, "active", 0.2)
        vent_cycles.observe(entry, "dormant", 0.4)  # flip at 0.3 +- 0.1, start unknown
        self.assertIsNone(entry.get("dormant"))
        hold(entry, "dormant", 0.4, 46.2)
        vent_cycles.observe(entry, "active", 46.4)  # flip at 46.3
        self.assertAlmostEqual(entry["dormant"], 46.0 * 60.0)
        vent_cycles.observe(entry, "dormant", 163.4)  # 117 h gap: flip +- 58.5 h
        self.assertIsNone(entry.get("active"))
        hold(entry, "dormant", 163.4, 209.6)
        vent_cycles.observe(entry, "active", 209.8)  # clean flip, but the dormant start was wide
        self.assertAlmostEqual(entry["dormant"], 46.0 * 60.0)
        hold(entry, "active", 209.8, 326.6)
        vent_cycles.observe(entry, "dormant", 326.8)
        self.assertAlmostEqual(entry["active"], 117.0 * 60.0)

    def test_late_poll_drops_length(self):
        entry = {}
        vent_cycles.observe(entry, "active", 0.0)
        vent_cycles.observe(entry, "dormant", 0.2)
        vent_cycles.observe(entry, "active", 40.0)  # gap 39.8 h: flip +- 19.9 h
        self.assertIsNone(entry.get("dormant"))

    def test_long_gap_in_same_phase_forgets_start(self):
        entry = {}
        vent_cycles.observe(entry, "active", 0.0)
        vent_cycles.observe(entry, "dormant", 0.2)
        vent_cycles.observe(entry, "dormant", 0.2 + vent_cycles.MAX_SAME_PHASE_GAP_HOURS + 1.0)
        self.assertIsNone(entry["since"])

    def test_deep_lengths_not_overwritten(self):
        entry = {"active": 7014, "dormant": 2760, "deep": True}
        vent_cycles.observe(entry, "active", 0.0)
        vent_cycles.observe(entry, "dormant", 0.2)
        vent_cycles.observe(entry, "active", 10.2)
        self.assertEqual(entry["dormant"], 2760)


class PlanTests(unittest.TestCase):
    # The two capped vents of a live save: vent_4 920 t/h 7014/2760 min, vent_1 1023 t/h 7825/2232 min.
    ENTRIES = {
        "vent_4": {"capped": True, "rate": 920, "active": 7014, "dormant": 2760},
        "vent_1": {"capped": True, "rate": 1023, "active": 7825, "dormant": 2232},
        "vent_2": {"capped": False, "rate": 1041, "active": None, "dormant": None},
    }

    def test_known_vents(self):
        plan = vent_cycles.plan_steam(self.ENTRIES, turbines=3, tanks=1)
        # 660 + 796 t/h average = 16.2 turbines; 16 carried, 13 more.
        self.assertEqual((plan["turbines_left"], plan["caps"], plan["estimated"]), (13, 2, False))
        # 3 turbines (270 t/h, split by average share): ~11,100 t over the dormant phases
        # - 2,000 Cap - 300 turbine buffers = ~8,800 t -> 2 tanks, 1 short.
        self.assertEqual(plan["short"], 1)
        # 16 turbines: ~59,300 t - 2,000 - 1,600 = ~55,700 t -> 12 tanks, 11 more.
        self.assertEqual(plan["tanks_left"], 11)
        self.assertEqual(vent_cycles.plan_lines(plan), ("3 (+13)", "1 [1 short!] (+11)", True))

    def test_short_and_estimated(self):
        entries = {"vent_4": {"capped": True, "rate": 920, "active": None, "dormant": None}}
        plan = vent_cycles.plan_steam(entries, turbines=7, tanks=0)
        self.assertTrue(plan["estimated"])
        turbine_line, tank_line, short = vent_cycles.plan_lines(plan)
        self.assertTrue(short)
        self.assertTrue(turbine_line.startswith("7 (+~"))
        self.assertIn("short!]", tank_line)
        self.assertIn("[~", tank_line)

    def test_no_caps(self):
        plan = vent_cycles.plan_steam({}, turbines=2, tanks=1)
        self.assertEqual(vent_cycles.plan_lines(plan), ("2 (no caps)", "1", False))


class StepTests(StubTestCase):
    def setUp(self):
        super().setUp()
        vent_cycles._STATE.update({"vents": None, "sites_tick": None, "entries": None, "polls": 0})
        self.vent = Site("thermal", site_id="vent_4", phase="active", steam_rate=920)
        self.world.services["journal"].surveyed = [self.vent, Site("mineral", site_id="m1")]

    def poll(self, hours, phase):
        self.world.clock.hours = hours
        self.world.clock.now += 50
        self.vent._phase = phase
        vent_cycles.step(self.world.clock.now)

    def test_logs_and_persists(self):
        self.poll(0.0, "active")
        self.poll(0.2, "dormant")
        for hours in range(10, 50, 10):
            self.poll(float(hours), "dormant")
        self.poll(46.2, "dormant")
        self.poll(46.4, "active")
        stored = self.world.notebook.get(vent_cycles.VENT_CYCLES_KEY, {}) or {}
        self.assertEqual(list(stored), ["vent_4"])
        self.assertAlmostEqual(stored["vent_4"]["dormant"], 46.2 * 60.0)
        self.assertEqual(stored["vent_4"]["rate"], 920)
        self.assertEqual(vent_cycles.cycle_minutes("vent_4"), (None, stored["vent_4"]["dormant"]))
        self.assertIn("dormant lasted", self.debug_log())

    def test_deep_survey_values_win(self):
        self.vent._cycle = (7014, 2760)
        self.poll(0.0, "active")
        self.assertEqual(vent_cycles.cycle_minutes("vent_4"), (7014, 2760))

    def test_prunes_vents_gone_from_journal(self):
        self.world.notebook.set(vent_cycles.VENT_CYCLES_KEY, {"vent_9": {"phase": "active"}})
        self.poll(0.0, "active")
        self.assertNotIn("vent_9", self.world.notebook.get(vent_cycles.VENT_CYCLES_KEY))


if __name__ == "__main__":
    unittest.main()
