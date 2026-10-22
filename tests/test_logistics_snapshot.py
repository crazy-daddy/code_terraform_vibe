"""lib/logistics_snapshot.py: the tier snapshot record, its reader and the pickup correction."""

import json
from unittest import mock

import harness
import logistics_snapshot as snap
from harness import StubTestCase, logistics_requests
from priority import BLOCKER, FAIR_BANDS, NEED, STOCK

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

    def test_task_error_skips_outpost(self):
        self._world()
        calls: list = []
        with self._slow_entries(calls, fail_for=("outpost_a",)), mock.patch.object(snap, "swallowed") as swallowed:
            results = []
            while not (results and results[-1]) and len(results) < 5:
                results.append(self.publisher.step(self.world.clock.now))
        self.assertTrue(results[-1])
        swallowed.assert_called_once()
        record, _state = snap.read_snapshot(self.world.clock.now)
        assert record is not None
        self.assertEqual(set(record["outposts"]), {"home", "outpost_b"})

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
            (3000, snap.FRESH),
            (3001, snap.STALE),
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
        self.assertIsNone(snap.view(reads, base + 3001))
        self.assertIsNotNone(snap.view(reads, base + 3001, allow_stale=True))
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
