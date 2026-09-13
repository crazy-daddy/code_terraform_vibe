# Component: oxygen_sensor

> **Category:** Sensors | **Component Name:** Oxygen Sensor

An atmospheric oxygen probe that landed broken. It reports a raw voltage until a script works out the calibration and repairs it, after which it reads oxygen directly.

| Field | Value |
| --- | --- |
| Type | Sensors |

**Returned by:** `get_component("oxygen_sensor")`

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

Before repair, read raw voltage from the uncalibrated probe as a small decimal value. This is not yet a ppt reading; compare it with a known reference to calculate the calibration factor. After repair, read the current atmospheric oxygen level in ppt directly.

- **Returns** Number (raw voltage before repair; atmospheric oxygen in ppt after repair)

##### `.calibrate(value)`

Start the black-box calibration suite with the processed value: `result = self.calibrate(raw_value * factor)`. The suite then checks the whole script against several readings. A fully correct suite repairs the sensor; failed test cases remain visible in the console.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `number` | Calibration value to test |

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
component = get_component("oxygen_sensor")
value = component.get_value()
print(value)
```

*Components / Sensors*
