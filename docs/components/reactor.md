# Component: reactor

> **Category:** Power | **Component Name:** Reactor

Generates up to **5,000 W** from Fuel Rods and cooling water. One rod lasts **72 hours** at heat **1.0**; fuel use follows commanded heat even while the core is warming or outside its efficient band.

| Field | Value |
| --- | --- |
| Type | Power |
| Power out | +5,000 W (feeds the grid) |
| Consumes | Water, buffer 3 t |
| Input buffer | 3 units |

### How to obtain

1. Requires the **Nuclear Program** research (Terraform Index 650,000).
2. Buy from the Shop for 750,000 cr.

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

##### `.water_in: FluidPort`

Automatic cooling-water input. The reactor consumes **0.5-1 t/h** while heating and pauses safely if the supply runs dry.

- **Returns** `FluidPort`: the automatic cooling-water input. Supports `connect()`, `level()`, `capacity()`, `flow_rate()`, and `connected_to()`.

##### `.input: InputSlot`

Normal Fuel Rod input. Rods arrive from a Lead Cask, and the reactor takes the next one automatically when needed.

- **Returns** `InputSlot`: ordinary Fuel Rod supply. Supports `connect()`, `take()`, `eject()`, `flush()`, `count()`, `capacity()`, and `connected_to()`. The reactor seats a rod automatically when needed. Fuel Rod recovery must target a compatible local Lead Cask.

### Methods

##### `.set_heat(value: float) → ActionResult` *(self only)*

Set reactor heat from **0-1**. Values outside the range are clamped. The setting returns to **0** when the owning script stops.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `float` | Heat setting in the **0-1** range. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.heat() → float`

Current heat setting from **0-1**.

- **Returns** Number **0-1**: the current heat setting.

##### `.temperature() → float`

Current temperature in °C. Output begins at **300**, peaks at **900**, then falls back to zero across the **900-950** red band. **950** triggers an automatic overheat shutdown.

- **Returns** Number: reactor temperature in °C this tick. Output starts at **300**, peaks at **900**, falls back to zero across the **900-950** red band, and **950** overheats.

##### `.fuel_level() → float`

Active Fuel Rod life from **0-1**. One full rod lasts **72 hours** at heat **1.0**; lower heat extends it proportionally. The next rod is taken automatically from `input`.

- **Returns** Number **0-1**: the active Fuel Rod's remaining life.

##### `.power_output() → float`

Watts on the grid this tick.

- **Returns** Number: watts produced this tick (**0-5,000**).

##### `.status() → str`

Current operating state: `running`, `overheated`, `no_fuel`, or `no_coolant`. Shutdowns recover automatically after cooling or supplies return.

- **Returns** `"running"` / `"overheated"` / `"no_fuel"` / `"no_coolant"`. Overheat cools and recovers automatically; restored supplies resume automatically.
- **Possible values** `"running"`, `"overheated"`, `"no_fuel"`, `"no_coolant"`

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Power*
