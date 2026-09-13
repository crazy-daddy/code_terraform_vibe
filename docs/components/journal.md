# Component: journal

> **Category:** Exploration | **Component Name:** Journal

Stores sites found or surveyed by sonar and fragments cataloged by Bio Labs. Access it with `get_component("journal")` to plan trips and Bio Orders without scanning again. Records are separated by planet and survive script restarts, vehicle changes, and save/load.

**Returned by:** `get_component("journal")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.discovered_sites(planet_id)`

Lists every site classified by sonar on `planet_id`. Call `journal.discovered_sites("nocturna")` for Nocturna. Each entry is a `MiningSite`, `ThermalVent`, `WaterWell`, `OilWell`, `ExoticDeposit`, or `GeologicalAnomaly`, according to `kind()`. Unsurveyed productive sites leave their detailed fields as `None`; inert formations are resolved by scanning. Duplicate scans do not add duplicate entries. Returns an empty list before any sites are found. See `Site`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `planet_id` | `string` | Journal planet id; the current planet is usually "nocturna". |

- **Returns** List of classified `Site` values for that planet. Each concrete type follows `kind()`. Unsurveyed productive sites leave detailed fields as `None`; inert formations are resolved by scanning. Query again for current survey, cycle, and cap data.

##### `.surveyed_sites(planet_id)`

Every fully-resolved site on `planet_id` as `list<Site>`, same shape as `discovered_sites()`, filtered to `surveyed == True`. This includes inert `GeologicalAnomaly` contacts because sonar resolves them without a second survey. Branch on `kind()` to access fields: `MiningSite` exposes `.item_id`, `.hardness`, `.purity`; `ThermalVent` exposes phase / rate / cycle timing (gated by sonar tier); `WaterWell` / `OilWell` expose `.yield_tier`, `.flow_rate`. See `Site`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `planet_id` | `string` | Journal planet id; the current planet is usually "nocturna". |

- **Returns** List of fully resolved `Site` snapshots, including inert formations resolved by a scan. Uses the same types as `discovered_sites()`, filtered to `surveyed == True`. Query again for current cycle and cap data.

##### `.cataloged_fragments(planet_id)`

Lists fragments analyzed at a Bio Lab on `planet_id`, newest first. Each `CatalogedFragment` includes its stable fragment id, display name, biome, coordinates, and rarity. Match `entry.fragment_id` against `BioOrder.requires`, and pass `entry.coords` to `bio_collector.collect(...)`. Unanalyzed fragments and creature identity remain hidden. After all five fragments are cataloged, the completed creature appears in `journal.cataloged_creatures(planet_id)`. Returns an empty list for a different planet.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `planet_id` | `string` | Journal planet id; the current planet is usually "nocturna". |

- **Returns** List of `CatalogedFragment`: every fragment you've analyzed at a Bio Lab on that planet, including its stable `.fragment_id` and player-facing `.name`. Sorted **most-recently-cataloged first**. Returns `[]` for any planet other than the current one.

##### `.cataloged_creatures(planet_id)`

Lists creatures whose five fragments have all been analyzed on `planet_id`, most recently completed first. Each `CatalogedCreature` provides the stable creature id, its five fragment ids, required feed item and Feed Maker recipe, minimum startup feed, and exact rarity-scaled revival reagents. Use `.creature_id` with `habitat.set_revival_target(...)`. Use `.feed_recipe_id` to find the matching unlocked `Recipe` in `feed_maker.list_recipes()`; recipe ingredients remain owned by that Recipe. Returns an empty list for a different planet.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `planet_id` | `string` | Journal planet id; the current planet is usually "nocturna". |

- **Returns** List of `CatalogedCreature`: every creature whose five fragments have been analyzed on that planet, with the ids and exact startup supplies needed by a generic Habitat revival script. Sorted **most-recently-completed first**. Returns `[]` for any planet other than the current one.

##### `.coord_info(x, y)`

Read the saved `LifeFormScanResult` for a discovered permanent biosite coordinate. Returns `None` for untouched biosites and scanned coordinates that are not sites. The query returns immediately.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | Whole-number world x |
| `y` | `number` | Whole-number world y |

- **Returns** `LifeFormScanResult` for permanent biosite `(x, y)` if it has been scanned. Returns `None` if untouched or not a biosite. Cheap; no yield.

##### `.biomass_coords()`

Lists every discovered permanent biosite as a `LifeFormScanResult`. This is the restart-safe route source for harvester drones: inspect `.coord`, each sample's `.remaining_tons`, and `is_ready(x, y)` before dispatching.

- **Returns** List of every discovered permanent biosite as `LifeFormScanResult` snapshots. Use each `.coord`, `.life_forms`, and `.remaining_tons` to schedule drone harvest routes.

##### `.has_scanned(x, y)`

`True` after the whole-number coordinate `(x, y)` has been scanned. Use it to skip biosites already visited by a route that resumes across script restarts.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | Whole-number world x |
| `y` | `number` | Whole-number world y |

- **Returns** Boolean: `True` if you've scanned this whole-number coordinate.

##### `.is_empty(x, y)`

`True` only when this whole-number tile has been scanned and contained no life forms. Returns `False` for both occupied and untouched tiles, so pair it with `has_scanned()`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | Whole-number world x |
| `y` | `number` | Whole-number world y |

- **Returns** Boolean: `True` only when you scanned this whole-number coordinate and it was not a biosite.

##### `.is_ready(x, y)`

`True` when a discovered biosite can be extracted now. Returns `False` while another drone is extracting there, after depletion, or during its rarity-based cooldown. The query uses current site state and returns immediately.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | Biosite world x |
| `y` | `number` | Biosite world y |

- **Returns** Boolean: `True` if a discovered biosite has stock or its cooldown has elapsed, and no extraction is currently in progress there.

##### `.next_ready_at(x, y)`

When the extraction cooldown ends, as an absolute hour. A depleted site's timestamp remains even after that hour passes, until extraction replenishes it. Returns `None` if the biosite is not recorded, still has material, or has never been extracted. Use `is_ready(x, y)` to check whether extraction can begin now.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | Biosite world x |
| `y` | `number` | Biosite world y |

- **Returns** Absolute hour when a depleted biosite's extraction cooldown ends. The deadline may already be in the past until extraction replenishes the site. Returns `None` if the site is not recorded, material remains, or it has never been extracted.

*Components / Exploration*
