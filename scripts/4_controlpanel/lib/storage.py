# Shared Storage Management: makes the production chain (Smelter, Fabricator,
# Supply Dock, Pioneer construction loading, vehicle unloading) aware of
# Warehouse/Large Warehouse buildings, not just the central home "inventory"
# freight endpoint. Also owns the "inventory manager" sweep that actively
# moves bulk stock out of Inventory into a Warehouse once it piles up.
#
# Scope: Warehouse + Large Warehouse (identical slot-based API, see
# docs/components/warehouse.md / large_warehouse.md) and Storage Bin. A bin's
# single-material API (docs/components/storage_bin.md) is wrapped in BinStore,
# a Warehouse-shaped view with one material-locked slot, so every caller of
# discover_storage_buildings() treats all three alike.
#
# Everything here defaults to the home outpost, matching how Inventory itself
# only participates at Nocturna Base (docs/components/inventory.md).

from archive import archive
from tree_console import TreeConsole
import components
from swallow import swallowed
from script_parking import wake_for_visit
from atomic import run_batched
from typing import TYPE_CHECKING
from game_clock import now_tick

if TYPE_CHECKING:
    from production import SourceCache

log = TreeConsole(module="storage")

# Warehouses first: drone_depot.slot_capacity() reads the first slot it sees.
STORAGE_TYPE_IDS = ("warehouse", "large_warehouse", "storage_bin")
STORAGE_BIN_TYPE_ID = "storage_bin"

# "inventory manager" sweep: an item spanning more than this many Inventory
# slots gets moved out to a Warehouse (see rebalance_inventory_to_warehouses()).
INVENTORY_REBALANCE_SLOT_THRESHOLD = 2

BIGGER_STACKS_TECH_ID = "research_high_density_storage"
DEFAULT_STACK_SIZE = 10
BIGGER_STACKS_SIZE = 20

# Default per-item stock target (ore and ingot buffers): one Storage Bin
# (docs/components/storage_bin.md) until Warehouse research, then one
# Warehouse slot (docs/components/warehouse.md: 5 x 2000).
WAREHOUSE_TECH_ID = "research_warehouse"
STORAGE_BIN_CAPACITY = 500
WAREHOUSE_SLOT_CAPACITY = 2000

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
INVENTORY_ONLY_ITEM_IDS = (
    "pioneer",
    "drone_station_kit", "drone_station_kit_medium", "drone_station_kit_large",
    "drone_small", "drone_medium", "drone_large",
    "electric_thruster", "heli_thruster", "battery_pack",
    "cargo_pod_small", "cargo_pod_medium", "cargo_pod_large",
    "oil_tank_small", "oil_tank_medium", "oil_tank_large",
    "portable_bio_scanner", "portable_bio_extractor", "shield_plating",
)


def _home_outpost():
    network = components.component("outpost_network")
    if network and hasattr(network, "home"):
        try:
            return network.home()
        except Exception as error:
            swallowed("storage._home_outpost: network.home", error)
    return None


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
    buildings = discover_storage_buildings(outpost)
    return buildings[0]["id"] if buildings else None


# discover_storage_buildings() runs under every total_stock()/take_item() call; results are reused for
# this many ticks (~2 s), so a newly placed Warehouse is seen at most that late.
DISCOVERY_TTL_TICKS = 20

# {(outpost_id, type_ids): (tick, [{"id", "component"}, ...])}
_DISCOVERY_MEMO = {}
# Warehouses per atomic stacks() read in warehouse_stocks(): a Large
# Warehouse holds at most 15 stacks, under ~150 steps per building.
STOCKS_CHUNK = 20


class BinSlot:
    """WarehouseSlot-shaped record for one Storage Bin stack."""

    def __init__(self, index, item, count, capacity, properties):
        self.index = index
        self.item = item
        self.count = count
        self.capacity = capacity
        self.properties = properties


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
        outpost = _home_outpost()
    if not outpost or not hasattr(outpost, "buildings"):
        return []
    key = (getattr(outpost, "id", None), tuple(type_ids))
    now = now_tick()
    memo = _DISCOVERY_MEMO.get(key)
    if memo is not None and 0 <= now - memo[0] < DISCOVERY_TTL_TICKS:
        return list(memo[1])
    found = _scan_storage_buildings(outpost, type_ids)
    _DISCOVERY_MEMO[key] = (now, found)
    return list(found)


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


def total_stock(item_id, outpost: "OutpostRef | None" = None):
    """inventory.count(item_id) + sum of warehouse.count(item_id) across every
    discovered Warehouse -- the single source of truth for "how much of this
    item exists at all", including both home Inventory and remote Warehouses."""
    total = 0
    inventory = components.component("inventory")
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


# Smelter recipes as {ore: product} (docs/database/recipes_smelter.md). An ore
# and its product are "partners": a Smelter takes the one and sends the other
# at the same time, and a Warehouse handles one material operation at a time,
# so the two in one Warehouse answer each other's transfers with "busy".
# best_unload_target() keeps them in separate Warehouses where it can.
SMELT_PARTNERS = {
    "iron_ore": "iron_ingot",
    "silicon": "glass",
    "titanium": "titanium_ingot",
    "cobalt": "cobalt_ingot",
    "lead_ore": "lead_ingot",
    "rare_earth": "rare_earth_core",
    "neutronium": "neutronium_bar",
}
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


def recipe_partners(item_id):
    """Items that should not share a Warehouse with item_id (empty set if none)."""
    return _partners.get(item_id, set())


def item_heat(item_id):
    """Assumed transfer volume of item_id (ORE_HEAT_ORDER), 0 when not listed."""
    return _heat.get(item_id, 0)


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


def _inventory_first(item_id, min_amount, outpost: "OutpostRef | None"):
    """True when item_id must stay in Inventory, Inventory has room for
    min_amount, and no active Supply Dock order at outpost owes it."""
    if not must_stay_in_inventory(item_id):
        return False
    inventory = components.component("inventory")
    if not inventory or not hasattr(inventory, "space_for"):
        return False
    try:
        if inventory.space_for(item_id) < min_amount:
            return False
    except Exception as error:
        swallowed("storage._inventory_first: inventory.space_for", error)
        return False
    return item_id not in _items_demanded_by_active_dock_orders(outpost)


def best_unload_target(item_id, min_amount=1, outpost: "OutpostRef | None" = None, exclude=()):
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
    then, for an item with heat, the Warehouse whose other contents are
    coldest, then least full. One Warehouse, or no partner-free one with room,
    gives the same pick as plain consolidation. Least-full alone would
    spread one item across every Warehouse one partial stack at a time.
    A Storage Bin (BinStore) has one slot, room only while empty or latched
    to item_id. A bin latched to item_id ranks like a Warehouse holder, but
    opening an empty bin ranks after every Warehouse with room: bins are
    the early, slot-tight stage, so a partner clash (Auto Feeder waits) is
    cheaper than locking a whole bin to one item.

    Only falls back to the literal "inventory" id when `outpost` resolves to the
    home outpost -- "inventory" only exists/connects there. Found live: a remote
    machine (e.g. a coastal Bio Luminizer) whose local Warehouses were all full
    would get handed "inventory" as the fallback and try to .connect() its own
    output port to it -- a non-local target from a Warehouse-only outpost. Returns
    None instead so callers can skip the stack (leave it staged) rather than
    attempt a connection that can't work.

    At home, an item that must stay in Inventory (must_stay_in_inventory())
    goes straight to "inventory" while it has room for min_amount, so a
    hauled-in kit or module doesn't wait in a Warehouse for
    reclaim_inventory_only_items_from_warehouses(). Items an active Supply
    Dock order owes keep the Warehouse routing, as in that sweep.

    exclude: Warehouse ids to skip (ones that already answered "busy" to a
    send), so a caller can ask for the next-best target. A non-empty exclude
    never opens an empty Storage Bin: a busy bin frees up after one feeder
    transfer, a bin locked to a second copy of the item stays taken.
    """
    log.start(f"best_unload_target({item_id})", level="debug")
    if outpost_is_home(outpost) and not exclude and _inventory_first(item_id, min_amount, outpost):
        log.debug("Inventory-only item with room in Inventory -> 'inventory'")
        log.end()
        return "inventory"
    partners = recipe_partners(item_id)
    heat = item_heat(item_id)
    ranked = []
    for building in discover_storage_buildings(outpost):
        component = building["component"]
        if not component or not hasattr(component, "space_for") or building["id"] in exclude:
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
        clash = sum([heat * item_heat(partner) for partner in held & partners])
        neighbours = sum([item_heat(other) for other in held if other != item_id]) if heat else 0
        opens_bin = new_stack and isinstance(component, BinStore)
        if opens_bin and exclude:
            continue
        ranked.append(((opens_bin, clash, new_stack, neighbours, _fill_fraction(building)), building))

    if not ranked:
        resolved = outpost if outpost is not None else _home_outpost()
        is_home = bool(resolved and getattr(resolved, "is_home", False))
        fallback = "inventory" if is_home and not exclude else None
        log.debug(f"no Warehouse or Storage Bin has space_for >= {min_amount}, falling back to {fallback!r} (is_home={is_home})")
        log.end()
        return fallback

    ranked.sort(key=lambda pair: pair[0])
    key, winner = ranked[0]
    log.debug(f"picked '{winner['id']}' of {len(ranked)}: {'new stack' if key[2] else 'consolidate'}, clash={key[1]}, neighbour heat={key[3]}, fill={key[4]:.2f}")
    log.end()
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


def mark_busy(source_id, tick=None):
    """Remembers that source_id answered "busy" (see TAKE_BUSY_COOLDOWN_TICKS)."""
    _recent_busy[source_id] = now_tick() if tick is None else tick


def recently_busy(source_id, now=None):
    """True if source_id answered "busy" within TAKE_BUSY_COOLDOWN_TICKS."""
    busy_tick = _recent_busy.get(source_id)
    now = now_tick() if now is None else now
    return busy_tick is not None and now > 0 and now - busy_tick <= TAKE_BUSY_COOLDOWN_TICKS


# Crop Automators (home Harvesting field) keep their Forage
# in their output instead of draining it to Warehouses, so Forage consumers
# take it from there (lib/crop_automator.py). Forage in Inventory or a
# Warehouse drains first: it only takes slots there. Among the automators,
# clogged ones go first (a full output pauses harvests; the automator queues
# one only while the output has room for it), and diversity-garden ones
# before the fill: the garden carries the field's variety bonus.
CROP_AUTOMATOR_TYPE_ID = "crop_automator"
CROP_AUTOMATOR_ITEM_ID = "forage"
CROP_AUTOMATOR_OUTPUT_CAP = 50000     # output buffer (docs/components/crop_automator.md)
CROP_AUTOMATOR_CLOG_FRACTION = 0.9    # at/above this fill (or status "output_full") it counts as clogged
CROP_AUTOMATOR_STATUS_KEY = "plant.automators"  # lib/crop_automator.py telemetry; "garden", "harvest_yield" read here
CROP_AUTOMATOR_WAKE_FREE_MIN = 1000   # a pull wakes a parked automator only if it leaves at least this much room (or its harvest_yield, if larger)


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
    resolved = outpost if outpost is not None else _home_outpost()
    if resolved is None or not hasattr(resolved, "harvesting_machines"):
        return []
    try:
        refs = list(resolved.harvesting_machines(CROP_AUTOMATOR_TYPE_ID) or [])
    except Exception as error:
        swallowed("storage.crop_automator_forage: resolved.harvesting_machines", error)
        return []
    telemetry = archive.get(CROP_AUTOMATOR_STATUS_KEY)
    telemetry = telemetry if isinstance(telemetry, dict) else {}
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
        try:
            count = int(sum(s.count for s in port.stacks() if s.id == CROP_AUTOMATOR_ITEM_ID))
        except Exception as error:
            swallowed("storage.crop_automator_forage: port.stacks", error)
            continue
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


# Extra Warehouses drain_port_to_storage() tries for a stack after a "busy" send.
BUSY_TARGET_RETRIES = 3


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
    resolved = outpost if outpost is not None else _home_outpost()
    is_home = outpost is None or bool(resolved and getattr(resolved, "is_home", False))

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


def eject_unneeded(port: "InputSlot", keep, target):
    """Ejects every stack in `port` whose item is not in `keep` to `target`,
    freeing its material slot. Returns ["item:status", ...] for the log."""
    out = []
    try:
        stacks = list(port.stacks())
    except Exception as error:
        swallowed("storage.eject_unneeded: port.stacks", error)
        return out
    for stack in stacks:
        if stack.id in keep or stack.count <= 0:
            continue
        try:
            result = port.eject(target, stack.id, stack.count)
        except Exception as error:
            swallowed("storage.eject_unneeded: port.eject", error)
            continue
        out.append(f"{stack.id}:{getattr(result, 'status', '?')}")
    return out


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


def _send_to_best_target(port: "OutputSlot", item_id, count, outpost: "OutpostRef | None", allow_partial):
    """Sends one stack to best_unload_target(); a Warehouse that answers "busy"
    (a material endpoint lock, e.g. the one a blend was just taken from) is
    skipped and the next-best one tried, up to BUSY_TARGET_RETRIES times.
    Returns units moved; 0 leaves the stack staged."""
    tried = []
    for _ in range(BUSY_TARGET_RETRIES + 1):
        target = best_unload_target(item_id, 1 if allow_partial else count, outpost=outpost, exclude=tried)
        if target is None:
            return 0  # no local storage has room -- leave it staged, try again next cycle
        moved, status, _message = send_stack(port, item_id, count, target)
        if moved > 0 or status != "busy":
            return moved
        mark_busy(target)
        tried.append(target)
        log.debug(f"'{target}' busy for {item_id}, trying the next-best Warehouse")
    return 0


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
    if not port or not hasattr(port, "stacks"):
        return 0

    moved_total = 0
    try:
        stacks = port.stacks()
    except Exception as error:
        swallowed("storage.drain_port_to_storage: port.stacks", error)
        return 0

    for stack in stacks:
        item_id = getattr(stack, "id", None)
        count = getattr(stack, "count", 0)
        if not item_id or count <= 0:
            continue
        if include is not None and not include(item_id):
            continue

        moved_total += _send_to_best_target(port, item_id, count, outpost, allow_partial)

    return moved_total


def drain_port_storage_first(port: "OutputSlot", outpost: "OutpostRef | None" = None, include=None):
    """
    Sends every stack staged in `port` to a local Warehouse
    (drain_port_to_storage()), then whatever no Warehouse took to
    local_port_target() (Inventory at home, the first local Warehouse
    elsewhere). For outputs that should stay out of Inventory unless the
    Warehouses are full (Seed Supply seeds, Feed Maker feed). `include`:
    optional item_id -> bool filter, as in drain_port_to_storage(). Returns
    total units moved.
    """
    moved = drain_port_to_storage(port, outpost=outpost, include=include)
    target = local_port_target(outpost)
    if not target or not port or not hasattr(port, "stacks"):
        return moved
    try:
        stacks = port.stacks()
    except Exception as error:
        swallowed("storage.drain_port_storage_first: port.stacks", error)
        return moved
    for stack in stacks:
        item_id = getattr(stack, "id", None)
        count = getattr(stack, "count", 0)
        if item_id and count > 0 and (include is None or include(item_id)):
            moved += send_stack(port, item_id, count, target)[0]
    return moved


# OutputSlot.send() rejections that mean "Inventory has no room for this"
# (docs/types/storage_and_inventory.md) -- the only cases
# drain_port_inventory_first() falls back to a Warehouse for.
INVENTORY_FULL_STATUSES = ("partial", "target_full", "slots_full")


def drain_port_inventory_first(port: "OutputSlot", outpost: "OutpostRef | None" = None):
    """
    Sends every stack staged in `port` (a Smelter/Fabricator output) to the
    home Inventory, and only when Inventory has no room (INVENTORY_FULL_STATUSES)
    sends the rest of that stack to a local Warehouse via
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
    results = []
    if not port or not hasattr(port, "stacks"):
        return results
    try:
        stacks = port.stacks()
    except Exception as exc:
        swallowed("storage.drain_port_inventory_first: port.stacks", exc)
        return results

    if not outpost_is_home(outpost):
        # No Inventory off-home: straight to a local Warehouse, per stack.
        for stack in stacks:
            item_id = getattr(stack, "id", None)
            if not item_id or getattr(stack, "count", 0) <= 0:
                continue
            moved = drain_port_to_storage(port, outpost=outpost, include=lambda i, wanted=item_id: i == wanted, allow_partial=True)
            results.append((item_id, moved, "warehouse", "ok" if moved > 0 else "target_full", "" if moved > 0 else "no local Warehouse has room"))
        return results

    for stack in stacks:
        item_id = getattr(stack, "id", None)
        count = getattr(stack, "count", 0)
        if not item_id or count <= 0:
            continue
        moved, status, message = send_stack(port, item_id, count, "inventory")
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
    """(units, final) default per-item stock target: WAREHOUSE_SLOT_CAPACITY
    once Warehouses are unlocked (final, safe to seed into the archive), else
    STORAGE_BIN_CAPACITY (not final: callers don't seed it, so the lookup after
    the unlock seeds the Warehouse default)."""
    if warehouses_unlocked():
        return WAREHOUSE_SLOT_CAPACITY, True
    return STORAGE_BIN_CAPACITY, False


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


def _cheapest_warehouse_occupant(exclude_item_id, outpost: "OutpostRef | None" = None):
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
        except Exception as error:
            swallowed("storage._cheapest_warehouse_occupant: component.slots", error)
            continue
        for slot in slots:
            item_id = getattr(slot, "item", None) or getattr(slot, "item_id", None)
            count = getattr(slot, "count", 0)
            if not item_id or count <= 0 or item_id == exclude_item_id:
                continue
            if best is None or count < best[2]:
                best = (building["id"], item_id, count)
    return best


def _warehouse_item_ids(outpost: "OutpostRef | None" = None):
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
        except Exception as error:
            swallowed("storage._warehouse_item_ids: component.slots", error)
            continue
        for slot in slots:
            item_id = getattr(slot, "item", None) or getattr(slot, "item_id", None)
            count = getattr(slot, "count", 0)
            if item_id and count > 0:
                held.add(item_id)
    return held


def _items_demanded_by_active_dock_orders(outpost: "OutpostRef | None" = None):
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


def reclaim_inventory_only_items_from_warehouses(outpost: "OutpostRef | None" = None):
    """
    Reverse of rebalance_inventory_to_warehouses(): sweeps every discovered
    Warehouse for stock in NON_WAREHOUSABLE_CATEGORIES (see
    must_stay_in_inventory) and moves it back to Inventory.

    This exists as a safety net, not a normal code path -- nothing in this
    codebase should ever *place* such an item into a Warehouse to begin with
    (rebalance_inventory_to_warehouses() itself skips them via
    _occupied_stackable_slots_by_item()), so any occurrence here means it
    arrived some other way (e.g. a player manually stashing gear). Left
    behind, it would be stranded with no way to equip a Pioneer/Rover or
    place it as equipment.

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
    log.start("reclaim_inventory_only_items_from_warehouses", level="debug")
    inventory = components.component("inventory")
    if not inventory or not hasattr(inventory, "transfer_to"):
        log.end()
        return

    dock_demanded = _items_demanded_by_active_dock_orders(outpost)

    reclaimed_total = 0
    for building in discover_storage_buildings(outpost):
        component = building["component"]
        if not component or not hasattr(component, "slots") or not hasattr(component, "transfer_to"):
            continue
        try:
            slots = component.slots()
        except Exception as error:
            swallowed("storage.reclaim_inventory_only_items_from_warehouses: component.slots", error)
            continue
        for slot in slots:
            item_id = getattr(slot, "item", None)
            count = getattr(slot, "count", 0)
            if not item_id or count <= 0:
                continue
            if not must_stay_in_inventory(item_id):
                continue
            if item_id in dock_demanded:
                log.debug(f"leaving {count}x {item_id} in Warehouse '{building['id']}' -- an active Supply Dock order still owes it, ships straight from the Warehouse")
                continue
            properties = getattr(slot, "properties", None)
            try:
                res = component.transfer_to("inventory", item_id, int(count), properties=properties, property_match="exact")
            except Exception as error:
                swallowed("storage.reclaim_inventory_only_items_from_warehouses: component.transfer_to", error)
                continue
            moved = getattr(res, "moved", 0) or 0
            if moved > 0:
                reclaimed_total += moved
                log.print(f"[storage] Reclaimed {moved}x {item_id} from Warehouse '{building['id']}' back to Inventory (Inventory-only category).")
            elif getattr(res, "status", None) not in ("no_op",):
                log.debug(f"'{building['id']}' transfer_to('inventory', {item_id}) moved 0 units ({getattr(res, 'status', '?')})")
    log.debug(f"reclaimed {reclaimed_total} unit(s) total across every discovered Warehouse")
    log.end()
    return reclaimed_total


def rebalance_inventory_to_warehouses(outpost: "OutpostRef | None" = None):
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
    inventory = components.component("inventory")
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

    log.start(f"[storage] Rebalancing Inventory: {len(bulky_items)} item(s) to move to Warehouses")
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
            except Exception as error:
                swallowed("storage.rebalance_inventory_to_warehouses: component.space_for", error)
                space = 0
            if space <= 0:
                continue
            amount = min(remaining, space)
            try:
                res = inventory.transfer_to(building["id"], item_id, int(amount))
            except Exception as error:
                swallowed("storage.rebalance_inventory_to_warehouses: inventory.transfer_to", error)
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

        # Slots still actually stuck in Inventory right now (not the original
        # slot_count, which may have been reduced by the direct-move loop above).
        # The current value is needed to compute the real slots-freed vs
        # slots-reclaimed trade-off for this swap.
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
        except Exception as error:
            swallowed("storage.rebalance_inventory_to_warehouses: warehouse_component.transfer_to", error)
            continue
        evicted = getattr(evict_res, "moved", 0) or 0
        if evicted <= 0:
            log.level("warn").print(f"[storage] Swap for {item_id} did not go through: evicting {occupant_qty}x {occupant_item} from Warehouse '{warehouse_id}' moved 0 units ({getattr(evict_res, 'status', '?')}).")
            continue
        log.print(f"[storage] Evicted {evicted}x {occupant_item} from Warehouse '{warehouse_id}' back to Inventory to free a slot (frees {slots_freed} vs costs {slots_reclaimed}).")

        try:
            space = warehouse_component.space_for(item_id)
        except Exception as error:
            swallowed("storage.rebalance_inventory_to_warehouses: warehouse_component.space_for", error)
            space = 0
        amount = min(remaining, space)
        if amount <= 0:
            log.level("warn").print(f"[storage] Freed a slot in Warehouse '{warehouse_id}' but it still reports no room for {item_id} -- skipping this cycle.")
            continue
        try:
            res = inventory.transfer_to(warehouse_id, item_id, int(amount))
        except Exception as error:
            swallowed("storage.rebalance_inventory_to_warehouses: inventory.transfer_to #2", error)
            continue
        moved = getattr(res, "moved", 0) or 0
        if moved > 0:
            remaining -= moved
            log.print(f"[storage] Moved {moved}x {item_id} from Inventory to Warehouse '{warehouse_id}' after swap.")
    log.end(f"[storage] Rebalance finished for {len(bulky_items)} item(s)")
