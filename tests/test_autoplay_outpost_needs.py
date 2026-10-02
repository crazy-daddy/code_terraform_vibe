"""Tests for autoplay/lib/outpost_needs.py (founding planner need model: now/soon/later needs, merge onto existing outposts)."""
import unittest

import harness
import outpost_needs as on
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
        self.assertFalse(on.covers(outpost("o", "deep", types={"refiner": 1}), "refinery_chlorine"))

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
        need = [n for n in needs if n["role"] == "refinery_chlorine"][0]
        self.assertEqual((need["urgency"], need["found"]), ("soon", False))
        self.assertNotIn("refinery_chlorine", roles_of(on.needs(snap([home], fluid_sites=raw))))


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
        added, reason = on.host_check(on.needs(s)[0], coastal, s)
        self.assertIsNone(added)
        self.assertTrue((reason or "").startswith("over cap"), reason)

    def test_exempt_only_role_may_exceed_cap(self):
        full = outpost("outpost_1", "deep", 300, 0, types={"warehouse": 25}, used=25)
        need = on._need("weather_deep", "soon", "test")
        self.assertEqual(on.host_check(need, full, snap([full]))[0], ["weather_deep"])

    def test_home_takes_no_penalized_role(self):
        need = on._need("liquifier_frozen", "now", "test")
        self.assertEqual(on.host_check(need, HOME, snap([HOME]))[1], "home slots reserved")
        self.assertEqual(on.host_check(on._need("weather_frozen", "now", "t"), HOME, snap([HOME]))[0], ["weather_frozen"])

    def test_refinery_goes_only_near_raw_site_and_never_founds(self):
        far = outpost("outpost_1", "deep", 600, 600)
        near = outpost("outpost_2", "deep", 90, 0)
        raw = [{"id": "f1", "fluid": "raw_chlorine", "x": 100.0, "y": 0.0, "box": extractor_box(100.0, 0.0)}]
        s = snap([far, near], fluid_sites=raw, fluids_in=["chlorine"])
        need = on._need("refinery_chlorine", "soon", "t")
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


if __name__ == "__main__":
    unittest.main()
