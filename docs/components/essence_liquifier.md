# Component: essence_liquifier

> **Category:** Biosphere | **Component Name:** Essence Liquifier

Renders native life-form samples down into their biome's essence fluid. It only accepts life forms from its own outpost's biome, and produces that biome's essence.

| Field | Value |
| --- | --- |
| Type | Biosphere |
| Power in | Variable (draws from grid) |
| Produces | One biome-matched port: Frozen Essence, Coastal Essence, Geothermal Essence, Volcanic Essence, and Deep Essence, buffer 50 t |
| Input buffer | 50 units |

### How to obtain

1. Requires the **Biosphere** research (Terraform Index 210,000).
2. Buy from the Shop for 35,000 cr.

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

The input slot for life-form samples native to this outpost's biome. Machine and storage sources must share the outpost. Inventory works only at home; remote Liquifiers receive samples from local storage. A wrong-biome sample is rejected without being moved.

- **Returns** `InputSlot` for life-form samples native to this outpost's biome. Wrong-biome samples are rejected without being moved; `eject(...)` recovers staged samples to an explicit local destination.

##### `.frozen_essence_out: FluidPort`

This machine has exactly one essence output, named for its outpost biome: `frozen_essence_out`, `coastal_essence_out`, `geothermal_essence_out`, `volcanic_essence_out`, or `deep_essence_out`. It is a `FluidPort`. Connect it to a local Liquid Tank or matching Mixer input. A remote peer relationship also needs a completed conflict-free Liquid Pipe route between both locations. Example: `self.frozen_essence_out.connect("liquid_tank_1")`.

- **Returns** `FluidPort` for Frozen essence. A Liquifier exposes only the port matching its outpost biome. Call `self.biome()` to confirm the port, then connect it like any fluid source: `self.frozen_essence_out.connect("liquid_tank_1")`.

### Methods

##### `.essence_rate() → float`

Current biome essence output, in **t/h**. At 100% outpost efficiency, the Essence Liquifier has a base **1 t/h** life-form intake. This readout applies both outpost efficiency and the loaded life form's rarity yield (common **×5**, uncommon **×10**, rare **×25**), and reads **0** when the machine cannot run or buffer its next whole output.

- **Returns** Number, current biome essence output in t/h.

##### `.yield_multiplier() → float`

Unscaled essence tons produced per ton of the life form currently in the input bin: **5** for a common life form, **10** uncommon, **25** rare. Returns **0** when the input is empty. At 100% outpost efficiency, `essence_rate()` equals this multiplier while the machine is powered, fed, and able to buffer its next whole output; overcrowding can reduce the actual output rate.

- **Returns** Number: essence tons produced per ton of the life form currently loaded (**5** common / **10** uncommon / **25** rare), or **0** when the input is empty.

##### `.is_stalled() → bool`

`True` whenever `stall_reason()` is not `"ok"`: no valid host biome, no input, or insufficient output room for the next whole rarity-scaled yield. Use `stall_reason()` for the specific cause.

- **Returns** Boolean. `True` whenever `stall_reason()` is not `"ok"`.

##### `.stall_reason() → str`

Why the Liquifier is idle, as a string you can branch on: `"no_biome"` (the machine has no valid host outpost), `"no_input"` (input bin empty, feed it native-biome life forms), `"output_full"` (the next whole rarity-scaled yield cannot fit and a configured output cannot drain right now), `"unconnected"` (the next whole yield cannot fit and the essence output has no effective peer relationship), or `"ok"` (running, ready, or able to buffer the next whole yield). More specific than `is_stalled()`.

- **Returns** String: one of `"ok"`, `"no_biome"`, `"no_input"`, `"output_full"`, `"unconnected"`. The specific reason the Liquifier is idle.
- **Possible values** `"ok"`, `"no_biome"`, `"no_input"`, `"output_full"`, `"unconnected"`

##### `.biome() → str | None`

Returns the biome the host outpost sits in: `"frozen"`, `"coastal"`, `"geothermal"`, `"volcanic"`, or `"deep"`. Returns `None` when the machine has no valid outpost. This determines which life-form items the Essence Liquifier will accept; wrong-biome items are rejected by the input port.

- **Returns** String: the biome the outpost sits in: `"frozen"`, `"coastal"`, `"geothermal"`, `"volcanic"`, or `"deep"`. `None` if the machine has no valid outpost. This determines which life-form items the Essence Liquifier accepts.
- **Possible values** `"frozen"`, `"coastal"`, `"geothermal"`, `"volcanic"`, `"deep"`

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Biosphere*
