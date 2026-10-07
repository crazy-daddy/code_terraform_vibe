"""Tests for autoplay/lib/outpost_sites.py (founding planner site search: placement checks, priors, scoring, step budget)."""
import unittest
from types import SimpleNamespace as NS

import harness
from game_stubs import Journal, Site
import outpost_sites as os_
import autoplay_roles as roles
from construction_plan import ATOMIC_STEP_BUDGET
from test_autoplay_geom import ops

BOUNDS = (-900.0, 900.0, -900.0, 900.0)
HOME = {"id": "outpost_home", "x": -10.0, "y": 10.0, "home": True}
PRESETS = dict(roles.DEFAULT_ROLE_PRESETS)


def west_frozen(x, y):
    """Fake biome map: frozen west of x = 0, coastal east of it."""
    return "frozen" if x < 0 else "coastal"


def world(outposts=None, pois=None, sites=None, ghosts=None, hardness_limit=4, blocked=None, unsupported=None):
    return {"bounds": BOUNDS, "outposts": [HOME] if outposts is None else outposts, "ghosts": ghosts or [],
            "pois": pois or [], "sites": sites or [], "range_m": 200.0, "hardness_limit": hardness_limit,
            "blocked": blocked, "unsupported": unsupported or {}}


def research_locked(unlocked=()):
    return {"reason": "research_required", "unlocked_scan_researches": list(unlocked)}


def mineral(x, y, item, purity="standard", hardness=1, surveyed=True):
    return {"x": float(x), "y": float(y), "kind": "mineral", "surveyed": surveyed,
            "item": item if surveyed else None, "purity": purity if surveyed else None,
            "hardness": hardness if surveyed else None, "fluid": None}


def fluid_site(x, y, kind, fluid=None, surveyed=True):
    return {"x": float(x), "y": float(y), "kind": kind, "surveyed": surveyed, "item": None, "purity": None,
            "hardness": None, "fluid": fluid}


def prepared(ctx, bundle):
    return os_.prepare_want(ctx, os_.wants(bundle, PRESETS))


def mining(*ores):
    return {"biome": None, "roles": ["mining", "drone_depot"], "ores": list(ores)}


class GeometryTests(unittest.TestCase):
    def test_centre_is_south_east_of_the_nw_anchor(self):
        self.assertEqual(os_.centre(100, 100), (110, 90))

    def test_bounds_take_the_whole_placement_square(self):
        self.assertTrue(os_.in_bounds(-900, 900, BOUNDS))
        self.assertFalse(os_.in_bounds(885, 0, BOUNDS))
        self.assertFalse(os_.in_bounds(0, -885, BOUNDS))

    def test_grid_anchors_on_tile_multiples_inside_bounds(self):
        anchors = os_.grid((-95.0, 95.0, -95.0, 95.0), 40)
        self.assertTrue(all(x % 10 == 0 and y % 10 == 0 for x, y in anchors))
        self.assertTrue(all(os_.in_bounds(x, y, (-95.0, 95.0, -95.0, 95.0)) for x, y in anchors))
        self.assertIn((-90, -70), anchors)


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.ctx = os_.prepare(world(pois=[{"x": 300, "y": 300, "kind": "unknown"}]), west_frozen)

    def test_outpost_clearance_is_centre_to_square(self):
        # home centre (0, 0); clearance square half 13 m: anchor (40, 10) has its square 37 m away.
        self.assertEqual(os_.check(self.ctx, 40, 10), "outpost_clearance")
        self.assertIsNone(os_.check(self.ctx, 60, 10))

    def test_poi_clearance_counts_unknown_contacts(self):
        # POI at (300, 300); anchor (310, 330) -> centre (320, 320), square edge 7 m off.
        self.assertEqual(os_.check(self.ctx, 310, 330), "poi_clearance")
        self.assertIsNone(os_.check(self.ctx, 330, 360))

    def test_ghost_outposts_block_like_outposts(self):
        ctx = os_.prepare(world(ghosts=[(500, 500)]), west_frozen)
        self.assertEqual(os_.check(ctx, 520, 500), "outpost_clearance")

    def test_biome_is_read_at_the_anchor(self):
        self.assertEqual(os_.check(self.ctx, -10, 400, "coastal"), "biome frozen")
        self.assertIsNone(os_.check(self.ctx, 0, 400, "coastal"))

    def test_out_of_bounds(self):
        self.assertEqual(os_.check(self.ctx, 890, 0), "out_of_bounds")


class ContactTests(unittest.TestCase):
    def test_site_wins_over_its_poi_and_levels_follow_knowledge(self):
        rows = os_.contacts([{"x": 100, "y": 100, "kind": "mineral"}, {"x": 5, "y": 5, "kind": "unknown"},
                             {"x": 9, "y": 9, "kind": "water"}],
                            [mineral(100, 100, "iron_ore"), mineral(200, 200, "silicon", surveyed=False)])
        by_xy = {(row["x"], row["y"]): row for row in rows}
        self.assertEqual(len(rows), 4)
        self.assertEqual(by_xy[(100.0, 100.0)]["level"], 3)
        self.assertEqual(by_xy[(200.0, 200.0)]["level"], 2)
        self.assertIsNone(by_xy[(200.0, 200.0)]["item"])
        self.assertEqual(by_xy[(5.0, 5.0)]["level"], 1)
        self.assertEqual(by_xy[(9.0, 9.0)]["fluid"], "water")   # kind tells the fluid

    def test_flat_prior_without_scans(self):
        prior = os_.priors(os_.contacts([{"x": 1, "y": 1, "kind": "unknown"}], []))
        self.assertAlmostEqual(prior["ore"]["iron_ore"], 1.0 / len(os_.RAW_ORE_ITEM_IDS))
        self.assertAlmostEqual(prior["kind"]["mineral"], 1.0 / len(os_.SITE_KINDS))

    def test_prior_from_own_scans(self):
        rows = os_.contacts([], [mineral(0, 0, "iron_ore"), mineral(50, 0, "iron_ore"), mineral(100, 0, "silicon"),
                                 fluid_site(200, 0, "water")])
        prior = os_.priors(rows)
        self.assertAlmostEqual(prior["ore"]["iron_ore"], 2 / 3)
        self.assertAlmostEqual(prior["kind"]["mineral"], 3 / 4)
        self.assertEqual(prior["ore"]["cobalt"], 0.0)

    def test_hard_site_is_worth_less(self):
        prior = os_.priors([])
        row = os_.contacts([], [mineral(0, 0, "titanium", hardness=3)])[0]
        self.assertEqual(os_.ore_value(row, "titanium", prior, 4), (1.0, True))
        self.assertEqual(os_.ore_value(row, "titanium", prior, 1), (os_.HARD_FACTOR, True))


class WantTests(unittest.TestCase):
    def test_wants_field_fluids_only_and_biosites_for_bio_roles(self):
        want = os_.wants({"biome": "coastal", "roles": ["bio_coastal", "drone_depot"], "ores": []}, PRESETS)
        self.assertEqual(want["fluids"], [])
        want = os_.wants({"biome": "volcanic", "roles": ["bio_caster", "biomass_mixer", "liquifier_volcanic"]}, PRESETS)
        self.assertEqual(sorted(want["fluids"]), ["steam", "water"])   # essences have no field site
        self.assertTrue(want["biosites"])


class ScoreTests(unittest.TestCase):
    def test_three_ore_cluster_beats_one_ore_cluster(self):
        sites = [mineral(400, 400, "iron_ore"), mineral(440, 400, "silicon"), mineral(400, 440, "cobalt"),
                 mineral(-400, -400, "iron_ore", purity="pure")]
        ctx = os_.prepare(world(sites=sites), west_frozen)
        best = os_.rank_sites(mining("iron_ore", "silicon", "cobalt"), ctx, PRESETS)[0]
        self.assertLess(os_._dist(best["x"], best["y"], 410, 410), 200)
        self.assertGreater(best["confidence"], os_.MIN_CONFIDENCE)
        self.assertFalse(best["survey"])

    def test_unknown_contacts_count_by_expected_value_and_ask_for_a_survey(self):
        pois = [{"x": 400 + 30 * i, "y": 400, "kind": "unknown"} for i in range(4)]
        ctx = os_.prepare(world(pois=pois), west_frozen)
        best = os_.rank_sites(mining("iron_ore"), ctx, PRESETS)[0]
        self.assertLess(os_._dist(best["x"], best["y"], 450, 400), 250)
        self.assertGreater(best["terms"]["ore"], 0)
        self.assertTrue(best["survey"])
        known = os_.prepare(world(sites=[mineral(400, 400, "iron_ore")]), west_frozen)
        sure = os_.score(known, 420, 430, prepared(known, mining("iron_ore")))
        self.assertGreater(sure["terms"]["ore"], os_.score(ctx, 420, 430, prepared(ctx, mining("iron_ore")))["terms"]["ore"])

    def test_ore_term_saturates(self):
        sites = [mineral(400 + 20 * i, 300, "iron_ore", purity="pure") for i in range(10)]
        ctx = os_.prepare(world(sites=sites), west_frozen)
        row = os_.score(ctx, 480, 340, prepared(ctx, mining("iron_ore")))
        self.assertAlmostEqual(row["terms"]["ore"], os_.WEIGHTS["ore"] * os_.ORE_CAP)

    def test_nearer_wanted_fluid_scores_higher(self):
        ctx = os_.prepare(world(sites=[fluid_site(400, 400, "thermal", "steam")]), west_frozen)
        want = prepared(ctx, {"biome": None, "roles": ["power"], "ores": []})
        close = os_.score(ctx, 420, 450, want)["terms"]["fluid"]
        far = os_.score(ctx, 420, 600, want)["terms"]["fluid"]
        self.assertGreater(close, far)
        self.assertGreater(far, 0)
        self.assertEqual(os_.score(ctx, 420, 700, want)["terms"]["fluid"], 0)

    def test_biome_locked_bundle_stays_in_its_biome_and_away_from_the_border(self):
        bio = {"x": 300.0, "y": 300.0, "kind": "biomass"}
        ctx = os_.prepare(world(pois=[bio, {"x": -300.0, "y": 300.0, "kind": "biomass"}]), west_frozen)
        rows = os_.rank_sites({"biome": "coastal", "roles": ["bio_coastal", "drone_depot"], "ores": []}, ctx, PRESETS)
        self.assertTrue(rows)
        self.assertTrue(all(row["x"] >= 0 and row["biome"] == "coastal" for row in rows))
        self.assertGreater(rows[0]["terms"]["biosite"], 0)
        want = prepared(ctx, {"biome": "coastal", "roles": ["bio_coastal"]})
        edge = os_.add_detail(ctx, os_.score(ctx, 10, 400, want), want)["terms"]["margin"]
        inner = os_.add_detail(ctx, os_.score(ctx, 400, 400, want), want)["terms"]["margin"]
        self.assertLess(edge, inner)

    def test_biosites_of_another_biome_do_not_count(self):
        ctx = os_.prepare(world(pois=[{"x": -50.0, "y": 400.0, "kind": "biomass"}]), west_frozen)
        want = prepared(ctx, {"biome": "coastal", "roles": ["bio_coastal"]})
        self.assertEqual(os_.score(ctx, 40, 400, want)["terms"]["biosite"], 0)

    def test_distance_to_home_costs(self):
        ctx = os_.prepare(world(), west_frozen)
        want = prepared(ctx, mining())
        self.assertGreater(os_.score(ctx, 200, 200, want)["score"], os_.score(ctx, 700, 700, want)["score"])

    def test_no_anchor_passes(self):
        ctx = os_.prepare(world(), lambda x, y: "frozen")
        self.assertEqual(os_.rank_sites({"biome": "deep", "roles": ["weather_deep"], "ores": []}, ctx, PRESETS), [])


class InferenceTests(unittest.TestCase):
    """Unresolved contacts typed by contact_inference (survey.unsupported_targets)."""
    POWER = {"biome": None, "roles": ["power"], "ores": []}
    ALL_BUT_GEO = ["research_hydrology_survey", "research_petroleum_survey",
                   "research_exotic_husbandry", "research_deep_exotics"]

    def test_single_kind_types_the_contact(self):
        ctx = os_.prepare(world(pois=[{"x": 400, "y": 400, "kind": "unknown"}],
                                unsupported={"poi_400_400": {"reason": "tier_too_low"}}), west_frozen)
        row = ctx["rows"][0]
        self.assertEqual((row["level"], row["kind"], row["fluid"]), (2, "oil", "oil"))

    def test_several_kinds_become_the_contact_prior(self):
        ctx = os_.prepare(world(pois=[{"x": 400, "y": 400, "kind": "unknown"}],
                                unsupported={"poi_400_400": research_locked()}), lambda x, y: None)
        row = ctx["rows"][0]
        self.assertEqual(row["level"], 1)
        self.assertAlmostEqual(row["kinds"]["thermal"], 1 / 4)
        self.assertNotIn("mineral", row["kinds"])

    def test_geothermal_biome_types_a_research_locked_contact_as_thermal(self):
        ctx = os_.prepare(world(pois=[{"x": 400, "y": 400, "kind": "unknown"}],
                                unsupported={"poi_400_400": research_locked()}), lambda x, y: "geothermal")
        row = ctx["rows"][0]
        self.assertEqual((row["level"], row["kind"], row["fluid"]), (2, "thermal", "steam"))

    def test_uninformative_reason_leaves_the_contact_unknown(self):
        ctx = os_.prepare(world(pois=[{"x": 400, "y": 400, "kind": "unknown"}],
                                unsupported={"poi_400_400": {"reason": "out_of_range"}}), west_frozen)
        self.assertEqual(ctx["rows"][0]["level"], 1)
        self.assertNotIn("kinds", ctx["rows"][0])

    def test_stuck_geothermal_contact_counts_toward_steam_without_a_survey(self):
        poi = [{"x": 400, "y": 400, "kind": "unknown"}]
        blocked = ({(400, 400)}, set())
        geo = lambda x, y: "geothermal"
        plain = os_.prepare(world(pois=poi, blocked=blocked), geo)
        inferred = os_.prepare(world(pois=poi, blocked=blocked, unsupported={"poi_400_400": research_locked()}), geo)
        base = os_.score(plain, 420, 430, prepared(plain, self.POWER))
        best = os_.score(inferred, 420, 430, prepared(inferred, self.POWER))
        self.assertEqual(base["terms"]["fluid"], 0)
        self.assertGreater(best["terms"]["fluid"], 0)
        self.assertGreaterEqual(best["confidence"], os_.MIN_CONFIDENCE)

    def test_geothermal_biome_beats_a_frozen_one(self):
        poi = [{"x": 400, "y": 400, "kind": "unknown"}]
        unsupported = {"poi_400_400": research_locked(self.ALL_BUT_GEO[:1])}
        geo = os_.prepare(world(pois=poi, unsupported=unsupported), lambda x, y: "geothermal")
        flat = os_.prepare(world(pois=poi, unsupported=unsupported), west_frozen)
        steam = {"biome": None, "roles": ["power"], "ores": []}
        self.assertGreater(os_.score(geo, 420, 430, prepared(geo, steam))["terms"]["fluid"],
                           os_.score(flat, 420, 430, prepared(flat, steam))["terms"]["fluid"])

    def test_only_geothermal_research_locked_means_a_thermal_vent(self):
        ctx = os_.prepare(world(pois=[{"x": 400, "y": 400, "kind": "unknown"}],
                                unsupported={"poi_400_400": research_locked(self.ALL_BUT_GEO)}), west_frozen)
        row = ctx["rows"][0]
        self.assertEqual((row["level"], row["kind"], row["fluid"]), (2, "thermal", "steam"))


class BudgetTests(unittest.TestCase):
    """
    Worst-case atomic slice costs on a dense map: a contact every 100 m around
    the candidates plus surveyed sites in between (~130 per km2, several
    times the density of a whole map with every contact counted).
    """

    def dense(self):
        pois = [{"x": float(x), "y": float(y), "kind": "unknown"} for x in range(0, 900, 100) for y in range(0, 900, 100)]
        sites = [mineral(x + 50, y + 50, "iron_ore") for x in range(0, 900, 200) for y in range(0, 900, 200)]
        outposts = [HOME] + [{"id": f"o{i}", "x": float(100 * i), "y": 700.0, "home": False} for i in range(8)]
        unsupported = {f"poi_{int(poi['x'])}_{int(poi['y'])}": research_locked() for poi in pois[::2]}
        return os_.prepare(world(outposts=outposts, pois=pois, sites=sites, unsupported=unsupported), west_frozen)

    def test_filter_slice_fits_with_dense_pipes(self):
        ctx = self.dense()
        ctx["pipes"] = os_.pipe_blocks([(tx, ty) for tx in range(30, 70) for ty in range(30, 70) if (tx + ty) % 2])
        anchors = [(450 + 7 * i, 450) for i in range(os_.FILTER_CHUNK)]
        self.assertLess(ops(os_.filter_slice, anchors, ctx, "coastal", True), ATOMIC_STEP_BUDGET)

    def test_filter_slice_fits(self):
        ctx = self.dense()
        anchors = [(450 + 7 * i, 450) for i in range(os_.FILTER_CHUNK)]
        self.assertLess(ops(os_.filter_slice, anchors, ctx, "coastal"), ATOMIC_STEP_BUDGET)

    def test_score_step_fits(self):
        ctx = self.dense()
        want = os_.prepare_want(ctx, {"ores": ["iron_ore", "silicon", "cobalt"], "fluids": ["steam", "water", "oil"],
                                      "biome": "coastal", "biosites": True})
        anchors = [(x, y) for x in range(0, 900, 80) for y in range(0, 900, 80)]
        state = os_.score_init(ctx, anchors, want)
        worst = 0
        while True:
            done = [False]
            cost = ops(lambda: done.__setitem__(0, os_.score_step(state)))
            worst = max(worst, cost)
            if done[0]:
                break
        self.assertLess(worst, ATOMIC_STEP_BUDGET)
        self.assertEqual(len(state["out"]), len(anchors))

    def test_stacked_contacts_split_mid_cell(self):
        pois = [{"x": 455.0, "y": 445.0, "kind": "unknown"}] * 200   # far more rows in one cell than a chunk takes
        ctx = os_.prepare(world(pois=pois), west_frozen)
        want = prepared(ctx, mining("iron_ore"))
        state = os_.score_init(ctx, [(450, 450)], want)
        worst = 0
        while True:
            done = [False]
            worst = max(worst, ops(lambda: done.__setitem__(0, os_.score_step(state))))
            if done[0]:
                break
        self.assertLess(worst, ATOMIC_STEP_BUDGET)
        whole = os_.score(ctx, 450, 450, want)
        self.assertEqual(state["out"][0]["terms"], whole["terms"])

    def test_detail_slice_fits(self):
        ctx = self.dense()
        want = prepared(ctx, {"biome": "coastal", "roles": ["bio_coastal"]})
        rows = [os_.score(ctx, 450, 450, want)][:os_.DETAIL_CHUNK]
        os_.detail_slice([dict(rows[0], terms=dict(rows[0]["terms"]))], ctx, want)   # warm the biome cache
        self.assertLess(ops(os_.detail_slice, rows, ctx, want), ATOMIC_STEP_BUDGET)

    def test_value_slice_fits(self):
        ctx = self.dense()
        want = {"ores": ["iron_ore", "silicon", "cobalt"], "fluids": ["steam", "water", "oil"],
                "biome": "coastal", "biosites": True}
        rows = ctx["rows"][:os_.VALUE_CHUNK]
        os_.value_rows(rows, ctx, want)   # biome cache warm: the cold reads are game calls, not steps
        self.assertLess(ops(os_.value_rows, rows, ctx, want), ATOMIC_STEP_BUDGET)


class _Site(Site):
    def __init__(self, x, y, kind, surveyed, **fields):
        super().__init__(kind, x, y)
        self.id = f"s{int(x)}_{int(y)}"
        self.surveyed = surveyed
        self._fluid = fields.pop("fluid", None)
        for name, value in fields.items():
            setattr(self, name, value)

    def fluid(self):
        return self._fluid


class _Planet:
    def get_bounds(self):
        return NS(min_x=-900, max_x=900, min_y=-900, max_y=900)

    def points_of_interest(self):
        return [NS(x=10, y=20, scanned=False, kind="unknown"), NS(x=300, y=300, scanned=True, kind="biomass")]


DISCOVERED = [_Site(100.0, 100.0, "mineral", True, item_id="cobalt", purity="rich", hardness=3),
              _Site(200.0, 200.0, "exotic", True, fluid="raw_chlorine"),
              _Site(250.0, 250.0, "water", False)]


class ReaderTests(harness.StubTestCase):
    def test_read_world_takes_pois_sites_and_drill_reach(self):
        self.world.components["nocturna"] = _Planet()
        self.world.components["journal"] = Journal(discovered=DISCOVERED)
        snap = os_.read_world([HOME], {"mining_drill_kit", "mining_drill_industrial_kit"}, 200.0)
        assert snap is not None
        self.assertEqual(snap["bounds"], (-900.0, 900.0, -900.0, 900.0))
        self.assertEqual(snap["hardness_limit"], 3)
        self.assertEqual([p["kind"] for p in snap["pois"]], ["unknown", "biomass"])
        by_kind = {row["kind"]: row for row in snap["sites"]}
        self.assertEqual((by_kind["mineral"]["item"], by_kind["mineral"]["purity"]), ("cobalt", "rich"))
        self.assertEqual(by_kind["exotic"]["fluid"], "raw_chlorine")
        self.assertFalse(by_kind["water"]["surveyed"])
        ctx = os_.prepare(snap, west_frozen)
        self.assertEqual(len(ctx["rows"]), 5)

    def test_read_world_without_planet(self):
        self.assertIsNone(os_.read_world([HOME], set(), 200.0))
        self.assertIsNone(os_.hardness_limit(set()))


if __name__ == "__main__":
    unittest.main()


class PipeBufferTests(unittest.TestCase):
    def test_storage_bundle_wants_clear_land(self):
        self.assertTrue(os_.wants({"roles": ["storage", "drone_depot"]}, PRESETS)["clear"])
        self.assertFalse(os_.wants(mining("iron_ore"), PRESETS)["clear"])

    def test_pipe_within_buffer_blocks_only_buffer_bundles(self):
        ctx = os_.prepare(dict(world(), pipes=[(45, 50)]), west_frozen)   # footprint tiles x 40..43, buffer 36..47
        self.assertEqual(os_.check(ctx, 400, 500, None, True), "pipe_buffer")
        self.assertIsNone(os_.check(ctx, 400, 500, None, False))

    def test_pipe_just_outside_buffer_passes(self):
        ctx = os_.prepare(dict(world(), pipes=[(48, 50), (35, 50)]), west_frozen)   # footprint tiles 40..43, buffer 36..47
        self.assertIsNone(os_.check(ctx, 400, 500, None, True))
        ctx = os_.prepare(dict(world(), pipes=[(47, 50)]), west_frozen)
        self.assertEqual(os_.check(ctx, 400, 500, None, True), "pipe_buffer")
