# Component: dna_sequencer

> **Category:** Terraforming | **Component Name:** DNA Sequencer

Splices genes into geothermal fragments so they carry what an order needs. You work at the gene level, load a fragment, read the genes it has and the genes it needs, splice the target set in, the machine composes the DNA for you. One splice per fragment.

| Field | Value |
| --- | --- |
| Type | Atmosphere |
| Power in | -20 W (draws from grid) |
| Input buffer | Units: 10 |
| Output buffer | Units: 10 |

### How to obtain

1. Requires the **Gene Sequencing** research (Pressure 120).
2. Buy from the Shop for 100,000 cr.

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

##### `self.chamber: ChamberFragment | None`

The `ChamberFragment` loaded right now, exposed as `self.chamber`, or `None`. Read `.genes` and `.spliced`; a second splice destroys an already-spliced sample.

- **Returns** `ChamberFragment | None`. `None` if the chamber is empty.

##### `self.input: InputSlot`

The `InputSlot` for geothermal samples. It holds one sample item id at a time and stays latched to that id until `load()` consumes the remaining units or `flush()` discards them. `stacks()` lists property-distinct variants and does not mean the port accepts multiple sample types. Inventory is a source only at Nocturna Base; remote Sequencers use a same-outpost Storage Bin/Warehouse.

- **Returns** `InputSlot`. For geothermal samples. Recover a mistaken property variant to an explicit local destination with `eject(...)` before loading it into the chamber.

##### `self.output: OutputSlot`

The `OutputSlot` for spliced or ejected samples. Exact sample properties are preserved.

- **Returns** `OutputSlot`. For spliced or ejected samples, preserving every property.

### Methods

##### `self.load(fragment_id: str, properties: ItemProperties | None = None, property_match: str | None = None) → ActionResult` *(self only)*

Pull a geothermal sample of `fragment_id` from `self.input` into the chamber, `self.load("gw_cardiac_node")`. Optional `properties` and `property_match` select a specific identity using the standard `any`, `subset`, or `exact` convention.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `fragment_id` | `str` | A geothermal fragment id staged in `self.input`. |
| `properties` | `ItemProperties \| None` | Optional property `dict`, matched as a subset by default. Omitted or `None` matches any properties; use `None` with `property_match="exact"` to select propertyless items only. |
| `property_match` | `str \| None` | Optional selection mode: `"any"`, `"subset"`, or `"exact"` |

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

##### `self.genes() → list[str] | None`

Lists the genes currently carried by the chambered fragment, such as `["cold_tolerance", "pressure_tolerance"]`, or returns `None` when empty. `splice()` takes time. On completion, the fragment moves to output and the chamber becomes empty. If output is full, the spliced fragment stays in the chamber until space is available.

- **Returns** `list[str] | None`. The genes currently carried by the chambered fragment, e.g. `["cold_tolerance", "pressure_tolerance"]`, or `None` if the chamber is empty. `splice()` takes time. Successful delivery empties the chamber; a completed splice waiting for output space retains its new genes in the chamber.

##### `self.gene_catalog() → list[str]`

Every gene id the machine can splice, `self.gene_catalog()` returns the full list (e.g. `["heat_resistance", "acid_resistance", "cold_tolerance", "pressure_tolerance", "toxin_resistance", "radiation_shield"]`), the valid values to pass to `splice()`.

- **Returns** `list[str]`. Every gene id the machine can splice (e.g. `["heat_resistance", "acid_resistance", "cold_tolerance", ...]`): the valid values for `splice()`.

##### `self.splice(genes: list[str]) → ActionResult` *(self only)*

Replace the chambered fragment's gene set with exactly `genes`, then place it in `self.output` while preserving every unrelated property.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `genes` | `list[str]` | A list of gene ids the engineered fragment must carry (from `gene_catalog()`, or an order's `required_genes[fragment_id]`). |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"destroyed"` | success | The target was destroyed. |
| `"empty"` | rejection | The relevant source or queue is empty. |
| `"unknown_gene"` | rejection | The supplied gene identifier does not exist. |
| `"busy"` | transient | The component is already performing another operation. |
| `"output_full"` | rejection | The output has no capacity for the result. |

##### `self.discard() → ActionResult` *(self only)*

Stage the chamber fragment in `self.output` without splicing.

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

*Components / Terraforming*
