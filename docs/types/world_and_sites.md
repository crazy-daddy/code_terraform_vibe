# Data Types: World And Sites

Complete property specifications, descriptions, units, and return types from the official documentation.

## Index

- [`Outpost`](#outpost) (WORLD & SITES)
- [`OutpostNetwork`](#outpostnetwork) (WORLD & SITES)
- [`OutpostRef`](#outpostref) (WORLD & SITES)
- [`BuildingRef`](#buildingref) (WORLD & SITES)
- [`HarvestingMachineRef`](#harvestingmachineref) (WORLD & SITES)
- [`Planet`](#planet) (WORLD & SITES)
- [`ScanResult`](#scanresult) (WORLD & SITES)
- [`Site`](#site) (WORLD & SITES)
- [`ExoticDeposit`](#exoticdeposit) (WORLD & SITES)
- [`GeologicalAnomaly`](#geologicalanomaly) (WORLD & SITES)
- [`MiningSite`](#miningsite) (WORLD & SITES)
- [`OilWell`](#oilwell) (WORLD & SITES)
- [`ThermalVent`](#thermalvent) (WORLD & SITES)
- [`WaterWell`](#waterwell) (WORLD & SITES)

---

## Outpost

**Returned by:** get_component(outpost_id) / get_component_by_name(outpost_name)

### Properties

##### `.id: str`

Immutable instance id (e.g. `"outpost_home"`, `"outpost_1"`). Stable for the life of the save: use this in scripts that need to outlive renames.

- **Returns** `str`

### Methods

##### `.name() → str`

Display name. Defaults to `"Nocturna Base"` for the home outpost or a generated `"Outpost N"` name for founded outposts; freely renameable from the Computer System tab. Mutable: prefer `id` when persistence matters.

- **Returns** `str`

##### `.coords() → list[int]`

World coordinates of the outpost anchor as `[x, y]`. Home outpost sits at `[0, 0]`; founded outposts carry the position chosen in Plan mode.

- **Returns** `list[int]`

##### `.buildings_used() → int`

Number of buildings deployed at this outpost. Sensors, mobile units, structural hubs, and POI extraction don't count.

- **Returns** `int`

##### `.buildings_capacity() → int`

Soft building threshold at this outpost. Each counted building above it reduces productive and service throughput. Nocturna Base has a few extra starter slots; founded outposts use the standard threshold.

- **Returns** `int`

##### `.is_full() → bool`

Returns `True` when this outpost has reached or exceeded its soft building threshold. The threshold itself does not block ordinary deployment.

- **Returns** `bool`

##### `.is_home() → bool`

Returns `True` when this is the home outpost (default name `"Nocturna Base"`).

- **Returns** `bool`

##### `.buildings(type_id?: str) → list[BuildingRef]`

Fresh list of `BuildingRef` snapshots: one entry per building deployed here. Pass a `type_id` (e.g. `"storage_bin"`) to filter, or omit for every building. Each ref carries `.id` / `.name` / `.type_id` / `.outpost` / `.powered` / `.position`: for type-specific live reads (`count()`, `material()`, `recipe`, etc.) call `get_component(ref.id)` to reach the full component API.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `type_id` | `str` | Optional. Machine type id to filter by (e.g. "storage_bin"). Omit to return every building at this outpost. |

- **Returns** `list[BuildingRef]`

##### `.harvesting_machines(type_id?: str) → list[HarvestingMachineRef]`

Fresh list of `HarvestingMachineRef` snapshots for fixed machines deployed on this outpost's Harvesting field. Currently only the home outpost, Nocturna Base, has that field, so founded outposts return an empty list. Includes Grow Lamps, Sprinklers, Dispensers, and Crop Automators, which occupy field cells but do not use building capacity or appear in `buildings()`. It does not include the mobile Harvester, crops, loose items, Water Wells, or other POI extractors. Pass a `type_id` to filter, or omit it for all four fixed machine types. Use `get_component(ref.id)` for type-specific live reads.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `type_id` | `str` | Optional fixed Harvesting-field machine type id: `"grow_lamp"`, `"sprinkler"`, `"dispenser"`, or `"crop_automator"`. Omit it to return every fixed machine deployed on the field. |

- **Returns** `list[HarvestingMachineRef]`

*Types / World & Sites*

## OutpostNetwork

**Returned by:** get_component("outpost_network")

### Related object types

- `OutpostRef`

### Methods

##### `.outposts() → list[OutpostRef]`

All owned outposts as read-only `OutpostRef` snapshots, including home. Use `.id` when passing an outpost to another API; call `outposts()` again when you need fresh counts/names.

- **Returns** `list[OutpostRef]`

##### `.home() → OutpostRef`

The home outpost as an `OutpostRef` snapshot.

- **Returns** `OutpostRef`

##### `.nearest(x: float, y: float) → OutpostRef`

Nearest owned outpost to the given world coordinate as an `OutpostRef` snapshot.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | World X coordinate |
| `y` | `float` | World Y coordinate |

- **Returns** `OutpostRef`

*Types / World & Sites*

## OutpostRef

**Returned by:** outpost_network.outposts() / outpost_network.home() / outpost_network.nearest()

### Related object types

- `BuildingRef`
- `HarvestingMachineRef`

### Properties

##### `.id: str`

Immutable outpost id, e.g. `"outpost_home"` or `"outpost_1"`. Use it with `get_component(id)` or APIs that need a stable target.

- **Returns** `str`

##### `.name: str`

Display name at the time this ref was returned.

- **Returns** `str`

##### `.x: int`

World X coordinate of the outpost footprint's top-left anchor, in meters from base. For an at-building action, route to that building's `BuildingRef.position` instead.

- **Returns** `int`

##### `.y: int`

World Y coordinate of the outpost footprint's top-left anchor, in meters from base. For an at-building action, route to that building's `BuildingRef.position` instead.

- **Returns** `int`

##### `.is_home: bool`

`True` for the home outpost.

- **Returns** `bool`

##### `.biome: str`

Biome this outpost sits in: one of `"frozen"`, `"coastal"`, `"geothermal"`, `"volcanic"`, `"deep"`. Derived from the outpost's location. A building reaches its own biome via `self.outpost.biome`.

- **Returns** `str`
- **Possible values** `"frozen"`, `"coastal"`, `"geothermal"`, `"volcanic"`, `"deep"`

##### `.buildings_used: int`

Buildings deployed at this outpost when this ref was returned.

- **Returns** `int`

##### `.buildings_capacity: int`

Soft building threshold at this outpost when this ref was returned. Buildings above it reduce productive and service throughput.

- **Returns** `int`

##### `.is_full: bool`

`True` when this outpost had reached or exceeded its soft building threshold at the time this ref was returned. The threshold itself does not block ordinary deployment.

- **Returns** `bool`

### Methods

##### `.position() → Position`

Top-left anchor of the outpost footprint as a `Position` snapshot. This identifies the outpost, not a particular building's docking point.

- **Returns** `Position`

##### `.coords() → list[int]`

Top-left anchor of the outpost footprint as `[x, y]`. Use `buildings()` and `BuildingRef.position` when routing to a particular service building.

- **Returns** `list[int]`

##### `.buildings(type_id?: str) → list[BuildingRef]`

Fresh list of `BuildingRef` snapshots: one entry per building deployed here. Pass a `type_id` (e.g. `"storage_bin"`) to filter, or omit for every building. Each ref carries `.id` / `.name` / `.type_id` / `.outpost` / `.powered` / `.position`: for type-specific live reads (`count()`, `material()`, `recipe`, etc.) call `get_component(ref.id)` to reach the full component API.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `type_id` | `str` | Optional. Machine type id to filter by (e.g. "storage_bin"). Omit to return every building at this outpost. |

- **Returns** `list[BuildingRef]`

##### `.harvesting_machines(type_id?: str) → list[HarvestingMachineRef]`

Fresh list of `HarvestingMachineRef` snapshots for fixed machines deployed on this outpost's Harvesting field. Currently only the home outpost, Nocturna Base, has that field, so founded outposts return an empty list. Includes Grow Lamps, Sprinklers, Dispensers, and Crop Automators, which occupy field cells but do not use building capacity or appear in `buildings()`. It does not include the mobile Harvester, crops, loose items, Water Wells, or other POI extractors. Pass a `type_id` to filter, or omit it for all four fixed machine types. Use `get_component(ref.id)` for type-specific live reads.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `type_id` | `str` | Optional fixed Harvesting-field machine type id: `"grow_lamp"`, `"sprinkler"`, `"dispenser"`, or `"crop_automator"`. Omit it to return every fixed machine deployed on the field. |

- **Returns** `list[HarvestingMachineRef]`

*Types / World & Sites*

## BuildingRef

**Returned by:** outpost.buildings() / outpost_network.outposts()[i].buildings()

### Properties

##### `.id: str`

Stable component id. Use with `get_component(id)` to reach the full machine API (counts, recipes, materials, etc.).

- **Returns** `str`

##### `.name: str`

Display name when this ref was returned (e.g. `"Iron Ore Bin"`). For fresh names or live machine state, call `get_component(id)`.

- **Returns** `str`

##### `.type_id: str`

Machine type id, e.g. `"storage_bin"`, `"smelter"`, `"solar_generator"`. Stable forever; use this for branching logic.

- **Returns** `str`

##### `.outpost_id: str`

Id of the outpost this building is deployed at.

- **Returns** `str`

##### `.outpost: OutpostRef | None`

Snapshot back-reference to the owning outpost as an `OutpostRef` (or `None` if the link can't be resolved).

- **Returns** `OutpostRef | None`

##### `.powered: bool`

`True` when the building's power toggle was on as this ref was returned. For live power/production reads, call `get_component(id)`.

- **Returns** `bool`

##### `.position: list[float]`

World coordinates as `[x, y]`. For most buildings this is the deploy anchor; doesn't move.

- **Returns** `list[float]`

*Types / World & Sites*

## HarvestingMachineRef

**Returned by:** outpost.harvesting_machines() / outpost_network.home().harvesting_machines()

### Properties

##### `.id: str`

Stable component id. Use with `get_component(id)` to reach the full Grow Lamp, Sprinkler, Dispenser, or Crop Automator API.

- **Returns** `str`

##### `.name: str`

Display name when this ref was returned. Call `get_component(id)` for current machine state.

- **Returns** `str`

##### `.type_id: str`

Fixed Harvesting-field machine type id: `"grow_lamp"`, `"sprinkler"`, `"dispenser"`, or `"crop_automator"`.

- **Returns** `str`
- **Possible values** `"grow_lamp"`, `"sprinkler"`, `"dispenser"`, `"crop_automator"`

##### `.powered: bool`

`True` when the machine's power toggle was on as this ref was returned. Call `get_component(id)` for live status and supply reads.

- **Returns** `bool`

##### `.position: str`

Harvesting-field sector occupied by the fixed machine, such as `"B22"`.

- **Returns** `str`

*Types / World & Sites*

## Planet

**Returned by:** transmitter.list_planets()

### Properties

##### `.id: str`

Planet id: pass this to transmitter.connect().

- **Returns** `str`

##### `.name: str`

Display name.

- **Returns** `str`

##### `.description: str`

Short planet description.

- **Returns** `str`

*Types / World & Sites*

## ScanResult

**Returned by:** scanner.scan(), harvester.collect()

### Properties

##### `.status: str`

Stable outcome code. Scanner results use `"ok"` / `"empty"`; Harvester results can also report `"holding"`, `"overheated"`, `"moving"` (in transit), `"busy"` (occupied by another action), or `"collecting"`.

- **Returns** `str`
- **Possible values** `"ok"`, `"empty"`, `"holding"`, `"overheated"`, `"moving"`, `"busy"`, `"collecting"`

##### `.message: str`

Player-readable explanation of the scan or collection outcome.

- **Returns** `str`

##### `.id: str`

Item ID at the scanned sector (empty string if nothing).

- **Returns** `str`

##### `.name: str`

Item display name.

- **Returns** `str`

##### `.value: float`

Credit value of the item.

- **Returns** `float`

*Types / World & Sites*

## Site

*abstract*

**Returned by:** SonarModule.scan().sites / SonarModule.survey().site / journal and site-bound machine queries

### Concrete subtypes

- `ExoticDeposit`
- `GeologicalAnomaly`
- `MiningSite`
- `OilWell`
- `ThermalVent`
- `WaterWell`

### Properties

##### `.id: str`

Unique site identifier.

- **Returns** `str`

##### `.name: str`

Human-readable display name.

- **Returns** `str`

##### `.x: float`

Site X coordinate in meters from base.

- **Returns** `float`

##### `.y: float`

Site Y coordinate in meters from base.

- **Returns** `float`

##### `.surveyed: bool`

Survey flag captured when this object was returned; resolved inert contacts also report `True`. The property never updates. Mining-site fields are snapshots. Well, vent and exotic-deposit methods read live, except on pre-survey sonar results: those keep their hidden values, so obtain a new object after surveying.

- **Returns** `bool`

### Methods

##### `.kind() → str`

One of `"mineral"` / `"thermal"` / `"water"` / `"oil"` / `"exotic"` / `"inert"`. Use it to narrow to the concrete subtype: after `if site.kind() == "mineral":` the editor surfaces `MiningSite`-specific fields on `site`. `"inert"` means sonar resolved a physical formation with no extractable signal.

- **Returns** `str`
- **Possible values** `"mineral"`, `"thermal"`, `"water"`, `"oil"`, `"exotic"`, `"inert"`

##### `.position() → Position`

`Position` snapshot with `.x` / `.y` world coordinates.

- **Returns** `Position`

*Types / World & Sites*

## ExoticDeposit

Extends `Site`

**Returned by:** any Site-returning API where `kind() == "exotic"` (e.g. `exotic_gas_cap.deposit()`, `exotic_spring_tap.deposit()`, sonar / journal queries)

### Properties

##### `.id: str`

Unique site identifier.

- **Returns** `str`

##### `.name: str`

Human-readable display name.

- **Returns** `str`

##### `.x: float`

Site X coordinate in meters from base.

- **Returns** `float`

##### `.y: float`

Site Y coordinate in meters from base.

- **Returns** `float`

##### `.surveyed: bool`

Survey flag captured when this object was returned; resolved inert contacts also report `True`. The property never updates. Mining-site fields are snapshots. Well, vent and exotic-deposit methods read live, except on pre-survey sonar results: those keep their hidden values, so obtain a new object after surveying.

- **Returns** `bool`

### Methods

##### `.kind() → str`

One of `"mineral"` / `"thermal"` / `"water"` / `"oil"` / `"exotic"` / `"inert"`. Use it to narrow to the concrete subtype: after `if site.kind() == "mineral":` the editor surfaces `MiningSite`-specific fields on `site`. `"inert"` means sonar resolved a physical formation with no extractable signal.

- **Returns** `str`
- **Possible values** `"mineral"`, `"thermal"`, `"water"`, `"oil"`, `"exotic"`, `"inert"`

##### `.position() → Position`

`Position` snapshot with `.x` / `.y` world coordinates.

- **Returns** `Position`

##### `.fluid() → str | None`

Fluid id this deposit emits, e.g. `"ammonia"` (common, usable direct) or `"raw_chlorine"` (rare, needs the Refiner). `None` until `surveyed`.

- **Returns** `str | None`
- **Possible values** `"ammonia"`, `"swamp_gas"`, `"raw_sulfur_gas"`, `"raw_chlorine"`, `"brine"`, `"raw_cryofluid"`, `"raw_quicksilver"`

##### `.medium() → str | None`

`"gas"` (tap with an **Exotic Gas Cap**) or `"liquid"` (tap with an **Exotic Spring Tap**). `None` until `surveyed`.

- **Returns** `str | None`
- **Possible values** `"gas"`, `"liquid"`

##### `.rarity() → str | None`

`"common"` emits the usable fluid with no refining; `"uncommon"` and `"rare"` emit a raw feedstock the Refiner converts with tar. Rarer deposits are sparser and stay dormant longer. `None` until `surveyed`.

- **Returns** `str | None`
- **Possible values** `"common"`, `"uncommon"`, `"rare"`

##### `.survey_level() → str | None`

Highest survey tier achieved on this deposit: `"basic"` / `"wide"` / `"deep"`, or `None` if not yet surveyed. Reads live: a deeper re-survey upgrades held Site objects too. Higher tiers unlock more fields below. A pre-survey sonar result stays unrevealed; obtain a new object after surveying.

- **Returns** `str | None`
- **Possible values** `"basic"`, `"wide"`, `"deep"`

##### `.current_phase() → str | None`

The deposit's phase right now: `"active"` (emitting) or `"dormant"` (idle). Reads live: poll it from a held Site object and it follows the cycle. Returns `None` before the deposit is surveyed. A pre-survey sonar result stays unrevealed; obtain a new object after surveying.

- **Returns** `str | None`
- **Possible values** `"active"`, `"dormant"`

##### `.cycle_active_minutes() → float | None`

Duration of the active phase in minutes. Requires **deep** survey: returns `None` otherwise.

- **Returns** `float | None`

##### `.cycle_dormant_minutes() → float | None`

Duration of the dormant phase in minutes (rare deposits stay dormant longest). Requires **deep** survey: returns `None` otherwise.

- **Returns** `float | None`

##### `.next_phase_in() → float | None`

Game-minutes until the next phase flip. Reads live: poll it in a control loop to act before dormancy hits. Requires **deep** survey: returns `None` otherwise. A pre-survey sonar result stays unrevealed; obtain a new object after surveying.

- **Returns** `float | None`

##### `.base_rate() → float | None`

Peak output rate during the active phase (t/h). Requires **wide** survey: returns `None` at basic.

- **Returns** `float | None`

##### `.current_rate() → float | None`

Output rate right now (t/h: **0** during dormant). Reads live. Requires **wide** survey: returns `None` at basic. A pre-survey sonar result stays unrevealed; obtain a new object after surveying.

- **Returns** `float | None`

##### `.has_cap() → bool`

Boolean: `True` if an Exotic Gas Cap or Exotic Spring Tap is currently deployed on this deposit. Reads live. A pre-survey sonar result stays unrevealed; obtain a new object after surveying.

- **Returns** `bool`

##### `.cap_id() → str`

Machine id of the currently deployed cap/tap, or empty string when none is present. Reads live. A pre-survey sonar result stays unrevealed; obtain a new object after surveying.

- **Returns** `str`

*Types / World & Sites*

## GeologicalAnomaly

Extends `Site`

**Returned by:** any Site-returning API where `kind() == "inert"`

### Properties

##### `.id: str`

Unique site identifier.

- **Returns** `str`

##### `.name: str`

Human-readable display name.

- **Returns** `str`

##### `.x: float`

Site X coordinate in meters from base.

- **Returns** `float`

##### `.y: float`

Site Y coordinate in meters from base.

- **Returns** `float`

##### `.surveyed: bool`

Survey flag captured when this object was returned; resolved inert contacts also report `True`. The property never updates. Mining-site fields are snapshots. Well, vent and exotic-deposit methods read live, except on pre-survey sonar results: those keep their hidden values, so obtain a new object after surveying.

- **Returns** `bool`

### Methods

##### `.kind() → str`

One of `"mineral"` / `"thermal"` / `"water"` / `"oil"` / `"exotic"` / `"inert"`. Use it to narrow to the concrete subtype: after `if site.kind() == "mineral":` the editor surfaces `MiningSite`-specific fields on `site`. `"inert"` means sonar resolved a physical formation with no extractable signal.

- **Returns** `str`
- **Possible values** `"mineral"`, `"thermal"`, `"water"`, `"oil"`, `"exotic"`, `"inert"`

##### `.position() → Position`

`Position` snapshot with `.x` / `.y` world coordinates.

- **Returns** `Position`

*Types / World & Sites*

## MiningSite

Extends `Site`

**Returned by:** any Site-returning API where `kind() == "mineral"`

### Properties

##### `.id: str`

Unique site identifier.

- **Returns** `str`

##### `.name: str`

Human-readable display name.

- **Returns** `str`

##### `.x: float`

Site X coordinate in meters from base.

- **Returns** `float`

##### `.y: float`

Site Y coordinate in meters from base.

- **Returns** `float`

##### `.surveyed: bool`

Survey flag captured when this object was returned; resolved inert contacts also report `True`. The property never updates. Mining-site fields are snapshots. Well, vent and exotic-deposit methods read live, except on pre-survey sonar results: those keep their hidden values, so obtain a new object after surveying.

- **Returns** `bool`

##### `.item_id: str | None`

Item id this site yields when drilled (e.g. `"iron_ore"`, `"silicon"`). `None` until `surveyed`.

- **Returns** `str | None`
- **Possible values** `"iron_ore"`, `"silicon"`, `"titanium"`, `"cobalt"`, `"rare_earth"`, `"neutronium"`, `"lead_ore"`

##### `.hardness: int | None`

Hardness rating (**1-4**): gates drill compatibility. `None` until `surveyed`.

- **Returns** `int | None`

##### `.purity: str | None`

Yield multiplier tier: `"standard"` (**1×**) / `"rich"` (**2×**) / `"pure"` (**3×**). `None` until `surveyed`.

- **Returns** `str | None`
- **Possible values** `"standard"`, `"rich"`, `"pure"`

### Methods

##### `.kind() → str`

One of `"mineral"` / `"thermal"` / `"water"` / `"oil"` / `"exotic"` / `"inert"`. Use it to narrow to the concrete subtype: after `if site.kind() == "mineral":` the editor surfaces `MiningSite`-specific fields on `site`. `"inert"` means sonar resolved a physical formation with no extractable signal.

- **Returns** `str`
- **Possible values** `"mineral"`, `"thermal"`, `"water"`, `"oil"`, `"exotic"`, `"inert"`

##### `.position() → Position`

`Position` snapshot with `.x` / `.y` world coordinates.

- **Returns** `Position`

*Types / World & Sites*

## OilWell

Extends `Site`

**Returned by:** any Site-returning API where `kind() == "oil"` (e.g. `oil_pump.well()`, sonar / journal queries)

### Properties

##### `.id: str`

Unique site identifier.

- **Returns** `str`

##### `.name: str`

Human-readable display name.

- **Returns** `str`

##### `.x: float`

Site X coordinate in meters from base.

- **Returns** `float`

##### `.y: float`

Site Y coordinate in meters from base.

- **Returns** `float`

##### `.surveyed: bool`

Survey flag captured when this object was returned; resolved inert contacts also report `True`. The property never updates. Mining-site fields are snapshots. Well, vent and exotic-deposit methods read live, except on pre-survey sonar results: those keep their hidden values, so obtain a new object after surveying.

- **Returns** `bool`

### Methods

##### `.kind() → str`

One of `"mineral"` / `"thermal"` / `"water"` / `"oil"` / `"exotic"` / `"inert"`. Use it to narrow to the concrete subtype: after `if site.kind() == "mineral":` the editor surfaces `MiningSite`-specific fields on `site`. `"inert"` means sonar resolved a physical formation with no extractable signal.

- **Returns** `str`
- **Possible values** `"mineral"`, `"thermal"`, `"water"`, `"oil"`, `"exotic"`, `"inert"`

##### `.position() → Position`

`Position` snapshot with `.x` / `.y` world coordinates.

- **Returns** `Position`

##### `.yield_tier() → str | None`

One of `"standard"` (**1×**) / `"rich"` (**2×**) / `"pure"` (**3×**). `None` until surveyed. Checks current survey progress, except on a pre-survey sonar result, which keeps returning `None`; obtain a new object after surveying.

- **Returns** `str | None`
- **Possible values** `"standard"`, `"rich"`, `"pure"`

##### `.flow_rate() → float | None`

Peak tons of oil per hour. **8 / 16 / 24** for standard / rich / pure. Oil wells pulse through active and dormant phases: a dormant well delivers nothing at any throttle (read the pump's `well_active()`). `None` until surveyed. Reads live, except on a pre-survey sonar result, which keeps returning `None`; obtain a new object after surveying.

- **Returns** `float | None`

##### `.has_pump() → bool`

Boolean: `True` if an Oil Pump is currently deployed on this well. A pre-survey sonar result always returns `False`; obtain a new object after surveying for live readings.

- **Returns** `bool`

##### `.pump_id() → str`

Current machine id of the Oil Pump deployed on this well, or empty string when no pump is present. A pre-survey sonar result always returns empty string; obtain a new object after surveying for live readings.

- **Returns** `str`

*Types / World & Sites*

## ThermalVent

Extends `Site`

**Returned by:** any Site-returning API where `kind() == "thermal"` (e.g. `thermal_cap.vent()`, sonar / journal queries)

### Properties

##### `.id: str`

Unique site identifier.

- **Returns** `str`

##### `.name: str`

Human-readable display name.

- **Returns** `str`

##### `.x: float`

Site X coordinate in meters from base.

- **Returns** `float`

##### `.y: float`

Site Y coordinate in meters from base.

- **Returns** `float`

##### `.surveyed: bool`

Survey flag captured when this object was returned; resolved inert contacts also report `True`. The property never updates. Mining-site fields are snapshots. Well, vent and exotic-deposit methods read live, except on pre-survey sonar results: those keep their hidden values, so obtain a new object after surveying.

- **Returns** `bool`

### Methods

##### `.kind() → str`

One of `"mineral"` / `"thermal"` / `"water"` / `"oil"` / `"exotic"` / `"inert"`. Use it to narrow to the concrete subtype: after `if site.kind() == "mineral":` the editor surfaces `MiningSite`-specific fields on `site`. `"inert"` means sonar resolved a physical formation with no extractable signal.

- **Returns** `str`
- **Possible values** `"mineral"`, `"thermal"`, `"water"`, `"oil"`, `"exotic"`, `"inert"`

##### `.position() → Position`

`Position` snapshot with `.x` / `.y` world coordinates.

- **Returns** `Position`

##### `.survey_level() → str | None`

Highest survey tier achieved on this vent: `"basic"` / `"wide"` / `"deep"`, or `None` if not yet surveyed. Reads live: a deeper re-survey upgrades held Site objects too. Higher tiers unlock more fields below. A pre-survey sonar result stays unrevealed; obtain a new object after surveying.

- **Returns** `str | None`
- **Possible values** `"basic"`, `"wide"`, `"deep"`

##### `.cycle_active_minutes() → float | None`

Duration of the active phase in minutes. Requires **deep** survey: returns `None` otherwise.

- **Returns** `float | None`

##### `.cycle_dormant_minutes() → float | None`

Duration of the dormant phase in minutes. Requires **deep** survey: returns `None` otherwise.

- **Returns** `float | None`

##### `.current_phase() → str | None`

The vent's phase right now: `"active"` or `"dormant"`. Reads live: poll it from a held Site object and it follows the cycle. Returns `None` before the vent is surveyed. A pre-survey sonar result stays unrevealed; obtain a new object after surveying.

- **Returns** `str | None`
- **Possible values** `"active"`, `"dormant"`

##### `.next_phase_in() → float | None`

Game-minutes until the next phase flip. Reads live: poll it in a control loop to act before dormancy hits. Requires **deep** survey: returns `None` otherwise. A pre-survey sonar result stays unrevealed; obtain a new object after surveying.

- **Returns** `float | None`

##### `.base_steam_rate() → float | None`

Peak steam rate during active phase (t/h). Requires **wide** survey: returns `None` at basic.

- **Returns** `float | None`

##### `.current_steam_rate() → float | None`

Steam rate right now (t/h: **0** during dormant phase). Reads live. Requires **wide** survey: returns `None` at basic. A pre-survey sonar result stays unrevealed; obtain a new object after surveying.

- **Returns** `float | None`

##### `.has_cap() → bool`

Boolean: `True` if a Thermal Cap is currently deployed on this vent. Reads live. A pre-survey sonar result stays unrevealed; obtain a new object after surveying.

- **Returns** `bool`

##### `.cap_id() → str`

Machine id of the currently deployed Thermal Cap, or empty string when no cap is present. Reads live. A pre-survey sonar result stays unrevealed; obtain a new object after surveying.

- **Returns** `str`

*Types / World & Sites*

## WaterWell

Extends `Site`

**Returned by:** any Site-returning API where `kind() == "water"` (e.g. `water_pump.well()`, sonar / journal queries)

### Properties

##### `.id: str`

Unique site identifier.

- **Returns** `str`

##### `.name: str`

Human-readable display name.

- **Returns** `str`

##### `.x: float`

Site X coordinate in meters from base.

- **Returns** `float`

##### `.y: float`

Site Y coordinate in meters from base.

- **Returns** `float`

##### `.surveyed: bool`

Survey flag captured when this object was returned; resolved inert contacts also report `True`. The property never updates. Mining-site fields are snapshots. Well, vent and exotic-deposit methods read live, except on pre-survey sonar results: those keep their hidden values, so obtain a new object after surveying.

- **Returns** `bool`

### Methods

##### `.kind() → str`

One of `"mineral"` / `"thermal"` / `"water"` / `"oil"` / `"exotic"` / `"inert"`. Use it to narrow to the concrete subtype: after `if site.kind() == "mineral":` the editor surfaces `MiningSite`-specific fields on `site`. `"inert"` means sonar resolved a physical formation with no extractable signal.

- **Returns** `str`
- **Possible values** `"mineral"`, `"thermal"`, `"water"`, `"oil"`, `"exotic"`, `"inert"`

##### `.position() → Position`

`Position` snapshot with `.x` / `.y` world coordinates.

- **Returns** `Position`

##### `.yield_tier() → str | None`

One of `"standard"` (**1×**) / `"rich"` (**2×**) / `"pure"` (**3×**). `None` until surveyed. Checks current survey progress, except on a pre-survey sonar result, which keeps returning `None`; obtain a new object after surveying. Wells reveal fully on basic survey.

- **Returns** `str | None`
- **Possible values** `"standard"`, `"rich"`, `"pure"`

##### `.flow_rate() → float | None`

Tons of water per hour this well produces. **10 / 20 / 30** for standard / rich / pure. `None` until surveyed. Reads live, except on a pre-survey sonar result, which keeps returning `None`; obtain a new object after surveying.

- **Returns** `float | None`

##### `.has_pump() → bool`

Boolean: `True` if a Water Pump is currently deployed on this well. A pre-survey sonar result always returns `False`; obtain a new object after surveying for live readings.

- **Returns** `bool`

##### `.pump_id() → str`

Current machine id of the Water Pump deployed on this well, or empty string when no pump is present. A pre-survey sonar result always returns empty string; obtain a new object after surveying for live readings.

- **Returns** `str`

*Types / Storage & Inventory*
