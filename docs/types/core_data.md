# Data Types: Core Data

Complete property specifications, descriptions, units, and return types from the official documentation.

## Index

- [`Bounds`](#bounds) (CORE DATA)
- [`Component`](#component) (CORE DATA)
- [`PointOfInterest`](#pointofinterest) (CORE DATA)
- [`Position`](#position) (CORE DATA)
- [`ScriptCommand`](#scriptcommand) (CORE DATA)
- [`ScriptStatusReport`](#scriptstatusreport) (CORE DATA)

---

## Bounds

**Returned by:** planet.get_bounds()

Import `Bounds` with `from __builtins__ import Bounds`. Arguments accept positional and keyword forms. Use `vars()` to obtain a dictionary for storage or messaging.

##### `Bounds(min_x: float, max_x: float, min_y: float, max_y: float) → Bounds`

Create a local `Bounds` value for your script. Creating this value does not change the world. Requires `min_x <= max_x`. Requires `min_y <= max_y`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `min_x` | `float` | Minimum X coordinate (meters). Must be a finite number. |
| `max_x` | `float` | Maximum X coordinate (meters). Must be a finite number. |
| `min_y` | `float` | Minimum Y coordinate (meters). Must be a finite number. |
| `max_y` | `float` | Maximum Y coordinate (meters). Must be a finite number. |

- **Returns** `Bounds`

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | An argument has the wrong type, or the call has missing, excess, duplicate, or unknown arguments. |
| `ValueError` | A numeric value is outside the permitted range, or the bounds are reversed. |
| `OverflowError` | An integer cannot be represented safely as a game number. |

### Properties

##### `.min_x: float`

Minimum X coordinate (meters).

- **Returns** `float`

##### `.max_x: float`

Maximum X coordinate (meters).

- **Returns** `float`

##### `.min_y: float`

Minimum Y coordinate (meters).

- **Returns** `float`

##### `.max_y: float`

Maximum Y coordinate (meters).

- **Returns** `float`

*Types / Core Data*

## Component

**Returned by:** get_component / self

Get `Component` from the APIs listed here. It has no script constructor.

### Properties

##### `.id: str`

Programmatic identifier of this component.

- **Returns** `str`

##### `.type_id: str`

Which kind of component this is, as the stable type id (`"bio_lab"`, `"rover"`, `"drone_small"`). Every component of the same kind shares it, so a library function can branch on what it was handed. For a building at an outpost, `outpost.buildings(self.type_id)` lists buildings of that type there; the query excludes mobile units and sensors. Use `.id` for which individual one this is.

- **Returns** `str`

*Types / Core Data*

## PointOfInterest

**Returned by:** nocturna.points_of_interest()

Get `PointOfInterest` from the APIs listed here. It has no script constructor.

### Properties

##### `.x: int`

Whole-number X coordinate (meters from base) of this contact. Pass straight to a Rover/Pioneer `self.nav.set_target(p.x, p.y)` or a drone `self.go_to(p.x, p.y)`.

- **Returns** `int`

##### `.y: int`

Whole-number Y coordinate (meters from base) of this contact.

- **Returns** `int`

##### `.scanned: bool`

`True` once you've resolved this contact: a Rover/Pioneer sonar **survey** for a productive non-biomass site, a drone **bio-scan** at a biomass site, or a sonar **scan** for an inert contact. `False` is your work list. Filter `if not p.scanned:` for the sites left to visit, and pair it with the sweep's `blocked` contacts: one your scanner cannot identify stays `False` after a sweep that succeeded, so a plain retry loop returns to it.

- **Returns** `bool`

##### `.kind: str`

The contact's type: **`"unknown"` until `.scanned` is `True`**. Once resolved it reads `"mineral"`, `"biomass"`, `"thermal"`, `"water"`, `"oil"`, `"exotic"`, or `"inert"`. A sonar `scan()` only places the contact on the map; a productive site stays `"unknown"` until you drive to it and `survey()` it, and a biomass site until a drone bio-scans it. Only inert contacts resolve from the scan alone.

- **Returns** `str`
- **Possible values** `"unknown"`, `"mineral"`, `"biomass"`, `"thermal"`, `"water"`, `"oil"`, `"exotic"`, `"inert"`

*Types / Core Data*

## Position

**Returned by:** self.nav.get_position()

Import `Position` with `from __builtins__ import Position`. Arguments accept positional and keyword forms. Use `vars()` to obtain a dictionary for storage or messaging.

##### `Position(x: float, y: float) → Position`

Create a local `Position` value for your script. Creating this value does not change the world.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | X coordinate in meters from base for this position snapshot. Must be a finite number. |
| `y` | `float` | Y coordinate in meters from base for this position snapshot. Must be a finite number. |

- **Returns** `Position`

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | An argument has the wrong type, or the call has missing, excess, duplicate, or unknown arguments. |
| `OverflowError` | An integer cannot be represented safely as a game number. |

### Properties

##### `.x: float`

X coordinate in meters from base for this position snapshot.

- **Returns** `float`

##### `.y: float`

Y coordinate in meters from base for this position snapshot.

- **Returns** `float`

### Methods

##### `.__iter__() → Iterator[float]`

Iterate over `x`, then `y`, so this position can be unpacked or passed to `list()`.

- **Returns** `Iterator[float]`

*Types / Core Data*

## ScriptCommand

**Returned by:** `self.peek_command()` / `self.next_command().command` after `status == "ok"`

Get `ScriptCommand` from the APIs listed here. It has no script constructor.

### Properties

##### `.id: str`

Unique command id assigned when the command entered this script's queue.

- **Returns** `str`

##### `.name: str`

Command name, such as `"return_base"`. Your script decides what each name means.

- **Returns** `str`

##### `.args: dict[str, JsonValue]`

JSON-safe argument `dict` sent with the command. Use `.get(key, default)` for optional arguments.

- **Returns** `dict[str, JsonValue]`

##### `.source: str`

Where the command came from: `"editor"`, `"script"`, `"signal"`, or `"system"`.

- **Returns** `str`
- **Possible values** `"editor"`, `"script"`, `"signal"`, `"system"`

##### `.created_at: float`

Creation bookkeeping value: a supplied real-world timestamp in milliseconds, otherwise the enqueueing simulation tick, or **0** when neither was supplied. For gameplay timing, use `.tick`.

- **Returns** `float`

##### `.tick: int | None`

Game tick when the command was queued, or `None` if not available.

- **Returns** `int | None`

*Types / Core Data*

## ScriptStatusReport

**Returned by:** get_status_report() / self.get_status_report()

Get `ScriptStatusReport` from the APIs listed here. It has no script constructor.

### Properties

##### `.message: str`

The player-authored plain-text explanation.

- **Returns** `str`

##### `.level: str`

The player-selected `info`, `warn`, or `error` presentation level.

- **Returns** `str`
- **Possible values** `"info"`, `"warn"`, `"error"`

##### `.active: bool`

`True` while the reporting run is running or waiting. `False` while paused, halted by the debugger, completed, or failed.

- **Returns** `bool`

##### `.run_id: str`

The exact run identity. Changes when a new execution starts.

- **Returns** `str`

*Types / World & Sites*
