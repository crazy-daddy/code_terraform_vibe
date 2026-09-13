# Component: sprinkler

> **Category:** Biosphere | **Component Name:** Sprinkler

Waters the four orthogonally adjacent field cells (directly above, below, left, and right) while powered, supplied, and enabled.

| Field | Value |
| --- | --- |
| Type | Biosphere |
| Power in | Variable (draws from grid) |
| Consumes | Water, buffer 10 t |
| Tiers | Mk II, Mk III, and Mk IV |

### How to obtain

1. The recipe unlocks with the **Sprinkler** research (Plants 100,000).
2. Fabricate a **Sprinkler Kit** on a **Fabricator**: 1× Machine Frame, 2× Liquid Pipe Segment, 1× Pressure Valve, and 2 t Water.
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

##### `.water_in`

Supplies water from a connected source. Call `self.water_in.connect(...)` with the source's stable machine id or display name. A remote source also needs a completed conflict-free Liquid Pipe route between both locations. See `FluidPort` for level, capacity, flow, and connection queries.

- **Returns** `FluidPort` water buffer. Call `connect(...)` with the provider's stable machine id or display name; completed liquid-pipe networks carry water between outposts. Sharing an outpost with a pipe or tank does not connect it automatically.

### Methods

##### `.set_enabled(enabled)` *(self only)*

Command watering on or off. Power loss pauses the script but preserves this setpoint; stopping the machine script resets it to `False`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `enabled` | `boolean` | Whether this script commands watering. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.is_enabled()`

`True` when the running script has commanded watering on.

- **Returns** `boolean`

##### `.is_active()`

`True` when commanded on with power and water available.

- **Returns** `boolean`

##### `.is_supplied()`

`True` when the sprinkler is commanded on, powered, and has water in its `water_in` buffer. If disabled, unpowered, or dry, covered cells lose `watered`.

- **Returns** Boolean: `True` when the sprinkler is placed, commanded on, powered, and has water in its `water_in` buffer. `False` when unplaced, disabled, unpowered, or dry; covered cells then lose `watered` and their plants pause.

##### `.status()`

Exact operating state: `"not_placed"`, `"disabled"`, `"no_power"`, `"no_water"`, or `"active"`.

- **Returns** Exact operating state: `"not_placed"`, `"disabled"`, `"no_power"`, `"no_water"`, or `"active"`.
- **Possible values** `"not_placed"`, `"disabled"`, `"no_power"`, `"no_water"`, `"active"`

##### `.buffer()`

Fraction of the onboard water buffer currently filled (**0-1**). It drops while watering and refills from the connected `water_in` source.

- **Returns** Number (**0-1**): fraction of the onboard water buffer currently filled. Drops as the sprinkler waters; refilled by the connected `water_in` flow source. **0** means dry (covered cells lose `watered`).

##### `.tier()`

Deployed tier (**1-4**). Mk I/II/III/IV provide **1×/2×/4×/8×** supported plant output, draw **5/25/100/500 W**, and consume **2/10/200/1,000 t/h Water** while active.

- **Returns** Number (**1-4**), the deployed tier. Higher tiers boost the output of plants they cover and drink more water and power; tier up by fabricating and applying a Sprinkler upgrade pack.

##### `.position()`

Grid sector occupied by this sprinkler, such as `"E14"`.

- **Returns** String: the grid sector this sprinkler occupies (e.g. `"E14"`).

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Storage & Inventory*
