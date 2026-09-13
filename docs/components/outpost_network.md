# Component: outpost_network

> **Category:** Infrastructure & Fluids | **Component Name:** Outpost Network

Read-only index of every owned outpost, including home. Use it for routing, deployment planning, capacity dashboards, and nearest-service decisions without hardcoding `outpost_1`, `outpost_2`, etc. An outpost's `.x` and `.y` identify its footprint anchor. For an at-building action, select that outpost's `BuildingRef` and route to `.position`. Construction planning belongs to Plan Mode and the shared `construction_blueprint` component; physical work belongs to Constructor scripts.

**Returned by:** `get_component("outpost_network")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.outposts()`

All owned outposts as `OutpostRef` snapshots. Each ref includes `.id`, `.name`, `.x`, `.y`, `.is_home`, `.buildings_used`, `.buildings_capacity`, and `.is_full`. The coordinates are the top-left footprint anchor, not a particular building's docking point.

- **Returns** List of `OutpostRef` snapshots. Re-query for fresh names/building counts.

##### `.home()`

The home outpost as an `OutpostRef`.

- **Returns** `OutpostRef` snapshot

##### `.nearest(x, y)`

Nearest owned outpost to the given world coordinate. Useful before routing a vehicle home to recharge or choosing where a constructor should stage.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | World X coordinate |
| `y` | `number` | World Y coordinate |

- **Returns** Nearest `OutpostRef` snapshot

*Components / Infrastructure & Fluids*
