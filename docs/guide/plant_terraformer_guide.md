# Guide: plant_terraformer_guide

## Plant Terraformer

The sole converter from harvested physical Forage to permanent Plants km². Load its input through ordinary timed item transfers; its high-capacity feeder handles 16 items per step at Mk I and 80 at Mk II. Each phase adds Water, Salt, Fertilizer, then Growth Accelerant. Mk I stops at the Fields threshold; Mk II carries the final two phases.

| Field | Value |
| --- | --- |
| Type | Biosphere |
| Power in | Variable (draws from grid) |
| Consumes | Water, buffer 60 t |
| Stockpile | 1,243 units (mixed) |
| Tiers | Mk II |

### How to obtain

1. The recipe unlocks with the **Plant Terraformer** research (Biomass 2,000).
2. Fabricate a **Plant Terraformer Kit** on a **Fabricator**: 5× Machine Frame, 3× Control Unit, 5× Circuit Panel, 4× Liquid Pipe Segment, and 10 t Water.
3. Deploy it from your Inventory.

**Returned by:** `self`

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

Standard timed `InputSlot` for Forage, Salt, Fertilizer, and Growth Accelerant. Connect Inventory, a local Storage Bin or Warehouse, or a local machine output such as a Crop Automator after Auto Feeders research. The destination feeder handles **16 items per step** at Mk I and **80** at Mk II, in either transfer direction. Its holders fit one full Forage batch plus Salt and up to **10 of each** support item type.

- **Returns** `InputSlot` for timed item transfers into the Terraformer's one-cycle material holders. Mk I handles 16 items per ordinary feeder quantum; Mk II handles 80.

##### `.water_in`

Water `FluidPort` sized for one full cycle: **60 t** at Mk I or **330 t** at Mk II. Connect it to a water source; a remote source also needs a completed conflict-free Liquid Pipe route between both locations. Water is required from the Seedlings phase onward.

- **Returns** `FluidPort` for Water. Water becomes required from the Seedlings phase onward.

### Methods

##### `.set_enabled(enabled)` *(self only)*

Enable or pause conversion. `True` starts a cycle whenever the onboard item holders and Water can supply at least one proportional Forage unit. A cycle runs for **3 hours** at full outpost efficiency. Stopping this machine's script resets the setpoint to `False`; an in-flight batch remains loaded.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `enabled` | `boolean` | `True` to convert from materials already loaded through `input`, `False` to pause the machine. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.is_enabled()`

`True` when the current machine script has commanded conversion on.

- **Returns** `boolean`

##### `.tier()`

Permanently installed Plant Terraformer tier as an integer (**1-2**). Mk II raises batch throughput and enables the late Plants recipes.

- **Returns** Integer: permanently installed Plant Terraformer tier (**1-2**).

##### `.status()`

Exact live state: `"complete"`, `"disabled"`, `"no_power"`, `"needs_mk2"`, `"no_forage"`, `"no_water"`, `"no_salt"`, `"no_fertilizer"`, `"no_accelerant"`, or `"running"`.

- **Returns** Exact live state: `"complete"`, `"disabled"`, `"no_power"`, `"needs_mk2"`, `"no_forage"`, `"no_water"`, `"no_salt"`, `"no_fertilizer"`, `"no_accelerant"`, or `"running"`.
- **Possible values** `"complete"`, `"disabled"`, `"no_power"`, `"needs_mk2"`, `"no_forage"`, `"no_water"`, `"no_salt"`, `"no_fertilizer"`, `"no_accelerant"`, `"running"`

##### `.is_running()`

`True` while a conversion cycle is running. An unpowered or disabled machine keeps its in-flight batch but reads `False` until it resumes.

- **Returns** Boolean

##### `.get_progress()`

Completion of the current conversion cycle, **0-1**. A full cycle requires **3 hours** of work at 100% outpost efficiency; overcrowding slows its progress proportionally. Reads **0** whenever no batch is loaded.

- **Returns** Number (**0-1**)

##### `.batch_size()`

Whole Forage items in the running cycle, or the batch that can load now. A full batch is **1,200** at Mk I and **6,600** at Mk II. Limited materials or a nearby phase boundary load less.

- **Returns** Whole Forage items committed to the running cycle, or the batch the next cycle would load. Returns 0 while stalled, disabled, or complete.

##### `.km2_rate()`

This machine's current permanent Plants output in km²/h. It combines the loaded batch, its nominal **3 hour** work cycle, the pinned phase exchange rate from **20 km² per Forage** early to **1 km² per 3 Forage** late, and this outpost's overcrowding efficiency. Returns **0** while blocked, disabled, or complete.

- **Returns** Current conversion rate in km²/h, the running batch spread across its cycle. Returns 0 while stalled, disabled, or complete.

##### `.phase()`

Current global Plants phase number, **1-6**.

- **Returns** Current global Plants phase index from 1 to 6.

##### `.recipe_tier()`

Derived production tier of the current cumulative Plants conversion recipe. Returns `None` after Continental completion.

- **Returns** Derived production tier for the current Plants conversion, or `None` after completion.

##### `.next_threshold()`

Permanent Plants km² required for the next phase. At completion, returns the **5,000,000 km²** ceiling.

- **Returns** Plants km² required for the next phase, or the completed 5,000,000 km² ceiling.

##### `.remaining()`

Permanent Plants km² still needed for the next phase. Returns **0** when Continental is complete.

- **Returns** Plants km² remaining to the next phase. Returns 0 at completion.

##### `.required_inputs()`

Current cumulative material ids. Starts with `forage`, then adds `water`, `salt`, the `fertilizer` category, and `growth_accelerant` across the five conversions.

- **Returns** List of the material ids required by the current cumulative phase recipe.

##### `.batch_requirements()`

Exact amounts for the largest next batch allowed by this tier and phase. The dict uses `forage`, `water`, `salt`, `fertilizer_potency`, and `growth_accelerant` as needed. Salt and Growth Accelerant are whole-item counts, rounded up per batch. Fertilizer potency is a whole number. It does not shrink when onboard stock is short.

- **Returns** Dict of the material amounts for the largest next batch allowed by this tier and phase. Salt and Growth Accelerant are whole-item counts, rounded up per batch. Fertilizer is reported as whole `fertilizer_potency`.

##### `.fertilizer_potency(item_id)`

Return one Fertilizer item's whole potency: **10** for Mk I, **30** for Mk II, or **50** for Mk III. Any other item id raises `ValueError`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `string` | A Fertilizer Mk I, Mk II, or Mk III item id. |

- **Returns** Potency of one Fertilizer item: 10 for Mk I, 30 for Mk II, or 50 for Mk III.

*Raises*

| Exception | Condition |
| --- | --- |
| `ValueError` | The item id must identify Fertilizer Mk I, Mk II, or Mk III. |

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Biosphere*

---
