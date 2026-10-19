"""lib/outpost_flow.py: decayed flow counters and the idle-hauler dispersal choice."""

import harness
import outpost_flow as of
from archive import archive

HALF = of.FLOW_HALF_LIFE_TICKS


class _Outpost:
    def __init__(self, outpost_id):
        self.id = outpost_id


class FlowCounterTests(harness.StubTestCase):
    def test_record_adds_to_decayed_values(self):
        of.record(0, sent={"a": 100}, received={"b": 40})
        of.record(HALF, sent={"a": 10})
        flow = archive.get(of.OUTPOST_FLOW_KEY)
        self.assertEqual(flow["a"], {"sent": 60.0, "received": 0.0, "tick": HALF})
        self.assertEqual(flow["b"], {"sent": 0.0, "received": 40.0, "tick": 0})
        self.assertEqual(of.read(2 * HALF), {"a": (30.0, 0.0), "b": (0.0, 10.0)})

    def test_record_skips_empty_and_unknown(self):
        of.record(5, sent={None: 10, "a": 0}, received={})
        self.assertIsNone(archive.get(of.OUTPOST_FLOW_KEY))

    def test_decayed_tolerates_malformed(self):
        self.assertEqual(of.decayed("junk", 10), (0.0, 0.0))
        self.assertEqual(of.decayed({"sent": 8}, 0), (8.0, 0.0))


class SourceOutpostTests(harness.StubTestCase):
    def test_own_outpost_else_nearest(self):
        outposts = {"a": (0.0, 0.0), "b": (100.0, 0.0)}
        moved = [
            ({"kind": "outpost", "outpost": _Outpost("b"), "coords": (0.0, 0.0)}, 30),
            ({"kind": "drill", "outpost": None, "coords": (90.0, 5.0)}, 20),
            ({"kind": "pump", "coords": (2.0, 2.0)}, 7),
            ({"kind": "drill", "coords": (2.0, 2.0)}, 0),
            ({"kind": "shop", "outpost": _Outpost("a"), "coords": (0.0, 0.0)}, 9),
        ]
        self.assertEqual(of.sent_by_outpost(moved, outposts), {"b": 50, "a": 7})

    def test_no_outposts_no_credit(self):
        self.assertEqual(of.sent_by_outpost([({"kind": "drill", "coords": (1.0, 1.0)}, 5)], {}), {})


class IdleHaulerTests(harness.StubTestCase):
    def test_counts_fresh_on_duty_pioneer_haulers_by_base(self):
        status = {
            "p1": {"role": "hauler", "state": "IDLE_AT_OUTPOST", "base": "a", "tick": 900},
            "p2": {"role": "hauler", "state": "READY_AT_OUTPOST", "base": "a", "tick": 900},
            "p3": {"role": "hauler", "state": "MOVING", "base": "a", "tick": 900},
            "p4": {"role": "hauler", "state": "RECALLED", "base": "b", "tick": 900},
            "p5": {"role": "hauler", "state": "IDLE_AT_OUTPOST", "base": "b", "tick": 900 - of.IDLE_STALE_TICKS},
            "d1": {"role": "hauler", "state": "IDLE_AT_OUTPOST", "home": "b", "tick": 900},
            "p6": {"role": "miner", "state": "IDLE_AT_OUTPOST", "base": "b", "tick": 900},
            "me": {"role": "hauler", "state": "IDLE_AT_OUTPOST", "base": "b", "tick": 900},
        }
        self.assertEqual(of.idle_haulers_by_base(status, 1000, exclude="me"), {"a": 2})


class DispersalTargetTests(harness.StubTestCase):
    OUTPOSTS = {"a": (0.0, 0.0), "b": (100.0, 0.0), "c": (200.0, 0.0)}

    def test_moves_to_busiest_source(self):
        flow = {"a": (0.0, 50.0), "b": (40.0, 0.0), "c": (10.0, 0.0)}
        self.assertEqual(of.dispersal_target("a", self.OUTPOSTS, flow, {}, (0.0, 0.0)), "b")

    def test_spreads_over_idle_haulers(self):
        # b sends twice what c does but already has three idle haulers.
        flow = {"b": (39.0, 0.0), "c": (19.0, 0.0)}
        self.assertEqual(of.dispersal_target("a", self.OUTPOSTS, flow, {"b": 3}, (0.0, 0.0)), "c")

    def test_stays_below_gain(self):
        flow = {"a": (10.0, 0.0), "b": (12.0, 0.0)}
        self.assertIsNone(of.dispersal_target("a", self.OUTPOSTS, flow, {}, (0.0, 0.0)))

    def test_balanced_pair_stays(self):
        flow = {"a": (10.0, 0.0), "b": (10.0, 0.0)}
        self.assertIsNone(of.dispersal_target("a", self.OUTPOSTS, flow, {"b": 1}, (0.0, 0.0)))
        self.assertEqual(of.dispersal_target("a", self.OUTPOSTS, flow, {"a": 1}, (0.0, 0.0)), "b")

    def test_tie_goes_to_nearest(self):
        flow = {"b": (20.0, 0.0), "c": (20.0, 0.0)}
        self.assertEqual(of.dispersal_target("a", self.OUTPOSTS, flow, {}, (190.0, 0.0)), "c")

    def test_no_flow_stays(self):
        self.assertIsNone(of.dispersal_target("a", self.OUTPOSTS, {}, {}, (0.0, 0.0)))
        self.assertIsNone(of.dispersal_target("a", {}, {}, {}, None))

    def test_base_gone_moves(self):
        self.assertEqual(of.dispersal_target("gone", {"a": (0.0, 0.0)}, {}, {}, (0.0, 0.0)), "a")


if __name__ == "__main__":
    import unittest

    unittest.main()
