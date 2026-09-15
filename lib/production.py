# Shared production-demand planning for mining and refining automation.
from archive import archive
from storage import total_stock


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
            order = dock.current_order()
        except Exception:
            continue
        if order:
            pairs.append((dock, order))
    return pairs


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


def can_source_fluid(fluid_key):
    """
    Whether any building type that could feed this FluidPort exists anywhere
    on the outpost network. Deliberately checks existence only, not an
    actual completed pipe route or fluid level -- matching can_source_item()'s
    own "known source" bar (a surveyed site doesn't guarantee a working claim
    either) -- so this only rules out the "not built at all yet" case, not
    "built but not yet piped/full".
    """
    type_ids = FLUID_SOURCE_TYPE_IDS.get(fluid_key)
    if not type_ids:
        return True  # unrecognized fluid key -- don't block on something we don't model
    network = _component("outpost_network")
    if not network or not hasattr(network, "outposts"):
        return False
    try:
        for outpost in network.outposts():
            for type_id in type_ids:
                if outpost.buildings(type_id):
                    return True
    except Exception:
        pass
    return False


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


def _cascade_blueprint_demand():
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

    def recipe_inputs_for(item_id):
        """{input_item_id: qty_per_output_unit} for whichever of Fabricator/
        Smelter builds item_id, or None if neither does."""
        for component in (_default_fabricator(), _default_smelter()):
            if not component or not hasattr(component, "list_recipes"):
                continue
            try:
                for recipe in component.list_recipes():
                    if getattr(recipe, "output_item", None) != item_id:
                        continue
                    output_count = max(1, getattr(recipe, "output_count", 1))
                    inputs = getattr(recipe, "inputs", {}) or {}
                    return {in_id: qty / output_count for in_id, qty in inputs.items()}
            except Exception:
                continue
        return None

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

    total_needed = {}
    depth = 0
    while frontier and depth < 6:  # generous bound against an accidental recipe cycle
        depth += 1
        next_frontier = {}
        for item_id, want in frontier.items():
            total_needed[item_id] = total_needed.get(item_id, 0) + want
            shortfall = max(0, want - total_stock(item_id))
            if shortfall <= 0:
                continue
            inputs = recipe_inputs_for(item_id)
            if not inputs:
                continue
            for input_id, ratio in inputs.items():
                next_frontier[input_id] = next_frontier.get(input_id, 0) + (shortfall * ratio)
        frontier = next_frontier

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


def get_fabricator_targets():
    """Returns desired finished-goods quantities for Fabricator planning."""
    targets = get_fabricator_stock_targets()

    fabricator_outputs = set()
    fabricator = _default_fabricator()
    if fabricator and hasattr(fabricator, "list_recipes"):
        try:
            for recipe in fabricator.list_recipes():
                output_item = getattr(recipe, "output_item", None)
                if output_item:
                    fabricator_outputs.add(output_item)
        except Exception:
            pass

    for dock, order in _all_dock_orders():
        if not hasattr(order, "requires"):
            continue
        try:
            shipped = getattr(order, "shipped", {}) or {}
            for item_id, required in order.requires.items():
                # Only order items the Fabricator can actually build become
                # targets; other order items (raw/mined) are handled by
                # the dock demand loop in get_material_demands() and must
                # not be double-counted here.
                if item_id not in targets and item_id not in fabricator_outputs:
                    continue
                remaining = required - shipped.get(item_id, 0)
                targets[item_id] = max(targets.get(item_id, 0), remaining)
        except Exception:
            pass

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
    for item_id, count in _cascade_blueprint_demand().items():
        if item_id in fabricator_outputs:
            targets[item_id] = max(targets.get(item_id, 0), count)

    return targets


def _fabricator_worker_count(recipe_id):
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


def get_fabricator_active_recipe(fabricator=None):
    """Returns (recipe, crafts_remaining) for the Fabricator's selected recipe,
    where crafts_remaining covers the full remaining shortfall against its
    output target/order (not just one craft's worth), divided evenly across
    every Fabricator currently working this same recipe (see
    _fabricator_worker_count()) so several Fabricators piled onto one
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
        current = total_stock(output_item)
        output_buffer = fabricator.get_output_count() if hasattr(fabricator, "get_output_count") else 0
        target = get_fabricator_targets().get(output_item, 0)
        still_needed = max(0, target - current - output_buffer)
        crafts_remaining = -(-still_needed // output_count)  # ceil division
        worker_count = _fabricator_worker_count(current_recipe_id)
        if worker_count > 1:
            crafts_remaining = -(-crafts_remaining // worker_count)  # ceil division -- an odd remainder goes to every worker equally rather than being dropped, converging (not undershooting) once demand nets back down on the next poll
        return recipe, crafts_remaining
    except Exception:
        return None, 0


def get_material_demands():
    """Returns material quantities currently requested by production and shipping."""
    demands = {}

    # Finished fabricated goods have a standing building-stock target and
    # may also be required by the active Supply Dock order.
    for item_id, target in get_fabricator_targets().items():
        current = total_stock(item_id)
        _add_demand(demands, item_id, max(0, target - current))

    # A selected Fabricator recipe is an explicit production intention; scale
    # by every remaining craft still needed to reach the target, not just one
    # craft's worth, or demand collapses to 0 as soon as a single unit of an
    # input is on hand even though hundreds more crafts remain.
    fabricator = _default_fabricator()
    recipe, crafts_remaining = get_fabricator_active_recipe(fabricator)
    if recipe and crafts_remaining > 0:
        try:
            stockpile = fabricator.get_stockpile() or {}
            for item_id, required in (getattr(recipe, "inputs", {}) or {}).items():
                missing = (required * crafts_remaining) - stockpile.get(item_id, 0)
                missing -= total_stock(item_id)
                _add_demand(demands, item_id, max(0, missing))
        except Exception:
            pass

    # Every dock's active order is a current downstream shipping requirement.
    for dock, order in _all_dock_orders():
        if not hasattr(order, "requires"):
            continue
        try:
            shipped = getattr(order, "shipped", {}) or {}
            for item_id, required in order.requires.items():
                missing = required - shipped.get(item_id, 0)
                if hasattr(dock, "count"):
                    missing -= dock.count(item_id)
                missing -= total_stock(item_id)
                _add_demand(demands, item_id, max(0, missing))
        except Exception:
            pass

    return demands


def get_raw_material_demands(smelter=None):
    """Converts refined-material demand into raw ore demand for mining."""
    demands = get_material_demands()
    refined_demands = dict(demands)
    raw_demands = {}

    # Raw items requested directly by an order are mined as-is.
    for item_id, quantity in demands.items():
        if item_id.endswith("_ore") or item_id in ["silicon", "rare_earth"]:
            current = total_stock(item_id)
            _add_demand(raw_demands, item_id, max(0, quantity - current))

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
                    _add_demand(refined_demands, input_id, max(0, needed - current))
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
                    _add_demand(raw_demands, raw_item, max(0, output_need * units_per_run - current))
        except Exception:
            pass

    return raw_demands


def _has_surveyed_mineral(item_id):
    journal = _component("journal")
    if not journal or not hasattr(journal, "surveyed_sites"):
        return False
    try:
        return any(
            getattr(site, "kind", lambda: "")() == "mineral"
            and getattr(site, "item_id", None) == item_id
            for site in journal.surveyed_sites("nocturna")
        )
    except Exception:
        return False


def can_source_item(item_id, seen=None):
    """Whether an item has storage (Inventory/Warehouse), surveyed-source, or unlocked recipe supply."""
    if total_stock(item_id) > 0:
        return True

    seen = set() if seen is None else seen
    if item_id in seen:
        return False
    seen.add(item_id)

    if _has_surveyed_mineral(item_id):
        return True

    for component in [_default_smelter(), _default_fabricator()]:
        if not component or not hasattr(component, "list_recipes"):
            continue
        try:
            recipes = component.list_recipes()
        except Exception:
            continue
        for recipe in recipes:
            if getattr(recipe, "output_item", None) != item_id:
                continue
            inputs = getattr(recipe, "inputs", {}) or {}
            fluid_inputs = getattr(recipe, "fluid_inputs", {}) or {}
            if all(can_source_fluid(fk) for fk in fluid_inputs) and all(can_source_item(input_id, seen.copy()) for input_id in inputs):
                return True

    return False


def can_fulfill_order(order):
    """Checks whether every remaining order item has a currently known source."""
    if not order or not hasattr(order, "requires"):
        return False
    shipped = getattr(order, "shipped", {}) or {}
    for item_id, required in order.requires.items():
        remaining = max(0, required - shipped.get(item_id, 0))
        if remaining > 0 and not can_source_item(item_id):
            return False
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