# Component: transmitter

> **Category:** Core Systems | **Component Name:** Transmitter

Sends data to other planets. Use it to report sensor readings to Earth or submit contract answers. Call `connect()` to choose a planet, then `transmit(key, value)` to send data; `disconnect()` clears the connection. A connection lasts only for the current script run, so each transmitting script must connect first. Save `get_component("transmitter")` to a variable and reuse it for both calls.

**Returned by:** `get_component("transmitter")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.list_planets() → list[Planet]`

Every available transmission destination as a list of `Planet` objects (each with `.id`, `.name`, etc.). Call once at script start to see what is available; pass a returned `.id` to `connect(id)`.

- **Returns** List of Planet objects

##### `.connect(planet: str) → ActionResult`

Open a channel to the planet with the given id: `result = transmitter.connect("earth")`. The id must be lowercase (from `list_planets()`). Read `transmitter.get_info().target` after success. Connection lasts only for the current script run, if your script restarts, `connect()` again before `transmit()`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `planet` | `str` | Planet id to connect to |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_found"` | rejection | The requested object, target, or record does not exist. |

##### `.disconnect() → ActionResult`

Close the current script-run channel. This does not affect contracts or any other script; it only clears this Transmitter object's active target so later `transmit()` calls must `connect()` again.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The Transmitter's current script-run channel is disconnected. |

##### `.get_info() → TransmitterInfo`

Current connection status. Returns an object with `.connected` (boolean) and `.target` (connected planet id, or `"none"`). Use as a guard before `transmit()`: `if transmitter.get_info().connected: transmitter.transmit(...)`.

- **Returns** Object { connected, target }

##### `.transmit(key: str, value: JsonValue) → ActionResult`

Send a named value to the connected planet with `transmitter.transmit(key, value)`. Opening sensor telemetry is unavailable until the power and sensor onboarding steps are complete and the uplink step is active. For sensor readings, use the name requested by Earth, such as `"current_temperature"`. For contract answers, use `self.contract.id`. The data arrives in the same tick.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `str` | A sensor-telemetry key such as `"current_temperature"` (what the opening uplink asks for), or a contract id read from `self.contract.id` inside a contract script. |
| `value` | `JsonValue` | The reading or computed answer to send. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"correct"` | success | The answer solved the active contract. The reward was paid and the contract is now complete. |
| `"incorrect"` | rejection | The submitted value is incorrect. |
| `"already_completed_correct"` | success | The contract is already completed. The value submitted now is correct. |
| `"already_completed_incorrect"` | rejection | The contract is already completed. The value submitted now is incorrect. |
| `"accepted"` | success | The reading matched the planet value for the requested key. This is the telemetry path used by the uplink step, not a contract answer. |
| `"rejected"` | rejection | The submitted value or request was rejected. |
| `"not_connected"` | rejection | The component has no active connection. |
| `"wrong_planet"` | rejection | The operation targets a different planet. |
| `"wrong_contract"` | rejection | The supplied contract is not active for this operation. |
| `"locked"` | rejection | The required feature, recipe, or operation is locked. |
| `"unknown_contract"` | rejection | The supplied contract identifier does not exist. |
| `"key_is_planet"` | rejection | The supplied key names a planet rather than a telemetry or contract key. |
| `"unknown_key"` | rejection | The supplied telemetry or contract key does not exist. |

*Components / Sensors*
