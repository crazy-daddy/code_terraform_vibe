# Component: run_control

> **Category:** Infrastructure & Fluids | **Component Name:** Run Control

Inspect machine scripts, discover and apply saved variants, and control execution remotely. Shared start/stop controller for machine scripts, the remote equivalent of a machine card's Run / Stop buttons. Use it to build a supervisor: one script that watches the base and shuts down another machine when it detects a fault, without parking that machine in a permanent `sleep` loop. This is the **run/stop axis**, separate from `power_control` (the breaker): `stop` ends a script and latches it off, while a power toggle only pauses and auto-resumes.

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

##### `.variants(machine_id: str, slot: int = 0) → list[ScriptVariantRef]`

Lists the saved variants available to one machine script, including its private Main and compatible shared variants. The optional slot is a zero-based script slot and defaults to 0. Results are snapshots; applying an id loads the latest saved code under that id.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `machine_id` | `str` | Machine instance id |
| `slot` | `int` | Zero-based script slot. Defaults to 0. Must be a nonnegative whole number. |

- **Returns** `list[ScriptVariantRef]`

*Raises*

| Exception | Condition |
| --- | --- |
| `ReferenceError` | The machine or an executable script in the requested slot does not exist. |
| `TypeError` | slot must be a whole number. |
| `ValueError` | slot must be zero or greater. |
| `OverflowError` | slot is outside the supported integer range. |

##### `.status(machine_id: str, slot: int = 0) → RunControlStatus`

Inspect a machine script's execution state and assigned variant. The optional slot is a zero-based script slot and defaults to 0. Results are snapshots; call again for current information.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `machine_id` | `str` | Machine instance id |
| `slot` | `int` | Zero-based script slot. Defaults to 0. Must be a nonnegative whole number. |

- **Returns** `RunControlStatus`

*Raises*

| Exception | Condition |
| --- | --- |
| `ReferenceError` | The machine or an executable script in the requested slot does not exist. |
| `TypeError` | slot must be a whole number. |
| `ValueError` | slot must be zero or greater. |
| `OverflowError` | slot is outside the supported integer range. |

##### `.apply_variant(machine_id: str, variant_id: str, slot: int = 0) → ActionResult`

Apply a saved variant to one machine script without starting it. The target must be fully built and its script must be stopped, completed, or errored. Running and paused scripts must be stopped first. Pending editor changes and unresolved conflicts block replacement. Main is preserved when switching away from it. Shared variants copy their current code into the target; later edits elsewhere do not automatically update it. The optional slot defaults to 0.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `machine_id` | `str` | Machine instance id |
| `variant_id` | `str` | Exact id returned by run.variants() for a compatible target. |
| `slot` | `int` | Zero-based script slot. Defaults to 0. Must be a nonnegative whole number. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The variant was applied. The script remains stopped. |
| `"not_found"` | rejection | The target machine does not exist. |
| `"no_script"` | rejection | The target slot has no executable machine script. |
| `"under_construction"` | rejection | The target machine is still under construction. |
| `"script_running"` | rejection | The target script is running. |
| `"script_paused"` | rejection | The target script is paused. |
| `"editor_busy"` | transient | An editor has pending changes or a conflicting source version is unresolved. |
| `"variant_not_found"` | rejection | The variant is no longer available under that id. |
| `"incompatible_variant"` | rejection | The variant belongs to a different script or an incompatible machine catalog. |
| `"source_too_large"` | rejection | The variant source exceeds the supported script size. |

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | slot must be a whole number. |
| `ValueError` | slot must be zero or greater. |
| `OverflowError` | slot is outside the supported integer range. |

##### `.is_running(machine_id: str) → bool`

Returns `True` when the named machine has a script actively scheduled, including while it sits mid-`sleep` or mid-action. A paused, stopped, completed, or errored script reads `False`, as does an unknown machine id. Call it before `start`/`stop` to avoid redundant commands.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `machine_id` | `str` | Machine instance id |

- **Returns** Boolean: `True` when the named machine has a script actively scheduled (running, including mid-`sleep`/mid-action). A paused, stopped, completed, or errored script reads `False`.

##### `.stop(machine_id: str) → ActionResult`

Stops the named machine's script the same way the card's Stop button does: `run.stop("o2gen_1")` ends the script, resets its setpoints to idle, and zeroes its live readouts. Structural state (recipes, in-flight progress, loaded materials) is preserved. The stop is **latched**, unlike a power-off, the script does not auto-resume; restart it with `start`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `machine_id` | `str` | Machine instance id |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_found"` | rejection | The requested object, target, or record does not exist. |
| `"no_script"` | rejection | No attached script could be started or stopped by this call. |

##### `.start(machine_id: str) → ActionResult`

Runs the named machine's script from the top, the same way the card's Run button does: `run.start("o2gen_1")`. A fresh run restarts from the first line; it does not resume mid-script. The machine must be powered and fully built.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `machine_id` | `str` | Machine instance id |

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

# Select saved code, then explicitly start it.
for variant in run.variants("o2gen_1"):
    if variant.name == "Production":
        run.stop("o2gen_1")
        result = run.apply_variant("o2gen_1", variant.id)
        if result.status == "ok":
            run.start("o2gen_1")
        break
```

*Components / Infrastructure & Fluids*
