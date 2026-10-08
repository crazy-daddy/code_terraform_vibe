# Component: drone_service_station

> **Category:** Logistics & Orders | **Component Name:** Drone Service Station

Charges electric drones in the field and recovers heli drones for queued refueling. Grid-tied.

| Field | Value |
| --- | --- |
| Type | Mining |
| Power in | Variable (draws from grid) |
| Consumes | Oil, buffer 100 t |

### How to obtain

1. The recipe unlocks when you complete **Spire, Drone Power Trial**.
2. Requires the **Basic Drone Operations** research (Terraform Index 180,000).
3. Fabricate **Drone Service Station Kit** on a **Fabricator**: 2× Machine Frame, 1× Control Unit, 2× Circuit Panel, 1× Battery Cell, and 1× Liquid Pipe Segment.
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

##### `.outpost: OutpostRef`

The outpost where this building is deployed. The returned `OutpostRef` includes its stable id, display name, biome, position, capacity, and `buildings()` query. Read the property again when you need current values.

- **Returns** `OutpostRef`. The outpost where this building is deployed.

##### `.oil_in: FluidPort`

Oil `FluidPort` for heli refueling. Call `self.oil_in.connect(...)` with an Oil Pump or oil tank's stable machine id or display name. A remote source also needs a completed conflict-free Liquid Pipe route between both locations.

- **Returns** `FluidPort`. Heli refueling supply. Call `connect(...)` with the provider's stable machine id or display name; local providers transfer directly and remote providers use completed liquid-pipe networks.

### Methods

##### `.get_docked() → list[str]`

List of all drone ids (electric and heli) currently parked at this station. Read each drone's state via `get_component(id)`.

- **Returns** `list[str]`. Ids of every drone docked at this station, electric and heli. Read each drone's state via `get_component(id)`.

##### `.charge(drone_id: str, target_level: float = 1.0) → ActionResult` *(self only)*

Queue a parked electric drone to charge until its battery reaches `target_level` (greater than **0** and at most **1**, defaults to **1.0**). Electric charge and heli refuel jobs share one FIFO and the same service bays. An oil-blocked heli keeps its queue position but does not occupy a bay, so ready electric work may bypass it. Example: `self.charge("drone_small_1", 0.8)`. Self-only.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `drone_id` | `str` | Display name or id of a docked electric drone |
| `target_level` | `float` | Optional battery target fraction greater than **0** and at most **1**. Defaults to **1.0**. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"charging"` | success | A charging job is active. |
| `"queued"` | success | The operation was added to the queue. |
| `"target_reached"` | rejection | The vehicle is already at or above the requested charge or fuel level. |
| `"not_docked"` | rejection | The requested vehicle is not docked at this station. |
| `"station_offline"` | transient | The station is offline. |
| `"invalid"` | rejection | One or more supplied arguments are outside the accepted domain. |

##### `.refuel(drone_id: str, target_level: float = 1.0) → ActionResult` *(self only)*

Queue a parked heli drone to refuel until its oil tank reaches `target_level` (greater than **0** and at most **1**, defaults to **1.0**). Electric charge and heli refuel jobs share one FIFO and the same service bays. Draws oil from `self.oil_in`. Self-only.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `drone_id` | `str` | Display name or id of a docked heli drone |
| `target_level` | `float` | Optional oil target fraction greater than **0** and at most **1**. Defaults to **1.0**. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"refueling"` | success | A refueling job is active. |
| `"queued"` | success | The operation was added to the queue. |
| `"target_reached"` | rejection | The vehicle is already at or above the requested charge or fuel level. |
| `"not_docked"` | rejection | The requested vehicle is not docked at this station. |
| `"station_offline"` | transient | The station is offline. |
| `"no_oil"` | rejection | No oil is available for the operation. |
| `"invalid"` | rejection | One or more supplied arguments are outside the accepted domain. |

##### `.dispatch_rescue(drone_name: str, target_level: float = 1.0) → ActionResult` *(self only)*

Send the recovery vehicle to a field drone chosen by your script; there is no hidden fuel threshold. Electric drones are charged in the field to `target_level` and resume their route. Heli drones are carried home, then join the normal refueling queue. Scrambled drones are also carried home so docking can reset their electronics. `target_level` must be above **0** and at most **1**, and defaults to **1.0**. Launch requires station power, but the mission can finish through a later outage. Self-only.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `drone_name` | `str` | Display name or id of the stranded drone to service. |
| `target_level` | `float` | Optional battery/oil target greater than **0** and at most **1**. Electric rescue charges to it in the field; heli recovery submits it to the station refueling FIFO. Defaults to **1.0**. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"already_dispatched"` | rejection | This station already has an active rescue, or the requested target is already assigned to a rescue. |
| `"station_offline"` | transient | The station is offline. |
| `"not_found"` | rejection | The requested object, target, or record does not exist. |
| `"not_stranded"` | rejection | The target is not considered stranded. |
| `"invalid"` | rejection | One or more supplied arguments are outside the accepted domain. |

##### `.cancel_rescue() → ActionResult` *(self only)*

Abort the in-flight rescue. The drone is released at its current position (it keeps any charge already delivered) and the recovery vehicle flies home. Self-only.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"no_rescue"` | rejection | There is no active rescue mission. |

##### `.is_rescuing() → bool`

`True` while the recovery vehicle is on a rescue mission.

- **Returns** `bool`. `True` while the service vehicle is mid-mission.

##### `.get_rescue_target() → str`

Mission target's display name while the recovery vehicle is outbound, servicing, carrying, or returning; empty string when idle.

- **Returns** `str`. The mission target's display name while the service vehicle is outbound, servicing, carrying, or returning; empty string when idle.

##### `.stop(drone_id: str) → ActionResult` *(self only)*

Cancel one active or queued job on this station, whether it is a charge or a refuel. The drone keeps any energy or oil already delivered.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `drone_id` | `str` | Display name or id of a queued drone |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_found"` | rejection | The requested object, target, or record does not exist. |
| `"invalid"` | rejection | One or more supplied arguments are outside the accepted domain. |

##### `.clear_queue() → CountResult` *(self only)*

Clear every active or queued charge and refuel job on this station. Docked drones stay parked and keep their current battery and oil.

- **Returns** `CountResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.count`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Command completed. Affected entries or units: `.count`. |
| `"no_op"` | success | The command affected no entries or units. |

##### `.get_active() → list[str]`

List of drone ids currently occupying active service bays (charging or refueling). An oil-blocked heli is waiting, not active.

- **Returns** `list[str]`. Ids of the drones occupying active service bays (charging or refueling). Oil-blocked heli jobs are waiting, not active.

##### `.get_queue() → list[str]`

One FIFO list of drone ids across electric charging and heli refueling. Oil-blocked helis stay in order while ready later jobs may use otherwise-idle bays.

- **Returns** `list[str]`. Queued drone ids, first in first out, across electric charging and heli refueling. Oil-blocked helis stay in this order while ready later jobs may use otherwise-idle bays.

##### `.status(drone_id: str) → dict[str, JsonValue]`

Detailed status for one drone's service job. Electric drones return a `dict` with `state`, `target_level`, `battery_wh`, `capacity_wh`, `rate_w`, `bay_index`, `queue_index`. Heli drones return `state`, `target_level`, `oil_tons`, `capacity_tons`, `rate_tons_per_hour`, `bay_index`, `queue_index`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `drone_id` | `str` | Display name or id of a drone |

- **Returns** `dict[str, JsonValue]`. The drone's active or queued service job. Electric: `state`, `target_level`, `battery_wh`, `capacity_wh`, `rate_w`, `bay_index`, `queue_index`. Heli: `state`, `target_level`, `oil_tons`, `capacity_tons`, `rate_tons_per_hour`, `bay_index`, `queue_index`.

##### `.get_bay_count() → int`

Number of simultaneous service bays.

- **Returns** `int`. How many drones can be serviced at once.

##### `.get_charge_rate(drone_id: str) → float`

Returns the Wh/h currently being pushed into the named electric drone (**0** if it is not in an active bay).

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `drone_id` | `str` | Display name or id of a docked electric drone |

- **Returns** `float`. **Wh/h** currently being pushed into that electric drone, **0** if it is not being charged.

##### `.get_refuel_rate(drone_id: str) → float`

Returns the oil t/h currently being pushed into the named heli drone (**0** if it is not in an active bay or the station has no oil).

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `drone_id` | `str` | Display name or id of a docked heli drone |

- **Returns** `float`. **t/h** currently being pushed into that heli drone, **0** if it is not being refueled.

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

*Components / Logistics & Orders*
