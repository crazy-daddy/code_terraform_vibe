# Component: oxygen_generator

> **Category:** Terraforming | **Component Name:** Oxygen Generator

Draws CO2 from the atmosphere and turns it into breathable oxygen, one of the core steps toward a livable planet. It runs only when a script sets its intake.

| Field | Value |
| --- | --- |
| Type | Atmosphere |
| Power in | -8 W (draws from grid) |
| Produces | up to 0.240 ppt / day at peak efficiency |
| Input buffer | 4 units |
| Tiers | Mk II, Mk III, and Mk IV |

### How to obtain

1. Buy from the Shop for 1,000 cr.

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

##### `.input`

Fuel Rod magazine for the Mk IV tier. Connect a Lead Cask to keep spare rods staged here; the generator swallows one whole rod at a time and burns it down internally. Empty and unused below Mk IV, and a Mk IV with no rod stops producing rather than degrading.

- **Returns** `InputSlot` magazine for the Mk IV Fuel Rod supply: `connect()`, `take()`, `eject()`, `count()`, `capacity()`, `connected_to()`. Empty and unused below Mk IV.

##### `.water_in`

Water supply port installed by the Mk III pack. Call `connect(...)` with a compatible water provider, then inspect `level()`, `capacity()`, `flow_rate()`, or `connected_to()`. Mk IV uses Fuel Rods instead, but the installed port remains available.

- **Returns** `FluidPort` for the water supply installed by the Mk III pack. Call `connect(...)` with a compatible water provider, then use `level()`, `capacity()`, `flow_rate()`, or `connected_to()`. Mk IV operation uses Fuel Rods instead, but the installed port remains available.

### Methods

##### `.set_intake(value)` *(self only)*

Set CO2 intake rate for this tick. Call `self.set_intake(atmosphere.get_co2() / 10)` each iteration, the chamber's peak-efficiency sweet spot is exactly **1/10th** of ambient CO2. Values above or below that point reduce efficiency smoothly; there is no precision-sensitive cutoff.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `number` | CO2 intake rate to request |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.waste()`

Current carbon waste level (**0-100**). Production runs clean below **60**, drops linearly **60-100**, and stalls (zero output) at **100**. Check this each iteration before calling `dump_waste()`, dumping between **50-60** is penalty-free; dumping elsewhere costs efficiency.

- **Returns** Number (0-100)

##### `.dump_penalty()`

Current efficiency penalty from the last `dump_waste()` call (**0-1**). `0` means no active waste-clearing penalty; `0.25` means output is reduced by 25%. A bad dump remains visible here until the next `dump_waste()` call.

- **Returns** Number (0-1, active waste-clearing efficiency penalty)

##### `.dump_waste()` *(self only)*

Clear accumulated carbon waste. Call `result = self.dump_waste()` when `waste()` is in the **50-60** sweet spot for a clean dump. The penalty lingers until the next dump.

- **Returns** `WasteDumpResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.penalty`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The waste chamber was emptied. This dump applied an efficiency penalty of `.penalty`. |

##### `.efficiency()`

Current conversion efficiency (**0-100%**). Hits **100%** when intake matches **CO2/10**, CO2 is available, waste is at or below **60**, and no dump penalty is active. Waste above **60** reduces efficiency; waste at **100** stalls production. The **50-60** range is the clean window for `dump_waste()`, dumping outside it applies an efficiency penalty you can read with `dump_penalty()`.

- **Returns** Number (0-100%)

##### `.output()`

Current O2 production rate in **ppt/h** at the current settings. Reflects `efficiency() × tier multiplier`, capped by available CO2. Reads `0` if the machine is unpowered, no script is running, CO2 is exhausted, or waste has stalled production. Recomputed live on every read, a fresh `set_intake(...)` is reflected immediately. Use this for live dashboards or to detect degradation mid-loop.

- **Returns** Number: current O2 output rate (ppt/h). Derived live; a fresh `set_intake(...)` is reflected immediately.

##### `.tier()`

Permanently installed Mk tier as an integer (**1-4**). Upgrade packs raise this value; temporary Mk III fluid starvation does not. Compare with `effective_tier()` when diagnosing a supplied or degraded generator.

- **Returns** Integer: permanently installed Mk tier.

##### `.is_degraded()`

`True` when a Mk III pack is starved of its required fluid input and the machine has fallen back to the previous tier multiplier for this tick. Check after applying a Mk III pack and before trusting `output()` to meet your Mk III projections, if `True`, check `self.water_in.level()` and the upstream pipe.

- **Returns** Boolean: `True` when a Mk III pack is starved of its required fluid input and the machine has fallen back to the previous tier multiplier for this tick.

##### `.effective_tier()`

The tier actually in effect this tick: `tier()` normally, previous tier while `is_degraded()` is `True`. Scripts that decide whether to route more water toward this generator should compare `effective_tier()` with `tier()`.

- **Returns** Integer: the tier actually in effect this tick: `tier()` normally, previous tier while `is_degraded()` is `True`.

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Terraforming*
