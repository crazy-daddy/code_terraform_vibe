"""vehicle_mining stationed mining at an outpost without its own Charging
Station: no top-off trip before launch (the transfer back spends what it
gained), a recharge only when a full battery brings an out-of-range site
into reach."""
import unittest

import harness
import vehicle_mining
from game_stubs import Cargo
from tree_console import TreeConsole


class _Vehicle:
    def __init__(self):
        self.cargo = Cargo(100, {})


class _Miner(vehicle_mining.VehicleMiningMixin):
    name = "pioneer_5"
    assigned_slot_coords = (170.0, 80.0)
    cruise_throttle = 0.5
    current_target_key = None
    current_target = None
    stockpile_empty_reason = "no ore assigned to this outpost"

    def __init__(self, charger, curr_wh, cheapest_wh=None):
        self.home_charging_station = object() if charger else None
        self.vehicle = _Vehicle()
        self.log = TreeConsole()
        self.curr_wh = curr_wh
        self.cheapest_wh = cheapest_wh
        self.recharges = 0

    def is_at_base(self, threshold=3.0):
        return True

    def get_battery(self):
        return self.curr_wh, 200.0, self.curr_wh / 200.0

    def recharge_at_station(self, target_level=1.0, station_coords=None, station_id=None):
        self.recharges += 1
        return True

    def get_nearest_charging_station(self, from_coords=None):
        return (0.0, 0.0), {"id": "charging_station_1"}

    def distance_between(self, a, b):
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    def energy_wh_for_leg(self, distance_m, throttle, cargo_units=None):
        return distance_m * 0.15

    def publish_telemetry(self, *_args):
        pass

    def build_local_stockpile_candidates(self, outpost_id):
        return [{"key": "site"}] if self.cheapest_wh is not None else []

    def select_best_mining_target(self, candidates):
        cheapest = None
        if self.cheapest_wh is not None:
            cheapest = {"total_required_wh": self.cheapest_wh, "current_wh": self.curr_wh,
                        "dist_inbound": 0.0, "nearest_cs_coords": (0.0, 0.0)}
        return None, None, {"candidate_count": len(candidates), "budget_candidates": 0,
                            "claims_lost": 0, "cheapest_rejected": cheapest}


class StationedRechargeTests(harness.StubTestCase):
    def test_no_charger_skips_top_off(self):
        miner = _Miner(charger=False, curr_wh=174.0)
        miner._stationed_mining_cycle("outpost_1")
        self.assertEqual(miner.recharges, 0)

    def test_local_charger_tops_off(self):
        miner = _Miner(charger=True, curr_wh=174.0)
        miner._stationed_mining_cycle("outpost_1")
        self.assertEqual(miner.recharges, 1)

    def test_no_charger_recharges_when_full_battery_reaches_site(self):
        miner = _Miner(charger=False, curr_wh=60.0, cheapest_wh=100.0)
        miner._stationed_mining_cycle("outpost_1")
        self.assertEqual(miner.recharges, 1)

    def test_no_charger_stands_by_when_transfer_eats_the_gain(self):
        # 188 m transfer at 0.15 Wh/m costs ~28 Wh: 200 - 28 < 190.
        miner = _Miner(charger=False, curr_wh=174.0, cheapest_wh=190.0)
        miner._stationed_mining_cycle("outpost_1")
        self.assertEqual(miner.recharges, 0)


if __name__ == "__main__":
    unittest.main()
