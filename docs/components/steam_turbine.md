# Component: steam_turbine

> **Category:** Power | **Component Name:** Steam Turbine

Produces up to 108 W from 90 t/h Steam. Its script-owned throttle scales both consumption and output.

| Field | Value |
| --- | --- |
| Type | Power |
| Power out | +108 W (feeds the grid) |
| Consumes | Steam, up to 90 t per hour, buffer 100 t |

### How to obtain

1. Requires the **Steam Turbine** research (Pressure 3).
2. Buy from the Shop for 7,500 cr.

**Returned by:** `self / get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

##### `.outpost: OutpostRef`

The outpost where this building is deployed. The returned `OutpostRef` includes its stable id, display name, biome, position, capacity, and `buildings()` query. Read the property again when you need current values.

- **Returns** `OutpostRef` for the outpost where this building is deployed.

##### `.steam_in: FluidPort`

Input flow port accepting steam from a Thermal Cap or Gas Tank. Call `self.steam_in.connect(...)` with the source's stable machine id or display name. A local source transfers directly; a remote source also needs a completed conflict-free Gas Pipe route between both locations. `self.steam_in.level()` shows the buffer, low = about to run dry; full = source is backpressured. See `FluidPort`.

- **Returns** `FluidPort`: `connect()`, `connected_to()`, `level()`, `capacity()`, `flow_rate()`.

### Methods

##### `.power_output() → float`

Watts fed to the grid on the last power tick. Scales with `throttle()` and the steam actually available. **0** when idle or steam-starved. Updates once per power tick, a fresh `set_throttle(...)` is reflected on the next tick, not the same one. Use for live dashboards or to compare against Oxygen / Heat consumption to balance the power budget.

- **Returns** Number (watts) currently fed to the grid.

##### `.efficiency() → float`

Fraction of the throttle's desired steam actually drawn on the last power tick (**0.0-1.0**). **1.0** = the turbine got all the steam its throttle asked for. Below **1** means steam-starved (vent dormant, or upstream can't keep up). Use to detect whether the turbine is being fed enough.

- **Returns** Number (**0-1**): fraction of the throttle's desired steam actually drawn (below **1** means steam-starved).

##### `.is_stalled() → bool`

`True` when the throttle is up but no steam is arriving (the vent is dormant or the steam line is disconnected). Check `self.steam_in.level()` (upstream) and the feeding Cap's vent phase to diagnose. There is no water side to back up anymore.

- **Returns** Boolean: `True` when the throttle is up but no steam is arriving (vent dormant or disconnected).

##### `.throttle() → float`

Current throttle setting (**0.0-1.0**). **0** = off, the turbine consumes no steam and produces nothing (the default; idle until `set_throttle()` is called). Higher values draw more steam and produce more power, up to the peak at **1.0**. Read-only view of what `set_throttle()` last committed.

- **Returns** Number (**0-1**): current throttle setting.

##### `.set_throttle(t: float) → ActionResult` *(self only)*

Set the turbine throttle (**0.0-1.0**, clamped). **0** switches the turbine off (no steam consumed, no power). **1.0** draws full steam for peak watts. `self.set_throttle(1.0)` runs it flat out; ease down when the steam buffer runs dry so it isn't spinning on empty, e.g. `if self.steam_in.level() < 5: self.set_throttle(0.3)`. This script-owned setpoint resets to **0** when the script stops, ends, or errors.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `t` | `float` | **0** = idle (no steam, no power), **1** = full steam draw / max power. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Power*
