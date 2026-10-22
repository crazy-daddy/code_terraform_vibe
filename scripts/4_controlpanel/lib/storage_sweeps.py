# Storage housekeeping sweeps, split out of lib/storage.py: Storage Bin and
# Warehouse stray consolidation, the "inventory manager" sweep that moves
# bulk stock out of Inventory into a Warehouse once it piles up, its reverse
# (Inventory-only items back home) and the fleet part parking. Run once per
# storage pass by orchestrator_automation.py; field_keeper.py calls the
# inventory manager sweep directly when Inventory runs full.

import components
from game_clock import now_tick
from storage import FLEET_PART_KEEP, INVENTORY_FREE_SLOTS_KEEP, INVENTORY_REBALANCE_SLOT_THRESHOLD, BinStore, StorageSnapshot, _items_demanded_by_active_dock_orders, _snapshot_clash, _snapshot_holders, best_unload_target, discover_storage_buildings, fleet_part_keep, inventory_count, inventory_part_room, inventory_stack_size, log, mark_busy, must_stay_in_inventory, recently_busy, recipe_partners, retiring_store_ids  # fmt: skip
from swallow import swallowed


# consolidate_storage_bins(): a Storage Bin stack of at most
# BIN_CONSOLIDATE_MAX_UNITS whose item a second bin at the same outpost also
# holds, with room for the whole stack, moves there. transfer_to() blocks the
# calling script for the feeder cycle (~2.5 ticks per unit), so each call moves
# at most BIN_CONSOLIDATE_CHUNK units, once, over every outpost.
BIN_CONSOLIDATE_MAX_UNITS = 200
BIN_CONSOLIDATE_CHUNK = 20


def _all_outposts():
    """Every outpost of the network, or None when it cannot be read."""
    network = components.component("outpost_network")
    try:
        return list(network.outposts()) if network and hasattr(network, "outposts") else []
    except Exception as error:
        swallowed("storage._all_outposts: network.outposts", error)
        return None


def _bins_by_item(outpost: "OutpostRef", snapshot: "StorageSnapshot"):
    """{item_id: [(count, room, bin_id, BinStore), ...]} for the Storage Bins
    at `outpost` latched to one material and holding some of it."""
    by_item = {}
    for entry in snapshot.buildings(outpost):
        component = entry["component"]
        rows = entry["rows"]
        if not isinstance(component, BinStore) or not rows:
            continue
        materials = {row[0] for row in rows if row[0] and row[1] > 0}
        if len(materials) != 1:
            continue
        count = sum([row[1] for row in rows])
        room = max(0, rows[0][2] - count)
        by_item.setdefault(next(iter(materials)), []).append((count, room, entry["id"], component))
    return by_item


def _consolidate_transfer(source, source_id, target_id, item_id, units, snapshot: "StorageSnapshot", now, where):
    """One transfer_to() for the consolidation sweeps. Returns (moved, status),
    or None when the call raised or the source answered "busy" (then
    mark_busy()); a finished call marks both stores touched in `snapshot`."""
    try:
        result = source.transfer_to(target_id, item_id, units)
    except Exception as error:
        swallowed(where, error)
        return None
    status = getattr(result, "status", None)
    if status == "busy":
        mark_busy(source_id, now)
        return None
    snapshot.touched(source_id, target_id)
    return (getattr(result, "moved", 0) or 0), status


def consolidate_storage_bins(outposts=None, snapshot: "StorageSnapshot | None" = None):
    """
    Frees Storage Bins that split an item with another bin at their outpost:
    the smallest bin of an item (at most BIN_CONSOLIDATE_MAX_UNITS) moves up
    to BIN_CONSOLIDATE_CHUNK units into the fullest other bin of that item
    with room for the whole small stack. One transfer per call over
    `outposts` (default: every outpost); later calls finish the stack, and
    take_item() drains the small bin first meanwhile. Bins that answered
    "busy" recently are skipped. Returns (source_id, target_id, item_id,
    moved), or None when nothing qualified.
    """
    outposts = _all_outposts() if outposts is None else outposts
    if not outposts:
        return None
    snapshot = StorageSnapshot() if snapshot is None else snapshot
    now = now_tick()
    retiring = retiring_store_ids()
    for outpost in outposts:
        for item_id, entries in _bins_by_item(outpost, snapshot).items():
            if len(entries) < 2:
                continue
            entries.sort(key=lambda entry: entry[0])
            count, _room, source_id, source = entries[0]
            if count > BIN_CONSOLIDATE_MAX_UNITS or recently_busy(source_id, now):
                continue
            targets = [entry for entry in entries[1:] if entry[1] >= count and not recently_busy(entry[2], now) and entry[2] not in retiring]
            if not targets:
                continue
            target_id = max(targets, key=lambda entry: entry[0])[2]
            done = _consolidate_transfer(source, source_id, target_id, item_id, min(count, BIN_CONSOLIDATE_CHUNK), snapshot, now, "storage.consolidate_storage_bins: transfer_to")
            if done is None:
                continue
            moved, status = done
            log.print(f"[storage] Consolidated {moved}/{count} {item_id} from '{source_id}' into '{target_id}' ({status}).")
            return source_id, target_id, item_id, moved
    return None


# consolidate_warehouse_strays(): a Warehouse stack of at most
# WAREHOUSE_STRAY_MAX_UNITS whose item another store at the same outpost also
# holds moves into best_unload_target()'s pick among those holders, at most
# WAREHOUSE_STRAY_CHUNK units per call (transfer_to() blocks like bin
# consolidation). Only while the stray's Warehouse has no empty slot left,
# the item has WAREHOUSE_STRAY_MANY_HOLDERS or more holders, or the stray
# shares its Warehouse with a recipe partner (recipe_partners()). A fold
# never lands next to a hotter partner than the stray already has.
WAREHOUSE_STRAY_MAX_UNITS = 200
WAREHOUSE_STRAY_CHUNK = 20
WAREHOUSE_STRAY_MANY_HOLDERS = 3


def consolidate_warehouse_strays(outposts=None, snapshot: "StorageSnapshot | None" = None):
    """
    Folds small Warehouse stacks back into the main holder of their item: a
    "busy" retry (_send_to_best_target()), a partial drain or a full slot can
    leave a few units of an item in a second Warehouse, where they take a
    whole slot and, as a holder, draw later deliveries too. Per outpost
    (default: every outpost), the smallest Warehouse holder of an item held
    by 2+ stores, at most WAREHOUSE_STRAY_MAX_UNITS, moves up to
    WAREHOUSE_STRAY_CHUNK units into best_unload_target(exclude=[source],
    holders_only=True) (the biggest other holder with room for the whole
    stray). Runs only when the stray's Warehouse has no empty slot, the item
    has WAREHOUSE_STRAY_MANY_HOLDERS or more holders, or the stray sits next
    to a recipe partner; otherwise the split costs nothing and a second
    holder gives take_item() a fallback while one answers "busy". A target
    whose recipe-partner clash (best_unload_target()) is higher than the
    source's is skipped: the fold would trade a slot for feeder waits.
    Retiring and
    recently busy stores are skipped. One transfer per call. Returns
    (source_id, target_id, item_id, moved), or None when nothing qualified.
    """
    outposts = _all_outposts() if outposts is None else outposts
    if not outposts:
        return None
    snapshot = StorageSnapshot() if snapshot is None else snapshot
    now = now_tick()
    retiring = retiring_store_ids()
    for outpost in outposts:
        entries = [entry for entry in snapshot.buildings(outpost) if entry["rows"] is not None and entry["id"] not in retiring]
        warehouses = [entry for entry in entries if not isinstance(entry["component"], BinStore)]
        if not warehouses:
            continue
        held_by = {entry["id"]: _snapshot_holders(entry) for entry in entries}
        holder_ids = {}
        for store_id, held in held_by.items():
            for item_id in held:
                holder_ids.setdefault(item_id, set()).add(store_id)
        for item_id, ids in holder_ids.items():
            pick = _stray_fold(item_id, ids, held_by, warehouses, outpost, now)
            if pick is None:
                continue
            count, source, target_id = pick
            source_id = source["id"]
            done = _consolidate_transfer(source["component"], source_id, target_id, item_id, min(count, WAREHOUSE_STRAY_CHUNK), snapshot, now, "storage.consolidate_warehouse_strays: transfer_to")
            if done is None:
                continue
            moved, status = done
            log.print(f"[storage] Folded {moved}/{count} stray {item_id} from '{source_id}' into '{target_id}' ({status}).")
            return source_id, target_id, item_id, moved
    return None


def _stray_fold(item_id, ids, held_by, warehouses, outpost, now):
    """
    consolidate_warehouse_strays()' pick for one item held by the store ids
    `ids`: (count, source entry, target_id) for its smallest Warehouse
    holder and the best_unload_target() to fold it into, or None when the
    item does not qualify (see consolidate_warehouse_strays()).
    """
    if len(ids) < 2:
        return None
    strays = [(held_by[entry["id"]][item_id], entry) for entry in warehouses if item_id in held_by[entry["id"]]]
    if not strays:
        return None
    count, source = min(strays, key=lambda pair: pair[0])
    source_id = source["id"]
    if count > WAREHOUSE_STRAY_MAX_UNITS or recently_busy(source_id, now):
        return None
    source_full = not any(row[0] == "" for row in source["rows"])
    if not source_full and len(ids) < WAREHOUSE_STRAY_MANY_HOLDERS and not recipe_partners(item_id) & set(held_by[source_id]):
        return None
    target_id = best_unload_target(item_id, count, outpost=outpost, exclude=[source_id], holders_only=True)
    if target_id not in ids or recently_busy(target_id, now):
        return None
    if _snapshot_clash(item_id, held_by[target_id]) > _snapshot_clash(item_id, held_by[source_id]):
        return None
    return count, source, target_id


def _occupied_stackable_slots_by_item():
    """{item_id: [count_per_occupied_slot, ...]} for Inventory, skipping empty,
    property-bearing (non-stackable), and Inventory-only-category slots
    (see must_stay_in_inventory)."""
    inventory = components.component("inventory")
    if not inventory or not hasattr(inventory, "get_slots"):
        return {}
    try:
        slots = inventory.get_slots()
    except Exception as error:
        swallowed("storage._occupied_stackable_slots_by_item: inventory.get_slots", error)
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
        if must_stay_in_inventory(item_id):
            continue  # equipment/module/portable: must stay in Inventory
        per_item.setdefault(item_id, []).append(count)
    return per_item


def _cheapest_warehouse_occupant(exclude_item_id, outpost: "OutpostRef | None", snapshot: "StorageSnapshot"):
    """
    Across every discovered Warehouse's slots, the (warehouse_id, item_id,
    quantity) of the smallest-quantity occupant that isn't exclude_item_id --
    the cheapest thing to evict back to Inventory to free a material-locked
    slot. None if no Warehouse has any occupant to evict.
    """
    best = None
    retiring = retiring_store_ids()
    for entry in snapshot.buildings(outpost):
        if entry["id"] in retiring:
            continue
        for item_id, count, _capacity, _properties in entry["rows"] or []:
            if not item_id or count <= 0 or item_id == exclude_item_id:
                continue
            if best is None or count < best[2]:
                best = (entry["id"], item_id, count)
    return best


def _warehouse_item_ids(outpost: "OutpostRef | None", snapshot: "StorageSnapshot"):
    """
    Set of item ids currently held (count > 0) anywhere in ANY discovered
    Warehouse -- used by rebalance_inventory_to_warehouses() to also
    consolidate an item that's already split between Inventory and a
    Warehouse, even when the Inventory-side slot count alone is too small to
    cross INVENTORY_REBALANCE_SLOT_THRESHOLD on its own (e.g. a single
    10-unit stack, exactly 1 slot).
    """
    return {row[0] for entry in snapshot.buildings(outpost) for row in entry["rows"] or [] if row[0] and row[1] > 0}


@log.block()
def reclaim_inventory_only_items_from_warehouses(outpost: "OutpostRef | None" = None, snapshot: "StorageSnapshot | None" = None):
    """
    Reverse of rebalance_inventory_to_warehouses(): sweeps every discovered
    Warehouse for stock in NON_WAREHOUSABLE_CATEGORIES (see
    must_stay_in_inventory) and moves it back to Inventory.

    Such an item lands in a Warehouse when Inventory had no room for it
    (unloads and machine drains keep INVENTORY_FREE_SLOTS_KEEP slots free),
    as a fleet part above its FLEET_PART_KEEP (park_surplus_fleet_parts()),
    or by a player's manual stash. rebalance_inventory_to_warehouses() skips
    them (_occupied_stackable_slots_by_item()). Left behind, it would be
    stranded with no way to equip a Pioneer/Rover or place it as equipment.

    Skips any item an active Supply Dock order still owes (see
    _items_demanded_by_active_dock_orders()) -- a bulk Earth Order contract
    for a deployable can run hundreds of units deep, far more than Inventory
    has room for, and the Dock already ships straight from the Warehouse
    without needing it staged here first. Everything else is reclaimed up to
    inventory_part_room() (INVENTORY_FREE_SLOTS_KEEP slots stay empty, a
    fleet part only up to its FLEET_PART_KEEP); the rest waits for a later
    sweep.

    Each exact property-variant slot is moved back individually (property_match
    "exact") so a durability-bearing equipment stack isn't merged with a
    different variant of the same item_id.
    """
    inventory = components.component("inventory")
    if not inventory or not hasattr(inventory, "transfer_to"):
        return

    dock_demanded = _items_demanded_by_active_dock_orders(outpost)
    snapshot = StorageSnapshot() if snapshot is None else snapshot

    reclaimed_total = 0
    for building in snapshot.buildings(outpost):
        component = building["component"]
        if not component or not hasattr(component, "transfer_to"):
            continue
        for item_id, count, _capacity, properties in building["rows"] or []:
            if not item_id or count <= 0:
                continue
            if not must_stay_in_inventory(item_id):
                continue
            if item_id in dock_demanded:
                log.debug(f"leaving {count}x {item_id} in Warehouse '{building['id']}' -- an active Supply Dock order still owes it, ships straight from the Warehouse")
                continue
            units = min(int(count), inventory_part_room(item_id, properties))
            if units <= 0:
                log.debug(f"leaving {count}x {item_id} in Warehouse '{building['id']}' -- Inventory keeps {INVENTORY_FREE_SLOTS_KEEP} slot(s) free or holds its FLEET_PART_KEEP")
                continue
            try:
                res = component.transfer_to("inventory", item_id, units, properties=properties, property_match="exact")
            except Exception as error:
                swallowed("storage.reclaim_inventory_only_items_from_warehouses: component.transfer_to", error)
                continue
            moved = getattr(res, "moved", 0) or 0
            if moved > 0:
                reclaimed_total += moved
                snapshot.touched(building["id"])
                log.print(f"[storage] Reclaimed {moved}x {item_id} from Warehouse '{building['id']}' back to Inventory (Inventory-only category).")
            elif getattr(res, "status", None) not in ("no_op",):
                log.debug(f"'{building['id']}' transfer_to('inventory', {item_id}) moved 0 units ({getattr(res, 'status', '?')})")
    log.debug(f"reclaimed {reclaimed_total} unit(s) total across every discovered Warehouse")
    return reclaimed_total


def park_surplus_fleet_parts(outpost: "OutpostRef | None" = None, snapshot: "StorageSnapshot | None" = None):
    """
    Moves home Inventory's FLEET_PART_KEEP items above their keep to a
    Warehouse (best_unload_target(), next-best after a full or "busy" pick).
    The surplus comes from a fleet_upgrade swap (undeploy() and an in-place
    Depot upgrade return the old parts to Inventory), a module upkeep swap or
    a Shop buy. Returns the units moved.
    """
    inventory = components.component("inventory")
    if not inventory or not hasattr(inventory, "transfer_to"):
        return 0
    retiring = retiring_store_ids()
    stores = [b for b in discover_storage_buildings(outpost) if b["id"] not in retiring]
    if not stores:
        return 0
    snapshot = StorageSnapshot() if snapshot is None else snapshot
    parked = 0
    for item_id in FLEET_PART_KEEP:
        keep = fleet_part_keep(item_id) or 0
        surplus = inventory_count(item_id) - keep
        tried = []
        for _ in range(len(stores)):
            if surplus <= 0:
                break
            target = best_unload_target(item_id, 1, outpost=outpost, exclude=tried)
            if target is None or target == "inventory":
                break
            tried.append(target)
            try:
                res = inventory.transfer_to(target, item_id, int(surplus))
            except Exception as error:
                swallowed("storage.park_surplus_fleet_parts: inventory.transfer_to", error)
                continue
            if getattr(res, "status", None) == "busy":
                mark_busy(target)
            moved = getattr(res, "moved", 0) or 0
            if moved > 0:
                surplus -= moved
                parked += moved
                snapshot.touched(target)
                log.print(f"[storage] Parked {moved}x {item_id} in Warehouse '{target}' (Inventory keeps {keep}).")
    return parked


def rebalance_inventory_to_warehouses(outpost: "OutpostRef | None" = None, snapshot: "StorageSnapshot | None" = None):
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
         same material across two places (e.g. a staged batch finishing
         after a Fabricator's target was met). Cleaning the split up here
         spares every producer from knowing every storage location.
    Worst offenders (most Inventory slots occupied) are processed first.
    Each move goes to best_unload_target(), next-best after a full or
    "busy" pick, so the item joins its existing holder instead of opening
    stacks in several Warehouses. After a "busy" answer only other holders
    are tried (holders_only); the rest waits for the next pass.

    If no Warehouse has room for an item at all (every material-locked slot
    already holds something else), falls back to a swap: evicts whichever
    Warehouse occupant is cheapest to bring back to Inventory (smallest
    quantity), but only when that's a genuine net reduction in Inventory
    slots used (slots freed by the move > slots the evicted occupant would
    cost) -- never a wash or a net loss.
    """
    inventory = components.component("inventory")
    if not inventory or not hasattr(inventory, "transfer_to"):
        return

    per_item = _occupied_stackable_slots_by_item()
    if not per_item:
        return

    snapshot = StorageSnapshot() if snapshot is None else snapshot
    warehouse_item_ids = _warehouse_item_ids(outpost, snapshot)
    bulky_items = [(item_id, len(counts), sum(counts)) for item_id, counts in per_item.items() if len(counts) > INVENTORY_REBALANCE_SLOT_THRESHOLD or item_id in warehouse_item_ids]
    if not bulky_items:
        return

    bulky_items.sort(key=lambda t: t[1], reverse=True)
    log.debug(f"rebalance_inventory_to_warehouses: {len(bulky_items)} item(s) qualify for rebalance, worst-first: {[(iid, slots) for iid, slots, _ in bulky_items]}")
    retiring = retiring_store_ids()
    if not any(b["id"] not in retiring for b in discover_storage_buildings(outpost)):
        log.debug("rebalance_inventory_to_warehouses: no Warehouse at this outpost, nothing to move to")
        return
    stack_size = inventory_stack_size()

    log.start(f"[storage] Rebalancing Inventory: {len(bulky_items)} item(s) to move to Warehouses")
    rebalance = _InventoryRebalance(inventory, outpost, snapshot, stack_size)
    for item_id, slot_count, total_units in bulky_items:
        retiring = retiring_store_ids()
        warehouses = [b for b in discover_storage_buildings(outpost) if b["id"] not in retiring]
        remaining = rebalance.move_direct(item_id, total_units, slot_count, len(warehouses))
        if remaining > 0:
            rebalance.swap(item_id, remaining, warehouses)
    log.end(f"[storage] Rebalance finished for {len(bulky_items)} item(s)")


class _InventoryRebalance:
    """One rebalance_inventory_to_warehouses() pass: its two moves per item."""

    def __init__(self, inventory, outpost: "OutpostRef | None", snapshot: "StorageSnapshot", stack_size):
        self.inventory = inventory
        self.outpost = outpost
        self.snapshot = snapshot
        self.stack_size = stack_size

    def move_direct(self, item_id, remaining, slot_count, tries):
        """1. Direct move: best_unload_target() first, the next-best one for
        what doesn't fit, at most `tries` targets. Returns the units left."""
        tried = []
        busy_seen = False
        for _ in range(tries):
            if remaining <= 0:
                break
            target = best_unload_target(item_id, 1, outpost=self.outpost, exclude=tried, holders_only=busy_seen)
            if target is None or target == "inventory":
                break
            tried.append(target)
            try:
                res = self.inventory.transfer_to(target, item_id, int(remaining))
            except Exception as error:
                swallowed("storage.rebalance_inventory_to_warehouses: inventory.transfer_to", error)
                continue
            moved = getattr(res, "moved", 0) or 0
            if getattr(res, "status", None) == "busy":
                mark_busy(target)
                busy_seen = True
            if moved > 0:
                remaining -= moved
                self.snapshot.touched(target)
                log.print(f"[storage] Moved {moved}x {item_id} from Inventory to Warehouse '{target}' ({slot_count} Inventory slots occupied).")
        return remaining

    def swap(self, item_id, remaining, warehouses):
        """2. Swap fallback: no Warehouse had any room at all for this item."""
        occupant = _cheapest_warehouse_occupant(item_id, self.outpost, self.snapshot)
        if not occupant:
            log.level("warn").print(f"[storage] Could not clear {remaining}x {item_id} from Inventory this cycle: no Warehouse has room, and no Warehouse holds anything to evict in its place.")
            return
        warehouse_id, occupant_item, occupant_qty = occupant

        # Slots still actually stuck in Inventory right now (not the original
        # slot_count, which may have been reduced by the direct-move loop above).
        # The current value is needed to compute the real slots-freed vs
        # slots-reclaimed trade-off for this swap.
        slots_freed = -(-remaining // self.stack_size)  # ceil division
        slots_reclaimed = -(-occupant_qty // self.stack_size)  # ceil division
        if slots_freed <= slots_reclaimed:
            log.level("warn").print(f"[storage] Skipping swap for {item_id}: evicting {occupant_qty}x {occupant_item} would cost {slots_reclaimed} Inventory slot(s) to reclaim only {slots_freed}.")
            return

        warehouse_component = next((b["component"] for b in warehouses if b["id"] == warehouse_id), None)
        if not warehouse_component or not hasattr(warehouse_component, "transfer_to"):
            return
        try:
            evict_res = warehouse_component.transfer_to("inventory", occupant_item, occupant_qty)
        except Exception as error:
            swallowed("storage.rebalance_inventory_to_warehouses: warehouse_component.transfer_to", error)
            return
        evicted = getattr(evict_res, "moved", 0) or 0
        if evicted <= 0:
            log.level("warn").print(f"[storage] Swap for {item_id} did not go through: evicting {occupant_qty}x {occupant_item} from Warehouse '{warehouse_id}' moved 0 units ({getattr(evict_res, 'status', '?')}).")
            return
        self.snapshot.touched(warehouse_id)
        log.print(f"[storage] Evicted {evicted}x {occupant_item} from Warehouse '{warehouse_id}' back to Inventory to free a slot (frees {slots_freed} vs costs {slots_reclaimed}).")

        try:
            space = warehouse_component.space_for(item_id)
        except Exception as error:
            swallowed("storage.rebalance_inventory_to_warehouses: warehouse_component.space_for", error)
            space = 0
        amount = min(remaining, space)
        if amount <= 0:
            log.level("warn").print(f"[storage] Freed a slot in Warehouse '{warehouse_id}' but it still reports no room for {item_id} -- skipping this cycle.")
            return
        try:
            res = self.inventory.transfer_to(warehouse_id, item_id, int(amount))
        except Exception as error:
            swallowed("storage.rebalance_inventory_to_warehouses: inventory.transfer_to #2", error)
            return
        moved = getattr(res, "moved", 0) or 0
        if moved > 0:
            log.print(f"[storage] Moved {moved}x {item_id} from Inventory to Warehouse '{warehouse_id}' after swap.")
