# Shared production-demand planning for mining and refining automation.
from archive import archive
from storage import total_stock, discover_storage_buildings
from outpost_mining import stock_target_for, RAW_ORE_ITEM_IDS, HOME_OUTPOST_ID
from power import DAY_CYCLE_DURATION_SECONDS
from tree_console import TreeConsole
import mining_reservations

log = TreeConsole(module="production")

# Recipe.duration_game_hours -> real seconds, from the fixed day-cycle
# schedule lib/power.py's DAY_CYCLE_DURATION_SECONDS already derives from
# (see docs/AI_CHEATSHEET.md) -- reused here, not redefined, so there's
# exactly one place this constant lives.
SECONDS_PER_GAME_HOUR = DAY_CYCLE_DURATION_SECONDS / 24.0

# How far ahead a Smelter/Fabricator should prefill its input buffer, in real
# seconds of continuous crafting -- see craft_prefill_units(). Deliberately
# time-based, not a fixed unit count: a fast recipe (a few seconds/craft)
# still gets several crafts' worth staged so the Auto Feeder isn't paid
# every single craft, while a slow recipe (tens of minutes/craft) only ever
# prefills what it needs for its next craft or two, instead of reflexively
# filling toward the machine's full hardware buffer cap regardless of how
# long that material would then sit idle.
INPUT_PREFILL_SECONDS = 30


def _ceil(x):
    """Ceiling without the math module -- this sandboxed script environment
    doesn't permit `import math`. Plain arithmetic: int(x) truncates toward
    zero, so for a non-negative x that's floor(x); bump by 1 whenever x has
    a fractional remainder above that. Only ever called here with
    non-negative x (seconds/unit ratios)."""
    i = int(x)
    return i + 1 if x > i else i


def craft_seconds(recipe):
    """Real-world seconds per craft for `recipe`, converted from its
    `.duration_game_hours` via the fixed day-cycle schedule. Floors at 1
    second if the recipe reports a missing/zero duration, so dividing
    against it (craft_prefill_units()) never blows up."""
    hours = getattr(recipe, "duration_game_hours", None)
    if not hours or hours <= 0:
        return 1.0
    return hours * SECONDS_PER_GAME_HOUR


def craft_prefill_units(recipe, item_id, prefill_seconds=INPUT_PREFILL_SECONDS):
    """
    How many units of `item_id` (one of recipe.inputs) a Smelter/Fabricator
    should keep staged to cover roughly the next `prefill_seconds` of real
    time spent crafting -- ceil(prefill_seconds / craft_seconds(recipe))
    crafts' worth, floored at one craft's own requirement (staging less than
    a single craft needs would be pointless -- the craft can't start until
    the full per-craft amount is present anyway). Returns 0 if item_id isn't
    one of this recipe's inputs.

    Deliberately per-recipe/time-based rather than a fixed unit chunk: this
    is what makes the buffer target scale correctly whether a recipe crafts
    every few seconds (many crafts fit in the window, more staged) or takes
    tens of minutes (one craft's worth is already more than the window asks
    for). Used as a cap on top-up size by both lib/smelter.py's ore intake
    and lib/fabricator.py's load_inputs() -- see docs/AI_CHEATSHEET.md.
    """
    inputs = getattr(recipe, "inputs", {}) or {}
    per_craft = inputs.get(item_id)
    if not per_craft:
        return 0
    crafts = max(1, _ceil(prefill_seconds / craft_seconds(recipe)))
    return int(_ceil(crafts * per_craft))


def _current_tick():
    """Module-level tick read (mirrors VehicleController.get_current_tick()) for callers with no vehicle instance."""
    clock = _component("clock")
    if clock and hasattr(clock, "tick"):
        try:
            return clock.tick()
        except Exception:
            pass
    return 0


def _component(component_id):
    try:
        return get_component(component_id)
    except Exception:
        return None


SMELTER_TYPE_ID = "smelter"


def discover_smelter_ids(outpost=None):
    """
    All Smelter building ids at outpost (default: home). Mirrors
    storage.discover_storage_buildings()'s shape. Every demand-cascade
    function below used to hard-fallback to the literal id "smelter_1" --
    a correctness bug, not just an inefficiency, the moment a second Smelter
    exists: raw-material demand and recipe-lookup would silently only ever
    consult smelter_1's recipe set, so a second smelter's distinct recipes
    (if any) would never drive mining at all. Recipe *availability* is
    tech-gated and identical across same-type buildings, so any one
    discovered smelter's list_recipes() is a representative stand-in
    everywhere below that just needs "a" smelter, not "smelter_1"
    specifically -- lib/smelter.py's own leader election (see
    docs/AI_CHEATSHEET.md) is the place that actually cares which physical
    smelter does what.
    """
    ids = []
    outpost = outpost or _home_outpost()
    if outpost and hasattr(outpost, "buildings"):
        try:
            for building in outpost.buildings(SMELTER_TYPE_ID):
                b_id = getattr(building, "id", None)
                if b_id:
                    ids.append(b_id)
        except Exception:
            pass
    return ids


def _home_outpost():
    network = _component("outpost_network")
    if network and hasattr(network, "home"):
        return network.home()
    return None


def _default_smelter():
    """First discovered Smelter component (dynamic stand-in for the old hardcoded 'smelter_1')."""
    ids = discover_smelter_ids()
    if ids:
        return _component(ids[0])
    return _component("smelter_1")  # last-resort fallback if discovery finds nothing (e.g. outpost_network unavailable)


FABRICATOR_TYPE_ID = "fabricator"


def discover_fabricator_ids(outpost=None):
    """All Fabricator building ids at outpost (default: home). Same shape/reasoning as discover_smelter_ids()."""
    ids = []
    outpost = outpost or _home_outpost()
    if outpost and hasattr(outpost, "buildings"):
        try:
            for building in outpost.buildings(FABRICATOR_TYPE_ID):
                b_id = getattr(building, "id", None)
                if b_id:
                    ids.append(b_id)
        except Exception:
            pass
    return ids


def _default_fabricator():
    """First discovered Fabricator component (dynamic stand-in for the old hardcoded 'fabricator_1')."""
    ids = discover_fabricator_ids()
    if ids:
        return _component(ids[0])
    return _component("fabricator_1")  # last-resort fallback if discovery finds nothing


SUPPLY_DOCK_TYPE_ID = "supply_dock"


def discover_supply_dock_ids(outpost=None):
    """
    All Supply Dock building ids at outpost (default: home). Same shape/reasoning
    as discover_smelter_ids()/discover_fabricator_ids(): every demand-cascade
    function below used to hard-fallback to the literal id "supply_dock_1" --
    the same correctness bug class Phase A fixed for Smelter/Fabricator, just
    not caught for Supply Dock at the time. A second dock's own active order
    must count toward Fabricator targets/raw-material demand too, not just
    whichever order supply_dock_1 happens to be running.
    """
    ids = []
    outpost = outpost or _home_outpost()
    if outpost and hasattr(outpost, "buildings"):
        try:
            for building in outpost.buildings(SUPPLY_DOCK_TYPE_ID):
                b_id = getattr(building, "id", None)
                if b_id:
                    ids.append(b_id)
        except Exception:
            pass
    return ids


def _all_dock_orders():
    """
    [(dock_component, order), ...] for every discovered Supply Dock currently
    holding an active order (docks with no order, or that can't be reached,
    are simply absent from the list). Single source of truth for "every
    current order across the whole dock fleet" -- every demand-cascade
    function below loops this instead of reading one hardcoded dock.
    """
    ids = discover_supply_dock_ids()
    if not ids:
        ids = ["supply_dock_1"]  # last-resort fallback if discovery finds nothing
    pairs = []
    for dock_id in ids:
        dock = _component(dock_id)
        if not dock or not hasattr(dock, "current_order"):
            continue
        try:
            order = getattr(dock, "current_order")()
        except Exception:
            continue
        if order:
            pairs.append((dock, order))
    return pairs


def _dock_order_remaining():
    """
    {order_id: {item_id: units}} still owed per active order:
    required - shipped - units already loaded into every dock serving it.

    Deduplicated per order: several docks may serve the same order and share
    its shipped progress (docs/components/supply_dock.md), so looping
    _all_dock_orders() pairs and adding each dock's remaining counted a
    shared order once per dock (seen live: spire_13 on two docks demanded
    120 Neutronium Bars for a 60-bar order). Loaded-but-undispatched units
    are in neither Inventory nor order.shipped, so every dock's count() is
    summed and subtracted -- without that, producers re-craft whatever sits
    in the dock and overshoot the order by that much (seen live: 104 Heli
    Thrusters / 204 small Oil Tanks for 100/200 orders, the extras stranded
    in Inventory, one slot each). Negative remainders are kept; callers clamp.
    """
    loaded_by_order = {}
    orders_by_id = {}
    for dock, order in _all_dock_orders():
        if not hasattr(order, "requires"):
            continue
        order_id = getattr(order, "id", None)
        orders_by_id[order_id] = order
        loaded = loaded_by_order.setdefault(order_id, {})
        if not hasattr(dock, "count"):
            continue
        try:
            for item_id in order.requires:
                loaded[item_id] = loaded.get(item_id, 0) + dock.count(item_id)
        except Exception:
            pass

    result = {}
    for order_id, order in orders_by_id.items():
        try:
            shipped = getattr(order, "shipped", {}) or {}
            loaded = loaded_by_order.get(order_id, {})
            result[order_id] = {
                item_id: required - shipped.get(item_id, 0) - loaded.get(item_id, 0)
                for item_id, required in (getattr(order, "requires", {}) or {}).items()
            }
        except Exception:
            pass
    log.trace(f"_dock_order_remaining: {len(orders_by_id)} distinct active order(s) -> {result}")
    return result


def find_dock_order_requiring(item_id):
    """
    First (dock, order) pair, across every discovered Supply Dock, whose
    active order still requires item_id (regardless of how much has already
    shipped -- callers that care about remaining-vs-shipped check that
    themselves). (None, None) if no current order anywhere requires it.
    Shared by get_raw_material_reason() below and lib/fabricator.py's
    target_reason(), so "which dock wants this" is answered in one place.
    """
    for dock, order in _all_dock_orders():
        if item_id in (getattr(order, "requires", {}) or {}):
            return dock, order
    return None, None


# A Fabricator recipe's water/steam/oil requirement (recipe.fluid_inputs,
# e.g. {"water_in": 1.0}) is a *separate* field from its solid .inputs
# (docs/components/fabricator.md) -- delivered by connecting the matching
# FluidPort (self.water_in / .steam_in / .oil_in) to one of these building
# types, not by taking an Inventory/Warehouse item. can_source_item() used to
# only ever look at .inputs, so a recipe needing Water was waved through as
# "sourceable" purely on its solid ingredients (Iron Ingot, Glass) even with
# no Water Pump anywhere on the network -- the Fabricator would then set that
# recipe and stall forever, and Supply Dock would commit to an Earth Order
# that could never actually complete.
FLUID_SOURCE_TYPE_IDS = {
    "water_in": ("water_pump", "steam_condenser", "liquid_tank", "large_liquid_tank"),
    "oil_in": ("oil_pump", "liquid_tank", "large_liquid_tank"),
    "steam_in": ("thermal_cap", "gas_tank"),
}

# liquid_tank/large_liquid_tank/gas_tank are generic multi-fluid buffers --
# they latch onto whichever exact fluid is piped into them FIRST and hold
# only that until drained to 0 (docs/components/liquid_tank.md,
# docs/components/gas_tank.md). Their mere existence on the network says
# nothing about which fluid they hold, or whether anything will ever fill
# one with the fluid we actually need -- e.g. a Liquid Tank latched to Water,
# or sitting empty with no Oil Pump anywhere to ever feed it, is not a
# usable Oil source even though the tank itself is real. Every other type in
# FLUID_SOURCE_TYPE_IDS is a dedicated producer (oil_pump, water_pump,
# steam_condenser, thermal_cap) that only ever emits its one fixed fluid, so
# its existence alone is sufficient.
BUFFER_FLUID_TYPE_IDS = ("liquid_tank", "large_liquid_tank", "gas_tank")
# Expected building.fluid() latch id for each fluid_key -- see both docs
# pages' `.fluid()` method above.
FLUID_LATCH_IDS = {"water_in": "water", "oil_in": "oil", "steam_in": "steam"}


def fluid_building_is_viable(fluid_key, type_id, building):
    """
    Whether this specific discovered building can actually deliver
    fluid_key, not just "this building type could in principle carry it".
    Shared by can_source_fluid() below and lib/fabricator.py's connection
    candidate discovery, so both apply the exact same buffer-latch rule --
    see BUFFER_FLUID_TYPE_IDS' comment for why existence alone isn't enough
    for a tank. Deliberately does NOT consult fluid_routing.tank_assignments
    -- that registry only gates which tank a producer may establish a NEW
    connection to (see fluid_routing.tank_is_eligible_target()); a tank's
    own .fluid() latch is already the complete, authoritative answer to "can
    it deliver fluid_key right now" regardless of the registry's state.
    """
    if type_id not in BUFFER_FLUID_TYPE_IDS:
        return True
    expected = FLUID_LATCH_IDS.get(fluid_key)
    if not expected:
        return True
    # `building` here is whatever outpost.buildings(type_id) handed us -- a
    # bare BuildingRef snapshot (.id/.name/.type_id/.outpost/.powered/
    # .position only, no .fluid()/.level()/etc, per docs/components/
    # outpost.md) when called from discovery loops, but the full live
    # component when called directly with one (e.g. from a unit test). A
    # BuildingRef has no .fluid() of its own -- must resolve the real
    # component via get_component(ref.id) first, or this always raises and
    # every buffer tank looks permanently non-viable regardless of what it
    # actually holds.
    if not hasattr(building, "fluid"):
        b_id = getattr(building, "id", None)
        if not b_id:
            return False
        building = _component(b_id)
        if not building:
            return False
    try:
        return getattr(building, "fluid")() == expected
    except Exception:
        return False


def can_source_fluid(fluid_key, cache=None):
    """
    Whether a building that could feed this FluidPort right now exists
    anywhere on the outpost network -- a dedicated producer of this exact
    fluid, or a buffer tank already latched to it (see
    fluid_building_is_viable()). Deliberately checks existence/latch state
    only, not an actual completed pipe route or fluid level -- matching
    can_source_item()'s own "known source" bar (a surveyed site doesn't
    guarantee a working claim either) -- so this only rules out the "not
    (yet) able to supply this fluid at all" case, not "built but not yet
    piped/full".

    Pass a shared `cache` (SourceCache) when checking several
    recipes/items/orders in one pass -- see SourceCache's docstring for why
    that matters; the outpost.buildings() scan this does is a real game call
    per fluid_key, otherwise repeated once per recipe that needs it.
    """
    if cache is not None and fluid_key in cache._fluid_results:
        log.trace(f"can_source_fluid({fluid_key}): cache hit -> {cache._fluid_results[fluid_key]}")
        return cache._fluid_results[fluid_key]

    type_ids = FLUID_SOURCE_TYPE_IDS.get(fluid_key)
    if not type_ids:
        result = True  # unrecognized fluid key -- don't block on something we don't model
        log.trace(f"can_source_fluid({fluid_key}): unrecognized fluid key, not blocking")
    else:
        result = False
        network = _component("outpost_network")
        if network and hasattr(network, "outposts"):
            try:
                for outpost in network.outposts():
                    for type_id in type_ids:
                        for building in outpost.buildings(type_id):
                            if fluid_building_is_viable(fluid_key, type_id, building):
                                result = True
                                log.trace(f"can_source_fluid({fluid_key}): viable source found -> {getattr(building, 'id', type_id)} ({type_id})")
                                break
                        if result:
                            break
                    if result:
                        break
            except Exception:
                pass
        if not result:
            log.trace(f"can_source_fluid({fluid_key}): no viable source among {type_ids}")

    if cache is not None:
        cache._fluid_results[fluid_key] = result
    return result


def _add_demand(demands, item_id, quantity):
    if item_id and quantity > 0:
        demands[item_id] = demands.get(item_id, 0) + quantity


# Defaults only seed the Data Archive once; edit the archived key afterward
# (Data Archive Notebook) to change stock targets without touching this file.
FABRICATOR_STOCK_TARGETS_KEY = "fabricator.stock_targets"
DEFAULT_FABRICATOR_STOCK_TARGETS = {
    "gas_pipe_segment": 10,
    "power_line_segment": 10,
    "liquid_pipe_segment": 10,
}


def get_fabricator_stock_targets():
    """Seeds the Data Archive with default stock targets on first run, then reads them back."""
    if not archive.has(FABRICATOR_STOCK_TARGETS_KEY):
        archive.set(FABRICATOR_STOCK_TARGETS_KEY, dict(DEFAULT_FABRICATOR_STOCK_TARGETS))
    stored = archive.get(FABRICATOR_STOCK_TARGETS_KEY, DEFAULT_FABRICATOR_STOCK_TARGETS)
    if not isinstance(stored, dict):
        return dict(DEFAULT_FABRICATOR_STOCK_TARGETS)
    return {
        item_id: int(qty) for item_id, qty in stored.items()
        if isinstance(qty, (int, float)) and qty >= 0
    }


MANUAL_ORDERS_KEY = "fabricator.manual_orders"


def get_manual_orders():
    """{item_id: quantity_still_wanted} -- ad-hoc Fabricator build requests, edited directly in the
    Data Archive Notebook (e.g. {"drone_small": 2}) on top of the standing stock targets/orders
    get_fabricator_targets() already covers. No default is seeded (unlike
    get_fabricator_stock_targets()) -- an empty manual order list is the normal state. Counted down
    to 0 (then dropped entirely) as the Fabricator actually delivers finished units -- see
    consume_manual_order(), called from lib/fabricator.py's drain_output()."""
    if not archive.has(MANUAL_ORDERS_KEY):
        archive.set(MANUAL_ORDERS_KEY, {})
    stored = archive.get(MANUAL_ORDERS_KEY, {})
    if not isinstance(stored, dict):
        return {}
    return {
        item_id: int(qty) for item_id, qty in stored.items()
        if isinstance(qty, (int, float)) and qty > 0
    }


def consume_manual_order(item_id, quantity):
    """Counts down an active manual build order (see get_manual_orders()) by quantity actually
    delivered to Inventory, dropping the entry entirely once it reaches zero. No-ops if item_id has
    no active manual order or quantity <= 0."""
    if not item_id or quantity <= 0:
        return
    # Plain read first: archive.transaction() always writes the key back, even when the updater
    # returns it unchanged, which locks out manual Notebook edits of fabricator.manual_orders.
    # Only transact when item_id actually has an active order to count down.
    if item_id not in get_manual_orders():
        return

    def updater(stored):
        stored = dict(stored or {})
        remaining = stored.get(item_id)
        if not isinstance(remaining, (int, float)):
            remaining = None
        if remaining is None or remaining <= 0:
            return stored
        remaining -= quantity
        if remaining <= 0:
            del stored[item_id]
        else:
            stored[item_id] = remaining
        return stored

    try:
        archive.transaction(MANUAL_ORDERS_KEY, {}, updater)
    except Exception:
        pass


# Fleet hardware upgrade orders (lib/fleet_upgrade.py, lib/drone_upgrade.py):
# ONE shared dict {requester_id: {item_id: quantity}} (CLAUDE.md rule 7), so
# each requester -- the coordinator, or a drone wanting a bigger Cargo Pod --
# owns and clears only its own entry. Quantities are "keep at least this many
# in stock" floors, summed across requesters. Ranked below manual orders AND
# blueprint demand in lib/fabricator.py's choose_recipe() (building new
# things beats upgrading working old ones), above everything else.
UPGRADE_ORDERS_KEY = "fabricator.upgrade_orders"


def get_upgrade_orders():
    """{item_id: quantity} summed across every requester's entry in UPGRADE_ORDERS_KEY."""
    stored = archive.get(UPGRADE_ORDERS_KEY, {})
    if not isinstance(stored, dict):
        return {}
    totals = {}
    for items in stored.values():
        if not isinstance(items, dict):
            continue
        for item_id, qty in items.items():
            if isinstance(qty, (int, float)) and qty > 0:
                totals[item_id] = totals.get(item_id, 0) + int(qty)
    return totals


def set_upgrade_order(requester, items):
    """Replaces requester's upgrade order with items ({item_id: qty}); empty or None
    clears it. Plain read first, so an unchanged order costs no archive write."""
    wanted = {i: int(q) for i, q in (items or {}).items() if q and q > 0}
    stored = archive.get(UPGRADE_ORDERS_KEY, {})
    current = stored.get(requester) if isinstance(stored, dict) else None
    if (current or {}) == wanted:
        return

    def updater(orders):
        if not isinstance(orders, dict):
            orders = {}
        if wanted:
            orders[requester] = wanted
        else:
            orders.pop(requester, None)
        return orders

    archive.transaction(UPGRADE_ORDERS_KEY, {}, updater)


def fabricator_unlocked_outputs(cache=None):
    """Set of item ids the default Fabricator can craft today (list_recipes()
    only lists unlocked recipes, docs/components/fabricator.md)."""
    if cache is not None:
        recipes = cache.fabricator_recipes()
    else:
        fabricator = _default_fabricator()
        try:
            recipes = fabricator.list_recipes() if fabricator and hasattr(fabricator, "list_recipes") else []
        except Exception:
            recipes = []
    return {getattr(r, "output_item", None) for r in recipes} - {None}


def blueprint_demand_items(cache=None):
    """Item ids any pending/paused Construction Blueprint needs, directly or via
    the recipe cascade (_cascade_blueprint_demand()). choose_recipe()'s tier 2."""
    return set(_cascade_blueprint_demand(cache).keys())


def _stock_fn(cache):
    """cache.stock when a SourceCache is threaded through, else the uncached
    storage.total_stock() -- lets every demand helper below take an optional
    `cache` without changing behavior for callers that don't pass one."""
    return cache.stock if cache is not None else total_stock


def _recipe_inputs_for(item_id, cache=None):
    """{input_item_id: qty_per_output_unit} for whichever of Fabricator/
    Smelter builds item_id, or None if neither does. Shared by
    _cascade_blueprint_demand(), _cascade_fabricator_output_demand() and
    get_smelter_demands(). With a `cache`, reads its memoized recipe lists
    instead of calling list_recipes() again per item."""
    if cache is not None:
        recipe_lists = [cache.fabricator_recipes(), cache.smelter_recipes()]
    else:
        recipe_lists = []
        for component in (_default_fabricator(), _default_smelter()):
            if not component or not hasattr(component, "list_recipes"):
                continue
            try:
                recipe_lists.append(list(component.list_recipes()))
            except Exception:
                continue
    for recipes in recipe_lists:
        try:
            for recipe in recipes:
                if getattr(recipe, "output_item", None) != item_id:
                    continue
                output_count = max(1, getattr(recipe, "output_count", 1))
                inputs = getattr(recipe, "inputs", {}) or {}
                return {in_id: qty / output_count for in_id, qty in inputs.items()}
        except Exception:
            continue
    return None


def _cascade_fabricator_output_demand(seed_targets, fabricator_outputs, cache=None):
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
    iron_ingot) are deliberately left to get_raw_material_demands()'s own
    expansion off the resulting target, not duplicated here.

    Returns {item_id: target_quantity} for every reached item still short of
    stock, restricted to fabricator_outputs (Smelter-built intermediates
    aren't Fabricator targets -- get_raw_material_demands() handles those).
    """
    stock = _stock_fn(cache)
    targets = {}
    frontier = dict(seed_targets)
    depth = 0
    while frontier and depth < 6:  # same generous bound as _cascade_blueprint_demand()
        depth += 1
        next_frontier = {}
        for item_id, want in frontier.items():
            if item_id in fabricator_outputs:
                targets[item_id] = max(targets.get(item_id, 0), want)
            shortfall = max(0, want - stock(item_id))
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
        log.debug(f"_cascade_fabricator_output_demand: hit depth bound (6) with frontier still non-empty: {list(frontier.keys())}")
    return targets


def get_manual_order_blocking_items(fabricator_outputs, orders=None):
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
    manual_items = get_manual_orders() if orders is None else orders
    frontier = {item_id: qty for item_id, qty in manual_items.items() if item_id in fabricator_outputs}
    blocking = set()
    depth = 0
    while frontier and depth < 6:  # same generous bound as the sibling cascades
        depth += 1
        next_frontier = {}
        for item_id, want in frontier.items():
            shortfall = max(0, want - total_stock(item_id))
            if shortfall <= 0:
                log.trace(f"get_manual_order_blocking_items depth={depth}: {item_id} has no shortfall (want={want}), not cascading further")
                continue
            inputs = _recipe_inputs_for(item_id)
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
        log.debug(f"get_manual_order_blocking_items: hit depth bound (6) with frontier still non-empty: {list(frontier.keys())}")
    return blocking


def _vehicle_cargo_counts(item_ids):
    """{item_id: units} of the given items currently aboard any ground
    vehicle (fleet.vehicles() + each vehicle's live cargo.stacks()). Only
    items with a non-zero count are returned."""
    counts = {}
    fleet = _component("fleet")
    if not fleet or not hasattr(fleet, "vehicles"):
        return counts
    try:
        refs = fleet.vehicles()
    except Exception:
        return counts
    for ref in refs:
        vehicle = _component(getattr(ref, "id", None))
        cargo = getattr(vehicle, "cargo", None) if vehicle else None
        if not cargo or not hasattr(cargo, "stacks"):
            continue
        try:
            for stack in cargo.stacks():
                item_id = getattr(stack, "id", None)
                if item_id in item_ids:
                    counts[item_id] = counts.get(item_id, 0) + (getattr(stack, "count", 0) or 0)
        except Exception:
            continue
    return {k: v for k, v in counts.items() if v > 0}


def _cascade_blueprint_demand(cache=None):
    """
    Breadth-first demand cascade seeded from pending/paused Construction
    Blueprint required_item/required_count (summed across jobs, deduped by
    job id), then propagated down through Fabricator and Smelter recipe
    inputs -- e.g. a Thermal Cap build's thermal_cap_kit demand cascades into
    titanium_ingot demand, which cascades into titanium_ore demand.

    At each tier, only that tier's *shortfall* (demand beyond current total
    stock of that exact item, across Inventory and every Warehouse -- see
    storage.total_stock()) propagates further down -- so a build that's
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
    frontier = {}
    bp = _component("construction_blueprint")
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
            except Exception:
                pass

    # A constructor Pioneer loads a whole batch for chained jobs before
    # driving out, and every job stays pending until actually built -- so
    # while the materials ride in its cargo they're in neither Inventory nor
    # a Warehouse, and the Fabricator re-crafted the full batch (seen live:
    # 3 Oil Pump blueprints -> 6 pumps built, 3 left over). Net those out.
    if frontier:
        for item_id, carried in _vehicle_cargo_counts(frontier).items():
            frontier[item_id] = max(0, frontier[item_id] - carried)
            log.trace(f"_cascade_blueprint_demand: {carried}x {item_id} already aboard vehicles -> seed demand {frontier[item_id]}")

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
        log.debug(f"_cascade_blueprint_demand: hit depth bound (6) with frontier still non-empty: {list(frontier.keys())}")
    return total_needed


def get_construction_material_reservations():
    """
    Returns {item_id: units} to protect (Inventory + every Warehouse -- see
    storage.total_stock()) for active Construction Blueprints, cascading down
    through Fabricator/Smelter recipes to intermediate materials and raw ore
    (see _cascade_blueprint_demand()) -- not just each blueprint's own
    required_item. Capped at min(current stock, total demand) per item: never
    reserves more than what's both actually on hand and actually still needed.

    Used to stop the Supply Dock from shipping away stock an active build (or
    the production chain feeding it) is waiting on -- see supply_dock.py
    step()/pick_best_order().
    """
    reservations = {}
    for item_id, want in _cascade_blueprint_demand().items():
        stock = total_stock(item_id)
        reserve = min(stock, want)
        if reserve > 0:
            reservations[item_id] = reserve
    return reservations


_WARNED_UNKNOWN_MANUAL_ITEMS = set()


def get_fabricator_targets(cache=None):
    """Returns desired finished-goods quantities for Fabricator planning.

    With a `cache` (SourceCache), the result is memoized on it for the rest
    of that pass: this is the single most expensive demand helper (manual
    orders, every dock order, the blueprint cascade and the Fabricator output
    cascade, each walking stock), and get_material_demands() alone used to
    rebuild it once per Fabricator via get_fabricator_active_recipe(). A copy
    is returned so a caller mutating its result can't poison the memo."""
    if cache is not None and cache._fabricator_targets is not None:
        return dict(cache._fabricator_targets)

    targets = get_fabricator_stock_targets()

    fabricator_outputs = set()
    if cache is not None:
        recipes = cache.fabricator_recipes()
    else:
        fabricator = _default_fabricator()
        try:
            recipes = fabricator.list_recipes() if fabricator and hasattr(fabricator, "list_recipes") else []
        except Exception:
            recipes = []
    for recipe in recipes:
        output_item = getattr(recipe, "output_item", None)
        if output_item:
            fabricator_outputs.add(output_item)

    # Manual build orders (get_manual_orders()) max()'d in like every other source below -- they
    # don't add to a standing target, they just guarantee at least this many exist. Priority over
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
    for item_id, quantity in get_manual_orders().items():
        targets[item_id] = max(targets.get(item_id, 0), quantity)
        log.trace(f"get_fabricator_targets: manual order raises target for {item_id} -> {targets[item_id]}")
        if fabricator_outputs and item_id not in fabricator_outputs and item_id not in _WARNED_UNKNOWN_MANUAL_ITEMS:
            _WARNED_UNKNOWN_MANUAL_ITEMS.add(item_id)
            log.level("warn").print(f"[production] Warning: fabricator.manual_orders has '{item_id}' ({quantity}x), which "
                  f"doesn't match any known Fabricator recipe output. Check for a typo/renamed item_id.")

    # Fleet upgrade orders (get_upgrade_orders()): same max() fold as manual
    # orders; their lower priority is again choose_recipe()'s job.
    for item_id, quantity in get_upgrade_orders().items():
        targets[item_id] = max(targets.get(item_id, 0), quantity)
        log.trace(f"get_fabricator_targets: fleet upgrade order raises target for {item_id} -> {targets[item_id]}")

    for order_id, remaining_by_item in _dock_order_remaining().items():
        for item_id, remaining in remaining_by_item.items():
            # Only order items the Fabricator can actually build become
            # targets; other order items (raw/mined) are handled by
            # the dock demand loop in get_material_demands() and must
            # not be double-counted here.
            if item_id not in targets and item_id not in fabricator_outputs:
                continue
            targets[item_id] = max(targets.get(item_id, 0), remaining)
            log.trace(f"get_fabricator_targets: dock order {order_id} raises target for {item_id} -> {targets[item_id]} (remaining={remaining})")

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
        log.trace(f"get_fabricator_targets: output-demand cascade raises target for {item_id} -> {targets[item_id]} (cascaded={count})")

    log.trace(f"get_fabricator_targets: final targets={targets}")
    if cache is not None:
        cache._fabricator_targets = dict(targets)
    return targets


def get_fabricator_worker_count(recipe_id):
    """
    How many discovered Fabricators currently have recipe_id selected
    (get_recipe() == recipe_id) right now -- a live headcount, not an
    archive-tracked one, so it reflects joiners too (lib/fabricator.py's
    choose_recipe() lets a Fabricator "join" a recipe another one already
    holds the coordination claim on, when no other demanded recipe is
    available -- see its pile-on fallback). Used to split crafts_remaining
    fairly below: without this, every Fabricator working the same recipe
    would each independently load_inputs() for the FULL remaining shortfall,
    overshooting the target well before total_stock() catches up on the next
    poll. Returns at least 1 (the caller itself, even if the network walk
    finds nothing -- e.g. outpost_network unavailable).
    """
    count = 0
    for fabricator_id in discover_fabricator_ids():
        candidate = _component(fabricator_id)
        if not candidate or not hasattr(candidate, "get_recipe"):
            continue
        try:
            if candidate.get_recipe() == recipe_id:
                count += 1
        except Exception:
            pass
    return max(1, count)


def get_smelter_worker_count(recipe_id):
    """
    Live headcount of discovered Smelters currently holding recipe_id
    (get_recipe() == recipe_id) right now -- mirrors get_fabricator_worker_count()
    exactly, same reasoning, for lib/smelter.py's ore-intake cap: with several
    Smelters "joined" on the same recipe (select_needed_ore()'s pile-on
    fallback, used whenever only one ore is currently demanded), each one
    independently topping its own 50-unit ore buffer up to the FULL current
    demand overshoots badly once you have more than one -- e.g. two Smelters
    each independently filling to a demand of 50 produces 100, not 50. Public
    (like get_fabricator_worker_count(), which lib/fabricator.py uses) since
    lib/smelter.py needs it directly. Returns at least 1.
    """
    count = 0
    for smelter_id in discover_smelter_ids():
        candidate = _component(smelter_id)
        if not candidate or not hasattr(candidate, "get_recipe"):
            continue
        try:
            if candidate.get_recipe() == recipe_id:
                count += 1
        except Exception:
            pass
    return max(1, count)


def get_fabricator_active_recipe(fabricator=None, cache=None):
    """Returns (recipe, crafts_remaining) for the Fabricator's selected recipe,
    where crafts_remaining covers the full remaining shortfall against its
    output target/order (not just one craft's worth), divided evenly across
    every Fabricator currently working this same recipe (see
    get_fabricator_worker_count()) so several Fabricators piled onto one
    large order split its remaining work instead of each independently
    re-loading the full shortfall."""
    if fabricator is None:
        fabricator = _default_fabricator()
    if not fabricator or not hasattr(fabricator, "get_recipe") or not hasattr(fabricator, "list_recipes"):
        return None, 0
    try:
        current_recipe_id = fabricator.get_recipe()
        if not current_recipe_id:
            return None, 0
        recipe = next((r for r in fabricator.list_recipes() if getattr(r, "id", None) == current_recipe_id), None)
        if not recipe:
            return None, 0
        output_item = getattr(recipe, "output_item", None)
        output_count = max(1, getattr(recipe, "output_count", 1))
        current = _stock_fn(cache)(output_item)
        output_buffer = fabricator.get_output_count() if hasattr(fabricator, "get_output_count") else 0
        target = get_fabricator_targets(cache).get(output_item, 0)
        still_needed = max(0, target - current - output_buffer)
        crafts_remaining = -(-still_needed // output_count)  # ceil division
        worker_count = get_fabricator_worker_count(current_recipe_id)
        if worker_count > 1:
            pre_split = crafts_remaining
            crafts_remaining = -(-crafts_remaining // worker_count)  # ceil division -- an odd remainder goes to every worker equally rather than being dropped, converging (not undershooting) once demand nets back down on the next poll
            log.debug(f"get_fabricator_active_recipe({getattr(fabricator, 'id', '?')}): recipe={current_recipe_id} split {pre_split} crafts across {worker_count} workers -> {crafts_remaining} each")
        log.debug(f"get_fabricator_active_recipe({getattr(fabricator, 'id', '?')}): recipe={current_recipe_id} output={output_item} target={target} current={current} output_buffer={output_buffer} still_needed={still_needed} crafts_remaining={crafts_remaining}")
        return recipe, crafts_remaining
    except Exception:
        return None, 0


def get_material_demands(cache=None):
    """Returns material quantities currently requested by production and shipping.

    NOTE: for Smelter outputs (ingots, glass, ...) this only sees the direct
    inputs of each Fabricator's *currently selected* recipe -- lib/smelter.py
    uses get_smelter_demands() instead, which follows the whole order tree."""
    stock = _stock_fn(cache)
    demands = {}

    # Finished fabricated goods have a standing building-stock target and
    # may also be required by the active Supply Dock order.
    for item_id, target in get_fabricator_targets(cache).items():
        current = stock(item_id)
        deficit = max(0, target - current)
        _add_demand(demands, item_id, deficit)
        if deficit > 0:
            log.trace(f"get_material_demands: {item_id} stock={current} target={target} -> deficit={deficit}")

    # Every Fabricator's own selected recipe is an explicit production
    # intention; scale by every remaining craft still needed to reach the
    # target, not just one craft's worth, or demand collapses to 0 as soon as
    # a single unit of an input is on hand even though hundreds more crafts
    # remain. Looping every discovered Fabricator (not just _default_fabricator())
    # matters as soon as a second one exists: with several Fabricators each
    # holding a DIFFERENT claimed recipe (see lib/fabricator.py's
    # claim_recipe()), only ever reading the first one's active recipe left
    # every other Fabricator's own input demand invisible here -- e.g.
    # fabricator_2 running craft_gas_pipe_segment (needs iron_ingot) never
    # registered any iron_ingot demand while fabricator_1 was busy on a
    # different recipe, so the Smelter never saw a reason to refine more,
    # even with raw ore sitting in a Warehouse. Same hardcoded-single-instance
    # bug class Phase A already fixed for Smelter/Fabricator/Supply Dock
    # discovery elsewhere in this file.
    fabricator_ids = discover_fabricator_ids() or ["fabricator_1"]
    for fabricator_id in fabricator_ids:
        fabricator = _component(fabricator_id)
        if not fabricator:
            continue
        recipe, crafts_remaining = get_fabricator_active_recipe(fabricator, cache)
        if not recipe or crafts_remaining <= 0:
            log.trace(f"get_material_demands: {fabricator_id} has no active recipe/crafts remaining, skipping input demand")
            continue
        try:
            stockpile = fabricator.get_stockpile() or {}
            for item_id, required in (getattr(recipe, "inputs", {}) or {}).items():
                missing = (required * crafts_remaining) - stockpile.get(item_id, 0)
                missing -= stock(item_id)
                missing = max(0, missing)
                _add_demand(demands, item_id, missing)
                if missing > 0:
                    log.trace(f"get_material_demands: {fabricator_id} recipe={getattr(recipe, 'id', '?')} needs {item_id} -> deficit={missing} (crafts_remaining={crafts_remaining})")
        except Exception:
            pass

    # Every dock's active order is a current downstream shipping requirement.
    for order_id, remaining_by_item in _dock_order_remaining().items():
        for item_id, remaining in remaining_by_item.items():
            missing = max(0, remaining - stock(item_id))
            _add_demand(demands, item_id, missing)
            if missing > 0:
                log.trace(f"get_material_demands: order {order_id} needs {item_id} -> deficit={missing}")

    log.trace(f"get_material_demands: final demands={demands}")
    return demands


def get_smelter_demands(cache=None):
    """
    {smelter_output_item: units_still_to_refine} -- what lib/smelter.py
    should actually produce, following the WHOLE order tree down to Smelter
    outputs (ingots, glass, ...), not just the direct inputs of whatever
    recipe a Fabricator happens to have selected right now.

    Why this exists (found live: 400 drone_small + 200 drone_medium on manual
    order, yet both iron Smelters trickled 1 ore per poll next to ~2000 iron
    ore): get_material_demands() only registers ingot demand through
    get_fabricator_active_recipe() -- already split per worker, and each
    Fabricator's share netted against the FULL total_stock() independently --
    while _cascade_fabricator_output_demand() deliberately stops at Smelter
    outputs. A big order therefore showed up as ~1 ingot of demand, and the
    Smelters ran one unit at a time.

    Gross-then-net-once:
      1. Every get_fabricator_targets() entry (manual orders, stock targets,
         docks, blueprints, and the Fabricator-intermediate cascade -- which
         already propagates a top-level order's shortfall into every
         Fabricator-built intermediate's own target) with a deficit D
         contributes D x ratio for each of its recipe inputs that is a
         Smelter output. Each Fabricator output's own direct ingot use is
         distinct, so summing these doesn't double-count.
      2. A target set directly on a Smelter output (a standing stock target,
         or a dock order get_fabricator_targets() already folded in) counts
         as gross need as-is.
      3. Dock orders for Smelter outputs NOT already covered by (2).
      4. Net once: minus total stock (Inventory + Warehouses) and minus what's
         already staged in every Fabricator's stockpile.

    Pass the step's SourceCache -- this walks the full target set, so it is
    not cheap uncached. Mining (get_raw_material_demands()) is deliberately
    NOT switched over yet -- see TODO.md.
    """
    cache = SourceCache() if cache is None else cache
    smelter_outputs = {getattr(r, "output_item", None) for r in cache.smelter_recipes()}
    smelter_outputs.discard(None)
    if not smelter_outputs:
        return {}

    gross = {}
    targets = get_fabricator_targets(cache)
    for item_id, target in targets.items():
        if item_id in smelter_outputs:
            _add_demand(gross, item_id, target)
            log.trace(f"get_smelter_demands: direct target on smelter output {item_id} -> gross += {target}")
            continue
        deficit = target - cache.stock(item_id)
        if deficit <= 0:
            continue
        for input_id, ratio in (_recipe_inputs_for(item_id, cache) or {}).items():
            if input_id in smelter_outputs:
                need = _ceil(deficit * ratio)
                _add_demand(gross, input_id, need)
                log.trace(f"get_smelter_demands: {item_id} deficit={deficit} x {ratio:.2f} -> {input_id} gross += {need}")

    for order_id, remaining_by_item in _dock_order_remaining().items():
        for item_id, remaining in remaining_by_item.items():
            if item_id not in smelter_outputs or item_id in targets:
                continue  # not ours, or already counted via get_fabricator_targets()
            _add_demand(gross, item_id, remaining)
            if remaining > 0:
                log.trace(f"get_smelter_demands: order {order_id} still needs {remaining}x {item_id}")

    staged = {}
    for fabricator_id in discover_fabricator_ids():
        fabricator = _component(fabricator_id)
        if not fabricator or not hasattr(fabricator, "get_stockpile"):
            continue
        try:
            for item_id, count in (fabricator.get_stockpile() or {}).items():
                if item_id in gross:
                    staged[item_id] = staged.get(item_id, 0) + count
        except Exception:
            pass

    demands = {}
    for item_id, qty in gross.items():
        net = qty - cache.stock(item_id) - staged.get(item_id, 0)
        if net > 0:
            demands[item_id] = net
        log.debug(f"get_smelter_demands: {item_id} gross={qty} stock={cache.stock(item_id)} staged_in_fabricators={staged.get(item_id, 0)} -> net={max(0, net)}")
    return demands


def dock_remaining_requirements():
    """{item_id: units} still owed (required - shipped - already loaded into
    the dock) across every active Supply Dock order. lib/smelter.py subtracts
    this from raw ore it may refine, so real ingot demand can't eat ore a dock
    order ships raw."""
    remaining_by_item = {}
    for remaining_for_order in _dock_order_remaining().values():
        for item_id, remaining in remaining_for_order.items():
            _add_demand(remaining_by_item, item_id, remaining)
    return remaining_by_item


def smelter_recipe_peers(recipe_id):
    """(worker_count, buffered_units) across every discovered Smelter currently
    holding recipe_id -- get_smelter_worker_count() plus the sum of their
    input buffers, in one walk. lib/smelter.py's fair-share cap uses both:
    (available ore + everything already buffered by these peers) // workers
    is the most any one of them should hold. worker_count is at least 1."""
    count = 0
    buffered = 0
    for smelter_id in discover_smelter_ids():
        candidate = _component(smelter_id)
        if not candidate or not hasattr(candidate, "get_recipe"):
            continue
        try:
            if candidate.get_recipe() != recipe_id:
                continue
            count += 1
            buffered += candidate.get_input_count() if hasattr(candidate, "get_input_count") else 0
        except Exception:
            pass
    return max(1, count), buffered


def get_raw_material_demands(smelter=None):
    """Converts refined-material demand into raw ore demand for mining."""
    demands = get_material_demands()
    refined_demands = dict(demands)
    raw_demands = {}

    # Raw items requested directly by an order are mined as-is.
    for item_id, quantity in demands.items():
        if item_id.endswith("_ore") or item_id in ["silicon", "rare_earth"]:
            current = total_stock(item_id)
            deficit = max(0, quantity - current)
            _add_demand(raw_demands, item_id, deficit)
            if deficit > 0:
                log.trace(f"get_raw_material_demands: {item_id} mined directly, stock={current} demand={quantity} -> deficit={deficit}")

    # Expand Fabricator output demand into refined-material demand before
    # asking the Smelter to expand refined materials into raw ore.
    fabricator = _default_fabricator()
    if fabricator and hasattr(fabricator, "list_recipes"):
        try:
            for recipe in fabricator.list_recipes():
                output_item = getattr(recipe, "output_item", None)
                output_need = demands.get(output_item, 0)
                if output_need <= 0:
                    continue
                output_count = max(1, getattr(recipe, "output_count", 1))
                for input_id, units_per_run in (getattr(recipe, "inputs", {}) or {}).items():
                    current = total_stock(input_id)
                    needed = (output_need * units_per_run + output_count - 1) // output_count
                    deficit = max(0, needed - current)
                    _add_demand(refined_demands, input_id, deficit)
                    if deficit > 0:
                        log.trace(f"get_raw_material_demands: fabricator output {output_item} (need={output_need}) expands into refined {input_id} -> deficit={deficit}")
        except Exception:
            pass

    # Only unlocked smelter recipes can create demand. Locked silicon recipes
    # therefore cannot cause either refining or rover mining.
    if smelter is None:
        smelter = _default_smelter()
    if smelter and hasattr(smelter, "list_recipes"):
        try:
            for recipe in smelter.list_recipes():
                output_item = getattr(recipe, "output_item", None)
                output_need = refined_demands.get(output_item, 0)
                if output_need <= 0:
                    continue
                for raw_item, units_per_run in (getattr(recipe, "inputs", {}) or {}).items():
                    current = total_stock(raw_item)
                    deficit = max(0, output_need * units_per_run - current)
                    _add_demand(raw_demands, raw_item, deficit)
                    if deficit > 0:
                        log.trace(f"get_raw_material_demands: smelter recipe {getattr(recipe, 'id', '?')} for {output_item} (need={output_need}) expands into raw {raw_item} -> deficit={deficit}")
        except Exception:
            pass

    # Standing home ore buffer: keep at least one Warehouse slot's worth
    # (outpost_mining.stock_target_for(), seed-once-editable) of every raw
    # ore on hand at home even with zero active production/order demand --
    # freely drawn down by Smelter/Supply Dock like any other stock, never a
    # reserved amount, just a floor that creates replenishment demand once
    # it's dipped into. Takes the max with (not additive to) whatever
    # production demand already computed above, since both ultimately want
    # the same ore delivered home -- adding them would double-count.
    for item_id in RAW_ORE_ITEM_IDS:
        buffer_deficit = max(0, stock_target_for(HOME_OUTPOST_ID, item_id) - total_stock(item_id))
        if buffer_deficit > raw_demands.get(item_id, 0):
            log.trace(f"get_raw_material_demands: home buffer floor for {item_id} ({buffer_deficit}) exceeds production demand ({raw_demands.get(item_id, 0)}), using buffer floor")
            raw_demands[item_id] = buffer_deficit

    # Debit ore already promised by an in-flight home-demand mining trip
    # (lib/vehicle_mining.py's select_best_mining_target(reserve_demand=True)) or
    # haul delivery (lib/vehicle_cargo.py's run_haul_loop()) so a peer's
    # candidate search this cycle or later doesn't also chase a deficit
    # that's already being fetched -- now that several Pioneers can mine the
    # same POI, get_claims() alone no longer prevents that, and the same
    # race applies across multiple mining-outpost haulers converging on the
    # same home buffer deficit. Only the home-demand path reads this:
    # outpost-stationed stockpile mining doesn't go through
    # get_raw_material_demands() at all, and is already self-bounded by its
    # own live stock-target check.
    reserved = mining_reservations.get_reserved_yield_totals(_current_tick())
    for item_id, units in reserved.items():
        if item_id in raw_demands:
            before = raw_demands[item_id]
            raw_demands[item_id] = max(0, raw_demands[item_id] - units)
            log.trace(f"get_raw_material_demands: {item_id} debited by {units} already-reserved yield ({before} -> {raw_demands[item_id]})")

    log.trace(f"get_raw_material_demands: final raw_demands={raw_demands}")
    return raw_demands


class SourceCache:
    """
    Per-pass memo for can_source_item()/can_source_fluid()'s underlying
    game-API lookups (Smelter/Fabricator discovery + list_recipes(),
    outpost.buildings() for fluid sources, journal.surveyed_sites(), a
    one-shot Inventory+Warehouse stock snapshot) plus the
    can_source_item()/can_source_fluid() results themselves.

    Each of those lookups is a real call across the script/game boundary, not
    a free local computation -- and callers that evaluate several
    items/recipes/orders in one pass (Supply Dock's plan_dock_assignments()
    across every order and dock, Fabricator's choose_recipe() across every
    candidate recipe) used to re-run every one of them from scratch per item,
    per recipe, and per order, which is what turned a single
    can_fulfill_order() call into several real seconds. That in turn was found
    to wedge panel_7.py's Custom Panel rendering outright whenever this ran
    inside its per-tick loop (not just slow it down) -- see panel_7.py's
    module docstring for why that script is now a headless calculator with no
    panel.* calls of its own. Building one SourceCache per pass and threading
    it through means each underlying game call happens at most once per pass,
    and a sub-item shared by several recipes/orders (e.g. Steel) gets resolved
    once instead of re-walked from scratch down every branch that needs it.

    Discard it once the pass finishes -- it's a snapshot of build/tech state
    that can change between ticks, not something to hold onto across calls.
    """

    def __init__(self):
        self._smelter_recipes = None
        self._fabricator_recipes = None
        self._fluid_results = {}
        self._item_results = {}
        self._item_stack = set()
        self._surveyed_sites = None
        self._stock_map = None
        self._building_stock = None  # {source_id: {item_id: units}}, filled alongside _stock_map
        self._fabricator_targets = None  # get_fabricator_targets() memo -- see its docstring

    def _build_stock_map(self):
        log.trace("SourceCache._build_stock_map: one-shot stock scan across Inventory + Warehouses starting")
        """One .stacks() call per Inventory/Warehouse -- each returns that
        building's ENTIRE contents in one shot -- summed by item id into a
        single {item_id: total_units} snapshot for the whole pass. Calling
        stock(item_id) per distinct item instead (total_stock()'s normal
        per-item .count(item_id) shape) would still cost one call per
        building per distinct item; a single .stacks() sweep per building up
        front replaces that with one call per building, period, no matter how
        many distinct items this pass ends up checking. The same sweep also
        fills the per-building breakdown building_stock() serves (used by
        storage.take_item() to pick which holder to pull from), at no extra
        game calls."""
        totals = {}
        per_building = {}
        sources = [("inventory", _component("inventory"))] + [(b["id"], b["component"]) for b in discover_storage_buildings()]
        for source_id, component in sources:
            if not component or not hasattr(component, "stacks"):
                continue
            held = per_building.setdefault(source_id, {})
            try:
                for stack in component.stacks():
                    stack_item_id = getattr(stack, "id", None)
                    if stack_item_id:
                        count = getattr(stack, "count", 0)
                        totals[stack_item_id] = totals.get(stack_item_id, 0) + count
                        held[stack_item_id] = held.get(stack_item_id, 0) + count
            except Exception:
                pass
        self._building_stock = per_building
        log.trace(f"SourceCache._build_stock_map: scanned {len(sources)} storage components, {len(totals)} distinct items")
        return totals

    def stock(self, item_id):
        """Item's total units across Inventory + every Warehouse, from this
        pass's one-shot stock snapshot -- see _build_stock_map()."""
        if self._stock_map is None:
            self._stock_map = self._build_stock_map()
        return self._stock_map.get(item_id, 0)

    def building_stock(self, item_id):
        """[(source_id, units), ...] for every home storage endpoint ("inventory"
        or a Warehouse id) holding item_id, from the same one-shot snapshot as
        stock(). Unordered -- storage.take_item() applies its own priority."""
        if self._stock_map is None:
            self._stock_map = self._build_stock_map()
        return [
            (source_id, held[item_id])
            for source_id, held in (self._building_stock or {}).items()
            if held.get(item_id, 0) > 0
        ]

    def smelter_recipes(self):
        if self._smelter_recipes is None:
            component = _default_smelter()
            try:
                self._smelter_recipes = list(component.list_recipes()) if component and hasattr(component, "list_recipes") else []
            except Exception:
                self._smelter_recipes = []
        return self._smelter_recipes

    def fabricator_recipes(self):
        if self._fabricator_recipes is None:
            component = _default_fabricator()
            try:
                self._fabricator_recipes = list(component.list_recipes()) if component and hasattr(component, "list_recipes") else []
            except Exception:
                self._fabricator_recipes = []
        return self._fabricator_recipes

    def surveyed_sites(self):
        if self._surveyed_sites is None:
            journal = _component("journal")
            try:
                self._surveyed_sites = list(journal.surveyed_sites("nocturna")) if journal and hasattr(journal, "surveyed_sites") else []
            except Exception:
                self._surveyed_sites = []
        return self._surveyed_sites


def _has_surveyed_mineral(item_id, cache):
    try:
        return any(
            getattr(site, "kind", lambda: "")() == "mineral"
            and getattr(site, "item_id", None) == item_id
            for site in cache.surveyed_sites()
        )
    except Exception:
        return False


def can_source_item(item_id, cache=None):
    """Whether an item has storage (Inventory/Warehouse), surveyed-source, or unlocked recipe supply.

    Pass a shared `cache` (SourceCache) when checking several items/recipes/
    orders in one pass -- see SourceCache's docstring for why that matters.
    """
    cache = SourceCache() if cache is None else cache
    if item_id in cache._item_results:
        log.trace(f"can_source_item({item_id}): cache hit -> {cache._item_results[item_id]}")
        return cache._item_results[item_id]
    if cache.stock(item_id) > 0:
        log.trace(f"can_source_item({item_id}): already in stock ({cache.stock(item_id)}) -> sourceable")
        cache._item_results[item_id] = True
        return True
    if item_id in cache._item_stack:
        log.trace(f"can_source_item({item_id}): recipe cycle guard hit, treating as not-yet-sourceable")
        return False  # cycle guard -- not memoized, this item's own answer is still being computed higher up
    cache._item_stack.add(item_id)

    try:
        result = _has_surveyed_mineral(item_id, cache)
        if result:
            log.trace(f"can_source_item({item_id}): surveyed mineral site found -> sourceable")
        if not result:
            for recipes in (cache.smelter_recipes(), cache.fabricator_recipes()):
                for recipe in recipes:
                    if getattr(recipe, "output_item", None) != item_id:
                        continue
                    inputs = getattr(recipe, "inputs", {}) or {}
                    fluid_inputs = getattr(recipe, "fluid_inputs", {}) or {}
                    if all(can_source_fluid(fk, cache) for fk in fluid_inputs) and all(can_source_item(input_id, cache) for input_id in inputs):
                        result = True
                        log.trace(f"can_source_item({item_id}): sourceable via recipe {getattr(recipe, 'id', '?')} (inputs={list(inputs.keys())}, fluids={list(fluid_inputs.keys())})")
                        break
                if result:
                    break
            if not result:
                log.trace(f"can_source_item({item_id}): no stock, no surveyed mineral, no sourceable recipe -> not sourceable")
    finally:
        cache._item_stack.discard(item_id)

    cache._item_results[item_id] = result
    return result


def can_fulfill_order(order, cache=None):
    """Checks whether every remaining order item has a currently known source.

    Pass a shared `cache` (SourceCache) when checking several orders in one
    pass (e.g. Supply Dock's plan_dock_assignments()) -- see SourceCache's
    docstring for why that matters.
    """
    if not order or not hasattr(order, "requires"):
        return False
    cache = SourceCache() if cache is None else cache
    shipped = getattr(order, "shipped", {}) or {}
    for item_id, required in order.requires.items():
        remaining = max(0, required - shipped.get(item_id, 0))
        if remaining > 0 and not can_source_item(item_id, cache):
            log.debug(f"can_fulfill_order({getattr(order, 'id', '?')}): {item_id} (remaining={remaining}) has no known source -> order not fulfillable")
            return False
    log.debug(f"can_fulfill_order({getattr(order, 'id', '?')}): all remaining requirements have a known source -> fulfillable")
    return True


def get_raw_material_reason(raw_item, smelter=None):
    """Describes the active downstream consumer driving a raw-material demand."""
    fabricator = _default_fabricator()

    _, order = find_dock_order_requiring(raw_item)
    if order:
        return f"Supply Dock Order {getattr(order, 'name', getattr(order, 'id', 'active'))}"

    if smelter is None:
        smelter = _default_smelter()
    if smelter and hasattr(smelter, "list_recipes"):
        try:
            for recipe in smelter.list_recipes():
                inputs = getattr(recipe, "inputs", {}) or {}
                if raw_item not in inputs:
                    continue
                output_item = getattr(recipe, "output_item", None)
                _, output_order = find_dock_order_requiring(output_item)
                if output_order:
                    return f"Supply Dock Order {getattr(output_order, 'name', getattr(output_order, 'id', 'active'))} via {getattr(recipe, 'id', 'Smelter')}"
                if fabricator and hasattr(fabricator, "get_recipe_inputs"):
                    fabricator_inputs = fabricator.get_recipe_inputs() or {}
                    if output_item in fabricator_inputs:
                        return f"Fabricator via {getattr(recipe, 'id', 'Smelter')}"
        except Exception:
            pass

    if fabricator and hasattr(fabricator, "get_recipe_inputs"):
        try:
            if raw_item in (fabricator.get_recipe_inputs() or {}):
                return f"Fabricator recipe {getattr(fabricator, 'get_recipe', lambda: 'active')()}"
        except Exception:
            pass

    if total_stock(raw_item) > 0:
        return "existing storage demand"
    return "active production demand"