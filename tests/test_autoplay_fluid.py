"""Tests for autoplay/lib/fluid_plan.py, autoplay_roles.py and the pipe route queue in blueprint_queue.py."""

import builtins
import unittest
from unittest import mock

import autoplay_roles as roles
import blueprint_queue as bq
import fluid_outlook as fo
import fluid_plan as fp
import grid_geom as g
import harness
import infra_topology as topo
import site_supply
import supply_tiers as st
from construction_plan import ATOMIC_STEP_BUDGET
from game_stubs import Building, ConstructionBlueprints, Journal
from test_autoplay_geom import ops
from test_autoplay_power import Job, Result, Site


def k(tx, ty):
    return g.tile_key(tx, ty)


class Blueprints(ConstructionBlueprints):
    """construction_blueprint fake: plan_pipe/plan_bridge answer from `answers` in order (default ok)."""

    def __init__(self, answers=()):
        super().__init__()
        self.answers = list(answers)
        self.calls = []
        self.cancelled = []
        self.next_id = 0
        self.short = False

    @property
    def jobs(self):
        return self.pending

    @jobs.setter
    def jobs(self, value):
        self.pending = value

    def _ids(self, count):
        ids = []
        for _ in range(count):
            self.next_id += 1
            ids.append(f"bp{self.next_id}")
        return ids

    def plan_pipe(self, medium, x1, y1, x2, y2):
        self.calls.append(("pipe", medium, x1, y1, x2, y2))
        status = self.answers.pop(0) if self.answers else "ok"
        if status != "ok":
            return Result(status, message="nope")
        pieces = int(abs(x1 - x2) + abs(y1 - y2)) // g.TILE_M
        ids = self._ids(1 if self.short else pieces)
        sx = (x2 > x1) - (x2 < x1)
        sy = (y2 > y1) - (y2 < y1)
        medium = topo.fluid_medium(medium)
        for i, jid in enumerate(ids):
            mid = (x1 + sx * (i + 0.5) * g.TILE_M, y1 + sy * (i + 0.5) * g.TILE_M)
            self.pending.append(Job(jid, "pipe", medium, mid[0], mid[1]))
        return Result("ok", ids)

    def plan_bridge(self, medium, x, y, axis):
        self.calls.append(("bridge", medium, x, y, axis))
        status = self.answers.pop(0) if self.answers else "ok"
        if status != "ok":
            return Result(status, message="nope")
        return Result("ok", self._ids(1))

    def cancel(self, blueprint_id):
        self.cancelled.append(blueprint_id)
        return Result("ok")


def entry(ins, outs=()):
    """autoplay_roles.fluids_for() shape."""
    order = list(ins) + [f for f in outs if f not in ins]
    return {"in": list(ins), "out": list(outs), "order": order}


def term(name, tiles, producer=False):
    return {"name": name, "producer": producer, "tiles": tiles}


class RolesTests(harness.StubTestCase):
    def test_presets_seeded_and_operator_edit_kept(self):
        self.assertEqual(roles.presets(), roles.DEFAULT_ROLE_PRESETS)
        self.assertEqual(self.world.notebook.data[roles.PRESETS_KEY], roles.DEFAULT_ROLE_PRESETS)
        self.world.notebook.set(roles.PRESETS_KEY, {"mine": ["oil"], "factory": ["water"]})
        got = roles.presets()
        self.assertEqual(got["mine"], ["oil"])
        self.assertEqual(got["factory"], ["water"])
        self.assertEqual(got["bio_volcanic"], roles.DEFAULT_ROLE_PRESETS["bio_volcanic"])
        self.assertEqual(self.world.notebook.data[roles.PRESETS_KEY], got)

    def test_fluids_for_multiple_roles_in_order(self):
        presets = {
            "farm": ["water"],
            "wildlife": {"in": ["ammonia", "water"]},
            "power": {"in": ["steam", "oil"]},
            "condenser": {"in": ["steam"], "out": ["water"]},
        }
        got = roles.fluids_for(["power", "wildlife", "farm"], presets)
        self.assertEqual(
            got,
            {
                "in": ["steam", "oil", "ammonia", "water"],
                "out": [],
                "supply": [],
                "order": ["steam", "oil", "ammonia", "water"],
            },
        )
        got = roles.fluids_for(["condenser", "farm"], presets)
        self.assertEqual(got, {"in": ["steam", "water"], "out": ["water"], "supply": [], "order": ["steam", "water"]})
        self.assertEqual(roles.fluids_for(["nope"], presets)["order"], [])
        self.assertEqual(roles.fluids_for(None, presets)["order"], [])

    def test_default_sub_roles(self):
        presets = roles.DEFAULT_ROLE_PRESETS
        self.assertNotIn("steam_hub", presets)
        self.assertEqual(presets["condenser"], {"in": ["steam"], "out": ["water"]})
        self.assertNotIn("refinery_quicksilver", presets)
        self.assertEqual(
            roles.fluids_for("refinery", presets)["order"],
            [
                "raw_sulfur_gas",
                "raw_chlorine",
                "raw_cryofluid",
                "raw_quicksilver",
                "sulfur_gas",
                "chlorine",
                "cryofluid",
                "quicksilver",
            ],
        )
        self.assertEqual(presets["wildlife_ammonia"], {"in": ["ammonia"]})
        self.assertEqual(presets["liquifier_deep"], {"out": ["deep_essence"]})
        self.assertEqual(presets["storage_steam"], {"in": ["steam"], "out": ["steam"]})
        self.assertEqual(len(presets["biomass_mixer"]["in"]), len(roles.BIOMES))
        self.assertTrue(
            all(fluid in roles.FLUIDS for preset in presets.values() for side in preset.values() for fluid in side)
        )

    def test_home_always_farms(self):
        presets = {"farm": ["water"], "wildlife": ["ammonia"]}
        demand = roles.demand(["home", "o1", "o2"], {"home": "wildlife", "o1": ["wildlife"]}, presets, "home")
        self.assertEqual({o: e["order"] for o, e in demand.items()}, {"home": ["ammonia", "water"], "o1": ["ammonia"]})
        self.assertEqual(roles.demand(["home"], {}, presets, "home")["home"]["in"], ["water"])

    def test_prune_gone_outposts(self):
        self.world.notebook.set(roles.ROLES_KEY, {"o1": "farm", "gone": "farm"})
        self.assertEqual(roles.prune_roles({"o1"}), 1)
        self.assertEqual(self.world.notebook.data[roles.ROLES_KEY], {"o1": "farm"})


class RequestTests(unittest.TestCase):
    def setUp(self):
        self.pump = term("wp1", g.extractor_tiles(205, 5), producer=True)  # tiles 18..21
        self.outpost = term("o1", g.outpost_tiles(10, 30))  # tiles 0..3

    def request(self, layer, terms=None, demand=None, failed=()):
        terms = terms or [self.pump, self.outpost]
        _walls, held = fp.split_labels(layer, "water")
        return fp.route_request(
            "water", terms, layer, held, demand or {"o1": entry(["water"])}, {"water", "oil"}, set(failed)
        )

    def test_empty_map_starts_at_producer_and_targets_consumers_only(self):
        req = self.request({})
        self.assertEqual(req["start"], "wp1")
        self.assertEqual(sorted(req["sources"]), sorted(self.pump["tiles"]))
        self.assertEqual(set(req["goals"].values()), {"o1"})

    def test_connected_terminal_sources_from_network(self):
        layer = {tile: "water" for tile in g.run_tiles(k(3, 0), k(18, 0))}
        req = self.request(layer)
        self.assertEqual(sorted(req["connected"]), ["o1", "wp1"])
        self.assertEqual(req["goals"], {})

    def test_full_and_failed(self):
        layer = {tile: "oil" for tile in self.outpost["tiles"]}
        req = self.request(layer)
        self.assertEqual(req["full"], ["o1"])
        self.assertEqual(req["goals"], {})
        req = self.request({}, failed=[("water", "o1")])
        self.assertEqual(req["failed"], ["o1"])
        self.assertEqual(req["goals"], {})

    def test_last_port_reserved_for_earlier_fluid(self):
        # o1 wants oil before water; one free liquid tile left and oil not yet there -> water waits
        tiles = self.outpost["tiles"]
        layer = {tile: "brine" for tile in tiles[1:]}
        req = self.request(layer, demand={"o1": entry(["oil", "water"])})
        self.assertEqual(req["reserved"], ["o1"])
        # oil has no producer on the map: it claims nothing
        _walls, held = fp.split_labels(layer, "water")
        req = fp.route_request(
            "water", [self.pump, self.outpost], layer, held, {"o1": entry(["oil", "water"])}, {"water"}, set()
        )
        self.assertEqual(set(req["goals"].values()), {"o1"})

    def test_terminals_and_order(self):
        producers = [
            {"name": "wp2", "fluid": "water", "tiles": []},
            {"name": "op1", "fluid": "oil", "tiles": []},
            {"name": "wp1", "fluid": "water", "tiles": []},
        ]
        demand = {
            "o2": entry(["water"]),
            "o1": entry(["oil"]),
            "o3": entry(["steam"], ["water"]),
            "o4": entry(["water"], ["water"]),
        }
        terms = fp.terminals("water", producers, {"o1": (0, 0), "o2": (100, 0), "o3": (200, 0), "o4": (300, 0)}, demand)
        self.assertEqual(
            [(t["name"], t["producer"]) for t in terms],
            [("wp1", True), ("wp2", True), ("o3", True), ("o4", True), ("o2", False)],
        )
        self.assertEqual(
            fo.fluid_priority(["ammonia", "steam", "water", "brine"], {}, {}), ["water", "steam", "ammonia", "brine"]
        )
        planned = producers + [
            {"name": "site:far", "fluid": "water", "tiles": [], "rank": 9},
            {"name": "contact:1_1", "fluid": "water", "tiles": [], "rank": 3},
        ]
        terms = fp.terminals("water", planned, {}, {})
        self.assertEqual(
            [t["name"] for t in terms], ["wp1", "wp2", "contact:1_1", "site:far"]
        )  # built first, then nearest planned

    def test_site_rows(self):
        rows = fp.site_rows(
            [
                Site("water", 205, 5, "wp1"),
                Site("water", 0, 0, ""),
                Site("thermal", 405, 5, "cap1"),
                Site("exotic", 605, 5, "ex1", fluid="ammonia"),
                Site("mineral", 1, 1, "x"),
            ]
        )
        self.assertEqual(
            [(r["name"], r["fluid"]) for r in rows], [("wp1", "water"), ("cap1", "steam"), ("ex1", "ammonia")]
        )


class RouteTests(unittest.TestCase):
    """find_route(): never touches another fluid or a foreign footprint, bridges a forced crossing."""

    def route(self, layer, terms, structures, fluid="water"):
        walls, held = fp.split_labels(layer, fluid)
        req = fp.route_request(
            fluid, terms, layer, held, {t["name"]: entry([fluid]) for t in terms if not t["producer"]}, {fluid}, set()
        )
        foreign = fp.foreign_footprints(structures, terms)
        return (req, fp.find_route(req, walls, foreign), walls, foreign)

    def test_route_avoids_other_fluid_and_foreign_footprint(self):
        pump = term("wp1", g.extractor_tiles(205, 25), producer=True)
        outpost = term("o1", g.outpost_tiles(0, 0))
        oil = {k(x, 1): "oil" for x in range(5, 15)}
        structures = {"wp1": pump["tiles"], "o1": outpost["tiles"], "op1": g.extractor_tiles(105, 25)}
        req, path, _walls, foreign = self.route(oil, [pump, outpost], structures)
        tiles = {t for t, _b in path}
        self.assertTrue(path)
        self.assertFalse(tiles & set(oil))
        self.assertFalse(tiles & foreign)
        self.assertEqual(req["goals"][path[-1][0]], "o1")
        self.assertEqual(len([t for t in tiles if t in outpost["tiles"]]), 1)  # one port taken

    def test_forced_crossing_is_a_bridge(self):
        # an endless vertical oil line at x tile 10 separates pump and outpost
        pump = term("wp1", g.extractor_tiles(205, 15), producer=True)
        outpost = term("o1", g.outpost_tiles(0, 0))
        oil = {k(10, y): "oil" for y in range(-60, 60)}
        _req, path, _walls, _foreign = self.route(oil, [pump, outpost], {"wp1": pump["tiles"], "o1": outpost["tiles"]})
        steps = g.path_plan(path)
        bridges = [s for s in steps if s[0] == "bridge"]
        self.assertEqual(len(bridges), 1)
        self.assertEqual((g.tile_xy(bridges[0][1])[0], bridges[0][2]), (10, "horizontal"))
        self.assertEqual(fp.route_cost(steps)[1], 1)

    def storage_setup(self, takes):
        pump = term("wp1", g.extractor_tiles(205, 15), producer=True)
        outpost = term("o1", g.outpost_tiles(0, 0))
        store = term("st", g.outpost_tiles(100, 0))  # between pump and o1
        structures = {"wp1": pump["tiles"], "o1": outpost["tiles"], "st": store["tiles"]}
        terms = [pump, outpost] + ([store] if takes else [])
        buffers = fp.storage_buffers({"st": (100.0, 0.0), "o1": (0.0, 0.0)}, {"st": ["storage"], "o1": "factory"})
        return terms, structures, buffers

    def test_storage_buffer_walls_other_fluids(self):
        terms, structures, buffers = self.storage_setup(False)
        wall, soft = fp.buffer_split(buffers, terms, structures)
        self.assertEqual(soft, set())
        self.assertFalse(wall & set(structures["wp1"]) or wall & set(structures["o1"]))
        walls, held = fp.split_labels({}, "water")
        req = fp.route_request("water", terms, {}, held, {"o1": entry(["water"])}, {"water"}, set())
        path = fp.find_route(req, walls, fp.foreign_footprints(structures, terms) | wall, soft)
        self.assertTrue(path)
        self.assertFalse({t for t, _b in path} & wall)

    def test_storage_buffer_soft_for_its_own_fluids(self):
        terms, structures, buffers = self.storage_setup(True)
        wall, soft = fp.buffer_split(buffers, terms, structures)
        self.assertEqual(wall, set())
        self.assertEqual(len(soft), 12 * 12 - 16)
        self.assertEqual(set(buffers), {"st"})

    def test_gas_ignores_liquid(self):
        cap = term("cap1", g.extractor_tiles(205, 15), producer=True)
        outpost = term("o1", g.outpost_tiles(0, 0))
        water = {k(10, y): "water" for y in range(-60, 60)}  # liquid layer: not on the gas layer at all
        _req, path, _walls, _foreign = self.route(
            {}, [cap, outpost], {"cap1": cap["tiles"], "o1": outpost["tiles"]}, fluid="steam"
        )
        self.assertTrue(path)
        self.assertTrue({t for t, _b in path} & set(water))  # crosses the water lane without a bridge
        self.assertFalse([s for s in g.path_plan(path) if s[0] == "bridge"])

    def test_same_fluid_network_reused(self):
        pump = term("wp1", g.extractor_tiles(205, 15), producer=True)
        o1 = term("o1", g.outpost_tiles(10, 30))  # tiles 0..3 x 0..3
        o2 = term("o2", g.outpost_tiles(10, 230))  # tiles 0..3 x 20..23
        water = {tile: "water" for tile in g.run_tiles(k(3, 1), k(18, 1))}  # o1 <-> wp1 exists
        req, path, _walls, _foreign = self.route(
            water, [pump, o1, o2], {"wp1": pump["tiles"], "o1": o1["tiles"], "o2": o2["tiles"]}
        )
        self.assertIsNone(req["start"])
        self.assertIn(path[0][0], water)
        self.assertEqual(req["goals"][path[-1][0]], "o2")


class QueueTests(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        self.blueprints = Blueprints()
        self.world.services["construction_blueprint"] = self.blueprints

    def test_route_records_networks_and_planned(self):
        steps = [("run", k(0, 0), k(4, 0)), ("bridge", k(5, 0), "horizontal"), ("run", k(6, 0), k(6, 3))]
        status, ids, _msg = bq.queue_pipe_route("water", steps, 0, set())
        self.assertEqual(status, "ok")
        self.assertEqual(
            self.blueprints.calls,
            [
                ("pipe", "water", 5.0, 5.0, 45.0, 5.0),
                ("bridge", "water", 55.0, 5.0, "horizontal"),
                ("pipe", "water", 65.0, 5.0, 65.0, 35.0),
            ],
        )
        self.assertEqual(len(ids), 4 + 1 + 3)
        networks = self.world.notebook.data[topo.NETWORKS_KEY]["water"]
        self.assertEqual(
            networks, [[5.0, 5.0, 45.0, 5.0], [45.0, 5.0, 45.0, 5.0], [65.0, 5.0, 65.0, 5.0], [65.0, 5.0, 65.0, 35.0]]
        )
        labels = topo.planned_labels(self.world.notebook.data[topo.NETWORKS_KEY])["liquid"]
        self.assertNotIn(k(5, 0), labels)  # the crossed line's tile stays theirs
        self.assertEqual({e["f"] for e in bq.planned().values()}, {"water"})

    def test_rejection_cancels_whole_route(self):
        self.blueprints.answers = ["ok", "blocked"]
        steps = [("run", k(0, 0), k(4, 0)), ("run", k(4, 0), k(4, 3))]
        status, ids, _msg = bq.queue_pipe_route("water", steps, 0, set())
        self.assertEqual((status, ids), ("blocked", []))
        self.assertEqual(len(self.blueprints.cancelled), 4)
        self.assertNotIn(topo.NETWORKS_KEY, self.world.notebook.data)

    def test_short_run_cancelled_unless_reuse_explains_it(self):
        self.blueprints.short = True
        steps = [("run", k(0, 0), k(4, 0))]
        status, _ids, _msg = bq.queue_pipe_route("water", steps, 0, set())
        self.assertEqual(status, "short")
        self.assertEqual(len(self.blueprints.cancelled), 1)
        held = {k(x, 0) for x in range(4)}  # 3 of 4 pieces may already exist
        status, ids, _msg = bq.queue_pipe_route("water", steps, 0, held)
        self.assertEqual((status, len(ids)), ("ok", 1))


class FluidPassTests(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        self.log = harness.TreeConsole(module="infra_planner")
        self.blueprints = Blueprints()
        self.world.services["construction_blueprint"] = self.blueprints
        self.world.services["journal"] = Journal([Site("water", 205, 5, "wp1"), Site("oil", 405, 5, "op1")])
        self.world.home.x = 10.0  # top-left anchor: footprint tiles 0..3 x 0..3
        self.world.home.y = 30.0
        self.world.inventory.add("liquid_pipe_segment", 1000)
        setattr(builtins, "list_pipes", list)

    def tearDown(self):
        delattr(builtins, "list_pipes")
        super().tearDown()

    def run_pass(self, planner=None):
        planner = planner or fp.FluidPlanner(self.log)
        return planner.run_pass(topo.Topology().read())

    def test_home_gets_water_first_then_done(self):
        self.assertEqual(self.run_pass(), "queued")
        self.assertEqual(len(self.blueprints.calls), 1)
        kind, fluid, x1, _y1, x2, _y2 = self.blueprints.calls[0]
        self.assertEqual((kind, fluid), ("pipe", "water"))
        # pump footprint tiles 18..21 -> home east edge tile 3
        self.assertEqual({x1, x2}, {35.0, 185.0})
        self.assertEqual(self.run_pass(), "done")
        status = self.world.notebook.data[fp.PORT_STATUS_KEY]
        self.assertEqual(status["home"]["liquid"], ["water"])

    def test_oil_network_stays_off_water(self):
        self.world.notebook.set(roles.ROLES_KEY, {"home": "power"})
        self.assertEqual(self.run_pass(), "queued")  # water (farm) first
        self.assertEqual(self.run_pass(), "queued")  # then oil
        oil_calls = [c for c in self.blueprints.calls if c[1] == "oil"]
        self.assertTrue(oil_calls)
        labels = topo.planned_labels(self.world.notebook.data[topo.NETWORKS_KEY])["liquid"]
        self.assertEqual(set(labels.values()), {"water", "oil"})  # no tile claimed by both (would be FOREIGN)
        self.assertEqual(self.run_pass(), "done")

    def test_condenser_outpost_feeds_home_without_pump(self):
        self.world.services["journal"] = Journal([])
        self.world.add_outpost("o1").x = 400.0
        self.world.outposts["o1"].y = 0.0
        self.world.notebook.set(roles.ROLES_KEY, {"o1": "condenser"})
        self.assertEqual(self.run_pass(), "queued")  # water: o1 (producer) -> home (farm)
        self.assertEqual({c[1] for c in self.blueprints.calls}, {"water"})
        self.assertEqual(self.run_pass(), "done")  # steam: no producer
        self.assertIn("Fluid steam: no producer", self.debug_log())

    def test_refinery_output_reaches_wildlife(self):
        self.world.services["journal"] = Journal([Site("exotic", 805, 5, "ex1", fluid="raw_quicksilver")])
        for oid, x in (("ref", 400.0), ("zoo", 600.0)):
            self.world.add_outpost(oid).x = x
            self.world.outposts[oid].y = 0.0
        self.world.notebook.set(roles.ROLES_KEY, {"ref": "refinery", "zoo": "wildlife_quicksilver"})
        self.world.inventory.items = {"liquid_pipe_segment": 1000}
        for _ in range(4):
            self.run_pass()
        networks = self.world.notebook.data[topo.NETWORKS_KEY]
        self.assertIn("raw_quicksilver", networks)
        self.assertIn("quicksilver", networks)
        self.assertEqual(self.run_pass(), "done")

    def test_stock_short_waits(self):
        self.world.inventory.items = {}
        self.assertEqual(self.run_pass(), "waiting")
        self.assertEqual(self.blueprints.calls, [])
        self.assertEqual(
            site_supply.construction_rush(), {"liquid_pipe_segment": 15}
        )  # the route (15 pieces, below the target) at NEED

    def test_urgent_route_short_on_stock_builds_a_chunk(self):
        self.world.notebook.set(site_supply.CONSTRUCTION_STOCK_KEY, {"liquid_pipe_segment": {"target": 5, "need": 0}})
        self.world.inventory.items = {"liquid_pipe_segment": 5}
        planner = fp.FluidPlanner(self.log)
        self.assertEqual(self.run_pass(planner), "queued")  # wp1 -> home needs more than 5 pieces
        self.assertEqual(len(self.blueprints.calls), 1)
        self.assertIn("(urgent chunk)", self.debug_log())
        self.assertEqual(self.run_pass(planner), "waiting")  # the chunk's job is still open
        self.assertEqual(len(self.blueprints.calls), 1)

    def test_urgent_chunk_waits_for_full_stock(self):
        self.world.notebook.set(site_supply.CONSTRUCTION_STOCK_KEY, {"liquid_pipe_segment": {"target": 10, "need": 0}})
        self.world.inventory.items = {"liquid_pipe_segment": 5}
        self.assertEqual(self.run_pass(), "waiting")
        self.assertEqual(self.blueprints.calls, [])
        self.assertEqual(site_supply.construction_rush(), {"liquid_pipe_segment": 10})
        self.world.inventory.items = {"liquid_pipe_segment": 10}
        self.assertEqual(self.run_pass(), "queued")
        self.assertEqual(site_supply.construction_rush(), {})

    def test_no_producer_is_done(self):
        self.world.services["journal"] = Journal([])
        self.assertEqual(self.run_pass(), "done")
        self.assertIn("no producer", self.debug_log())

    def test_rejected_route_not_retried(self):
        self.blueprints.answers = ["blocked"]
        planner = fp.FluidPlanner(self.log)
        self.assertEqual(self.run_pass(planner), "done")
        self.assertEqual(self.run_pass(planner), "done")
        self.assertEqual(len(self.blueprints.calls), 1)

    def test_untapped_site_piped_ahead_before_its_pump(self):
        self.world.services["journal"] = Journal(
            [Site("water", 205, 5, "wp1")], [Site("water", 1505, 5, site_id="far")]
        )
        planner = fp.FluidPlanner(self.log)
        self.assertEqual(self.run_pass(planner), "queued")  # wp1 -> home (urgent)
        self.assertEqual(self.run_pass(planner), "ahead")  # then toward the untapped site, before any pump stands there
        ahead = [e for e in bq.planned().values() if e["p"] == st.PLAN_AHEAD_PRIO]
        self.assertTrue(ahead)
        self.assertIn("1 planned producer(s)", self.debug_log())

    def test_inferred_contact_starts_a_network_ahead(self):
        self.world.services["journal"] = Journal([])
        contact = [{"x": 805.0, "y": 5.0, "fluid": "water"}]
        with mock.patch.object(fo, "read_contacts", return_value=contact):
            self.assertEqual(self.run_pass(), "ahead")  # only a planned producer: plan-ahead chunk from the contact
        self.assertEqual({c[1] for c in self.blueprints.calls}, {"water"})
        self.assertIn("1 inferred contact(s)", self.debug_log())

    def test_liquifiers_piped_to_the_mixer_outpost(self):
        self.world.services["journal"] = Journal([])
        for oid, x in (("liq_f", 400.0), ("liq_c", 400.0), ("mix", 800.0)):
            self.world.add_outpost(oid).x = x
            self.world.outposts[oid].y = 0.0 if oid != "liq_c" else 400.0
        mixer = Building(self.world, "mixer_1", self.world.outposts["mix"])
        mixer.type_id = "biomass_mixer"  # built by hand, no designation
        self.world.components[mixer.id] = mixer
        self.world.notebook.set(roles.ROLES_KEY, {"liq_f": "liquifier_frozen", "liq_c": "liquifier_coastal"})
        for _ in range(3):
            self.run_pass()
        networks = self.world.notebook.data[topo.NETWORKS_KEY]
        self.assertIn("frozen_essence", networks)
        self.assertIn("coastal_essence", networks)
        self.assertEqual(self.run_pass(), "done")
        self.assertNotIn("biomass_mixer", roles.role_list(roles.outpost_roles().get("mix")))  # designation untouched


class OutlookTests(unittest.TestCase):
    def test_priority_follows_need_over_supply(self):
        consumers = {"water": (1, 0), "oil": (2, 0)}
        self.assertEqual(fo.fluid_priority(["water", "oil"], consumers, {}), ["oil", "water"])
        self.assertEqual(fo.fluid_priority(["water", "oil"], consumers, {"oil": 3}), ["water", "oil"])
        # designated-only consumers count FORECAST_WEIGHT each: 2 x 0.5 ties with 1 built, FLUID_ORDER breaks it
        self.assertEqual(fo.fluid_priority(["oil", "water"], {"water": (1, 0), "oil": (0, 2)}, {}), ["water", "oil"])

    def test_priority_phase_weights(self):
        consumers = {"water": (1, 0), "steam": (1, 0)}
        weights = {"early": {}, "late": {"steam": 3.0}}
        self.assertEqual(fo.fluid_priority(["water", "steam"], consumers, {}, "early", weights), ["water", "steam"])
        self.assertEqual(fo.fluid_priority(["water", "steam"], consumers, {}, "late", weights), ["steam", "water"])

    def test_consumer_counts_built_vs_designated(self):
        presets = roles.DEFAULT_ROLE_PRESETS
        roles_map = {"o1": "factory", "o2": "power"}
        demand = roles.demand(["o1", "o2"], roles_map, presets)
        counts = fo.consumer_counts(demand, roles_map, presets, {"o1": {"fabricator": 1}, "o2": {}})
        self.assertEqual(counts, {"water": (1, 0), "oil": (1, 1), "steam": (1, 1)})
        self.assertEqual(fo.consumer_counts(demand, roles_map, presets, None)["oil"], (2, 0))  # unreadable: all built

    def test_observed_mixer_adds_its_role(self):
        roles_map = {"o1": "liquifier_frozen", "o2": ["biomass_mixer"]}
        out = fo.with_observed_roles(roles_map, {"mx": {"biomass_mixer": 1}, "o1": {}, "o2": {"biomass_mixer": 1}})
        self.assertEqual(out["mx"], ["biomass_mixer"])
        self.assertEqual(out["o2"], ["biomass_mixer"])
        self.assertEqual(out["o1"], "liquifier_frozen")
        self.assertNotIn("mx", roles_map)

    def test_inferred_contacts_by_biome(self):
        targets = {
            "poi_100_200": {"reason": "research_required"},  # frozen: water only
            "poi_300_200": {"reason": "research_required"},  # biome unknown: any tech kind
            "poi_500_200": {"reason": "tier_too_low"},  # oil
            "poi_700_200": {"reason": "too_hard"},  # mineral
            "poi_905_5": {"reason": "tier_too_low"},  # on a discovered site
            "site_abc": {"reason": "tier_too_low"},
        }
        biomes = {100: "frozen", 500: "volcanic"}
        rows = [{"id": "s1", "x": 905.0, "y": 5.0}]
        out = fo.inferred_contacts(targets, lambda x, y: biomes.get(int(x)), rows)
        self.assertEqual(out, [{"x": 100.0, "y": 200.0, "fluid": "water"}, {"x": 500.0, "y": 200.0, "fluid": "oil"}])

    def test_planned_producers_names_and_rank(self):
        rows = [
            {"id": "near", "fluid": "water", "x": 205.0, "y": 5.0, "machine": ""},
            {"id": "ghosted", "fluid": "water", "x": 605.0, "y": 5.0, "machine": ""},
            {"id": "built", "fluid": "water", "x": 405.0, "y": 5.0, "machine": "wp1"},
        ]
        ghosts = [{"id": "bp7", "kind": "water_pump", "x": 605.0, "y": 5.0}]
        contacts = [{"x": 1005.0, "y": 5.0, "fluid": "water"}]
        demand = {"home": entry(["water"])}
        out = fo.planned_producers(rows, ghosts, contacts, demand, {"home": (0.0, 0.0)})
        self.assertEqual(
            [r["name"] for r in sorted(out, key=lambda r: r["rank"])], ["site:near", "ghost:bp7", "contact:1005_5"]
        )
        self.assertEqual(out[0]["tiles"], g.extractor_tiles(205.0, 5.0))


class AtomicBudgetTests(unittest.TestCase):
    def test_label_slice(self):
        items = [(k(i, 0), "water" if i % 2 else "oil") for i in range(fp.LABEL_CHUNK)]
        self.assertLess(ops(fp.label_slice, items, "water"), ATOMIC_STEP_BUDGET)


if __name__ == "__main__":
    unittest.main()
