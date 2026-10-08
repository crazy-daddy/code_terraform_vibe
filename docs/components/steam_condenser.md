# Component: steam_condenser

> **Category:** Infrastructure & Fluids | **Component Name:** Steam Condenser

Converts incoming steam into clean water at a 1:1 mass ratio. Scripted throttle controls its 250 t/h peak and 150 W draw.

| Field | Value |
| --- | --- |
| Type | Fluids |
| Power in | Variable (draws from grid) |
| Consumes | Steam, up to 250 t per hour, buffer 250 t |
| Produces | Water, up to 250 t per hour, buffer 250 t |

### How to obtain

1. Requires the **Steam Condensation** research (Plants 1,000,000).
2. Buy from the Shop for 50,000 cr.

**Access via:** `self / get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id: str`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** `str`

##### `.name: str`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** `str`

##### `.outpost: OutpostRef`

The outpost where this building is deployed. The returned `OutpostRef` includes its stable id, display name, biome, position, capacity, and `buildings()` query. Read the property again when you need current values.

- **Returns** `OutpostRef`. The outpost where this building is deployed.

##### `.steam_in: FluidPort`

Steam input port. Connect a Thermal Cap or a steam-latched Gas Tank. Its 250 t internal buffer is consumed by condensation after the grid powers the machine.

- **Returns** `FluidPort`. Accepts steam from a Thermal Cap or Gas Tank.

##### `.water_out: FluidPort`

Clean-water output port. Connect a Liquid Tank, Large Liquid Tank, Plant Terraformer, Sprinkler, or other water consumer. Its 250 t internal buffer backpressures condensation when full.

- **Returns** `FluidPort`. Supplies the condensed clean water.

### Methods

##### `.condensation_rate() → float`

Clean water produced on the last simulation tick in t/h. Full throttle reaches **250 t/h** when the steam input has supply, the water output has room, and the host outpost is not overcrowded.

- **Returns** `float`. Clean water produced on the last tick, in t/h.

##### `.efficiency() → float`

Fraction of the throttle's requested condensation completed on the last tick (**0.0-1.0**). Low values mean the steam input ran short or the water output filled before the tick completed.

- **Returns** `float`. Fraction of requested condensation completed (**0-1**).

##### `.is_stalled() → bool`

`True` when throttle is above zero and the current fluid state blocks condensation because `steam_in` is empty or `water_out` is full. This is derived immediately from both ports; use `status()` to distinguish the blockers.

- **Returns** `bool`. `True` when the condenser is fully built, powered, and has an open throttle, but steam is empty or the water buffer is full. `False` when the throttle is closed, power is unavailable, or construction is unfinished.

##### `.status() → str`

Current actionable state: `"idle"`, `"no_power"`, `"no_steam"`, `"output_full"`, or `"running"`. This is derived live from throttle, power, and both fluid buffers. Once throttle is **0**, it reports `"idle"`; inspect port levels to decide when to reopen it.

- **Returns** `str`
- **Possible values** `"idle"`, `"no_power"`, `"no_steam"`, `"output_full"`, `"running"`

##### `.throttle() → float`

Current condensation setpoint (**0.0-1.0**). It scales steam use, water output, and power draw linearly.

- **Returns** `float`. Current condensation setpoint (**0-1**).

##### `.set_throttle(t: float) → ActionResult` *(self only)*

Set condensation from **0.0-1.0** (clamped). **0** idles with no conversion or variable draw. **1.0** requests **250 t/h** and **150 W**. Draw follows the throttle even when steam is empty or the output is full, so set **0** to save power while blocked. This script-owned setpoint resets to **0** when the script stops, ends, or errors. Call from this Condenser's own script.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `t` | `float` | Condensation rate fraction in the **0-1** range. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.set_status(message: str, level: str = "info") → None` *(self only)*

Show a status message for this machine's current script run. Use `self.set_status(message, "info")`. The same reporting capability is available as `set_status()` in every script. Messages follow the current execution, independently of machine state and game warnings.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `str` | Non-empty plain text, at most 240 characters. Null characters are not accepted. |
| `level` | `str` | Presentation severity: `info`, `warn`, or `error`. Defaults to `info`. |

- **Returns** `None`. `None`.

##### `.clear_status() → None` *(self only)*

Clear the current script run's status message. Clearing an absent message has no effect. Does not wait or change machine behaviour.

- **Returns** `None`. `None`.

##### `.get_status_report() → ScriptStatusReport | None`

Read this machine's script status report from any script. Returns `None` when it has no report. The returned snapshot includes `message`, `level`, `active`, and `run_id`.

- **Returns** `ScriptStatusReport | None`. Read this machine's script status report from any script. Returns `None` when it has no report. The returned snapshot includes `message`, `level`, `active`, and `run_id`.

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Infrastructure & Fluids*
