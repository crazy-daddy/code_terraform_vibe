# Field Mining Drills as pull-hauler pickup sources (lib/vehicle_cargo.py
# run_pull_loop()).
#
# Each drill's telemetry script (lib/mining_drill.py) advertises its
# stockpile in drill.status. Where a drill stands comes from the journal:
# every surveyed MiningSite with a drill on it names it (drill_id()), and the
# site's coordinates are the drill's (centre-anchored, like pumps and caps).
# The site list is cached (DRILL_CACHE_TICKS); a drill on no surveyed site
# has no position and is skipped by the hauler.
#
# The pull hauler imports it whether or not drills exist; with no drills
# deployed, nothing here does anything.

from archive import archive, STATUS_STALE_TICKS
from tree_console import TreeConsole, flush_all
from swallow import swallowed
from game_clock import now_tick

log = TreeConsole(module="drill_sites")

STATUS_KEY = "drill.status"  # written by lib/mining_drill.py

# A drill whose script hasn't published within STATUS_STALE_TICKS isn't offered as a source.

DRILL_TYPE_IDS = ("mining_drill", "mining_drill_industrial", "mining_drill_heavy")

# Arrival precision at a drill before connecting to its stockpile.
DRILL_ARRIVAL_PRECISION_M = 2.0

DRILL_CACHE_TICKS = 3000  # re-walk the journal's mineral sites at most every ~5 min

_cache = {"tick": None, "drills": {}}


def advertised_drills(curr_tick=None):
    """{drill_id: status entry} of every drill that published within STATUS_STALE_TICKS."""
    tick = curr_tick if curr_tick is not None else now_tick()
    raw = archive.get(STATUS_KEY, {})
    if not isinstance(raw, dict):
        return {}
    return {d: e for d, e in raw.items() if isinstance(e, dict) and tick - e.get("tick", 0) < STATUS_STALE_TICKS}


def site_drills(sites):
    """{drill_id: (x, y)} of every Mining Drill standing on one of `sites` (journal.surveyed_sites())."""
    drills = {}
    for site in sites or []:
        try:
            if site.kind() != "mineral":
                continue
            drill_id = site.drill_id()
            if drill_id:
                drills[drill_id] = (float(site.x), float(site.y))
        except Exception as error:
            swallowed("drill_sites.site_drills: site read", error)
    return drills


def drill_positions(curr_tick=None):
    """{drill_id: (x, y)} of every Mining Drill on a surveyed site, cached DRILL_CACHE_TICKS."""
    tick = curr_tick if curr_tick is not None else now_tick()
    if _cache["tick"] is not None and tick - _cache["tick"] < DRILL_CACHE_TICKS:
        return _cache["drills"]
    journal = get_component("journal")
    try:
        sites = journal.surveyed_sites("nocturna") if journal else []
    except Exception as error:
        swallowed("drill_sites.drill_positions: journal.surveyed_sites", error)
        sites = []
    _cache["tick"] = tick
    _cache["drills"] = site_drills(sites)
    log.debug(f"{len(_cache['drills'])} Mining Drill(s) on surveyed sites.")
    return _cache["drills"]


def connect_to_drill(port: "InputSlot | VehicleInputSlot", drill_id):
    """True when `port` (vehicle.input) is now connected to drill_id -- only possible inside its service area."""
    log.start(f"connect_to_drill({drill_id!r})", level="debug")
    try:
        if port.connected_id() == drill_id:
            log.end()
            return True
    except Exception as exc:
        swallowed("drill_sites.connect_to_drill: port.connected_id", exc)
    try:
        res = port.connect(drill_id)
    except Exception as error:
        log.debug(f"raised {error}.")
        log.end()
        return False
    status = getattr(res, "status", None)
    log.debug(f"{status} - {getattr(res, 'message', '')}")
    log.end()
    return status == "ok"


def take_from_drill(port: "InputSlot | VehicleInputSlot", item_id, amount):
    """take()s up to `amount` of item_id from the already-connected drill; returns units moved."""
    log.start("take_from_drill", level="debug")
    moved_total = 0
    for _attempt in range(5):
        remaining = amount - moved_total
        if remaining <= 0:
            break
        try:
            res = port.take(item_id, remaining)
        except Exception as error:
            log.debug(f"raised {error}.")
            break
        moved = getattr(res, "moved", 0) or 0
        status = getattr(res, "status", None)
        moved_total += moved
        if status == "busy":
            flush_all()
            sleep(0.5)
            continue
        if moved <= 0 or status not in ("ok", "partial"):
            log.debug(f"{status}, moved {moved}.")
            break
    log.end()
    return moved_total
