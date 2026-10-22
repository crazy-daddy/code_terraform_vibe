"""Tests for autoplay/lib/outpost_needs.py (founding planner need model: now/soon/later needs, merge onto existing outposts)."""

import unittest
from unittest import mock

import autoplay_roles as roles
import harness  # noqa: F401 (side effect: installs game builtins and lib paths)
import machine_activity
import outpost_needs as on
from archive import archive
from game_stubs import Recipe
from grid_geom import extractor_box

ALL_KITS = {
    "smelter",
    "fabricator",
    "warehouse",
    "drone_station_kit",
    "weather_station",
    "essence_liquifier",
    "bio_collector",
    "bio_lab",
    "bio_exchange",
    "bio_luminizer",
    "dna_sequencer",
    "bio_caster",
    "bio_conditioner",
    "refiner",
}


def outpost(oid, biome, x=0.0, y=0.0, roles=None, types=None, used=None, capacity=20, home=False):
    types = dict(types or {})
    return {
        "id": oid,
        "x": x,
        "y": y,
        "biome": biome,
        "home": home,
        "roles": list(roles or []),
        "types": types,
        "used": sum(types.values()) if used is None else used,
        "capacity": capacity,
    }


def snap(outposts, **extra):
    base = {
        "outposts": outposts,
        "kits": set(ALL_KITS),
        "bio_orders": {},
        "essences_required": None,
        "ore_wanted": [],
        "ore_sites": [],
        "fluid_sites": [],
        "fluids_in": [],
        "range_m": 200.0,
    }
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
        self.assertNotIn("weather_coastal", later)  # designated
        self.assertNotIn("liquifier_coastal", later)  # observed in its biome
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
        sites = [
            {"id": "s1", "item": "cobalt", "x": 800.0, "y": 0.0},
            {"id": "s2", "item": "iron_ore", "x": 50.0, "y": 0.0},
        ]
        needs = on.needs(snap([HOME], ore_wanted=["cobalt", "iron_ore", "lead_ore"], ore_sites=sites))
        mining = [n for n in needs if n["role"] == "mining"][0]
        self.assertEqual((mining["urgency"], mining["ores"]), ("soon", ["cobalt"]))  # lead: no surveyed site
        drilled = [dict(sites[0], drill="mining_drill_1"), sites[1]]
        self.assertNotIn(
            "mining", roles_of(on.needs(snap([HOME], ore_wanted=["cobalt", "iron_ore"], ore_sites=drilled)))
        )  # drones fetch from the drill

    def test_full_factory_hosts_need_another_only_when_busy(self):
        home = dict(HOME, used=25)
        self.assertNotIn("factory", roles_of(on.needs(snap([home]))))  # busy share unknown: no need
        idle = snap([home], activity={"fabricator": 0.3, "smelter": 0.3})
        self.assertNotIn("factory", roles_of(on.needs(idle)))
        busy = snap([home], activity={"fabricator": 0.8, "smelter": 0.2})
        self.assertEqual(roles_of(on.needs(busy), "soon"), ["factory"])
        nearly = snap([dict(HOME, used=18)], activity={"fabricator": 0.8})  # 18/25 = 72 %: full enough
        self.assertIn("factory", roles_of(on.needs(nearly), "soon"))
        self.assertNotIn("factory", roles_of(on.needs(snap([HOME], activity={"fabricator": 0.9}))))

    def test_third_factory_host_needs_more_busy(self):
        a = outpost("outpost_1", "deep", 300, 0, types={"fabricator": 2}, used=20)
        b = outpost("outpost_2", "coastal", -300, 0, types={"fabricator": 2}, used=20)
        self.assertNotIn("factory", roles_of(on.needs(snap([a, b], activity={"fabricator": 0.8}))))
        self.assertIn("factory", roles_of(on.needs(snap([a, b], activity={"fabricator": 0.95})), "soon"))

    def test_first_factory_host_off_home(self):
        home = outpost("outpost_home", "frozen", home=True, capacity=25, types={"smelter": 1})
        phase = {"research": {on.OUTPOSTS_RESEARCH, on.FABRICATOR_RESEARCH}, "pillars": {}, "history": {}}
        needs = on.needs(snap([home], phase=phase))
        first = [n for n in needs if n["role"] in ("smelter", "factory")]
        self.assertEqual(sorted(n["role"] for n in first), ["factory", "smelter"])
        self.assertTrue(all(n["urgency"] == "now" and n["off_home"] for n in first))
        self.assertEqual([n for n in first if n["role"] == "smelter"][0]["ores"], list(on.EARLY_ORES))
        plan = on.plan_hosts(needs, snap([home], phase=phase))
        self.assertEqual(plan["designate"], [])
        self.assertEqual(plan["found"][0]["roles"], ["factory", "smelter", "drone_depot", "charging"])
        self.assertEqual(plan["found"][0]["ores"], ["iron_ore", "silicon"])
        self.assertEqual(plan["found"][0]["blocked_by"], [on.FABRICATOR_RESEARCH])
        # Fabricator still locked, TP rising: soon by ETA, kit lock does not demote it
        locked = {
            "research": {on.OUTPOSTS_RESEARCH},
            "tp": 120000,
            "pillars": {},
            "history": {"tp": [[0, 110000.0], [36000, 120000.0]]},
        }
        needs = on.needs(snap([home], phase=locked, kits=set(ALL_KITS) - {"fabricator"}))
        factory = [n for n in needs if n["role"] == "factory"][0]
        self.assertEqual(
            (factory["urgency"], factory["locked"], factory["blocked_by"]), ("now", True, on.FABRICATOR_RESEARCH)
        )
        # a factory outpost standing: the second host is a soon need, and home takes no factory role beside it
        fab = outpost("outpost_1", "deep", 300, 0, roles=["factory"], types={"fabricator": 1}, used=20)
        needs = on.needs(snap([home, fab], phase=phase, activity={"fabricator": 0.9}))
        second = [n for n in needs if n["role"] in ("smelter", "factory")]
        self.assertEqual(sorted(n["role"] for n in second), ["factory", "smelter"])
        self.assertTrue(all(n["urgency"] == "soon" and n["off_home"] for n in second))
        self.assertEqual([n for n in second if n["role"] == "smelter"][0]["ores"], list(on.EARLY_ORES))
        plan = on.plan_hosts([on._need("factory", "soon", "x")], snap([home, fab], phase=phase))
        self.assertEqual(plan["designate"], [])
        self.assertIn(
            ("factory", "outpost_home", "home takes no factory role beside a factory outpost"), plan["rejected"]
        )

    def test_second_factory_host_waits_for_the_fabricator(self):
        home = outpost("outpost_home", "frozen", home=True, capacity=25)
        fab = outpost("outpost_1", "deep", 300, 0, roles=["smelter"], types={"smelter": 1})
        phase = {"research": {on.OUTPOSTS_RESEARCH}, "pillars": {}, "history": {}}
        needs = on.lookahead(snap([home, fab], phase=phase))
        self.assertEqual([n for n in needs if n["role"] in ("smelter", "factory")], [])

    def test_second_factory_host_stops_at_max(self):
        phase = {"research": {on.OUTPOSTS_RESEARCH, on.FABRICATOR_RESEARCH}, "pillars": {}, "history": {}}
        a = outpost("outpost_1", "deep", 300, 0, roles=["factory"], types={"fabricator": 1}, used=20)
        b = outpost("outpost_2", "coastal", -300, 0, roles=["factory"], types={"fabricator": 1}, used=20)
        needs = on.lookahead(snap([HOME, a, b], phase=phase))
        self.assertNotIn("smelter", roles_of(needs))
        self.assertNotIn("factory", roles_of(needs))

    def test_charging_in_bundles_before_drones(self):
        bundle = on.found_bundles([on._need("factory", "soon", "f")], snap([HOME]))[0]
        self.assertEqual(bundle["roles"], ["factory", "drone_depot", "charging"])
        bundle = on.found_bundles([on._need("factory", "soon", "f")], snap([HOME], drones=True))[0]
        self.assertEqual(bundle["roles"], ["factory", "drone_depot"])

    def test_power_near_vent_before_thermal_cap(self):
        vent = [{"id": "v1", "fluid": "steam", "x": 500.0, "y": 0.0, "box": extractor_box(500.0, 0.0)}]
        phase = {
            "research": {on.OUTPOSTS_RESEARCH},
            "pillars": {"pressure": {"value": 2.0, "target": 100.0}},
            "history": {"pressure": [[0, 1.0], [36000 * 5, 2.0]]},
        }
        needs = on.needs(snap([HOME], fluid_sites=vent, phase=phase))  # 0.5 kPa left at 0.2 kPa/h: ~2.5 h
        power = [n for n in needs if n["role"] == "power"][0]
        self.assertEqual(
            (power["urgency"], power["blocked_by"], power["site_fluid"]), ("now", on.THERMAL_CAP_RESEARCH, "steam")
        )
        slow = dict(phase, history={"pressure": [[0, 1.9], [36000 * 50, 2.0]]})  # ~250 h away
        self.assertEqual(
            [n["urgency"] for n in on.needs(snap([HOME], fluid_sites=vent, phase=slow)) if n["role"] == "power"],
            ["later"],
        )
        near = outpost("outpost_1", "geothermal", 490, 0)
        self.assertNotIn("power", roles_of(on.needs(snap([HOME, near], fluid_sites=vent, phase=phase))))
        far = outpost("outpost_1", "geothermal", 900, 0)
        plan = on.plan_hosts([power], snap([HOME, far], fluid_sites=vent, phase=phase))
        self.assertEqual(plan["designate"], [])
        self.assertEqual(plan["found"][0]["roles"], ["power", "charging"])
        plan = on.plan_hosts([power], snap([HOME, near], fluid_sites=vent, phase=phase))
        self.assertEqual(plan["designate"][0]["outpost"], "outpost_1")

    def test_power_on_discovered_vent(self):
        phase = {
            "research": {on.OUTPOSTS_RESEARCH},
            "pillars": {"pressure": {"value": 2.0, "target": 100.0}},
            "history": {"pressure": [[0, 1.0], [36000 * 5, 2.0]]},
        }
        vent = [{"id": "t1", "x": 500.0, "y": 0.0}]
        far = outpost("outpost_1", "geothermal", 900, 0)
        needs = on.needs(snap([HOME, far], thermal_sites=vent, phase=phase))
        power = [n for n in needs if n["role"] == "power"][0]
        self.assertEqual((power["site_fluid"], power["urgency"], power["survey_first"]), ("steam", "now", True))

    def test_power_discovered_vent_hosted(self):
        vent = [{"id": "t1", "x": 500.0, "y": 0.0}]
        phase = {"research": {on.OUTPOSTS_RESEARCH}, "pillars": {}, "history": {}}
        away = outpost("outpost_2", "geothermal", 900, 0)
        self.assertIn("power", roles_of(on.needs(snap([HOME, away], thermal_sites=vent, phase=phase))))
        near = outpost("outpost_1", "geothermal", 490, 0)
        self.assertNotIn("power", roles_of(on.needs(snap([HOME, near], thermal_sites=vent, phase=phase))))

    def test_surveyed_vent_no_survey_first(self):
        vent = [{"id": "v1", "fluid": "steam", "x": 500.0, "y": 0.0, "box": extractor_box(500.0, 0.0)}]
        phase = {"research": {on.OUTPOSTS_RESEARCH}, "pillars": {}, "history": {}}
        power = [n for n in on.needs(snap([HOME], fluid_sites=vent, phase=phase)) if n["role"] == "power"][0]
        self.assertFalse(power.get("survey_first"))
        both = on.needs(snap([HOME], fluid_sites=vent, phase=phase, thermal_sites=[{"id": "v1", "x": 500.0, "y": 0.0}]))
        self.assertEqual(len([n for n in both if n["role"] == "power"]), 1)

    def test_bundle_carries_survey_first(self):
        need = on._need("power", "now", "x", site_fluid="steam", survey_first=True)
        self.assertTrue(on.found_bundles([need], snap([HOME]))[0]["survey_first"])
        self.assertFalse(on.found_bundles([on._need("power", "now", "x")], snap([HOME]))[0]["survey_first"])

    def test_terraform_host_when_slots_run_out(self):
        home = dict(HOME, used=24)
        tight = outpost("outpost_1", "deep", 300, 0, used=19)
        phase = {"research": {on.OUTPOSTS_RESEARCH}, "pillars": {}, "history": {}}
        kits = set(ALL_KITS) | {"oxygen_generator"}
        self.assertIn("terraform", roles_of(on.needs(snap([home, tight], phase=phase, kits=kits)), "soon"))
        self.assertNotIn(
            "terraform",
            roles_of(on.needs(snap([home, outpost("outpost_1", "deep", 300, 0, used=10)], phase=phase, kits=kits))),
        )
        done = {
            "research": {on.OUTPOSTS_RESEARCH},
            "pillars": {p: {"value": 1, "target": 1, "complete": True} for p in ("temperature", "oxygen", "pressure")},
            "history": {},
        }
        self.assertNotIn("terraform", roles_of(on.needs(snap([home, tight], phase=done, kits=kits))))

    def test_essence_chain_leaves_home_before_wildlife(self):
        home = outpost(
            "outpost_home", "frozen", home=True, capacity=25, types={"biomass_mixer": 1, "essence_liquifier": 1}
        )
        phase = {
            "research": {on.OUTPOSTS_RESEARCH},
            "pillars": {"plants": {"value": 2000000.0, "target": 5000000.0}},
            "history": {"plants": [[0, 1900000.0], [36000, 2000000.0]]},
        }
        needs = on.needs(snap([home], phase=phase))  # 250k left at 100k/h: 2.5 h
        need = [n for n in needs if n["role"] == "liquifier_frozen"][0]
        self.assertEqual((need["urgency"], need["off_home"]), ("now", True))
        plan = on.plan_hosts(needs, snap([home], phase=phase))
        self.assertEqual([b["roles"] for b in plan["found"]], [["liquifier_frozen", "drone_depot", "charging"]])
        self.assertEqual(plan["found"][0]["biome"], "frozen")
        self.assertNotIn(
            "liquifier_frozen", roles_of(on.needs(snap([home], phase=dict(phase, done={"biomass": True}))))
        )

    def test_storage_outpost_when_tanks_crowd_production(self):
        unlocked = {"research": {on.OUTPOSTS_RESEARCH}, "pillars": {}, "history": {}}
        crowded = outpost("outpost_1", "deep", 300, 0, types={"smelter": 2, "liquid_tank": 3, "gas_tank": 2}, used=19)
        self.assertIn("storage", roles_of(on.needs(snap([HOME, crowded], phase=unlocked)), "soon"))
        roomy = outpost("outpost_1", "deep", 300, 0, types={"smelter": 2, "liquid_tank": 3, "gas_tank": 2}, used=12)
        self.assertNotIn("storage", roles_of(on.needs(snap([HOME, roomy], phase=unlocked))))
        exempt = outpost("outpost_1", "deep", 300, 0, types={"warehouse": 10, "liquid_tank": 5, "gas_tank": 5}, used=20)
        self.assertNotIn("storage", roles_of(on.needs(snap([HOME, exempt], phase=unlocked))))

    def test_reactor_bundle_before_nuclear_is_exclusive(self):
        water = [{"id": "w1", "fluid": "water", "x": 500.0, "y": 0.0, "box": extractor_box(500.0, 0.0)}]
        phase = {
            "research": {on.OUTPOSTS_RESEARCH, on.game_phase.WILDLIFE_RESEARCH},
            "tp": 640000,
            "pillars": {},
            "history": {"tp": [[0, 630000.0], [36000, 640000.0]]},
        }
        needs = on.needs(snap([HOME], fluid_sites=water, phase=phase, kits=set(ALL_KITS) | {"reactor"}))
        reactor = [n for n in needs if n["role"] == "reactor"][0]
        early = dict(phase, research={on.OUTPOSTS_RESEARCH})
        self.assertNotIn(
            "reactor",
            roles_of(on.needs(snap([HOME], fluid_sites=water, phase=early, kits=set(ALL_KITS) | {"reactor"}))),
        )
        self.assertEqual((reactor["urgency"], reactor["blocked_by"]), ("now", on.NUCLEAR_RESEARCH))
        busy = outpost("outpost_1", "deep", 490, 0, roles=["refinery"], types={"refiner": 1}, used=0)
        empty = outpost("outpost_2", "deep", 480, 40, used=0)
        plan = on.plan_hosts([reactor], snap([HOME, busy, empty], fluid_sites=water, phase=phase))
        self.assertEqual([d["outpost"] for d in plan["designate"]], ["outpost_2"])
        self.assertIn(("reactor", "outpost_1", "exclusive role: host has other production roles"), plan["rejected"])
        nuke = outpost("outpost_3", "deep", 300, 0, roles=["reactor"], used=3)
        plan = on.plan_hosts(
            [on._need("refinery", "soon", "x"), on._need("terraform", "soon", "y")], snap([nuke], fluid_sites=water)
        )
        self.assertEqual([d["roles"] for d in plan["designate"]], [["terraform"]])
        self.assertTrue(
            any(
                r[0] == "refinery" and r[1] == "outpost_3" and r[2].startswith("host is exclusive")
                for r in plan["rejected"]
            )
        )
        far = {
            "research": {on.OUTPOSTS_RESEARCH, on.game_phase.WILDLIFE_RESEARCH},
            "tp": 100000,
            "pillars": {},
            "history": {"tp": [[0, 90000.0], [36000, 100000.0]]},
        }
        self.assertNotIn("reactor", roles_of(on.needs(snap([HOME], fluid_sites=water, phase=far))))
        bundles = on.found_bundles([reactor, on._need("terraform", "soon", "t")], snap([HOME]))
        self.assertEqual([b["roles"] for b in bundles], [["reactor", "charging"], ["terraform", "charging"]])

    def test_refused_roles_make_no_need_unless_now(self):
        home = dict(HOME, used=25)
        self.assertNotIn(
            "factory", roles_of(on.needs(snap([home], activity={"fabricator": 0.9}, refused_roles=["factory"])))
        )
        needs = on.needs(snap([HOME], bio_orders={"deep": 3}, refused_roles=["bio_deep"]))
        self.assertIn("bio_deep", roles_of(needs, "now"))

    def test_read_activity_converts_spare_machines_to_busy_share(self):
        self.assertEqual(on.read_activity(), {})
        groups = {
            "smelter": {"n": 4, "spare_mean": 1.0},
            "fabricator": {"n": 2, "spare_mean": 2.0},
            "habitat": {"n": 1},
        }
        archive.set(machine_activity.ACTIVITY_KEY, {"groups": groups})
        self.assertEqual(on.read_activity(), {"smelter": 0.75, "fabricator": 0.0})
        archive.set(machine_activity.ACTIVITY_KEY, {})

    def test_urgency_for_lead(self):
        lead = on.LEAD_TICKS["designate"]
        self.assertEqual(
            [on.urgency_for(e, lead) for e in (None, 0, lead, lead + 1, 2 * lead, 2 * lead + 1)],
            ["later", "now", "now", "soon", "soon", "later"],
        )

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
        self.assertEqual(
            [(b["biome"], b["roles"]) for b in plan["found"]],
            [("volcanic", ["bio_volcanic", "drone_depot", "charging"])],
        )

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
        self.assertEqual(
            on.host_check(on._need("weather_frozen", "now", "t"), early, late)[1], "home reserved for farm and wildlife"
        )
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
        self.assertEqual([b["roles"] for b in plan["found"]], [["bio_deep", "drone_depot", "charging"]])

    def test_found_bundles_group_by_biome_and_mining(self):
        needs = [
            on._need("mining", "soon", "m", ores=["cobalt"]),
            on._need("bio_deep", "now", "b"),
            on._need("liquifier_deep", "now", "l"),
            on._need("factory", "soon", "f"),
        ]
        bundles = on.found_bundles(needs)
        self.assertEqual(
            [(b["urgency"], b["biome"], b["roles"]) for b in bundles],
            [
                ("now", "deep", ["bio_deep", "liquifier_deep", "drone_depot", "charging"]),
                ("soon", None, ["factory", "drone_depot", "charging"]),
                ("soon", None, ["mining", "drone_depot", "charging"]),
            ],
        )
        self.assertEqual(bundles[2]["ores"], ["cobalt"])


class UndesignatedTests(unittest.TestCase):
    def test_takes_first_later_need_it_can_host(self):
        deep = outpost("outpost_1", "deep", 300, 0)
        s = snap([HOME, deep])
        plan = on.plan_hosts(on.needs(s), s)
        self.assertEqual([d["outpost"] for d in plan["designate"]], ["outpost_1"])
        item = plan["designate"][0]
        self.assertEqual((item["urgency"], item["needs"]), ("later", ["bio_deep"]))
        self.assertTrue(item["why"][0].startswith("no designation yet: "), item["why"])

    def test_designated_or_home_gets_no_fallback(self):
        deep = outpost("outpost_1", "deep", 300, 0, roles=["storage"])
        s = snap([HOME, deep])
        self.assertEqual(on.plan_hosts(on.needs(s), s)["designate"], [])

    def test_mining_of_wanted_ore_in_reach(self):
        empty = outpost("outpost_1", "deep", 300, 0)
        ores = [{"item": "iron_ore", "x": 350.0, "y": 0.0}, {"item": "cobalt", "x": 900.0, "y": 0.0}]
        s = snap([HOME, empty], ore_wanted=["iron_ore", "cobalt"], ore_sites=ores)
        item = on.undesignated_item(empty, [], set(), s)
        assert item is not None
        self.assertEqual((item["roles"], item["needs"]), (["mining", "drone_depot"], ["mining"]))
        self.assertIn("iron_ore", item["why"][0])
        self.assertNotIn("cobalt", item["why"][0])

    def test_adopts_what_stands_when_nothing_fits(self):
        fab = outpost("outpost_1", "deep", 300, 0, types={"fabricator": 2})
        item = on.undesignated_item(fab, [], set(), snap([HOME, fab]))
        assert item is not None
        self.assertEqual((item["roles"], item["needs"]), (["factory", "drone_depot"], ["factory"]))
        refused = snap([HOME, fab], refused=[["factory", "outpost_1"]])
        self.assertIsNone(on.undesignated_item(fab, [], set(), refused))

    def test_built_roles_ride_along_with_a_need(self):
        fab = outpost("outpost_1", "deep", 300, 0, types={"fabricator": 2})
        item = on.undesignated_item(fab, [on._need("weather_deep", "later", "w")], set(), snap([HOME, fab]))
        assert item is not None
        self.assertEqual((item["roles"], item["needs"]), (["factory", "weather_deep", "drone_depot"], ["weather_deep"]))

    def test_need_taken_elsewhere_is_skipped(self):
        empty = outpost("outpost_1", "deep", 300, 0)
        need = on._need("weather_deep", "later", "w")
        self.assertIsNone(on.undesignated_item(empty, [need], {"weather_deep"}, snap([HOME, empty])))

    def test_retired_chain_still_standing_is_not_adopted(self):
        chain = {"bio_collector": 1, "bio_lab": 1, "bio_exchange": 1, "bio_conditioner": 1}
        bio = outpost("outpost_1", "deep", 300, 0, types=chain)
        item = on.undesignated_item(bio, [], set(), snap([HOME, bio]))
        assert item is not None
        self.assertIn("bio_deep", item["roles"])
        self.assertNotIn(
            "bio_frozen", item["roles"]
        )  # biome lock: the frozen chain's buildings stand, but not in frozen
        self.assertIsNone(on.undesignated_item(bio, [], set(), snap([HOME, bio], phase={"bio_retired": ["deep"]})))


class RetiredRoleTests(unittest.TestCase):
    def test_retired_follows_the_retire_latches(self):
        self.assertFalse(roles.retired("bio_deep", {}))
        self.assertTrue(roles.retired("bio_deep", {"bio_retired": ["deep"]}))
        self.assertTrue(roles.retired("bio_caster", {"bio_retired": ["volcanic"]}))
        self.assertFalse(roles.retired("bio_coastal", {"bio_retired": ["deep"]}))
        biomass = {"done": {"biomass": True}}
        self.assertTrue(all(roles.retired(name, biomass) for name in ("liquifier_deep", "biomass_mixer")))
        self.assertFalse(roles.retired("wildlife_ammonia", biomass))
        wildlife = {"pillars": {"wildlife": {"complete": True}}}
        self.assertTrue(all(roles.retired(name, wildlife) for name in ("wildlife", "wildlife_ammonia", "feed")))
        self.assertTrue(roles.retired("plants", {"done": {"plants": True}}))
        everything = {"done": {"biomass": True, "plants": True, "wildlife": True}, "bio_retired": list(roles.BIOMES)}
        self.assertFalse(
            [
                name
                for name in ("factory", "power", "weather_deep", "terraform", "drone_depot", "refinery")
                if roles.retired(name, everything)
            ]
        )

    def test_needs_skip_retired_roles(self):
        s = snap([HOME], bio_orders={"deep": 2})
        self.assertIn("bio_deep", roles_of(on.needs(s)))
        self.assertIn("liquifier_deep", roles_of(on.needs(s)))
        s["phase"] = {"bio_retired": ["deep"], "done": {"biomass": True}}
        got = roles_of(on.needs(s))
        self.assertNotIn("bio_deep", got)
        self.assertFalse([name for name in got if name.startswith("liquifier_")])
        self.assertIn("bio_coastal", got)

    def test_drop_retired_roles_rewrites_the_designation(self):
        archive.set(
            roles.ROLES_KEY,
            {"o1": ["bio_deep", "liquifier_deep", "drone_depot"], "o2": "factory", "o3": "biomass_mixer"},
        )
        dropped = roles.drop_retired_roles({"bio_retired": ["deep"]})
        self.assertEqual(dropped, {"o1": ["bio_deep"]})
        self.assertEqual(
            roles.outpost_roles(), {"o1": ["liquifier_deep", "drone_depot"], "o2": "factory", "o3": "biomass_mixer"}
        )
        self.assertEqual(
            roles.drop_retired_roles({"done": {"biomass": True}}), {"o1": ["liquifier_deep"], "o3": ["biomass_mixer"]}
        )
        self.assertEqual(roles.outpost_roles(), {"o1": ["drone_depot"], "o2": "factory", "o3": []})
        self.assertEqual(roles.drop_retired_roles({"done": {"biomass": True}}), {})


class StationKeeperTests(unittest.TestCase):
    HOME = outpost("outpost_home", "rocky", home=True)

    def keepers(self, extra, status):
        return roles.station_keepers([self.HOME] + extra, status)

    def test_station_keepers_builder_base(self):
        at_home = {"p1": {"role": "builder", "home": "outpost_home"}, "p2": {"role": "builder"}}
        self.assertEqual(self.keepers([], at_home), {"outpost_home"})  # home holds: no salt keeper added

        def frozen(x):
            return outpost("outpost_f", "frozen", x=x)

        away = {
            "p1": {"role": "builder", "base": "outpost_b", "home": "outpost_home"},
            "h1": {"role": "hauler", "base": "outpost_z"},
        }
        b = outpost("outpost_b", "rocky", x=900.0)
        self.assertEqual(self.keepers([b, frozen(250.0)], away), {"outpost_b", "outpost_f"})
        self.assertEqual(self.keepers([b, frozen(350.0)], away), {"outpost_b", "outpost_home"})
        self.assertEqual(self.keepers([b], {}), {"outpost_home"})

    def test_charging_role_sync_survives_a_pruned_entry(self):
        archive.set(roles.ROLES_KEY, {"o1": ["charging"]})
        with mock.patch.object(roles, "outpost_roles", return_value={"o1": ["charging"], "o2": ["charging"]}):
            self.assertEqual(roles.sync_charging_roles({"o3"}), (["o3"], ["o1", "o2"]))
        self.assertEqual(roles.outpost_roles(), {"o1": [], "o3": ["charging"]})

    def test_charging_role_follows_keepers(self):
        archive.set(roles.ROLES_KEY, {"o1": ["factory", "charging"], "o2": "charging", "o3": ["mining"], "o4": []})
        added, removed = roles.sync_charging_roles({"o1", "o3"})
        self.assertEqual((added, removed), (["o3"], ["o2"]))
        self.assertEqual(
            roles.outpost_roles(), {"o1": ["factory", "charging"], "o2": [], "o3": ["mining", "charging"], "o4": []}
        )
        self.assertEqual(roles.sync_charging_roles({"o1", "o3"}), ([], []))
        self.assertEqual(roles.sync_charging_roles({"o9"})[0], ["o9"])  # a keeper without an entry gets one


class WarehouseSlotTests(unittest.TestCase):
    STOCK = {"smelter": ["iron_ore", "cobalt", "iron_ingot", "cobalt_ingot"], "factory": ["iron_ingot", "cobalt_ingot"]}

    def test_stock_slots_share_items_between_roles(self):
        self.assertEqual(roles.stock_slots(["smelter"], self.STOCK), 4)
        self.assertEqual(roles.stock_slots(["smelter", "factory"], self.STOCK), 4 + roles.FACTORY_BUFFER_SLOTS)
        self.assertEqual(roles.stock_slots(["mining", "smelter"], dict(self.STOCK, mining=["cobalt"])), 4)
        self.assertEqual(roles.stock_slots(["smelter"], {}), roles.SMELTER_FALLBACK_SLOTS)
        self.assertEqual(roles.stock_slots(["drone_depot", "weather_deep", "storage"], {}), 0)

    def test_site_slots_count_warehouses_beyond_standing_slots(self):
        self.assertEqual(roles.site_slots(["factory", "drone_depot"], self.STOCK, 0, 5), (5, 1, 3))  # 12 slots
        self.assertEqual(roles.site_slots(["factory", "drone_depot"], self.STOCK, 10, 5), (3, 1, 1))
        self.assertEqual(roles.site_slots(["factory", "drone_depot"], self.STOCK, 0, 15), (3, 1, 1))
        self.assertEqual(roles.site_slots(["feed"], {}, 0, 15), (3, 1, 2))  # 30 life forms + Forage fallback
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
        import bio_orders
        import outpost_reagents

        self.assertEqual(
            roles.BIO_STOCK_SLOTS,
            bio_orders.MAX_LOCAL_BIO_ARTIFACTS + len(outpost_reagents.DEFAULT_REAGENT_STOCK_TARGETS),
        )
        self.assertEqual(roles.stock_slots(["bio_deep"], {}), roles.BIO_STOCK_SLOTS)
        self.assertEqual(roles.stock_slots(["bio_volcanic"], {}), roles.BIO_STOCK_SLOTS + roles.CASTER_STOCK_SLOTS)

    def test_feed_stock_only_from_complete_recipe_list(self):
        from wildlife_common import recipe_of
        from wildlife_data import SPECIES

        recipes = {recipe_of(s): {"forage": 100, "form_" + s: 1} for s in SPECIES}
        got = on.feed_stock({"feed_maker_1": {"recipes": recipes}})
        self.assertEqual(len(got["feed"]), len(SPECIES) + 1)
        partial = dict(list(recipes.items())[:2])
        self.assertEqual(on.feed_stock({"feed_maker_1": {"recipes": partial}}), {})
        self.assertEqual(roles.stock_slots(["feed"], on.feed_stock({})), roles.FEED_FALLBACK_SLOTS)
        self.assertEqual(on.feed_stock(None), {})

    def test_smelter_stock_only_when_every_ore_smelts(self):
        from game_rules import RAW_ORE_ITEM_IDS

        full = [Recipe("smelt_" + ore, {ore: 2}, ore + "_out") for ore in RAW_ORE_ITEM_IDS]
        got = on.smelter_stock(full)
        self.assertEqual(len(got["smelter"]), 2 * len(RAW_ORE_ITEM_IDS))
        self.assertEqual(len(got["factory"]), len(RAW_ORE_ITEM_IDS))
        self.assertEqual(on.smelter_stock(full[:1]), {})  # Large Warehouse: end state, incomplete
        early = on.smelter_stock(full[:2], large=False)  # small Warehouses: what is unlocked now
        self.assertEqual((len(early["smelter"]), len(early["factory"])), (4, 2))
        self.assertEqual(on.smelter_stock([], large=False), {})

    def test_liquifier_one_slot_per_life_form(self):
        self.assertEqual(roles.stock_slots(["liquifier_deep"], {}), 6)

    def test_found_bundle_reports_buildings(self):
        s = snap([HOME], stock=self.STOCK, per_warehouse=5)
        bundle = on.found_bundles([on._need("factory", "soon", "f")], s)[0]
        self.assertEqual(bundle["slots"], {"counted": 6, "penalized": 2, "warehouses": 3})
        self.assertFalse(bundle["over_cap"])


OUTPOSTS_ON = {"research": {on.OUTPOSTS_RESEARCH}, "tp": 0, "pillars": {}, "history": {}}
NUCLEAR_ON = {"research": {on.OUTPOSTS_RESEARCH, on.NUCLEAR_RESEARCH}, "tp": 0, "pillars": {}, "history": {}}


class FutureFluidTests(unittest.TestCase):
    """future_fluids(): look-ahead fluids no outpost and no proposed need covers yet."""

    def test_future_fluids_empty_before_outposts(self):
        self.assertEqual(on.future_fluids(snap([HOME], phase={}), []), [])

    def test_future_fluids_steam_until_power_host(self):
        self.assertEqual(on.future_fluids(snap([HOME], phase=OUTPOSTS_ON), []), ["steam"])
        power = outpost("outpost_1", "geothermal", 300, 0, roles=["power"])
        self.assertEqual(on.future_fluids(snap([HOME, power], phase=OUTPOSTS_ON), []), [])

    def test_future_fluids_skip_proposed_power(self):
        s = snap([HOME], phase=OUTPOSTS_ON)
        self.assertEqual(on.future_fluids(s, [on._need("power", "soon", "x")]), [])
        self.assertEqual(on.future_fluids(s, [on._need("power", "later", "x")]), ["steam"])

    def test_future_fluids_water_when_nuclear_ahead(self):
        self.assertEqual(on.future_fluids(snap([HOME], phase=NUCLEAR_ON), []), ["steam", "water"])
        self.assertEqual(on.future_fluids(snap([HOME], phase=NUCLEAR_ON), [on._need("reactor", "now", "x")]), ["steam"])
        reactor = outpost("outpost_1", "frozen", 300, 0, roles=["reactor"])
        self.assertEqual(on.future_fluids(snap([HOME, reactor], phase=NUCLEAR_ON), []), ["steam"])

    def test_plan_hosts_carries_future(self):
        self.assertEqual(on.plan_hosts([], snap([HOME], phase=OUTPOSTS_ON))["future"], ["steam"])
        self.assertEqual(on.plan_hosts([], snap([HOME], phase={}))["future"], [])


if __name__ == "__main__":
    unittest.main()
