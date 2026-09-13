# Data Types: Fleet And Vehicles

Complete property specifications, descriptions, units, and return types from the official documentation.

## Index

- [`BlockedContact`](#blockedcontact) (FLEET & VEHICLES)
- [`CollectResult`](#collectresult) (FLEET & VEHICLES)
- [`ConstructorModule`](#constructormodule) (FLEET & VEHICLES)
- [`DrillModule`](#drillmodule) (FLEET & VEHICLES)
- [`DroneBattery`](#dronebattery) (FLEET & VEHICLES)
- [`DroneCargo`](#dronecargo) (FLEET & VEHICLES)
- [`DroneOilTank`](#droneoiltank) (FLEET & VEHICLES)
- [`Fleet`](#fleet) (FLEET & VEHICLES)
- [`DroneRef`](#droneref) (FLEET & VEHICLES)
- [`MobileUnitRef`](#mobileunitref) (FLEET & VEHICLES)
- [`VehicleRef`](#vehicleref) (FLEET & VEHICLES)
- [`MountSlot`](#mountslot) (FLEET & VEHICLES)
- [`NavModule`](#navmodule) (FLEET & VEHICLES)
- [`SonarModule`](#sonarmodule) (FLEET & VEHICLES)
- [`SonarScanResult`](#sonarscanresult) (FLEET & VEHICLES)
- [`SurveyResult`](#surveyresult) (FLEET & VEHICLES)

---

## BlockedContact

**Returned by:** SonarScanResult.blocked

### Properties

##### `.x`

Whole-number X coordinate (meters from base) of the unidentified contact, matching the `"?"` marker on the map.

- **Returns** `number`

##### `.y`

Whole-number Y coordinate (meters from base) of the unidentified contact.

- **Returns** `number`

##### `.reason`

Why this sonar could not identify the contact. `"wrong_scanner"` needs a different instrument entirely, such as a drone bio-scan for a biomass contact. `"too_hard"` exceeds the mounted sonar's hardness limit, `"tier_too_low"` needs a higher sonar tier, and `"research_required"` needs a classification technology that is not unlocked.

- **Returns** `string`
- **Possible values** `"wrong_scanner"`, `"too_hard"`, `"tier_too_low"`, `"research_required"`

##### `.message`

Readable explanation of `.reason`, suitable for printing straight to the console.

- **Returns** `string`

*Types / Fleet & Vehicles*

---

## CollectResult

**Returned by:** drone_small.collect(), drone_medium.collect(), drone_large.collect()

### Properties

##### `.status`

Stable collection outcome: `"ok"`, `"moving"`, `"busy"`, `"nothing_here"`, `"no_cargo_space"`, or `"scrambled"`.

- **Returns** `string`
- **Possible values** `"ok"`, `"moving"`, `"busy"`, `"nothing_here"`, `"no_cargo_space"`, `"scrambled"`

##### `.message`

Player-readable explanation of the exact collection outcome.

- **Returns** `string`

##### `.item_id`

Stable id of the collected material, or `None` when no material was collected.

- **Returns** `Optional[string]`

##### `.collected`

Whole-number units committed to drone cargo by this call.

- **Returns** `number`

*Types / Fleet & Vehicles*

---

## ConstructorModule

**Returned by:** self.constructor (Pioneer)

### Methods

##### `.execute(blueprint_id)`

Execute a Plan Mode construction or deconstruction blueprint. Drive the Pioneer within interaction range of `blueprint.position`, then pass a blueprint id from `get_component("construction_blueprint").pending_constructions()`, `.active_constructions()`, or `.paused_constructions()`. Yielding. One Pioneer performs one field action at a time. Stop, power loss, leaving the site, rescue, or removing the Constructor Module pauses paid work without losing progress or materials. The owning Pioneer can rejoin active work, including after save/load; another Pioneer cannot steal an owned job.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `blueprint_id` | `string` | Pending, active, or paused blueprint id from the construction_blueprint queue. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_mounted"` | rejection | The required module is not mounted. |
| `"not_found"` | rejection | The requested object, target, or record does not exist. |
| `"locked"` | rejection | The required feature, recipe, or operation is locked. |
| `"already_active"` | transient | The requested operation is already active. |
| `"busy"` | transient | The component is already performing another operation. |
| `"wrong_position"` | rejection | The worker is not at the operation's required position. |
| `"insufficient_materials"` | rejection | The Pioneer does not have enough of the required construction material in cargo. |
| `"paused_no_power"` | transient | The operation is paused because power is unavailable. |
| `"cargo_present"` | rejection | Existing cargo prevents the requested configuration change. |
| `"blocked"` | rejection | The operation is blocked by the current world state. |
| `"paused"` | transient | The operation is paused. |
| `"canceled"` | rejection | The operation was canceled. |
| `"not_ready"` | rejection | The operation's prerequisites are not currently satisfied. |

*Types / Fleet & Vehicles*

---

## DrillModule

**Returned by:** self.drill (vehicles)

### Methods

##### `.mine()`

Drill one unit while stationary.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_mounted"` | rejection | The required module is not mounted. |
| `"not_at_site"` | rejection | The vehicle is not positioned at a compatible site. |
| `"not_surveyed"` | rejection | The mineral site has not been surveyed. |
| `"too_hard"` | rejection | The target exceeds the mounted tool's hardness limit. |
| `"no_cargo_space"` | rejection | Cargo has no compatible space for the result. |
| `"no_power"` | transient | The component has no available power. |
| `"not_enough_power"` | rejection | The available energy is below the operation's requirement. |
| `"busy"` | transient | The component is already performing another operation. |

##### `.hardness_limit()`

Max mineral hardness this drill can extract (**1** basic, **3** Industrial, **4** Heavy). A stale captured module reference raises `ReferenceError`.

- **Returns** `number`

*Raises*

| Exception | Condition |
| --- | --- |
| `ReferenceError` | This DrillModule reference is stale because its module is no longer mounted. Read self.drill again after mounting a drill. |

##### `.speed_multiplier()`

Drill-time multiplier (**1.0** basic, **0.75** Industrial, **0.6** Heavy: lower is faster). A stale captured module reference raises `ReferenceError`.

- **Returns** `number`

*Raises*

| Exception | Condition |
| --- | --- |
| `ReferenceError` | This DrillModule reference is stale because its module is no longer mounted. Read self.drill again after mounting a drill. |

*Types / Fleet & Vehicles*

---

## DroneBattery

**Returned by:** self.battery (electric drones)

### Methods

##### `.level()`

Current charge in Wh across mounted Battery Packs. Raises `ReferenceError` when this drone does not have an electric powertrain.

- **Returns** `number`

*Raises*

| Exception | Condition |
| --- | --- |
| `ReferenceError` | This drone does not currently have an electric powertrain and mounted Battery Pack. |

##### `.capacity()`

Total charge capacity in Wh. Raises `ReferenceError` when this drone does not have an electric powertrain.

- **Returns** `number`

*Raises*

| Exception | Condition |
| --- | --- |
| `ReferenceError` | This drone does not currently have an electric powertrain and mounted Battery Pack. |

##### `.percent()`

Charge as a fraction **0-1** (`level / capacity`). Raises `ReferenceError` when this drone does not have an electric powertrain.

- **Returns** `number`

*Raises*

| Exception | Condition |
| --- | --- |
| `ReferenceError` | This drone does not currently have an electric powertrain and mounted Battery Pack. |

*Types / Fleet & Vehicles*

---

## DroneCargo

**Returned by:** self.cargo (drones)

### Methods

##### `.count()`

Total units across every Cargo Pod plus the Bio Extractor chamber.

- **Returns** `number`

##### `.capacity()`

Total physical capacity summed over every container: each mounted Cargo Pod (Small **100**, Medium **250**, Large **500**) plus the Bio Extractor's **25 t** chamber. Shield Plating halves each pod's capacity.

- **Returns** `number`

##### `.contents()`

Dict mapping `item_id` → unit count for every material currently in cargo. Iterate with `.keys()` / `.items()`.

- **Returns** `dict<number>`

##### `.space_for(item_id)`

Free room for this specific material. **Each Cargo Pod holds one material**, so a pod counts only if it is empty or already holds `item_id`; the Bio Extractor's 25 t chamber counts only for life forms. Returns **0** for a material with no empty or matching pod, even while other pods still have room for their own materials.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `string` | Item id to size remaining room for |

- **Returns** `number`

##### `.full()`

`True` when `count() >= capacity()`. A drone may still be unable to load a new item type when every pod is committed, even if `full()` is `False`; use `space_for(item_id)` for a specific item.

- **Returns** `boolean`

##### `.load(item_id, count, properties=None, property_match=None)`

Move up to whole-number `count` units into this drone's cargo, retaining exact properties. Loads from the docked Drone Depot stockpile or a field Mining Drill after the drone finishes its route there. Hot cargo loads from a local Lead Cask and requires Shield Plating.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `string` | Item id to load |
| `count` | `number` | Whole-number maximum units to load |
| `properties` | `any` | Optional property dict, matched as a subset by default. Omitted or `None` matches any properties; use `None` with `property_match="exact"` to select propertyless items only. |
| `property_match` | `string` | Optional selection mode: any, subset, or exact |

- **Returns** `TransferResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.requested`, `.moved`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Moved all `.moved` requested units. |
| `"partial"` | partial | Moved `.moved` of `.requested` requested units; source availability or destination capacity limited the transfer. |
| `"no_op"` | success | No units were requested, so no state changed. |
| `"invalid_properties"` | rejection | The item property selector has an invalid shape or value. |
| `"invalid_property_match"` | rejection | The requested property matching mode is invalid. |
| `"research_required"` | rejection | The required material-transfer research is not unlocked. |
| `"target_moving"` | transient | The destination vehicle must stop before cargo can be handed off. |
| `"not_at_source"` | rejection | The vehicle is outside the source's service area. |
| `"source_empty"` | rejection | The source has no matching units available. |
| `"target_full"` | rejection | The destination has no capacity for matching units. |
| `"needs_plating"` | rejection | This hot cargo requires Shield Plating on the drone. |
| `"cask_missing"` | rejection | No compatible Lead Cask is available at this outpost. |
| `"source_changed"` | transient | The source changed between transfer planning and commit. |
| `"target_changed"` | transient | The destination changed between transfer planning and commit. |

##### `.unload(item_id, count, properties=None, property_match=None)`

Move up to whole-number `count` units from this drone's cargo into its docked Drone Depot, retaining exact properties. Hot cargo unloads into a compatible Lead Cask.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `string` | Item id to unload |
| `count` | `number` | Whole-number maximum units to unload |
| `properties` | `any` | Optional property dict, matched as a subset by default. Omitted or `None` matches any properties; use `None` with `property_match="exact"` to select propertyless items only. |
| `property_match` | `string` | Optional selection mode: any, subset, or exact |

- **Returns** `TransferResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.requested`, `.moved`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Moved all `.moved` requested units. |
| `"partial"` | partial | Moved `.moved` of `.requested` requested units; source availability or destination capacity limited the transfer. |
| `"no_op"` | success | No units were requested, so no state changed. |
| `"invalid_properties"` | rejection | The item property selector has an invalid shape or value. |
| `"invalid_property_match"` | rejection | The requested property matching mode is invalid. |
| `"research_required"` | rejection | The required material-transfer research is not unlocked. |
| `"not_at_target"` | rejection | The vehicle is outside the target's service area. |
| `"source_empty"` | rejection | The source has no matching units available. |
| `"slots_full"` | rejection | The destination has capacity but no slot for this material identity. |
| `"target_full"` | rejection | The destination has no capacity for matching units. |
| `"cask_missing"` | rejection | No compatible Lead Cask is available at this outpost. |
| `"source_changed"` | transient | The source changed between transfer planning and commit. |
| `"target_changed"` | transient | The destination changed between transfer planning and commit. |

##### `.discard(item_id, count, properties=None, property_match=None)`

Permanently destroy up to whole-number `count` units from this drone's cargo. This jettison needs no station and a drained pod unlatches for a new material.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `string` | Item id to destroy |
| `count` | `number` | Whole-number maximum units to destroy |
| `properties` | `any` | Optional property dict, matched as a subset by default. Omitted or `None` matches any properties; use `None` with `property_match="exact"` to select propertyless items only. |
| `property_match` | `string` | Optional selection mode: any, subset, or exact |

- **Returns** `DiscardResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.requested`, `.discarded`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Permanently discarded `.discarded` units. |
| `"partial"` | partial | Permanently discarded `.discarded` of `.requested` requested units. |
| `"empty"` | success | The selected cargo area was already empty. |
| `"no_op"` | success | No units were requested, so nothing was discarded. |
| `"invalid_properties"` | rejection | The item property selector has an invalid shape or value. |
| `"invalid_property_match"` | rejection | The requested property matching mode is invalid. |
| `"source_changed"` | transient | Cargo changed between transfer planning and commit. |

*Types / Fleet & Vehicles*

---

## DroneOilTank

**Returned by:** self.oil_tank (heli drones)

### Methods

##### `.level()`

Current oil in tons across mounted Oil Tanks. Raises `ReferenceError` when this drone does not have a heli powertrain.

- **Returns** `number`

*Raises*

| Exception | Condition |
| --- | --- |
| `ReferenceError` | This drone does not currently have a heli powertrain. |

##### `.capacity()`

Total oil capacity in tons. Raises `ReferenceError` when this drone does not have a heli powertrain.

- **Returns** `number`

*Raises*

| Exception | Condition |
| --- | --- |
| `ReferenceError` | This drone does not currently have a heli powertrain. |

##### `.percent()`

Oil as a fraction **0-1**. Raises `ReferenceError` when this drone does not have a heli powertrain.

- **Returns** `number`

*Raises*

| Exception | Condition |
| --- | --- |
| `ReferenceError` | This drone does not currently have a heli powertrain. |

*Types / Fleet & Vehicles*

---

## Fleet

**Returned by:** get_component("fleet")

### Related object types

- `DroneRef`
- `MobileUnitRef`
- `VehicleRef`

### Methods

##### `.vehicles()`

All owned ground vehicles as read-only `VehicleRef` snapshots. Use `.id` when passing a vehicle to station APIs; call `vehicles()` again for fresh ref fields, or `get_component(ref.id)` for the live vehicle API.

- **Returns** `list<VehicleRef>`

##### `.drones()`

All owned drones as read-only `DroneRef` snapshots. Use `.id` when passing a drone to station/recovery APIs; call `drones()` again for fresh ref fields, or `get_component(ref.id)` for the live drone API.

- **Returns** `list<DroneRef>`

##### `.mobile_units()`

All owned vehicles and drones in one snapshot list. Use `.category` to branch between `"vehicle"` and `"drone"`; re-query for fresh positions/status.

- **Returns** `list<MobileUnitRef>`

*Types / Fleet & Vehicles*

---

## DroneRef

**Returned by:** fleet.drones()

### Properties

##### `.category`

Always `"drone"`.

- **Returns** `string`
- **Possible values** `"drone"`

##### `.id`

Stable component id. Use with `get_component(id)` or pass it to Drone Service Station and Depot APIs.

- **Returns** `string`

##### `.name`

Display name when this ref was returned.

- **Returns** `string`

##### `.kind`

Drone chassis id.

- **Returns** `string`
- **Possible values** `"drone_small"`, `"drone_medium"`, `"drone_large"`

##### `.engine`

`"electric"`, `"heli"`, or empty string if no thruster is mounted.

- **Returns** `string`
- **Possible values** `""`, `"electric"`, `"heli"`

##### `.status`

Activity/status string when this ref was returned.

- **Returns** `string`
- **Possible values** `"idle"`, `"traveling"`, `"charging"`, `"refueling"`, `"waiting_service"`, `"waiting_oil"`, `"waiting_bay"`, `"being_rescued"`, `"holding_weather"`, `"scrambled"`, `"stalled_no_battery"`, `"stalled_no_oil"`, `"stalled_no_route"`

##### `.x`

X coordinate in meters from base when this ref was returned.

- **Returns** `number`

##### `.y`

Y coordinate in meters from base when this ref was returned.

- **Returns** `number`

##### `.current_station`

Station id when this ref was returned, or empty string.

- **Returns** `string`

##### `.is_docked`

`True` if the drone was parked at a drone station when this ref was returned.

- **Returns** `boolean`

##### `.battery_level`

Electric drone charge fraction **0-1** when this ref was returned, or `None` for heli drones.

- **Returns** `Optional[number]`

##### `.battery_wh`

Electric drone charge in Wh when this ref was returned, or `None` for heli drones.

- **Returns** `Optional[number]`

##### `.battery_capacity`

Electric drone charge capacity in Wh, or `None` for heli drones.

- **Returns** `Optional[number]`

##### `.oil_level`

Heli drone oil fraction **0-1** when this ref was returned, or `None` for electric drones.

- **Returns** `Optional[number]`

##### `.oil_tons`

Heli drone oil in tons when this ref was returned, or `None` for electric drones.

- **Returns** `Optional[number]`

##### `.oil_capacity`

Heli drone oil capacity in tons, or `None` for electric drones.

- **Returns** `Optional[number]`

##### `.is_being_rescued`

`True` if a Drone Service Station rescue was active for this drone when this ref was returned.

- **Returns** `boolean`

##### `.rescue_status`

Rescue status when this ref was returned: `"none"`, `"outbound"`, `"charging"`, `"carrying"`, or `"returning"`.

- **Returns** `string`
- **Possible values** `"none"`, `"outbound"`, `"charging"`, `"carrying"`, `"returning"`

### Methods

##### `.position()`

Position snapshot from when this ref was returned.

- **Returns** `Position`

*Types / Fleet & Vehicles*

---

## MobileUnitRef

**Returned by:** fleet.mobile_units()

### Properties

##### `.category`

`"vehicle"` or `"drone"`.

- **Returns** `string`
- **Possible values** `"vehicle"`, `"drone"`

##### `.id`

Stable component id. Use with `get_component(id)` or station APIs.

- **Returns** `string`

##### `.name`

Display name when this ref was returned.

- **Returns** `string`

##### `.kind`

Unit type, e.g. `"rover"`, `"pioneer"`, or a drone chassis id.

- **Returns** `string`
- **Possible values** `"rover"`, `"pioneer"`, `"drone_small"`, `"drone_medium"`, `"drone_large"`

##### `.status`

Activity/status string when this ref was returned.

- **Returns** `string`
- **Possible values** `"idle"`, `"moving"`, `"stranded"`, `"scanning"`, `"surveying"`, `"drilling"`, `"discarding"`, `"constructing"`, `"transferring"`, `"charging"`, `"queued"`, `"being_rescued"`, `"traveling"`, `"refueling"`, `"waiting_service"`, `"waiting_oil"`, `"waiting_bay"`, `"holding_weather"`, `"scrambled"`, `"stalled_no_battery"`, `"stalled_no_oil"`, `"stalled_no_route"`

##### `.x`

X coordinate in meters from base when this ref was returned.

- **Returns** `number`

##### `.y`

Y coordinate in meters from base when this ref was returned.

- **Returns** `number`

##### `.is_docked`

`True` if the unit was parked at a service point/station when this ref was returned.

- **Returns** `boolean`

##### `.is_being_rescued`

`True` if a rescue/recovery mission owned this unit when this ref was returned.

- **Returns** `boolean`

##### `.rescue_status`

Rescue status when this ref was returned: `"none"`, `"outbound"`, `"charging"`, `"carrying"`, or `"returning"`.

- **Returns** `string`
- **Possible values** `"none"`, `"outbound"`, `"charging"`, `"carrying"`, `"returning"`

### Methods

##### `.position()`

Position snapshot from when this ref was returned.

- **Returns** `Position`

*Types / Fleet & Vehicles*

---

## VehicleRef

**Returned by:** fleet.vehicles()

### Properties

##### `.category`

Always `"vehicle"`.

- **Returns** `string`
- **Possible values** `"vehicle"`

##### `.id`

Stable component id. Use with `get_component(id)` or `charging_station.dispatch_rescue(id)`.

- **Returns** `string`

##### `.name`

Display name when this ref was returned.

- **Returns** `string`

##### `.kind`

`"rover"` or `"pioneer"`.

- **Returns** `string`
- **Possible values** `"rover"`, `"pioneer"`

##### `.status`

Current vehicle activity when this ref was returned.

- **Returns** `string`
- **Possible values** `"idle"`, `"moving"`, `"stranded"`, `"scanning"`, `"surveying"`, `"drilling"`, `"discarding"`, `"constructing"`, `"transferring"`, `"charging"`, `"queued"`, `"being_rescued"`

##### `.x`

X coordinate in meters from base when this ref was returned.

- **Returns** `number`

##### `.y`

Y coordinate in meters from base when this ref was returned.

- **Returns** `number`

##### `.battery_level`

Battery fraction **0-1** when this ref was returned.

- **Returns** `number`

##### `.battery_wh`

Battery charge in Wh when this ref was returned.

- **Returns** `number`

##### `.battery_capacity`

Maximum battery capacity in Wh.

- **Returns** `number`

##### `.is_docked`

`True` if the vehicle was parked inside an outpost's **2 by 2-tile footprint**, including the **~2 m** service margin, when this ref was returned. A moving or merely stopped vehicle with an active route is not docked.

- **Returns** `boolean`

##### `.docked_at`

Outpost id when this ref was returned, or empty string.

- **Returns** `string`

##### `.is_being_rescued`

`True` if a Vehicle Charging Station rescue was active for this vehicle when this ref was returned.

- **Returns** `boolean`

##### `.rescue_status`

Rescue status when this ref was returned: `"none"`, `"outbound"`, `"charging"`, or `"returning"`.

- **Returns** `string`
- **Possible values** `"none"`, `"outbound"`, `"charging"`, `"returning"`

### Methods

##### `.position()`

Position snapshot from when this ref was returned.

- **Returns** `Position`

*Types / Fleet & Vehicles*

---

## MountSlot

**Returned by:** self.modules() on rover / pioneer

### Properties

##### `.index`

Slot position on the chassis, 0-indexed.

- **Returns** `number`

##### `.type`

Slot's type: determines which modules fit (`nav`, `sonar_basic`, `drill_basic`, `universal`, `thruster`, or `drone_module`).

- **Returns** `string`
- **Possible values** `"nav"`, `"sonar_basic"`, `"drill_basic"`, `"universal"`, `"thruster"`, `"drone_module"`

##### `.module_id`

Module id currently mounted in this slot, or `None` if empty.

- **Returns** `Optional[string]`

##### `.internal_count`

Number of internal slots this mounted module exposes. `0` for non-container modules.

- **Returns** `number`

##### `.internal_items`

List of item ids currently installed in this module's internal slots. `None` entries mark empty internal slots.

- **Returns** `list<Optional[string]>`

*Types / Fleet & Vehicles*

---

## NavModule

**Returned by:** self.nav (vehicles)

### Methods

##### `.set_target(x, y)`

Set target coordinates to drive toward.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | Target X coordinate |
| `y` | `number` | Target Y coordinate |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_mounted"` | rejection | The required module is not mounted. |
| `"invalid"` | rejection | One or more supplied arguments are outside the accepted domain. |
| `"out_of_bounds"` | rejection | The requested position lies outside the valid world bounds. |
| `"busy"` | transient | The component is already performing another operation. |

##### `.set_throttle(power)`

Set throttle (0.0-1.0; clamped).

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `power` | `number` | Throttle power (0.0-1.0) |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_mounted"` | rejection | The required module is not mounted. |
| `"busy"` | transient | The component is already performing another operation. |

##### `.throttle()`

Current throttle setpoint (**0.0-1.0**). Returns the value the script last wrote via `set_throttle(...)`. Distinct from `get_speed()`: `throttle()` is intent (does not change tick-to-tick); `get_speed()` is what the vehicle actually moved last tick.

- **Returns** `number`

##### `.brake()`

Stop the vehicle (throttle set to 0).

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_mounted"` | rejection | The required module is not mounted. |

##### `.get_position()`

Vehicle position as a `Position` object with `.x` and `.y`.

- **Returns** `Position`

##### `.get_speed()`

Vehicle speed in m/h.

- **Returns** `number`

##### `.get_distance_to(x, y)`

Distance (meters) from the vehicle to the given point. Arrival loops need a tolerance, normally `> 2`, rather than exact zero. When the next action targets a building, route to its `BuildingRef.position`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | Target X coordinate |
| `y` | `number` | Target Y coordinate |

- **Returns** `number`

##### `.speed_multiplier()`

Top-speed multiplier: **1.0** basic, or **1 + mounted Sport Nav count** on Pioneer. Speed only; range still depends on battery, throttle, cargo load, and movement draw.

- **Returns** `number`

*Types / Fleet & Vehicles*

---

## SonarModule

**Returned by:** self.sonar (vehicles)

### Methods

##### `.scan()`

Point-sweep for nearby sites. A completed sweep can find no compatible contacts. Mineral contacts obey sonar range and hardness; thermal, water, oil, and exotic contacts also require matching research. The sweep updates the Journal with newly classified sites. A stale captured module reference raises `ReferenceError`.

- **Returns** `SonarScanResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.sites`, `.blocked`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The sonar sweep completed. `result.sites` contains every compatible contact found; an empty list means there were no compatible contacts in range. |
| `"too_hard"` | partial | The completed sweep detected a nearby unresolved contact above the mounted sonar's hardness limit. |
| `"tier_too_low"` | partial | The completed sweep detected a nearby unresolved contact that the mounted sonar tier cannot classify. |
| `"research_required"` | partial | The completed sweep detected a nearby unresolved contact whose classification research is not unlocked. |
| `"wrong_scanner"` | partial | The completed sweep detected a nearby contact that vehicle sonar cannot classify. |
| `"busy"` | transient | Another field action currently occupies the vehicle. |
| `"no_power"` | rejection | The vehicle battery does not contain enough energy for a sonar sweep. |

*Raises*

| Exception | Condition |
| --- | --- |
| `ReferenceError` | This SonarModule reference is stale because its module is no longer mounted. Read self.sonar again after mounting a sonar. |

##### `.survey(site)`

Reveal the details available for a productive site. An inert `GeologicalAnomaly` is already resolved, so surveying it is free. Re-surveying is also free unless a deeper sonar tier can reveal more. Malformed site values raise `ValueError`; a stale captured module reference raises `ReferenceError`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `site` | `any` | Site id string or a `Site` from `scan()` |

- **Returns** `SurveyResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.site`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Surveyed `site_id` successfully. |
| `"busy"` | transient | Another field action currently occupies the vehicle. |
| `"not_discovered"` | rejection | Site `site_id` is not in this planet's discovered-site journal. |
| `"research_required"` | rejection | Site `site_id` requires research that is not currently unlocked. |
| `"tier_too_low"` | rejection | The mounted sonar tier cannot survey site `site_id`. |
| `"out_of_range"` | rejection | Site `site_id` is outside the mounted sonar's current range. |
| `"too_hard"` | rejection | Site `site_id` exceeds the mounted sonar's mineral hardness limit. |
| `"no_power"` | rejection | The vehicle battery does not contain enough energy to survey site `site_id`. |

*Raises*

| Exception | Condition |
| --- | --- |
| `ValueError` | survey() requires a non-empty site id or a Site object. |
| `ReferenceError` | This SonarModule reference is stale because its module is no longer mounted. Read self.sonar again after mounting a sonar. |

##### `.range()`

Sonar range in meters (**50** basic, **180** Wide, **280** Deep). A stale captured module reference raises `ReferenceError`.

- **Returns** `number`

*Raises*

| Exception | Condition |
| --- | --- |
| `ReferenceError` | This SonarModule reference is stale because its module is no longer mounted. Read self.sonar again after mounting a sonar. |

##### `.hardness_limit()`

Max mineral hardness this sonar can identify (**1** basic, **3** Wide, **4** Deep). A stale captured module reference raises `ReferenceError`.

- **Returns** `number`

*Raises*

| Exception | Condition |
| --- | --- |
| `ReferenceError` | This SonarModule reference is stale because its module is no longer mounted. Read self.sonar again after mounting a sonar. |

##### `.tier()`

Survey-depth tier granted by the mounted sonar: `"basic"` / `"wide"` / `"deep"`. Determines thermal/exotic survey detail; `"deep"` is also required to discover oil wells once **Petroleum Survey** is unlocked. A stale captured module reference raises `ReferenceError`.

- **Returns** `string`
- **Possible values** `"basic"`, `"wide"`, `"deep"`

*Raises*

| Exception | Condition |
| --- | --- |
| `ReferenceError` | This SonarModule reference is stale because its module is no longer mounted. Read self.sonar again after mounting a sonar. |

*Types / Fleet & Vehicles*

---

## SonarScanResult

**Returned by:** SonarModule.scan()

### Properties

##### `.status`

Stable sweep outcome. An empty `.sites` list with `"ok"` is a completed sweep with no contacts requiring player action.

- **Returns** `string`
- **Possible values** `"ok"`, `"too_hard"`, `"tier_too_low"`, `"research_required"`, `"wrong_scanner"`, `"busy"`, `"no_power"`

##### `.message`

Player-readable explanation of the sweep outcome.

- **Returns** `string`

##### `.sites`

Sites resolved by this completed sweep; empty when no compatible site was returned.

- **Returns** `list<Site>`

##### `.blocked`

Contacts the sweep detected but this sonar cannot identify, nearest first, and empty when everything in range was identified. A contact appears here instead of in `.sites`, so the two lists never overlap. Each entry carries `.x`, `.y`, a `.reason` code, and a readable `.message`. This is how a script tells an unreachable contact apart from empty ground: `.status` describes the sweep itself and stays `"ok"` whenever any site was identified.

- **Returns** `list<BlockedContact>`

*Types / Fleet & Vehicles*

---

## SurveyResult

**Returned by:** SonarModule.survey()

### Properties

##### `.status`

`"ok"`, `"busy"`, `"not_discovered"`, `"research_required"`, `"tier_too_low"`, `"out_of_range"`, `"too_hard"`, or `"no_power"`.

- **Returns** `string`
- **Possible values** `"ok"`, `"busy"`, `"not_discovered"`, `"research_required"`, `"tier_too_low"`, `"out_of_range"`, `"too_hard"`, `"no_power"`

##### `.message`

Player-readable, exact explanation of the survey outcome.

- **Returns** `string`

##### `.site`

Surveyed concrete `Site`, or `None` when the survey was rejected.

- **Returns** `Optional[Site]`

*Types / Infrastructure & Fluids*

---
