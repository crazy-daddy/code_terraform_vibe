"""Stub tests for lib/role_demand.py: the per-role demand entries, the
switch candidates an idle Pioneer weighs, and role-slot contention."""

import unittest

import role_demand
from harness import StubTestCase
from priority import BUILD, NEED, NONE, ORDER, STOCK
from survey_requests import scout_work


class EntryTests(unittest.TestCase):
    def test_hauler_counts_outposts_at_top_band(self):
        entry = role_demand.hauler_demand(
            {
                "outpost_1": {ORDER: {"iron_ore": 5}},
                "outpost_2": {ORDER: {"salt": 1}, STOCK: {"sand": 9}},
                "outpost_3": {STOCK: {"sand": 3}},
                "outpost_4": {},
            }
        )
        self.assertEqual(entry["band"], ORDER)
        self.assertEqual(entry["wanted"], 2)
        self.assertEqual(entry["keep"], role_demand.KEEP_HAULERS)
        self.assertEqual(entry["outposts"], {"outpost_1": ORDER, "outpost_2": ORDER, "outpost_3": STOCK})

    def test_hauler_without_deficit_keeps_floor(self):
        entry = role_demand.hauler_demand({"outpost_1": {STOCK: {"sand": 0}}})
        self.assertEqual((entry["band"], entry["wanted"], entry["keep"]), (NONE, 0, role_demand.KEEP_HAULERS))

    def test_constructor_capped(self):
        entry = role_demand.builder_demand(["outpost_1", "outpost_1", None, "outpost_2"])
        self.assertEqual((entry["band"], entry["wanted"], entry["keep"]), (BUILD, role_demand.MAX_BUILDERS, 1))
        self.assertEqual(entry["outposts"], {"outpost_1": BUILD, "outpost_2": BUILD})
        self.assertEqual(role_demand.builder_demand([])["keep"], 0)

    def test_scout_bands(self):
        self.assertEqual(role_demand.scout_demand({"r1": {}}, 0, 0)["band"], NEED)
        self.assertEqual(role_demand.scout_demand({}, 2, 0)["band"], STOCK)
        idle = role_demand.scout_demand({}, 0, 0)
        self.assertEqual((idle["band"], idle["wanted"], idle["keep"]), (NONE, 0, 0))

    def test_miner_keeps_one_per_smelter_outpost(self):
        entry = role_demand.miner_demand(["outpost_home", "outpost_2"])
        self.assertEqual((entry["band"], entry["wanted"], entry["keep"]), (NONE, 0, 2))


class ScoutWorkTests(unittest.TestCase):
    class Poi:
        def __init__(self, x, y, scanned=False):
            self.x, self.y, self.scanned = x, y, scanned

    class Known:
        def __init__(self, site_id, surveyed=False):
            self.id, self.surveyed = site_id, surveyed

    def test_blocked_and_biomass_are_no_work(self):
        points = [self.Poi(10, 20), self.Poi(30, 40), self.Poi(50, 60), self.Poi(70, 80, scanned=True)]
        sites = [self.Known("s1"), self.Known("s2"), self.Known("s3", surveyed=True)]
        targets = {
            "poi_30_40": {"reason": "too_hard"},
            "poi_50_60": {"reason": "wrong_scanner"},
            "site_s2": {"reason": "tier_too_low"},
        }
        self.assertEqual(scout_work(points, sites, targets, []), (1, 1))


class SwitchCandidateTests(unittest.TestCase):
    ROLES = {
        "hauler": {"band": ORDER, "wanted": 2, "keep": 1},
        "builder": {"band": BUILD, "wanted": 1, "keep": 1},
        "scout": {"band": NONE, "wanted": 0, "keep": 0},
        "miner": {"band": NONE, "wanted": 0, "keep": 1},
    }

    def test_higher_band_first_and_full_roles_skipped(self):
        self.assertEqual(
            role_demand.switch_candidates("scout", self.ROLES, {"scout": 1, "hauler": 1}),
            [("builder", 1), ("hauler", 2)],
        )
        # Every role full: an idle scout without work still joins the haulers (refit, never sell).
        self.assertEqual(
            role_demand.switch_candidates("scout", self.ROLES, {"scout": 1, "hauler": 2, "builder": 1}),
            [("hauler", role_demand.MAX_ROLE_SLOTS)],
        )
        roles = dict(self.ROLES, scout={"band": STOCK, "wanted": 1, "keep": 0})
        self.assertEqual(role_demand.switch_candidates("scout", roles, {"scout": 1, "hauler": 2, "builder": 1}), [])

    def test_keep_floor_blocks_leaving(self):
        self.assertEqual(role_demand.switch_candidates("miner", self.ROLES, {"miner": 1}), [])
        self.assertEqual(role_demand.switch_candidates("hauler", self.ROLES, {"hauler": 1}), [])

    def test_only_a_higher_band_pulls_a_busy_role(self):
        roles = dict(self.ROLES, scout={"band": STOCK, "wanted": 1, "keep": 1})
        self.assertEqual(role_demand.switch_candidates("hauler", roles, {"hauler": 3}), [("builder", 1)])

    def test_role_without_work_falls_back_to_hauler_over_wanted(self):
        roles = dict(self.ROLES, builder={"band": NONE, "wanted": 0, "keep": 0})
        self.assertEqual(
            role_demand.switch_candidates("builder", roles, {"builder": 1, "hauler": 5}),
            [("hauler", role_demand.MAX_ROLE_SLOTS)],
        )

    def test_fallback_to_hauler_without_hauler_demand(self):
        roles = {"hauler": {"band": NONE, "wanted": 0, "keep": 1}, "scout": {"band": NONE, "wanted": 0, "keep": 0}}
        self.assertEqual(
            role_demand.switch_candidates("scout", roles, {"scout": 3, "hauler": 1}),
            [("hauler", role_demand.MAX_ROLE_SLOTS)],
        )

    def test_no_demand_record(self):
        self.assertEqual(role_demand.switch_candidates("hauler", {}, {"hauler": 2}), [])


class SlotTests(StubTestCase):
    def test_two_names_one_slot(self):
        self.assertEqual(role_demand.claim_slot("hauler", "pioneer_1", 10, 1), "hauler:0")
        self.assertIsNone(role_demand.claim_slot("hauler", "pioneer_2", 11, 1))
        self.assertEqual(role_demand.claim_slot("hauler", "pioneer_2", 11, 2), "hauler:1")
        self.assertEqual(role_demand.claimed_counts(role_demand.read_claims(), 12), {"hauler": 2})

    def test_own_slot_kept_and_released(self):
        role_demand.claim_slot("scout", "pioneer_1", 10, 3)
        self.assertEqual(role_demand.claim_slot("scout", "pioneer_1", 20, 1), "scout:0")
        self.assertEqual(role_demand.read_claims()["scout:0"]["tick"], 20)
        role_demand.release_slot("scout:0", "pioneer_2")
        self.assertIn("scout:0", role_demand.read_claims())
        role_demand.release_slot("scout:0", "pioneer_1")
        self.assertEqual(role_demand.read_claims(), {})

    def test_stale_slot_taken_over(self):
        role_demand.claim_slot("hauler", "pioneer_1", 10, 1)
        later = 10 + role_demand.common.CLAIM_STALE_TICKS
        self.assertEqual(role_demand.claim_slot("hauler", "pioneer_2", later, 1), "hauler:0")
        self.assertEqual(role_demand.claimed_counts(role_demand.read_claims(), later), {"hauler": 1})


class PublishTests(StubTestCase):
    def test_stored_has_no_role_keys(self):
        value = role_demand.publish(self.world.clock.now)
        raw = self.world.notebook.get(role_demand.ROLE_DEMAND_KEY) or {}
        self.assertIsInstance(raw["roles"], list)  # role names are values, never archive dict keys
        self.assertEqual(raw["roles"][1]["role"], "builder")
        self.assertEqual(role_demand.read(self.world.clock.now)["roles"], value["roles"])

    def test_publish_writes_every_role(self):
        value = role_demand.publish(self.world.clock.now)
        self.assertEqual(set(value["roles"]), {"hauler", "builder", "scout", "miner"})
        self.assertEqual(role_demand.read()["roles"], value["roles"])

    def test_open_blueprint_wants_a_constructor(self):
        self.world.add_blueprint("job_1", "iron_ingot")
        entry = role_demand.publish(self.world.clock.now)["roles"]["builder"]
        self.assertEqual((entry["band"], entry["wanted"]), (BUILD, 1))


if __name__ == "__main__":
    unittest.main()
