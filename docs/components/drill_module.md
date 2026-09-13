# Component: drill_module

> **Category:** Vehicles & Modules | **Component Name:** Drill Module

Extracts minerals through `self.drill`. The basic drill handles hardness **1** at **1.0×** speed using **10 W**; Industrial handles hardness **3** at **0.75×** using **20 W**; Heavy handles hardness **4** at **0.6×** using **30 W**. Without a mounted Drill Module, the vehicle cannot mine.

**Returned by:** `self.drill`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.mine()` *(self only)*

Extract **1** unit of the current site's mineral into vehicle cargo. Mining takes `mineral_base_minutes × drill.speed_multiplier() / site_purity` game-time, and the script pauses until it finishes.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_mounted"` | rejection | The required module is not mounted. |
| `"not_at_site"` | rejection | The vehicle is not positioned at a compatible site. |
| `"not_surveyed"` | rejection | The mineral site has not been surveyed. |
| `"too_hard"` | rejection | The target exceeds the mounted tool's hardness limit. |
| `"no_cargo_space"` | rejection | Cargo has no compatible space for the result. |
| `"no_power"` | transient | The component has no available power. |
| `"not_enough_power"` | rejection | The available energy is below the operation's requirement. |
| `"busy"` | transient | The component is already performing another operation. |

##### `.hardness_limit()`

Maximum mineral hardness this drill can extract.

- **Returns** Number: **1** basic, **3** Industrial, **4** Heavy. A stale captured module reference raises `ReferenceError`.

*Raises*

| Exception | Condition |
| --- | --- |
| `ReferenceError` | This DrillModule reference is stale because its module is no longer mounted. Read self.drill again after mounting a drill. |

##### `.speed_multiplier()`

Per-unit time multiplier (lower = faster).

- **Returns** Number: **1.0** basic, **0.75** Industrial, **0.6** Heavy. A stale captured module reference raises `ReferenceError`.

*Raises*

| Exception | Condition |
| --- | --- |
| `ReferenceError` | This DrillModule reference is stale because its module is no longer mounted. Read self.drill again after mounting a drill. |

*Components / Vehicles & Modules*
