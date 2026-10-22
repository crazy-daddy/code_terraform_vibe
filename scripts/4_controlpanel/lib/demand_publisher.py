# The demand publisher: computes the production demand picture (network and
# per-site Fabricator targets, Smelter demands) and publishes it as the shared
# demand record (lib/production_demand_record.py). The orchestrator's
# publish_demand_if_due() calls step() each loop; step() does nothing while
# demand_signature() is unchanged and the record is younger than
# DEMAND_BACKSTOP_TICKS, else it refreshes the record in tasks, each one
# run_atomic() call, as many per call as fit DEMAND_SLICE_TICKS. site_supply's
# publish_site_requests() already holds a SourceCache with most of that
# memoized and publishes through publish_from_cache() in one call.
# After a publish, the parked Fabricators and Smelters whose part of the signature rose
# are woken (wake_risen()): a writer's own wake comes before the record carries its
# change, so a machine woken then reads the old record, finds nothing and parks again.
#
# Tasks and atomic calls (lib/atomic.py): a refresh first prefetches, outside any
# atomic call, every read that writes or runs its own atomic calls (machine
# holdings, every outpost's stock scan, the manual-orders and ingot-target seeds).
# The tasks after it are reads plus Python only, so each could run as one
# run_atomic() call (ATOMIC_TASKS). That is off: on the mid-late sample save a
# task costs up to ~150k steps (one site's Fabricator part), network targets
# ~80k, finish ~25k, a site's Smelter need ~19k, an ingot batch ~4k, against the
# 10,000-step callback cap (the synthetic worlds of `devtools/perf/step_profile.py
# demand_refresh` understate this 10-300x). With the flag off each task logs its
# tick cost; ticks x the census allowance sizes it on a real save.
# A task that raises (a forbidden call inside the callback included) is
# skipped: that site computes its own targets until the next record.
from archive import archive
from atomic import run_atomic
from game_clock import now_tick
from parking_client import wake_on_rise
from priority import ladder_max
from production_cascade import blueprint_demand_items, compute_recipe_depths, fabricator_target_ladders
from production_core import discover_fabricator_ids, discover_smelter_ids, log
from production_demand import fab_site_ingot_targets, get_smelter_demands, site_ingot_ladders, site_smelter_demands
from production_demand_record import demand_signature, new_record, publish_record
from production_orders import get_manual_orders
from production_sites import SITE_PLAN_KEY, _compute_site_fabricator_targets, fab_site_counts, outpost_by_site_id
from production_source import SourceCache
from swallow import swallowed

# An unchanged signature still republishes this often (computed targets shrink as stock
# arrives; readers net their own changes meanwhile, and the storage pass publishes for free).
DEMAND_BACKSTOP_TICKS = 1800
# One step() keeps running tasks while fewer ticks than this have passed since the call began:
# a whole refresh normally fits one call, so the record is published before it ages; a slow
# refresh spills into the next between_steps() call.
DEMAND_SLICE_TICKS = 400
# Run the prefetch holdings and the tasks inside run_atomic(). Off: the headless run on the
# mid-late sample save crashed the orchestrator on the 10,000-step cap (2026-10-12): the
# synthetic worlds that sized the tasks are smaller than a real save. Turn on only after
# sizing the tasks on a real save.
ATOMIC_TASKS = False
# Smelter outputs per ingot-buffer task: up to ~960 opcodes each (the first batch of a site
# builds its stock totals), so a batch stays near 6k opcodes, under 4k steps.
INGOT_CHUNK_ITEMS = 6


def _run(fn, *args):
    """fn(*args), as one run_atomic() call when ATOMIC_TASKS is on."""
    return run_atomic(fn, *args) if ATOMIC_TASKS else fn(*args)


def prefetch(cache):
    """Every read of a refresh that must not run inside an atomic call, done on `cache`:
    the archive seeds (get_manual_orders(), ingot_stock_levels() through
    fab_site_ingot_targets()), the machine holdings and every outpost's stock scan
    (stock_scan.scan() runs its own atomic batches). Returns ({site_id: OutpostRef} of every
    outpost, {site_id: fab_site_ingot_targets()} of every outpost with a Fabricator)."""
    get_manual_orders()
    # Machine reads plus Python only (~2.3k opcodes each on the large synthetic world).
    _run(cache.fabricator_holdings)
    _run(cache.smelter_holdings)
    outposts = {}
    ingot_targets = {}
    levels = None  # fab_site_ingot_targets() is the same at every outpost with a Fabricator: read once
    for outpost in cache.outposts():
        site_id = getattr(outpost, "id", None)
        if site_id is None:
            continue
        outposts[site_id] = outpost
        cache.scan(outpost)
        if discover_fabricator_ids(outpost):
            if levels is None:
                levels = fab_site_ingot_targets(outpost, cache)
            ingot_targets[site_id] = levels
    cache.scan()
    return outposts, ingot_targets


class Refresh:
    """One refresh: the tasks still to run and what they produced."""

    def __init__(self, cache, prefetched):
        self.cache = cache
        self.outposts, self.ingot_targets = prefetched
        self.fab_sites = set(fab_site_counts(cache))
        self.smelting = {site_id for site_id, outpost in self.outposts.items() if discover_smelter_ids(outpost)}
        self.network = {}
        self.sites = {}  # {site_id: (targets, ship, have)}
        self.smelter_demands = {}  # {site_id: {item_id: ladder}}: the need, then the ingot buffer merged in
        self.smelter_have = {}  # {site_id: {item_id: held_stock()}}
        self.finished = None  # (smelter network demands, depths, blueprint cascade)
        self.skipped = 0
        outputs = sorted({getattr(r, "output_item", None) for r in cache.smelter_recipes()} - {None})
        batches = [tuple(outputs[i : i + INGOT_CHUNK_ITEMS]) for i in range(0, len(outputs), INGOT_CHUNK_ITEMS)]
        # Taken from the end: network first, then per site the Fabricator part, the Smelter need
        # and the ingot buffer in item batches, then finish.
        tasks: list[tuple[str, str | None, tuple | None]] = [("network", None, None)]
        for site_id in sorted(self.fab_sites | self.smelting):
            if site_id in self.fab_sites:
                tasks.append(("fab", site_id, None))
            if site_id in self.smelting:
                tasks.append(("need", site_id, None))
                tasks.extend([("ingot", site_id, batch) for batch in batches])
        tasks.append(("finish", None, None))
        self.pending = list(reversed(tasks))

    @property
    def smelter_sites(self):
        """{site_id: (demands, have)} of the Smelter sites done so far."""
        return {site_id: (demands, self.smelter_have.get(site_id, {})) for site_id, demands in self.smelter_demands.items()}

    def run_next(self):
        """Runs the next task as one atomic call; a failing task is skipped and logged. Without
        ATOMIC_TASKS each task logs its tick cost (debug): ticks x the census allowance
        (`scripts running` line) estimates its steps, which sizes the tasks on a real save."""
        kind, site_id, items = self.pending.pop()
        start = 0 if ATOMIC_TASKS else now_tick()
        try:
            _run(self._task, kind, site_id, items)
        except Exception as error:
            self.skipped += 1
            swallowed(f"demand_publisher.Refresh.{kind}({site_id})", error)
        if not ATOMIC_TASKS:
            log.debug(f"demand task {kind} {site_id or '-'} items={len(items or ())}: {now_tick() - start} ticks")

    def _task(self, kind, site_id, items):
        cache = self.cache
        if kind == "network":
            self.network = fabricator_target_ladders(cache)
        elif kind == "fab":
            outpost = self.outposts.get(site_id) or outpost_by_site_id(site_id)
            targets = cache._site_targets.get(site_id) if site_id in cache._site_ship_plan else None
            if targets is None:
                targets = _compute_site_fabricator_targets(site_id, cache)
            self.sites[site_id] = (targets, cache._site_ship_plan.get(site_id, {}), {item_id: cache.fab_have(item_id, outpost) for item_id in targets})
        elif kind == "need":
            self.smelter_demands[site_id] = site_smelter_demands(self.outposts[site_id], cache)
        elif kind == "ingot":
            outpost = self.outposts[site_id]
            demands = self.smelter_demands.setdefault(site_id, {})
            for item_id, levels in site_ingot_ladders(outpost, cache, self.ingot_targets.get(site_id, {}), items).items():
                demands[item_id] = ladder_max(demands.get(item_id, []), levels)
            have = self.smelter_have.setdefault(site_id, {})
            for item_id in items:
                have[item_id] = cache.held_stock(item_id, outpost)
        elif kind == "finish":
            self.finished = (get_smelter_demands(cache), compute_recipe_depths(cache), blueprint_demand_items(cache))

    def record(self):
        """The record body (new_record()), None when the finish task failed."""
        if self.finished is None:
            return None
        smelter_network, depths, blueprint = self.finished
        return new_record(archive.get(SITE_PLAN_KEY, {}) or {}, self.network, self.sites, smelter_network, self.smelter_sites, depths, blueprint)


class DemandPublisher:
    def __init__(self):
        self.signature = None  # demand_signature() of the last published record
        self.last_publish_tick = None  # stamp of the last publish (None: never)
        self._reset()

    def _reset(self):
        self.refresh = None  # Refresh in progress (None: idle)
        self.refresh_signature = None  # the signature the refresh in progress is for
        self.started_tick = 0  # tick the refresh in progress began (the record's stamp)

    @property
    def cache(self):
        """SourceCache of the refresh in progress, None when idle."""
        return self.refresh.cache if self.refresh is not None else None

    def due(self, signature, now):
        """True when `signature` differs from the published one or the backstop passed."""
        return signature != self.signature or self.last_publish_tick is None or now - self.last_publish_tick >= DEMAND_BACKSTOP_TICKS

    def step(self, now, dock_plan):
        """One call of work: starts a refresh when due, runs tasks for up to DEMAND_SLICE_TICKS,
        publishes when every task is done. True when a record was published this call."""
        if self.refresh is None:
            signature = demand_signature(dock_plan)
            if not self.due(signature, now):
                return False
            if not self._start(now, signature):
                return False
        refresh = self.refresh
        if refresh is None:
            return False
        while refresh.pending:  # at least one task per call, more while the tick budget lasts
            refresh.run_next()
            if now_tick() - now >= DEMAND_SLICE_TICKS:
                break
        if refresh.pending:
            return False
        return self._finish()

    def publish_from_cache(self, cache, now, dock_plan=None):
        """Computes and publishes the whole record from `cache` in one call when due (an
        unchanged signature inside the backstop publishes nothing), each task one atomic call.
        A refresh in progress is dropped: this record is newer. True when published."""
        signature = demand_signature(dock_plan)
        if not self.due(signature, now):
            return False
        self._reset()
        try:
            refresh = Refresh(cache, prefetch(cache))
        except Exception as error:
            swallowed("demand_publisher.DemandPublisher.publish_from_cache: prefetch", error)
            return False
        while refresh.pending:
            refresh.run_next()
        record = refresh.record()
        if record is None:
            return False
        return self._publish(record, min(now, cache.born or now), signature, len(refresh.sites) + len(refresh.smelter_sites), 0, refresh.skipped)

    def _start(self, now, signature):
        """Begins a refresh: the prefetch and the task list. False (nothing started) on an error."""
        try:
            cache = SourceCache()
            refresh = Refresh(cache, prefetch(cache))
        except Exception as error:
            swallowed("demand_publisher.DemandPublisher._start", error)
            return False
        self._reset()
        self.refresh = refresh
        self.refresh_signature = signature
        self.started_tick = now
        log.debug(f"demand record: refresh started ({len(refresh.pending)} task(s), prefetch {now_tick() - now} ticks)")
        return True

    def _finish(self):
        """Publishes the refresh in progress, stamped with the tick it began (its reads are that old), and ends it."""
        refresh = self.refresh
        if refresh is None:
            return False
        record = refresh.record()
        published = False
        if record is not None:
            published = self._publish(record, self.started_tick, self.refresh_signature, len(refresh.sites) + len(refresh.smelter_sites), now_tick() - self.started_tick, refresh.skipped)
        self._reset()
        return published

    def _publish(self, record, stamp, signature, parts, ticks, skipped=0):
        if not publish_record(record, stamp):
            return False  # a newer record won, or no clock: the next step sees the signature as unpublished
        previous, self.signature = self.signature, signature
        self.last_publish_tick = stamp
        note = f", {skipped} task(s) skipped" if skipped else ""
        log.print(f"[demand] Published demand record ({parts} part(s), {ticks} ticks{note})")
        if previous is not None:  # the first publish of a script has nothing to compare against
            wake_risen(previous, signature)
        return True


def wake_risen(before, after):
    """Wakes the parked machines of each kind whose entries in the demand signature
    ({(kind, source key, item): amount}, demand_signature()) rose from `before` to `after`."""
    kinds = {}
    for (kind, _source, item), amount in after.items():
        kinds.setdefault(kind, ({}, {}))[1][item] = amount
    for (kind, _source, item), amount in before.items():
        if kind in kinds:
            kinds[kind][0][item] = amount
    for kind, (old, new) in kinds.items():
        try:
            wake_on_rise((kind,), old, new, "demand record:")
        except Exception as error:
            swallowed("demand_publisher.wake_risen: wake_on_rise", error)


# The one instance of a script: the orchestrator's step() and site_supply's publish_from_cache()
# share it, so a publish from either keeps the other from recomputing at once.
PUBLISHER = DemandPublisher()
