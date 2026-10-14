"""Stub tests for Supply Dock load sizing (lib/supply_dock.py load_chunk())."""

import unittest

from harness import supply_dock

CHUNK = supply_dock.SUPPLY_DOCK_LOAD_CHUNK_SIZE


class LoadChunkTests(unittest.TestCase):
    def test_covers_dispatch_until_next_step(self):
        # Bulk Logistics III (400 u/h), 0.4 h step gap, lookahead 2 -> 320 units.
        self.assertEqual(supply_dock.load_chunk(400.0, 0.4, 0, 15000), 320)

    def test_cargo_in_dock_counts_against_the_window(self):
        self.assertEqual(supply_dock.load_chunk(400.0, 0.4, 300, 15000), 20)

    def test_never_below_the_chunk(self):
        self.assertEqual(supply_dock.load_chunk(25.0, 0.1, 50, 15000), CHUNK)

    def test_unmeasured_gap_uses_the_default(self):
        expected = round(100.0 * supply_dock.SUPPLY_DOCK_DEFAULT_GAP_HOURS * supply_dock.SUPPLY_DOCK_LOAD_LOOKAHEAD)
        self.assertEqual(supply_dock.load_chunk(100.0, None, 0, 15000), expected)

    def test_long_gap_is_clamped(self):
        expected = round(100.0 * supply_dock.SUPPLY_DOCK_MAX_GAP_HOURS * supply_dock.SUPPLY_DOCK_LOAD_LOOKAHEAD)
        self.assertEqual(supply_dock.load_chunk(100.0, 50.0, 0, 15000), expected)

    def test_short_stock_is_split_among_sibling_docks(self):
        self.assertEqual(supply_dock.load_chunk(400.0, 0.4, 0, 300, siblings=3), 100)

    def test_never_more_than_available(self):
        self.assertEqual(supply_dock.load_chunk(400.0, 0.4, 0, 4), 4)
        self.assertEqual(supply_dock.load_chunk(400.0, 0.4, 0, 0), 0)


if __name__ == "__main__":
    unittest.main()
