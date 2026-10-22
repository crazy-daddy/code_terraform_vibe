# Unload path, split out of lib/storage.py: best_unload_target() picks the
# Warehouse, Storage Bin or Inventory a stack goes to (consolidating, smelt
# partners kept apart, Inventory-only items home), and the send side moves
# it there: send_stack(), direct delivery push_to_targets(), bin top-up,
# the port drains (storage first or Inventory first) and eject_unneeded().
# Every machine that empties an output port or a vehicle hold calls it.

from storage import FLEET_PART_KEEP, INVENTORY_FREE_SLOTS_KEEP, BinStore, _items_demanded_by_active_dock_orders, discover_storage_buildings, inventory_part_room, inventory_room, item_heat, local_port_target, log, mark_busy, must_stay_in_inventory, outpost_is_home, recipe_partners, retiring_store_ids
from swallow import swallowed


def _materials(component, item_id):
    """Item ids the Warehouse holds. Falls back to a count(item_id) probe
    (holder or not, no neighbours) when materials() is missing or raises."""
    try:
        if hasattr(component, "materials"):
            return set(component.materials())
    except Exception as error:
        swallowed("storage._materials: component.materials", error)
    try:
        return {item_id} if component.count(item_id) > 0 else set()
    except Exception as error:
        swallowed("storage._materials: component.count", error)
        return set()


def _fill_fraction(building):
    component = building["component"]
    try:
        return component.fill_percent()
    except Exception as error:
        swallowed("storage._fill_fraction: component.fill_percent", error)
        return 1.0


def _holder_count(component, item_id):
    """Units of item_id in a store that holds it, 0 when count() raises."""
    try:
        return component.count(item_id) or 0
    except Exception as error:
        swallowed("storage._holder_count: component.count", error)
        return 0


def _inventory_first(item_id, min_amount, outpost: "OutpostRef | None"):
    """True when item_id must stay in Inventory, Inventory has room for
    min_amount (inventory_part_room()), and no active Supply Dock order at outpost owes it."""
    if not must_stay_in_inventory(item_id):
        return False
    if inventory_part_room(item_id) < min_amount:
        return False
    return item_id not in _items_demanded_by_active_dock_orders(outpost)


@log.block(lambda item_id, *_, **__: f"best_unload_target({item_id})")
def best_unload_target(item_id, min_amount=1, outpost: "OutpostRef | None" = None, exclude=(), holders_only=False):
    """
    Destination id string for offloading item_id, else None if there is nowhere
    local to put it. Ranks every discovered Warehouse with space_for(item_id) >=
    min_amount by what it holds (materials()), never by recent "busy" answers:
      1. no recipe partner of item_id (recipe_partners()) inside, already
         holding item_id -- consolidates onto the existing stack;
      2. no partner inside, not holding item_id -- opens a new stack; this
         beats 3, so an item stuck next to its partner splits off once and
         then rank 1 sends every later delivery to the new stack;
      3. a partner inside (clash = item_heat(item) x item_heat(partner)),
         holding item_id first;
    then, among holders, the one holding the most item_id, so deliveries
    grow the main stack and a stray never draws them; among new stacks, for
    an item with heat, the Warehouse whose other contents are coldest, then
    least full. One Warehouse, or no partner-free one with room, gives the
    same pick as plain consolidation. Least-full alone would spread one item
    across every Warehouse one partial stack at a time.
    A Storage Bin (BinStore) has one slot, room only while empty or latched
    to item_id. A bin latched to item_id ranks like a Warehouse holder, the
    fullest such bin first: take_item() drains the emptiest bin, so two bins
    of one item converge into one instead of filling evenly. Opening an
    empty bin ranks after every Warehouse with room: bins are
    the early, slot-tight stage, so a partner clash (Auto Feeder waits) is
    cheaper than locking a whole bin to one item.

    Only falls back to the literal "inventory" id when `outpost` resolves to the
    home outpost -- "inventory" only exists/connects there. Found live: a remote
    machine (e.g. a coastal Bio Luminizer) whose local Warehouses were all full
    would get handed "inventory" as the fallback and try to .connect() its own
    output port to it -- a non-local target from a Warehouse-only outpost. Returns
    None instead so callers can skip the stack (leave it staged) rather than
    attempt a connection that can't work. At home, too, "inventory" needs
    inventory_room() >= min_amount (INVENTORY_FREE_SLOTS_KEEP slots stay
    empty), else None. A caller passing min_amount below the units it sends
    can overshoot that reserve by the difference.

    At home, an item that must stay in Inventory (must_stay_in_inventory())
    goes straight to "inventory" while it has room for min_amount, so a
    hauled-in kit or module doesn't wait in a Warehouse for
    reclaim_inventory_only_items_from_warehouses(). Items an active Supply
    Dock order owes keep the Warehouse routing, as in that sweep.

    exclude: Warehouse ids to skip (ones that already answered "busy" to a
    send), so a caller can ask for the next-best target. A non-empty exclude
    never opens an empty Storage Bin: a busy bin frees up after one feeder
    transfer, a bin locked to a second copy of the item stays taken.

    holders_only: skip every store not already holding item_id (no new
    stack, no Inventory fallback). A "busy" retry passes it: a busy holder
    frees up within a few ticks, a new stack in another Warehouse stays as a
    stray (consolidate_warehouse_strays()).
    """
    if outpost_is_home(outpost) and not exclude and not holders_only and _inventory_first(item_id, min_amount, outpost):
        log.debug("Inventory-only item with room in Inventory -> 'inventory'")
        return "inventory"
    partners = recipe_partners(item_id)
    heat = item_heat(item_id)
    retiring = retiring_store_ids()
    ranked = []
    for building in discover_storage_buildings(outpost):
        component = building["component"]
        if not component or not hasattr(component, "space_for") or building["id"] in exclude or building["id"] in retiring:
            continue
        try:
            space = component.space_for(item_id)
        except Exception as error:
            swallowed("storage.best_unload_target: component.space_for", error)
            continue
        if space < min_amount:
            continue
        held = _materials(component, item_id)
        new_stack = item_id not in held
        if new_stack and holders_only:
            continue
        clash = sum([heat * item_heat(partner) for partner in held & partners])
        is_bin = isinstance(component, BinStore)
        opens_bin = new_stack and is_bin
        if opens_bin and exclude:
            continue
        if new_stack:
            neighbours = sum([item_heat(other) for other in held]) if heat else 0
            ranked.append(((opens_bin, clash, True, neighbours, _fill_fraction(building)), building))
        else:
            ranked.append(((False, clash, False, 0, -_holder_count(component, item_id)), building))

    if not ranked:
        is_home = outpost_is_home(outpost)
        fallback = "inventory" if is_home and not exclude and not holders_only and inventory_room(item_id) >= min_amount else None
        log.debug(f"no Warehouse or Storage Bin has space_for >= {min_amount}, falling back to {fallback!r} (is_home={is_home})")
        return fallback

    ranked.sort(key=lambda pair: pair[0])
    key, winner = ranked[0]
    if key[2]:
        log.debug(f"picked '{winner['id']}' of {len(ranked)}: new stack, clash={key[1]}, neighbour heat={key[3]}, fill={key[4]:.2f}")
    else:
        log.debug(f"picked '{winner['id']}' of {len(ranked)}: consolidate, clash={key[1]}, holds {-key[4]}")
    return winner["id"]


# Extra Warehouses drain_port_to_storage() tries for a stack after a "busy" send.
BUSY_TARGET_RETRIES = 3


def _staged_stacks(port, where):
    """[(item_id, count), ...] of the non-empty stacks in `port`; [] when the
    port has no stacks() or the read raised (`where` labels the error)."""
    if not port or not hasattr(port, "stacks"):
        return []
    try:
        return [(stack.id, stack.count) for stack in port.stacks() if getattr(stack, "id", None) and getattr(stack, "count", 0) > 0]
    except Exception as error:
        swallowed(where, error)
        return []


def eject_unneeded(port: "InputSlot", keep, target=None, outpost: "OutpostRef | None" = None):
    """Ejects every stack in `port` whose item is not in `keep` to `target`,
    freeing its material slot. Without `target`, each stack goes to
    best_unload_target() at `outpost`; a stack no store has room for stays.
    Returns ["item:status", ...] for the log."""
    out = []
    for item_id, count in _staged_stacks(port, "storage.eject_unneeded: port.stacks"):
        if item_id in keep:
            continue
        try:
            destination = target if target is not None else best_unload_target(item_id, count, outpost=outpost)
            if destination is None:
                continue
            result = port.eject(destination, item_id, count)
        except Exception as error:
            swallowed("storage.eject_unneeded: port.eject", error)
            continue
        out.append(f"{item_id}:{getattr(result, 'status', '?')}")
    return out


def send_stack(port: "OutputSlot", item_id, count, target):
    """
    Points `port` (an OutputSlot) at `target` unless already connected there,
    then send(item_id, count). Returns (moved, status, message); a raising
    connect/send gives (0, "exception", error text).
    """
    try:
        if not hasattr(port, "connected_id") or port.connected_id() != target:
            port.connect(target)
        res = port.send(item_id, count)
    except Exception as error:
        swallowed("storage.send_stack: port.send", error)
        return 0, "exception", str(error)
    return (getattr(res, "moved", 0) or 0), getattr(res, "status", None), getattr(res, "message", "")


def push_to_targets(port: "OutputSlot", item_id, count, targets):
    """
    Sends up to `count` units of item_id from `port` (an OutputSlot) straight
    into consumer machines, skipping the storage hop: `targets` is
    [(target_id, max_units), ...] in order of preference. A target whose
    connect() is refused (another outpost, not an item destination) or that
    takes nothing (busy, full) is skipped for the next. Returns
    [(target_id, moved), ...] for every target that took units; whatever is
    left stays in the port for the caller's storage drain.
    """
    delivered = []
    left = count
    for target, cap in targets:
        amount = min(left, int(cap))
        if amount <= 0:
            continue
        try:
            if port.connected_id() != target:
                status = getattr(port.connect(target), "status", None)
                if status != "ok":
                    log.debug(f"push {item_id} -> '{target}': connect {status}")
                    continue
        except Exception as error:
            swallowed("storage.push_to_targets: port.connect", error)
            continue
        moved, status, _message = send_stack(port, item_id, amount, target)
        log.debug(f"push {moved}/{amount} {item_id} -> '{target}' ({status})")
        if moved > 0:
            delivered.append((target, moved))
            left -= moved
            if left <= 0:
                break
    return delivered


def top_up_target(item_id, count, outpost: "OutpostRef | None" = None):
    """
    (bin_id, room) for a stack of `count` units of item_id that no holder
    takes whole: the fullest Storage Bin latched to item_id with room for
    some of it. (None, 0) when a holder (bin or Warehouse) has room for all
    `count` units, or no bin latched to the item has room left. Sending
    `room` units there first keeps the overflow small, so a full Pioneer
    load or Smelter batch tops up the bin it belongs in before
    best_unload_target() opens a new one for the rest.
    """
    best_id, best_room = None, 0
    retiring = retiring_store_ids()
    for building in discover_storage_buildings(outpost):
        component = building["component"]
        if not component or not hasattr(component, "space_for") or building["id"] in retiring or item_id not in _materials(component, item_id):
            continue
        try:
            room = component.space_for(item_id)
        except Exception as error:
            swallowed("storage.top_up_target: component.space_for", error)
            continue
        if room >= count:
            return None, 0
        # Bins share one capacity, so the least room is the fullest bin.
        if room > 0 and isinstance(component, BinStore) and (best_id is None or room < best_room):
            best_id, best_room = building["id"], room
    return best_id, best_room


def top_up_bin(port: "OutputSlot", item_id, count, outpost: "OutpostRef | None" = None):
    """Sends what fits of `count` units of item_id from `port` into
    top_up_target()'s bin. Returns units moved (0 when there is no such bin
    or it answers "busy", which is mark_busy()'d)."""
    target, room = top_up_target(item_id, count, outpost)
    if target is None:
        return 0
    moved, status, _message = send_stack(port, item_id, min(room, count), target)
    if status == "busy":
        mark_busy(target)
    log.debug(f"top-up {moved}/{min(room, count)} {item_id} -> '{target}' ({status})")
    return moved


def _send_to_best_target(port: "OutputSlot", item_id, count, outpost: "OutpostRef | None", allow_partial):
    """Sends one stack to best_unload_target(); a Warehouse that answers "busy"
    (a material endpoint lock, e.g. the one a blend was just taken from) is
    skipped and the next-best holder of the item tried, up to
    BUSY_TARGET_RETRIES times. A retry never opens a new stack: with every
    holder busy the stack waits, instead of leaving a stray in another
    Warehouse.
    Without allow_partial, top_up_bin() first fills the bin already holding
    the item. Returns units moved; 0 leaves the stack staged."""
    topped = 0 if allow_partial else top_up_bin(port, item_id, count, outpost)
    count -= topped
    if count <= 0:
        return topped
    tried = []
    for _ in range(BUSY_TARGET_RETRIES + 1):
        # A fleet part takes its keep's share into Inventory, the rest goes on to a Warehouse.
        target = best_unload_target(item_id, 1 if allow_partial or item_id in FLEET_PART_KEEP else count, outpost=outpost, exclude=tried, holders_only=bool(tried))
        if target is None:
            return topped  # no local storage has room -- leave it staged, try again next cycle
        units = min(count, inventory_part_room(item_id)) if target == "inventory" else count
        moved, status, _message = send_stack(port, item_id, units, target)
        if target == "inventory" and 0 < moved < count and item_id in FLEET_PART_KEEP:
            return topped + moved + _send_to_best_target(port, item_id, count - moved, outpost, allow_partial)
        if moved > 0 or status != "busy":
            return topped + moved
        mark_busy(target)
        tried.append(target)
        log.debug(f"'{target}' busy for {item_id}, trying the next-best Warehouse")
    return topped


def drain_port_to_storage(port: "OutputSlot", outpost: "OutpostRef | None" = None, include=None, allow_partial=False):
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

    include: optional item_id -> bool filter (stacks it rejects stay put).
    allow_partial: pick any destination with room for >= 1 unit and send
    the whole stack anyway (the port moves what fits), instead of requiring
    room for the whole stack -- for large stockpiles (a Drone Depot unload)
    that should trickle into a nearly full Warehouse rather than wait.
    """
    moved_total = 0
    for item_id, count in _staged_stacks(port, "storage.drain_port_to_storage: port.stacks"):
        if include is None or include(item_id):
            moved_total += _send_to_best_target(port, item_id, count, outpost, allow_partial)
    return moved_total


def drain_port_storage_first(port: "OutputSlot", outpost: "OutpostRef | None" = None, include=None):
    """
    Sends every stack staged in `port` to a local Warehouse
    (drain_port_to_storage()), then whatever no Warehouse took to
    local_port_target() (Inventory at home, the first local Warehouse
    elsewhere). For outputs that should stay out of Inventory unless the
    Warehouses are full (Seed Supply seeds, Feed Maker feed). Inventory
    takes at most inventory_room(). `include`:
    optional item_id -> bool filter, as in drain_port_to_storage(). Returns
    total units moved.
    """
    moved = drain_port_to_storage(port, outpost=outpost, include=include)
    target = local_port_target(outpost)
    if not target:
        return moved
    for item_id, count in _staged_stacks(port, "storage.drain_port_storage_first: port.stacks"):
        if include is None or include(item_id):
            if target == "inventory":
                count = min(count, inventory_room(item_id))
                if count <= 0:
                    continue
            moved += send_stack(port, item_id, count, target)[0]
    return moved


# OutputSlot.send() rejections that mean "Inventory has no room for this"
# (docs/types/storage_and_inventory.md) -- the only cases
# drain_port_inventory_first() falls back to a Warehouse for.
INVENTORY_FULL_STATUSES = ("partial", "target_full", "slots_full")


def _drain_port_off_home(port: "OutputSlot", outpost: "OutpostRef | None", stacks):
    """drain_port_inventory_first() off-home: no Inventory, so each stack goes
    straight to a local Warehouse."""
    results = []
    for item_id, _count in stacks:
        moved = drain_port_to_storage(port, outpost=outpost, include=lambda i, wanted=item_id: i == wanted, allow_partial=True)
        results.append((item_id, moved, "warehouse", "ok" if moved > 0 else "target_full", "" if moved > 0 else "no local Warehouse has room"))
    return results


def drain_port_inventory_first(port: "OutputSlot", outpost: "OutpostRef | None" = None):
    """
    Sends every stack staged in `port` (a Smelter/Fabricator output) to the
    home Inventory, and only when Inventory has no room (INVENTORY_FULL_STATUSES,
    or inventory_room() short of the stack) sends the rest of that stack to a local Warehouse via
    drain_port_to_storage(). Inventory stays the normal destination: a
    Warehouse-held input costs the consumer an Auto Feeder hop on take_item().
    But a finished item stuck in an output buffer stalls the machine outright,
    and is invisible to take_item() entirely. take_item() already rotates
    through Warehouses, so Supply Docks and Fabricators still find a
    fallback-stored item. INVENTORY_ONLY_ITEM_IDS fall back too: a stall is
    worse, and the rebalance sweep only moves items away from Inventory, so
    such an item waits in the Warehouse until someone takes it.

    Reconnects the port to "inventory" before each send, since a previous
    fallback leaves it pointed at a Warehouse. Off-home (`outpost` resolves
    to a non-home outpost) every stack goes straight to a local Warehouse,
    since Inventory only connects at home.

    Returns [(item_id, moved, destination, status, message), ...] per stack,
    destination "inventory" or "warehouse"; a stack neither accepted is
    reported with moved 0 and the Inventory send's status/message.
    """
    stacks = _staged_stacks(port, "storage.drain_port_inventory_first: port.stacks")
    if not outpost_is_home(outpost):
        return _drain_port_off_home(port, outpost, stacks)

    results = []
    for item_id, count in stacks:
        room = inventory_room(item_id)
        if room <= 0:
            moved, status, message = 0, "slots_full", f"Inventory keeps {INVENTORY_FREE_SLOTS_KEEP} slot(s) free"
        else:
            moved, status, message = send_stack(port, item_id, min(count, room), "inventory")
            if room < count and status == "ok":
                status = "partial"
        if moved > 0:
            results.append((item_id, moved, "inventory", status, message))
        if status not in INVENTORY_FULL_STATUSES:
            if moved <= 0:
                results.append((item_id, 0, "inventory", status, message))
            continue
        fallback = drain_port_to_storage(port, outpost=outpost, include=lambda i, wanted=item_id: i == wanted, allow_partial=True)
        if fallback > 0:
            results.append((item_id, fallback, "warehouse", "ok", ""))
        elif moved <= 0:
            results.append((item_id, 0, "inventory", status, message))
    return results
