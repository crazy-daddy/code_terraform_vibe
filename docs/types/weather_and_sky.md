# Data Types: Weather And Sky

Complete property specifications, descriptions, units, and return types from the official documentation.

## Index

- [`SignalReceiver`](#signalreceiver) (WEATHER & SKY)
- [`SignalTransmission`](#signaltransmission) (WEATHER & SKY)
- [`Storm`](#storm) (WEATHER & SKY)
- [`WeatherEventForecast`](#weathereventforecast) (WEATHER & SKY)
- [`WeatherReport`](#weatherreport) (WEATHER & SKY)
- [`WeatherSignalBoard`](#weathersignalboard) (WEATHER & SKY)
- [`WeatherSignalBoardStatus`](#weathersignalboardstatus) (WEATHER & SKY)
- [`WeatherStrike`](#weatherstrike) (WEATHER & SKY)
- [`Zone`](#zone) (WEATHER & SKY)

---

## SignalReceiver

**Returned by:** weather_station.signal_receiver

### Methods

##### `.transmissions() → list[SignalTransmission]`

Raw transmissions audible to this powered station right now. More than one event may be present. Ordering is stable, but copies sharing a packet number are not ordered by validity. The receiver stores no history.

- **Returns** `list[SignalTransmission]`

*Types / Weather & Sky*

## SignalTransmission

**Returned by:** SignalReceiver.transmissions()

### Properties

##### `.event_id: str`

Event id shared by every packet and noise duplicate.

- **Returns** `str`

##### `.number: int`

Declared packet number. Different copies may declare the same number.

- **Returns** `int`

##### `.total: int`

Declared packet count for the event.

- **Returns** `int`

##### `.channel: str`

Channel on which this copy is heard.

- **Returns** `str`
- **Possible values** `"broadcast"`, `"frozen"`, `"coastal"`, `"geothermal"`, `"volcanic"`, `"deep"`

##### `.data: str`

Encoded movement record `event_id|number|total|dx|dy`. Numbered records form a movement sequence beginning at `(0, 0)`; `dx` and `dy` are that record's signed movement offsets, and the sequence endpoint is the event coordinate.

- **Returns** `str`

##### `.checksum: int`

Checksum supplied with the transmission: the full sum of every character's ASCII code in `.data`, with no modulo reduction.

- **Returns** `int`

##### `.emitted_at_gh: float`

Storm-start world-clock timestamp shared by every valid and noisy copy in this event.

- **Returns** `float`

##### `.expires_at_gh: float`

World-clock timestamp when this event's live listening window closes.

- **Returns** `float`

##### `.source_station_id: str`

Physical Weather Station hearing this copy.

- **Returns** `str`

*Types / Weather & Sky*

## Storm

**Returned by:** WeatherReport.active()

### Properties

##### `.id: str`

Stable storm id.

- **Returns** `str`

##### `.x: float`

Cell-center x at this report's observation time, m.

- **Returns** `float`

##### `.y: float`

Cell-center y at this report's observation time, m.

- **Returns** `float`

### Methods

##### `.kind() → str`

`"dust"` or `"thunder"`. Dust events transmit a Raw Uranium aftermath message. Thunder charges eligible Lightning Rods and may produce a Storm Glass message.

- **Returns** `str`
- **Possible values** `"dust"`, `"thunder"`

##### `.radius_m() → float`

Cell radius in m. A heli drone on a straight route holds once its current position is inside the cell; it does not automatically route around it. Electric drones fly through.

- **Returns** `float`

##### `.speed() → float`

Travel speed in m/h.

- **Returns** `float`

##### `.heading() → list[float]`

Unit travel direction as `[dx, dy]`.

- **Returns** `list[float]`

##### `.intensity() → float`

Observed strength **0-1** at report time.

- **Returns** `float`

##### `.expires_in() → float`

Live hours remaining before this observed cell dissipates.

- **Returns** `float`

##### `.eta_to(x: float, y: float) → float | None`

Hours until the cell's edge reaches the point. **0** when the point is already inside the cell; `None` when the track never gets there before dissipating.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | World x, m. |
| `y` | `float` | World y, m. |

- **Returns** `float | None`

*Types / Weather & Sky*

## WeatherEventForecast

**Returned by:** WeatherReport.forecast()

### Properties

##### `.id: str`

Stable event id shared with the active Storm and later signal transmissions.

- **Returns** `str`

### Methods

##### `.kind() → str`

Broad event family: `"dust"` or `"thunder"`.

- **Returns** `str`
- **Possible values** `"dust"`, `"thunder"`

##### `.arrival_window() → list[float]`

`[earliest, latest]` hours after this report's observation time when the cell should enter coverage.

- **Returns** `list[float]`

##### `.corridor() → Zone`

Coarse predicted travel corridor as a `Zone`; it is storm information, never the hidden aftermath path.

- **Returns** `Zone`

##### `.intensity_range() → list[float]`

Observed forecast range `[low, high]`, each **0-1**.

- **Returns** `list[float]`

*Types / Weather & Sky*

## WeatherReport

**Returned by:** weather_station.observe() / weather_station.last_report()

### Properties

##### `.id: str`

Stable report id for provenance and logging.

- **Returns** `str`

##### `.source_id: str`

Physical Weather Station id that made this report.

- **Returns** `str`

##### `.observed_at_gh: float`

World-clock timestamp when the report was measured.

- **Returns** `float`

### Methods

##### `.age_gh() → float`

Live age of this immutable report in world-clock hours.

- **Returns** `float`

##### `.coverage() → Zone`

The station's local coverage as a `Zone` frozen at observation time.

- **Returns** `Zone`

##### `.active() → list[Storm]`

List of active `Storm` snapshots inside local coverage at observation time.

- **Returns** `list[Storm]`

##### `.forecast() → list[WeatherEventForecast]`

Local `WeatherEventForecast` entries expected to enter coverage within **8 world-clock hours**, or **24** after Weather Forecasting research.

- **Returns** `list[WeatherEventForecast]`

*Types / Weather & Sky*

## WeatherSignalBoard

**Returned by:** weather_station.signal_board

### Methods

##### `.reveal(transmission: SignalTransmission | TransmissionRecord) → ActionResult`

Publish one transmission into its declared numbered slot. A different event replaces this station's current board. An already-published slot for the same event is left unchanged. The board checks shape and bounds, not meaning or checksum validity.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `transmission` | `SignalTransmission \| TransmissionRecord` | A `SignalTransmission`, a saved dictionary such as `vars(signal)`, or a class instance with the same fields. Requires string `event_id`, `channel`, and `data`, plus whole-number `number` and `total` within the signal slot limits. Optional string `source_station_id` defaults to this station when omitted. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"no_power"` | transient | The component has no available power. |
| `"duplicate"` | rejection | That entry is already present and nothing was added or changed. |
| `"invalid_type"` | rejection | The supplied value does not carry the required API type and provenance. |

##### `.reject(transmission: SignalTransmission | TransmissionRecord) → ActionResult`

Add one to the supplied event's refusal count without opening a slot. A different event replaces this station's current board.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `transmission` | `SignalTransmission \| TransmissionRecord` | A `SignalTransmission`, a saved dictionary such as `vars(signal)`, or a class instance with the same fields and validation as `reveal()`. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"no_power"` | transient | The component has no available power. |
| `"invalid_type"` | rejection | The supplied value does not carry the required API type and provenance. |

##### `.resolve(event_id: str, info: dict[str, object]) → ActionResult`

Publish up to **6** labelled rows for an event. A different event replaces this station's current board. The board displays supplied values without validating them.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `event_id` | `str` | Event id the rows describe. |
| `info` | `dict[str, object]` | String-keyed dictionary of labels and display values. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"no_power"` | transient | The component has no available power. |
| `"invalid_type"` | rejection | The supplied value does not carry the required API type and provenance. |

##### `.clear() → ActionResult`

Clear the board, its rejection count, and any published conclusion.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"no_power"` | transient | The component has no available power. |

##### `.status() → WeatherSignalBoardStatus`

This station's current board publication metadata.

- **Returns** `WeatherSignalBoardStatus`

*Types / Weather & Sky*

## WeatherSignalBoardStatus

**Returned by:** weather_station.signal_board.status()

### Properties

##### `.has_input: bool`

Whether this station has published a Signal Board value.

- **Returns** `bool`

##### `.published_at_gh: float | None`

Publication timestamp, or `None` with no input.

- **Returns** `float | None`

##### `.freshness: str`

`"no_input"`, `"fresh"`, or `"stale"`. A publication becomes stale after **2 world-clock hours**.

- **Returns** `str`
- **Possible values** `"no_input"`, `"fresh"`, `"stale"`

##### `.event_id: str`

Event shown on this station's board, or an empty string with no input.

- **Returns** `str`

*Types / Weather & Sky*

## WeatherStrike

**Returned by:** weather_station.strikes()

### Properties

##### `.id: str`

Stable observed-strike id.

- **Returns** `str`

##### `.event_id: str`

Thunderstorm event id.

- **Returns** `str`

##### `.observed_at_gh: float`

World-clock hour when the strike landed.

- **Returns** `float`

##### `.energy_wh: float`

Electrical energy carried by the strike in Wh.

- **Returns** `float`

##### `.caught: bool`

Whether an eligible Lightning Rod banked this strike.

- **Returns** `bool`

*Types / Weather & Sky*

## Zone

**Returned by:** WeatherReport.coverage() and WeatherEventForecast.corridor()

### Methods

##### `.intersect(other: Zone) → Zone`

Keep only the geometry shared by both zones.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `other` | `Zone` | Another `Zone`. |

- **Returns** `Zone`

##### `.union(other: Zone) → Zone`

Keep everything covered by either zone.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `other` | `Zone` | Another `Zone`. |

- **Returns** `Zone`

##### `.subtract(other: Zone) → Zone`

Remove the other zone's geometry from this zone.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `other` | `Zone` | Another `Zone`. |

- **Returns** `Zone`

##### `.diff(other: Zone) → Zone`

Keep geometry present in only one of the two zones.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `other` | `Zone` | Another `Zone`. |

- **Returns** `Zone`

##### `.center() → list[float] | None`

Centroid as `[x, y]` in m, or `None` for an empty zone. This describes visible storm geometry, not its hidden aftermath.

- **Returns** `list[float] | None`

##### `.area() → float`

Covered area in m².

- **Returns** `float`

##### `.contains(x: float, y: float) → bool`

`True` when the point is inside the zone.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | World x, m. |
| `y` | `float` | World y, m. |

- **Returns** `bool`

##### `.is_empty() → bool`

`True` when the zone covers nothing.

- **Returns** `bool`
