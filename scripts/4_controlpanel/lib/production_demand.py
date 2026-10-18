# Material and Smelter demand: the order tree down to Smelter outputs, per-site
# Smelter demand, the fab-site ingot buffer, Smelter peers and raw-ore reasons.
from archive import archive
from components import component
from logistics_requests import in_flight
from priority import NEED, STOCK, deficits_text, ladder_add, ladder_add_levels, ladder_deficits, ladder_lower, ladder_max, ladder_total
from production_cascade import _recipe_inputs_for, _stock_fn, fabricator_target_ladders, get_fabricator_targets
from production_core import _add_demand, _ceil, _default_fabricator, _default_smelter, discover_fabricator_ids, discover_smelter_ids, log, machine_outpost_id
from production_demand_record import smelter_entry
from production_docks import _dock_order_remaining, dock_order_prios, find_dock_order_requiring, order_prio_of
from production_sites import fab_site_gross_need, get_fabricator_active_recipe
from production_source import SourceCache
from script_parking import wake_on_rise
from storage import default_stock_target, total_stock
from swallow import swallowed


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
        candidate = component(smelter_id)
        if not candidate or not hasattr(candidate, "get_recipe"):
            continue
        try:
            if candidate.get_recipe() == recipe_id:
                count += 1
        except Exception as error:
            swallowed("production_demand.get_smelter_worker_count: candidate.get_recipe", error)
    return max(1, count)


def get_material_demands(cache: "SourceCache | None" = None):
    """Returns material quantities currently requested by production and shipping.

    NOTE: for Smelter outputs (ingots, glass, ...) this only sees the direct
    inputs of each Fabricator's *currently selected* recipe -- lib/smelter.py
    uses get_smelter_demands() instead, which follows the whole order tree."""
    log.start("get_material_demands", level="debug")
    stock = _stock_fn(cache)
    demands = {}

    # Finished fabricated goods have a Fabricator target (orders, cascade) and
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
        fabricator = component(fabricator_id)
        if not fabricator:
            continue
        recipe, crafts_remaining, _prio = get_fabricator_active_recipe(fabricator, cache)
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


def get_smelter_demands(cache: "SourceCache | None" = None):
    """
    {smelter_output_item: ladder of units still to refine} -- what
    lib/smelter.py should actually produce, following the WHOLE order tree
    down to Smelter outputs (ingots, glass, ...), not just the direct inputs
    of whatever recipe a Fabricator happens to have selected right now. Each
    level carries the prio of the demand it serves (lib/priority.py), so a
    Smelter refines an order's ingots before a buffer's; ladder_total() is
    the flat figure.

    get_material_demands() only sees ingot demand through each Fabricator's
    get_fabricator_active_recipe() (already split per worker, each share
    netted against the full total_stock() separately), and
    _cascade_fabricator_output_demand() stops at Smelter outputs. So a large
    order reads as ~1 ingot there. This walks the whole order tree instead,
    so Smelters see the real ore demand.

    Gross-then-net-once:
      1. Every fabricator_target_ladders() entry (manual orders, the orders
         book, docks, blueprints, and the Fabricator-intermediate cascade --
         which already propagates a top-level order's shortfall into every
         Fabricator-built intermediate's own target) with a deficit D at
         some level against SourceCache.network_have() (units built, running
         or staged need no more ingots) contributes D x ratio at that level's
         prio for each of its recipe inputs that is a Smelter output. Each
         Fabricator output's own direct ingot use is distinct, so summing
         these doesn't double-count.
      2. A target set directly on a Smelter output (the key-unlock
         look-ahead, a dock order fabricator_root_targets() already folded
         in) counts as gross need as-is, level by level.
      3. Dock orders for Smelter outputs NOT already covered by (2), at the
         order's prio.
      4. Net once against SourceCache.network_have(): stock anywhere on the
         network (home Inventory + every outpost's Warehouses + hauler cargo, so
         ingots a remote Smelter made aren't refined again at home), units
         staged in every Fabricator's stockpile, and Smelter output not yet in
         storage (output slots and running crafts). Stock covers the highest
         levels first (ladder_lower()).

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
    targets = fabricator_target_ladders(cache)
    for item_id, levels in targets.items():
        if item_id in smelter_outputs:
            ladder_add_levels(gross.setdefault(item_id, []), levels)
            log.trace(f"direct target on smelter output {item_id} -> gross += {levels}")
            continue
        deficits = ladder_deficits(levels, cache.network_have(item_id))
        if not deficits:
            continue
        for input_id, ratio in (_recipe_inputs_for(item_id, cache) or {}).items():
            if input_id in smelter_outputs:
                child = gross.setdefault(input_id, [])
                for prio, missing in deficits:
                    ladder_add(child, prio, _ceil(missing * ratio))
                if log.verbose:
                    log.trace(f"{item_id} short {deficits_text(deficits)} x {ratio:.2f} -> {input_id} gross {child}")

    dock_remaining = _dock_order_remaining()
    prios = (cache._order_prios if cache._order_prios is not None else dock_order_prios()) if dock_remaining else {}
    for order_id, remaining_by_item in dock_remaining.items():
        for item_id, remaining in remaining_by_item.items():
            if item_id not in smelter_outputs or item_id in targets:
                continue  # not ours, or already counted via fabricator_target_ladders()
            if remaining > 0:
                ladder_add(gross.setdefault(item_id, []), order_prio_of(order_id, prios), remaining)
                log.trace(f"order {order_id} still needs {remaining}x {item_id}")

    demands = {}
    for item_id, levels in gross.items():
        have = cache.network_have(item_id)
        net = ladder_lower(levels, have)
        if net:
            demands[item_id] = net
        log.debug(f"{item_id} gross={ladder_total(levels)} network_have={have} (stock {cache.network_stock(item_id)}) -> net={net}")
    log.end()
    return demands


def site_smelter_demands(outpost: "OutpostRef | None", cache: "SourceCache | None" = None):
    """
    {smelter_output: ladder} a site's own Fabricators still need
    (fab_site_gross_need(), at each recipe's prio) minus that output's local
    stock, units in flight to the site and the site's Smelter output not yet
    in storage (SourceCache.pipeline_units()). lib/smelter.py merges it (per
    level max) with get_smelter_demands() for every Smelter, home included:
    the network-wide figure nets against stock anywhere, so it misses a site
    short of an output that sits at another outpost.
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
    for item_id, levels in gross.items():
        local = cache.local_stock(item_id, outpost)
        smelting = cache.pipeline_units(item_id, getattr(outpost, "id", None))
        net = ladder_lower(levels, local + flying.get(item_id, 0) + smelting)
        if net:
            demands[item_id] = net
        log.debug(f"{item_id} gross={ladder_total(levels)} local={local} in_flight={flying.get(item_id, 0)} smelting={smelting} -> net={net}")
    log.end()
    return demands


# Fab-site ingot buffer: every outpost with a Fabricator keeps each Smelter
# output a Fabricator recipe takes on hand, so a recipe switch finds its
# ingots staged instead of waiting on single Smelter crafts. "target" is the
# buffer tier (local Smelters refill it in idle time, site_supply requests
# it), "need" the need tier hauled ahead of other sites' buffers. Seeded once
# per item, then editable: {item_id: {"target": n, "need": n}}.
INGOT_STOCK_TARGETS_KEY = "production.ingot_stock_targets"
INGOT_STOCK_NEED = 100


def _ingot_level(entry, key, default):
    """entry[key] as a non-negative int (one INGOT_STOCK_TARGETS_KEY entry), else default."""
    value = entry.get(key) if isinstance(entry, dict) else None
    if value is None or not isinstance(value, (int, float)) or value < 0:
        return default
    return int(value)


def ingot_stock_levels(item_ids):
    """{item_id: (target, need)} from INGOT_STOCK_TARGETS_KEY. Items not stored
    yet get target storage.default_stock_target() and need INGOT_STOCK_NEED,
    seeded into the archive only once Warehouses are unlocked."""
    stored = archive.get(INGOT_STOCK_TARGETS_KEY, {})
    stored = stored if isinstance(stored, dict) else {}
    missing = [i for i in item_ids if not isinstance(stored.get(i), dict)]
    default_target, final = default_stock_target()
    if missing and final:

        def updater(levels):
            levels = dict(levels) if isinstance(levels, dict) else {}
            for item_id in missing:
                if not isinstance(levels.get(item_id), dict):
                    levels[item_id] = {"target": default_target, "need": INGOT_STOCK_NEED}
            return levels

        archive.transaction(INGOT_STOCK_TARGETS_KEY, {}, updater)
        log.debug(f"ingot_stock_levels: seeded defaults for {missing}")
        wake_on_rise(("smelter",), {}, {item_id: default_target for item_id in missing}, "ingot target")
        stored = archive.get(INGOT_STOCK_TARGETS_KEY, {})
        stored = stored if isinstance(stored, dict) else {}
    levels = {}
    for item_id in item_ids:
        target = _ingot_level(stored.get(item_id), "target", default_target)
        need = _ingot_level(stored.get(item_id), "need", INGOT_STOCK_NEED)
        levels[item_id] = (target, min(need, target))
    return levels


def fab_site_ingot_targets(outpost: "OutpostRef | None", cache: "SourceCache"):
    """{smelter_output: (target, need)} the ingot buffer this outpost keeps:
    every Smelter output some Fabricator recipe takes as input, {} when the
    outpost has no Fabricator. The same at every outpost with a Fabricator."""
    if not discover_fabricator_ids(outpost):
        return {}
    smelter_outputs = {getattr(r, "output_item", None) for r in cache.smelter_recipes()}
    smelter_outputs.discard(None)
    inputs = set()
    for recipe in cache.fabricator_recipes():
        inputs |= set(getattr(recipe, "inputs", {}) or {})
    items = sorted(smelter_outputs & inputs)
    return ingot_stock_levels(items) if items else {}


def smelter_site_record(outpost: "OutpostRef", cache: "SourceCache"):
    """(demands, have) of one smelting site for the demand record: site_smelter_demands()
    merged per level (max) with site_ingot_ladders() (the buffer bands, computed here where the
    cache is warm: they read every machine's holdings), and held_stock() there of every Smelter
    output. `have` is held stock, not fab_have(): a reader nets by the local stock change alone,
    which costs one local scan instead of every machine's holdings
    (smelter_demands_from_record())."""
    outputs = {getattr(r, "output_item", None) for r in cache.smelter_recipes()} - {None}
    demands = site_smelter_demands(outpost, cache)
    for item_id, levels in site_ingot_ladders(outpost, cache).items():
        demands[item_id] = ladder_max(demands.get(item_id, []), levels)
    return demands, {item_id: cache.held_stock(item_id, outpost) for item_id in sorted(outputs)}


def smelter_demands_from_record(record, outpost: "OutpostRef | None", cache: "SourceCache"):
    """
    {smelter_output: ladder} for a Smelter at `outpost` from a demand record: the network
    ladders and the site's ladders (its Fabricators' need and the ingot buffer, see
    smelter_site_record()), each lowered by the units that reached this site's storage since
    the record (held_stock() now minus the record's `have`; output pushed straight into a
    Fabricator or made at another site shows at the next record), merged per level (max).
    Reads one local stock scan and no machine holdings: what get_smelter_demands() +
    site_smelter_demands() + site_ingot_ladders() give when the record is current.
    """
    network, _none = smelter_entry(record)
    site_demands, have = smelter_entry(record, getattr(outpost, "id", None))
    demands = {}
    for source in (network, site_demands):
        for item_id, levels in source.items():
            made = max(0, cache.held_stock(item_id, outpost) - have[item_id]) if item_id in have else 0
            net = ladder_lower(levels, made)
            if net:
                demands[item_id] = ladder_max(demands.get(item_id, []), net)
    return demands


def site_ingot_ladders(outpost: "OutpostRef | None", cache: "SourceCache", targets=None, item_ids=None):
    """{smelter_output: ladder} this fab site's ingot buffer still lacks:
    [[NEED, need], [STOCK, target]] minus local stock, units in flight here
    and the site's Smelter output not yet in storage
    (SourceCache.pipeline_units()). lib/smelter.py merges it into its demand
    map, where the buffer's bands rank under every order. `targets` =
    fab_site_ingot_targets() when already read (it may seed the archive, so
    an atomic caller reads it first); `item_ids` limits the walk to those
    items (lib/demand_publisher.py runs the items in batches)."""
    if targets is None:
        targets = fab_site_ingot_targets(outpost, cache)
    if item_ids is not None:
        targets = {item_id: levels for item_id, levels in targets.items() if item_id in item_ids}
    if not targets:
        return {}
    flying = in_flight(getattr(outpost, "id", None))
    refill = {}
    for item_id, (target, need) in targets.items():
        levels = [[NEED, need], [STOCK, target]] if 0 < need < target else [[STOCK, target]]
        have = cache.local_stock(item_id, outpost) + flying.get(item_id, 0) + cache.pipeline_units(item_id, getattr(outpost, "id", None))
        net = ladder_lower(levels, have)
        if net:
            refill[item_id] = net
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
        candidate = component(smelter_id)
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


def get_raw_material_reason(raw_item, smelter: "Smelter | None" = None):
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
