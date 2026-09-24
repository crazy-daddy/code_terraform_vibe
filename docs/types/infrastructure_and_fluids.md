# Data Types: Infrastructure And Fluids

Complete property specifications, descriptions, units, and return types from the official documentation.

## Index

- [`ComputerDeployResult`](#computerdeployresult) (INFRASTRUCTURE & FLUIDS)
- [`Construction`](#construction) (INFRASTRUCTURE & FLUIDS)
- [`FluidPort`](#fluidport) (INFRASTRUCTURE & FLUIDS)
- [`FluidConnection`](#fluidconnection) (INFRASTRUCTURE & FLUIDS)
- [`Pipe`](#pipe) (INFRASTRUCTURE & FLUIDS)
- [`PowerGrid`](#powergrid) (INFRASTRUCTURE & FLUIDS)
- [`PowerGridMember`](#powergridmember) (INFRASTRUCTURE & FLUIDS)
- [`PowerSummary`](#powersummary) (INFRASTRUCTURE & FLUIDS)
- [`RunControlStatus`](#runcontrolstatus) (INFRASTRUCTURE & FLUIDS)
- [`ScriptVariantRef`](#scriptvariantref) (INFRASTRUCTURE & FLUIDS)
- [`BlueprintPlanResult`](#blueprintplanresult) (INFRASTRUCTURE)

---

## ComputerDeployResult

**Returned by:** computer.deploy()

### Properties

##### `.status: str`

Stable deploy outcome.

- **Returns** `str`
- **Possible values** `"ok"`, `"no_kit"`, `"locked"`, `"not_deployable"`, `"deploy_limit"`, `"location_not_found"`, `"wrong_biome_for_machine"`, `"duplicate_outpost_machine"`, `"missing_drone_station"`, `"drone_station_full"`

##### `.message: str`

Localized explanation of what happened, for logs and the player.

- **Returns** `str`

##### `.machine_id: str`

Id of the machine that was created, empty when nothing was deployed. Pass it to `get_component()` to read the new machine.

- **Returns** `str`

*Types / Infrastructure & Fluids*

## Construction

**Returned by:** .pending_constructions() / .active_constructions() / .paused_constructions()

### Properties

##### `.id: str`

Unique blueprint id. Pass to `self.constructor.execute(id)`.

- **Returns** `str`

##### `.kind: str`

What's being built or removed. One of `"pipe"` / `"power_line"` / `"gas_bridge"` / `"liquid_bridge"` / `"power_bridge"` / `"deconstruct"` / `"outpost"` / `"thermal_cap"` / `"water_pump"` / `"oil_pump"` / `"exotic_gas_cap"` / `"exotic_spring_tap"` / `"mining_drill"` / `"mining_drill_industrial"` / `"mining_drill_heavy"`.

- **Returns** `str`
- **Possible values** `"pipe"`, `"power_line"`, `"gas_bridge"`, `"liquid_bridge"`, `"power_bridge"`, `"deconstruct"`, `"outpost"`, `"thermal_cap"`, `"water_pump"`, `"oil_pump"`, `"exotic_gas_cap"`, `"exotic_spring_tap"`, `"mining_drill"`, `"mining_drill_industrial"`, `"mining_drill_heavy"`

##### `.medium: str | None`

Physical utility layer: `"gas"`, `"liquid"`, or `"power"`; `None` for point structures. Pipe jobs keep `.kind == "pipe"`, so use this field to distinguish Gas Pipe from Liquid Pipe. Deconstruction reports the target's utility layer.

- **Returns** `str | None`
- **Possible values** `"gas"`, `"liquid"`, `"power"`

##### `.position: Position`

Tile-aligned world coordinates as a `Position` snapshot (`.x`, `.y`). Pioneer drives here to start/resume construction.

- **Returns** `Position`

##### `.progress: float`

Build completion **0-1** when this `Construction` snapshot was returned. Useful especially for paused work: sort by progress to resume the most-completed first; re-query construction lists for fresh progress.

- **Returns** `float`

##### `.required_item: str | None`

Item id the Pioneer must carry before executing this job, or `None` for deconstruction and paused jobs that have already started.

- **Returns** `str | None`

##### `.required_count: int`

Units of `.required_item` needed to accept this job. Most single-piece jobs need 1; deconstruction needs 0.

- **Returns** `int`

*Types / Infrastructure & Fluids*

## FluidPort

**Returned by:** any `<fluid>_in` / `<fluid>_out` property on a flow-network machine

### Related object types

- `FluidConnection`

### Methods

##### `.connect(target: str) → ActionResult`

Record or replace this port's one declared target, using a stable machine id or display name. The target must expose a compatible opposite-direction port. Either the provider or consumer may declare the relationship; one declaration is enough. Local machines transfer directly, while remote intent waits for any completed conflict-free same-medium component reaching both anchors.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `target` | `str` | Stable id or display name of the provider or consumer |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_found"` | rejection | The requested object, target, or record does not exist. |
| `"incompatible"` | rejection | The selected endpoints or values are incompatible. |

##### `.disconnect() → ActionResult`

Clear only this port's declared target. Buffered fluid remains. If the peer independently declared the same relationship, that reverse declaration remains active.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.connected_to() → str`

Display name of the target declared by this port, or empty string. It does not list compatible reverse declarations owned by peer ports.

- **Returns** `str`

##### `.connected_id() → str`

Stable id of the target declared by this port, or empty string. `connect()` accepts an id or a display name, so compare against this when you need the identity to match what you passed: `connected_to()` answers with the renameable name. For every effective peer, including declarations owned by the other side, use `connections()`.

- **Returns** `str`

##### `.connections() → list[FluidConnection]`

Read-only snapshots of every effective peer relationship on this port, including declarations authored by peer ports. Each `FluidConnection` reports the peer, exact fluid when known, declaration ownership, and structural state. Pipe ids are deliberately not exposed or selected.

- **Returns** `list[FluidConnection]`

##### `.level() → float`

Current tons of fluid buffered at this port. Pass-through source ports such as Pump outputs store nothing and therefore read **0**.

- **Returns** `float`

##### `.capacity() → float`

Max tons this port's buffer can hold.

- **Returns** `float`

##### `.flow_rate() → float`

Current total live flow in **t/h**. **0** may mean idle, starved, full, unreachable, conflicted, or waiting across a simulation timing boundary; it does not erase the connection or pipe identity.

- **Returns** `float`

*Types / Infrastructure & Fluids*

## FluidConnection

**Returned by:** FluidPort.connections()

### Properties

##### `.machine_id: str`

Stable id of the peer machine.

- **Returns** `str`

##### `.machine_name: str`

Current display name of the peer machine.

- **Returns** `str`

##### `.fluid: str | None`

Exact fluid established by this relationship, or `None` while the relationship is neutral or incompatible.

- **Returns** `str | None`
- **Possible values** `"steam"`, `"water"`, `"oil"`, `"frozen_essence"`, `"coastal_essence"`, `"geothermal_essence"`, `"volcanic_essence"`, `"deep_essence"`, `"ammonia"`, `"swamp_gas"`, `"raw_sulfur_gas"`, `"sulfur_gas"`, `"raw_chlorine"`, `"chlorine"`, `"brine"`, `"raw_cryofluid"`, `"cryofluid"`, `"raw_quicksilver"`, `"quicksilver"`

##### `.declared_by: str`

Who owns the durable declaration: `"self"`, `"peer"`, or `"both"`. One side is sufficient for transport.

- **Returns** `str`
- **Possible values** `"self"`, `"peer"`, `"both"`

##### `.state: str`

Connection state: `"local"` for a direct same-outpost link; `"ready"` for a usable remote pipe network; `"unreachable"` when no completed component can be assigned; `"conflict"` when the assigned component carries different fluid connections; `"neutral"` before a fluid is known; or `"incompatible"` when the two fluids disagree.

- **Returns** `str`
- **Possible values** `"local"`, `"ready"`, `"unreachable"`, `"conflict"`, `"neutral"`, `"incompatible"`

*Types / Infrastructure & Fluids*

## Pipe

**Returned by:** list_pipes() / get_pipe(pipe_id)

### Properties

##### `.id: str`

Unique pipe identifier.

- **Returns** `str`

### Methods

##### `.start() → Position | None`

Geometric start coordinate of this pipe piece as a `Position`. This is construction geometry, not flow direction. Returns `None` only if malformed state contains no segment geometry.

- **Returns** `Position | None`

##### `.end() → Position | None`

Geometric end coordinate of this pipe piece as a `Position`. This is construction geometry, not flow direction. Returns `None` only if malformed state contains no segment geometry.

- **Returns** `Position | None`

##### `.type() → str`

Pipe hardware medium: `"gas"` or `"liquid"`. Use `contents()` for the exact substance established by complete provider-consumer connections.

- **Returns** `str`
- **Possible values** `"gas"`, `"liquid"`

##### `.contents() → str | None`

The one exact fluid established by complete player connections whose locations this physical component reaches, such as `"steam"`, `"water"`, or `"oil"`. Returns `None` when there is no complete connection or multiple exact substances conflict. Activity, power, throttle, flow, and headroom do not change this identity.

- **Returns** `str | None`
- **Possible values** `"steam"`, `"water"`, `"oil"`, `"frozen_essence"`, `"coastal_essence"`, `"geothermal_essence"`, `"volcanic_essence"`, `"deep_essence"`, `"ammonia"`, `"swamp_gas"`, `"raw_sulfur_gas"`, `"sulfur_gas"`, `"raw_chlorine"`, `"chlorine"`, `"brine"`, `"raw_cryofluid"`, `"cryofluid"`, `"raw_quicksilver"`, `"quicksilver"`

##### `.conflicting_contents() → list[str]`

Sorted exact substances established by complete provider-consumer connections when more than one uses this physical component, or an empty list. A non-empty result means flow is halted.

- **Returns** `list[str]`

##### `.connections() → list[dict[str, str]]`

Diagnostic machine-port claims established on this physical component. Each dictionary contains `machine_id`, `port`, `direction`, `fluid`, and a representative `pipe_id` from the component; players never connect to that pipe id directly.

- **Returns** `list[dict[str, str]]`

##### `.incompatible_sinks() → list[str]`

Ids of directly connected consumers that cannot accept `contents()`. Those consumers receive nothing, while compatible branches continue flowing. Live read.

- **Returns** `list[str]`

##### `.is_complete() → bool`

Boolean: `True` once the Constructor has finished laying the pipe and flow can run. Live read.

- **Returns** `bool`

##### `.length() → int`

Total length of the pipe in meters, summed over every H/V segment.

- **Returns** `int`

##### `.laying_head() → list[int] | None`

`[x, y]` coordinates of the current laying head while incomplete, or `None` once complete. Live read.

- **Returns** `list[int] | None`

##### `.flow_rate() → float`

Tons per world hour (`t/h`) currently moving through the pipe. **0** while incomplete, stalled, source-empty, or conflicted. Live read.

- **Returns** `float`

##### `.state() → str`

Current pipe state: one of `"flowing"` / `"stalled"` / `"incomplete"` / `"no_source"` / `"conflict"`. Live read.

- **Returns** `str`
- **Possible values** `"flowing"`, `"stalled"`, `"incomplete"`, `"no_source"`, `"conflict"`

*Types / Infrastructure & Fluids*

## PowerGrid

**Returned by:** power_control.grids() / power_control.grid(target_id)

### Related object types

- `PowerGridMember`

### Properties

##### `.anchor_id: str`

Deterministic entity id that identifies this connected grid right now and can be passed to `power.grid(...)`. Re-discover grids after rewiring because merging or splitting a grid can change its anchor.

- **Returns** `str`

##### `.outpost_ids: list[str]`

Outpost ids connected to this grid, sorted for deterministic iteration. The list is empty for a field-only grid.

- **Returns** `list[str]`

##### `.machine_ids: list[str]`

Building and field power-structure ids assigned to this grid, sorted for deterministic iteration. Mobile units and ship equipment are excluded because their deployment location is not an electrical connection.

- **Returns** `list[str]`

##### `.members: list[PowerGridMember]`

Power details for every building and field power structure on this grid as `PowerGridMember` snapshots. Use each member's `.id` with `get_component(...)` for type-specific recipe, material, or control methods.

- **Returns** `list[PowerGridMember]`

##### `.generated: float`

Power currently supplied by this grid's active generators in W when this snapshot was returned.

- **Returns** `float`

##### `.consumed: float`

Power currently drawn by this grid's active consumers in W when this snapshot was returned.

- **Returns** `float`

##### `.net: float`

Current grid generation minus consumption in W. A negative value means the current load needs stored energy.

- **Returns** `float`

##### `.stored: float`

Energy held in conventional batteries on this grid in Wh.

- **Returns** `float`

##### `.capacity: float`

Total conventional battery capacity on this grid in Wh.

- **Returns** `float`

##### `.reserve_stored: float`

Energy currently banked by Lightning Rods on this grid in Wh. This reserve is spent only after conventional batteries and never absorbs ordinary generation surplus.

- **Returns** `float`

##### `.reserve_capacity: float`

Total Lightning Rod reserve capacity on this grid in Wh.

- **Returns** `float`

##### `.has_generator: bool`

`True` when this grid contains a generator, even when its current output is 0 W.

- **Returns** `bool`

*Types / Infrastructure & Fluids*

## PowerGridMember

**Returned by:** PowerGrid.members

### Properties

##### `.id: str`

Stable stationary machine instance id. Pass it to `get_component(...)`, `power.grid(...)`, or breaker APIs.

- **Returns** `str`

##### `.name: str`

Display name when this snapshot was returned.

- **Returns** `str`

##### `.type_id: str`

Stable machine type id, such as `"solar_generator"`, `"battery"`, or `"smelter"`.

- **Returns** `str`

##### `.outpost_id: str`

Owning outpost id, or an empty string for an independently placed field structure.

- **Returns** `str`

##### `.powered: bool`

`True` when the machine's power state was on as this snapshot was returned.

- **Returns** `bool`

##### `.roles: list[str]`

Power capabilities of this machine: any combination of `"generator"`, `"consumer"`, `"storage"`, and `"reserve"`. An empty list means the machine has no direct electrical role but is installed at a connected outpost.

- **Returns** `list[str]`

##### `.generated: float`

Power this machine is currently supplying in W. A generator may report 0 W because it is off, idle, unfueled, or lacks sunlight.

- **Returns** `float`

##### `.consumed: float`

Power this machine is currently drawing in W. Powered-off and idle machines report 0 W.

- **Returns** `float`

##### `.stored: float`

Energy held by this conventional battery in Wh, or 0 for another machine role.

- **Returns** `float`

##### `.capacity: float`

Conventional battery capacity in Wh, or 0 for another machine role.

- **Returns** `float`

##### `.reserve_stored: float`

Lightning reserve held by this machine in Wh, or 0 for another machine role.

- **Returns** `float`

##### `.reserve_capacity: float`

Lightning reserve capacity in Wh, or 0 for another machine role.

- **Returns** `float`

*Types / Infrastructure & Fluids*

## PowerSummary

**Returned by:** power_control.total()

### Properties

##### `.grid_count: int`

Number of independent completed power grids included in this snapshot.

- **Returns** `int`

##### `.generated: float`

Power currently supplied across every grid in W when this snapshot was returned.

- **Returns** `float`

##### `.consumed: float`

Power currently drawn across every grid in W when this snapshot was returned.

- **Returns** `float`

##### `.net: float`

Planet-wide generation minus consumption in W across every grid.

- **Returns** `float`

##### `.stored: float`

Energy held in conventional batteries across every grid in Wh.

- **Returns** `float`

##### `.capacity: float`

Total conventional battery capacity across every grid in Wh.

- **Returns** `float`

##### `.reserve_stored: float`

Energy banked by Lightning Rods across every grid in Wh.

- **Returns** `float`

##### `.reserve_capacity: float`

Total Lightning Rod reserve capacity across every grid in Wh.

- **Returns** `float`

*Types / Infrastructure & Fluids*

## RunControlStatus

**Returned by:** run.status()

### Properties

##### `.script_id: str`

The script attached to the requested machine slot.

- **Returns** `str`

##### `.state: str`

Current execution state: idle, running, paused, error, or completed. Sleeping and waiting for actions count as running.

- **Returns** `str`
- **Possible values** `"idle"`, `"running"`, `"paused"`, `"error"`, `"completed"`

##### `.variant_id: str`

Identity of the assigned variant, suitable for run.apply_variant().

- **Returns** `str`

##### `.variant_name: str`

Name of the assigned variant.

- **Returns** `str`

##### `.modified: bool`

True when the machine's working code differs from its saved named variant. Editing a shared variant elsewhere can cause this difference. Main always reads False because it tracks its own working code.

- **Returns** `bool`

##### `.source_pending: bool`

True when a running or paused script still has an older code version loaded than its current working code.

- **Returns** `bool`

##### `.editor_busy: bool`

True while an editor has pending changes or an unresolved conflict, or a recovered source draft differs from the current code.

- **Returns** `bool`

*Types / Infrastructure & Fluids*

## ScriptVariantRef

**Returned by:** run.variants()

### Properties

##### `.id: str`

Variant identifier passed to run.apply_variant(). Shared variants can be applied to compatible machines. Main belongs only to its original script. Renaming changes the id; reusing a deleted name in the same catalog reuses its id.

- **Returns** `str`

##### `.name: str`

The variant name shown in the editor.

- **Returns** `str`

##### `.description: str`

The description saved with the variant.

- **Returns** `str`

*Types / Orders & Comms*

## BlueprintPlanResult

**Returned by:** construction_blueprint planning commands

### Properties

##### `.status: str`

Stable planning outcome. Branch on this field before reading `.blueprint_ids`.

- **Returns** `str`
- **Possible values** `"ok"`, `"locked"`, `"invalid_kind"`, `"invalid_rotation"`, `"invalid_medium"`, `"invalid_axis"`, `"invalid_layer"`, `"out_of_bounds"`, `"wrong_target"`, `"unsurveyed_target"`, `"too_hard"`, `"target_claimed"`, `"occupied"`, `"clearance"`, `"invalid_route"`, `"blocked"`, `"already_exists"`, `"already_queued"`, `"ambiguous_target"`, `"nothing_here"`

##### `.message: str`

Player-readable explanation of the exact planning outcome.

- **Returns** `str`

##### `.blueprint_ids: list[str]`

Newly created blueprint ids. Empty for every outcome except `"ok"`.

- **Returns** `list[str]`

*Types / System*
