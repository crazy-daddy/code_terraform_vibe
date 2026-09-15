# Outpost ore-assignment & stock-target scaffolding for the multi-outpost
# mining network (docs/AI_CHEATSHEET.md, TODO.md Phase 3). Answers two
# questions for a vehicle stationed at a mining outpost: "which ores should I
# mine here?" (assigned_ores_for()) and "how much of each should I stockpile
# before stopping?" (stock_target_for()).
#
# Both use the same "seed once, then editable" convention already established
# by lib/production.py's FABRICATOR_STOCK_TARGETS_KEY: the first time an
# outpost/item is ever looked up, a sensible default is computed and written
# to archive; every read after that returns the stored value untouched, even
# across new POI surveys, so a player's manual edit is never silently
# clobbered by a background loop. Rebuilding a stale assignment (e.g. after
# surveying new nearby sites, or adding a second Warehouse) is a deliberate,
# separately-callable action (reseed_ore_assignment()), not automatic --
# meant to be wired to a not-yet-designed Control Panel button.

from storage import discover_storage_buildings

OUTPOST_ORE_ASSIGNMENTS_KEY = "outposts.ore_assignments"
OUTPOST_ORE_STOCK_TARGETS_KEY = "outposts.ore_stock_targets"

# One Warehouse slot's worth (docs/components/warehouse.md: 5 slots x 2000
# capacity = 10,000 total) -- fixed regardless of research, unlike
# Inventory's stack size. Default stockpile target per assigned ore.
WAREHOUSE_SLOT_CAPACITY = 2000


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


def _warehouse_slot_count(outpost_id):
    """How many distinct-material Warehouse slots this outpost currently has, network-wide at that outpost only."""
    outpost = outpost_by_id(outpost_id)
    if not outpost:
        return 0
    try:
        total_capacity = sum(
            b["component"].capacity()
            for b in discover_storage_buildings(outpost)
            if hasattr(b.get("component"), "capacity")
        )
    except Exception:
        return 0
    return total_capacity // WAREHOUSE_SLOT_CAPACITY


def _compute_ore_assignment(outpost_id):
    """
    Ranks candidate ores for outpost_id by how many surveyed mineral sites of
    that ore type are nearest to it (most sites first), capped to the
    outpost's current Warehouse slot count. Shared by both
    assigned_ores_for()'s auto-seed path and reseed_ore_assignment()'s
    explicit rebuild -- kept as one function so the two entry points can
    never silently drift apart in ranking logic.
    """
    journal = _component("journal")
    if not journal or not hasattr(journal, "surveyed_sites"):
        return []

    site_counts = {}
    try:
        for site in journal.surveyed_sites("nocturna"):
            if getattr(site, "kind", lambda: "")() != "mineral":
                continue
            item_id = getattr(site, "item_id", None)
            if not item_id:
                continue
            if nearest_outpost_id(site.x, site.y) != outpost_id:
                continue
            site_counts[item_id] = site_counts.get(item_id, 0) + 1
    except Exception:
        return []

    ranked = sorted(site_counts.keys(), key=lambda item_id: site_counts[item_id], reverse=True)
    slot_cap = _warehouse_slot_count(outpost_id)
    return ranked[:slot_cap]


def assigned_ores_for(outpost_id):
    """
    Ores this outpost should mine locally. Auto-seeds via
    _compute_ore_assignment() only the first time this outpost id has no
    stored entry at all; every subsequent call (including after new POIs are
    surveyed nearby) returns the stored list untouched -- a player's manual
    edit always wins. Use reseed_ore_assignment() to deliberately rebuild.
    """
    archive = _archive()
    assignments = archive.get(OUTPOST_ORE_ASSIGNMENTS_KEY, {}) or {}
    if outpost_id in assignments:
        return list(assignments[outpost_id])

    computed = _compute_ore_assignment(outpost_id)
    assignments = dict(assignments)
    assignments[outpost_id] = computed
    archive.set(OUTPOST_ORE_ASSIGNMENTS_KEY, assignments)
    return list(computed)


def reseed_ore_assignment(outpost_id):
    """
    Explicit, never-auto-called rebuild of this outpost's ore assignment --
    recomputes and overwrites regardless of whether an entry already exists.
    Meant for a future Control Panel action once the player has surveyed new
    POIs or added Warehouse capacity near this outpost, not for any
    background loop to call on its own schedule.
    """
    computed = _compute_ore_assignment(outpost_id)
    archive = _archive()
    assignments = dict(archive.get(OUTPOST_ORE_ASSIGNMENTS_KEY, {}) or {})
    assignments[outpost_id] = computed
    archive.set(OUTPOST_ORE_ASSIGNMENTS_KEY, assignments)
    return computed


def stock_target_for(outpost_id, item_id):
    """
    Stockpile target (units) for item_id at outpost_id -- seed-once-then-
    editable, same convention as assigned_ores_for(), default one Warehouse
    slot's worth (WAREHOUSE_SLOT_CAPACITY).
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
    return WAREHOUSE_SLOT_CAPACITY
