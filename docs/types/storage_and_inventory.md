# Data Types: Storage And Inventory

Complete property specifications, descriptions, units, and return types from the official documentation.

## Index

- [`Battery`](#battery) (STORAGE & INVENTORY)
- [`Holder`](#holder) (STORAGE & INVENTORY)
- [`PortableBattery`](#portablebattery) (STORAGE & INVENTORY)
- [`Cargo`](#cargo) (STORAGE & INVENTORY)
- [`Rack`](#rack) (STORAGE & INVENTORY)
- [`Bin`](#bin) (STORAGE & INVENTORY)
- [`DiscardResult`](#discardresult) (STORAGE & INVENTORY)
- [`InputSlot`](#inputslot) (STORAGE & INVENTORY)
- [`ItemInfo`](#iteminfo) (STORAGE & INVENTORY)
- [`ItemResult`](#itemresult) (STORAGE & INVENTORY)
- [`ItemStack`](#itemstack) (STORAGE & INVENTORY)
- [`OutputSlot`](#outputslot) (STORAGE & INVENTORY)
- [`PickupOutputSlot`](#pickupoutputslot) (STORAGE & INVENTORY)
- [`Recipe`](#recipe) (STORAGE & INVENTORY)
- [`SaleResult`](#saleresult) (STORAGE & INVENTORY)
- [`ShopItem`](#shopitem) (STORAGE & INVENTORY)
- [`Slot`](#slot) (STORAGE & INVENTORY)
- [`TransferResult`](#transferresult) (STORAGE & INVENTORY)
- [`VehicleInputSlot`](#vehicleinputslot) (STORAGE & INVENTORY)
- [`WarehouseSlot`](#warehouseslot) (STORAGE & INVENTORY)

---

## Battery

**Returned by:** self.battery (vehicles)

### Related object types

- `Holder`
- `PortableBattery`

### Methods

##### `.level() → float`

Charge level as a fraction, **0-1**.

- **Returns** `float`

##### `.wh() → float`

Current charge in Wh (across all batteries).

- **Returns** `float`

##### `.capacity() → float`

Maximum capacity in Wh.

- **Returns** `float`

##### `.holders() → list[Holder]`

List of every Battery Holder currently mounted on the vehicle. Empty for the Rover (sealed battery).

- **Returns** `list[Holder]`

*Types / Storage & Inventory*

## Holder

**Returned by:** self.battery.holders()

### Properties

##### `.id: str`

Holder module id, e.g. `"battery_holder_medium"`.

- **Returns** `str`

##### `.size: str`

Holder size: `"small"` / `"medium"` / `"large"`.

- **Returns** `str`
- **Possible values** `"small"`, `"medium"`, `"large"`

##### `.capacity: float`

Rated Wh across every battery in this holder.

- **Returns** `float`

##### `.wh: float`

Current Wh in this holder (pool level × rated capacity).

- **Returns** `float`

##### `.batteries: list[PortableBattery | None]`

List indexed by internal slot: each entry is a `PortableBattery` object, or `None` for an empty slot.

- **Returns** `list[PortableBattery | None]`

*Types / Storage & Inventory*

## PortableBattery

**Returned by:** self.battery.holders()[...].batteries[...]

### Properties

##### `.id: str`

Portable battery item id: `"portable_battery"` or `"heavy_portable_battery"`.

- **Returns** `str`
- **Possible values** `"portable_battery"`, `"heavy_portable_battery"`

### Methods

##### `.level() → float`

Charge level as a fraction, **0-1**.

- **Returns** `float`

##### `.wh() → float`

Current charge in Wh.

- **Returns** `float`

##### `.capacity() → float`

Rated capacity in Wh.

- **Returns** `float`

*Types / Storage & Inventory*

## Cargo

**Returned by:** self.cargo (vehicles)

### Related object types

- `Rack`

### Methods

##### `.count() → int`

Total units currently carried by the vehicle.

- **Returns** `int`

##### `.capacity() → int`

Total units the vehicle can carry in its integrated hold or installed Cargo Racks.

- **Returns** `int`

##### `.stacks() → list[ItemStack]`

Snapshot of every property-distinct `ItemStack` in the vehicle's cargo. Use this to distinguish variants that share an item id.

- **Returns** `list[ItemStack]`

##### `.full() → bool`

`True` when the integrated hold or every installed cargo bin is full. A Pioneer without installed bins is also full.

- **Returns** `bool`

##### `.racks() → list[Rack]`

List of every Cargo Rack currently mounted. Empty for the Rover.

- **Returns** `list[Rack]`

##### `.compact() → TransferResult`

On a Pioneer, consolidate equal item ids into the fewest installed Portable Bins that can hold them. Property-distinct variants remain intact, and the planner preserves the fullest compatible bins to minimize physical movement. Requires **Auto Feeders**, waits for time proportional to the units repositioned, and holds the Pioneer stationary as a material endpoint during that cycle. This does not change which bin `send()` drains first.

- **Returns** `TransferResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.requested`, `.moved`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Repositioned `.moved` units into fewer Pioneer Portable Bins. |
| `"already_compact"` | success | This cargo is already compact; no Portable Bin cargo needs to move. |
| `"research_required"` | rejection | The required material-transfer research is not unlocked. |
| `"busy"` | transient | This material endpoint is already handling another material operation. |
| `"source_changed"` | transient | The source changed between transfer planning and commit. |
| `"target_full"` | rejection | The destination has no capacity for matching units. |

##### `.discard(rack_index: int) → DiscardResult`

Permanently jettison everything in the whole-number, zero-based `rack_index`. On a Rover, which has no racks, `self.cargo.discard(0)` addresses the integrated hold. An already-empty hold or rack finishes immediately; destroying cargo takes **1 hour** and pauses the script. This is the vehicle cargo destruction API.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `rack_index` | `int` | Whole-number zero-based index among mounted Cargo Racks (0 = the integrated hold on a Rover) |

- **Returns** `DiscardResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.requested`, `.discarded`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Permanently discarded `.discarded` units. |
| `"empty"` | success | The selected cargo area was already empty. |
| `"busy"` | transient | The vehicle is occupied by another field action. |
| `"invalid_rack"` | rejection | The requested cargo rack does not exist. |

*Types / Storage & Inventory*

## Rack

**Returned by:** self.cargo.racks()

### Related object types

- `Bin`

### Properties

##### `.id: str`

Rack module id, e.g. `"cargo_rack_medium"`.

- **Returns** `str`

##### `.size: str`

Rack size: `"small"` / `"medium"` / `"large"`.

- **Returns** `str`
- **Possible values** `"small"`, `"medium"`, `"large"`

##### `.bins: list[Bin | None]`

List indexed by internal slot: each entry is a `Bin` object, or `None` for an empty slot.

- **Returns** `list[Bin | None]`

*Types / Storage & Inventory*

## Bin

**Returned by:** Rack.bins

### Properties

##### `.id: str`

Portable bin item id: `"portable_bin"` or `"heavy_portable_bin"`.

- **Returns** `str`
- **Possible values** `"portable_bin"`, `"heavy_portable_bin"`

##### `.capacity: int`

Rated units: **25** basic, **50** heavy.

- **Returns** `int`

##### `.count: int`

Current units stored.

- **Returns** `int`

##### `.item_id: str | None`

Assigned item id (mineral, ingot, component: anything the bin holds), or `None` if the bin is empty/unassigned.

- **Returns** `str | None`

##### `.stacks: list[ItemStack]`

Property-distinct `ItemStack` snapshots in this portable bin. Equal ids with different properties remain separate entries.

- **Returns** `list[ItemStack]`

*Types / Storage & Inventory*

## DiscardResult

**Returned by:** Cargo.discard(), DroneCargo.discard()

### Properties

##### `.status: str`

Stable discard outcome code.

- **Returns** `str`
- **Possible values** `"ok"`, `"partial"`, `"empty"`, `"busy"`, `"invalid_rack"`, `"no_op"`, `"invalid_properties"`, `"invalid_property_match"`, `"source_changed"`

##### `.message: str`

Player-readable explanation of the discard outcome.

- **Returns** `str`

##### `.requested: int`

Whole-number units requested or observed for destruction.

- **Returns** `int`

##### `.discarded: int`

Whole-number units permanently destroyed.

- **Returns** `int`

*Types / Storage & Inventory*

## InputSlot

**Returned by:** self.input on stationary machines with an input buffer

### Methods

##### `.connect(name: str) → ActionResult`

Set a compatible item source by stable id or display name. Two stationary endpoints must share an outpost. A Rover or Pioneer is reachable from any outpost, but only while it is parked inside this machine's service area. Field-extractor pickup outputs can be pulled only by a Rover or Pioneer. A drone's cargo moves through its Drone Depot. `"inventory"` is a freight source only while the endpoint is at Nocturna Base; remote stationary ports use local Storage Bins, Warehouses, or machine buffers.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `name` | `str` | Stable id or display name of a compatible item source, or inventory |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_found"` | rejection | The requested object, target, or record does not exist. |
| `"not_local"` | rejection | The requested endpoint belongs to another outpost. |
| `"same_endpoint"` | rejection | The requested item source and destination are the same endpoint. |
| `"unsupported_source"` | rejection | The selected component does not expose a compatible item source. |
| `"source_is_vehicle"` | rejection | The requested source is a drone. Drone cargo moves through its Drone Depot. |

##### `.disconnect() → ActionResult`

Clear the current source connection. Does not move or discard buffered items; use `eject(...)` to recover them or `flush()` to destroy them.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.connected_to() → str`

Display name of the currently connected source, or empty string.

- **Returns** `str`

##### `.connected_id() → str`

Stable id of the currently connected source, or empty string. `connect()` accepts an id or a display name, so compare against this when you need the identity to match what you passed: `connected_to()` answers with the renameable name.

- **Returns** `str`

##### `.take(item_id: str, count: int, properties: ItemProperties | None = None, property_match: str | None = None) → TransferResult`

Take up to whole-number `count` units of `item_id` from the connected source. A property dict selects stacks containing that subset by default. Pass `"exact"` as the fourth argument for one full identity; `None, "exact"` selects only propertyless items. `"any"` ignores properties. Exact source properties are always retained. The transfer waits automatically for time proportional to units moved and requires Auto Feeders research.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `str` | Item id to take |
| `count` | `int` | Whole-number max units to take |
| `properties` | `ItemProperties \| None` | Optional property dict, matched as a subset by default. Omitted or `None` matches any properties; use `None` with `property_match="exact"` to select propertyless items only. |
| `property_match` | `str \| None` | Optional selection mode: any, subset, or exact |

- **Returns** `TransferResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.requested`, `.moved`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Moved all `.moved` requested units. |
| `"partial"` | partial | Moved `.moved` of `.requested` requested units; source availability or destination capacity limited the transfer. |
| `"no_op"` | success | No units were requested, so no state changed. |
| `"research_required"` | rejection | The required material-transfer research is not unlocked. |
| `"busy"` | transient | This material endpoint is already handling another material operation. |
| `"invalid_properties"` | rejection | The item property selector has an invalid shape or value. |
| `"invalid_property_match"` | rejection | The requested property matching mode is invalid. |
| `"no_connection"` | rejection | The port has no configured transfer endpoint. |
| `"inventory_not_local"` | rejection | This endpoint cannot access the home freight Inventory from its current outpost. |
| `"same_endpoint"` | rejection | The configured source and destination are the same item endpoint. |
| `"source_missing"` | rejection | The configured source no longer exists. |
| `"source_under_construction"` | transient | The configured source is still under construction. |
| `"source_is_vehicle"` | rejection | The mobile source is a drone, or is a ground vehicle that is not docked in this endpoint's service area. |
| `"source_not_local"` | rejection | The configured source belongs to another outpost. |
| `"not_at_source"` | rejection | The vehicle is outside the source's service area. |
| `"unsupported_source"` | rejection | The configured source does not expose compatible cargo. |
| `"source_wrong_material"` | rejection | The source contains a different material from the one requested. |
| `"source_empty"` | rejection | The source has no matching units available. |
| `"source_reserved"` | rejection | The source is reserving its cargo for an active operation. |
| `"source_changed"` | transient | The source changed between transfer planning and commit. |
| `"buffer_full"` | rejection | The receiving input buffer is full. |
| `"slots_full"` | rejection | The destination has capacity but no slot for this material identity. |
| `"target_wrong_material"` | rejection | The destination is latched to or accepts a different material. |
| `"wrong_biome"` | rejection | The destination rejects this biological material because its biome is incompatible. |
| `"target_unconfigured"` | rejection | The destination lacks the world-state configuration required to accept this material. |
| `"hot_cargo_requires_cask"` | rejection | This hot cargo must move through a compatible Lead Cask. |
| `"order_item_not_required"` | rejection | The active order does not require this item. |
| `"order_slots_full"` | rejection | Every Supply Dock material slot is assigned to another required item. |
| `"order_fulfilled"` | rejection | The active order already has all required units of this item loaded or shipped. |
| `"target_full"` | rejection | The destination has no capacity for matching units. |
| `"target_complete"` | rejection | The destination has completed its work and no longer accepts materials. |
| `"target_changed"` | transient | The destination changed between transfer planning and commit. |
| `"same_vehicle"` | rejection | A vehicle cannot transfer cargo to itself. |
| `"source_moving"` | transient | The source vehicle must stop before cargo can be handed off. |
| `"target_moving"` | transient | The destination vehicle must stop before cargo can be handed off. |
| `"out_of_range"` | rejection | The vehicles are outside cargo handoff range. |

##### `.eject(destination: str, item_id: str, count: int, properties: ItemProperties | None = None, property_match: str | None = None) → TransferResult`

Recover up to whole-number `count` units of `item_id` from this buffer without changing its source connection. Use `"inventory"` at Nocturna Base, or a compatible same-outpost store, machine input, or parked ground vehicle. Optional properties use the standard any, subset, or exact selection rules; exact item properties are preserved. Destination capacity may limit the move. Active or reserved work rejects without moving anything; a successful ejection cancels fractional work attached to the staged input. The transfer waits automatically for time proportional to units moved and requires Auto Feeders research.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `destination` | `str` | Stable id or display name of a local compatible freight destination, or inventory |
| `item_id` | `str` | Item id to recover |
| `count` | `int` | Whole-number max units to recover |
| `properties` | `ItemProperties \| None` | Optional property dict, matched as a subset by default. Omitted or `None` matches any properties; use `None` with `property_match="exact"` to select propertyless items only. |
| `property_match` | `str \| None` | Optional selection mode: any, subset, or exact |

- **Returns** `TransferResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.requested`, `.moved`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Moved all `.moved` requested units. |
| `"partial"` | partial | Moved `.moved` of `.requested` requested units; source availability or destination capacity limited the transfer. |
| `"no_op"` | success | No units were requested, so no state changed. |
| `"research_required"` | rejection | The required material-transfer research is not unlocked. |
| `"busy"` | transient | This material endpoint is already handling another material operation. |
| `"invalid_properties"` | rejection | The item property selector has an invalid shape or value. |
| `"invalid_property_match"` | rejection | The requested property matching mode is invalid. |
| `"inventory_not_local"` | rejection | This endpoint cannot access the home freight Inventory from its current outpost. |
| `"same_endpoint"` | rejection | The configured source and destination are the same item endpoint. |
| `"source_under_construction"` | transient | The configured source is still under construction. |
| `"source_wrong_material"` | rejection | The source contains a different material from the one requested. |
| `"source_empty"` | rejection | The source has no matching units available. |
| `"source_reserved"` | rejection | The source is reserving its cargo for an active operation. |
| `"source_changed"` | transient | The source changed between transfer planning and commit. |
| `"target_missing"` | rejection | The configured target no longer exists. |
| `"target_under_construction"` | transient | The configured target is still under construction. |
| `"target_is_vehicle"` | rejection | The mobile target is a drone, or is a ground vehicle that is not docked in this endpoint's service area. |
| `"target_not_local"` | rejection | The configured target belongs to another outpost. |
| `"unsupported_target"` | rejection | The configured target cannot accept compatible cargo. |
| `"target_wrong_material"` | rejection | The destination is latched to or accepts a different material. |
| `"wrong_biome"` | rejection | The destination rejects this biological material because its biome is incompatible. |
| `"target_unconfigured"` | rejection | The destination lacks the world-state configuration required to accept this material. |
| `"hot_cargo_requires_cask"` | rejection | This hot cargo must move through a compatible Lead Cask. |
| `"cask_accepts_hot_only"` | rejection | Lead Casks accept only supported hot cargo. |
| `"order_item_not_required"` | rejection | The active order does not require this item. |
| `"order_slots_full"` | rejection | Every Supply Dock material slot is assigned to another required item. |
| `"order_fulfilled"` | rejection | The active order already has all required units of this item loaded or shipped. |
| `"slots_full"` | rejection | The destination has capacity but no slot for this material identity. |
| `"target_full"` | rejection | The destination has no capacity for matching units. |
| `"target_complete"` | rejection | The destination has completed its work and no longer accepts materials. |
| `"target_changed"` | transient | The destination changed between transfer planning and commit. |

##### `.flush() → TransferResult`

Permanently discard everything currently buffered in this input port. Flushed items are not returned to inventory. On processing machines, flushing also cancels any in-progress craft.

- **Returns** `TransferResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.requested`, `.moved`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Moved all `.moved` requested units. |
| `"no_op"` | success | No units were requested, so no state changed. |

##### `.count() → int`

Total units currently in this port's buffer.

- **Returns** `int`

##### `.capacity() → int`

Maximum units this port's buffer can hold.

- **Returns** `int`

##### `.stacks() → list[ItemStack]`

Snapshot list of property-distinct `ItemStack` values currently buffered. Two entries may have the same id when their properties differ.

- **Returns** `list[ItemStack]`

*Types / Storage & Inventory*

## ItemInfo

**Returned by:** item_catalog.lookup(item_id)

### Properties

##### `.id: str`

Stable item id.

- **Returns** `str`

##### `.name: str`

Localized item display name.

- **Returns** `str`

##### `.category: str`

Stable category used to distinguish materials, biological items, and equipment kinds.

- **Returns** `str`
- **Possible values** `"mineral"`, `"refined"`, `"crafted"`, `"agriculture"`, `"life_form"`, `"field_resource"`, `"biology_sample"`, `"reagent"`, `"equipment"`, `"module"`, `"portable"`, `"upgrade_pack"`, `"construction_kit"`

##### `.stackable: bool`

`True` when multiple units share one inventory stack; `False` when each unit occupies its own slot.

- **Returns** `bool`

##### `.biome: str | None`

Native biome for a life form or biology sample; `None` when biome does not apply.

- **Returns** `str | None`
- **Possible values** `"frozen"`, `"coastal"`, `"geothermal"`, `"volcanic"`, `"deep"`

##### `.rarity: str | None`

Rarity for a life form or biology sample; `None` when rarity does not apply.

- **Returns** `str | None`
- **Possible values** `"common"`, `"uncommon"`, `"rare"`, `"legendary"`

##### `.production_tier: int | None`

Lowest production tier that creates this item, or `None` when it is a raw, harvested, purchased, or otherwise source item. Smelter products are Tier 0.

- **Returns** `int | None`

*Types / Storage & Inventory*

## ItemResult

**Returned by:** harvester.store(), inventory.drop()

### Properties

##### `.status: str`

`"ok"`, `"empty"`, `"inventory_full"`, or `"invalid_slot"`, narrowed further by the command that returned it.

- **Returns** `str`
- **Possible values** `"ok"`, `"empty"`, `"inventory_full"`, `"invalid_slot"`

##### `.message: str`

Player-readable explanation of the item operation.

- **Returns** `str`

##### `.item_id: str | None`

Stable id of the item moved or destroyed, or `None` when no item changed.

- **Returns** `str | None`

*Types / Storage & Inventory*

## ItemStack

**Returned by:** InputSlot.stacks(), VehicleInputSlot.stacks(), OutputSlot.stacks(), PickupOutputSlot.stacks(), Cargo.stacks(), Bin.stacks, storage_bin.stacks(), warehouse.stacks()

### Properties

##### `.id: str`

Stable item id shared by every unit in this stack.

- **Returns** `str`

##### `.count: int`

Whole-number units with this exact property identity.

- **Returns** `int`

##### `.properties: ItemProperties | None`

Exact property dict for this item, or `None` for an ordinary commodity. Items with different properties form separate stacks and never merge.

- **Returns** `ItemProperties | None`

*Types / Storage & Inventory*

## OutputSlot

**Returned by:** self.output (machines with output port)

### Methods

##### `.connect(name: str) → ActionResult`

Set a compatible item destination by stable id or display name. Two stationary endpoints must share an outpost. A Rover or Pioneer is reachable from any outpost, but only while it is parked inside this machine's service area. A drone's cargo moves through its Drone Depot. `"inventory"` is a freight destination only while the endpoint is at Nocturna Base; remote stationary ports use local Storage Bins, Warehouses, or machine inputs.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `name` | `str` | Stable id or display name of a compatible item destination, or inventory |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_found"` | rejection | The requested object, target, or record does not exist. |
| `"not_local"` | rejection | The requested endpoint belongs to another outpost. |
| `"same_endpoint"` | rejection | The requested item source and destination are the same endpoint. |
| `"unsupported_target"` | rejection | The selected component does not expose a compatible item destination. |
| `"target_is_vehicle"` | rejection | The requested destination is a drone. Drone cargo moves through its Drone Depot. |

##### `.disconnect() → ActionResult`

Clear the current target connection. Does not move or discard buffered output.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.connected_to() → str`

Display name of the currently connected target, or empty string.

- **Returns** `str`

##### `.connected_id() → str`

Stable id of the currently connected target, or empty string. `connect()` accepts an id or a display name, so compare against this when you need the identity to match what you passed: `connected_to()` answers with the renameable name.

- **Returns** `str`

##### `.send(item_id: str, count: int, properties: ItemProperties | None = None, property_match: str | None = None) → TransferResult`

Send up to whole-number `count` units of `item_id` to the connected target. A property dict selects stacks containing that subset by default. Pass `"exact"` as the fourth argument for one full identity; `None, "exact"` selects only propertyless items. `"any"` ignores properties. Exact source properties are preserved. The transfer waits automatically for time proportional to units moved and requires Auto Feeders research.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `str` | Item id to send |
| `count` | `int` | Whole-number max units to send |
| `properties` | `ItemProperties \| None` | Optional property dict, matched as a subset by default. Omitted or `None` matches any properties; use `None` with `property_match="exact"` to select propertyless items only. |
| `property_match` | `str \| None` | Optional selection mode: any, subset, or exact |

- **Returns** `TransferResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.requested`, `.moved`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Moved all `.moved` requested units. |
| `"partial"` | partial | Moved `.moved` of `.requested` requested units; source availability or destination capacity limited the transfer. |
| `"no_op"` | success | No units were requested, so no state changed. |
| `"research_required"` | rejection | The required material-transfer research is not unlocked. |
| `"busy"` | transient | This material endpoint is already handling another material operation. |
| `"invalid_properties"` | rejection | The item property selector has an invalid shape or value. |
| `"invalid_property_match"` | rejection | The requested property matching mode is invalid. |
| `"no_connection"` | rejection | The port has no configured transfer endpoint. |
| `"inventory_not_local"` | rejection | This endpoint cannot access the home freight Inventory from its current outpost. |
| `"same_endpoint"` | rejection | The configured source and destination are the same item endpoint. |
| `"source_wrong_material"` | rejection | The source contains a different material from the one requested. |
| `"source_empty"` | rejection | The source has no matching units available. |
| `"source_changed"` | transient | The source changed between transfer planning and commit. |
| `"target_missing"` | rejection | The configured target no longer exists. |
| `"target_under_construction"` | transient | The configured target is still under construction. |
| `"target_is_vehicle"` | rejection | The mobile target is a drone, or is a ground vehicle that is not docked in this endpoint's service area. |
| `"target_not_local"` | rejection | The configured target belongs to another outpost. |
| `"not_at_target"` | rejection | The vehicle is outside the target's service area. |
| `"unsupported_target"` | rejection | The configured target cannot accept compatible cargo. |
| `"target_wrong_material"` | rejection | The destination is latched to or accepts a different material. |
| `"wrong_biome"` | rejection | The destination rejects this biological material because its biome is incompatible. |
| `"target_unconfigured"` | rejection | The destination lacks the world-state configuration required to accept this material. |
| `"mixed_materials"` | rejection | One transfer can contain only one item id. |
| `"hot_cargo_requires_cask"` | rejection | This hot cargo must move through a compatible Lead Cask. |
| `"cask_accepts_hot_only"` | rejection | Lead Casks accept only supported hot cargo. |
| `"order_item_not_required"` | rejection | The active order does not require this item. |
| `"order_slots_full"` | rejection | Every Supply Dock material slot is assigned to another required item. |
| `"order_fulfilled"` | rejection | The active order already has all required units of this item loaded or shipped. |
| `"slots_full"` | rejection | The destination has capacity but no slot for this material identity. |
| `"target_full"` | rejection | The destination has no capacity for matching units. |
| `"target_complete"` | rejection | The destination has completed its work and no longer accepts materials. |
| `"target_changed"` | transient | The destination changed between transfer planning and commit. |
| `"same_vehicle"` | rejection | A vehicle cannot transfer cargo to itself. |
| `"source_moving"` | transient | The source vehicle must stop before cargo can be handed off. |
| `"target_moving"` | transient | The destination vehicle must stop before cargo can be handed off. |
| `"out_of_range"` | rejection | The vehicles are outside cargo handoff range. |

##### `.count() → int`

Total units currently in this port's buffer.

- **Returns** `int`

##### `.capacity() → int`

Maximum units this port's buffer can hold.

- **Returns** `int`

##### `.stacks() → list[ItemStack]`

Snapshot list of property-distinct `ItemStack` values currently buffered. Use `.properties` to inspect and select variants before `send()`.

- **Returns** `list[ItemStack]`

*Types / Storage & Inventory*

## PickupOutputSlot

**Returned by:** self.output on field Water Pumps and Mining Drills

### Methods

##### `.count() → int`

Total item units waiting for carrier pickup.

- **Returns** `int`

##### `.capacity() → int`

Maximum item units this pickup stockpile can hold.

- **Returns** `int`

##### `.stacks() → list[ItemStack]`

Snapshot list of property-distinct `ItemStack` values waiting for carrier pickup.

- **Returns** `list[ItemStack]`

*Types / Storage & Inventory*

## Recipe

**Returned by:** list_recipes() / find_recipe() on Smelter, Fabricator, Feed Maker, Refiner, and Fuel Assembler

### Properties

##### `.tier: int`

Derived production tier. Smelter foundations are Tier 0; every other recipe is one tier above its deepest manufactured input.

- **Returns** `int`

##### `.id: str`

Recipe id (e.g. `"smelt_iron_ingot"`). Stable across saves: use to compare recipes or pass back to `set_recipe(...)`.

- **Returns** `str`

##### `.name: str`

Pre-translated display name of the recipe.

- **Returns** `str`

##### `.inputs: dict[str, int]`

A dict `{item_id: count}` of materials consumed per run. Iterate via `.keys()`, `.values()`, `.items()`, or index: `recipe.inputs["iron_ore"]`.

- **Returns** `dict[str, int]`

##### `.output_item: str`

Product id produced per run: an item id for discrete recipes or a fluid id for fluid-output recipes such as the Refiner.

- **Returns** `str`

##### `.output_count: int`

Amount of `output_item` produced per run: whole units for an item or tons for a fluid.

- **Returns** `int`

##### `.duration_game_hours: float`

Cycle duration in hours at full efficiency, including the querying Feed Maker's Mk tier. Inputs, power and output space must be available; overcrowding and blocked output can extend actual completion time.

- **Returns** `float`

##### `.power_draw: float`

Watts the machine draws while this recipe is running.

- **Returns** `float`

##### `.fluid_inputs: dict[str, float]`

A dict `{port_name: tons_per_run}` of fluid consumed when one run completes (`"water_in"` etc.). Empty dict for recipes with no fluid input.

- **Returns** `dict[str, float]`

##### `.input_fluid: str | None`

Concrete fluid id required by a generic input port, or `None` when the port itself already identifies the fluid. Refiner recipes use this to distinguish raw feedstocks on `gas_in` / `liquid_in`.

- **Returns** `str | None`
- **Possible values** `"raw_sulfur_gas"`, `"raw_cryofluid"`, `"raw_chlorine"`, `"raw_quicksilver"`

##### `.fluid_outputs: dict[str, float]`

A dict `{port_name: tons_per_run}` of fluid deposited when one run completes. Empty dict for item-output recipes; Refiner recipes identify `gas_out` or `liquid_out` here.

- **Returns** `dict[str, float]`

##### `.output_fluid: str | None`

Concrete fluid id produced through a generic output port, or `None` for item-output recipes. Equal to `output_item` for current fluid-only Refiner recipes.

- **Returns** `str | None`
- **Possible values** `"sulfur_gas"`, `"cryofluid"`, `"chlorine"`, `"quicksilver"`

##### `.byproduct_item: str | None`

Item id of the byproduct, or `None` if this recipe has no byproduct.

- **Returns** `str | None`

##### `.byproduct_count: int`

Units of `byproduct_item` produced per run; **0** for recipes with no byproduct.

- **Returns** `int`

*Types / Storage & Inventory*

## SaleResult

**Returned by:** shop.sell(), shop.sell_all()

### Properties

##### `.status: str`

`"ok"`, `"not_sellable"`, or `"no_stock"`.

- **Returns** `str`
- **Possible values** `"ok"`, `"not_sellable"`, `"no_stock"`

##### `.message: str`

Player-readable explanation of the sale outcome.

- **Returns** `str`

##### `.item_id: str`

Stable item id requested for sale.

- **Returns** `str`

##### `.units: int`

Whole-number units removed from Inventory.

- **Returns** `int`

##### `.credits: int`

Whole-number credits earned by this sale.

- **Returns** `int`

*Types / Storage & Inventory*

## ShopItem

**Returned by:** shop.get_catalogue()

### Properties

##### `.id: str`

Item ID (used for buying).

- **Returns** `str`

##### `.name: str`

Item display name.

- **Returns** `str`

##### `.cost: int`

Price in credits.

- **Returns** `int`

*Types / Storage & Inventory*

## Slot

**Returned by:** inventory.get_slots()

### Properties

##### `.slot: int`

Slot index number.

- **Returns** `int`

##### `.id: str`

Item ID (empty string if slot is empty).

- **Returns** `str`

##### `.name: str`

Item display name.

- **Returns** `str`

##### `.value: float`

Credit value per item.

- **Returns** `float`

##### `.count: int`

Stack count in this slot.

- **Returns** `int`

##### `.properties: ItemProperties | None`

Exact property dict for this stack, or `None` for an ordinary item. Pass it to property-aware transfer and capacity methods.

- **Returns** `ItemProperties | None`

##### `.genes: list[str]`

The genes a held **geothermal** fragment carries, e.g. `["cold_tolerance", "pressure_tolerance"]`: read it straight from inventory without loading the DNA Sequencer. A spliced fragment carries exactly the set you engineered; a raw fragment carries its natural genes. Empty for non-geothermal items.

- **Returns** `list[str]`

##### `.glow: list[int] | None`

Per-instance bioluminescent glow `[r,g,b]` (0-255) for a held **coastal** fragment. `None` for any other item.

- **Returns** `list[int] | None`

##### `.spliced: bool`

`True` if this is an engineered (already gene-spliced) geothermal fragment: a further DNA Sequencer alter would destroy it. `False` for raw items.

- **Returns** `bool`

*Types / Storage & Inventory*

## TransferResult

**Returned by:** InputSlot.take(), InputSlot.eject(), InputSlot.flush(), VehicleInputSlot.take(), OutputSlot.send(), Cargo.compact(), storage_bin transfer methods, warehouse.compact()

### Properties

##### `.status: str`

Stable result code for scripts to check. `.message` explains what happened.

- **Returns** `str`
- **Possible values** `"ok"`, `"partial"`, `"no_op"`, `"already_compact"`, `"research_required"`, `"busy"`, `"invalid_properties"`, `"invalid_property_match"`, `"no_connection"`, `"inventory_not_local"`, `"source_missing"`, `"source_under_construction"`, `"source_is_vehicle"`, `"source_not_local"`, `"not_at_source"`, `"unsupported_source"`, `"source_wrong_material"`, `"source_empty"`, `"source_reserved"`, `"source_changed"`, `"buffer_full"`, `"slots_full"`, `"target_missing"`, `"target_under_construction"`, `"target_is_vehicle"`, `"target_not_local"`, `"not_at_target"`, `"unsupported_target"`, `"target_wrong_material"`, `"wrong_biome"`, `"needs_plating"`, `"cask_missing"`, `"target_unconfigured"`, `"mixed_materials"`, `"hot_cargo_requires_cask"`, `"cask_accepts_hot_only"`, `"order_item_not_required"`, `"order_slots_full"`, `"order_fulfilled"`, `"target_full"`, `"target_complete"`, `"target_changed"`, `"same_endpoint"`, `"same_storage"`, `"same_vehicle"`, `"source_moving"`, `"target_moving"`, `"out_of_range"`

##### `.message: str`

Player-readable, contextual explanation of this exact outcome. Suitable for logs and player-facing diagnostics.

- **Returns** `str`

##### `.requested: int`

Whole-number units requested by the call. For parameterless `flush()` or `compact()`, this is the buffered or repositioned amount observed by the operation.

- **Returns** `int`

##### `.moved: int`

Whole-number units actually transferred, repositioned, or destroyed. Always **0** for rejected outcomes.

- **Returns** `int`

*Types / Storage & Inventory*

## VehicleInputSlot

**Returned by:** self.input on Rover and Pioneer

### Methods

##### `.connect(name: str) → ActionResult`

Set a compatible cargo source by stable id or display name. A Rover or Pioneer must be parked inside a stationary source's service area. Field Mining Drill and Water Pump stockpiles support carrier pickup. Vehicle handoffs require both vehicles to be stopped and nearby. `"inventory"` is available only while parked at Nocturna Base; remote outposts use local Storage Bins, Warehouses, or machine buffers.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `name` | `str` | Stable id or display name of a compatible cargo source, or inventory |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_found"` | rejection | The requested object, target, or record does not exist. |
| `"same_endpoint"` | rejection | The requested item source and destination are the same endpoint. |
| `"unsupported_source"` | rejection | The selected component does not expose a compatible item source. |
| `"source_is_vehicle"` | rejection | The requested source is a drone. Drone cargo moves through its Drone Depot. |

##### `.disconnect() → ActionResult`

Clear the current cargo source connection. This does not move or discard cargo.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.connected_to() → str`

Display name of the currently connected cargo source, or empty string.

- **Returns** `str`

##### `.connected_id() → str`

Stable id of the currently connected cargo source, or empty string. `connect()` accepts an id or display name, so compare against this when identity must survive renaming.

- **Returns** `str`

##### `.take(item_id: str, count: int, properties: ItemProperties | None = None, property_match: str | None = None) → TransferResult`

Load up to whole-number `count` units of `item_id` into vehicle cargo from the connected source. A property dict selects stacks containing that subset by default. Pass `"exact"` as the fourth argument for one full identity; `None, "exact"` selects only propertyless items. `"any"` ignores properties. Exact source properties are retained. The transfer waits automatically for time proportional to units moved and requires Auto Feeders research.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `str` | Item id to load |
| `count` | `int` | Whole-number max units to load |
| `properties` | `ItemProperties \| None` | Optional property dict, matched as a subset by default. Omitted or `None` matches any properties; use `None` with `property_match="exact"` to select propertyless items only. |
| `property_match` | `str \| None` | Optional selection mode: any, subset, or exact |

- **Returns** `TransferResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.requested`, `.moved`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Moved all `.moved` requested units. |
| `"partial"` | partial | Moved `.moved` of `.requested` requested units; source availability or destination capacity limited the transfer. |
| `"no_op"` | success | No units were requested, so no state changed. |
| `"research_required"` | rejection | The required material-transfer research is not unlocked. |
| `"busy"` | transient | This material endpoint is already handling another material operation. |
| `"invalid_properties"` | rejection | The item property selector has an invalid shape or value. |
| `"invalid_property_match"` | rejection | The requested property matching mode is invalid. |
| `"no_connection"` | rejection | The port has no configured transfer endpoint. |
| `"inventory_not_local"` | rejection | This endpoint cannot access the home freight Inventory from its current outpost. |
| `"same_endpoint"` | rejection | The configured source and destination are the same item endpoint. |
| `"source_missing"` | rejection | The configured source no longer exists. |
| `"source_under_construction"` | transient | The configured source is still under construction. |
| `"source_is_vehicle"` | rejection | The mobile source is a drone, or is a ground vehicle that is not docked in this endpoint's service area. |
| `"source_not_local"` | rejection | The configured source belongs to another outpost. |
| `"not_at_source"` | rejection | The vehicle is outside the source's service area. |
| `"unsupported_source"` | rejection | The configured source does not expose compatible cargo. |
| `"source_wrong_material"` | rejection | The source contains a different material from the one requested. |
| `"source_empty"` | rejection | The source has no matching units available. |
| `"source_reserved"` | rejection | The source is reserving its cargo for an active operation. |
| `"source_changed"` | transient | The source changed between transfer planning and commit. |
| `"buffer_full"` | rejection | The receiving input buffer is full. |
| `"slots_full"` | rejection | The destination has capacity but no slot for this material identity. |
| `"target_wrong_material"` | rejection | The destination is latched to or accepts a different material. |
| `"wrong_biome"` | rejection | The destination rejects this biological material because its biome is incompatible. |
| `"target_unconfigured"` | rejection | The destination lacks the world-state configuration required to accept this material. |
| `"hot_cargo_requires_cask"` | rejection | This hot cargo must move through a compatible Lead Cask. |
| `"order_item_not_required"` | rejection | The active order does not require this item. |
| `"order_slots_full"` | rejection | Every Supply Dock material slot is assigned to another required item. |
| `"order_fulfilled"` | rejection | The active order already has all required units of this item loaded or shipped. |
| `"target_full"` | rejection | The destination has no capacity for matching units. |
| `"target_complete"` | rejection | The destination has completed its work and no longer accepts materials. |
| `"target_changed"` | transient | The destination changed between transfer planning and commit. |
| `"same_vehicle"` | rejection | A vehicle cannot transfer cargo to itself. |
| `"source_moving"` | transient | The source vehicle must stop before cargo can be handed off. |
| `"target_moving"` | transient | The destination vehicle must stop before cargo can be handed off. |
| `"out_of_range"` | rejection | The vehicles are outside cargo handoff range. |

##### `.count() → int`

Total units currently carried in the vehicle's cargo.

- **Returns** `int`

##### `.capacity() → int`

Maximum units the vehicle's cargo can hold.

- **Returns** `int`

##### `.stacks() → list[ItemStack]`

Snapshot list of property-distinct `ItemStack` values currently carried. Two entries may have the same id when their properties differ.

- **Returns** `list[ItemStack]`

*Types / Storage & Inventory*

## WarehouseSlot

**Returned by:** warehouse.slots()

### Properties

##### `.index: int`

Slot index (0-based).

- **Returns** `int`

##### `.item: str`

Item id this slot holds (empty string if the slot is empty).

- **Returns** `str`

##### `.count: int`

Units currently in this slot.

- **Returns** `int`

##### `.capacity: int`

This slot's capacity (units).

- **Returns** `int`

##### `.properties: ItemProperties | None`

Exact property dict for the item variant in this physical slot, or `None` when the slot is empty or holds an ordinary item.

- **Returns** `ItemProperties | None`

*Types / Fleet & Vehicles*
