# Outpost reagent-resupply scaffolding for a remote Bio Lab (docs/AI_CHEATSHEET.md,
# TODO.md Phase 4). Mirrors lib/outpost_mining.py's "seed once, then editable"
# convention exactly, adapted for reagents: the candidate set is small and fixed
# (unlike survey-derived ore assignment), so only the per-item stock TARGET needs
# seeding, and it's a per-reagent dict rather than one flat constant -- reagent
# prices vary enormously (docs/database/items_lab_reagents.md: 1cr to 1,000cr), so a
# single flat target would either starve the cheap ones or bankrupt the expensive
# ones this early in a save.

from storage import warehouse_stock
from outpost_mining import outpost_by_id

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
    if isinstance(outpost_targets, dict) and item_id in outpost_targets:
        return outpost_targets[item_id]

    default = DEFAULT_REAGENT_STOCK_TARGETS.get(item_id, FALLBACK_REAGENT_STOCK_TARGET)
    targets = dict(targets)
    outpost_targets = dict(outpost_targets) if isinstance(outpost_targets, dict) else {}
    outpost_targets[item_id] = default
    targets[outpost_id] = outpost_targets
    archive.set(OUTPOST_REAGENT_STOCK_TARGETS_KEY, targets)
    return default


def get_outpost_reagent_demand(outpost_id):
    """
    {item_id: deficit} for every reagent assigned to outpost_id, deficit = target -
    warehouse_stock (never total_stock -- see storage.warehouse_stock()'s docstring;
    a remote outpost's own deficit must not be masked by reagents sitting untouched
    back at home). Only positive deficits are included.
    """
    outpost = outpost_by_id(outpost_id)
    demand = {}
    for item_id in assigned_reagents_for(outpost_id):
        target = reagent_stock_target_for(outpost_id, item_id)
        have = warehouse_stock(item_id, outpost)
        deficit = target - have
        if deficit > 0:
            demand[item_id] = deficit
    return demand
