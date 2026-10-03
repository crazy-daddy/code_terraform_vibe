"""Tests for autoplay/lib/outpost_needs.py (founding planner need model: now/soon/later needs, merge onto existing outposts)."""
import unittest

import harness
from game_stubs import Recipe
import outpost_needs as on
import autoplay_roles as roles
from grid_geom import extractor_box

ALL_KITS = {"smelter", "fabricator", "warehouse", "drone_station_kit", "weather_station", "essence_liquifier",
            "bio_collector", "bio_lab", "bio_exchange", "bio_luminizer", "dna_sequencer", "bio_caster",
            "bio_conditioner", "refiner"}


def outpost(oid, biome, x=0.0, y=0.0, roles=None, types=None, used=None, capacity=20, home=False):
    types = dict(types or {})
    return {"id": oid, "x": x, "y": y, "biome": biome, "home": home, "roles": list(roles or []), "types": types,
            "used": sum(types.values()) if used is None else used, "capacity": capacity}


def snap(outposts, **extra):
    base = {"outposts": outposts, "kits": set(ALL_KITS), "bio_orders": {}, "essences_required": None,
            "ore_wanted": [], "ore_sites": [], "fluid_sites": [], "fluids_in": [], "range_m": 200.0}
    base.update(extra)
    return base


def roles_of(needs, urgency=None):
    return [n["role"] for n in needs if urgency is None or n["urgency"] == urgency]


HOME = outpost("outpost_home", "frozen", home=True, capacity=25, types={"smelter": 2, "fabricator": 3})


class NeedTests(unittest.TestCase):
    def test_later_checklist_skips_frozen_bio_and_covered_roles(self):
        coastal = outpost("outpost_1", "coastal", 300, 0, roles=["weather_coastal"], types={"essence_liquifier": 1})
        needs = on.needs(snap([HOME, coastal]))
        later = roles_of(needs, "later")
        self.assertNotIn("bio_frozen", later)
        self.assertIn("bio_coastal", later)
        self.assertNotIn("weather_coastal", later)     # designated
        self.assertNotIn("liquifier_coastal", later)   # observed in its biome
        self.assertIn("weather_frozen", later)

    def test_observed_biome_role_in_wrong_biome_does_not_cover(self):
        deep = outpost("outpost_1", "deep", types={"weather_station": 1})
        self.assertFalse(on.covers(deep, "weather_coastal"))
        self.assertTrue(on.covers(deep, "weather_deep"))
        self.assertTrue(on.covers(outpost("o", "deep", types={"refiner": 1}), "refinery"))

    def test_bio_orders_without_chain_are_now(self):
        needs = on.needs(snap([HOME], bio_orders={"coastal": 2, "frozen": 1}))
        self.assertEqual(roles_of(needs, "now"), ["bio_coastal", "bio_frozen"])
        home = dict(HOME, types={"bio_collector": 1, "bio_lab": 1, "bio_exchange": 1})
        self.assertEqual(roles_of(on.needs(snap([home], bio_orders={"frozen": 1})), "now"), [])

    def test_locked_role_moves_to_later(self):
        kits = set(ALL_KITS) - {"bio_luminizer"}
        needs = on.needs(snap([HOME], kits=kits, bio_orders={"coastal": 1}))
        need = [n for n in needs if n["role"] == "bio_coastal"][0]
        self.assertEqual((need["urgency"], need["locked"]), ("later", True))

    def test_essence_deficit_prefers_settled_biomes(self):
        deep = outpost("outpost_1", "deep", 400, 0, types={"warehouse": 1})
        home = dict(HOME, roles=["liquifier_frozen"])
        needs = on.needs(snap([home, deep], essences_required=2))
        self.assertEqual(roles_of(needs, "now"), ["liquifier_deep"])
        self.assertEqual(roles_of(needs, "soon"), ["liquifier_coastal"])

    def test_unreached_ore_is_soon_mining(self):
        sites = [{"id": "s1", "item": "cobalt", "x": 800.0, "y": 0.0}, {"id": "s2", "item": "iron_ore", "x": 50.0, "y": 0.0}]
        needs = on.needs(snap([HOME], ore_wanted=["cobalt", "iron_ore", "lead_ore"], ore_sites=sites))
        mining = [n for n in needs if n["role"] == "mining"][0]
        self.assertEqual((mining["urgency"], mining["ores"]), ("soon", ["cobalt"]))   # lead: no surveyed site

    def test_full_factory_hosts_need_another(self):
        home = dict(HOME, used=25)
        self.assertIn("factory", roles_of(on.needs(snap([home])), "soon"))
        self.assertNotIn("factory", roles_of(on.needs(snap([HOME]))))

    def test_refinery_only_for_taken_fluid_with_raw_site(self):
        raw = [{"id": "f1", "fluid": "raw_chlorine", "x": 100.0, "y": 0.0, "box": extractor_box(100.0, 0.0)}]
        home = dict(HOME, roles=["wildlife_chlorine"])
        needs = on.needs(snap([home], fluid_sites=raw, fluids_in=["chlorine"]))
        need = [n for n in needs if n["role"] == "refinery"][0]
        self.assertEqual((need["urgency"], need["found"]), ("soon", False))
        self.assertIn("chlorine", need["why"])
        self.assertNotIn("refinery", roles_of(on.needs(snap([home], fluid_sites=raw))))


class HostTests(unittest.TestCase):
    def test_merge_onto_existing_outpost_before_founding(self):
        coastal = outpost("outpost_1", "coastal", 300, 0, types={"warehouse": 2})
        s = snap([HOME, coastal], bio_orders={"coastal": 1})
        plan = on.plan_hosts(on.needs(s), s)
        self.assertEqual([d["outpost"] for d in plan["designate"]], ["outpost_1"])
        self.assertEqual(plan["designate"][0]["roles"], ["bio_coastal", "drone_depot"])
        self.assertEqual(plan["found"], [])

    def test_biome_lock_founds_new_outpost(self):
        s = snap([HOME], bio_orders={"volcanic": 1})
        plan = on.plan_hosts(on.needs(s), s)
        self.assertEqual(plan["designate"], [])
        self.assertEqual([(b["biome"], b["roles"]) for b in plan["found"]], [("volcanic", ["bio_volcanic", "drone_depot"])])

    def test_over_cap_with_penalized_machine_rejected(self):
        coastal = outpost("outpost_1", "coastal", 300, 0, types={"smelter": 1}, used=18)
        s = snap([coastal], bio_orders={"coastal": 1})
        added, reason, _extra = on.host_check(on.needs(s)[0], coastal, s)
        self.assertIsNone(added)
        self.assertTrue((reason or "").startswith("over cap"), reason)

    def test_exempt_only_role_may_exceed_cap(self):
        full = outpost("outpost_1", "deep", 300, 0, types={"warehouse": 25}, used=25)
        need = on._need("weather_deep", "soon", "test")
        self.assertEqual(on.host_check(need, full, snap([full]))[0], ["weather_deep"])

    def test_home_reserved_once_wildlife_is_unlocked(self):
        need = on._need("liquifier_frozen", "now", "test")
        early = dict(HOME, used=5)
        self.assertEqual(on.host_check(need, early, snap([early]))[0], ["liquifier_frozen", "drone_depot"])
        late = snap([early], kits=ALL_KITS | {"habitat"})
        self.assertEqual(on.host_check(need, early, late)[1], "home reserved for farm and wildlife")
        self.assertEqual(on.host_check(on._need("weather_frozen", "now", "t"), early, late)[1],
                         "home reserved for farm and wildlife")
        housed = dict(early, types={"habitat": 1})
        self.assertTrue(on.home_reserved(housed, set()))

    def test_home_counts_warehouses_too(self):
        home = dict(HOME, used=20, types={})
        s = snap([home], stock={"smelter": ["a", "b", "c", "d", "e", "f"]})
        # Smelter + Drone Depot + 2 Warehouses (6 slots) = 4: 24 of 25
        self.assertEqual(on.host_check(on._need("smelter", "soon", "t"), home, s)[2], 4)
        self.assertIsNone(on.host_check(on._need("smelter", "soon", "t"), dict(home, used=22), s)[0])

    def test_refinery_goes_only_near_raw_site_and_never_founds(self):
        far = outpost("outpost_1", "deep", 600, 600)
        near = outpost("outpost_2", "deep", 90, 0)
        raw = [{"id": "f1", "fluid": "raw_cryofluid", "x": 100.0, "y": 0.0, "box": extractor_box(100.0, 0.0)}]
        s = snap([far, near], fluid_sites=raw, fluids_in=["chlorine"])
        need = on._need("refinery", "soon", "t")
        plan = on.plan_hosts([need], s)
        self.assertEqual([d["outpost"] for d in plan["designate"]], ["outpost_2"])
        plan = on.plan_hosts([need], snap([far], fluid_sites=raw))
        self.assertEqual((plan["designate"], plan["found"]), ([], []))

    def test_later_needs_make_no_proposal(self):
        s = snap([HOME])
        plan = on.plan_hosts(on.needs(s), s)
        self.assertEqual((plan["designate"], plan["found"]), ([], []))

    def test_host_counts_its_new_roles_for_the_next_need(self):
        deep = outpost("outpost_1", "deep", 300, 0, types={"warehouse": 1}, used=17)
        needs = [on._need("liquifier_deep", "now", "a"), on._need("bio_deep", "now", "b")]
        plan = on.plan_hosts(needs, snap([deep]))
        self.assertEqual(plan["designate"][0]["roles"], ["liquifier_deep", "drone_depot"])
        self.assertEqual([b["roles"] for b in plan["found"]], [["bio_deep", "drone_depot"]])

    def test_found_bundles_group_by_biome_and_mining(self):
        needs = [on._need("mining", "soon", "m", ores=["cobalt"]), on._need("bio_deep", "now", "b"),
                 on._need("liquifier_deep", "now", "l"), on._need("factory", "soon", "f")]
        bundles = on.found_bundles(needs)
        self.assertEqual([(b["urgency"], b["biome"], b["roles"]) for b in bundles],
                         [("now", "deep", ["bio_deep", "liquifier_deep", "drone_depot"]),
                          ("soon", None, ["factory", "drone_depot"]),
                          ("soon", None, ["mining", "drone_depot"])])
        self.assertEqual(bundles[2]["ores"], ["cobalt"])


class WarehouseSlotTests(unittest.TestCase):
    STOCK = {"smelter": ["iron_ore", "cobalt", "iron_ingot", "cobalt_ingot"], "factory": ["iron_ingot", "cobalt_ingot"]}

    def test_stock_slots_share_items_between_roles(self):
        self.assertEqual(roles.stock_slots(["smelter"], self.STOCK), 4)
        self.assertEqual(roles.stock_slots(["smelter", "factory"], self.STOCK), 4 + roles.FACTORY_BUFFER_SLOTS)
        self.assertEqual(roles.stock_slots(["mining", "smelter"], dict(self.STOCK, mining=["cobalt"])), 4)
        self.assertEqual(roles.stock_slots(["smelter"], {}), roles.SMELTER_FALLBACK_SLOTS)
        self.assertEqual(roles.stock_slots(["drone_depot", "weather_deep", "storage"], {}), 0)

    def test_site_slots_count_warehouses_beyond_standing_slots(self):
        self.assertEqual(roles.site_slots(["factory", "drone_depot"], self.STOCK, 0, 5), (5, 1, 3))   # 12 slots
        self.assertEqual(roles.site_slots(["factory", "drone_depot"], self.STOCK, 10, 5), (3, 1, 1))
        self.assertEqual(roles.site_slots(["factory", "drone_depot"], self.STOCK, 0, 15), (3, 1, 1))
        self.assertEqual(roles.site_slots(["feed"], {}, 0, 15), (3, 1, 2))   # 30 life forms + Forage fallback
        self.assertEqual(roles.site_slots(["mining"], {"mining": ["cobalt"]}, 0, 5), (1, 0, 1))

    def test_merge_counts_warehouses_against_the_cap(self):
        def host(used):
            return outpost("outpost_1", "deep", 300, 0, types={"warehouse": 1}, used=used)
        need = on._need("smelter", "soon", "t")
        s = snap([host(0)], stock={"smelter": ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l"]})
        # 12 slots, 5 standing: 2 new Warehouses + Smelter + Drone Depot = 4 buildings
        self.assertEqual(on.host_check(need, host(16), s)[2], 4)
        added, reason, _extra = on.host_check(need, host(17), s)
        self.assertIsNone(added)
        self.assertIn("2 new Warehouse(s)", reason or "")

    def test_bio_slots_match_bio_and_reagent_code(self):
        import bio
        import outpost_reagents
        self.assertEqual(roles.BIO_STOCK_SLOTS,
                         bio.MAX_LOCAL_BIO_ARTIFACTS + len(outpost_reagents.DEFAULT_REAGENT_STOCK_TARGETS))
        self.assertEqual(roles.stock_slots(["bio_deep"], {}), roles.BIO_STOCK_SLOTS)

    def test_feed_stock_only_from_complete_recipe_list(self):
        from wildlife_data import SPECIES
        from wildlife_common import recipe_of
        recipes = {recipe_of(s): {"forage": 100, "form_" + s: 1} for s in SPECIES}
        got = on.feed_stock({"feed_maker_1": {"recipes": recipes}})
        self.assertEqual(len(got["feed"]), len(SPECIES) + 1)
        partial = dict(list(recipes.items())[:2])
        self.assertEqual(on.feed_stock({"feed_maker_1": {"recipes": partial}}), {})
        self.assertEqual(roles.stock_slots(["feed"], on.feed_stock({})), roles.FEED_FALLBACK_SLOTS)
        self.assertEqual(on.feed_stock(None), {})

    def test_smelter_stock_only_when_every_ore_smelts(self):
        from outpost_mining import RAW_ORE_ITEM_IDS
        full = [Recipe("smelt_" + ore, {ore: 2}, ore + "_out") for ore in RAW_ORE_ITEM_IDS]
        got = on.smelter_stock(full)
        self.assertEqual(len(got["smelter"]), 2 * len(RAW_ORE_ITEM_IDS))
        self.assertEqual(len(got["factory"]), len(RAW_ORE_ITEM_IDS))
        self.assertEqual(on.smelter_stock(full[:1]), {})   # Large Warehouse: end state, incomplete
        early = on.smelter_stock(full[:2], large=False)       # small Warehouses: what is unlocked now
        self.assertEqual((len(early["smelter"]), len(early["factory"])), (4, 2))
        self.assertEqual(on.smelter_stock([], large=False), {})

    def test_liquifier_one_slot_per_life_form(self):
        self.assertEqual(roles.stock_slots(["liquifier_deep"], {}), 6)

    def test_found_bundle_reports_buildings(self):
        s = snap([HOME], stock=self.STOCK, per_warehouse=5)
        bundle = on.found_bundles([on._need("factory", "soon", "f")], s)[0]
        self.assertEqual(bundle["slots"], {"counted": 5, "penalized": 1, "warehouses": 3})
        self.assertFalse(bundle["over_cap"])


if __name__ == "__main__":
    unittest.main()
