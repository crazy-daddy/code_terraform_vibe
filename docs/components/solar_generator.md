# Component: solar_generator

> **Category:** Power | **Component Name:** Solar Generator

Turns sunlight into up to **50 W** for the grid when a script tracks the Sun. Poor tilt reduces daytime output, and night produces **0 W**.

| Field | Value |
| --- | --- |
| Type | Power |
| Power out | +50 W (feeds the grid) |

### How to obtain

1. Buy from the Shop for 500 cr.

**Returned by:** `self / get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

##### `.outpost`

The outpost where this building is deployed. The returned `OutpostRef` includes its stable id, display name, biome, position, capacity, and `buildings()` query. Read the property again when you need current values.

- **Returns** `OutpostRef` for the outpost where this building is deployed.

### Methods

##### `.set_tilt(degrees)` *(self only)*

Set the panel tilt angle in degrees. Range is **0°** (flat) to **90°** (vertical); values outside are clamped. A well-tuned tracker holds output near its maximum throughout the day; a fixed tilt wastes a large fraction.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `degrees` | `number` | Panel tilt in degrees |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.tilt()`

Current panel tilt setpoint in degrees (**0-90**). Returns the value the script last wrote via `self.set_tilt(...)`, or the default rest angle for an idle panel. Use to verify your sweep loop or to step a tilt search against the previous value.

- **Returns** Number (degrees, 0-90): the current panel tilt setpoint.

##### `.get_output()`

Current power output in watts for this specific generator. Returns **0** if powered off. Computed live from sun elevation vs panel tilt, use it to verify the tracker is holding peak (compare current output against the panel's rated max).

- **Returns** Number (watts)

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Power*
