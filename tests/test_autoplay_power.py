"""Tests for autoplay/lib/power_plan.py and blueprint_queue.py: footprint boxes, MST links, power pass against fakes."""
import builtins
import unittest
from typing import Any, cast

import harness
from game_stubs import Construction, ConstructionBlueprints, Journal, Position, PowerControl, PowerGrid, Result as BaseResult
import grid_geom as g
import infra_topology as topo
import power_plan as pp
import blueprint_queue as bq
from construction_plan import ATOMIC_STEP_BUDGET, PRIORITY_KEY
from test_autoplay_geom import ops


def k(tx, ty):
    return g.tile_key(tx, ty)


class Result(BaseResult):
    """BlueprintPlanResult: the created ids are the second positional argument."""

    def __init__(self, status, blueprint_ids=None, message=""):
        super().__init__(status, message=message, blueprint_ids=blueprint_ids or [])


class Power(PowerControl):
    """power_control over a fixed grid list; no world behind it."""

    def __init__(self, grids):
        super().__init__(cast(Any, None))
        self.grid_list = list(grids)


class Grid(PowerGrid):
    """Grid named by its outposts and machine ids; no world behind it."""

    def __init__(self, anchor, outposts=(), machines=()):
        super().__init__(cast(Any, None), anchor, machines)
        self._outpost_ids = list(outposts)

    @property
    def outpost_ids(self):
        return self._outpost_ids


class Site:
    """Surveyed site fake (WaterWell / OilWell / ThermalVent / ExoticDeposit / MiningSite surface)."""

    def __init__(self, kind, x, y, machine="", fluid=None, rate=None, site_id=None, item=None, hardness=1, purity="standard"):
        self._kind = kind
        self.id = site_id or f"{kind}_{x}_{y}"
        self.x = x
        self.y = y
        self._machine = machine
        self._fluid = fluid
        self._rate = rate
        self.item_id = item
        self.hardness = hardness
        self.purity = purity

    def kind(self):
        return self._kind

    def pump_id(self):
        return self._machine

    def cap_id(self):
        return self._machine

    def fluid(self):
        return self._fluid

    def medium(self):
        return None if self._fluid is None else topo.fluid_medium(self._fluid)

    def flow_rate(self):
        return self._rate

    def yield_tier(self):
        return None

    def base_steam_rate(self):
        return self._rate

    def base_rate(self):
        return self._rate


class Blueprints(ConstructionBlueprints):
    """construction_blueprint fake: plan_power_line answers from `answers` in order (default ok), counts pieces."""

    def __init__(self, answers=(), jobs=()):
        super().__init__()
        self.answers = list(answers)
        self.calls = []
        self.cancelled = []
        self.pending = list(jobs)
        self.next_id = 0

    @property
    def jobs(self):
        return self.pending

    @jobs.setter
    def jobs(self, value):
        self.pending = value

    def plan_power_line(self, x1, y1, x2, y2):
        self.calls.append((x1, y1, x2, y2))
        status = self.answers.pop(0) if self.answers else "ok"
        if status != "ok":
            return Result(status, message="nope")
        pieces = int(abs(x1 - x2) + abs(y1 - y2)) // g.TILE_M
        ids = []
        for _ in range(pieces):
            self.next_id += 1
            ids.append(f"bp{self.next_id}")
        return Result("ok", ids)

    def cancel(self, blueprint_id):
        self.cancelled.append(blueprint_id)
        return Result("ok")



class Job(Construction):
    def __init__(self, jid, kind, medium, x, y):
        super().__init__(jid, "", 0)
        self.kind = kind
        self.medium = medium
        self.position = Position(x, y)


class GeometryTests(unittest.TestCase):
    def test_boxes_match_footprint_tiles(self):
        box = g.outpost_box(0, 0)
        self.assertEqual(box, (0, 0, 3, 3))
        tiles = {k(x, y) for x in range(box[0], box[2] + 1) for y in range(box[1], box[3] + 1)}
        self.assertEqual(tiles, set(g.outpost_tiles(0, 0)))
        box = g.extractor_box(50, 50)
        self.assertEqual(box, (3, 3, 6, 6))
        tiles = {k(x, y) for x in range(box[0], box[2] + 1) for y in range(box[1], box[3] + 1)}
        self.assertEqual(tiles, set(g.extractor_tiles(50, 50)))

    def test_box_closest(self):
        self.assertEqual(g.box_closest((0, 0, 3, 3), (10, 0, 13, 3)), (7, k(3, 0), k(10, 0)))
        self.assertEqual(g.box_closest((10, 10, 13, 13), (0, 0, 3, 3)), (14, k(10, 10), k(3, 3)))
        dist, a, b = g.box_closest((0, 0, 3, 3), (2, 8, 5, 11))
        self.assertEqual((dist, a, b), (5, k(2, 3), k(2, 8)))


class SpanningTests(unittest.TestCase):
    def comps(self, *origins):
        return [{"anchor": f"g{i}", "boxes": [(g.outpost_box(x, y), False, f"o{i}")]} for i, (x, y) in enumerate(origins)]

    def test_n_components_get_n_minus_1_links(self):
        comps = self.comps((0, 0), (100, 0), (0, 100), (500, 500), (100, 100))
        links = pp.spanning_links(len(comps), pp.component_edges(pp.flat_boxes(comps)))
        self.assertEqual(len(links), 4)
        parent = list(range(5))

        def root(n):
            while parent[n] != n:
                n = parent[n]
            return n
        for _d, a, b, _i, _j in links:
            parent[root(a)] = root(b)
        self.assertEqual(len({root(n) for n in range(5)}), 1)

    def test_link_uses_nearest_footprints_of_multi_box_component(self):
        comps = [{"anchor": "home", "boxes": [(g.outpost_box(0, 0), False, "home"), (g.outpost_box(300, 0), False, "o1")]},
                 {"anchor": "pump", "boxes": [(g.extractor_box(400, 15), False, "pump")]}]
        flat = pp.flat_boxes(comps)
        links = pp.spanning_links(2, pp.component_edges(flat))
        self.assertEqual(len(links), 1)
        cost, ci, cj, i, j = links[0]
        self.assertEqual((ci, cj, i, j), (0, 1, 1, 2))
        self.assertEqual(g.box_closest(flat[i][1], flat[j][1]), (5, k(33, 0), k(38, 0)))
        self.assertEqual(cost, 5)

    def test_ring_cost_prefers_outpost_over_shared_field_structure(self):
        # grid "main" = outpost far away + cap close by; the lone pump links to the outpost
        # unless the cap is more than RING_PIECES tiles nearer.
        rows = pp.grid_rows([Grid("main", outposts=["o1"], machines=["cap"]), Grid("pump", machines=["pump"])])
        far = {"o1": (0, 0)}
        comps, _ = pp.components(rows, far, {"cap": (220, 20), "pump": (300, 20)})
        self.assertEqual([r for _b, r, _n in comps[0]["boxes"]], [False, True])
        self.assertEqual([r for _b, r, _n in comps[1]["boxes"]], [False])  # lone structure: leaf, no ring
        flat = pp.flat_boxes(comps)
        cost, _ci, _cj, i, j = pp.spanning_links(2, pp.component_edges(flat))[0]
        # cap: 5 tiles apart + 12 ring = 17 < outpost 25 tiles apart -> cap, ringed
        self.assertEqual((comps[0]["boxes"][i][2], cost), ("cap", 5 + pp.RING_PIECES))
        comps, _ = pp.components(rows, far, {"cap": (220, 20), "pump": (150, 20)})
        flat = pp.flat_boxes(comps)
        cost, _ci, _cj, i, j = pp.spanning_links(2, pp.component_edges(flat))[0]
        # cap: 4 + 12 = 16 > outpost 10 tiles apart -> outpost
        self.assertEqual((comps[0]["boxes"][i][2], cost), ("o1", 10))

    def test_ring_legs_cover_perimeter(self):
        legs = pp.ring_legs(g.extractor_box(50, 50))
        self.assertEqual(legs[0], [35.0, 35.0, 65.0, 35.0])
        self.assertEqual(sum(int(abs(a - c) + abs(b - d)) // g.TILE_M for a, b, c, d in legs), pp.RING_PIECES)

    def test_components_skip_unplaced(self):
        rows = pp.grid_rows([Grid("a", outposts=["o1"]), Grid("b", machines=["pump1"]), Grid("c", machines=["solar"])])
        placed, unplaced = pp.components(rows, {"o1": (0, 0)}, {"pump1": (100, 100)})
        self.assertEqual([c["anchor"] for c in placed], ["a", "b"])
        self.assertEqual(unplaced, ["c"])

    def test_site_machines(self):
        sites = [Site("water", 10, 20, "wp1"), Site("water", 30, 40, ""), Site("thermal", 50, 60, "cap1"),
                 Site("mineral", 70, 80)]
        out = pp.site_machines(sites, {"drill1": {"pos": [5, 6]}, "bad": {"pos": None}})
        self.assertEqual(out, {"wp1": (10.0, 20.0), "cap1": (50.0, 60.0), "drill1": (5.0, 6.0)})

    def test_link_routes(self):
        routes = pp.link_routes(k(0, 0), k(3, 2))
        self.assertEqual(routes[0], [[5.0, 5.0, 35.0, 25.0]])
        self.assertEqual(routes[1], [[5.0, 5.0, 35.0, 5.0], [35.0, 5.0, 35.0, 25.0]])
        self.assertEqual(routes[2], [[5.0, 5.0, 5.0, 25.0], [5.0, 25.0, 35.0, 25.0]])
        self.assertEqual(len(pp.link_routes(k(0, 0), k(3, 0))), 1)

    def test_pair_segments_cover_every_pair_once(self):
        for count in (0, 1, 2, 7, 30):
            batches = pp.pair_segments(list(range(count)), size=5)
            pairs = [(i, j) for batch in batches for i, j0, j1 in batch for j in range(j0, j1)]
            self.assertEqual(sorted(pairs), [(i, j) for i in range(count) for j in range(i + 1, count)])
            self.assertTrue(all(sum(j1 - j0 for _i, j0, j1 in batch) <= 5 for batch in batches))

    def test_pair_segments_skip_same_component(self):
        comp_of = [0, 0, 0, 1, 1, 2]
        batches = pp.pair_segments(comp_of, size=4)
        pairs = sorted((i, j) for batch in batches for i, j0, j1 in batch for j in range(j0, j1))
        expected = sorted((i, j) for i in range(6) for j in range(i + 1, 6) if comp_of[i] != comp_of[j])
        self.assertEqual(pairs, expected)

    def test_flood_assigns_lines_and_drops_contested(self):
        comps = [{"anchor": "a", "boxes": [(g.outpost_box(0, 0), False, "o_a")]},
                 {"anchor": "b", "boxes": [(g.outpost_box(200, 0), False, "o_b")]}]
        # a's line runs east from its footprint edge (3,1) to (8,1); b's line west from (20,1) to (12,1); (10,1) touches neither
        power = {k(x, 1) for x in range(3, 9)} | {k(x, 1) for x in range(12, 21)} | {k(10, 5)}
        runs, contested = pp.attach_lines(comps, power)
        self.assertEqual(contested, 0)
        self.assertIn(((3, 1, 8, 1), False, pp.LINE_NAME), comps[0]["boxes"])
        self.assertIn(((12, 1, 20, 1), False, pp.LINE_NAME), comps[1]["boxes"])
        self.assertEqual(runs, 2)  # the orphan tile (10,5) is reached by no footprint

    def test_flood_contested_tile_dropped(self):
        comps = [{"anchor": "a", "boxes": [(g.outpost_box(0, 0), False, "o_a")]},
                 {"anchor": "b", "boxes": [(g.outpost_box(60, 0), False, "o_b")]}]
        power = {k(x, 1) for x in range(3, 7)}  # (3,1) in a, (6,1) in b: both floods meet
        _runs, contested = pp.attach_lines(comps, power)
        self.assertGreater(contested, 0)

    def test_line_end_beats_footprint_and_ring(self):
        # main = outpost far west + shared cap; its line runs east to x tile 27; lone pump at tiles 30..33
        comps = [{"anchor": "main", "boxes": [(g.outpost_box(0, 0), False, "o1"), (g.extractor_box(220, 20), True, "cap")]},
                 {"anchor": "pump", "boxes": [(g.extractor_box(320, 20), False, "pump")]}]
        pp.attach_lines(comps, {k(x, 1) for x in range(23, 28)})
        flat = pp.flat_boxes(comps)
        cost, _ci, _cj, i, j = pp.spanning_links(2, pp.component_edges(flat))[0]
        self.assertEqual(cost, 3)  # line end (27,1) to pump edge (30,1), no ring
        self.assertEqual(flat[i][2], 0)

    def test_flood_step_budget(self):
        comps = [{"anchor": "a", "boxes": [(g.outpost_box(0, 0), False, "o_a")]}]
        power = {k(x, y) for x in range(0, 40) for y in range(0, 40)}
        state = pp.flood_init(comps, power)
        worst = 0
        while True:
            done = [False]
            worst = max(worst, ops(lambda: done.__setitem__(0, pp.flood_step(state))))
            if done[0]:
                break
        self.assertLess(worst, ATOMIC_STEP_BUDGET)

    def test_edge_slice_budget(self):
        comps = [{"anchor": f"g{i}", "boxes": [(g.outpost_box(i * 100, 0), True, f"m{i}")]} for i in range(3 * pp.PAIR_CHUNK)]
        boxes = pp.flat_boxes(comps)
        batches = pp.pair_segments([box[0] for box in boxes])
        self.assertLess(max(ops(pp.edge_slice, batch, boxes) for batch in batches), ATOMIC_STEP_BUDGET)


class PowerPassTests(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        self.log = harness.TreeConsole(module="infra_planner")
        self.blueprints = Blueprints()
        self.world.services["construction_blueprint"] = self.blueprints
        self.world.services["journal"] = Journal([Site("water", 220, 20, "wp1"), Site("water", 900, 900, "wp2")])
        self.world.services["power_control"] = Power([Grid("home", outposts=["home"]), Grid("wp1", machines=["wp1"]),
                                                     Grid("wp2", machines=["wp2"])])
        self.world.inventory.add(pp.POWER_ITEM, 1000)
        self.world.home.x = 0.0
        self.world.home.y = 0.0
        builtins.list_pipes = lambda: []

    def tearDown(self):
        del builtins.list_pipes
        super().tearDown()

    def run_pass(self, planner=None):
        import infra_topology
        planner = planner or pp.PowerPlanner(self.log)
        return planner.run_pass(infra_topology.Topology().read())

    def test_queues_shortest_link_first(self):
        self.assertEqual(self.run_pass(), "queued")
        self.assertEqual(len(self.blueprints.calls), 1)
        # home outpost 0..40 (tiles 0..3), wp1 footprint 200..240 (tiles 20..23): nearest tiles (3,0)-(20,0)
        self.assertEqual(self.blueprints.calls[0], (35.0, 5.0, 205.0, 5.0))
        planned = bq.planned()
        self.assertEqual(len(planned), 17)
        self.assertTrue(all(e["f"] == "power" and e["p"] == 0 for e in planned.values()))
        self.assertEqual(self.world.notebook.data.get(PRIORITY_KEY, {}), {})

    def test_link_to_shared_field_structure_rings_it(self):
        self.world.services["journal"] = Journal([Site("water", 220, 20, "wp1"), Site("water", 290, 20, "wp2")])
        self.world.services["power_control"] = Power([Grid("main", outposts=["home"], machines=["wp1"]),
                                                     Grid("wp2", machines=["wp2"])])
        self.assertEqual(self.run_pass(), "queued")
        # wp1 box tiles 20..23, wp2 box 27..30: link (23,0)->(27,0), then the four sides of wp1's footprint
        self.assertEqual(self.blueprints.calls, [(235.0, 5.0, 275.0, 5.0), (205.0, 5.0, 235.0, 5.0),
                                                 (235.0, 5.0, 235.0, 35.0), (235.0, 35.0, 205.0, 35.0),
                                                 (205.0, 35.0, 205.0, 5.0)])
        self.assertEqual(len(bq.planned()), 4 + pp.RING_PIECES)
        self.assertIn("ring around wp1", self.debug_log())

    def test_waits_while_power_job_open(self):
        self.blueprints.pending = [Job("j1", "power_line", "power", 10, 5)]
        self.assertEqual(self.run_pass(), "waiting")
        self.assertEqual(self.blueprints.calls, [])

    def test_stock_short_waits(self):
        self.world.inventory.items = {}
        self.assertEqual(self.run_pass(), "waiting")
        self.assertEqual(self.blueprints.calls, [])

    def test_one_grid_is_joined(self):
        self.world.services["power_control"] = Power([Grid("home", outposts=["home"], machines=["wp1"])])
        self.assertEqual(self.run_pass(), "joined")

    def test_blocked_retries_elbow_and_cancels_partial(self):
        self.world.services["journal"] = Journal([Site("water", 220, 120, "wp1")])
        self.world.services["power_control"] = Power([Grid("home", outposts=["home"]), Grid("wp1", machines=["wp1"])])
        # direct blocked, first elbow: leg 1 ok, leg 2 blocked -> cancelled; second elbow ok
        self.blueprints.answers = ["blocked", "ok", "blocked", "ok", "ok"]
        self.assertEqual(self.run_pass(), "queued")
        self.assertEqual(len(self.blueprints.calls), 5)
        self.assertTrue(self.blueprints.cancelled)
        self.assertFalse(set(self.blueprints.cancelled) & set(bq.planned()))

    def test_rejected_link_not_retried(self):
        self.blueprints.answers = ["locked"]
        planner = pp.PowerPlanner(self.log)
        self.assertEqual(self.run_pass(planner), "waiting")  # the only urgent link (home -> wp1) was rejected
        calls = len(self.blueprints.calls)
        self.assertEqual(self.run_pass(planner), "ahead")    # far wp2 is plan-ahead: next pass links it in a chunk
        self.assertNotIn(self.blueprints.calls[0], self.blueprints.calls[calls:])

    def test_prune_planned(self):
        self.run_pass()
        live = set(list(bq.planned())[:3])
        self.assertEqual(bq.prune_planned(live, True), 14)
        self.assertEqual(set(bq.planned()), live)
        self.assertEqual(bq.prune_planned(set(), False), 0)


if __name__ == "__main__":
    unittest.main()
