# Data Types: Infrastructure And Fluids

Complete property specifications, descriptions, units, and return types from the official documentation.

## Index

- [`Construction`](#construction) (INFRASTRUCTURE & FLUIDS)
- [`FluidPort`](#fluidport) (INFRASTRUCTURE & FLUIDS)
- [`FluidConnection`](#fluidconnection) (INFRASTRUCTURE & FLUIDS)
- [`Pipe`](#pipe) (INFRASTRUCTURE & FLUIDS)
- [`PowerGrid`](#powergrid) (INFRASTRUCTURE & FLUIDS)
- [`PowerGridMember`](#powergridmember) (INFRASTRUCTURE & FLUIDS)
- [`PowerSummary`](#powersummary) (INFRASTRUCTURE & FLUIDS)
- [`BlueprintPlanResult`](#blueprintplanresult) (INFRASTRUCTURE)

---

## Construction

**Returned by:** .pending_constructions() / .active_constructions() / .paused_constructions()

### Properties

##### `.id`

Unique blueprint id. Pass to `self.constructor.execute(id)`.

- **Returns** `string`

##### `.kind`

What's being built or removed. One of `"pipe"` / `"power_line"` / `"gas_bridge"` / `"liquid_bridge"` / `"power_bridge"` / `"deconstruct"` / `"outpost"` / `"thermal_cap"` / `"water_pump"` / `"oil_pump"` / `"exotic_gas_cap"` / `"exotic_spring_tap"` / `"mining_drill"` / `"mining_drill_industrial"` / `"mining_drill_heavy"`.

- **Returns** `string`
- **Possible values** `"pipe"`, `"power_line"`, `"gas_bridge"`, `"liquid_bridge"`, `"power_bridge"`, `"deconstruct"`, `"outpost"`, `"thermal_cap"`, `"water_pump"`, `"oil_pump"`, `"exotic_gas_cap"`, `"exotic_spring_tap"`, `"mining_drill"`, `"mining_drill_industrial"`, `"mining_drill_heavy"`

##### `.medium`

Physical utility layer: `"gas"`, `"liquid"`, or `"power"`; `None` for point structures. Pipe jobs keep `.kind == "pipe"`, so use this field to distinguish Gas Pipe from Liquid Pipe. Deconstruction reports the target's utility layer.

- **Returns** `Optional[string]`
- **Possible values** `"gas"`, `"liquid"`, `"power"`

##### `.position`

Tile-aligned world coordinates as a `Position` snapshot (`.x`, `.y`). Pioneer drives here to start/resume construction.

- **Returns** `Position`

##### `.progress`

Build completion **0-1** when this `Construction` snapshot was returned. Useful especially for paused work: sort by progress to resume the most-completed first; re-query construction lists for fresh progress.

- **Returns** `number`

##### `.required_item`

Item id the Pioneer must carry before executing this job, or `None` for deconstruction and paused jobs that have already started.

- **Returns** `Optional[string]`

##### `.required_count`

Units of `.required_item` needed to accept this job. Most single-piece jobs need 1; deconstruction needs 0.

- **Returns** `number`

*Types / Infrastructure & Fluids*

---

## FluidPort

**Returned by:** any `<fluid>_in` / `<fluid>_out` property on a flow-network machine

### Related object types

- `FluidConnection`

### Methods

##### `.connect(target)`

Record or replace this port's one declared target, using a stable machine id or display name. The target must expose a compatible opposite-direction port. Either the provider or consumer may declare the relationship; one declaration is enough. Local machines transfer directly, while remote intent waits for any completed conflict-free same-medium component reaching both anchors.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `target` | `string` | Stable id or display name of the provider or consumer |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_found"` | rejection | The requested object, target, or record does not exist. |
| `"incompatible"` | rejection | The selected endpoints or values are incompatible. |

##### `.disconnect()`

Clear only this port's declared target. Buffered fluid remains. If the peer independently declared the same relationship, that reverse declaration remains active.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.connected_to()`

Display name of the target declared by this port, or empty string. It does not list compatible reverse declarations owned by peer ports.

- **Returns** `string`

##### `.connected_id()`

Stable id of the target declared by this port, or empty string. `connect()` accepts an id or a display name, so compare against this when you need the identity to match what you passed: `connected_to()` answers with the renameable name. For every effective peer, including declarations owned by the other side, use `connections()`.

- **Returns** `string`

##### `.connections()`

Read-only snapshots of every effective peer relationship on this port, including declarations authored by peer ports. Each `FluidConnection` reports the peer, exact fluid when known, declaration ownership, and structural state. Pipe ids are deliberately not exposed or selected.

- **Returns** `list<FluidConnection>`

##### `.level()`

Current tons of fluid buffered at this port. Pass-through source ports such as Pump outputs store nothing and therefore read **0**.

- **Returns** `number`

##### `.capacity()`

Max tons this port's buffer can hold.

- **Returns** `number`

##### `.flow_rate()`

Current total live flow in **t/h**. **0** may mean idle, starved, full, unreachable, conflicted, or waiting across a simulation timing boundary; it does not erase the connection or pipe identity.

- **Returns** `number`

*Types / Infrastructure & Fluids*

---

## FluidConnection

**Returned by:** FluidPort.connections()

### Properties

##### `.machine_id`

Stable id of the peer machine.

- **Returns** `string`

##### `.machine_name`

Current display name of the peer machine.

- **Returns** `string`

##### `.fluid`

Exact fluid established by this relationship, or `None` while the relationship is neutral or incompatible.

- **Returns** `Optional[string]`
- **Possible values** `"steam"`, `"water"`, `"oil"`, `"frozen_essence"`, `"coastal_essence"`, `"geothermal_essence"`, `"volcanic_essence"`, `"deep_essence"`, `"ammonia"`, `"swamp_gas"`, `"raw_sulfur_gas"`, `"sulfur_gas"`, `"raw_chlorine"`, `"chlorine"`, `"brine"`, `"raw_cryofluid"`, `"cryofluid"`, `"raw_quicksilver"`, `"quicksilver"`

##### `.declared_by`

Who owns the durable declaration: `"self"`, `"peer"`, or `"both"`. One side is sufficient for transport.

- **Returns** `string`
- **Possible values** `"self"`, `"peer"`, `"both"`

##### `.state`

Connection state: `"local"` for a direct same-outpost link; `"ready"` for a usable remote pipe network; `"unreachable"` when no completed component can be assigned; `"conflict"` when the assigned component carries different fluid connections; `"neutral"` before a fluid is known; or `"incompatible"` when the two fluids disagree.

- **Returns** `string`
- **Possible values** `"local"`, `"ready"`, `"unreachable"`, `"conflict"`, `"neutral"`, `"incompatible"`

*Types / Infrastructure & Fluids*

---

## Pipe

**Returned by:** list_pipes() / get_pipe(pipe_id)

### Properties

##### `.id`

Unique pipe identifier.

- **Returns** `string`

### Methods

##### `.start()`

Geometric start coordinate of this pipe piece as a `Position`. This is construction geometry, not flow direction. Returns `None` only if malformed state contains no segment geometry.

- **Returns** `Optional[Position]`

##### `.end()`

Geometric end coordinate of this pipe piece as a `Position`. This is construction geometry, not flow direction. Returns `None` only if malformed state contains no segment geometry.

- **Returns** `Optional[Position]`

##### `.type()`

Pipe hardware medium: `"gas"` or `"liquid"`. Use `contents()` for the exact substance established by complete provider-consumer connections.

- **Returns** `string`
- **Possible values** `"gas"`, `"liquid"`

##### `.contents()`

The one exact fluid established by complete player connections whose locations this physical component reaches, such as `"steam"`, `"water"`, or `"oil"`. Returns `None` when there is no complete connection or multiple exact substances conflict. Activity, power, throttle, flow, and headroom do not change this identity.

- **Returns** `Optional[string]`
- **Possible values** `"steam"`, `"water"`, `"oil"`, `"frozen_essence"`, `"coastal_essence"`, `"geothermal_essence"`, `"volcanic_essence"`, `"deep_essence"`, `"ammonia"`, `"swamp_gas"`, `"raw_sulfur_gas"`, `"sulfur_gas"`, `"raw_chlorine"`, `"chlorine"`, `"brine"`, `"raw_cryofluid"`, `"cryofluid"`, `"raw_quicksilver"`, `"quicksilver"`

##### `.conflicting_contents()`

Sorted exact substances established by complete provider-consumer connections when more than one uses this physical component, or an empty list. A non-empty result means flow is halted.

- **Returns** `list[string]`

##### `.connections()`

Diagnostic machine-port claims established on this physical component. Each dictionary contains `machine_id`, `port`, `direction`, `fluid`, and a representative `pipe_id` from the component; players never connect to that pipe id directly.

- **Returns** `list[dict[str, string]]`

##### `.incompatible_sinks()`

Ids of directly connected consumers that cannot accept `contents()`. Those consumers receive nothing, while compatible branches continue flowing. Live read.

- **Returns** `list[string]`

##### `.is_complete()`

Boolean: `True` once the Constructor has finished laying the pipe and flow can run. Live read.

- **Returns** `boolean`

##### `.length()`

Total length of the pipe in meters, summed over every H/V segment.

- **Returns** `number`

##### `.laying_head()`

`[x, y]` coordinates of the current laying head while incomplete, or `None` once complete. Live read.

- **Returns** `Optional[[number, number]]`

##### `.flow_rate()`

Tons per world hour (`t/h`) currently moving through the pipe. **0** while incomplete, stalled, source-empty, or conflicted. Live read.

- **Returns** `number`

##### `.state()`

Current pipe state: one of `"flowing"` / `"stalled"` / `"incomplete"` / `"no_source"` / `"conflict"`. Live read.

- **Returns** `string`
- **Possible values** `"flowing"`, `"stalled"`, `"incomplete"`, `"no_source"`, `"conflict"`

*Types / Infrastructure & Fluids*

---

## PowerGrid

**Returned by:** power_control.grids() / power_control.grid(target_id)

### Related object types

- `PowerGridMember`

### Properties

##### `.anchor_id`

Deterministic entity id that identifies this connected grid right now and can be passed to `power.grid(...)`. Re-discover grids after rewiring because merging or splitting a grid can change its anchor.

- **Returns** `string`

##### `.outpost_ids`

Outpost ids connected to this grid, sorted for deterministic iteration. The list is empty for a field-only grid.

- **Returns** `list<string>`

##### `.machine_ids`

Building and field power-structure ids assigned to this grid, sorted for deterministic iteration. Mobile units and ship equipment are excluded because their deployment location is not an electrical connection.

- **Returns** `list<string>`

##### `.members`

Power details for every building and field power structure on this grid as `PowerGridMember` snapshots. Use each member's `.id` with `get_component(...)` for type-specific recipe, material, or control methods.

- **Returns** `list<PowerGridMember>`

##### `.generated`

Power currently supplied by this grid's active generators in W when this snapshot was returned.

- **Returns** `number`

##### `.consumed`

Power currently drawn by this grid's active consumers in W when this snapshot was returned.

- **Returns** `number`

##### `.net`

Current grid generation minus consumption in W. A negative value means the current load needs stored energy.

- **Returns** `number`

##### `.stored`

Energy held in conventional batteries on this grid in Wh.

- **Returns** `number`

##### `.capacity`

Total conventional battery capacity on this grid in Wh.

- **Returns** `number`

##### `.reserve_stored`

Energy currently banked by Lightning Rods on this grid in Wh. This reserve is spent only after conventional batteries and never absorbs ordinary generation surplus.

- **Returns** `number`

##### `.reserve_capacity`

Total Lightning Rod reserve capacity on this grid in Wh.

- **Returns** `number`

##### `.has_generator`

`True` when this grid contains a generator, even when its current output is 0 W.

- **Returns** `boolean`

*Types / Infrastructure & Fluids*

---

## PowerGridMember

**Returned by:** PowerGrid.members

### Properties

##### `.id`

Stable stationary machine instance id. Pass it to `get_component(...)`, `power.grid(...)`, or breaker APIs.

- **Returns** `string`

##### `.name`

Display name when this snapshot was returned.

- **Returns** `string`

##### `.type_id`

Stable machine type id, such as `"solar_generator"`, `"battery"`, or `"smelter"`.

- **Returns** `string`

##### `.outpost_id`

Owning outpost id, or an empty string for an independently placed field structure.

- **Returns** `string`

##### `.powered`

`True` when the machine's power state was on as this snapshot was returned.

- **Returns** `boolean`

##### `.roles`

Power capabilities of this machine: any combination of `"generator"`, `"consumer"`, `"storage"`, and `"reserve"`. An empty list means the machine has no direct electrical role but is installed at a connected outpost.

- **Returns** `list<string>`

##### `.generated`

Power this machine is currently supplying in W. A generator may report 0 W because it is off, idle, unfueled, or lacks sunlight.

- **Returns** `number`

##### `.consumed`

Power this machine is currently drawing in W. Powered-off and idle machines report 0 W.

- **Returns** `number`

##### `.stored`

Energy held by this conventional battery in Wh, or 0 for another machine role.

- **Returns** `number`

##### `.capacity`

Conventional battery capacity in Wh, or 0 for another machine role.

- **Returns** `number`

##### `.reserve_stored`

Lightning reserve held by this machine in Wh, or 0 for another machine role.

- **Returns** `number`

##### `.reserve_capacity`

Lightning reserve capacity in Wh, or 0 for another machine role.

- **Returns** `number`

*Types / Infrastructure & Fluids*

---

## PowerSummary

**Returned by:** power_control.total()

### Properties

##### `.grid_count`

Number of independent completed power grids included in this snapshot.

- **Returns** `number`

##### `.generated`

Power currently supplied across every grid in W when this snapshot was returned.

- **Returns** `number`

##### `.consumed`

Power currently drawn across every grid in W when this snapshot was returned.

- **Returns** `number`

##### `.net`

Planet-wide generation minus consumption in W across every grid.

- **Returns** `number`

##### `.stored`

Energy held in conventional batteries across every grid in Wh.

- **Returns** `number`

##### `.capacity`

Total conventional battery capacity across every grid in Wh.

- **Returns** `number`

##### `.reserve_stored`

Energy banked by Lightning Rods across every grid in Wh.

- **Returns** `number`

##### `.reserve_capacity`

Total Lightning Rod reserve capacity across every grid in Wh.

- **Returns** `number`

*Types / Orders & Comms*

---

## BlueprintPlanResult

**Returned by:** construction_blueprint planning commands

### Properties

##### `.status`

Stable planning outcome. Branch on this field before reading `.blueprint_ids`.

- **Returns** `string`
- **Possible values** `"ok"`, `"locked"`, `"invalid_kind"`, `"invalid_rotation"`, `"invalid_medium"`, `"invalid_axis"`, `"invalid_layer"`, `"out_of_bounds"`, `"wrong_target"`, `"unsurveyed_target"`, `"too_hard"`, `"target_claimed"`, `"occupied"`, `"clearance"`, `"invalid_route"`, `"blocked"`, `"already_exists"`, `"already_queued"`, `"ambiguous_target"`, `"nothing_here"`

##### `.message`

Player-readable explanation of the exact planning outcome.

- **Returns** `string`

##### `.blueprint_ids`

Newly created blueprint ids. Empty for every outcome except `"ok"`.

- **Returns** `list<string>`

*Types / System*

---
