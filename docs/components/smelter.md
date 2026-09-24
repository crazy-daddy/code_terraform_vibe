# Component: smelter

> **Category:** Production & Storage | **Component Name:** Smelter

Refines raw ore into metal stock, one unit at a time, following a recipe you choose. A script sets the recipe, feeds ore in from a bin, and drains the finished metal out to another.

| Field | Value |
| --- | --- |
| Type | Mining |
| Power in | Variable (draws from grid) |
| Produces | Depends on the selected recipe |
| Input buffer | 50 units |
| Output buffer | 50 units |
| Recipes | 7 available |

### How to obtain

1. Requires the **Ore Refinement** research (Oxygen 5).
2. Buy from the Shop for 650 cr.

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

##### `.input: InputSlot`

Loads ore into the Smelter. At home it can use Inventory; remote Smelters must connect a local Storage Bin or Warehouse. Pull material with `self.input.take(item_id, count)`. Failed transfers leave the source cargo unchanged. Requires **Auto Feeders** research. See `InputSlot`.

- **Returns** InputSlot: `connect()`, `take()`, `eject()`, `flush()`, `count()`, `capacity()`, `connected_to()`

##### `.output: OutputSlot`

Sends refined material out of the Smelter. At home it can use Inventory; remote Smelters must connect a local Storage Bin or Warehouse. Send material with `self.output.send(item_id, count)`. Failed transfers leave the output unchanged. Requires **Auto Feeders** research. See `OutputSlot`.

- **Returns** OutputSlot: `connect()`, `send()`, `count()`, `capacity()`, `connected_to()`

### Methods

##### `.list_recipes() → list[Recipe]`

Every recipe this smelter has been given a blueprint for. Returns Recipe objects with `.tier`, `.id`, `.name`, `.inputs`, `.output_item`, `.output_count`, `.duration_game_hours`, and `.power_draw`. Locked recipes (no blueprint yet) do not appear, the list reflects what the player can actually run today. Day-1 starts with `"smelt_iron_ingot"` only; more arrive as blueprints unlock.

- **Returns** List of unlocked Recipe objects. Each has `.tier`, `.id`, `.name`, `.inputs`, `.output_item`, `.output_count`, `.duration_game_hours`, and `.power_draw`.

##### `.find_recipe(recipe_id: str) → Recipe | None`

Find one unlocked recipe by id without looping through `list_recipes()`. Returns its `Recipe` object, or `None` when the id is unknown, locked, or belongs to another machine.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `recipe_id` | `str` | Smelter recipe id |

- **Returns** The matching unlocked `Recipe`, or `None` if this Smelter cannot currently run that id.

##### `.set_recipe(recipe_or_id: str | Recipe | IdRecord) → ActionResult` *(self only)*

Select which recipe the smelter should run. Call `self.set_recipe("smelt_iron_ingot")` or pass a Recipe from `list_recipes()`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `recipe_or_id` | `str \| Recipe \| IdRecord` | Recipe id, a `Recipe` object, or a dictionary or class instance with a string `id` field. The recipe must belong to this machine and be unlocked. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"unknown_recipe"` | rejection | The supplied recipe is unknown or does not apply to this machine. |
| `"offline"` | transient | The component is offline. |
| `"recipe_locked"` | rejection | The selected recipe is locked. |
| `"busy"` | transient | The component is already performing another operation. |
| `"material_mismatch"` | rejection | The existing material does not match the requested material. |

##### `.clear_recipe() → ActionResult` *(self only)*

Unset the current recipe and leave the smelter idle. Empty latched buffers clear back to no material.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"busy"` | transient | The component is already performing another operation. |
| `"material_present"` | rejection | Existing material prevents the requested configuration change. |

##### `.get_recipe() → str`

Current recipe id as a string, or the empty string if no recipe is set. Use after `set_recipe()` to confirm, or to gate other logic (`if self.get_recipe() == "": ...`).

- **Returns** String (recipe id, or empty string if none set)
- **Possible values** `""`, `"smelt_iron_ingot"`, `"smelt_glass"`, `"smelt_titanium_ingot"`, `"smelt_cobalt_ingot"`, `"smelt_rare_earth_core"`, `"smelt_neutronium_bar"`, `"smelt_lead_ingot"`

##### `.get_recipe_inputs() → dict[str, int]`

Input requirements for the current recipe as a dict `{item_id: count_per_craft}`. Returns an empty dict if no recipe is set.

- **Returns** A dict (item_id → count per craft), or empty dict if no recipe is set

##### `.is_running() → bool`

`True` while the smelter is actively processing a unit. Use before `set_recipe()` to avoid the `"busy"` rejection: `if not self.is_running(): self.set_recipe(new_id)`. Stays `True` across ticks until the unit completes.

- **Returns** Boolean

##### `.get_progress() → float`

Progress toward the next completed unit (**0-1**). Resets to **0** when a unit completes and a new one starts. Useful for progress bars and scripts that want to detect completions by watching the value drop.

- **Returns** Number (**0-1**)

##### `.get_input_count() → int`

Units currently in the input buffer, waiting to be smelted. Check before `self.input.take(...)` to avoid overfilling, or to decide whether to pull more.

- **Returns** Number (units in input buffer)

##### `.get_output_count() → int`

Units currently in the output buffer, waiting to be drained. Check before `self.output.send(...)`, if high, unload downstream first; if low, let processing catch up.

- **Returns** Number (units in output buffer)

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Production & Storage*
