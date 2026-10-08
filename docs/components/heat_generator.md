# Component: heat_generator

> **Category:** Terraforming | **Component Name:** Heat Generator

Warms the planet surface by producing heat. The best power setting shifts with the day's weather, so a script reads the conditions and holds the heater at the right level.

### Mk I

| Field | Value |
| --- | --- |
| Type | Atmosphere |
| Power in | Variable (draws from grid) |
| Produces | up to 0.252 heat / day at peak efficiency |
| Input buffer | Units: 4 |
| Tiers | Mk II, Mk III, and Mk IV |

### Mk II

| Field | Value |
| --- | --- |
| Produces | up to 1.184 heat / day at peak efficiency |

### Mk III

| Field | Value |
| --- | --- |
| Produces | up to 52.416 heat / day at peak efficiency |
| Consumes | Steam, up to 12 t per hour, buffer 8 t |

### Mk IV

| Field | Value |
| --- | --- |
| Produces | up to 129.780 heat / day at peak efficiency |
| Consumes | Fuel Rod, 0.1 per day |

### How to obtain

1. Buy from the Shop for 800 cr.

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

##### `.steam_in: FluidPort`

Steam supply port installed by the Mk III pack. Call `connect(...)` with a compatible steam provider, then inspect `level()`, `capacity()`, `flow_rate()`, or `connected_to()`. Mk IV uses Fuel Rods instead, but the installed port remains available.

- **Returns** `FluidPort`. The steam supply installed by the Mk III pack. Call `connect(...)` with a compatible steam provider. Mk IV operation uses Fuel Rods instead, but the installed port remains available.

### Methods

##### `.set_power(watts: float) → ActionResult` *(self only)*

Set base heater power from **0-10**; values outside that range are clamped. `0` turns heating off. The best positive setting depends on the current `thermal_state()`, so update it with `self.set_power(value)` as conditions change. Higher Mk tiers multiply grid draw without changing the best base setting. A poor setting wastes energy and reduces heat output. The setting returns to **0** when the script stops, ends, or errors.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `watts` | `float` | Power draw in watts |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.thermal_state() → str`

Current daily heater thermal state, one of `"clear"`, `"dust_storm"`, `"heat_bleed"`, `"dust_veil"`. Each state has its own optimal positive `set_power()` value. The state is stable throughout the current day and changes only on a new day, so read it at the start of each iteration and branch when the string changes: `if state == "clear": self.set_power(5)` etc. Your job is figuring out the four optimal values.

- **Returns** `str`
- **Possible values** `"clear"`, `"dust_storm"`, `"heat_bleed"`, `"dust_veil"`

##### `.efficiency() → float`

Current heating efficiency (**0-100%**). Hits **100%** only when `set_power()` exactly matches the current `thermal_state()`'s optimal, and falls off *steeply* around it (not linearly): about **31%** one step away, then a **10%** floor for any setting two or more steps off. Reads **0%** only when power is `0`. Scan positive power values and take the setting that reads **100%** as each state's optimal.

- **Returns** `float`. 0-100%.

##### `.output() → float`

Current heat-unit production rate per hour at the current settings. Heat accumulates to raise surface temperature over many days; the sensor rate display projects per-day totals. Reflects `efficiency()` × the tier multiplier. Reads `0` if unpowered or no script running. Recomputed live on every read, a fresh `set_power(...)` is reflected immediately.

- **Returns** `float`. Current heat output rate, in heat units/h. Derived live; a fresh `set_power(...)` is reflected immediately.

##### `.tier() → int`

Permanently installed Mk tier as an integer (**1-4**). Upgrade packs raise this value; temporary Mk III steam starvation does not. Compare with `effective_tier()` when diagnosing a supplied or degraded heater.

- **Returns** `int`. Permanently installed Mk tier.

##### `.is_degraded() → bool`

`True` when a Mk III pack is starved of its required fluid input and the machine has fallen back to the previous tier multiplier for this tick. Check after applying a Mk III pack, if `True`, your tier-3 heater is temporarily running as Mk II; look at `self.steam_in.level()` and the upstream thermal cap.

- **Returns** `bool`. `True` when a Mk III pack is starved of its required fluid input and the machine has fallen back to the previous tier multiplier for this tick.

##### `.effective_tier() → int`

The tier actually in effect this tick: `tier()` normally, previous tier while `is_degraded()` is `True`. Scripts that rebalance steam flow between heaters should compare `effective_tier()` with `tier()`.

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
