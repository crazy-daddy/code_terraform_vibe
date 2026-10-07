"""Tests for lib/pioneer_split.py (holder/rack split math) and PioneerUpgradeMixin._rebalance_container_split()."""
import unittest

from harness import StubTestCase
from game_stubs import Journal, MountSlot, Site
import pioneer_split
import pioneer_upgrade
import vehicle_energy
from tree_console import TreeConsole


SAFETY = 1.05
RESERVE = 8.0


class UnitsPerTripTests(unittest.TestCase):
    def test_battery_bound(self):
        # 2 x 50 Wh, 40 Wh drive, 5 Wh/unit: (100 - 8) / 1.05 - 40 = 47.6 Wh -> 9 units
        self.assertEqual(pioneer_split.units_per_trip(2, 4, 50, 100, 40, 5.0, SAFETY, RESERVE), 9)

    def test_cargo_bound(self):
        self.assertEqual(pioneer_split.units_per_trip(10, 1, 300, 20, 40, 1.0, SAFETY, RESERVE), 20)

    def test_drive_eats_battery(self):
        self.assertEqual(pioneer_split.units_per_trip(1, 1, 50, 100, 60, 1.0, SAFETY, RESERVE), 0)


class BestHolderCountTests(unittest.TestCase):
    def test_small_holders_want_battery(self):
        # 50 Wh holders vs 100-unit racks, Industrial on iron (3.75 Wh/unit)
        self.assertEqual(pioneer_split.best_holder_count(6, 50, 100, [(32.0, 3.8)], SAFETY, RESERVE), 5)

    def test_large_tiers_balance(self):
        # 300 Wh holders vs 150-unit racks: 4 holders carry ~290 units, 3 only ~200
        self.assertEqual(pioneer_split.best_holder_count(6, 300, 150, [(54.0, 3.8)], SAFETY, RESERVE), 4)

    def test_rich_site_wants_cargo(self):
        self.assertEqual(pioneer_split.best_holder_count(6, 300, 150, [(20.0, 0.8)], SAFETY, RESERVE), 2)

    def test_far_site_shifts_toward_battery(self):
        near = pioneer_split.best_holder_count(6, 300, 150, [(20.0, 2.5)], SAFETY, RESERVE)
        far = pioneer_split.best_holder_count(6, 300, 150, [(600.0, 2.5)], SAFETY, RESERVE)
        self.assertEqual((near, far), (3, 4))

    def test_far_site_outweighs_cheap_near_one(self):
        # A near rich site alone wants racks; drive overhead per unit at the far site dominates the mix.
        mix = [(5.0, 0.8), (60.0, 5.0)]
        self.assertEqual(pioneer_split.best_holder_count(6, 50, 100, mix, SAFETY, RESERVE), 5)

    def test_unreachable_site_counts_first(self):
        # Only 5 holders (250 Wh) reach a 200 Wh round trip.
        self.assertEqual(pioneer_split.best_holder_count(6, 50, 100, [(200.0, 1.0)], SAFETY, RESERVE), 5)

    def test_no_sites_or_slots(self):
        self.assertIsNone(pioneer_split.best_holder_count(6, 300, 150, [], SAFETY, RESERVE))
        self.assertIsNone(pioneer_split.best_holder_count(1, 300, 150, [(20.0, 2.5)], SAFETY, RESERVE))
        self.assertIsNone(pioneer_split.best_holder_count(6, 50, 100, [(500.0, 1.0)], SAFETY, RESERVE))


class Drill:
    def __init__(self, hardness_limit=3, speed=0.75):
        self._limit = hardness_limit
        self._speed = speed

    def hardness_limit(self):
        return self._limit

    def speed_multiplier(self):
        return self._speed


class Miner(pioneer_upgrade.PioneerUpgradeMixin):
    """The VehicleController surface _rebalance_container_split() reads, over a stub Pioneer."""
    SAFETY_MARGIN_MULTIPLIER = SAFETY
    MIN_EMERGENCY_RESERVE_WH = RESERVE

    def __init__(self, vehicle, home):
        self.name = vehicle.id
        self.vehicle = vehicle
        self.home_outpost = home
        self.cruise_throttle = 0.5
        self.current_target_key = None
        self.log = TreeConsole()
        self.recharged = False

    def get_home_slot_coords(self):
        return (self.home_outpost.x, self.home_outpost.y)

    def distance_between(self, p1, p2):
        return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5

    def wh_per_meter_at_throttle(self, throttle, cargo_units=None):
        return vehicle_energy.travel_wh_per_meter_for(self.vehicle, throttle, cargo_units)

    def mine_wh_per_unit(self, item_id, purity=None):
        return vehicle_energy.mine_wh_per_unit_for(self.vehicle, item_id, purity)

    def get_battery(self):
        return (50.0, 100.0, 0.5)

    def recharge_at_station(self, target_level=1.0, **_):
        self.recharged = True


PRICES = {
    "battery_holder_small": 500, "cargo_rack_small": 500, "cargo_rack_medium": 1000,
    "portable_battery": 150, "portable_bin": 150, "heavy_portable_bin": 300,
}


class RebalanceTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.world.services["shop"].prices = dict(PRICES)
        self.world.services["commander"].credits = 10000000

    def make_miner(self, holders, racks, sites):
        slots = [MountSlot(0, "universal", "nav_module"), MountSlot(1, "universal", "drill_module_industrial")]
        for _ in range(holders):
            slots.append(MountSlot(len(slots), "universal", "battery_holder_small", ["portable_battery"]))
        for _ in range(racks):
            slots.append(MountSlot(len(slots), "universal", "cargo_rack_medium", ["heavy_portable_bin", "heavy_portable_bin"]))
        pioneer = self.world.add_pioneer("pioneer_4", slots=slots)
        pioneer.drill = Drill()
        self.world.services["journal"] = Journal(sites)
        return Miner(pioneer, self.world.home)

    def kinds(self, miner):
        mounted = [s.module_id for s in miner.vehicle.modules()]
        return mounted.count("battery_holder_small"), mounted.count("cargo_rack_medium")

    def test_cargo_heavy_miner_moves_to_batteries(self):
        miner = self.make_miner(2, 4, [Site("mineral", 120, 0, item_id="iron_ore", hardness=1, site_id="a")])
        miner._rebalance_container_split()
        self.assertEqual(self.kinds(miner), (5, 1), self.debug_log())
        holder = next(s for s in miner.vehicle.modules() if s.module_id == "battery_holder_small" and s.index >= 6)
        self.assertEqual(holder.internal_items, ["portable_battery"])
        self.assertEqual(self.world.services["shop"].sold.get("heavy_portable_bin"), 6)

    def test_cheap_near_site_moves_to_cargo(self):
        miner = self.make_miner(5, 1, [Site("mineral", 20, 0, item_id="iron_ore", hardness=1, purity="pure", site_id="near")])
        miner._rebalance_container_split()
        self.assertEqual(self.kinds(miner), (4, 2), self.debug_log())
        self.assertTrue(miner.recharged)  # full charge before selling batteries

    def test_new_site_is_picked_up(self):
        # Sites are read from the journal on every call, so a newly surveyed one shifts the split.
        miner = self.make_miner(4, 2, [Site("mineral", 20, 0, item_id="iron_ore", hardness=1, purity="pure", site_id="near")])
        miner._rebalance_container_split()
        self.assertEqual(self.kinds(miner), (4, 2))
        self.world.services["journal"].surveyed.append(Site("mineral", 150, 0, item_id="titanium", hardness=3, site_id="new"))
        miner._rebalance_container_split()
        self.assertEqual(self.kinds(miner), (5, 1), self.debug_log())

    def test_other_outposts_sites_and_too_hard_ones_ignored(self):
        self.world.add_outpost("outpost_2").x = 1000.0
        miner = self.make_miner(2, 4, [
            Site("mineral", 990, 0, item_id="iron_ore", hardness=1, site_id="theirs"),
            Site("mineral", 50, 0, item_id="neutronium", hardness=4, site_id="hard"),
        ])
        miner._rebalance_container_split()
        self.assertEqual(self.kinds(miner), (2, 4))

    def test_small_gain_keeps_split(self):
        miner = self.make_miner(5, 1, [Site("mineral", 120, 0, item_id="iron_ore", hardness=1, site_id="a")])
        miner._rebalance_container_split()
        self.assertEqual(self.kinds(miner), (5, 1))


if __name__ == "__main__":
    unittest.main()
