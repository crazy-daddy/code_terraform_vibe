# Component: biomass_mixer

> **Category:** Biosphere | **Component Name:** Biomass Mixer

Blends biome essences into biomass. The global Biomass phase sets the minimum diversity, while every additional well-balanced essence can raise output. Mk II raises output 4.5× while essence demand rises only 2.4×, at five times the power draw.

| Field | Value |
| --- | --- |
| Type | Biosphere |
| Power in | Variable (draws from grid) |
| Consumes | Frozen Essence, buffer 30 t |
| Consumes | Coastal Essence, buffer 30 t |
| Consumes | Geothermal Essence, buffer 30 t |
| Consumes | Volcanic Essence, buffer 30 t |
| Consumes | Deep Essence, buffer 30 t |
| Tiers | Mk II |

### How to obtain

1. Requires the **Biosphere** research (Terraform Index 210,000).
2. Buy from the Shop for 60,000 cr.

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

##### `.frozen_essence_in`

Input port for Frozen Essence. Wire with `self.frozen_essence_in.connect(...)`. See `FluidPort`.

- **Returns** `FluidPort` for Frozen Essence input.

##### `.coastal_essence_in`

Input port for Coastal Essence. Wire with `self.coastal_essence_in.connect(...)`. See `FluidPort`.

- **Returns** `FluidPort` for Coastal Essence input.

##### `.geothermal_essence_in`

Input port for Geothermal Essence. Wire with `self.geothermal_essence_in.connect(...)`. See `FluidPort`.

- **Returns** `FluidPort` for Geothermal Essence input.

##### `.volcanic_essence_in`

Input port for Volcanic Essence. Wire with `self.volcanic_essence_in.connect(...)`. See `FluidPort`.

- **Returns** `FluidPort` for Volcanic Essence input.

##### `.deep_essence_in`

Input port for Deep Essence. Wire with `self.deep_essence_in.connect(...)`. See `FluidPort`.

- **Returns** `FluidPort` for Deep Essence input.

### Methods

##### `.biomass_rate()`

Biomass tons produced last tick, in **t/h**. Sum across every Biomass Mixer on the planet = total biomass production rate.

- **Returns** Number, biomass produced last tick in t/h.

##### `.active_essences()`

Number of essence input buffers currently carrying supply (**0-5**). The current phase decides the minimum required by `required_essences()`. Extra balanced essence types can increase output.

- **Returns** Number: count of essence input buffers that currently have supply (0-5).

##### `.mixing_essences()`

Number of supplied essence types selected for the strongest balanced mix on the last tick (**0-5**). The Mixer evaluates every diversity level from the phase minimum upward, so a weak extra feed can never reduce output.

- **Returns** Number (**0-5**), the count of supplied essence types selected for the strongest balanced mix last tick.

##### `.tier()`

Installed Mixer tier: **1** for Mk I or **2** for Mk II. Mk II produces **4.5×** biomass while consuming only **2.4×** as much of every selected essence, with **5×** power draw, so it yields **87.5%** more biomass per ton of essence.

- **Returns** Number, installed Mixer tier: **1** (Mk I) or **2** (Mk II).

##### `.is_stalled()`

`True` if the mixer is powered and fewer input buffers contain usable essence than the current Biomass phase requires. Buffered essence counts even without new inflow. `False` when unpowered or enough essence types are available. Connect each missing essence input to a compatible source and complete a remote Liquid Pipe route where needed; Biomass phases only advance and never drop.

- **Returns** Boolean: `True` if the mixer is powered and fewer input buffers contain usable essence than the current Biomass phase requires. Buffered essence counts even without new inflow. `False` when unpowered or enough essence types are available.

##### `.phase()`

The global Biomass phase (**1-6**), derived from cumulative biomass tons, using the same thresholds as the Sensors phase badge. The phase sets the minimum essence diversity but does not directly multiply output.

- **Returns** Number (**1-6**), the global Biomass phase derived from cumulative biomass tons. It sets the minimum required essence diversity.

##### `.required_essences()`

How many distinct biome essences must be supplied this phase (**1-5**, equal to the phase, capped at 5). Below this the Mixer stalls. Supplying more can raise output when the larger mix is balanced enough.

- **Returns** Number (**1-5**), the minimum distinct biome essences needed this phase. Extra balanced essences can raise output.

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Biosphere*
