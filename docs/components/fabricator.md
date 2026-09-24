# Component: fabricator

> **Category:** Production & Storage | **Component Name:** Fabricator

Assembles finished parts from several refined materials at once. A script picks a recipe, gathers each ingredient into its shared stockpile, and drains the finished items out.

| Field | Value |
| --- | --- |
| Type | Mining |
| Power in | Variable (draws from grid) |
| Consumes | Steam, buffer 10 t |
| Consumes | Water, buffer 10 t |
| Consumes | Oil, buffer 10 t |
| Output buffer | 20 units |
| Byproduct buffer | 20 units |
| Stockpile | 200 units (mixed) |
| Recipes | 70 available |

### How to obtain

1. Requires the **Fabrication** research (Terraform Index 130,000).
2. Buy from the Shop for 1,400 cr.

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

Input I/O port feeding the multi-material stockpile. Inventory works at home only; remote Fabricators connect local stores and may switch between them for each ingredient. Transfers require **Auto Feeders** research. See `InputSlot`.

- **Returns** InputSlot: `connect()`, `take()`, `eject()`, `flush()`, `count()`, `capacity()`, `connected_to()`

##### `.output: OutputSlot`

Output I/O port for finished items. Inventory works at home only; remote Fabricators connect a local Storage Bin or Warehouse. Requires **Auto Feeders** research. See `OutputSlot`.

- **Returns** OutputSlot: `connect()`, `send()`, `count()`, `capacity()`, `connected_to()`

##### `.byproduct: OutputSlot`

Secondary output port for **byproducts**. Most recipes only emit through `self.output`; oil-refining recipes (lubricant, plastic, rubber) emit `tar` here on every craft. Same API as `self.output`: `self.byproduct.connect("Tar Bin")` then drain with `self.byproduct.send("tar", count)`. Requires **Auto Feeders** research. The byproduct bin must have space for the next craft, otherwise the recipe stalls, you have to keep this drained, not just `self.output`. See `OutputSlot`.

- **Returns** OutputSlot for byproducts: `connect()`, `send()`, `count()`, `capacity()`, `connected_to()`. Recipes that emit a byproduct (e.g. oil refining produces tar) deposit it here.

##### `.steam_in: FluidPort`

Internal steam process buffer for recipes that declare `fluid_inputs["steam_in"]`. Call `self.steam_in.connect(...)` with a Thermal Cap or steam Gas Tank's stable machine id or display name. A local source transfers directly; a remote source also needs a completed conflict-free gas-pipe route between both locations. Read `self.steam_in.level()` / `.flow_rate()` to detect starvation. **10** ton buffer. See `FluidPort`.

- **Returns** `FluidPort` process buffer. Call `connect(...)` with the provider's stable machine id or display name; a local provider transfers directly, while a remote provider uses any completed gas network reaching both outposts. Recipes with `fluid_inputs["steam_in"]` consume from it on craft completion.

##### `.water_in: FluidPort`

Internal water process buffer for recipes that declare `fluid_inputs["water_in"]`. Call `self.water_in.connect(...)` with a Water Pump, Steam Condenser, water Liquid Tank, or Large Liquid Tank's stable machine id or display name. A local source transfers directly; a remote source also needs a completed conflict-free liquid-pipe route between both locations. Read `self.water_in.level()` / `.flow_rate()` to detect starvation. **10** ton buffer. See `FluidPort`.

- **Returns** `FluidPort` process buffer. Call `connect(...)` with the provider's stable machine id or display name; a local provider transfers directly, while a remote provider uses any completed liquid network reaching both outposts. Recipes with `fluid_inputs["water_in"]` consume from it on craft completion.

##### `.oil_in: FluidPort`

Internal oil process buffer for recipes that declare `fluid_inputs["oil_in"]` (oil-refining recipes). Call `self.oil_in.connect(...)` with an Oil Pump, oil Liquid Tank, or Large Liquid Tank's stable machine id or display name. A local source transfers directly; a remote source also needs a completed conflict-free liquid-pipe route between both locations. Read `self.oil_in.level()` / `.flow_rate()` to detect starvation. **10** ton buffer. See `FluidPort`.

- **Returns** `FluidPort` process buffer. Call `connect(...)` with the provider's stable machine id or display name. A complete oil provider-consumer connection claims oil on the reachable physical component even while idle, full, or off; mere machine presence does not. Recipes with `fluid_inputs["oil_in"]` consume from it on craft completion.

### Methods

##### `.list_recipes() → list[Recipe]`

Every recipe this fabricator has been given a blueprint for. Returns Recipe objects with `.tier`, `.id`, `.name`, `.inputs`, `.output_item`, `.output_count`, `.duration_game_hours`, `.power_draw`, `.fluid_inputs` (tons consumed per run), and optional byproduct fields. Locked recipes (no blueprint yet) do not appear, the list reflects what the player can actually craft today. `sorted(self.list_recipes(), key=lambda recipe: recipe.tier)` orders the available queue from foundations upward.

- **Returns** List of unlocked Recipe objects. Each has `.tier`, `.id`, `.name`, `.inputs`, `.output_item`, `.output_count`, `.duration_game_hours`, `.power_draw`, `.fluid_inputs`, and optional byproduct fields.

##### `.find_recipe(recipe_id: str) → Recipe | None`

Find one unlocked recipe by id without looping through `list_recipes()`. Returns its `Recipe` object, or `None` when the id is unknown, locked, or belongs to another machine.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `recipe_id` | `str` | Fabricator recipe id |

- **Returns** The matching unlocked `Recipe`, or `None` if this Fabricator cannot currently run that id.

##### `.set_recipe(recipe_or_id: str | Recipe | IdRecord) → ActionResult` *(self only)*

Select which recipe to assemble: `self.set_recipe("craft_gas_pipe_segment")`, or pass a Recipe from `list_recipes()`. Setting a recipe doesn't clear the stockpile, so leftovers from a previous recipe stay until consumed or `self.input.flush()` discards them.

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

Unset the selected recipe and leave the Fabricator idle. The input stockpile is preserved because it is general staged material, not the selected recipe.

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

Current recipe id as a string, or the empty string if no recipe is set. Use to gate other logic or confirm after `set_recipe()`.

- **Returns** String (recipe id, or empty string)
- **Possible values** `""`, `"craft_gas_pipe_segment"`, `"craft_liquid_pipe_segment"`, `"craft_power_line_segment"`, `"craft_gas_pipe_bridge"`, `"craft_liquid_pipe_bridge"`, `"craft_power_line_bridge"`, `"craft_pressure_valve"`, `"craft_machine_frame"`, `"craft_circuit_panel"`, `"craft_control_unit"`, `"craft_battery_cell"`, `"craft_thermal_cap_kit"`, `"craft_turbine_rotor"`, `"craft_tank_lining"`, `"craft_water_pump"`, `"craft_oil_pump"`, `"craft_lubricant"`, `"craft_plastic"`, `"craft_rubber"`, `"craft_tar"`, `"craft_reinforced_biopolymer"`, `"craft_enrichment_compound"`, `"craft_drone_station_kit"`, `"craft_drone_station_kit_medium"`, `"craft_drone_station_kit_large"`, `"craft_drone_service_station_kit"`, `"craft_mining_drill_kit"`, `"craft_mining_drill_industrial_kit"`, `"craft_mining_drill_heavy_kit"`, `"craft_drone_small"`, `"craft_drone_medium"`, `"craft_drone_large"`, `"craft_electric_thruster"`, `"craft_heli_thruster"`, `"craft_cargo_pod_small"`, `"craft_cargo_pod_medium"`, `"craft_cargo_pod_large"`, `"craft_battery_pack"`, `"craft_oil_tank_small"`, `"craft_oil_tank_medium"`, `"craft_oil_tank_large"`, `"craft_coolant_loop"`, `"craft_neutron_capacitor"`, `"craft_seed_maker_kit"`, `"craft_plant_terraformer_kit"`, `"craft_grow_lamp_kit"`, `"craft_sprinkler_kit"`, `"craft_dispenser_kit"`, `"craft_garbage_disposal_kit"`, `"craft_exotic_gas_cap_kit"`, `"craft_exotic_spring_tap_kit"`, `"craft_fertilizer"`, `"craft_fertilizer_mk2"`, `"craft_fertilizer_mk3"`, `"craft_growth_accelerant"`, `"craft_yield_amplifier"`, `"craft_plant_terraformer_pack_mk2"`, `"craft_grow_lamp_pack_mk2"`, `"craft_grow_lamp_pack_mk3"`, `"craft_sprinkler_pack_mk2"`, `"craft_sprinkler_pack_mk3"`, `"craft_feed_maker_pack_mk2"`, `"craft_habitat_pack_mk2"`, `"craft_lead_plate"`, `"craft_oxygen_upgrade_pack_mk4"`, `"craft_heat_upgrade_pack_mk4"`, `"craft_pressure_upgrade_pack_mk4"`, `"craft_lead_cask"`, `"craft_shield_plating"`, `"craft_lightning_rod_kit"`

##### `.get_recipe_inputs() → dict[str, int]`

Input requirements for the current recipe as a dict `{item_id: count_per_craft}`. Empty dict if no recipe is set. Use with `.keys()` / `.values()` / `.items()` to drive a loop: `for mat, need in self.get_recipe_inputs().items(): self.input.connect(bin_for(mat)); self.input.take(mat, need)`.

- **Returns** A dict (item_id → count per craft), or empty dict if no recipe set

##### `.get_stockpile() → dict[str, int]`

Current stockpile contents as a dict `{item_id: count_currently_stored}`. Iterate with `.items()` to see every material; index directly with `self.get_stockpile()["iron_ingot"]` to read one. Essential for deciding what else needs pulling in.

- **Returns** A dict (item_id → count currently stored)

##### `.get_stockpile_used() → int`

Total units across every material in the stockpile. Compare to `get_stockpile_capacity()` to detect when the pile is full. When it is full, further input is blocked until the running craft consumes some material.

- **Returns** Number (total units across every material)

##### `.get_stockpile_capacity() → int`

Combined unit cap across all materials (fixed for this fabricator). Queryable rather than hardcoded, the cap tunes separately from your script. Use `used / capacity` for a fill-percent gauge.

- **Returns** Number (combined unit cap across all materials)

##### `.is_running() → bool`

`True` while a craft is in progress. Use before `set_recipe()` to avoid `"busy"`, or to show status. Stays `True` across ticks until the craft completes.

- **Returns** Boolean

##### `.get_progress() → float`

Progress toward the current craft's completion (**0-1**). Resets to **0** when a craft finishes. Use for progress bars and to detect completions by watching the value drop.

- **Returns** Number (**0-1**)

##### `.get_output_count() → int`

Completed units waiting in the output buffer. Drain them via `self.output.send(...)` before the buffer fills, processing stalls when the output is full.

- **Returns** Number (completed units waiting for pickup)

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Production & Storage*
