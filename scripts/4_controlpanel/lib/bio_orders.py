# Shared order and stock helpers of the bio pipeline: biome, sibling and
# processor discovery, the local stock snapshot, and Bio Order focus/demand.
# Imported by bio.py's controllers and every bio_<biome>.py processor; split
# from bio.py so the processors don't pay for the pipeline controllers.
from functools import lru_cache

from storage import discover_storage_buildings, outpost_is_home, total_stock
from swallow import swallowed
from tree_console import TreeConsole

# Module-level singleton for the shared, biome-agnostic helper functions below
# (get_my_biome, local_sibling, local_stock_snapshot, focus_local_order,
# order_fragment_remaining, etc.) -- none of them are class methods, so none
# have a self.log to use. Constructed once at import time, same as every
# other module-scoped `log` singleton elsewhere in lib/ (see storage.py,
# production.py) -- these helpers are called every step() cycle by every
# bio_*.py controller, so a per-call TreeConsole() would violate the
# "construct once" rule.
log = TreeConsole(module="bio")


def get_my_biome(machine):
    if hasattr(machine, "outpost") and machine.outpost:
        return getattr(machine.outpost, "biome", None)
    return None


def local_sibling(outpost: "OutpostRef | None", type_id):
    """
    First same-outpost sibling component of type_id (e.g. a Bio Lab's own Bio
    Collector, or a Bio Collector's own Bio Exchange/Bio Lab), discovered via
    outpost.buildings(type_id) rather than a hardcoded instance id like
    "bio_collector_1" -- a save with more than one Bio pipeline (e.g. a second
    one at a remote outpost, see docs/AI_CHEATSHEET.md Phase 4) needs each
    controller to find its OWN outpost's sibling, not always the same
    hardcoded home-outpost instance. Returns None if this outpost has none
    (or outpost is None/unavailable).
    """
    log.start(f"local_sibling({type_id})", level="debug")
    if not outpost or not hasattr(outpost, "buildings"):
        log.end()
        return None
    try:
        found = outpost.buildings(type_id)
    except Exception:
        log.trace("outpost.buildings() raised -- treating as none found.")
        log.end()
        return None
    if not found:
        log.trace("no matching sibling building at this outpost.")
        log.end()
        return None
    b_id = getattr(found[0], "id", None)
    result = get_component(b_id) if b_id else None
    log.trace(f"resolved to '{b_id}' -> {'found' if result else 'get_component failed'}.")
    log.end()
    return result


def local_stock(item_id, outpost: "OutpostRef"):
    """Units of item_id a Bio Lab at `outpost` can reach: storage.total_stock()
    there (Inventory only at home)."""
    return total_stock(item_id, outpost)


def is_local_order(ord_info, my_biome):
    if not my_biome:
        return True
    ord_biome = getattr(ord_info, "biome", None)
    if not ord_biome:
        return True
    return ord_biome == my_biome or ord_biome in my_biome or my_biome in ord_biome


def is_order_incomplete(ord_info):
    """
    Checks if an order is incomplete.
    Note: percent in BioOrder is an integer (0..100) or float (0.0..1.0).
    We check both ord_info.status and percent (< 100).
    """
    if getattr(ord_info, "status", "") == "complete":
        return False
    pct = getattr(ord_info, "percent", 0.0)
    # If percent is formatted as 0..100 (e.g. 13% or 4%), compare against 100
    if pct >= 100:
        return False
    # If percent is formatted as 0.0..1.0, compare against 1.0 (unless it's an integer >= 1)
    if isinstance(pct, float) and pct >= 1.0:
        return False
    return True


# Every biome-transform building this pipeline knows how to drive, in no particular
# order -- an outpost has at most one of these deployed (Frozen has none at all).
BIOME_PROCESSOR_TYPE_IDS = ["bio_luminizer", "bio_caster", "bio_conditioner", "dna_sequencer"]


def local_biome_processor(outpost: "OutpostRef"):
    """
    (component, type_id) for whichever biome-transform building is deployed at this
    outpost -- Bio Luminizer (Coastal), Bio Caster (Volcanic), Bio Conditioner (Deep),
    or DNA Sequencer (Geothermal) -- discovered the same capability-probing way as
    local_sibling(), never assumed from the outpost's biome. Returns (None, None) for
    Frozen (which has none) or an outpost that hasn't had its processor deployed yet.

    Deliberately never imports bio_coastal/bio_volcanic/bio_deep/bio_geothermal to
    call anything on the returned component beyond the plain Component properties
    every one of them shares (.chamber, .input, .output, .fragment()) -- this module
    only needs to know THAT a processor is present and whether it's idle
    (processor_is_idle()), never how to drive its biome-specific control loop. That
    keeps the shared pipeline stages (BioCollectorController/BioLabController/
    BioExchangeController in bio.py) biome-agnostic and avoids a circular import, since
    every bio_<biome>.py module imports helpers FROM this one.
    """
    for type_id in BIOME_PROCESSOR_TYPE_IDS:
        comp = local_sibling(outpost, type_id)
        if comp:
            return comp, type_id
    return None, None


def processor_is_idle(processor, processor_type):
    """
    True when the local biome processor's chamber, input, and output are all
    empty -- i.e. genuinely ready for a new sample, not still holding/working the
    previous one. Used by BioLabController to gate pulling the next specimen from
    the Collector and draining its own extracted output into the Warehouse: since
    Collector/Lab/processor are each single-slot hardware, refusing both of those
    two actions until the processor is fully idle bounds the pipeline to at most one
    raw specimen in flight ahead of it at a time -- no Warehouse pileup is
    structurally possible regardless of how broadly the Collector searches for
    "needed" fragments (see docs/AI_CHEATSHEET.md Sec 1f for the numeric per-fragment
    throttle this structural approach replaced, originally for Coastal only).

    Generalizes the old Luminizer-only idle check to whichever of the four processor
    types is actually present -- they don't share one shape: Bio Luminizer/DNA
    Sequencer expose a `.chamber` property, while Bio Caster/Bio Conditioner instead
    expose a `.fragment()` method (no `.chamber` at all, per their component docs).

    True when there's no local processor at all (Frozen, or an outpost with none
    deployed yet), so this gate never blocks a Lab that isn't feeding one.
    """
    if not processor:
        return True
    try:
        if processor_type in ("bio_luminizer", "dna_sequencer"):
            if processor.chamber is not None:
                return False
        elif processor_type == "bio_caster":
            if processor.fragment() is not None:
                return False
        elif processor_type == "bio_conditioner":
            if processor.fragment() is not None or processor.is_running():
                return False
        if processor.input.count() > 0:
            return False
        if processor.output.count() > 0:
            return False
    except Exception as error:
        swallowed("bio_orders.processor_is_idle: processor.fragment", error)
        return True
    return True


def processor_fragment_preference(processor, processor_type, fragment_ids):
    """
    fragment_ids ordered so the local processor switches setup as rarely as
    possible. Bio Caster: its selected recipe() first (repeat casts need no
    re-heat), then the smallest gap between temperature() and each recipe's
    temperature_range. Other processor types have no setup cost, so the input
    order is kept. Collector and Caster both rank with this, so the Collector
    harvests the fragment the Caster wants next.
    """
    fragment_ids = list(fragment_ids)
    if not processor or processor_type != "bio_caster":
        return fragment_ids
    try:
        current = processor.recipe()
        temp = processor.temperature()
    except Exception as error:
        swallowed("bio_orders.processor_fragment_preference: processor.recipe", error)
        return fragment_ids

    def gap(fragment_id):
        try:
            recipe = processor.find_recipe(fragment_id)
            band = getattr(recipe, "temperature_range", None) if recipe is not None else None
        except Exception as error:
            swallowed("bio_orders.processor_fragment_preference: processor.find_recipe", error)
            band = None
        if not band:
            return float("inf")
        return max(0.0, band[0] - temp, temp - band[1])

    ordered = sorted(fragment_ids, key=lambda fragment_id: (fragment_id != current, gap(fragment_id)))
    log.debug(f"processor_fragment_preference({processor_type}): recipe={current} temp={temp:.0f}C -> {ordered}")
    return ordered


def local_sources(outpost: "OutpostRef"):
    """[(source_id, component), ...] for every storage location this outpost can pull
    from: "inventory" first if home, then every discovered Warehouse at `outpost`."""
    sources = []
    if outpost_is_home(outpost):
        inv = get_component("inventory")
        if inv:
            sources.append(("inventory", inv))
    for building in discover_storage_buildings(outpost):
        sources.append((building["id"], building["component"]))
    log.trace(f"local_sources: resolved {len(sources)} source(s): {[s[0] for s in sources]}")
    return sources


def _properties_key(properties):
    """
    Canonical hashable key for an item's properties dict -- sorts keys and tuples any
    list values (glow triples, gene lists) so one snapshot index (see
    local_stock_snapshot()) works uniformly across every biome's marker shape, not
    just Coastal's glow. () for no/empty properties.
    """
    if not properties:
        return ()
    return tuple((k, tuple(v) if isinstance(v, list) else v) for k, v in sorted(properties.items()))


def local_stock_snapshot(outpost: "OutpostRef"):
    """
    One full walk of local storage (see local_sources()), returning
    (totals, by_properties):
      totals: {item_id: total_count} -- every local_stock()-equivalent answer for
        this outpost, from a SINGLE storage walk instead of one walk per item_id.
      by_properties: {(item_id, properties_key): count} -- every
        _snapshot_property_count()-equivalent answer (any biome's marker property --
        glow, genes, forged/conditioned flags, ...), same single-walk sharing.

    Caching exchange.orders() alone (see focus_local_order()'s docstring) only got
    BioCollectorController.step() from ~20s to ~8s/cycle -- the remaining cost was
    THIS: local_stock()/property lookups were each independently re-walking every
    Warehouse's stacks() from scratch, once per fragment (sometimes several times per
    fragment, inside per-order loops). Building one snapshot per step() and having
    every stock/property lookup read from it instead is the same fix applied one
    layer deeper. See docs/AI_CHEATSHEET.md Sec 1f.
    """
    log.start("local_stock_snapshot", level="debug")
    log.trace("entry, walking local storage.")
    totals = {}
    by_properties = {}
    for source_id, component in local_sources(outpost):
        if not component or not hasattr(component, "stacks"):
            continue
        try:
            stacks = component.stacks()
        except Exception as error:
            swallowed("bio_orders.local_stock_snapshot: component.stacks", error)
            continue
        for stack in stacks:
            item_id = getattr(stack, "id", None)
            count = getattr(stack, "count", 0)
            if not item_id or count <= 0:
                continue
            totals[item_id] = totals.get(item_id, 0) + count
            properties = getattr(stack, "properties", None) or {}
            if properties:
                key = (item_id, _properties_key(properties))
                by_properties[key] = by_properties.get(key, 0) + count
    log.trace(f"exit, {len(totals)} distinct item id(s), {len(by_properties)} property-tagged variant(s).")
    log.end()
    return totals, by_properties


def snapshot_stock(snapshot, item_id):
    """Total local stock of item_id from a local_stock_snapshot() -- the
    snapshot-based equivalent of local_stock(item_id, outpost)."""
    totals, _ = snapshot
    return totals.get(item_id, 0)


def _snapshot_property_count(snapshot, item_id, properties):
    """
    Local stock of item_id whose properties include every key/value of `properties`
    (finished output keeps the raw sample's other properties next to the marker), from a
    local_stock_snapshot() -- generalizes the old Coastal-only glow-tuple lookup to
    any biome's marker property (glow triple, gene list, forged/conditioned flag,
    ...). Direct property comparison, NOT exchange.matches_order() --
    matches_order() only reflects whatever the Exchange's OWN active_order currently
    is, and self.set_order()/self.clear_order()/self.deliver() are all documented
    *(self only)* hardware calls: a script can only ever drive the machine it's
    physically attached to, never a sibling fetched via get_component()/
    local_sibling() (confirmed live: calling exchange.set_order() from the
    Luminizer's own script raised "PermissionError: Cannot call set_order() on
    bio_exchange_4 remotely"). So any OTHER script (a processor, the Collector) that
    needs to know "does this stack match THIS SPECIFIC order" has no way to force the
    Exchange's active order to check against -- it has to compare the relevant
    property directly instead, which needs no hardware call at all.

    None/empty `properties` always returns 0 (nothing to match against).
    """
    if not properties:
        return 0
    _, by_properties = snapshot
    wanted = set(_properties_key(properties))
    return sum(count for (stock_id, key), count in by_properties.items() if stock_id == item_id and wanted.issubset(key))


# Coarse safety-net cap on total local stock of every currently-demanded fragment
# (raw and already-processed, across every fragment type), before
# BioCollectorController pauses harvesting entirely. Biome-agnostic: it doesn't care
# whether a biome's transform step marks progress with a glow property, a gene list,
# a forged/conditioned flag, or nothing at all (Frozen) -- it just counts units of
# stuff that's demanded and sitting locally. NOT the primary flow-control mechanism --
# that's each processor controller's structural idle-gate (processor_is_idle()),
# which bounds in-flight specimens to the pipeline's own single-slot hardware
# (Collector cargo, Lab specimen/output, processor chamber/input/output) and should
# keep this number at 0-2 in a healthy pipeline. This cap exists purely as insurance
# against that structural bound somehow not holding (e.g. a sibling script not
# running) -- see docs/AI_CHEATSHEET.md Sec 1f for the numeric per-fragment throttle
# this replaces (originally Coastal/glow-only; generalized here to protect every
# biome's backlog uniformly).
MAX_LOCAL_BIO_ARTIFACTS = 4


@lru_cache(maxsize=512)
def item_category(item_id):
    """item_catalog category of item_id, or None if unknown. Static metadata, so
    looked up once per id. A raised error is not cached; the caller logs it."""
    catalog = get_component("item_catalog")
    info = catalog.lookup(item_id) if catalog else None
    return getattr(info, "category", None) if info else None


def total_demanded_artifacts(snapshot, fragment_ids):
    """Total local stock across every fragment id in `fragment_ids` (typically a
    demand dict's .keys()) -- the coarse warehouse-overflow safety net for
    BioCollectorController, independent of which biome's transform step (if any) is
    in play. See MAX_LOCAL_BIO_ARTIFACTS."""
    return sum(snapshot_stock(snapshot, f) for f in fragment_ids)


def find_matching_stack(exchange_machine: "BioExchange", item_id, outpost: "OutpostRef"):
    """
    Scans every local storage source for a stack of item_id whose exact properties
    satisfy exchange_machine.matches_order() (glow/genes/Forged/Conditioned/plain-
    sample, whatever the active order actually requires) -- the documented pattern
    (docs/components/bio_exchange.md: matches_order() before an exact take()) for
    picking the RIGHT variant instead of blindly grabbing whatever's staged first.
    Returns (source_id, properties) or None.
    """
    log.start("find_matching_stack", level="debug")
    log.trace(f"entry, item_id={item_id}")
    for source_id, component in local_sources(outpost):
        if not component or not hasattr(component, "stacks"):
            continue
        try:
            stacks = component.stacks()
        except Exception as error:
            swallowed("bio_orders.find_matching_stack: component.stacks", error)
            continue
        for stack in stacks:
            if getattr(stack, "id", None) != item_id:
                continue
            properties = getattr(stack, "properties", None)
            try:
                if exchange_machine.matches_order(item_id, properties):
                    log.trace(f"exit, matched '{source_id}' properties={properties}")
                    log.end()
                    return source_id, properties
            except Exception as error:
                swallowed("bio_orders.find_matching_stack: exchange_machine.matches_order", error)
                continue
    log.trace(f"exit, no locally-staged {item_id} variant satisfies matches_order().")
    log.end()
    return None


def _order_target_properties(order: "BioOrder", fragment_id):
    """
    The properties a local fragment_id stack must carry (as a subset, see
    _snapshot_property_count()) to already satisfy `order`: the marker each
    biome's processor adds and the Exchange checks. Coastal: the target glow plus
    luminous=True (a raw sample's glow lacks the flag). Volcanic/Deep: forged/
    conditioned, the same for every order of the biome. Geothermal returns None:
    spliced output carries an encoded dnaSequence, not a gene list a script can
    compare, so spliced stock is not netted out here.
    """
    target_glow = getattr(order, "target_glow", None)
    if target_glow:
        return {"glow": list(target_glow), "luminous": True}
    biome = getattr(order, "biome", None)
    if biome == "volcanic":
        return {"forged": True}
    if biome == "deep":
        return {"conditioned": True}
    return None


def order_fragment_remaining(order: "BioOrder", fragment_id, snapshot):
    """
    Units of fragment_id this order still genuinely needs, net of what's already
    delivered, in transit, or sitting locally already correctly processed for it
    (see _order_target_properties()/_snapshot_property_count()). Module-level (not
    just a processor controller's own delegate) so focus_local_order() can use the
    same check when picking which order to concentrate on.

    Found live: without this, an order that merely lists fragment_id in `.requires`
    -- even with its deficit for that specific fragment already fully covered --
    looked identical to one still genuinely wanting more of it. `focus_local_order()`
    could lock onto that already-satisfied order while a DIFFERENT incomplete local
    order genuinely still needed more of the same fragment; every subsequent
    per-fragment remaining-check on the locked order came back 0, so the processor
    found nothing to load and just repeated the same no-op every tick, even with
    matching raw stock sitting right there and real aggregate demand for it
    elsewhere.
    """
    needed = (order.requires or {}).get(fragment_id, 0)
    if needed <= 0:
        return 0
    delivered = (order.delivered or {}).get(fragment_id, 0)
    in_transit = (order.in_transit or {}).get(fragment_id, 0)
    remaining = needed - delivered - in_transit
    if remaining <= 0:
        return 0
    target_properties = _order_target_properties(order, fragment_id)
    already_matching = _snapshot_property_count(snapshot, fragment_id, target_properties)
    final = max(0, remaining - already_matching)
    log.trace(f"order_fragment_remaining({getattr(order, 'id', '?')}, {fragment_id}): needed={needed} delivered={delivered} in_transit={in_transit} remaining_raw={remaining} target_properties={target_properties} already_matching_local={already_matching} -> final={final}")
    return final


@log.block()
def focus_local_order(orders, snapshot, my_biome, fragment_id=None):
    """
    The ONE local, incomplete order (needing its own biome-specific processing step)
    to concentrate on right now -- optionally the one that specifically still needs
    more of fragment_id (not just any order that lists it in `.requires` -- see
    order_fragment_remaining()'s docstring for the live bug that distinction
    fixes). When fragment_id is omitted, prefers a candidate that already has local
    stock of one of its genuinely-still-needed required fragments over one needing
    fresh collection.

    Excludes Frozen orders: every other biome requires its own processor building
    (Luminizer/Caster/Conditioner/Sequencer) as a single-slot bottleneck worth
    coordinating the whole pipeline's focus around; a Frozen order has no such
    bottleneck (BioExchangeController's own blanket sweep already delivers a plain
    fragment the moment it's extracted), so narrowing focus for it would only reduce
    the Collector's options for no benefit.

    Takes an already-fetched `orders` list (exchange.orders()) rather than
    `exchange` itself -- exchange.orders() returns ~80 orders and is expensive
    to call, so callers fetch it once per step() and thread it through every
    helper that needs it instead of each fetching its own copy (per-helper
    fetching costs ~20 s/cycle; see docs/AI_CHEATSHEET.md §1f).

    Shared by BioCollectorController (used to prefer harvesting this order's
    fragments over other incomplete orders') and every processor controller (each
    delegates to this from its own biome-flavored finder) so all of them agree on
    the SAME "order we're concentrating on right now" -- e.g. a Luminizer's tint
    target and the Collector's harvest preference stay in sync. Actual
    overproduction prevention is structural (see processor_is_idle()), not
    enforced by this selection.
    """
    log.trace(f"entry, {len(orders)} order(s) to filter, my_biome={my_biome} fragment_id={fragment_id}")
    candidates = []
    for order in orders:
        if not is_order_incomplete(order):
            continue
        if not is_local_order(order, my_biome):
            continue
        if getattr(order, "biome", None) == "frozen":
            continue
        if fragment_id is not None and fragment_id not in (order.requires or {}):
            continue
        candidates.append(order)
    log.trace(f"{len(candidates)} local/incomplete/non-frozen candidate(s) survived filtering (of {len(orders)} total).")

    if not candidates:
        log.trace("exit, no candidates.")
        return None

    if fragment_id is not None:
        for order in candidates:
            if order_fragment_remaining(order, fragment_id, snapshot) > 0:
                log.trace(f"exit, chose {order.id} (still needs {fragment_id}).")
                return order
        log.trace(f"every candidate already has {fragment_id} fully covered/matched -- none chosen.")
        return None

    for order in candidates:
        if any(order_fragment_remaining(order, frag_id, snapshot) > 0 and snapshot_stock(snapshot, frag_id) > 0 for frag_id in (order.requires or {}).keys()):
            log.trace(f"exit, chose {order.id} (already has local stock of a still-needed fragment).")
            return order
    log.trace(f"exit, no candidate has local stock of a needed fragment -- defaulting to first candidate {candidates[0].id}.")
    return candidates[0]


def bio_demand_totals(orders, my_biome):
    """
    {fragment_id: count_needed} over the local (is_local_order()),
    incomplete orders in `orders` (this outpost's exchange.orders(),
    fetched once by the caller): requires - delivered - in_transit, NOT
    yet netted against local stock -- callers compare it against their own
    stock read (see snapshot_stock()). Read straight from the outpost's
    own Bio Exchange, never a network-wide broadcast: each outpost's
    Collector and Lab must see their own Exchange's orders.

    Shared by BioCollectorController (decides what's worth harvesting) and
    BioLabController (decides whether an analyzed specimen is still worth
    extracting, or should be discard()-ed instead) so both agree on the same
    definition of "needed": without the Lab's check it would extract every
    analyzed specimen, including ones the Collector only picked up via its
    "uncataloged discovery" harvesting (to identify a new location, not
    because anything ordered it), overproducing fragments nothing wants
    until they saturate MAX_LOCAL_BIO_ARTIFACTS and wedge the pipeline.
    """
    demands = {}
    for ord_info in orders:
        if not is_order_incomplete(ord_info) or not is_local_order(ord_info, my_biome):
            continue
        delivered = ord_info.delivered or {}
        in_transit = ord_info.in_transit or {}
        for frag_id, count_needed in (ord_info.requires or {}).items():
            remaining = count_needed - delivered.get(frag_id, 0) - in_transit.get(frag_id, 0)
            if remaining > 0:
                demands[frag_id] = demands.get(frag_id, 0) + remaining
    return demands
