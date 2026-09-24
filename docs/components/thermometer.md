# Component: thermometer

> **Category:** Sensors | **Component Name:** Thermometer

Always-working surface temperature probe, no calibration needed. Reads the planet's current surface temperature in **°C** directly.

| Field | Value |
| --- | --- |
| Type | Sensors |

**Returned by:** `get_component("thermometer")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.get_value() → float`

Current surface temperature in **°C** as a number. Safe to call from any script; no repair step needed. This is the display °C, for the heat-units progression metric that research thresholds compare against, read `get_component("atmosphere").get_heat()`.

- **Returns** Number (°C)

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

```python
component = get_component("thermometer")
value = component.get_value()
print(value)
```

*Components / Sensors*
