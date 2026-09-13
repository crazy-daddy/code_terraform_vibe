# Component: thermal_cap

> **Category:** Infrastructure & Fluids | **Component Name:** Thermal Cap

Captures Steam from a thermal vent. If its chamber reaches 100%, every stored ton blows into the atmosphere; a script must release, route, or relieve pressure.

| Field | Value |
| --- | --- |
| Type | Fluids |
| Built on | Thermal vents |
| Power in | -3 W (draws from grid) |
| Produces | Steam, buffer 1,000 t |

### How to obtain

1. The recipe unlocks with the **Thermal Cap** research (Pressure 2.5).
2. Fabricate a **Thermal Cap Kit** on a **Fabricator**: 2× Titanium Ingot and 2× Gas Pipe Segment.
3. Build it on a surveyed thermal vent with a Pioneer's Constructor.

**Returned by:** `self / get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

##### `.steam_out`

Fluid output for the chamber's steam. This port may declare one destination with `self.steam_out.connect("bio_caster_1")`; additional consumers may connect their own `steam_in` ports to this Cap. Because the Cap is a field structure, every destination needs a compatible completed Gas Pipe component reaching the Cap and the destination. `connected_to()` reports only this output port's own declaration; `flow_rate()` reports total live release. See `FluidPort`.

- **Returns** `FluidPort` for chamber steam. This port may declare one destination with `connect("bio_caster_1")`; additional consumers may connect their own `steam_in` ports to the Cap. Completed gas-pipe networks carry steam between outposts.

### Methods

##### `.vent()`

The `ThermalVent` this cap sits on. Field availability follows the sonar tier that last surveyed the vent: basic reveals phase, wide adds steam rates, deep adds cycle timing. Use `self.vent().current_phase()` (or the cap's own `phase()`) to know when steam is coming. See `ThermalVent`.

- **Returns** `ThermalVent` for the vent this cap sits on. Read `current_phase()` / `next_phase_in()` / rates off it, or use the cap's own `phase()` / `next_phase_in()`.

##### `.phase()`

`"active"` while the vent produces steam (your chamber fills) or `"dormant"` while it rests (the chamber only drains). `None` until the vent is surveyed. Drive your release loop off this: open the throttle when active, ease it when dormant so you do not run downstream dry.

- **Returns** `"active"` while the vent produces steam (chamber fills), `"dormant"` while it rests. `None` until the vent is surveyed. Ease the throttle in dormancy so you do not run downstream dry.
- **Possible values** `"active"`, `"dormant"`

##### `.next_phase_in()`

Game-minutes until the vent flips between active and dormant, so you can open up before a surge or ease off before a dry spell. Returns `None` unless the vent was **Deep**-surveyed, so a predictive loop is the payoff for deep sonar.

- **Returns** Game-minutes until the vent flips phase, to pre-empt a surge or a dry spell. `None` unless the vent was Deep-surveyed.

##### `.pressure()`

Chamber fill in the `0.0 to 1.0` range. It climbs while the cap captures steam from the vent and drops as you release through `steam_out`. Hit `1.0` and the cap **overpressurizes**: the whole chamber blows off to atmosphere and rebuilds from empty. The job is keeping this off the ceiling, so poll it every tick and open the throttle as it rises.

- **Returns** Chamber fill in the `0.0 to 1.0` range. Climbs as the vent captures, drops as you release. At `1.0` it overpressurizes: the whole chamber blows off to atmosphere and refills from empty. Keep it off the ceiling.

##### `.capture_rate()`

Steam captured from the vent on the last tick, in t/h. **0** during the dormant phase, up to the vent's current output while active. Already factors in the vent's phase, so read it instead of computing from the vent rate. Updates once per flow tick.

- **Returns** Steam captured from the vent this tick, t/h. `0` while the vent is dormant.

##### `.is_overpressured()`

`True` the tick the chamber tops out and blows its whole contents to atmosphere. After that the chamber is empty and must refill from the vent before you get steam again, so everything you had banked is gone. If you see this, you released too slowly, open the throttle sooner.

- **Returns** `True` the tick the chamber tops out and blows off to atmosphere. You then rebuild from empty, losing everything banked. Release sooner next time.

##### `.is_stalled()`

`True` if, on the last flow tick, the powered cap had an open throttle and chamber steam available for release but could transfer none across its connected routes. An empty chamber, closed throttle, or lack of power does not report a stall. Declare a destination with `self.steam_out.connect(...)`, or let consumers connect their own `steam_in` ports to this Cap.

- **Returns** `True` if, on the last flow tick, the powered cap had `throttle > 0` and chamber steam available for release but could transfer none across its connected routes. `False` when unpowered, the throttle is closed, or the chamber has no steam to release.

##### `.throttle()`

The current release-valve setting, `0.0` (sealed) to `1.0` (wide open). Read it back after `set_throttle(...)`.

- **Returns** Current release-valve setting in the `0.0 to 1.0` range.

##### `.set_throttle(t)` *(self only)*

Open the cap's release valve in the `0.0 to 1.0` range (clamped). `0` seals the chamber so it fills; `1.0` releases steam across all reachable connected destinations as fast as chamber supply, destination headroom, and throughput allow. Your primary knob against overpressure, so call it every tick against `pressure()`. This script-owned setpoint resets to `0` when the script stops, ends, or errors. If no destination can accept enough and `pressure()` still climbs, use `set_relief(...)` to shed the surplus. `[self only]`

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

##### `.relief()`

The current relief-valve setting, `0.0` (shut) to `1.0` (wide open). Read it back after `set_relief(...)`.

- **Returns** Current relief-valve setting in the `0.0 to 1.0` range: how wide the atmosphere overflow is open.

##### `.relief_rate()`

Steam wasted to atmosphere through the relief valve this tick, in t/h. `0` when the relief valve is shut. Watch it to see how much surplus you're dumping.

- **Returns** Steam wasted to atmosphere through the relief valve this tick, t/h. `0` when the valve is shut.

##### `.set_relief(t)` *(self only)*

Open the relief valve from **0-1** to dump excess chamber steam into the atmosphere. Use it when connected consumers cannot keep up and `pressure()` is still climbing. `0` keeps all steam available for consumers. Values outside the range are clamped. Call this only from the Thermal Cap's own script.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `t` | `number` | Relief-valve fraction in the **0-1** range |

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
