"""Stub tests for Forage held in Crop Automator outputs counting as stock
(production.SourceCache.stock()), so Forage-fed Fabricator recipes such as
Reinforced Biopolymer stay sourceable when no Warehouse holds Forage."""
import unittest
from unittest import mock

from harness import StubTestCase, production


class ForageStockTests(StubTestCase):
    def test_automator_forage_counts_as_stock(self):
        with mock.patch.object(production, "crop_automator_forage_total", lambda outpost=None: 500):
            cache = production.SourceCache()
            self.assertEqual(cache.stock("forage"), 500)
            self.assertTrue(production.can_source_item("forage", cache))
            self.assertEqual(cache.building_stock("forage"), [])

    def test_no_automator_forage_is_not_stock(self):
        with mock.patch.object(production, "crop_automator_forage_total", lambda outpost=None: 0):
            self.assertEqual(production.SourceCache().stock("forage"), 0)


if __name__ == "__main__":
    unittest.main()
