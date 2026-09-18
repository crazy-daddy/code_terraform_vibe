# Shared Library for Biology Pipeline Automation
# Event-driven and Signal Bus aware coordination for the pipeline stages that are the
# same regardless of biome: Bio Collector, Bio Lab, and Bio Exchange. Outpost-aware
# throughout: these buildings started out home-only (hardcoded to "inventory"), but
# the pipeline can now be deployed at a remote outpost that has Warehouses only, no
# Inventory -- see docs/AI_CHEATSHEET.md and TODO.md Phase 4.
#
# The one biome-specific step -- Coastal glow-tinting, Volcanic forge-casting, Deep
# QC conditioning, Geothermal gene-splicing, or nothing at all for Frozen -- lives in
# its own bio_coastal.py/bio_volcanic.py/bio_deep.py/bio_geothermal.py module, each
# importing the shared helpers below. This module never imports any of them (see
# local_biome_processor()'s docstring for why that would be circular); only each
# biome's thin entrypoint script imports its own controller directly.
from archive import archive
from storage import take_item, warehouse_stock, total_stock, drain_port_to_storage, discover_storage_buildings, best_unload_target
from version_guard import validate_game_version

def get_my_biome(machine):
    if hasattr(machine, "outpost") and machine.outpost:
        return getattr(machine.outpost, "biome", None)
    return None

def local_sibling(outpost, type_id):
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
    if not outpost or not hasattr(outpost, "buildings"):
        return None
    try:
        found = outpost.buildings(type_id)
    except Exception:
        return None
    if not found:
        return None
    b_id = getattr(found[0], "id", None)
    return get_component(b_id) if b_id else None

def is_home_outpost(outpost):
    # outpost is an OutpostRef (see storage.discover_storage_buildings() /
    # outpost_mining.outpost_by_id() callers) -- .is_home is a plain bool
    # property there, not a method (docs/types/world_and_sites.md's
    # OutpostRef vs. Outpost component distinction), so this must NOT call it.
    return getattr(outpost, "is_home", True) if outpost else True

def local_stock(item_id, outpost):
    """
    How much of item_id this machine can actually reach locally: home Inventory (plus
    any Warehouse) at the home outpost, or Warehouse-only at a remote outpost.
    total_stock() always adds home Inventory regardless of `outpost` -- correct when
    `outpost` IS home, wrong for a remote outpost (would over-report by whatever's
    sitting untouched back at home). See storage.warehouse_stock()'s docstring.
    """
    if is_home_outpost(outpost):
        return total_stock(item_id)
    return warehouse_stock(item_id, outpost)

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


def local_biome_processor(outpost):
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
    (_processor_is_idle()), never how to drive its biome-specific control loop. That
    keeps the shared pipeline stages (BioCollectorController/BioLabController/
    BioExchangeController below) biome-agnostic and avoids a circular import, since
    every bio_<biome>.py module imports helpers FROM this one.
    """
    for type_id in BIOME_PROCESSOR_TYPE_IDS:
        comp = local_sibling(outpost, type_id)
        if comp:
            return comp, type_id
    return None, None


def _processor_is_idle(processor, processor_type):
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
    except Exception:
        return True
    return True


def _local_sources(outpost):
    """[(source_id, component), ...] for every storage location this outpost can pull
    from: "inventory" first if home, then every discovered Warehouse at `outpost`."""
    sources = []
    if is_home_outpost(outpost):
        inv = get_component("inventory")
        if inv:
            sources.append(("inventory", inv))
    for building in discover_storage_buildings(outpost):
        sources.append((building["id"], building["component"]))
    return sources


def _properties_key(properties):
    """
    Canonical hashable key for an item's properties dict -- sorts keys and tuples any
    list values (glow triples, gene lists) so one snapshot index (see
    _local_stock_snapshot()) works uniformly across every biome's marker shape, not
    just Coastal's glow. () for no/empty properties.
    """
    if not properties:
        return ()
    return tuple(
        (k, tuple(v) if isinstance(v, list) else v)
        for k, v in sorted(properties.items())
    )


def _local_stock_snapshot(outpost):
    """
    One full walk of local storage (see _local_sources()), returning
    (totals, by_properties):
      totals: {item_id: total_count} -- every local_stock()-equivalent answer for
        this outpost, from a SINGLE storage walk instead of one walk per item_id.
      by_properties: {(item_id, properties_key): count} -- every
        _snapshot_property_count()-equivalent answer (any biome's marker property --
        glow, genes, forged/conditioned flags, ...), same single-walk sharing.

    Caching exchange.orders() alone (see _focus_local_order()'s docstring) only got
    BioCollectorController.step() from ~20s to ~8s/cycle -- the remaining cost was
    THIS: local_stock()/property lookups were each independently re-walking every
    Warehouse's stacks() from scratch, once per fragment (sometimes several times per
    fragment, inside per-order loops). Building one snapshot per step() and having
    every stock/property lookup read from it instead is the same fix applied one
    layer deeper. See docs/AI_CHEATSHEET.md Sec 1f.
    """
    totals = {}
    by_properties = {}
    for source_id, component in _local_sources(outpost):
        if not component or not hasattr(component, "stacks"):
            continue
        try:
            stacks = component.stacks()
        except Exception:
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
    return totals, by_properties


def _snapshot_stock(snapshot, item_id):
    """Total local stock of item_id from a _local_stock_snapshot() -- the
    snapshot-based equivalent of local_stock(item_id, outpost)."""
    totals, _ = snapshot
    return totals.get(item_id, 0)


def _snapshot_property_count(snapshot, item_id, properties):
    """
    Local stock of item_id whose properties dict exactly equals `properties`, from a
    _local_stock_snapshot() -- generalizes the old Coastal-only glow-tuple lookup to
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
    return by_properties.get((item_id, _properties_key(properties)), 0)


# Coarse safety-net cap on total local stock of every currently-demanded fragment
# (raw and already-processed, across every fragment type), before
# BioCollectorController pauses harvesting entirely. Biome-agnostic: it doesn't care
# whether a biome's transform step marks progress with a glow property, a gene list,
# a forged/conditioned flag, or nothing at all (Frozen) -- it just counts units of
# stuff that's demanded and sitting locally. NOT the primary flow-control mechanism --
# that's each processor controller's structural idle-gate (_processor_is_idle()),
# which bounds in-flight specimens to the pipeline's own single-slot hardware
# (Collector cargo, Lab specimen/output, processor chamber/input/output) and should
# keep this number at 0-2 in a healthy pipeline. This cap exists purely as insurance
# against that structural bound somehow not holding (e.g. a sibling script not
# running) -- see docs/AI_CHEATSHEET.md Sec 1f for the numeric per-fragment throttle
# this replaces (originally Coastal/glow-only; generalized here to protect every
# biome's backlog uniformly).
MAX_LOCAL_BIO_ARTIFACTS = 4


def _total_demanded_artifacts(snapshot, fragment_ids):
    """Total local stock across every fragment id in `fragment_ids` (typically a
    demand dict's .keys()) -- the coarse warehouse-overflow safety net for
    BioCollectorController, independent of which biome's transform step (if any) is
    in play. See MAX_LOCAL_BIO_ARTIFACTS."""
    return sum(_snapshot_stock(snapshot, f) for f in fragment_ids)


def _find_matching_stack(exchange_machine, item_id, outpost):
    """
    Scans every local storage source for a stack of item_id whose exact properties
    satisfy exchange_machine.matches_order() (glow/genes/Forged/Conditioned/plain-
    sample, whatever the active order actually requires) -- the documented pattern
    (docs/components/bio_exchange.md: matches_order() before an exact take()) for
    picking the RIGHT variant instead of blindly grabbing whatever's staged first.
    Returns (source_id, properties) or None.
    """
    for source_id, component in _local_sources(outpost):
        if not component or not hasattr(component, "stacks"):
            continue
        try:
            stacks = component.stacks()
        except Exception:
            continue
        for stack in stacks:
            if getattr(stack, "id", None) != item_id:
                continue
            properties = getattr(stack, "properties", None)
            try:
                if exchange_machine.matches_order(item_id, properties):
                    return source_id, properties
            except Exception:
                continue
    return None


def _order_target_properties(order, fragment_id):
    """
    The `properties` dict a locally-staged fragment_id stack must exactly match to
    already satisfy `order` -- generalizes the old Coastal-only target_glow lookup to
    also cover Geothermal's required_genes. Volcanic and Deep have no per-order
    target (forging/conditioning isn't order-specific: any correctly Forged/
    Conditioned unit of the fragment satisfies any order requiring it), so this
    returns None for them; each of their own controllers checks for their biome's
    marker property directly instead (see bio_volcanic.py/bio_deep.py).
    """
    target_glow = getattr(order, "target_glow", None)
    if target_glow:
        return {"glow": list(target_glow)}
    required_genes = getattr(order, "required_genes", None) or {}
    genes = required_genes.get(fragment_id)
    if genes:
        return {"genes": list(genes)}
    return None


def _order_fragment_remaining(order, fragment_id, snapshot):
    """
    Units of fragment_id this order still genuinely needs, net of what's already
    delivered, in transit, or sitting locally already correctly processed for it
    (see _order_target_properties()/_snapshot_property_count()). Module-level (not
    just a processor controller's own delegate) so _focus_local_order() can use the
    same check when picking which order to concentrate on.

    Found live: without this, an order that merely lists fragment_id in `.requires`
    -- even with its deficit for that specific fragment already fully covered --
    looked identical to one still genuinely wanting more of it. `_focus_local_order()`
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
    return max(0, remaining - already_matching)


def _focus_local_order(orders, snapshot, my_biome, fragment_id=None):
    """
    The ONE local, incomplete order (needing its own biome-specific processing step)
    to concentrate on right now -- optionally the one that specifically still needs
    more of fragment_id (not just any order that lists it in `.requires` -- see
    _order_fragment_remaining()'s docstring for the live bug that distinction
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
    `exchange` itself -- found live: exchange.orders() returns ~80 orders and isn't
    free to call, so callers fetch it once per step() and thread it through every
    helper that needs it instead of each fetching its own copy (see
    docs/AI_CHEATSHEET.md Sec 1f for the ~20s/cycle this caused before that fix).

    Shared by BioCollectorController (used to prefer harvesting this order's
    fragments over other incomplete orders') and every processor controller (each
    delegates to this from its own biome-flavored finder) so all of them agree on
    the SAME "order we're concentrating on right now" -- e.g. a Luminizer's tint
    target and the Collector's harvest preference stay in sync. Actual
    overproduction prevention is structural (see _processor_is_idle()), not
    enforced by this selection.
    """
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

    if not candidates:
        return None

    if fragment_id is not None:
        for order in candidates:
            if _order_fragment_remaining(order, fragment_id, snapshot) > 0:
                return order
        return None

    for order in candidates:
        if any(
            _order_fragment_remaining(order, frag_id, snapshot) > 0 and _snapshot_stock(snapshot, frag_id) > 0
            for frag_id in (order.requires or {}).keys()
        ):
            return order
    return candidates[0]


def _bio_demand_totals(comms, exchange, my_biome):
    """
    {fragment_id: count_needed} currently required by local, incomplete orders,
    NOT yet netted against local stock -- callers compare the returned count
    against their own already-fetched snapshot (see _snapshot_stock()) to
    decide whether more is still genuinely needed. Reads the Signal Bus
    'bio_orders' broadcast (BioExchangeController.broadcast_demands()) when
    available -- comms.latest(channel) returns the raw broadcast payload
    directly, `-> Any`, never a status-wrapped object, so this checks
    isinstance(..., dict) rather than a nonexistent .status (see
    docs/AI_CHEATSHEET.md Sec 1f for the live AttributeError this used to
    silently swallow). Falls back to this outpost's own Bio Exchange
    active_order() when comms is unavailable.

    Shared by BioCollectorController (decides what's worth harvesting) and
    BioLabController (decides whether an analyzed specimen is still worth
    extracting, or should be discard()-ed instead) so both agree on the same
    definition of "needed" -- see BioLabController.step()'s docstring for why
    the Lab needs this too, not just the Collector: without it, the Lab
    extracted every analyzed specimen unconditionally, including ones the
    Collector only picked up via its own "uncataloged discovery" harvesting
    (to identify a new location, not because anything ordered it), silently
    overproducing fragments nothing wants until they saturate
    MAX_LOCAL_BIO_ARTIFACTS and wedge the whole pipeline.
    """
    if comms:
        try:
            broadcast = comms.latest("bio_orders")
            if isinstance(broadcast, dict):
                return dict(broadcast.get("local_demands", {}) or {})
        except Exception:
            pass
    demands = {}
    if exchange:
        try:
            active = exchange.active_order()
        except Exception:
            active = None
        if active and is_local_order(active, my_biome) and is_order_incomplete(active):
            for frag_id, count_needed in (active.requires or {}).items():
                deliv = (active.delivered or {}).get(frag_id, 0)
                in_tr = (active.in_transit or {}).get(frag_id, 0)
                remaining = count_needed - deliv - in_tr
                if remaining > 0:
                    demands[frag_id] = demands.get(frag_id, 0) + remaining
    return demands


class BioExchangeController:
    """
    Manages Bio Orders, aggressive inventory sweeps, and sample deliveries.
    Broadcasting channel: 'bio_orders'
    Receiving channel: 'sample_ready'
    """
    def __init__(self, machine, sweep_delay=10.0):
        self.machine = machine
        self.name = getattr(machine, "id", "bio_exchange")
        self.comms = get_component("comms")
        self.sweep_delay = sweep_delay

    def drain_output(self):
        drain_port_to_storage(self.machine.output, self.machine.outpost)

    def clear_input(self):
        if self.machine.input.count() > 0:
            for stack in self.machine.input.stacks():
                try:
                    destination = best_unload_target(stack.id, stack.count, outpost=self.machine.outpost)
                    self.machine.input.eject(destination, stack.id, stack.count)
                except Exception:
                    pass

    def _required_fragment_ids(self, all_orders):
        """Every fragment item id genuinely still needed (remaining > 0, net of
        delivered + in-transit) by any incomplete order anywhere -- local or
        foreign. sweep_and_deliver()'s own delivery loop above already ships a
        matching sample to ANY such order regardless of locality, so "needed by
        nothing" for _cleanup_orphaned_artifacts() has to mean nothing here, not
        just nothing local."""
        required = set()
        for order in all_orders:
            if not is_order_incomplete(order):
                continue
            requires = getattr(order, "requires", {}) or {}
            delivered = getattr(order, "delivered", {}) or {}
            in_transit = getattr(order, "in_transit", {}) or {}
            for item_id, needed in requires.items():
                remaining = needed - delivered.get(item_id, 0) - in_transit.get(item_id, 0)
                if remaining > 0:
                    required.add(item_id)
        return required

    def _cleanup_orphaned_artifacts(self, all_orders):
        """
        Destroys locally-staged property-tagged bio samples (raw or already
        processed) of a fragment type that no order anywhere still needs any of. The
        delivery loop above only ever ships a matching sample toward an order that
        still wants it, so a fragment type nothing wants any more -- its one
        requesting order already completed, or it was only ever picked up via
        BioCollectorController's "uncataloged discovery" harvesting -- has no path
        back out of local storage; it just sits there forever. Left alone, that dead
        stock counts against MAX_LOCAL_BIO_ARTIFACTS (lib/bio.py) exactly like live
        in-flight stock, so a handful of orphaned samples permanently wedges the
        Collector into refusing to harvest ANYTHING further, needed or not (see
        BioLabController.step()'s demand-gated extract() for the other half:
        stopping this from building up going forward).

        Matches on item id only, not exact properties -- a raw, not-yet-processed
        sample never matches any order's exact requirement (that's the whole point
        of the biome processor), so gating on exact properties would misclassify
        perfectly good raw stock waiting to be processed as orphaned and destroy it.
        """
        outpost = self.machine.outpost
        required = self._required_fragment_ids(all_orders)
        for source_id, component in _local_sources(outpost):
            if not component or not hasattr(component, "stacks"):
                continue
            try:
                stacks = component.stacks()
            except Exception:
                continue
            for stack in stacks:
                item_id = getattr(stack, "id", None)
                count = getattr(stack, "count", 0)
                properties = getattr(stack, "properties", None) or {}
                if not item_id or count <= 0 or not properties:
                    continue
                if item_id in required:
                    continue
                if hasattr(self.machine.input, "connected_id") and self.machine.input.connected_id() != source_id:
                    self.machine.input.connect(source_id)
                take_res = self.machine.input.take(item_id, count, properties, "exact")
                if getattr(take_res, "moved", 0) > 0:
                    flush_res = self.machine.input.flush()
                    print(f"[EXCHANGE] Flushed {getattr(flush_res, 'moved', count)}x orphaned {item_id} "
                          f"(properties {properties}) from '{source_id}' -- no order needs this fragment.")

    def broadcast_demands(self):
        """Broadcasts all pending order demands across the Signal Bus."""
        if not self.comms:
            return

        all_orders = self.machine.orders()
        my_biome = get_my_biome(self.machine)
        local_demands = {}
        all_demands = {}

        for ord_info in all_orders:
            if not is_order_incomplete(ord_info):
                continue

            for item_id, needed in ord_info.requires.items():
                deliv = ord_info.delivered.get(item_id, 0)
                in_tr = ord_info.in_transit.get(item_id, 0)
                rem = needed - (deliv + in_tr)
                if rem > 0:
                    all_demands[item_id] = all_demands.get(item_id, 0) + rem
                    if is_local_order(ord_info, my_biome):
                        local_demands[item_id] = local_demands.get(item_id, 0) + rem

        payload = {
            "local_demands": local_demands,
            "all_demands": all_demands,
            "active_order": getattr(self.machine.active_order(), "id", None),
        }
        try:
            self.comms.broadcast("bio_orders", payload)
        except Exception:
            pass

    def sweep_and_deliver(self):
        """
        Aggressive Sweep: Iterates local storage (home Inventory, or this outpost's
        Warehouses if remote) and delivers ANY sample matching ANY incomplete order
        (local OR foreign) to declutter it. Only takes a stack whose exact properties
        satisfy matches_order() -- required for biomes like Coastal, where a sample
        only counts if its glow matches the order's target_glow exactly, not just the
        right fragment id.
        """
        self.drain_output()
        self.clear_input()

        outpost = self.machine.outpost
        all_orders = self.machine.orders()
        delivered_count = 0

        print(f"[EXCHANGE] Starting sweep across {len(all_orders)} orders. Checking local storage...")

        for ord_info in all_orders:
            if not is_order_incomplete(ord_info):
                continue

            for item_id, count_needed in ord_info.requires.items():
                deliv = ord_info.delivered.get(item_id, 0)
                in_tr = ord_info.in_transit.get(item_id, 0)
                remaining_needed = count_needed - (deliv + in_tr)

                if remaining_needed <= 0:
                    continue

                available = local_stock(item_id, outpost)
                if available <= 0:
                    continue

                to_deliver = min(remaining_needed, available)

                # Switch active order to deliver matching items
                active = self.machine.active_order()
                if active is None or active.id != ord_info.id:
                    set_res = self.machine.set_order(ord_info.id)
                    if set_res.status != "ok":
                        print(f"[EXCHANGE] Failed to set order {ord_info.id}: {set_res.status} - {set_res.message}")
                        continue
                    biome_tag = getattr(ord_info, "biome", "order")
                    print(f"[EXCHANGE] Switched to {ord_info.id} ({ord_info.name} - {biome_tag}) to deliver {to_deliver}x {item_id}")

                for _ in range(to_deliver):
                    self.drain_output()

                    match = _find_matching_stack(self.machine, item_id, outpost)
                    if not match:
                        print(f"[EXCHANGE] No locally-staged {item_id} variant currently satisfies this order.")
                        break
                    source_id, properties = match

                    if hasattr(self.machine.input, "connected_id") and self.machine.input.connected_id() != source_id:
                        self.machine.input.connect(source_id)

                    take_res = self.machine.input.take(item_id, 1, properties, "exact")
                    if take_res.status != "ok":
                        print(f"[EXCHANGE] Take {item_id} status: {take_res.status} - {take_res.message}")
                        if take_res.status == "target_wrong_material":
                            self.clear_input()
                        break

                    deliv_res = self.machine.deliver()
                    while deliv_res.status == "busy":
                        sleep(0.2)
                        deliv_res = self.machine.deliver()

                    if deliv_res.status in ["ok", "complete"]:
                        delivered_count += 1
                        print(f"[EXCHANGE] Delivered 1x {item_id} -> {ord_info.id} ({ord_info.name}) (Status: {deliv_res.status})")
                        if deliv_res.status == "complete":
                            reward_str = f" (+{ord_info.reward} credits)" if getattr(ord_info, "reward", 0) else ""
                            try:
                                notify(f"[Bio Order Complete] {ord_info.name}{reward_str}!", level="info", duration_seconds=10.0)
                            except Exception:
                                pass
                            try:
                                archive.transaction(
                                    "bio.completed_orders",
                                    [],
                                    lambda lst: lst if ord_info.id in lst else lst + [ord_info.id]
                                )
                            except Exception:
                                pass
                    else:
                        print(f"[EXCHANGE] Deliver error: {deliv_res.status} - {deliv_res.message}")
                        break

        self.drain_output()
        self.clear_input()
        self._cleanup_orphaned_artifacts(all_orders)

        if delivered_count > 0:
            print(f"[EXCHANGE] Sweep finished: delivered {delivered_count} sample(s).")

        # Select a local incomplete order for ongoing collection
        my_biome = get_my_biome(self.machine)
        active = self.machine.active_order()
        if active is None or not is_order_incomplete(active) or not is_local_order(active, my_biome):
            for ord_info in all_orders:
                if is_order_incomplete(ord_info):
                    if is_local_order(ord_info, my_biome):
                        self.machine.set_order(ord_info.id)
                        print(f"[EXCHANGE] Set default local order: {ord_info.id} ({ord_info.name})")
                        break

        self.broadcast_demands()

    def run(self):
        print(f"Bio Exchange ({self.name}) online via Shared Library & Signal Bus.")
        validate_game_version()
        while True:
            self.sweep_and_deliver()

            # Wait for either the next sweep interval OR an instant 'sample_ready' signal from the lab
            if self.comms:
                try:
                    # Non-blocking check for instant delivery trigger
                    msg = self.comms.receive("sample_ready")
                    if msg.status == "ok":
                        print(f"[EXCHANGE] Received sample_ready event ({msg.packet.get('sample_id')}), triggering immediate sweep!")
                        continue
                except Exception:
                    pass

            sleep(self.sweep_delay)


class BioLabController:
    """
    Automates Analyze and Extract for the Bio Lab.
    Cleans latched inputs/outputs, auto-purchases missing reagents (home only --
    a remote Lab has no direct Shop delivery, so it waits on the reagent transporter
    instead, see lib/vehicle_cargo.py's run_haul_loop()), and notifies
    the Signal Bus ('sample_ready') upon completing an extraction.
    """
    def __init__(self, machine):
        self.machine = machine
        self.name = getattr(machine, "id", "bio_lab")
        self.shop = get_component("shop")
        self.comms = get_component("comms")
        self.inventory_full_notified = False

    def drain_output(self):
        outpost = self.machine.outpost
        if self.machine.output.count() > 0:
            for stack in self.machine.output.stacks():
                target = best_unload_target(stack.id, stack.count, outpost=outpost)
                if target is None:
                    return False  # no local storage has room -- leave staged, retry next cycle
                if hasattr(self.machine.output, "connected_id") and self.machine.output.connected_id() != target:
                    self.machine.output.connect(target)
                res_send = self.machine.output.send(stack.id, stack.count)
                if res_send.status == "ok":
                    print(f"[{self.name}] Sent {res_send.moved}x {stack.id} to '{target}'.")
                    self.inventory_full_notified = False
                elif res_send.status == "busy":
                    sleep(0.2)
                    return False
                elif res_send.status in ["target_full", "slots_full", "inventory_full"]:
                    self.handle_storage_full()
                    return False
                else:
                    print(f"[{self.name}] Output notice: {res_send.status} - {res_send.message}")
                    sleep(0.5)
                    return False
        return True

    def handle_storage_full(self):
        """Pause extraction while preserving the sample in the lab output."""
        if not self.inventory_full_notified:
            print(f"[{self.name}] WARNING: local storage is full. Free space to resume sample extraction.")
            try:
                notify(f"[{self.name}] Storage Full! Free space to resume extraction.", level="warn", duration_seconds=8.0)
            except Exception:
                pass
            self.inventory_full_notified = True
        sleep(2.0)

    def _wait_for_processor(self):
        """
        Blocks until the local biome processor's next heartbeat broadcast, instead
        of busy-polling with sleep() while this Lab holds off pulling its next
        specimen from the Collector or draining its own extracted output -- see
        _processor_is_idle()'s docstring for why that gate exists. The heartbeat
        fires once every processor step() cycle regardless of what that cycle did
        (see each processor controller's own _notify_heartbeat()-equivalent
        docstring for why it's not just "fired on a successful load" -- that version
        could leave a Lab waiting forever if the processor went idle with nothing
        left to load), so this always wakes up again within one processor cycle to
        re-check _processor_is_idle() from scratch. Falls back to a short sleep if
        comms is unavailable or the wait itself errors.
        """
        if self.comms:
            try:
                self.comms.wait_broadcast("biome_processor_heartbeat")
                return
            except Exception:
                pass
        sleep(0.5)

    def step(self):
        outpost = self.machine.outpost
        is_home = is_home_outpost(outpost)
        processor, processor_type = local_biome_processor(outpost)
        processor_idle = _processor_is_idle(processor, processor_type)

        if processor_idle:
            if not self.drain_output():
                return
        # else: leave whatever's in Lab output staged -- the local biome processor
        # isn't ready for it yet -- and fall through to analyze/extract below, which
        # keep working on whatever's already in the chamber.

        specimen = self.machine.specimen

        if specimen is None:
            # Clear unwanted input reagents
            if self.machine.input.count() > 0:
                for stack in self.machine.input.stacks():
                    try:
                        destination = best_unload_target(stack.id, stack.count, outpost=outpost)
                        self.machine.input.eject(destination, stack.id, stack.count)
                    except Exception:
                        pass

            if not processor_idle:
                self._wait_for_processor()
                return

            # Pull specimen from collector cargo -- must be this Lab's own
            # outpost's Collector (take_from() requires same-outpost source).
            collector = local_sibling(outpost, "bio_collector")
            if collector and collector.cargo is not None:
                t_res = self.machine.take_from(collector)
                if t_res.status == "ok":
                    print(f"[{self.name}] Transferred specimen from collector to lab chamber.")
            sleep(0.5)
            return

        # Stage 1: Analyze
        if specimen.stage == "collected":
            print(f"[{self.name}] Analyzing specimen...")
            a_res = self.machine.analyze()
            if a_res.status == "ok":
                print(f"[{self.name}] Analyzed: {a_res.info.name} ({a_res.info.fragment_id}). Recipe: {a_res.info.required_recipe}")
                try:
                    def update_recipes(curr):
                        d = dict(curr or {})
                        d[a_res.info.fragment_id] = {
                            "name": a_res.info.name,
                            "recipe": a_res.info.required_recipe,
                            "rarity": getattr(a_res.info, "rarity", "unknown")
                        }
                        return d
                    archive.transaction("bio.fragment_recipes", {}, update_recipes)
                except Exception:
                    pass
            sleep(0.5)
            return

        # Stage 2: Extract
        if specimen.stage == "analyzed":
            fragment_id = specimen.fragment_id
            loaded = self.machine.loaded_reagents or {}

            # Discard instead of extract when no order anywhere still needs
            # more of this fragment -- see _bio_demand_totals()'s docstring
            # for why the Lab (not just the Collector) needs this check: the
            # Collector's own "uncataloged discovery" harvesting picks up
            # specimens purely to identify a new location/fragment, with no
            # demand behind them at all, and previously the Lab extracted
            # every analyzed specimen unconditionally regardless of demand.
            # analyze() already cataloged the fragment either way, so
            # discarding here loses nothing but the reagent/output cost of an
            # extraction nothing would ever collect.
            if not loaded:
                exchange = local_sibling(outpost, "bio_exchange")
                my_biome = get_my_biome(self.machine)
                demand_totals = _bio_demand_totals(self.comms, exchange, my_biome)
                if demand_totals.get(fragment_id, 0) <= local_stock(fragment_id, outpost):
                    print(f"[{self.name}] {fragment_id} not needed by any order -- discarding instead of extracting.")
                    self.machine.discard()
                    sleep(0.5)
                    return

            recipe = specimen.recipe or {}

            # Unload wrong reagents
            mismatched = any(r not in recipe or q > recipe.get(r, 0) for r, q in loaded.items())
            if mismatched:
                print(f"[{self.name}] Unloading mismatched reagents...")
                self.machine.unload_reagents()
                sleep(0.5)
                return

            # Check and load input buffer reagents
            if self.machine.input.count() > 0:
                for stack in self.machine.input.stacks():
                    needed = recipe.get(stack.id, 0) - loaded.get(stack.id, 0)
                    if needed > 0:
                        load_qty = min(stack.count, needed)
                        self.machine.load(stack.id, load_qty)
                    else:
                        try:
                            destination = best_unload_target(stack.id, stack.count, outpost=outpost)
                            self.machine.input.eject(destination, stack.id, stack.count)
                        except Exception:
                            pass
                sleep(0.5)
                return

            # Load missing reagents: from local stock, buying the shortfall only when
            # this Lab is at home (a remote Lab can't have the Shop deliver to it --
            # see run_haul_loop() for how a remote Lab gets restocked).
            needs_loading = False
            for reagent_id, req_qty in recipe.items():
                curr_qty = loaded.get(reagent_id, 0)
                missing = req_qty - curr_qty
                if missing > 0:
                    needs_loading = True
                    local_have = local_stock(reagent_id, outpost)
                    if local_have < missing:
                        if is_home and self.shop:
                            buy_qty = missing - local_have
                            buy_res = self.shop.buy(reagent_id, buy_qty)
                            if buy_res.status == "ok":
                                print(f"[{self.name}] Purchased {buy_qty}x {reagent_id} from shop.")
                            else:
                                sleep(1.0)
                                break
                        else:
                            print(f"[{self.name}] Waiting on {reagent_id} resupply ({local_have}/{missing} on hand locally).")
                            sleep(2.0)
                            break

                    moved = take_item(self.machine.input, reagent_id, missing, outpost=outpost)
                    if moved > 0:
                        self.machine.load(reagent_id, moved)
                    sleep(0.5)
                    break

            if not needs_loading:
                print(f"[{self.name}] Extracting sample for {specimen.fragment_id}...")
                ext_res = self.machine.extract()
                if ext_res.status == "ok":
                    sample_id = specimen.fragment_id
                    print(f"[{self.name}] Extracted sample: {sample_id}!")
                    if not processor_idle:
                        self._wait_for_processor()
                        return
                    if not self.drain_output():
                        return

                    # Notify Exchange over Signal Bus for immediate delivery
                    if self.comms:
                        try:
                            self.comms.send("sample_ready", {"sample_id": sample_id})
                        except Exception:
                            pass

    def run(self):
        print(f"Bio Lab ({self.name}) online via Shared Library & Signal Bus.")
        validate_game_version()
        while True:
            self.step()
            sleep(0.5)


class BioCollectorController:
    """
    Gathers specimens matching active demands broadcast over Signal Bus.
    Prevents over-harvesting:
    - Never harvests fragments already sufficient in local storage/deliveries.
    - Caps uncataloged harvests if local storage already holds ample samples.
    """
    def __init__(self, machine):
        self.machine = machine
        self.name = getattr(machine, "id", "bio_collector")
        self.comms = get_component("comms")
        self.pending_analysis = set()

    def coord_key(self, c):
        return (round(c[0], 2), round(c[1], 2))

    def step(self):
        if self.machine.cargo is not None:
            sleep(0.5)
            return

        outpost = self.machine.outpost
        my_biome = get_my_biome(self.machine)
        exchange = local_sibling(outpost, "bio_exchange")

        # Fetch exchange.orders() and walk local storage exactly ONCE per
        # step(), not once per fragment -- see _focus_local_order()'s and
        # _local_stock_snapshot()'s docstrings: re-fetching/re-walking per
        # fragment (~20-30 of them) measured at ~20s, then still ~8s/cycle
        # even after caching orders() alone, from the storage walk.
        orders = []
        current_order = None
        snapshot = _local_stock_snapshot(outpost)
        if exchange:
            try:
                orders = exchange.orders()
            except Exception:
                orders = []
            current_order = _focus_local_order(orders, snapshot, my_biome)
        preferred_fragments = set((current_order.requires or {}).keys()) if current_order else set()

        # 1. Determine demand -- shared with BioLabController's own extract-vs-
        # discard() gate, see _bio_demand_totals()'s docstring.
        demand_totals = _bio_demand_totals(self.comms, exchange, my_biome)
        needed_fragments = {
            frag_id for frag_id, count_needed in demand_totals.items()
            if _snapshot_stock(snapshot, frag_id) < count_needed
        }

        # Coarse safety net, NOT the primary flow control (that's each processor
        # controller's structural idle-gate, see _processor_is_idle()): in a
        # healthy pipeline this should basically never trip, since the Lab won't
        # hand off/drain faster than the processor can keep up. Biome-agnostic --
        # reads the already-built snapshot's totals rather than re-scanning
        # anything, and doesn't care which (if any) marker property applies.
        if _total_demanded_artifacts(snapshot, demand_totals.keys()) >= MAX_LOCAL_BIO_ARTIFACTS:
            sleep(1.0)
            return

        # 2. Scan local biome
        locations = self.machine.scan()
        if not locations:
            sleep(2.0)
            return

        for loc in locations:
            if loc.cataloged:
                self.pending_analysis.discard(self.coord_key(loc.coords))

        target_coords = None

        # Priority 1: Collect what is actively needed by local orders --
        # prefer the current/focus order's own fragments first, falling back
        # to any other incomplete order's fragment if none of those are
        # discoverable nearby right now.
        if needed_fragments:
            for loc in locations:
                if loc.cataloged and loc.fragment_id in needed_fragments and loc.fragment_id in preferred_fragments:
                    target_coords = loc.coords
                    print(f"[{self.name}] Harvesting needed specimen (current order): {loc.fragment_id} at {loc.coords}")
                    break
            if target_coords is None:
                for loc in locations:
                    if loc.cataloged and loc.fragment_id in needed_fragments:
                        target_coords = loc.coords
                        print(f"[{self.name}] Harvesting needed specimen (other order): {loc.fragment_id} at {loc.coords}")
                        break

        # Priority 2: Uncataloged discovery (strictly throttled)
        if target_coords is None:
            lab = local_sibling(outpost, "bio_lab")
            lab_busy = (lab and lab.specimen is not None and lab.specimen.stage == "collected")
            if not lab_busy:
                for loc in locations:
                    if not loc.cataloged and self.coord_key(loc.coords) not in self.pending_analysis:
                        target_coords = loc.coords
                        self.pending_analysis.add(self.coord_key(loc.coords))
                        print(f"[{self.name}] Harvesting uncataloged fragment at {loc.coords} (discovery)")
                        break

        if target_coords:
            res = self.machine.collect(target_coords)
            if res.status != "ok":
                self.pending_analysis.discard(self.coord_key(target_coords))
                sleep(1.0)
        else:
            # Idle cleanly
            sleep(2.0)

    def run(self):
        print(f"Bio Collector ({self.name}) online via Shared Library & Signal Bus.")
        validate_game_version()
        while True:
            self.step()
