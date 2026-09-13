# Component: refiner

> **Category:** Terraforming | **Component Name:** Refiner

Refines raw exotic feedstock into creature-grade gas or liquid, using tar as a reagent. Only uncommon and rare exotics need refining; commons are used directly. Recipes unlock through Biolab orders.

| Field | Value |
| --- | --- |
| Type | Biosphere |
| Power in | Variable (draws from grid) |
| Produces | Depends on the selected recipe |
| Input buffer | 50 units |
| Recipes | 4 available |

### How to obtain

1. Requires the **Exotic Husbandry** research (Wildlife 1,000).
2. Buy from the Shop for 80,000 cr.

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

##### `.gas_in`

Receives raw exotic gas. Connect a tank holding the raw gas with `self.gas_in.connect("Raw Chlorine Tank")`. See `FluidPort` for level, capacity, and flow queries.

- **Returns** `FluidPort`: raw exotic GAS feedstock in. Wire from a Gas Tank: `self.gas_in.connect("Raw Chlorine Tank")`. `level()`, `capacity()`, `flow_rate()`, `connected_to()`.

##### `.liquid_in`

Receives raw exotic liquid. Connect a tank holding the raw liquid with `self.liquid_in.connect("Raw Cryofluid Tank")`. See `FluidPort` for level, capacity, and flow queries.

- **Returns** `FluidPort`: raw exotic LIQUID feedstock in. Wire from a Liquid Tank: `self.liquid_in.connect("Raw Cryofluid Tank")`. `level()`, `capacity()`, `flow_rate()`, `connected_to()`.

##### `.gas_out`

Sends refined gas such as Sulfur Gas or Chlorine onward. Connect a destination tank with `self.gas_out.connect("Chlorine Tank")`. See `FluidPort` for level, capacity, and flow queries.

- **Returns** `FluidPort`: refined exotic GAS out (Sulfur Gas / Chlorine). Wire to a Gas Tank: `self.gas_out.connect("Chlorine Tank")`. `level()`, `capacity()`, `flow_rate()`, `connected_to()`.

##### `.liquid_out`

Sends refined liquid such as Cryofluid or Quicksilver onward. Connect a destination tank with `self.liquid_out.connect("Cryofluid Tank")`. See `FluidPort` for level, capacity, and flow queries.

- **Returns** `FluidPort`: refined exotic LIQUID out (Cryofluid / Quicksilver). Wire to a Liquid Tank: `self.liquid_out.connect("Cryofluid Tank")`. `level()`, `capacity()`, `flow_rate()`, `connected_to()`.

##### `.input`

Loads the tar consumed during refining. Connect a source with `self.input.connect("Tar Bin")`, then pull tar with `self.input.take("tar", 20)`. This slot holds only tar. See `InputSlot`.

- **Returns** `InputSlot`: load the tar reagent: `self.input.connect("Tar Bin")` then `self.input.take("tar", 20)`. This is a single-material bin; use `eject(...)` to recover staged tar while the machine is idle.

### Methods

##### `.list_recipes()`

Lists the refining recipes unlocked through Bio Lab orders, one `Recipe` per exotic fluid. Locked recipes do not appear. Each recipe includes `.tier`, names its exact raw feedstock in `.input_fluid`, gives port tons consumed per run in `.fluid_inputs`, lists tar in `.inputs`, and identifies the refined product and output port through `.output_fluid` / `.fluid_outputs`. Use `for recipe in self.list_recipes(): print(recipe.tier, recipe.id, recipe.input_fluid, recipe.output_fluid)` to discover what is available.

- **Returns** List of unlocked `Recipe` objects (one per refinable exotic whose recipe a Biolab order has unlocked). Each includes `.tier`, identifies raw feedstock through `.input_fluid` / `.fluid_inputs`, then the refined product and port through `.output_fluid` / `.fluid_outputs`.

##### `.find_recipe(recipe_id)`

Find one unlocked refining recipe by id without looping through `list_recipes()`. Returns its `Recipe` object, or `None` when the id is unknown, locked, or belongs to another machine.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `recipe_id` | `string` | Refiner recipe id |

- **Returns** The matching unlocked `Recipe`, or `None` if this Refiner cannot currently run that id.

##### `.set_recipe(recipe_or_id)` *(self only)*

Pick which exotic to refine by id or by passing a Recipe from `list_recipes()`, e.g. `self.set_recipe("refine_chlorine")`. Once set, the refiner crafts automatically whenever the raw feedstock + tar are present and the out port has room.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `recipe_or_id` | `any` | Refiner recipe id, a `Recipe` object, or a dictionary or class instance with a string `id` field. The recipe must belong to this machine and be unlocked. |

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
| `"output_busy"` | transient | Incompatible fluid remains in the output, preventing the recipe change. |

##### `.clear_recipe()` *(self only)*

Unset the selected refine recipe and leave the Refiner idle. Tar and raw feedstock inputs are preserved because they are staged supply.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"busy"` | transient | The component is already performing another operation. |
| `"material_present"` | rejection | Existing material prevents the requested configuration change. |

##### `.purge_input()` *(self only)*

Vents whatever raw feedstock is sitting in `gas_in` and `liquid_in`, releasing the port so it can accept a different fluid. The feedstock ports take the first fluid that reaches them and then only accept that one, so a port wired to the wrong Cap holds a fluid the recipe cannot use. Purge it, rewire, and carry on: `self.purge_input()` then `self.gas_in.connect("Raw Sulfur Cap")`. The vented fluid is destroyed, and tar in the input bin is untouched.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"empty"` | rejection | The relevant source or queue is empty. |
| `"busy"` | transient | The component is already performing another operation. |

##### `.get_recipe()`

Returns the current recipe id, or `""` when none is set (or the set recipe is no longer unlocked). Use to check state before re-setting: `if self.get_recipe() == "": self.set_recipe("refine_sulfur_gas")`.

- **Returns** String: the current recipe id, or `""` when none is set (or the set one is no longer unlocked).
- **Possible values** `""`, `"refine_sulfur_gas"`, `"refine_cryofluid"`, `"refine_chlorine"`, `"refine_quicksilver"`

##### `.get_recipe_inputs()`

Dict mapping each input `item_id` → units consumed per craft, for the Refiner this is the **tar** cost, e.g. `{"tar": 5}` for a rare exotic. Empty dict if no recipe is set. Read it to keep the tar bin stocked: `for item, qty in self.get_recipe_inputs().items(): self.input.take(item, qty * 5)`. (The raw-feedstock fluid amount is metered on the input ports, not listed here.)

- **Returns** Dict (`item_id` → count consumed per craft): for the Refiner this is the tar cost, e.g. `{"tar": 5}`. Empty dict if no recipe is set. (The raw-feedstock fluid cost is on the input ports, not here.)

##### `.is_running()`

`True` while a refine craft is actively advancing this tick (recipe set + unlocked, raw feedstock + tar present, out port has room). `False` when stalled, idle, or powered off.

- **Returns** Boolean: `True` while a refine craft is actively advancing this tick (recipe set + unlocked, raw feedstock + tar present, out port has room).

##### `.is_stalled()`

`True` when the refiner is powered and a recipe is set but the craft can't advance, for example because raw feedstock is missing (check `self.gas_in.level()` / `self.liquid_in.level()`), tar has run out (refill the input bin), or the refined-fluid out port is full (downstream backpressure, drain the out tank). `False` when unpowered, running, or no recipe is set. Poll to diagnose a stuck line.

- **Returns** Boolean: `True` when the refiner is powered and a recipe is set but the craft can't advance, for example because raw feedstock or tar is missing, or the refined-fluid out port is full (downstream backpressure). `False` when unpowered, running, or no recipe is set.

##### `.get_rate()`

Refined exotic produced this tick in t/h. **0** when stalled or idle. Use to confirm throughput while balancing feedstock against demand.

- **Returns** Number: refined exotic produced this tick in t/h. **0** when stalled or idle.

##### `.get_progress()`

Fraction **0-1** through the current refine craft. Resets to 0 each time a craft completes (a batch of refined fluid lands in the out port) and starts again if the feedstock + tar remain.

- **Returns** Number (**0-1**): progress through the current refine craft.

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Production & Storage*
