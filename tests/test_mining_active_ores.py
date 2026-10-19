"""Demand-driven mining (TODO.md C): the active-ore latch, published mining
reach, the ore buffer's slot rule, and a stationed miner built on them."""

import unittest
from types import SimpleNamespace
from unittest import mock

import harness
import logistics_requests
import outpost_mining
import priority
import site_supply
import unsupported_markers
from archive_cleaner import ArchiveCleaner
from game_stubs import Journal
from test_mining_need_tier import _Miner, _MineralSite


class ActiveOreLatchTests(harness.StubTestCase):
    def test_latch_adds_and_never_removes(self):
        self.assertEqual(outpost_mining.active_ores(), set())
        self.assertEqual(outpost_mining.latch_active_ores({"iron_ore"}), ["iron_ore"])
        self.assertEqual(outpost_mining.latch_active_ores({"silicon", "iron_ore"}), ["silicon"])
        self.assertEqual(outpost_mining.latch_active_ores(set()), [])
        self.assertEqual(outpost_mining.active_ores(), {"iron_ore", "silicon"})

    def test_no_write_when_nothing_new(self):
        outpost_mining.latch_active_ores({"iron_ore"})
        with mock.patch.object(harness.archive.archive, "transaction") as transaction:
            outpost_mining.latch_active_ores({"iron_ore"})
        transaction.assert_not_called()

    def test_needed_ores_from_ore_and_ingot_wants(self):
        planned = {
            "outpost_home": {
                "glass": {"levels": [[priority.NEED, 20]], "have": 0},
                "iron_ore": {"levels": [[priority.STOCK, 500]], "have": 0},
            },
            "outpost_2": {"titanium": {"levels": [[priority.ORDER, 50], [priority.STOCK, 500]], "have": 0}},
        }
        self.assertEqual(site_supply.needed_ores(planned), {"silicon", "titanium"})


class MiningReachTests(harness.StubTestCase):
    def test_fresh_entries_aggregate_by_outpost(self):
        now = self.world.clock.now
        outpost_mining.publish_reach("pioneer_1", "outpost_2", {"iron_ore"}, now)
        outpost_mining.publish_reach("pioneer_2", "outpost_2", {"silicon"}, now)
        outpost_mining.publish_reach("pioneer_3", "outpost_4", {"cobalt"}, now - outpost_mining.REACH_STALE_TICKS)
        self.assertEqual(outpost_mining.mineable_ores_by_outpost(now), {"outpost_2": {"iron_ore", "silicon"}})
        self.assertEqual(outpost_mining.mineable_ores("outpost_4", now), set())

    def test_unchanged_reach_not_rewritten_until_refresh(self):
        now = self.world.clock.now
        self.assertTrue(outpost_mining.publish_reach("pioneer_1", "outpost_2", {"iron_ore"}, now))
        self.assertFalse(outpost_mining.publish_reach("pioneer_1", "outpost_2", {"iron_ore"}, now + 1))
        self.assertTrue(
            outpost_mining.publish_reach(
                "pioneer_1", "outpost_2", {"iron_ore"}, now + outpost_mining.REACH_REFRESH_TICKS
            )
        )


class CleanMiningReachTests(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        self.data = self.world.notebook.data
        self.data[outpost_mining.MINING_REACH_KEY] = {
            "pioneer_1": {"outpost": "outpost_2", "ores": ["iron_ore"], "tick": 0},
            "pioneer_gone": {"outpost": "outpost_2", "ores": ["silicon"], "tick": 0},
            "pioneer_junk": 5,
        }

    def test_drops_gone_and_malformed_entries(self):
        ArchiveCleaner(dry_run=False, verbose=False).clean_mining_reach({"pioneer_1", "pioneer_junk"})
        self.assertEqual(list(self.data[outpost_mining.MINING_REACH_KEY]), ["pioneer_1"])

    def test_empty_fleet_query_keeps_entries(self):
        ArchiveCleaner(dry_run=False, verbose=False).clean_mining_reach(set())
        self.assertEqual(sorted(self.data[outpost_mining.MINING_REACH_KEY]), ["pioneer_1", "pioneer_gone"])

    def test_dry_run_writes_nothing(self):
        ArchiveCleaner(dry_run=True, verbose=False).clean_mining_reach({"pioneer_1"})
        self.assertEqual(len(self.data[outpost_mining.MINING_REACH_KEY]), 3)


class _Markers:
    def __init__(self, ids):
        self.ids = set(ids)

    def list(self, prefix=""):
        return [i for i in self.ids if i.startswith(prefix)]

    def clear(self, prefix):
        gone = {i for i in self.ids if i.startswith(prefix)}
        self.ids -= gone
        return SimpleNamespace(status="ok", count=len(gone))


class CleanResourceMarkersTests(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        self.markers = _Markers({"resource.poi_1_1", "resource.poi_2_2", "unsupported.poi_3_3"})
        self.world.components["markers"] = self.markers

    def test_removes_only_resource_markers(self):
        ArchiveCleaner(dry_run=False, verbose=False).clean_resource_markers()
        self.assertEqual(self.markers.ids, {"unsupported.poi_3_3"})

    def test_dry_run_counts_only(self):
        cleaner = ArchiveCleaner(dry_run=True, verbose=False)
        cleaner.clean_resource_markers()
        self.assertEqual(cleaner.stats["resource_markers_removed"], 2)
        self.assertEqual(len(self.markers.ids), 3)

    def test_no_markers_component(self):
        del self.world.components["markers"]
        self.assertEqual(unsupported_markers.clear_resource_markers(), 0)


class OreBufferFitsTests(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        self.outpost = self.world.add_outpost("outpost_2")

    def test_held_slot_or_spare_empty_slot(self):
        self.world.add_storage_bin("bin_1", self.outpost, "silicon", 10)
        self.world.add_storage_bin("bin_2", self.outpost)
        self.assertTrue(outpost_mining.ore_buffer_fits(self.outpost, "silicon"))
        # The last empty slot stays free.
        self.assertFalse(outpost_mining.ore_buffer_fits(self.outpost, "iron_ore"))
        self.world.add_storage_bin("bin_3", self.outpost)
        self.assertTrue(outpost_mining.ore_buffer_fits(self.outpost, "iron_ore"))

    def test_no_store_passes(self):
        self.assertTrue(outpost_mining.ore_buffer_fits(self.outpost, "iron_ore"))


class StationedMinerTests(harness.StubTestCase):
    """Pre-Cartography: no markers, a stationed Pioneer still mines."""

    def setUp(self):
        super().setUp()
        w = self.world
        self.outpost = w.add_outpost("outpost_3")
        w.add_warehouse("wh_3", self.outpost, {}, capacity=100000)
        w.services["journal"] = Journal(
            [
                _MineralSite("rust_hollow", "iron_ore", 90, 0),
                _MineralSite("silver_flats", "silicon", 10, 0),
                # 2 * 600 + 1 Wh > the 1000 Wh battery (_Miner).
                _MineralSite("far_flats", "cobalt", 600, 0),
            ]
        )
        patch = mock.patch.object(outpost_mining, "ore_stock_target", lambda item_id: 500)
        patch.start()
        self.addCleanup(patch.stop)

    def _candidates(self):
        return _Miner(self.world, self.outpost).build_local_stockpile_candidates("outpost_3")

    def test_reach_published_without_far_site(self):
        self._candidates()
        self.assertEqual(outpost_mining.mineable_ores("outpost_3", self.world.clock.now), {"iron_ore", "silicon"})

    def test_reach_checks_one_site_per_ore_and_stops_past_battery(self):
        miner = _Miner(self.world, self.outpost)
        sites = [
            _MineralSite("rust_far", "iron_ore", 300, 0),
            _MineralSite("rust_hollow", "iron_ore", 90, 0),
            _MineralSite("cobalt_beyond", "cobalt", 1200, 0),
        ]
        with mock.patch.object(miner, "full_battery_reaches", wraps=miner.full_battery_reaches) as check:
            self.assertEqual(miner.reach_ores(sites, "outpost_3"), {"iron_ore"})
        # Nearest iron only; cobalt's outbound leg alone (1200 Wh) is past the 1000 Wh battery.
        self.assertEqual([c.args[1] for c in check.call_args_list], [(90, 0)])

    def test_inactive_ore_gets_no_buffer(self):
        self.assertEqual(self._candidates(), [])

    def test_need_latches_ore_then_buffer_stays(self):
        logistics_requests.set_requests(
            "outpost_3", "site_supply", {"iron_ore": (harness.request(500, 200), 0)}, self.world.clock.now
        )
        cands = self._candidates()
        self.assertEqual({c["harvest_item"] for c in cands}, {"iron_ore"})
        self.assertEqual(outpost_mining.active_ores(), {"iron_ore"})
        logistics_requests.set_requests("outpost_3", "site_supply", {}, self.world.clock.now)
        cands = self._candidates()
        self.assertEqual(
            [(c["harvest_item"], c["band"], c["max_units"]) for c in cands], [("iron_ore", priority.STOCK, 500)]
        )


if __name__ == "__main__":
    unittest.main()
