# Shared Storage Management, data layer: makes the production chain
# (Smelter, Fabricator, Supply Dock, Pioneer construction loading, vehicle
# unloading) aware of Warehouse/Large Warehouse buildings, not just the
# central home "inventory" freight endpoint. Here: storage discovery and the
# retiring registry, stock reads and the StorageSnapshot, slot and
# Inventory capacity, the busy registry and the smelt partner table.
# The modules above it import from here, never the reverse: the take path
# (take_item() and its holder search) lives in lib/storage_take.py, the
# unload path (best_unload_target(), the sends and port drains) in
# lib/storage_unload.py; the two never import each other. The housekeeping
# sweeps (the "inventory manager" sweep, consolidation, fleet part parking)
# in lib/storage_sweeps.py use the unload path's best_unload_target().
#
# Scope: Warehouse + Large Warehouse (identical slot-based API, see
# docs/components/warehouse.md / large_warehouse.md) and Storage Bin. A bin's
# single-material API (docs/components/storage_bin.md) is wrapped in BinStore,
# a Warehouse-shaped view with one material-locked slot, so every caller of
# discover_storage_buildings() treats all three alike.
#
# Everything here defaults to the home outpost, matching how Inventory itself
# only participates at Nocturna Base (docs/components/inventory.md).

from dataclasses import dataclass

import components
from archive import archive
from atomic import run_batched
from game_clock import TickCache, now_tick
from game_rules import SMELT_PRODUCTS, WAREHOUSE_SLOT_UNITS
from item_tiers import BATTERY_TIERS, CARGO_POD_TIERS, DEPOT_KIT_TIERS, DRONE_CHASSIS_TIERS, OIL_TANK_TIERS
from swallow import swallowed
from tree_console import TreeConsole

log = TreeConsole(module="storage")

# Warehouses first: drone_depot.slot_capacity() reads the first slot it sees.
STORAGE_TYPE_IDS = ("warehouse", "large_warehouse", "storage_bin")
STORAGE_BIN_TYPE_ID = "storage_bin"

# Overcrowding (simworker machine table): counted buildings that lose 10%
# per building over the outpost cap; every other counted building (storage,
# tanks, Drone Depots) is exempt. Autoplay sizes outposts with it
# (autoplay_roles.py); lib/site_supply.py finds storage outposts by it.
PENALIZED_TYPES = (
    "smelter",
    "fabricator",
    "refiner",
    "bio_collector",
    "bio_lab",
    "bio_exchange",
    "bio_luminizer",
    "dna_sequencer",
    "bio_caster",
    "bio_conditioner",
    "essence_liquifier",
    "biomass_mixer",
    "seed_maker",
    "feed_maker",
    "habitat",
    "plant_terraformer",
    "reactor",
    "fuel_assembler",
    "steam_turbine",
    "steam_condenser",
    "oil_generator",
    "solar_generator",
    "oxygen_generator",
    "temp_heater",
    "pressure_generator",
    "garbage_disposal",
    "lightning_rod",
    "charging_station",
    "drone_service_station",
    "supply_dock",
)

# "inventory manager" sweep: an item spanning more than this many Inventory
# slots gets moved out to a Warehouse (see rebalance_inventory_to_warehouses()).
INVENTORY_REBALANCE_SLOT_THRESHOLD = 2

# Empty Inventory slots automated bulk moves (unloads, machine output drains,
# Warehouse-to-Inventory sweeps) never fill: Shop purchases, undeploy() and
# module swaps land in Inventory and need a free slot (inventory_room()).
INVENTORY_FREE_SLOTS_KEEP = 4
# Empty slots a Warehouse keeps for ore/cargo unloads when a Drone Depot stages
# life forms into it (drone_depot.buffer_target()); eviction leaves one more
# than this at an outpost whose Depot stages life forms (site_evict.evict_room()).
STAGING_FREE_SLOTS_KEEP = 1

BIGGER_STACKS_TECH_ID = "research_high_density_storage"
DEFAULT_STACK_SIZE = 10
BIGGER_STACKS_SIZE = 20

# Default per-item stock target (ore and ingot buffers): BIN_STOCK_TARGET
# until Warehouse research, then WAREHOUSE_STOCK_TARGET. Both stay below one
# slot's capacity (docs/components/storage_bin.md: 500,
# docs/components/warehouse.md: 5 x 2000), so a small overshoot (a late
# Smelter batch, a full Pioneer load) still fits the slot that holds the
# item instead of opening a second one.
WAREHOUSE_TECH_ID = "research_warehouse"
BIN_STOCK_TARGET = 400
WAREHOUSE_STOCK_TARGET = 1800

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
#   - "upgrade_pack": Mk II+ building upgrade packs (e.g.
#     pressure_upgrade_pack_mk2) apply to a placed building from Inventory
#     only.
NON_WAREHOUSABLE_CATEGORIES = ("equipment", "module", "portable", "upgrade_pack")
# Explicit ids on top of the categories above: drone hardware must also sit in
# Inventory -- computer.deploy() takes Depot kits and chassis from there, and
# drone.couple() takes modules from there (docs/components/drone.md). Listed
# by id since their item_catalog categories aren't documented; the fleet
# upgrade (lib/fleet_upgrade.py) orders and consumes these. The Pioneer
# chassis likewise, for lib/fleet_commission.py's deploy.
# The biosphere kits deploy from Inventory too (an outpost building, or a
# field machine from the Harvester), but item_catalog files them under
# "agriculture", not "equipment" (docs/database/items_agriculture_and_feeds.md).
AGRICULTURE_DEPLOY_KITS = ("seed_maker_kit", "grow_lamp_kit", "sprinkler_kit", "dispenser_kit", "garbage_disposal_kit")
INVENTORY_ONLY_ITEM_IDS = tuple(["pioneer", "electric_thruster", "heli_thruster", "portable_bio_scanner", "portable_bio_extractor", "shield_plating", "drone_service_station_kit"] + list(AGRICULTURE_DEPLOY_KITS) + DEPOT_KIT_TIERS + DRONE_CHASSIS_TIERS + BATTERY_TIERS + CARGO_POD_TIERS + OIL_TANK_TIERS)
# Fleet parts home Inventory holds only a few of per item id: one chassis or
# Depot kit, FLEET_MODULE_KEEP of each module (the largest drone_upgrade
# FIT_LOADOUTS count of one category: a large scout's 4 Battery Packs). Each
# unit takes a whole Inventory slot, so the kits of a queued drone backlog or
# the parts a swap returns would fill Inventory and stall every unload into
# it. The surplus waits in a Warehouse, where one item id shares a slot:
# best_unload_target() routes it there, park_surplus_fleet_parts() moves it
# out, and reclaim_inventory_only_items_from_warehouses() tops Inventory back
# up to the keep as parts get used.
FLEET_MODULE_KEEP = 4
# Thrusters too: a heli conversion or chassis swap returns the old one.
FLEET_PART_KEEP = {item_id: (1 if item_id in DRONE_CHASSIS_TIERS + DEPOT_KIT_TIERS else FLEET_MODULE_KEEP) for item_id in DRONE_CHASSIS_TIERS + DEPOT_KIT_TIERS + BATTERY_TIERS + CARGO_POD_TIERS + OIL_TANK_TIERS + ["electric_thruster", "heli_thruster"]}
# A tier below the best craftable one of its ladder keeps 0 (fleet_part_keep()):
# commissions, swaps and module upkeep only fit the best tier.
FLEET_PART_LADDERS = (DRONE_CHASSIS_TIERS, DEPOT_KIT_TIERS, CARGO_POD_TIERS, OIL_TANK_TIERS)


def outpost_is_home(outpost: "OutpostRef | None" = None):
    """True for the home outpost. None counts as home, matching every helper
    here that defaults `outpost` to home. Reads OutpostRef.is_home (a plain
    bool) and tolerates the Outpost component's is_home() method."""
    if outpost is None:
        return True
    is_home = getattr(outpost, "is_home", False)
    try:
        return bool(is_home() if callable(is_home) else is_home)
    except Exception as error:
        swallowed("storage.outpost_is_home: outpost.is_home", error)
        return False


def local_port_target(outpost: "OutpostRef | None" = None):
    """
    Default endpoint for a machine port at `outpost`: "inventory" at home,
    else the first local Warehouse id (Inventory only connects at home,
    docs/components/smelter.md / fabricator.md), None when the outpost has no
    Warehouse. take_item()/drain_port_to_storage() reconnect per holder
    anyway; this is only the resting connection.
    """
    if outpost_is_home(outpost):
        return "inventory"
    retiring = retiring_store_ids()
    buildings = discover_storage_buildings(outpost)
    staying = [b for b in buildings if b["id"] not in retiring] or buildings
    return staying[0]["id"] if staying else None


# discover_storage_buildings() runs under every total_stock()/take_item() call; results are reused for
# this many ticks (~2 s), so a newly placed Warehouse is seen at most that late.
DISCOVERY_TTL_TICKS = 20

# {(outpost_id, type_ids): [{"id", "component"}, ...]}
_DISCOVERY = TickCache(DISCOVERY_TTL_TICKS)

# Stores a building swap is emptying (lib/warehouse_upgrade.py): {building_id: owner}.
# Never picked to deliver into (best_unload_target(), top_up_target(),
# local_port_target(), the Inventory sweep, bin consolidation), still taken
# from (take_item(), stock reads), which helps the drain. Read through
# _RETIRING for DISCOVERY_TTL_TICKS.
RETIRING_STORES_KEY = "storage.retiring"
# tuple of retiring ids
_RETIRING = TickCache(DISCOVERY_TTL_TICKS)
# Warehouses per atomic stacks() read in warehouse_stocks(): a Large
# Warehouse holds at most 15 stacks, under ~150 steps per building.
STOCKS_CHUNK = 20


@dataclass
class BinSlot:
    """WarehouseSlot-shaped record for one Storage Bin stack."""

    index: int
    item: str
    count: int
    capacity: int
    properties: object


class BinStore:
    """
    Warehouse-shaped view of a Storage Bin: one material-locked slot of
    get_capacity() units. The bin latches to its first material and unlatches
    when empty, so space_for() is the free space for that material (or any
    material while empty) and 0 for every other item. Reads and transfer_to()
    pass straight through.
    """

    def __init__(self, bin_component):
        self._bin = bin_component
        self.id = getattr(bin_component, "id", None)
        self.name = getattr(bin_component, "name", self.id)
        self.outpost = getattr(bin_component, "outpost", None)

    def count(self, item_id):
        return self._bin.count(item_id)

    def stacks(self):
        return self._bin.stacks()

    def is_empty(self):
        return self._bin.is_empty()

    def fill_percent(self):
        return self._bin.fill_percent()

    def capacity(self):
        return self._bin.get_capacity()

    def total(self):
        return self._bin.get_capacity() - self._bin.space()

    def materials(self):
        material = self._bin.get_material()
        return [material] if material else []

    def space_for(self, item_id, properties=None):
        return self._bin.space() if self._bin.get_material() in ("", item_id) else 0

    def has_space(self, item_id, amount, properties=None):
        return self.space_for(item_id) >= amount

    def slots(self):
        """One BinSlot per stored stack (property variants stay separate), or one empty slot."""
        capacity = self._bin.get_capacity()
        stacks = [stack for stack in self._bin.stacks() if stack.count > 0]
        if not stacks:
            return [BinSlot(0, "", 0, capacity, None)]
        return [BinSlot(index, stack.id, stack.count, capacity, getattr(stack, "properties", None)) for index, stack in enumerate(stacks)]

    def transfer_to(self, target, item_id, count, properties=None, property_match=None):
        return self._bin.transfer_to(target, item_id, count, properties, property_match)


def discover_storage_buildings(outpost: "OutpostRef | None" = None, type_ids=STORAGE_TYPE_IDS):
    """
    [{"id": str, "component": obj}, ...] for every Warehouse, Large Warehouse
    and Storage Bin (as BinStore) at `outpost` (default: home outpost). Mirrors the existing
    get_all_charging_stations() discovery idiom in lib/vehicle_energy.py.
    Memoized for DISCOVERY_TTL_TICKS; entries are shared, treat them as read-only.
    """
    if outpost is None:
        outpost = components.home_outpost()
    if not outpost or not hasattr(outpost, "buildings"):
        return []
    key = (getattr(outpost, "id", None), tuple(type_ids))
    return list(_DISCOVERY.get(lambda: _scan_storage_buildings(outpost, type_ids), key))


def forget_storage_discovery():
    """Drops the discover_storage_buildings() memo, for a caller that just deployed or removed a store."""
    _DISCOVERY.clear()


def _retiring_entries():
    raw = archive.get(RETIRING_STORES_KEY, {})
    return raw if isinstance(raw, dict) else {}


def retiring_store_ids():
    """Ids of the stores no delivery may target (RETIRING_STORES_KEY), memoized for DISCOVERY_TTL_TICKS."""
    return _RETIRING.get(lambda: tuple(_retiring_entries().keys()))


def set_retiring_stores(owner, ids):
    """Makes `ids` owner's whole retiring set; empty `ids` clears it. Plain read
    first, so an unchanged set costs no archive write."""
    wanted = set(ids)
    current = _retiring_entries()
    if {k for k, v in current.items() if v == owner} == wanted and all(current.get(i) == owner for i in wanted):
        return

    def updater(state):
        state = {k: v for k, v in (state if isinstance(state, dict) else {}).items() if v != owner}
        for building_id in wanted:
            state[building_id] = owner
        return state

    try:
        archive.transaction(RETIRING_STORES_KEY, {}, updater)
    except Exception as error:
        swallowed("storage.set_retiring_stores: archive.transaction", error)
    _RETIRING.clear()


def _scan_storage_buildings(outpost: "OutpostRef", type_ids):
    found = []
    seen_ids = set()
    for type_id in type_ids:
        try:
            buildings = outpost.buildings(type_id)
        except Exception as error:
            swallowed("storage.discover_storage_buildings: outpost.buildings", error)
            continue
        for b in buildings:
            b_id = getattr(b, "id", None)
            if not b_id or b_id in seen_ids:
                continue
            component = components.component(b_id) or b
            if type_id == STORAGE_BIN_TYPE_ID:
                component = BinStore(component)
            seen_ids.add(b_id)
            found.append({"id": b_id, "component": component})
    return found


def slot_layout(outpost: "OutpostRef", snapshot: "StorageSnapshot | None" = None):
    """[(item_id or "", count, capacity)] per storage slot at `outpost`: each
    Warehouse / Large Warehouse slot (slots()), each Storage Bin as one slot.
    Unreadable buildings are left out."""
    snapshot = StorageSnapshot() if snapshot is None else snapshot
    return [(item_id, count, capacity) for entry in snapshot.buildings(outpost) for item_id, count, capacity, _properties in entry["rows"] or []]


def slot_fill(capacity):
    """Units the stock rule fills one slot of `capacity` to: WAREHOUSE_STOCK_TARGET for a
    Warehouse slot, BIN_STOCK_TARGET for a Storage Bin, so a full haul load never spills
    into a second slot; the capacity itself when smaller."""
    target = WAREHOUSE_STOCK_TARGET if capacity >= WAREHOUSE_SLOT_UNITS else BIN_STOCK_TARGET
    return min(capacity, target)


def slot_room(item_id, layout, planned=0, keep_free=0):
    """
    Units of item_id a store with `layout` (slot_layout()) may still take
    without filling a slot nobody planned for it, each slot only up to
    slot_fill(): the slots already holding it, or `planned` rounded up to
    whole slots when that is more. With neither, one empty slot while more
    than `keep_free` others stay empty. 0 when no slot fits or the layout is
    empty.
    """
    size = max([cap for _item, _count, cap in layout] or [0])
    if size <= 0:
        return 0
    fill = slot_fill(size)
    held = [(count, cap) for item, count, cap in layout if item == item_id]
    planned_cap = -(-planned // fill) * fill if planned > 0 else 0
    ceiling = max(sum(slot_fill(cap) for _count, cap in held), planned_cap)
    if ceiling > 0:
        return max(0, ceiling - sum(count for count, _cap in held))
    empty = [cap for item, _count, cap in layout if not item]
    return slot_fill(max(empty)) if len(empty) > keep_free else 0


def open_room(item_id, layout):
    """
    Units of item_id a store with `layout` (slot_layout()) takes when every
    slot may fill to its capacity: room in the slots already holding it plus
    every empty slot, as Warehouse.space_for() counts it. For a dump that
    keeps no slot free (site_supply storage outposts).
    """
    return sum(max(0, cap - count) for item, count, cap in layout if item == item_id) + sum(cap for item, _count, cap in layout if not item)


def total_stock(item_id, outpost: "OutpostRef | None" = None):
    """Units of item_id in the Warehouses and Storage Bins at `outpost` (None =
    home), plus Inventory at home: one count() per store, no Drone Depots.
    A one-off read for a loader or a count check; netting and request
    planning count stock_scan HELD (SourceCache.held_stock(),
    logistics_requests.outpost_stock()) instead."""
    total = 0
    inventory = components.component("inventory") if outpost_is_home(outpost) else None
    if inventory and hasattr(inventory, "count"):
        try:
            total += inventory.count(item_id)
        except Exception as error:
            swallowed("storage.total_stock: inventory.count", error)
    for building in discover_storage_buildings(outpost):
        component = building["component"]
        if component and hasattr(component, "count"):
            try:
                total += component.count(item_id)
            except Exception as error:
                swallowed("storage.total_stock: component.count", error)
    return total


def inventory_count(item_id):
    """inventory.count(item_id): units in home Inventory only, 0 if unreadable."""
    inventory = components.component("inventory")
    if not inventory or not hasattr(inventory, "count"):
        return 0
    try:
        return int(inventory.count(item_id) or 0)
    except Exception as error:
        swallowed("storage.inventory_count: inventory.count", error)
        return 0


def warehouse_stock(item_id, outpost: "OutpostRef | None" = None):
    """Sum of count(item_id) over the Warehouses and Storage Bins at `outpost`
    (None = home); never Inventory, even at home."""
    total = 0
    for building in discover_storage_buildings(outpost):
        component = building["component"]
        if component and hasattr(component, "count"):
            try:
                total += component.count(item_id)
            except Exception as error:
                swallowed("storage.warehouse_stock: component.count", error)
    return total


def stacks_stock(component, item_ids):
    """{item_id: units} of item_ids in one store (Warehouse, Inventory, ...): one
    stacks() read instead of a count() per item; count() when there is no stacks()."""
    totals = {item_id: 0 for item_id in item_ids}
    if not component:
        return totals
    if not hasattr(component, "stacks"):
        for item_id in totals:
            totals[item_id] = component.count(item_id)
        return totals
    for stack in component.stacks():
        if stack.id in totals:
            totals[stack.id] += stack.count
    return totals


def _stacks_rows(buildings):
    """[[(item_id, units), ...]] per building, from one stacks() read each (count() needs item ids, so a store without stacks() gives None); pure reads, run atomically."""
    rows = []
    for building in buildings:
        component = building["component"]
        if not component or not hasattr(component, "stacks"):
            rows.append(None)
            continue
        try:
            rows.append([(stack.id, stack.count) for stack in component.stacks()])
        except Exception as error:
            swallowed("storage.warehouse_stocks: stacks", error)
            rows.append([])
    return rows


def warehouse_stocks(item_ids, outpost: "OutpostRef | None" = None):
    """{item_id: warehouse_stock(item_id, outpost)} for every item, one stacks() read per Warehouse (atomic, STOCKS_CHUNK buildings per call)."""
    totals = {item_id: 0 for item_id in item_ids}
    if not totals:
        return totals
    buildings = discover_storage_buildings(outpost)
    for building, row in zip(buildings, run_batched(_stacks_rows, buildings, STOCKS_CHUNK)):
        if row is None:
            try:
                row = list(stacks_stock(building["component"], totals).items())
            except Exception as error:
                swallowed("storage.warehouse_stocks: stacks_stock", error)
                continue
        for item_id, units in row:
            if item_id in totals:
                totals[item_id] += units
    return totals


def _slot_rows(buildings):
    """[[(item_id or "", count, capacity, properties), ...]] per building, one
    slots() read each (None when unreadable); pure reads, run atomically."""
    rows = []
    for building in buildings:
        component = building["component"]
        if not component or not hasattr(component, "slots"):
            rows.append(None)
            continue
        try:
            rows.append([(getattr(s, "item", "") or "", getattr(s, "count", 0) or 0, getattr(s, "capacity", 0) or 0, getattr(s, "properties", None)) for s in component.slots()])
        except Exception as error:
            swallowed("storage._slot_rows: slots", error)
            rows.append(None)
    return rows


class StorageSnapshot:
    """
    Slot contents of every store at an outpost, read once (one slots() per
    building, STOCKS_CHUNK buildings per atomic call) and shared by the
    storage pass's sweeps. A sweep that moves units calls touched() for the
    stores it changed; their rows are read again on the next access. Other
    changes (machines, haulers) between sweeps are accepted as stale:
    transfer_to() moves what is there and reports "partial".
    """

    def __init__(self):
        self._outposts = {}  # {outpost_id: [{"id", "component", "rows"}, ...]}
        self._stale = set()

    def buildings(self, outpost: "OutpostRef | None" = None):
        """[{"id", "component", "rows"}] for discover_storage_buildings(outpost);
        rows is a list of (item_id or "", count, capacity, properties), or None
        when the store could not be read."""
        if outpost is None:
            outpost = components.home_outpost()
        key = getattr(outpost, "id", None)
        entries = self._outposts.get(key)
        if entries is None:
            found = discover_storage_buildings(outpost)
            entries = [{"id": b["id"], "component": b["component"], "rows": row} for b, row in zip(found, run_batched(_slot_rows, found, STOCKS_CHUNK))]
            self._outposts[key] = entries
        stale = [entry for entry in entries if entry["id"] in self._stale]
        for entry, row in zip(stale, _slot_rows(stale)):
            entry["rows"] = row
            self._stale.discard(entry["id"])
        return entries

    def touched(self, *building_ids):
        """Marks stores whose contents a sweep just changed."""
        self._stale.update(building_ids)


def _snapshot_holders(entry):
    """{item_id: units} of propertyless stock in one snapshot entry; property
    variants are left out, a plain transfer_to() would not move them."""
    held = {}
    for item_id, count, _capacity, properties in entry["rows"] or []:
        if item_id and count > 0 and not properties:
            held[item_id] = held.get(item_id, 0) + count
    return held


# Smelter recipes as {ore: product} (game_rules.SMELT_PRODUCTS). An ore
# and its product are "partners": a Smelter takes the one and sends the other
# at the same time, and a Warehouse handles one material operation at a time,
# so the two in one Warehouse answer each other's transfers with "busy".
# best_unload_target() keeps them in separate Warehouses where it can.
SMELT_PARTNERS = SMELT_PRODUCTS
# Assumed transfer volume, hottest first (harder ore is mined and used less).
# A product shares its ore's heat; an item not listed has heat 0.
ORE_HEAT_ORDER = ["iron_ore", "silicon", "titanium", "cobalt", "lead_ore", "rare_earth", "neutronium"]

_partners = {}
for _ore, _product in SMELT_PARTNERS.items():
    _partners[_ore] = {_product}
    _partners[_product] = {_ore}
_heat = {}
for _rank, _ore in enumerate(ORE_HEAT_ORDER):
    _heat[_ore] = len(ORE_HEAT_ORDER) - _rank
    _heat[SMELT_PARTNERS[_ore]] = len(ORE_HEAT_ORDER) - _rank


def _snapshot_clash(item_id, held):
    """best_unload_target()'s clash of item_id with the items in `held`."""
    heat = item_heat(item_id)
    return sum([heat * item_heat(partner) for partner in recipe_partners(item_id) if partner in held])


def recipe_partners(item_id):
    """Items that should not share a Warehouse with item_id (empty set if none)."""
    return _partners.get(item_id, set())


def item_heat(item_id):
    """Assumed transfer volume of item_id (ORE_HEAT_ORDER), 0 when not listed."""
    return _heat.get(item_id, 0)


# A storage endpoint that answered "busy" to a take() within this many ticks
# (~2s at 10 ticks/s) is tried LAST by take_item(), not skipped -- still
# used when nothing else holds the item. There is no API to ask "is this
# Warehouse busy?" up front; a "busy" rejection comes back immediately (no
# feeder wait), so the rejection itself is the probe, remembered here so
# the next take_item() call (from any consumer in this script) doesn't lead
# with the same locked building again.
TAKE_BUSY_COOLDOWN_TICKS = 20
_recent_busy = {}  # {source_id: tick of last "busy" rejection}


def mark_busy(source_id, tick=None):
    """Remembers that source_id answered "busy" (see TAKE_BUSY_COOLDOWN_TICKS)."""
    _recent_busy[source_id] = now_tick() if tick is None else tick


def recently_busy(source_id, now=None):
    """True if source_id answered "busy" within TAKE_BUSY_COOLDOWN_TICKS."""
    busy_tick = _recent_busy.get(source_id)
    now = now_tick() if now is None else now
    return busy_tick is not None and now > 0 and now - busy_tick <= TAKE_BUSY_COOLDOWN_TICKS


def inventory_stack_size():
    """Current Inventory stack size per slot: 10, or 20 once Bigger Stacks is unlocked."""
    research = components.component("research")
    if research and hasattr(research, "is_unlocked"):
        try:
            if research.is_unlocked(BIGGER_STACKS_TECH_ID):
                return BIGGER_STACKS_SIZE
        except Exception as error:
            swallowed("storage.inventory_stack_size: research.is_unlocked", error)
    return DEFAULT_STACK_SIZE


def inventory_room(item_id, properties=None, keep=INVENTORY_FREE_SLOTS_KEEP):
    """
    Units of item_id home Inventory takes while `keep` slots stay empty:
    space_for() minus the empty slots held back, at the current stack size
    (one unit per slot for a property-bearing or non-stackable item). 0 when Inventory is
    missing or unreadable. Without get_size()/get_used() it is space_for().
    """
    inventory = components.component("inventory")
    if not inventory or not hasattr(inventory, "space_for"):
        return 0
    try:
        space = inventory.space_for(item_id, properties) if properties else inventory.space_for(item_id)
    except Exception as error:
        swallowed("storage.inventory_room: inventory.space_for", error)
        return 0
    if keep <= 0 or not hasattr(inventory, "get_size") or not hasattr(inventory, "get_used"):
        return max(0, space)
    try:
        empty = inventory.get_size() - inventory.get_used()
    except Exception as error:
        swallowed("storage.inventory_room: inventory.get_size", error)
        return 0
    # A non-stackable item (construction kit, equipment, module: one unit per
    # slot) fits exactly one unit per empty slot; a stackable one at least a
    # full stack per empty slot. Charging it the stack size per reserved slot
    # zeroed its room while Inventory sat nearly empty.
    per_slot = 1 if properties or space <= empty else inventory_stack_size()
    return max(0, space - min(max(0, empty), keep) * per_slot)


def inventory_part_room(item_id, properties=None):
    """inventory_room(), and for a FLEET_PART_KEEP item at most the units
    Inventory lacks of its keep."""
    room = inventory_room(item_id, properties)
    keep = fleet_part_keep(item_id)
    return room if keep is None else min(room, max(0, keep - inventory_count(item_id)))


_UNLOCKED_OUTPUTS = TickCache(DISCOVERY_TTL_TICKS)


def fleet_part_keep(item_id):
    """FLEET_PART_KEEP of item_id (None if not a fleet part), 0 when a higher
    tier of its FLEET_PART_LADDERS ladder is craftable. With nothing of the
    ladder craftable (no Fabricator, or parts only bought) every tier keeps."""
    keep = FLEET_PART_KEEP.get(item_id)
    if not keep:
        return keep
    ladder = next((tiers for tiers in FLEET_PART_LADDERS if item_id in tiers), None)
    if ladder is None:
        return keep
    from production_cascade import fabricator_unlocked_outputs  # cycle: production_cascade imports storage

    unlocked = _UNLOCKED_OUTPUTS.get(fabricator_unlocked_outputs)
    if any(tier in unlocked for tier in ladder[ladder.index(item_id) + 1 :]):
        return 0
    return keep


def warehouses_unlocked():
    """True once Warehouse research is unlocked."""
    research = components.component("research")
    if research and hasattr(research, "is_unlocked"):
        try:
            return bool(research.is_unlocked(WAREHOUSE_TECH_ID))
        except Exception as error:
            swallowed("storage.warehouses_unlocked: research.is_unlocked", error)
    return False


def default_stock_target():
    """(units, final) default per-item stock target: WAREHOUSE_STOCK_TARGET
    once Warehouses are unlocked (final, safe to seed into the archive), else
    BIN_STOCK_TARGET (not final: callers don't seed it, so the lookup after
    the unlock seeds the Warehouse default)."""
    if warehouses_unlocked():
        return WAREHOUSE_STOCK_TARGET, True
    return BIN_STOCK_TARGET, False


def must_stay_in_inventory(item_id):
    """True if item_catalog classifies item_id as one of
    NON_WAREHOUSABLE_CATEGORIES -- equipment that deploys straight from
    Inventory, or vehicle-slot gear needed to equip a Pioneer/Rover -- so the
    inventory manager sweep must leave it alone."""
    if item_id in INVENTORY_ONLY_ITEM_IDS:
        return True
    catalog = components.component("item_catalog")
    if not catalog or not hasattr(catalog, "lookup"):
        return False
    try:
        info = catalog.lookup(item_id)
    except Exception as error:
        swallowed("storage.must_stay_in_inventory: catalog.lookup", error)
        return False
    return bool(info) and getattr(info, "category", None) in NON_WAREHOUSABLE_CATEGORIES


def _items_demanded_by_active_dock_orders(outpost: "OutpostRef | None" = None):
    """
    Set of item_ids still owed (requires - shipped > 0) by any Supply Dock's
    current active order at `outpost` (default: home outpost). A campaign/
    weekly Earth Order can demand a NON_WAREHOUSABLE_CATEGORIES item (e.g. a
    "deployable" equipment item) hundreds of units deep -- far more than
    Inventory has slots for -- but supply_dock.py's loading step already
    pulls straight from a Warehouse via storage_take.take_item()/storage.total_stock()
    without needing the stock staged in Inventory first, so there's no
    benefit (and real risk of flooding every open Inventory slot) in
    reclaim_inventory_only_items_from_warehouses() also dragging that bulk
    stock back. Self-contained (doesn't import production.py's
    discover_supply_dock_ids()/_all_dock_orders() to avoid a circular
    import -- production.py already imports from this module) using the same
    outpost.buildings() discovery idiom as discover_storage_buildings().
    """
    if outpost is None:
        outpost = components.home_outpost()
    if not outpost or not hasattr(outpost, "buildings"):
        return set()

    demanded = set()
    try:
        dock_refs = outpost.buildings("supply_dock")
    except Exception as error:
        swallowed("storage._items_demanded_by_active_dock_orders: outpost.buildings", error)
        return demanded
    for ref in dock_refs:
        dock_id = getattr(ref, "id", None)
        if not dock_id:
            continue
        dock = components.component(dock_id)
        if not dock or not hasattr(dock, "current_order"):
            continue
        try:
            order = getattr(dock, "current_order")()
        except Exception as error:
            swallowed("storage._items_demanded_by_active_dock_orders: getattr(dock, 'current_order')", error)
            continue
        if not order:
            continue
        requires = getattr(order, "requires", {}) or {}
        shipped = getattr(order, "shipped", {}) or {}
        for item_id, req_count in requires.items():
            if req_count - shipped.get(item_id, 0) > 0:
                demanded.add(item_id)
    return demanded
