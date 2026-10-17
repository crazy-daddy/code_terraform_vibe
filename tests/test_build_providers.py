"""Tests for autoplay/lib/build_providers.py (building pass providers) and the building_plan glue around them."""

import unittest

import harness  # noqa: F401 (side effect: installs game builtins and lib paths)

# isort: split
import build_providers as bpv
import building_ops
import building_plan as bp
import fleet_commission
import fleet_decommission
import fleet_status
import game_phase as gp
from archive import archive
from harness import StubTestCase

EXPANSION = ["research_data_archive", gp.CONTROL_ROOM_RESEARCH]


def outpost(oid, biome="deep", roles=(), types=None, used=None, capacity=20, home=False):
    types = dict(types or {})
    return {
        "id": oid,
        "x": 0.0,
        "y": 0.0,
        "biome": biome,
        "home": home,
        "roles": list(roles),
        "types": types,
        "used": sum(types.values()) if used is None else used,
        "capacity": capacity,
    }


HOME = outpost("outpost_home", "frozen", home=True, capacity=25, types={"oxygen_generator": 3, "battery": 2})


def phase(research=EXPANSION, tp=200000, history=None, done=None):
    return {
        "tick": 0,
        "tp": tp,
        "pillars": {},
        "research": set(research),
        "drills": False,
        "done": done or {},
        "history": history or {},
    }


def ctx(
    outposts=None,
    kits=(),
    focus=None,
    generators=None,
    machines=None,
    grids=None,
    prices=None,
    inventory=None,
    fleet=None,
    phase_snap=None,
    **extra,
):
    snap = {
        "outposts": outposts if outposts is not None else [HOME],
        "kits": set(kits),
        "activity": extra.pop("activity", {}),
        "bio_orders": extra.pop("bio_orders", {}),
        "bio_done": extra.pop("bio_done", {}),
        "ore_sites": extra.pop("ore_sites", []),
        "ore_wanted": extra.pop("ore_wanted", []),
    }
    out = {
        "snap": snap,
        "phase": phase_snap or phase(),
        "focus": focus or {},
        "generators": generators or {},
        "machines": machines or {},
        "machine_ids": extra.pop("machine_ids", {}),
        "grids": grids or [],
        "prices": prices or {},
        "inventory": inventory or {},
        "fleet": fleet or {},
        "survey_open": False,
        "survey_idle_since": None,
        "pickup_backlog": 0,
        "drills_missing": [],
        "seismic_open": False,
        "tick": 0,
    }
    out.update(extra)
    return out


def grid(
    anchor="outpost_home",
    outposts=("outpost_home",),
    generated=100.0,
    consumed=50.0,
    capacity=500.0,
    reserve=0.8,
    phase_name="solar",
    types=None,
):
    return {
        "anchor": anchor,
        "outposts": list(outposts),
        "generated": generated,
        "consumed": consumed,
        "stored": capacity * reserve,
        "capacity": capacity,
        "reserve": reserve,
        "phase": phase_name,
        "types": dict(types or {}),
    }


def kinds(wants):
    return [
        (
            w["kind"],
            w.get("type_id") or w.get("role"),
            w.get("count", 1) if w["kind"] == "deploy" else w.get("delta", 0),
        )
        for w in wants
    ]


class AtmosphereTests(unittest.TestCase):
    def test_generators_fit_slots_and_power(self):
        c = ctx(
            kits=["oxygen_generator"],
            focus={"pillar": "o2", "swap": False},
            grids=[grid(generated=100.0, consumed=52.0)],
        )
        wants = bpv.atmosphere_wants(c)
        self.assertEqual(kinds(wants), [("deploy", "oxygen_generator", 3)])  # 48 W - 20 margin = 28 W: 3 Mk I at 8 W
        self.assertEqual(bpv.generator_draw("pressure_generator", 3), 21.0)
        self.assertEqual(bpv.generator_draw("temp_heater", 2), 0.0)
        self.assertIsNone(wants[0]["blocked"])
        tight = ctx(
            kits=["oxygen_generator"],
            focus={"pillar": "o2", "swap": False},
            grids=[grid(generated=60.0, consumed=55.0)],
        )
        wants = bpv.atmosphere_wants(tight)
        self.assertEqual(kinds(wants), [("deploy", "oxygen_generator", 1)])
        self.assertTrue(wants[0]["blocked"].startswith("power:"))
        self.assertEqual(bpv.atmosphere_wants(ctx(focus={"pillar": "o2", "swap": True})), [])
        self.assertEqual(bpv.atmosphere_wants(ctx(focus={"pillar": "o2"}, kits=[])), [])

    def test_pack_in_place_before_another_machine(self):
        gens = {
            "oxygen_generator": [("oxygen_generator_1", "outpost_home", 1), ("oxygen_generator_2", "outpost_home", 2)]
        }
        c = ctx(
            kits=["oxygen_generator"], focus={"pillar": "o2"}, generators=gens, prices={"oxygen_upgrade_pack_mk2": 100}
        )
        wants = bpv.atmosphere_wants(c)
        self.assertEqual(
            [(w["kind"], w["machine_id"], w["item_id"]) for w in wants],
            [("upgrade", "oxygen_generator_1", "oxygen_upgrade_pack_mk2")],
        )
        c = ctx(
            kits=["oxygen_generator"], focus={"pillar": "o2"}, generators=gens, prices={"oxygen_upgrade_pack_mk3": 100}
        )
        self.assertEqual(
            [(w["kind"], w["machine_id"]) for w in bpv.atmosphere_wants(c)], [("upgrade", "oxygen_generator_2")]
        )


class PowerTests(unittest.TestCase):
    def test_deficit_generator_by_phase(self):
        c = ctx(kits=["solar_generator", "steam_turbine"], grids=[grid(generated=40.0, consumed=60.0, reserve=0.2)])
        self.assertEqual(kinds(bpv.power_wants(c)), [("deploy", "solar_generator", 1)])
        steam = ctx(
            kits=["solar_generator", "steam_turbine"],
            grids=[grid(generated=40.0, consumed=60.0, reserve=0.2, phase_name="steam", types={"steam_turbine": 1})],
        )
        self.assertEqual(kinds(bpv.power_wants(steam)), [("deploy", "steam_turbine", 1)])
        oil_host = outpost("outpost_home", "frozen", home=True, capacity=25, types={"liquid_tank": 1})
        oil = ctx(
            outposts=[oil_host],
            kits=["oil_generator", "steam_turbine"],
            grids=[grid(generated=40.0, consumed=60.0, reserve=0.2, phase_name="steam")],
        )
        self.assertEqual(kinds(bpv.power_wants(oil)), [("deploy", "oil_generator", 1)])
        fine = ctx(kits=["solar_generator"], grids=[grid(generated=40.0, consumed=60.0, reserve=0.9)])
        self.assertEqual(bpv.power_wants(fine), [])

    def test_battery_floor_and_producer_tanks(self):
        c = ctx(kits=["battery", "battery_large"], grids=[grid(capacity=500.0, types={"smelter": 1})])
        wants = bpv.power_wants(c)
        self.assertEqual(kinds(wants), [("deploy", "battery_large", 1)])
        small = ctx(kits=["battery"], grids=[grid(capacity=200.0, types={"fabricator": 2})])
        self.assertEqual(kinds(bpv.power_wants(small)), [("deploy", "battery", 3)])
        vent = outpost("outpost_2", "geothermal", roles=["power"], types={"steam_turbine": 1})
        tanks = ctx(outposts=[HOME, vent], kits=["gas_tank"], grids=[grid(capacity=5000.0)])
        self.assertEqual(kinds(bpv.power_wants(tanks)), [("deploy", "gas_tank", 1)])
        self.assertEqual(
            bpv.power_wants(
                ctx(outposts=[HOME, dict(vent, types={"steam_turbine": 1, "gas_tank": 1})], kits=["gas_tank"])
            ),
            [],
        )


class FactoryTests(unittest.TestCase):
    def test_pack_first_then_machine(self):
        host = outpost("outpost_1", types={"smelter": 1}, used=5)
        machines = {"smelter": [("smelter_1", "outpost_1", 1)]}
        c = ctx(
            outposts=[HOME, host],
            kits=["smelter"],
            machines=machines,
            activity={"smelter": 0.9},
            prices={"smelter_upgrade_pack_mk2": 50},
        )
        wants = bpv.factory_wants(c)
        self.assertEqual(
            [(w["kind"], w["machine_id"], w["item_id"]) for w in wants],
            [("upgrade", "smelter_1", "smelter_upgrade_pack_mk2")],
        )
        no_pack = ctx(outposts=[HOME, host], kits=["smelter"], machines=machines, activity={"smelter": 0.9})
        self.assertEqual([(w["kind"], w["outpost"]) for w in bpv.factory_wants(no_pack)], [("deploy", "outpost_1")])
        second = outpost("outpost_2", types={"fabricator": 1}, used=5)
        two_hosts = ctx(outposts=[HOME, host, second], kits=["smelter"], machines=machines, activity={"smelter": 0.8})
        self.assertEqual(bpv.factory_wants(two_hosts), [])  # two factory outposts: the 0.9 bar applies
        idle = ctx(outposts=[HOME, host], kits=["smelter"], machines=machines, activity={"smelter": 0.3})
        self.assertEqual(bpv.factory_wants(idle), [])
        self.assertEqual(bpv.factory_wants(ctx(outposts=[HOME, host], kits=["smelter"], machines=machines)), [])


class KitTests(unittest.TestCase):
    def test_phase_kits(self):
        c = ctx(
            kits=["seed_maker", "drone_station_kit", "biomass_mixer"],
            phase_snap=phase(EXPANSION + ["research_seed_maker", gp.BIOSPHERE_RESEARCH]),
        )
        self.assertEqual(
            kinds(bpv.kit_wants(c)), [("deploy", "seed_maker", 2), ("deploy", "biomass_mixer", 1)]
        )  # home holds no item role: no Depot
        fab = outpost("outpost_1", types={"fabricator": 1})
        c = ctx(outposts=[HOME, fab], kits=["drone_station_kit", "drone_service_station_kit"])
        self.assertEqual(
            kinds(bpv.kit_wants(c)), [("deploy", "drone_station", 1), ("deploy", "drone_service_station", 1)]
        )
        self.assertEqual([w["outpost"] for w in bpv.kit_wants(c)], ["outpost_1", "outpost_home"])

    def test_nuclear_prep_by_eta(self):
        soon = phase(EXPANSION, tp=640000, history={"tp": [[0, 630000.0], [36000, 640000.0]]})
        deep = outpost("outpost_1", "deep", used=3)
        c = ctx(outposts=[HOME, deep], kits=["weather_station", "lead_cask", "fuel_assembler"], phase_snap=soon)
        self.assertEqual(
            kinds(bpv.kit_wants(c)),
            [
                ("deploy", "weather_station", 1),
                ("deploy", "weather_station", 1),
                ("deploy", "lead_cask", 2),
                ("deploy", "fuel_assembler", 1),
            ],
        )
        far = phase(EXPANSION, tp=100000, history={"tp": [[0, 90000.0], [36000, 100000.0]]})
        self.assertEqual(
            bpv.kit_wants(ctx(outposts=[HOME, deep], kits=["weather_station", "lead_cask"], phase_snap=far)), []
        )


class RetireTests(unittest.TestCase):
    def test_bins_and_stations(self):
        coastal = outpost("outpost_1", "coastal", types={"bio_collector": 1, "warehouse": 1, "storage_bin": 2})
        ids = {
            ("outpost_1", "bio_collector"): ["bio_collector_1"],
            ("outpost_1", "storage_bin"): ["storage_bin_1", "storage_bin_2"],
        }
        c = ctx(outposts=[HOME, coastal], machine_ids=ids)
        self.assertEqual(
            [w["machine_id"] for w in bpv.retire_wants(c)], ["storage_bin_1", "storage_bin_2"]
        )  # the bio chain is bio_retire's job
        stations = {
            ("outpost_home", "weather_station"): ["weather_station_1"],
            ("outpost_1", "weather_station"): ["weather_station_2"],
        }
        far = phase(EXPANSION, tp=100000, history={"tp": [[0, 90000.0], [36000, 100000.0]]})
        c = ctx(outposts=[HOME, coastal], machine_ids=stations, phase_snap=far)
        self.assertEqual([w["machine_id"] for w in bpv.retire_wants(c)], ["weather_station_2"])
        kept = ctx(outposts=[HOME, dict(coastal, roles=["weather_coastal"])], machine_ids=stations, phase_snap=far)
        self.assertEqual(bpv.retire_wants(kept), [])

    def test_batteries_above_the_floor(self):
        ids = {("outpost_home", "battery"): ["battery_1", "battery_2", "battery_3"]}
        c = ctx(grids=[grid(capacity=4600.0, phase_name="steam")], machine_ids=ids)
        self.assertEqual(
            [w["machine_id"] for w in bpv.retire_wants(c)], ["battery_1", "battery_2"]
        )  # 4600 - 1500 - 2000 = 1100 Wh: two 500 Wh batteries
        self.assertEqual(bpv.retire_wants(ctx(grids=[grid(capacity=4600.0, phase_name="solar")], machine_ids=ids)), [])
        drained = ctx(grids=[grid(capacity=4600.0, reserve=0.3, phase_name="steam")], machine_ids=ids)
        self.assertEqual(bpv.retire_wants(drained), [])


class FleetTests(unittest.TestCase):
    def test_scout_before_miners_and_haulers(self):
        bio = outpost("outpost_1", "coastal", roles=["liquifier_coastal"])
        c = ctx(outposts=[HOME, bio], kits=["drone_small"], fleet={"drone": {}})
        wants = bpv.fleet_wants(c)
        self.assertEqual(kinds(wants), [("fleet", "scout", 1), ("fleet", "miner", 2)])
        self.assertEqual(wants[1]["blocked"], "scout first")
        c = ctx(
            outposts=[HOME, bio],
            kits=["drone_small"],
            fleet={"drone": {"scout": 1, "miner": 1}},
            pickup_backlog=2 * 36000,
        )
        self.assertEqual(kinds(bpv.fleet_wants(c)), [("fleet", "miner", 1), ("fleet", "hauler", 1)])
        queued = ctx(
            outposts=[HOME, bio], kits=["drone_small"], fleet={"drone": {"scout": 1}, "queued": {"drone": {"miner": 2}}}
        )
        self.assertEqual(bpv.fleet_wants(queued), [])  # commissions in flight count

    def test_retire_rules(self):
        c = ctx(
            fleet={"pioneer": {"scout": 3, "miner": 2, "hauler": 4}, "drone": {"hauler": 2}},
            survey_idle_since=0,
            tick=3 * 36000,
            phase_snap=dict(phase(), drills=True),
            drills_missing=["rare_earth"],
        )
        wants = bpv.fleet_wants(c)
        self.assertEqual(kinds(wants), [("fleet", "scout", -1), ("fleet", "miner", -1), ("fleet", "hauler", -1)])
        self.assertEqual(wants[1]["blocked"], "no drill on rare_earth")
        two = ctx(fleet={"pioneer": {"scout": 2}}, survey_idle_since=0, tick=3 * 36000, seismic_open=True)
        self.assertEqual(bpv.fleet_wants(two)[0]["blocked"], "seismic work open")
        busy = ctx(fleet={"pioneer": {"scout": 3}}, survey_open=True, survey_idle_since=None, tick=3 * 36000)
        self.assertEqual(bpv.fleet_wants(busy), [])
        retiring = ctx(
            fleet={"pioneer": {"scout": 3}, "retiring": {"pioneer": {"scout": 1}}}, survey_idle_since=0, tick=3 * 36000
        )
        self.assertEqual(bpv.fleet_wants(retiring), [])

    def test_plated_drone_before_nuclear(self):
        soon = phase(EXPANSION, tp=640000, history={"tp": [[0, 630000.0], [36000, 640000.0]]})
        station = outpost("outpost_home", "frozen", home=True, capacity=25, types={"weather_station": 1})
        c = ctx(outposts=[station], kits=["drone_small"], fleet={"drone": {}}, phase_snap=soon)
        self.assertEqual(kinds(bpv.fleet_wants(c)), [("fleet", "aftermath", 1)])


class GlueTests(unittest.TestCase):
    def test_want_ids_and_gates(self):
        c = ctx(kits=["oxygen_generator"], focus={"pillar": "o2"}, grids=[grid(generated=100.0, consumed=52.0)])
        proposals = bp.provider_proposals(c, {})
        self.assertIn("deploy:outpost_home:oxygen_generator", proposals)
        self.assertEqual(proposals["deploy:outpost_home:oxygen_generator"]["kit_source"], "available")
        full = ctx(outposts=[dict(HOME, used=24)], kits=["oxygen_generator"], focus={"pillar": "o2"})
        self.assertEqual(bp.provider_proposals(full, {}), {})  # one free slot is kept
        self.assertEqual(
            bp.want_id({"kind": "fleet", "fleet_kind": "drone", "role": "miner", "delta": 2}), "fleet:drone:miner:+"
        )
        self.assertEqual(
            bp.want_id({"kind": "upgrade", "machine_id": "smelter_1", "item_id": "smelter_upgrade_pack_mk2"}),
            "upgrade:smelter_1:smelter_upgrade_pack_mk2",
        )

    def test_helpers(self):
        status = {
            "pioneer_1": {"role": "scout", "state": "IDLE"},
            "pioneer_2": {"role": "scout", "state": "MOVING"},
            "drone_3": {"role": "hauler", "state": "idle"},
            "x": 1,
        }
        counts = bp.fleet_counts(
            status,
            {
                "jobs": [
                    {"kind": "drone", "role": "miner", "state": "queued"},
                    {"kind": "pioneer", "role": "scout", "state": "done"},
                ]
            },
            {"pioneer_2": {}},
        )
        self.assertEqual(
            counts,
            {
                "pioneer": {"scout": 2},
                "drone": {"hauler": 1},
                "queued": {"drone": {"miner": 1}},
                "retiring": {"pioneer": {"scout": 1}},
            },
        )
        self.assertEqual(bp.idle_unit(status, "pioneer", "scout"), "pioneer_1")
        self.assertIsNone(bp.idle_unit(status, "pioneer", "scout", {"pioneer_1": {}}))
        self.assertIsNone(
            bp.idle_unit({"pioneer_2": {"role": "scout", "state": "MOVING"}}, "pioneer", "scout")
        )  # a busy unit is never recalled
        self.assertIsNone(bp.idle_unit(status, "drone", "miner"))
        self.assertEqual(bp.pickup_backlog({"a": {"tick": 10}, "b": {"tick": 50, "aboard": True}}, 100), 90)
        self.assertEqual(
            bp.pickup_backlog({"a": {"tick": 10}}, 10 + bp.PICKUP_STALE_TICKS), 0
        )  # stale entries do not count
        self.assertEqual(bp.pickup_backlog({}, 100), 0)
        snap = {
            "ore_wanted": ["iron_ore", "cobalt"],
            "ore_sites": [{"item": "iron_ore", "drill": "drill_1"}, {"item": "cobalt", "drill": ""}],
        }
        self.assertEqual(bp.drills_missing(snap), ["cobalt"])


class FlowTests(StubTestCase):
    def test_fleet_row_approve_commissions_or_retires(self):
        archive.set(
            fleet_status.FLEET_STATUS_KEY,
            {"pioneer_1": {"role": "scout", "state": "IDLE"}, "pioneer_2": {"role": "scout", "state": "IDLE"}},
        )
        proposals = {
            "fleet:drone:scout:+": {
                "kind": "fleet",
                "fleet_kind": "drone",
                "role": "scout",
                "delta": 1,
                "provider": "fleet",
                "why": "x",
                "status": "approved",
                "tick": 1,
            },
            "fleet:pioneer:scout:-": {
                "kind": "fleet",
                "fleet_kind": "pioneer",
                "role": "scout",
                "delta": -1,
                "provider": "fleet",
                "why": "y",
                "status": "approved",
                "tick": 1,
            },
            "fleet:pioneer:miner:-": {
                "kind": "fleet",
                "fleet_kind": "pioneer",
                "role": "miner",
                "delta": -1,
                "provider": "fleet",
                "why": "z",
                "status": "approved",
                "tick": 1,
            },
        }
        archive.set(bp.PROPOSALS_KEY, proposals)
        planner = bp.BuildingPlanner(bp.building_ops.log)
        planner.full_tick = 0
        planner.run_pass({"outposts": [], "kits": set()})
        stored = bp.load()
        self.assertNotIn("fleet:drone:scout:+", stored)
        self.assertNotIn("fleet:pioneer:scout:-", stored)
        self.assertEqual(
            (stored["fleet:pioneer:miner:-"]["status"], stored["fleet:pioneer:miner:-"]["blocked"]),
            ("proposed", "no idle unit of that role"),
        )
        jobs = fleet_commission.commission_state().get("jobs") or []
        self.assertEqual([(j["kind"], j["role"]) for j in jobs], [("drone", "scout")])
        self.assertIn("pioneer_1", fleet_decommission.decommission_state())

    def test_upgrade_row_queues_an_upgrade_job(self):
        self.world.add_outpost("outpost_1")
        smelter = self.world.add_building("smelter_1", "outpost_1", "smelter")
        self.assertIsNotNone(smelter)
        archive.set(
            bp.PROPOSALS_KEY,
            {
                "upgrade:smelter_1:smelter_upgrade_pack_mk2": {
                    "kind": "upgrade",
                    "outpost": "outpost_1",
                    "type_id": "smelter",
                    "machine_id": "smelter_1",
                    "item_id": "smelter_upgrade_pack_mk2",
                    "kit": "smelter_upgrade_pack_mk2",
                    "provider": "factory",
                    "why": "x",
                    "status": "approved",
                    "tick": 1,
                }
            },
        )
        planner = bp.BuildingPlanner(bp.building_ops.log)
        planner.full_tick = 0
        self.assertEqual(planner.run_pass({"outposts": [], "kits": set()}), "working")
        job_id = bp.load()["upgrade:smelter_1:smelter_upgrade_pack_mk2"]["jobs"][0]
        self.assertEqual(building_ops.jobs()[job_id]["kind"], "upgrade")

    def test_full_pass_builds_the_context(self):
        self.world.research.unlocked.update(EXPANSION)
        planner = bp.BuildingPlanner(bp.building_ops.log)
        snap = {
            "outposts": [dict(HOME)],
            "kits": {"oxygen_generator"},
            "activity": {},
            "ore_sites": [],
            "ore_wanted": [],
            "bio_orders": {},
            "bio_done": {},
        }
        planner.run_pass(snap)
        self.assertIn("deploy:outpost_home:oxygen_generator", bp.load())
        self.assertIsInstance(archive.get(bp.IDLE_KEY, {}).get("since"), int)


if __name__ == "__main__":
    unittest.main()
