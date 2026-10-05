# Outpost reagent-resupply scaffolding for a remote Bio Lab (docs/AI_CHEATSHEET.md,
# TODO.md Phase 4). Mirrors lib/outpost_mining.py's "seed once, then editable"
# convention exactly, adapted for reagents: the candidate set is small and fixed
# (unlike survey-derived ore assignment), so only the per-item stock TARGET needs
# seeding, and it's a per-reagent dict rather than one flat constant -- reagent
# prices vary enormously (docs/database/items_lab_reagents.md: 1cr to 1,000cr), so a
# single flat target would either starve the cheap ones or bankrupt the expensive
# ones this early in a save.

import logistics_requests
from tree_console import TreeConsole
from game_clock import now_tick

log = TreeConsole(module="outpost_reagents")

# Tune against actual credit budget as the save progresses -- see docs/AI_CHEATSHEET.md.
# A reagent this dict doesn't yet know about (a future dev addition) still gets a
# sane fallback via reagent_stock_target_for()'s default, rather than erroring.
DEFAULT_REAGENT_STOCK_TARGETS = {
    "alkaline_buffer": 100,
    "cryo_solvent": 100,
    "protein_marker": 60,
    "chelating_agent": 20,
    "enzyme_solution": 10,
}

FALLBACK_REAGENT_STOCK_TARGET = 100

OUTPOST_REAGENT_ASSIGNMENTS_KEY = "outposts.reagent_assignments"
OUTPOST_REAGENT_STOCK_TARGETS_KEY = "outposts.reagent_stock_targets"

# logistics.requests requester id for remote Bio Lab reagents.
REQUESTER_ID = "bio_reagents"
# Recompute interval (ticks) for the reagent wants; publish_requests() decides the write.
REAGENT_REQUEST_REFRESH_TICKS = 600

_last_publish_tick = {}


def _archive():
    from archive import archive
    return archive


def assigned_reagents_for(outpost_id):
    """
    Reagents this outpost's Bio Lab should be kept stocked with. Auto-seeds from
    DEFAULT_REAGENT_STOCK_TARGETS.keys() only the first time this outpost id has no
    stored entry at all; every subsequent call returns the stored list untouched -- a
    player's manual edit (e.g. dropping a reagent this save never needs) always wins.
    """
    archive = _archive()
    assignments = archive.get(OUTPOST_REAGENT_ASSIGNMENTS_KEY, {}) or {}
    if outpost_id in assignments:
        return list(assignments[outpost_id])

    computed = list(DEFAULT_REAGENT_STOCK_TARGETS.keys())
    assignments = dict(assignments)
    assignments[outpost_id] = computed
    archive.set(OUTPOST_REAGENT_ASSIGNMENTS_KEY, assignments)
    log.debug(f"assigned_reagents_for({outpost_id}): seeding default reagent list (first lookup) -> {computed}")
    return list(computed)


def reagent_stock_target_for(outpost_id, item_id):
    """
    Stockpile target (units) for item_id at outpost_id -- seed-once-then-editable,
    same convention as outpost_mining.stock_target_for(). Defaults to
    DEFAULT_REAGENT_STOCK_TARGETS.get(item_id, FALLBACK_REAGENT_STOCK_TARGET) so an
    unrecognized reagent (a future game update) still gets a sane starting point.
    """
    archive = _archive()
    targets = archive.get(OUTPOST_REAGENT_STOCK_TARGETS_KEY, {}) or {}
    outpost_targets = targets.get(outpost_id)
    if not isinstance(outpost_targets, dict):
        outpost_targets = None
    if outpost_targets is not None and item_id in outpost_targets:
        return outpost_targets[item_id]

    default = DEFAULT_REAGENT_STOCK_TARGETS.get(item_id, FALLBACK_REAGENT_STOCK_TARGET)
    targets = dict(targets)
    outpost_targets = dict(outpost_targets) if outpost_targets is not None else {}
    outpost_targets[item_id] = default
    targets[outpost_id] = outpost_targets
    archive.set(OUTPOST_REAGENT_STOCK_TARGETS_KEY, targets)
    log.debug(f"reagent_stock_target_for({outpost_id}, {item_id}): seeding default target {default} (first lookup)")
    return default


def publish_reagent_requests(outpost: "OutpostRef", curr_tick=None, force=False):
    """
    Publishes this remote outpost's reagent stock targets as pull requests
    (logistics_requests.publish_requests(), requester REQUESTER_ID, whole
    target as need tier, flagged buyable), so a Pioneer pull hauler homed here
    fetches them, buying at the Shop on home pickup. Recomputed at most once
    per REAGENT_REQUEST_REFRESH_TICKS per outpost unless force. "have" =
    logistics_requests.outpost_stock() (Warehouses + Drone Depots), the stock
    a remote Lab can load from. No-op for the home outpost: a home Lab buys
    its own reagents just in time.
    """
    outpost_id = getattr(outpost, "id", None)
    if outpost_id is None or getattr(outpost, "is_home", True):
        return False
    tick = curr_tick if curr_tick is not None else now_tick()
    last = _last_publish_tick.get(outpost_id)
    if not force and last is not None and 0 <= tick - last < REAGENT_REQUEST_REFRESH_TICKS:
        return False
    _last_publish_tick[outpost_id] = tick
    reagents = assigned_reagents_for(outpost_id)
    have = logistics_requests.outpost_stock(reagents, outpost)
    wants = {item_id: (reagent_stock_target_for(outpost_id, item_id), have.get(item_id, 0)) for item_id in reagents}
    wants = {item_id: pair for item_id, pair in wants.items() if pair[0] > 0}
    logistics_requests.publish_requests(outpost_id, REQUESTER_ID, wants, tick, buyable=True)
    short = sorted(item_id for item_id, (target, got) in wants.items() if got < target)
    log.debug(f"publish_reagent_requests({outpost_id}): {len(wants)} reagent(s), below target: {short}")
    return True
