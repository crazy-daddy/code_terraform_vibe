"""Tests for lib/survey_requests.py (survey request areas, known biomass) and its use by the founding planner."""
import unittest
from types import SimpleNamespace as NS

import harness
import survey_requests as sr
import outpost_plan as plan_
import outpost_sites as sites_

REQUESTS = {"f-b": {"x": 100.0, "y": 100.0, "radius": 50.0, "why": "b"},
            "f-a": {"x": 0.0, "y": 0.0, "radius": 10.0, "why": "a"}}


class RequestTests(unittest.TestCase):
    def test_clean_drops_malformed_entries(self):
        raw = {"ok": {"x": 1, "y": "2", "radius": 3}, "no_radius": {"x": 1, "y": 2}, "bad": 5,
               "nan": {"x": "a", "y": 1, "radius": 1}}
        self.assertEqual(sr.clean_requests(raw), {"ok": {"x": 1.0, "y": 2.0, "radius": 3.0, "why": ""}})
        self.assertEqual(sr.clean_requests(None), {})

    def test_request_at_takes_the_first_sorted_id_holding_the_point(self):
        self.assertEqual(sr.request_at(130, 100, REQUESTS), "f-b")
        self.assertEqual(sr.request_at(5, 5, REQUESTS), "f-a")
        self.assertIsNone(sr.request_at(20, 0, REQUESTS))

    def test_requested_first_keeps_order_within_both_parts(self):
        items = [(20, 0), (110, 100), (300, 0), (0, 5), (100, 140)]
        out = sr.requested_first(items, lambda c: c, REQUESTS)
        self.assertEqual(out, [(110, 100), (0, 5), (100, 140), (20, 0), (300, 0)])
        self.assertEqual(sr.requested_first(items, lambda c: c, {}), items)

    def test_known_biomass_reads_wrong_scanner_poi_keys_only(self):
        targets = {"poi_12_-30": {"reason": "wrong_scanner"}, "poi_1.5_2": {"reason": "wrong_scanner"},
                   "poi_5_5": {"reason": "too_hard"}, "site_7": {"reason": "wrong_scanner"},
                   "poi_x_y": {"reason": "wrong_scanner"}, "poi_9_9": "junk"}
        self.assertEqual(sorted(sr.known_biomass(targets)), [(1.5, 2.0), (12.0, -30.0)])
        self.assertEqual(sr.known_biomass(None), [])


class BlockedTests(unittest.TestCase):
    TARGETS = {"poi_10_20": {"reason": "too_hard"},
               "site_s7": {"reason": "tier_too_low"},
               "poi_1_1": {"reason": "wrong_scanner"},
               "poi_2_2": {"reason": "research_required", "unlocked_scan_researches": ["research_geological_survey"]},
               "poi_3_3": {"reason": "research_required", "unlocked_scan_researches": []}}

    def test_blocked_skips_biomass_and_research_stale_entries(self):
        pois, site_ids = sr.blocked_targets(self.TARGETS, ["research_geological_survey"])
        self.assertEqual(pois, {(10, 20), (2, 2)})
        self.assertEqual(site_ids, {"s7"})

    def test_new_scan_research_unblocks_research_required(self):
        pois, _ = sr.blocked_targets(self.TARGETS, ["research_geological_survey", "research_hydrology_survey"])
        self.assertEqual(pois, {(10, 20)})

    def test_stuck_contacts_neither_score_nor_ask_for_a_survey(self):
        pois = [{"x": 100.0, "y": 100.0, "kind": "unknown"}]
        surveyed = [{"id": "a", "x": 120.0, "y": 100.0, "kind": "mineral", "surveyed": True, "item": "cobalt",
                     "purity": "rich", "hardness": 1, "fluid": None}]
        world = {"bounds": (-900.0, 900.0, -900.0, 900.0), "outposts": [], "ghosts": [], "pois": pois,
                 "sites": surveyed, "range_m": 200.0, "hardness_limit": 5}
        want_of = {"roles": ["mining"], "ores": ["cobalt"], "biome": None}

        def rate(blocked):
            ctx = sites_.prepare(dict(world, blocked=blocked), lambda x, y: "frozen")
            want = sites_.prepare_want(ctx, sites_.wants(want_of, {}))
            return sites_.score(ctx, 100.0, 120.0, want)

        free = rate(None)
        stuck = rate(({(100, 100)}, set()))
        self.assertLess(free["confidence"], 1.0)
        self.assertEqual(stuck["confidence"], 1.0)
        self.assertLessEqual(stuck["score"], free["score"])


class ArchiveTests(harness.StubTestCase):
    def test_write_only_on_change(self):
        self.assertTrue(sr.write_requests(dict(REQUESTS)))
        self.assertEqual(sr.read_requests(), REQUESTS)
        self.assertFalse(sr.write_requests(dict(REQUESTS)))
        self.assertTrue(sr.write_requests({}))
        self.assertEqual(sr.read_requests(), {})

    def test_read_blocked_checks_unlocked_scan_research(self):
        sr.archive.set(sr.UNSUPPORTED_KEY, {"poi_2_2": {"reason": "research_required", "unlocked_scan_researches": []}})
        self.assertEqual(sr.read_blocked(), ({(2, 2)}, set()))

    def test_read_known_biomass_from_the_blacklist(self):
        sr.archive.set(sr.UNSUPPORTED_KEY, {"poi_3_4": {"reason": "wrong_scanner"}})
        self.assertEqual(sr.read_known_biomass(), [(3.0, 4.0)])


class PlannerUseTests(unittest.TestCase):
    def test_wrong_scanner_contact_counts_as_known_biomass(self):
        points = [NS(x=3, y=4, kind="unknown"), NS(x=8, y=8, kind="unknown"), NS(x=1, y=1, kind="mineral")]
        rows = sites_.poi_rows(points, [(3.0, 4.0), (1.0, 1.0)])
        self.assertEqual([row["kind"] for row in rows], ["biomass", "unknown", "mineral"])
        levels = [row["level"] for row in sites_.contacts(rows, [])]
        self.assertEqual(levels, [2, 1, 2])

    def test_survey_areas_cover_open_found_proposals_that_want_a_survey(self):
        base = {"kind": "found", "x": 100.0, "y": 200.0, "roles": ["mining"], "status": "proposed", "survey": True}
        proposals = {"f-mining": dict(base, id="f-mining"),
                     "f-general": dict(base, id="f-general", survey=False),
                     "f-deep": dict(base, id="f-deep", status="rejected"),
                     "d-home": dict(base, id="d-home", kind="designate")}
        out = plan_.survey_areas(proposals, lambda entry: 250.0)
        self.assertEqual(sorted(out), ["f-mining"])
        cx, cy = sites_.centre(100.0, 200.0)
        self.assertEqual((out["f-mining"]["x"], out["f-mining"]["y"], out["f-mining"]["radius"]), (cx, cy, 250.0))


if __name__ == "__main__":
    unittest.main()
