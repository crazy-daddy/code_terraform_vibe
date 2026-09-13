# Component: power_control

> **Category:** Infrastructure & Fluids | **Component Name:** Power Control

Discover every independent power grid, inspect connected outposts, buildings, and field power structures, read generation, consumption, battery charge, and Lightning reserve, or operate machine breakers from one shared controller. Grid objects are snapshots of the latest completed power allocation. After changing a breaker or rewiring infrastructure, re-query on the next loop iteration for refreshed grid totals and membership.

**Returned by:** `get_component("power_control")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.grids()`

Returns every independent power grid on the planet as a fresh list of `PowerGrid` snapshots. Isolated completed outposts and field structures appear as their own grids, so scripts do not need to guess or hardcode grid ids.

- **Returns** Fresh list of every independent `PowerGrid` snapshot on the planet.

##### `.grid(target_id)`

Finds the grid containing `target_id`, which may be an outpost, building, or field power-structure id. Pass a returned grid's `.anchor_id` to look it up again. Returns `None` for an unknown, mobile, under-construction, non-grid, or currently unmapped target.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `target_id` | `string` | Outpost, building, or field power-structure instance id |

- **Returns** `Optional[PowerGrid]`
- **None means** `None` means the target is unknown, mobile, under construction, not a building or field power structure, or not part of a completed power grid.

*Outcomes*

| Status | Meaning |
| --- | --- |
| `None` | `None` means the target is unknown, mobile, under construction, not a building or field power structure, or not part of a completed power grid. |

##### `.total()`

Returns a planet-wide `PowerSummary` across every independent grid. Conventional battery storage and Lightning reserve remain separate so automation can decide which supply it is relying on.

- **Returns** Planet-wide `PowerSummary` snapshot across every independent grid.

##### `.is_powered(machine_id)`

Returns `True` when the named machine is currently switched on. Unknown machine ids return `False`, so this is safe to call before deciding whether to send a breaker command.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `machine_id` | `string` | Machine instance id |

- **Returns** Boolean: `True` when the named machine is powered on.

##### `.can_power_off(machine_id)`

Returns `True` when the named machine exists and has a visible breaker toggle. Terraforming machines and many production machines can usually be switched; batteries, passive tanks, mobile units, and ship equipment usually cannot.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `machine_id` | `string` | Machine instance id |

- **Returns** Boolean: `True` when the named machine exposes a breaker/power toggle.

##### `.set_powered(machine_id, on)`

Send the same breaker command as clicking the machine card toggle. `power.set_powered("o2gen_1", False)` switches a machine off; `True` switches it back on. Switching off pauses scripts attached to that machine and preserves their setpoints; switching back on resumes only scripts that were paused by the power-off.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `machine_id` | `string` | Machine instance id |
| `on` | `boolean` | `True` powers on; `False` powers off |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_found"` | rejection | The requested object, target, or record does not exist. |
| `"not_toggleable"` | rejection | The target does not expose a script power toggle. |
| `"under_construction"` | transient | The target is still under construction. |
| `"not_connected"` | rejection | The component has no active connection. |
| `"not_enough_power"` | rejection | The available energy is below the operation's requirement. |

```python
power = get_component("power_control")
for grid in power.grids():
    print(grid.anchor_id, grid.generated, grid.consumed, grid.net)
    for member in grid.members:
        print("  ", member.id, member.roles, member.generated, member.consumed)
```

*Components / Infrastructure & Fluids*
