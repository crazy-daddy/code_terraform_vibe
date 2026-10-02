"""Tests for autoplay/lib/power_plan.py and blueprint_queue.py: footprint boxes, MST links, power pass against fakes."""
import builtins
import unittest

import harness
import grid_geom as g
import power_plan as pp
import blueprint_queue as bq
from construction_plan import ATOMIC_STEP_BUDGET, PRIORITY_KEY
from test_autoplay_geom import ops


def k(tx, ty):
    return g.tile_key(tx, ty)


class Result:
    def __init__(self, status, blueprint_ids=None, message=""):
        self.status = status
        self.blueprint_ids = blueprint_ids or []
        self.message = message


class Grid:
    def __init__(self, anchor, outposts=(), machines=()):
        self.anchor_id = anchor
        self.outpost_ids = list(outposts)
        self.machine_ids = list(machines)


class Power:
    def __init__(self, grids):
        self._grids = grids

    def grids(self):
        return self._grids


class Site:
    def __init__(self, kind, x, y, machine=""):
        self._kind = kind
        self.x = x
        self.y = y
        self._machine = machine

    def kind(self):
        return self._kind

    def pump_id(self):
        return self._machine

    def cap_id(self):
        return self._machine


class Journal:
    def __init__(self, sites):
        self._sites = sites

    def surveyed_sites(self, planet):
        return self._sites


class Blueprints:
    """construction_blueprint fake: plan_power_line answers from `answers` in order (default ok), counts pieces."""

    def __init__(self, answers=(), jobs=()):
        self.answers = list(answers)
        self.calls = []
        self.cancelled = []
        self.jobs = list(jobs)
        self.next_id = 0

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

    def pending_constructions(self):
        return self.jobs

    def active_constructions(self):
        return []

    def paused_constructions(self):
        return []


class Pos:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class Job:
    def __init__(self, jid, kind, medium, x, y):
        self.id = jid
        self.kind = kind
        self.medium = medium
        self.position = Pos(x, y)


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
        return [{"anchor": f"g{i}", "boxes": [g.outpost_box(x, y)]} for i, (x, y) in enumerate(origins)]

    def test_n_components_get_n_minus_1_links(self):
        comps = self.comps((0, 0), (100, 0), (0, 100), (500, 500), (100, 100))
        links = pp.spanning_links(len(comps), pp.component_edges(pp.flat_boxes(comps)))
        self.assertEqual(len(links), 4)
        parent = list(range(5))

        def root(n):
            while parent[n] != n:
                n = parent[n]
            return n
        for _d, a, b, _ta, _tb in links:
            parent[root(a)] = root(b)
        self.assertEqual(len({root(n) for n in range(5)}), 1)

    def test_link_uses_nearest_footprints_of_multi_box_component(self):
        comps = [{"anchor": "home", "boxes": [g.outpost_box(0, 0), g.outpost_box(300, 0)]},
                 {"anchor": "pump", "boxes": [g.extractor_box(400, 15)]}]
        links = pp.spanning_links(2, pp.component_edges(pp.flat_boxes(comps)))
        self.assertEqual(len(links), 1)
        dist, ci, cj, ta, tb = links[0]
        self.assertEqual((ci, cj), (0, 1))
        self.assertEqual(ta, k(33, 0))
        self.assertEqual(tb, k(38, 0))
        self.assertEqual(dist, 5)

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
            batches = pp.pair_segments(count, size=5)
            pairs = [(i, j) for batch in batches for i, j0, j1 in batch for j in range(j0, j1)]
            self.assertEqual(sorted(pairs), [(i, j) for i in range(count) for j in range(i + 1, count)])
            self.assertTrue(all(sum(j1 - j0 for _i, j0, j1 in batch) <= 5 for batch in batches))

    def test_edge_slice_budget(self):
        comps = [{"anchor": f"g{i}", "boxes": [g.outpost_box(i * 100, 0)]} for i in range(3 * pp.PAIR_CHUNK)]
        boxes = pp.flat_boxes(comps)
        batches = pp.pair_segments(len(boxes))
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

    def test_waits_while_power_job_open(self):
        self.blueprints.jobs = [Job("j1", "power_line", "power", 10, 5)]
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
        self.assertEqual(self.run_pass(planner), "queued")  # next link (wp1 -> wp2) still queued
        calls = len(self.blueprints.calls)
        self.run_pass(planner)
        self.assertNotIn(self.blueprints.calls[0], self.blueprints.calls[calls:])

    def test_prune_planned(self):
        self.run_pass()
        live = set(list(bq.planned())[:3])
        self.assertEqual(bq.prune_planned(live, True), 14)
        self.assertEqual(set(bq.planned()), live)
        self.assertEqual(bq.prune_planned(set(), False), 0)


if __name__ == "__main__":
    unittest.main()
