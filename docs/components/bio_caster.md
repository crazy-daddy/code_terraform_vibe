# Component: bio_caster

> **Category:** Terraforming | **Component Name:** Bio Caster

Forges a volcanic fragment by holding the crucible in a target temperature band while the recipe's materials are loaded, then casting. Steam and water use separate 20 t internal process buffers. Connect each input port to a compatible source; local sources transfer directly, while remote sources also need a completed conflict-free pipe route between both locations. A script drives the heat and cooling; casting out of band or with the wrong materials burns the whole charge.

| Field | Value |
| --- | --- |
| Type | Atmosphere |
| Power in | -15 W (draws from grid) |
| Consumes | Steam, buffer 20 t |
| Consumes | Water, buffer 20 t |
| Output buffer | 30 units |
| Stockpile | 30 units (mixed) |

### How to obtain

1. Requires the **Volcanic Forge-Casting** research (Oxygen 350).
2. Buy from the Shop for 150,000 cr.

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

##### `self.input`

The multi-material `InputSlot` for both the raw volcanic sample and fabricated materials. Connect Inventory only at Nocturna Base; at another outpost connect a same-outpost Storage Bin/Warehouse. Call `take(...)` for every required item.

- **Returns** `InputSlot` for the raw Volcanic sample and fabricated materials. Inventory is available only at home; at remote outposts route freight through local storage. Before `cast()`, recover a mistaken sample or material with `eject(...)`.

##### `self.output`

The `OutputSlot` for Forged samples and non-destructively ejected items. Exact item properties are preserved.

- **Returns** `OutputSlot` for Forged samples and non-destructively ejected items.

##### `self.steam_in`

Supplies the Caster's heat control through a **20 t** steam buffer. Call `self.steam_in.connect(...)` with a Thermal Cap or steam Gas Tank's stable machine id or display name. A local source transfers directly; a remote source also needs a completed conflict-free Gas Pipe route between both locations. The connection remains while idle, full, or powered off. See `FluidPort` for level, capacity, and flow queries.

- **Returns** The Caster's **20 t** steam buffer as a `FluidPort`. Call `connect(...)` with the provider's stable machine id or display name; completed gas-pipe networks carry steam between outposts.

##### `self.water_in`

Supplies the Caster's cooling control through a **20 t** water buffer. Call `self.water_in.connect(...)` with a Water Pump, Steam Condenser, water Liquid Tank, or Large Liquid Tank's stable machine id or display name. A local source transfers directly; a remote source also needs a completed conflict-free Liquid Pipe route between both locations. The connection remains while idle, full, or powered off. See `FluidPort` for level, capacity, and flow queries.

- **Returns** The Caster's **20 t** water buffer as a `FluidPort`. Call `connect(...)` with the provider's stable machine id or display name; completed liquid-pipe networks carry water between outposts.

### Methods

##### `self.list_recipes()`

List all 16 forge recipes without changing the selected recipe, `self.list_recipes()`. Each `BioCasterRecipe` includes its fragment id, tier, exact material shopping list, and target temperature range. The read works through `get_component(...)`, so another machine can plan supplies without possessing every fragment.

- **Returns** List of all 16 `BioCasterRecipe` objects. Each exposes `.fragment_id`, `.tier`, `.materials`, and `.temperature_range` for read-only production planning.

##### `self.find_recipe(fragment_id)`

Look up one forge recipe by volcanic fragment id without selecting it, `self.find_recipe(fragment_id)`. Returns `None` for an unknown id.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `fragment_id` | `string` | Volcanic fragment id from `catalog()`. |

- **Returns** The matching `BioCasterRecipe`, or `None` for an unknown fragment id.

##### `self.catalog()`

The 16 forgeable volcanic fragment ids, `self.catalog()`. Pass one to `set_recipe(...)`, or use `list_recipes()` when you also need every recipe's material and temperature requirements. Fixed hardware; read it once.

- **Returns** List of the 16 forgeable Volcanic fragment ids. Use `list_recipes()` when you also need material and temperature requirements.

##### `self.recipe_tier(fragment_id)`

Derived production tier for one recipe from `catalog()`. Returns `None` for an unknown fragment id.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `fragment_id` | `string` | Volcanic fragment id from `catalog()`. |

- **Returns** Derived production tier for this Bio Caster recipe, or `None` for an unknown fragment id.

##### `self.set_recipe(fragment_id)` *(self only)*

Select which volcanic fragment to forge, `self.set_recipe("sd_tail_barb")`. After this, `required_range()` and `required_materials()` describe that recipe. The selection persists like a Smelter recipe.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `fragment_id` | `string` | A Volcanic fragment id from `catalog()`: the fragment you intend to forge. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"invalid_recipe"` | rejection | The supplied recipe is invalid. |
| `"busy"` | transient | The component is already performing another operation. |
| `"output_full"` | rejection | Finished work is waiting for space in this machine's output, so nothing else can start. Free the output and the wait ends on its own. |

##### `self.recipe()`

The recipe you've selected, `self.recipe()` returns the volcanic fragment id you're set to forge (also the raw fragment to `load`), or `None` if none is set.

- **Returns** The selected recipe = the Volcanic fragment id this Caster will forge (also the raw fragment to `load`), or `None` if no recipe is set.
- **Possible values** `"ma_chitinous_seta"`, `"st_beak"`, `"ms_abdomen_sclerite"`, `"mh_chitin_node"`, `"gm_abdominal_sheath"`, `"vm_tail_barb"`, `"vc_walking_leg"`, `"oc_ink_sac"`, `"bw_hindlimb"`, `"vd_photophore"`, `"hs_abdomen_segment"`, `"hc_beak"`, `"fs_oral_tegmen"`, `"ce_great_appendage"`, `"gw_jaw_fang"`, `"sd_tail_barb"`

##### `self.required_range()`

The selected recipe's target band `[low, high]` in °C, `self.required_range()`. `cast()` must fire with `temperature()` inside it (inclusive). `None` if no recipe is set.

- **Returns** The selected recipe's target temperature band `[low, high]` in °C: `cast()` must fire with `temperature()` inside it (inclusive). `None` if no recipe is set.

##### `self.required_materials()`

Lists the fabricated materials required by the selected recipe as `{item_id: count}`. Load exactly those amounts before casting. Iterate with `.items()`. Returns an empty dict when no recipe is selected.

- **Returns** Dict `{item_id: count}` of the fabricated materials the selected recipe needs: load EXACTLY these (no more, no less) before `cast()`. `{}` if no recipe is set. Iterate with `.items()`.

##### `self.required_fragment()`

The raw fragment id the recipe consumes, `self.required_fragment()` (identical to `recipe()`). `None` if no recipe is set.

- **Returns** The raw Volcanic fragment id the selected recipe consumes (identical to `recipe()`). `None` if no recipe is set.
- **Possible values** `"ma_chitinous_seta"`, `"st_beak"`, `"ms_abdomen_sclerite"`, `"mh_chitin_node"`, `"gm_abdominal_sheath"`, `"vm_tail_barb"`, `"vc_walking_leg"`, `"oc_ink_sac"`, `"bw_hindlimb"`, `"vd_photophore"`, `"hs_abdomen_segment"`, `"hc_beak"`, `"fs_oral_tegmen"`, `"ce_great_appendage"`, `"gw_jaw_fang"`, `"sd_tail_barb"`

##### `self.temperature()`

Current crucible temperature in °C, `self.temperature()`, ranging **100** (cold baseline) to **1000** (max). Drive it into `required_range()` with the knobs before casting.

- **Returns** Current crucible temperature in °C (**100-1,000**). Drive it into `required_range()` with the knobs before casting.

##### `self.temp_rate()`

Net temperature change in °C/h right now, `self.temp_rate()`. Positive = heating and negative = cooling. Full heat is +2400 °C/h and full cool is -2400 °C/h; with both knobs at 0, an unlocked crucible above baseline cools naturally at -20 °C/h. Returns 0 at the 100 °C baseline or while a cast is in progress.

- **Returns** Current net temperature rate in °C/h, signed: positive = heating and negative = cooling. Full heat is +2400 °C/h and full cool is -2400 °C/h. With both knobs at 0, an unlocked crucible above baseline returns -20 °C/h for passive cooling; returns 0 at baseline or during a cast.

##### `self.heat()`

Current heat-knob setting **0-100 %**, `self.heat()`. At 100 % temperature rises **+2400 °C/h** (burning steam); use a lower setting near the target band.

- **Returns** Current heat-knob setting, **0-100%**. At 100 % temperature rises **+2400 °C/h** (burning steam); use a lower setting near the target band.

##### `self.cool()`

Current cool-knob setting **0-100 %**, `self.cool()`. At 100 % temperature falls **-2400 °C/h** (burning water); use a lower setting near the target band.

- **Returns** Current cool-knob setting, **0-100%**. At 100 % temperature falls **-2400 °C/h** (burning water); use a lower setting near the target band.

##### `self.fragment()`

The raw fragment id loaded in the chamber, `self.fragment()`, or `None` if the chamber is empty.

- **Returns** The raw Volcanic fragment id currently in the chamber (from `load`), or `None` if the chamber is empty.
- **Possible values** `"ma_chitinous_seta"`, `"st_beak"`, `"ms_abdomen_sclerite"`, `"mh_chitin_node"`, `"gm_abdominal_sheath"`, `"vm_tail_barb"`, `"vc_walking_leg"`, `"oc_ink_sac"`, `"bw_hindlimb"`, `"vd_photophore"`, `"hs_abdomen_segment"`, `"hc_beak"`, `"fs_oral_tegmen"`, `"ce_great_appendage"`, `"gw_jaw_fang"`, `"sd_tail_barb"`

##### `self.materials()`

The materials currently loaded in the crucible, `self.materials()` returns `{item_id: count}`. Compare against `required_materials()` before `cast()`. Iterate with `.items()`.

- **Returns** Dict `{item_id: count}` of the fabricated materials currently loaded in the crucible. Compare against `required_materials()` before `cast()`. Iterate with `.items()`.

##### `self.set_heat(pct)` *(self only)*

Set the heat knob (steam to temperature up), `self.set_heat(100)` for +2400 °C/h, then use a lower percentage for the final approach. Range **0-100**, clamped. Open-loop: it keeps heating and burning steam until you set it back. With both knobs at 0, the crucible cools naturally at 20 °C/h, so cast after entering the band. Re-idles to 0 when the chamber empties or the script stops.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pct` | `number` | Heat level 0-100 (%). Both knobs may run at once; net rate = heat − cool. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"empty"` | rejection | The relevant source or queue is empty. |
| `"busy"` | transient | The component is already performing another operation. |
| `"output_full"` | rejection | Finished work is waiting for space in this machine's output, so nothing else can start. Free the output and the wait ends on its own. |

##### `self.set_cool(pct)` *(self only)*

Set the cool knob (water to temperature down), `self.set_cool(100)` for -2400 °C/h, then use a lower percentage for the final approach. Range **0-100**, clamped. Open-loop: keeps cooling and burning water until you set it back. Both knobs may run at once, but that burns both fluids for little movement. With both knobs at 0, the crucible still cools naturally at 20 °C/h. Re-idles to 0 when the chamber empties or the script stops.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pct` | `number` | Cool level 0-100 (%). Both knobs may run at once; net rate = heat − cool. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"empty"` | rejection | The relevant source or queue is empty. |
| `"busy"` | transient | The component is already performing another operation. |
| `"output_full"` | rejection | Finished work is waiting for space in this machine's output, so nothing else can start. Free the output and the wait ends on its own. |

##### `self.load(fragment_id, properties=None, property_match=None)` *(self only)*

Pull a raw volcanic sample of `fragment_id` from `self.input` into the chamber, usually `self.load(self.recipe())`. Optional `properties` and `property_match` select a specific identity using the standard any, subset, or exact convention.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `fragment_id` | `string` | A raw Volcanic fragment id staged in `self.input`. Usually `recipe()`. |
| `properties` | `any` | Optional property dict, matched as a subset by default. Omitted or `None` matches any properties; use `None` with `property_match="exact"` to select propertyless items only. |
| `property_match` | `string` | Optional selection mode: any, subset, or exact |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"chamber_occupied"` | rejection | The processing chamber already contains an item. |
| `"not_in_input"` | rejection | The requested item is not present in the input. |
| `"invalid_fragment"` | rejection | The supplied fragment identifier is invalid. |
| `"invalid_properties"` | rejection | The supplied item-property selector is invalid. |
| `"invalid_property_match"` | rejection | The supplied property-matching mode is invalid. |
| `"busy"` | transient | The component is already performing another operation. |
| `"output_full"` | rejection | Finished work is waiting for space in this machine's output, so nothing else can start. Free the output and the wait ends on its own. |

##### `self.eject()` *(self only)*

Stage the chamber sample and all loaded materials in `self.output` without changing their properties. A single-material output may require a send/eject cycle for each item type.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"empty"` | rejection | The relevant source or queue is empty. |
| `"busy"` | transient | The component is already performing another operation. |
| `"output_full"` | rejection | The output has no capacity for the result. |

##### `self.cast()` *(self only)*

Forge the loaded fragment, `self.cast()`.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"out_of_range"` | rejection | The chamber temperature was outside the selected recipe's required range, so the loaded fragment and materials were destroyed. |
| `"wrong_materials"` | rejection | The staged materials do not match the operation's requirements. |
| `"wrong_fragment"` | rejection | The loaded fragment does not match the requested fragment. |
| `"empty"` | rejection | The relevant source or queue is empty. |
| `"no_recipe"` | rejection | No recipe is currently selected. |
| `"busy"` | transient | The component is already performing another operation. |
| `"output_full"` | rejection | The output has no capacity for the result. |

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Terraforming*
