# Component: grow_lamp

> **Category:** Biosphere | **Component Name:** Grow Lamp

Lights the four orthogonally adjacent field cells (directly above, below, left, and right) while powered and enabled.

| Field | Value |
| --- | --- |
| Type | Biosphere |
| Power in | Variable (draws from grid) |
| Tiers | Mk II, Mk III, and Mk IV |

### How to obtain

1. The recipe unlocks with the **Grow Lamp** research (Plants 500,000).
2. Fabricate a **Grow Lamp Kit** on a **Fabricator**: 1× Machine Frame, 2× Circuit Panel, and 2× Glass.
3. Deploy the kit on an empty field cell with a Harvester's `deploy()`.

**Returned by:** `self / get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.set_enabled(enabled)` *(self only)*

Command the lamp on or off. Power loss pauses the script but preserves this setpoint; stopping the machine script resets it to `False`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `enabled` | `boolean` | Whether this script commands the lamp to light its cells. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.is_enabled()`

`True` when the running script has commanded this lamp on.

- **Returns** `boolean`

##### `.is_active()`

`True` when the lamp is commanded on and has power.

- **Returns** `boolean`

##### `.is_supplied()`

`True` when the lamp is commanded on, powered, and actively lighting its covered cells. If disabled or unpowered, covered cells lose `lit` and their plants pause.

- **Returns** Boolean: `True` when the lamp is placed, commanded on, powered, and actively lighting its covered cells. `False` when unplaced, disabled, or unpowered; covered cells then lose `lit` and their plants pause.

##### `.status()`

Exact operating state: `"not_placed"`, `"disabled"`, `"no_power"`, or `"active"`.

- **Returns** Exact operating state: `"not_placed"` after placement recovery, `"disabled"` when the script command is off, `"no_power"` when commanded on but unpowered, or `"active"` while lighting.
- **Possible values** `"not_placed"`, `"disabled"`, `"no_power"`, `"active"`

##### `.tier()`

Deployed tier (**1-4**). Mk I/II/III/IV provide **1×/2×/4×/8×** supported plant output and draw **5/25/100/500 W** while active.

- **Returns** Number (**1-4**), the deployed tier. Higher tiers boost the output of plants they cover and draw far more power; tier up by fabricating and applying a Grow Lamp upgrade pack.

##### `.position()`

Grid sector occupied by this lamp, such as `"E14"`.

- **Returns** String: the grid sector this lamp occupies (e.g. `"E14"`).

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Biosphere*
