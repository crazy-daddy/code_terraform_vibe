# Outpost ore-assignment & stock-target scaffolding for the multi-outpost
# mining network (docs/AI_CHEATSHEET.md, TODO.md Phase 3). Answers two
# questions for a vehicle stationed at a mining outpost: "which ores should I
# mine here?" (assigned_ores_for()) and "how much of each should I stockpile
# before stopping?" (ore_stock_target()).
#
# "Which ores" is answered LIVE from the Planet Map, not an archive list: every
# surveyed mineral site gets a "resource.poi_X_Y" marker (same id convention
# as lib/unsupported_markers.py), labeled with its ore and purity (e.g. "Iron
# Ore - Rich"), whose .note names the outpost responsible for mining it --
# assigned_ores_for(outpost_id) just scans markers.list("resource.") for notes
# matching outpost_id and recovers each item id from its own label. The marker
# stays the single source of truth, so no archive assignment list can drift
# out of sync with what the map shows.
#
# Owner: only an outpost designated for mining (MINING_ROLE in its
# autoplay.outpost_roles entry) is ever picked automatically, the closest one
# within resource_assignment_range_m(). Without one in range the site stays
# unassigned. The operator assigns any other outpost by editing the marker
# note. auto_assign_new_site() runs right after each survey;
# assign_unassigned_sites() sweeps every unassigned marker each storage pass
# of control_room_automation.py, so a new designation or a new outpost picks
# up its sites. Markers need Cartography (140k TP): sync_mineral_site_markers()
# backfills the sites surveyed before then.
#
# A site already assigned to an outpost is NEVER auto-reassigned, even to a
# now-closer mining outpost -- that could strand supply at an outpost whose
# transport/miner is already relying on it.
#
# ore_stock_target() keeps the same seed-once-then-editable convention already
# established by lib/production.py's FABRICATOR_STOCK_TARGETS_KEY: the first
# time an ore is ever looked up, a sensible default is computed and written to
# archive; every read after that returns the stored value untouched, so a
# player's manual edit is never silently clobbered by a background loop.

from tree_console import TreeConsole
from components import component
from swallow import swallowed

log = TreeConsole(module="outpost_mining")

# One {ore_item_id: units} dict for every outpost: a mining outpost's
# stockpile target, home's standing ore floor and a smelting site's ore
# buffer (lib/site_supply.py) all read the same number.
ORE_STOCK_TARGETS_KEY = "mining.ore_stock_targets"

# One Warehouse slot's worth (docs/components/warehouse.md: 5 slots x 2000
# capacity = 10,000 total) -- fixed regardless of research, unlike
# Inventory's stack size. Default stockpile target per assigned ore.
WAREHOUSE_SLOT_CAPACITY = 2000

# Marker family for surveyed mineral sites (see module docstring).
RESOURCE_MARKER_PREFIX = "resource."

# How close (meters) a mining outpost needs to be to a site to own it.
# Archive-configurable (player-tunable without a code change) rather than a
# bare constant.
RESOURCE_ASSIGNMENT_RANGE_KEY = "outposts.resource_assignment_range_m"
DEFAULT_RESOURCE_ASSIGNMENT_RANGE_M = 200.0

# Outpost designations, written by autoplay (autoplay_roles.ROLES_KEY; same key,
# read here without importing autoplay, which a save may not deploy):
# {outpost_id: role | [role, ...]}. Only outposts holding MINING_ROLE own sites.
OUTPOST_ROLES_KEY = "autoplay.outpost_roles"
MINING_ROLE = "mining"

# item_id -> display name is just its title-cased form ("iron_ore" -> "Iron
# Ore"), reversible exactly (see _item_id_from_label()) for every known
# MiningSite.item_id (docs/types/world_and_sites.md): iron_ore, silicon,
# titanium, cobalt, rare_earth, neutronium, lead_ore.
RESOURCE_PURITY_LABELS = {"standard": "Standard", "rich": "Rich", "pure": "Pure"}

# Every raw ore item_id mineable in this save (docs/types/world_and_sites.md).
# Shared by production.py's home-buffer floor (see ore_stock_target()) so both the mining-outpost stockpile target and the home
# buffer target iterate the exact same ore set.
RAW_ORE_ITEM_IDS = ("iron_ore", "silicon", "titanium", "cobalt", "rare_earth", "neutronium", "lead_ore")

# Canonical home outpost id (docs/components/outpost.md; also hardcoded as a
# literal in a few tier-1 scripts, e.g. power/solar.py).
HOME_OUTPOST_ID = "outpost_home"


def _archive():
    from archive import archive
    return archive


def _outpost_network():
    return component("outpost_network")


def _markers():
    return component("markers")


def outpost_by_id(outpost_id):
    """Resolves an outpost id string to its live OutpostRef/Outpost object, or None."""
    network = _outpost_network()
    if not network or not hasattr(network, "outposts"):
        return None
    try:
        for outpost in network.outposts():
            if getattr(outpost, "id", None) == outpost_id:
                return outpost
    except Exception as error:
        swallowed("outpost_mining.outpost_by_id: network.outposts", error)
    return None


def nearest_outpost_id(x, y):
    """Id of the outpost nearest to world coords (x, y), or None if unavailable."""
    network = _outpost_network()
    if not network or not hasattr(network, "nearest"):
        return None
    try:
        nearest = network.nearest(x, y)
        return getattr(nearest, "id", None) if nearest else None
    except Exception as error:
        swallowed("outpost_mining.nearest_outpost_id: network.nearest", error)
        return None


def resource_assignment_range_m():
    """Player-tunable auto-assignment radius (meters), archive-backed, default DEFAULT_RESOURCE_ASSIGNMENT_RANGE_M."""
    return _archive().get(RESOURCE_ASSIGNMENT_RANGE_KEY, DEFAULT_RESOURCE_ASSIGNMENT_RANGE_M)


def resource_marker_id(x, y):
    """Stable marker id for the mineral site at (x, y), same poi_X_Y convention as lib/unsupported_markers.py."""
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


def mining_outpost_ids():
    """Ids of the outposts whose designation holds MINING_ROLE (empty set without designations)."""
    roles = _archive().get(OUTPOST_ROLES_KEY, {})
    if not isinstance(roles, dict):
        return set()
    out = set()
    for outpost_id, value in roles.items():
        names = [value] if isinstance(value, str) else (value if isinstance(value, (list, tuple)) else [])
        if MINING_ROLE in names:
            out.add(outpost_id)
    return out


def _mining_outposts():
    """[(id, x, y)] of the live outposts designated for mining."""
    eligible = mining_outpost_ids()
    network = _outpost_network()
    if not eligible or not network or not hasattr(network, "outposts"):
        return []
    try:
        outposts = network.outposts()
    except Exception as error:
        swallowed("outpost_mining._mining_outposts: network.outposts", error)
        return []
    out = []
    for outpost in outposts:
        outpost_id = getattr(outpost, "id", None)
        ox, oy = getattr(outpost, "x", None), getattr(outpost, "y", None)
        if outpost_id in eligible and ox is not None and oy is not None:
            out.append((outpost_id, ox, oy))
    return out


def _closest_owner(x, y, owners, range_m):
    """Id of the closest of owners [(id, x, y)] within range_m of (x, y), or ""."""
    best, best_d = "", range_m
    for outpost_id, ox, oy in owners:
        d = _distance(x, y, ox, oy)
        if d <= best_d:
            best, best_d = outpost_id, d
    return best


def auto_assign_new_site(site, range_m=None, owners=None):
    """
    Call once per freshly-surveyed mineral site (vehicle_survey.py's
    scan_and_survey()). Places/refreshes its resource marker and, only when
    it isn't already assigned to an outpost, hands it to the closest
    mining-designated outpost within range_m (resource_assignment_range_m()
    by default). owners: _mining_outposts(), when the caller already has it.
    Never reassigns a site that already names a responsible outpost -- see
    module docstring.
    """
    markers = _markers()
    item_id = getattr(site, "item_id", None)
    if not markers or not item_id:
        return None

    existing = markers.get(resource_marker_id(site.x, site.y))
    outpost_id = getattr(existing, "note", "") if existing else ""
    if not outpost_id:
        effective_range = range_m if range_m is not None else resource_assignment_range_m()
        outpost_id = _closest_owner(site.x, site.y, _mining_outposts() if owners is None else owners, effective_range)
        if outpost_id:
            log.debug(f"auto_assign_new_site: {item_id} site at ({site.x:.0f},{site.y:.0f}) assigned to closest mining outpost '{outpost_id}' within {effective_range:.0f}m")
        else:
            log.trace(f"auto_assign_new_site: {item_id} site at ({site.x:.0f},{site.y:.0f}) has no mining outpost within {effective_range:.0f}m, left unassigned")
    else:
        log.trace(f"auto_assign_new_site: {item_id} site at ({site.x:.0f},{site.y:.0f}) already assigned to '{outpost_id}', refreshing marker only")

    return sync_resource_marker(site, outpost_id=outpost_id)


def sync_mineral_site_markers():
    """
    auto_assign_new_site() for every surveyed mineral site: the backfill of
    sites surveyed before Cartography (control_room_automation.py, once per
    run; sync_resource_markers.py by hand). Returns the count synced, 0
    without markers or journal.
    """
    journal = component("journal")
    if not _markers() or not journal or not hasattr(journal, "surveyed_sites"):
        return 0
    try:
        sites = journal.surveyed_sites("nocturna") or []
    except Exception as error:
        swallowed("outpost_mining.sync_mineral_site_markers: journal.surveyed_sites", error)
        return 0
    owners = _mining_outposts()
    range_m = resource_assignment_range_m()
    synced = 0
    for site in sites:
        if site.kind() != "mineral" or not getattr(site, "item_id", None):
            continue
        auto_assign_new_site(site, range_m=range_m, owners=owners)
        synced += 1
    log.debug(f"sync_mineral_site_markers: {synced} mineral site marker(s) synced, {len(owners)} mining outpost(s)")
    return synced


def assign_unassigned_sites(range_m=None):
    """
    Hands every still-UNASSIGNED "resource." marker to the closest
    mining-designated outpost within range_m. Markers that already name an
    outpost stay untouched -- see module docstring. Run each storage pass by
    control_room_automation.py. Returns the count of markers newly assigned.
    """
    markers = _markers()
    owners = _mining_outposts()
    if not markers or not owners:
        return 0
    effective_range = range_m if range_m is not None else resource_assignment_range_m()
    try:
        candidates = markers.list(RESOURCE_MARKER_PREFIX)
    except Exception as error:
        swallowed("outpost_mining.assign_unassigned_sites: markers.list", error)
        return 0

    assigned = 0
    for marker in candidates:
        if getattr(marker, "note", ""):
            continue
        outpost_id = _closest_owner(marker.x, marker.y, owners, effective_range)
        if not outpost_id:
            continue
        res = markers.place(
            id=marker.id, x=marker.x, y=marker.y,
            label=marker.label, icon=marker.icon, color=marker.color,
            note=outpost_id,
        )
        if getattr(res, "status", "") == "ok":
            assigned += 1
            log.debug(f"assign_unassigned_sites: '{marker.id}' ({marker.label}) to mining outpost '{outpost_id}'")
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
    except Exception as error:
        swallowed("outpost_mining.assigned_ores_for: markers.list", error)
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


def assigned_ores_by_outpost():
    """{outpost_id: set of ores} from one markers.list() scan: assigned_ores_for() for every
    outpost at once, for passes that ask about several outposts."""
    markers = _markers()
    if not markers:
        return {}
    try:
        candidates = markers.list(RESOURCE_MARKER_PREFIX)
    except Exception as error:
        swallowed("outpost_mining.assigned_ores_by_outpost: markers.list", error)
        return {}
    result = {}
    for marker in candidates:
        outpost_id = getattr(marker, "note", "")
        item_id = _item_id_from_label(getattr(marker, "label", ""))
        if outpost_id and item_id:
            result.setdefault(outpost_id, set()).add(item_id)
    return result


def ore_stock_target(item_id):
    """
    Stock target (units) for raw ore item_id, the same at every outpost --
    seed-once-then-editable under ORE_STOCK_TARGETS_KEY, default one
    Warehouse slot's worth (WAREHOUSE_SLOT_CAPACITY). Read as a stationed
    miner's stockpile target at its mining outpost and as every smelting
    site's ore buffer tier, home included (lib/site_supply.py).
    """
    archive = _archive()
    targets = archive.get(ORE_STOCK_TARGETS_KEY, {}) or {}
    if not isinstance(targets, dict):
        targets = {}
    value = targets.get(item_id)
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)

    targets = dict(targets)
    targets[item_id] = WAREHOUSE_SLOT_CAPACITY
    archive.set(ORE_STOCK_TARGETS_KEY, targets)
    log.debug(f"ore_stock_target({item_id}): seeding default target {WAREHOUSE_SLOT_CAPACITY} (first lookup)")
    return WAREHOUSE_SLOT_CAPACITY
