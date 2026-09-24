# Component: waste_processor

> **Category:** Production & Storage | **Component Name:** Waste Processor

Permanently destroys one script-selected waste stream: items, liquids, or gases. Use the item input for unwanted stock, `liquid_in` for surplus water or other liquids, and `gas_in` for gases. It destroys only while the script that armed it is still running. It has no output and recovers no value.

| Field | Value |
| --- | --- |
| Type | Mining |
| Power in | Variable (draws from grid) |
| Stockpile | 200 units (mixed) |

### How to obtain

1. The recipe unlocks with the **Waste Processing** research (Oxygen 1,400).
2. Fabricate a **Waste Processor Kit** on a **Fabricator**: 2× Machine Frame, 4× Iron Ingot, and 1× Circuit Panel.
3. Deploy it from your Inventory.

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

Stage unwanted items for permanent destruction. Connect a storage bin or machine buffer with `self.input.connect(name)`, then pull items with `self.input.take(item_id, count)`. Item transfers are explicit, so they may be staged while another mode is selected; only enabled `"items"` mode destroys them. See `InputSlot`.

- **Returns** `InputSlot`: `connect()`, `take()`, `eject()`, `flush()`, `count()`, `capacity()`, `connected_to()`. Route any item here from a storage bin or machine byproduct bin. The input accepts **any** item in every mode; only enabled `"items"` mode destroys it. Disable destruction before recovering a mistaken load with `eject(...)`.

##### `.liquid_in: FluidPort`

Generic **120 t** liquid input buffer. Connect a liquid source, select `"liquid"`, and enable the processor. A non-empty buffer accepts only its currently latched liquid until it drains. See `FluidPort`.

- **Returns** Generic **120 t** `FluidPort` input for any liquid. It accepts flow only while the processor is enabled in `"liquid"` mode. A non-empty buffer remains latched to one exact liquid until drained.

##### `.gas_in: FluidPort`

Generic **120 t** gas input buffer. Connect a gas source, select `"gas"`, and enable the processor. A non-empty buffer accepts only its currently latched gas until it drains. See `FluidPort`.

- **Returns** Generic **120 t** `FluidPort` input for any gas. It accepts flow only while the processor is enabled in `"gas"` mode. A non-empty buffer remains latched to one exact gas until drained.

### Methods

##### `.set_enabled(enabled: bool) → ActionResult` *(self only)*

Arm or pause destruction in the selected mode. The processor destroys only while the script that armed it keeps running: when that script stops, completes, or errors, this setpoint returns to off and `status()` reads `"disabled"`. A Smelter keeps working from its committed recipe, this machine does not. Staged items and fluids remain intact.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `enabled` | `bool` | `True` arms destruction in the selected mode. `False` stops destruction and rejects new fluid while preserving every staged buffer. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.is_enabled() → bool`

Read whether the processor is currently armed. The arm belongs to a running script, so it reads `False` again once that script ends.

- **Returns** `bool`

##### `.set_mode(mode: str) → ActionResult` *(self only)*

Select exactly one destruction stream: `"items"`, `"liquid"`, or `"gas"`. Changing modes pauses the other buffers without deleting them. The selected fluid port accepts flow only while enabled.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `mode` | `str` | Selected waste stream: `"items"`, `"liquid"`, or `"gas"`. Only that stream is destroyed. The selected fluid port accepts flow only while enabled; explicit item transfers may stage items in any mode. Other buffers pause without losing their contents. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

*Raises*

| Exception | Condition |
| --- | --- |
| `ValueError` | mode must be "items", "liquid", or "gas". |

##### `.mode() → str`

Read the selected waste stream.

- **Returns** Current selected stream: `"items"`, `"liquid"`, or `"gas"`.
- **Possible values** `"items"`, `"liquid"`, `"gas"`

##### `.status() → str`

Read the exact live state: `"disabled"`, `"no_power"`, `"idle"`, or `"processing"`. `"disabled"` means no running script has armed the processor, so staged waste waits untouched.

- **Returns** Current operating state: `"disabled"`, `"no_power"`, `"idle"`, or `"processing"`.
- **Possible values** `"disabled"`, `"no_power"`, `"idle"`, `"processing"`

##### `.throughput() → float`

Read the selected mode's current destruction rate. Item mode reports units/h; liquid and gas modes report t/h.

- **Returns** Number: current destruction rate for the selected mode. Item mode reports units/h; liquid and gas modes report t/h. **0** when the selected stream is not processing.

##### `.item_throughput() → float`

Read the current item destruction rate in units/h. At 100% outpost efficiency, the maximum is **60 units/h**.

- **Returns** Number: current whole-item destruction rate in units/h. At 100% outpost efficiency, the maximum is **60 units/h**. **0** unless item mode is powered, enabled, and has staged items.

##### `.liquid_throughput() → float`

Read the last liquid destruction rate in t/h. At 100% outpost efficiency, the maximum is **120 t/h**.

- **Returns** Number: liquid destroyed during the last processing tick, in t/h. At 100% outpost efficiency, the maximum is **120 t/h**.

##### `.gas_throughput() → float`

Read the last gas destruction rate in t/h. At 100% outpost efficiency, the maximum is **120 t/h**.

- **Returns** Number: gas destroyed during the last processing tick, in t/h. At 100% outpost efficiency, the maximum is **120 t/h**.

##### `.is_running() → bool`

Read whether the selected mode is currently processing staged material.

- **Returns** Boolean: `True` while the selected mode is processing staged material. Pure destruction has no output port and recovers no value.

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Vehicles & Modules*
