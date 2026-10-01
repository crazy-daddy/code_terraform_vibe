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


def scan_slice(jobs, pos, cargo, claims, me, tick, stale_ticks, failed):
    """
    [(ids, open_rows, matching)] for one slice of blueprint jobs:
    - ids: every job's id (for the finished-claim sweep),
    - open_rows: a row dict (job, id, coords, kind, item, count, progress)
      per job with an id, not in `failed` and free of a fresh peer claim,
    - matching: (dist from pos, id, row) for the open rows that are a
      deconstruction or whose materials are aboard per cargo {item: units};
      sorting it (plain tuple sort) gives nearest first.
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
        row = {
            "job": job,
            "id": job_id,
            "coords": coords,
            "kind": getattr(job, "kind", None),
            "item": item,
            "count": count,
            "progress": getattr(job, "progress", 0.0) or 0.0,
        }
        open_rows.append(row)
        if not item or count <= 0 or cargo.get(item, 0) >= count:
            if coords:
                dx = coords[0] - px
                dy = coords[1] - py
                dist = (dx * dx + dy * dy) ** 0.5
            else:
                dist = NO_COORDS_DIST
            matching.append((dist, job_id, row))
    return [(ids, open_rows, matching)]


def scan_jobs(jobs, pos, cargo, claims, me, tick, stale_ticks, failed):
    """scan_slice() over all jobs in JOB_CHUNK slices, one atomic call each; returns (ids, open_rows, matching nearest first)."""
    ids = []
    open_rows = []
    matching = []
    for slice_ids, slice_open, slice_matching in run_batched(scan_slice, jobs, JOB_CHUNK, pos, cargo, claims, me, tick, stale_ticks, failed):
        ids.extend(slice_ids)
        open_rows.extend(slice_open)
        matching.extend(slice_matching)
    matching.sort()
    return ids, open_rows, matching


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
