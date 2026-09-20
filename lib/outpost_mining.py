# Outpost ore-assignment & stock-target scaffolding for the multi-outpost
# mining network (docs/AI_CHEATSHEET.md, TODO.md Phase 3). Answers two
# questions for a vehicle stationed at a mining outpost: "which ores should I
# mine here?" (assigned_ores_for()) and "how much of each should I stockpile
# before stopping?" (stock_target_for()).
#
# "Which ores" is answered LIVE from the Planet Map, not an archive list: every
# surveyed mineral site gets a "resource.poi_X_Y" marker (mirroring
# mark_unsupported_targets.py's id/style conventions), labeled with its ore and
# purity (e.g. "Iron Ore - Rich"), whose .note names the outpost responsible for
# mining it -- assigned_ores_for(outpost_id) just scans markers.list("resource.")
# for notes matching outpost_id and recovers each item id from its own label. A
# site earns its outpost either automatically (auto_assign_new_site(), called
# right after survey, hands it to the closest owned outpost within
# assignment_range_m() -- configurable via archive, default 200m) or by the
# player editing/dragging the marker by hand -- either way, the marker itself
# stays the single source of truth, so there's no separate archive assignment
# list that could drift out of sync with what the map actually shows.
#
# A site already assigned to an outpost is NEVER auto-reassigned, even to a
# now-closer outpost founded later -- that could strand supply at an outpost
# whose transport/miner is already relying on it. reevaluate_unassigned_near_outpost()
# is the explicit, player-triggered sweep for "I just founded a new outpost,
# hand it any still-unassigned sites nearby" (see sync_resource_markers.py).
#
# stock_target_for() keeps the same seed-once-then-editable convention already
# established by lib/production.py's FABRICATOR_STOCK_TARGETS_KEY: the first
# time an outpost/item is ever looked up, a sensible default is computed and
# written to archive; every read after that returns the stored value untouched,
# so a player's manual edit is never silently clobbered by a background loop.

from tree_console import TreeConsole

log = TreeConsole(module="outpost_mining")

OUTPOST_ORE_STOCK_TARGETS_KEY = "outposts.ore_stock_targets"

# One Warehouse slot's worth (docs/components/warehouse.md: 5 slots x 2000
# capacity = 10,000 total) -- fixed regardless of research, unlike
# Inventory's stack size. Default stockpile target per assigned ore.
WAREHOUSE_SLOT_CAPACITY = 2000

# Marker family for surveyed mineral sites (see module docstring). Mirrors
# mark_unsupported_targets.py's MARKER_PREFIX convention.
RESOURCE_MARKER_PREFIX = "resource."

# How close (meters) a freshly-surveyed site or a freshly-founded outpost needs
# to be before auto-assignment considers them a match. Archive-configurable
# (player-tunable without a code change) rather than a bare constant.
RESOURCE_ASSIGNMENT_RANGE_KEY = "outposts.resource_assignment_range_m"
DEFAULT_RESOURCE_ASSIGNMENT_RANGE_M = 200.0

# item_id -> display name is just its title-cased form ("iron_ore" -> "Iron
# Ore"), reversible exactly (see _item_id_from_label()) for every known
# MiningSite.item_id (docs/types/world_and_sites.md): iron_ore, silicon,
# titanium, cobalt, rare_earth, neutronium, lead_ore.
RESOURCE_PURITY_LABELS = {"standard": "Standard", "rich": "Rich", "pure": "Pure"}

# Every raw ore item_id mineable in this save (docs/types/world_and_sites.md).
# Shared by production.py's home-buffer floor (see stock_target_for()'s
# module docstring) so both the mining-outpost stockpile target and the home
# buffer target iterate the exact same ore set.
RAW_ORE_ITEM_IDS = ("iron_ore", "silicon", "titanium", "cobalt", "rare_earth", "neutronium", "lead_ore")

# Canonical home outpost id (docs/components/outpost.md; also hardcoded as a
# literal in lib/vehicle_cargo.py's _outpost_haul_demand()/pioneer_5-7.py).
HOME_OUTPOST_ID = "outpost_home"


def _component(component_id):
    try:
        return get_component(component_id)
    except Exception:
        return None


def _archive():
    from archive import archive
    return archive


def _outpost_network():
    return _component("outpost_network")


def _markers():
    return _component("markers")


def outpost_by_id(outpost_id):
    """Resolves an outpost id string to its live OutpostRef/Outpost object, or None."""
    network = _outpost_network()
    if not network or not hasattr(network, "outposts"):
        return None
    try:
        for outpost in network.outposts():
            if getattr(outpost, "id", None) == outpost_id:
                return outpost
    except Exception:
        pass
    return None


def nearest_outpost_id(x, y):
    """Id of the outpost nearest to world coords (x, y), or None if unavailable."""
    network = _outpost_network()
    if not network or not hasattr(network, "nearest"):
        return None
    try:
        nearest = network.nearest(x, y)
        return getattr(nearest, "id", None) if nearest else None
    except Exception:
        return None


def resource_assignment_range_m():
    """Player-tunable auto-assignment radius (meters), archive-backed, default DEFAULT_RESOURCE_ASSIGNMENT_RANGE_M."""
    return _archive().get(RESOURCE_ASSIGNMENT_RANGE_KEY, DEFAULT_RESOURCE_ASSIGNMENT_RANGE_M)


def resource_marker_id(x, y):
    """Stable marker id for the mineral site at (x, y), mirroring the poi_X_Y convention mark_unsupported_targets.py already uses."""
    return f"{RESOURCE_MARKER_PREFIX}poi_{x:.0f}_{y:.0f}"[:64]


def _item_display_name(item_id):
    return item_id.replace("_", " ").title()


def _item_id_from_label(label):
    """Recovers item_id from a "Iron Ore - Rich"-style marker label -- the exact inverse of _item_display_name(), so no separate lookup table is needed."""
    if not label:
        return None
    name_part = label.split(" - ")[0].strip()
    return name_part.lower().replace(" ", "_") if name_part else None


def _distance(ax, ay, bx, by):
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def _closest_outpost_within_range(x, y, range_m):
    """Id of the closest owned outpost to (x, y), or None when the nearest one is still farther than range_m (or outpost_network is unavailable)."""
    network = _outpost_network()
    if not network or not hasattr(network, "nearest"):
        return None
    try:
        nearest = network.nearest(x, y)
    except Exception:
        return None
    if not nearest:
        return None
    ox, oy = getattr(nearest, "x", None), getattr(nearest, "y", None)
    if ox is None or oy is None or _distance(x, y, ox, oy) > range_m:
        return None
    return getattr(nearest, "id", None)


def sync_resource_marker(site, outpost_id=None):
    """
    Places/updates the "resource." marker for a surveyed mineral site.
    outpost_id=None (the default) preserves whatever outpost the marker
    already names (read back via markers.get()) -- a plain style refresh,
    e.g. after a purity re-survey. Pass an explicit outpost_id (including ""
    to clear) to actually change the assignment. Returns the outpost id left
    on the marker (possibly ""), or None if the Markers component or the
    site's item_id is unavailable.
    """
    markers = _markers()
    item_id = getattr(site, "item_id", None)
    if not markers or not item_id:
        return None

    marker_id = resource_marker_id(site.x, site.y)
    if outpost_id is None:
        existing = markers.get(marker_id)
        outpost_id = getattr(existing, "note", "") if existing else ""

    purity_label = RESOURCE_PURITY_LABELS.get(getattr(site, "purity", None), "Standard")
    label = f"{_item_display_name(item_id)} - {purity_label}"[:48]
    res = markers.place(
        id=marker_id, x=site.x, y=site.y,
        label=label, icon="resource", color="neutral",
        note=outpost_id or "",
    )
    if getattr(res, "status", "") != "ok":
        return None
    return outpost_id or ""


def auto_assign_new_site(site, range_m=None):
    """
    Call once per freshly-surveyed mineral site (vehicle_survey.py's
    scan_and_survey()). Places/refreshes its resource marker and, only when
    it isn't already assigned to an outpost, hands it to the closest owned
    outpost within range_m (resource_assignment_range_m() by default). Never
    reassigns a site that already names a responsible outpost -- see module
    docstring.
    """
    markers = _markers()
    item_id = getattr(site, "item_id", None)
    if not markers or not item_id:
        return None

    marker_id = resource_marker_id(site.x, site.y)
    existing = markers.get(marker_id)
    outpost_id = getattr(existing, "note", "") if existing else ""
    if not outpost_id:
        effective_range = range_m if range_m is not None else resource_assignment_range_m()
        outpost_id = _closest_outpost_within_range(site.x, site.y, effective_range) or ""
        if outpost_id:
            log.debug(f"auto_assign_new_site: {item_id} site at ({site.x:.0f},{site.y:.0f}) assigned to closest outpost '{outpost_id}' within {effective_range:.0f}m")
        else:
            log.debug(f"auto_assign_new_site: {item_id} site at ({site.x:.0f},{site.y:.0f}) has no owned outpost within {effective_range:.0f}m, left unassigned")
    else:
        log.debug(f"auto_assign_new_site: {item_id} site at ({site.x:.0f},{site.y:.0f}) already assigned to '{outpost_id}', refreshing marker only")

    return sync_resource_marker(site, outpost_id=outpost_id)


def reevaluate_unassigned_near_outpost(outpost_id, range_m=None):
    """
    Explicit, never-auto-called sweep: call after founding a new outpost
    (CLAUDE.md's Outpost Construction Safety Rule means there is no automatic
    "an outpost just got founded" hook -- this function never founds anything
    itself) to hand any still-UNASSIGNED "resource." marker within range_m to
    outpost_id. Deliberately leaves markers that already name a different
    outpost untouched, even one now farther away than this new outpost -- see
    module docstring. Returns the count of markers newly assigned.
    """
    markers = _markers()
    outpost = outpost_by_id(outpost_id)
    if not markers or not outpost:
        return 0

    ox, oy = getattr(outpost, "x", None), getattr(outpost, "y", None)
    if ox is None or oy is None:
        return 0
    effective_range = range_m if range_m is not None else resource_assignment_range_m()

    assigned = 0
    try:
        candidates = markers.list(RESOURCE_MARKER_PREFIX)
    except Exception:
        return 0

    for marker in candidates:
        if not getattr(marker, "note", ""):
            continue
        if _distance(marker.x, marker.y, ox, oy) > effective_range:
            continue
        res = markers.place(
            id=marker.id, x=marker.x, y=marker.y,
            label=marker.label, icon=marker.icon, color=marker.color,
            note=outpost_id,
        )
        if getattr(res, "status", "") == "ok":
            assigned += 1
            log.debug(f"reevaluate_unassigned_near_outpost({outpost_id}): claimed unassigned marker '{marker.id}' ({marker.label}) within {effective_range:.0f}m")
    log.debug(f"reevaluate_unassigned_near_outpost({outpost_id}): assigned {assigned} previously-unassigned marker(s) out of {len(candidates)} scanned")
    return assigned


def site_assigned_outpost(x, y):
    """Outpost id this specific site's resource marker names (its .note), or None if unassigned/no marker yet."""
    markers = _markers()
    if not markers:
        return None
    marker = markers.get(resource_marker_id(x, y))
    return getattr(marker, "note", "") or None if marker else None


def assigned_ores_for(outpost_id):
    """
    Ores this outpost's markers currently say it supplies -- reads the Planet
    Map live (markers.list(RESOURCE_MARKER_PREFIX)) rather than an archive
    list, so moving supply between outposts is a marker edit (see module
    docstring), not an archive mutation. Each qualifying marker's item id is
    recovered from its own label (_item_id_from_label()), so no journal/
    archive cross-reference is needed at read time.
    """
    markers = _markers()
    if not markers:
        return []
    try:
        candidates = markers.list(RESOURCE_MARKER_PREFIX)
    except Exception:
        return []

    items = set()
    for marker in candidates:
        if getattr(marker, "note", "") != outpost_id:
            continue
        item_id = _item_id_from_label(getattr(marker, "label", ""))
        if item_id:
            items.add(item_id)
    result = sorted(items)
    log.trace(f"assigned_ores_for({outpost_id}): {result}")
    return result


def stock_target_for(outpost_id, item_id):
    """
    Stockpile target (units) for item_id at outpost_id -- seed-once-then-
    editable, same convention as assigned_ores_for() used to follow, default
    one Warehouse slot's worth (WAREHOUSE_SLOT_CAPACITY). Also used for
    outpost_id=HOME_OUTPOST_ID by production.py's get_raw_material_demands()
    as a standing home ore buffer -- same "1 Warehouse slot per ore" default,
    freely drawn down by Smelter/Supply Dock (not a reserved stockpile), just
    a floor that creates mining/haul demand to top itself back up.
    """
    archive = _archive()
    targets = archive.get(OUTPOST_ORE_STOCK_TARGETS_KEY, {}) or {}
    outpost_targets = targets.get(outpost_id)
    if isinstance(outpost_targets, dict) and item_id in outpost_targets:
        return outpost_targets[item_id]

    targets = dict(targets)
    outpost_targets = dict(outpost_targets) if isinstance(outpost_targets, dict) else {}
    outpost_targets[item_id] = WAREHOUSE_SLOT_CAPACITY
    targets[outpost_id] = outpost_targets
    archive.set(OUTPOST_ORE_STOCK_TARGETS_KEY, targets)
    log.debug(f"stock_target_for({outpost_id}, {item_id}): seeding default target {WAREHOUSE_SLOT_CAPACITY} (first lookup)")
    return WAREHOUSE_SLOT_CAPACITY
