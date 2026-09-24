# Component: plants_sensor

> **Category:** Sensors | **Component Name:** Plants Sensor

Reports permanent vegetated km² produced by the Plant Terraformer fleet. Available after the Biosphere research lands. Field growth alone does not change this value.

**Returned by:** `get_component("plants_sensor")`

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

Returns permanent Plants km² as a number. Plant Terraformers are the only writers; repeated crop cycles, diversity, providers, Fertilizer, and Yield Amplifier increase the physical Forage supply they process.

- **Returns** Number (km² planted)

```python
component = get_component("plants_sensor")
value = component.get_value()
print(value)
```

*Components / Sensors*
