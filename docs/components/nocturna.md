# Component: nocturna

> **Category:** Core Systems | **Component Name:** Nocturna

Provides stable planet-wide data for Nocturna through `get_component("nocturna")`, including map bounds, biomes, terraforming progress, and permanent map contacts. Hidden weather aftermaths are deliberately absent; their coordinates exist only in the storm packets your station network captures. Sonar discoveries and surveys are stored separately in `get_component("journal")`.

**Returned by:** `get_component("nocturna")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.get_name() → str`

Display name of this planet, returns `"Nocturna"`. Safe to hardcode, but querying future-proofs scripts against rename or multi-planet expansion.

- **Returns** String (display name)

##### `.get_bounds() → Bounds`

Surface coordinate bounds as a `Bounds` object with `.min_x`, `.max_x`, `.min_y`, `.max_y`, all in meters from base. Use to clamp nav targets inside the operational surface, or to generate random valid coordinates: `import random; b = planet.get_bounds(); x = random.randint(b.min_x, b.max_x); y = random.randint(b.min_y, b.max_y)`. See `Bounds`.

- **Returns** `Bounds` object with `.min_x`, `.max_x`, `.min_y`, `.max_y` (meters)

##### `.contains(x: float, y: float) → bool`

`True` if the point `(x, y)` is inside Nocturna's surface bounds. Use as a safety check before `nav.set_target()`: `if nocturna.contains(x, y): self.nav.set_target(x, y)`. Targeting outside the bounds returns immediately with no drive.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | X coordinate in meters |
| `y` | `float` | Y coordinate in meters |

- **Returns** Boolean: `True` if the point is inside the planet's surface bounds

##### `.biome_at(x: float, y: float) → str`

Biome id at the world coordinate `(x, y)`. Returns one of `"frozen"`, `"coastal"`, `"geothermal"`, `"volcanic"`, `"deep"`. Pure geography, same answer for the same coordinate forever. Use to script biome-aware behavior anywhere on the planet: `if nocturna.biome_at(x, y) == "volcanic": deploy_heat_resistant()`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | World x coordinate. |
| `y` | `float` | World y coordinate. |

- **Returns** Biome id at the coordinate: one of `"frozen"`, `"coastal"`, `"geothermal"`, `"volcanic"`, `"deep"`.
- **Possible values** `"frozen"`, `"coastal"`, `"geothermal"`, `"volcanic"`, `"deep"`

##### `.life_form_biome(item_id: str) → str | None`

Find the native biome for a life-form item: `"frozen"`, `"coastal"`, `"geothermal"`, `"volcanic"`, or `"deep"`. Returns `None` for other items. A species always belongs to the same biome, regardless of where the specimen was found. Essence Liquifiers accept only life forms native to their outpost, so a drone can test `nocturna.life_form_biome(item) == self.outpost.biome` before unloading.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `str` | A life-form item id, e.g. `"vent_fungus"`. |

- **Returns** Native biome id for the life form, or `None` for another item type. The value is fixed per species and matches the biome whose Essence Liquifier accepts it.
- **Possible values** `"frozen"`, `"coastal"`, `"geothermal"`, `"volcanic"`, `"deep"`

##### `.biomes() → list[str]`

Lists every biome id on the planet. Use it for planet-wide loops: `for biome in nocturna.biomes(): print(biome)`. The set never changes during play.

- **Returns** List of every biome id on the planet.

##### `.terraform_progress() → float`

Terraform Index progress on a **0-100%** scale: **0** is untouched; **100** means 1,000,000 TP and all six pillars are complete. Atmosphere owns 70% of the Index; biomass, plants, and wildlife each own a separate 10% that cannot substitute for another pillar. Gate progress logic with it: `if nocturna.terraform_progress() >= 50: ...`. For the raw TP value, use `total_tp()`.

- **Returns** Number: Terraform Index progress as a percent (**0-100**).

##### `.total_tp() → float`

The finite Terraform Index in TP, in the **0-1,000,000** range. Temperature, oxygen, and pressure together own 700,000 TP; biomass, plants, and wildlife each own a non-substitutable 100,000 TP. Raw metrics may keep growing after their final phase, but a completed pillar contributes no additional Index. The value gates cross-system research.

- **Returns** Number: finite Terraform Index points (**0-1,000,000**) used by cross-system research.

##### `.points_of_interest() → list[PointOfInterest]`

Lists every permanent "?" contact on the Planet Map so scripts can route to real sites. Each `PointOfInterest` has whole-number coordinates, a `scanned` flag, and a `kind` that stays `"unknown"` until a scanner reaches the contact. Filter for `not point.scanned`, travel to its coordinates, and scan with Rover or Pioneer sonar or a drone Bio Scanner. A contact the instrument you brought cannot identify stays unscanned even after a sweep that succeeded, and the sweep lists it in `scan.blocked` with the same coordinates and a reason: record those or your loop reselects the same contact. See `PointOfInterest`.

- **Returns** List of `PointOfInterest` records: every physical map contact (the "?" markers), each with `.x` / `.y` / `.scanned`. `.kind` reads `"unknown"` until you scan the contact.

*Components / Core Systems*
