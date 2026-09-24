# Component: vehicle_charging_station

> **Category:** Power | **Component Name:** Vehicle Charging Station

Grid-powered fleet charging: Mk I provides **1 bay / 30 W**, Mk II **2 bays / 120 W**, and Mk III **4 bays / 240 W**. Idle bays pool onto one vehicle; several vehicles share the budget. A script queues charging or dispatches rescue.

| Field | Value |
| --- | --- |
| Type | Mining |
| Power in | Variable (draws from grid) |
| Tiers | Mk II and Mk III |

### How to obtain

1. Requires the **Vehicle Charging Station** research (Oxygen 9).
2. Buy from the Shop for 1,200 cr.

**Returned by:** `self / get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

##### `.outpost: OutpostRef`

The outpost where this building is deployed. The returned `OutpostRef` includes its stable id, display name, biome, position, capacity, and `buildings()` query. Read the property again when you need current values.

- **Returns** `OutpostRef` for the outpost where this building is deployed.

### Methods

##### `.get_docked() → list[str]`

List of vehicle instance ids parked inside the station's local service pad plus its **~2 m** margin, or inside the owning Outpost's common service area. Returns ids, not vehicles; dereference each via `get_component(id)` to read battery state, cargo, or anything else. Empty list means no vehicles docked. Call each iteration; the list can change between ticks as vehicles drive in or out.

- **Returns** List of vehicle instance ids docked at this station. Read each vehicle's state via `get_component(id)`.

##### `.charge(vehicle_id: str, target_level: float = 1.0) → ActionResult` *(self only)*

Queue a docked rover or Pioneer to charge until its battery reaches `target_level` (greater than **0** and at most **1**, defaults to **1.0**). The station decides whether it starts immediately or waits behind another vehicle: Mk I charges one vehicle at a time, Mk II two, Mk III four. The fewer vehicles active, the faster each charges (idle bays pool). Example: `self.charge("pioneer_1", 0.8)` means 'charge this vehicle until it reaches 80%'.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `vehicle_id` | `str` | Display name or id of a docked rover or pioneer |
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

##### `.stop(vehicle_id: str) → ActionResult` *(self only)*

Remove a vehicle from this station's charge queue. It does not move the vehicle or change its current battery.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `vehicle_id` | `str` | Display name or id of a queued vehicle |

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

Clear every queued charge job on this station. Rescue-drone missions are separate and are not cancelled by this.

- **Returns** `CountResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.count`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The command affected `.count` entries or units. |
| `"no_op"` | success | The command affected no entries or units. |

##### `.get_active() → list[str]`

List of vehicle ids currently occupying active charging bays. Mk I returns at most one id, Mk II two, Mk III four. These are the vehicles sharing the station's pooled budget this tick.

- **Returns** List of vehicle ids currently occupying charging bays

##### `.get_queue() → list[str]`

List of vehicle ids in charge-queue order. The first `get_bay_count()` entries are the ones that can be active right now, assuming they are still docked and below their target.

- **Returns** List of queued vehicle ids in order; the first `get_bay_count()` entries can be active

##### `.status(vehicle_id: str) → dict[str, JsonValue]`

Detailed status for one vehicle: a dict with `state` (`"charging"`, `"queued"`, `"docked"`, `"target_reached"`, `"not_docked"`, `"station_offline"`, or `"missing"`), `target_level`, `battery_wh`, `capacity_wh`, `rate_w` (the pooled watts this vehicle is actually receiving, rises as fewer vehicles share the bays), `bay_index`, and `queue_index`. Use this for dashboards or queue managers.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `vehicle_id` | `str` | Display name or id of a vehicle |

- **Returns** A dict with `state`, `target_level`, `battery_wh`, `capacity_wh`, `rate_w`, `bay_index`, `queue_index`

##### `.tier() → int`

Permanently installed Charging Station tier as an integer (**1-3**). Mk II raises bay count and bay rate; Mk III raises bay count again.

- **Returns** Integer: permanently installed Charging Station tier (**1-3**).

##### `.get_bay_count() → int`

Number of simultaneous vehicle charging bays. Mk I is **1**, Mk II **2**, Mk III **4**.

- **Returns** Number of simultaneous vehicle charging bays

##### `.get_bay_rate() → float`

Watts pushed by a single bay (**30 W** Mk I, **60 W** Mk II/III). With bay pooling a lone vehicle draws every idle bay, so its actual rate is up to `get_bay_count() × get_bay_rate()`, read `get_charge_rate(id)` for what a specific vehicle is really getting. The station's total grid draw is `get_bay_count() × get_bay_rate()` whenever any vehicle is charging, plus rescue-drone draw if a rescue is out.

- **Returns** Watts pushed by each active bay

##### `.get_charge_rate(vehicle_id: str) → float`

Actual watts being pushed into the specified vehicle right now, the station's total budget (`get_bay_count() × get_bay_rate()`) split evenly across every active vehicle. A lone vehicle gets the whole budget (Mk III: **240 W**); the more vehicles charging, the lower each one's share. Returns **0** if the vehicle is not occupying an active bay.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `vehicle_id` | `str` | Display name or id of a docked vehicle |

- **Returns** Number (W currently being pushed into that vehicle)

##### `.dispatch_rescue(vehicle_name: str, target_level: float = 1.0) → ActionResult` *(self only)*

Send a field-service drone to a Rover or Pioneer by display name or id. `target_level` is a battery fraction greater than **0** and at most **1** and defaults to **1.0**. Dispatch stops the target vehicle so the drone can reach it. The station must be powered at launch, but the drone can finish its mission through a later outage. If the target reaches a powered Charging Station first, the remaining request joins that station's queue. Only one rescue can run at a time; call `cancel_rescue()` to recall it.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `vehicle_name` | `str` | Display name or instance id of the rover/Pioneer to service. |
| `target_level` | `float` | Optional battery target fraction greater than **0** and at most **1**. Defaults to **1.0**. |

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
| `"invalid"` | rejection | One or more supplied arguments are outside the accepted domain. |

##### `.cancel_rescue() → ActionResult` *(self only)*

Recall this station's active field-service drone. If the drone was outbound or trickle-charging, the target vehicle is released immediately and keeps any charge already delivered while the drone returns to the station.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_found"` | rejection | The requested object, target, or record does not exist. |

##### `.is_rescuing() → bool`

`True` while a rescue drone is deployed (out, at the target, or returning). A recalled drone still counts as rescuing until it reaches the station, but the target vehicle is released as soon as `cancel_rescue()` succeeds. Use before `dispatch_rescue()` to avoid the `"already_dispatched"` rejection: `if not self.is_rescuing(): self.dispatch_rescue(name)`. Exactly one drone at a time, queue rescues manually if you need more.

- **Returns** Boolean

##### `.get_rescue_target() → str`

Display name of the vehicle currently being rescued, or empty string if the drone is idle. Use for dashboards ("rescuing Rover 1") or to decide whether to wait vs send a different vehicle to pick up slack.

- **Returns** String (display name of the vehicle being rescued, or empty)

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Terraforming*
