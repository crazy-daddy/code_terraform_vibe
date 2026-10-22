"""devtools/perf/log_block_timing.py: block pairing, nesting and the --since filter."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "devtools", "perf"))

import log_block_timing as lbt

LOG = """\
[2026-10-02T20:13:18.702Z] [debug] [fabricator_9.py] [tick=100] 03:57:07 ┏━ get_fabricator_active_recipe(fabricator_9)
[2026-10-02T20:13:18.702Z] [debug] [fabricator_9.py] [tick=100] 03:57:07 ┃   ┏━ get_site_fabricator_targets(outpost_5)
[2026-10-02T20:13:18.702Z] [debug] [fabricator_9.py] [tick=100] 04:00:57 ┃   ┗━ END get_site_fabricator_targets(outpost_5)
[2026-10-02T20:13:18.702Z] [debug] [fabricator_9.py] [tick=100] 04:01:55 ┗━ END get_fabricator_active_recipe(fabricator_9)
[2026-10-02T20:13:19.000Z] [output] [fabricator_9.py] [tick=110] ┏━ [fabricator_9] Recipe 'a' -> 'b'
[2026-10-02T20:13:20.000Z] [output] [fabricator_9.py] [tick=112] ┗━ switched
"""

OUTER = ("fabricator", "get_fabricator_active_recipe(fabricator_#)")

# run.mjs console.log: a debug flush is one tagged line plus bare "HH:MM:SS ..." continuations.
# [approve]/[lib-tier] lines carry no script id; the stray clock line after one must not be
# attributed to fabricator_9. A clockless line inside a flush (multi-line text) is skipped and the
# flush goes on.
HEADLESS = """\
[tick 90] [debug] [automation_1] 03:50:00 script census: scripts running: 100 of 300 machines
[tick 120] [debug] [automation_1] 03:55:00 parked
[tick 100] [debug] [fabricator_9] 03:57:07 ┏━ get_fabricator_active_recipe(fabricator_9)
03:57:07 ┃   ┏━ get_site_fabricator_targets(outpost_5)
  wrapped text without a clock
04:00:57 ┃   ┗━ END get_site_fabricator_targets(outpost_5)
04:01:55 ┗━ END get_fabricator_active_recipe(fabricator_9)
[tick 105] [approve] marker marker_3
04:02:00 ┗━ END get_fabricator_active_recipe(fabricator_9)
[tick 106] [lib-tier] tier2: lib/ added
junk without a clock or tag
[tick 110] [output] [fabricator_9] ┏━ [fabricator_9] Recipe 'a' -> 'b'
[tick 112] [output] [fabricator_9] ┗━ switched
"""


class LogBlockTimingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        with open(os.path.join(self.tmp.name, "fabricator_9.log"), "w", encoding="utf-8") as handle:
            handle.write(LOG)
        self.paths = lbt.log_files(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_pairs_nested_and_tick_only_blocks(self):
        stats, unclosed, _windows, _span, _census = lbt.collect(self.paths, 10.0, None)
        self.assertEqual(unclosed, 0)
        self.assertEqual(stats[("fabricator", "get_site_fabricator_targets(outpost_#)")]["seconds"], [230.0])
        self.assertEqual(stats[OUTER]["seconds"], [288.0])
        self.assertEqual(stats[OUTER]["self"], [58.0])
        self.assertEqual(stats[("fabricator", "[fabricator_#] Recipe 'a' -> 'b'")]["seconds"], [20.0])

    def test_census_turns_ticks_into_steps(self):
        with open(os.path.join(self.tmp.name, "automation_1.log"), "w", encoding="utf-8") as handle:
            handle.write(
                "[2026-10-02T20:13:17.000Z] [debug] [automation_1.py] [tick=90] 03:50:00 "
                "script census: scripts running: 100 of 300 machines, allowance 500 steps/tick (+0s)\n"
            )
        stats, _, _, _, census = lbt.collect(lbt.log_files(self.tmp.name), 10.0, None)
        self.assertEqual(census.at(100), 100)
        self.assertIsNone(census.at(89))
        med_n, steps = lbt.step_costs(stats[("fabricator", "get_site_fabricator_targets(outpost_#)")], 10.0, census)
        self.assertEqual(med_n, 100)
        self.assertEqual(steps, [23 * 500])
        self.assertEqual(lbt.allowance(165), 303)
        self.assertEqual(lbt.allowance(20), 1000)

    def test_since_skips_older_lines(self):
        stats, _, _, span, _census = lbt.collect(self.paths, 10.0, None, since="2026-10-02T20:13:19")
        self.assertNotIn(OUTER, stats)
        self.assertEqual(span[0], "2026-10-02T20:13:19.000Z")

    def test_headless_console_lines(self):
        console = os.path.join(self.tmp.name, "console.log")
        with open(console, "w", encoding="utf-8") as handle:
            handle.write(HEADLESS)
        lines = lbt.headless_lines(console)
        self.assertEqual(set(lines), {"automation_1", "fabricator_9"})
        self.assertEqual(len(lines["fabricator_9"]), 6)
        bare = lbt.parse_line(lines["fabricator_9"][2])
        self.assertEqual(
            bare, ("fabricator_9", "debug", 100, 4 * 3600 + 57, 1, "end", "END get_site_fabricator_targets(outpost_5)")
        )
        self.assertEqual(
            lbt.parse_line(lines["fabricator_9"][4]),
            ("fabricator_9", "output", 110, None, 0, "start", "[fabricator_9] Recipe 'a' -> 'b'"),
        )

        paths = {base: [source] for base, source in lines.items()}
        stats, unclosed, windows, _span, census = lbt.collect(paths, 10.0, None)
        self.assertEqual(unclosed, 0)
        self.assertEqual(stats[OUTER]["seconds"], [288.0])
        self.assertEqual(stats[OUTER]["self"], [58.0])
        self.assertEqual(stats[("fabricator", "[fabricator_#] Recipe 'a' -> 'b'")]["seconds"], [20.0])
        self.assertEqual(census.at(100), 100)
        self.assertEqual(windows["fabricator_9"], [100, 112])
        self.assertEqual(lbt.calibration(paths), (10.0, 1))  # automation_1: 300 s over 30 ticks
        self.assertEqual(lbt.headless_iso(10), "2026-01-01T00:00:01.000Z")

        stats, _, _, _, _ = lbt.collect(paths, 10.0, None, since=lbt.headless_iso(110))
        self.assertNotIn(OUTER, stats)
        self.assertIn(("fabricator", "[fabricator_#] Recipe 'a' -> 'b'"), stats)

    def test_headless_path_resolution(self):
        run_dir = os.path.join(self.tmp.name, "out")
        os.makedirs(os.path.join(run_dir, "run"))
        for path in (os.path.join(run_dir, "console.log"), os.path.join(run_dir, "run", "console.log")):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("")
        nested = os.path.join(run_dir, "run", "console.log")
        self.assertEqual(lbt.headless_console(run_dir), nested)
        self.assertEqual(lbt.headless_console(os.path.join(run_dir, "run")), nested)
        self.assertEqual(
            lbt.headless_console(os.path.join(run_dir, "console.log")), os.path.join(run_dir, "console.log")
        )
        with self.assertRaises(SystemExit):
            lbt.headless_console(os.path.join(self.tmp.name, "missing"))


if __name__ == "__main__":
    unittest.main()
