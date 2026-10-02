# Power-line ledger upkeep for the infrastructure planner
# (autoplay/infra_planner_automation.py). Scripts cannot list completed power
# lines, so their tiles live in construction.power_tiles
# (lib/construction_plan.py, kept current by Pioneers as they finish jobs).
# This module fills it and repairs it:
#   - run_full(): one-off survey of every map tile, when the ledger has none;
#   - reprobe_dirty(): re-checks tiles a finished deconstruction or bridge
#     marked dirty;
#   - track_jobs(): marks the tiles of a vanished power job dirty when the
#     ledger did not gain them (the Pioneer did not record its completion).
#
# A probe is construction_blueprint.mark_deconstruct(x, y, layer="power") on a
# tile centre. The game matches every completed power piece touching the tile:
#   nothing_here      no piece (no side effect),
#   ambiguous_target  two or more pieces (line interior, junction; no job),
#   ok                one piece (line end) or a power bridge centre: a
#                     deconstruct job was queued and is cancelled at once,
#   already_queued    a deconstruct job exists already: still a power tile,
#   locked            no Constructor research: no survey possible.
# While probing, construction.hold keeps Pioneers off deconstruct jobs, so none
# starts on a probe's job before it is cancelled.

from archive import archive
from swallow import swallowed
from grid_geom import tile_key, tile_xy
from construction_plan import POWER_TILES_KEY, HOLD_KEY, DECONSTRUCT_KIND, POWER_LINE_KIND
from construction_plan import clean_power_ledger, empty_power_ledger, power_rows_decode, power_rows_encode, mark_power_dirty

TILE_M = 10
MAP_MIN_TILE = -90           # world tile range on both axes (the game's 180 x 180 tile planet)
MAP_MAX_TILE = 89
SURVEY_CHUNK = 400           # probes between hold refreshes and console flushes
HOLD_BY = "infra_planner"
JOBS_KEY = "autoplay.power_jobs"   # {job_id: {"k": kind, "t": [[tx, ty], ...]}} open power jobs seen last pass

_POWER_STATUSES = ("ok", "ambiguous_target", "already_queued")


def _now_tick():
    try:
        clock = get_component("clock")
        return clock.tick() if clock else 0
    except Exception as error:
        swallowed("power_survey._now_tick: clock.tick", error)
        return 0


def _set_hold(tick):
    archive.set(HOLD_KEY, {"by": HOLD_BY, "tick": tick, "kinds": [DECONSTRUCT_KIND]})


def _clear_hold():
    archive.delete(HOLD_KEY)


def ledger():
    """The cleaned construction.power_tiles value."""
    return clean_power_ledger(archive.get(POWER_TILES_KEY, None))


def ledger_tiles():
    """Power tiles of the ledger as grid_geom.tile_key()s."""
    return {tile_key(tx, ty) for tx, ty in power_rows_decode(ledger()["rows"])}


class Prober:
    """mark_deconstruct probes with immediate cancel; remembers ids it could not cancel."""

    def __init__(self, blueprints):
        self.blueprints = blueprints
        self.leftover = []
        self.cancelled = 0
        self.locked = False

    def probe(self, tx, ty):
        """True (power piece on the tile), False (none) or None (unknown answer)."""
        try:
            result = self.blueprints.mark_deconstruct(tx * TILE_M + TILE_M / 2, ty * TILE_M + TILE_M / 2, "power")
        except Exception as error:
            swallowed("power_survey.Prober.probe: mark_deconstruct", error)
            return None
        status = getattr(result, "status", "")
        if status == "ok":
            for blueprint_id in list(getattr(result, "blueprint_ids", None) or []):
                self._cancel(blueprint_id)
        if status in _POWER_STATUSES:
            return True
        if status == "nothing_here":
            return False
        if status == "locked":
            self.locked = True
        return None

    def _cancel(self, blueprint_id):
        try:
            result = self.blueprints.cancel(blueprint_id)
        except Exception as error:
            swallowed("power_survey.Prober._cancel: cancel", error)
            result = None
        if getattr(result, "status", "") == "ok":
            self.cancelled += 1
        else:
            self.leftover.append(blueprint_id)

    def retry_leftover(self):
        """Cancels the probe jobs a first cancel missed; returns the ids still left."""
        pending = self.leftover
        self.leftover = []
        for blueprint_id in pending:
            self._cancel(blueprint_id)
        return self.leftover


def run_full(log):
    """
    One-off survey of every map tile into the ledger. Returns "done", "locked"
    (no Constructor research; ledger untouched) or "error" (no construction_blueprint).
    Lines Pioneers finish during the walk are kept (ledger rows added since the start).
    """
    blueprints = get_component("construction_blueprint")
    if blueprints is None:
        return "error"
    prober = Prober(blueprints)
    start_tick = _now_tick()
    rows_before = power_rows_decode(ledger()["rows"])
    found = set()
    probed = 0
    log.start(f"Power survey: probing {(MAP_MAX_TILE - MAP_MIN_TILE + 1) ** 2} tiles")
    outcome = "done"
    try:
        _set_hold(start_tick)
        for ty in range(MAP_MIN_TILE, MAP_MAX_TILE + 1):
            for tx in range(MAP_MIN_TILE, MAP_MAX_TILE + 1):
                if prober.probe(tx, ty):
                    found.add((tx, ty))
                probed += 1
                if prober.locked:
                    break
                if probed % SURVEY_CHUNK == 0:
                    _set_hold(_now_tick())
                    log.trace(f"Power survey: {probed} tiles, {len(found)} with power.")
                    log.flush()
            if prober.locked:
                outcome = "locked"
                break
        left = prober.retry_leftover()
        if left:
            log.level("warn").print(f"Power survey: {len(left)} probe job(s) could not be cancelled: {', '.join(left[:5])}")
    finally:
        _clear_hold()
    if outcome == "locked":
        log.end("locked: mark_deconstruct needs Constructor research; links use footprints only")
        return outcome

    def updater(current):
        merged = clean_power_ledger(current)
        added = power_rows_decode(merged["rows"]) - rows_before
        merged["rows"] = power_rows_encode(found | added)
        merged["surveyed"] = start_tick
        return merged

    archive.transaction(POWER_TILES_KEY, empty_power_ledger(), updater)
    log.end(f"{probed} tiles probed, {len(found)} with power, {prober.cancelled} probe job(s) cancelled")
    return outcome


def reprobe_dirty(log):
    """Re-probes the ledger's dirty tiles; returns how many were probed."""
    dirty = [(d[0], d[1]) for d in ledger()["dirty"]]
    if not dirty:
        return 0
    blueprints = get_component("construction_blueprint")
    if blueprints is None:
        return 0
    prober = Prober(blueprints)
    answers = {}
    try:
        _set_hold(_now_tick())
        for tx, ty in dirty:
            answers[(tx, ty)] = prober.probe(tx, ty)
        prober.retry_leftover()
    finally:
        _clear_hold()

    def updater(current):
        merged = clean_power_ledger(current)
        tiles = power_rows_decode(merged["rows"])
        for tile, has_power in answers.items():
            if has_power is True:
                tiles.add(tile)
            elif has_power is False:
                tiles.discard(tile)
        merged["rows"] = power_rows_encode(tiles)
        merged["dirty"] = [d for d in merged["dirty"] if (d[0], d[1]) not in answers]
        return merged

    archive.transaction(POWER_TILES_KEY, empty_power_ledger(), updater)
    gained = len([a for a in answers.values() if a is True])
    log.debug(f"Power ledger: re-probed {len(answers)} dirty tile(s), {gained} with power.")
    return len(answers)


def vanished_dirty(seen, open_jobs, known_tiles):
    """
    Tiles to re-probe for power jobs in `seen` ({job_id: {"k", "t"}}) that are no
    longer in `open_jobs`: a finished deconstruction always, a line piece whose
    tiles are not all in known_tiles ((tx, ty) set), a bridge always.
    """
    out = []
    for job_id, entry in seen.items():
        if job_id in open_jobs or not isinstance(entry, dict):
            continue
        tiles = [(t[0], t[1]) for t in entry.get("t") or [] if isinstance(t, list) and len(t) == 2]
        if entry.get("k") == POWER_LINE_KIND and all(tile in known_tiles for tile in tiles):
            continue
        out.extend(tiles)
    return out


def track_jobs(topo):
    """Updates autoplay.power_jobs from this pass's open power jobs and marks the tiles of vanished ones dirty; returns how many tiles."""
    if not topo.jobs_ok:
        return 0
    open_jobs = {}
    for row in topo.job_rows:
        if row["medium"] == "power":
            open_jobs[row["id"]] = {"k": row["kind"], "t": [list(tile_xy(tile)) for tile in row["tiles"]]}
    raw = archive.get(JOBS_KEY, {})
    seen = raw if isinstance(raw, dict) else {}
    dirty = vanished_dirty(seen, open_jobs, power_rows_decode(ledger()["rows"])) if seen else []
    if dirty:
        def updater(current):
            return mark_power_dirty(clean_power_ledger(current), dirty)

        archive.transaction(POWER_TILES_KEY, empty_power_ledger(), updater)
    if open_jobs != seen:
        archive.set(JOBS_KEY, open_jobs)
    return len(dirty)
