"""vehicle_mining: ore an outpost requests at need tier beats stock-only ore when a miner picks a site."""
import unittest
from types import SimpleNamespace
from unittest import mock

from game_stubs import Journal
import harness
import logistics_requests
import mining_reservations
import outpost_mining
import vehicle_mining


class _Log:
    def level(self, _name):
        return self

    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


class _MineralSite:
    def __init__(self, site_id, item_id, x, y, purity="standard"):
        self.id = site_id
        self.item_id = item_id
        self.x = x
        self.y = y
        self.hardness = 1.0
        self.purity = purity

    def kind(self):
        return "mineral"


class _Miner(vehicle_mining.VehicleMiningMixin):
    name = "pioneer_1"

    def __init__(self, world, outpost):
        self._world = world
        self.home_outpost = outpost
        self.log = _Log()
        self.vehicle = SimpleNamespace(drill=SimpleNamespace(hardness_limit=lambda: 1.0))
        self.saved = None

    def get_current_tick(self):
        return self._world.clock.now

    def get_unsupported_targets(self):
        return {}

    def get_position(self):
        return (0.0, 0.0)

    def distance_between(self, a, b):
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    def calculate_trip_energy(self, coords, **kwargs):
        return {"is_achievable": True, "total_required_wh": 10.0}

    def claim_target(self, key, cand):
        return True

    def max_mineable_units(self, coords, item_id, purity=None):
        return 20

    def save_mission(self, kind, cand):
        self.saved = cand


class OreTiersTests(unittest.TestCase):
    def test_non_ore_items_dropped(self):
        need, buffer = vehicle_mining.ore_tiers({"iron_ingot": 10, "iron_ore": 5}, {"tar": 5})
        self.assertEqual((need, buffer), ({"iron_ore": 5}, {}))


class StationedNeedTierTests(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        self.outpost = w.add_outpost("outpost_3")
        w.add_warehouse("wh_3", self.outpost, {}, capacity=100000)
        # Silicon is closer and richer; iron is farther.
        w.services["journal"] = Journal([_MineralSite("silver_flats", "silicon", 10, 0, purity="rich"), _MineralSite("rust_hollow", "iron_ore", 90, 0)])
        for patch in (
            mock.patch.object(outpost_mining, "assigned_ores_for", lambda outpost_id: ["iron_ore", "silicon"]),
            mock.patch.object(outpost_mining, "site_assigned_outpost", lambda x, y: "outpost_3"),
            mock.patch.object(outpost_mining, "ore_stock_target", lambda item_id: 500),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def _pick(self):
        miner = _Miner(self.world, self.outpost)
        target, _budget, _diag = miner.select_best_mining_target(miner.build_local_stockpile_candidates("outpost_3"))
        assert target is not None
        return target

    def test_stock_only_picks_richer_closer_site(self):
        self.assertEqual(self._pick()["harvest_item"], "silicon")

    def test_need_tier_ore_beats_stock_ore(self):
        w = self.world
        logistics_requests.set_requests("outpost_3", "site_supply", {"iron_ore": (500, 0, 200)}, w.clock.now)
        target = self._pick()
        self.assertEqual(target["harvest_item"], "iron_ore")
        self.assertEqual(target["tier"], vehicle_mining.TIER_NEED)

    def test_need_covered_by_peer_trip_falls_back_to_stock(self):
        w = self.world
        logistics_requests.set_requests("outpost_3", "site_supply", {"iron_ore": (500, 0, 200)}, w.clock.now)
        mining_reservations.reserve_yield("pioneer_2", "site_rust_hollow", "iron_ore", 200, w.clock.now, outpost_id="outpost_3")
        self.assertEqual(self._pick()["harvest_item"], "silicon")

    def test_reserved_yield_debits_need_first(self):
        w = self.world
        logistics_requests.set_requests("outpost_3", "site_supply", {"iron_ore": (500, 0, 100)}, w.clock.now)
        mining_reservations.reserve_yield("pioneer_2", "site_rust_hollow", "iron_ore", 130, w.clock.now, outpost_id="outpost_3")
        self.assertEqual(logistics_requests.outpost_deficits_tiered(self.outpost, w.clock.now), ({}, {"iron_ore": 370}))
        # The miner's own trip doesn't cover its own deficit.
        self.assertEqual(logistics_requests.outpost_deficits_tiered(self.outpost, w.clock.now, exclude_vehicle="pioneer_2"),
                         ({"iron_ore": 100}, {"iron_ore": 400}))

    def test_hauler_pickup_caps_stockpile_headroom(self):
        w = self.world
        logistics_requests.reserve_pickup("pioneer_13", "outpost_3", "iron_ore", 450, w.clock.now, source_id="outpost_2")
        miner = _Miner(self.world, self.outpost)
        self.assertEqual(miner.stockpile_headroom("outpost_3", "iron_ore"), 50)

    def test_need_above_stock_target_keeps_iron_a_candidate(self):
        w = self.world
        w.add_warehouse("wh_3b", self.outpost, {"iron_ore": 500}, capacity=100000)
        logistics_requests.set_requests("outpost_3", "site_supply", {"iron_ore": (800, 500, 800)}, w.clock.now)
        target = self._pick()
        self.assertEqual(target["harvest_item"], "iron_ore")
        self.assertEqual(target["max_units"], 300)


    def test_dock_ore_need_beats_stock_ore(self):
        w = self.world
        w.notebook.set(outpost_mining.DOCK_ORE_NEED_KEY, {"tick": w.clock.now, "sites": {"outpost_3": {"iron_ore": 150}}})
        target = self._pick()
        self.assertEqual(target["harvest_item"], "iron_ore")
        self.assertEqual(target["tier"], vehicle_mining.TIER_NEED)

    def test_dock_ore_need_netted_by_local_stock(self):
        w = self.world
        w.add_warehouse("wh_3b", self.outpost, {"iron_ore": 150}, capacity=100000)
        w.notebook.set(outpost_mining.DOCK_ORE_NEED_KEY, {"tick": w.clock.now, "sites": {"outpost_3": {"iron_ore": 150}}})
        self.assertEqual(self._pick()["harvest_item"], "silicon")

    def test_stale_dock_ore_need_ignored(self):
        w = self.world
        w.notebook.set(outpost_mining.DOCK_ORE_NEED_KEY, {"tick": w.clock.now - logistics_requests.REQUEST_STALE_TICKS, "sites": {"outpost_3": {"iron_ore": 150}}})
        self.assertEqual(self._pick()["harvest_item"], "silicon")


if __name__ == "__main__":
    unittest.main()
