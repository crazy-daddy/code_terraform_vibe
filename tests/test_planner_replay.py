"""Tests for devtools/simulation/replay_snapshot.py (save -> planner snapshots) and planner_replay.py's matching."""

import os
import sys
import unittest

import harness  # noqa: F401 (side effect: installs game builtins and lib paths)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "devtools", "simulation"))

# isort: split
import planner_replay as pr  # noqa: E402
import replay_snapshot as rs  # noqa: E402

SITES = [
    {"id": "black_rim", "item": "iron_ore", "purity": "standard", "hardness": 1, "x": 30.0, "y": 30.0},
    {"id": "deep_vein", "item": "cobalt", "purity": "standard", "hardness": 2, "x": -80.0, "y": -290.0},
]


def state(tick=1000, tech=(), outposts=None, machines=None, recipes=(), surveyed=(), notebook=None, inventory=()):
    outposts = (
        outposts
        if outposts is not None
        else [{"id": "outpost_home", "x": 0, "y": 0}, {"id": "outpost_1", "x": 170, "y": 80}]
    )
    machines = (
        machines
        if machines is not None
        else {
            "smelter_1": {"id": "smelter_1", "typeId": "smelter", "locationId": "outpost_1", "data": {"tier": 2}},
            "battery_1": {"id": "battery_1", "typeId": "battery", "locationId": "outpost_home"},
        }
    )
    return {
        "tickCount": tick,
        "unlockedTech": list(tech),
        "planet": {
            "outposts": outposts,
            "atmosphere": {"oxygen": 20.0, "pressure": 1.0},
            "temperature": {"heatUnits": 50.0},
            "biomass": {"totalTons": 0.0},
            "plants": {"km2": 0.0},
            "wildlife": {"population": 0.0},
            "power": {
                "subnets": {"subnet_0": {"generated": 100.0, "consumed": 60.0, "stored": 400.0, "capacity": 500.0}}
            },
            "sources": [
                {"kind": "thermal", "id": "vent_1", "x": 250, "y": -560, "basePeakSteamRate": 1000},
                {"kind": "water", "id": "water_well_1", "x": 410, "y": -210, "baseFlowRate": 10},
            ],
        },
        "machines": machines,
        "player": {"unlockedRecipes": list(recipes), "credits": 0},
        "inventory": {"slots": [{"id": item, "count": 1} for item in inventory]},
        "journal": {
            "planets": {"nocturna": {"mining": {"surveyedSites": list(surveyed), "discoveredSites": list(surveyed)}}}
        },
        "notebook": {"entries": {k: {"value": v} for k, v in (notebook or {}).items()}},
        "researchRates": {"terraform": {"lastValue": 150000}},
    }


class SnapshotTests(unittest.TestCase):
    def test_biome_lattice_matches_the_documented_outposts(self):
        # docs/gameknowledge biomes: home (0, 0) frozen, outpost_1 (170, 80) coastal, outpost_2 (200, -440) geothermal, outpost_5 (30, 420) volcanic, (-460, 280) deep
        self.assertEqual(rs.biome_at(0, 0), "frozen")
        self.assertEqual(rs.biome_at(170, 80), "coastal")
        self.assertEqual(rs.biome_at(200, -440), "geothermal")
        self.assertEqual(rs.biome_at(30, 420), "volcanic")
        self.assertEqual(rs.biome_at(-460, 280), "deep")
        self.assertIn(
            rs.biome_at(5000, -5000), ("frozen", "coastal", "geothermal", "volcanic", "deep")
        )  # clamps to the edge

    def test_kits_from_types_inventory_recipes_and_tech(self):
        table = {"smelter": (True, True), "warehouse": (True, False), "battery": (True, False)}
        kits = rs.kits_of(
            state(
                tech=["warehouse_unlock", "luminizer_unlock", "high_bay_warehousing_unlock"],
                recipes=["craft_drone_station_kit"],
                inventory=["seed_maker"],
            ),
            table,
        )
        for kit in (
            "smelter",
            "battery",
            "warehouse",
            "bio_luminizer",
            "large_warehouse",
            "drone_station_kit",
            "seed_maker",
            "solar_generator",
        ):
            self.assertIn(kit, kits)
        self.assertNotIn("reactor", kits)

    def test_outposts_biome_cap_and_counts(self):
        table = {"smelter": (True, True), "battery": (True, False)}
        rows = rs.outposts_of(state(), table, {"outpost_1": ["factory"]})
        home, one = rows
        self.assertEqual((home["home"], home["biome"], home["capacity"], home["used"]), (True, "frozen", 25, 1))
        self.assertEqual(
            (one["biome"], one["roles"], one["types"], one["used"], one["capacity"]),
            ("coastal", ["factory"], {"smelter": 1}, 1, 20),
        )

    def test_sites_filtered_to_surveyed_and_drills(self):
        s = state(
            surveyed=["black_rim", "vent_1"], notebook={"drill.status": {"mining_drill_1": {"items": {"iron_ore": 10}}}}
        )
        ores = rs.ore_sites_of(s, SITES)
        self.assertEqual([(r["id"], r["drill"]) for r in ores], [("black_rim", "drill")])
        fluids = rs.fluid_sites_of(s)
        self.assertEqual([(r["id"], r["fluid"]) for r in fluids], [("vent_1", "steam")])
        self.assertEqual(rs.ore_wanted_of(state(recipes=["smelt_iron_ingot", "smelt_glass"])), ["iron_ore", "silicon"])
        self.assertEqual(rs.ore_wanted_of(state()), list(rs.EARLY_ORES))

    def test_phase_snapshot(self):
        s = state(
            tech=["custom_panels_unlock", "biosphere_unlock"], machines={"d": {"id": "d", "typeId": "mining_drill"}}
        )
        phase = rs.phase_of(s, {"tp": [[0, 100000.0], [1000, 150000.0]]})
        self.assertEqual(phase["tp"], 150000.0)
        self.assertIn("research_custom_panels", phase["research"])
        self.assertTrue(phase["drills"])
        self.assertEqual(phase["pillars"]["oxygen"]["value"], 20.0)
        self.assertGreater(phase["pillars"]["oxygen"]["target"], 20.0)
        self.assertFalse(phase["done"]["biomass"])

    def test_needs_snapshot_and_context(self):
        table = {"smelter": (True, True), "battery": (True, False)}
        s = state(
            tech=["outpost_unlock", "fabricator_unlock"],
            surveyed=["black_rim"],
            notebook={"fleet.status": {"pioneer_1": {"role": "scout", "state": "IDLE"}}},
        )
        rs.load_archive(s)
        snap = rs.needs_snapshot(s, table, SITES, {}, {})
        self.assertEqual([o["id"] for o in snap["outposts"]], ["outpost_home", "outpost_1"])
        self.assertIn("research_outpost_hub", snap["phase"]["research"])
        self.assertEqual(snap["ore_sites"][0]["id"], "black_rim")
        ctx = rs.context_of(s, snap, {"pillar": "o2"}, table)
        self.assertEqual(ctx["machines"]["smelter"], [("smelter_1", "outpost_1", 2)])
        self.assertEqual(ctx["grids"][0]["phase"], "solar")
        self.assertEqual(ctx["fleet"]["pioneer"], {"scout": 1})
        world = rs.world_of(snap, SITES, s)
        self.assertEqual([r["id"] for r in world["sites"]], ["black_rim"])
        self.assertEqual(len(world["pois"]), len(SITES) + 2)


class MatchTests(unittest.TestCase):
    def test_real_decisions_fold_a_swap(self):
        a = {
            "outposts": {"outpost_home": "Home"},
            "caps": {},
            "counts": {"outpost_home": {"temp_heater": 5, "smelter": 1}},
            "tiers": {"smelter@1": 1},
            "tech": [],
            "orders_done": [],
            "weekly_done": 0,
            "purchased": {},
            "infra": {},
            "blueprints": 0,
            "suggestions": {},
            "proposals": {},
            "power": {},
            "fluids": {},
            "scripts": {},
            "running": 0,
            "stock": {},
        }
        b = dict(a, counts={"outpost_home": {"pressure_generator": 5, "smelter": 2}}, tiers={"smelter@2": 1})
        decisions = pr.real_decisions(a, b, {"planet": {"outposts": []}})
        kinds = sorted((d["kind"], d["type"]) for d in decisions)
        self.assertEqual(kinds, [("deploy", "smelter"), ("swap", "pressure"), ("upgrade", "smelter")])

    def test_match_window_and_extras(self):
        offers = [set(), {("deploy", "smelter")}, {("found", "deep"), ("found", "any")}]
        self.assertEqual(pr.match({"kind": "deploy", "type": "smelter"}, offers, 2, 3), ("early", 1))
        self.assertEqual(pr.match({"kind": "found", "type": "deep"}, offers, 2, 3), ("match", 2))
        self.assertEqual(pr.match({"kind": "found", "type": "coastal"}, offers, 2, 3), ("match (other biome)", 2))
        self.assertEqual(pr.match({"kind": "retire", "type": "battery"}, offers, 2, 1), ("missed", None))
        result = {
            "proposals": {"deploy:o:smelter": {"kind": "deploy", "type_id": "smelter"}},
            "plan": {"found": [], "designate": []},
            "ranked": {},
        }
        self.assertEqual(pr.extras(result, [{"kind": "deploy", "type": "fabricator"}]), [("deploy", "smelter")])
        self.assertEqual(pr.extras(result, [{"kind": "deploy", "type": "smelter"}]), [])


if __name__ == "__main__":
    unittest.main()
