"""Tests for autoplay/lib/grid_geom.py: tile mapping, footprints, router, build steps."""
import os
import sys
import unittest

import harness  # noqa: F401  (puts the lib/ folders on sys.path)
import grid_geom as g
from construction_plan import ATOMIC_STEP_BUDGET

_AUTOPLAY_LIB = os.path.dirname(os.path.abspath(g.__file__))


def ops(fn, *args):
    """CPython opcodes executed inside autoplay/lib while fn(*args) runs (pessimistic stand-in for game steps)."""
    total = [0]

    def tracer(frame, event, arg):
        frame.f_trace_opcodes = True
        if event == "opcode" and os.path.dirname(os.path.abspath(frame.f_code.co_filename)) == _AUTOPLAY_LIB:
            total[0] += 1
        return tracer

    previous = sys.gettrace()
    sys.settrace(tracer)
    try:
        fn(*args)
    finally:
        sys.settrace(previous)
    return total[0]


def k(tx, ty):
    return g.tile_key(tx, ty)


class TileTests(unittest.TestCase):
    def test_key_round_trip_negative(self):
        for tx, ty in ((0, 0), (-1, -1), (-300, 42), (999, -999)):
            self.assertEqual(g.tile_xy(k(tx, ty)), (tx, ty))

    def test_tile_at_and_centre(self):
        self.assertEqual(g.tile_at(5, -5), k(0, -1))
        self.assertEqual(g.tile_centre(k(0, -1)), (5.0, -5.0))
        self.assertEqual(g.tile_at(-465, 275), k(-47, 27))

    def test_piece_tiles_from_completed_pipe(self):
        # pipe_32 in the probe log: gas -465,275 -> -465,265
        self.assertEqual(sorted(g.piece_tiles(-465, 275, -465, 265)), sorted([k(-47, 27), k(-47, 26)]))

    def test_job_tiles_from_midpoint(self):
        # probe: horizontal piece at (10,-5) joins centres (5,-5) and (15,-5)
        self.assertEqual(g.job_tiles(10, -5), [k(0, -1), k(1, -1)])
        # probe: vertical piece at (5,10) joins centres (5,5) and (5,15)
        self.assertEqual(g.job_tiles(5, 10), [k(0, 0), k(0, 1)])
        # bridge centre (35,-5): one tile
        self.assertEqual(g.job_tiles(35, -5), [k(3, -1)])


class FootprintTests(unittest.TestCase):
    def test_outpost_top_left_anchor(self):
        tiles = g.outpost_tiles(0, 0)
        self.assertEqual(len(tiles), 16)
        xs = sorted({g.tile_xy(t)[0] for t in tiles})
        self.assertEqual(xs, [0, 1, 2, 3])

    def test_extractor_centre_anchor(self):
        tiles = g.extractor_tiles(50, 50)  # spans 30..70
        xs = sorted({g.tile_xy(t)[0] for t in tiles})
        ys = sorted({g.tile_xy(t)[1] for t in tiles})
        self.assertEqual(xs, [3, 4, 5, 6])
        self.assertEqual(ys, [3, 4, 5, 6])


class RouterTests(unittest.TestCase):
    def test_straight_route_and_one_run(self):
        path = g.route([k(0, 0)], [k(5, 0)], set())
        self.assertEqual([t for t, _ in path], [k(x, 0) for x in range(6)])
        self.assertEqual(g.path_plan(path), [("run", k(0, 0), k(5, 0))])

    def test_route_avoids_walls(self):
        wall = {k(2, y) for y in range(-3, 4)}
        path = g.route([k(0, 0)], [k(4, 0)], wall)
        tiles = [t for t, _ in path]
        self.assertTrue(tiles)
        self.assertFalse(set(tiles) & wall)

    def test_bridge_over_a_crossing_line(self):
        # A long perpendicular line at x=2: no way around within the node limit, so bridge it.
        wall = {k(2, y) for y in range(-200, 201)}
        path = g.route([k(0, 0)], [k(4, 0)], wall, bridgeable=wall, max_nodes=2000)
        steps = g.path_plan(path)
        self.assertIn(("bridge", k(2, 0), "horizontal"), steps)
        self.assertEqual(steps[0], ("run", k(0, 0), k(1, 0)))
        self.assertEqual(steps[-1], ("run", k(3, 0), k(4, 0)))

    def test_bridge_needs_free_landing(self):
        wall = {k(2, y) for y in range(-200, 201)} | {k(3, y) for y in range(-200, 201)}
        path = g.route([k(0, 0)], [k(5, 0)], wall, bridgeable=wall, max_nodes=2000)
        self.assertEqual(path, [])  # two adjacent lines cannot be crossed by one 3-tile bridge

    def test_reuses_source_network_for_free(self):
        network = [k(x, 0) for x in range(10)]
        path = g.route(network, [k(9, 3)], set())
        self.assertEqual(path[0][0], k(9, 0))
        self.assertEqual(g.path_plan(path), [("run", k(9, 0), k(9, 3))])

    def test_soft_tiles_are_avoided_when_cheap(self):
        soft = {k(x, 0) for x in range(1, 5)}
        path = g.route([k(0, 0)], [k(5, 0)], set(), soft=soft)
        self.assertFalse({t for t, _ in path} & soft)

    def test_l_route_splits_into_two_runs(self):
        wall = {k(x, y) for x in range(1, 6) for y in range(0, 5)}
        path = g.route([k(0, 0)], [k(6, 5)], wall)
        for kind, *_ in g.path_plan(path):
            self.assertEqual(kind, "run")
        self.assertTrue(len(g.path_plan(path)) >= 2)

    def test_stepper_matches_one_shot(self):
        state = g.route_init([k(0, 0)], [k(30, 30)], set())
        calls = 0
        while not g.route_step(state, nodes=10):
            calls += 1
        self.assertGreater(calls, 1)
        self.assertEqual(len(g.route_path(state)), 61)


class AtomicBudgetTests(unittest.TestCase):
    def test_route_step_worst_case(self):
        # Every expanded tile has a bridgeable wall on one side and soft tiles around it.
        wall = {k(5, y) for y in range(-100, 100)}
        soft = {k(x, y) for x in range(-50, 50) for y in range(-50, 50)}
        state = g.route_init([k(0, 0)], [k(300, 300)], wall, bridgeable=wall, soft=soft)
        for _ in range(5):
            self.assertLess(ops(g.route_step, state, g.ROUTE_STEP_NODES), ATOMIC_STEP_BUDGET)

    def test_route_seed_slice(self):
        state = g.route_init([], [k(300, 300)], set())
        tiles = [k(x, 0) for x in range(g.SEED_CHUNK)]
        self.assertLess(ops(g.route_seed, tiles, state), ATOMIC_STEP_BUDGET)


class RunTests(unittest.TestCase):
    def test_run_tiles_and_pieces(self):
        self.assertEqual(g.run_tiles(k(3, 1), k(0, 1)), [k(3, 1), k(2, 1), k(1, 1), k(0, 1)])
        self.assertEqual(g.run_pieces(k(3, 1), k(0, 1)), 3)

    def test_bridge_tiles(self):
        self.assertEqual(g.bridge_tiles(k(2, 0), "horizontal"), [k(1, 0), k(2, 0), k(3, 0)])
        self.assertEqual(g.bridge_tiles(k(2, 0), "vertical"), [k(2, -1), k(2, 0), k(2, 1)])


if __name__ == "__main__":
    unittest.main()
