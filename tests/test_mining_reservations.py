"""Shared mine sites: per-vehicle mine claims (lib/vehicle_claims.py) and
per-vehicle yield reservations (lib/mining_reservations.py)."""
import unittest

from harness import StubTestCase
from tree_console import TreeConsole
import mining_reservations
import vehicle_claims


class _Vehicle(vehicle_claims.VehicleClaimsMixin):
    def __init__(self, world, name):
        self._world = world
        self.name = name
        self.log = TreeConsole(module="test")
        self.current_target: dict | None = None
        self.current_target_key: str | None = None
        self.current_target_reserved = False

    def get_current_tick(self):
        return self._world.clock.now

    def clear_mission(self):
        pass


def _entry(name):
    entry = mining_reservations.reservation_of(name)
    assert entry is not None
    return entry


MINE = {"type": "mine", "coords": (5, 5), "name": "Site_9_iron_ore"}


class MineClaimTests(StubTestCase):
    def test_two_vehicles_claim_same_mine_site(self):
        a, b = _Vehicle(self.world, "rover_1"), _Vehicle(self.world, "rover_2")
        self.assertTrue(a.claim_target("site_9", MINE))
        self.assertTrue(b.claim_target("site_9", MINE))
        self.assertEqual(set(a.get_claims()), {"site_9@rover_1", "site_9@rover_2"})

    def test_survey_claim_stays_exclusive(self):
        a, b = _Vehicle(self.world, "rover_1"), _Vehicle(self.world, "rover_2")
        poi = {"type": "poi", "coords": (1, 1)}
        self.assertTrue(a.claim_target("poi_1_1", poi))
        self.assertFalse(b.claim_target("poi_1_1", poi))

    def test_release_drops_own_claim_and_reservation(self):
        a, b = _Vehicle(self.world, "rover_1"), _Vehicle(self.world, "rover_2")
        for v in (a, b):
            v.claim_target("site_9", MINE)
            v.current_target, v.current_target_key, v.current_target_reserved = MINE, "site_9", True
            mining_reservations.reserve_yield(v.name, "site_9", "iron_ore", 10, self.world.clock.now)
        a.release_target_claim("site_9")
        self.assertEqual(set(a.get_claims()), {"site_9@rover_2"})
        self.assertIsNone(mining_reservations.reservation_of("rover_1"))
        self.assertEqual(_entry("rover_2")["units"], 10)
        self.assertFalse(a.current_target_reserved)

    def test_mission_claims_finds_own_mine_claim_by_plain_key(self):
        a = _Vehicle(self.world, "rover_1")
        a.claim_target("site_9", MINE)
        claims = a._mission_claims()
        self.assertTrue(a._owns(claims["site_9"]))


class ReservationTests(StubTestCase):
    def test_peers_on_same_site_both_count(self):
        now = self.world.clock.now
        mining_reservations.reserve_yield("rover_1", "site_9", "iron_ore", 10, now, outpost_id="home")
        mining_reservations.reserve_yield("rover_2", "site_9", "iron_ore", 7, now, outpost_id="home")
        self.assertEqual(mining_reservations.get_reserved_yield_totals(now), {"iron_ore": 17})

    def test_new_reservation_replaces_vehicle_entry(self):
        now = self.world.clock.now
        mining_reservations.reserve_yield("rover_1", "site_9", "iron_ore", 10, now)
        mining_reservations.reserve_yield("rover_1", "site_4", "iron_ore", 3, now)
        self.assertEqual(mining_reservations.get_reserved_yield_totals(now), {"iron_ore": 3})
        self.assertEqual(_entry("rover_1")["target_key"], "site_4")

    def test_outpost_filter_and_exclude(self):
        now = self.world.clock.now
        mining_reservations.reserve_yield("p1", "site_1", "iron_ore", 10, now, outpost_id="north")
        mining_reservations.reserve_yield("p2", "site_1", "iron_ore", 4, now, outpost_id="south")
        totals = mining_reservations.get_reserved_yield_totals
        self.assertEqual(totals(now, outpost_id="north"), {"iron_ore": 10})
        self.assertEqual(totals(now, outpost_id="north", exclude_vehicle="p1"), {})

    def test_legacy_site_keyed_entry_still_read_and_released(self):
        now = self.world.clock.now
        self.world.notebook.data[mining_reservations.RESERVED_YIELD_KEY] = {
            "site_9": {"vehicle": "rover_1", "item_id": "iron_ore", "units": 5, "tick": now},
        }
        self.assertEqual(_entry("rover_1")["target_key"], "site_9")
        self.assertEqual(mining_reservations.get_reserved_yield_totals(now, outpost_id="home"), {"iron_ore": 5})
        mining_reservations.release_yield("rover_1")
        self.assertIsNone(mining_reservations.reservation_of("rover_1"))


if __name__ == "__main__":
    unittest.main()
