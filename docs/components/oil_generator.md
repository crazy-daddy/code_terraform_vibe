# Component: oil_generator

> **Category:** Power | **Component Name:** Oil Generator

Burns oil into strong buffered bridge power. Oil wells pulse between active and dormant phases, so bank their output in Liquid Tanks for continuous generation. Idle until a script runs it.

| Field | Value |
| --- | --- |
| Type | Power |
| Power out | +700 W (feeds the grid) |
| Consumes | Oil, buffer 10 t |

### How to obtain

1. Requires the **Oil Generator** research (Temperature 1,500).
2. Buy from the Shop for 2,000 cr.

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

##### `.oil_in: FluidPort`

Input flow port for oil. Wire with `self.oil_in.connect("Liquid Tank 1")` (recommended) or directly to an `Oil Pump`. See `FluidPort`.

- **Returns** `FluidPort`: `connect()`, `connected_to()`, `level()`, `capacity()`, `flow_rate()`.

### Methods

##### `.power_output() → float`

Watts fed to the grid on the last power tick. **0** when throttled to 0 OR oil_in buffer is starved. The generator scales output proportionally to available oil, so a partially-starved generator produces partial power. Updates once per power tick, a fresh `set_throttle(...)` is reflected on the next tick.

- **Returns** Number (watts) currently fed to the grid. **0** when idle (throttle=0) or starved (no oil in buffer).

##### `.oil_consumption() → float`

Actual oil consumed on the last power tick, in t/h. With enough oil supplied, demand scales linearly with throttle from **0 t/h** at 0 to **8 t/h** at 1. Partial or total oil starvation lowers the actual rate.

- **Returns** Number: oil consumed in t/h. **0** when idle.

##### `.throttle() → float`

Current throttle (**0-1**). **0** by default, generator idles until scripted.

- **Returns** Number (**0-1**).

##### `.set_throttle(rate: float) → ActionResult` *(self only)*

Set the generator throttle (**0-1**). Power output and oil consumption scale linearly with the throttle. This script-owned setpoint resets to **0** when the script stops, ends, or errors, so keep the control loop running while the Generator should operate.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `rate` | `float` | Throttle setting (**0-1**). |

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
