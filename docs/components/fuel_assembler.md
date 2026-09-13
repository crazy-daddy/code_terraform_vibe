# Component: fuel_assembler

> **Category:** Production & Storage | **Component Name:** Fuel Assembler

Presses Raw Uranium and lead plates into Fuel Rods or Nuclear Batteries, working like the Fabricator. It draws heavy recipe power while running, so it is best run in bursts when your lightning banks are full.

| Field | Value |
| --- | --- |
| Type | Mining |
| Power in | Variable (draws from grid) |
| Produces | Depends on the selected recipe |
| Output buffer | 5 units |
| Stockpile | 40 units (mixed) |
| Recipes | 2 available |

### How to obtain

1. Requires the **Fuel Assembler** research (Temperature 10,000).
2. Buy from the Shop for 225,000 cr.

**Returned by:** `self / get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

##### `.outpost`

The outpost where this building is deployed. The returned `OutpostRef` includes its stable id, display name, biome, position, capacity, and `buildings()` query. Read the property again when you need current values.

- **Returns** `OutpostRef` for the outpost where this building is deployed.

##### `.input`

Receives Raw Uranium only from a Lead Cask and lead plates from an ordinary compatible local source. The port has one source relationship at a time, so reconnect it between materials.

- **Returns** `InputSlot`: stage Raw Uranium and lead plates. Raw Uranium may enter only from a Lead Cask; reconnect the one-source input to an ordinary local source for lead plates. While idle, recover ordinary items to local freight and hot cargo to a compatible Lead Cask with `eject(...)`.

##### `.output`

Output port. Fuel Rods are hot and only a Lead Cask (or their exact Supply Dock order) accepts them. Nuclear Batteries are ordinary fabricated products and may go to compatible local storage or home Inventory.

- **Returns** `OutputSlot`: route Fuel Rods to a separate Lead Cask (or their exact Supply Dock order). Nuclear Batteries are ordinary fabricated products and may route to ordinary compatible local storage or home Inventory.

### Methods

##### `.list_recipes()`

Unlocked recipes this machine can run, including each recipe's derived `.tier`. The Fuel Rod recipe arrives through Vestibule's queue; the Nuclear Battery recipe arrives through Helios's queue.

- **Returns** List of unlocked `Recipe` entries this machine can run, including each recipe's derived `.tier`.

##### `.find_recipe(recipe_id)`

Find one unlocked fuel recipe by id without looping through `list_recipes()`. Returns its `Recipe` object, or `None` when the id is unknown, locked, or belongs to another machine.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `recipe_id` | `string` | Fuel Assembler recipe id |

- **Returns** The matching unlocked `Recipe`, or `None` if this Fuel Assembler cannot currently run that id.

##### `.set_recipe(recipe_or_id)` *(self only)*

Select a Fuel Rod or Nuclear Battery recipe by id or by passing a Recipe from `list_recipes()`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `recipe_or_id` | `any` | Fuel recipe id, a `Recipe` object, or a dictionary or class instance with a string `id` field. The recipe must belong to this machine and be unlocked. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"unknown_recipe"` | rejection | The supplied recipe is unknown or does not apply to this machine. |
| `"recipe_locked"` | rejection | The selected recipe is locked. |
| `"offline"` | transient | The component is offline. |
| `"busy"` | transient | The component is already performing another operation. |
| `"material_mismatch"` | rejection | The existing material does not match the requested material. |

##### `.clear_recipe()` *(self only)*

Release the recipe once the current craft is idle and the output buffer is drained.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"busy"` | transient | The component is already performing another operation. |
| `"material_present"` | rejection | Existing material prevents the requested configuration change. |

##### `.get_recipe()`

The committed recipe id, empty when none.

- **Returns** Current recipe id, or empty string when none is set.
- **Possible values** `""`, `"craft_fuel_rod"`, `"craft_nuclear_battery"`

##### `.get_recipe_inputs()`

Input requirements for the committed recipe as a dict `{item_id: count_per_craft}`. Returns an empty dict when no recipe is committed.

- **Returns** Dict (`item_id` → count consumed per craft), or an empty dict if no recipe is set.

##### `.is_running()`

`True` while a craft is actually advancing, power, inputs, and output space all present.

- **Returns** Boolean: a craft is advancing this tick.

##### `.get_progress()`

Current craft progress **0-1**. Progress survives power cuts and resumes.

- **Returns** Number **0-1**: current craft progress.

##### `.get_stockpile()`

Staged inputs by item id, `{"raw_uranium": 12, "lead_plate": 4}`-shaped dict.

- **Returns** Dict: staged input materials by item id.

##### `.get_output_count()`

Finished products for the selected recipe waiting in the small output buffer.

- **Returns** Number: finished products for the selected recipe waiting in the output buffer.

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Production & Storage*
