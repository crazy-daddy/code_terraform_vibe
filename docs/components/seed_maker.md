# Component: seed_maker

> **Category:** Biosphere | **Component Name:** Seed Maker

An outpost processing building that combines three life-form samples into a viable seed. Most blends fail; the working recipes are unique to this planet and found by trial, and a discovered one can be re-run for more.

| Field | Value |
| --- | --- |
| Type | Biosphere |
| Power in | Variable (draws from grid) |
| Output buffer | 1 units |
| Stockpile | 3 units (mixed) |

### How to obtain

1. The recipe unlocks with the **Seed Maker** research (Biomass 500).
2. Fabricate a **Seed Maker Kit** on a **Fabricator**: 2× Machine Frame, 1× Control Unit, 2× Circuit Panel, and 3 t Water.
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

`InputSlot` for loading the Seed Maker's three-sample reaction chamber. The natural source is a local Drone Depot where biological drones unload; a local Warehouse, Storage Bin, or home Inventory is also valid. The chamber accepts exactly **1 t each of three distinct life forms** and cannot stockpile surplus material.

- **Returns** `InputSlot` for the **3 t** reaction chamber. It accepts one unit each of three distinct life forms and rejects duplicates or a fourth sample. `combine()` reserves the trio while running. When idle, use `eject(...)` to recover a mistaken load or `flush()` to destroy it.

##### `.output`

`OutputSlot` containing the one physical seed produced by a successful trial. Send it to home Inventory, then call the Harvester's `load_seed()` anywhere on the local grid, or route it to a Crop Automator. The Seed Maker cannot start another trial until this result bay is empty. Sludge produces no item.

- **Returns** `OutputSlot` for the single physical result seed. Send it to home Inventory, then transfer it into the Harvester with `load_seed()`; another local store is also valid. A successful trial leaves exactly **1** species-specific seed here, and no further trial can start until `send(...)` removes it. A sludge result produces no output item.

### Methods

##### `.combine(blend)` *(self only)*

Run the exact three different life-form ids loaded in this machine's reaction chamber. Every accepted trial consumes the chamber's **1 t of each**. The one-seed result bay must be empty before any trial can start.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `blend` | `any` | A list of exactly 3 distinct life-form item ids, e.g. `["ice_algae", "sea_algae", "vent_algae"]`. Order does not matter; duplicates and any other length raise `ValueError`. |

- **Returns** `SeedResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.seed_id`, `.species`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"seed_found"` | success | Discovered `.species` and deposited `.seed_id` into the Seed Maker output. |
| `"sludge"` | success | The accepted three-life-form blend produced no seed. |
| `"locked"` | rejection | Seed Maker research is not unlocked. |
| `"busy"` | transient | A Seed Maker combine trial is already in progress. |
| `"missing_life_forms"` | rejection | The Seed Maker chamber does not contain exactly the requested three 1 t life-form samples. |
| `"output_full"` | rejection | The Seed Maker result bay already contains its one physical seed. |

*Raises*

| Exception | Condition |
| --- | --- |
| `ValueError` | The blend must contain exactly three distinct, known life-form ids. |

##### `.life_forms()`

List of the **30** accepted life-form item ids. For each `blend` from `combinations(self.life_forms(), 3)`, load its three items with `self.input.take(item_id, 1)`, then call `self.combine(blend)`. Enumeration does not move materials. Send any resulting physical seed from `self.output` before continuing.

- **Returns** List of the **30** accepted life-form item ids. For each `blend` from `combinations(self.life_forms(), 3)`, load its three items with `self.input.take(item_id, 1)`, then call `self.combine(blend)`. Enumeration does not move materials. Send any resulting physical seed with `self.output.send(...)` before the next trial.

##### `.is_running()`

`True` while a combine trial is in flight.

- **Returns** Boolean: `True` while a combine trial is in flight.

##### `.get_progress()`

Progress of the current combine trial as **0-1**; returns **0** when idle.

- **Returns** Number (**0-1**): progress of the current trial; **0** when idle.

##### `.get_output_count()`

Number of physical seeds waiting in the single-result bay: **0** or **1**.

- **Returns** Number (**0** or **1**): whether a physical seed is waiting in the result bay.

##### `.recipes()`

List of `SeedRecipe` for every blend discovered so far, the same discover-once-kept-forever journal the Flora / Seed Recipes tab shows. Each carries `.tier`, the physical `.seed_id`, bare `.species`, `.blend`, `.requirements`, `.requirement`, and `.growth_time`. `.requirements` is the programmable form: every `PlantRequirement` has `.kind` and optional `.species`, so companion and antagonist entries identify the exact related plant. `.requirement` remains a compact string summary. Empty until your first hit; re-run a known `.blend` with `self.combine(...)` to reproduce that seed without re-sweeping.

- **Returns** List of every discovered `SeedRecipe`, or an empty list before the first discovery. Each recipe includes its species, three-item blend, cultivation requirements, and growth time. Use `self.combine(recipe.blend)` to reproduce its seed.

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Biosphere*
