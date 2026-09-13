# Component: constructor_module

> **Category:** Vehicles & Modules | **Component Name:** Constructor Module

Pioneer-exclusive module for construction and deconstruction blueprints created in Plan Mode or by scripts: gas/liquid pipes, utility bridges, power lines, outposts, pumps, caps, and mining drills. Fits a `universal` slot. Load the required kits, segments, or bridge items into the Pioneer's cargo for build jobs, drive within interaction range of the blueprint position, then call `execute(blueprint_id)`. Deconstruction reclaims the dismantled kit or segment into the Pioneer's cargo. Internal outpost machines, including drone facilities, deploy directly from Inventory and are not Constructor jobs.

**Returned by:** `self.constructor`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.execute(blueprint_id)` *(self only)*

Pick up one Construction job from the shared planning queue and build or deconstruct it. Plan Mode and `get_component("construction_blueprint")` create equivalent jobs. Drive the Pioneer within interaction range of `blueprint.position` first, and use `get_component("construction_blueprint").pending_constructions()` to see what's ready. A Pioneer performs only one field action at a time. Stop, power loss, leaving the site, rescue, or removing the Constructor Module pauses paid work without losing its progress or materials. Resume the same id from `get_component("construction_blueprint").paused_constructions()`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `blueprint_id` | `string` | Blueprint id from `get_component("construction_blueprint").pending_constructions()`, `.active_constructions()`, or `.paused_constructions()`. |

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

*Components / Vehicles & Modules*
