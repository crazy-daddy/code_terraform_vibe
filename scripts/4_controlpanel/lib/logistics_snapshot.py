# The logistics tier snapshot: every outpost's tier deficits and free stock
# computed once by the orchestrator and shared through the archive, so the
# haul and pull planners and role_demand.compute() read it instead of walking
# outpost_tier_deficits() / outpost_tier_free() per plan. Writer: the
# orchestrator only (publish_snapshot()); a reader never writes it.
#
# Shape of LOGISTICS_SNAPSHOT_KEY (one dict, JSON-safe, band keys are str):
#   {"v": LOGISTICS_SNAPSHOT_VERSION, "tick": round start tick,
#    "outposts": {outpost_id: {
#        "deficits": {band: {item_id: units}},  outpost_tier_deficits(live=True), in-flight and reserved yields counted
#        "free":     {band: {item_id: units}},  outpost_tier_free(loader=LOADER_DRONE), no exclude_vehicle
#        "flying":   {item_id: units},          reads.in_flight(outpost_id) when built
#        "taken":    {item_id: units}}}}        reads.reserved_from(outpost_id) when built
# Stock is as old as the record; pickups are read live. A TierView corrects
# an entry for what the pickups gained since the build: units newly claimed
# towards a destination cut its deficits from the top band down, units newly
# reserved from a source cut every band's free units. Units that left the
# in-flight set stay counted (delivered: the deficit stays covered).
from archive import archive
from game_clock import now_tick
from logistics_requests import LOADER_DRONE, REQUEST_STALE_TICKS, TIERS, PlanReads, outpost_tier_deficits, outpost_tier_free
from priority import FAIR_BANDS
from production_demand_record import FRESH, MISSING, STALE
from swallow import swallowed

LOGISTICS_SNAPSHOT_KEY = "logistics.tier_snapshot"
# Records of another version are never read.
LOGISTICS_SNAPSHOT_VERSION = 1
# A new build round starts this long after the last one started.
LOGISTICS_SNAPSHOT_TICKS = 600
# One publisher step runs outpost tasks while fewer ticks than this have passed (at least one task).
LOGISTICS_SLICE_TICKS = 100
# Record age (reader tick - "tick") up to which a record is FRESH.
LOGISTICS_FRESH_TICKS = 3000
# Up to this age a record is STALE; older, MISSING.
LOGISTICS_MAX_STALE_TICKS = REQUEST_STALE_TICKS

__all__ = [
    "FRESH",
    "LOGISTICS_FRESH_TICKS",
    "LOGISTICS_MAX_STALE_TICKS",
    "LOGISTICS_SLICE_TICKS",
    "LOGISTICS_SNAPSHOT_KEY",
    "LOGISTICS_SNAPSHOT_TICKS",
    "LOGISTICS_SNAPSHOT_VERSION",
    "MISSING",
    "PUBLISHER",
    "STALE",
    "SnapshotPublisher",
    "TierView",
    "build_entry",
    "publish_snapshot",
    "read_snapshot",
    "view",
]


_ENTRY_FIELDS = ("deficits", "free", "flying", "taken")


def _bands_out(bands):
    """{str(band): {item_id: units}} of the non-empty bands, for the archive."""
    return {str(band): dict(items) for band, items in bands.items() if items}


def build_entry(outpost: "OutpostRef", reads, item_ids):
    """One outpost's record entry (see the header) from `reads` (PlanReads). `item_ids` = the items to record free stock for."""
    outpost_id = getattr(outpost, "id", None)
    deficits = outpost_tier_deficits(outpost, reads.tick, live=True, reads=reads)
    free = outpost_tier_free(outpost, item_ids, None, reads.tick, loader=LOADER_DRONE, reads=reads)
    return {
        "deficits": _bands_out(deficits),
        "free": _bands_out(free),
        "flying": dict(reads.in_flight(outpost_id)),
        "taken": dict(reads.reserved_from(outpost_id)),
    }


def publish_snapshot(entries: dict, tick: int):
    """Stores the record `entries` ({outpost_id: build_entry()}) stamped `tick`. Outposts with nothing in any
    field and ids that are not str (not JSON-safe keys) are left out. True when stored; False without a clock."""
    if not tick:
        return False  # no clock: nothing can judge its age
    outposts = {outpost_id: entry for outpost_id, entry in entries.items() if isinstance(outpost_id, str) and isinstance(entry, dict) and any(entry.get(field) for field in _ENTRY_FIELDS)}
    return bool(archive.set(LOGISTICS_SNAPSHOT_KEY, {"v": LOGISTICS_SNAPSHOT_VERSION, "tick": int(tick), "outposts": outposts}))


def read_snapshot(now=None):
    """(record, state): the stored record and FRESH (age <= LOGISTICS_FRESH_TICKS), STALE (older, up to
    LOGISTICS_MAX_STALE_TICKS) or MISSING (none, another version, too old or no clock; record is then None)."""
    now = now_tick("logistics_snapshot.read_snapshot") if now is None else now
    record = archive.get(LOGISTICS_SNAPSHOT_KEY, None)
    if not now or not isinstance(record, dict) or record.get("v") != LOGISTICS_SNAPSHOT_VERSION:
        return None, MISSING
    tick = record.get("tick")
    if not isinstance(tick, (int, float)) or not isinstance(record.get("outposts"), dict):
        return None, MISSING
    age = now - tick
    if age < 0:
        return None, MISSING  # stamped ahead of the clock: not a record this clock wrote
    if age <= LOGISTICS_FRESH_TICKS:
        return record, FRESH
    if age <= LOGISTICS_MAX_STALE_TICKS:
        return record, STALE
    return None, MISSING


def _bands_in(stored):
    """{int band: {item_id: int units}} from an archive {str band: {item_id: units}}; junk entries skipped."""
    bands = {}
    if not isinstance(stored, dict):
        return bands
    for band, items in stored.items():
        if not isinstance(items, dict):
            continue
        try:
            key = int(band)
        except (TypeError, ValueError):
            continue
        bands[key] = {item_id: int(units) for item_id, units in items.items() if isinstance(units, (int, float))}
    return bands


def _units_in(stored):
    """{item_id: int units} from an archive units dict; junk skipped."""
    if not isinstance(stored, dict):
        return {}
    return {item_id: int(units) for item_id, units in stored.items() if isinstance(units, (int, float))}


def _cut_deficits(bands, recorded, live):
    """`bands` less the units `live` in-flight gained over `recorded`, taken from the top band down; zeros dropped."""
    for item_id, units in live.items():
        extra = units - recorded.get(item_id, 0)
        for band in TIERS:
            if extra <= 0:
                break
            have = bands.get(band, {}).get(item_id, 0)
            if have > 0:
                cut = min(have, extra)
                bands[band][item_id] = have - cut
                extra -= cut
    return {band: {i: u for i, u in items.items() if u > 0} for band, items in bands.items() if any(u > 0 for u in items.values())}


def _cut_free(bands, recorded, live):
    """`bands` less the units `live` reservations gained over `recorded`, from every band; non-positive dropped."""
    extras = {item_id: units - recorded.get(item_id, 0) for item_id, units in live.items()}
    extras = {item_id: extra for item_id, extra in extras.items() if extra > 0}
    cut = {}
    for band, items in bands.items():
        left = {i: u - extras.get(i, 0) for i, u in items.items()}
        cut[band] = {i: u for i, u in left.items() if u > 0}
    return cut


class TierView:
    """A snapshot record read for one planning pass: deficits(), free() and rivals() as the live
    outpost_tier_deficits() / outpost_tier_free() / fair_rivals_index() would answer, corrected for the
    pickups `reads` (PlanReads) holds now. `exclude_vehicle` applies to the source side only (its own
    reservations are left out of free()); destination in-flight counts every vehicle, as
    PlanReads.in_flight() does. Built per plan, like PlanReads: each outpost's entry is parsed and
    corrected once, against the pickups `reads` held at first use, so a long-lived view goes stale.
    Answers are fresh dicts."""

    def __init__(self, record, reads, exclude_vehicle=None):
        outposts = record.get("outposts") if isinstance(record, dict) else None
        self._outposts = outposts if isinstance(outposts, dict) else {}
        self._reads = reads
        self._exclude = exclude_vehicle
        self._deficits = {}
        self._free = {}

    def _entry(self, outpost_id):
        entry = self._outposts.get(outpost_id)
        return entry if isinstance(entry, dict) else {}

    def _deficits_of(self, outpost_id):
        bands = self._deficits.get(outpost_id)
        if bands is None:
            entry = self._entry(outpost_id)
            live = self._reads.in_flight(outpost_id)
            bands = _cut_deficits(_bands_in(entry.get("deficits")), _units_in(entry.get("flying")), live)
            self._deficits[outpost_id] = bands
        return bands

    def _free_of(self, outpost_id):
        bands = self._free.get(outpost_id)
        if bands is None:
            entry = self._entry(outpost_id)
            live = self._reads.reserved_from(outpost_id, self._exclude)
            bands = _cut_free(_bands_in(entry.get("free")), _units_in(entry.get("taken")), live)
            self._free[outpost_id] = bands
        return bands

    def deficits(self, outpost_id):
        """{band: {item_id: units}} still missing at `outpost_id`; bands and items with a deficit only."""
        return {band: dict(items) for band, items in self._deficits_of(outpost_id).items()}

    def free(self, outpost_id, item_ids, tiers=TIERS):
        """{band: {item_id: units}} `outpost_id` can give per band in `tiers` for `item_ids`; every TIERS key present."""
        bands = self._free_of(outpost_id)
        free = {tier: {} for tier in TIERS}
        for tier in tiers:
            items = bands.get(tier)
            if items:
                free[tier] = {item_id: items[item_id] for item_id in item_ids if item_id in items}
        return free

    def rivals(self, item_ids):
        """{item_id: [(outpost_id, {band: units})]}: fair_rivals_index() shape, FAIR_BANDS only, record order,
        from every outpost in the record with a FAIR_BANDS deficit for one of `item_ids`."""
        rivals = {}
        for outpost_id in self._outposts:
            deficits = self._deficits_of(outpost_id)
            for item_id in item_ids:
                bands = {band: deficits[band][item_id] for band in FAIR_BANDS if deficits.get(band, {}).get(item_id, 0) > 0}
                if bands:
                    rivals.setdefault(item_id, []).append((outpost_id, bands))
        return rivals


def view(reads, now=None, allow_stale=False, exclude_vehicle=None):
    """A TierView over the stored record when it is FRESH (or STALE with `allow_stale`), else None."""
    record, state = read_snapshot(now)
    if state == FRESH or (allow_stale and state == STALE):
        return TierView(record, reads, exclude_vehicle)
    return None


class SnapshotPublisher:
    """Builds the record in sliced rounds, one task (build_entry) per outpost. A round starts once
    LOGISTICS_SNAPSHOT_TICKS have passed since the last one started; each step() runs tasks until
    LOGISTICS_SLICE_TICKS have passed since the call began (at least one) and the round publishes
    when its last task is done, stamped with the tick it started. Orchestrator only. The tasks are
    not atomic: outpost_tier_free() scans through stock_scan, which batches its own reads."""

    def __init__(self):
        self.last_start_tick = None  # tick the last round started (None: never)
        self._reset()

    def _reset(self):
        self.pending = []  # outposts the round in progress still has to build
        self.entries = {}  # {outpost_id: build_entry()} of the round in progress
        self.reads = None  # the round's PlanReads
        self.item_ids = []  # the items the round records free stock for
        self.started_tick = 0  # tick the round in progress began (the record's stamp)
        self.active = False

    def due(self, now):
        """True when no round ever started or the interval since the last start passed (a clock gone back counts)."""
        return self.last_start_tick is None or not 0 <= now - self.last_start_tick < LOGISTICS_SNAPSHOT_TICKS

    def _start(self, now):
        """Begins a round at `now`. False (nothing started, retried after the interval) on an error."""
        self.last_start_tick = now
        try:
            network = get_component("outpost_network")
            outposts = list(network.outposts()) if network else []
            reads = PlanReads(now)
            item_ids = sorted({item_id for items in reads.requests.values() for item_id in items})
        except Exception as error:
            swallowed("logistics_snapshot.SnapshotPublisher._start", error)
            return False
        self._reset()
        self.pending = outposts
        self.reads = reads
        self.item_ids = item_ids
        self.started_tick = now
        self.active = True
        return True

    def _run_next(self):
        """Builds the next outpost's entry; an error leaves that outpost out of the record."""
        outpost = self.pending.pop(0)
        try:
            self.entries[outpost.id] = build_entry(outpost, self.reads, self.item_ids)
        except Exception as error:
            swallowed("logistics_snapshot.SnapshotPublisher._run_next", error)

    def step(self, now):
        """One call of work: starts a round when due, runs tasks for up to LOGISTICS_SLICE_TICKS,
        publishes when every task is done. True when the record was published this call."""
        if not now:
            return False
        if not self.active:
            if not self.due(now) or not self._start(now):
                return False
        while self.pending:  # at least one task per call, more while the tick budget lasts
            self._run_next()
            if now_tick() - now >= LOGISTICS_SLICE_TICKS:
                break
        if self.pending:
            return False
        published = publish_snapshot(self.entries, self.started_tick)
        self._reset()
        return published


PUBLISHER = SnapshotPublisher()
