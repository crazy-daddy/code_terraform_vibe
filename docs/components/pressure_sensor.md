# Component: pressure_sensor

> **Category:** Sensors | **Component Name:** Pressure Sensor

An atmospheric pressure probe that landed broken. Its readings come out scrambled until a script stabilizes the repair signal, after which it reads pressure directly.

| Field | Value |
| --- | --- |
| Type | Sensors |

**Returned by:** `get_component("pressure_sensor")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.get_value()`

Current unstable repair reading as an integer. If the value is odd, add **1**; if it is even, use it unchanged. After repair, this method returns real atmospheric pressure in kPa.

- **Returns** Number (unstable repair reading; kPa after repair)

##### `.stabilize(value)`

Start the black-box stabilization suite with the corrected even reading: `result = self.stabilize(corrected_value)`. The suite then checks the whole script against several readings. A fully correct suite repairs the sensor; failed test cases remain visible in the console.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `number` | Stabilization value to test |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"started"` | success | The operation started. |
| `"already_repaired"` | success | The target is already repaired. |
| `"no_source"` | rejection | No source is configured or available. |
| `"already_testing"` | transient | The requested test is already running. |

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

```python
component = get_component("pressure_sensor")
value = component.get_value()
print(value)
```

*Components / Sensors*
