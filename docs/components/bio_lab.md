# Component: bio_lab

> **Category:** Terraforming | **Component Name:** Bio Lab

Automates the Analyze and Extract steps of the biology loop, studying a specimen and pulling a usable sample from it. It stays idle until a script drives it.

| Field | Value |
| --- | --- |
| Type | Atmosphere |
| Power in | -5 W (draws from grid) |
| Input buffer | 30 units |
| Stockpile | 30 units (mixed) |

### How to obtain

1. Buy from the Shop for 5,000 cr.

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

##### `self.specimen: Specimen | None`

The `Specimen` in the lab chamber right now, exposed as `self.specimen`, or `None`. Read `self.specimen.stage` to distinguish `"collected"` from `"analyzed"`. Before analysis its identifying fields are hidden; after analysis its `fragment_id`, `rarity`, and `recipe` are populated.

- **Returns** The `Specimen` currently in the chamber, with `.stage` `"collected"` or `"analyzed"`, or `None` if empty.

##### `self.loaded_reagents: dict[str, int]`

A dict `{reagent_id: qty}` of reagents staged for the next `extract()`. Iterate `.items()` to inspect.

- **Returns** A dict `{reagent_id: qty}` of reagents staged for the next `extract()`.

##### `self.input: InputSlot`

The `InputSlot` for scripted reagent routing. It holds one reagent item id at a time and stays latched to that id until `load()` consumes the remaining units or `flush()` discards them. `stacks()` lists property-distinct variants and does not mean the port accepts multiple reagent types. Connect Inventory only at Nocturna Base; at another outpost connect a same-outpost Storage Bin/Warehouse. Call `take(...)` before `load(...)`.

- **Returns** `InputSlot` for scripted reagent routing. Inventory is available only at Nocturna Base; remote Labs use a local Storage Bin or Warehouse. Recover an unneeded staged reagent with `eject(...)`.

##### `self.output: OutputSlot`

The `OutputSlot` for extracted property-bearing samples and unloaded reagents. Connect any eligible local item store and drain it with `send(...)`.

- **Returns** `OutputSlot` holding extracted samples and unloaded reagents with exact properties intact.

### Methods

##### `self.take_from(collector: Component | IdRecord) → ActionResult` *(self only)*

Pull the specimen out of a Bio Collector's cargo into this lab's specimen chamber. The source Collector must be at the same outpost as this Lab; pass an explicit collector reference: `self.take_from(get_component("bio_collector_1"))`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `collector` | `Component \| IdRecord` | A `bio_collector` component reference, or a dictionary or class instance with its string `id` field. The collector must still exist in the same outpost; cargo is read from the current collector. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The specimen was transferred into the Bio Lab's specimen chamber. |
| `"busy"` | transient | The Bio Lab is currently analyzing or extracting. |
| `"input_occupied"` | rejection | The Bio Lab's specimen chamber already contains a specimen. |
| `"not_found"` | rejection | The supplied component reference does not exist. |
| `"source_empty"` | rejection | The Bio Collector's cargo contains no specimen. |
| `"source_busy"` | transient | The Bio Collector is still completing a collection trip. |
| `"wrong_outpost"` | rejection | The Bio Collector belongs to a different outpost. |
| `"invalid_source"` | rejection | The supplied component is not a valid Bio Collector. |
| `"output_full"` | rejection | Finished work is waiting for space in this machine's output, so nothing else can start. Free the output and the wait ends on its own. |

##### `self.analyze() → AnalyzeResult` *(self only)*

Identify the lab's current fragment and reveal its extraction recipe. Analysis takes **~0.1 h** in every biome; the script pauses until it finishes. A successful analysis adds the fragment to `journal.cataloged_fragments(planet_id)`. Creature identity stays hidden until all five fragments are cataloged, then the creature appears in `journal.cataloged_creatures(planet_id)`.

- **Returns** `AnalyzeResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.info`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The specimen analysis completed successfully. |
| `"busy"` | transient | The Bio Lab is already completing another action. |
| `"output_full"` | rejection | The Bio Lab is holding a finished sample that is waiting for space in its output, so nothing else can start. |
| `"input_empty"` | rejection | The Bio Lab has no specimen to analyze. |
| `"invalid_specimen"` | rejection | The loaded specimen has no recognizable fragment identity and cannot be analyzed. |

##### `self.load(reagent_id: str, qty: int, properties: ItemProperties | None = None, property_match: str | None = None) → ActionResult` *(self only)*

Stage a whole-number reagent quantity for the next `extract()` by consuming it from `self.input`. `self.load("alkaline_buffer", 4)`. Reagents are sold by the `shop`; both UI purchases and `shop.buy(reagent_id)` place them in base Inventory. Optional `properties` and `property_match` select a specific item identity using the standard any, subset, or exact convention. Fractional or negative quantities raise an argument error. Calling `extract()` with a mismatched recipe destroys the loaded reagents.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `reagent_id` | `str` | Reagent item id to load from the connected input. |
| `qty` | `int` | Whole-number reagent units to load |
| `properties` | `ItemProperties \| None` | Optional property dict, matched as a subset by default. Omitted or `None` matches any properties; use `None` with `property_match="exact"` to select propertyless items only. |
| `property_match` | `str \| None` | Optional selection mode: any, subset, or exact |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"busy"` | transient | The component is already performing another operation. |
| `"invalid_reagent"` | rejection | The supplied reagent is invalid for this operation. |
| `"invalid_qty"` | rejection | The supplied quantity is invalid. |
| `"invalid_properties"` | rejection | The supplied item-property selector is invalid. |
| `"invalid_property_match"` | rejection | The supplied property-matching mode is invalid. |
| `"insufficient_input"` | rejection | The input does not contain the required quantity. |
| `"output_full"` | rejection | Finished work is waiting for space in this machine's output, so nothing else can start. Free the output and the wait ends on its own. |

##### `self.unload_reagents() → ActionResult` *(self only)*

Stage all loaded reagents in `self.output` without touching the specimen. Use this when you staged the wrong recipe.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | All loaded reagents were staged in the Bio Lab's output without changing the specimen. |
| `"empty"` | rejection | The Bio Lab has no loaded reagents. |
| `"busy"` | transient | The Bio Lab is currently taking, analyzing, or extracting. |
| `"output_full"` | rejection | The output has no capacity for the loaded reagents; the reagents remain loaded. |

##### `self.extract() → ActionResult` *(self only)*

Consume `loaded_reagents` and place **1 sample** of the analyzed specimen in `self.output`, preserving its exact properties. Extraction takes **~0.1 + 0.05 × units h** in every biome; the script pauses until it finishes.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The loaded reagents were consumed and one sample preserving the analyzed specimen's exact properties was staged in the output. |
| `"output_full"` | rejection | The completed extraction is preserved because the output has no capacity for its sample. |
| `"recipe_mismatch"` | rejection | The loaded reagents do not match the analyzed specimen's recipe; the reagents are destroyed and the specimen is preserved. |
| `"busy"` | transient | The Bio Lab is currently taking, analyzing, or extracting. |
| `"input_empty"` | rejection | The Bio Lab has no specimen to extract. |
| `"not_analyzed"` | rejection | The loaded specimen has not been analyzed. |
| `"invalid_specimen"` | rejection | The loaded specimen has no recognizable fragment identity. |

##### `self.discard() → ActionResult` *(self only)*

Drop the current specimen and stage any loaded reagents in `self.output`. Use it after `analyze()` reveals a fragment you do not need.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"input_empty"` | rejection | The operation's input contains no applicable item or material. |
| `"busy"` | transient | The component is already performing another operation. |
| `"output_full"` | rejection | The output has no capacity for the result. |

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Terraforming*
