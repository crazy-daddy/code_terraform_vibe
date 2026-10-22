"""lib/logistics_snapshot.py: the tier snapshot record, its reader and the pickup correction."""

import json
from unittest import mock

import harness
import logistics_snapshot as snap
import pull_plan
import role_demand
from harness import StubTestCase, logistics_requests
from job_pull import NO_DEMAND, PullJob
from priority import BLOCKER, FAIR_BANDS, NEED, STOCK
from test_job_pull import _Host

R = harness.request
ARCHIVE = harness.archive.archive


def _record(tick, **outposts):
    return {"v": snap.LOGISTICS_SNAPSHOT_VERSION, "tick": tick, "outposts": outposts}


def _entry(deficits=None, free=None, flying=None, taken=None):
    return {
        "deficits": {str(b): dict(v) for b, v in (deficits or {}).items()},
        "free": {str(b): dict(v) for b, v in (free or {}).items()},
        "flying": dict(flying or {}),
        "taken": dict(taken or {}),
    }


class SnapshotCase(StubTestCase):
    def _world(self):
        w = self.world
        now = w.clock.now
        a = w.add_outpost("outpost_a")
        b = w.add_outpost("outpost_b")
        w.add_warehouse("wh_home", w.home, {"iron_ore": 40, "copper_ore": 5})
        w.add_warehouse("wh_a", a, {"iron_ore": 300, "copper_ore": 120, "salt": 7})
        w.add_warehouse("wh_b", b, {"copper_ore": 30})
        w.inventory.items["copper_ore"] = 11
        logistics_requests.set_requests("home", "smelter", {"iron_ore": (R(200, 80), 0), "copper_ore": (R(60), 0)}, now)
        logistics_requests.set_requests(
            "outpost_a", "fab", {"iron_ore": (R(100, 50), 0), "copper_ore": (R(50, 10), 0)}, now
        )
        logistics_requests.set_requests(
            "outpost_b", "fab", {"iron_ore": (R(90, 20), 0), "copper_ore": (R(40, 10), 30)}, now
        )
        logistics_requests.reserve_pickup("drone_2", "home", "iron_ore", 30, now, source_id="outpost_a")
        logistics_requests.reserve_pickup("drone_1", "outpost_b", "iron_ore", 9, now, source_id="outpost_a")
        return now, [w.home, a, b]

    def _reads(self, *pickups):
        """PlanReads over the stub world plus extra reserve_pickup() calls (vehicle, dest, item, units, source)."""
        now = self.world.clock.now
        for vehicle, dest, item_id, units, source in pickups:
            logistics_requests.reserve_pickup(vehicle, dest, item_id, units, now, source_id=source)
        return logistics_requests.PlanReads(now)


class EntryTests(SnapshotCase):
    def test_entry_matches_live_reads(self):
        now, outposts = self._world()
        reads = logistics_requests.PlanReads(now)
        items = ["iron_ore", "copper_ore", "salt"]
        entries = {o.id: snap.build_entry(o, reads, items) for o in outposts}
        view = snap.TierView(_record(now, **entries), reads)
        for o in outposts:
            want = logistics_requests.outpost_tier_deficits(o, now, live=True, reads=reads)
            self.assertEqual(view.deficits(o.id), want, o.id)
            free = logistics_requests.outpost_tier_free(
                o, items, None, now, loader=logistics_requests.LOADER_DRONE, reads=reads
            )
            self.assertEqual(view.free(o.id, items), free, o.id)
            entry = entries[o.id]
            self.assertEqual(entry["flying"], dict(reads.in_flight(o.id)))
            self.assertEqual(entry["taken"], dict(reads.reserved_from(o.id)))
            for field in ("deficits", "free"):
                self.assertTrue(all(isinstance(band, str) for band in entry[field]))

    def test_publish_and_read_roundtrip(self):
        now, outposts = self._world()
        reads = logistics_requests.PlanReads(now)
        idle = self.world.add_outpost("outpost_idle")  # no requests, no stock, no pickups
        entries: dict = {o.id: snap.build_entry(o, reads, ["iron_ore"]) for o in [*outposts, idle]}
        self.assertFalse(any(entries[idle.id][field] for field in ("deficits", "free", "flying", "taken")))
        entries[None] = entries["outpost_a"]  # an id that is not a str is not a JSON-safe key
        self.assertTrue(snap.publish_snapshot(entries, now))
        record, state = snap.read_snapshot(now)
        self.assertEqual(state, snap.FRESH)
        assert record is not None
        self.assertEqual(record["tick"], now)
        self.assertEqual(set(record["outposts"]), {o.id for o in outposts})  # nothing-in-any-field and None left out
        # What the game stores is JSON: int band keys or tuples would not survive it.
        self.assertEqual(json.loads(json.dumps(record)), record)
        view = snap.TierView(json.loads(json.dumps(record)), reads)
        for o in outposts:
            self.assertEqual(view.deficits(o.id), logistics_requests.outpost_tier_deficits(o, now, reads=reads), o.id)

    def test_publish_without_clock_is_false(self):
        self.assertFalse(snap.publish_snapshot({}, 0))
        self.assertIsNone(ARCHIVE.get(snap.LOGISTICS_SNAPSHOT_KEY, None))


class PublisherTests(SnapshotCase):
    def setUp(self):
        super().setUp()
        self.publisher = snap.SnapshotPublisher()

    def _slow_entries(self, calls, fail_for=()):
        """A build_entry stand-in that advances the stub clock 60 ticks per task and records the outpost ids."""
        real = snap.build_entry

        def build(outpost, reads, item_ids):
            calls.append(outpost.id)
            self.world.clock.now += 60
            if outpost.id in fail_for:
                raise RuntimeError("boom")
            return real(outpost, reads, item_ids)

        return mock.patch.object(snap, "build_entry", build)

    def test_round_publishes_every_outpost(self):
        now, outposts = self._world()
        self.assertTrue(self.publisher.step(now))  # the stub clock stands still: one call runs the round
        record, state = snap.read_snapshot(now)
        self.assertEqual(state, snap.FRESH)
        assert record is not None
        self.assertEqual(record["tick"], now)
        self.assertEqual(set(record["outposts"]), {o.id for o in outposts})
        reads = logistics_requests.PlanReads(now)
        view = snap.TierView(record, reads)
        for o in outposts:
            self.assertEqual(
                view.deficits(o.id), logistics_requests.outpost_tier_deficits(o, now, live=True, reads=reads)
            )
        free = logistics_requests.outpost_tier_free(
            outposts[1], ["iron_ore", "copper_ore"], None, now, loader=logistics_requests.LOADER_DRONE, reads=reads
        )
        self.assertEqual(view.free("outpost_a", ["iron_ore", "copper_ore"]), free)

    def test_not_due_before_interval(self):
        now, _ = self._world()
        self.assertTrue(self.publisher.step(now))
        ARCHIVE.set(snap.LOGISTICS_SNAPSHOT_KEY, None)
        with mock.patch.object(snap, "build_entry") as build:
            self.assertFalse(self.publisher.step(now + snap.LOGISTICS_SNAPSHOT_TICKS - 1))
            build.assert_not_called()
        self.assertIsNone(ARCHIVE.get(snap.LOGISTICS_SNAPSHOT_KEY, None))
        self.assertTrue(self.publisher.step(now + snap.LOGISTICS_SNAPSHOT_TICKS))
        record, _state = snap.read_snapshot(now + snap.LOGISTICS_SNAPSHOT_TICKS)
        assert record is not None
        self.assertEqual(record["tick"], now + snap.LOGISTICS_SNAPSHOT_TICKS)

    def test_step_stops_after_slice(self):
        now, _ = self._world()
        for n in range(4, 8):
            self.world.add_outpost(f"outpost_x{n}")  # 3 + 4 = 7 outposts
        calls: list = []
        with self._slow_entries(calls):
            self.assertFalse(self.publisher.step(self.world.clock.now))
            self.assertEqual(len(calls), 2)  # 60 < 100 runs a second task, 120 stops
            self.assertIsNone(ARCHIVE.get(snap.LOGISTICS_SNAPSHOT_KEY, None))
            results = []
            while len(results) < 6 and not (results and results[-1]):
                results.append(self.publisher.step(self.world.clock.now))
        self.assertEqual(results, [False, False, True])  # 2 + 2 + 2 + 1 tasks
        self.assertEqual(sorted(calls), sorted(self.world.outposts))
        self.assertEqual(len(calls), 7)
        record, _state = snap.read_snapshot(self.world.clock.now)
        assert record is not None
        self.assertEqual(record["tick"], now)  # the round's start tick

    def test_task_error_discards_round(self):
        now, _ = self._world()
        old = _record(now - 10, outpost_a=_entry(deficits={STOCK: {"iron_ore": 3}}))
        ARCHIVE.set(snap.LOGISTICS_SNAPSHOT_KEY, old)
        calls: list = []
        with self._slow_entries(calls, fail_for=("outpost_a",)), mock.patch.object(snap, "swallowed") as swallowed:
            results = [self.publisher.step(self.world.clock.now) for _ in range(3)]
        self.assertEqual(len(calls), 3)  # every outpost was still tried
        self.assertEqual(results, [False, False, False])  # the round finished and published nothing
        self.assertEqual(swallowed.call_count, 2)  # the build error, then the discarded round
        self.assertEqual(ARCHIVE.get(snap.LOGISTICS_SNAPSHOT_KEY, None), old)
        self.assertFalse(self.publisher.active)

    def test_clean_round_publishes_after_a_discarded_one(self):
        now, _ = self._world()
        calls: list = []
        with self._slow_entries(calls, fail_for=("outpost_a",)), mock.patch.object(snap, "swallowed"):
            while self.publisher.active or not calls:
                self.assertFalse(self.publisher.step(self.world.clock.now))
        self.assertIsNone(ARCHIVE.get(snap.LOGISTICS_SNAPSHOT_KEY, None))
        self.world.clock.now = now + snap.LOGISTICS_SNAPSHOT_TICKS - 1
        with mock.patch.object(snap, "build_entry") as build:
            self.assertFalse(
                self.publisher.step(self.world.clock.now)
            )  # the next round is 600 ticks after this one began
            build.assert_not_called()
        self.world.clock.now = now + snap.LOGISTICS_SNAPSHOT_TICKS
        self.assertTrue(self.publisher.step(self.world.clock.now))
        record, _state = snap.read_snapshot(self.world.clock.now)
        assert record is not None
        self.assertEqual(record["tick"], now + snap.LOGISTICS_SNAPSHOT_TICKS)
        self.assertEqual(set(record["outposts"]), {"home", "outpost_a", "outpost_b"})

    def test_refused_write_is_logged(self):
        now, _ = self._world()
        with (
            mock.patch.object(snap.archive, "set", return_value=False),
            mock.patch.object(snap, "swallowed") as swallowed,
        ):
            self.assertFalse(self.publisher.step(now))
        swallowed.assert_called_once_with("logistics_snapshot.SnapshotPublisher.step", "record write refused")
        self.assertFalse(self.publisher.active)
        self.assertIsNone(ARCHIVE.get(snap.LOGISTICS_SNAPSHOT_KEY, None))

    def test_no_clock_starts_nothing(self):
        self._world()
        with mock.patch.object(snap, "build_entry") as build:
            self.assertFalse(self.publisher.step(0))
            build.assert_not_called()


class ReadStateTests(SnapshotCase):
    def test_read_states(self):
        base = 100000
        ARCHIVE.set(snap.LOGISTICS_SNAPSHOT_KEY, _record(base))
        for age, state in (
            (0, snap.FRESH),
            (5000, snap.FRESH),
            (5001, snap.STALE),
            (6000, snap.STALE),
            (6001, snap.MISSING),
            (-1, snap.MISSING),  # stamped ahead of the clock
        ):
            record, got = snap.read_snapshot(base + age)
            self.assertEqual(got, state, age)
            self.assertEqual(record is None, state == snap.MISSING, age)

    def test_other_version_and_nothing_stored_are_missing(self):
        base = 100000
        self.assertEqual(snap.read_snapshot(base), (None, snap.MISSING))
        ARCHIVE.set(snap.LOGISTICS_SNAPSHOT_KEY, {"v": 2, "tick": base, "outposts": {}})
        self.assertEqual(snap.read_snapshot(base), (None, snap.MISSING))
        ARCHIVE.set(snap.LOGISTICS_SNAPSHOT_KEY, "junk")
        self.assertEqual(snap.read_snapshot(base), (None, snap.MISSING))
        ARCHIVE.set(snap.LOGISTICS_SNAPSHOT_KEY, {"v": 1, "tick": base, "outposts": []})
        self.assertEqual(snap.read_snapshot(base), (None, snap.MISSING))

    def test_junk_entries_read_as_empty(self):
        junk = {
            "bad_fields": {
                "deficits": {"x": {"a": 1}, "400": "bad", "300": {"i": "many", "j": 5}},
                "free": 3,
                "flying": {"i": "s"},
                "taken": None,
            },
            "not_a_dict": "junk",
        }
        view = snap.TierView(_record(1, **junk), self._reads())
        self.assertEqual(view.deficits("bad_fields"), {300: {"j": 5}})
        self.assertEqual(view.free("bad_fields", ["j"]), {tier: {} for tier in logistics_requests.TIERS})
        self.assertEqual(view.deficits("not_a_dict"), {})
        self.assertEqual(snap.TierView({"outposts": "junk"}, self._reads()).deficits("x"), {})

    def test_no_clock_is_missing(self):
        ARCHIVE.set(snap.LOGISTICS_SNAPSHOT_KEY, _record(5))
        self.world.clock.now = 0
        self.assertEqual(snap.read_snapshot(), (None, snap.MISSING))

    def test_view_none_unless_fresh(self):
        base = 100000
        reads = self._reads()
        ARCHIVE.set(snap.LOGISTICS_SNAPSHOT_KEY, _record(base))
        self.assertIsNotNone(snap.view(reads, base + 10))
        self.assertIsNone(snap.view(reads, base + 5001))
        self.assertIsNotNone(snap.view(reads, base + 5001, allow_stale=True))
        self.assertIsNone(snap.view(reads, base + 6001))
        self.assertIsNone(snap.view(reads, base + 6001, allow_stale=True))


class CorrectionTests(SnapshotCase):
    def test_new_pickup_cuts_top_band_first(self):
        self._world()
        reads = self._reads(("drone_7", "outpost_a", "x", 8, "outpost_b"))
        entry = _entry(deficits={BLOCKER: {"x": 5}, NEED: {"x": 10}}, flying={})
        view = snap.TierView(_record(1, outpost_a=entry), reads)
        self.assertEqual(view.deficits("outpost_a"), {NEED: {"x": 7}})

    def test_delivered_pickup_keeps_deficit_covered(self):
        self._world()
        reads = self._reads()
        entry = _entry(deficits={NEED: {"x": 4}}, flying={"x": 10})
        view = snap.TierView(_record(1, outpost_a=entry), reads)
        self.assertEqual(view.deficits("outpost_a"), {NEED: {"x": 4}})

    def test_pickup_already_in_record_changes_nothing(self):
        self._world()
        reads = self._reads(("drone_7", "outpost_a", "x", 8, "outpost_b"))
        entry = _entry(deficits={NEED: {"x": 4}}, flying={"x": 8})
        view = snap.TierView(_record(1, outpost_a=entry), reads)
        self.assertEqual(view.deficits("outpost_a"), {NEED: {"x": 4}})

    def test_new_reservation_cuts_every_free_band(self):
        self._world()
        reads = self._reads(("drone_7", "outpost_b", "x", 8, "outpost_a"))
        entry = _entry(free={NEED: {"x": 6}, STOCK: {"x": 20}}, taken={})
        view = snap.TierView(_record(1, outpost_a=entry), reads)
        free = view.free("outpost_a", ["x"])
        self.assertEqual(free[STOCK], {"x": 12})
        self.assertNotIn("x", free[NEED])
        mine = snap.TierView(_record(1, outpost_a=entry), reads, exclude_vehicle="drone_7")
        free = mine.free("outpost_a", ["x"])
        self.assertEqual(free[STOCK], {"x": 20})
        self.assertEqual(free[NEED], {"x": 6})

    def test_free_drops_non_positive_units_without_new_reservations(self):
        self._world()
        entry = _entry(free={NEED: {"x": 0}, STOCK: {"x": 4, "y": -2}})
        free = snap.TierView(_record(1, outpost_a=entry), self._reads()).free("outpost_a", ["x", "y"])
        self.assertEqual(free[STOCK], {"x": 4})
        self.assertNotIn("x", free[NEED])

    def test_free_subset_equals_full_free_filtered(self):
        self._world()
        reads = self._reads(
            ("drone_7", "outpost_b", "x", 8, "outpost_a"), ("drone_8", "outpost_b", "z", 50, "outpost_a")
        )
        entry = _entry(
            free={NEED: {"x": 6, "y": 4, "z": 30}, STOCK: {"x": 20, "y": 9, "z": 60}, BLOCKER: {"y": 1}},
            taken={"z": 10},
        )
        view = snap.TierView(_record(1, outpost_a=entry), reads)
        full = view.free("outpost_a", ["x", "y", "z"])
        self.assertEqual(full[STOCK], {"x": 12, "y": 9, "z": 20})
        for tiers in ((STOCK,), (NEED, STOCK), (BLOCKER,), ()):
            for items in (["x"], ["y", "z"], ["x", "y", "z", "nope"], []):
                got = view.free("outpost_a", items, tiers)
                self.assertEqual(set(got), set(logistics_requests.TIERS))
                for tier in logistics_requests.TIERS:
                    want = {i: u for i, u in full[tier].items() if i in items} if tier in tiers else {}
                    self.assertEqual(got[tier], want, (tiers, items, tier))

    def test_free_filters_to_item_ids(self):
        self._world()
        entry = _entry(free={STOCK: {"x": 20, "y": 3}})
        view = snap.TierView(_record(1, outpost_a=entry), self._reads())
        self.assertEqual(view.free("outpost_a", ["y"])[STOCK], {"y": 3})

    def test_unknown_outpost_reads_empty(self):
        view = snap.TierView(_record(1), self._reads())
        self.assertEqual(view.deficits("nope"), {})
        free = view.free("nope", ["x"])
        self.assertEqual(set(free), set(logistics_requests.TIERS))
        self.assertTrue(all(not units for units in free.values()))


class RivalsTests(SnapshotCase):
    def test_rivals_are_fair_bands_only_in_record_order(self):
        self._world()
        reads = self._reads(("drone_7", "outpost_a", "x", 55, "outpost_b"))
        band = FAIR_BANDS[0]
        record = _record(
            1,
            outpost_a=_entry(deficits={NEED: {"x": 50}, band: {"x": 10}, STOCK: {"x": 5}}),
            outpost_b=_entry(deficits={STOCK: {"x": 7, "y": 2}}),
            outpost_c=_entry(deficits={NEED: {"x": 9}}),
        )
        rivals = snap.TierView(record, reads).rivals(["x", "y"])
        self.assertEqual(
            rivals,
            {
                "x": [("outpost_a", {band: 5, STOCK: 5}), ("outpost_b", {STOCK: 7})],
                "y": [("outpost_b", {STOCK: 2})],
            },
        )

    def test_rivals_skip_items_not_asked_for(self):
        self._world()
        record = _record(1, outpost_a=_entry(deficits={STOCK: {"x": 5, "z": 1}}))
        rivals = snap.TierView(record, self._reads()).rivals(["x"])
        self.assertEqual(rivals, {"x": [("outpost_a", {STOCK: 5})]})


class TrimToLiveTests(StubTestCase):
    def test_trim_to_live_caps_legs(self):
        w = self.world
        now = w.clock.now
        dest = w.add_outpost("outpost_x")
        logistics_requests.set_requests("outpost_x", "fab", {"x": (R(5), 0)}, now)
        legs = [("a", "x", 4), ("b", "x", 4)]
        self.assertEqual(snap.trim_to_live(dest, legs, now), [("a", "x", 4), ("b", "x", 1)])
        w.add_warehouse("wh_x", dest, {"x": 5})  # filled since the record was built
        self.assertEqual(snap.trim_to_live(dest, legs, now), [("a", "x", 0), ("b", "x", 0)])

    def test_trim_to_live_leaves_growth_since_seen_to_the_claim(self):
        w = self.world
        now = w.clock.now
        dest = w.add_outpost("outpost_x")
        logistics_requests.set_requests("outpost_x", "fab", {"x": (R(5), 0)}, now)
        seen = logistics_requests.pickups_snapshot()
        logistics_requests.reserve_pickup("drone_7", "outpost_x", "x", 3, now, source_id="c")
        legs = [("a", "x", 4), ("b", "x", 4)]
        # Live deficit 2; claim_pickups() cuts drone_7's 3 itself, so the trim adds them back.
        self.assertEqual(snap.trim_to_live(dest, legs, now), [("a", "x", 2), ("b", "x", 0)])
        self.assertEqual(snap.trim_to_live(dest, legs, now, seen, "drone_9"), [("a", "x", 4), ("b", "x", 1)])
        # The claiming vehicle's own units are not claim_pickups()' to cut.
        self.assertEqual(snap.trim_to_live(dest, legs, now, seen, "drone_7"), [("a", "x", 2), ("b", "x", 0)])

    def test_trim_to_live_rival_landing_during_the_deficit_read_is_not_added_back(self):
        w = self.world
        now = w.clock.now
        dest = w.add_outpost("outpost_x")
        logistics_requests.set_requests("outpost_x", "fab", {"x": (R(5), 0)}, now)
        seen = logistics_requests.pickups_snapshot()
        live_deficits = snap.outpost_tier_deficits

        def deficits_then_rival_claim(*args, **kwargs):
            tiers = live_deficits(*args, **kwargs)
            logistics_requests.reserve_pickup("drone_7", "outpost_x", "x", 3, now, source_id="c")
            return tiers

        legs = [("a", "x", 4), ("b", "x", 4)]
        with mock.patch.object(snap, "outpost_tier_deficits", side_effect=deficits_then_rival_claim):
            trimmed = snap.trim_to_live(dest, legs, now, seen, "drone_9")
        # The deficit (5) was read without the rival's 3; the pickups were read before it, so the 3 is not
        # added back (that would grant 8 against a true deficit of 2). claim_pickups() then cuts the 3.
        self.assertEqual(trimmed, [("a", "x", 4), ("b", "x", 1)])

    def test_trim_to_live_rival_released_between_the_reads_is_not_added_back(self):
        w = self.world
        now = w.clock.now
        dest = w.add_outpost("outpost_x")
        logistics_requests.set_requests("outpost_x", "fab", {"x": (R(5), 0)}, now)
        seen = logistics_requests.pickups_snapshot()
        logistics_requests.reserve_pickup("drone_7", "outpost_x", "x", 3, now, source_id="c")
        read_pickups = snap.pickups_snapshot

        def read_then_release():
            pickups = read_pickups()
            logistics_requests.release_pickups("drone_7")
            return pickups

        legs = [("a", "x", 4), ("b", "x", 4)]
        with mock.patch.object(snap, "pickups_snapshot", side_effect=read_then_release):
            trimmed = snap.trim_to_live(dest, legs, now, seen, "drone_9")
        # One read holds the rival's 3: deficit 2 plus the 3 added back is the 5 the destination misses
        # once the rival has let go (separate reads would add the 3 back to a deficit of 5: 8).
        self.assertEqual(trimmed, [("a", "x", 4), ("b", "x", 1)])


class _PullHost(_Host):
    """test_job_pull's Pioneer stub on the stub world's clock."""

    def __init__(self, tick):
        super().__init__()
        self.tick = tick

    def get_current_tick(self):
        return self.tick


class PullSnapshotTests(SnapshotCase):
    def _publish(self, now, outposts, tick=None):
        reads = logistics_requests.PlanReads(now)
        entries = {o.id: snap.build_entry(o, reads, ["iron_ore", "copper_ore"]) for o in outposts}
        self.assertTrue(snap.publish_snapshot(entries, now if tick is None else tick))

    @staticmethod
    def _shape(groups):
        return [[(outpost.id, tiers) for outpost, tiers in group] for group in groups]

    def test_pull_destinations_from_snapshot(self):
        now, outposts = self._world()
        live = pull_plan.pull_destinations(now, logistics_requests.PlanReads(now))
        self.assertTrue(live)
        self._publish(now, outposts)
        reads = logistics_requests.PlanReads(now)
        view = snap.view(reads, now, exclude_vehicle="pioneer_8")
        assert view is not None
        with mock.patch.object(reads, "scan", side_effect=AssertionError("stock scan with a FRESH record")):
            groups = pull_plan.pull_destinations(now, reads, view)
        self.assertEqual(self._shape(groups), self._shape(live))

    def _pick(self, now, publish_tick=None, fill=True, second=False):
        """(job.pick() result, job, pull_destinations mock, claim_pickups mock, debug lines) for a record of outpost_x
        that the destination has outgrown (`fill`) since it was built; `second`: outpost_y, short in the record and
        live, is planned after it."""
        w = self.world
        dest = w.add_outpost("outpost_x")
        logistics_requests.set_requests("outpost_x", "fab", {"iron_ore": (R(50), 0)}, now)
        dests_in_record = [dest]
        if second:
            other = w.add_outpost("outpost_y")
            logistics_requests.set_requests("outpost_y", "fab", {"iron_ore": (R(50), 0)}, now)
            dests_in_record.append(other)
        self._publish(now, dests_in_record, publish_tick)
        if fill:
            w.add_warehouse("wh_x", dest, {"iron_ore": 50})
        src = {"kind": "outpost", "id": "outpost_9", "coords": (50.0, 0.0), "outpost": None}
        host = _PullHost(now)
        job = PullJob(host)
        with (
            mock.patch.object(pull_plan, "pull_destinations", wraps=pull_plan.pull_destinations) as dests,
            mock.patch.object(pull_plan, "plan_pull_route", return_value=([(src, [("iron_ore", 30)])], 30, (0.1,))),
            mock.patch.object(logistics_requests, "min_load_units", return_value=1),
            mock.patch.object(logistics_requests, "claim_pickups", wraps=logistics_requests.claim_pickups) as claim,
            mock.patch.object(host.log, "debug", wraps=host.log.debug) as debug,
        ):
            mission = job.pick()
        return mission, job, dests, claim, [c.args[0] for c in debug.call_args_list]

    def test_pull_pick_trims_to_live(self):
        now = self.world.clock.now
        mission, job, dests, claim, _lines = self._pick(now)
        self.assertIsNotNone(dests.call_args_list[0].args[2])  # planned from the FRESH record
        # The destination filled since the build: nothing to claim, the trip is dropped and planned live.
        self.assertIsNone(dests.call_args_list[1].args[2])
        self.assertEqual(len(dests.call_args_list), 2)
        claim.assert_not_called()
        self.assertIsNone(mission)
        self.assertEqual(job.wait, NO_DEMAND)  # nothing else short live
        self.assertEqual(logistics_requests.in_flight("outpost_x", now), {})

    def test_pull_pick_replans_live_when_the_snapshot_trip_trims_out(self):
        now = self.world.clock.now
        with mock.patch.object(snap, "trim_to_live", wraps=snap.trim_to_live) as trim:
            mission, _job, dests, claim, lines = self._pick(now, second=True)
        trim.assert_called_once()  # the live replan is not trimmed again
        assert mission is not None
        self.assertEqual(mission.target["dest"], "outpost_y")
        self.assertEqual(len(dests.call_args_list), 2)
        # The live plan is claimed as it is (no second trim); only the live trip reached claim_pickups().
        self.assertEqual([c.args[1] for c in claim.call_args_list], ["outpost_y"])
        self.assertEqual(logistics_requests.in_flight("outpost_y", now), {"iron_ore": 30})
        self.assertEqual(logistics_requests.in_flight("outpost_x", now), {})
        self.assertEqual(len([line for line in lines if "outpost_x" in line and "replanning live" in line]), 1, lines)

    def test_pull_pick_claims_the_live_deficit_of_a_snapshot_plan(self):
        now = self.world.clock.now
        mission, _job, _dests, claim, _lines = self._pick(now, fill=False)
        assert mission is not None
        self.assertEqual(mission.target["dest"], "outpost_x")
        self.assertEqual(claim.call_args.args[2], [("outpost_9", "iron_ore", 30)])
        self.assertEqual(logistics_requests.in_flight("outpost_x", now), {"iron_ore": 30})

    def test_pull_pick_stale_snapshot_plans_live_with_one_line(self):
        now = self.world.clock.now
        stale = now - snap.LOGISTICS_FRESH_TICKS - 1
        _mission, _job, dests, claim, lines = self._pick(now, publish_tick=stale)
        self.assertIsNone(dests.call_args.args[2])
        snapshot_lines = [line for line in lines if "snapshot" in line]
        self.assertEqual(len(snapshot_lines), 1, snapshot_lines)
        self.assertIn("STALE", snapshot_lines[0])
        # Planned live: the filled destination has no deficit, so no trip and nothing to claim.
        claim.assert_not_called()

    def test_pull_pick_stale_snapshot_claims_live(self):
        now = self.world.clock.now
        stale = now - snap.LOGISTICS_FRESH_TICKS - 1
        mission, _job, dests, claim, _lines = self._pick(now, publish_tick=stale, fill=False)
        self.assertIsNone(dests.call_args.args[2])
        assert mission is not None
        self.assertEqual(claim.call_args.args[2], [("outpost_9", "iron_ore", 30)])
        self.assertEqual(logistics_requests.in_flight("outpost_x", now), {"iron_ore": 30})

    def test_pull_pick_missing_snapshot_plans_live_silently(self):
        now = self.world.clock.now
        with mock.patch.object(snap, "read_snapshot", return_value=(None, snap.MISSING)):
            _mission, _job, dests, _claim, lines = self._pick(now)
        self.assertIsNone(dests.call_args.args[2])
        self.assertEqual([line for line in lines if "snapshot" in line], [])

    def test_pull_pick_missing_snapshot_claims_live(self):
        now = self.world.clock.now
        with mock.patch.object(snap, "read_snapshot", return_value=(None, snap.MISSING)):
            mission, _job, dests, claim, lines = self._pick(now, fill=False)
        self.assertIsNone(dests.call_args.args[2])
        assert mission is not None
        self.assertEqual(claim.call_args.args[2], [("outpost_9", "iron_ore", 30)])
        self.assertEqual([line for line in lines if "snapshot" in line], [])


class RoleDemandSnapshotTests(SnapshotCase):
    def _recorded(self, now, tick):
        """Publish a record whose deficits differ from the live ones (outpost_a: 7 iron_ore at NEED)."""
        entries = {o.id: _entry() for o in role_demand._network_outposts()}
        entries["outpost_a"] = _entry(deficits={NEED: {"iron_ore": 7}})
        self.assertTrue(snap.publish_snapshot(entries, tick))

    def test_role_compute_uses_stale_snapshot(self):
        now, _outposts = self._world()
        self._recorded(now, now - snap.LOGISTICS_FRESH_TICKS - 1)
        reads = logistics_requests.PlanReads(now)
        view = snap.view(reads, now, allow_stale=True)
        assert view is not None
        with (
            mock.patch.object(reads, "scan", side_effect=AssertionError("stock scan with a STALE record")),
            mock.patch.object(role_demand, "outpost_tier_deficits", side_effect=AssertionError("live deficits")),
        ):
            parts = role_demand.compute(now, reads, view)["parts"]
        self.assertEqual(parts["deficits"]["outpost_a"], {NEED: {"iron_ore": 7}})
        self.assertEqual(parts["deficits"]["outpost_b"], {})
        self.assertEqual(parts["requests"], reads.requests)

    def test_role_compute_missing_is_live(self):
        now, _outposts = self._world()
        live = role_demand.compute(now, logistics_requests.PlanReads(now))
        self.assertTrue(any(live["parts"]["deficits"].values()))
        with mock.patch.object(snap, "read_snapshot", return_value=(None, snap.MISSING)):
            reads = logistics_requests.PlanReads(now)
            view = snap.view(reads, now, allow_stale=True)
            self.assertIsNone(view)
            again = role_demand.compute(now, reads, view)
        self.assertEqual(again, live)

    def test_role_publish_writes_the_snapshot_deficits(self):
        now, _outposts = self._world()
        self._recorded(now, now)
        reads = logistics_requests.PlanReads(now)
        view = snap.view(reads, now, allow_stale=True)
        value = role_demand.publish(now, reads, view)
        self.assertEqual(value["parts"]["deficits"]["outpost_a"], {NEED: {"iron_ore": 7}})
