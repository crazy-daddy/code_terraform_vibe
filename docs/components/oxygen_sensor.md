# Component: oxygen_sensor

> **Category:** Sensors | **Component Name:** Oxygen Sensor

An atmospheric oxygen probe that landed broken. It reports a raw voltage until a script works out the calibration and repairs it, after which it reads oxygen directly.

| Field | Value |
| --- | --- |
| Type | Sensors |

**Access via:** `get_component("oxygen_sensor")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id: str`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** `str`

##### `.name: str`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** `str`

### Methods

##### `.get_value() → float`

Before repair, read raw voltage from the uncalibrated probe as a small decimal value. This is not yet a ppt reading; compare it with a known reference to calculate the calibration factor. After repair, read the current atmospheric oxygen level in ppt directly.

- **Returns** `float`. Raw voltage before repair; atmospheric oxygen in ppt after repair.

##### `.calibrate(value: float) → ActionResult`

Start the black-box calibration suite with the processed value: `result = self.calibrate(raw_value * factor)`. The suite then checks the whole script against several readings. A fully correct suite repairs the sensor; failed test cases remain visible in the console.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `float` | Calibration value to test |

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

##### `.set_status(message: str, level: str = "info") → None`

Show a status message for this machine's current script run. Use `self.set_status(message, "info")`. The same reporting capability is available as `set_status()` in every script. Messages follow the current execution, independently of machine state and game warnings.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `str` | Non-empty plain text, at most 240 characters. Null characters are not accepted. |
| `level` | `str` | Presentation severity: `info`, `warn`, or `error`. Defaults to `info`. |

- **Returns** `None`. `None`.

##### `.clear_status() → None`

Clear the current script run's status message. Clearing an absent message has no effect. Does not wait or change machine behaviour.

- **Returns** `None`. `None`.

##### `.get_status_report() → ScriptStatusReport | None`

Read this machine's script status report from any script. Returns `None` when it has no report. The returned snapshot includes `message`, `level`, `active`, and `run_id`.

- **Returns** `ScriptStatusReport | None`. Read this machine's script status report from any script. Returns `None` when it has no report. The returned snapshot includes `message`, `level`, `active`, and `run_id`.

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

```python
component = get_component("oxygen_sensor")
value = component.get_value()
print(value)
```

*Components / Sensors*
