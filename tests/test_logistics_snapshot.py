"""lib/logistics_snapshot.py: the tier snapshot record, its reader and the pickup correction."""

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
        entries = {o.id: snap.build_entry(o, reads, ["iron_ore"]) for o in outposts}
        self.assertTrue(snap.publish_snapshot(entries, now))
        record, state = snap.read_snapshot(now)
        self.assertEqual(state, snap.FRESH)
        assert record is not None
        self.assertEqual(record["tick"], now)
        self.assertEqual(set(record["outposts"]), set(entries))

    def test_publish_without_clock_is_false(self):
        self.assertFalse(snap.publish_snapshot({}, 0))
        self.assertIsNone(ARCHIVE.get(snap.LOGISTICS_SNAPSHOT_KEY, None))


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
