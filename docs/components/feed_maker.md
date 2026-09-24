# Component: feed_maker

> **Category:** Terraforming | **Component Name:** Feed Maker

Crafts the creature feeds that Habitat colonies eat, working like the Fabricator from a recipe you choose. Each creature's recipe unlocks through a Biolab order, so it only makes what you've unlocked. Mk II is upgraded per machine with a Fabricator-made pack unlocked at 250,000 Wildlife: 1.5× crafting and input Auto Feeder speed, with 2× operating power. Crafting can advance while the feeder cools down.

| Field | Value |
| --- | --- |
| Type | Biosphere |
| Power in | Variable (draws from grid) |
| Produces | Depends on the selected recipe |
| Output buffer | 50 units |
| Stockpile | 200 units (mixed) |
| Recipes | 16 available |
| Tiers | Mk II |

### How to obtain

1. Requires the **Wildlife** research (Plants 2,250,000).
2. Buy from the Shop for 50,000 cr.

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

Loads forage and life forms into the Feed Maker. Connect a source with `self.input.connect("Forage Bin")`, then pull materials with `self.input.take("forage", 8)`. See `InputSlot`.

- **Returns** `InputSlot`: load forage + life-forms: `self.input.connect("Forage Bin")` then `self.input.take("forage", 8)`. This is a multi-material stockpile; use `eject(...)` to recover a staged material while the machine is idle.

##### `.output: OutputSlot`

Sends finished feed to a bin or Habitat supply chain. Connect a destination with `self.output.connect("Feed Bin")`, then send feed with `self.output.send("feed_salt_tortoise", 10)`. See `OutputSlot`.

- **Returns** `OutputSlot`: push finished feed onward: `self.output.connect("Feed Bin")` then `self.output.send("feed_salt_tortoise", 10)`.

### Methods

##### `.tier() → int`

The machine's upgrade tier: 1 for Mk I or 2 for Mk II.

- **Returns** Number: 1 for Mk I or 2 for Mk II.

##### `.list_recipes() → list[Recipe]`

Lists the feed recipes unlocked through Bio Lab orders, one `Recipe` per creature whose feed you can craft. Locked recipes do not appear. Each recipe includes its tier, id, name, inputs, output, duration, and power draw. Use `for recipe in self.list_recipes(): print(recipe.tier, recipe.id)` to discover what is available.

- **Returns** List of unlocked `Recipe` objects (one per creature feed whose recipe a Biolab order has unlocked). Each has `.tier`, `.id`, `.name`, `.inputs`, `.output_item`, `.output_count`, `.duration_game_hours`, `.power_draw`.

##### `.find_recipe(recipe_id: str) → Recipe | None`

Find one unlocked feed recipe by id without looping through `list_recipes()`. Returns its `Recipe` object, or `None` when the id is unknown, locked, or belongs to another machine.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `recipe_id` | `str` | Feed Maker recipe id |

- **Returns** The matching unlocked `Recipe`, or `None` if this Feed Maker cannot currently run that id.

##### `.set_recipe(recipe_or_id: str | Recipe | IdRecord) → ActionResult` *(self only)*

Pick which creature feed to craft by id or by passing a Recipe from `list_recipes()`, e.g. `self.set_recipe("craft_feed_salt_tortoise")`. Once set, ProcessingSystem crafts automatically whenever the stockpile holds the inputs and the output bin has room.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `recipe_or_id` | `str \| Recipe \| IdRecord` | Feed recipe id, a `Recipe` object, or a dictionary or class instance with a string `id` field. The recipe must belong to this machine and be unlocked. |

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

Unset the selected feed recipe and leave the Feed Maker idle. The input stockpile stays loaded.

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

Returns the current recipe id, or `""` when none is set (or the set recipe is no longer unlocked). Use to check state before re-setting: `if self.get_recipe() == "": self.set_recipe(...)`.

- **Returns** String: the current recipe id, or `""` when none is set (or the set one is no longer unlocked).
- **Possible values** `""`, `"craft_feed_salt_tortoise"`, `"craft_feed_magmatic_annelid"`, `"craft_feed_mycelial_husk"`, `"craft_feed_mantle_strider"`, `"craft_feed_glasswing_mantis"`, `"craft_feed_veil_mantle"`, `"craft_feed_vault_crab"`, `"craft_feed_tidal_cephalopod"`, `"craft_feed_bone_walker"`, `"craft_feed_vent_drifter"`, `"craft_feed_hive_sentinel"`, `"craft_feed_hollow_choir"`, `"craft_feed_ferric_sea_lily"`, `"craft_feed_crustal_echo"`, `"craft_feed_glacial_wyrm"`, `"craft_feed_spire_drake"`

##### `.get_recipe_inputs() → dict[str, int]`

A dict mapping each input `item_id` → units consumed per craft for the current recipe (empty dict if no recipe set). Iterate it to know what to stock: `for item, qty in self.get_recipe_inputs().items(): self.input.take(item, qty * 5)`.

- **Returns** A dict (`item_id` → count consumed per craft), or an empty dict if no recipe is set. Iterate it to stock the right life-forms + forage.

##### `.get_stockpile() → dict[str, int]`

A dict mapping each `item_id` currently in the input stockpile → its unit count. Read it to see what's loaded before crafting.

- **Returns** A dict (`item_id` → units currently in the input stockpile).

##### `.get_stockpile_used() → int`

Total units across every material in the input stockpile. Compare to `get_stockpile_capacity()` to avoid overfilling.

- **Returns** Number: total units across every material in the input stockpile.

##### `.get_stockpile_capacity() → int`

Combined unit cap across all materials in the input stockpile. The cap is shared, many materials sum against one limit.

- **Returns** Number: combined unit cap across all materials in the input stockpile.

##### `.is_running() → bool`

`True` while a craft is actively advancing this tick (recipe set, inputs present, output has room). `False` when starved, output-full, idle, or powered off. Poll to detect a stalled line.

- **Returns** Boolean: `True` while a craft is actively advancing this tick.

##### `.get_progress() → float`

Fraction **0-1** through the current craft. Resets to 0 each time a craft completes (a batch of feed lands in the output bin) and starts again if inputs remain.

- **Returns** Number (**0-1**): progress through the current craft.

##### `.get_output_count() → int`

Completed feed units waiting in the output bin for pickup. Push them onward with `self.output.send(...)` before the bin fills (a full output bin stalls crafting).

- **Returns** Number: completed feed units waiting in the output bin for pickup.

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Terraforming*
