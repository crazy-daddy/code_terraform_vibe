# Component: research

> **Category:** Core Systems | **Component Name:** Research

Checks global research progress through `get_component("research")`. Use the public ids shown on the Research page, such as `"research_auto_feeders"`. Available from the beginning and read-only.

**Returned by:** `get_component("research")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.is_unlocked(research_id: str) → bool`

Return `True` only when `research_id` is known and unlocked. Known but locked research returns `False`. An unknown id also returns `False` without printing, so scripts can handle every lookup result themselves.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `research_id` | `str` | Public research id, for example `research_auto_feeders`. |

- **Returns** Boolean. `True` only when the known research is unlocked and available in the current build.

##### `.unlocked() → list[str]`

Return a fresh list of public research ids that are unlocked and available in the current build. The list follows stable Research-page registry order, contains no internal capability ids, and can be modified without changing game state.

- **Returns** List of public research ids unlocked and available in the current build, in stable research-registry order.

*Components / Core Systems*
