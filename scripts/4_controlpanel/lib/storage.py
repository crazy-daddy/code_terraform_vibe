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

from archive import archive
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
# Explicit ids on top of the categories above: drone hardware must also sit in
# Inventory -- computer.deploy() takes Depot kits and chassis from there, and
# drone.couple() takes modules from there (docs/components/drone.md). Listed
# by id since their item_catalog categories aren't documented; the fleet
# upgrade (lib/fleet_upgrade.py) orders and consumes these.
INVENTORY_ONLY_ITEM_IDS = (
    "drone_station_kit", "drone_station_kit_medium", "drone_station_kit_large",
    "drone_small", "drone_medium", "drone_large",
    "electric_thruster", "heli_thruster", "battery_pack",
    "cargo_pod_small", "cargo_pod_medium", "cargo_pod_large",
    "oil_tank_small", "oil_tank_medium", "oil_tank_large",
    "portable_bio_scanner", "portable_bio_extractor", "shield_plating",
)


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


# A storage endpoint that answered "busy" to a take() within this many ticks
# (~2s at 10 ticks/s) is tried LAST by take_item(), not skipped -- still
# used when nothing else holds the item. There is no API to ask "is this
# Warehouse busy?" up front; a "busy" rejection comes back immediately (no
# feeder wait), so the rejection itself is the probe, remembered here so
# the next take_item() call (from any consumer in this script) doesn't lead
# with the same locked building again.
TAKE_BUSY_COOLDOWN_TICKS = 20
_recent_busy = {}  # {source_id: tick of last "busy" rejection}


def _now_tick():
    clock = _component("clock")
    if clock and hasattr(clock, "tick"):
        try:
            return clock.tick()
        except Exception:
            pass
    return 0


# Crop Automators (home Harvesting field, tier 8_planting) keep their Forage
# in their output instead of draining it to Warehouses, so Forage consumers
# take it from there (lib/crop_automator.py). A full output pauses the
# automator's harvests (a partial harvest discards the rest), so clogged ones
# are drained before anything else, and diversity-garden ones before the
# fill: the garden carries the field's variety bonus.
CROP_AUTOMATOR_TYPE_ID = "crop_automator"
CROP_AUTOMATOR_ITEM_ID = "forage"
CROP_AUTOMATOR_OUTPUT_CAP = 50000     # output buffer (docs/components/crop_automator.md)
CROP_AUTOMATOR_CLOG_FRACTION = 0.9    # at/above this fill (or status "output_full") it counts as clogged
CROP_AUTOMATOR_STATUS_KEY = "plant.automators"  # lib/crop_automator.py telemetry; "garden" flag read here


def crop_automator_forage(outpost=None):
    """
    [(automator_id, forage, clogged, garden)] for every Crop Automator at
    `outpost` (default home; only home has a Harvesting field) holding
    Forage, in drain order: clogged first, then garden, then most Forage.
    Automators are identified by HarvestingMachineRef.type_id, never by id.
    """
    resolved = outpost if outpost is not None else _home_outpost()
    if resolved is None or not hasattr(resolved, "harvesting_machines"):
        return []
    try:
        refs = list(resolved.harvesting_machines(CROP_AUTOMATOR_TYPE_ID) or [])
    except Exception:
        return []
    telemetry = archive.get(CROP_AUTOMATOR_STATUS_KEY)
    telemetry = telemetry if isinstance(telemetry, dict) else {}
    garden_ids = [k for k, v in telemetry.items() if isinstance(v, dict) and v.get("garden")]
    out = []
    for ref in refs:
        if getattr(ref, "type_id", CROP_AUTOMATOR_TYPE_ID) != CROP_AUTOMATOR_TYPE_ID:
            continue
        ca_id = getattr(ref, "id", None)
        machine = _component(ca_id) if ca_id else None
        port = getattr(machine, "output", None)
        if not ca_id or not port or not hasattr(port, "count"):
            continue
        try:
            count = int(port.count(CROP_AUTOMATOR_ITEM_ID) or 0)
        except Exception:
            continue
        if count <= 0:
            continue
        try:
            status = getattr(machine, "status")()
        except Exception:
            status = None
        clogged = status == "output_full" or count >= CROP_AUTOMATOR_CLOG_FRACTION * CROP_AUTOMATOR_OUTPUT_CAP
        garden = ca_id in garden_ids
        out.append((ca_id, count, clogged, garden))
    out.sort(key=lambda e: (0 if e[2] else 1, 0 if e[3] else 1, -e[1]))
    return out


def crop_automator_forage_total(outpost=None):
    """Forage sitting in the Crop Automators' outputs at `outpost`."""
    return int(sum(e[1] for e in crop_automator_forage(outpost)))


def _holder_candidates(item_id, outpost=None, cache=None):
    """
    [(source_id, units)] for every storage endpoint holding item_id, in the
    order take_item() should try them:
      0. Forage only: clogged Crop Automators (garden first), before
         anything else -- a full output stalls their harvests.
      1. Inventory (home only) -- it has no Auto Feeder of its own and never
         locks, so it's the one source that can't be "busy".
      2. Warehouses holding the item, most units first.
      3. Forage only: the other Crop Automators, garden first, then most
         Forage (Warehouse Forage drains first, keeping auto-loaders free).
      4. ...with any endpoint that answered "busy" within
         TAKE_BUSY_COOLDOWN_TICKS moved to the end (stable, so the order
         above is kept within each group).
    Endpoints holding 0 are left out entirely -- the old blind
    connect()+take() walk over every Warehouse regardless of contents cost a
    reconnect per miss. Uses a SourceCache's one-shot per-building snapshot
    when one is passed (home outpost only, which is all it covers).
    """
    resolved = outpost if outpost is not None else _home_outpost()
    is_home = outpost is None or bool(resolved and getattr(resolved, "is_home", False))

    holders = []
    # {automator_id: rank within the sort: 0 = clogged, 3 = normal}, plus
    # garden order; stored per id so nothing depends on the id's spelling.
    automator_rank = {}
    if item_id == CROP_AUTOMATOR_ITEM_ID and is_home:
        for ca_id, count, clogged, garden in crop_automator_forage(resolved):
            holders.append((ca_id, count))
            automator_rank[ca_id] = (0 if clogged else 3, 0 if garden else 1)
    if cache is not None and outpost is None and hasattr(cache, "building_stock"):
        holders += list(cache.building_stock(item_id))
    else:
        if is_home:
            inventory = _component("inventory")
            if inventory and hasattr(inventory, "count"):
                try:
                    count = inventory.count(item_id)
                except Exception:
                    count = 0
                if count > 0:
                    holders.append(("inventory", count))
        for building in discover_storage_buildings(outpost):
            component = building["component"]
            if not component or not hasattr(component, "count"):
                continue
            try:
                count = component.count(item_id)
            except Exception:
                continue
            if count > 0:
                holders.append((building["id"], count))

    now = _now_tick()
    ranked = []
    for source_id, count in holders:
        busy_tick = _recent_busy.get(source_id)
        recently_busy = busy_tick is not None and now > 0 and now - busy_tick <= TAKE_BUSY_COOLDOWN_TICKS
        # 0 clogged automator, 1 Inventory, 2 Warehouse, 3 other automator.
        kind_rank, garden_rank = automator_rank.get(source_id, (1 if source_id == "inventory" else 2, 0))
        ranked.append(((1 if recently_busy else 0, kind_rank, garden_rank, -count), (source_id, count)))
    ranked.sort(key=lambda pair: pair[0])
    return [entry for _key, entry in ranked]


def take_item(port, item_id, amount, outpost=None, cache=None, report=None):
    """
    Pulls up to `amount` units of item_id into `port` (a machine/vehicle
    input port exposing .connect(id)/.connected_id()/.take(item_id, count)).
    Only endpoints that actually hold the item are tried, in
    _holder_candidates() order (Inventory first, then Warehouses by most
    stock, recently-"busy" ones last; Forage adds Crop Automators, clogged
    ones before everything, the rest after Warehouses), reconnecting between them since a
    port holds one source at a time (same single-source constraint as
    FluidPort, see lib/thermal_cap.py). Stops once `amount` is met or every
    holder has been tried. Returns total units actually moved.

    `cache`: optional SourceCache (lib/production.py) -- its stock snapshot
    replaces a .count() call per building. `report`: optional dict, filled
    with {"sources": [(source_id, status, moved), ...]} for diagnostics.
    """
    if report is not None:
        report["sources"] = []
    if not port or not hasattr(port, "take") or amount <= 0:
        return 0

    current_id = None
    if hasattr(port, "connected_id"):
        try:
            current_id = port.connected_id()
        except Exception:
            current_id = None

    moved_total = 0
    remaining = amount
    for source_id, _held in _holder_candidates(item_id, outpost, cache):
        if remaining <= 0:
            break
        if source_id != current_id:
            try:
                res = port.connect(source_id)
            except Exception:
                continue
            status = getattr(res, "status", None)
            if status != "ok":
                if report is not None:
                    report["sources"].append((source_id, f"connect:{status}", 0))
                continue
            current_id = source_id
        moved, status = _take_from_current(port, item_id, remaining)
        if status == "busy":
            _recent_busy[source_id] = _now_tick()
        if report is not None:
            report["sources"].append((source_id, status, moved))
        log.debug(f"take_item({item_id}): '{source_id}' -> status={status} moved={moved}/{remaining}")
        moved_total += moved
        remaining -= moved

    return moved_total


def _take_from_current(port, item_id, remaining):
    """take(item_id, remaining) off whatever port is currently connected to.
    Returns (units actually moved, status) -- (0, "exception") if the call
    raised. Split out of take_item() as a plain helper (not a nested closure)
    since the sandboxed script parser does not support `nonlocal`."""
    if remaining <= 0:
        return 0, "no_op"
    try:
        res = port.take(item_id, remaining)
    except Exception:
        return 0, "exception"
    return (getattr(res, "moved", 0) or 0), getattr(res, "status", None)


def drain_port_to_storage(port, outpost=None, include=None, allow_partial=False):
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
        if include is not None and not include(item_id):
            continue

        target = best_unload_target(item_id, 1 if allow_partial else count, outpost=outpost)
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


# OutputSlot.send() rejections that mean "Inventory has no room for this"
# (docs/types/storage_and_inventory.md) -- the only cases
# drain_port_inventory_first() falls back to a Warehouse for.
INVENTORY_FULL_STATUSES = ("partial", "target_full", "slots_full")


def drain_port_inventory_first(port, outpost=None):
    """
    Sends every stack staged in `port` (a Smelter/Fabricator output) to the
    home Inventory, and only when Inventory has no room (INVENTORY_FULL_STATUSES)
    sends the rest of that stack to a local Warehouse via
    drain_port_to_storage(). Inventory stays the normal destination: a
    Warehouse-held input costs the consumer an Auto Feeder hop on take_item().
    But a finished item stuck in an output buffer stalls the machine outright,
    and is invisible to take_item() entirely -- found live with Inventory at
    36/36 slots (data-bearing Oil Tanks, one slot each): Fabricator output
    bins filled and every recipe behind them stalled. take_item() already
    rotates through Warehouses, so Supply Docks and Fabricators still find a
    fallback-stored item. INVENTORY_ONLY_ITEM_IDS fall back too: a stall is
    worse, and the rebalance sweep only moves items away from Inventory, so
    such an item waits in the Warehouse until someone takes it.

    Reconnects the port to "inventory" before each send, since a previous
    fallback leaves it pointed at a Warehouse.

    Returns [(item_id, moved, destination, status, message), ...] per stack,
    destination "inventory" or "warehouse"; a stack neither accepted is
    reported with moved 0 and the Inventory send's status/message.
    """
    results = []
    if not port or not hasattr(port, "stacks"):
        return results
    try:
        stacks = port.stacks()
    except Exception:
        return results

    for stack in stacks:
        item_id = getattr(stack, "id", None)
        count = getattr(stack, "count", 0)
        if not item_id or count <= 0:
            continue
        try:
            if not hasattr(port, "connected_id") or port.connected_id() != "inventory":
                port.connect("inventory")
            res = port.send(item_id, count)
        except Exception as error:
            results.append((item_id, 0, "inventory", "exception", str(error)))
            continue
        status = getattr(res, "status", None)
        moved = getattr(res, "moved", 0) or 0
        if moved > 0:
            results.append((item_id, moved, "inventory", status, getattr(res, "message", "")))
        if status not in INVENTORY_FULL_STATUSES:
            if moved <= 0:
                results.append((item_id, 0, "inventory", status, getattr(res, "message", "")))
            continue
        fallback = drain_port_to_storage(port, outpost=outpost, include=lambda i, wanted=item_id: i == wanted, allow_partial=True)
        if fallback > 0:
            results.append((item_id, fallback, "warehouse", "ok", ""))
        elif moved <= 0:
            results.append((item_id, 0, "inventory", status, getattr(res, "message", "")))
    return results


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
    if item_id in INVENTORY_ONLY_ITEM_IDS:
        return True
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


def _items_demanded_by_active_dock_orders(outpost=None):
    """
    Set of item_ids still owed (requires - shipped > 0) by any Supply Dock's
    current active order at `outpost` (default: home outpost). A campaign/
    weekly Earth Order can demand a NON_WAREHOUSABLE_CATEGORIES item (e.g. a
    "deployable" equipment item) hundreds of units deep -- far more than
    Inventory has slots for -- but supply_dock.py's loading step already
    pulls straight from a Warehouse via storage.take_item()/total_stock()
    without needing the stock staged in Inventory first, so there's no
    benefit (and real risk of flooding every open Inventory slot) in
    reclaim_inventory_only_items_from_warehouses() also dragging that bulk
    stock back. Self-contained (doesn't import production.py's
    discover_supply_dock_ids()/_all_dock_orders() to avoid a circular
    import -- production.py already imports from this module) using the same
    outpost.buildings() discovery idiom as discover_storage_buildings().
    """
    if outpost is None:
        outpost = _home_outpost()
    if not outpost or not hasattr(outpost, "buildings"):
        return set()

    demanded = set()
    try:
        dock_refs = outpost.buildings("supply_dock")
    except Exception:
        return demanded
    for ref in dock_refs:
        dock_id = getattr(ref, "id", None)
        if not dock_id:
            continue
        dock = _component(dock_id)
        if not dock or not hasattr(dock, "current_order"):
            continue
        try:
            order = getattr(dock, "current_order")()
        except Exception:
            continue
        if not order:
            continue
        requires = getattr(order, "requires", {}) or {}
        shipped = getattr(order, "shipped", {}) or {}
        for item_id, req_count in requires.items():
            if req_count - shipped.get(item_id, 0) > 0:
                demanded.add(item_id)
    return demanded


def reclaim_inventory_only_items_from_warehouses(outpost=None):
    """
    Reverse of rebalance_inventory_to_warehouses(): sweeps every discovered
    Warehouse for stock in NON_WAREHOUSABLE_CATEGORIES (see
    _must_stay_in_inventory) and moves it back to Inventory.

    This exists as a safety net, not a normal code path -- nothing in this
    codebase should ever *place* such an item into a Warehouse to begin with
    (rebalance_inventory_to_warehouses() itself skips them via
    _occupied_stackable_slots_by_item()), so any occurrence here means it
    arrived some other way (e.g. a player manually stashing gear, or a
    Warehouse compact()/consolidate operation moving a stack the sweep never
    intended to touch). Left behind, it would be stranded with no way to
    equip a Pioneer/Rover or place it as equipment.

    Skips any item an active Supply Dock order still owes (see
    _items_demanded_by_active_dock_orders()) -- a bulk Earth Order contract
    for a deployable can run hundreds of units deep, far more than Inventory
    has room for, and the Dock already ships straight from the Warehouse
    without needing it staged here first. Everything else is reclaimed
    unconditionally regardless of Inventory slot pressure.

    Each exact property-variant slot is moved back individually (property_match
    "exact") so a durability-bearing equipment stack isn't merged with a
    different variant of the same item_id.
    """
    inventory = _component("inventory")
    if not inventory or not hasattr(inventory, "transfer_to"):
        return

    dock_demanded = _items_demanded_by_active_dock_orders(outpost)

    reclaimed_total = 0
    for building in discover_storage_buildings(outpost):
        component = building["component"]
        if not component or not hasattr(component, "slots") or not hasattr(component, "transfer_to"):
            continue
        try:
            slots = component.slots()
        except Exception:
            continue
        for slot in slots:
            item_id = getattr(slot, "item", None)
            count = getattr(slot, "count", 0)
            if not item_id or count <= 0:
                continue
            if not _must_stay_in_inventory(item_id):
                continue
            if item_id in dock_demanded:
                log.debug(f"reclaim_inventory_only_items_from_warehouses: leaving {count}x {item_id} in Warehouse '{building['id']}' -- an active Supply Dock order still owes it, ships straight from the Warehouse")
                continue
            properties = getattr(slot, "properties", None)
            try:
                res = component.transfer_to("inventory", item_id, int(count), properties=properties, property_match="exact")
            except Exception:
                continue
            moved = getattr(res, "moved", 0) or 0
            if moved > 0:
                reclaimed_total += moved
                log.print(f"[storage] Reclaimed {moved}x {item_id} from Warehouse '{building['id']}' back to Inventory (Inventory-only category).")
            elif getattr(res, "status", None) not in ("no_op",):
                log.debug(f"reclaim_inventory_only_items_from_warehouses: '{building['id']}' transfer_to('inventory', {item_id}) moved 0 units ({getattr(res, 'status', '?')})")
    log.debug(f"reclaim_inventory_only_items_from_warehouses: reclaimed {reclaimed_total} unit(s) total across every discovered Warehouse")
    return reclaimed_total


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
