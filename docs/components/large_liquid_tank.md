# Component: large_liquid_tank

> **Category:** Infrastructure & Fluids | **Component Name:** Large Liquid Tank

A big passive tank holding 1,000 t of one liquid. Like a Liquid Tank it sticks to the first fluid piped in, and only lets go once it has drained completely.

| Field | Value |
| --- | --- |
| Type | Fluids |
| Storage | Any liquid, 1,000 t |

### How to obtain

1. Requires the **Large Liquid Tank** research (Plants 900,000).
2. Buy from the Shop for 15,000 cr.

**Returned by:** `get_component(id)`

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

##### `.liquid_in`

The latched liquid id (e.g. `"water"`, `"oil"`, `"frozen_essence"`), or `""` while empty. The tank commits to the first liquid it receives and holds only that until it drains to **0**, then re-latches.

- **Returns** Neutral generic `FluidPort` input while empty. Call `connect(...)` with the provider's stable machine id or display name; the first exact liquid delivered latches the reservoir.

##### `.liquid_out`

The latched liquid id (e.g. `"water"`, `"oil"`, `"frozen_essence"`), or `""` while empty. The tank commits to the first liquid it receives and holds only that until it drains to **0**, then re-latches.

- **Returns** Generic `FluidPort` output for the reservoir's latched liquid.

##### `.water_in`

The latched liquid id (e.g. `"water"`, `"oil"`, `"frozen_essence"`), or `""` while empty. The tank commits to the first liquid it receives and holds only that until it drains to **0**, then re-latches.

- **Returns** `FluidPort` input for the tank's exact latched liquid. This property exists only while `fluid()` is `"water"`.

##### `.water_out`

The latched liquid id (e.g. `"water"`, `"oil"`, `"frozen_essence"`), or `""` while empty. The tank commits to the first liquid it receives and holds only that until it drains to **0**, then re-latches.

- **Returns** `FluidPort` output for the tank's exact latched liquid. This property exists only while `fluid()` is `"water"`.

### Methods

##### `.fluid()`

The latched liquid id (e.g. `"water"`, `"oil"`, `"frozen_essence"`), or `""` while empty. The tank commits to the first liquid it receives and holds only that until it drains to **0**, then re-latches.

- **Returns** String: the latched liquid id, or `""` while empty/unlatched.
- **Possible values** `""`, `"water"`, `"oil"`, `"frozen_essence"`, `"coastal_essence"`, `"geothermal_essence"`, `"volcanic_essence"`, `"deep_essence"`, `"brine"`, `"raw_cryofluid"`, `"cryofluid"`, `"raw_quicksilver"`, `"quicksilver"`

##### `.level()`

Current liquid stored in tons, from **0** to `capacity()`. At **0** the tank unlatches and can accept a different liquid next.

- **Returns** Number: current liquid stored in tons.

##### `.capacity()`

Maximum tons this tank holds. Queryable rather than hardcoded. Use with `level()` or `fill_pct()` for threshold checks.

- **Returns** Number: maximum capacity in tons.

##### `.fill_pct()`

Fill fraction (**0.0-1.0**), shortcut for `level() / capacity()`. Common threshold in supply-control scripts.

- **Returns** Number (**0-1**).

##### `.inflow_rate()`

Liquid arriving in t/h. **0** = no upstream flow.

- **Returns** Number: liquid arriving in t/h.

##### `.outflow_rate()`

Liquid leaving in t/h. **0** = no downstream consumer drawing.

- **Returns** Number: liquid leaving in t/h.

##### `.is_full()`

`True` when `level() == capacity()`; upstream source is backpressured.

- **Returns** Boolean.

##### `.is_empty()`

`True` when `level() == 0`; the tank is unlatched and downstream consumers are starved.

- **Returns** Boolean.

*Components / Infrastructure & Fluids*
