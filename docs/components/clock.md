# Component: clock

> **Category:** Core Systems | **Component Name:** Clock

The ship's clock. It tracks the time of day, the day count, and the sun's position, everything a script needs for day-night timing and solar tracking.

| Field | Value |
| --- | --- |
| Type | Infrastructure |

**Returned by:** `get_component("clock")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.get_time() → list[int]`

Current time as a **3-element list** `[hours, minutes, seconds]` in 24-hour format. Index with `t[0]`, `t[1]`, `t[2]`. Use for time-of-day branches or to wait for specific hours.

- **Returns** List [hours, minutes, seconds]

##### `.get_day() → int`

Current day number, starts at **1** and increments when the in-world clock rolls past midnight. Use for daily-budget logic (e.g. reset counters at the start of each day) or to detect day transitions for machines like the Heat Generator whose state changes per day.

- **Returns** Number (day count)

##### `.get_time_of_day() → str`

Current daylight phase as a string: `"dawn"`, `"day"`, `"dusk"`, or `"night"`. This is the simulation phase used by solar/day-night logic; the header may further label `"day"` as Morning/Afternoon/Evening for flavor.

- **Returns** String: dawn / day / dusk / night
- **Possible values** `"dawn"`, `"day"`, `"dusk"`, `"night"`

##### `.get_elevation() → float`

Sun's elevation above the horizon (**0-90** degrees). **0** at night, rises to **90** at solar noon (equator), back to **0** at dusk. Solar panels peak when their tilt complements the current elevation.

- **Returns** Number (0-90 degrees)

##### `.tick() → int`

Deterministic simulation tick since save start. At normal speed the simulation grants a fresh script step budget every tick (**10 ticks/sec**, so one tick is **0.1** simulation seconds). Use tick deltas for profiling script timing instead of wall-clock milliseconds.

- **Returns** Integer simulation tick since save start. Deterministic; one normal-speed tick is 100 ms of simulation time.

##### `.elapsed_seconds() → float`

Elapsed simulation seconds since save start. This is the same time base that `sleep(seconds)` waits against, not browser wall-clock time.

- **Returns** Number: elapsed simulation seconds since save start.

##### `.elapsed_game_hours() → float`

Elapsed world-clock hours since save start. Useful for rate calculations and logs that should follow the compressed day/night cycle instead of real seconds.

- **Returns** Number, elapsed world-clock hours since save start.

##### `.real_seconds_per_hour() → float`

Number of real seconds in one world-clock hour. The day cycle compresses **24** world-clock hours into a fixed real-time window, so `sleep(clock.real_seconds_per_hour())` waits exactly one world-clock hour and multiplying by **24** waits a full day. Lets scripts express world-time delays without hardcoding the conversion.

- **Returns** Number, real seconds in one world-clock hour. Multiply by `24` for a full day. Use for planet-aware `sleep()` calls (`sleep(clock.real_seconds_per_hour())` waits exactly one world-clock hour regardless of pacing).

*Components / Core Systems*
