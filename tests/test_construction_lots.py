"""pioneer_construction build lots: construction.lots read/write against the
shared archive and fleet.status, and the restock step reserving a lot."""
import unittest

import harness
import construction_plan
import fleet_status
import pioneer_construction
from archive import archive
from tree_console import TreeConsole


def _row(job_id, x, count=1, item="power_line_segment"):
    return {"id": job_id, "coords": (x, 0), "kind": "power_line", "job": job_id, "item": item, "count": count, "progress": 0.0, "prio": 0}


def _builder_status(*names, tick=1000):
    return {name: {"role": "constructor", "home": "outpost_home", "state": "BUILDING", "tick": tick} for name in names}


class _Builder(pioneer_construction.PioneerConstructionMixin):
    def __init__(self, name, tick=1000):
        self.name = name
        self.tick = tick
        self.log = TreeConsole()

    def get_current_tick(self):
        return self.tick


class LotArchiveTests(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        archive.set(fleet_status.FLEET_STATUS_KEY, _builder_status("pioneer_4", "pioneer_14"))

    def test_peer_lot_taken_own_lot_mine(self):
        _Builder("pioneer_14").write_construction_lot([_row("bp_1", 0), _row("bp_2", 10)])
        _Builder("pioneer_4").write_construction_lot([_row("bp_3", 20)])
        taken, mine = _Builder("pioneer_4").read_construction_lots(1000)
        self.assertEqual(taken, {"bp_1", "bp_2"})
        self.assertEqual(mine, {"bp_3"})

    def test_write_keeps_peer_reservations(self):
        _Builder("pioneer_14").write_construction_lot([_row("bp_1", 0)])
        kept = _Builder("pioneer_4").write_construction_lot([_row("bp_1", 0), _row("bp_2", 10)])
        self.assertEqual(kept, ["bp_2"])

    def test_inactive_owner_lot_ignored_and_pruned(self):
        _Builder("pioneer_14").write_construction_lot([_row("bp_1", 0)])
        status = _builder_status("pioneer_4", "pioneer_14")
        status["pioneer_14"]["state"] = "RECALLED"
        archive.set(fleet_status.FLEET_STATUS_KEY, status)
        taken, _ = _Builder("pioneer_4").read_construction_lots(1000)
        self.assertEqual(taken, set())
        _Builder("pioneer_4").write_construction_lot([_row("bp_1", 0)])
        self.assertEqual(set(archive.get(construction_plan.LOTS_KEY, {})), {"pioneer_4"})

    def test_release(self):
        builder = _Builder("pioneer_4")
        builder.write_construction_lot([_row("bp_1", 0)])
        builder.release_construction_lot()
        self.assertNotIn("pioneer_4", archive.get(construction_plan.LOTS_KEY, {}))


class ReserveLotTests(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        archive.set(fleet_status.FLEET_STATUS_KEY, _builder_status("pioneer_4", "pioneer_14"))

    def test_two_builders_split_one_line(self):
        line = [_row(f"bp_{i}", i * 10) for i in range(40)]
        first = _Builder("pioneer_4")
        first._reserve_lot(line[0], line, 20)
        taken, _ = _Builder("pioneer_14").read_construction_lots(1000)
        rest = [row for row in line if row["id"] not in taken]
        _Builder("pioneer_14")._reserve_lot(rest[0], rest, 20)
        _, first_lot = first.read_construction_lots(1000)
        _, second_lot = _Builder("pioneer_14").read_construction_lots(1000)
        self.assertEqual(first_lot, {f"bp_{i}" for i in range(20)})
        self.assertEqual(second_lot, {f"bp_{i}" for i in range(20, 40)})


if __name__ == "__main__":
    unittest.main()
