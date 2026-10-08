# Component: reactor

> **Category:** Power | **Component Name:** Reactor

Generates up to **5,000 W** from Fuel Rods and cooling water. One rod lasts **72 hours** at heat **1.0**; fuel use follows commanded heat even while the core is warming or outside its efficient band.

| Field | Value |
| --- | --- |
| Type | Power |
| Power out | +5,000 W (feeds the grid) |
| Consumes | Water, buffer 3 t |
| Input buffer | Units: 3 |

### How to obtain

1. Requires the **Nuclear Program** research (Terraform Index 650,000).
2. Buy from the Shop for 750,000 cr.

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

##### `.water_in: FluidPort`

Automatic cooling-water input. The reactor consumes **0.5-1 t/h** while heating and pauses safely if the supply runs dry.

- **Returns** `FluidPort`. The automatic cooling-water input.

##### `.input: InputSlot`

Normal Fuel Rod input. Rods arrive from a Lead Cask, and the reactor takes the next one automatically when needed.

- **Returns** `InputSlot`. Ordinary Fuel Rod supply. The reactor seats a rod automatically when needed. Fuel Rod recovery must target a compatible local Lead Cask.

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

- **Returns** `float`. The current heat setting (**0-1**).

##### `.temperature() → float`

Current temperature in °C. Output begins at **300**, peaks at **900**, then falls back to zero across the **900-950** red band. **950** triggers an automatic overheat shutdown.

- **Returns** `float`. Reactor temperature this tick, in °C. Output starts at **300**, peaks at **900**, falls back to zero across the **900-950** red band, and **950** overheats.

##### `.fuel_level() → float`

Active Fuel Rod life from **0-1**. One full rod lasts **72 hours** at heat **1.0**; lower heat extends it proportionally. The next rod is taken automatically from `input`.

- **Returns** `float`. The active Fuel Rod's remaining life (**0-1**).

##### `.power_output() → float`

Watts on the grid this tick.

- **Returns** `float`. Watts produced this tick (**0-5,000**).

##### `.status() → str`

Current operating state: `running`, `overheated`, `no_fuel`, or `no_coolant`. Shutdowns recover automatically after cooling or supplies return.

- **Returns** `str`. Overheat cools and recovers automatically; restored supplies resume automatically.
- **Possible values** `"running"`, `"overheated"`, `"no_fuel"`, `"no_coolant"`

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

*Components / Power*
