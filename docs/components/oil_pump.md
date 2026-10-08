# Component: oil_pump

> **Category:** Infrastructure & Fluids | **Component Name:** Oil Pump

Extracts oil from a surveyed well at a throttle your script sets. Oil wells run in active and dormant phases, so buffer the output through a Liquid Tank to ride out the dry spells.

### Mk I

| Field | Value |
| --- | --- |
| Type | Fluids |
| Built on | Oil wells |
| Power in | Up to -5 W at full throttle (draws from grid) |
| Produces | Oil, buffer 10 t |
| Tiers | Mk II |

### Mk II

| Field | Value |
| --- | --- |
| Power in | Up to -100 W at full throttle (draws from grid) |

### How to obtain

1. The recipe unlocks with the **Petroleum Survey** research (Oxygen 1,500).
2. Fabricate **Oil Pump** on a **Fabricator**: 2× Iron Ingot, 1× Titanium Ingot, 1× Pressure Valve, and 1× Circuit Panel.
3. Build it on a surveyed oil well with a Pioneer's Constructor.

**Access via:** `self / get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id: str`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** `str`

##### `.name: str`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** `str`

##### `.oil_out: FluidPort`

Fluid output for oil. This port may declare one destination with `self.oil_out.connect("Oil Reserve")`; additional consumers may connect their own `oil_in` ports to this Pump. Because the Pump is a field structure, every destination needs a compatible completed Liquid Pipe component reaching the Pump and the destination. `connected_to()` reports only this output port's declaration; `flow_rate()` reports total live delivery. The Pump stores nothing, so `level()` reads **0**. See `FluidPort`.

- **Returns** `FluidPort`. Routes oil to a connected target. Call `connect(...)` with the target's stable machine id or display name, then open `set_throttle(...)`. Completed liquid-pipe networks carry oil between outposts.

### Methods

##### `.tier() → int`

Installed machinery tier: `1` for Mk I, `2` for Mk II, or `3` for Mk III where supported.

- **Returns** `int`

##### `.well() → OilWell`

The `OilWell` this pump is bolted to. Same shape as `WaterWell`, yield tier (1×/2×/3×) and base flow rate.

- **Returns** `OilWell`. A snapshot of the well this pump is on.

##### `.pump_rate() → float`

Total oil delivered across every reachable connected destination this tick, in t/h. **0** when throttle is **0**, the well is dormant, or no destination can accept flow. See `is_stalled()` to tell a routing block from a dormant well.

- **Returns** `float`. Total oil delivered across every reachable connected destination this tick, in t/h. **0** when throttle is **0**, the well is dormant, or no destination can accept flow.

##### `.well_active() → bool`

Reads the well's pulse. `True`, the well below is in its active phase and delivers at full rate. `False`, dormant: no oil at any throttle, typically for several hours. Bank oil in a downstream Liquid Tank and throttle down during the gap to save watts.

- **Returns** `bool`. `True` while the well below is in its active phase. Dormant wells deliver nothing at any throttle: bank oil in a downstream Liquid Tank to ride the gap.

##### `.is_stalled() → bool`

`True` if, on the last flow tick, the powered pump had an open throttle and oil available from its active well but could transfer none across its connected routes. Dormancy, a closed throttle, or lack of power does not report a stall. Declare a destination with `self.oil_out.connect(...)`, or let consumers connect their own `oil_in` ports to this Pump.

- **Returns** `bool`. `True` if, on the last flow tick, the powered pump had `throttle > 0` and oil available from its active well but could transfer none across its connected routes. `False` when unpowered, the throttle is closed, or the well supplies no oil, including during dormancy.

##### `.throttle() → float`

Current throttle setting (**0-1**). **0** by default.

- **Returns** `float`. The throttle setting (**0-1**).

##### `.set_throttle(rate: float) → ActionResult` *(self only)*

Set the pump's total output rate (**0-1**) across reachable connected destinations. `0` idles the pump; `1` allows full active-well output subject to headroom and throughput. This script-owned setpoint resets to `0` when the script stops, ends, or errors, so keep the control loop running while the Pump should operate.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `rate` | `float` | Throttle setting (**0-1**). |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

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

*Components / Infrastructure & Fluids*
