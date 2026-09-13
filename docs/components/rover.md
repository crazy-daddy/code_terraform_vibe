# Component: rover

> **Category:** Vehicles & Modules | **Component Name:** Rover

Your starter expedition vehicle for driving, scanning, and mining. The bare chassis does nothing on its own; every ability comes from the modules mounted in its three fixed slots.

| Field | Value |
| --- | --- |
| Type | Mining |
| Energy | 100 Wh |
| Stockpile | 10 units (mixed) |

### How to obtain

1. Requires the **Rover Chassis** research (Pressure 0.11).
2. Buy from the Shop for 2,000 cr.

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

How much charge the Rover has left. `self.battery.level()` returns a **0-1** fraction, `self.battery.wh()` raw watt-hours, `self.battery.capacity()` the **100 Wh** max. Below **0.1** you're close to getting stranded, `charging_station.dispatch_rescue()` can fetch you, but it's slow. `.holders()` returns an empty list (sealed rig). See `Battery`.

- **Returns** `Battery`: `level()`, `wh()`, `capacity()`, `holders()`

##### `.cargo`

Everything carried in the Rover's integrated hold. `self.cargo.count()` returns total units across every item and property variant; `self.cargo.capacity()` is **10**; `self.cargo.full()` is `True` at capacity, check it before loading or drilling. `.racks()` is empty because the hold is integrated. `self.cargo.discard(0)` permanently jettisons the whole hold and takes **1 hour** when cargo is present; an empty hold finishes immediately. See `Cargo`.

- **Returns** `Cargo`: `count()`, `capacity()`, `full()`, `racks()`, `discard()`

##### `.nav`

Drives the Rover. Set a destination in meters from base with `self.nav.set_target(x, y)`. The call returns immediately and the Rover keeps driving while the script runs. A distance tolerance means the Rover is close enough, not stopped, so call `self.nav.brake()` before mining, scanning, surveying, or transferring cargo. The Rover stops and clears its route if the script stops, ends, or errors. Requires a mounted Nav Module. See `NavModule` for throttle, braking, and speed.

- **Returns** `NavModule` when a Nav Module is mounted, else unavailable

##### `.sonar`

Finds useful sites near the Rover. Use `self.sonar.scan()` to find nearby sites, then `self.sonar.survey(site)` to reveal details such as mineral hardness, purity, or vent output. Scanning and new surveys take time, so the script pauses while the sonar works. Requires a mounted Sonar Module. See `SonarModule` for its range, capabilities, and battery use.

- **Returns** `SonarModule` when a Sonar Module is mounted, else unavailable

##### `.drill`

Extracts one mineral unit from the surveyed site under the Rover with `self.drill.mine()`. The vehicle must be stationary and have enough cargo space and power. Requires a mounted Drill Module. See `DrillModule` for speed and hardness limits.

- **Returns** `DrillModule` when a Drill Module is mounted, else unavailable

##### `.input`

Loads cargo from Inventory at home, local storage at outposts, field-extractor stockpiles, or a nearby stopped cargo vehicle. Field and vehicle transfers require service range; both vehicles must be stopped. It never destroys cargo; use `self.cargo.discard(0)` to jettison the hold. Requires **Auto Feeders**. See `VehicleInputSlot`.

- **Returns** `VehicleInputSlot`: `connect()`, `disconnect()`, `take()`, `count()`, `capacity()`, `stacks()`, `connected_to()`, `connected_id()`

##### `.output`

Unloads cargo to Inventory, a Storage Bin, a Warehouse, or a nearby stopped cargo vehicle. Inventory freight is physically available only while the Rover is parked at home. Remote outposts use their local stores. Vehicle-to-vehicle handoffs require both vehicles stopped within **~2 m**. Requires **Auto Feeders** research. See `OutputSlot`.

- **Returns** `OutputSlot`: `connect()`, `send()`, `count()`, `capacity()`, `connected_to()`

### Methods

##### `.status()`

Read the Rover's current physical activity. Each call reads fresh state, including through `get_component(...)`. An idle Rover may still have a script running or a job assigned.

- **Returns** String: current vehicle activity, evaluated when called.
- **Possible values** `"idle"`, `"moving"`, `"stranded"`, `"scanning"`, `"surveying"`, `"drilling"`, `"discarding"`, `"constructing"`, `"transferring"`, `"charging"`, `"queued"`, `"being_rescued"`

##### `.is_being_rescued()`

`True` while a Vehicle Charging Station rescue drone is actively recovering this Rover. Use this to pause movement or mining scripts even if the battery has started rising above zero.

- **Returns** Boolean

##### `.rescue_status()`

Current rescue mission phase for this Rover: `"none"`, `"outbound"`, `"charging"`, or `"returning"`. `"returning"` means the rescue drone is going home and the Rover is free again.

- **Returns** String status: `"none"` / `"outbound"` / `"charging"` / `"returning"`.
- **Possible values** `"none"`, `"outbound"`, `"charging"`, `"returning"`

##### `.modules()`

Inspect what's mounted. Returns a list of `MountSlot`, one per chassis slot. Each has `.index` (pass to `mount` / `unmount`), `.type` (which modules fit), `.module_id` (mounted id or `None`), `.internal_items` (empty on the Rover's function slots). Call this before `self.mount(...)` to find an empty slot and verify the slot type accepts the module you want. See `MountSlot`.

- **Returns** List of `MountSlot` objects: one per mount point on the chassis, each with `.index`, `.type`, `.module_id`, `.internal_count`, `.internal_items`.

##### `.mount(slot_index, item_id)` *(self only)*

Request a hardware service order from Inventory into whole-number `slot_index`: `self.mount(0, "nav_module")`. Biological field modules are drone-only. The Rover must be inside a founded outpost service area. This dedicated-hardware exception does not make Inventory a freight endpoint there.

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

Request a hardware service order that returns the module at whole-number `slot_index` to Inventory: `self.unmount(0)`. The Rover must be inside a founded outpost service area, and container modules must be empty.

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

Install a portable item (Portable Battery / Portable Storage Bin) into a container module's internal slot. **Not used on the Rover**, its fixed slots only accept Nav, Sonar, and Drill function modules, never containers. See Pioneer for the modular version.

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

Uninstall a portable item from a container module's internal slot. **Not used on the Rover**, same reason as `install`. See Pioneer for the modular version.

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
