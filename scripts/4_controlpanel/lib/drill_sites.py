# Field Mining Drills as pull-hauler pickup sources (lib/vehicle_cargo.py
# run_pull_loop()).
#
# Each drill's telemetry script (lib/mining_drill.py, tier 7_miningdrills)
# advertises its stockpile in drill.status. What no API gives is where the
# drill stands: the component has no position, drills aren't on the outpost
# network, PowerGridMember carries no coordinates, and MiningSite (unlike
# WaterWell/OilWell's pump_id()) doesn't say which drill stands on it --
# requested from the dev. Until then drill.positions is filled by:
#   - construction: a Pioneer that just finished a mining_drill* blueprint
#     records the blueprint position for the new drill (record_built_drill(),
#     called from lib/pioneer.py execute_construction());
#   - seeding by hand for drills built any other way (Playground one-liner
#     writing drill.positions directly).
# A drill with no known position is skipped by the hauler.
#
# Lives in the 4_controlpanel lib (not 7_miningdrills) because the pull
# hauler and the Pioneer constructor import it at every tier; with no drills
# deployed, nothing here does anything.
#
# Archive shape (one shared dict per concern, CLAUDE.md rule 7):
#   drill.positions = {drill_id: {"pos": [x, y], "site": site_id | None}}
# Entries of drills no longer deployed (discover_drill_ids()) are pruned on
# every write, unless discovery came back empty.

from archive import archive
from tree_console import TreeConsole

log = TreeConsole(module="drill_sites")

STATUS_KEY = "drill.status"  # written by lib/mining_drill.py
POSITIONS_KEY = "drill.positions"

# Same window as lib/mining_drill.py STATUS_STALE_TICKS: a drill whose script
# hasn't published for an hour isn't offered as a source.
STATUS_STALE_TICKS = 36000

DRILL_TYPE_IDS = ("mining_drill", "mining_drill_industrial", "mining_drill_heavy")

# Arrival precision at a drill before connecting to its stockpile.
DRILL_ARRIVAL_PRECISION_M = 2.0

# A freshly built drill may not show up in power_control grids until the
# next power allocation; record_built_drill() retries this often, 1 s apart.
BUILT_DRILL_DISCOVERY_ATTEMPTS = 3

# Max distance from a blueprint position to the surveyed site it snapped to.
SITE_MATCH_TOLERANCE_M = 3.0


def _now_tick():
    try:
        clock = get_component("clock")
        return clock.tick() if clock else 0
    except Exception:
        return 0


def advertised_drills(curr_tick=None):
    """{drill_id: status entry} of every drill that published within STATUS_STALE_TICKS."""
    tick = curr_tick if curr_tick is not None else _now_tick()
    raw = archive.get(STATUS_KEY, {})
    if not isinstance(raw, dict):
        return {}
    return {d: e for d, e in raw.items() if isinstance(e, dict) and tick - e.get("tick", 0) < STATUS_STALE_TICKS}


def known_positions():
    raw = archive.get(POSITIONS_KEY, {})
    return raw if isinstance(raw, dict) else {}


def position_of(drill_id, positions=None):
    """[x, y] of drill_id, or None when not recorded yet."""
    positions = positions if positions is not None else known_positions()
    entry = positions.get(drill_id) or {}
    return entry.get("pos") if isinstance(entry, dict) else None


def discover_drill_ids(type_id=None):
    """Ids of deployed drills (optionally one variant): power_control grid members plus drill.status publishers."""
    ids = set()
    power = get_component("power_control")
    try:
        grids = power.grids() if power else []
    except Exception:
        grids = []
    for grid in grids:
        for member in getattr(grid, "members", []) or []:
            member_type = getattr(member, "type_id", "")
            if member_type in DRILL_TYPE_IDS and (type_id is None or member_type == type_id):
                ids.add(member.id)
    for drill_id, entry in advertised_drills().items():
        if type_id is None or entry.get("type") in (None, type_id):
            ids.add(drill_id)
    return ids


def confirm_position(drill_id, site_id, pos):
    """Records drill_id at pos (site_id may be None), pruning entries of drills no longer deployed."""
    live = discover_drill_ids()
    entry = {"pos": [float(pos[0]), float(pos[1])], "site": site_id}

    def updater(positions):
        if not isinstance(positions, dict):
            positions = {}
        if live:
            for d in list(positions.keys()):
                if d != drill_id and d not in live:
                    del positions[d]
        positions[drill_id] = entry
        return positions

    archive.transaction(POSITIONS_KEY, {}, updater)
    log.print(f"Drill '{drill_id}' located at site {site_id} ({pos[0]:.0f}, {pos[1]:.0f}).")


def site_at(coords, tolerance=SITE_MATCH_TOLERANCE_M):
    """Id of the surveyed mineral site at coords (nearest within tolerance), or None."""
    journal = get_component("journal")
    if not journal or not hasattr(journal, "surveyed_sites"):
        return None
    best, best_dist = None, tolerance
    try:
        for site in journal.surveyed_sites("nocturna"):
            if site.kind() != "mineral":
                continue
            dist = ((float(site.x) - coords[0]) ** 2 + (float(site.y) - coords[1]) ** 2) ** 0.5
            if dist <= best_dist:
                best, best_dist = getattr(site, "id", None), dist
    except Exception as error:
        log.debug(f"site_at({coords}): journal read failed: {error}")
    return best


def record_built_drill(port, kind, coords):
    """
    Called by a Pioneer parked at a just-finished mining_drill* blueprint:
    finds the new drill among this variant's drills with no known position
    by connecting `port` (vehicle.input) to each -- only the one standing
    here accepts -- and records it at the blueprint position. Falls back to
    the sole unresolved drill of that variant when none accepts (unverified).
    Returns the drill id or None.
    """
    site_id = site_at(coords)
    unresolved = []
    for attempt in range(BUILT_DRILL_DISCOVERY_ATTEMPTS):
        positions = known_positions()
        unresolved = sorted(d for d in discover_drill_ids(kind) if not position_of(d, positions))
        log.debug(f"record_built_drill({kind}, {coords}): attempt {attempt + 1}, unresolved={unresolved}, site={site_id}.")
        for drill_id in unresolved:
            if connect_to_drill(port, drill_id):
                confirm_position(drill_id, site_id, coords)
                return drill_id
        sleep(1.0)
    if len(unresolved) == 1:
        log.level("warn").print(f"New {kind} at {coords} didn't accept a connection; assuming it is '{unresolved[0]}' (only unresolved one).")
        confirm_position(unresolved[0], site_id, coords)
        return unresolved[0]
    log.level("warn").print(f"New {kind} at {coords}: couldn't tell which drill it is ({len(unresolved)} unresolved). Seed drill.positions by hand.")
    return None


def connect_to_drill(port, drill_id):
    """True when `port` (vehicle.input) is now connected to drill_id -- only possible inside its service area."""
    try:
        if port.connected_id() == drill_id:
            return True
    except Exception:
        pass
    try:
        res = port.connect(drill_id)
    except Exception as error:
        log.debug(f"connect_to_drill({drill_id!r}): raised {error}.")
        return False
    status = getattr(res, "status", None)
    log.debug(f"connect_to_drill({drill_id!r}): {status} - {getattr(res, 'message', '')}")
    return status == "ok"


def take_from_drill(port, item_id, amount):
    """take()s up to `amount` of item_id from the already-connected drill; returns units moved."""
    moved_total = 0
    for _attempt in range(5):
        remaining = amount - moved_total
        if remaining <= 0:
            break
        try:
            res = port.take(item_id, remaining)
        except Exception as error:
            log.debug(f"take_from_drill({item_id}, {remaining}): raised {error}.")
            break
        moved = getattr(res, "moved", 0) or 0
        status = getattr(res, "status", None)
        moved_total += moved
        if status == "busy":
            sleep(0.5)
            continue
        if moved <= 0 or status not in ("ok", "partial"):
            log.debug(f"take_from_drill({item_id}, {remaining}): {status}, moved {moved}.")
            break
    return moved_total
