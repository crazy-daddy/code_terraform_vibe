# Material and Smelter demand: the order tree down to Smelter outputs, per-site
# Smelter demand, the fab-site ingot buffer, Smelter peers and raw-ore reasons.
from archive import archive
from storage import total_stock
from logistics_requests import in_flight
from swallow import swallowed
from production_core import discover_fabricator_ids, discover_smelter_ids, log, machine_outpost_id, _add_demand, _ceil, _component, _default_fabricator, _default_smelter
from production_docks import find_dock_order_requiring, _dock_order_remaining
from production_source import SourceCache
from production_cascade import get_fabricator_targets, _recipe_inputs_for, _stock_fn
from production_sites import fab_site_gross_need, get_fabricator_active_recipe


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
        except Exception as error:
            swallowed("production_demand.get_smelter_worker_count: candidate.get_recipe", error)
    return max(1, count)


def get_material_demands(cache=None):
    """Returns material quantities currently requested by production and shipping.

    NOTE: for Smelter outputs (ingots, glass, ...) this only sees the direct
    inputs of each Fabricator's *currently selected* recipe -- lib/smelter.py
    uses get_smelter_demands() instead, which follows the whole order tree."""
    log.start("get_material_demands", level="debug")
    stock = _stock_fn(cache)
    demands = {}

    # Finished fabricated goods have a standing building-stock target and
    # may also be required by the active Supply Dock order.
    for item_id, target in get_fabricator_targets(cache).items():
        current = stock(item_id)
        deficit = max(0, target - current)
        _add_demand(demands, item_id, deficit)
        if deficit > 0:
            log.trace(f"{item_id} stock={current} target={target} -> deficit={deficit}")

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
    # even with raw ore sitting in a Warehouse. So every discovered Fabricator
    # counts here, like Smelter/Supply Dock discovery (production_core.py).
    fabricator_ids = discover_fabricator_ids() or ["fabricator_1"]
    for fabricator_id in fabricator_ids:
        fabricator = _component(fabricator_id)
        if not fabricator:
            continue
        recipe, crafts_remaining = get_fabricator_active_recipe(fabricator, cache)
        if not recipe or crafts_remaining <= 0:
            log.trace(f"{fabricator_id} has no active recipe/crafts remaining, skipping input demand")
            continue
        try:
            stockpile = fabricator.get_stockpile() or {}
            for item_id, required in (getattr(recipe, "inputs", {}) or {}).items():
                missing = (required * crafts_remaining) - stockpile.get(item_id, 0)
                missing -= stock(item_id)
                missing = max(0, missing)
                _add_demand(demands, item_id, missing)
                if missing > 0:
                    log.trace(f"{fabricator_id} recipe={getattr(recipe, 'id', '?')} needs {item_id} -> deficit={missing} (crafts_remaining={crafts_remaining})")
        except Exception as error:
            swallowed("production_demand.get_material_demands: fabricator.get_stockpile", error)

    # Every dock's active order is a current downstream shipping requirement.
    for order_id, remaining_by_item in _dock_order_remaining().items():
        for item_id, remaining in remaining_by_item.items():
            missing = max(0, remaining - stock(item_id))
            _add_demand(demands, item_id, missing)
            if missing > 0:
                log.trace(f"order {order_id} needs {item_id} -> deficit={missing}")

    log.trace(f"final demands={demands}")
    log.end()
    return demands


def get_smelter_demands(cache=None):
    """
    {smelter_output_item: units_still_to_refine} -- what lib/smelter.py
    should actually produce, following the WHOLE order tree down to Smelter
    outputs (ingots, glass, ...), not just the direct inputs of whatever
    recipe a Fabricator happens to have selected right now.

    get_material_demands() only sees ingot demand through each Fabricator's
    get_fabricator_active_recipe() (already split per worker, each share
    netted against the full total_stock() separately), and
    _cascade_fabricator_output_demand() stops at Smelter outputs. So a large
    order reads as ~1 ingot there. This walks the whole order tree instead,
    so Smelters see the real ore demand.

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
      4. Net once: minus stock anywhere on the network (home Inventory +
         every outpost's Warehouses + hauler cargo, SourceCache.network_stock(), so ingots
         a remote Smelter made aren't refined again at home) and minus what's
         already staged in every Fabricator's stockpile.

    Pass the step's SourceCache -- this walks the full target set, so it is
    not cheap uncached.
    """
    cache = SourceCache() if cache is None else cache
    smelter_outputs = {getattr(r, "output_item", None) for r in cache.smelter_recipes()}
    smelter_outputs.discard(None)
    if not smelter_outputs:
        return {}

    log.start("get_smelter_demands", level="debug")
    gross = {}
    targets = get_fabricator_targets(cache)
    for item_id, target in targets.items():
        if item_id in smelter_outputs:
            _add_demand(gross, item_id, target)
            log.trace(f"direct target on smelter output {item_id} -> gross += {target}")
            continue
        deficit = target - cache.network_stock(item_id)
        if deficit <= 0:
            continue
        for input_id, ratio in (_recipe_inputs_for(item_id, cache) or {}).items():
            if input_id in smelter_outputs:
                need = _ceil(deficit * ratio)
                _add_demand(gross, input_id, need)
                log.trace(f"{item_id} deficit={deficit} x {ratio:.2f} -> {input_id} gross += {need}")

    for order_id, remaining_by_item in _dock_order_remaining().items():
        for item_id, remaining in remaining_by_item.items():
            if item_id not in smelter_outputs or item_id in targets:
                continue  # not ours, or already counted via get_fabricator_targets()
            _add_demand(gross, item_id, remaining)
            if remaining > 0:
                log.trace(f"order {order_id} still needs {remaining}x {item_id}")

    staged = {}
    for fabricator_id in discover_fabricator_ids():
        fabricator = _component(fabricator_id)
        if not fabricator or not hasattr(fabricator, "get_stockpile"):
            continue
        try:
            for item_id, count in (fabricator.get_stockpile() or {}).items():
                if item_id in gross:
                    staged[item_id] = staged.get(item_id, 0) + count
        except Exception as error:
            swallowed("production_demand.get_smelter_demands: (fabricator.get_stockpile() or {}).items", error)

    demands = {}
    for item_id, qty in gross.items():
        stock = cache.network_stock(item_id)
        net = qty - stock - staged.get(item_id, 0)
        if net > 0:
            demands[item_id] = net
        log.debug(f"{item_id} gross={qty} network_stock={stock} staged_in_fabricators={staged.get(item_id, 0)} -> net={max(0, net)}")
    log.end()
    return demands


def site_smelter_demands(outpost, cache=None):
    """
    {smelter_output: units} a site's own Fabricators still need
    (fab_site_gross_need()) minus that output's local stock and units in
    flight to the site. lib/smelter.py merges it (per item max) with
    get_smelter_demands() for every Smelter, home included: the network-wide
    figure nets against stock anywhere, so it misses a site short of an
    output that sits at another outpost.
    """
    cache = SourceCache() if cache is None else cache
    smelter_outputs = {getattr(r, "output_item", None) for r in cache.smelter_recipes()}
    smelter_outputs.discard(None)
    if not smelter_outputs:
        return {}
    gross = fab_site_gross_need(discover_fabricator_ids(outpost), smelter_outputs, cache)
    if not gross:
        return {}
    flying = in_flight(getattr(outpost, "id", None))
    demands = {}
    log.start(f"site_smelter_demands({getattr(outpost, 'id', None)})", level="debug")
    for item_id, units in gross.items():
        local = cache.local_stock(item_id, outpost)
        net = units - local - flying.get(item_id, 0)
        if net > 0:
            demands[item_id] = net
        log.debug(f"{item_id} gross={units} local={local} in_flight={flying.get(item_id, 0)} -> net={max(0, net)}")
    log.end()
    return demands


# Fab-site ingot buffer: every outpost with a Fabricator keeps each Smelter
# output a Fabricator recipe takes on hand, so a recipe switch finds its
# ingots staged instead of waiting on single Smelter crafts. "target" is the
# buffer tier (local Smelters refill it in idle time, site_supply requests
# it), "need" the need tier hauled ahead of other sites' buffers. Seeded once
# per item, then editable: {item_id: {"target": n, "need": n}}.
INGOT_STOCK_TARGETS_KEY = "production.ingot_stock_targets"
INGOT_STOCK_TARGET = 2000
INGOT_STOCK_NEED = 100


def _ingot_level(entry, key, default):
    """entry[key] as a non-negative int (one INGOT_STOCK_TARGETS_KEY entry), else default."""
    value = entry.get(key) if isinstance(entry, dict) else None
    if value is None or not isinstance(value, (int, float)) or value < 0:
        return default
    return int(value)


def ingot_stock_levels(item_ids):
    """{item_id: (target, need)} from INGOT_STOCK_TARGETS_KEY, seeding the
    INGOT_STOCK_TARGET/INGOT_STOCK_NEED defaults for any item not stored yet."""
    stored = archive.get(INGOT_STOCK_TARGETS_KEY, {})
    stored = stored if isinstance(stored, dict) else {}
    missing = [i for i in item_ids if not isinstance(stored.get(i), dict)]
    if missing:
        def updater(levels):
            levels = dict(levels) if isinstance(levels, dict) else {}
            for item_id in missing:
                if not isinstance(levels.get(item_id), dict):
                    levels[item_id] = {"target": INGOT_STOCK_TARGET, "need": INGOT_STOCK_NEED}
            return levels
        archive.transaction(INGOT_STOCK_TARGETS_KEY, {}, updater)
        log.debug(f"ingot_stock_levels: seeded defaults for {missing}")
        stored = archive.get(INGOT_STOCK_TARGETS_KEY, {})
        stored = stored if isinstance(stored, dict) else {}
    levels = {}
    for item_id in item_ids:
        target = _ingot_level(stored.get(item_id), "target", INGOT_STOCK_TARGET)
        need = _ingot_level(stored.get(item_id), "need", INGOT_STOCK_NEED)
        levels[item_id] = (target, min(need, target))
    return levels


def fab_site_ingot_targets(outpost, cache):
    """{smelter_output: (target, need)} the ingot buffer this outpost keeps:
    every Smelter output some Fabricator recipe takes as input, {} when the
    outpost has no Fabricator."""
    if not discover_fabricator_ids(outpost):
        return {}
    smelter_outputs = {getattr(r, "output_item", None) for r in cache.smelter_recipes()}
    smelter_outputs.discard(None)
    inputs = set()
    for recipe in cache.fabricator_recipes():
        inputs |= set(getattr(recipe, "inputs", {}) or {})
    items = sorted(smelter_outputs & inputs)
    return ingot_stock_levels(items) if items else {}


def site_ingot_refill(outpost, cache):
    """{smelter_output: units} this fab site's ingot buffer still lacks:
    target - local stock - units in flight here. lib/smelter.py works it only
    when no real demand is sourceable."""
    targets = fab_site_ingot_targets(outpost, cache)
    if not targets:
        return {}
    flying = in_flight(getattr(outpost, "id", None))
    refill = {}
    for item_id, (target, _need) in targets.items():
        units = target - cache.local_stock(item_id, outpost) - flying.get(item_id, 0)
        if units > 0:
            refill[item_id] = units
    return refill


def smelter_recipe_peers(recipe_id, outpost_id=None):
    """(worker_count, buffered_units) across every discovered Smelter currently
    holding recipe_id -- get_smelter_worker_count() plus the sum of their
    input buffers, in one walk. With `outpost_id`, only Smelters deployed at
    that outpost count: they draw from the same local ore pool, which is what
    lib/smelter.py's fair-share cap splits ((available ore + everything
    already buffered by these peers) // workers). Without it, every Smelter
    on the network counts, which is what splitting network-wide demand
    needs. worker_count is at least 1."""
    count = 0
    buffered = 0
    for smelter_id in discover_smelter_ids():
        candidate = _component(smelter_id)
        if not candidate or not hasattr(candidate, "get_recipe"):
            continue
        try:
            if candidate.get_recipe() != recipe_id:
                continue
            if outpost_id is not None and machine_outpost_id(candidate) != outpost_id:
                continue
            count += 1
            buffered += candidate.get_input_count() if hasattr(candidate, "get_input_count") else 0
        except Exception as error:
            swallowed("production_demand.smelter_recipe_peers: candidate.get_recipe", error)
    return max(1, count), buffered


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
        except Exception as error:
            swallowed("production_demand.get_raw_material_reason: smelter.list_recipes", error)

    if fabricator and hasattr(fabricator, "get_recipe_inputs"):
        try:
            if raw_item in (fabricator.get_recipe_inputs() or {}):
                return f"Fabricator recipe {getattr(fabricator, 'get_recipe', lambda: 'active')()}"
        except Exception as error:
            swallowed("production_demand.get_raw_material_reason: fabricator.get_recipe_inputs", error)

    if total_stock(raw_item) > 0:
        return "existing storage demand"
    return "active production demand"
