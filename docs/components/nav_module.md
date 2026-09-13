# Component: nav_module

> **Category:** Vehicles & Modules | **Component Name:** Nav Module

Lets a vehicle drive through `self.nav`. A basic module provides **1.0×** top speed. One Sport Nav on the same rig provides **2×** top speed with **2.6×** movement power draw, about **1.3×** battery use per meter at full throttle. Further Sport Navs add **1.0×** base top speed each and raise draw faster. It fits a `nav` or `universal` slot. Keep the script running until arrival. The vehicle stops and clears its route if the script stops, ends, or errors.

**Returned by:** `self.nav`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.set_target(x, y)` *(self only)*

Set target coordinates to drive toward. **Returns immediately**, the vehicle then drives asynchronously over subsequent ticks while this script remains active. Poll `get_distance_to(x, y)` or `get_position()` in a wait loop to detect proximity. Use a tolerance, normally `while self.nav.get_distance_to(x, y) > 2:`, instead of waiting for exact zero, then call `self.nav.brake()` before `drill.mine()` or another stationary action. For an at-building action, target that building's `BuildingRef.position` rather than the outpost footprint anchor. The vehicle stops and clears its route if the script stops, ends, or errors.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | Target X coordinate in meters |
| `y` | `number` | Target Y coordinate in meters |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_mounted"` | rejection | The required module is not mounted. |
| `"invalid"` | rejection | One or more supplied arguments are outside the accepted domain. |
| `"out_of_bounds"` | rejection | The requested position lies outside the valid world bounds. |

##### `.set_throttle(power)` *(self only)*

Set throttle (**0.0-1.0**, clamped). `self.nav.set_throttle(0.5)` cruises; `1.0` sprints but burns more battery per meter. Use to trade speed for range on long runs. Stop, completion, error, and `brake()` reset throttle to **0**.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `power` | `number` | Throttle fraction in the **0-1** range |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_mounted"` | rejection | The required module is not mounted. |

##### `.throttle()`

Current throttle setpoint (**0.0-1.0**). Returns the value the script last wrote via `self.nav.set_throttle(...)`, or **0** after Stop, completion, error, or `brake()`. Distinct from `get_speed()`, `throttle()` is your intent, `get_speed()` is what the vehicle actually moved last tick.

- **Returns** Number (**0.0-1.0**): current throttle setpoint.

##### `.brake()` *(self only)*

Stop the vehicle immediately, throttle and speed set to **0**, and the current target is cleared to the vehicle's current position. Use when a script needs to abort a drive mid-route (e.g. re-pathing toward a closer site). Cheaper battery-wise than driving to destination.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_mounted"` | rejection | The required module is not mounted. |

##### `.get_position()`

Current position as a `Position` object with `.x` and `.y` in meters from base. Read each iteration of a drive loop to detect arrival, plan next hop, or log the path. See `Position`.

- **Returns** `Position` object `{x, y}` in meters from base

##### `.get_speed()`

Speed in meters per hour as recorded on the last drive tick. **0** while idle or braked; up to the Nav's top speed at throttle **1.0**. Use to confirm the vehicle is actually moving (if `0` when you expected drive, there's a power or target issue). A fresh `set_throttle(...)` won't show up here until the next drive tick.

- **Returns** Number (m/h)

##### `.get_distance_to(x, y)`

Euclidean distance in meters from the vehicle's current position to the given point. Use it inside an intentional wait loop to detect proximity, with an arrival tolerance such as `> 2`, never exact zero. Reaching that tolerance does not stop the vehicle; call `brake()` before a stationary at-site action. For an at-building action, route to that building's `BuildingRef.position`. `set_target()` does not block while the vehicle drives, and the drive is canceled if the script stops, completes, or errors. This is pure straight-line distance and does not account for obstacles.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | Target X coordinate in meters |
| `y` | `number` | Target Y coordinate in meters |

- **Returns** Number (meters)

##### `.speed_multiplier()`

Current top-speed multiplier: **1.0** with Basic Nav/no Sport Nav, or **1 + mounted Sport Nav count** on Pioneer. Use it to plan trip times and scout builds. This is speed only; range still depends on battery, throttle, cargo load, and movement draw.

- **Returns** Number: **1.0** basic, or **1 + Sport Nav count** on Pioneer. Speed only; range depends on battery, throttle, cargo load, and movement draw.

*Components / Vehicles & Modules*
