# Component: water_pump

> **Category:** Infrastructure & Fluids | **Component Name:** Water Pump

Extracts water from a surveyed well at a throttle your script sets. Its Planet Map blueprint can be placed in Plan Mode or by script; a Pioneer must still build it on the well.

| Field | Value |
| --- | --- |
| Type | Fluids |
| Built on | Water wells |
| Power in | -4 W (draws from grid) |
| Produces | Water, buffer 10 t |
| Output buffer | 20 units |

### How to obtain

1. The recipe unlocks with the **Hydrology Survey** research (Pressure 30).
2. Fabricate a **Water Pump** on a **Fabricator**: 2× Iron Ingot, 2× Glass, and 4× Liquid Pipe Segment.
3. Build it on a surveyed water well with a Pioneer's Constructor.

**Returned by:** `self / get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

##### `.output: PickupOutputSlot`

`PickupOutputSlot` holding salt created as a water-pumping byproduct. This is separate from `water_out`, which carries water through Liquid Pipes. Read `count()`, `capacity()`, or `stacks()` to inspect it. A physically present Rover or Pioneer connects its own input and pulls salt; the Pump has no direct item-routing methods.

- **Returns** `PickupOutputSlot` holding the discrete salt byproduct for a physically present Rover or Pioneer.

##### `.water_out: FluidPort`

Fluid output for water. This port may declare one destination with `self.water_out.connect("bio_caster_1")`; additional consumers may connect their own `water_in` ports to this Pump. Because the Pump is a field structure, every destination needs a completed Liquid Pipe route reaching the Pump and destination. `connected_to()` reports only this output port's declaration; `flow_rate()` reports total live delivery. The Pump stores nothing, so `level()` reads **0**. See `FluidPort`.

- **Returns** `FluidPort` routing water to a connected target. Call `connect(...)` with the target's stable machine id or display name, then open `set_throttle(...)`. Completed liquid-pipe networks carry water between outposts.

### Methods

##### `.well() → WaterWell`

The `WaterWell` this pump is bolted to. Read `.yield_tier()` to see whether the well is `"standard"` / `"rich"` / `"pure"` (1×/2×/3× multiplier) and `.flow_rate()` for the well's per-hour output. Useful for prioritization scripts that compare yields across the fleet.

- **Returns** `WaterWell` snapshot for the well this pump is on: `.id`, `position()`, `yield_tier()`, `flow_rate()`.

##### `.pump_rate() → float`

Total water delivered to connected destinations this tick, in t/h. Reads **0** when throttle is **0** or no destination can accept flow. If a productive well still reports 0, check the connections, completed pipe routes, conflicts, power, and destination capacity.

- **Returns** Number: total water delivered across every reachable connected destination this tick, in t/h. **0** when throttle is **0** or no destination can accept flow.

##### `.is_stalled() → bool`

`True` if, on the last flow tick, the powered pump had an open throttle and water available from its well but could transfer none across its connected routes. No available water, a closed throttle, or lack of power does not report a stall. Declare a destination with `self.water_out.connect(...)`, or let consumers connect their own `water_in` ports to this Pump.

- **Returns** `True` if, on the last flow tick, the powered pump had `throttle > 0` and water available from its well but could transfer none across its connected routes. `False` when unpowered, the throttle is closed, or no water is available to pump.

##### `.throttle() → float`

Current throttle setting (**0-1**). **0** by default, the pump idles until a script calls `set_throttle()`.

- **Returns** Number (**0-1**): current throttle setting.

##### `.set_throttle(rate: float) → ActionResult` *(self only)*

Set the pump's total output rate (**0-1**) across reachable connected destinations. **0** idles the pump (no extraction, no draw); **1** allows full well output subject to headroom and throughput. This script-owned setpoint resets to **0** when the script stops, ends, or errors, so keep the control loop running while the Pump should operate.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `rate` | `float` | Throttle setting (**0-1**). Default **0**: pump idles until scripted. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Biosphere*
