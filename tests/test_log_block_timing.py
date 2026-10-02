"""devtools/log_block_timing.py: block pairing, nesting and the --since filter."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "devtools"))

import log_block_timing as lbt  # noqa: E402

LOG = """\
[2026-10-02T20:13:18.702Z] [debug] [fabricator_9.py] [tick=100] 03:57:07 ┏━ get_fabricator_active_recipe(fabricator_9)
[2026-10-02T20:13:18.702Z] [debug] [fabricator_9.py] [tick=100] 03:57:07 ┃   ┏━ get_site_fabricator_targets(outpost_5)
[2026-10-02T20:13:18.702Z] [debug] [fabricator_9.py] [tick=100] 04:00:57 ┃   ┗━ END get_site_fabricator_targets(outpost_5)
[2026-10-02T20:13:18.702Z] [debug] [fabricator_9.py] [tick=100] 04:01:55 ┗━ END get_fabricator_active_recipe(fabricator_9)
[2026-10-02T20:13:19.000Z] [output] [fabricator_9.py] [tick=110] ┏━ [fabricator_9] Recipe 'a' -> 'b'
[2026-10-02T20:13:20.000Z] [output] [fabricator_9.py] [tick=112] ┗━ switched
"""

OUTER = ("fabricator", "get_fabricator_active_recipe(fabricator_#)")


class LogBlockTimingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        with open(os.path.join(self.tmp.name, "fabricator_9.log"), "w", encoding="utf-8") as handle:
            handle.write(LOG)
        self.paths = lbt.log_files(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_pairs_nested_and_tick_only_blocks(self):
        stats, unclosed, _windows, _span = lbt.collect(self.paths, 10.0, None)
        self.assertEqual(unclosed, 0)
        self.assertEqual(stats[("fabricator", "get_site_fabricator_targets(outpost_#)")]["seconds"], [230.0])
        self.assertEqual(stats[OUTER]["seconds"], [288.0])
        self.assertEqual(stats[OUTER]["self"], [58.0])
        self.assertEqual(stats[("fabricator", "[fabricator_#] Recipe 'a' -> 'b'")]["seconds"], [20.0])

    def test_since_skips_older_lines(self):
        stats, _, _, span = lbt.collect(self.paths, 10.0, None, since="2026-10-02T20:13:19")
        self.assertNotIn(OUTER, stats)
        self.assertEqual(span[0], "2026-10-02T20:13:19.000Z")


if __name__ == "__main__":
    unittest.main()
