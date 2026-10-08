# Component: bio_luminizer

> **Category:** Terraforming | **Component Name:** Bio Luminizer

Tints a coastal fragment's glow to a target color using three built-in colored lamps. The lamps bleed into each other, so a script solves the brightness mix that lands on the exact target.

| Field | Value |
| --- | --- |
| Type | Atmosphere |
| Power in | -12 W (draws from grid) |
| Input buffer | Units: 10 |
| Output buffer | Units: 10 |

### How to obtain

1. Requires the **Bioluminescent Infusion** research (Temperature 90).
2. Buy from the Shop for 60,000 cr.

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

##### `self.chamber: ChamberSample | None`

The `ChamberSample` loaded right now, exposed as `self.chamber`, or `None`. Read `.glow` for its starting color and `.fragment_id` for its item id.

- **Returns** `ChamberSample | None`. `None` if the chamber is empty.

##### `self.input: InputSlot`

The `InputSlot` for raw coastal samples. It holds one sample item id at a time and stays latched to that id until `load()` consumes the remaining units or `flush()` discards them. `stacks()` lists property-distinct variants and does not mean the port accepts multiple sample types. Inventory is a source only at Nocturna Base; remote Luminizers use a same-outpost Storage Bin/Warehouse.

- **Returns** `InputSlot`. For raw coastal samples. Recover a mistaken property variant to an explicit local destination with `eject(...)` before loading it into the chamber.

##### `self.output: OutputSlot`

The `OutputSlot` for Luminous or ejected samples. Exact sample properties are preserved.

- **Returns** `OutputSlot`. For Luminous or ejected samples, preserving exact properties.

### Methods

##### `self.load(fragment_id: str, properties: ItemProperties | None = None, property_match: str | None = None) → ActionResult` *(self only)*

Pull a raw glowing coastal sample of `fragment_id` from `self.input` into the chamber, `self.load("gw_caudal_fin")`. Optional `properties` and `property_match` select a specific identity using the standard `any`, `subset`, or `exact` convention. Read its start color with `self.chamber.glow`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `fragment_id` | `str` | A coastal fragment id staged in `self.input`. |
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

##### `self.lamp_signature(channel: str) → list[int] | None`

The RGB-per-unit `[r,g,b]` a lamp adds per brightness step, its impurity. `self.lamp_signature("red")` is roughly `[6, 1, 1]`: mostly red, but it bleeds a little into green and blue. Read all three (`"red"`, `"green"`, `"blue"`) to build the 3×3 you invert. Fixed hardware, read once and reuse. `None` for an unknown channel.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `channel` | `str` | Lamp channel: `"red"`, `"green"`, or `"blue"`. |

- **Returns** `list[int] | None`. The lamp's RGB-per-unit `[r,g,b]` (its impurity) for `channel` `"red"` / `"green"` / `"blue"`, or `None` for an unknown channel. Fixed hardware: read once and reuse.

##### `self.glow() → list[int] | None`

The chamber's **current** resulting glow `[r,g,b]` given the lamps set right now, it reflects `set_lamps(...)` immediately, so use it to verify your solve before committing: `if self.glow() == target: self.infuse()`. `None` when the chamber is empty.

- **Returns** `list[int] | None`. The chamber's **current** resulting glow `[r,g,b]` given the lamps set right now (reflects `set_lamps` immediately), or `None` if the chamber is empty. Compare against the order's `target_glow` before `infuse()`.

##### `self.set_lamps(r: int, g: int, b: int) → ActionResult` *(self only)*

Set the three lamp brightnesses, `self.set_lamps(7, 13, 4)`. Each is a **whole number 0-40**; the exact answer is always an integer, so `round()` your computed values. Fractional or out-of-range values raise an argument error (not silently floored). Re-idles to 0 when the script stops.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `r` | `int` | Red lamp intensity. |
| `g` | `int` | Green lamp intensity. |
| `b` | `int` | Blue lamp intensity. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"busy"` | transient | The component is already performing another operation. |
| `"output_full"` | rejection | Finished work is waiting for space in this machine's output, so nothing else can start. Free the output and the wait ends on its own. |

##### `self.infuse() → ActionResult` *(self only)*

Produce a **Luminous** sample in `self.output`, preserving its other properties and replacing its previous glow with the tuned glow.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"output_full"` | rejection | The output has no capacity for the result. |
| `"empty"` | rejection | The relevant source or queue is empty. |
| `"busy"` | transient | The component is already performing another operation. |

##### `self.discard() → ActionResult` *(self only)*

Stage the unchanged chamber sample in `self.output`.

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
