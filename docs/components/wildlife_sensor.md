# Component: wildlife_sensor

> **Category:** Sensors | **Component Name:** Wildlife Sensor

Reports total individual fauna across all established Habitat colonies. Available after Biosphere research lands; reads `0` until the first Wildlife colony establishes.

**Access via:** `get_component("wildlife_sensor")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id: str`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** `str`

##### `.name: str`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** `str`

### Methods

##### `.get_value() → int`

Returns the current Wildlife population count as a number, summed from established Habitat colonies.

- **Returns** `int`. Individuals.

```python
component = get_component("wildlife_sensor")
value = component.get_value()
print(value)
```

*Components / Exploration*
