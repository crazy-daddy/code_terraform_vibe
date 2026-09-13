# Data Types: Core Data

Complete property specifications, descriptions, units, and return types from the official documentation.

## Index

- [`Bounds`](#bounds) (CORE DATA)
- [`Component`](#component) (CORE DATA)
- [`PointOfInterest`](#pointofinterest) (CORE DATA)
- [`Position`](#position) (CORE DATA)
- [`ScriptCommand`](#scriptcommand) (CORE DATA)
- [`Start Here*`](#start-here) (*GUIDE)

---

## Bounds

**Returned by:** planet.get_bounds()

### Properties

##### `.min_x`

Minimum X coordinate (meters).

- **Returns** `number`

##### `.max_x`

Maximum X coordinate (meters).

- **Returns** `number`

##### `.min_y`

Minimum Y coordinate (meters).

- **Returns** `number`

##### `.max_y`

Maximum Y coordinate (meters).

- **Returns** `number`

*Types / Core Data*

---

## Component

**Returned by:** get_component / self

### Properties

##### `.id`

Programmatic identifier of this component.

- **Returns** `string`

##### `.type_id`

Which kind of component this is, as the stable type id ("bio_lab", "rover", "drone_small"). Every component of the same kind shares it, so a library function can branch on what it was handed. The same token machine-type queries accept, so `outpost.buildings(self.type_id)` lists this machine's siblings. Use `.id` for which individual one this is.

- **Returns** `string`

*Types / Core Data*

---

## PointOfInterest

**Returned by:** nocturna.points_of_interest()

### Properties

##### `.x`

Whole-number X coordinate (meters from base) of this contact. Pass straight to a Rover/Pioneer `self.nav.set_target(p.x, p.y)` or a drone `self.go_to(p.x, p.y)`.

- **Returns** `number`

##### `.y`

Whole-number Y coordinate (meters from base) of this contact.

- **Returns** `number`

##### `.scanned`

`True` once you've resolved this contact: a Rover/Pioneer sonar **survey** for a productive non-biomass site, a drone **bio-scan** that logged life at a biomass site, or a sonar **scan** that discovered an inert contact. `False` is your work list: the "?" is still unidentified. Filter `if not p.scanned:` to find the sites left to visit.

- **Returns** `boolean`

##### `.kind`

What the contact is: but **`"unknown"` until `.scanned` is True**. Once resolved it reads `"mineral"`, `"biomass"`, `"thermal"`, `"water"`, `"oil"`, `"exotic"`, or `"inert"`. A sonar `scan()` only places the contact on the map; a productive site stays `"unknown"` until you drive to it and `survey()` it, and a biomass site until a drone bio-scans it. Only inert contacts resolve from the scan alone.

- **Returns** `string`
- **Possible values** `"unknown"`, `"mineral"`, `"biomass"`, `"thermal"`, `"water"`, `"oil"`, `"exotic"`, `"inert"`

*Types / Core Data*

---

## Position

**Returned by:** self.nav.get_position()

### Properties

##### `.x`

X coordinate in meters from base for this position snapshot.

- **Returns** `number`

##### `.y`

Y coordinate in meters from base for this position snapshot.

- **Returns** `number`

### Methods

##### `.__iter__()`

Iterate over `x`, then `y`, so this position can be unpacked or passed to `list()`.

- **Returns** `iterator<number>`

*Types / Core Data*

---

## ScriptCommand

**Returned by:** self.peek_command() / self.next_command().command after status == "ok"

### Properties

##### `.id`

Unique command id assigned when the command entered this script's queue.

- **Returns** `string`

##### `.name`

Command name, such as `"return_base"`. Your script decides what each name means.

- **Returns** `string`

##### `.args`

JSON-safe argument dict sent with the command. Use `.get(key, default)` for optional arguments.

- **Returns** `dict`

##### `.source`

Where the command came from: `"editor"`, `"script"`, `"signal"`, or `"system"`.

- **Returns** `string`
- **Possible values** `"editor"`, `"script"`, `"signal"`, `"system"`

##### `.created_at`

Creation bookkeeping value: a supplied real-world timestamp in milliseconds, otherwise the enqueueing simulation tick, or **0** when neither was supplied. For gameplay timing, use `.tick`.

- **Returns** `number`

##### `.tick`

Game tick when the command was queued, or `None` if not available.

- **Returns** `Optional[number]`

*Types / World & Sites*

---
