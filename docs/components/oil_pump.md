# Component: oil_pump

> **Category:** Infrastructure & Fluids | **Component Name:** Oil Pump

Extracts oil from a surveyed well at a throttle your script sets. Oil wells run in active and dormant phases, so buffer the output through a Liquid Tank to ride out the dry spells.

| Field | Value |
| --- | --- |
| Type | Fluids |
| Built on | Oil wells |
| Power in | -5 W (draws from grid) |
| Produces | Oil, buffer 10 t |

### How to obtain

1. The recipe unlocks with the **Petroleum Survey** research (Oxygen 1,500).
2. Fabricate a **Oil Pump** on a **Fabricator**: 2× Iron Ingot, 1× Titanium Ingot, 1× Pressure Valve, and 1× Circuit Panel.
3. Build it on a surveyed oil well with a Pioneer's Constructor.

**Returned by:** `self / get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

##### `.oil_out`

Fluid output for oil. This port may declare one destination with `self.oil_out.connect("Oil Reserve")`; additional consumers may connect their own `oil_in` ports to this Pump. Because the Pump is a field structure, every destination needs a compatible completed Liquid Pipe component reaching the Pump and the destination. `connected_to()` reports only this output port's declaration; `flow_rate()` reports total live delivery. The Pump stores nothing, so `level()` reads **0**. See `FluidPort`.

- **Returns** `FluidPort` routing oil to a connected target. Call `connect(...)` with the target's stable machine id or display name, then open `set_throttle(...)`. Completed liquid-pipe networks carry oil between outposts.

### Methods

##### `.well()`

The `OilWell` this pump is bolted to. Same shape as `WaterWell`, yield tier (1×/2×/3×) and base flow rate.

- **Returns** `OilWell` snapshot for the well this pump is on: `.id`, `position()`, `yield_tier()`, `flow_rate()`.

##### `.pump_rate()`

Total oil delivered across every reachable connected destination this tick, in t/h. **0** when throttle is **0**, the well is dormant, or no destination can accept flow. See `is_stalled()` to tell a routing block from a dormant well.

- **Returns** Number: total oil delivered across every reachable connected destination this tick, in t/h. **0** when throttle is **0**, the well is dormant, or no destination can accept flow.

##### `.well_active()`

Reads the well's pulse. `True`, the well below is in its active phase and delivers at full rate. `False`, dormant: no oil at any throttle, typically for several hours. Bank oil in a downstream Liquid Tank and throttle down during the gap to save watts.

- **Returns** Boolean: `True` while the well below is in its active phase. Dormant wells deliver nothing at any throttle: bank oil in a downstream Liquid Tank to ride the gap.

##### `.is_stalled()`

`True` if, on the last flow tick, the powered pump had an open throttle and oil available from its active well but could transfer none across its connected routes. Dormancy, a closed throttle, or lack of power does not report a stall. Declare a destination with `self.oil_out.connect(...)`, or let consumers connect their own `oil_in` ports to this Pump.

- **Returns** `True` if, on the last flow tick, the powered pump had `throttle > 0` and oil available from its active well but could transfer none across its connected routes. `False` when unpowered, the throttle is closed, or the well supplies no oil, including during dormancy.

##### `.throttle()`

Current throttle setting (**0-1**). **0** by default.

- **Returns** Number (**0-1**).

##### `.set_throttle(rate)` *(self only)*

Set the pump's total output rate (**0-1**) across reachable connected destinations. `0` idles the pump; `1` allows full active-well output subject to headroom and throughput. This script-owned setpoint resets to `0` when the script stops, ends, or errors, so keep the control loop running while the Pump should operate.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `rate` | `number` | Throttle setting (**0-1**). |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Infrastructure & Fluids*
