"""vehicle_mining.VehicleMiningMixin.home_ore_demand(): a miner's demand is its home's ore requests."""
import unittest

import harness
import logistics_requests
import mining_reservations
import vehicle_mining


class _Miner(vehicle_mining.VehicleMiningMixin):
    name = "rover_1"

    def __init__(self, world):
        self._world = world
        self.home_outpost = world.home

    def get_current_tick(self):
        return self._world.clock.now


class HomeOreDemandTests(harness.StubTestCase):
    def test_ore_requests_minus_reserved_yield(self):
        w = self.world
        w.add_warehouse("wh_home", w.home, {"iron_ore": 300}, capacity=100000)
        logistics_requests.set_requests(w.home.id, "site_supply", {"iron_ore": (2000, 300, 500), "iron_ingot": (40, 0)}, w.clock.now)
        miner = _Miner(w)
        self.assertEqual(miner.home_ore_demand(), {"iron_ore": 1700})
        mining_reservations.reserve_yield("rover_2", "site_9", "iron_ore", 200, w.clock.now)
        self.assertEqual(miner.home_ore_demand(), {"iron_ore": 1500})

    def test_no_requests_no_demand(self):
        self.assertEqual(_Miner(self.world).home_ore_demand(), {})


if __name__ == "__main__":
    unittest.main()
