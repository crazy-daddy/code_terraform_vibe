# Component: battery

> **Category:** Power | **Component Name:** Battery

Base-station energy storage. It fills on its own when generation runs a surplus and drains when the grid falls short. If it empties, machines shut off and their scripts pause.

| Field | Value |
| --- | --- |
| Type | Power |
| Energy | 500 Wh |

### How to obtain

1. Buy from the Shop for 300 cr.

**Returned by:** `get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

##### `.outpost: OutpostRef`

The outpost where this building is deployed. The returned `OutpostRef` includes its stable id, display name, biome, position, capacity, and `buildings()` query. Read the property again when you need current values.

- **Returns** `OutpostRef` for the outpost where this building is deployed.

### Methods

##### `.get_level() → float`

Current stored energy in watt-hours (**Wh**). Drops when consumption exceeds generation, rises when generation exceeds consumption, and stays level when they are equal. Approaching **0** is a red flag, the grid is about to brown out.

- **Returns** Number (Wh)

##### `.get_capacity() → float`

Total battery capacity in watt-hours (**Wh**). Queryable rather than hardcoded so future upgrades don't break scripts. Use with `get_level()` for charge percent.

- **Returns** Number (Wh)

*Components / Power*
