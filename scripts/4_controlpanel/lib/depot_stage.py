# Drone Depot staging requests: a floating hauler drone (lib/drone_hauler.py)
# that plans a pickup at an outpost asks that outpost's Drone Depot to pull
# the items out of local storage (Warehouses, Inventory at home) into its
# stockpile, where a docked drone's cargo.load() can reach them. The Depot
# controller (lib/drone_depot.py fulfil_stage()) does the take() and keeps
# staged items out of its own drain/staging passes until the drone clears
# the request.
#
# Archive shape (one shared dict per concern, CODE_GUIDES.md#archive):
#   depot.stage = {depot_id: {item_id: {"units": n, "by": drone, "tick": t}}}
# One requester per (depot, item): a second drone staging the same item at
# the same Depot adds its units to the entry and takes over "by"; clearing
# drops the entry only when it is still owned by the clearing drone.

from archive import archive
from tree_console import TreeConsole
from script_parking import wake_for_visit
from game_clock import now_tick

log = TreeConsole(module="depot_stage")

STAGE_KEY = "depot.stage"

# A stage request is dropped this long after its last write (10 ticks/s ->
# 15 minutes, longer than a full-range hauler leg): a hauler that died
# mid-trip can't pin Depot stock forever.
STAGE_STALE_TICKS = 9000


def _prune(stages, tick):
    """Drops stale entries and empty depots in place."""
    for depot_id in list(stages.keys()):
        items = stages.get(depot_id)
        if not isinstance(items, dict):
            del stages[depot_id]
            continue
        for item_id in list(items.keys()):
            entry = items[item_id]
            if not isinstance(entry, dict) or tick - entry.get("tick", 0) >= STAGE_STALE_TICKS or (entry.get("units", 0) or 0) <= 0:
                del items[item_id]
        if not items:
            del stages[depot_id]
    return stages


def request_stage(depot_id, drone_name, item_id, units, curr_tick=None):
    """Asks depot_id to hold `units` of item_id in its stockpile for drone_name (units <= 0 withdraws it)."""
    tick = curr_tick if curr_tick is not None else now_tick()

    def updater(stages):
        if not isinstance(stages, dict):
            stages = {}
        _prune(stages, tick)
        items = stages.setdefault(depot_id, {})
        entry = items.get(item_id)
        if units <= 0:
            if isinstance(entry, dict) and entry.get("by") == drone_name:
                del items[item_id]
        elif isinstance(entry, dict) and entry.get("by") != drone_name:
            items[item_id] = {"units": (entry.get("units", 0) or 0) + units, "by": drone_name, "tick": tick}
        else:
            items[item_id] = {"units": units, "by": drone_name, "tick": tick}
        if not items:
            del stages[depot_id]
        return stages

    archive.transaction(STAGE_KEY, {}, updater)
    log.debug(f"request_stage({depot_id!r}, {drone_name!r}): {units}x {item_id}.")
    if units > 0:
        wake_for_visit(depot_id, f"{drone_name} pickup staged")


def clear_stage(drone_name, depot_id=None):
    """Withdraws every stage request drone_name owns (at depot_id, or everywhere), plus stale ones."""
    tick = now_tick()

    def updater(stages):
        if not isinstance(stages, dict):
            return {}
        for d_id, items in list(stages.items()):
            if depot_id is not None and d_id != depot_id:
                continue
            if isinstance(items, dict):
                for item_id in list(items.keys()):
                    entry = items[item_id]
                    if isinstance(entry, dict) and entry.get("by") == drone_name:
                        del items[item_id]
        return _prune(stages, tick)

    archive.transaction(STAGE_KEY, {}, updater)
    log.debug(f"clear_stage({drone_name!r}, depot_id={depot_id!r}).")


def staged_for(depot_id, curr_tick=None):
    """{item_id: units} fresh stage requests at depot_id (read-only)."""
    tick = curr_tick if curr_tick is not None else now_tick()
    stages = archive.get(STAGE_KEY, {})
    if not isinstance(stages, dict):
        return {}
    items = stages.get(depot_id, {})
    if not isinstance(items, dict):
        return {}
    wanted = {}
    for item_id, entry in items.items():
        if isinstance(entry, dict) and tick - entry.get("tick", 0) < STAGE_STALE_TICKS:
            units = entry.get("units", 0) or 0
            if units > 0:
                wanted[item_id] = units
    return wanted


def staged_items(depot_id, curr_tick=None):
    """Item ids depot_id must keep in its stockpile for a hauler (no drain, no Warehouse staging)."""
    return list(staged_for(depot_id, curr_tick).keys())
