# Shared Storage Management: makes the production chain (Smelter, Fabricator,
# Supply Dock, Pioneer construction loading, vehicle unloading) aware of
# Warehouse/Large Warehouse buildings, not just the central home "inventory"
# freight endpoint. Also owns the "inventory manager" sweep that actively
# moves bulk stock out of Inventory into a Warehouse once it piles up.
#
# Scope: Warehouse + Large Warehouse only (both share the identical slot-based
# API -- see docs/components/warehouse.md / large_warehouse.md). Storage Bins
# use a different, single-material API shape (docs/components/storage_bin.md)
# and aren't included yet, though discover_storage_buildings()'s type_ids
# param leaves room to add them later without changing any caller.
#
# Everything here defaults to the home outpost, matching how Inventory itself
# only participates at Nocturna Base (docs/components/inventory.md).

from tree_console import TreeConsole

log = TreeConsole(module="storage")

STORAGE_TYPE_IDS = ("warehouse", "large_warehouse")

# "inventory manager" sweep: an item spanning more than this many Inventory
# slots gets moved out to a Warehouse (see rebalance_inventory_to_warehouses()).
INVENTORY_REBALANCE_SLOT_THRESHOLD = 2

BIGGER_STACKS_TECH_ID = "research_high_density_storage"
DEFAULT_STACK_SIZE = 10
BIGGER_STACKS_SIZE = 20

# item_catalog categories that must stay in Inventory, not a Warehouse (see
# docs/components/item_catalog.md for the category list):
#   - "equipment": deploys straight into a building/machine from Inventory
#     only (a Gas Tank or Solar Generator bought/produced as itself) --
#     moving one into a Warehouse would just strand it with no way to place
#     it. NOTE: "construction_kit" (e.g. mining_drill_kit) is deliberately
#     NOT included here -- those are placed by a Pioneer via blueprint
#     construction, which doesn't require the kit to sit in Inventory.
#   - "module" / "portable": vehicle equipment-slot gear (battery holders,
#     cargo racks, portable batteries/bins/scanners) that has to be in
#     Inventory to equip a newly-built or refitted Pioneer/Rover.
NON_WAREHOUSABLE_CATEGORIES = ("equipment", "module", "portable")


def _component(component_id):
    try:
        return get_component(component_id)
    except Exception:
        return None


def _home_outpost():
    network = _component("outpost_network")
    if network and hasattr(network, "home"):
        try:
            return network.home()
        except Exception:
            pass
    return None


def discover_storage_buildings(outpost=None, type_ids=STORAGE_TYPE_IDS):
    """
    [{"id": str, "component": obj}, ...] for every Warehouse/Large Warehouse
    at `outpost` (default: home outpost). Mirrors the existing
    get_all_charging_stations() discovery idiom in lib/vehicle_energy.py.
    """
    if outpost is None:
        outpost = _home_outpost()
    if not outpost or not hasattr(outpost, "buildings"):
        return []

    found = []
    seen_ids = set()
    for type_id in type_ids:
        try:
            buildings = outpost.buildings(type_id)
        except Exception:
            continue
        for b in buildings:
            b_id = getattr(b, "id", None)
            if not b_id or b_id in seen_ids:
                continue
            component = _component(b_id) or b
            seen_ids.add(b_id)
            found.append({"id": b_id, "component": component})
    return found


def total_stock(item_id, outpost=None):
    """inventory.count(item_id) + sum of warehouse.count(item_id) across every
    discovered Warehouse -- the single source of truth for "how much of this
    item exists at all", used everywhere a demand calc used to only check
    Inventory."""
    total = 0
    inventory = _component("inventory")
    if inventory and hasattr(inventory, "count"):
        try:
            total += inventory.count(item_id)
        except Exception:
            pass
    for building in discover_storage_buildings(outpost):
        component = building["component"]
        if component and hasattr(component, "count"):
            try:
                total += component.count(item_id)
            except Exception:
                pass
    return total


def warehouse_stock(item_id, outpost=None):
    """
    Sum of warehouse.count(item_id) across every discovered Warehouse at `outpost` --
    unlike total_stock(), this never adds home Inventory, regardless of `outpost`.
    total_stock()'s unconditional Inventory add is correct for its existing callers
    (raw ore realistically never sits in home Inventory), but wrong for anything that
    routinely DOES sit there -- e.g. Bio Lab reagents, bought straight into Inventory by
    the Shop. Checking "how much of this item does outpost X actually have on hand"
    with total_stock() would over-report by whatever's sitting untouched at home. Use
    this whenever the answer needs to be scoped to a single remote outpost's own
    storage, not "does this item exist anywhere at all".
    """
    total = 0
    for building in discover_storage_buildings(outpost):
        component = building["component"]
        if component and hasattr(component, "count"):
            try:
                total += component.count(item_id)
            except Exception:
                pass
    return total


def _fill_fraction(building):
    component = building["component"]
    try:
        return component.fill_percent()
    except Exception:
        return 1.0


def best_unload_target(item_id, min_amount=1, outpost=None):
    """
    Destination id string for offloading item_id, else None if there is nowhere
    local to put it. Among every discovered Warehouse with space_for(item_id) >=
    min_amount, prefers one that already holds item_id (count(item_id) > 0) --
    consolidating onto an existing stack -- and only falls back to ranking every
    candidate by least-full when none already stocks it. Ranking purely by
    fill_percent (the old behavior) ignores which Warehouse already has the item, so
    alternating "least full" picks across separate deliveries could spread
    the same item across every Warehouse at the outpost one partial stack
    at a time (e.g. a 100-unit reagent target ending up as 50 in one
    Warehouse and 50 in another, each a needless partial stack) even though
    a single Warehouse had room for the full amount the whole time.

    Only falls back to the literal "inventory" id when `outpost` resolves to the
    home outpost -- "inventory" only exists/connects there. Found live: a remote
    machine (e.g. a coastal Bio Luminizer) whose local Warehouses were all full
    would get handed "inventory" as the fallback and try to .connect() its own
    output port to it -- a non-local target from a Warehouse-only outpost. Returns
    None instead so callers can skip the stack (leave it staged) rather than
    attempt a connection that can't work.
    """
    holders = []
    others = []
    for building in discover_storage_buildings(outpost):
        component = building["component"]
        if not component or not hasattr(component, "space_for"):
            continue
        try:
            space = component.space_for(item_id)
        except Exception:
            continue
        if space < min_amount:
            continue
        try:
            already_holds = component.count(item_id) > 0
        except Exception:
            already_holds = False
        (holders if already_holds else others).append(building)

    pool = holders if holders else others
    if not pool:
        resolved = outpost if outpost is not None else _home_outpost()
        is_home = bool(resolved and getattr(resolved, "is_home", False))
        fallback = "inventory" if is_home else None
        log.debug(f"best_unload_target({item_id}): no Warehouse has space_for >= {min_amount}, falling back to {fallback!r} (is_home={is_home})")
        return fallback

    pool.sort(key=_fill_fraction)
    winner = pool[0]
    if holders:
        log.debug(f"best_unload_target({item_id}): {len(holders)} Warehouse(s) already hold this item, picked '{winner['id']}' (fill={_fill_fraction(winner):.2f}) to consolidate onto")
    else:
        log.debug(f"best_unload_target({item_id}): no Warehouse already holds this item, picked least-full '{winner['id']}' (fill={_fill_fraction(winner):.2f}) among {len(others)} candidate(s)")
    return winner["id"]


def take_item(port, item_id, amount, outpost=None):
    """
    Pulls up to `amount` units of item_id into `port` (a machine/vehicle
    input port exposing .connect(id)/.connected_to()/.take(item_id, count)).
    Tries whatever `port` is currently connected to first (usually Inventory,
    the existing default every consumer already connects to), then -- only if
    that source can't supply enough -- reconnects to each discovered
    Warehouse in turn until `amount` is satisfied or every source is
    exhausted. Ports hold one source at a time (same single-destination
    constraint as FluidPort, see lib/thermal_cap.py), so this reconnects on
    demand rather than fanning out. Returns total units actually moved.
    """
    if not port or not hasattr(port, "take") or amount <= 0:
        return 0

    moved_total = 0
    remaining = amount

    moved = _take_from_current(port, item_id, remaining)
    moved_total += moved
    remaining -= moved
    if remaining <= 0:
        return moved_total

    candidate_ids = ["inventory"] + [b["id"] for b in discover_storage_buildings(outpost)]
    current_id = None
    if hasattr(port, "connected_id"):
        try:
            current_id = port.connected_id()
        except Exception:
            current_id = None

    for source_id in candidate_ids:
        if remaining <= 0:
            break
        if source_id == current_id:
            continue  # already tried above
        try:
            res = port.connect(source_id)
        except Exception:
            continue
        if getattr(res, "status", None) != "ok":
            continue
        current_id = source_id
        moved = _take_from_current(port, item_id, remaining)
        moved_total += moved
        remaining -= moved

    return moved_total


def _take_from_current(port, item_id, remaining):
    """take(item_id, remaining) off whatever port is currently connected to.
    Returns units actually moved, 0 on any rejection/exception. Split out of
    take_item() as a plain helper (not a nested closure) since the sandboxed
    script parser does not support `nonlocal`."""
    if remaining <= 0:
        return 0
    try:
        res = port.take(item_id, remaining)
    except Exception:
        return 0
    return getattr(res, "moved", 0) or 0


def drain_port_to_storage(port, outpost=None):
    """
    Sends every stack currently staged in `port` (a machine output/byproduct slot
    exposing .stacks()/.connect(id)/.send(item_id, count)) to the best local
    destination for that item (best_unload_target(), same routing take_item() and
    unload_cargo() already use), reconnecting per-stack since a port holds one
    destination at a time. Replaces the old pattern of a single static
    .connect("inventory") at __init__ time, which only ever works at the home outpost
    -- a remote machine (Bio Lab, Bio Exchange, Bio Luminizer, etc.) needs its output
    routed to whichever local Warehouse actually has room for what it just produced.
    Returns total units moved.
    """
    if not port or not hasattr(port, "stacks"):
        return 0

    moved_total = 0
    try:
        stacks = port.stacks()
    except Exception:
        return 0

    for stack in stacks:
        item_id = getattr(stack, "id", None)
        count = getattr(stack, "count", 0)
        if not item_id or count <= 0:
            continue

        target = best_unload_target(item_id, count, outpost=outpost)
        if target is None:
            continue  # no local storage has room -- leave it staged, try again next cycle
        if hasattr(port, "connected_id") and port.connected_id() != target:
            try:
                port.connect(target)
            except Exception:
                continue

        try:
            res = port.send(item_id, count)
        except Exception:
            continue
        moved_total += getattr(res, "moved", 0) or 0

    return moved_total


def consolidate_cross_warehouse_stock(outpost=None):
    """
    Calls `.compact()` on every discovered Warehouse/Large Warehouse at
    `outpost` to pull a same-item stock split across more than one of them
    back together. `.compact()` is NOT purely an intra-building operation
    despite reading that way at a glance ("fewest Warehouse slots") -- its
    own outcome table shares `transfer_to()`'s exact vocabulary
    (`source_under_construction`/`source_changed`/`slots_full`/`target_full`),
    which only makes sense if it pulls from *other* storage endpoints (a
    "source") into the one it's called on. That also lines up with there
    being no other reason for the game to expose it at all: with Auto
    Feeders, a single Warehouse already adds to / draws from its
    lowest-numbered occupied slot for a given item on its own, so a purely
    intra-building `.compact()` would have nothing to ever actually do.
    Confirmed by observing it consolidate stock that was split across
    separate Warehouse buildings in-game, and by `.compact()` locking its
    Warehouse as a material endpoint for the whole cycle -- exactly the
    "busy while a transfer between buildings is in flight" cost a same-
    building-only operation would have no reason to pay. Complements
    best_unload_target()'s now-consolidation-aware routing for stock that
    was already split before that fix landed (or split for any other
    reason, e.g. a manual move). Returns total units moved across every
    building.
    """
    moved_total = 0
    for building in discover_storage_buildings(outpost):
        component = building["component"]
        if not component or not hasattr(component, "compact"):
            continue
        try:
            res = component.compact()
        except Exception:
            continue
        moved = getattr(res, "moved", 0) or 0
        if moved > 0:
            moved_total += moved
            log.print(f"[storage] Compacted {moved} unit(s) into Warehouse '{building['id']}'.")
        else:
            log.trace(f"consolidate_cross_warehouse_stock: '{building['id']}' compact() moved 0 units ({getattr(res, 'status', '?')})")
    log.debug(f"consolidate_cross_warehouse_stock: moved {moved_total} unit(s) total across every discovered Warehouse")
    return moved_total


def inventory_stack_size():
    """Current Inventory stack size per slot: 10, or 20 once Bigger Stacks is unlocked."""
    research = _component("research")
    if research and hasattr(research, "is_unlocked"):
        try:
            if research.is_unlocked(BIGGER_STACKS_TECH_ID):
                return BIGGER_STACKS_SIZE
        except Exception:
            pass
    return DEFAULT_STACK_SIZE


def _must_stay_in_inventory(item_id):
    """True if item_catalog classifies item_id as one of
    NON_WAREHOUSABLE_CATEGORIES -- equipment that deploys straight from
    Inventory, or vehicle-slot gear needed to equip a Pioneer/Rover -- so the
    inventory manager sweep must leave it alone."""
    catalog = _component("item_catalog")
    if not catalog or not hasattr(catalog, "lookup"):
        return False
    try:
        info = catalog.lookup(item_id)
    except Exception:
        return False
    return bool(info) and getattr(info, "category", None) in NON_WAREHOUSABLE_CATEGORIES


def _occupied_stackable_slots_by_item():
    """{item_id: [count_per_occupied_slot, ...]} for Inventory, skipping empty,
    property-bearing (non-stackable), and Inventory-only-category slots
    (see _must_stay_in_inventory)."""
    inventory = _component("inventory")
    if not inventory or not hasattr(inventory, "get_slots"):
        return {}
    try:
        slots = inventory.get_slots()
    except Exception:
        return {}

    per_item = {}
    for slot in slots:
        item_id = getattr(slot, "id", None)
        if not item_id:
            continue
        if getattr(slot, "properties", None) is not None:
            continue  # property-bearing / non-stackable, leave alone
        count = getattr(slot, "count", 0)
        if count <= 0:
            continue
        if _must_stay_in_inventory(item_id):
            continue  # equipment/module/portable: must stay in Inventory
        per_item.setdefault(item_id, []).append(count)
    return per_item


def _cheapest_warehouse_occupant(exclude_item_id, outpost=None):
    """
    Across every discovered Warehouse's slots, the (warehouse_id, item_id,
    quantity) of the smallest-quantity occupant that isn't exclude_item_id --
    the cheapest thing to evict back to Inventory to free a material-locked
    slot. None if no Warehouse has any occupant to evict.
    """
    best = None
    for building in discover_storage_buildings(outpost):
        component = building["component"]
        if not component or not hasattr(component, "slots"):
            continue
        try:
            slots = component.slots()
        except Exception:
            continue
        for slot in slots:
            item_id = getattr(slot, "item", None) or getattr(slot, "item_id", None)
            count = getattr(slot, "count", 0)
            if not item_id or count <= 0 or item_id == exclude_item_id:
                continue
            if best is None or count < best[2]:
                best = (building["id"], item_id, count)
    return best


def _warehouse_item_ids(outpost=None):
    """
    Set of item ids currently held (count > 0) anywhere in ANY discovered
    Warehouse -- used by rebalance_inventory_to_warehouses() to also
    consolidate an item that's already split between Inventory and a
    Warehouse, even when the Inventory-side slot count alone is too small to
    cross INVENTORY_REBALANCE_SLOT_THRESHOLD on its own (e.g. a single
    10-unit stack, exactly 1 slot).
    """
    held = set()
    for building in discover_storage_buildings(outpost):
        component = building["component"]
        if not component or not hasattr(component, "slots"):
            continue
        try:
            slots = component.slots()
        except Exception:
            continue
        for slot in slots:
            item_id = getattr(slot, "item", None) or getattr(slot, "item_id", None)
            count = getattr(slot, "count", 0)
            if item_id and count > 0:
                held.add(item_id)
    return held


def rebalance_inventory_to_warehouses(outpost=None):
    """
    "Inventory manager" sweep: moves a stackable (propertyless) item out to a
    Warehouse entirely (not just the excess -- a Warehouse is exactly as fast
    to read from as Inventory, so there's no benefit to keeping a partial
    stack behind) in either of two cases:
      1. It spans more than INVENTORY_REBALANCE_SLOT_THRESHOLD Inventory slots
         on its own -- the original bulk-item rule.
      2. It's ALREADY split: some units sit in Inventory while a Warehouse
         also already holds some of the same item, regardless of Inventory
         slot count. Once an item has a home in a Warehouse, leaving a
         further remainder behind in Inventory serves no "quick access"
         purpose (every consumer already reads combined stock via
         total_stock(), not by physical location) and just fragments the
         same material across two places -- found from a real case where a
         Fabricator's own stock-target tracking (which nets against
         total_stock(), so this SHOULD have been impossible) still ended up
         with an equal split, e.g. 10 in Inventory + 10 already in a
         Warehouse for a target of only 10, most likely a staged-batch
         completing after the target was already met elsewhere. Whatever the
         production-side cause, the "inventory manager" sweep is the correct
         place to clean up an existing split regardless, rather than
         requiring the specific producer to know about every possible
         storage location in advance.
    Worst offenders (most Inventory slots occupied) are processed first.

    If no Warehouse has room for an item at all (every material-locked slot
    already holds something else), falls back to a swap: evicts whichever
    Warehouse occupant is cheapest to bring back to Inventory (smallest
    quantity), but only when that's a genuine net reduction in Inventory
    slots used (slots freed by the move > slots the evicted occupant would
    cost) -- never a wash or a net loss.
    """
    inventory = _component("inventory")
    if not inventory or not hasattr(inventory, "transfer_to"):
        return

    per_item = _occupied_stackable_slots_by_item()
    if not per_item:
        return

    warehouse_item_ids = _warehouse_item_ids(outpost)
    bulky_items = [
        (item_id, len(counts), sum(counts))
        for item_id, counts in per_item.items()
        if len(counts) > INVENTORY_REBALANCE_SLOT_THRESHOLD or item_id in warehouse_item_ids
    ]
    if not bulky_items:
        return

    bulky_items.sort(key=lambda t: t[1], reverse=True)
    log.debug(f"rebalance_inventory_to_warehouses: {len(bulky_items)} item(s) qualify for rebalance, worst-first: {[(iid, slots) for iid, slots, _ in bulky_items]}")
    stack_size = inventory_stack_size()

    for item_id, slot_count, total_units in bulky_items:
        remaining = total_units
        warehouses = discover_storage_buildings(outpost)

        # 1. Direct move: spread across whichever Warehouses have room.
        for building in sorted(warehouses, key=_fill_fraction):
            if remaining <= 0:
                break
            component = building["component"]
            if not component or not hasattr(component, "space_for"):
                continue
            try:
                space = component.space_for(item_id)
            except Exception:
                space = 0
            if space <= 0:
                continue
            amount = min(remaining, space)
            try:
                res = inventory.transfer_to(building["id"], item_id, int(amount))
            except Exception:
                continue
            moved = getattr(res, "moved", 0) or 0
            if moved > 0:
                remaining -= moved
                log.print(f"[storage] Moved {moved}x {item_id} from Inventory to Warehouse '{building['id']}' ({slot_count} Inventory slots occupied).")

        if remaining <= 0:
            continue

        # 2. Swap fallback: no Warehouse had any room at all for this item.
        occupant = _cheapest_warehouse_occupant(item_id, outpost)
        if not occupant:
            log.level("warn").print(f"[storage] Could not clear {remaining}x {item_id} from Inventory this cycle: no Warehouse has room, and no Warehouse holds anything to evict in its place.")
            continue
        warehouse_id, occupant_item, occupant_qty = occupant

        # Slots still actually stuck in Inventory *right now* -- not slot_count,
        # which is this item's slot footprint from the TOP of this iteration,
        # before the direct-move loop above may have already moved part of it
        # out. Using the stale full count here overstated how many Inventory
        # slots this swap would free, so a swap that looked "worth it" against
        # the ORIGINAL total could actually be a net loss (or wash) against
        # what's genuinely left after a partial direct move already happened.
        slots_freed = -(-remaining // stack_size)  # ceil division
        slots_reclaimed = -(-occupant_qty // stack_size)  # ceil division
        if slots_freed <= slots_reclaimed:
            log.level("warn").print(f"[storage] Skipping swap for {item_id}: evicting {occupant_qty}x {occupant_item} would cost {slots_reclaimed} Inventory slot(s) to reclaim only {slots_freed}.")
            continue

        warehouse_component = next((b["component"] for b in warehouses if b["id"] == warehouse_id), None)
        if not warehouse_component or not hasattr(warehouse_component, "transfer_to"):
            continue
        try:
            evict_res = warehouse_component.transfer_to("inventory", occupant_item, occupant_qty)
        except Exception:
            continue
        evicted = getattr(evict_res, "moved", 0) or 0
        if evicted <= 0:
            log.level("warn").print(f"[storage] Swap for {item_id} did not go through: evicting {occupant_qty}x {occupant_item} from Warehouse '{warehouse_id}' moved 0 units ({getattr(evict_res, 'status', '?')}).")
            continue
        log.print(f"[storage] Evicted {evicted}x {occupant_item} from Warehouse '{warehouse_id}' back to Inventory to free a slot (frees {slots_freed} vs costs {slots_reclaimed}).")

        try:
            space = warehouse_component.space_for(item_id)
        except Exception:
            space = 0
        amount = min(remaining, space)
        if amount <= 0:
            log.level("warn").print(f"[storage] Freed a slot in Warehouse '{warehouse_id}' but it still reports no room for {item_id} -- skipping this cycle.")
            continue
        try:
            res = inventory.transfer_to(warehouse_id, item_id, int(amount))
        except Exception:
            continue
        moved = getattr(res, "moved", 0) or 0
        if moved > 0:
            remaining -= moved
            log.print(f"[storage] Moved {moved}x {item_id} from Inventory to Warehouse '{warehouse_id}' after swap.")
