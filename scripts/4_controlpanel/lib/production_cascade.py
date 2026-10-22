# Network-wide Fabricator demand: the recipe input table, the blueprint and
# Fabricator-output demand cascades and the folded root/final targets.
#
# Every target is a priority ladder (lib/priority.py): [[prio, cum_units], ...]
# from the root that wants the item (manual order, blueprint, Supply Dock
# order, orders book) down to every intermediate, which inherits the prio of
# the shortfall it serves. The flat "keep at least N" number of a target is
# its ladder_total(); the int-shaped getters here return that.
from archive import archive
from components import component
from construction_plan import DEFAULT_PRIORITY, PLANNED_KEY, PRIORITY_KEY, clean_priorities
from game_clock import TickCache
from logistics_requests import aboard_units, active_requests, request_keep
from priority import BLOCKER, BUILD, MANUAL, blueprint_prio, deficits_text, ladder_add, ladder_add_levels, ladder_deficits, ladder_level, ladder_lower, ladder_max, ladder_raise, ladder_total
from production_core import FUEL_ASSEMBLER_OUTPUTS, _all_outposts, _default_fabricator, _default_smelter, construction_site_id, home_outpost_id, log
from production_demand_record import blueprint_entry, depths_entry, read_record
from production_docks import _dock_order_remaining, _dock_order_sites, dock_order_prios, dock_order_site_shares, dock_owed_at, order_prio_of
from production_orders import NO_CONSUMER_SITE, SITE_ORDER_REQUESTERS, get_manual_orders, manual_transit_wants, order_consumer_sites, order_ladders
from production_source import SourceCache, can_source_item
from swallow import swallowed

# Recipe input table ({output_item: {input_item: qty per output unit}}), built from the
# Fabricator + Smelter recipe lists. Recipes only change when research unlocks new ones,
# which changes the list lengths; the table is rebuilt then, or after this many ticks.
RECIPE_INDEX_TTL_TICKS = 6000

# keyed by (fabricator count, smelter count): a new key replaces the table
_RECIPE_INDEX = TickCache(RECIPE_INDEX_TTL_TICKS, single=True)
# keyed by the list lengths and the machine speeds the lists were read from: {output: (kind, recipe)}
_RECIPE_OUTPUTS = TickCache(RECIPE_INDEX_TTL_TICKS, single=True)

# Depth bound of every demand cascade: a generous bound against an accidental recipe cycle.
CASCADE_MAX_DEPTH = 6


def fabricator_unlocked_outputs(cache: "SourceCache | None" = None):
    """Set of item ids the default Fabricator can craft today (list_recipes()
    only lists unlocked recipes, docs/components/fabricator.md)."""
    if cache is not None:
        recipes = cache.fabricator_recipes()
    else:
        fabricator = _default_fabricator()
        try:
            recipes = fabricator.list_recipes() if fabricator and hasattr(fabricator, "list_recipes") else []
        except Exception as error:
            swallowed("production_cascade.fabricator_unlocked_outputs: fabricator.list_recipes", error)
            recipes = []
    return {r.output_item for r in recipes if getattr(r, "output_item", None)}


def totals(ladders):
    """{item_id: ladder_total} of {item_id: ladder}."""
    return {item_id: ladder_total(levels) for item_id, levels in ladders.items()}


def blueprint_demand_items(cache: "SourceCache | None" = None):
    """{item_id: gross demand} for every item any pending/paused Construction
    Blueprint needs, directly or via the recipe cascade
    (_cascade_blueprint_demand())."""
    return totals(_cascade_blueprint_demand(cache))


def _stock_fn(cache: "SourceCache | None"):
    """`held_stock(item_id)` of the SourceCache threaded through (a fresh one
    without): units on hand at home for netting, Inventory + home Warehouses
    + home Drone Depots -- the same count Fabricator targets and the Supply
    Dock net against, so every planner agrees on "enough"."""
    return (cache if cache is not None else SourceCache()).held_stock


def _recipe_lists(cache: "SourceCache | None" = None):
    """[Fabricator recipes, Smelter recipes] (a cache's memoized lists, else one list_recipes() each)."""
    if cache is not None:
        return [cache.fabricator_recipes(), cache.smelter_recipes()]
    lists = []
    for machine in (_default_fabricator(), _default_smelter()):
        if not machine or not hasattr(machine, "list_recipes"):
            lists.append([])
            continue
        try:
            lists.append(list(machine.list_recipes()))
        except Exception as error:
            swallowed("production_cascade._recipe_lists: machine.list_recipes", error)
            lists.append([])
    return lists


def _build_recipe_index(recipe_lists):
    """{output_item: {input_item: qty / output_count}}; the first recipe per output wins (Fabricator before Smelter)."""
    index = {}
    for recipes in recipe_lists:
        for recipe in recipes:
            output = getattr(recipe, "output_item", None)
            if not output or output in index:
                continue
            output_count = max(1, getattr(recipe, "output_count", 1))
            inputs = getattr(recipe, "inputs", {}) or {}
            index[output] = {in_id: qty / output_count for in_id, qty in inputs.items()}
    return index


def _build_recipe_outputs(cache: "SourceCache"):
    """{output_item: ("fabricator"|"smelter", Recipe)}; the first recipe per output wins (Fabricator before Smelter)."""
    outputs = {}
    for kind, recipes in (("fabricator", cache.fabricator_recipes()), ("smelter", cache.smelter_recipes())):
        for recipe in recipes:
            output = getattr(recipe, "output_item", None)
            if output and output not in outputs:
                outputs[output] = (kind, recipe)
    return outputs


def recipe_for_output(item_id, cache: "SourceCache"):
    """("fabricator"|"smelter", Recipe) building item_id, (None, None) when none does. The table is kept
    per script like _recipe_index(), keyed also by the source machines' speeds (recipe durations carry
    their Mk tier), and memoized on `cache` for its pass."""
    if cache._recipe_outputs is None:
        lists = (cache.fabricator_recipes(), cache.smelter_recipes())
        signature = (len(lists[0]), len(lists[1]), cache.recipe_source_speed("fabricator"), cache.recipe_source_speed("smelter"))
        cache._recipe_outputs = _RECIPE_OUTPUTS.get(lambda: _build_recipe_outputs(cache), signature)
    return cache._recipe_outputs.get(item_id, (None, None))


def _recipe_index(cache: "SourceCache | None" = None):
    """
    The recipe input table, kept per script for RECIPE_INDEX_TTL_TICKS and rebuilt
    early when a recipe list's length changes (a research unlock). Memoized on
    `cache` for the rest of its pass. Shared: treat it and its dicts as read-only.
    """
    if cache is not None and cache._recipe_index is not None:
        return cache._recipe_index
    lists = _recipe_lists(cache)
    signature = tuple(len(recipes) for recipes in lists)
    index = _RECIPE_INDEX.get(lambda: _build_recipe_index(lists), signature)
    if cache is not None:
        cache._recipe_index = index
    return index


def _recipe_inputs_for(item_id, cache: "SourceCache | None" = None):
    """{input_item_id: qty_per_output_unit} for whichever of Fabricator/
    Smelter builds item_id, or None if neither does. Shared by
    _cascade_blueprint_demand(), _cascade_fabricator_output_demand() and
    get_smelter_demands(). Reads the long-lived recipe table (_recipe_index());
    the returned dict is shared, treat it as read-only."""
    return _recipe_index(cache).get(item_id)


def _cascade_fabricator_output_demand(seed_targets, fabricator_outputs, cache: "SourceCache | None" = None, stock=None, supply=None):
    """
    Breadth-first demand cascade seeded from seed_targets ({item_id: ladder}:
    Fabricator stock targets/Supply Dock orders, restricted to items the
    Fabricator itself builds), propagated down through Fabricator recipe
    inputs that are THEMSELVES a Fabricator output -- e.g. Control Unit needs
    Circuit Panel, which is its own Fabricator recipe. Without this, a target
    set only on Control Unit (the order's own required item) never tells any
    Fabricator to build Circuit Panel, so Control Unit -- and every other
    Fabricator recipe needing it -- stalls forever on an input nothing ever
    produces. Same shortfall-only propagation and depth bound as
    _cascade_blueprint_demand(); intermediate raw/refined materials (e.g.
    iron_ingot) are left to the Smelter demand (get_smelter_demands()) and
    the site supply ore requests (lib/site_supply.py), not duplicated here.

    Each level of a parent's shortfall (ladder_deficits() against `stock`)
    cascades at its own prio, so an intermediate inherits the priority of the
    demand it serves; contributions from several parents sum (ladder_add()).

    Returns {item_id: ladder} for every reached item still short of stock,
    restricted to fabricator_outputs (Smelter-built intermediates aren't
    Fabricator targets -- get_smelter_demands() handles those).
    `stock` (item_id -> units) defaults to SourceCache.fab_have() at home,
    the count Fabricator readers net a target against; a site passes its own
    (get_site_fabricator_targets()).
    `supply(item_id, shortfall, prio) -> units` (optional) says how much of a
    non-seed item's shortfall (its top level at `prio`) arrives from
    elsewhere (in flight or to be shipped, see get_site_fabricator_targets()):
    those units come off that item's target (ladder_lower()) and are not
    cascaded into its inputs.
    An item whose recipe has an input with no known source (none on the
    network and can_source_item() false, e.g. a component whose recipe is
    still locked) is not cascaded: building its other inputs would only
    strand them.
    """
    log.start("_cascade_fabricator_output_demand", level="debug")
    source_cache = SourceCache() if cache is None else cache
    stock = stock or source_cache.fab_have
    seeds = set(seed_targets)
    targets = {}
    frontier = {item_id: [list(level) for level in levels] for item_id, levels in seed_targets.items()}
    depth = 0
    while frontier and depth < CASCADE_MAX_DEPTH:
        depth += 1
        next_frontier = {}
        for item_id, want in frontier.items():
            have = stock(item_id)
            deficits = ladder_deficits(want, have)
            shortfall = sum(missing for _prio, missing in deficits)
            covered = 0
            if supply is not None and shortfall > 0 and item_id not in seeds:
                covered = min(shortfall, supply(item_id, shortfall, deficits[0][0]))
            if item_id in fabricator_outputs:
                targets[item_id] = ladder_max(targets.get(item_id, []), ladder_lower(want, covered))
            if shortfall - covered <= 0:
                log.trace(f"_cascade_fabricator_output_demand depth={depth}: {item_id} has no shortfall (want={ladder_total(want)}), not cascading further")
                continue
            inputs = _recipe_inputs_for(item_id, cache)
            if not inputs:
                continue
            blocked = next((i for i in inputs if source_cache.network_stock(i) <= 0 and not can_source_item(i, source_cache)), None)
            if blocked is not None:
                log.debug(f"_cascade_fabricator_output_demand depth={depth}: {item_id} not cascaded, no known source for input '{blocked}'")
                continue
            # Covered units arrive for the most urgent levels first (the netting rule).
            deficits = ladder_deficits(ladder_lower(want, covered), have)
            for input_id, ratio in inputs.items():
                if input_id not in fabricator_outputs:
                    continue  # only cascade through other Fabricator-built intermediates
                child = next_frontier.setdefault(input_id, [])
                for prio, missing in deficits:
                    ladder_add(child, prio, missing * ratio)
                if log.verbose:
                    log.trace(f"_cascade_fabricator_output_demand depth={depth}: {item_id} short {deficits_text(deficits)} cascades {ratio:.2f}x into {input_id} -> {ladder_total(child):.2f}")
        frontier = next_frontier
    if depth >= CASCADE_MAX_DEPTH and frontier:
        log.debug(f"hit depth bound ({CASCADE_MAX_DEPTH}) with frontier still non-empty: {list(frontier.keys())}")
    log.end()
    return targets


def recipe_depths(cache: "SourceCache"):
    """{item_id: depth} of every Fabricator output below a root target: a
    root is 0, an input of a depth-d item is d + 1 (the deepest parent
    counts). lib/fabricator.py's choose_recipe() crafts the deeper item of
    one band first, since its parent cannot be built without it. The same
    for every Fabricator, so a usable demand record's copy is taken
    (production_demand_record.depths_entry()) before computing
    (compute_recipe_depths(), which the record's publishers call). Memoized
    on `cache`."""
    if cache._recipe_depth is not None:
        return cache._recipe_depth
    record, _state = read_record()
    depths = depths_entry(record) if record is not None else None
    if depths is not None:
        cache._recipe_depth = depths
        return depths
    return compute_recipe_depths(cache)


def compute_recipe_depths(cache: "SourceCache"):
    """recipe_depths() computed from fabricator_root_targets(), never from the record. Memoized on `cache`."""
    roots, _consumers, fabricator_outputs = fabricator_root_targets(cache)
    depths = {item_id: 0 for item_id in roots if item_id in fabricator_outputs}
    frontier = dict(depths)
    depth = 0
    while frontier and depth < CASCADE_MAX_DEPTH:
        depth += 1
        next_frontier = {}
        for item_id in frontier:
            for input_id in _recipe_inputs_for(item_id, cache) or {}:
                if input_id in fabricator_outputs and depths.get(input_id, -1) < depth:
                    depths[input_id] = depth
                    next_frontier[input_id] = depth
        frontier = next_frontier
    cache._recipe_depth = depths
    return depths


def _vehicle_cargo_counts(item_ids):
    """{item_id: units} of the given items currently aboard any ground
    vehicle (fleet.vehicles() + each vehicle's live cargo.stacks()). Only
    items with a non-zero count are returned."""
    counts = {}
    fleet = component("fleet")
    if not fleet or not hasattr(fleet, "vehicles"):
        return counts
    try:
        refs = fleet.vehicles()
    except Exception as error:
        swallowed("production_cascade._vehicle_cargo_counts: fleet.vehicles", error)
        return counts
    for ref in refs:
        vehicle = component(getattr(ref, "id", ""))
        cargo = getattr(vehicle, "cargo", None) if vehicle else None
        if not cargo or not hasattr(cargo, "stacks"):
            continue
        try:
            for stack in cargo.stacks():
                item_id = getattr(stack, "id", None)
                if item_id in item_ids:
                    counts[item_id] = counts.get(item_id, 0) + (getattr(stack, "count", 0) or 0)
        except Exception as error:
            swallowed("production_cascade._vehicle_cargo_counts: cargo.stacks", error)
            continue
    return {k: v for k, v in counts.items() if v > 0}


def blueprint_prios(cache: "SourceCache | None" = None):
    """(planned, priorities): the autoplay planner's blueprint ids
    (construction_plan.PLANNED_KEY) and {blueprint_id: construction.priority}
    (PRIORITY_KEY), read once per `cache`. priority.blueprint_prio() turns
    them into a job's prio: MANUAL for an operator-placed blueprint, BUILD for
    an autoplay job at priority 0, BUILD_AHEAD for plan-ahead jobs."""
    if cache is not None and cache._blueprint_prios is not None:
        return cache._blueprint_prios
    planned = archive.get(PLANNED_KEY, {})
    planned = set(planned) if isinstance(planned, dict) else set()
    priorities = clean_priorities(archive.get(PRIORITY_KEY, {}))
    result = (planned, priorities)
    if cache is not None:
        cache._blueprint_prios = result
    return result


def blueprint_required_ladders(cache: "SourceCache | None" = None):
    """{item_id: ladder} pending/paused Construction Blueprints still need as
    their own required_item (summed per prio across jobs, deduped by job id,
    each job at blueprint_prio()), minus units aboard vehicles that no
    hauler pickup already counts as stock (aboard_units()). The seed of
    _walk_blueprint_demand(). Memoized on `cache`."""
    if cache is not None and cache._blueprint_seeds is not None:
        return {i: [list(level) for level in l] for i, l in cache._blueprint_seeds.items()}
    frontier = {}
    bp = component("construction_blueprint")
    if bp:
        planned, priorities = blueprint_prios(cache)
        seen_jobs = set()
        for getter_name in ("pending_constructions", "paused_constructions"):
            getter = getattr(bp, getter_name, None)
            if not getter:
                continue
            try:
                for job in getter():
                    job_id = getattr(job, "id", "")
                    if job_id and job_id in seen_jobs:
                        continue
                    item_id = getattr(job, "required_item", None)
                    count = getattr(job, "required_count", 0)
                    if not item_id or count <= 0:
                        continue
                    if job_id:
                        seen_jobs.add(job_id)
                    prio = blueprint_prio(job_id in planned, priorities.get(job_id, DEFAULT_PRIORITY))
                    ladder_add(frontier.setdefault(item_id, []), prio, count)
            except Exception as error:
                swallowed("production_cascade.blueprint_required_items: getter", error)

    # A constructor Pioneer loads a whole batch for chained jobs before
    # driving out, and every job stays pending until actually built -- so
    # while the materials ride in its cargo they're in neither Inventory nor
    # a Warehouse, and the Fabricator would re-craft the full batch. Net
    # those out. A hauler's load is already stock (aboard_units() in
    # network_stock()), so only cargo beyond the aboard pickups comes off here.
    if frontier:
        aboard = aboard_units()
        for item_id, cargo in _vehicle_cargo_counts(frontier).items():
            carried = max(0, cargo - aboard.get(item_id, 0))
            frontier[item_id] = ladder_lower(frontier[item_id], carried)
            log.trace(f"{carried}x {item_id} already aboard vehicles -> seed demand {ladder_total(frontier[item_id])}")
        frontier = {i: l for i, l in frontier.items() if l}
    if cache is not None:
        cache._blueprint_seeds = {i: [list(level) for level in l] for i, l in frontier.items()}
    return frontier


def blueprint_required_items(cache: "SourceCache | None" = None):
    """{item_id: units} of blueprint_required_ladders()."""
    return totals(blueprint_required_ladders(cache))


def _cascade_blueprint_demand(cache: "SourceCache | None" = None):
    """Memoized on `cache` (one blueprint + fleet cargo walk per pass) -- see _walk_blueprint_demand()."""
    if cache is None:
        return _walk_blueprint_demand(None)
    if cache._blueprint_demand is None:
        cache._blueprint_demand = _walk_blueprint_demand(cache)
    return {i: [list(level) for level in l] for i, l in cache._blueprint_demand.items()}


def _walk_blueprint_demand(cache: "SourceCache | None"):
    """
    Breadth-first demand cascade seeded from pending/paused Construction
    Blueprint required_item/required_count (blueprint_required_ladders()),
    then propagated down through Fabricator and Smelter recipe inputs -- e.g.
    a Thermal Cap build's thermal_cap_kit demand cascades into titanium_ingot
    demand, which cascades into titanium_ore demand.

    At each tier, only that tier's *shortfall* (demand beyond the item's
    held stock at home, see _stock_fn()) propagates further down -- so a build that's
    mostly already satisfied by existing stock at some tier doesn't overstate
    demand for the tiers beneath it. Each level of the shortfall cascades at
    its own prio. Returns {item_id: ladder}, the gross demand accumulated for
    every item reached at any tier (not yet netted against its own stock --
    see get_construction_material_reservations() for that).

    Known limitation: an item reachable via more than one distinct path
    (e.g. two different blueprint items both consuming iron_ingot) nets its
    shortfall against the same stock snapshot independently at each
    occurrence, which can slightly overstate demand for a shared
    intermediate under a diamond-shaped recipe dependency. Not worth a full
    MRP-style low-level-code solve for this game's shallow (2-3 tier)
    recipe chains.
    """
    log.start("_cascade_blueprint_demand", level="debug")
    frontier = blueprint_required_ladders(cache)

    stock = _stock_fn(cache)
    total_needed = {}
    depth = 0
    while frontier and depth < CASCADE_MAX_DEPTH:
        depth += 1
        next_frontier = {}
        for item_id, want in frontier.items():
            ladder_add_levels(total_needed.setdefault(item_id, []), want)
            deficits = ladder_deficits(want, stock(item_id))
            if not deficits:
                log.trace(f"_cascade_blueprint_demand depth={depth}: {item_id} has no shortfall (want={ladder_total(want)}), not cascading further")
                continue
            inputs = _recipe_inputs_for(item_id, cache)
            if not inputs:
                continue
            for input_id, ratio in inputs.items():
                child = next_frontier.setdefault(input_id, [])
                for prio, missing in deficits:
                    ladder_add(child, prio, missing * ratio)
                if log.verbose:
                    log.trace(f"_cascade_blueprint_demand depth={depth}: {item_id} short {deficits_text(deficits)} cascades {ratio:.2f}x into {input_id} -> {ladder_total(child):.2f}")
        frontier = next_frontier

    if depth >= CASCADE_MAX_DEPTH and frontier:
        log.debug(f"hit depth bound ({CASCADE_MAX_DEPTH}) with frontier still non-empty: {list(frontier.keys())}")
    log.end()
    return total_needed


def blueprint_demand_wants(cache: "SourceCache | None" = None):
    """blueprint_demand_items() from a usable demand record (production_demand_record.blueprint_entry(),
    the same for every reader) when there is one, else computed: the gross construction cascade."""
    record, _state = read_record()
    wants = blueprint_entry(record) if record is not None else None
    return wants if wants is not None else blueprint_demand_items(cache)


def outranking_order_wants():
    """{item_id: units} the Fabricator order book (order_ladders()) wants at
    BUILD or above: floors that outrank every Supply Dock order (ORDER band),
    e.g. a FLEET Commission kit at MANUAL. Gross, like blueprint demand."""
    out = {}
    for item_id, levels in order_ladders().items():
        want = ladder_level(levels, BUILD)
        if want > 0:
            out[item_id] = want
    return out


def dock_protected_wants(cache: "SourceCache | None" = None):
    """{item_id: units} a Supply Dock must leave alone: gross blueprint demand
    (blueprint_demand_wants()) plus outranking_order_wants()."""
    wants = dict(blueprint_demand_wants(cache))
    for item_id, units in outranking_order_wants().items():
        wants[item_id] = wants.get(item_id, 0) + units
    return wants


def remote_dock_reservations(cache: "SourceCache | None" = None):
    """{item_id: units} a Supply Dock away from home leaves in its outpost's
    stock: outranking_order_wants() still missing from held stock at home
    (_stock_fn()). Those units are on their way home (site supply), so the
    dock may only take what is left beyond them."""
    stock_of = _stock_fn(cache)
    out = {}
    for item_id, want in outranking_order_wants().items():
        short = want - stock_of(item_id)
        if short > 0:
            out[item_id] = short
    return out


def get_construction_material_reservations(cache: "SourceCache | None" = None):
    """
    Returns {item_id: units} to protect (held stock at home, see
    _stock_fn()) for active Construction Blueprints, cascading down
    through Fabricator/Smelter recipes to intermediate materials and raw ore
    (see _cascade_blueprint_demand()) -- not just each blueprint's own
    required_item -- and for order-book floors that outrank Supply Dock
    orders (outranking_order_wants()). Capped at min(current stock, total demand) per item: never
    reserves more than what's both actually on hand and actually still needed.

    Used to stop the Supply Dock from shipping away stock an active build (or
    the production chain feeding it) is waiting on -- see supply_dock.py
    step()/pick_best_order(). The gross demand comes from a usable demand
    record (production_demand_record.blueprint_entry(), the same for every
    dock) when there is one, else from the cascade; the stock is always live.
    With a `cache`, reads its stock snapshot and memoized blueprint cascade.
    """
    reservations = {}
    stock_of = _stock_fn(cache)
    for item_id, want in dock_protected_wants(cache).items():
        stock = stock_of(item_id)
        reserve = min(stock, want)
        if reserve > 0:
            reservations[item_id] = reserve
    return reservations


def dock_delivery_targets(item_id, count, outpost: "OutpostRef | None" = None, cache: "SourceCache | None" = None):
    """
    [(dock_id, units)] a producer at `outpost` may push `count` fresh units of
    item_id into directly (storage.push_to_targets()): the local Supply Docks
    whose order still owes it (production_docks.dock_owed_at()). Blueprint
    demand and order-book floors above the dock band come first, as in the
    docks' own loading (get_construction_material_reservations()): with
    such demand for the item (dock_protected_wants()), only held stock +
    count beyond it may ship.
    """
    targets = dock_owed_at(item_id, outpost)
    if not targets:
        return []
    want = dock_protected_wants(cache).get(item_id, 0)
    if want <= 0:
        return targets
    free = max(0, _stock_fn(cache)(item_id) + count - want)
    log.debug(f"dock push {item_id}: protected demand {want}, {free} of {count} free to ship")
    return [(dock_id, min(owed, free)) for dock_id, owed in targets if min(owed, free) > 0]


_WARNED_UNKNOWN_MANUAL_ITEMS = set()


def builder_reserve(cache: "SourceCache"):
    """{item_id: units} of the reserve at the Constructor's home
    (construction_site_id()): every request entry there with a "keep"
    (logistics_requests.request_keep(), set by lib/site_supply.py on the
    Fabricator-built construction stock), as units held there capped at
    that keep. Network stock that a Supply Dock order does not count."""
    site_id = construction_site_id()
    entries = active_requests().get(site_id, {})
    keep = {i: request_keep(e) for i, e in entries.items() if isinstance(e, dict) and request_keep(e) > 0}
    if not keep:
        return {}
    outpost = next((o for o in _all_outposts() if getattr(o, "id", None) == site_id), None)
    if outpost is None:
        return {}
    held = {i: min(units, cache.held_stock(i, outpost)) for i, units in keep.items()}
    reserve = {i: units for i, units in held.items() if units > 0}
    log.debug(f"builder_reserve: {reserve or 'none'} kept at {site_id}")
    return reserve


def fabricator_target_ladders(cache: "SourceCache | None" = None):
    """{item_id: ladder}: desired finished-goods quantities for Fabricator
    planning, every root (fabricator_root_targets()) plus every
    Fabricator-built intermediate the roots' shortfalls cascade into
    (_cascade_fabricator_output_demand()), each level at the prio of the
    demand it serves.

    With a `cache` (SourceCache), the result is memoized on it for the rest
    of that pass: this is the single most expensive demand helper (manual
    orders, every dock order, the blueprint cascade and the Fabricator output
    cascade, each walking stock). A copy is returned so a caller mutating its
    result can't poison the memo."""
    log.start("fabricator_target_ladders", level="debug")
    if cache is not None and cache._fabricator_targets is not None:
        _ret = {i: [list(level) for level in l] for i, l in cache._fabricator_targets.items()}
        log.end()
        return _ret

    targets, _consumers, fabricator_outputs = fabricator_root_targets(cache)

    # Cascade demand for a targeted Fabricator output down through its own
    # recipe inputs when those inputs are themselves Fabricator-built (e.g.
    # Control Unit needs Circuit Panel) -- see
    # _cascade_fabricator_output_demand(). Without this, an order/blueprint
    # target set only on the top-level item (Control Unit) never becomes a
    # target for the intermediate (Circuit Panel), so no Fabricator ever
    # builds it and the top-level item stalls forever waiting on stock that
    # nothing produces.
    for item_id, levels in _cascade_fabricator_output_demand(targets, fabricator_outputs, cache).items():
        targets[item_id] = ladder_max(targets.get(item_id, []), levels)
        log.trace(f"output-demand cascade raises target for {item_id} -> {targets[item_id]}")

    log.trace(f"final targets={targets}")
    if cache is not None:
        cache._fabricator_targets = {i: [list(level) for level in l] for i, l in targets.items()}
    log.end()
    return targets


def get_fabricator_targets(cache: "SourceCache | None" = None):
    """{item_id: units} of fabricator_target_ladders(): the flat "keep at least N" targets."""
    return totals(fabricator_target_ladders(cache))


@log.block()
def fabricator_root_targets(cache: "SourceCache | None" = None):
    """
    (roots, consumers, fabricator_outputs): the root Fabricator targets
    before the intermediate cascade -- manual orders (MANUAL), the orders
    book (each requester's prio), Supply Dock orders (the dock planner's
    prio) and blueprint demand (blueprint_prio()), max()-folded per item
    into {item_id: ladder} -- plus {item_id: {site_id: ladder}}, where each
    root is consumed (its Supply Dock's outpost for dock orders,
    construction_site_id() for a blueprint's own required_item, home for
    everything else; dock order items the Fabricator can't build and
    blueprint items included, for hauling), plus the set of
    Fabricator-buildable item ids.
    Memoized on `cache`.
    """
    if cache is not None and cache._root_targets is not None:
        roots, consumers, outputs = cache._root_targets
        return _copy_ladders(roots), {i: _copy_ladders(c) for i, c in consumers.items()}, set(outputs)

    targets = {}
    home_id = home_outpost_id()
    home_wants = {}  # the non-dock roots, all consumed at home

    fabricator_outputs = fabricator_unlocked_outputs(cache)

    # Manual build orders (get_manual_orders()) count units still to BUILD: consume_manual_order()
    # counts them down as units leave a Fabricator, so stock already built never satisfies the
    # rest. The order folds in as network stock + staged units + remaining (max()'d like every
    # other source below), which root_remaining() nets back down to remaining - pipeline, at
    # MANUAL prio.
    #
    # A manual order is hand-typed straight into the Data Archive Notebook (no validation on
    # write), so a typo'd/renamed item_id (e.g. "small_drone" instead of "drone_small") silently
    # never matches any recipe's output_item -- it still gets folded into targets here, but no
    # Fabricator ever produces a candidate for it, and since nothing else was set either, the
    # machine prints nothing at all (see lib/fabricator.py's step()/choose_recipe()). Warn once per
    # script run so a bad key doesn't fail completely silently. fabricator_outputs only reflects
    # the default Fabricator's currently unlocked recipes, so this can false-positive for an item
    # only a different Fabricator (or a not-yet-unlocked recipe) can build -- it's a heads-up, not
    # proof the order is unfulfillable.
    manual_cache = cache if cache is not None else SourceCache()
    for item_id, quantity in get_manual_orders().items():
        ladder_raise(targets.setdefault(item_id, []), MANUAL, manual_cache.network_stock(item_id) + manual_cache.staged_units(item_id) + quantity)
        ladder_raise(home_wants.setdefault(item_id, []), MANUAL, quantity)
        log.trace(f"get_fabricator_targets: manual order raises target for {item_id} -> {targets[item_id]}")
        if fabricator_outputs and item_id not in fabricator_outputs and item_id not in FUEL_ASSEMBLER_OUTPUTS and item_id not in _WARNED_UNKNOWN_MANUAL_ITEMS:
            _WARNED_UNKNOWN_MANUAL_ITEMS.add(item_id)
            log.level("warn").print(f"[production] Warning: fabricator.manual_orders has '{item_id}' ({quantity}x), which doesn't match any known Fabricator recipe output. Check for a typo/renamed item_id.")

    # The orders book (production_orders.order_ladders(): fleet parts, site
    # stockpiles, Terraformer batches, key-unlock look-ahead): same max() fold,
    # each level at the prio its requester gave it. Site orders
    # (SITE_ORDER_REQUESTERS) raise the target only: their sites request the
    # items themselves. A requester naming its site (order_consumer_sites()) is
    # consumed there instead of at home, or nowhere for NO_CONSUMER_SITE.
    for item_id, levels in order_ladders().items():
        targets[item_id] = ladder_max(targets.get(item_id, []), levels)
        log.trace(f"get_fabricator_targets: order book raises target for {item_id} -> {targets[item_id]}")
    sited = order_consumer_sites()
    for item_id, levels in order_ladders(skip=tuple(SITE_ORDER_REQUESTERS) + tuple(sited)).items():
        home_wants[item_id] = ladder_max(home_wants.get(item_id, []), levels)
    site_wants = {}  # {site_id: {item_id: ladder}} of the sited requesters
    for site_id in set(sited.values()) - {NO_CONSUMER_SITE}:
        requesters = [r for r, s in sited.items() if s == site_id and r not in SITE_ORDER_REQUESTERS]
        site_wants[site_id] = order_ladders(only=requesters)

    order_sites = _dock_order_sites()
    consumers = {}
    dock_remaining = _dock_order_remaining()
    prios = dock_order_prios() if dock_remaining else {}
    if cache is not None:
        cache._order_prios = prios
    # The reserve at the Constructor's home (builder_reserve()) is kept for
    # blueprints: a dock order builds its own units on top of it.
    reserve = builder_reserve(manual_cache) if dock_remaining else {}
    for order_id, remaining_by_item in dock_remaining.items():
        prio = order_prio_of(order_id, prios)
        for item_id, remaining in remaining_by_item.items():
            shares = dock_order_site_shares(remaining, order_sites.get(order_id) or {home_id: 1})
            for site_id, share in shares.items():
                site = consumers.setdefault(item_id, {})
                ladder_raise(site.setdefault(site_id, []), prio, share)
            # Only order items the Fabricator can actually build become
            # targets; other order items (raw/mined) are handled by
            # the dock demand loop in get_material_demands() and must
            # not be double-counted here.
            if item_id not in targets and item_id not in fabricator_outputs:
                continue
            kept = reserve.get(item_id, 0) if remaining > 0 else 0
            ladder_raise(targets.setdefault(item_id, []), prio, remaining + kept)
            log.trace(f"get_fabricator_targets: dock order {order_id} (prio {prio}) raises target for {item_id} -> {targets[item_id]} (remaining={remaining}, reserve={kept})")

    # Fold in Construction Blueprint demand for items the Fabricator can
    # actually build (e.g. thermal_cap_kit) -- a queued build could otherwise
    # sit forever with nothing ever telling the Fabricator to craft it. Uses
    # the raw demand cascade, not get_construction_material_reservations()'s
    # netted (capped-at-current-stock) numbers -- a target must reflect how
    # much still needs to exist, not how much can currently be reserved.
    # max()'d against the existing target, same as the Supply Dock order
    # handling above -- targets are a steady-state "keep at least N in
    # Inventory" floor, not additive per demand source: the standing stock
    # buffer IS what a blueprint (or order) draws from, and choose_recipe()
    # already nets target-vs-current to rebuild it after that draw, so
    # adding would just over-target and waste materials/time.
    for item_id, levels in _cascade_blueprint_demand(cache).items():
        if item_id in fabricator_outputs:
            targets[item_id] = ladder_max(targets.get(item_id, []), levels)
            log.trace(f"get_fabricator_targets: blueprint cascade raises target for {item_id} -> {targets[item_id]}")

    # Stock targets and manual/book orders are consumed at home (Inventory
    # side), site orders excepted. A blueprint's own required_item is consumed where the
    # Constructor Pioneer loads it (construction_site_id()); the intermediates
    # beneath it are Fabricator inputs, consumed at whichever fab site builds
    # the item, so they are no consumer root.
    # Manual-order units built off home stay wanted at home until they arrive
    # (MANUAL_TRANSIT_KEY); no build target, they already exist, so they are
    # a BLOCKER want: nothing more arrives by waiting.
    for item_id, qty in manual_transit_wants(cache).items():
        ladder_raise(home_wants.setdefault(item_id, []), BLOCKER, qty)
    for item_id, levels in home_wants.items():
        site = consumers.setdefault(item_id, {})
        site[home_id] = ladder_max(site.get(home_id, []), levels)
    for site_id, wants in site_wants.items():
        for item_id, levels in wants.items():
            site = consumers.setdefault(item_id, {})
            site[site_id] = ladder_max(site.get(site_id, []), levels)
            log.trace(f"fabricator_root_targets: order book needs {ladder_total(levels)}x {item_id} at {site_id}")
    seeds = blueprint_required_ladders(cache)
    if seeds:
        builder_site = construction_site_id()
        for item_id, levels in seeds.items():
            site = consumers.setdefault(item_id, {})
            site[builder_site] = ladder_max(site.get(builder_site, []), levels)
            log.trace(f"fabricator_root_targets: blueprint needs {ladder_total(levels)}x {item_id} at {builder_site}")

    targets = {i: l for i, l in targets.items() if l}
    if cache is not None:
        cache._root_targets = (_copy_ladders(targets), {i: _copy_ladders(c) for i, c in consumers.items()}, set(fabricator_outputs))
    return targets, consumers, fabricator_outputs


def _copy_ladders(ladders):
    return {key: [list(level) for level in levels] for key, levels in ladders.items()}
