# Component: run_control

> **Category:** Infrastructure & Fluids | **Component Name:** Run Control

Shared start/stop controller for machine scripts, the remote equivalent of a machine card's Run / Stop buttons. Use it to build a supervisor: one script that watches the base and shuts down another machine when it detects a fault, without parking that machine in a permanent `sleep` loop. This is the **run/stop axis**, separate from `power_control` (the breaker): `stop` ends a script and latches it off, while a power toggle only pauses and auto-resumes.

**Returned by:** `get_component("run_control")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.is_running(machine_id)`

Returns `True` when the named machine has a script actively scheduled, including while it sits mid-`sleep` or mid-action. A paused, stopped, completed, or errored script reads `False`, as does an unknown machine id. Call it before `start`/`stop` to avoid redundant commands.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `machine_id` | `string` | Machine instance id |

- **Returns** Boolean: `True` when the named machine has a script actively scheduled (running, including mid-`sleep`/mid-action). A paused, stopped, completed, or errored script reads `False`.

##### `.stop(machine_id)`

Stops the named machine's script the same way the card's Stop button does: `run.stop("o2gen_1")` ends the script, resets its setpoints to idle, and zeroes its live readouts. Structural state (recipes, in-flight progress, loaded materials) is preserved. The stop is **latched**, unlike a power-off, the script does not auto-resume; restart it with `start`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `machine_id` | `string` | Machine instance id |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_found"` | rejection | The requested object, target, or record does not exist. |
| `"no_script"` | rejection | No attached script could be started or stopped by this call. |

##### `.start(machine_id)`

Runs the named machine's script from the top, the same way the card's Run button does: `run.start("o2gen_1")`. A fresh run restarts from the first line; it does not resume mid-script. The machine must be powered and fully built.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `machine_id` | `string` | Machine instance id |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_found"` | rejection | The requested object, target, or record does not exist. |
| `"no_script"` | rejection | No attached script could be started or stopped by this call. |
| `"already_running"` | transient | The operation is already running. |
| `"not_powered"` | rejection | The component is not powered. |
| `"under_construction"` | transient | The target is still under construction. |

```python
run = get_component("run_control")

if run.is_running("o2gen_1"):
    run.stop("o2gen_1")    # latched off , won't auto-resume on power
else:
    run.start("o2gen_1")   # re-run the machine's script from the top
```

*Components / Infrastructure & Fluids*
