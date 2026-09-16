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

STORAGE_TYPE_IDS = ("warehouse", "large_warehouse")

# "inventory manager" sweep: an item spanning more than this many Inventory
# slots gets moved out to a Warehouse (see rebalance_inventory_to_warehouses()).
INVENTORY_REBALANCE_SLOT_THRESHOLD = 2

BIGGER_STACKS_TECH_ID = "research_high_density_storage"
DEFAULT_STACK_SIZE = 10
BIGGER_STACKS_SIZE = 20


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
    Destination id string for offloading item_id: the least-full discovered
    Warehouse with space_for(item_id) >= min_amount, else "inventory" as the
    fallback (no Warehouse, or none with room).
    """
    candidates = []
    for building in discover_storage_buildings(outpost):
        component = building["component"]
        if not component or not hasattr(component, "space_for"):
            continue
        try:
            space = component.space_for(item_id)
        except Exception:
            continue
        if space >= min_amount:
            candidates.append(building)

    if not candidates:
        return "inventory"

    candidates.sort(key=_fill_fraction)
    return candidates[0]["id"]


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


def _occupied_stackable_slots_by_item():
    """{item_id: [count_per_occupied_slot, ...]} for Inventory, skipping empty
    and property-bearing (non-stackable) slots."""
    inventory = _component("inventory")
    if not inventory or not hasattr(inventory, "get_slots"):
        return {}
    try:
        slots = inventory.get_slots()
    except Exception:
        return {}

    per_item = {}
    for slot in slots:
        item_id = getattr(slot, "item_id", None)
        if not item_id:
            continue
        if getattr(slot, "properties", None) is not None:
            continue  # property-bearing / non-stackable, leave alone
        count = getattr(slot, "count", 0)
        if count <= 0:
            continue
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
                res = inventory.transfer_to(building["id"], item_id, amount)
            except Exception:
                continue
            moved = getattr(res, "moved", 0) or 0
            if moved > 0:
                remaining -= moved
                print(f"[storage] Moved {moved}x {item_id} from Inventory to Warehouse '{building['id']}' ({slot_count} Inventory slots occupied).")

        if remaining <= 0:
            continue

        # 2. Swap fallback: no Warehouse had any room at all for this item.
        occupant = _cheapest_warehouse_occupant(item_id, outpost)
        if not occupant:
            continue
        warehouse_id, occupant_item, occupant_qty = occupant

        slots_freed = slot_count
        slots_reclaimed = -(-occupant_qty // stack_size)  # ceil division
        if slots_freed <= slots_reclaimed:
            print(f"[storage] Skipping swap for {item_id}: evicting {occupant_qty}x {occupant_item} would cost {slots_reclaimed} Inventory slot(s) to reclaim only {slots_freed}.")
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
            continue
        print(f"[storage] Evicted {evicted}x {occupant_item} from Warehouse '{warehouse_id}' back to Inventory to free a slot (frees {slots_freed} vs costs {slots_reclaimed}).")

        try:
            space = warehouse_component.space_for(item_id)
        except Exception:
            space = 0
        amount = min(remaining, space)
        if amount <= 0:
            continue
        try:
            res = inventory.transfer_to(warehouse_id, item_id, amount)
        except Exception:
            continue
        moved = getattr(res, "moved", 0) or 0
        if moved > 0:
            remaining -= moved
            print(f"[storage] Moved {moved}x {item_id} from Inventory to Warehouse '{warehouse_id}' after swap.")
