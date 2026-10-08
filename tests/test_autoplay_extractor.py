"""Tests for autoplay/lib/supply_tiers.py, extractor_plan.py and the plan-ahead paths of fluid_plan/power_plan."""
import builtins
import unittest

import harness
import grid_geom as g
import supply_tiers as st
import extractor_plan as ep
import fluid_plan as fp
import power_plan as pp
import blueprint_queue as bq
import autoplay_roles as roles
import infra_topology as topo
from construction_plan import PRIORITY_KEY, EXTRACTOR_KITS
from game_stubs import Recipe
from test_autoplay_power import Result, Job, Site, Journal, Power, Grid
from test_autoplay_power import Blueprints as PowerBlueprints
from test_autoplay_fluid import Blueprints as PipeBlueprints


def k(tx, ty):
    return g.tile_key(tx, ty)


def entry(ins, outs=(), supply=None):
    """autoplay_roles.fluids_for() shape; supply defaults to outs."""
    return {"in": list(ins), "out": list(outs), "supply": list(outs if supply is None else supply),
            "order": list(ins) + [f for f in outs if f not in ins]}


class StructJob(Job):
    def __init__(self, jid, kind, x, y, item, count=1):
        super().__init__(jid, kind, None, x, y)
        self.required_item = item
        self.required_count = count


class Blueprints(PipeBlueprints):
    """Pipe fake plus plan_structure (job needs its EXTRACTOR_KITS item x1) and plan_power_line."""

    def __init__(self, answers=()):
        super().__init__(answers)
        self.structure_answers = []

    def plan_structure(self, kind, x, y, rotation=0):
        self.calls.append(("structure", kind, x, y))
        status = self.structure_answers.pop(0) if self.structure_answers else "ok"
        if status != "ok":
            return Result(status, message="nope")
        ids = self._ids(1)
        self.jobs.append(StructJob(ids[0], kind, x, y, EXTRACTOR_KITS[kind]))
        return Result("ok", ids)

    def cancel(self, blueprint_id):
        self.jobs = [job for job in self.jobs if job.id != blueprint_id]
        return super().cancel(blueprint_id)

    def plan_power_line(self, x1, y1, x2, y2):
        self.calls.append(("power", x1, y1, x2, y2))
        return Result("ok", self._ids(int(abs(x1 - x2) + abs(y1 - y2)) // g.TILE_M))


class TierTests(unittest.TestCase):
    """The user's example: a power outpost by three steam vents, home farming water, oil nobody takes."""

    def setUp(self):
        self.outpost_xy = {"pwr": (0.0, 0.0), "home": (2000.0, 0.0)}
        self.demand = {"pwr": entry(["steam"]), "home": entry(["water"])}

    def sites(self, built=()):
        specs = [("thermal", 1005, 5, "v_far"), ("thermal", 205, 5, "v1"), ("thermal", 305, 5, "v2"),
                 ("water", 1505, 5, "w1"), ("oil", 105, 205, "o1")]
        return st.fluid_sites([Site(kind, x, y, "m_" + sid if sid in built else "", site_id=sid) for kind, x, y, sid in specs])

    def test_now_then_soon_then_ahead_then_spare(self):
        cands = st.fluid_candidates(self.sites(), self.demand, self.outpost_xy, set())
        self.assertEqual([(c[3], c[0]) for c in cands],
                         [("v1", st.TIER_NOW), ("w1", st.TIER_NOW), ("v2", st.TIER_SOON), ("v_far", st.TIER_AHEAD), ("o1", st.TIER_SPARE)])
        self.assertEqual([st.tier_prio(c[0]) for c in cands], [0, 0, 0, st.PLAN_AHEAD_PRIO, st.PLAN_AHEAD_PRIO])

    def test_supplied_fluid_far_site_is_plan_ahead(self):
        cands = st.fluid_candidates(self.sites(built=("v1",)), self.demand, self.outpost_xy, set())
        self.assertEqual({c[3]: c[0] for c in cands}["v_far"], st.TIER_AHEAD)
        # a planned ghost counts as supply too; a skipped site is no candidate
        cands = st.fluid_candidates(self.sites(), self.demand, self.outpost_xy, {"v1"}, {"w1"})
        self.assertEqual([(c[3], c[0]) for c in cands][:2], [("v2", st.TIER_SOON), ("v_far", st.TIER_AHEAD)])

    def test_new_consumer_makes_its_fluid_urgent(self):
        demand = dict(self.demand, pwr=entry(["steam", "oil"]))
        cands = st.fluid_candidates(self.sites(built=("v1", "w1")), demand, self.outpost_xy, set())
        self.assertEqual(cands[0][3], "o1")
        self.assertEqual(cands[0][0], st.TIER_NOW)

    def test_urgent_producers(self):
        rows = self.sites(built=("v_far",))
        self.assertEqual(st.urgent_producers(rows, self.demand, self.outpost_xy), {"m_v_far"})   # only one: nearest
        rows = self.sites(built=("v_far", "v1", "v2", "o1"))
        self.assertEqual(st.urgent_producers(rows, self.demand, self.outpost_xy), {"m_v1", "m_v2"})
        rows = self.sites(built=("w1",))
        demand = dict(self.demand, src=entry([], ["water"]))   # an outpost that is a water source: the far well waits
        self.assertEqual(st.urgent_producers(rows, demand, self.outpost_xy), set())
        demand = dict(self.demand, cond=entry(["steam"], ["water"], supply=[]))   # condenser / tank: no supply, well stays urgent
        self.assertEqual(st.urgent_producers(rows, demand, self.outpost_xy), {"m_w1"})

    def test_condenser_and_tank_do_not_block_tapping_a_well(self):
        demand = dict(self.demand, cond=entry(["steam"], ["water"], supply=[]), tank=entry(["water"], ["water"], supply=[]))
        cands = st.fluid_candidates(self.sites(), demand, self.outpost_xy, set())
        self.assertEqual({c[3]: c[0] for c in cands}["w1"], st.TIER_NOW)
        presets = roles.DEFAULT_ROLE_PRESETS
        self.assertEqual(roles.fluids_for(["condenser", "storage_water"], presets)["supply"], [])
        self.assertEqual(roles.fluids_for(["refinery"], presets)["supply"], ["sulfur_gas", "chlorine", "cryofluid", "quicksilver"])


class ChunkTests(unittest.TestCase):
    def test_truncate_steps(self):
        steps = [("run", k(0, 0), k(10, 0)), ("bridge", k(11, 0), "horizontal"), ("run", k(12, 0), k(12, 30))]
        self.assertEqual(g.truncate_steps(steps, 100), (steps, False))
        self.assertEqual(g.truncate_steps(steps, 12), (steps[:2], True))
        self.assertEqual(g.truncate_steps(steps, 11), (steps[:1], True))   # bridge does not fit
        self.assertEqual(g.truncate_steps(steps, 4), ([("run", k(0, 0), k(4, 0))], True))
        self.assertEqual(g.truncate_steps(steps, 20), (steps[:2] + [("run", k(12, 0), k(12, 8))], True))

    def test_capped_l_routes(self):
        routes = g.capped_l_routes(k(0, 0), k(30, 30), 40)
        self.assertEqual(routes[0], [[5.0, 5.0, 305.0, 5.0], [305.0, 5.0, 305.0, 105.0]])
        self.assertEqual(routes[1], [[5.0, 5.0, 5.0, 305.0], [5.0, 305.0, 105.0, 305.0]])
        self.assertEqual(g.capped_l_routes(k(0, 0), k(100, 0), 40), [[[5.0, 5.0, 405.0, 5.0]]])


class DrillTests(unittest.TestCase):
    def setUp(self):
        self.rows = ep.mining_sites([
            Site("mineral", 1205, 5, site_id="iron_near", item="iron_ore", hardness=1, purity="standard"),
            Site("mineral", 3005, 5, site_id="iron_far", item="iron_ore", hardness=1, purity="pure"),
            Site("mineral", 1305, 205, site_id="sil", item="silicon", hardness=3),
            Site("mineral", 1105, 5, site_id="cob", item="cobalt", hardness=2),
        ])
        self.smelter_boxes = [g.outpost_box(1000.0, 0.0)]

    def test_one_drill_per_wanted_ore_nearest_smelter(self):
        cands = ep.drill_candidates(self.rows, {"iron_ore", "silicon"}, self.smelter_boxes, set())
        self.assertEqual([c[3] for c in cands], ["iron_near", "sil"])
        self.assertTrue(all(c[0] == st.TIER_SOON for c in cands))

    def test_drilled_ore_skipped(self):
        rows = ep.mining_sites([Site("mineral", 3005, 5, "d1", site_id="iron_far", item="iron_ore")])
        taken = ep.drilled_sites(rows, [])
        self.assertEqual(taken, {"iron_far"})
        cands = ep.drill_candidates(self.rows, {"iron_ore", "silicon"}, self.smelter_boxes, taken)
        self.assertEqual([c[3] for c in cands], ["sil"])
        ghost = {"id": "j1", "kind": "mining_drill_industrial", "x": 1305.0, "y": 205.0}
        self.assertEqual(ep.drilled_sites(self.rows, [ghost]), {"sil"})

    def test_drill_kind(self):
        stock = {"mining_drill_heavy_kit": 1}.get
        in_stock = lambda item: stock(item, 0)
        self.assertEqual(ep.drill_kind(1, in_stock, set()), ("mining_drill_heavy", "mining_drill_heavy_kit"))
        self.assertEqual(ep.drill_kind(3, lambda item: 0, set()), ("mining_drill_industrial", "mining_drill_industrial_kit"))
        self.assertEqual(ep.drill_kind(1, lambda item: 0, set()), ("mining_drill", "mining_drill_kit"))
        self.assertIsNone(ep.drill_kind(4, lambda item: 0, {"mining_drill_heavy"}))


class PassCase(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        self.log = harness.TreeConsole(module="infra_planner")
        self.blueprints = Blueprints()
        self.world.services["construction_blueprint"] = self.blueprints
        self.world.home.x = 0.0
        self.world.home.y = 0.0
        setattr(builtins, "list_pipes", lambda: [])

    def tearDown(self):
        delattr(builtins, "list_pipes")
        super().tearDown()

    def outpost(self, oid, x, y=0.0):
        ref = self.world.add_outpost(oid)
        ref.x = x
        ref.y = y
        return ref

    def read(self):
        return topo.Topology().read()


class ExtractorPassTests(PassCase):
    def setUp(self):
        super().setUp()
        self.outpost("pwr", 2000.0)
        self.world.notebook.set(roles.ROLES_KEY, {"pwr": "power"})   # steam + oil
        self.world.services["journal"] = Journal([Site("thermal", 2205, 5, site_id="vent"), Site("water", 205, 5, site_id="well"),
                                                  Site("oil", 5005, 5, site_id="oilw")])

    def structures(self):
        return [c[1] for c in self.blueprints.calls if c[0] == "structure"]

    def test_urgent_extractors_capped_at_two_open(self):
        planner = ep.ExtractorPlanner(self.log)
        self.assertEqual(planner.run_pass(self.read(), False), "queued")
        self.assertEqual(planner.run_pass(self.read(), False), "queued")
        self.assertEqual(sorted(self.structures()), ["thermal_cap", "water_pump"])
        self.assertEqual(planner.run_pass(self.read(), False), "waiting")   # oil is urgent too, but two are open
        self.assertEqual(len(self.structures()), 2)
        self.assertEqual({e["site"] for e in bq.planned().values()}, {"vent", "well"})
        self.assertEqual(self.world.notebook.data.get(PRIORITY_KEY, {}), {})
        # the water pump is built: its slot frees up
        self.blueprints.jobs = [job for job in self.blueprints.jobs if job.kind != "water_pump"]
        self.world.services["journal"] = Journal([Site("thermal", 2205, 5, site_id="vent"), Site("water", 205, 5, "wp1", site_id="well"),
                                                  Site("oil", 5005, 5, site_id="oilw")])
        bq.prune_planned({job.id for job in self.blueprints.jobs}, True)
        self.assertEqual(planner.run_pass(self.read(), False), "queued")
        self.assertEqual(self.structures()[-1], "oil_pump")

    def test_plan_ahead_needs_idle_and_kit_in_stock(self):
        self.world.notebook.set(roles.ROLES_KEY, {})
        self.world.services["journal"] = Journal([Site("water", 205, 5, "wp1", site_id="well"), Site("oil", 505, 5, site_id="oilw")])
        planner = ep.ExtractorPlanner(self.log)
        self.assertEqual(planner.run_pass(self.read(), False), "done")
        self.assertEqual(self.blueprints.calls, [])
        self.assertEqual(planner.run_pass(self.read(), True), "done")   # no oil pump in stock: nothing planned
        self.assertEqual(self.blueprints.calls, [])
        self.assertIn("waits for oil_pump in stock", self.debug_log())
        self.world.inventory.add("oil_pump", 1)
        self.assertEqual(planner.run_pass(self.read(), True), "queued")
        self.assertEqual(list(self.world.notebook.data[PRIORITY_KEY].values()), [st.PLAN_AHEAD_PRIO])
        self.assertEqual(planner.run_pass(self.read(), True), "waiting")   # own job open

    def test_rejected_site_skipped_locked_kind_dropped(self):
        self.blueprints.structure_answers = ["target_claimed", "locked"]
        planner = ep.ExtractorPlanner(self.log)
        planner.run_pass(self.read(), False)
        self.assertEqual(len(planner.skip), 1)
        self.assertEqual(len(planner.locked), 1)
        self.assertEqual(len(self.structures()), 3)   # third candidate still placed in the same pass

    def test_drill_for_smelter_ore(self):
        smelt = self.outpost("smelt", 1000.0)
        self.world.add_smelter("sm1", smelt, [Recipe("smelt_iron_ingot", {"iron_ore": 1}, "iron_ingot")])
        self.world.notebook.set(roles.ROLES_KEY, {})
        self.world.services["journal"] = Journal([Site("water", 205, 5, "wp1", site_id="well"),
                                                  Site("mineral", 1205, 5, site_id="fe", item="iron_ore", hardness=1),
                                                  Site("mineral", 1305, 5, site_id="si", item="silicon", hardness=1)])
        planner = ep.ExtractorPlanner(self.log)
        self.assertEqual(planner.run_pass(self.read(), False), "queued")
        self.assertEqual(self.blueprints.calls, [("structure", "mining_drill", 1205.0, 5.0)])
        self.assertEqual(planner.run_pass(self.read(), False), "waiting")   # iron drilled (ghost), silicon not smelted here


class FluidAheadTests(PassCase):
    def setUp(self):
        super().setUp()
        self.world.services["journal"] = Journal([Site("water", 205, 5, "wp1"), Site("water", 1505, 5, "wp2")])
        self.world.inventory.add("liquid_pipe_segment", 1000)

    def test_far_producer_routed_in_prio_chunks_after_urgent(self):
        planner = fp.FluidPlanner(self.log)
        self.assertEqual(planner.run_pass(self.read()), "queued")   # wp1 -> home
        self.assertEqual(planner.run_pass(self.read(), False), "done")   # wp2 deferred, power busy
        self.assertEqual(planner.run_pass(self.read()), "ahead")
        ahead = {bid: e for bid, e in bq.planned().items() if e["p"] == st.PLAN_AHEAD_PRIO}
        self.assertEqual(len(ahead), st.PLAN_AHEAD_MAX_PIECES)
        self.assertEqual(set(self.world.notebook.data[PRIORITY_KEY].values()), {st.PLAN_AHEAD_PRIO})
        self.assertEqual(planner.run_pass(self.read()), "waiting")   # chunk still open
        bq.prune_planned(set(), True)   # chunk built (its ghosts stand in for the pipes here)
        self.assertEqual(planner.run_pass(self.read()), "ahead")   # continues from the stub
        self.assertIn("plan-ahead chunk", self.debug_log())

    def test_plan_ahead_keeps_stock_reserve(self):
        self.world.inventory.items = {"liquid_pipe_segment": 30}
        planner = fp.FluidPlanner(self.log)
        self.assertEqual(planner.run_pass(self.read()), "queued")   # urgent: 14 pieces, no reserve
        calls = len(self.blueprints.calls)
        self.world.inventory.items = {"liquid_pipe_segment": st.PLAN_AHEAD_MAX_PIECES + st.PLAN_AHEAD_RESERVE - 1}
        self.assertEqual(planner.run_pass(self.read()), "done")
        self.assertEqual(len(self.blueprints.calls), calls)


class PowerAheadTests(PassCase):
    def setUp(self):
        super().setUp()
        self.world.services["journal"] = Journal([Site("water", 220, 20, "wp1"), Site("water", 1220, 20, "wp2")])
        self.world.inventory.add(pp.POWER_ITEM, 1000)

    def run_pass(self, planner):
        return planner.run_pass(self.read())

    def test_far_extractor_linked_in_chunks_without_blocking_urgent(self):
        self.world.services["power_control"] = Power([Grid("home", outposts=["home"], machines=["wp1"]), Grid("wp2", machines=["wp2"])])
        planner = pp.PowerPlanner(self.log)
        self.assertEqual(self.run_pass(planner), "ahead")
        ahead = [bid for bid, e in bq.planned().items() if e["p"] == st.PLAN_AHEAD_PRIO]
        self.assertEqual(len(ahead), st.PLAN_AHEAD_MAX_PIECES)
        self.blueprints.jobs = [Job(bid, "power_line", "power", 300, 15) for bid in ahead]
        self.assertEqual(self.run_pass(planner), "waiting")   # one chunk at a time
        # a new urgent grid appears near home: linked although the chunk is still open
        self.world.services["journal"] = Journal([Site("water", 220, 20, "wp1"), Site("water", 1220, 20, "wp2"),
                                                  Site("water", 20, 220, "wp3")])
        self.world.services["power_control"] = Power([Grid("home", outposts=["home"], machines=["wp1"]), Grid("wp2", machines=["wp2"]),
                                                     Grid("wp3", machines=["wp3"])])
        self.assertEqual(self.run_pass(planner), "queued")

    def test_short_stock_leaves_plan_ahead(self):
        self.world.services["power_control"] = Power([Grid("home", outposts=["home"], machines=["wp1"]), Grid("wp2", machines=["wp2"])])
        self.world.inventory.items = {pp.POWER_ITEM: st.PLAN_AHEAD_RESERVE}
        self.assertEqual(self.run_pass(pp.PowerPlanner(self.log)), "joined")
        self.assertEqual(self.blueprints.calls, [])


if __name__ == "__main__":
    unittest.main()
