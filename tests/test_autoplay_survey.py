"""Tests for the power-line ledger: construction_plan helpers, autoplay/lib/power_survey.py, Pioneer hold."""
import unittest

import harness
import construction_plan as cp
import power_survey as ps
import grid_geom as g


class Result:
    def __init__(self, status, blueprint_ids=None):
        self.status = status
        self.blueprint_ids = blueprint_ids or []
        self.message = ""


class ProbeBlueprints:
    """construction_blueprint fake: mark_deconstruct answers from a {(tx, ty): pieces} map like the game."""

    def __init__(self, pieces, locked=False, fail_cancel=()):
        self.pieces = pieces
        self.locked = locked
        self.fail_cancel = set(fail_cancel)
        self.jobs = []
        self.cancelled = []
        self.calls = 0
        self.next_id = 0
        self.hold_seen = []
        self.notebook = None

    def mark_deconstruct(self, x, y, layer="auto", target_id=""):
        self.calls += 1
        if self.notebook is not None:
            self.hold_seen.append(self.notebook.data.get(cp.HOLD_KEY))
        if self.locked:
            return Result("locked")
        count = self.pieces.get((int(x // 10), int(y // 10)), 0)
        if count == 0:
            return Result("nothing_here")
        if count > 1:
            return Result("ambiguous_target")
        self.next_id += 1
        job_id = f"dc{self.next_id}"
        self.jobs.append(job_id)
        return Result("ok", [job_id])

    def cancel(self, blueprint_id):
        if blueprint_id in self.fail_cancel:
            self.fail_cancel.discard(blueprint_id)
            return Result("busy")
        self.cancelled.append(blueprint_id)
        self.jobs.remove(blueprint_id)
        return Result("ok")


class LedgerHelperTests(unittest.TestCase):
    def test_rows_round_trip(self):
        tiles = {(1, 0), (2, 0), (3, 0), (7, 0), (-5, -2), (-4, -2), (0, 9)}
        rows = cp.power_rows_encode(tiles)
        self.assertEqual(rows["0"], [[1, 3], [7, 7]])
        self.assertEqual(cp.power_rows_decode(rows), tiles)

    def test_job_tiles(self):
        self.assertEqual(cp.power_job_tiles(10, -5), [(0, -1), (1, -1)])
        self.assertEqual(cp.power_job_tiles(15, 20), [(1, 1), (1, 2)])
        self.assertEqual(cp.power_job_tiles(15, 25), [(1, 2)])

    def test_note_power_job(self):
        ledger = cp.note_power_job(None, cp.POWER_LINE_KIND, 10, -5)
        self.assertEqual(cp.power_rows_decode(ledger["rows"]), {(0, -1), (1, -1)})
        ledger = cp.note_power_job(ledger, cp.DECONSTRUCT_KIND, 10, -5)
        self.assertEqual({tuple(d) for d in ledger["dirty"]}, {(0, -1), (1, -1)})
        self.assertEqual(cp.power_rows_decode(ledger["rows"]), {(0, -1), (1, -1)})  # kept until re-probed
        ledger = cp.note_power_job(ledger, cp.POWER_BRIDGE_KIND, 55, 55)
        self.assertIn([5, 5], ledger["dirty"])
        self.assertEqual(cp.note_power_job(ledger, "pipe", 0, 0), cp.clean_power_ledger(ledger))

    def test_dirty_cap_requests_survey(self):
        ledger = cp.clean_power_ledger({"surveyed": 5, "rows": {}, "dirty": []})
        cp.mark_power_dirty(ledger, [(i, 0) for i in range(cp.POWER_DIRTY_MAX + 1)])
        self.assertIsNone(ledger["surveyed"])
        self.assertEqual(ledger["dirty"], [])

    def test_held_kinds(self):
        hold = {"by": "x", "tick": 100, "kinds": ["deconstruct"]}
        self.assertEqual(cp.held_kinds(hold, 150), {"deconstruct"})
        self.assertEqual(cp.held_kinds(hold, 100 + cp.HOLD_STALE_TICKS), set())
        self.assertEqual(cp.held_kinds(None, 150), set())
        self.assertEqual(cp.held_kinds({"tick": 1, "kinds": "deconstruct"}, 2), set())


class SurveyTests(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        self.log = harness.TreeConsole(module="infra_planner")
        # line along y tile 0 from x tile 2 to 5: ends (2,0),(5,0) have 1 piece, interior 2
        self.pieces = {(2, 0): 1, (3, 0): 2, (4, 0): 2, (5, 0): 1}
        self.blueprints = ProbeBlueprints(self.pieces)
        self.blueprints.notebook = self.world.notebook
        self.world.services["construction_blueprint"] = self.blueprints
        self.ledger_raw = lambda: self.world.notebook.data.get(cp.POWER_TILES_KEY)

    def test_full_survey_finds_line_and_cancels_probe_jobs(self):
        self.assertEqual(ps.run_full(self.log), "done")
        self.assertEqual(self.blueprints.calls, (ps.MAP_MAX_TILE - ps.MAP_MIN_TILE + 1) ** 2)
        self.assertEqual(cp.power_rows_decode(self.ledger_raw()["rows"]), set(self.pieces))
        self.assertEqual(self.blueprints.jobs, [])
        self.assertEqual(len(self.blueprints.cancelled), 2)
        self.assertIsNotNone(self.ledger_raw()["surveyed"])
        self.assertTrue(all(h and h["kinds"] == ["deconstruct"] for h in self.blueprints.hold_seen))
        self.assertNotIn(cp.HOLD_KEY, self.world.notebook.data)
        self.assertEqual(ps.ledger_tiles(), {g.tile_key(tx, ty) for tx, ty in self.pieces})

    def test_survey_keeps_pioneer_tiles_and_dirty(self):
        self.world.notebook.data[cp.POWER_TILES_KEY] = {"surveyed": None, "rows": {}, "dirty": [[9, 9]]}
        original = self.blueprints.mark_deconstruct

        def probe(x, y, layer="auto", target_id=""):
            if self.blueprints.calls == 100:  # a Pioneer finishes a piece mid-survey
                raw = self.world.notebook.data[cp.POWER_TILES_KEY]
                self.world.notebook.data[cp.POWER_TILES_KEY] = cp.note_power_job(raw, cp.POWER_LINE_KIND, 10, -805)
            return original(x, y, layer, target_id)

        self.blueprints.mark_deconstruct = probe
        ps.run_full(self.log)
        tiles = cp.power_rows_decode(self.ledger_raw()["rows"])
        self.assertTrue({(0, -81), (1, -81)} <= tiles)
        self.assertEqual(self.ledger_raw()["dirty"], [[9, 9]])

    def test_locked_aborts_without_ledger(self):
        self.blueprints.locked = True
        self.assertEqual(ps.run_full(self.log), "locked")
        self.assertEqual(self.blueprints.calls, 1)
        self.assertIsNone(self.ledger_raw())
        self.assertNotIn(cp.HOLD_KEY, self.world.notebook.data)

    def test_hold_cleared_on_exception(self):
        def boom(_self):
            raise RuntimeError("walk aborted")

        original = ps.Prober.retry_leftover
        ps.Prober.retry_leftover = boom
        try:
            with self.assertRaises(RuntimeError):
                ps.run_full(self.log)
        finally:
            ps.Prober.retry_leftover = original
            harness.tree_console.reset_all()
        self.assertNotIn(cp.HOLD_KEY, self.world.notebook.data)

    def test_failed_cancel_retried(self):
        self.blueprints.fail_cancel = {"dc1"}
        ps.run_full(self.log)
        self.assertEqual(self.blueprints.jobs, [])

    def test_reprobe_dirty(self):
        self.world.notebook.data[cp.POWER_TILES_KEY] = {
            "surveyed": 1, "rows": cp.power_rows_encode({(7, 7)}), "dirty": [[7, 7], [3, 0]]}
        self.assertEqual(ps.reprobe_dirty(self.log), 2)
        ledger = self.ledger_raw()
        self.assertEqual(cp.power_rows_decode(ledger["rows"]), {(3, 0)})
        self.assertEqual(ledger["dirty"], [])
        self.assertNotIn(cp.HOLD_KEY, self.world.notebook.data)

    def test_vanished_dirty(self):
        seen = {"a": {"k": "power_line", "t": [[0, 0], [1, 0]]},
                "b": {"k": "power_line", "t": [[5, 5], [6, 5]]},
                "c": {"k": "deconstruct", "t": [[0, 0], [1, 0]]},
                "d": {"k": "power_line", "t": [[8, 8], [9, 8]]}}
        out = ps.vanished_dirty(seen, {"d": {}}, {(0, 0), (1, 0)})
        self.assertEqual(sorted(out), [(0, 0), (1, 0), (5, 5), (6, 5)])


if __name__ == "__main__":
    unittest.main()


class PioneerLedgerTests(harness.StubTestCase):
    """PioneerController's hold reader and power-job recorder, called with a minimal stand-in self."""

    class FakeSelf:
        name = "pioneer_1"

        def __init__(self):
            self.log = harness.TreeConsole(module="pioneer")

    def test_note_finished_power_job(self):
        from pioneer import PioneerController
        me = self.FakeSelf()
        PioneerController.note_finished_power_job(me, cp.POWER_LINE_KIND, (10.0, -5.0))
        PioneerController.note_finished_power_job(me, "mining_drill_heavy", (10.0, -5.0))
        raw = self.world.notebook.data[cp.POWER_TILES_KEY]
        self.assertEqual(cp.power_rows_decode(raw["rows"]), {(0, -1), (1, -1)})
        PioneerController.note_finished_power_job(me, cp.DECONSTRUCT_KIND, (10.0, -5.0))
        self.assertEqual(len(self.world.notebook.data[cp.POWER_TILES_KEY]["dirty"]), 2)

    def test_read_construction_hold(self):
        from pioneer import PioneerController
        me = self.FakeSelf()
        self.assertEqual(PioneerController.read_construction_hold(me, 10), set())
        self.world.notebook.data[cp.HOLD_KEY] = {"by": "t", "tick": 10, "kinds": ["deconstruct"]}
        self.assertEqual(PioneerController.read_construction_hold(me, 20), {"deconstruct"})
