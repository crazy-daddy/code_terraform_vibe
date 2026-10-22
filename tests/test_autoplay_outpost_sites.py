"""Tests for autoplay/lib/outpost_sites.py (founding planner site search: placement checks, priors, scoring, step budget)."""

import unittest
from types import SimpleNamespace as NS

import autoplay_roles as roles
import harness
import outpost_sites as os_
from construction_plan import ATOMIC_STEP_BUDGET
from game_stubs import Journal, Site
from test_autoplay_geom import ops

BOUNDS = (-900.0, 900.0, -900.0, 900.0)
HOME = {"id": "outpost_home", "x": -10.0, "y": 10.0, "home": True}
PRESETS = dict(roles.DEFAULT_ROLE_PRESETS)


def west_frozen(x, y):
    """Fake biome map: frozen west of x = 0, coastal east of it."""
    return "frozen" if x < 0 else "coastal"


def world(outposts=None, pois=None, sites=None, ghosts=None, hardness_limit=4, blocked=None, unsupported=None):
    return {
        "bounds": BOUNDS,
        "outposts": [HOME] if outposts is None else outposts,
        "ghosts": ghosts or [],
        "pois": pois or [],
        "sites": sites or [],
        "range_m": 200.0,
        "hardness_limit": hardness_limit,
        "blocked": blocked,
        "unsupported": unsupported or {},
    }


def research_locked(unlocked=()):
    return {"reason": "research_required", "unlocked_scan_researches": list(unlocked)}


def mineral(x, y, item, purity="standard", hardness=1, surveyed=True):
    return {
        "x": float(x),
        "y": float(y),
        "kind": "mineral",
        "surveyed": surveyed,
        "item": item if surveyed else None,
        "purity": purity if surveyed else None,
        "hardness": hardness if surveyed else None,
        "fluid": None,
    }


def fluid_site(x, y, kind, fluid=None, surveyed=True):
    return {
        "x": float(x),
        "y": float(y),
        "kind": kind,
        "surveyed": surveyed,
        "item": None,
        "purity": None,
        "hardness": None,
        "fluid": fluid,
    }


def prepared(ctx, bundle):
    return os_.prepare_want(ctx, os_.wants(bundle, PRESETS))


def mining(*ores):
    return {"biome": None, "roles": ["mining", "drone_depot"], "ores": list(ores)}


class GeometryTests(unittest.TestCase):
    def test_centre_is_south_east_of_the_nw_anchor(self):
        self.assertEqual(os_.outpost_centre(100, 100), (110, 90))

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
        rows = os_.contacts(
            [
                {"x": 100, "y": 100, "kind": "mineral"},
                {"x": 5, "y": 5, "kind": "unknown"},
                {"x": 9, "y": 9, "kind": "water"},
            ],
            [mineral(100, 100, "iron_ore"), mineral(200, 200, "silicon", surveyed=False)],
        )
        by_xy = {(row["x"], row["y"]): row for row in rows}
        self.assertEqual(len(rows), 4)
        self.assertEqual(by_xy[(100.0, 100.0)]["level"], 3)
        self.assertEqual(by_xy[(200.0, 200.0)]["level"], 2)
        self.assertIsNone(by_xy[(200.0, 200.0)]["item"])
        self.assertEqual(by_xy[(5.0, 5.0)]["level"], 1)
        self.assertEqual(by_xy[(9.0, 9.0)]["fluid"], "water")  # kind tells the fluid

    def test_flat_prior_without_scans(self):
        prior = os_.priors(os_.contacts([{"x": 1, "y": 1, "kind": "unknown"}], []))
        self.assertAlmostEqual(prior["ore"]["iron_ore"], 1.0 / len(os_.RAW_ORE_ITEM_IDS))
        self.assertAlmostEqual(prior["kind"]["mineral"], 1.0 / len(os_.SITE_KINDS))

    def test_prior_from_own_scans(self):
        rows = os_.contacts(
            [],
            [
                mineral(0, 0, "iron_ore"),
                mineral(50, 0, "iron_ore"),
                mineral(100, 0, "silicon"),
                fluid_site(200, 0, "water"),
            ],
        )
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
        self.assertEqual(sorted(want["fluids"]), ["steam", "water"])  # essences have no field site
        self.assertTrue(want["biosites"])


class ScoreTests(unittest.TestCase):
    def test_three_ore_cluster_beats_one_ore_cluster(self):
        sites = [
            mineral(400, 400, "iron_ore"),
            mineral(440, 400, "silicon"),
            mineral(400, 440, "cobalt"),
            mineral(-400, -400, "iron_ore", purity="pure"),
        ]
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
        self.assertGreater(
            sure["terms"]["ore"], os_.score(ctx, 420, 430, prepared(ctx, mining("iron_ore")))["terms"]["ore"]
        )

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
        cluster = [{"x": 300.0 + dx, "y": 300.0 + dy, "kind": "biomass"} for dx in (0, 50) for dy in (0, 50)]
        ctx = os_.prepare(world(pois=cluster + [{"x": -300.0, "y": 300.0, "kind": "biomass"}]), west_frozen)
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

    def test_link_length_counts_the_full_l(self):
        ctx = os_.prepare(world(), west_frozen)
        want = prepared(ctx, mining())
        diagonal = os_.score(ctx, 290, 310, want)["terms"]["grid"]  # centre (300, 300): 600 m of L
        straight = os_.score(ctx, 414, 10, want)["terms"]["grid"]  # centre (424, 0): same straight distance
        self.assertAlmostEqual(diagonal, os_.WEIGHTS["grid"] * 0.6)
        self.assertLess(diagonal, straight)

    def test_travel_from_the_nearest_charging_station(self):
        station = {"id": "o1", "x": 490.0, "y": 10.0, "home": False, "types": {"charging_station": 1}}
        bare = dict(station, types={})
        want_spec = mining()
        charged = os_.prepare(world(outposts=[HOME, station]), west_frozen)
        uncharged = os_.prepare(world(outposts=[HOME, bare]), west_frozen)
        near = os_.score(charged, 640, 10, prepared(charged, want_spec))["terms"]["travel"]  # 150 m from o1
        far = os_.score(uncharged, 640, 10, prepared(uncharged, want_spec))["terms"]["travel"]  # 650 m from home
        self.assertAlmostEqual(near, os_.WEIGHTS["travel"] * 0.15)
        self.assertAlmostEqual(far, os_.WEIGHTS["travel"] * 0.65)

    def test_crowding_puts_the_best_gap_at_spacing_tiles(self):
        ctx = os_.prepare(world(), west_frozen)
        want = prepared(ctx, mining())
        self.assertLess(os_.score(ctx, 50, 10, want)["terms"]["crowd"], 0)  # centre 60 m from home: 2 free tiles
        self.assertEqual(os_.score(ctx, 70, 10, want)["terms"]["crowd"], 0.0)  # 4 free tiles

        def spacing(cx):
            terms = os_.score(ctx, cx - 10, 10, want)["terms"]
            return terms["grid"] + terms["crowd"]

        best = max(range(60, 400, 10), key=spacing)
        self.assertEqual(best // 10 - 4, os_.SPACING_TILES)  # 4x4 footprints: free tiles = centre gap - 4

    def test_near_puts_the_best_home_distance_at_home_near_m(self):
        ctx = os_.prepare(world(), west_frozen)
        want = prepared(ctx, mining())
        near = os_.score(ctx, 140, 10, want)["terms"]["near"]  # centre 150 m from home
        self.assertAlmostEqual(near, os_.WEIGHTS["near"] * 0.5)
        self.assertEqual(os_.score(ctx, 290, 10, want)["terms"]["near"], 0.0)  # 300 m

        def distance(cx):
            terms = os_.score(ctx, cx - 10, 10, want)["terms"]
            return terms["home"] + terms["near"]

        self.assertEqual(max(range(60, 600, 10), key=distance), os_.HOME_NEAR_M)

    def test_demand_factors(self):
        self.assertEqual(os_.demand_factors(["iron_ore", "silicon"], {}), {"iron_ore": 1.0, "silicon": 1.0})
        factors = os_.demand_factors(["iron_ore", "silicon"], {"iron_ore": 0.6, "silicon": 0.3})
        self.assertAlmostEqual(factors["iron_ore"], 0.6 / 0.45)
        self.assertAlmostEqual(factors["silicon"], 0.3 / 0.45)
        side = os_.demand_factors(["iron_ore", "cobalt"], {"iron_ore": 0.9})  # cobalt gets the smallest listed share
        self.assertAlmostEqual(side["cobalt"], 1.0)
        self.assertEqual(os_.demand_factors([], {"iron_ore": 1.0}), {})

    def test_demand_share_prefers_the_iron_site(self):
        sites = [mineral(400, 400, "iron_ore"), mineral(-400, -400, "silicon")]
        even = os_.prepare(world(sites=sites), west_frozen)
        want = prepared(even, mining("iron_ore", "silicon"))
        self.assertAlmostEqual(
            os_.score(even, 390, 410, want)["terms"]["ore"], os_.score(even, -410, -390, want)["terms"]["ore"]
        )
        iron = os_.prepare(dict(world(sites=sites), demand={"iron_ore": 0.8, "silicon": 0.2}), west_frozen)
        want = prepared(iron, mining("iron_ore", "silicon"))
        self.assertGreater(
            os_.score(iron, 390, 410, want)["terms"]["ore"], os_.score(iron, -410, -390, want)["terms"]["ore"]
        )

    def test_early_weights_cost_distance_more_and_reward_a_new_biome(self):
        settled = [dict(HOME, biome="frozen")]
        late = os_.prepare(world(outposts=settled), west_frozen)
        early = os_.prepare(dict(world(outposts=settled), weights=os_.WEIGHTS_EARLY), west_frozen)
        want_late = prepared(late, mining())
        want_early = prepared(early, mining())
        self.assertLess(
            os_.score(early, 700, 700, want_early)["terms"]["home"],
            os_.score(late, 700, 700, want_late)["terms"]["home"],
        )
        self.assertEqual(
            os_.score(late, 200, 200, want_late)["terms"]["biome_new"], os_.WEIGHTS["biome_new"]
        )  # coastal: no outpost there
        self.assertEqual(os_.score(late, -200, 200, want_late)["terms"]["biome_new"], 0.0)  # frozen: home's biome
        self.assertEqual(os_.score(early, 200, 200, want_early)["terms"]["biome_new"], os_.WEIGHTS_EARLY["biome_new"])

    def test_reach_gate(self):
        weights, reach = os_.phase_inputs(
            [HOME, {"id": "o1", "x": 500.0, "y": 0.0, "types": {"charging_station": 1}}], True
        )
        self.assertEqual(weights, os_.WEIGHTS_EARLY)
        reach = reach or {}
        self.assertEqual(len(reach["points"]), 2)
        ctx = os_.prepare(dict(world(), reach=reach), west_frozen)
        self.assertIsNone(os_.check(ctx, 500, 500))
        self.assertEqual(os_.check(ctx, 800, -800), "out_of_reach")
        self.assertIsNone(os_.check(ctx, 850, 0))  # within the Charging Station host's reach, not home's
        self.assertEqual(os_.phase_inputs([HOME], False), (os_.WEIGHTS, None))
        closed = os_.prepare(dict(world(), reach={"points": [], "m": 600.0}), west_frozen)
        self.assertEqual(os_.check(closed, 500, 500), "out_of_reach")

    def test_unknown_biome_earns_no_new_biome_bonus(self):
        ctx = os_.prepare(world(outposts=[dict(HOME, biome="frozen")]), lambda x, y: None)
        want = prepared(ctx, mining())
        self.assertEqual(os_.score(ctx, 200, 200, want)["terms"]["biome_new"], 0.0)

    def test_no_anchor_passes(self):
        ctx = os_.prepare(world(), lambda x, y: "frozen")
        self.assertEqual(os_.rank_sites({"biome": "deep", "roles": ["weather_deep"], "ores": []}, ctx, PRESETS), [])


def unknowns(*spots):
    return [{"x": float(x), "y": float(y), "kind": "unknown"} for x, y in spots]


class ReachGainTests(unittest.TestCase):
    """reach_gain: share of out-of-reach, non-stuck contacts a candidate's Charging Station would bring within reach."""

    def term(self, ctx, x, y):
        return os_.score(ctx, x, y, prepared(ctx, mining("iron_ore")))["terms"]["reach_gain"]

    def test_reach_gain_rewards_new_ground(self):
        ctx = os_.prepare(world(pois=unknowns((1500, 0), (1500, 20), (1520, 0), (1520, 20))), west_frozen)
        self.assertEqual(ctx["remote_n"], 4)
        self.assertEqual(self.term(ctx, 1000, 0), os_.WEIGHTS["reach_gain"] * 1.0)
        self.assertEqual(self.term(ctx, -300, 0), 0.0)

    def test_reach_gain_share_of_remote(self):
        ctx = os_.prepare(world(pois=unknowns((1500, 0), (1520, 0), (-1500, 0), (-1520, 0))), west_frozen)
        self.assertEqual(self.term(ctx, 1000, 0), os_.WEIGHTS["reach_gain"] * 0.5)

    def test_reach_gain_zero_without_starts_or_remote(self):
        bare = os_.prepare(world(outposts=[], pois=unknowns((1500, 0))), west_frozen)
        self.assertEqual(bare["remote_n"], 0)
        self.assertEqual(self.term(bare, 1000, 0), 0.0)
        near = os_.prepare(world(pois=unknowns((300, 0), (0, 300))), west_frozen)
        self.assertEqual(near["remote"], [])
        self.assertEqual(self.term(near, 300, 300), 0.0)

    def test_reach_gain_ignores_stuck(self):
        ctx = os_.prepare(world(pois=unknowns((1500, 0)), blocked=({(1500, 0)}, set())), west_frozen)
        self.assertEqual(ctx["remote_n"], 0)
        self.assertEqual(self.term(ctx, 1000, 0), 0.0)

    def test_reach_gain_out_of_confidence(self):
        site = [mineral(1050, 0, "iron_ore")]
        plain = os_.prepare(world(sites=site, pois=unknowns((-1500, 0))), west_frozen)
        more = os_.prepare(world(sites=site, pois=unknowns((-1500, 0), (1400, 0), (1400, 20))), west_frozen)
        a = os_.score(plain, 1000, 0, prepared(plain, mining("iron_ore")))
        b = os_.score(more, 1000, 0, prepared(more, mining("iron_ore")))
        self.assertGreater(b["terms"]["reach_gain"], a["terms"]["reach_gain"])
        self.assertEqual(a["confidence"], b["confidence"])

    def test_reach_gain_off_when_drones_haul(self):
        for early in (True, False):
            weights, _reach = os_.phase_inputs([HOME], early, drones=True)
            self.assertEqual(weights["reach_gain"], 0.0)
        self.assertEqual(os_.phase_inputs([HOME], True, drones=False)[0]["reach_gain"], 9.0)
        self.assertEqual(os_.phase_inputs([HOME], False, drones=False)[0]["reach_gain"], 3.0)
        self.assertEqual(os_.WEIGHTS["reach_gain"], 3.0)  # drones=True must not mutate the shared tables
        self.assertEqual(os_.WEIGHTS_EARLY["reach_gain"], 9.0)


def geo_east(x, y):
    """Fake biome map: frozen west of x = 0, geothermal east of it."""
    return "frozen" if x < 0 else "geothermal"


def centred(cx, cy):
    """Anchor whose outpost centre is (cx, cy)."""
    half = os_.OUTPOST_PLACE_M / 2
    return (cx - half, cy + half)


class FutureTests(unittest.TestCase):
    """future: closeness to the best contact of each look-ahead fluid (outpost_needs.future_fluids())."""

    def row(self, ctx, cx, cy, future):
        x, y = centred(cx, cy)
        return os_.score(ctx, x, y, os_.prepare_want(ctx, os_.wants(mining("iron_ore"), PRESETS, future)))

    def term(self, ctx, cx, cy, future=("steam",)):
        return self.row(ctx, cx, cy, future)["terms"]["future"]

    def test_future_pulls_to_discovered_vent(self):
        ctx = os_.prepare(world(sites=[fluid_site(500, 0, "thermal", surveyed=False)]), geo_east)
        self.assertAlmostEqual(self.term(ctx, 250, 0), os_.WEIGHTS["future"] * 0.5, delta=0.01)
        self.assertEqual(self.term(ctx, -100, 0), 0.0)
        self.assertEqual(os_.WEIGHTS["future"], 3.0)
        self.assertEqual(os_.WEIGHTS_EARLY["future"], 3.0)

    def test_future_unknown_poi_needs_geothermal_biome(self):
        hot = os_.prepare(world(pois=unknowns((300, 0))), geo_east)
        self.assertGreater(self.term(hot, 250, 0), 0.0)
        cold = os_.prepare(world(pois=unknowns((300, 0))), lambda x, y: "frozen")
        self.assertEqual(self.term(cold, 250, 0), 0.0)

    def test_future_unknown_poi_uses_inferred_kinds(self):
        ctx = os_.prepare(world(pois=unknowns((300, 0))), geo_east)
        ctx["rows"][0]["kinds"] = {"thermal": 0.5, "water": 0.5}
        want = os_.prepare_want(ctx, os_.wants(mining("iron_ore"), PRESETS, ["steam"]))
        self.assertEqual([value for _x, _y, value in want["future_spots"]["steam"]], [0.5])

    def test_future_falls_back_to_geothermal_cell(self):
        ctx = os_.prepare(dict(world(), geothermal=[(400, 0)]), geo_east)
        expected = os_.WEIGHTS["future"] * os_.FUTURE_CELL_VALUE * (1 - 400 / os_.FUTURE_RANGE_M)
        self.assertAlmostEqual(self.term(ctx, 0, 0), expected, delta=0.01)
        water = self.term(ctx, 0, 0, ("water",))
        self.assertEqual(water, 0.0)  # the geothermal fallback is for steam only

    def test_future_empty_is_zero(self):
        ctx = os_.prepare(world(sites=[fluid_site(500, 0, "thermal", surveyed=False)]), geo_east)
        self.assertEqual(self.term(ctx, 450, 0, ()), 0.0)
        bare = os_.prepare(world(), lambda x, y: "frozen")
        self.assertEqual(self.term(bare, 450, 0, ("steam", "water")), 0.0)

    def test_future_ignores_stuck(self):
        ctx = os_.prepare(
            world(sites=[fluid_site(500, 0, "thermal", surveyed=False)], blocked=({(500, 0)}, set())),
            lambda x, y: "frozen",
        )
        self.assertEqual(self.term(ctx, 450, 0), 0.0)

    def test_future_mean_over_fluids(self):
        sites = [fluid_site(500, 0, "thermal", surveyed=False)]
        ctx = os_.prepare(world(sites=sites), geo_east)
        self.assertAlmostEqual(self.term(ctx, 500, 0, ("steam", "water")), os_.WEIGHTS["future"] * 0.5, delta=0.01)

    def test_future_out_of_confidence(self):
        sites = [mineral(450, 0, "iron_ore"), fluid_site(500, 0, "thermal", surveyed=False)]
        ctx = os_.prepare(world(sites=sites, pois=unknowns((350, 50))), geo_east)
        plain = self.row(ctx, 450, 0, ())
        ahead = self.row(ctx, 450, 0, ("steam",))
        self.assertGreater(ahead["terms"]["future"], 0.0)
        self.assertEqual(plain["confidence"], ahead["confidence"])

    def test_future_keeps_top_spots(self):
        sites = [fluid_site(100 * i, 0, "thermal", surveyed=False) for i in range(12)]
        ctx = os_.prepare(world(sites=sites), geo_east)
        want = os_.prepare_want(ctx, os_.wants(mining("iron_ore"), PRESETS, ["steam"]))
        self.assertEqual(len(want["future_spots"]["steam"]), os_.FUTURE_TOP)


class InferenceTests(unittest.TestCase):
    """Unresolved contacts typed by contact_inference (survey.unsupported_targets)."""

    POWER = {"biome": None, "roles": ["power"], "ores": []}
    ALL_BUT_GEO = [
        "research_hydrology_survey",
        "research_petroleum_survey",
        "research_exotic_husbandry",
        "research_deep_exotics",
    ]

    def test_single_kind_types_the_contact(self):
        ctx = os_.prepare(
            world(
                pois=[{"x": 400, "y": 400, "kind": "unknown"}], unsupported={"poi_400_400": {"reason": "tier_too_low"}}
            ),
            west_frozen,
        )
        row = ctx["rows"][0]
        self.assertEqual((row["level"], row["kind"], row["fluid"]), (2, "oil", "oil"))

    def test_several_kinds_become_the_contact_prior(self):
        ctx = os_.prepare(
            world(pois=[{"x": 400, "y": 400, "kind": "unknown"}], unsupported={"poi_400_400": research_locked()}),
            lambda x, y: None,
        )
        row = ctx["rows"][0]
        self.assertEqual(row["level"], 1)
        self.assertAlmostEqual(row["kinds"]["thermal"], 1 / 4)
        self.assertNotIn("mineral", row["kinds"])

    def test_geothermal_biome_types_a_research_locked_contact_as_thermal(self):
        ctx = os_.prepare(
            world(pois=[{"x": 400, "y": 400, "kind": "unknown"}], unsupported={"poi_400_400": research_locked()}),
            lambda x, y: "geothermal",
        )
        row = ctx["rows"][0]
        self.assertEqual((row["level"], row["kind"], row["fluid"]), (2, "thermal", "steam"))

    def test_uninformative_reason_leaves_the_contact_unknown(self):
        ctx = os_.prepare(
            world(
                pois=[{"x": 400, "y": 400, "kind": "unknown"}], unsupported={"poi_400_400": {"reason": "out_of_range"}}
            ),
            west_frozen,
        )
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
        self.assertGreater(
            os_.score(geo, 420, 430, prepared(geo, steam))["terms"]["fluid"],
            os_.score(flat, 420, 430, prepared(flat, steam))["terms"]["fluid"],
        )

    def test_only_geothermal_research_locked_means_a_thermal_vent(self):
        ctx = os_.prepare(
            world(
                pois=[{"x": 400, "y": 400, "kind": "unknown"}],
                unsupported={"poi_400_400": research_locked(self.ALL_BUT_GEO)},
            ),
            west_frozen,
        )
        row = ctx["rows"][0]
        self.assertEqual((row["level"], row["kind"], row["fluid"]), (2, "thermal", "steam"))


class BudgetTests(unittest.TestCase):
    """
    Worst-case atomic slice costs on a dense map: a contact every 100 m around
    the candidates plus surveyed sites in between (~130 per km2, several
    times the density of a whole map with every contact counted).
    """

    def dense(self):
        pois = [
            {"x": float(x), "y": float(y), "kind": "unknown"} for x in range(0, 900, 100) for y in range(0, 900, 100)
        ]
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
        want = os_.prepare_want(
            ctx,
            {
                "ores": ["iron_ore", "silicon", "cobalt"],
                "fluids": ["steam", "water", "oil"],
                "biome": "coastal",
                "biosites": True,
            },
        )
        anchors = [(x, y) for x in range(0, 900, 80) for y in range(0, 900, 80)]
        state = os_.score_init(ctx, anchors, want)
        worst = 0
        while True:
            done = [False]
            cost = ops(lambda: done.__setitem__(0, os_.score_step(state)))  # noqa: B023 (called within the iteration)
            worst = max(worst, cost)
            if done[0]:
                break
        self.assertLess(worst, ATOMIC_STEP_BUDGET)
        self.assertEqual(len(state["out"]), len(anchors))

    def test_score_step_fits_with_remote(self):
        far = [
            {"x": float(x), "y": float(y), "kind": "unknown"}
            for x in range(-880, 900, 125)
            for y in range(-880, 900, 125)
            if (x * x + y * y) ** 0.5 > 700
        ]
        base = self.dense()
        pois = [{"x": row["x"], "y": row["y"], "kind": "unknown"} for row in base["rows"] if row["level"] == 1]
        pois += far[:200]
        ctx = os_.prepare(world(outposts=[HOME, {"id": "o1", "x": 700.0, "y": 700.0}], pois=pois), west_frozen)
        self.assertGreater(len(ctx["remote"]), 30)
        want = prepared(ctx, mining("iron_ore"))
        anchors = [(x, y) for x in range(0, 900, 80) for y in range(0, 900, 80)]
        state = os_.score_init(ctx, anchors, want)
        worst = 0
        while True:
            done = [False]
            worst = max(worst, ops(lambda: done.__setitem__(0, os_.score_step(state))))  # noqa: B023 (called within the iteration)
            if done[0]:
                break
        self.assertLess(worst, ATOMIC_STEP_BUDGET)

    def test_remote_capped_to_top_clusters(self):
        far = [
            {"x": float(x), "y": float(y), "kind": "unknown"}
            for x in range(-880, 900, 50)
            for y in range(-880, 900, 50)
            if (x * x + y * y) ** 0.5 > 700
        ]
        sites = [fluid_site(-800 + 90 * i, -600, "thermal", surveyed=False) for i in range(10)]
        sites += [fluid_site(-800 + 90 * i, -800, "water", surveyed=False) for i in range(10)]
        total = len(far) + len(sites)
        ctx = os_.prepare(
            world(outposts=[HOME, {"id": "o1", "x": 700.0, "y": 700.0}], pois=far, sites=sites), west_frozen
        )
        self.assertEqual(len(ctx["remote"]), os_.REMOTE_TOP)
        self.assertEqual(ctx["remote_n"], sum([n for _x, _y, n in os_.remote_clusters(ctx["rows"], ctx["starts"])]))
        self.assertGreater(ctx["remote_n"], total // 2)
        want = os_.prepare_want(ctx, os_.wants(mining("iron_ore"), PRESETS, ["steam", "water"]))
        want["future_n"] = 16
        anchors = [(x, y) for x in range(0, 900, 80) for y in range(0, 900, 80)]
        state = os_.score_init(ctx, anchors, want)
        worst = 0
        while True:
            done = [False]
            worst = max(worst, ops(lambda: done.__setitem__(0, os_.score_step(state))))  # noqa: B023 (called within the iteration)
            if done[0]:
                break
        self.assertLess(worst, ATOMIC_STEP_BUDGET)

    def test_future_n_defers_a_finish(self):
        ctx = os_.prepare(world(), west_frozen)
        want = prepared(ctx, mining("iron_ore"))
        want["future_n"] = 50  # finish 22 + 25 units: one fits a slice after a start, two do not
        state = os_.score_init(ctx, [(100.0, 100.0), (200.0, 200.0)], want)
        start = os_._start

        def instant(st):
            start(st)
            st["acc"]["cell"] = st["acc"]["cells"]

        orig = os_._start
        os_._start = instant
        try:
            self.assertFalse(os_.score_step(state))  # the second finish would pass STEP_UNITS
            self.assertEqual(len(state["out"]), 1)
            self.assertTrue(os_.score_step(state))
            self.assertEqual(len(state["out"]), 2)
        finally:
            os_._start = orig

    def test_score_step_fits_with_wide_range(self):
        ctx = self.dense()
        ctx["range_m"] = 1500.0  # player-tunable mining range: a window far wider than the valued cells
        want = prepared(ctx, mining("iron_ore"))
        self.assertLess(want["window"], (int(2 * want["radius"] // os_.CELL_M) + 2) ** 2)
        anchors = [(x, y) for x in range(0, 900, 160) for y in range(0, 900, 160)]
        state = os_.score_init(ctx, anchors, want)
        worst = 0
        while True:
            done = [False]
            worst = max(worst, ops(lambda: done.__setitem__(0, os_.score_step(state))))  # noqa: B023 (called within the iteration)
            if done[0]:
                break
        self.assertLess(worst, ATOMIC_STEP_BUDGET)
        self.assertEqual(len(state["out"]), len(anchors))

    def test_start_lists_match_the_window_walk(self):
        ctx = self.dense()
        for range_m in (200.0, 1500.0):  # window scan, then the sorted-cells filter
            ctx["range_m"] = range_m
            want = prepared(ctx, mining("iron_ore"))
            state = os_.score_init(ctx, [(450, 450), (-700, 820)], want)
            for _ in range(2):
                os_._start(state)
                acc = state["acc"]
                cx, cy, radius = acc["cx"], acc["cy"], want["radius"]
                walk = [
                    want["valued"][(i, j)]
                    for i in range(int((cx - radius) // os_.CELL_M), int((cx + radius) // os_.CELL_M) + 1)
                    for j in range(int((cy - radius) // os_.CELL_M), int((cy + radius) // os_.CELL_M) + 1)
                    if (i, j) in want["valued"]
                ]
                self.assertEqual(acc["lists"], walk)

    def test_score_step_fits_with_future(self):
        base = self.dense()
        pois = [{"x": row["x"], "y": row["y"], "kind": "unknown"} for row in base["rows"] if row["level"] == 1]
        sites = [fluid_site(-800 + 90 * i, -600, "thermal", surveyed=False) for i in range(10)]
        sites += [fluid_site(-800 + 90 * i, -800, "water", surveyed=False) for i in range(10)]
        far = [{"x": float(x), "y": -300.0, "kind": "unknown"} for x in range(-880, 900, 125)]
        outposts = [HOME, {"id": "o1", "x": 700.0, "y": 700.0}]
        ctx = os_.prepare(world(outposts=outposts, pois=pois + far, sites=sites), west_frozen)
        want = os_.prepare_want(ctx, os_.wants(mining("iron_ore"), PRESETS, ["steam", "water"]))
        self.assertEqual([len(want["future_spots"][fluid]) for fluid in ("steam", "water")], [os_.FUTURE_TOP] * 2)
        anchors = [(x, y) for x in range(0, 900, 80) for y in range(0, 900, 80)]
        state = os_.score_init(ctx, anchors, want)
        worst = 0
        while True:
            done = [False]
            worst = max(worst, ops(lambda: done.__setitem__(0, os_.score_step(state))))  # noqa: B023 (called within the iteration)
            if done[0]:
                break
        self.assertLess(worst, ATOMIC_STEP_BUDGET)

    def test_future_slice_fits(self):
        ctx = self.dense()
        rows = ctx["rows"][: os_.VALUE_CHUNK]
        os_.future_rows(rows, ctx, ["steam", "water"])  # biome cache warm: the cold reads are game calls, not steps
        self.assertLess(ops(os_.future_rows, rows, ctx, ["steam", "water"]), ATOMIC_STEP_BUDGET)

    def test_stacked_contacts_split_mid_cell(self):
        pois = [{"x": 455.0, "y": 445.0, "kind": "unknown"}] * 200  # far more rows in one cell than a chunk takes
        ctx = os_.prepare(world(pois=pois), west_frozen)
        want = prepared(ctx, mining("iron_ore"))
        state = os_.score_init(ctx, [(450, 450)], want)
        worst = 0
        while True:
            done = [False]
            worst = max(worst, ops(lambda: done.__setitem__(0, os_.score_step(state))))  # noqa: B023 (called within the iteration)
            if done[0]:
                break
        self.assertLess(worst, ATOMIC_STEP_BUDGET)
        whole = os_.score(ctx, 450, 450, want)
        self.assertEqual(state["out"][0]["terms"], whole["terms"])

    def test_detail_slice_fits(self):
        ctx = self.dense()
        want = prepared(ctx, {"biome": "coastal", "roles": ["bio_coastal"]})
        rows = [os_.score(ctx, 450, 450, want)][: os_.DETAIL_CHUNK]
        os_.detail_slice([dict(rows[0], terms=dict(rows[0]["terms"]))], ctx, want)  # warm the biome cache
        self.assertLess(ops(os_.detail_slice, rows, ctx, want), ATOMIC_STEP_BUDGET)

    def test_value_slice_fits(self):
        ctx = self.dense()
        want = {
            "ores": ["iron_ore", "silicon", "cobalt"],
            "fluids": ["steam", "water", "oil"],
            "biome": "coastal",
            "biosites": True,
        }
        rows = ctx["rows"][: os_.VALUE_CHUNK]
        os_.value_rows(rows, ctx, want)  # biome cache warm: the cold reads are game calls, not steps
        self.assertLess(ops(os_.value_rows, rows, ctx, want), ATOMIC_STEP_BUDGET)


PIN_BUNDLES = (
    ("mine", mining("iron_ore", "silicon"), ["steam", "water"]),
    ("bio", {"biome": "coastal", "roles": ["bio_coastal", "drone_depot"], "ores": []}, []),
    ("store", {"roles": ["storage", "drone_depot"], "ores": []}, ["water"]),
    ("iron", mining("iron_ore"), []),
)


def pinned_ranks():
    """
    rank_sites() of PIN_BUNDLES in turn on one shared ctx (remote clusters,
    look-ahead fluids, demand, early weights, pipes, reach), each row as
    (x, y, score, confidence, biome, survey) with floats rounded to 9 places.
    """
    far = [
        {"x": float(x), "y": float(y), "kind": "unknown"}
        for x in range(-880, 900, 150)
        for y in range(-880, 900, 150)
        if (x * x + y * y) ** 0.5 > 650
    ]
    pois = far + unknowns(*[(x, y) for x in range(-400, 400, 230) for y in range(-400, 400, 230)])
    sites = [mineral(x + 50, y + 50, "iron_ore") for x in range(-300, 300, 200) for y in range(-300, 300, 200)]
    sites += [mineral(-450, 150, "silicon", purity="rich"), mineral(520, -80, "silicon", surveyed=False)]
    sites += [fluid_site(-500 + 190 * i, -200, "water", surveyed=False) for i in range(5)]
    sites += [fluid_site(250, 350, "thermal")]
    outposts = [
        HOME,
        {"id": "o1", "x": 300.0, "y": 200.0, "home": False},
        {"id": "o2", "x": -200.0, "y": 300.0, "home": False},
    ]
    data = dict(world(outposts=outposts, pois=pois, sites=sites, ghosts=[(100.0, -400.0)]))
    data["weights"] = os_.WEIGHTS_EARLY
    data["demand"] = {"iron_ore": 0.6, "silicon": 0.3}
    data["geothermal"] = [(-300.0, -300.0)]
    data["pipes"] = [(tx, 8) for tx in range(-20, 20)]
    data["reach"] = {"points": [(0.0, 0.0), (300.0, 200.0)], "m": 700.0}
    ctx = os_.prepare(data, west_frozen)
    out = {}
    for name, bundle, future in PIN_BUNDLES:
        want = os_.prepare_want(ctx, os_.wants(bundle, PRESETS, future))
        rows = os_.rank_sites(bundle, ctx, PRESETS, os_.REFINE_TOP, want)
        out[name] = [
            (row["x"], row["y"], round(row["score"], 9), round(row["confidence"], 9), row["biome"], row["survey"])
            for row in rows
        ]
    return out


PINNED_RANKS = {
    "bio": [
        (220.0, 200.0, 6.164986033, 1.0, "coastal", False),
        (220.0, 180.0, 6.008020979, 1.0, "coastal", False),
        (200.0, 200.0, 5.999588136, 1.0, "coastal", False),
        (220.0, 220.0, 5.96986239, 1.0, "coastal", False),
        (100.0, -320.0, 5.054558397, 1.0, "coastal", False),
    ],
    "iron": [
        (-240.0, 180.0, 22.995581954, 1.0, "frozen", False),
        (-300.0, 280.0, 22.902715678, 0.5, "frozen", False),
        (-240.0, 200.0, 22.902547009, 1.0, "frozen", False),
        (-300.0, 260.0, 22.876154903, 0.5, "frozen", False),
        (-220.0, 200.0, 22.867393014, 1.0, "frozen", False),
    ],
    "mine": [
        (60.0, -280.0, 43.384498229, 0.666666667, "coastal", False),
        (-200.0, 200.0, 43.275027649, 0.666666667, "frozen", False),
        (-220.0, 200.0, 43.247533748, 0.666666667, "frozen", False),
        (-240.0, 200.0, 43.237067437, 0.666666667, "frozen", False),
        (80.0, -280.0, 43.227414158, 0.666666667, "coastal", False),
    ],
    "store": [
        (60.0, -280.0, 4.614498229, 1.0, "coastal", False),
        (80.0, -260.0, 4.566764472, 1.0, "coastal", False),
        (60.0, -260.0, 4.556291736, 1.0, "coastal", False),
        (60.0, -240.0, 4.498357494, 1.0, "coastal", False),
        (80.0, -280.0, 4.450827825, 1.0, "coastal", False),
    ],
}


class RankPinTests(unittest.TestCase):
    """rank_sites() results pinned before the scoring hoists (perf Vector 6): any change in a rank is a regression."""

    def test_ranks_unchanged(self):
        self.assertEqual(pinned_ranks(), PINNED_RANKS)


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


DISCOVERED = [
    _Site(100.0, 100.0, "mineral", True, item_id="cobalt", purity="rich", hardness=3),
    _Site(200.0, 200.0, "exotic", True, fluid="raw_chlorine"),
    _Site(250.0, 250.0, "water", False),
]


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
        ctx = os_.prepare(dict(world(), pipes=[(45, 50)]), west_frozen)  # footprint tiles x 39..42, buffer 35..46
        self.assertEqual(os_.check(ctx, 400, 500, None, True), "pipe_buffer")
        self.assertIsNone(os_.check(ctx, 400, 500, None, False))

    def test_pipe_just_outside_buffer_passes(self):
        ctx = os_.prepare(
            dict(world(), pipes=[(47, 50), (34, 50)]), west_frozen
        )  # footprint tiles 39..42, buffer 35..46
        self.assertIsNone(os_.check(ctx, 400, 500, None, True))
        ctx = os_.prepare(dict(world(), pipes=[(46, 50)]), west_frozen)
        self.assertEqual(os_.check(ctx, 400, 500, None, True), "pipe_buffer")
