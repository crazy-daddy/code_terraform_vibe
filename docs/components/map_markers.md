# Component: map_markers

> **Category:** Exploration | **Component Name:** Map Markers

Annotates the Planet Map from your scripts. Get it with `get_component("markers")` after Cartography unlocks, then `markers.place("survey.rover_1.empty:120:-40", 120, -40, "No contact", "x")` to drop a marker anywhere in the world, instantly, with no vehicle and no materials. Markers are notes, not blueprints: to actually build somewhere, pass the coordinates to `construction_blueprint.plan_structure(...)`. Store structured data in the Data Archive under the same id.

**Returned by:** `get_component("markers")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.place(id: str, x: float, y: float, label: str = "", icon: str = "pin", color: str = "accent", note: str = "") → ActionResult`

Create or rewrite one marker. Reusing an id moves and restyles that marker instead of adding a second one, so a script that restarts after a save does not fill the map with duplicates. Coordinates are world meters and keep their fractions. Organize families of markers by id prefix, and include the controlling machine in the prefix, as in `"survey.rover_1."`, so two scripts cannot overwrite each other.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `id` | `str` | Stable marker id, 1-64 characters using letters, numbers, `_`, `.`, `:`, or `-`. Reusing an id rewrites that marker. |
| `x` | `float` | World x coordinate in meters. Fractions are kept exactly. |
| `y` | `float` | World y coordinate in meters. Fractions are kept exactly. |
| `label` | `str` | Display text, up to 48 characters. Empty shows the id instead. |
| `icon` | `str` | Marker glyph. |
| `color` | `str` | Marker color. |
| `note` | `str` | Longer note shown on hover and in the Markers list, up to 240 characters. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"invalid_key"` | rejection | The supplied key is invalid. |
| `"invalid_coords"` | rejection | The supplied coordinates are invalid. |
| `"out_of_bounds"` | rejection | The requested position lies outside the valid world bounds. |
| `"invalid_icon"` | rejection | The supplied marker glyph is not one of the available glyphs. |
| `"invalid_color"` | rejection | The supplied marker color is not one of the available colors. |
| `"invalid_text"` | rejection | The supplied text is longer than the field allows. |
| `"limit_reached"` | rejection | The collection already holds its maximum number of entries. |

##### `.get(id: str) → Marker | None`

Read one marker by id.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `id` | `str` | Marker id to look up. |

- **Returns** The `Marker` with that id, or `None` when no marker uses it.

*Raises*

| Exception | Condition |
| --- | --- |
| `ValueError` | The marker id must be 1-64 characters using letters, numbers, `_`, `.`, `:`, or `-`, and cannot be a reserved object-field name. |

##### `.list(prefix: str = "") → list[Marker]`

Read markers as a list sorted by id. Pass a prefix such as `"build."` to read one family. Loop the result to route a vehicle: `for m in markers.list("build."): self.nav.set_target(m.x, m.y)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `prefix` | `str` | Optional id prefix such as `"survey.rover_1."`. |

- **Returns** List of `Marker` values sorted by id, optionally narrowed to one id prefix. Empty prefix returns every marker.

*Raises*

| Exception | Condition |
| --- | --- |
| `ValueError` | The marker prefix must use letters, numbers, `_`, `.`, `:`, or `-` and be at most 64 characters. |

##### `.remove(id: str) → ActionResult`

Delete one marker by id.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `id` | `str` | Marker id to delete. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_found"` | rejection | The requested object, target, or record does not exist. |
| `"invalid_key"` | rejection | The supplied key is invalid. |

##### `.clear(prefix: str) → CountResult`

Delete a whole family of markers by id prefix, then place the current ones again to keep a family in step with what your script now believes. The prefix is required: `markers.clear("")` deletes every marker on the planet, including the ones you placed by hand, and nothing records who placed what.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `prefix` | `str` | Id prefix to delete. Pass `""` to delete every marker, including the ones you placed by hand. |

- **Returns** `CountResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.count`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The command affected `.count` entries or units. |
| `"no_op"` | success | The command affected no entries or units. |
| `"invalid_key"` | rejection | The supplied key is invalid. |

*Components / Exploration*
