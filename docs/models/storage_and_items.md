# Models: Storage, Slots, Stacks & Item Structures

Granular data models and return types extracted from `__builtins__.pyi`.

## `Bin`

```python
class Bin:
    """Rack.bins"""
    id: Literal["portable_bin", "heavy_portable_bin"]
    capacity: _int
    count: _int
    item_id: _str | None
    stacks: _list[ItemStack]
```

## `Cargo`

```python
class Cargo:
    """self.cargo (vehicles)"""
    def count(self) -> _int:
        """Total units currently carried by the vehicle."""
        ...
    def capacity(self) -> _int:
        """Total units the vehicle can carry in its integrated hold or installed Cargo Racks."""
        ...
    def stacks(self) -> _list[ItemStack]:
        """Snapshot of every property-distinct `ItemStack` in the vehicle's cargo. Use this to distinguish variants that share an item id."""
        ...
    def full(self) -> _bool:
        """`True` when the integrated hold or every installed cargo bin is full. A Pioneer without installed bins is also full."""
        ...
    def racks(self) -> _list[Rack]:
        """List of every Cargo Rack currently mounted. Empty for the Rover."""
        ...
    def compact(self) -> TransferResult[Literal["ok", "already_compact", "research_required", "busy", "source_changed", "target_full"]]:
        """On a Pioneer, consolidate equal item ids into the fewest installed Portable Bins that can hold them. Property-distinct variants remain intact, and the planner preserves the fullest compatible bins to minimize physical movement. Requires **Auto Feeders**, waits for time proportional to the units repositioned, and holds the Pioneer stationary as a material endpoint during that cycle. This does not change which bin `send()` drains first. Fixed result contract: `TransferResult`; branch on `.status` and read `.message`. Payload fields: `.requested` and `.moved`."""
        ...
    def discard(self, rack_index: _int) -> DiscardResult[Literal["ok", "empty", "busy", "invalid_rack"]]:
        """Permanently jettison everything in the whole-number, zero-based `rack_index`. On a Rover, which has no racks, `self.cargo.discard(0)` addresses the integrated hold. An already-empty hold or rack finishes immediately; destroying cargo takes **1 hour** and pauses the script. This is the vehicle cargo destruction API. Fixed result contract: `DiscardResult`; branch on `.status` and read `.message`. Payload fields: `.requested` and `.discarded`."""
        ...
```

## `DockSlot`

```python
class DockSlot:
    """supply_dock.slots()"""
    index: _int
    item_id: _str | None
    count: _int
```

## `DroneCargo`

```python
class DroneCargo:
    """self.cargo (drones)"""
    def count(self) -> _int:
        """Total units across every Cargo Pod plus the Bio Extractor chamber."""
        ...
    def capacity(self) -> _int:
        """Total physical capacity summed over every container: each mounted Cargo Pod (Small **100**, Medium **250**, Large **500**) plus the Bio Extractor's **25 t** chamber. Shield Plating halves each pod's capacity."""
        ...
    def contents(self) -> _dict[_str, _int]:
        """A dict mapping `item_id` → unit count for every material currently in cargo. Iterate with `.keys()` / `.items()`."""
        ...
    def space_for(self, item_id: _str) -> _int:
        """Free room for this specific material. **Each Cargo Pod holds one material**, so a pod counts only if it is empty or already holds `item_id`; the Bio Extractor's 25 t chamber counts only for life forms. Returns **0** for a material with no empty or matching pod, even while other pods still have room for their own materials."""
        ...
    def full(self) -> _bool:
        """`True` when `count() >= capacity()`. A drone may still be unable to load a new item type when every pod is committed, even if `full()` is `False`; use `space_for(item_id)` for a specific item."""
        ...
    def load(self, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "invalid_properties", "invalid_property_match", "research_required", "target_moving", "not_at_source", "source_empty", "target_full", "needs_plating", "cask_missing", "source_changed", "target_changed"]]:
        """Move up to whole-number `count` units into this drone's cargo, retaining exact properties. Loads from the docked Drone Depot stockpile or a field Mining Drill after the drone finishes its route there. Hot cargo loads from a local Lead Cask and requires Shield Plating. Fixed result contract: `TransferResult`; branch on `.status` and read `.message`. Payload fields: `.requested` and `.moved`."""
        ...
    def unload(self, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "invalid_properties", "invalid_property_match", "research_required", "not_at_target", "source_empty", "slots_full", "target_full", "cask_missing", "source_changed", "target_changed"]]:
        """Move up to whole-number `count` units from this drone's cargo into its docked Drone Depot, retaining exact properties. Hot cargo unloads into a compatible Lead Cask. Fixed result contract: `TransferResult`; branch on `.status` and read `.message`. Payload fields: `.requested` and `.moved`."""
        ...
    def discard(self, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> DiscardResult[Literal["ok", "partial", "empty", "no_op", "invalid_properties", "invalid_property_match", "source_changed"]]:
        """Permanently destroy up to whole-number `count` units from this drone's cargo. This jettison needs no station and a drained pod unlatches for a new material. Fixed result contract: `DiscardResult`; branch on `.status` and read `.message`. Payload fields: `.requested` and `.discarded`."""
        ...
```

## `DroneOilTank`

```python
class DroneOilTank:
    """self.oil_tank (heli drones)"""
    def level(self) -> _float:
        """Current oil in tons across mounted Oil Tanks. Raises `ReferenceError` when this drone does not have a heli powertrain."""
        ...
    def capacity(self) -> _float:
        """Total oil capacity in tons. Raises `ReferenceError` when this drone does not have a heli powertrain."""
        ...
    def percent(self) -> _float:
        """Oil as a fraction **0-1**. Raises `ReferenceError` when this drone does not have a heli powertrain."""
        ...
```

## `GasTank`

```python
class GasTank(Component):
    """Gas Tank: A passive buffer that latches onto the first gas piped in (steam, ammonia, swamp gas) and holds only that until it drains. Sitting between a source and its consumer, it smooths out the gaps in supply."""
    name: _str
    outpost: OutpostRef
    def fluid(self) -> Literal["", "steam", "ammonia", "swamp_gas", "raw_sulfur_gas", "sulfur_gas", "raw_chlorine", "chlorine"]:
        """The latched gas id (e.g. `\"steam\"`, `\"ammonia\"`), or `\"\"` while empty. The tank commits to the first gas it receives and holds only that until it drains to **0**, then re-latches."""
        ...
    def level(self) -> _float:
        """Current gas stored in tons, from **0** to `capacity()`. Read each iteration to gauge the buffer, near **0** means downstream is about to starve; near `capacity()` means upstream is backpressured. At **0** the tank unlatches and can accept a different gas next."""
        ...
    def capacity(self) -> _float:
        """Maximum tons of gas this tank holds, queryable rather than hardcoded so tank tuning doesn't break scripts. Use with `level()` for a fill-percent indicator, or directly via `fill_pct()`."""
        ...
    def fill_pct(self) -> _float:
        """Fill fraction (**0.0-1.0**), shortcut for `level() / capacity()`. Use for threshold checks: `if self.fill_pct() < 0.2: # boost throttle upstream`."""
        ...
    def inflow_rate(self) -> _float:
        """Gas arriving in t/h. **0** means no upstream flow, for example a dormant source, unavailable relationship, incomplete remote route, or full tank. Compare to `outflow_rate()` to see if the tank is filling or draining."""
        ...
    def outflow_rate(self) -> _float:
        """Gas leaving in t/h. **0** means downstream consumer is saturated or the pipe is disconnected."""
        ...
    def is_full(self) -> _bool:
        """`True` when `level() == capacity()`, upstream backpressure is kicking in, and a Cap may start venting to atmosphere. Check it to detect when connected destinations cannot absorb current production."""
        ...
    def is_empty(self) -> _bool:
        """`True` when `level() == 0`; the tank is unlatched and nothing can be sent downstream. If the source is still active while the tank remains empty, inspect the source and its pipe connection."""
        ...
    gas_in: FluidPort
    gas_out: FluidPort
    steam_in: FluidPort
    steam_out: FluidPort
    ammonia_in: FluidPort
    ammonia_out: FluidPort
    swamp_gas_in: FluidPort
    swamp_gas_out: FluidPort
    raw_sulfur_gas_in: FluidPort
    raw_sulfur_gas_out: FluidPort
    sulfur_gas_in: FluidPort
    sulfur_gas_out: FluidPort
    raw_chlorine_in: FluidPort
    raw_chlorine_out: FluidPort
    chlorine_in: FluidPort
    chlorine_out: FluidPort
```

## `InputSlot`

```python
class InputSlot:
    """self.input on stationary machines with an input buffer"""
    def connect(self, name: _str) -> ActionResult[Literal["ok", "not_found", "not_local", "same_endpoint", "unsupported_source", "source_is_vehicle"]]:
        """Set a compatible item source by stable id or display name. Two stationary endpoints must share an outpost. A Rover or Pioneer is reachable from any outpost, but only while it is parked inside this machine's service area. Field-extractor pickup outputs can be pulled only by a Rover or Pioneer. A drone's cargo moves through its Drone Depot. `\"inventory\"` is a freight source only while the endpoint is at Nocturna Base; remote stationary ports use local Storage Bins, Warehouses, or machine buffers. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
        ...
    def disconnect(self) -> ActionResult[Literal["ok"]]:
        """Clear the current source connection. Does not move or discard buffered items; use `eject(...)` to recover them or `flush()` to destroy them. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
        ...
    def connected_to(self) -> _str:
        """Display name of the currently connected source, or empty string."""
        ...
    def connected_id(self) -> _str:
        """Stable id of the currently connected source, or empty string. `connect()` accepts an id or a display name, so compare against this when you need the identity to match what you passed: `connected_to()` answers with the renameable name."""
        ...
    def take(self, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "research_required", "busy", "invalid_properties", "invalid_property_match", "no_connection", "inventory_not_local", "same_endpoint", "source_missing", "source_under_construction", "source_is_vehicle", "source_not_local", "not_at_source", "unsupported_source", "source_wrong_material", "source_empty", "source_reserved", "source_changed", "buffer_full", "slots_full", "target_wrong_material", "wrong_biome", "target_unconfigured", "hot_cargo_requires_cask", "order_item_not_required", "order_slots_full", "order_fulfilled", "target_full", "target_complete", "target_changed", "same_vehicle", "source_moving", "target_moving", "out_of_range"]]:
        """Take up to whole-number `count` units of `item_id` from the connected source. A property dict selects stacks containing that subset by default. Pass `\"exact\"` as the fourth argument for one full identity; `None, \"exact\"` selects only propertyless items. `\"any\"` ignores properties. Exact source properties are always retained. The transfer waits automatically for time proportional to units moved and requires Auto Feeders research. Fixed result contract: `TransferResult`; branch on `.status` and read `.message`. Payload fields: `.requested` and `.moved`."""
        ...
    def eject(self, destination: _str, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "research_required", "busy", "invalid_properties", "invalid_property_match", "inventory_not_local", "same_endpoint", "source_under_construction", "source_wrong_material", "source_empty", "source_reserved", "source_changed", "target_missing", "target_under_construction", "target_is_vehicle", "target_not_local", "unsupported_target", "target_wrong_material", "wrong_biome", "target_unconfigured", "hot_cargo_requires_cask", "cask_accepts_hot_only", "order_item_not_required", "order_slots_full", "order_fulfilled", "slots_full", "target_full", "target_complete", "target_changed"]]:
        """Recover up to whole-number `count` units of `item_id` from this buffer without changing its source connection. Use `\"inventory\"` at Nocturna Base, or a compatible same-outpost store, machine input, or parked ground vehicle. Optional properties use the standard any, subset, or exact selection rules; exact item properties are preserved. Destination capacity may limit the move. Active or reserved work rejects without moving anything; a successful ejection cancels fractional work attached to the staged input. The transfer waits automatically for time proportional to units moved and requires Auto Feeders research. Fixed result contract: `TransferResult`; branch on `.status` and read `.message`. Payload fields: `.requested` and `.moved`."""
        ...
    def flush(self) -> TransferResult[Literal["ok", "no_op"]]:
        """Permanently discard everything currently buffered in this input port. Flushed items are not returned to inventory. On processing machines, flushing also cancels any in-progress craft. Fixed result contract: `TransferResult`; branch on `.status` and read `.message`. Payload fields: `.requested` and `.moved`."""
        ...
    def count(self) -> _int:
        """Total units currently in this port's buffer."""
        ...
    def capacity(self) -> _int:
        """Maximum units this port's buffer can hold."""
        ...
    def stacks(self) -> _list[ItemStack]:
        """Snapshot list of property-distinct `ItemStack` values currently buffered. Two entries may have the same id when their properties differ."""
        ...
```

## `Inventory`

```python
class Inventory(Component):
    """Inventory: Inventory is the physical storeroom at **Nocturna Base**. Its page and read-only script methods are visible planet-wide, but ordinary freight to machines or vehicles reaches it only at the home outpost; remote sites use local storage and vehicles. Purchases land here.

    Deploy, undeploy, decommission, upgrade, and empty-rig hardware controls are explicit commissioning or service orders, not freight routes. Manual Biology uses Inventory at home and a selected same-outpost Warehouse elsewhere; Habitat reagents are staged locally.
    """
    name: _str
    def stacks(self) -> _list[ItemStack]:
        """Lists every occupied item stack as an `ItemStack` with `.id`, `.count`, and exact `.properties`. Items with the same id but different properties appear separately. Storage Bins and Warehouses use the same format, so routing scripts can inspect all three in one way and pass exact properties to transfer methods."""
        ...
    def get_slots(self) -> _list[Slot]:
        """Lists every current Inventory slot. Inventory starts with **36** slots, and Cargo Expansion can increase it to **60**. Stackable items hold **10** units per slot, or **20** after **Bigger Stacks**. Each `Slot` has a zero-based index from `0` through `get_size() - 1`, plus its item id, name, value, count, and properties. Properties are an exact identity dict, or `None` for ordinary items. Use them to distinguish variants with the same id and to select an exact item during transfers."""
        ...
    def count(self, item_id: _str) -> _int:
        """How many units of `item_id` are currently stored across all slots. Returns **0** if no slot holds that item. Storage Bins, Warehouses, and Lead Casks expose the same `count(item_id)` query, so one helper can search every store."""
        ...
    def has_space(self, item_id: _str | None = ..., properties: ItemProperties | None = ...) -> _bool:
        """Check whether Inventory has room. With no argument, `has_space()` is `True` when any slot is free. Passing an item id and properties checks that exact variant: a partial stack counts only when both match, while an empty slot accepts it. Pass `slot.properties` when checking an item with properties."""
        ...
    def space_for(self, item_id: _str, properties: ItemProperties | None = ...) -> _int:
        """How many units of one exact item identity fit **right now**: remaining room in partial stacks with the same id and properties, plus empty slots times the current stack size. **Bigger Stacks** raises that size from **10** to **20** for stackable items. Use `inventory.space_for(slot.id, slot.properties)` for a property-bearing item. Omitting properties checks the ordinary propertyless variant."""
        ...
    def transfer_to(self, target: _str, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "research_required", "busy", "invalid_properties", "invalid_property_match", "target_missing", "unsupported_target", "same_storage", "target_not_local", "source_under_construction", "source_wrong_material", "source_empty", "source_changed", "target_under_construction", "target_wrong_material", "hot_cargo_requires_cask", "cask_accepts_hot_only", "slots_full", "target_full", "target_changed"]]:
        """Requires **Auto Feeders** research. Move up to whole-number `count` units of `item_id` from this storage endpoint to another Storage Bin, Warehouse, Large Warehouse, Lead Cask, or Inventory. Pass a storage building's display name or instance id, or `\"inventory\"`. Inventory participates only at **Nocturna Base**. The call waits for the physical store's feeder cycle to finish, and every participating storage building remains busy during that cycle. Exact item properties are preserved; optional `properties` and `property_match` select a variant. The calling script may run anywhere, but cargo never crosses outpost boundaries through this method. Fixed result contract: `TransferResult`; branch on `.status` and read `.message`. Payload fields: `.requested` and `.moved`."""
        ...
    def drop(self, slot: _int) -> ItemResult[Literal["ok", "empty", "invalid_slot"]]:
        """Remove **1** unit from a specific slot by its zero-based index. Valid indexes run from `0` through `get_size() - 1`, including slots added by Cargo Expansion. Dropped items are deleted, not returned to the world; use `shop.sell(item_id)` if you want credits. Fixed result contract: `ItemResult`; branch on `.status` and read `.message`. Payload fields: `.item_id`."""
        ...
    def drop_all(self, item_id: _str) -> CountResult[Literal["ok", "no_op"]]:
        """Remove every unit of `item_id` from inventory. For credits, use `shop.sell_all(item_id)`. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
        ...
    def get_size(self) -> _int:
        """Current number of Inventory slots. Inventory starts with **36**, and Cargo Expansion can increase it one slot at a time to **60**. Use this value instead of hardcoding a slot count."""
        ...
    def get_used(self) -> _int:
        """Number of occupied slots. `get_used() == get_size()` means inventory is full."""
        ...
```

## `ItemCatalog`

```python
class ItemCatalog(Component):
    """Item Catalog: Looks up static identity metadata for any known item id. Use `get_component(\"item_catalog\")` when a script needs to classify an item without maintaining its own data archive."""
    name: _str
    def lookup(self, item_id: _str) -> ItemInfo | None:
        """Return an `ItemInfo` with `.id`, `.name`, `.category`, `.stackable`, `.biome`, `.rarity`, and `.production_tier`. Categories distinguish `\"mineral\"`, `\"refined\"`, `\"crafted\"`, `\"agriculture\"`, `\"life_form\"`, `\"field_resource\"`, `\"biology_sample\"`, `\"reagent\"`, `\"equipment\"`, `\"module\"`, `\"portable\"`, `\"upgrade_pack\"`, and `\"construction_kit\"`. Production tier is `None` for source items and biome and rarity are `None` when they do not apply. An unknown item id returns `None`."""
        ...
```

## `ItemInfo`

```python
class ItemInfo:
    """item_catalog.lookup(item_id)"""
    id: _str
    name: _str
    category: Literal["mineral", "refined", "crafted", "agriculture", "life_form", "field_resource", "biology_sample", "reagent", "equipment", "module", "portable", "upgrade_pack", "construction_kit"]
    stackable: _bool
    biome: Literal["frozen", "coastal", "geothermal", "volcanic", "deep"] | None
    rarity: Literal["common", "uncommon", "rare", "legendary"] | None
    production_tier: _int | None
```

## `ItemStack`

```python
class ItemStack:
    """InputSlot.stacks(), VehicleInputSlot.stacks(), OutputSlot.stacks(), PickupOutputSlot.stacks(), Cargo.stacks(), Bin.stacks, storage_bin.stacks(), warehouse.stacks()"""
    id: _str
    count: _int
    properties: ItemProperties | None
```

## `LargeWarehouse`

```python
class LargeWarehouse(Component):
    """Large Warehouse: High-bay multi-material depot, 15 material-locked slots, 2,000 each (30,000 total). Broad enough to stage a full biological catalogue."""
    name: _str
    outpost: OutpostRef
    def count(self, item_id: _str) -> _int:
        """Units of `item_id` held across every slot. Returns **0** if no slot holds it. Inventory, Storage Bins, and Lead Casks expose the same query. `wh.count(\"iron_ore\")`."""
        ...
    def total(self) -> _int:
        """Total units across all slots (every material combined). For one material use `count(item_id)`."""
        ...
    def capacity(self) -> _int:
        """Total capacity across all physical slots. A Warehouse returns **10,000** (**5** × **2,000**); a Large Warehouse returns **30,000** (**15** × **2,000**). Query this value instead of hardcoding a tier."""
        ...
    def fill_percent(self) -> _float:
        """Fraction full across the whole warehouse, `total() / capacity()`, in the range **0-1**."""
        ...
    def is_empty(self) -> _bool:
        """`True` if every slot is empty."""
        ...
    def materials(self) -> _list[_str]:
        """List of item ids currently stored (one entry per material with units in a slot). Iterate it: `for m in wh.materials():`."""
        ...
    def stacks(self) -> _list[ItemStack]:
        """Lists the item variants stored across all physical slots as `ItemStack` values. Items with the same id but different properties occupy separate slots. Call it again when you need current contents."""
        ...
    def space_for(self, item_id: _str, properties: ItemProperties | None = ...) -> _int:
        """How many more units of one exact item variant fit **right now**, using room in matching-identity slots plus every empty slot. Omit `properties` for ordinary propertyless items, or pass the full `.properties` dict returned by `stacks()`. This never counts room belonging to a different property variant."""
        ...
    def has_space(self, item_id: _str, amount: _int, properties: ItemProperties | None = ...) -> _bool:
        """`True` if at least whole-number `amount` more units of that exact item variant fit. Omit `properties` for propertyless items or pass the full property dict. Use before a transfer to avoid partial moves."""
        ...
    def slots(self) -> _list[WarehouseSlot]:
        """Every physical slot as a `WarehouseSlot` record with `.index`, `.item`, `.count`, `.capacity`, and `.properties`. Property-distinct variants use distinct slots."""
        ...
    def compact(self) -> TransferResult[Literal["ok", "already_compact", "research_required", "busy", "source_under_construction", "source_changed", "slots_full", "target_full"]]:
        """Requires **Auto Feeders** research. Consolidate every exact item variant into the fewest Warehouse slots that can hold it. The smallest redundant stacks move into larger compatible stacks, minimizing physical handling; equal item ids with different properties always remain separate. The call waits for time proportional to the units repositioned and locks this Warehouse as a material endpoint for the cycle. Port transfers and manual Biology actions using this Warehouse wait until that cycle finishes. Fixed result contract: `TransferResult`; branch on `.status` and read `.message`. Payload fields: `.requested` and `.moved`."""
        ...
    def transfer_to(self, target: _str, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "research_required", "busy", "invalid_properties", "invalid_property_match", "target_missing", "unsupported_target", "same_storage", "target_not_local", "source_under_construction", "source_wrong_material", "source_empty", "source_changed", "target_under_construction", "target_wrong_material", "hot_cargo_requires_cask", "cask_accepts_hot_only", "slots_full", "target_full", "target_changed"]]:
        """Requires **Auto Feeders** research. Move up to whole-number `count` units of `item_id` from this storage endpoint to another Storage Bin, Warehouse, Large Warehouse, Lead Cask, or Inventory. Pass a storage building's display name or instance id, or `\"inventory\"`. Inventory participates only at **Nocturna Base**. The call waits for the physical store's feeder cycle to finish, and every participating storage building remains busy during that cycle. Exact item properties are preserved; optional `properties` and `property_match` select a variant. The calling script may run anywhere, but cargo never crosses outpost boundaries through this method. Fixed result contract: `TransferResult`; branch on `.status` and read `.message`. Payload fields: `.requested` and `.moved`."""
        ...
```

## `LeadCask`

```python
class LeadCask(Component):
    """Lead Cask: The only safe stationary home for hot radioactive cargo. Drones drop Raw Uranium into it, the Fuel Assembler draws from it and returns finished Fuel Rods, and the Reactor pulls its fuel from it."""
    name: _str
    outpost: OutpostRef
    def count(self, item_id: _str) -> _int:
        """Units of `item_id` currently casked. Returns **0** when the cask is empty or latched to the other hot item. Inventory, Storage Bins, and Warehouses expose the same `count(item_id)` query."""
        ...
    def fill_percent(self) -> _float:
        """Fill fraction **0-1**, watch your strategic reserve."""
        ...
    def capacity(self) -> _int:
        """Maximum hot units (**100**)."""
        ...
    def material(self) -> Literal["", "raw_uranium", "fuel_rod"]:
        """What the cask is latched to, `\"raw_uranium\"`, `\"fuel_rod\"`, or empty. One material per cask, like every stock bin."""
        ...
    def transfer_to(self, target: _str, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "research_required", "busy", "invalid_properties", "invalid_property_match", "target_missing", "unsupported_target", "same_storage", "target_not_local", "source_under_construction", "source_wrong_material", "source_empty", "source_changed", "target_under_construction", "target_wrong_material", "hot_cargo_requires_cask", "cask_accepts_hot_only", "slots_full", "target_full", "target_changed"]]:
        """Requires **Auto Feeders** research. Move up to whole-number `count` units of `item_id` from this storage endpoint to another Storage Bin, Warehouse, Large Warehouse, Lead Cask, or Inventory. Pass a storage building's display name or instance id, or `\"inventory\"`. Inventory participates only at **Nocturna Base**. The call waits for the physical store's feeder cycle to finish, and every participating storage building remains busy during that cycle. Exact item properties are preserved; optional `properties` and `property_match` select a variant. The calling script may run anywhere, but cargo never crosses outpost boundaries through this method. Fixed result contract: `TransferResult`; branch on `.status` and read `.message`. Payload fields: `.requested` and `.moved`."""
        ...
```

## `LiquidTank`

```python
class LiquidTank(Component):
    """Liquid Tank: Passive buffer that holds any one liquid, water, oil, or a biome essence. It commits to the first liquid piped in."""
    name: _str
    outpost: OutpostRef
    def fluid(self) -> Literal["", "water", "oil", "frozen_essence", "coastal_essence", "geothermal_essence", "volcanic_essence", "deep_essence", "brine", "raw_cryofluid", "cryofluid", "raw_quicksilver", "quicksilver"]:
        """The latched liquid id (e.g. `\"water\"`, `\"oil\"`, `\"frozen_essence\"`), or `\"\"` while empty. The tank commits to the first liquid it receives and holds only that until it drains to **0**, then re-latches."""
        ...
    def level(self) -> _float:
        """Current liquid stored in tons, from **0** to `capacity()`. At **0** the tank unlatches and can accept a different liquid next."""
        ...
    def capacity(self) -> _float:
        """Maximum tons this tank holds. Queryable rather than hardcoded. Use with `level()` or `fill_pct()` for threshold checks."""
        ...
    def fill_pct(self) -> _float:
        """Fill fraction (**0.0-1.0**), shortcut for `level() / capacity()`. Common threshold in supply-control scripts."""
        ...
    def inflow_rate(self) -> _float:
        """Liquid arriving in t/h. **0** = no upstream flow."""
        ...
    def outflow_rate(self) -> _float:
        """Liquid leaving in t/h. **0** = no downstream consumer drawing."""
        ...
    def is_full(self) -> _bool:
        """`True` when `level() == capacity()`; upstream source is backpressured."""
        ...
    def is_empty(self) -> _bool:
        """`True` when `level() == 0`; the tank is unlatched and downstream consumers are starved."""
        ...
    liquid_in: FluidPort
    liquid_out: FluidPort
    water_in: FluidPort
    water_out: FluidPort
    oil_in: FluidPort
    oil_out: FluidPort
    frozen_essence_in: FluidPort
    frozen_essence_out: FluidPort
    coastal_essence_in: FluidPort
    coastal_essence_out: FluidPort
    geothermal_essence_in: FluidPort
    geothermal_essence_out: FluidPort
    volcanic_essence_in: FluidPort
    volcanic_essence_out: FluidPort
    deep_essence_in: FluidPort
    deep_essence_out: FluidPort
    brine_in: FluidPort
    brine_out: FluidPort
    raw_cryofluid_in: FluidPort
    raw_cryofluid_out: FluidPort
    cryofluid_in: FluidPort
    cryofluid_out: FluidPort
    raw_quicksilver_in: FluidPort
    raw_quicksilver_out: FluidPort
    quicksilver_in: FluidPort
    quicksilver_out: FluidPort
```

## `MountSlot`

```python
class MountSlot:
    """self.modules() on rover / pioneer"""
    index: _int
    type: Literal["nav", "sonar_basic", "drill_basic", "universal", "thruster", "drone_module"]
    module_id: _str | None
    internal_count: _int
    internal_items: _list[_str | None]
```

## `OutputSlot`

```python
class OutputSlot:
    """self.output (machines with output port)"""
    def connect(self, name: _str) -> ActionResult[Literal["ok", "not_found", "not_local", "same_endpoint", "unsupported_target", "target_is_vehicle"]]:
        """Set a compatible item destination by stable id or display name. Two stationary endpoints must share an outpost. A Rover or Pioneer is reachable from any outpost, but only while it is parked inside this machine's service area. A drone's cargo moves through its Drone Depot. `\"inventory\"` is a freight destination only while the endpoint is at Nocturna Base; remote stationary ports use local Storage Bins, Warehouses, or machine inputs. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
        ...
    def disconnect(self) -> ActionResult[Literal["ok"]]:
        """Clear the current target connection. Does not move or discard buffered output. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
        ...
    def connected_to(self) -> _str:
        """Display name of the currently connected target, or empty string."""
        ...
    def connected_id(self) -> _str:
        """Stable id of the currently connected target, or empty string. `connect()` accepts an id or a display name, so compare against this when you need the identity to match what you passed: `connected_to()` answers with the renameable name."""
        ...
    def send(self, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "research_required", "busy", "invalid_properties", "invalid_property_match", "no_connection", "inventory_not_local", "same_endpoint", "source_wrong_material", "source_empty", "source_changed", "target_missing", "target_under_construction", "target_is_vehicle", "target_not_local", "not_at_target", "unsupported_target", "target_wrong_material", "wrong_biome", "target_unconfigured", "mixed_materials", "hot_cargo_requires_cask", "cask_accepts_hot_only", "order_item_not_required", "order_slots_full", "order_fulfilled", "slots_full", "target_full", "target_complete", "target_changed", "same_vehicle", "source_moving", "target_moving", "out_of_range"]]:
        """Send up to whole-number `count` units of `item_id` to the connected target. A property dict selects stacks containing that subset by default. Pass `\"exact\"` as the fourth argument for one full identity; `None, \"exact\"` selects only propertyless items. `\"any\"` ignores properties. Exact source properties are preserved. The transfer waits automatically for time proportional to units moved and requires Auto Feeders research. Fixed result contract: `TransferResult`; branch on `.status` and read `.message`. Payload fields: `.requested` and `.moved`."""
        ...
    def count(self) -> _int:
        """Total units currently in this port's buffer."""
        ...
    def capacity(self) -> _int:
        """Maximum units this port's buffer can hold."""
        ...
    def stacks(self) -> _list[ItemStack]:
        """Snapshot list of property-distinct `ItemStack` values currently buffered. Use `.properties` to inspect and select variants before `send()`."""
        ...
```

## `PickupOutputSlot`

```python
class PickupOutputSlot:
    """self.output on field Water Pumps and Mining Drills"""
    def count(self) -> _int:
        """Total item units waiting for carrier pickup."""
        ...
    def capacity(self) -> _int:
        """Maximum item units this pickup stockpile can hold."""
        ...
    def stacks(self) -> _list[ItemStack]:
        """Snapshot list of property-distinct `ItemStack` values waiting for carrier pickup."""
        ...
```

## `ShopItem`

```python
class ShopItem:
    """shop.get_catalogue()"""
    id: _str
    name: _str
    cost: _int
```

## `Slot`

```python
class Slot:
    """inventory.get_slots()"""
    slot: _int
    id: _str
    name: _str
    value: _float
    count: _int
    properties: ItemProperties | None
    genes: _list[_str]
    glow: _list[_int] | None
    spliced: _bool
```

## `SteamTurbine`

```python
class SteamTurbine(Component):
    """Steam Turbine: Produces up to 108 W from 90 t/h Steam. Its script-owned throttle scales both consumption and output."""
    name: _str
    outpost: OutpostRef
    def power_output(self) -> _float:
        """Watts fed to the grid on the last power tick. Scales with `throttle()` and the steam actually available. **0** when idle or steam-starved. Updates once per power tick, a fresh `set_throttle(...)` is reflected on the next tick, not the same one. Use for live dashboards or to compare against Oxygen / Heat consumption to balance the power budget."""
        ...
    def efficiency(self) -> _float:
        """Fraction of the throttle's desired steam actually drawn on the last power tick (**0.0-1.0**). **1.0** = the turbine got all the steam its throttle asked for. Below **1** means steam-starved (vent dormant, or upstream can't keep up). Use to detect whether the turbine is being fed enough."""
        ...
    def is_stalled(self) -> _bool:
        """`True` when the throttle is up but no steam is arriving (the vent is dormant or the steam line is disconnected). Check `self.steam_in.level()` (upstream) and the feeding Cap's vent phase to diagnose. There is no water side to back up anymore."""
        ...
    def throttle(self) -> _float:
        """Current throttle setting (**0.0-1.0**). **0** = off, the turbine consumes no steam and produces nothing (the default; idle until `set_throttle()` is called). Higher values draw more steam and produce more power, up to the peak at **1.0**. Read-only view of what `set_throttle()` last committed."""
        ...
    def set_throttle(self, t: _float) -> ActionResult[Literal["ok"]]:
        """Set the turbine throttle (**0.0-1.0**, clamped). **0** switches the turbine off (no steam consumed, no power). **1.0** draws full steam for peak watts. `self.set_throttle(1.0)` runs it flat out; ease down when the steam buffer runs dry so it isn't spinning on empty, e.g. `if self.steam_in.level() < 5: self.set_throttle(0.3)`. This script-owned setpoint resets to **0** when the script stops, ends, or errors. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
        ...
    steam_in: FluidPort
    def peek_command(self) -> ScriptCommand | None:
        """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
        ...
    def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
        """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
        ...
    def command_count(self) -> _int:
        """Return how many commands are waiting in this script's mailbox."""
        ...
    def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
        """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
        ...
```

## `StorageBin`

```python
class StorageBin(Component):
    """Storage Bin: A passive base container that holds one material at a time. The first deposit sets what it stores, and the lock clears only once it drains empty. Other scripts can read and move its contents."""
    name: _str
    outpost: OutpostRef
    def count(self, item_id: _str) -> _int:
        """Units of `item_id` currently stored. Returns **0** when the bin is empty or latched to another item. Inventory, Warehouses, and Lead Casks expose the same `count(item_id)` query."""
        ...
    def get_capacity(self) -> _int:
        """Maximum units the bin holds, **500** by default. Queryable rather than hardcoded so a retune doesn't break scripts. Use `fill_percent()` when you need the current fill ratio."""
        ...
    def get_material(self) -> _str:
        """Currently latched material id, or the empty string if the bin is empty (and therefore accepts any material on the next deposit). Use to check a bin's material before routing transfers: `if bin.get_material() in (\"\", \"iron_ore\"): # safe to deposit iron`."""
        ...
    def stacks(self) -> _list[ItemStack]:
        """Lists the item variants stored in this bin as `ItemStack` values. Items with the same id but different properties remain separate. Call it again when you need current contents."""
        ...
    def is_empty(self) -> _bool:
        """`True` if the bin holds nothing. An empty bin has no material lock, any material can take the slot on the next deposit. Different from `has_space(0)` which is always `True`."""
        ...
    def has_space(self, amount: _int) -> _bool:
        """`True` if the bin has room for whole-number `amount` more units. Use before a transfer to avoid partial moves."""
        ...
    def space(self) -> _int:
        """Free units of capacity remaining. Sizes a transfer in one call: `n = bin.space()`, then move up to `n`."""
        ...
    def fill_percent(self) -> _float:
        """Fraction full in the range **0-1**. Common threshold for rebalance scripts: `if bin.fill_percent() < 0.2: # route more here`."""
        ...
    def transfer_from_inventory(self, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "research_required", "busy", "invalid_properties", "invalid_property_match", "inventory_not_local", "source_empty", "source_changed", "target_wrong_material", "hot_cargo_requires_cask", "target_full", "target_changed"]]:
        """Requires **Auto Feeders** research and a Storage Bin at the home outpost. Move up to whole-number `count` units of `item_id` from Inventory into the bin, preserving exact properties. The call waits for the feeder cycle to finish, and the bin cannot start another transfer during that cycle. A property dict selects a subset by default. Pass `\"exact\"` as `property_match` for a full identity, including `None` for propertyless items. Fixed result contract: `TransferResult`; branch on `.status` and read `.message`. Payload fields: `.requested` and `.moved`."""
        ...
    def transfer_to_inventory(self, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "research_required", "busy", "invalid_properties", "invalid_property_match", "source_empty", "source_changed", "inventory_not_local", "target_full", "target_changed"]]:
        """Requires **Auto Feeders** research and a Storage Bin at the home outpost. Move up to whole-number `count` units back to Inventory, preserving exact properties. The call waits for the feeder cycle to finish, and the bin cannot start another transfer during that cycle. A property dict selects a subset by default. Pass `\"exact\"` as `property_match` for a full identity, including `None` for propertyless items. If the bin drains completely, its item-id latch clears. Fixed result contract: `TransferResult`; branch on `.status` and read `.message`. Payload fields: `.requested` and `.moved`."""
        ...
    def transfer_to(self, target: _str, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "research_required", "busy", "invalid_properties", "invalid_property_match", "target_missing", "unsupported_target", "same_storage", "target_not_local", "source_under_construction", "source_wrong_material", "source_empty", "source_changed", "target_under_construction", "target_wrong_material", "hot_cargo_requires_cask", "cask_accepts_hot_only", "slots_full", "target_full", "target_changed"]]:
        """Requires **Auto Feeders** research. Move up to whole-number `count` units of `item_id` from this storage endpoint to another Storage Bin, Warehouse, Large Warehouse, Lead Cask, or Inventory. Pass a storage building's display name or instance id, or `\"inventory\"`. Inventory participates only at **Nocturna Base**. The call waits for the physical store's feeder cycle to finish, and every participating storage building remains busy during that cycle. Exact item properties are preserved; optional `properties` and `property_match` select a variant. The calling script may run anywhere, but cargo never crosses outpost boundaries through this method. Fixed result contract: `TransferResult`; branch on `.status` and read `.message`. Payload fields: `.requested` and `.moved`."""
        ...
```

## `VehicleInputSlot`

```python
class VehicleInputSlot:
    """self.input on Rover and Pioneer"""
    def connect(self, name: _str) -> ActionResult[Literal["ok", "not_found", "same_endpoint", "unsupported_source", "source_is_vehicle"]]:
        """Set a compatible cargo source by stable id or display name. A Rover or Pioneer must be parked inside a stationary source's service area. Field Mining Drill and Water Pump stockpiles support carrier pickup. Vehicle handoffs require both vehicles to be stopped and nearby. `\"inventory\"` is available only while parked at Nocturna Base; remote outposts use local Storage Bins, Warehouses, or machine buffers. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
        ...
    def disconnect(self) -> ActionResult[Literal["ok"]]:
        """Clear the current cargo source connection. This does not move or discard cargo. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
        ...
    def connected_to(self) -> _str:
        """Display name of the currently connected cargo source, or empty string."""
        ...
    def connected_id(self) -> _str:
        """Stable id of the currently connected cargo source, or empty string. `connect()` accepts an id or display name, so compare against this when identity must survive renaming."""
        ...
    def take(self, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "research_required", "busy", "invalid_properties", "invalid_property_match", "no_connection", "inventory_not_local", "same_endpoint", "source_missing", "source_under_construction", "source_is_vehicle", "source_not_local", "not_at_source", "unsupported_source", "source_wrong_material", "source_empty", "source_reserved", "source_changed", "buffer_full", "slots_full", "target_wrong_material", "wrong_biome", "target_unconfigured", "hot_cargo_requires_cask", "order_item_not_required", "order_slots_full", "order_fulfilled", "target_full", "target_complete", "target_changed", "same_vehicle", "source_moving", "target_moving", "out_of_range"]]:
        """Load up to whole-number `count` units of `item_id` into vehicle cargo from the connected source. A property dict selects stacks containing that subset by default. Pass `\"exact\"` as the fourth argument for one full identity; `None, \"exact\"` selects only propertyless items. `\"any\"` ignores properties. Exact source properties are retained. The transfer waits automatically for time proportional to units moved and requires Auto Feeders research. Fixed result contract: `TransferResult`; branch on `.status` and read `.message`. Payload fields: `.requested` and `.moved`."""
        ...
    def count(self) -> _int:
        """Total units currently carried in the vehicle's cargo."""
        ...
    def capacity(self) -> _int:
        """Maximum units the vehicle's cargo can hold."""
        ...
    def stacks(self) -> _list[ItemStack]:
        """Snapshot list of property-distinct `ItemStack` values currently carried. Two entries may have the same id when their properties differ."""
        ...
```

## `Warehouse`

```python
class Warehouse(Component):
    """Warehouse: Multi-material bulk depot, 5 material-locked slots, 2,000 each (10,000 total). Drone-scale haulage absorption."""
    name: _str
    outpost: OutpostRef
    def count(self, item_id: _str) -> _int:
        """Units of `item_id` held across every slot. Returns **0** if no slot holds it. Inventory, Storage Bins, and Lead Casks expose the same query. `wh.count(\"iron_ore\")`."""
        ...
    def total(self) -> _int:
        """Total units across all slots (every material combined). For one material use `count(item_id)`."""
        ...
    def capacity(self) -> _int:
        """Total capacity across all physical slots. A Warehouse returns **10,000** (**5** × **2,000**); a Large Warehouse returns **30,000** (**15** × **2,000**). Query this value instead of hardcoding a tier."""
        ...
    def fill_percent(self) -> _float:
        """Fraction full across the whole warehouse, `total() / capacity()`, in the range **0-1**."""
        ...
    def is_empty(self) -> _bool:
        """`True` if every slot is empty."""
        ...
    def materials(self) -> _list[_str]:
        """List of item ids currently stored (one entry per material with units in a slot). Iterate it: `for m in wh.materials():`."""
        ...
    def stacks(self) -> _list[ItemStack]:
        """Lists the item variants stored across all physical slots as `ItemStack` values. Items with the same id but different properties occupy separate slots. Call it again when you need current contents."""
        ...
    def space_for(self, item_id: _str, properties: ItemProperties | None = ...) -> _int:
        """How many more units of one exact item variant fit **right now**, using room in matching-identity slots plus every empty slot. Omit `properties` for ordinary propertyless items, or pass the full `.properties` dict returned by `stacks()`. This never counts room belonging to a different property variant."""
        ...
    def has_space(self, item_id: _str, amount: _int, properties: ItemProperties | None = ...) -> _bool:
        """`True` if at least whole-number `amount` more units of that exact item variant fit. Omit `properties` for propertyless items or pass the full property dict. Use before a transfer to avoid partial moves."""
        ...
    def slots(self) -> _list[WarehouseSlot]:
        """Every physical slot as a `WarehouseSlot` record with `.index`, `.item`, `.count`, `.capacity`, and `.properties`. Property-distinct variants use distinct slots."""
        ...
    def compact(self) -> TransferResult[Literal["ok", "already_compact", "research_required", "busy", "source_under_construction", "source_changed", "slots_full", "target_full"]]:
        """Requires **Auto Feeders** research. Consolidate every exact item variant into the fewest Warehouse slots that can hold it. The smallest redundant stacks move into larger compatible stacks, minimizing physical handling; equal item ids with different properties always remain separate. The call waits for time proportional to the units repositioned and locks this Warehouse as a material endpoint for the cycle. Port transfers and manual Biology actions using this Warehouse wait until that cycle finishes. Fixed result contract: `TransferResult`; branch on `.status` and read `.message`. Payload fields: `.requested` and `.moved`."""
        ...
    def transfer_to(self, target: _str, item_id: _str, count: _int, properties: ItemProperties | None = ..., property_match: _str | None = ...) -> TransferResult[Literal["ok", "partial", "no_op", "research_required", "busy", "invalid_properties", "invalid_property_match", "target_missing", "unsupported_target", "same_storage", "target_not_local", "source_under_construction", "source_wrong_material", "source_empty", "source_changed", "target_under_construction", "target_wrong_material", "hot_cargo_requires_cask", "cask_accepts_hot_only", "slots_full", "target_full", "target_changed"]]:
        """Requires **Auto Feeders** research. Move up to whole-number `count` units of `item_id` from this storage endpoint to another Storage Bin, Warehouse, Large Warehouse, Lead Cask, or Inventory. Pass a storage building's display name or instance id, or `\"inventory\"`. Inventory participates only at **Nocturna Base**. The call waits for the physical store's feeder cycle to finish, and every participating storage building remains busy during that cycle. Exact item properties are preserved; optional `properties` and `property_match` select a variant. The calling script may run anywhere, but cargo never crosses outpost boundaries through this method. Fixed result contract: `TransferResult`; branch on `.status` and read `.message`. Payload fields: `.requested` and `.moved`."""
        ...
```

## `WarehouseSlot`

```python
class WarehouseSlot:
    """warehouse.slots()"""
    index: _int
    item: _str
    count: _int
    capacity: _int
    properties: ItemProperties | None
```
