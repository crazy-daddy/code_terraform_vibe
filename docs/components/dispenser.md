# Component: dispenser

> **Category:** Biosphere | **Component Name:** Dispenser

Salts the four orthogonally adjacent field cells (directly above, below, left, and right) while powered, supplied, and enabled. Scripts find it with `outpost.harvesting_machines()`.

| Field | Value |
| --- | --- |
| Type | Biosphere |
| Power in | Variable (draws from grid) |
| Input buffer | Units: 50 |

### How to obtain

1. The recipe unlocks with the **Dispenser** research (Plants 300,000).
2. Fabricate **Dispenser Kit** on a **Fabricator**: 1× Machine Frame, 1× Control Unit, and 1× Circuit Panel.
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

##### `.input: InputSlot`

Loads salt from a storage bin or other source. Connect a source with `self.input.connect(name)`, then pull salt with `self.input.take("salt", count)`. See `InputSlot`.

- **Returns** `InputSlot`. Feed salt in from a storage bin: `self.input.connect("Salt Bin")` then `self.input.take("salt", 50)`. Salt is a Water Pump byproduct.

### Methods

##### `.set_enabled(enabled: bool) → ActionResult` *(self only)*

Command salting on or off. Power loss pauses the script but preserves this setpoint; stopping the machine script resets it to `False`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `enabled` | `bool` | Whether this script commands salting. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.is_enabled() → bool`

`True` when the running script has commanded salting on.

- **Returns** `bool`

##### `.is_active() → bool`

`True` when commanded on with power and salt available.

- **Returns** `bool`

##### `.is_supplied() → bool`

`True` when the dispenser is commanded on, powered, and has salt in its input buffer. If disabled, unpowered, or empty, covered cells lose `salted`.

- **Returns** `bool`. `True` when the dispenser is placed, commanded on, powered, and has salt in its input buffer. `False` when unplaced, disabled, unpowered, or empty; covered cells then lose `salted` and their plants pause.

##### `.status() → str`

Exact operating state: `"not_placed"`, `"disabled"`, `"no_power"`, `"no_salt"`, or `"active"`.

- **Returns** `str`
- **Possible values** `"not_placed"`, `"disabled"`, `"no_power"`, `"no_salt"`, `"active"`

##### `.buffer() → float`

Fraction of the onboard salt buffer currently filled (**0-1**). It drops while dosing cells and refills through `self.input`.

- **Returns** `float`. Fraction of the onboard salt buffer currently filled (**0-1**). Drops as the dispenser doses cells; refilled by feeding salt into `self.input`. **0** means empty (covered cells lose `salted`).

##### `.tier() → int`

Always **1**. The Dispenser ships at Mk I and has no upgrade pack; salt providers don't tier, so every deployed Dispenser reads **1**.

- **Returns** `int`. Always **1**. The Dispenser ships at Mk I and has no upgrade pack; salt providers don't tier.

##### `.position() → str`

Grid sector occupied by this dispenser, such as `"E14"`.

- **Returns** `str`. The grid sector this dispenser occupies (e.g. `"E14"`).

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

*Components / Biosphere*
