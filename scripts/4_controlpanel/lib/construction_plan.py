# Pure job-selection math for the Constructor Pioneer loop (lib/pioneer.py
# run_construction_loop()), safe to run through lib/atomic.py's run_atomic()
# (docs/cheatsheet/dev_workflow.md §1d-1): no logging, no game writes, only
# attribute reads on the blueprint job objects. A call handles one slice of
# jobs (the *_CHUNK constants below); the worst slice of each function is
# measured in tests/test_construction_plan.py against ATOMIC_STEP_BUDGET.

from atomic import run_atomic, run_batched

JOB_CHUNK = 16               # jobs per scan_slice() call (worst job ~235 operations)
TRIP_CHUNK = 12              # rows per station_trip_wh() call (worst row ~250 operations at 12 stations, +15 per station)
PROGRESS_CHUNK = 256         # jobs per find_progress() call (worst job ~12 operations)
ATOMIC_STEP_BUDGET = 4000    # worst-case interpreter operations allowed for one atomic call here
NO_COORDS_DIST = 1e18        # sort key for a job without readable coordinates (last)
PEER_BUILDER_ACTIVE_TICKS = 6000  # a same-home Constructor counts toward fair_share() while its fleet.status heartbeat is younger than this
PEER_INACTIVE_STATES = ("RECALLED", "DECOMMISSION_READY", "UPGRADE_HOLD", "AWAITING_MODULES")
PRIORITY_KEY = "construction.priority"  # archive {blueprint_id: int}; no entry = DEFAULT_PRIORITY, lower runs first
DEFAULT_PRIORITY = 0


def claim_key(job_id):
    """Shared claims dict key for a construction job (see PioneerController.construction_claim_key())."""
    return f"build_{job_id}"


def claim_free(claim, me, tick, stale_ticks):
    """True unless claim is a claim by another vehicle than `me` younger than stale_ticks (tick 0 = unknown clock, counts as fresh)."""
    if not claim or claim.get("vehicle") == me or claim.get("rover") == me:
        return True
    return not (tick == 0 or tick - claim.get("tick", 0) < stale_ticks)


def coords_of(pos):
    """(x, y) floats from a tuple/list, dict or Position object, None if unreadable (VehicleController.extract_coords())."""
    if pos is None:
        return None
    if isinstance(pos, (tuple, list)) and len(pos) >= 2:
        return (float(pos[0]), float(pos[1]))
    if isinstance(pos, dict) and "x" in pos and "y" in pos:
        return (float(pos["x"]), float(pos["y"]))
    x = getattr(pos, "x", None)
    y = getattr(pos, "y", None)
    if x is not None and y is not None:
        return (float(x), float(y))
    return None


def clean_priorities(raw):
    """{blueprint_id: int} from the raw PRIORITY_KEY archive value; non-int (or bool) values and a non-dict value are dropped."""
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if isinstance(v, int) and not isinstance(v, bool)}


def scan_slice(jobs, pos, cargo, claims, me, tick, stale_ticks, failed, priorities):
    """
    [(ids, open_rows, matching)] for one slice of blueprint jobs:
    - ids: every job's id (for the finished-claim sweep),
    - open_rows: a row dict (job, id, coords, kind, item, count, progress,
      prio) per job with an id, not in `failed` and free of a fresh peer
      claim; prio from priorities {id: int}, DEFAULT_PRIORITY if absent,
    - matching: (prio, dist from pos, id, row) for the open rows that are a
      deconstruction or whose materials are aboard per cargo {item: units};
      sorting it (plain tuple sort) gives lowest prio, then nearest first.
    """
    ids = []
    open_rows = []
    matching = []
    px, py = pos
    for job in jobs:
        job_id = getattr(job, "id", None) or getattr(job, "blueprint_id", None)
        ids.append(job_id)
        if not job_id or job_id in failed or not claim_free(claims.get(claim_key(job_id)), me, tick, stale_ticks):
            continue
        coords = coords_of(getattr(job, "position", None))
        item = getattr(job, "required_item", None)
        count = getattr(job, "required_count", 0) or 0
        prio = priorities.get(job_id, DEFAULT_PRIORITY)
        row = {
            "job": job,
            "id": job_id,
            "coords": coords,
            "kind": getattr(job, "kind", None),
            "item": item,
            "count": count,
            "progress": getattr(job, "progress", 0.0) or 0.0,
            "prio": prio,
        }
        open_rows.append(row)
        if not item or count <= 0 or cargo.get(item, 0) >= count:
            if coords:
                dx = coords[0] - px
                dy = coords[1] - py
                dist = (dx * dx + dy * dy) ** 0.5
            else:
                dist = NO_COORDS_DIST
            matching.append((prio, dist, job_id, row))
    return [(ids, open_rows, matching)]


def scan_jobs(jobs, pos, cargo, claims, me, tick, stale_ticks, failed, priorities):
    """scan_slice() over all jobs in JOB_CHUNK slices, one atomic call each; returns (ids, open_rows, matching by prio, then nearest first)."""
    ids = []
    open_rows = []
    matching = []
    for slice_ids, slice_open, slice_matching in run_batched(scan_slice, jobs, JOB_CHUNK, pos, cargo, claims, me, tick, stale_ticks, failed, priorities):
        ids.extend(slice_ids)
        open_rows.extend(slice_open)
        matching.extend(slice_matching)
    matching.sort()
    return ids, open_rows, matching


def top_priority(rows):
    """Lowest prio among rows, DEFAULT_PRIORITY when rows is empty."""
    if not rows:
        return DEFAULT_PRIORITY
    return min([row["prio"] for row in rows])


def at_priority(rows, prio):
    """Rows whose prio equals prio."""
    return [row for row in rows if row["prio"] == prio]


def stale_priorities(priorities, live_ids):
    """Ids in priorities whose blueprint is not in live_ids (finished or cancelled)."""
    return [job_id for job_id in priorities if job_id not in live_ids]


def station_trip_wh(rows, stations, wh_per_meter, wh_per_progress, progress_per_trip, margin, reserve):
    """
    [(row, Wh)] for one slice of rows: a round trip from the row's nearest
    station (stations: non-empty list of (x, y)) at wh_per_meter, plus the
    row's remaining progress capped at progress_per_trip at wh_per_progress,
    times margin, plus reserve. Wh is None for a row without coordinates.
    """
    out = []
    for row in rows:
        coords = row["coords"]
        if not coords:
            out.append((row, None))
            continue
        x, y = coords
        best = min([(sx - x) * (sx - x) + (sy - y) * (sy - y) for sx, sy in stations])
        progress = min(max(0.0, 1.0 - row["progress"]), progress_per_trip)
        out.append((row, ((2.0 * best ** 0.5 * wh_per_meter) + progress * wh_per_progress) * margin + reserve))
    return out


def find_progress(jobs, blueprint_id):
    """[progress] of the first job in jobs whose id is blueprint_id, [] if none is."""
    for job in jobs:
        if getattr(job, "id", None) == blueprint_id:
            return [getattr(job, "progress", 0.0) or 0.0]
    return []


def job_progress(jobs, blueprint_id):
    """find_progress() over jobs in PROGRESS_CHUNK slices, one atomic call each, stopping at the first hit; None if absent."""
    jobs = list(jobs)
    for start in range(0, len(jobs), PROGRESS_CHUNK):
        found = run_atomic(find_progress, jobs[start:start + PROGRESS_CHUNK], blueprint_id)
        if found:
            return found[0]
    return None


def batch_count(rows, item_id, max_limit=None):
    """Sum of `count` over rows needing item_id, stopping at max_limit when given."""
    total = 0
    for row in rows:
        if row["item"] == item_id:
            total += max(0, row["count"])
            if max_limit is not None and total >= max_limit:
                return max_limit
    return total


def ids_needing(rows, item_id):
    """Ids of rows needing item_id."""
    return [row["id"] for row in rows if row["item"] == item_id]


def peer_builders(status, me, home, tick, active_ticks):
    """
    Names of other Constructor vehicles in status ({name: fleet.status
    telemetry}) with the same home whose telemetry is younger than
    active_ticks and not in PEER_INACTIVE_STATES (tick 0 = unknown clock,
    counts as fresh).
    """
    return sorted([
        name for name, entry in status.items()
        if name != me and isinstance(entry, dict)
        and entry.get("role") == "constructor" and entry.get("home") == home
        and entry.get("state") not in PEER_INACTIVE_STATES
        and (tick == 0 or tick - (entry.get("tick", 0) or 0) < active_ticks)
    ])


def fair_share(batch, stock, builders):
    """batch capped at stock split evenly (rounded up) across builders; batch unchanged for a lone builder."""
    if builders <= 1:
        return batch
    return min(batch, -(-max(0, stock) // builders))


# ---------------------------------------------------------------- power-line ledger
# Scripts cannot list completed power lines, so the tiles they cover are kept
# in one archive key, POWER_TILES_KEY:
#   {"surveyed": tick | None, "rows": {"<ty>": [[tx0, tx1], ...]}, "dirty": [[tx, ty], ...]}
# Tiles are world tile indices (floor(coord / POWER_TILE_M)); rows hold
# inclusive runs per tile row. "surveyed" is the tick of the last full map
# survey (autoplay/lib/power_survey.py), None when one is due. A Pioneer that
# finishes a job updates the ledger (note_power_job()): a power-line piece adds
# its two tiles; a deconstruction or a power bridge marks its tiles dirty (a
# removed piece may leave others on the tile; a bridge job has no axis), and
# whoever keeps the ledger re-probes dirty tiles.
POWER_TILES_KEY = "construction.power_tiles"
POWER_TILE_M = 10
POWER_DIRTY_MAX = 400        # dirty tiles kept; beyond this the ledger asks for a full survey instead
POWER_LINE_KIND = "power_line"
POWER_BRIDGE_KIND = "power_bridge"
DECONSTRUCT_KIND = "deconstruct"

# Jobs of a held kind are left alone by Pioneers while the hold is fresh:
#   HOLD_KEY = {"by": str, "tick": int, "kinds": [kind, ...]}
# A holder refreshes "tick" while it works and deletes the key when done; a
# stale hold (crashed holder) stops counting after HOLD_STALE_TICKS.
HOLD_KEY = "construction.hold"
HOLD_STALE_TICKS = 600


def held_kinds(raw, tick):
    """Job kinds a fresh HOLD_KEY value holds, else an empty set (tick 0 = unknown clock: fresh)."""
    if not isinstance(raw, dict):
        return set()
    kinds = raw.get("kinds")
    held_tick = raw.get("tick", 0)
    if not isinstance(kinds, list) or not isinstance(held_tick, int):
        return set()
    if tick and tick - held_tick >= HOLD_STALE_TICKS:
        return set()
    return {kind for kind in kinds if isinstance(kind, str)}


def _power_tile(coord):
    return int(coord // POWER_TILE_M)


def power_job_tiles(x, y):
    """
    (tx, ty) tiles of a job at world position (x, y): a line piece's midpoint
    sits on a tile edge (x on an edge = horizontal piece joining two tiles,
    y on an edge = vertical piece); any other position is the one tile it is in.
    """
    x_edge = x % POWER_TILE_M == 0
    y_edge = y % POWER_TILE_M == 0
    if x_edge and not y_edge:
        tx = _power_tile(x)
        return [(tx - 1, _power_tile(y)), (tx, _power_tile(y))]
    if y_edge and not x_edge:
        ty = _power_tile(y)
        return [(_power_tile(x), ty - 1), (_power_tile(x), ty)]
    return [(_power_tile(x), _power_tile(y))]


def power_rows_decode(rows):
    """Set of (tx, ty) from the ledger's "rows" value; malformed entries are skipped."""
    tiles = set()
    if not isinstance(rows, dict):
        return tiles
    for row_key, runs in rows.items():
        try:
            ty = int(row_key)
        except (TypeError, ValueError):
            continue
        for run in runs if isinstance(runs, list) else []:
            if isinstance(run, list) and len(run) == 2 and isinstance(run[0], int) and isinstance(run[1], int):
                tiles.update([(tx, ty) for tx in range(run[0], run[1] + 1)])
    return tiles


def power_rows_encode(tiles):
    """The ledger's "rows" value for a set of (tx, ty): inclusive runs per row."""
    by_row = {}
    for tx, ty in tiles:
        by_row.setdefault(ty, []).append(tx)
    rows = {}
    for ty, xs in by_row.items():
        xs.sort()
        runs = []
        for tx in xs:
            if runs and tx == runs[-1][1] + 1:
                runs[-1][1] = tx
            elif not runs or tx > runs[-1][1]:
                runs.append([tx, tx])
        rows[str(ty)] = runs
    return rows


def empty_power_ledger():
    return {"surveyed": None, "rows": {}, "dirty": []}


def clean_power_ledger(raw):
    """A well-formed ledger dict from the raw POWER_TILES_KEY value."""
    if not isinstance(raw, dict):
        return empty_power_ledger()
    surveyed = raw.get("surveyed")
    rows = raw.get("rows")
    dirty = raw.get("dirty")
    return {
        "surveyed": surveyed if isinstance(surveyed, int) and not isinstance(surveyed, bool) else None,
        "rows": rows if isinstance(rows, dict) else {},
        "dirty": [d for d in dirty if isinstance(d, list) and len(d) == 2] if isinstance(dirty, list) else [],
    }


def mark_power_dirty(ledger, tiles):
    """Adds (tx, ty) tiles to the ledger's dirty list; past POWER_DIRTY_MAX the ledger asks for a full survey. Returns the ledger."""
    known = {(d[0], d[1]) for d in ledger["dirty"]}
    for tile in tiles:
        if tile not in known:
            known.add(tile)
            ledger["dirty"].append([tile[0], tile[1]])
    if len(ledger["dirty"]) > POWER_DIRTY_MAX:
        ledger["surveyed"] = None
        ledger["dirty"] = []
    return ledger


def note_power_job(raw, kind, x, y):
    """The ledger after a finished job of `kind` at (x, y); unchanged for kinds that do not touch power lines."""
    ledger = clean_power_ledger(raw)
    if kind == POWER_LINE_KIND:
        tiles = power_rows_decode(ledger["rows"])
        tiles.update(power_job_tiles(x, y))
        ledger["rows"] = power_rows_encode(tiles)
    elif kind == POWER_BRIDGE_KIND:
        tx, ty = _power_tile(x), _power_tile(y)
        mark_power_dirty(ledger, [(tx, ty), (tx - 1, ty), (tx + 1, ty), (tx, ty - 1), (tx, ty + 1)])
    elif kind == DECONSTRUCT_KIND:
        mark_power_dirty(ledger, power_job_tiles(x, y))
    return ledger
