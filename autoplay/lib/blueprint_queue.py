# The infrastructure planner's only writer of construction blueprints
# (autoplay/infra_planner.py). Wraps construction_blueprint.plan_*, records
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

PLANNED_KEY = "autoplay.planned"


def _blueprints():
    return get_component("construction_blueprint")


def stock(item_id):
    """Count of item_id in the planet inventory, 0 when unreadable."""
    inventory = get_component("inventory")
    if inventory is None:
        return 0
    try:
        return int(inventory.count(item_id) or 0)
    except Exception as error:
        swallowed("blueprint_queue.stock: inventory.count", error)
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
    return len(cancelled)


def _plan_power_leg(blueprints, leg):
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
