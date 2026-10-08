# Component: weather_station

> **Category:** Weather & Sky | **Component Name:** Weather Station

A programmable local storm station and live receiver. It measures immutable local reports, hears event transmissions on `broadcast` and biome channels, and may publish to the Signal Board.

| Field | Value |
| --- | --- |
| Type | Sensors |
| Power in | -50 W (draws from grid) |

### How to obtain

1. Requires the **Weather Program** research (Terraform Index 330,000).
2. Buy from the Shop for 60,000 cr.

**Access via:** `self / get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id: str`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** `str`

##### `.name: str`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** `str`

##### `.outpost: OutpostRef`

The outpost where this building is deployed. The returned `OutpostRef` includes its stable id, display name, biome, position, capacity, and `buildings()` query. Read the property again when you need current values.

- **Returns** `OutpostRef`. The outpost where this building is deployed.

##### `.signal_board: WeatherSignalBoard`

This station's programmable Weather display. `reveal()` publishes a transmission into a numbered slot, `reject()` counts a refused copy, and `resolve()` publishes labelled values. The board displays what your script supplies without interpreting it.

- **Returns** `WeatherSignalBoard`. This station's optional player-authored board. It displays supplied transmissions and labelled values without interpreting them.

##### `.signal_receiver: SignalReceiver`

Live receiver. `transmissions()` returns only the raw copies audible to this powered station now and stores no history. Dust reception uses local biome channels; thunder reception uses the `broadcast` channel.

- **Returns** `SignalReceiver`. This station's live receiver. `transmissions()` exposes only what is audible now and stores no raw history. Dust-event channels are biome-specific; all thunder packets use the `broadcast` channel.

### Methods

##### `.observe() → WeatherReport` *(self only)*

Measure one immutable local report. The station refreshes at most once per world-clock hour; faster calls return the same report id. The report includes local coverage, active storm snapshots, and a local forecast reaching 8 world-clock hours ahead, or 24 once Weather Forecasting is researched. It never contains an aftermath coordinate.

- **Returns** `WeatherReport`. An immutable report from this station's local coverage. Repeated calls inside one observation hour return the same report. Raises `RuntimeError` when the station is unfinished or unpowered.

*Raises*

| Exception | Condition |
| --- | --- |
| `RuntimeError` | The Weather Station is unfinished or unpowered, so no observation can be recorded. |

##### `.last_report() → WeatherReport | None`

Read the last measured report without taking a new observation. This is useful for startup recovery and stale-data handling; `None` means this station has never completed `observe()`.

- **Returns** `WeatherReport | None`. The last local report, or `None` before the first successful observation. The snapshot remains readable while stale or unpowered.

##### `.strikes() → list[WeatherStrike]`

Return this station's bounded strike history. Each `WeatherStrike` includes its event id, observation time, energy, and whether a Lightning Rod banked it. Exact strike positions and Storm Glass eligibility are not included. Only strikes this station physically observed are returned.

- **Returns** `list[WeatherStrike]`. Lightning strikes observed by this station, oldest first.

##### `.set_status(message: str, level: str = "info") → None` *(self only)*

Show a status message for this machine's current script run. Use `self.set_status(message, "info")`. The same reporting capability is available as `set_status()` in every script. Messages follow the current execution, independently of machine state and game warnings.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `str` | Non-empty plain text, at most 240 characters. Null characters are not accepted. |
| `level` | `str` | Presentation severity: `info`, `warn`, or `error`. Defaults to `info`. |

- **Returns** `None`. `None`.

##### `.clear_status() → None` *(self only)*

Clear the current script run's status message. Clearing an absent message has no effect. Does not wait or change machine behaviour.

- **Returns** `None`. `None`.

##### `.get_status_report() → ScriptStatusReport | None`

Read this machine's script status report from any script. Returns `None` when it has no report. The returned snapshot includes `message`, `level`, `active`, and `run_id`.

- **Returns** `ScriptStatusReport | None`. Read this machine's script status report from any script. Returns `None` when it has no report. The returned snapshot includes `message`, `level`, `active`, and `run_id`.

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Database / Production*
