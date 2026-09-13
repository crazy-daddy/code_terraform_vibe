# Models: Vehicles, Modules, Harvester & Navigation Models

Granular data models and return types extracted from `__builtins__.pyi`.

## `ConstructorModule`

```python
class ConstructorModule:
 """self.constructor (Pioneer)"""
 def execute(self, blueprint_id: _str) -> ActionResult[Literal["ok", "not_mounted", "not_found", "locked", "already_active", "busy", "wrong_position", "insufficient_materials", "paused_no_power", "cargo_present", "blocked", "paused", "canceled", "not_ready"]]:
 """Execute a Plan Mode construction or deconstruction blueprint. Drive the Pioneer within interaction range of `blueprint.position`, then pass a blueprint id from `get_component(\"construction_blueprint\").pending_constructions()`, `.active_constructions()`, or `.paused_constructions()`. Yielding. One Pioneer performs one field action at a time. Stop, power loss, leaving the site, rescue, or removing the Constructor Module pauses paid work without losing progress or materials. The owning Pioneer can rejoin active work, including after save/load; another Pioneer cannot steal an owned job. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
```

## `ConstructorModuleComponent`

```python
class ConstructorModuleComponent(Component):
 """Constructor Module: Pioneer-exclusive module for construction and deconstruction blueprints created in Plan Mode or by scripts: gas/liquid pipes, utility bridges, power lines, outposts, pumps, caps, and mining drills. Fits a `universal` slot. Load the required kits, segments, or bridge items into the Pioneer's cargo for build jobs, drive within interaction range of the blueprint position, then call `execute(blueprint_id)`. Deconstruction reclaims the dismantled kit or segment into the Pioneer's cargo. Internal outpost machines, including drone facilities, deploy directly from Inventory and are not Constructor jobs."""
 name: _str
 def execute(self, blueprint_id: _str) -> ActionResult[Literal["ok", "not_mounted", "not_found", "locked", "already_active", "busy", "wrong_position", "insufficient_materials", "paused_no_power", "cargo_present", "blocked", "paused", "canceled", "not_ready"]]:
 """Pick up one Construction job from the shared planning queue and build or deconstruct it. Plan Mode and `get_component(\"construction_blueprint\")` create equivalent jobs. Drive the Pioneer within interaction range of `blueprint.position` first, and use `get_component(\"construction_blueprint\").pending_constructions()` to see what's ready. A Pioneer performs only one field action at a time. Stop, power loss, leaving the site, rescue, or removing the Constructor Module pauses paid work without losing its progress or materials. Resume the same id from `get_component(\"construction_blueprint\").paused_constructions()`. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
```

## `DrillModule`

```python
class DrillModule:
 """self.drill (vehicles)"""
 def mine(self) -> ActionResult[Literal["ok", "not_mounted", "not_at_site", "not_surveyed", "too_hard", "no_cargo_space", "no_power", "not_enough_power", "busy"]]:
 """Drill one unit while stationary. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def hardness_limit(self) -> _float:
 """Max mineral hardness this drill can extract (**1** basic, **3** Industrial, **4** Heavy). A stale captured module reference raises `ReferenceError`."""
 ...
 def speed_multiplier(self) -> _float:
 """Drill-time multiplier (**1.0** basic, **0.75** Industrial, **0.6** Heavy: lower is faster). A stale captured module reference raises `ReferenceError`."""
 ...
```

## `DrillModuleComponent`

```python
class DrillModuleComponent(Component):
 """Drill Module: Extracts minerals through `self.drill`. The basic drill handles hardness **1** at **1.0×** speed using **10 W**; Industrial handles hardness **3** at **0.75×** using **20 W**; Heavy handles hardness **4** at **0.6×** using **30 W**. Without a mounted Drill Module, the vehicle cannot mine."""
 name: _str
 def mine(self) -> ActionResult[Literal["ok", "not_mounted", "not_at_site", "not_surveyed", "too_hard", "no_cargo_space", "no_power", "not_enough_power", "busy"]]:
 """Extract **1** unit of the current site's mineral into vehicle cargo. Mining takes `mineral_base_minutes × drill.speed_multiplier() / site_purity` game-time, and the script pauses until it finishes. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def hardness_limit(self) -> _float:
 """Maximum mineral hardness this drill can extract."""
 ...
 def speed_multiplier(self) -> _float:
 """Per-unit time multiplier (lower = faster)."""
 ...
```

## `DroneBattery`

```python
class DroneBattery:
 """self.battery (electric drones)"""
 def level(self) -> _float:
 """Current charge in Wh across mounted Battery Packs. Raises `ReferenceError` when this drone does not have an electric powertrain."""
 ...
 def capacity(self) -> _float:
 """Total charge capacity in Wh. Raises `ReferenceError` when this drone does not have an electric powertrain."""
 ...
 def percent(self) -> _float:
 """Charge as a fraction **0-1** (`level / capacity`). Raises `ReferenceError` when this drone does not have an electric powertrain."""
 ...
```

## `DroneLarge`

```python
class DroneLarge(Component):
 """Drone (Large): Heavy industrial drone, 1 thruster + 5 modules."""
 name: _str
 def go_to_station(self, name: _str) -> ActionResult[Literal["ok", "station_not_found", "out_of_range", "busy", "scrambled"]]:
 """Queue a route to the named Drone Depot or Drone Service Station and return immediately without waiting for docking. An accepted powered route reports `\"traveling\"` immediately; position and docking advance after simulation advances. Stop, completion, or error cancels the flight and clears the route. Compare `current_station()` with the destination's stable id to confirm arrival. Moving between drone buildings inside the same outpost is a local transfer and costs no flight fuel. Drone Service Stations accept parked arrivals even while unpowered. A full Drone Depot keeps the drone undocked in `\"waiting_bay\"` until a physical bay opens. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def undock(self) -> ActionResult[Literal["ok", "not_docked", "busy"]]:
 """Release the station berth without flying anywhere. The drone keeps its exact world position, cargo, modules, fuel, and exposure, clears any dormant route, resets throttle to **0**, and becomes idle. An active rescue, or an active or queued Drone Service Station charge/refuel job, retains control until that station-owned work ends. Use `go_to_station(...)` when the drone should claim a berth again. Self-only. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def go_to_drill(self, name: _str) -> ActionResult[Literal["ok", "drill_not_found", "out_of_range", "busy", "scrambled"]]:
 """Fly to a named field Mining Drill for ore pickup. Hauling needs no field module. An accepted powered route reports `\"traveling\"` immediately, then the drone flies in a straight line and hovers on arrival. Compare `current_drill()` with the destination's stable id to confirm that cargo loading is available. Stopping or completing the script, hitting an error, or calling `go_to_station()` cancels this route. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def current_station(self) -> _str:
 """Stable station id where the drone is physically docked. Returns an empty string while flying to coordinates, traveling between stations, or waiting outside a full Drone Depot. Use equality with the destination id as the authoritative station-arrival check, even when `go_to_station()` was called with a display name."""
 ...
 def current_drill(self) -> _str:
 """Stable Mining Drill id where the drone can currently load cargo, or an empty string when no Drill is available. The drone must be within the Drill's loading area with no active route; merely passing over the Drill or holding a zero-throttle route does not count. Compare this value with the destination id as the authoritative Drill-arrival check, even when `go_to_drill()` was called with a display name."""
 ...
 def position(self) -> Position:
 """World coordinates `(.x, .y)`, lerped each tick by DroneSystem during transit, snapped to station coords on dock."""
 ...
 def get_distance_to(self, x: _float, y: _float) -> _float:
 """Straight-line distance in meters from the drone's current position to the given world coordinate. Use it to compare possible destinations, check remaining route distance, or pair it with `range_remaining()` before dispatch. It measures geometry only and does not select a destination or account for available fuel."""
 ...
 battery: DroneBattery
 oil_tank: DroneOilTank
 cargo: DroneCargo
 def go_to(self, x: _float, y: _float) -> ActionResult[Literal["ok", "invalid_target", "out_of_bounds", "out_of_range", "busy", "scrambled"]]:
 """Fly to any world coordinate as a base drone capability; no field module is required. An accepted powered route reports `\"traveling\"` immediately, then the drone flies in a straight line and hovers on arrival. Stopping or completing the script, hitting an error, or calling `go_to_station()` cancels this route. For Weather, pass the exact x and y assembled from checksum-valid storm packets. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 bio_scanner: PortableBioScanner
 bio_extractor: PortableBioExtractor
 def collect(self) -> CollectResult[Literal["ok", "moving", "busy", "nothing_here", "no_cargo_space", "scrambled"]]:
 """Collect one weather aftermath batch at the drone's exact current coordinate. A successful batch transfers at most **5** Storm Glass or Raw Uranium. Raw Uranium collection adds **40** exposure without Shield Plating and **0** with it; the batch is retained even if it reaches the scramble threshold. Fixed result contract: `CollectResult`; branch on `.status` and read `.message`. Payload fields: `.item_id` and `.collected`."""
 ...
 def exposure(self) -> _float:
 """Current extraction exposure, from **0** to `exposure_capacity()`. It changes only when collecting Raw Uranium or receiving Service Station care; simply flying across a hidden aftermath is inert. A working drone docked at a powered Drone Service Station clears **10 per hour**. At capacity the drone is scrambled and requires Service Station rescue."""
 ...
 def exposure_capacity(self) -> _float:
 """The **100** exposure scramble threshold. An unplated drone can collect two 5-unit batches safely; the third batch is retained and then scrambles it."""
 ...
 def is_plated(self) -> _bool:
 """`True` with Shield Plating mounted. Plating reduces Raw Uranium extraction exposure to zero, halves each Cargo Pod's capacity, and raises fuel burn **1.5×** because lead is heavy."""
 ...
 def range_remaining(self) -> _float:
 """Estimated flight distance in meters at the current energy and throttle. Electric burn is **5 Wh/h** at full throttle; Heli burn is **5 t/h Oil**. Both scale with throttle squared, so slower routes stretch range."""
 ...
 def throttle(self) -> _float:
 """Current throttle (**0-1**). Full-throttle burn is **5 Wh/h** for electric propulsion or **5 t/h Oil** for Heli; both scale with throttle squared. Reads **0** after Stop, completion, or error."""
 ...
 def set_throttle(self, rate: _float) -> ActionResult[Literal["ok"]]:
 """Set throttle (**0-1**). At full throttle, electric drones fly **300 m/h** using **5 Wh/h**; Heli drones fly **900 m/h** using **5 t/h Oil**. Lower throttle reduces burn quadratically. Stop, completion, or error resets throttle to **0**. Self-only. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def couple(self, slot_index: _float, module_id: _str) -> ActionResult[Literal["ok", "not_at_station", "item_not_in_inventory", "unknown_module", "slot_not_compatible", "slot_occupied", "invalid_slot", "locked", "wrong_engine_for_module", "cargo_capacity_exceeded"]]:
 """Request a hardware service order from Inventory into an explicit whole-number slot: `self.couple(0, \"electric_thruster\")` for the thruster slot, or `self.couple(1, \"battery_pack\")` for a module slot. The drone must be docked at an operational Drone Depot. This dedicated-hardware exception does not expose ordinary Inventory freight at that outpost. Self-only. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def uncouple(self, slot_index: _float) -> ActionResult[Literal["ok", "invalid_slot", "module_not_mounted", "not_at_station", "cargo_capacity_exceeded", "container_not_empty", "hot_cargo_requires_plating", "inventory_full"]]:
 """Request a hardware service order that returns the module in an explicit whole-number slot to Inventory: `self.uncouple(1)`. The drone must be docked at an operational Drone Depot. Cargo Pods must be empty before removal, and Shield Plating cannot be removed while Raw Uranium or Fuel Rod cargo remains aboard. Fuel-bearing modules preserve their contents. Self-only. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def status(self) -> Literal["idle", "traveling", "charging", "refueling", "waiting_service", "waiting_oil", "waiting_bay", "being_rescued", "holding_weather", "scrambled", "stalled_no_battery", "stalled_no_oil", "stalled_no_route"]:
 """Current operational activity for progress and blocker handling, not an arrival test. `\"idle\"` can mean docked, hovering at a field coordinate, or holding a queued route at zero throttle; charging or refueling can begin immediately after docking. `\"waiting_bay\"` means the drone reached a full Depot but is not docked, `\"holding_weather\"` is a temporary heli hold, and stalled or scrambled states need intervention. Use `current_station()` or `current_drill()` to confirm arrival at an interaction endpoint."""
 ...
 def is_being_rescued(self) -> _bool:
 """`True` while a Drone Service Station is actively servicing or carrying this drone. Use this to pause route scripts while the rescue vehicle has control."""
 ...
 def rescue_status(self) -> Literal["none", "outbound", "charging", "carrying", "returning"]:
 """Current recovery mission phase for this drone: `\"none\"`, `\"outbound\"`, `\"charging\"`, `\"carrying\"`, or `\"returning\"`. `\"returning\"` means the recovery vehicle is heading home and the drone is no longer under rescue control."""
 ...
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

## `DroneMedium`

```python
class DroneMedium(Component):
 """Drone (Medium): Mid-size cargo drone, 1 thruster + 3 modules."""
 name: _str
 def go_to_station(self, name: _str) -> ActionResult[Literal["ok", "station_not_found", "out_of_range", "busy", "scrambled"]]:
 """Queue a route to the named Drone Depot or Drone Service Station and return immediately without waiting for docking. An accepted powered route reports `\"traveling\"` immediately; position and docking advance after simulation advances. Stop, completion, or error cancels the flight and clears the route. Compare `current_station()` with the destination's stable id to confirm arrival. Moving between drone buildings inside the same outpost is a local transfer and costs no flight fuel. Drone Service Stations accept parked arrivals even while unpowered. A full Drone Depot keeps the drone undocked in `\"waiting_bay\"` until a physical bay opens. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def undock(self) -> ActionResult[Literal["ok", "not_docked", "busy"]]:
 """Release the station berth without flying anywhere. The drone keeps its exact world position, cargo, modules, fuel, and exposure, clears any dormant route, resets throttle to **0**, and becomes idle. An active rescue, or an active or queued Drone Service Station charge/refuel job, retains control until that station-owned work ends. Use `go_to_station(...)` when the drone should claim a berth again. Self-only. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def go_to_drill(self, name: _str) -> ActionResult[Literal["ok", "drill_not_found", "out_of_range", "busy", "scrambled"]]:
 """Fly to a named field Mining Drill for ore pickup. Hauling needs no field module. An accepted powered route reports `\"traveling\"` immediately, then the drone flies in a straight line and hovers on arrival. Compare `current_drill()` with the destination's stable id to confirm that cargo loading is available. Stopping or completing the script, hitting an error, or calling `go_to_station()` cancels this route. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def current_station(self) -> _str:
 """Stable station id where the drone is physically docked. Returns an empty string while flying to coordinates, traveling between stations, or waiting outside a full Drone Depot. Use equality with the destination id as the authoritative station-arrival check, even when `go_to_station()` was called with a display name."""
 ...
 def current_drill(self) -> _str:
 """Stable Mining Drill id where the drone can currently load cargo, or an empty string when no Drill is available. The drone must be within the Drill's loading area with no active route; merely passing over the Drill or holding a zero-throttle route does not count. Compare this value with the destination id as the authoritative Drill-arrival check, even when `go_to_drill()` was called with a display name."""
 ...
 def position(self) -> Position:
 """World coordinates `(.x, .y)`, lerped each tick by DroneSystem during transit, snapped to station coords on dock."""
 ...
 def get_distance_to(self, x: _float, y: _float) -> _float:
 """Straight-line distance in meters from the drone's current position to the given world coordinate. Use it to compare possible destinations, check remaining route distance, or pair it with `range_remaining()` before dispatch. It measures geometry only and does not select a destination or account for available fuel."""
 ...
 battery: DroneBattery
 oil_tank: DroneOilTank
 cargo: DroneCargo
 def go_to(self, x: _float, y: _float) -> ActionResult[Literal["ok", "invalid_target", "out_of_bounds", "out_of_range", "busy", "scrambled"]]:
 """Fly to any world coordinate as a base drone capability; no field module is required. An accepted powered route reports `\"traveling\"` immediately, then the drone flies in a straight line and hovers on arrival. Stopping or completing the script, hitting an error, or calling `go_to_station()` cancels this route. For Weather, pass the exact x and y assembled from checksum-valid storm packets. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 bio_scanner: PortableBioScanner
 bio_extractor: PortableBioExtractor
 def collect(self) -> CollectResult[Literal["ok", "moving", "busy", "nothing_here", "no_cargo_space", "scrambled"]]:
 """Collect one weather aftermath batch at the drone's exact current coordinate. A successful batch transfers at most **5** Storm Glass or Raw Uranium. Raw Uranium collection adds **40** exposure without Shield Plating and **0** with it; the batch is retained even if it reaches the scramble threshold. Fixed result contract: `CollectResult`; branch on `.status` and read `.message`. Payload fields: `.item_id` and `.collected`."""
 ...
 def exposure(self) -> _float:
 """Current extraction exposure, from **0** to `exposure_capacity()`. It changes only when collecting Raw Uranium or receiving Service Station care; simply flying across a hidden aftermath is inert. A working drone docked at a powered Drone Service Station clears **10 per hour**. At capacity the drone is scrambled and requires Service Station rescue."""
 ...
 def exposure_capacity(self) -> _float:
 """The **100** exposure scramble threshold. An unplated drone can collect two 5-unit batches safely; the third batch is retained and then scrambles it."""
 ...
 def is_plated(self) -> _bool:
 """`True` with Shield Plating mounted. Plating reduces Raw Uranium extraction exposure to zero, halves each Cargo Pod's capacity, and raises fuel burn **1.5×** because lead is heavy."""
 ...
 def range_remaining(self) -> _float:
 """Estimated flight distance in meters at the current energy and throttle. Electric burn is **5 Wh/h** at full throttle; Heli burn is **5 t/h Oil**. Both scale with throttle squared, so slower routes stretch range."""
 ...
 def throttle(self) -> _float:
 """Current throttle (**0-1**). Full-throttle burn is **5 Wh/h** for electric propulsion or **5 t/h Oil** for Heli; both scale with throttle squared. Reads **0** after Stop, completion, or error."""
 ...
 def set_throttle(self, rate: _float) -> ActionResult[Literal["ok"]]:
 """Set throttle (**0-1**). At full throttle, electric drones fly **300 m/h** using **5 Wh/h**; Heli drones fly **900 m/h** using **5 t/h Oil**. Lower throttle reduces burn quadratically. Stop, completion, or error resets throttle to **0**. Self-only. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def couple(self, slot_index: _float, module_id: _str) -> ActionResult[Literal["ok", "not_at_station", "item_not_in_inventory", "unknown_module", "slot_not_compatible", "slot_occupied", "invalid_slot", "locked", "wrong_engine_for_module", "cargo_capacity_exceeded"]]:
 """Request a hardware service order from Inventory into an explicit whole-number slot: `self.couple(0, \"electric_thruster\")` for the thruster slot, or `self.couple(1, \"battery_pack\")` for a module slot. The drone must be docked at an operational Drone Depot. This dedicated-hardware exception does not expose ordinary Inventory freight at that outpost. Self-only. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def uncouple(self, slot_index: _float) -> ActionResult[Literal["ok", "invalid_slot", "module_not_mounted", "not_at_station", "cargo_capacity_exceeded", "container_not_empty", "hot_cargo_requires_plating", "inventory_full"]]:
 """Request a hardware service order that returns the module in an explicit whole-number slot to Inventory: `self.uncouple(1)`. The drone must be docked at an operational Drone Depot. Cargo Pods must be empty before removal, and Shield Plating cannot be removed while Raw Uranium or Fuel Rod cargo remains aboard. Fuel-bearing modules preserve their contents. Self-only. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def status(self) -> Literal["idle", "traveling", "charging", "refueling", "waiting_service", "waiting_oil", "waiting_bay", "being_rescued", "holding_weather", "scrambled", "stalled_no_battery", "stalled_no_oil", "stalled_no_route"]:
 """Current operational activity for progress and blocker handling, not an arrival test. `\"idle\"` can mean docked, hovering at a field coordinate, or holding a queued route at zero throttle; charging or refueling can begin immediately after docking. `\"waiting_bay\"` means the drone reached a full Depot but is not docked, `\"holding_weather\"` is a temporary heli hold, and stalled or scrambled states need intervention. Use `current_station()` or `current_drill()` to confirm arrival at an interaction endpoint."""
 ...
 def is_being_rescued(self) -> _bool:
 """`True` while a Drone Service Station is actively servicing or carrying this drone. Use this to pause route scripts while the rescue vehicle has control."""
 ...
 def rescue_status(self) -> Literal["none", "outbound", "charging", "carrying", "returning"]:
 """Current recovery mission phase for this drone: `\"none\"`, `\"outbound\"`, `\"charging\"`, `\"carrying\"`, or `\"returning\"`. `\"returning\"` means the recovery vehicle is heading home and the drone is no longer under rescue control."""
 ...
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

## `DroneRef`

```python
class DroneRef:
 """fleet.drones()"""
 category: Literal["drone"]
 id: _str
 name: _str
 kind: Literal["drone_small", "drone_medium", "drone_large"]
 engine: Literal["", "electric", "heli"]
 status: Literal["idle", "traveling", "charging", "refueling", "waiting_service", "waiting_oil", "waiting_bay", "being_rescued", "holding_weather", "scrambled", "stalled_no_battery", "stalled_no_oil", "stalled_no_route"]
 x: _float
 y: _float
 def position(self) -> Position:
 """Position snapshot from when this ref was returned."""
 ...
 current_station: _str
 is_docked: _bool
 battery_level: _float | None
 battery_wh: _float | None
 battery_capacity: _float | None
 oil_level: _float | None
 oil_tons: _float | None
 oil_capacity: _float | None
 is_being_rescued: _bool
 rescue_status: Literal["none", "outbound", "charging", "carrying", "returning"]
```

## `DroneServiceStation`

```python
class DroneServiceStation(Component):
 """Drone Service Station: Charges electric drones in the field and recovers heli drones for queued refueling. Grid-tied."""
 name: _str
 outpost: OutpostRef
 def get_docked(self) -> _list[_str]:
 """List of all drone ids (electric and heli) currently parked at this station. Read each drone's state via `get_component(id)`."""
 ...
 def charge(self, drone_id: _str, target_level: _float = ...) -> ActionResult[Literal["charging", "queued", "target_reached", "not_docked", "station_offline", "invalid"]]:
 """Queue a parked electric drone to charge until its battery reaches `target_level` (greater than **0** and at most **1**, defaults to **1.0**). Electric charge and heli refuel jobs share one FIFO and the same service bays. An oil-blocked heli keeps its queue position but does not occupy a bay, so ready electric work may bypass it. Example: `self.charge(\"drone_small_1\", 0.8)`. Self-only. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def refuel(self, drone_id: _str, target_level: _float = ...) -> ActionResult[Literal["refueling", "queued", "target_reached", "not_docked", "station_offline", "no_oil", "invalid"]]:
 """Queue a parked heli drone to refuel until its oil tank reaches `target_level` (greater than **0** and at most **1**, defaults to **1.0**). Electric charge and heli refuel jobs share one FIFO and the same service bays. Draws oil from `self.oil_in`. Self-only. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def dispatch_rescue(self, drone_name: _str, target_level: _float = ...) -> ActionResult[Literal["ok", "already_dispatched", "station_offline", "not_found", "not_stranded", "invalid"]]:
 """Send the recovery vehicle to a field drone chosen by your script; there is no hidden fuel threshold. Electric drones are charged in the field to `target_level` and resume their route. Heli drones are carried home, then join the normal refueling queue. Scrambled drones are also carried home so docking can reset their electronics. `target_level` must be above **0** and at most **1**, and defaults to **1.0**. Launch requires station power, but the mission can finish through a later outage. Self-only. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def cancel_rescue(self) -> ActionResult[Literal["ok", "no_rescue"]]:
 """Abort the in-flight rescue. The drone is released at its current position (it keeps any charge already delivered) and the service vehicle flies home. Self-only. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def is_rescuing(self) -> _bool:
 """`True` while the service vehicle is on a rescue mission."""
 ...
 def get_rescue_target(self) -> _str:
 """Mission target's display name while the service vehicle is outbound, servicing, carrying, or returning; empty string when idle."""
 ...
 def stop(self, drone_id: _str) -> ActionResult[Literal["ok", "not_found", "invalid"]]:
 """Cancel one active or queued job on this station, whether it is a charge or a refuel. The drone keeps any energy or oil already delivered. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def clear_queue(self) -> CountResult[Literal["ok", "no_op"]]:
 """Clear every active or queued charge and refuel job on this station. Docked drones stay parked and keep their current battery and oil. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
 def get_active(self) -> _list[_str]:
 """List of drone ids currently occupying active service bays (charging or refueling). An oil-blocked heli is waiting, not active."""
 ...
 def get_queue(self) -> _list[_str]:
 """One FIFO list of drone ids across electric charging and heli refueling. Oil-blocked helis stay in order while ready later jobs may use otherwise-idle bays."""
 ...
 def status(self, drone_id: _str) -> _dict[_str, Any]:
 """Detailed status for one drone's service job. Electric drones return a dict with `state`, `target_level`, `battery_wh`, `capacity_wh`, `rate_w`, `bay_index`, `queue_index`. Heli drones return `state`, `target_level`, `oil_tons`, `capacity_tons`, `rate_tons_per_hour`, `bay_index`, `queue_index`."""
 ...
 def get_bay_count(self) -> _int:
 """Number of simultaneous service bays."""
 ...
 def get_charge_rate(self, drone_id: _str) -> _float:
 """Returns the Wh/h currently being pushed into the named electric drone (**0** if it is not in an active bay)."""
 ...
 def get_refuel_rate(self, drone_id: _str) -> _float:
 """Returns the oil t/h currently being pushed into the named heli drone (**0** if it is not in an active bay or the station has no oil)."""
 ...
 oil_in: FluidPort
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

## `DroneSmall`

```python
class DroneSmall(Component):
 """Drone (Small): Small aerial cargo drone, 1 thruster + 2 modules."""
 name: _str
 def go_to_station(self, name: _str) -> ActionResult[Literal["ok", "station_not_found", "out_of_range", "busy", "scrambled"]]:
 """Queue a route to the named Drone Depot or Drone Service Station and return immediately without waiting for docking. An accepted powered route reports `\"traveling\"` immediately; position and docking advance after simulation advances. Stop, completion, or error cancels the flight and clears the route. Compare `current_station()` with the destination's stable id to confirm arrival. Moving between drone buildings inside the same outpost is a local transfer and costs no flight fuel. Drone Service Stations accept parked arrivals even while unpowered. A full Drone Depot keeps the drone undocked in `\"waiting_bay\"` until a physical bay opens. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def undock(self) -> ActionResult[Literal["ok", "not_docked", "busy"]]:
 """Release the station berth without flying anywhere. The drone keeps its exact world position, cargo, modules, fuel, and exposure, clears any dormant route, resets throttle to **0**, and becomes idle. An active rescue, or an active or queued Drone Service Station charge/refuel job, retains control until that station-owned work ends. Use `go_to_station(...)` when the drone should claim a berth again. Self-only. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def go_to_drill(self, name: _str) -> ActionResult[Literal["ok", "drill_not_found", "out_of_range", "busy", "scrambled"]]:
 """Fly to a named field Mining Drill for ore pickup. Hauling needs no field module. An accepted powered route reports `\"traveling\"` immediately, then the drone flies in a straight line and hovers on arrival. Compare `current_drill()` with the destination's stable id to confirm that cargo loading is available. Stopping or completing the script, hitting an error, or calling `go_to_station()` cancels this route. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def current_station(self) -> _str:
 """Stable station id where the drone is physically docked. Returns an empty string while flying to coordinates, traveling between stations, or waiting outside a full Drone Depot. Use equality with the destination id as the authoritative station-arrival check, even when `go_to_station()` was called with a display name."""
 ...
 def current_drill(self) -> _str:
 """Stable Mining Drill id where the drone can currently load cargo, or an empty string when no Drill is available. The drone must be within the Drill's loading area with no active route; merely passing over the Drill or holding a zero-throttle route does not count. Compare this value with the destination id as the authoritative Drill-arrival check, even when `go_to_drill()` was called with a display name."""
 ...
 def position(self) -> Position:
 """World coordinates `(.x, .y)`, lerped each tick by DroneSystem during transit, snapped to station coords on dock."""
 ...
 def get_distance_to(self, x: _float, y: _float) -> _float:
 """Straight-line distance in meters from the drone's current position to the given world coordinate. Use it to compare possible destinations, check remaining route distance, or pair it with `range_remaining()` before dispatch. It measures geometry only and does not select a destination or account for available fuel."""
 ...
 battery: DroneBattery
 oil_tank: DroneOilTank
 cargo: DroneCargo
 def go_to(self, x: _float, y: _float) -> ActionResult[Literal["ok", "invalid_target", "out_of_bounds", "out_of_range", "busy", "scrambled"]]:
 """Fly to any world coordinate as a base drone capability; no field module is required. An accepted powered route reports `\"traveling\"` immediately, then the drone flies in a straight line and hovers on arrival. Stopping or completing the script, hitting an error, or calling `go_to_station()` cancels this route. For Weather, pass the exact x and y assembled from checksum-valid storm packets. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 bio_scanner: PortableBioScanner
 bio_extractor: PortableBioExtractor
 def collect(self) -> CollectResult[Literal["ok", "moving", "busy", "nothing_here", "no_cargo_space", "scrambled"]]:
 """Collect one weather aftermath batch at the drone's exact current coordinate. A successful batch transfers at most **5** Storm Glass or Raw Uranium. Raw Uranium collection adds **40** exposure without Shield Plating and **0** with it; the batch is retained even if it reaches the scramble threshold. Fixed result contract: `CollectResult`; branch on `.status` and read `.message`. Payload fields: `.item_id` and `.collected`."""
 ...
 def exposure(self) -> _float:
 """Current extraction exposure, from **0** to `exposure_capacity()`. It changes only when collecting Raw Uranium or receiving Service Station care; simply flying across a hidden aftermath is inert. A working drone docked at a powered Drone Service Station clears **10 per hour**. At capacity the drone is scrambled and requires Service Station rescue."""
 ...
 def exposure_capacity(self) -> _float:
 """The **100** exposure scramble threshold. An unplated drone can collect two 5-unit batches safely; the third batch is retained and then scrambles it."""
 ...
 def is_plated(self) -> _bool:
 """`True` with Shield Plating mounted. Plating reduces Raw Uranium extraction exposure to zero, halves each Cargo Pod's capacity, and raises fuel burn **1.5×** because lead is heavy."""
 ...
 def range_remaining(self) -> _float:
 """Estimated flight distance in meters at the current energy and throttle. Electric burn is **5 Wh/h** at full throttle; Heli burn is **5 t/h Oil**. Both scale with throttle squared, so slower routes stretch range."""
 ...
 def throttle(self) -> _float:
 """Current throttle (**0-1**). Full-throttle burn is **5 Wh/h** for electric propulsion or **5 t/h Oil** for Heli; both scale with throttle squared. Reads **0** after Stop, completion, or error."""
 ...
 def set_throttle(self, rate: _float) -> ActionResult[Literal["ok"]]:
 """Set throttle (**0-1**). At full throttle, electric drones fly **300 m/h** using **5 Wh/h**; Heli drones fly **900 m/h** using **5 t/h Oil**. Lower throttle reduces burn quadratically. Stop, completion, or error resets throttle to **0**. Self-only. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def couple(self, slot_index: _float, module_id: _str) -> ActionResult[Literal["ok", "not_at_station", "item_not_in_inventory", "unknown_module", "slot_not_compatible", "slot_occupied", "invalid_slot", "locked", "wrong_engine_for_module", "cargo_capacity_exceeded"]]:
 """Request a hardware service order from Inventory into an explicit whole-number slot: `self.couple(0, \"electric_thruster\")` for the thruster slot, or `self.couple(1, \"battery_pack\")` for a module slot. The drone must be docked at an operational Drone Depot. This dedicated-hardware exception does not expose ordinary Inventory freight at that outpost. Self-only. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def uncouple(self, slot_index: _float) -> ActionResult[Literal["ok", "invalid_slot", "module_not_mounted", "not_at_station", "cargo_capacity_exceeded", "container_not_empty", "hot_cargo_requires_plating", "inventory_full"]]:
 """Request a hardware service order that returns the module in an explicit whole-number slot to Inventory: `self.uncouple(1)`. The drone must be docked at an operational Drone Depot. Cargo Pods must be empty before removal, and Shield Plating cannot be removed while Raw Uranium or Fuel Rod cargo remains aboard. Fuel-bearing modules preserve their contents. Self-only. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def status(self) -> Literal["idle", "traveling", "charging", "refueling", "waiting_service", "waiting_oil", "waiting_bay", "being_rescued", "holding_weather", "scrambled", "stalled_no_battery", "stalled_no_oil", "stalled_no_route"]:
 """Current operational activity for progress and blocker handling, not an arrival test. `\"idle\"` can mean docked, hovering at a field coordinate, or holding a queued route at zero throttle; charging or refueling can begin immediately after docking. `\"waiting_bay\"` means the drone reached a full Depot but is not docked, `\"holding_weather\"` is a temporary heli hold, and stalled or scrambled states need intervention. Use `current_station()` or `current_drill()` to confirm arrival at an interaction endpoint."""
 ...
 def is_being_rescued(self) -> _bool:
 """`True` while a Drone Service Station is actively servicing or carrying this drone. Use this to pause route scripts while the rescue vehicle has control."""
 ...
 def rescue_status(self) -> Literal["none", "outbound", "charging", "carrying", "returning"]:
 """Current recovery mission phase for this drone: `\"none\"`, `\"outbound\"`, `\"charging\"`, `\"carrying\"`, or `\"returning\"`. `\"returning\"` means the recovery vehicle is heading home and the drone is no longer under rescue control."""
 ...
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

## `DroneStation`

```python
class DroneStation(Component):
 """Drone Depot: 1-bay logistics endpoint at an outpost. Cargo I/O."""
 name: _str
 outpost: OutpostRef
 input: InputSlot
 output: OutputSlot
 def get_docked(self) -> _list[_str]:
 """List of drone ids currently docked at this Depot, in stable id order. Read each drone's state with `get_component(id)`."""
 ...
 def bay_count(self) -> _int:
 """Total bays at this station: **1** (basic) / **2** (medium) / **4** (large)."""
 ...
 def bays_occupied(self) -> _int:
 """Bays currently occupied by docked drones. When equal to `bay_count`, arriving drones queue in airspace."""
 ...
 def slots_used(self) -> _int:
 """How many distinct materials the stockpile currently holds. One material is one slot no matter how many units of it are stored, so **50** units of one material fills a single slot."""
 ...
 def slot_capacity(self) -> _int:
 """How many distinct materials this depot can hold at once. A depot is a transfer proxy, not a warehouse: when every slot is taken, a `cargo.unload()` of a new material moves **0** units and reports that no slot is free, even while units remain free. Drain a material out to release its slot."""
 ...
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

## `DroneStationLarge`

```python
class DroneStationLarge(Component):
 """Drone Depot (Large): 4-bay major drone hub."""
 name: _str
 outpost: OutpostRef
 input: InputSlot
 output: OutputSlot
 def get_docked(self) -> _list[_str]:
 """List of drone ids currently docked at this Depot, in stable id order. Read each drone's state with `get_component(id)`."""
 ...
 def bay_count(self) -> _int:
 """Total bays at this station: **1** (basic) / **2** (medium) / **4** (large)."""
 ...
 def bays_occupied(self) -> _int:
 """Bays currently occupied by docked drones. When equal to `bay_count`, arriving drones queue in airspace."""
 ...
 def slots_used(self) -> _int:
 """How many distinct materials the stockpile currently holds. One material is one slot no matter how many units of it are stored, so **50** units of one material fills a single slot."""
 ...
 def slot_capacity(self) -> _int:
 """How many distinct materials this depot can hold at once. A depot is a transfer proxy, not a warehouse: when every slot is taken, a `cargo.unload()` of a new material moves **0** units and reports that no slot is free, even while units remain free. Drain a material out to release its slot."""
 ...
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

## `DroneStationMedium`

```python
class DroneStationMedium(Component):
 """Drone Depot (Medium): 2-bay logistics endpoint. Parallel docking."""
 name: _str
 outpost: OutpostRef
 input: InputSlot
 output: OutputSlot
 def get_docked(self) -> _list[_str]:
 """List of drone ids currently docked at this Depot, in stable id order. Read each drone's state with `get_component(id)`."""
 ...
 def bay_count(self) -> _int:
 """Total bays at this station: **1** (basic) / **2** (medium) / **4** (large)."""
 ...
 def bays_occupied(self) -> _int:
 """Bays currently occupied by docked drones. When equal to `bay_count`, arriving drones queue in airspace."""
 ...
 def slots_used(self) -> _int:
 """How many distinct materials the stockpile currently holds. One material is one slot no matter how many units of it are stored, so **50** units of one material fills a single slot."""
 ...
 def slot_capacity(self) -> _int:
 """How many distinct materials this depot can hold at once. A depot is a transfer proxy, not a warehouse: when every slot is taken, a `cargo.unload()` of a new material moves **0** units and reports that no slot is free, even while units remain free. Drain a material out to release its slot."""
 ...
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

## `Harvester`

```python
class Harvester(Component):
 """Harvester: A slow general-purpose surface vehicle that collects loose items, plants and tends crops, harvests Forage, and deploys fixed field machines. Movement and field work take time and build heat, so long routes need cooling pauses."""
 name: _str
 def move(self, sector: _str) -> ActionResult[Literal["ok", "invalid", "too_far", "already_here", "overheated", "moving", "busy"]]:
 """Move one sector up, down, left, or right with `self.move(\"E14\")`; diagonal moves are invalid. Travel takes **0.5 hours** and pauses the script. `self.get_position()` shows the destination immediately, but physical actions stay locked until arrival. Moving into an item sector adds **1** heat; moving into an empty one adds **7**, so scan first. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def collect(self) -> ScanResult[Literal["ok", "empty", "holding", "overheated", "moving", "busy", "collecting"]]:
 """Pick up the item in the current sector into the Harvester's single held slot, not Inventory. Collection takes **0.25 hours** and pauses the script. Empty sectors still take time and add **9** heat. Fixed result contract: `ScanResult`; branch on `.status` and read `.message`. Payload fields: `.id`, `.name`, and `.value`."""
 ...
 def store(self) -> ItemResult[Literal["ok", "empty", "inventory_full"]]:
 """Move the harvester's held item into the first empty inventory slot, freeing the held slot for the next pickup. A full inventory leaves the item held; drop it or free space by selling. Fixed result contract: `ItemResult`; branch on `.status` and read `.message`. Payload fields: `.item_id`."""
 ...
 def drop(self) -> ActionResult[Literal["dropped", "empty", "occupied", "moving", "busy"]]:
 """Release the currently held item into the harvester's current sector, the cell becomes collectable again. Use it to stage items for later pickup or clear the held slot without storing. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def get_held(self) -> _str:
 """Item id currently held by the harvester, or empty string if the held slot is empty. Call `self.get_held()` before `collect()` (if non-empty, the slot is busy) or before `self.store()` (if empty, nothing to store). Essential first line of any collect loop."""
 ...
 def get_position(self) -> _str:
 """Current sector id as a string (e.g. `\"E14\"`). Use to plan the next `move()` target, movement is strictly to adjacent cells, so the script needs to know where it is to compute where it can go."""
 ...
 def get_heat(self) -> _float:
 """Exact current heat level (**0-100**), including fractional cooling between whole heat costs. Every `move()` adds heat, and an empty-sector `collect()` attempt also adds heat; passive cooling runs continuously as game time passes, including during movement and collection. Read before moving, if you're close to **100** and your planned route crosses empty cells (+7 heat each), stop and cool. Losing the route to `\"overheated\"` mid-sweep wastes hours."""
 ...
 def get_max_heat(self) -> _float:
 """Maximum heat capacity, always **100**. Reaching this stalls all movement and collection until heat drops below the cap. Exposed as a method so scripts can reason about thresholds without hardcoding the number."""
 ...
 def is_overheated(self) -> _bool:
 """`True` when heat `>= 100`. Shortcut for `self.get_heat() >= self.get_max_heat()`. Use it as an early-exit guard when you intentionally want the harvester to cool: `if self.is_overheated(): sleep(1)`. The harvester cools passively whenever game time advances."""
 ...
 def water_level(self) -> _float:
 """Read the water currently in the Harvester's onboard tank, in tons, including fractional amounts. Each watering uses **1 t**. Compare with `water_capacity()` to plan refills from the home outpost's water tanks."""
 ...
 def water_capacity(self) -> _float:
 """Read the Harvester's maximum onboard water supply in tons, currently **5 t**. Compare with `water_level()` to check how full the tank is."""
 ...
 def load_seed(self, seed: _str) -> ActionResult[Literal["ok", "locked", "invalid_seed", "no_seed", "holding", "overheated", "moving", "busy"]]:
 """Transfer one species seed from home Inventory, from anywhere on the grid, into the Harvester's single held slot. Use the same seed id with `plant(seed)` after driving to an empty field cell. Loading fails while another item is held. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def plant(self, seed: _str) -> ActionResult[Literal["ok", "locked", "invalid_seed", "no_seed", "not_empty", "base_sector", "overheated", "moving", "busy"]]:
 """Sow the physical seed currently in the Harvester's held slot into this empty cell. The argument must identify that held seed. The base sector is depot ground and refuses sowing. Sowing takes **0.5 hours**, and the seed and new crop appear only after the action finishes. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def deploy(self, kit: _str) -> ActionResult[Literal["ok", "locked", "no_kit", "not_empty", "invalid_kit", "overheated", "moving", "busy"]]:
 """Place a supported field-machine kit in the current empty cell, consuming one kit from Inventory. Installation takes **0.25 hours** and pauses the script. Call `deployables()` for the available kit ids. Seed Makers and other outpost buildings deploy through Inventory. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def deployables(self) -> _list[_str]:
 """List of fixed field-machine kit ids unlocked by your current research. This is a capability list, not a live deployment check: `deploy(...)` still checks Inventory stock, the current cell, movement, heat, and whether the Harvester is busy."""
 ...
 def light(self) -> ActionResult[Literal["ok", "locked", "not_plantable", "overheated", "moving", "busy"]]:
 """Light the current plantable cell with the Harvester's work lamp, even if it is already lit or covered by a Grow Lamp. Each application resets the treatment to **24 hours** when the work finishes, replacing any remaining time. Lighting takes **0.25 hours** and pauses the script. Use a Grow Lamp later to cover four orthogonally adjacent cells (directly above, below, left, and right) continuously. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def water(self) -> ActionResult[Literal["ok", "locked", "insufficient_water", "not_plantable", "overheated", "moving", "busy"]]:
 """Water the current plantable cell from the Harvester's onboard supply, even if it is already watered or covered by a Sprinkler. Each watering uses **1 t** and resets the treatment to **24 hours** when the work finishes, replacing any remaining time. Watering takes **0.25 hours** and pauses the script. Use `refill_water()` anywhere on the local grid to draw from the home outpost's tanks. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def refill_water(self) -> ActionResult[Literal["ok", "locked", "moving", "overheated", "tank_empty", "already_full", "busy"]]:
 """Refill the Harvester's onboard water supply from the home outpost's water tanks, from anywhere on the grid. Refilling takes **0.25 hours** and pauses the script. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def dispense_salt(self) -> ActionResult[Literal["ok", "locked", "no_salt", "not_plantable", "overheated", "moving", "busy"]]:
 """Treat the current plantable cell with one unit of `salt` from Inventory, even if it is already salted or covered by a Dispenser. Each application resets the treatment to **24 hours** when the work finishes, replacing any remaining time. Dispensing takes **0.25 hours** and pauses the script. Water Pumps produce salt as a byproduct. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def fertilize(self, item_id: _str = ...) -> ActionResult[Literal["ok", "invalid_input", "locked", "no_plant", "already_mature", "tier_conflict", "no_dose", "overheated", "moving", "busy"]]:
 """Dose the current cell's growing plant with one Fertilizer Mk I, II, or III. Each unit boosts output for **8 hours**. Additional units of the same tier extend it; wait for the active dose to drain before switching tiers. Dosing occupies the Harvester for **0.25 hours**. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def accelerate(self) -> ActionResult[Literal["ok", "locked", "no_plant", "already_mature", "no_dose", "overheated", "moving", "busy"]]:
 """Dose the current cell's growing plant with one `growth_accelerant` to double its growth rate for **8 hours**. Dosing occupies the Harvester for **0.25 hours**. The dose cannot affect a crop that is already mature. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def amplify(self) -> ActionResult[Literal["ok", "locked", "no_dose", "overheated", "moving", "busy"]]:
 """Apply one `yield_amplifier`, the capstone **field-wide** Forage-output boost (no cell needed). Applying it occupies the Harvester for **0.25 hours**. The dose drains over about one game-day, so re-call to sustain. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def amplifier_remaining(self) -> _float:
 """Hours remaining on the field-wide Yield Amplifier effect. Each applied unit adds **24 hours**. Returns **0** when the field is not amplified."""
 ...
 def uproot(self) -> ActionResult[Literal["ok", "no_plant", "inventory_full", "locked", "overheated", "moving", "busy"]]:
 """Remove the plant in the current cell and place one matching seed in Inventory. Uprooting takes **0.5 hours** and pauses the script. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def undeploy(self) -> ActionResult[Literal["ok", "nothing", "not_empty", "script_present", "inventory_full", "overheated", "moving", "busy"]]:
 """Remove the fixed field machine in the current cell and return its kit to Inventory. This is the only removal path for Grow Lamps, Sprinklers, Dispensers, and Crop Automators. Its stored items must be empty, the hardware refund must fit, and its attached script must not be running. Authored scripts remain available in Computer > Scripts without a host. Unfinished machine work and machine-only result history are discarded; queued Crop Automator jobs have not consumed their inputs. Removal takes **0.25 hours** and pauses the Harvester script. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def harvest(self) -> ActionResult[Literal["ok", "partial", "locked", "no_plant", "not_mature", "no_forage", "inventory_full", "overheated", "moving", "busy"]]:
 """Harvest the ready crop in the current cell. The action takes **0.5 hours** and transfers nothing until it finishes. On completion it moves as much of `cell.forage` as Inventory can hold: a crop larger than the free room leaves its remainder banked and the plant standing, so drain Inventory and harvest again to collect the rest. Only a fully collected crop is removed and frees the cell for another physical seed. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def cell(self, sector: _str) -> Cell | None:
 """Read one grid sector as a `Cell` snapshot. Unscanned natural ground has status `\"unknown\"` until scanned; the depot and player-created plants or providers stay visible. The snapshot includes plant, growth, conditions, and remaining treatment hours. Returns `None` for an invalid sector."""
 ...
 def cells(self) -> _list[Cell]:
 """Read every harvester-grid sector as a list of `Cell` snapshots. Unscanned natural ground reports status `\"unknown\"`; scan sectors before planning around occupancy. Use the list for field-wide planting, treatment-route scheduling, uprooting, undeploying, and harvesting policies."""
 ...
 def position(self) -> _str:
 """Current sector id as a string. Same position source as `get_position()`, exposed as a property-style read for grid scripts."""
 ...
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

## `MiningDrill`

```python
class MiningDrill(Component):
 """Mining Drill: Mk I static drill for hardness-1 deposits: 25 t/h at standard purity and 10 W while extracting."""
 name: _str
 def drill_rate(self) -> _float:
 """Mineral extraction rate in t/h right now: the full rate while drilling, and **0** whenever the drill is powered off, has no deposit under it, cannot cut the deposit's hardness, or its stockpile is full. Adjusted for site purity and drill tier."""
 ...
 output: PickupOutputSlot
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

## `MiningDrillHeavy`

```python
class MiningDrillHeavy(Component):
 """Heavy Mining Drill: Mk III static drill for hardness-4 deposits: 200 t/h at standard purity and 100 W while extracting."""
 name: _str
 def drill_rate(self) -> _float:
 """Mineral extraction rate in t/h right now: the full rate while drilling, and **0** whenever the drill is powered off, has no deposit under it, cannot cut the deposit's hardness, or its stockpile is full. Adjusted for site purity and drill tier."""
 ...
 output: PickupOutputSlot
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

## `MiningDrillIndustrial`

```python
class MiningDrillIndustrial(Component):
 """Industrial Mining Drill: Mk II static drill for hardness-3 deposits: 75 t/h at standard purity and 35 W while extracting."""
 name: _str
 def drill_rate(self) -> _float:
 """Mineral extraction rate in t/h right now: the full rate while drilling, and **0** whenever the drill is powered off, has no deposit under it, cannot cut the deposit's hardness, or its stockpile is full. Adjusted for site purity and drill tier."""
 ...
 output: PickupOutputSlot
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

## `NavModule`

```python
class NavModule:
 """self.nav (vehicles)"""
 def set_target(self, x: _float, y: _float) -> ActionResult[Literal["ok", "not_mounted", "invalid", "out_of_bounds", "busy"]]:
 """Set target coordinates to drive toward. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def set_throttle(self, power: _float) -> ActionResult[Literal["ok", "not_mounted", "busy"]]:
 """Set throttle (0.0-1.0; clamped). Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def throttle(self) -> _float:
 """Current throttle setpoint (**0.0-1.0**). Returns the value the script last wrote via `set_throttle(...)`. Distinct from `get_speed()`: `throttle()` is intent (does not change tick-to-tick); `get_speed()` is what the vehicle actually moved last tick."""
 ...
 def brake(self) -> ActionResult[Literal["ok", "not_mounted"]]:
 """Stop the vehicle (throttle set to 0). Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def get_position(self) -> Position:
 """Vehicle position as a `Position` object with `.x` and `.y`."""
 ...
 def get_speed(self) -> _float:
 """Vehicle speed in m/h."""
 ...
 def get_distance_to(self, x: _float, y: _float) -> _float:
 """Distance (meters) from the vehicle to the given point. Arrival loops need a tolerance, normally `> 2`, rather than exact zero. When the next action targets a building, route to its `BuildingRef.position`."""
 ...
 def speed_multiplier(self) -> _float:
 """Top-speed multiplier: **1.0** basic, or **1 + mounted Sport Nav count** on Pioneer. Speed only; range still depends on battery, throttle, cargo load, and movement draw."""
 ...
```

## `NavModuleComponent`

```python
class NavModuleComponent(Component):
 """Nav Module: Lets a vehicle drive through `self.nav`. A basic module provides **1.0×** top speed. One Sport Nav on the same rig provides **2×** top speed with **2.6×** movement power draw, about **1.3×** battery use per meter at full throttle. Further Sport Navs add **1.0×** base top speed each and raise draw faster. It fits a `nav` or `universal` slot. Keep the script running until arrival. The vehicle stops and clears its route if the script stops, ends, or errors."""
 name: _str
 def set_target(self, x: _float, y: _float) -> ActionResult[Literal["ok", "not_mounted", "invalid", "out_of_bounds"]]:
 """Set target coordinates to drive toward. **Returns immediately**, the vehicle then drives asynchronously over subsequent ticks while this script remains active. Poll `get_distance_to(x, y)` or `get_position()` in a wait loop to detect proximity. Use a tolerance, normally `while self.nav.get_distance_to(x, y) > 2:`, instead of waiting for exact zero, then call `self.nav.brake()` before `drill.mine()` or another stationary action. For an at-building action, target that building's `BuildingRef.position` rather than the outpost footprint anchor. The vehicle stops and clears its route if the script stops, ends, or errors. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def set_throttle(self, power: _float) -> ActionResult[Literal["ok", "not_mounted"]]:
 """Set throttle (**0.0-1.0**, clamped). `self.nav.set_throttle(0.5)` cruises; `1.0` sprints but burns more battery per meter. Use to trade speed for range on long runs. Stop, completion, error, and `brake()` reset throttle to **0**. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def throttle(self) -> _float:
 """Current throttle setpoint (**0.0-1.0**). Returns the value the script last wrote via `self.nav.set_throttle(...)`, or **0** after Stop, completion, error, or `brake()`. Distinct from `get_speed()`, `throttle()` is your intent, `get_speed()` is what the vehicle actually moved last tick."""
 ...
 def brake(self) -> ActionResult[Literal["ok", "not_mounted"]]:
 """Stop the vehicle immediately, throttle and speed set to **0**, and the current target is cleared to the vehicle's current position. Use when a script needs to abort a drive mid-route (e.g. re-pathing toward a closer site). Cheaper battery-wise than driving to destination. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def get_position(self) -> Position:
 """Current position as a `Position` object with `.x` and `.y` in meters from base. Read each iteration of a drive loop to detect arrival, plan next hop, or log the path. See `Position`."""
 ...
 def get_speed(self) -> _float:
 """Speed in meters per hour as recorded on the last drive tick. **0** while idle or braked; up to the Nav's top speed at throttle **1.0**. Use to confirm the vehicle is actually moving (if `0` when you expected drive, there's a power or target issue). A fresh `set_throttle(...)` won't show up here until the next drive tick."""
 ...
 def get_distance_to(self, x: _float, y: _float) -> _float:
 """Euclidean distance in meters from the vehicle's current position to the given point. Use it inside an intentional wait loop to detect proximity, with an arrival tolerance such as `> 2`, never exact zero. Reaching that tolerance does not stop the vehicle; call `brake()` before a stationary at-site action. For an at-building action, route to that building's `BuildingRef.position`. `set_target()` does not block while the vehicle drives, and the drive is canceled if the script stops, completes, or errors. This is pure straight-line distance and does not account for obstacles."""
 ...
 def speed_multiplier(self) -> _float:
 """Current top-speed multiplier: **1.0** with Basic Nav/no Sport Nav, or **1 + mounted Sport Nav count** on Pioneer. Use it to plan trip times and scout builds. This is speed only; range still depends on battery, throttle, cargo load, and movement draw."""
 ...
```

## `Pioneer`

```python
class Pioneer(Component):
 """Pioneer: A modular long-range vehicle for driving, scanning, mining, and building in the field. The bare chassis does nothing; everything comes from the modules, batteries, and cargo you mount in its eight slots."""
 name: _str
 def status(self) -> Literal["idle", "moving", "stranded", "scanning", "surveying", "drilling", "discarding", "constructing", "transferring", "charging", "queued", "being_rescued"]:
 """Read the Pioneer's current physical activity. Each call reads fresh state, including through `get_component(...)`. An idle Pioneer may still have a script running or a job assigned."""
 ...
 battery: Battery
 cargo: Cargo
 nav: NavModule
 sonar: SonarModule
 drill: DrillModule
 constructor: ConstructorModule
 input: VehicleInputSlot
 output: OutputSlot
 def is_being_rescued(self) -> _bool:
 """`True` while a Vehicle Charging Station rescue drone is actively recovering this Pioneer. Use this to pause movement, mining, or construction scripts even if the battery has started rising above zero."""
 ...
 def rescue_status(self) -> Literal["none", "outbound", "charging", "returning"]:
 """Current rescue mission phase for this Pioneer: `\"none\"`, `\"outbound\"`, `\"charging\"`, or `\"returning\"`. `\"returning\"` means the rescue drone is going home and the Pioneer is free again."""
 ...
 def modules(self) -> _list[MountSlot]:
 """Inspect every slot on the chassis. Returns a list of `MountSlot`, eight entries for the Pioneer. Each has `.index` (pass to `mount` / `unmount`), `.type` (always `\"universal\"` on Pioneer), `.module_id` (what's mounted, or `None` for empty), `.internal_count` (non-zero for Battery Holders / Cargo Racks), `.internal_items` (list of installed portable item ids). Call before `self.mount(...)` or `self.install(...)` to find an empty target. See `MountSlot`."""
 ...
 def mount(self, slot_index: _float, item_id: _str) -> ActionResult[Literal["ok", "not_at_service_point", "locked", "item_not_in_inventory", "unknown_module", "slot_not_compatible", "slot_occupied", "invalid_slot", "capability_already_mounted"]]:
 """Request a hardware service order from Inventory into whole-number `slot_index`: `self.mount(0, \"nav_module\")`. Biological field modules are drone-only. The Pioneer must be inside a founded outpost service area. This dedicated-hardware exception does not make Inventory a freight endpoint there. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def unmount(self, slot_index: _float) -> ActionResult[Literal["ok", "not_at_service_point", "slot_empty", "invalid_slot", "holder_not_empty", "inventory_full"]]:
 """Request a hardware service order that returns the module at whole-number `slot_index` to Inventory: `self.unmount(0)`. The Pioneer must be inside a founded outpost service area. Empty every internal bay before removing a holder or rack. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def install(self, slot_index: _float, internal_index: _float, item_id: _str) -> ActionResult[Literal["ok", "not_at_service_point", "locked", "invalid_slot", "invalid_internal_slot", "slot_empty", "not_container", "item_not_accepted", "internal_slot_occupied", "item_not_in_inventory"]]:
 """Request a service order that installs a Portable Battery or empty Portable Storage Bin from Inventory into a container's whole-number internal slot. `self.install(0, 1, \"portable_battery\")` uses bay **1** of the Battery Holder at chassis slot **0**. `self.install(4, 0, \"portable_bin\")` uses bay **0** of the Cargo Rack at chassis slot **4**. The Pioneer must be inside a founded outpost service area. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def uninstall(self, slot_index: _float, internal_index: _float) -> ActionResult[Literal["ok", "not_at_service_point", "invalid_slot", "invalid_internal_slot", "slot_empty", "not_container", "internal_slot_empty", "inventory_full", "container_not_empty"]]:
 """Request a service order that returns the portable item in a container's whole-number internal slot to Inventory: `self.uninstall(0, 1)`. The Pioneer must be inside a founded outpost service area, and Portable Storage Bins must be empty. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
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

## `Position`

```python
class Position:
 """self.nav.get_position()"""
 x: _float
 y: _float
 def __iter__(self) -> Iterator[_float]:
 """Iterate over `x`, then `y`, so this position can be unpacked or passed to `list()`."""
 ...
```

## `Rover`

```python
class Rover(Component):
 """Rover: Your starter expedition vehicle for driving, scanning, and mining. The bare chassis does nothing on its own; every ability comes from the modules mounted in its three fixed slots."""
 name: _str
 def status(self) -> Literal["idle", "moving", "stranded", "scanning", "surveying", "drilling", "discarding", "constructing", "transferring", "charging", "queued", "being_rescued"]:
 """Read the Rover's current physical activity. Each call reads fresh state, including through `get_component(...)`. An idle Rover may still have a script running or a job assigned."""
 ...
 battery: Battery
 cargo: Cargo
 nav: NavModule
 sonar: SonarModule
 drill: DrillModule
 input: VehicleInputSlot
 output: OutputSlot
 def is_being_rescued(self) -> _bool:
 """`True` while a Vehicle Charging Station rescue drone is actively recovering this Rover. Use this to pause movement or mining scripts even if the battery has started rising above zero."""
 ...
 def rescue_status(self) -> Literal["none", "outbound", "charging", "returning"]:
 """Current rescue mission phase for this Rover: `\"none\"`, `\"outbound\"`, `\"charging\"`, or `\"returning\"`. `\"returning\"` means the rescue drone is going home and the Rover is free again."""
 ...
 def modules(self) -> _list[MountSlot]:
 """Inspect what's mounted. Returns a list of `MountSlot`, one per chassis slot. Each has `.index` (pass to `mount` / `unmount`), `.type` (which modules fit), `.module_id` (mounted id or `None`), `.internal_items` (empty on the Rover's function slots). Call this before `self.mount(...)` to find an empty slot and verify the slot type accepts the module you want. See `MountSlot`."""
 ...
 def mount(self, slot_index: _float, item_id: _str) -> ActionResult[Literal["ok", "not_at_service_point", "locked", "item_not_in_inventory", "unknown_module", "slot_not_compatible", "slot_occupied", "invalid_slot", "capability_already_mounted"]]:
 """Request a hardware service order from Inventory into whole-number `slot_index`: `self.mount(0, \"nav_module\")`. Biological field modules are drone-only. The Rover must be inside a founded outpost service area. This dedicated-hardware exception does not make Inventory a freight endpoint there. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def unmount(self, slot_index: _float) -> ActionResult[Literal["ok", "not_at_service_point", "slot_empty", "invalid_slot", "holder_not_empty", "inventory_full"]]:
 """Request a hardware service order that returns the module at whole-number `slot_index` to Inventory: `self.unmount(0)`. The Rover must be inside a founded outpost service area, and container modules must be empty. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def install(self, slot_index: _float, internal_index: _float, item_id: _str) -> ActionResult[Literal["ok", "not_at_service_point", "locked", "invalid_slot", "invalid_internal_slot", "slot_empty", "not_container", "item_not_accepted", "internal_slot_occupied", "item_not_in_inventory"]]:
 """Install a portable item (Portable Battery / Portable Storage Bin) into a container module's internal slot. **Not used on the Rover**, its fixed slots only accept Nav, Sonar, and Drill function modules, never containers. See Pioneer for the modular version. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def uninstall(self, slot_index: _float, internal_index: _float) -> ActionResult[Literal["ok", "not_at_service_point", "invalid_slot", "invalid_internal_slot", "slot_empty", "not_container", "internal_slot_empty", "inventory_full", "container_not_empty"]]:
 """Uninstall a portable item from a container module's internal slot. **Not used on the Rover**, same reason as `install`. See Pioneer for the modular version. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
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

## `SonarModule`

```python
class SonarModule:
 """self.sonar (vehicles)"""
 def scan(self) -> SonarScanResult[Literal["ok", "too_hard", "tier_too_low", "research_required", "wrong_scanner", "busy", "no_power"]]:
 """Point-sweep for nearby sites. A completed sweep can find no compatible contacts. Mineral contacts obey sonar range and hardness; thermal, water, oil, and exotic contacts also require matching research. The sweep updates the Journal with newly classified sites. A stale captured module reference raises `ReferenceError`. Fixed result contract: `SonarScanResult`; branch on `.status` and read `.message`. Payload fields: `.sites`."""
 ...
 def survey(self, site: Any) -> SurveyResult[Literal["ok", "busy", "not_discovered", "research_required", "tier_too_low", "out_of_range", "too_hard", "no_power"]]:
 """Reveal the details available for a productive site. An inert `GeologicalAnomaly` is already resolved, so surveying it is free. Re-surveying is also free unless a deeper sonar tier can reveal more. Malformed site values raise `ValueError`; a stale captured module reference raises `ReferenceError`. Fixed result contract: `SurveyResult`; branch on `.status` and read `.message`. Payload fields: `.site`."""
 ...
 def range(self) -> _float:
 """Sonar range in meters (**50** basic, **180** Wide, **280** Deep). A stale captured module reference raises `ReferenceError`."""
 ...
 def hardness_limit(self) -> _float:
 """Max mineral hardness this sonar can identify (**1** basic, **3** Wide, **4** Deep). A stale captured module reference raises `ReferenceError`."""
 ...
 def tier(self) -> Literal["basic", "wide", "deep"]:
 """Survey-depth tier granted by the mounted sonar: `\"basic\"` / `\"wide\"` / `\"deep\"`. Determines thermal/exotic survey detail; `\"deep\"` is also required to discover oil wells once **Petroleum Survey** is unlocked. A stale captured module reference raises `ReferenceError`."""
 ...
```

## `SonarModuleComponent`

```python
class SonarModuleComponent(Component):
 """Sonar Module: Finds and surveys world sites through `self.sonar`. A scan checks the area around the vehicle; driving alone does not scan. Use `get_component(\"nocturna\").points_of_interest()` to find unscanned \"?\" markers, travel near one, then call `scan()` and `survey(site)`. Basic Sonar reaches **50 m** and minerals up to hardness **1**; Wide reaches **180 m** and hardness **3**; Deep reaches **280 m** and hardness **4**. Research unlocks thermal vents, wells, and exotic deposits. Results are saved in the Journal. Local Harvester sectors, biological sites, and radiation fields use different scanners."""
 name: _str
 def scan(self) -> SonarScanResult[Literal["ok", "too_hard", "tier_too_low", "research_required", "wrong_scanner", "busy", "no_power"]]:
 """Sweep for compatible `Site`s within range of the vehicle's current position. Contact types include `MiningSite`, `ThermalVent`, `WaterWell`, `OilWell`, `ExoticDeposit`, and `GeologicalAnomaly`. A completed sweep updates the Journal with newly classified contacts. Fixed result contract: `SonarScanResult`; branch on `.status` and read `.message`. Payload fields: `.sites`."""
 ...
 def survey(self, site: Any) -> SurveyResult[Literal["ok", "busy", "not_discovered", "research_required", "tier_too_low", "out_of_range", "too_hard", "no_power"]]:
 """Reveal the details available for a productive `Site`. Pass either its string id or a `Site` from `scan()`. A repeat survey is free and instant unless a better sonar tier can reveal more. Inert `GeologicalAnomaly` contacts are already resolved by scanning. Fixed result contract: `SurveyResult`; branch on `.status` and read `.message`. Payload fields: `.site`."""
 ...
 def range(self) -> _float:
 """Current sonar range in meters."""
 ...
 def hardness_limit(self) -> _float:
 """Maximum mineral hardness this sonar can identify."""
 ...
 def tier(self) -> Literal["basic", "wide", "deep"]:
 """Survey-depth tier granted by this sonar: `\"basic\"` / `\"wide\"` / `\"deep\"`. Controls how much of a thermal vent or exotic deposit is revealed by `survey()`; `\"deep\"` is also required for oil-well discovery."""
 ...
```

## `VehicleRef`

```python
class VehicleRef:
 """fleet.vehicles()"""
 category: Literal["vehicle"]
 id: _str
 name: _str
 kind: Literal["rover", "pioneer"]
 status: Literal["idle", "moving", "stranded", "scanning", "surveying", "drilling", "discarding", "constructing", "transferring", "charging", "queued", "being_rescued"]
 x: _float
 y: _float
 def position(self) -> Position:
 """Position snapshot from when this ref was returned."""
 ...
 battery_level: _float
 battery_wh: _float
 battery_capacity: _float
 is_docked: _bool
 docked_at: _str
 is_being_rescued: _bool
 rescue_status: Literal["none", "outbound", "charging", "returning"]
```
