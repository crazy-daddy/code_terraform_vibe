# Component: wildlife_sensor

> **Category:** Sensors | **Component Name:** Wildlife Sensor

Reports total individual fauna across all established Habitat colonies. Available after Biosphere research lands; reads `0` until the first Wildlife colony establishes.

**Returned by:** `get_component("wildlife_sensor")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.get_value()`

Returns the current Wildlife population count as a number, summed from established Habitat colonies.

- **Returns** Number (individuals)

```python
component = get_component("wildlife_sensor")
value = component.get_value()
print(value)
```

*Components / Exploration*
