# Component: gas_tank

> **Category:** Infrastructure & Fluids | **Component Name:** Gas Tank

A passive buffer that latches onto the first gas piped in (steam, ammonia, swamp gas) and holds only that until it drains. Sitting between a source and its consumer, it smooths out the gaps in supply.

| Field | Value |
| --- | --- |
| Type | Fluids |
| Storage | Any gas, 5,000 t |

### How to obtain

1. Requires the **Gas Tank** research (Pressure 2.75).
2. Buy from the Shop for 1,200 cr.

**Returned by:** `get_component(id)`

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

##### `.gas_in: FluidPort`

The latched gas id (e.g. `"steam"`, `"ammonia"`), or `""` while empty. The tank commits to the first gas it receives and holds only that until it drains to **0**, then re-latches.

- **Returns** Neutral generic `FluidPort` input while empty. Call `connect(...)` with the provider's stable machine id or display name; the first exact gas delivered latches the tank.

##### `.gas_out: FluidPort`

The latched gas id (e.g. `"steam"`, `"ammonia"`), or `""` while empty. The tank commits to the first gas it receives and holds only that until it drains to **0**, then re-latches.

- **Returns** Generic `FluidPort` output. It remains neutral while empty and provides the tank's latched exact gas to connected consumers.

##### `.steam_in: FluidPort`

The latched gas id (e.g. `"steam"`, `"ammonia"`), or `""` while empty. The tank commits to the first gas it receives and holds only that until it drains to **0**, then re-latches.

- **Returns** `FluidPort` input for the tank's exact latched gas. This property exists only while `fluid()` is `"steam"`.

##### `.steam_out: FluidPort`

The latched gas id (e.g. `"steam"`, `"ammonia"`), or `""` while empty. The tank commits to the first gas it receives and holds only that until it drains to **0**, then re-latches.

- **Returns** `FluidPort` output for the tank's exact latched gas. This property exists only while `fluid()` is `"steam"`.

### Methods

##### `.fluid() → str`

The latched gas id (e.g. `"steam"`, `"ammonia"`), or `""` while empty. The tank commits to the first gas it receives and holds only that until it drains to **0**, then re-latches.

- **Returns** String: the latched gas id (e.g. `"steam"`, `"ammonia"`), or `""` while empty/unlatched.
- **Possible values** `""`, `"steam"`, `"ammonia"`, `"swamp_gas"`, `"raw_sulfur_gas"`, `"sulfur_gas"`, `"raw_chlorine"`, `"chlorine"`

##### `.level() → float`

Current gas stored in tons, from **0** to `capacity()`. Read each iteration to gauge the buffer, near **0** means downstream is about to starve; near `capacity()` means upstream is backpressured. At **0** the tank unlatches and can accept a different gas next.

- **Returns** Number: current gas stored in tons.

##### `.capacity() → float`

Maximum tons of gas this tank holds, queryable rather than hardcoded so tank tuning doesn't break scripts. Use with `level()` for a fill-percent indicator, or directly via `fill_pct()`.

- **Returns** Number: maximum gas capacity in tons.

##### `.fill_pct() → float`

Fill fraction (**0.0-1.0**), shortcut for `level() / capacity()`. Use for threshold checks: `if self.fill_pct() < 0.2: # boost throttle upstream`.

- **Returns** Number (**0-1**).

##### `.inflow_rate() → float`

Gas arriving in t/h. **0** means no upstream flow, for example a dormant source, unavailable relationship, incomplete remote route, or full tank. Compare to `outflow_rate()` to see if the tank is filling or draining.

- **Returns** Number: gas arriving in t/h.

##### `.outflow_rate() → float`

Gas leaving in t/h. **0** means downstream consumer is saturated or the pipe is disconnected.

- **Returns** Number: gas leaving in t/h.

##### `.is_full() → bool`

`True` when `level() == capacity()`, upstream backpressure is kicking in, and a Cap may start venting to atmosphere. Check it to detect when connected destinations cannot absorb current production.

- **Returns** Boolean.

##### `.is_empty() → bool`

`True` when `level() == 0`; the tank is unlatched and nothing can be sent downstream. If the source is still active while the tank remains empty, inspect the source and its pipe connection.

- **Returns** Boolean.

*Components / Infrastructure & Fluids*
