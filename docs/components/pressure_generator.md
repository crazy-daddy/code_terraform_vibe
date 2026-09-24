# Component: pressure_generator

> **Category:** Terraforming | **Component Name:** Pressure Generator

Compresses the thin atmosphere to raise surface pressure. It runs best when a script catches each sync window as its gauge sweeps; missed windows cost efficiency.

| Field | Value |
| --- | --- |
| Type | Atmosphere |
| Power in | -7 W (draws from grid) |
| Produces | up to 0.012 kPa / day at peak efficiency |
| Input buffer | 4 units |
| Tiers | Mk II, Mk III, and Mk IV |

### How to obtain

1. Buy from the Shop for 900 cr.

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

Fuel Rod magazine for the Mk IV tier. Connect a Lead Cask to keep spare rods staged here; the generator swallows one whole rod at a time and burns it down internally. Empty and unused below Mk IV, and a Mk IV with no rod stops producing rather than degrading.

- **Returns** `InputSlot` magazine for the Mk IV Fuel Rod supply: `connect()`, `take()`, `eject()`, `count()`, `capacity()`, `connected_to()`. Empty and unused below Mk IV.

##### `.water_in: FluidPort`

Water supply port installed by the Mk III pack. Call `connect(...)` with a compatible water provider, then inspect `level()`, `capacity()`, `flow_rate()`, or `connected_to()`. Mk IV uses Fuel Rods instead, but the installed port remains available.

- **Returns** `FluidPort` for the water supply installed by the Mk III pack. Call `connect(...)` with a compatible water provider, then use `level()`, `capacity()`, `flow_rate()`, or `connected_to()`. Mk IV operation uses Fuel Rods instead, but the installed port remains available.

### Methods

##### `.gauge() → float`

Current value on the resonance sweep (**0-100**). Rises each tick and wraps at **100**. Compare it to `next_window_low()` and `next_window_high()`; when the gauge is inside that range, both edges included, call `sync()`.

- **Returns** Number (0-100)

##### `.next_window_low() → float`

Lower edge of the current sweep's sync window, included in the window. Use with `next_window_high()` and `gauge()`; call `sync()` when the gauge is inside the range. The value changes when the sweep wraps to the next cycle.

- **Returns** Number (lower bound of this cycle's sync window)

##### `.next_window_high() → float`

Upper edge of the current sweep's sync window, included in the window. Use with `next_window_low()` and `gauge()`; call `sync()` when the gauge is inside the range. The value changes when the sweep wraps to the next cycle.

- **Returns** Number (upper bound of this cycle's sync window)

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

- **Returns** Number (0-100%)

##### `.output() → float`

Current **kPa/h** production rate at the current `efficiency()`. Proportional to `efficiency() × tier multiplier`. The resonance gauge advances slowly, so pressure progress is best judged from `efficiency()` and the per-day projection on the sensor display rather than from a single `output()` read.

- **Returns** Number: current pressure output rate (kPa/h). Derived live from `efficiency()` and tier multiplier.

##### `.tier() → int`

Permanently installed Mk tier as an integer (**1-4**). Upgrade packs raise this value; temporary Mk III fluid starvation does not. Compare with `effective_tier()` when diagnosing a supplied or degraded generator.

- **Returns** Integer: permanently installed Mk tier.

##### `.is_degraded() → bool`

`True` when a Mk III pack is starved of its required fluid input and the machine has fallen back to the previous tier multiplier for this tick. Check after applying a Mk III pack, if `True`, the pack is in fallback; investigate `self.water_in.level()` and the upstream supply.

- **Returns** Boolean: `True` when a Mk III pack is starved of its required fluid input and the machine has fallen back to the previous tier multiplier for this tick.

##### `.effective_tier() → int`

The tier actually in effect this tick: `tier()` normally, previous tier while `is_degraded()` is `True`. Scripts rebalancing water flow between generators should compare `effective_tier()` with `tier()`.

- **Returns** Integer: the tier actually in effect this tick: `tier()` normally, previous tier while `is_degraded()` is `True`.

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Terraforming*
