# Component: drone

> **Category:** Vehicles & Modules | **Component Name:** Drone

Small aerial cargo drone, 1 thruster + 2 modules.

| Field | Value |
| --- | --- |
| Type | Mining |

### How to obtain

1. The recipe unlocks when you complete **Helios, Rotor Run**.
2. Requires the **Basic Drone Operations** research (Terraform Index 180,000).
3. Fabricate **Drone (Small)** on a **Fabricator**: 1× Rare Earth Core, 1× Titanium Ingot, 1× Control Unit, and 2 t Water.
4. Deploy it from your Inventory.

**Access via:** `self / get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id: str`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** `str`

##### `.name: str`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** `str`

##### `.battery: DroneBattery`

Reads power on electric drones. Use `self.battery.level()` for current charge in **Wh**, `capacity()` for total Battery Pack capacity, and `percent()` for the **0-1** charge fraction. These calls raise `ReferenceError` on a heli drone. In mixed fleets, check `DroneRef.engine` from `fleet.drones()` first.

- **Returns** `DroneBattery`. On **electric drones** only. Its methods raise `ReferenceError` on a drone without an electric powertrain; inspect `fleet.drones()` and branch on `DroneRef.engine` before calling across a mixed fleet.

##### `.oil_tank: DroneOilTank`

Reads fuel on heli drones. Use `self.oil_tank.level()` for current oil in **tons**, plus `capacity()` and `percent()`. These calls raise `ReferenceError` on an electric drone. In mixed fleets, check `DroneRef.engine` from `fleet.drones()` first.

- **Returns** `DroneOilTank`. On **heli drones** only. Its methods raise `ReferenceError` on a drone without a heli powertrain; inspect `fleet.drones()` and branch on `DroneRef.engine` before calling across a mixed fleet.

##### `.cargo: DroneCargo`

Each Cargo Pod holds one item type; the Bio Extractor chamber holds one life-form type. Containers unlatch when empty. Loads top up matching containers before using empty ones, with life-form chambers before pods within each group. Plan with `self.cargo.count()`, `contents()`, `capacity()`, and `space_for(item_id)`. `load()` and `unload()` work while docked at a Drone Depot; `load()` also works at a field Mining Drill or Lead Cask. Item properties are preserved. See `DroneCargo`.

- **Returns** `DroneCargo`. Mounted Cargo Pods plus the Bio Extractor's typed 25 t chamber. Use `space_for(item_id)` because biological room is item-specific.

##### `.bio_scanner: PortableBioScanner`

Portable Bio Scanner

- **Returns** `PortableBioScanner`. `scan()` requires the module, a completed route, and working electronics and exposes the completed biological reading through `BioScanResult.scan`.

##### `.bio_extractor: PortableBioExtractor`

Portable Bio Extractor

- **Returns** `PortableBioExtractor`. `extract()` requires a hovering, non-scrambled drone and uses its integrated 25 t one-life-form chamber plus any Cargo Pods.

### Methods

##### `.go_to_station(name: str) → ActionResult` *(self only)*

Queue a route to the named Drone Depot or Drone Service Station and return immediately without waiting for docking. An accepted powered route reports `"traveling"` immediately; position and docking advance after simulation advances. Stop, completion, or error cancels the flight and clears the route. Compare `current_station()` with the destination's stable id to confirm arrival. Moving between drone buildings inside the same outpost is a local transfer and costs no flight fuel. Drone Service Stations accept parked arrivals even while unpowered. A full Drone Depot keeps the drone undocked in `"waiting_bay"` until a physical bay opens.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `name` | `str` | Display name or id of the destination Drone Depot or Drone Service Station. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"station_not_found"` | rejection | The requested station does not exist. |
| `"out_of_range"` | rejection | The requested target lies outside the operation's range. |
| `"busy"` | transient | The component is already performing another operation. |
| `"scrambled"` | transient | Radiation scrambling prevents the operation. |

##### `.undock() → ActionResult` *(self only)*

Release the station berth without flying anywhere. The drone keeps its exact world position, cargo, modules, fuel, and exposure, clears any dormant route, resets throttle to **0**, and becomes `idle`. An active rescue, or an active or queued Drone Service Station charge/refuel job, retains control until that station-owned work ends. Use `go_to_station(...)` when the drone should claim a berth again. Self-only.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_docked"` | rejection | The requested vehicle is not docked at this station. |
| `"busy"` | transient | The component is already performing another operation. |

##### `.go_to_drill(name: str) → ActionResult` *(self only)*

Fly to a named field Mining Drill for ore pickup. Hauling needs no field module. An accepted powered route reports `"traveling"` immediately, then the drone flies in a straight line and hovers on arrival. Compare `current_drill()` with the destination's stable id to confirm that cargo loading is available. Stopping or completing the script, hitting an error, or calling `go_to_station()` cancels this route.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `name` | `str` | Display name or id of a deployed Mining Drill (any tier). |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"drill_not_found"` | rejection | No completed mining drill matching the request is available within the planet's bounds. |
| `"out_of_range"` | rejection | The requested target lies outside the operation's range. |
| `"busy"` | transient | The component is already performing another operation. |
| `"scrambled"` | transient | Radiation scrambling prevents the operation. |

##### `.current_station() → str`

Stable station id where the drone is physically docked. Returns an empty string while flying to coordinates, traveling between stations, or waiting outside a full Drone Depot. Use equality with the destination id as the authoritative station-arrival check, even when `go_to_station()` was called with a display name.

- **Returns** `str`. The station id, or empty if in transit.

##### `.current_drill() → str`

Stable Mining Drill id where the drone can currently load cargo, or an empty string when no Drill is available. The drone must be within the Drill's loading area with no active route; merely passing over the Drill or holding a zero-throttle route does not count. Compare this value with the destination id as the authoritative Drill-arrival check, even when `go_to_drill()` was called with a display name.

- **Returns** `str`. The Mining Drill id available for cargo loading, or empty otherwise.

##### `.position() → Position`

World coordinates `(.x, .y)`, lerped each tick by DroneSystem during transit, snapped to station coords on dock.

- **Returns** `Position`. Current world coordinates.

##### `.get_distance_to(x: float, y: float) → float`

Straight-line distance in meters from the drone's current position to the given world coordinate. Use it to compare possible destinations, check remaining route distance, or pair it with `range_remaining()` before dispatch. It measures geometry only and does not select a destination or account for available fuel.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | Target X coordinate in meters |
| `y` | `float` | Target Y coordinate in meters |

- **Returns** `float`. Straight-line distance in meters from the drone's current position to the given point.

##### `.go_to(x: float, y: float) → ActionResult` *(self only)*

Fly to any world coordinate as a base drone capability; no field module is required. An accepted powered route reports `"traveling"` immediately, then the drone flies in a straight line and hovers on arrival. Stopping or completing the script, hitting an error, or calling `go_to_station()` cancels this route. For Weather, pass the exact `x` and `y` assembled from checksum-valid storm packets.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | World x, m. |
| `y` | `float` | World y, m. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"invalid_target"` | rejection | The supplied target is not valid for this operation. |
| `"out_of_bounds"` | rejection | The requested position lies outside the valid world bounds. |
| `"out_of_range"` | rejection | The requested target lies outside the operation's range. |
| `"busy"` | transient | The component is already performing another operation. |
| `"scrambled"` | transient | Radiation scrambling prevents the operation. |

##### `.collect() → CollectResult` *(self only)*

Collect one weather aftermath batch at the drone's exact current coordinate. A successful batch transfers at most **5** Storm Glass or Raw Uranium. Raw Uranium collection adds **40** exposure without Shield Plating and **0** with it; the batch is retained even if it reaches the scramble threshold.

- **Returns** `CollectResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.item_id`, `.collected`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Drone cargo received: `.item_id` × `.collected`. |
| `"moving"` | transient | The drone is still moving. |
| `"busy"` | transient | The drone is occupied by a biological extraction. |
| `"nothing_here"` | rejection | No live weather aftermath exists at the drone's current coordinate. |
| `"no_cargo_space"` | rejection | The drone has no cargo capacity for the material at this site. |
| `"scrambled"` | transient | The drone's electronics are radiation-scrambled and cannot collect. |

##### `.exposure() → float`

Current extraction exposure, from **0** to `exposure_capacity()`. It changes only when collecting Raw Uranium or receiving Service Station care; simply flying across a hidden aftermath is inert. A working drone docked at a powered Drone Service Station clears **10 per hour**. At capacity the drone is scrambled and requires Service Station rescue.

- **Returns** `float`. Radiation exposure from **0** to capacity. An unplated uranium collection adds **40**; Shield Plating adds **0**. A powered Drone Service Station clears non-terminal exposure at **10/h**. At capacity the drone scrambles and requires rescue.

##### `.exposure_capacity() → float`

The **100** exposure scramble threshold. An unplated drone can collect two 5-unit batches safely; the third batch is retained and then scrambles it.

- **Returns** `float`. The scramble threshold.

##### `.is_plated() → bool`

`True` with Shield Plating mounted. Plating reduces Raw Uranium extraction exposure to zero, halves each Cargo Pod's capacity, and raises fuel burn **1.5×** because lead is heavy.

- **Returns** `bool`. `True` when Shield Plating is mounted: zero Raw Uranium extraction exposure and required for hot-cargo loads from Lead Casks; halves Cargo Pod capacity and raises burn.

##### `.range_remaining() → float`

Estimated flight distance in meters at the current energy and throttle. Electric burn is **5 Wh/h** at full throttle; Heli burn is **5 t/h Oil**. Both scale with throttle squared, so slower routes stretch range.

- **Returns** `float`. Estimated meters of flight at current charge and current throttle. **0** if throttle is 0 or battery or oil is empty.

##### `.throttle() → float`

Current throttle (**0-1**). Full-throttle burn is **5 Wh/h** for electric propulsion or **5 t/h Oil** for Heli; both scale with throttle squared. Reads **0** after Stop, completion, or error.

- **Returns** `float`. Current throttle setting (**0-1**).

##### `.set_throttle(rate: float) → ActionResult` *(self only)*

Set throttle (**0-1**). At full throttle, electric drones fly **300 m/h** using **5 Wh/h**; Heli drones fly **900 m/h** using **5 t/h Oil**. Lower throttle reduces burn quadratically. Stop, completion, or error resets throttle to **0**. Self-only.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `rate` | `float` | Throttle setting (**0-1**). |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.modules() → list[MountSlot]`

Inspect what's coupled. Returns a list of `MountSlot`, one per slot on the chassis. Each has `.index` (pass to `couple` / `uncouple`), `.type` (`"thruster"` for slot 0, `"drone_module"` for the rest), `.module_id` (the coupled module, or `None` for an empty slot). Works on any drone, not only `self`. See `MountSlot`.

- **Returns** `list[MountSlot]`. One per slot on the chassis.

##### `.couple(slot_index: int, module_id: str) → ActionResult` *(self only)*

Request a hardware service order from Inventory into an explicit whole-number slot: `self.couple(0, "electric_thruster")` for the thruster slot, or `self.couple(1, "battery_pack")` for a module slot. The drone must be docked at an operational Drone Depot. This dedicated-hardware exception does not expose ordinary Inventory freight at that outpost. Self-only.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `slot_index` | `int` | Whole-number drone slot index, starting at 0. |
| `module_id` | `str` | Shop id of the drone module |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_at_station"` | rejection | The vehicle is not docked at a compatible station. |
| `"item_not_in_inventory"` | rejection | Inventory does not contain the requested item. |
| `"unknown_module"` | rejection | The supplied module identifier does not exist. |
| `"slot_not_compatible"` | rejection | The selected slot is not compatible with the module. |
| `"slot_occupied"` | rejection | The selected slot is occupied. |
| `"invalid_slot"` | rejection | The supplied slot does not exist. |
| `"locked"` | rejection | The required feature, recipe, or operation is locked. |
| `"wrong_engine_for_module"` | rejection | The module is incompatible with the vehicle's engine type. |
| `"cargo_capacity_exceeded"` | rejection | Current cargo exceeds the requested rig's capacity. |

##### `.uncouple(slot_index: int) → ActionResult` *(self only)*

Request a hardware service order that returns the module in an explicit whole-number slot to Inventory: `self.uncouple(1)`. The drone must be docked at an operational Drone Depot. Cargo Pods must be empty before removal, and Shield Plating cannot be removed while Raw Uranium or Fuel Rod cargo remains aboard. Fuel-bearing modules preserve their contents. Self-only.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `slot_index` | `int` | Whole-number drone slot index, starting at 0. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"invalid_slot"` | rejection | The supplied slot does not exist. |
| `"module_not_mounted"` | rejection | The selected module slot has no mounted module. |
| `"not_at_station"` | rejection | The vehicle is not docked at a compatible station. |
| `"cargo_capacity_exceeded"` | rejection | Current cargo exceeds the requested rig's capacity. |
| `"container_not_empty"` | rejection | The module's cargo container is not empty. |
| `"hot_cargo_requires_plating"` | rejection | Raw Uranium or Fuel Rod cargo remains aboard and requires Shield Plating. |
| `"inventory_full"` | rejection | Inventory has no capacity for the result. |

##### `.status() → str`

Current operational activity for progress and blocker handling, not an arrival test. `"idle"` can mean docked, hovering at a field coordinate, or holding a queued route at zero throttle; `charging` or `refueling` can begin immediately after docking. `"waiting_bay"` means the drone reached a full Depot but is not docked, `"holding_weather"` is a temporary heli hold, and `stalled` or `scrambled` states need intervention. Use `current_station()` or `current_drill()` to confirm arrival at an interaction endpoint.

- **Returns** `str`. Current operational activity. Use `current_station()` for the separate physical-arrival check.
- **Possible values** `"idle"`, `"traveling"`, `"charging"`, `"refueling"`, `"waiting_service"`, `"waiting_oil"`, `"waiting_bay"`, `"being_rescued"`, `"holding_weather"`, `"scrambled"`, `"stalled_no_battery"`, `"stalled_no_oil"`, `"stalled_no_route"`

##### `.is_being_rescued() → bool`

`True` while a Drone Service Station's recovery vehicle is outbound to, servicing, or carrying this drone. Use this to pause route scripts while the recovery vehicle has control.

- **Returns** `bool`

##### `.rescue_status() → str`

Current rescue mission phase for this drone: `"none"`, `"outbound"`, `"charging"`, `"carrying"`, or `"returning"`. `"returning"` means the recovery vehicle is heading home and the drone is no longer under rescue control.

- **Returns** `str`
- **Possible values** `"none"`, `"outbound"`, `"charging"`, `"carrying"`, `"returning"`

##### `.set_status(message: str, level: str = "info") → None` *(self only)*

Show a status message for this machine's current script run. Use `self.set_status(message, "info")`. The same reporting capability is available as `set_status()` in every script. Messages follow the current execution, independently of machine state and game warnings.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `str` | Non-empty plain text, at most 240 characters. Null characters are not accepted. |
| `level` | `str` | Presentation severity: `info`, `warn`, or `error`. Defaults to `info`. |

- **Returns** `None`. `None`.

##### `.clear_status() → None` *(self only)*

Clear the current script run's status message. Clearing an absent message has no effect. Does not wait or change machine behaviour.

- **Returns** `None`. `None`.

##### `.get_status_report() → ScriptStatusReport | None`

Read this machine's script status report from any script. Returns `None` when it has no report. The returned snapshot includes `message`, `level`, `active`, and `run_id`.

- **Returns** `ScriptStatusReport | None`. Read this machine's script status report from any script. Returns `None` when it has no report. The returned snapshot includes `message`, `level`, `active`, and `run_id`.

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Vehicles & Modules*
