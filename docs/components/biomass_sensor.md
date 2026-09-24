# Component: biomass_sensor

> **Category:** Sensors | **Component Name:** Biomass Sensor

Reports cultivated biomass on the planet, in tons. Updates live as Biomass Mixers produce. Available after the Biosphere research lands; no calibration step.

**Returned by:** `get_component("biomass_sensor")`

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

Returns total biomass tonnage on the planet as a number. `0` before any Biomass Mixer has produced.

- **Returns** Number (tons of biomass)

```python
component = get_component("biomass_sensor")
value = component.get_value()
print(value)
```

*Components / Sensors*
