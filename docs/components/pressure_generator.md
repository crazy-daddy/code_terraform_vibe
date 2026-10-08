# Component: pressure_generator

> **Category:** Terraforming | **Component Name:** Pressure Generator

Compresses the thin atmosphere to raise surface pressure. It runs best when a script catches each sync window as its gauge sweeps; missed windows cost efficiency.

### Mk I

| Field | Value |
| --- | --- |
| Type | Atmosphere |
| Power in | -7 W (draws from grid) |
| Produces | up to 0.012 kPa / day at peak efficiency |
| Input buffer | Units: 4 |
| Tiers | Mk II, Mk III, and Mk IV |

### Mk II

| Field | Value |
| --- | --- |
| Power in | -35 W (draws from grid) |
| Produces | up to 0.300 kPa / day at peak efficiency |

### Mk III

| Field | Value |
| --- | --- |
| Power in | -140 W (draws from grid) |
| Produces | up to 2.400 kPa / day at peak efficiency |
| Consumes | Water, up to 5 t per hour, buffer 5 t |

### Mk IV

| Field | Value |
| --- | --- |
| Power in | -700 W (draws from grid) |
| Produces | up to 6.000 kPa / day at peak efficiency |
| Consumes | Fuel Rod, 0.1 per day |

### How to obtain

1. Buy from the Shop for 900 cr.

**Access via:** `self / get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id: str`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** `str`

##### `.name: str`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** `str`

##### `.outpost: OutpostRef`

The outpost where this building is deployed. The returned `OutpostRef` includes its stable id, display name, biome, position, capacity, and `buildings()` query. Read the property again when you need current values.

- **Returns** `OutpostRef`. The outpost where this building is deployed.

##### `.input: InputSlot`

Fuel Rod magazine for the Mk IV tier. Connect a Lead Cask to keep spare rods staged here; the generator swallows one whole rod at a time and burns it down internally. Empty and unused below Mk IV, and a Mk IV with no rod stops producing rather than degrading.

- **Returns** `InputSlot`. Magazine for the Mk IV Fuel Rod supply. Empty and unused below Mk IV.

##### `.water_in: FluidPort`

Water supply port installed by the Mk III pack. Call `connect(...)` with a compatible water provider, then inspect `level()`, `capacity()`, `flow_rate()`, or `connected_to()`. Mk IV uses Fuel Rods instead, but the installed port remains available.

- **Returns** `FluidPort`. The water supply installed by the Mk III pack. Call `connect(...)` with a compatible water provider. Mk IV operation uses Fuel Rods instead, but the installed port remains available.

### Methods

##### `.gauge() → float`

Current value on the resonance sweep (**0-100**). Rises each tick while the generator's script runs and wraps at **100**. With no script running, the sweep pauses where it is. Compare it to `next_window_low()` and `next_window_high()`; when the gauge is inside that range, both edges included, call `sync()`.

- **Returns** `float`. 0-100.

##### `.next_window_low() → float`

Lower edge of the current sweep's sync window, included in the window. Use with `next_window_high()` and `gauge()`; call `sync()` when the gauge is inside the range. The value changes when the sweep wraps to the next cycle.

- **Returns** `float`. Lower bound of this cycle's sync window.

##### `.next_window_high() → float`

Upper edge of the current sweep's sync window, included in the window. Use with `next_window_low()` and `gauge()`; call `sync()` when the gauge is inside the range. The value changes when the sweep wraps to the next cycle.

- **Returns** `float`. Upper bound of this cycle's sync window.

##### `.sync() → ActionResult` *(self only)*

Try to sync this sweep. First call per sweep counts; later calls before the gauge wraps do nothing. Hit (gauge in window) -> **+25%** efficiency. Miss (outside window, or no sync before the sweep ends) -> **-10%**.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.efficiency() → float`

Current compression efficiency (**0-100%**). Climbs with hits, drops with misses, floored at **0**. A well-tuned script holds this at or near **100%** by hitting every cycle's window. Use it to detect a script that's out of sync with the shifting window.

- **Returns** `float`. 0-100%.

##### `.output() → float`

Current **kPa/h** production rate at the current `efficiency()`. Proportional to `efficiency()` × the tier multiplier. The resonance gauge advances slowly, so pressure progress is best judged from `efficiency()` and the per-day projection on the sensor display rather than from a single `output()` read.

- **Returns** `float`. Current pressure output rate, in kPa/h. Derived live from `efficiency()` and the tier multiplier.

##### `.tier() → int`

Permanently installed Mk tier as an integer (**1-4**). Upgrade packs raise this value; temporary Mk III fluid starvation does not. Compare with `effective_tier()` when diagnosing a supplied or degraded generator.

- **Returns** `int`. Permanently installed Mk tier.

##### `.is_degraded() → bool`

`True` when a Mk III pack is starved of its required fluid input and the machine has fallen back to the previous tier multiplier for this tick. Check after applying a Mk III pack, if `True`, the pack is in fallback; investigate `self.water_in.level()` and the upstream supply.

- **Returns** `bool`. `True` when a Mk III pack is starved of its required fluid input and the machine has fallen back to the previous tier multiplier for this tick.

##### `.effective_tier() → int`

The tier actually in effect this tick: `tier()` normally, previous tier while `is_degraded()` is `True`. Scripts rebalancing water flow between generators should compare `effective_tier()` with `tier()`.

- **Returns** `int`. The tier actually in effect this tick: `tier()` normally, the previous tier while `is_degraded()` is `True`.

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

*Components / Terraforming*
