# The infrastructure planner's only writer of construction blueprints
# (autoplay/infra_planner_automation.py). Wraps construction_blueprint.plan_*, records
# what it queued in autoplay.planned and sets construction.priority for jobs
# that are not normal priority (no entry = construction_plan.DEFAULT_PRIORITY).
#
# Archive shapes (one shared dict per concern):
#   autoplay.planned = {blueprint_id: {"k": kind, "f": fluid | "power" | None,
#                       "p": prio, "seg": [x1, y1, x2, y2] | None, "site": id | None}}
# Entries leave autoplay.planned once their job is no longer pending, active
# or paused (prune_planned()). Pioneers prune construction.priority themselves.

from archive import archive
from swallow import swallowed
from construction_plan import PRIORITY_KEY, DEFAULT_PRIORITY
from grid_geom import tile_centre, run_tiles, bridge_tiles
from infra_topology import NETWORKS_KEY
from production import construction_site_id
from storage import takeable_stock

PLANNED_KEY = "autoplay.planned"


def _blueprints():
    return get_component("construction_blueprint")


def _construction_outpost():
    """OutpostRef where Constructor Pioneers load (production.construction_site_id()); None = home."""
    network = get_component("outpost_network")
    if network is None:
        return None
    site_id = construction_site_id()
    try:
        for ref in network.outposts() or []:
            if ref.id == site_id:
                return ref
    except Exception as error:
        swallowed("blueprint_queue._construction_outpost: outpost_network.outposts", error)
    return None


def stock(item_id):
    """Units of item_id a Constructor Pioneer can load at its home (storage.takeable_stock()), 0 when unreadable."""
    try:
        return int(takeable_stock(item_id, outpost=_construction_outpost()) or 0)
    except Exception as error:
        swallowed("blueprint_queue.stock: takeable_stock", error)
        return 0


def _record(ids, entry, prio):
    def planned_updater(planned):
        if not isinstance(planned, dict):
            planned = {}
        for blueprint_id in ids:
            planned[blueprint_id] = entry
        return planned

    archive.transaction(PLANNED_KEY, {}, planned_updater)
    if prio == DEFAULT_PRIORITY:
        return

    def priority_updater(priorities):
        if not isinstance(priorities, dict):
            priorities = {}
        for blueprint_id in ids:
            priorities[blueprint_id] = prio
        return priorities

    archive.transaction(PRIORITY_KEY, {}, priority_updater)


def cancel(ids):
    """Cancels the given blueprints and drops them from autoplay.planned; returns how many cancelled."""
    blueprints = _blueprints()
    if blueprints is None or not ids:
        return 0
    cancelled = []
    for blueprint_id in ids:
        try:
            result = blueprints.cancel(blueprint_id)
        except Exception as error:
            swallowed("blueprint_queue.cancel: construction_blueprint.cancel", error)
            continue
        if getattr(result, "status", "") == "ok":
            cancelled.append(blueprint_id)
    if cancelled:
        def updater(planned):
            if not isinstance(planned, dict):
                return {}
            for blueprint_id in cancelled:
                planned.pop(blueprint_id, None)
            return planned

        archive.transaction(PLANNED_KEY, {}, updater)
        if any(blueprint_id in (archive.get(PRIORITY_KEY, {}) or {}) for blueprint_id in cancelled):
            archive.transaction(PRIORITY_KEY, {}, updater)
    return len(cancelled)


def _plan_power_leg(blueprints: "ConstructionBlueprint", leg):
    """(status, ids, message) of one plan_power_line() call."""
    try:
        result = blueprints.plan_power_line(leg[0], leg[1], leg[2], leg[3])
    except Exception as error:
        swallowed("blueprint_queue._plan_power_leg: plan_power_line", error)
        return ("error", [], str(error))
    status = getattr(result, "status", "error")
    ids = list(getattr(result, "blueprint_ids", None) or []) if status == "ok" else []
    return (status, ids, getattr(result, "message", ""))


def queue_power_route(legs, prio):
    """
    Plans a power route of one or more legs [x1, y1, x2, y2] (world coordinates
    on tile centres). All or nothing: when a leg is rejected, the legs already
    queued are cancelled. Returns (status, ids, message); status "ok" when
    every leg was queued (ids may be empty when every piece already existed).
    """
    blueprints = _blueprints()
    if blueprints is None:
        return ("no_component", [], "construction_blueprint missing")
    ids = []
    for leg in legs:
        status, leg_ids, message = _plan_power_leg(blueprints, leg)
        if status != "ok":
            cancel(ids)
            return (status, [], message)
        ids.extend(leg_ids)
        if leg_ids:
            _record(leg_ids, {"k": "power_line", "f": "power", "p": prio, "seg": list(leg), "site": None}, prio)
    return ("ok", ids, "")


def _plan_call(label, call, *args):
    """(status, ids, message) of one plan_* call; "already_exists" is ok with no ids."""
    try:
        result = call(*args)
    except Exception as error:
        swallowed(f"blueprint_queue._plan_call: {label}", error)
        return ("error", [], str(error))
    status = getattr(result, "status", "error")
    if status == "already_exists":
        return ("ok", [], "")
    ids = list(getattr(result, "blueprint_ids", None) or []) if status == "ok" else []
    return (status, ids, getattr(result, "message", ""))


def reusable_pieces(tiles, held):
    """Pieces of a run (consecutive tile pairs) whose two tiles both carry the fluid already: at most that many may exist."""
    return len([1 for i in range(len(tiles) - 1) if tiles[i] in held and tiles[i + 1] in held])


def step_segment(step):
    """[x1, y1, x2, y2] world coordinates (tile centres) of a path_plan() step: the run, or the bridge's span."""
    if step[0] == "run":
        tiles = [step[1], step[2]]
    else:
        span = bridge_tiles(step[1], step[2])
        tiles = [span[0], span[2]]
    ax, ay = tile_centre(tiles[0])
    bx, by = tile_centre(tiles[1])
    return [ax, ay, bx, by]


def network_runs(steps):
    """autoplay.networks entries for a route: each run, and each bridge's two end tiles as one-tile runs (the middle belongs to the line crossed)."""
    runs = []
    for step in steps:
        seg = step_segment(step)
        if step[0] == "run":
            runs.append(seg)
        else:
            runs.append([seg[0], seg[1], seg[0], seg[1]])
            runs.append([seg[2], seg[3], seg[2], seg[3]])
    return runs


def _note_network(fluid, runs):
    def updater(networks):
        if not isinstance(networks, dict):
            networks = {}
        kept = networks.get(fluid, [])
        if not isinstance(kept, list):
            kept = []
        for run in runs:
            if run not in kept:
                kept.append(run)
        networks[fluid] = kept
        return networks

    archive.transaction(NETWORKS_KEY, {}, updater)


def queue_pipe_route(fluid, steps, prio, held):
    """
    Plans a fluid route from path_plan() steps: one plan_pipe() per straight
    run, one plan_bridge() per bridge. All or nothing: on a rejection, or when
    a run creates fewer jobs than its pieces minus reusable_pieces() (the game
    stopped short), every job of the route is cancelled. held = tiles already
    carrying the fluid. plan_pipe() takes the fluid id but keeps only the
    medium: the route's fluid lives in autoplay.networks until a connect()
    through it sets the pipes' contents. Returns (status, ids, message).
    """
    blueprints = _blueprints()
    if blueprints is None:
        return ("no_component", [], "construction_blueprint missing")
    ids = []
    for step in steps:
        seg = step_segment(step)
        if step[0] == "run":
            status, step_ids, message = _plan_call("plan_pipe", blueprints.plan_pipe, fluid, seg[0], seg[1], seg[2], seg[3])
            tiles = run_tiles(step[1], step[2])
            floor = len(tiles) - 1 - reusable_pieces(tiles, held)
            if status == "ok" and len(step_ids) < floor:
                status = "short"
                message = f"{len(step_ids)} of {floor} new pieces for {seg}"
                ids.extend(step_ids)
            kind = "pipe"
        else:
            status, step_ids, message = _plan_call("plan_bridge", blueprints.plan_bridge, fluid, seg[0] / 2 + seg[2] / 2, seg[1] / 2 + seg[3] / 2, step[2])
            kind = "bridge"
        if status != "ok":
            cancel(ids)
            return (status, [], message)
        ids.extend(step_ids)
        if step_ids:
            _record(step_ids, {"k": kind, "f": fluid, "p": prio, "seg": seg, "site": None}, prio)
    _note_network(fluid, network_runs(steps))
    return ("ok", ids, "")


def queue_structure(kind, x, y, prio, site_id, fluid=None):
    """
    Plans one extractor (plan_structure(kind, x, y)) on a surveyed site and
    records it in autoplay.planned with its site id. Returns (status, ids, message).
    """
    blueprints = _blueprints()
    if blueprints is None:
        return ("no_component", [], "construction_blueprint missing")
    try:
        result = blueprints.plan_structure(kind, x, y)
    except Exception as error:
        swallowed("blueprint_queue.queue_structure: plan_structure", error)
        return ("error", [], str(error))
    status = getattr(result, "status", "error")
    ids = list(getattr(result, "blueprint_ids", None) or []) if status == "ok" else []
    if ids:
        _record(ids, {"k": kind, "f": fluid, "p": prio, "seg": [x, y, x, y], "site": site_id}, prio)
    return (status, ids, getattr(result, "message", ""))


def job_need(blueprint_id):
    """(required_item, required_count) of an open job, (None, 0) when not found or unreadable."""
    blueprints = _blueprints()
    if blueprints is None:
        return (None, 0)
    try:
        for job in blueprints.pending_constructions() or []:
            if job.id == blueprint_id:
                return (job.required_item, int(job.required_count or 0))
    except Exception as error:
        swallowed("blueprint_queue.job_need: pending_constructions", error)
    return (None, 0)


def open_planned(kinds=None, prio=None):
    """autoplay.planned entries (blueprint id -> entry) of the given kinds and prio (None = any)."""
    return {bid: e for bid, e in planned().items()
            if isinstance(e, dict) and (kinds is None or e.get("k") in kinds) and (prio is None or e.get("p") == prio)}


def planned():
    """autoplay.planned as a dict ({} when missing or malformed)."""
    raw = archive.get(PLANNED_KEY, {})
    return raw if isinstance(raw, dict) else {}


def prune_planned(live_ids, jobs_ok):
    """Drops autoplay.planned entries whose job is gone; skipped when the job lists were not fully read. Returns how many dropped."""
    if not jobs_ok:
        return 0
    stale = [blueprint_id for blueprint_id in planned() if blueprint_id not in live_ids]
    if not stale:
        return 0

    def updater(entries):
        if not isinstance(entries, dict):
            return {}
        for blueprint_id in stale:
            entries.pop(blueprint_id, None)
        return entries

    archive.transaction(PLANNED_KEY, {}, updater)
    return len(stale)
