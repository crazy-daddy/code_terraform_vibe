# Component: bio_conditioner

> **Category:** Terraforming | **Component Name:** Bio Conditioner

Inspects a deep-biome fragment against a fixed rulebook, quizzing your script on its properties one at a time. Judge each one correctly to pass the fragment; a single wrong call burns the whole specimen.

| Field | Value |
| --- | --- |
| Type | Atmosphere |
| Power in | -25 W (draws from grid) |
| Input buffer | 10 units |
| Output buffer | 10 units |

### How to obtain

1. Requires the **Deep-Sea Conditioning** research (Temperature 1,200).
2. Buy from the Shop for 225,000 cr.

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

##### `self.input: InputSlot`

The `InputSlot` for raw deep samples. It holds one sample item id at a time and stays latched to that id until `load()` consumes the remaining units or `flush()` discards them. `stacks()` lists property-distinct variants and does not mean the port accepts multiple sample types. Inventory is a source only at Nocturna Base; remote Conditioners use a same-outpost Storage Bin/Warehouse.

- **Returns** `InputSlot` for raw Deep samples. Recover a mistaken property variant to an explicit local destination with `eject(...)` before loading it into the chamber.

##### `self.output: OutputSlot`

The `OutputSlot` for Conditioned or ejected samples. Exact sample properties are preserved.

- **Returns** `OutputSlot` for Conditioned or ejected samples with exact properties.

### Methods

##### `self.report() → dict[str, JsonValue]`

The loaded fragment's full condition report, `self.report()` returns `{property: value}` for all 10 properties (`glow`, `brightness`, `smell`, `gunk`, `cracks`, `feel`, `twitch`, `bugs`, `weight`, `sound`). Read the whole thing: the combo rules need siblings (brightness reads glow, weight reads gunk, sound reads cracks). Word properties are strings, numbers are numbers. `{}` if nothing is loaded. Iterate with `.items()` or index `report["gunk"]`.

- **Returns** A dict of all ten condition properties for the loaded fragment, or `{}` when empty. Word values are strings and numeric values are numbers. Read the full report because brightness uses glow, weight uses gunk, and sound uses cracks.

##### `self.properties() → list[str]`

Lists the ten property ids in their fixed inspection order, from `"glow"` through `"sound"`. The order is the same for every Deep fragment, making it suitable for a general inspection loop.

- **Returns** List of the 10 property ids in their fixed order (`glow`, `brightness`, … `sound`). The inspection rubric is the same for every Deep fragment.

##### `self.fragment() → str | None`

The raw deep fragment id loaded in the chamber, `self.fragment()`, or `None` if empty.

- **Returns** The raw Deep fragment id currently loaded in the chamber (from `load`), or `None` if empty.
- **Possible values** `"gw_spinal_vertebra"`, `"vc_eye_stalk"`, `"oc_lens_eye"`, `"bw_tail_spike"`, `"vd_tendril"`, `"mh_stigmatic_disc"`, `"hs_compound_eye"`, `"ms_eye_cluster"`, `"hc_tentacle_crown"`, `"ma_luminous_ring"`, `"gm_antennal_whip"`, `"fs_holdfast_rootlet"`, `"sd_talon"`, `"ce_cephalic_photophore"`, `"st_carapace_neural"`, `"vm_ventral_photophore"`

##### `self.stage() → int`

The current QC stage, `self.stage()` returns **1-5** while a run is live, or **0** when none is active (nothing loaded, or the run just resolved). Each stage quizzes one property.

- **Returns** The current QC stage, **1-5** while a run is live, or **0** when no run is active (nothing loaded, or the run just resolved). Each stage quizzes one property.

##### `self.current() → str | None`

The property this stage is quizzing, `self.current()` returns one of the 10 ids (look its value up in `report()`, apply its rule, then `accept()`/`reject()`), or `None` if no run is active. You can't predict which 5 of the 10 come up, so encode every rule.

- **Returns** The property id this stage is quizzing (one of the 10): look its value up in `report()`, apply its rule, then `accept()` or `reject()`. `None` if no run is active. You can't predict which 5 of the 10 you'll be quizzed on, so know every rule.
- **Possible values** `"glow"`, `"brightness"`, `"smell"`, `"gunk"`, `"cracks"`, `"feel"`, `"twitch"`, `"bugs"`, `"weight"`, `"sound"`

##### `self.lights() → list[str]`

The 5 stage results so far, `self.lights()` returns a list of `"green"` (correct call), `"red"` (a miss, run over), and `"pending"` (not reached). They light one at a time as you answer.

- **Returns** List of the 5 stage results so far: `"green"` (a correct call), `"red"` (a miss: the run is over), or `"pending"` (not reached yet). Lights up one at a time as you answer.

##### `self.is_running() → bool`

`True` while a 5-stage run is live (a fragment is loaded with stages left), `self.is_running()`. Drive the gauntlet with `while cond.is_running(): prop = cond.current(); ...`. Goes `False` when the run finishes, burns, or nothing is loaded.

- **Returns** `True` while a 5-stage run is in progress (a fragment is loaded and stages remain). Loop on it: `while cond.is_running(): ...`. Goes `False` when the run finishes, burns, or nothing is loaded.

##### `self.load(fragment_id: str, properties: ItemProperties | None = None, property_match: str | None = None) → ActionResult` *(self only)*

Pull one raw deep sample from `self.input` into the chamber and start a fresh 5-stage run. Optional `properties` and `property_match` select a specific identity using the standard any, subset, or exact convention.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `fragment_id` | `str` | A raw Deep fragment id staged in `self.input`. |
| `properties` | `ItemProperties \| None` | Optional property dict, matched as a subset by default. Omitted or `None` matches any properties; use `None` with `property_match="exact"` to select propertyless items only. |
| `property_match` | `str \| None` | Optional selection mode: any, subset, or exact |

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

##### `self.eject() → ActionResult` *(self only)*

Stage the unchanged chamber sample in `self.output` and end the run.

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

##### `self.accept() → ActionResult` *(self only)*

Stamp the current property as passing.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The decision matched the rule book for this stage. The specimen remains in the chamber and the inspection advances to the next property. |
| `"conditioned"` | success | The decision matched the rule book on the final stage, so the inspection passed and the Conditioned fragment was delivered to the output. |
| `"burned"` | success | An incorrect conditioning decision burned the specimen and emptied the chamber. |
| `"no_run"` | rejection | There is no active run. |
| `"busy"` | transient | The component is already performing another operation. |
| `"output_full"` | rejection | The output has no capacity for the result. |

##### `self.reject() → ActionResult` *(self only)*

Stamp the current property as damaged.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The decision matched the rule book for this stage. The specimen remains in the chamber and the inspection advances to the next property. |
| `"conditioned"` | success | The decision matched the rule book on the final stage, so the inspection passed and the Conditioned fragment was delivered to the output. |
| `"burned"` | success | An incorrect conditioning decision burned the specimen and emptied the chamber. |
| `"no_run"` | rejection | There is no active run. |
| `"busy"` | transient | The component is already performing another operation. |
| `"output_full"` | rejection | The output has no capacity for the result. |

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Terraforming*
