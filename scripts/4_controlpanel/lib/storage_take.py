# Take path, split out of lib/storage.py: finds the holders of an item
# (Inventory, Warehouses, Storage Bins and the home Crop Automators' Forage)
# and take()s it into a machine or vehicle input port, recently busy
# holders last. take_item() serves every consumer that loads from storage
# (Smelter, Fabricator, Supply Dock, Pioneer loading, the bio machines);
# stock_scan and the Forage consumers read the crop automator helpers.

from typing import TYPE_CHECKING

import components
from archive import archive
from game_clock import now_tick
from game_rules import CROP_AUTOMATOR_OUTPUT_CAP
from machine_controller import port_counts
from parking_client import wake_for_visit
from storage import BinStore, discover_storage_buildings, log, mark_busy, outpost_is_home, recently_busy
from swallow import swallowed

if TYPE_CHECKING:
    from production import SourceCache


# Crop Automators (home Harvesting field) keep their Forage
# in their output instead of draining it to Warehouses, so Forage consumers
# take it from there (lib/crop_automator.py). Forage in Inventory or a
# Warehouse drains first: it only takes slots there. Among the automators,
# clogged ones go first (a full output pauses harvests; the automator queues
# one only while the output has room for it), and diversity-garden ones
# before the fill: the garden carries the field's variety bonus.
CROP_AUTOMATOR_TYPE_ID = "crop_automator"
CROP_AUTOMATOR_ITEM_ID = "forage"
CROP_AUTOMATOR_CLOG_FRACTION = 0.9  # at/above this fill (or status "output_full") it counts as clogged
CROP_AUTOMATOR_STATUS_KEY = "plant.automators"  # lib/crop_automator.py telemetry; "garden", "harvest_yield" read here
CROP_AUTOMATOR_WAKE_FREE_MIN = 1000  # a pull wakes a parked automator only if it leaves at least this much room (or its harvest_yield, if larger)


def crop_automator_wake_free(automator_id):
    """Free output units a parked Crop Automator needs before a wake is worth it: one harvest."""
    telemetry = archive.get(CROP_AUTOMATOR_STATUS_KEY, {})
    entry = telemetry.get(automator_id, {}) if isinstance(telemetry, dict) else {}
    harvest_yield = entry.get("harvest_yield") if isinstance(entry, dict) else None
    return max(CROP_AUTOMATOR_WAKE_FREE_MIN, harvest_yield or 0)


def crop_automator_forage(outpost: "OutpostRef | None" = None):
    """
    [(automator_id, forage, clogged, garden)] for every Crop Automator at
    `outpost` (default home; only home has a Harvesting field) holding
    Forage, in drain order: clogged first, then garden, then most Forage.
    Automators are identified by HarvestingMachineRef.type_id, never by id.
    """
    resolved = outpost if outpost is not None else components.home_outpost()
    if resolved is None or not hasattr(resolved, "harvesting_machines"):
        return []
    try:
        refs = list(resolved.harvesting_machines(CROP_AUTOMATOR_TYPE_ID) or [])
    except Exception as error:
        swallowed("storage.crop_automator_forage: resolved.harvesting_machines", error)
        return []
    telemetry = archive.get_dict(CROP_AUTOMATOR_STATUS_KEY)
    garden_ids = [k for k, v in telemetry.items() if isinstance(v, dict) and v.get("garden")]
    out = []
    for ref in refs:
        if getattr(ref, "type_id", CROP_AUTOMATOR_TYPE_ID) != CROP_AUTOMATOR_TYPE_ID:
            continue
        ca_id = getattr(ref, "id", None)
        machine = components.component(ca_id) if ca_id else None
        port = getattr(machine, "output", None)
        if not ca_id or not port or not hasattr(port, "stacks"):
            continue
        # OutputSlot.count() takes no item id (docs/types/storage_and_inventory.md):
        # must iterate stacks instead of calling count("forage").
        count = int(port_counts(port, "storage.crop_automator_forage: port.stacks").get(CROP_AUTOMATOR_ITEM_ID, 0))
        if count <= 0:
            continue
        try:
            status = getattr(machine, "status")()
        except Exception as error:
            swallowed("storage.crop_automator_forage: getattr(machine, 'status')", error)
            status = None
        clogged = status == "output_full" or count >= CROP_AUTOMATOR_CLOG_FRACTION * CROP_AUTOMATOR_OUTPUT_CAP
        garden = ca_id in garden_ids
        out.append((ca_id, count, clogged, garden))
    out.sort(key=lambda e: (0 if e[2] else 1, 0 if e[3] else 1, -e[1]))
    return out


def crop_automator_forage_total(outpost: "OutpostRef | None" = None):
    """Forage sitting in the Crop Automators' outputs at `outpost`."""
    return int(sum(e[1] for e in crop_automator_forage(outpost)))


def _live_holders(item_id, outpost: "OutpostRef | None", is_home):
    """[(source_id, units)] read live: Inventory (home only), then each storage building."""
    holders = []
    if is_home:
        inventory = components.component("inventory")
        if inventory and hasattr(inventory, "count"):
            try:
                count = inventory.count(item_id)
            except Exception as error:
                swallowed("storage._holder_candidates: inventory.count", error)
                count = 0
            if count > 0:
                holders.append(("inventory", count))
    for building in discover_storage_buildings(outpost):
        component = building["component"]
        if not component or not hasattr(component, "count"):
            continue
        try:
            count = component.count(item_id)
        except Exception as error:
            swallowed("storage._holder_candidates: component.count", error)
            continue
        if count > 0:
            holders.append((building["id"], count))
    return holders


def _holder_candidates(item_id, outpost: "OutpostRef | None" = None, cache: "SourceCache | None" = None, automators=None):
    """
    [(source_id, units)] for every storage endpoint holding item_id, in the
    order take_item() should try them:
      1. Inventory (home only) -- it has no Auto Feeder of its own and never
         locks, so it's the one source that can't be "busy".
      2. Storage Bins holding the item, fewest units first: emptying a bin
         unlatches its material, so the whole bin is free again.
      3. Warehouses holding the item, most units first.
      4. Forage only: clogged Crop Automators (a full output stalls their
         harvests), garden first, then most Forage. Forage in Inventory and
         storage drains before any automator: it only takes slots there.
      5. Forage only: the other Crop Automators, garden first, then most
         Forage.
      6. ...with any endpoint that answered "busy" within
         TAKE_BUSY_COOLDOWN_TICKS moved to the end (stable, so the order
         above is kept within each group).
    Endpoints holding 0 are left out entirely -- the old blind
    connect()+take() walk over every Warehouse regardless of contents cost a
    reconnect per miss. Uses a SourceCache's one-shot per-building snapshot
    when one is passed (home outpost only, which is all it covers).
    `automators` (a set, optional) receives the Crop Automator ids listed.
    """
    resolved = outpost if outpost is not None else components.home_outpost()
    is_home = outpost_is_home(outpost)

    holders = []
    # {automator_id: rank within the sort: 3 = clogged, 4 = normal}, plus
    # garden order; stored per id so nothing depends on the id's spelling.
    automator_rank = {}
    if item_id == CROP_AUTOMATOR_ITEM_ID and is_home:
        for ca_id, count, clogged, garden in crop_automator_forage(resolved):
            holders.append((ca_id, count))
            automator_rank[ca_id] = (3 if clogged else 4, 0 if garden else 1)
            if automators is not None:
                automators.add(ca_id)
    if cache is not None and outpost is None and hasattr(cache, "building_stock"):
        holders += list(cache.building_stock(item_id))
    else:
        holders += _live_holders(item_id, outpost, is_home)

    bin_ids = {b["id"] for b in discover_storage_buildings(outpost) if isinstance(b["component"], BinStore)}
    now = now_tick()
    ranked = []
    for source_id, count in holders:
        # 1 Inventory, 2 Storage Bin, 3 Warehouse, 4 clogged automator, 5 other automator.
        if source_id in bin_ids:
            kind_rank, garden_rank, size_key = 2, 0, count
        else:
            kind_rank, garden_rank = automator_rank.get(source_id, (1 if source_id == "inventory" else 3, 0))
            size_key = -count
        ranked.append(((1 if recently_busy(source_id, now) else 0, kind_rank, garden_rank, size_key), (source_id, count)))
    ranked.sort(key=lambda pair: pair[0])
    return [entry for _key, entry in ranked]


def takeable_stock(item_id, outpost: "OutpostRef | None" = None):
    """Units of item_id that take_item() could pull at `outpost`: the sum over the same holders it tries."""
    return sum([units for _source_id, units in _holder_candidates(item_id, outpost)])


def take_item(port: "InputSlot | VehicleInputSlot", item_id, amount, outpost: "OutpostRef | None" = None, cache: "SourceCache | None" = None, report=None):
    """
    Pulls up to `amount` units of item_id into `port` (a machine/vehicle
    input port exposing .connect(id)/.connected_id()/.take(item_id, count)).
    Only endpoints that actually hold the item are tried, in
    _holder_candidates() order (Inventory first, then Storage Bins by least
    stock, then Warehouses by most stock, recently-"busy" ones last; Forage adds Crop Automators after
    Warehouses, clogged ones first), reconnecting between them since a
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
        except Exception as error:
            swallowed("storage.take_item: port.connected_id", error)
            current_id = None

    moved_total = 0
    remaining = amount
    log.start(f"take_item({item_id})", level="debug")
    automators = set()
    for source_id, held in _holder_candidates(item_id, outpost, cache, automators):
        if remaining <= 0:
            break
        if source_id in automators:
            # A Crop Automator parked on a full output (lib/script_parking.py) is
            # switched on once this pull leaves room for one harvest; a smaller
            # pull would only wake it to find no room.
            free_after = CROP_AUTOMATOR_OUTPUT_CAP - (held - min(held, remaining))
            if free_after >= crop_automator_wake_free(source_id):
                wake_for_visit(source_id, "Forage pulled", hold=False)
        if source_id != current_id:
            try:
                res = port.connect(source_id)
            except Exception as error:
                swallowed("storage.take_item: port.connect", error)
                continue
            status = getattr(res, "status", None)
            if status != "ok":
                if report is not None:
                    report["sources"].append((source_id, f"connect:{status}", 0))
                continue
            current_id = source_id
        moved, status = _take_from_current(port, item_id, remaining)
        if status == "busy":
            mark_busy(source_id)
        if report is not None:
            report["sources"].append((source_id, status, moved))
        log.debug(f"'{source_id}' -> status={status} moved={moved}/{remaining}")
        moved_total += moved
        remaining -= moved

    log.end()
    return moved_total


def hit_slot_cap(report):
    """True when a take_item() `report` holds a "slots_full": the port has unit
    room but no free material slot. Multi-material stockpiles cap distinct
    materials per machine type, and no method reports that cap."""
    return any(status == "slots_full" for _source, status, _moved in (report or {}).get("sources", []))


def _take_from_current(port: "InputSlot | VehicleInputSlot", item_id, remaining):
    """take(item_id, remaining) off whatever port is currently connected to.
    Returns (units actually moved, status) -- (0, "exception") if the call
    raised. Split out of take_item() as a plain helper (not a nested closure)
    since the sandboxed script parser does not support `nonlocal`."""
    if remaining <= 0:
        return 0, "no_op"
    try:
        res = port.take(item_id, remaining)
    except Exception as error:
        swallowed("storage._take_from_current: port.take", error)
        return 0, "exception"
    return (getattr(res, "moved", 0) or 0), getattr(res, "status", None)
