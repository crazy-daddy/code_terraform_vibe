# Component: smelter

> **Category:** Production & Storage | **Component Name:** Smelter

Refines raw ore into metal stock, one unit at a time, following a recipe you choose. A script sets the recipe, feeds ore in from a bin, and drains the finished metal out to another.

| Field | Value |
| --- | --- |
| Type | Mining |
| Power in | Variable (draws from grid) |
| Produces | Depends on the selected recipe |
| Input buffer | Units: 50 |
| Output buffer | Units: 50 |
| Recipes | 7 available |
| Tiers | Mk II and Mk III |

### How to obtain

1. Requires the **Ore Refinement** research (Oxygen 5).
2. Buy from the Shop for 650 cr.

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

##### `.input: InputSlot`

Loads ore into the Smelter. At home it can use Inventory; remote Smelters must connect a local Storage Bin or Warehouse. Pull material with `self.input.take(item_id, count)`. Failed transfers leave the source cargo unchanged. Requires **Auto Feeders** research. See `InputSlot`.

- **Returns** `InputSlot`

##### `.output: OutputSlot`

Sends refined material out of the Smelter. At home it can use Inventory; remote Smelters must connect a local Storage Bin or Warehouse. Send material with `self.output.send(item_id, count)`. Failed transfers leave the output unchanged. Requires **Auto Feeders** research. See `OutputSlot`.

- **Returns** `OutputSlot`

### Methods

##### `.tier() → int`

Installed machinery tier: `1` for Mk I, `2` for Mk II, or `3` for Mk III where supported.

- **Returns** `int`

##### `.list_recipes() → list[Recipe]`

Every recipe this smelter has been given a blueprint for. Returns `Recipe` objects with `.tier`, `.id`, `.name`, `.inputs`, `.output_item`, `.output_count`, `.duration_game_hours`, and `.power_draw`. Locked recipes (no blueprint yet) do not appear, the list reflects what the player can actually run today. Day-1 starts with `"smelt_iron_ingot"` only; more arrive as blueprints unlock.

- **Returns** `list[Recipe]`. The recipes this Smelter has unlocked.

##### `.find_recipe(recipe_id: str) → Recipe | None`

Find one unlocked recipe by id without looping through `list_recipes()`. Returns its `Recipe` object, or `None` when the id is unknown, locked, or belongs to another machine.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `recipe_id` | `str` | Smelter recipe id |

- **Returns** `Recipe | None`. `None` if this Smelter cannot currently run that id.

##### `.set_recipe(recipe_or_id: str | Recipe | IdRecord) → ActionResult` *(self only)*

Select which recipe the smelter should run. Call `self.set_recipe("smelt_iron_ingot")` or pass a `Recipe` from `list_recipes()`.

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

- **Returns** `str`. Empty when no recipe is set.
- **Possible values** `""`, `"smelt_iron_ingot"`, `"smelt_glass"`, `"smelt_titanium_ingot"`, `"smelt_cobalt_ingot"`, `"smelt_rare_earth_core"`, `"smelt_neutronium_bar"`, `"smelt_lead_ingot"`

##### `.get_recipe_inputs() → dict[str, int]`

Input requirements for the current recipe as a `dict` `{item_id: count_per_craft}`. Returns an empty `dict` if no recipe is set.

- **Returns** `dict[str, int]`. `{item_id: count}` consumed per craft, or empty if no recipe is set.

##### `.is_running() → bool`

Whether the smelter is actively processing. Can be `False` while an unfinished unit is paused, for example when its output is full. Paused progress is retained; use `get_progress()` to check for unfinished work before changing recipes.

- **Returns** `bool`

##### `.get_progress() → float`

Progress toward the next completed unit (**0-1**). Resets to **0** when a unit completes and a new one starts. Useful for progress bars and scripts that want to detect completions by watching the value drop.

- **Returns** `float`. Progress through the current craft (**0-1**).

##### `.get_input_count() → int`

Units currently in the input buffer, waiting to be smelted. Check before `self.input.take(...)` to avoid overfilling, or to decide whether to pull more.

- **Returns** `int`. Units in the input buffer.

##### `.get_output_count() → int`

Units currently in the output buffer, waiting to be drained. Check before `self.output.send(...)`, if high, unload downstream first; if low, let processing catch up.

- **Returns** `int`. Units in the output buffer.

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

*Components / Production & Storage*
