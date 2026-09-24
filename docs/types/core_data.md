# Data Types: Core Data

Complete property specifications, descriptions, units, and return types from the official documentation.

## Index

- [`Bounds`](#bounds) (CORE DATA)
- [`Component`](#component) (CORE DATA)
- [`PointOfInterest`](#pointofinterest) (CORE DATA)
- [`Position`](#position) (CORE DATA)
- [`ScriptCommand`](#scriptcommand) (CORE DATA)

---

## Bounds

**Returned by:** planet.get_bounds()

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

### Properties

##### `.id: str`

Programmatic identifier of this component.

- **Returns** `str`

##### `.type_id: str`

Which kind of component this is, as the stable type id ("bio_lab", "rover", "drone_small"). Every component of the same kind shares it, so a library function can branch on what it was handed. The same token machine-type queries accept, so `outpost.buildings(self.type_id)` lists this machine's siblings. Use `.id` for which individual one this is.

- **Returns** `str`

*Types / Core Data*

## PointOfInterest

**Returned by:** nocturna.points_of_interest()

### Properties

##### `.x: int`

Whole-number X coordinate (meters from base) of this contact. Pass straight to a Rover/Pioneer `self.nav.set_target(p.x, p.y)` or a drone `self.go_to(p.x, p.y)`.

- **Returns** `int`

##### `.y: int`

Whole-number Y coordinate (meters from base) of this contact.

- **Returns** `int`

##### `.scanned: bool`

`True` once you've resolved this contact: a Rover/Pioneer sonar **survey** for a productive non-biomass site, a drone **bio-scan** at a biomass site, or a sonar **scan** for an inert contact. `False` is your work list. Filter `if not p.scanned:` for the sites left to visit, and pair it with the sweep's blocked contacts: one your scanner cannot identify stays `False` after a sweep that succeeded, so a plain retry loop returns to it.

- **Returns** `bool`

##### `.kind: str`

What the contact is: but **`"unknown"` until `.scanned` is True**. Once resolved it reads `"mineral"`, `"biomass"`, `"thermal"`, `"water"`, `"oil"`, `"exotic"`, or `"inert"`. A sonar `scan()` only places the contact on the map; a productive site stays `"unknown"` until you drive to it and `survey()` it, and a biomass site until a drone bio-scans it. Only inert contacts resolve from the scan alone.

- **Returns** `str`
- **Possible values** `"unknown"`, `"mineral"`, `"biomass"`, `"thermal"`, `"water"`, `"oil"`, `"exotic"`, `"inert"`

*Types / Core Data*

## Position

**Returned by:** self.nav.get_position()

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

**Returned by:** self.peek_command() / self.next_command().command after status == "ok"

### Properties

##### `.id: str`

Unique command id assigned when the command entered this script's queue.

- **Returns** `str`

##### `.name: str`

Command name, such as `"return_base"`. Your script decides what each name means.

- **Returns** `str`

##### `.args: dict[str, JsonValue]`

JSON-safe argument dict sent with the command. Use `.get(key, default)` for optional arguments.

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

*Types / World & Sites*
