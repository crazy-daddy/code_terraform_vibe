"""vehicle_mining: ore an outpost requests at need tier beats stock-only ore when a miner picks a site."""

import unittest
from types import SimpleNamespace
from unittest import mock

import harness
import logistics_requests
import mining_reservations
import outpost_mining
import priority
import vehicle_energy
import vehicle_mining
from game_stubs import Journal


class _Log:
    def level(self, _name):
        return self

    def run(self, _label, fn, _level=None):
        return fn()

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
        self.vehicle = SimpleNamespace(
            drill=SimpleNamespace(hardness_limit=lambda: 1.0), battery=SimpleNamespace(capacity=lambda: 1000.0)
        )
        self.mission = None

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

    def begin_mission(self, mission, claimed=False):
        self.mission = mission
        return True

    def max_mineable_units(self, coords, item_id, purity=None):
        return 20

    def mine_hours_per_unit(self, item_id, purity=None):
        return vehicle_energy.mine_hours_per_unit_for(self.vehicle, item_id, purity)

    def leg_speed_m_per_hour(self, x, y):
        return 130.0

    # Full-battery reach (full_battery_reaches()): 1 Wh/m both legs, the
    # charging station at the origin, so a site reaches when 2 * d + 1 <= 1000.
    SAFETY_MARGIN_MULTIPLIER = 1.0
    MIN_EMERGENCY_RESERVE_WH = 0.0
    cruise_throttle = 1.0

    def get_nearest_charging_station(self, from_coords=None):
        return (0.0, 0.0), {}

    def wh_per_meter_at_throttle(self, throttle, cargo_units=None):
        return 1.0

    def mine_wh_per_unit(self, item_id, purity=None):
        return 1.0


class OreTiersTests(unittest.TestCase):
    def test_non_ore_items_dropped(self):
        bands = vehicle_mining.ore_bands({priority.NEED: {"iron_ingot": 10, "iron_ore": 5}, priority.STOCK: {"tar": 5}})
        self.assertEqual(bands, {priority.NEED: {"iron_ore": 5}})
        self.assertEqual(vehicle_mining.top_band(bands, "iron_ore"), priority.NEED)
        self.assertEqual(vehicle_mining.sum_bands(bands), {"iron_ore": 5})


class StationedNeedTierTests(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        self.outpost = w.add_outpost("outpost_3")
        w.add_warehouse("wh_3", self.outpost, {}, capacity=100000)
        # Silicon is closer and richer; iron is farther.
        w.services["journal"] = Journal(
            [
                _MineralSite("silver_flats", "silicon", 10, 0, purity="rich"),
                _MineralSite("rust_hollow", "iron_ore", 90, 0),
            ]
        )
        for patch in (
            mock.patch.object(outpost_mining, "active_ores", lambda: {"iron_ore", "silicon"}),
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
        logistics_requests.set_requests(
            "outpost_3", "site_supply", {"iron_ore": (harness.request(500, 200), 0)}, w.clock.now
        )
        target = self._pick()
        self.assertEqual(target["harvest_item"], "iron_ore")
        self.assertEqual(target["band"], priority.NEED)

    def test_need_covered_by_peer_trip_falls_back_to_stock(self):
        w = self.world
        logistics_requests.set_requests(
            "outpost_3", "site_supply", {"iron_ore": (harness.request(500, 200), 0)}, w.clock.now
        )
        mining_reservations.reserve_yield(
            "pioneer_2", "site_rust_hollow", "iron_ore", 200, w.clock.now, outpost_id="outpost_3"
        )
        self.assertEqual(self._pick()["harvest_item"], "silicon")

    def test_reserved_yield_debits_need_first(self):
        w = self.world
        logistics_requests.set_requests(
            "outpost_3", "site_supply", {"iron_ore": (harness.request(500, 100), 0)}, w.clock.now
        )
        mining_reservations.reserve_yield(
            "pioneer_2", "site_rust_hollow", "iron_ore", 130, w.clock.now, outpost_id="outpost_3"
        )
        self.assertEqual(logistics_requests.outpost_deficits_tiered(self.outpost, w.clock.now), ({}, {"iron_ore": 370}))
        # The miner's own trip doesn't cover its own deficit.
        self.assertEqual(
            logistics_requests.outpost_deficits_tiered(self.outpost, w.clock.now, exclude_vehicle="pioneer_2"),
            ({"iron_ore": 100}, {"iron_ore": 400}),
        )

    def test_hauler_pickup_caps_stockpile_headroom(self):
        w = self.world
        logistics_requests.reserve_pickup(
            "pioneer_13", "outpost_3", "iron_ore", 450, w.clock.now, source_id="outpost_2"
        )
        miner = _Miner(self.world, self.outpost)
        self.assertEqual(miner.stockpile_headroom("outpost_3", "iron_ore"), 50)

    def test_need_above_stock_target_keeps_iron_a_candidate(self):
        w = self.world
        w.add_warehouse("wh_3b", self.outpost, {"iron_ore": 500}, capacity=100000)
        logistics_requests.set_requests(
            "outpost_3", "site_supply", {"iron_ore": (harness.request(800, 800), 500)}, w.clock.now
        )
        target = self._pick()
        self.assertEqual(target["harvest_item"], "iron_ore")
        self.assertEqual(target["max_units"], 300)

    def test_dock_ore_need_beats_stock_ore(self):
        w = self.world
        logistics_requests.set_requests(
            "outpost_3", "site_supply", {"iron_ore": ([[priority.ORDER, 150]], 0)}, w.clock.now
        )
        target = self._pick()
        self.assertEqual(target["harvest_item"], "iron_ore")
        self.assertEqual(target["band"], priority.ORDER)

    def test_dock_ore_need_netted_by_local_stock(self):
        w = self.world
        w.add_warehouse("wh_3b", self.outpost, {"iron_ore": 150}, capacity=100000)
        logistics_requests.set_requests(
            "outpost_3", "site_supply", {"iron_ore": ([[priority.ORDER, 150]], 0)}, w.clock.now
        )
        self.assertEqual(self._pick()["harvest_item"], "silicon")

    def test_stale_dock_ore_need_ignored(self):
        w = self.world
        stale = w.clock.now - logistics_requests.REQUEST_STALE_TICKS
        logistics_requests.set_requests("outpost_3", "site_supply", {"iron_ore": ([[priority.ORDER, 150]], 0)}, stale)
        self.assertEqual(self._pick()["harvest_item"], "silicon")


class RemoteOreNeedTests(harness.StubTestCase):
    """2026-10-12: outpost_3 needed rare_earth at 800 but has no rare_earth
    site; outpost_5, which does, mined cobalt at stock band instead."""

    def setUp(self):
        super().setUp()
        w = self.world
        self.outpost = w.add_outpost("outpost_5")
        w.add_outpost("outpost_3")
        w.add_warehouse("wh_5", self.outpost, {}, capacity=100000)
        w.services["journal"] = Journal(
            [
                _MineralSite("indigo_plateau", "cobalt", 10, 0),
                _MineralSite("magnet_rim", "rare_earth", 90, 0),
            ]
        )
        self.reach = {"outpost_5": {"cobalt", "rare_earth"}, "outpost_3": {"iron_ore"}}
        for patch in (
            mock.patch.object(outpost_mining, "active_ores", lambda: {"cobalt", "rare_earth"}),
            mock.patch.object(outpost_mining, "mineable_ores_by_outpost", lambda tick=None: self.reach),
            mock.patch.object(outpost_mining, "ore_stock_target", lambda item_id: 1800),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def _request(self, outpost_id, ore, prio, units):
        logistics_requests.set_requests(outpost_id, "site_supply", {ore: ([[prio, units]], 0)}, self.world.clock.now)

    def _pick(self):
        miner = _Miner(self.world, self.outpost)
        target, _budget, _diag = miner.select_best_mining_target(miner.build_local_stockpile_candidates("outpost_5"))
        assert target is not None
        return miner, target

    def test_stock_only_picks_closer_cobalt(self):
        self.assertEqual(self._pick()[1]["harvest_item"], "cobalt")

    def test_unassigned_remote_need_raises_band_here(self):
        self._request("outpost_3", "rare_earth", priority.MANUAL, 937)
        miner, target = self._pick()
        self.assertEqual(target["harvest_item"], "rare_earth")
        self.assertEqual(target["band"], priority.MANUAL)
        self.assertEqual(miner.stockpile_need("outpost_5"), {"rare_earth": 937})

    def test_remote_need_netted_by_ore_held_here(self):
        self.world.add_warehouse("wh_5b", self.outpost, {"rare_earth": 900}, capacity=100000)
        self._request("outpost_3", "rare_earth", priority.MANUAL, 937)
        miner = _Miner(self.world, self.outpost)
        self.assertEqual(miner.stockpile_need("outpost_5"), {"rare_earth": 37})

    def test_remote_ore_in_reach_there_left_to_its_own_miners(self):
        self.reach["outpost_3"] = {"iron_ore", "rare_earth"}
        self._request("outpost_3", "rare_earth", priority.MANUAL, 500)
        self.assertEqual(_Miner(self.world, self.outpost).stockpile_need("outpost_5"), {})

    def test_remote_stock_band_ignored(self):
        self._request("outpost_3", "rare_earth", priority.STOCK, 937)
        self.assertEqual(self._pick()[1]["harvest_item"], "cobalt")


class StockUrgencyTests(harness.StubTestCase):
    """outpost_1 on 2026-10-10: iron (closest, fastest to dig) kept winning
    while cobalt sat at 81 of 1800, because purity and distance tied every
    stock ore and the nearest won."""

    def setUp(self):
        super().setUp()
        w = self.world
        self.outpost = w.add_outpost("outpost_1")
        w.add_warehouse("wh_1", self.outpost, {"iron_ore": 738, "cobalt": 81, "titanium": 1737}, capacity=100000)
        w.services["journal"] = Journal(
            [
                _MineralSite("black_rim", "iron_ore", 149, 0),
                _MineralSite("cobalt_ridge", "cobalt", 157, 0),
                _MineralSite("copper_ridge", "titanium", 150, 0),
            ]
        )
        for patch in (
            mock.patch.object(outpost_mining, "active_ores", lambda: {"iron_ore", "cobalt", "titanium"}),
            mock.patch.object(outpost_mining, "ore_stock_target", lambda item_id: 1800),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def _ranked(self):
        miner = _Miner(self.world, self.outpost)
        target, _budget, _diag = miner.select_best_mining_target(miner.build_local_stockpile_candidates("outpost_1"))
        if target is not None:
            assert (
                miner.mission is not None
                and miner.mission.target is target
                and miner.mission.target_key == target["key"]
            )
            assert miner.mission.kind == "mine" and miner.mission.reserved_yield
        return miner, target

    def test_emptiest_ore_beats_faster_ore(self):
        _miner, target = self._ranked()
        assert target is not None
        self.assertEqual(target["harvest_item"], "cobalt")

    def test_faster_ore_wins_at_equal_fill(self):
        self.world.add_warehouse("wh_1b", self.outpost, {"cobalt": 657}, capacity=100000)
        _miner, target = self._ranked()
        assert target is not None
        self.assertEqual(target["harvest_item"], "iron_ore")

    def test_richer_site_cuts_hours_per_unit(self):
        miner = _Miner(self.world, self.outpost)
        std = {"type": "mine", "coords": (150, 0), "harvest_item": "cobalt", "purity": "standard"}
        rich = dict(std, purity="rich")
        rich_hours = miner.mining_hours_per_unit(rich, (0, 0))
        std_hours = miner.mining_hours_per_unit(std, (0, 0))
        assert rich_hours is not None and std_hours is not None
        self.assertLess(rich_hours, std_hours)


if __name__ == "__main__":
    unittest.main()
