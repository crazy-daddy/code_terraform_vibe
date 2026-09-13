# Component: gps

> **Category:** Core Systems | **Component Name:** GPS

A ship sensor that reports which outpost you're viewing, its name and coordinates, and how many buildings are deployed there. Switching outposts on the dashboard retargets it.

| Field | Value |
| --- | --- |
| Type | Infrastructure |

**Returned by:** `get_component("gps")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.planet()`

Returns the current planet component. Use `gps.planet().id` for stable ids such as `"nocturna"` when calling Journal APIs, and `gps.planet().get_name()` for the display name `"Nocturna"`.

- **Returns** `Nocturna` planet component: use `.id` for stable journal ids and `.get_name()` for display.

##### `.site_name()`

Returns the current outpost's display name. `"Nocturna Base"` for the home outpost (default, players can rename); `"Outpost 1"`, `"Outpost 2"`, ... for player-founded outposts.

- **Returns** String (current outpost name, e.g. "Nocturna Base")

##### `.coords()`

Returns the current outpost's world coordinates as a **2-element list** `[x, y]`. The home outpost sits at `[0, 0]`; founded outposts carry the position the player chose in Plan mode.

- **Returns** List [x, y] (current outpost coordinates)

##### `.buildings_used()`

Returns the number of buildings deployed at the **current** outpost. Sensors, mobile units, structural hubs, and POI extraction machines don't count, only shop-purchased deployable buildings.

- **Returns** Number (buildings deployed at the current outpost)

##### `.buildings_capacity()`

Returns the soft building threshold at the current outpost. Each counted building above it reduces productive and service throughput. Nocturna Base has a few extra starter slots; founded outposts use the standard threshold.

- **Returns** Number (soft building threshold at the current outpost)

##### `.is_full()`

Returns `True` when the current outpost has reached or exceeded its soft building threshold. The threshold itself does not block ordinary deployment.

- **Returns** Boolean (true if the soft building threshold is reached or exceeded)

##### `.is_home()`

Returns `True` when the current outpost is the home outpost (the one the player started at, default name `"Nocturna Base"`). Useful for branching on whether you're managing the spawn site versus a remote outpost.

- **Returns** Boolean (true if the current outpost is the home base)

*Components / Core Systems*
