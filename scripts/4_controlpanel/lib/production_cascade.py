# Network-wide Fabricator demand: the recipe input table, the blueprint and
# Fabricator-output demand cascades and the folded root/final targets.
from components import component
from swallow import swallowed
from production_core import construction_site_id, FUEL_ASSEMBLER_OUTPUTS, home_outpost_id, log, _all_outposts, _default_fabricator, _default_smelter
from production_docks import dock_owed_at, _dock_order_remaining, _dock_order_sites
from production_source import SourceCache
from production_orders import get_backlog_orders, get_manual_orders, get_upgrade_orders, manual_transit_wants, SITE_ORDER_REQUESTERS
from game_clock import now_tick
from logistics_requests import active_requests, request_keep


# Recipe input table ({output_item: {input_item: qty per output unit}}), built from the
# Fabricator + Smelter recipe lists. Recipes only change when research unlocks new ones,
# which changes the list lengths; the table is rebuilt then, or after this many ticks.
RECIPE_INDEX_TTL_TICKS = 6000

# {"index": (tick, (fabricator count, smelter count), table)}
_RECIPE_INDEX_MEMO = {}


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
    return {getattr(r, "output_item", None) for r in recipes} - {None}


def blueprint_demand_items(cache: "SourceCache | None" = None):
    """{item_id: gross demand} for every item any pending/paused Construction
    Blueprint needs, directly or via the recipe cascade
    (_cascade_blueprint_demand()). choose_recipe()'s tier 2 while the item's
    stock plus pipeline is below that demand."""
    return _cascade_blueprint_demand(cache)


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
    for component in (_default_fabricator(), _default_smelter()):
        if not component or not hasattr(component, "list_recipes"):
            lists.append([])
            continue
        try:
            lists.append(list(component.list_recipes()))
        except Exception as error:
            swallowed("production_cascade._recipe_lists: component.list_recipes", error)
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
    now = now_tick()
    memo = _RECIPE_INDEX_MEMO.get("index")
    if memo is not None and memo[1] == signature and 0 <= now - memo[0] < RECIPE_INDEX_TTL_TICKS:
        index = memo[2]
    else:
        index = _build_recipe_index(lists)
        _RECIPE_INDEX_MEMO["index"] = (now, signature, index)
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
    Breadth-first demand cascade seeded from seed_targets (Fabricator stock
    targets/Supply Dock orders, restricted to items the Fabricator itself
    builds), propagated down through Fabricator recipe inputs that are
    THEMSELVES a Fabricator output -- e.g. Control Unit needs Circuit Panel,
    which is its own Fabricator recipe. Without this, a target set only on
    Control Unit (the order's own required item) never tells any Fabricator
    to build Circuit Panel, so Control Unit -- and every other Fabricator
    recipe needing it -- stalls forever on an input nothing ever produces.
    Same shortfall-only propagation and depth bound as
    _cascade_blueprint_demand(); intermediate raw/refined materials (e.g.
    iron_ingot) are left to the Smelter demand (get_smelter_demands()) and
    the site supply ore requests (lib/site_supply.py), not duplicated here.

    Returns {item_id: target_quantity} for every reached item still short of
    stock, restricted to fabricator_outputs (Smelter-built intermediates
    aren't Fabricator targets -- get_smelter_demands() handles those).
    `stock` overrides the stock read (item_id -> units), e.g. one site's
    local stock for get_site_fabricator_targets().
    `supply(item_id, shortfall) -> units` (optional) says how much of a
    non-seed item's shortfall arrives from elsewhere (in flight or to be
    shipped, see get_site_fabricator_targets()): those units come off that
    item's target and are not cascaded into its inputs.
    """
    log.start("_cascade_fabricator_output_demand", level="debug")
    stock = stock or _stock_fn(cache)
    seeds = set(seed_targets)
    targets = {}
    frontier = dict(seed_targets)
    depth = 0
    while frontier and depth < 6:  # same generous bound as _cascade_blueprint_demand()
        depth += 1
        next_frontier = {}
        for item_id, want in frontier.items():
            shortfall = max(0, want - stock(item_id))
            covered = 0
            if supply is not None and shortfall > 0 and item_id not in seeds:
                covered = min(shortfall, supply(item_id, shortfall))
                shortfall -= covered
            if item_id in fabricator_outputs:
                targets[item_id] = max(targets.get(item_id, 0), want - covered)
            if shortfall <= 0:
                log.trace(f"_cascade_fabricator_output_demand depth={depth}: {item_id} has no shortfall (want={want}), not cascading further")
                continue
            inputs = _recipe_inputs_for(item_id, cache)
            if not inputs:
                continue
            for input_id, ratio in inputs.items():
                if input_id not in fabricator_outputs:
                    continue  # only cascade through other Fabricator-built intermediates
                next_frontier[input_id] = next_frontier.get(input_id, 0) + (shortfall * ratio)
                log.trace(f"_cascade_fabricator_output_demand depth={depth}: {item_id} shortfall={shortfall:.2f} cascades {ratio:.2f}x into {input_id} -> {next_frontier[input_id]:.2f}")
        frontier = next_frontier
    if depth >= 6 and frontier:
        log.debug(f"hit depth bound (6) with frontier still non-empty: {list(frontier.keys())}")
    log.end()
    return targets


def get_manual_order_blocking_items(fabricator_outputs, orders=None, cache: "SourceCache | None" = None):
    """
    Set of Fabricator-output item_ids that an active manual build order
    (get_manual_orders(), or the `orders` dict given instead -- e.g.
    get_upgrade_orders()) transitively needs as an INPUT -- e.g. machine_frame
    when a manual order asks for drone_service_station_kit -- excluding the
    manually-ordered item itself. Same shortfall-only breadth-first walk as
    _cascade_fabricator_output_demand(), just seeded from manual orders only
    and returning the reached item_ids rather than their quantities.

    A manual order jumps every other demanded recipe in choose_recipe()
    regardless of shortfall size (see get_fabricator_targets()'s docstring),
    but a manual order for e.g. drone_service_station_kit can't itself be
    built while machine_frame stock is 0 and nothing is producing it --
    can_source_item() only checks that SOME recipe path exists, not that
    anything is actually in flight, so a Fabricator holding that manual
    order kept re-selecting it forever instead of ever pivoting to build the
    missing intermediate. Items in this set outrank even the manual orders
    themselves in choose_recipe()'s priority order, since the manual order
    is provably stuck without them first.
    """
    log.start("get_manual_order_blocking_items", level="debug")
    stock = _stock_fn(cache)
    if orders is None:
        # Manual orders count units still to build (see get_fabricator_targets()), not a floor.
        frontier = {item_id: stock(item_id) + qty for item_id, qty in get_manual_orders().items() if item_id in fabricator_outputs}
    else:
        frontier = {item_id: qty for item_id, qty in orders.items() if item_id in fabricator_outputs}
    blocking = set()
    depth = 0
    while frontier and depth < 6:  # same generous bound as the sibling cascades
        depth += 1
        next_frontier = {}
        for item_id, want in frontier.items():
            shortfall = max(0, want - stock(item_id))
            if shortfall <= 0:
                log.trace(f"get_manual_order_blocking_items depth={depth}: {item_id} has no shortfall (want={want}), not cascading further")
                continue
            inputs = _recipe_inputs_for(item_id, cache)
            if not inputs:
                continue
            for input_id, ratio in inputs.items():
                if input_id not in fabricator_outputs:
                    continue  # only cascade through other Fabricator-built intermediates
                blocking.add(input_id)
                next_frontier[input_id] = next_frontier.get(input_id, 0) + (shortfall * ratio)
                log.trace(f"get_manual_order_blocking_items depth={depth}: {item_id} shortfall={shortfall:.2f} cascades {ratio:.2f}x into {input_id} -> {next_frontier[input_id]:.2f}")
        frontier = next_frontier
    if depth >= 6 and frontier:
        log.debug(f"hit depth bound (6) with frontier still non-empty: {list(frontier.keys())}")
    log.end()
    return blocking


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
        vehicle = component(getattr(ref, "id", None))
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


def blueprint_required_items(cache: "SourceCache | None" = None):
    """{item_id: units} pending/paused Construction Blueprints still need as
    their own required_item (summed across jobs, deduped by job id), minus
    units already aboard vehicles. The seed of _walk_blueprint_demand().
    Memoized on `cache`."""
    if cache is not None and cache._blueprint_seeds is not None:
        return dict(cache._blueprint_seeds)
    frontier = {}
    bp = component("construction_blueprint")
    if bp:
        seen_jobs = set()
        for getter_name in ("pending_constructions", "paused_constructions"):
            getter = getattr(bp, getter_name, None)
            if not getter:
                continue
            try:
                for job in getter():
                    job_id = getattr(job, "id", None)
                    if job_id and job_id in seen_jobs:
                        continue
                    item_id = getattr(job, "required_item", None)
                    count = getattr(job, "required_count", 0)
                    if not item_id or count <= 0:
                        continue
                    if job_id:
                        seen_jobs.add(job_id)
                    frontier[item_id] = frontier.get(item_id, 0) + count
            except Exception as error:
                swallowed("production_cascade.blueprint_required_items: getter", error)

    # A constructor Pioneer loads a whole batch for chained jobs before
    # driving out, and every job stays pending until actually built -- so
    # while the materials ride in its cargo they're in neither Inventory nor
    # a Warehouse, and the Fabricator re-crafted the full batch (seen live:
    # 3 Oil Pump blueprints -> 6 pumps built, 3 left over). Net those out.
    if frontier:
        for item_id, carried in _vehicle_cargo_counts(frontier).items():
            frontier[item_id] = max(0, frontier[item_id] - carried)
            log.trace(f"{carried}x {item_id} already aboard vehicles -> seed demand {frontier[item_id]}")
    if cache is not None:
        cache._blueprint_seeds = dict(frontier)
    return frontier


def _cascade_blueprint_demand(cache: "SourceCache | None" = None):
    """Memoized on `cache` (one blueprint + fleet cargo walk per pass) -- see _walk_blueprint_demand()."""
    if cache is None:
        return _walk_blueprint_demand(None)
    if cache._blueprint_demand is None:
        cache._blueprint_demand = _walk_blueprint_demand(cache)
    return dict(cache._blueprint_demand)


def _walk_blueprint_demand(cache: "SourceCache | None"):
    """
    Breadth-first demand cascade seeded from pending/paused Construction
    Blueprint required_item/required_count (summed across jobs, deduped by
    job id), then propagated down through Fabricator and Smelter recipe
    inputs -- e.g. a Thermal Cap build's thermal_cap_kit demand cascades into
    titanium_ingot demand, which cascades into titanium_ore demand.

    At each tier, only that tier's *shortfall* (demand beyond the item's
    held stock at home, see _stock_fn()) propagates further down -- so a build that's
    mostly already satisfied by existing stock at some tier doesn't overstate
    demand for the tiers beneath it. Returns {item_id: total_demand}, the
    gross demand accumulated for every item reached at any tier (not yet
    netted against its own stock -- see get_construction_material_reservations()
    for that).

    Known limitation: an item reachable via more than one distinct path
    (e.g. two different blueprint items both consuming iron_ingot) nets its
    shortfall against the same stock snapshot independently at each
    occurrence, which can slightly overstate demand for a shared
    intermediate under a diamond-shaped recipe dependency. Not worth a full
    MRP-style low-level-code solve for this game's shallow (2-3 tier)
    recipe chains.
    """
    log.start("_cascade_blueprint_demand", level="debug")
    frontier = blueprint_required_items(cache)

    stock = _stock_fn(cache)
    total_needed = {}
    depth = 0
    while frontier and depth < 6:  # generous bound against an accidental recipe cycle
        depth += 1
        next_frontier = {}
        for item_id, want in frontier.items():
            total_needed[item_id] = total_needed.get(item_id, 0) + want
            shortfall = max(0, want - stock(item_id))
            if shortfall <= 0:
                log.trace(f"_cascade_blueprint_demand depth={depth}: {item_id} has no shortfall (want={want}), not cascading further")
                continue
            inputs = _recipe_inputs_for(item_id, cache)
            if not inputs:
                continue
            for input_id, ratio in inputs.items():
                next_frontier[input_id] = next_frontier.get(input_id, 0) + (shortfall * ratio)
                log.trace(f"_cascade_blueprint_demand depth={depth}: {item_id} shortfall={shortfall:.2f} cascades {ratio:.2f}x into {input_id} -> {next_frontier[input_id]:.2f}")
        frontier = next_frontier

    if depth >= 6 and frontier:
        log.debug(f"hit depth bound (6) with frontier still non-empty: {list(frontier.keys())}")
    log.end()
    return total_needed


def get_construction_material_reservations(cache: "SourceCache | None" = None):
    """
    Returns {item_id: units} to protect (held stock at home, see
    _stock_fn()) for active Construction Blueprints, cascading down
    through Fabricator/Smelter recipes to intermediate materials and raw ore
    (see _cascade_blueprint_demand()) -- not just each blueprint's own
    required_item. Capped at min(current stock, total demand) per item: never
    reserves more than what's both actually on hand and actually still needed.

    Used to stop the Supply Dock from shipping away stock an active build (or
    the production chain feeding it) is waiting on -- see supply_dock.py
    step()/pick_best_order(). With a `cache`, reads its stock snapshot and
    memoized blueprint cascade.
    """
    reservations = {}
    stock_of = _stock_fn(cache)
    for item_id, want in _cascade_blueprint_demand(cache).items():
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
    demand comes first, as in the docks' own loading
    (get_construction_material_reservations()): with gross blueprint demand
    for the item, only stock + count beyond that demand may ship.
    """
    targets = dock_owed_at(item_id, outpost)
    if not targets:
        return []
    want = _cascade_blueprint_demand(cache).get(item_id, 0)
    if want <= 0:
        return targets
    free = max(0, _stock_fn(cache)(item_id) + count - want)
    log.debug(f"dock push {item_id}: blueprint demand {want}, {free} of {count} free to ship")
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


def get_fabricator_targets(cache: "SourceCache | None" = None):
    """Returns desired finished-goods quantities for Fabricator planning.

    With a `cache` (SourceCache), the result is memoized on it for the rest
    of that pass: this is the single most expensive demand helper (manual
    orders, every dock order, the blueprint cascade and the Fabricator output
    cascade, each walking stock), and get_material_demands() alone used to
    rebuild it once per Fabricator via get_fabricator_active_recipe(). A copy
    is returned so a caller mutating its result can't poison the memo."""
    log.start("get_fabricator_targets", level="debug")
    if cache is not None and cache._fabricator_targets is not None:
        _ret = dict(cache._fabricator_targets)
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
    for item_id, count in _cascade_fabricator_output_demand(targets, fabricator_outputs, cache).items():
        targets[item_id] = max(targets.get(item_id, 0), count)
        log.trace(f"output-demand cascade raises target for {item_id} -> {targets[item_id]} (cascaded={count})")

    log.trace(f"final targets={targets}")
    if cache is not None:
        cache._fabricator_targets = dict(targets)
    log.end()
    return targets


def fabricator_root_targets(cache: "SourceCache | None" = None):
    """
    (roots, consumers, fabricator_outputs): the root Fabricator targets
    before the intermediate cascade -- manual orders, upgrade and backlog
    orders, Supply Dock orders and blueprint demand, max()-folded per
    item into {item_id: qty} -- plus {item_id: {site_id: qty}}, where each
    root is consumed (its Supply Dock's outpost for dock orders,
    construction_site_id() for a blueprint's own required_item, home for
    everything else; dock order items the Fabricator can't build and
    blueprint items included, for hauling), plus the set of
    Fabricator-buildable item ids.
    Memoized on `cache`.
    """
    log.start("fabricator_root_targets", level="debug")
    if cache is not None and cache._root_targets is not None:
        roots, consumers, outputs = cache._root_targets
        _ret = dict(roots), {i: dict(c) for i, c in consumers.items()}, set(outputs)
        log.end()
        return _ret

    targets = {}
    home_id = home_outpost_id()
    home_wants = {}  # the non-dock roots, all consumed at home

    fabricator_outputs = set()
    if cache is not None:
        recipes = cache.fabricator_recipes()
    else:
        fabricator = _default_fabricator()
        try:
            recipes = fabricator.list_recipes() if fabricator and hasattr(fabricator, "list_recipes") else []
        except Exception as error:
            swallowed("production_cascade.get_fabricator_targets: fabricator.list_recipes", error)
            recipes = []
    for recipe in recipes:
        output_item = getattr(recipe, "output_item", None)
        if output_item:
            fabricator_outputs.add(output_item)

    # Manual build orders (get_manual_orders()) count units still to BUILD: consume_manual_order()
    # counts them down as units leave a Fabricator, so stock already built never satisfies the
    # rest. The order folds in as network stock + remaining (max()'d like every other source
    # below), which root_remaining() nets back down to remaining - pipeline. Priority over
    # other demanded recipes (build these first regardless of shortfall size) is handled separately
    # in lib/fabricator.py's choose_recipe(), which needs get_manual_orders() itself, not just the
    # folded-in quantity, to tell which candidates to jump ahead.
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
        targets[item_id] = max(targets.get(item_id, 0), manual_cache.network_stock(item_id) + quantity)
        home_wants[item_id] = max(home_wants.get(item_id, 0), quantity)
        log.trace(f"get_fabricator_targets: manual order raises target for {item_id} -> {targets[item_id]}")
        if fabricator_outputs and item_id not in fabricator_outputs and item_id not in FUEL_ASSEMBLER_OUTPUTS and item_id not in _WARNED_UNKNOWN_MANUAL_ITEMS:
            _WARNED_UNKNOWN_MANUAL_ITEMS.add(item_id)
            log.level("warn").print(f"[production] Warning: fabricator.manual_orders has '{item_id}' ({quantity}x), which "
                  f"doesn't match any known Fabricator recipe output. Check for a typo/renamed item_id.")

    # Fleet upgrade orders (get_upgrade_orders()): same max() fold as manual
    # orders; their lower priority is again choose_recipe()'s job.
    # Site orders (SITE_ORDER_REQUESTERS) raise the target only: their sites
    # request the items themselves.
    for item_id, quantity in get_upgrade_orders().items():
        targets[item_id] = max(targets.get(item_id, 0), quantity)
        log.trace(f"get_fabricator_targets: fleet upgrade order raises target for {item_id} -> {targets[item_id]}")
    for item_id, quantity in get_upgrade_orders(skip=SITE_ORDER_REQUESTERS).items():
        home_wants[item_id] = max(home_wants.get(item_id, 0), quantity)

    # Backlog orders (get_backlog_orders()): same fold; choose_recipe() ranks
    # the part above every other floor last (tier 5).
    for item_id, quantity in get_backlog_orders().items():
        targets[item_id] = max(targets.get(item_id, 0), quantity)
        log.trace(f"get_fabricator_targets: backlog order raises target for {item_id} -> {targets[item_id]}")
    for item_id, quantity in get_backlog_orders(skip=SITE_ORDER_REQUESTERS).items():
        home_wants[item_id] = max(home_wants.get(item_id, 0), quantity)

    order_sites = _dock_order_sites()
    consumers = {}
    dock_remaining = _dock_order_remaining()
    # The reserve at the Constructor's home (builder_reserve()) is kept for
    # blueprints: a dock order builds its own units on top of it.
    reserve = builder_reserve(manual_cache) if dock_remaining else {}
    for order_id, remaining_by_item in dock_remaining.items():
        for item_id, remaining in remaining_by_item.items():
            for site_id in order_sites.get(order_id, (home_id,)):
                site = consumers.setdefault(item_id, {})
                site[site_id] = max(site.get(site_id, 0), remaining)
            # Only order items the Fabricator can actually build become
            # targets; other order items (raw/mined) are handled by
            # the dock demand loop in get_material_demands() and must
            # not be double-counted here.
            if item_id not in targets and item_id not in fabricator_outputs:
                continue
            kept = reserve.get(item_id, 0) if remaining > 0 else 0
            targets[item_id] = max(targets.get(item_id, 0), remaining + kept)
            log.trace(f"get_fabricator_targets: dock order {order_id} raises target for {item_id} -> {targets[item_id]} (remaining={remaining}, reserve={kept})")

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
    for item_id, count in _cascade_blueprint_demand(cache).items():
        if item_id in fabricator_outputs:
            targets[item_id] = max(targets.get(item_id, 0), count)
            log.trace(f"get_fabricator_targets: blueprint cascade raises target for {item_id} -> {targets[item_id]} (cascaded={count})")

    # Stock targets and manual/upgrade/backlog orders are consumed at home
    # (Inventory side), site orders excepted. A blueprint's own required_item is consumed where the
    # Constructor Pioneer loads it (construction_site_id()); the intermediates
    # beneath it are Fabricator inputs, consumed at whichever fab site builds
    # the item, so they are no consumer root.
    # Manual-order units built off home stay wanted at home until they arrive
    # (MANUAL_TRANSIT_KEY); no build target, they already exist.
    for item_id, qty in manual_transit_wants(cache).items():
        home_wants[item_id] = max(home_wants.get(item_id, 0), qty)
    for item_id, qty in home_wants.items():
        site = consumers.setdefault(item_id, {})
        site[home_id] = max(site.get(home_id, 0), qty)
    seeds = {i: n for i, n in blueprint_required_items(cache).items() if n > 0}
    if seeds:
        builder_site = construction_site_id()
        for item_id, qty in seeds.items():
            site = consumers.setdefault(item_id, {})
            site[builder_site] = max(site.get(builder_site, 0), qty)
            log.trace(f"fabricator_root_targets: blueprint needs {qty}x {item_id} at {builder_site}")

    if cache is not None:
        cache._root_targets = (dict(targets), {i: dict(c) for i, c in consumers.items()}, set(fabricator_outputs))
    log.end()
    return targets, consumers, fabricator_outputs
