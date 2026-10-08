# Component: sprinkler

> **Category:** Biosphere | **Component Name:** Sprinkler

Waters the four orthogonally adjacent field cells (directly above, below, left, and right) while powered, supplied, and enabled. Scripts find it with `outpost.harvesting_machines()`.

| Field | Value |
| --- | --- |
| Type | Biosphere |
| Power in | Variable (draws from grid) |
| Consumes | Water, buffer 10 t |
| Tiers | Mk II, Mk III, and Mk IV |

### How to obtain

1. The recipe unlocks with the **Sprinkler** research (Plants 100,000).
2. Fabricate **Sprinkler Kit** on a **Fabricator**: 1× Machine Frame, 2× Liquid Pipe Segment, 1× Pressure Valve, and 2 t Water.
3. Deploy the kit on an empty field cell with a Harvester's `deploy()`.

**Access via:** `self / get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id: str`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** `str`

##### `.name: str`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** `str`

##### `.water_in: FluidPort`

Supplies water from a connected source. Call `self.water_in.connect(...)` with the source's stable machine id or display name. A remote source also needs a completed conflict-free Liquid Pipe route between both locations. See `FluidPort` for level, capacity, flow, and connection queries.

- **Returns** `FluidPort`. Water buffer. Call `connect(...)` with the provider's stable machine id or display name; completed liquid-pipe networks carry water between outposts. Sharing an outpost with a pipe or tank does not connect it automatically.

### Methods

##### `.set_enabled(enabled: bool) → ActionResult` *(self only)*

Command watering on or off. Power loss pauses the script but preserves this setpoint; stopping the machine script resets it to `False`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `enabled` | `bool` | Whether this script commands watering. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.is_enabled() → bool`

`True` when the running script has commanded watering on.

- **Returns** `bool`

##### `.is_active() → bool`

`True` when commanded on with power and water available.

- **Returns** `bool`

##### `.is_supplied() → bool`

`True` when the sprinkler is commanded on, powered, and has water in its `water_in` buffer. If disabled, unpowered, or dry, covered cells lose `watered`.

- **Returns** `bool`. `True` when the sprinkler is placed, commanded on, powered, and has water in its `water_in` buffer. `False` when unplaced, disabled, unpowered, or dry; covered cells then lose `watered` and their plants pause.

##### `.status() → str`

Exact operating state: `"not_placed"`, `"disabled"`, `"no_power"`, `"no_water"`, or `"active"`.

- **Returns** `str`
- **Possible values** `"not_placed"`, `"disabled"`, `"no_power"`, `"no_water"`, `"active"`

##### `.buffer() → float`

Fraction of the onboard water buffer currently filled (**0-1**). It drops while watering and refills from the connected `water_in` source.

- **Returns** `float`. Fraction of the onboard water buffer currently filled (**0-1**). Drops as the sprinkler waters; refilled by the connected `water_in` flow source. **0** means dry (covered cells lose `watered`).

##### `.tier() → int`

Deployed tier (**1-4**). Mk I/II/III/IV provide **1×/2×/4×/8×** supported plant output, draw **5/25/100/500 W**, and consume **2/4/8/16 t/h Water** while active.

- **Returns** `int`. The deployed tier (**1-4**). Higher tiers boost the output of plants they cover and drink more water and power; tier up by fabricating and applying a Sprinkler upgrade pack.

##### `.position() → str`

Grid sector occupied by this sprinkler, such as `"E14"`.

- **Returns** `str`. The grid sector this sprinkler occupies (e.g. `"E14"`).

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

*Components / Storage & Inventory*
