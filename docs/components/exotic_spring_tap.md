# Component: exotic_spring_tap

> **Category:** Infrastructure & Fluids | **Component Name:** Exotic Spring Tap

Captures liquid from a cyclic exotic spring during its active phase. Connect `self.liquid_out` to a consumer, build a completed Liquid Pipe route from the field Tap to that destination, then set a **0-1** release rate with `self.set_throttle(value)`. A full buffer pauses collection without losing liquid.

| Field | Value |
| --- | --- |
| Type | Fluids |
| Built on | Exotic deposits |
| Power in | -35 W (draws from grid) |

### How to obtain

1. The recipe unlocks with the **Exotic Husbandry** research (Wildlife 1,000).
2. Fabricate a **Exotic Spring Tap Kit** on a **Fabricator**: 2× Titanium Ingot, 2× Liquid Pipe Segment, and 1× Pressure Valve.
3. Build it on a surveyed exotic deposit with a Pioneer's Constructor.

**Returned by:** `self / get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

##### `.liquid_out`

Fluid output for the buffered liquid. This port may declare one destination with `self.liquid_out.connect("Cryofluid Tank")`; additional consumers may connect their own compatible input ports to this Tap. Because the Tap is a field structure, every destination needs a compatible completed Liquid Pipe component reaching the Tap and the destination. `connected_to()` reports only this port's own declaration; `flow_rate()` reports total live release. See `FluidPort`.

- **Returns** `FluidPort` for the deposit's liquid. This port may declare one destination with `self.liquid_out.connect("Cryofluid Tank")`; additional consumers may connect their own compatible inputs to the Tap. Completed liquid-pipe networks carry liquid between outposts.

### Methods

##### `.deposit()`

The `ExoticDeposit` this tap is bolted to, `.id`, `position()`, `fluid()`, `current_phase()`, cycle timing. Field availability is gated by the sonar tier that last surveyed the deposit (basic / wide / deep). `None` if the tap isn't on a deposit. Use `deposit.current_phase()` to check whether the source is active. See `ExoticDeposit`.

- **Returns** `ExoticDeposit` attached to this tap, or `None`. Its cycle, survey and collector methods read live state on each call: keep the object and call its methods for fresh readings. The `.surveyed` property remains a creation-time snapshot.

##### `.capture_rate()`

Exotic liquid captured from the spring on the last flow tick in t/h. **0** during the deposit's dormant phase, or when the buffer is full and holding (see `is_venting()`). Already factors in current phase and buffer headroom. Updates once per flow tick.

- **Returns** Number: exotic liquid captured from the spring this tick in t/h. **0** during the deposit's dormant phase, or when the buffer is full and holding (see `is_venting()`).

##### `.is_venting()`

`True` if active liquid production exceeded the capture buffer's available space on the last flow tick. The excess is held upstream without losing liquid. Dormancy returns `False` even with a full buffer, as does loss of power. This is a capture-space limit, unlike `is_stalled()`, which reports a blocked release. Open `self.set_throttle(...)` toward a tank with room.

- **Returns** Boolean: `True` if active liquid production exceeded the capture buffer's available space on the last flow tick. The excess is held upstream, not lost. `False` during dormancy even if the buffer is full, or when unpowered. Open `set_throttle(...)` to a tank with room.

##### `.is_stalled()`

`True` if, on the last flow tick, the powered tap had an open throttle and buffered liquid available for release but could transfer none across its connected routes. An empty buffer, closed throttle, or lack of power does not report a stall.

- **Returns** Boolean: `True` if, on the last flow tick, the powered tap had `throttle > 0` and buffered liquid available for release but could transfer none across its connected routes. `False` when unpowered, the throttle is closed, or the buffer has no liquid to release.

##### `.throttle()`

Current release-valve setting, `0.0` (holding) to `1.0` (wide open). Read it back after `set_throttle(...)`.

- **Returns** Number (**0-1**): current release-valve setting.

##### `.set_throttle(t)` *(self only)*

Open the tap's release valve in the `0.0 to 1.0` range (clamped). `0` holds the buffer; `1.0` releases liquid across reachable connected destinations as fast as buffer supply, headroom, and throughput allow. This script-owned setpoint resets to `0` when the script stops, ends, or errors. `[self only]`

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `t` | `number` | Release-valve fraction in the **0-1** range |

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
