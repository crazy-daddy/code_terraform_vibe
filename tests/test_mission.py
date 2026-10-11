"""Mission record, VehicleClaimsMixin.begin_mission/end_mission and the read-only current_target* views."""
import unittest

import mining_reservations
import vehicle_claims
from archive import archive
from fleet_unit import FleetUnitMixin
from harness import StubTestCase
from mission import Mission
from tree_console import TreeConsole
from vehicle import VehicleController

MINE = {"type": "mine", "coords": (5, 5), "name": "Site_9_iron_ore", "harvest_item": "iron_ore", "estimated_units": 8}


class _Vehicle(vehicle_claims.VehicleClaimsMixin, FleetUnitMixin):
    def __init__(self, name):
        self.name = name
        self.log = TreeConsole(module="test")
        self.mission: Mission | None = None

    def _owns(self, claim):
        return claim.get("vehicle") == self.name


class MissionRecordTests(unittest.TestCase):
    def test_record_round_trip(self):
        m = Mission(kind="mine", target_key="site_9", target=MINE, tick=77)
        self.assertEqual(m.to_record(), {"target_key": "site_9", "kind": "mine", "target": MINE, "tick": 77})
        back = Mission.from_record(m.to_record())
        self.assertEqual((back.kind, back.target_key, back.target, back.tick), ("mine", "site_9", MINE, 77))
        self.assertFalse(back.reserved_yield)

    def test_from_record_tolerates_missing_target(self):
        m = Mission.from_record({"target_key": "poi_1_2"})
        self.assertEqual((m.kind, m.target, m.tick), ("", {}, 0))
        self.assertIsNone(m.coords)

    def test_coords(self):
        self.assertEqual(Mission("mine", "site_9", MINE).coords, (5.0, 5.0))


class ViewTests(unittest.TestCase):
    def test_views_follow_mission_and_reject_writes(self):
        v = VehicleController.__new__(VehicleController)
        v.mission = None
        self.assertEqual((v.current_target, v.current_target_key, v.current_target_reserved), (None, None, False))
        v.mission = Mission("mine", "site_9", MINE, reserved_yield=True)
        self.assertEqual((v.current_target, v.current_target_key, v.current_target_reserved), (MINE, "site_9", True))
        for name in ("current_target", "current_target_key", "current_target_reserved"):
            with self.assertRaises(AttributeError):
                setattr(v, name, None)


class BeginEndMissionTests(StubTestCase):
    def test_begin_claims_reserves_and_saves(self):
        v = _Vehicle("rover_1")
        m = Mission("mine", "site_9", dict(MINE), reserved_yield=True)
        self.assertTrue(v.begin_mission(m))
        self.assertIs(v.mission, m)
        self.assertEqual(set(v.get_claims()), {"site_9@rover_1"})
        reservation = mining_reservations.reservation_of("rover_1")
        assert reservation is not None
        self.assertEqual(reservation["units"], 8)
        record = archive.get_entry(v.MISSION_KEY, "rover_1")
        assert record is not None
        self.assertEqual((record["target_key"], record["kind"], record["target"]), ("site_9", "mine", m.target))
        self.assertEqual(record["tick"], self.world.clock.now)

    def test_lost_claim_changes_nothing(self):
        a, b = _Vehicle("rover_1"), _Vehicle("rover_2")
        poi = {"type": "poi", "coords": (1, 1), "name": "poi_1_1"}
        self.assertTrue(a.begin_mission(Mission("poi_survey", "poi_1_1", poi)))
        self.assertFalse(b.begin_mission(Mission("poi_survey", "poi_1_1", poi)))
        self.assertIsNone(b.mission)
        self.assertIsNone(archive.get_entry(b.MISSION_KEY, "rover_2"))

    def test_end_releases_everything(self):
        v = _Vehicle("rover_1")
        v.begin_mission(Mission("mine", "site_9", dict(MINE), reserved_yield=True))
        v.end_mission()
        self.assertIsNone(v.mission)
        self.assertEqual(v.get_claims(), {})
        self.assertIsNone(mining_reservations.reservation_of("rover_1"))
        self.assertIsNone(archive.get_entry(v.MISSION_KEY, "rover_1"))

    def test_release_target_claim_of_current_ends_mission_other_key_does_not(self):
        v = _Vehicle("rover_1")
        v.begin_mission(Mission("poi_survey", "poi_1_1", {"type": "poi", "coords": (1, 1)}))
        v.release_target_claim("poi_9_9")
        self.assertIsNotNone(v.mission)
        v.release_target_claim("poi_1_1")
        self.assertIsNone(v.mission)
        self.assertIsNone(archive.get_entry(v.MISSION_KEY, "rover_1"))

    def test_load_mission_adopts_saved_record(self):
        a = _Vehicle("rover_1")
        a.begin_mission(Mission("poi_survey", "poi_1_1", {"type": "poi", "coords": (1, 1)}))
        b = _Vehicle("rover_1")
        loaded = b.load_mission()
        self.assertIsInstance(loaded, Mission)
        assert isinstance(loaded, Mission)
        self.assertIs(b.mission, loaded)
        self.assertEqual(loaded.target_key, "poi_1_1")


if __name__ == "__main__":
    unittest.main()
