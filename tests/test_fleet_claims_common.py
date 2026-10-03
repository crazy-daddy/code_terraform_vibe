"""Stub tests for the claim/mission/recall archive helpers shared by
lib/vehicle_claims.py and lib/drone_claims.py (lib/fleet_claims_common.py)."""
import unittest

from harness import StubTestCase
from tree_console import TreeConsole
import fleet_claims_common as common

KEY = "test.claims"
STALE = 100


def owner_of(claim):
    return claim.get("unit")


class ClaimTests(StubTestCase):
    def claim(self, name, tick, target="site_1"):
        notes = []
        return common.try_claim(KEY, target, name, owner_of, {"unit": name, "tick": tick}, tick, STALE, notes), notes

    def claims(self):
        return self.world.notebook.get(KEY) or {}

    def test_fresh_claim_held_against_peer_until_stale(self):
        self.assertTrue(self.claim("a", 10)[0])
        won, notes = self.claim("b", 50)
        self.assertFalse(won)
        self.assertIn("held by 'a'", notes[0])
        self.assertTrue(self.claim("b", 10 + STALE)[0])
        self.assertEqual(self.claims()["site_1"]["unit"], "b")

    def test_own_claim_renews(self):
        self.claim("a", 10)
        self.assertTrue(self.claim("a", 20)[0])

    def test_refresh_only_by_owner(self):
        self.claim("a", 10)
        common.refresh_claim(KEY, "site_1", lambda c: c.get("unit") == "b", 60)
        self.assertEqual(self.claims()["site_1"]["tick"], 10)
        common.refresh_claim(KEY, "site_1", lambda c: c.get("unit") == "a", 60)
        self.assertEqual(self.claims()["site_1"]["tick"], 60)

    def test_release_one_or_all_owned(self):
        self.claim("a", 10, "site_1")
        self.claim("a", 10, "site_2")
        self.claim("b", 10, "site_3")
        owns_a = lambda c: c.get("unit") == "a"
        self.assertEqual(common.release_claims(KEY, "site_3", owns_a), [])
        self.assertEqual(common.release_claims(KEY, "site_1", owns_a), ["site_1"])
        self.assertEqual(common.release_claims(KEY, None, owns_a), ["site_2"])
        self.assertEqual(list(self.claims()), ["site_3"])

    def test_drop_stale(self):
        self.claim("a", 10, "site_1")
        self.claim("b", 90, "site_2")
        self.assertEqual(common.drop_stale_claims(KEY, 10 + STALE, STALE), 1)
        self.assertEqual(list(self.claims()), ["site_2"])


class MissionAndRecallTests(StubTestCase):
    def test_legacy_mission_key_moves_into_shared_dict(self):
        notebook = self.world.notebook
        notebook.set("test.mission:rover_1", {"target_key": "poi_1", "kind": "survey"})
        record = common.read_mission("test.mission", "test.mission:", "rover_1", TreeConsole(module="test"))
        self.assertEqual(record, {"target_key": "poi_1", "kind": "survey"})
        self.assertFalse(notebook.has("test.mission:rover_1"))
        self.assertEqual((notebook.get("test.mission") or {})["rover_1"]["target_key"], "poi_1")
        common.clear_mission("test.mission", "rover_1")
        self.assertIsNone(common.read_mission("test.mission", "test.mission:", "rover_1", TreeConsole(module="test")))

    def test_recall_flags(self):
        common.set_flagged("test.recall", "drone_1", True)
        self.assertTrue(common.is_flagged("test.recall", "drone_1"))
        self.assertFalse(common.is_flagged("test.recall", "drone_2"))
        common.set_flagged("test.recall", "drone_1", False)
        self.assertEqual(self.world.notebook.get("test.recall"), {})


if __name__ == "__main__":
    unittest.main()
