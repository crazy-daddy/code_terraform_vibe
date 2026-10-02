"""Tests for autoplay/lib/infra_topology.py: rows from game objects, occupancy labels, footprint ports."""
import unittest

import harness  # noqa: F401  (puts the lib/ folders on sys.path)
import grid_geom as g
import infra_topology as topo


def k(tx, ty):
    return g.tile_key(tx, ty)


class Pos:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class FakePipe:
    def __init__(self, pid, medium, x1, y1, x2, y2, contents=None, complete=True, conflicts=()):
        self.id = pid
        self._medium = medium
        self._start = Pos(x1, y1)
        self._end = Pos(x2, y2)
        self._contents = contents
        self._complete = complete
        self._conflicts = list(conflicts)

    def start(self):
        return self._start

    def end(self):
        return self._end

    def type(self):
        return self._medium

    def contents(self):
        return self._contents

    def is_complete(self):
        return self._complete

    def conflicting_contents(self):
        return self._conflicts


class FakeJob:
    def __init__(self, jid, kind, medium, x, y):
        self.id = jid
        self.kind = kind
        self.medium = medium
        self.position = Pos(x, y)


class OccupancyTests(unittest.TestCase):
    def occ(self, pipes=(), jobs=(), networks=None):
        return topo.build_occupancy(topo.read_pipe_slice(list(pipes)), topo.read_job_slice(list(jobs)),
                                    topo.planned_labels(networks or {}))

    def test_contents_label_tiles(self):
        occ = self.occ([FakePipe("p1", "liquid", 5, 5, 15, 5, contents="water")])
        self.assertEqual(occ["liquid"], {k(0, 0): "water", k(1, 0): "water"})
        self.assertEqual(occ["gas"], {})

    def test_relic_and_conflict_are_foreign(self):
        occ = self.occ([
            FakePipe("relic", "liquid", 5, 5, 15, 5),
            FakePipe("bad", "gas", 5, 5, 15, 5, contents=None, conflicts=["ammonia", "steam"]),
        ])
        self.assertEqual(set(occ["liquid"].values()), {topo.FOREIGN})
        self.assertEqual(set(occ["gas"].values()), {topo.FOREIGN})

    def test_planned_network_labels_ghost_and_empty_piece(self):
        networks = {"water": [[5, 5, 35, 5]]}
        occ = self.occ([FakePipe("p1", "liquid", 5, 5, 15, 5, contents=None, complete=False)],
                       [FakeJob("j1", "pipe", "liquid", 30, 5)], networks)
        self.assertEqual(occ["liquid"][k(0, 0)], "water")
        self.assertEqual(occ["liquid"][k(2, 0)], "water")
        self.assertEqual(occ["liquid"][k(3, 0)], "water")

    def test_unknown_ghost_is_foreign_and_power_is_own_layer(self):
        occ = self.occ(jobs=[FakeJob("j1", "pipe", "liquid", 10, 5), FakeJob("w1", "power_line", "power", 10, 5)])
        self.assertEqual(occ["liquid"][k(0, 0)], topo.FOREIGN)
        self.assertEqual(occ["power"][k(0, 0)], topo.POWER)

    def test_two_fluids_on_one_tile_become_foreign(self):
        occ = self.occ([FakePipe("a", "liquid", 5, 5, 15, 5, contents="water"),
                        FakePipe("b", "liquid", 15, 5, 25, 5, contents="oil")])
        self.assertEqual(occ["liquid"][k(1, 0)], topo.FOREIGN)
        self.assertEqual(occ["liquid"][k(0, 0)], "water")

    def test_walls_and_held(self):
        occ = self.occ([FakePipe("a", "liquid", 5, 5, 15, 5, contents="water"),
                        FakePipe("b", "liquid", 5, 25, 15, 25, contents="oil")])
        self.assertEqual(topo.held(occ["liquid"], "water"), {k(0, 0), k(1, 0)})
        self.assertEqual(topo.walls(occ["liquid"], "water"), {k(0, 2), k(1, 2)})

    def test_gas_fluid_medium(self):
        self.assertEqual(topo.fluid_medium("steam"), "gas")
        self.assertEqual(topo.fluid_medium("water"), "liquid")
        self.assertEqual(topo.fluid_medium("coastal_essence"), "liquid")


class PortTests(unittest.TestCase):
    def test_second_network_gets_a_free_port(self):
        footprint = g.outpost_tiles(0, 0)
        layer = {k(0, 0): "water", k(1, 0): "water"}
        ports = topo.footprint_ports(footprint, layer, "oil")
        self.assertEqual(ports["held"], [])
        self.assertEqual(len(ports["free"]), 14)
        self.assertEqual(ports["others"], {"water": [k(0, 0), k(1, 0)]})

    def test_full_footprint(self):
        footprint = g.outpost_tiles(0, 0)
        layer = {tile: "water" for tile in footprint}
        ports = topo.footprint_ports(footprint, layer, "oil")
        self.assertEqual(ports["held"] + ports["free"], [])

    def test_route_into_outpost_beside_another_network(self):
        footprint = g.outpost_tiles(0, 0)
        water = {k(x, 0) for x in range(-5, 4)}  # water runs in along the top row
        layer = {tile: "water" for tile in water}
        ports = topo.footprint_ports(footprint, layer, "oil")
        path = g.route([k(-5, 2)], ports["free"], topo.walls(layer, "oil"))
        self.assertTrue(path)
        self.assertFalse({t for t, _ in path} & water)
        self.assertIn(path[-1][0], ports["free"])


if __name__ == "__main__":
    unittest.main()


class CountingPipe(FakePipe):
    """FakePipe counting contents() reads (one per full row read)."""
    reads = 0

    def contents(self):
        CountingPipe.reads += 1
        return self._contents


class IncrementalReadTests(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        import builtins
        self.pipes = [CountingPipe(f"p{i}", "liquid", 5, 5 + 10 * i, 5, 15 + 10 * i, contents="water") for i in range(5)]
        builtins.list_pipes = lambda: list(self.pipes)
        self.world.services["construction_blueprint"] = None
        CountingPipe.reads = 0

    def tearDown(self):
        import builtins
        del builtins.list_pipes
        super().tearDown()

    def test_only_new_pipes_read_and_removed_dropped(self):
        t = topo.Topology()
        t.read()
        self.assertEqual(CountingPipe.reads, 5)
        self.assertIn("full read", t.last)
        t.read()
        self.assertEqual(CountingPipe.reads, 5)  # nothing new: no pipe read again
        self.pipes.append(CountingPipe("p9", "gas", 105, 5, 115, 5, contents="steam"))
        t.read()
        self.assertEqual(CountingPipe.reads, 6)
        self.assertEqual(t.occ["gas"][k(10, 0)], "steam")
        self.pipes = [p for p in self.pipes if p.id != "p0"]
        t.read()
        self.assertNotIn("p0", t.cache)
        self.assertNotIn(k(0, 0), t.occ["liquid"])
        self.assertIn("1 removed", t.last)

    def test_full_refresh_catches_contents_change(self):
        t = topo.Topology()
        t.read()
        self.pipes[0]._contents = "oil"
        for _ in range(topo.FULL_REFRESH_PASSES):
            t.read()
        self.assertEqual(t.occ["liquid"][k(0, 0)], "water")  # not seen yet by the incremental reads
        t.read()
        self.assertEqual(t.occ["liquid"][k(0, 0)], "oil")


class AtomicBudgetTests(unittest.TestCase):
    """Worst slice of every atomically run function stays under construction_plan.ATOMIC_STEP_BUDGET."""

    def test_pipe_and_job_slices(self):
        from construction_plan import ATOMIC_STEP_BUDGET
        from test_autoplay_geom import ops
        pipes = [FakePipe(f"p{i}", "liquid", 5, 5 + 10 * i, 5, 15 + 10 * i, contents="water", conflicts=["a"])
                 for i in range(topo.PIPE_CHUNK)]
        jobs = [FakeJob(f"j{i}", "pipe", "liquid", 10, 5 + 10 * i) for i in range(topo.JOB_CHUNK)]
        self.assertLess(ops(topo.read_pipe_slice, pipes), ATOMIC_STEP_BUDGET)
        self.assertLess(ops(topo.read_job_slice, jobs), ATOMIC_STEP_BUDGET)
        known = {f"p{i}": None for i in range(5000)}
        fresh = [FakePipe(f"n{i}", "liquid", 5, 5, 5, 15) for i in range(topo.ID_CHUNK)]
        self.assertLess(ops(topo.new_pipe_slice, fresh, known), ATOMIC_STEP_BUDGET)
