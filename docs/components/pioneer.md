# Component: pioneer

> **Category:** Vehicles & Modules | **Component Name:** Pioneer

A modular long-range vehicle for driving, scanning, mining, and building in the field. The bare chassis does nothing; everything comes from the modules, batteries, and cargo you mount in its eight slots.

| Field | Value |
| --- | --- |
| Type | Mining |
| Stockpile | 0 units (mixed) |

### How to obtain

1. Requires the **Pioneer Chassis** research (Terraform Index 100,000).
2. Buy from the Shop for 5,000 cr.

**Returned by:** `self / get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

##### `.battery`

Aggregated battery pool across every Portable Battery in every mounted Battery Holder. `self.battery.level()` returns a **0-1** fraction; `self.battery.wh()` raw watt-hours; `self.battery.capacity()` the summed max. For per-holder detail, `self.battery.holders()` returns each Holder with its `.batteries` list. The aggregate view covers most scripts, introspection is for advanced rebalance logic. If zero Portable Batteries are installed, the Pioneer can't move. See `Battery`.

- **Returns** `Battery`: aggregated across every battery in every mounted Battery Holder

##### `.cargo`

Combines the Portable Bins in the Pioneer's Cargo Racks. Use `count()`, `capacity()`, and `full()` for totals, or `racks()` to inspect the physical layout. Each bin holds one item type. `take()` and `send()` handle bins independently. `compact()` consolidates matching cargo into fewer bins without changing `send()` order. `discard(rack_index)` permanently empties one rack and takes **1 hour** when cargo is present; an empty rack finishes immediately. See `Cargo`.

- **Returns** `Cargo`: aggregated across every bin in every mounted Cargo Rack

##### `.nav`

Drives the Pioneer. Set a destination in meters from base with `self.nav.set_target(x, y)`. The call returns immediately and the Pioneer keeps driving while the script runs. A distance tolerance means the Pioneer is close enough, not stopped, so call `self.nav.brake()` before mining, constructing, or transferring cargo. The Pioneer stops and clears its route if the script stops, ends, or errors. Requires a Nav Module in a Universal slot. See `NavModule` for throttle, braking, and position.

- **Returns** `NavModule` when a Nav Module is mounted

##### `.sonar`

Finds useful sites near the Pioneer. Use `self.sonar.scan()` to find nearby sites, then `self.sonar.survey(site)` to reveal details such as mineral hardness, purity, or vent output. Scanning and new surveys take time and use battery, so the script pauses while the sonar works. Requires a mounted Sonar Module. See `SonarModule` for its range, capabilities, and battery use.

- **Returns** `SonarModule` when a Sonar Module is mounted

##### `.drill`

Extracts one mineral unit from the surveyed site under the Pioneer with `self.drill.mine()`. The vehicle must be stationary and have enough cargo space and power. Requires a mounted Drill Module. See `DrillModule` for speed and hardness limits.

- **Returns** `DrillModule` when a Drill Module is mounted

##### `.constructor`

Builds or removes Planet Map blueprints from Plan Mode or scripts. Read pending work from `get_component("construction_blueprint")`, drive near `construction.position`, then call `self.constructor.execute(construction.id)`. Building consumes the required kits or segments from cargo; removal returns reclaimed parts to cargo, so leave room. Requires a mounted Constructor Module. See `ConstructorModule`.

- **Returns** `ConstructorModule` when a Constructor Module is mounted: exposes `execute()`.

##### `.input`

Loads cargo from Inventory at home, local storage at outposts, field-extractor stockpiles, or a nearby stopped cargo vehicle. Field and vehicle transfers require service range; both vehicles must be stopped. It never destroys cargo; use `self.cargo.discard(rack_index)` to jettison one rack. Requires **Auto Feeders**. See `VehicleInputSlot`.

- **Returns** `VehicleInputSlot`: `connect()`, `disconnect()`, `take()`, `count()`, `capacity()`, `stacks()`, `connected_to()`, `connected_id()`

##### `.output`

Unloads cargo to Inventory, a Storage Bin, a Warehouse, or a nearby stopped cargo vehicle. Inventory freight is physically available only while the Pioneer is parked at home. Remote outposts use their local stores. Vehicle-to-vehicle handoffs require both vehicles stopped within **~2 m**. Requires **Auto Feeders** research. See `OutputSlot`.

- **Returns** `OutputSlot`: `connect()`, `send()`, `count()`, `capacity()`, `connected_to()`

### Methods

##### `.status()`

Read the Pioneer's current physical activity. Each call reads fresh state, including through `get_component(...)`. An idle Pioneer may still have a script running or a job assigned.

- **Returns** String: current vehicle activity, evaluated when called.
- **Possible values** `"idle"`, `"moving"`, `"stranded"`, `"scanning"`, `"surveying"`, `"drilling"`, `"discarding"`, `"constructing"`, `"transferring"`, `"charging"`, `"queued"`, `"being_rescued"`

##### `.is_being_rescued()`

`True` while a Vehicle Charging Station rescue drone is actively recovering this Pioneer. Use this to pause movement, mining, or construction scripts even if the battery has started rising above zero.

- **Returns** Boolean

##### `.rescue_status()`

Current rescue mission phase for this Pioneer: `"none"`, `"outbound"`, `"charging"`, or `"returning"`. `"returning"` means the rescue drone is going home and the Pioneer is free again.

- **Returns** String status: `"none"` / `"outbound"` / `"charging"` / `"returning"`.
- **Possible values** `"none"`, `"outbound"`, `"charging"`, `"returning"`

##### `.modules()`

Inspect every slot on the chassis. Returns a list of `MountSlot`, eight entries for the Pioneer. Each has `.index` (pass to `mount` / `unmount`), `.type` (always `"universal"` on Pioneer), `.module_id` (what's mounted, or `None` for empty), `.internal_count` (non-zero for Battery Holders / Cargo Racks), `.internal_items` (list of installed portable item ids). Call before `self.mount(...)` or `self.install(...)` to find an empty target. See `MountSlot`.

- **Returns** List of `MountSlot` objects: one per mount point on the chassis, each with `.index`, `.type`, `.module_id`, `.internal_count`, `.internal_items`.

##### `.mount(slot_index, item_id)` *(self only)*

Request a hardware service order from Inventory into whole-number `slot_index`: `self.mount(0, "nav_module")`. Biological field modules are drone-only. The Pioneer must be inside a founded outpost service area. This dedicated-hardware exception does not make Inventory a freight endpoint there.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `slot_index` | `number` | Whole-number zero-based slot position on the chassis. |
| `item_id` | `string` | Shop id of the module to mount. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_at_service_point"` | rejection | The vehicle is not parked inside base's or an operational outpost's service area. Parked means not moving and no active throttle; a vehicle with no drive energy counts as parked whatever its throttle says. |
| `"locked"` | rejection | The required feature, recipe, or operation is locked. |
| `"item_not_in_inventory"` | rejection | Inventory does not contain the requested item. |
| `"unknown_module"` | rejection | The supplied module identifier does not exist. |
| `"slot_not_compatible"` | rejection | The selected slot is not compatible with the module. |
| `"slot_occupied"` | rejection | The selected slot is occupied. |
| `"invalid_slot"` | rejection | The supplied slot does not exist. |
| `"capability_already_mounted"` | rejection | The vehicle already has a module providing this capability. |

##### `.unmount(slot_index)` *(self only)*

Request a hardware service order that returns the module at whole-number `slot_index` to Inventory: `self.unmount(0)`. The Pioneer must be inside a founded outpost service area. Empty every internal bay before removing a holder or rack.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `slot_index` | `number` | Whole-number zero-based slot position on the chassis. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_at_service_point"` | rejection | The vehicle is not parked inside base's or an operational outpost's service area. Parked means not moving and no active throttle; a vehicle with no drive energy counts as parked whatever its throttle says. |
| `"slot_empty"` | rejection | The selected slot is empty. |
| `"invalid_slot"` | rejection | The supplied slot does not exist. |
| `"holder_not_empty"` | rejection | The equipment holder still contains an item. |
| `"inventory_full"` | rejection | Inventory has no capacity for the result. |

##### `.install(slot_index, internal_index, item_id)` *(self only)*

Request a service order that installs a Portable Battery or empty Portable Storage Bin from Inventory into a container's whole-number internal slot. `self.install(0, 1, "portable_battery")` uses bay **1** of the Battery Holder at chassis slot **0**. `self.install(4, 0, "portable_bin")` uses bay **0** of the Cargo Rack at chassis slot **4**. The Pioneer must be inside a founded outpost service area.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `slot_index` | `number` | Whole-number slot where the container (Battery Holder / Cargo Rack) is mounted. |
| `internal_index` | `number` | Whole-number zero-based index within the container's internal slots. |
| `item_id` | `string` | Shop id of the portable item to install. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_at_service_point"` | rejection | The vehicle is not parked inside base's or an operational outpost's service area. Parked means not moving and no active throttle; a vehicle with no drive energy counts as parked whatever its throttle says. |
| `"locked"` | rejection | The required feature, recipe, or operation is locked. |
| `"invalid_slot"` | rejection | The supplied slot does not exist. |
| `"invalid_internal_slot"` | rejection | The supplied internal slot does not exist. |
| `"slot_empty"` | rejection | The selected slot is empty. |
| `"not_container"` | rejection | The supplied target is not a compatible container. |
| `"item_not_accepted"` | rejection | The destination does not accept the supplied item. |
| `"internal_slot_occupied"` | rejection | The selected internal slot is occupied. |
| `"item_not_in_inventory"` | rejection | Inventory does not contain the requested item. |

##### `.uninstall(slot_index, internal_index)` *(self only)*

Request a service order that returns the portable item in a container's whole-number internal slot to Inventory: `self.uninstall(0, 1)`. The Pioneer must be inside a founded outpost service area, and Portable Storage Bins must be empty.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `slot_index` | `number` | Whole-number slot where the container is mounted. |
| `internal_index` | `number` | Whole-number zero-based index within the container's internal slots. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_at_service_point"` | rejection | The vehicle is not parked inside base's or an operational outpost's service area. Parked means not moving and no active throttle; a vehicle with no drive energy counts as parked whatever its throttle says. |
| `"invalid_slot"` | rejection | The supplied slot does not exist. |
| `"invalid_internal_slot"` | rejection | The supplied internal slot does not exist. |
| `"slot_empty"` | rejection | The selected slot is empty. |
| `"not_container"` | rejection | The supplied target is not a compatible container. |
| `"internal_slot_empty"` | rejection | The selected internal slot is empty. |
| `"inventory_full"` | rejection | Inventory has no capacity for the result. |
| `"container_not_empty"` | rejection | The module's cargo container is not empty. |

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Vehicles & Modules*
