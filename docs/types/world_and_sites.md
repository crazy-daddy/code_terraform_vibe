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

##### `.id`

Immutable instance id (e.g. `"outpost_home"`, `"outpost_1"`). Stable for the life of the save: use this in scripts that need to outlive renames.

- **Returns** `string`

### Methods

##### `.name()`

Display name. Defaults to `"Nocturna Base"` for the home outpost or a generated `"Outpost N"` name for founded outposts; freely renameable from the Computer System tab. Mutable: prefer `id` when persistence matters.

- **Returns** `string`

##### `.coords()`

World coordinates of the outpost anchor as `[x, y]`. Home outpost sits at `[0, 0]`; founded outposts carry the position chosen in Plan mode.

- **Returns** `[number, number]`

##### `.buildings_used()`

Number of buildings deployed at this outpost. Sensors, mobile units, structural hubs, and POI extraction don't count.

- **Returns** `number`

##### `.buildings_capacity()`

Soft building threshold at this outpost. Each counted building above it reduces productive and service throughput. Nocturna Base has a few extra starter slots; founded outposts use the standard threshold.

- **Returns** `number`

##### `.is_full()`

Returns `True` when this outpost has reached or exceeded its soft building threshold. The threshold itself does not block ordinary deployment.

- **Returns** `boolean`

##### `.is_home()`

Returns `True` when this is the home outpost (default name `"Nocturna Base"`).

- **Returns** `boolean`

##### `.buildings(type_id?)`

Fresh list of `BuildingRef` snapshots: one entry per building deployed here. Pass a `type_id` (e.g. `"storage_bin"`) to filter, or omit for every building. Each ref carries `.id` / `.name` / `.type_id` / `.outpost` / `.powered` / `.position`: for type-specific live reads (`count()`, `material()`, `recipe`, etc.) call `get_component(ref.id)` to reach the full component API.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `type_id` | `string` | Optional. Machine type id to filter by (e.g. "storage_bin"). Omit to return every building at this outpost. |

- **Returns** `list<BuildingRef>`

##### `.harvesting_machines(type_id?)`

Fresh list of `HarvestingMachineRef` snapshots for fixed machines deployed on this outpost's Harvesting field. Currently only the home outpost, Nocturna Base, has that field, so founded outposts return an empty list. Includes Grow Lamps, Sprinklers, Dispensers, and Crop Automators, which occupy field cells but do not use building capacity or appear in `buildings()`. It does not include the mobile Harvester, crops, loose items, Water Wells, or other POI extractors. Pass a `type_id` to filter, or omit it for all four fixed machine types. Use `get_component(ref.id)` for type-specific live reads.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `type_id` | `string` | Optional fixed Harvesting-field machine type id: `"grow_lamp"`, `"sprinkler"`, `"dispenser"`, or `"crop_automator"`. Omit it to return every fixed machine deployed on the field. |

- **Returns** `list<HarvestingMachineRef>`

*Types / World & Sites*

---

## OutpostNetwork

**Returned by:** get_component("outpost_network")

### Related object types

- `OutpostRef`

### Methods

##### `.outposts()`

All owned outposts as read-only `OutpostRef` snapshots, including home. Use `.id` when passing an outpost to another API; call `outposts()` again when you need fresh counts/names.

- **Returns** `list<OutpostRef>`

##### `.home()`

The home outpost as an `OutpostRef` snapshot.

- **Returns** `OutpostRef`

##### `.nearest(x, y)`

Nearest owned outpost to the given world coordinate as an `OutpostRef` snapshot.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `number` | World X coordinate |
| `y` | `number` | World Y coordinate |

- **Returns** `OutpostRef`

*Types / World & Sites*

---

## OutpostRef

**Returned by:** outpost_network.outposts() / outpost_network.home() / outpost_network.nearest()

### Related object types

- `BuildingRef`
- `HarvestingMachineRef`

### Properties

##### `.id`

Immutable outpost id, e.g. `"outpost_home"` or `"outpost_1"`. Use it with `get_component(id)` or APIs that need a stable target.

- **Returns** `string`

##### `.name`

Display name at the time this ref was returned.

- **Returns** `string`

##### `.x`

World X coordinate of the outpost footprint's top-left anchor, in meters from base. For an at-building action, route to that building's `BuildingRef.position` instead.

- **Returns** `number`

##### `.y`

World Y coordinate of the outpost footprint's top-left anchor, in meters from base. For an at-building action, route to that building's `BuildingRef.position` instead.

- **Returns** `number`

##### `.is_home`

`True` for the home outpost.

- **Returns** `boolean`

##### `.biome`

Biome this outpost sits in: one of `"frozen"`, `"coastal"`, `"geothermal"`, `"volcanic"`, `"deep"`. Derived from the outpost's location. A building reaches its own biome via `self.outpost.biome`.

- **Returns** `string`
- **Possible values** `"frozen"`, `"coastal"`, `"geothermal"`, `"volcanic"`, `"deep"`

##### `.buildings_used`

Buildings deployed at this outpost when this ref was returned.

- **Returns** `number`

##### `.buildings_capacity`

Soft building threshold at this outpost when this ref was returned. Buildings above it reduce productive and service throughput.

- **Returns** `number`

##### `.is_full`

`True` when this outpost had reached or exceeded its soft building threshold at the time this ref was returned. The threshold itself does not block ordinary deployment.

- **Returns** `boolean`

### Methods

##### `.position()`

Top-left anchor of the outpost footprint as a `Position` snapshot. This identifies the outpost, not a particular building's docking point.

- **Returns** `Position`

##### `.coords()`

Top-left anchor of the outpost footprint as `[x, y]`. Use `buildings()` and `BuildingRef.position` when routing to a particular service building.

- **Returns** `[number, number]`

##### `.buildings(type_id?)`

Fresh list of `BuildingRef` snapshots: one entry per building deployed here. Pass a `type_id` (e.g. `"storage_bin"`) to filter, or omit for every building. Each ref carries `.id` / `.name` / `.type_id` / `.outpost` / `.powered` / `.position`: for type-specific live reads (`count()`, `material()`, `recipe`, etc.) call `get_component(ref.id)` to reach the full component API.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `type_id` | `string` | Optional. Machine type id to filter by (e.g. "storage_bin"). Omit to return every building at this outpost. |

- **Returns** `list<BuildingRef>`

##### `.harvesting_machines(type_id?)`

Fresh list of `HarvestingMachineRef` snapshots for fixed machines deployed on this outpost's Harvesting field. Currently only the home outpost, Nocturna Base, has that field, so founded outposts return an empty list. Includes Grow Lamps, Sprinklers, Dispensers, and Crop Automators, which occupy field cells but do not use building capacity or appear in `buildings()`. It does not include the mobile Harvester, crops, loose items, Water Wells, or other POI extractors. Pass a `type_id` to filter, or omit it for all four fixed machine types. Use `get_component(ref.id)` for type-specific live reads.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `type_id` | `string` | Optional fixed Harvesting-field machine type id: `"grow_lamp"`, `"sprinkler"`, `"dispenser"`, or `"crop_automator"`. Omit it to return every fixed machine deployed on the field. |

- **Returns** `list<HarvestingMachineRef>`

*Types / World & Sites*

---

## BuildingRef

**Returned by:** outpost.buildings() / outpost_network.outposts()[i].buildings()

### Properties

##### `.id`

Stable component id. Use with `get_component(id)` to reach the full machine API (counts, recipes, materials, etc.).

- **Returns** `string`

##### `.name`

Display name when this ref was returned (e.g. `"Iron Ore Bin"`). For fresh names or live machine state, call `get_component(id)`.

- **Returns** `string`

##### `.type_id`

Machine type id, e.g. `"storage_bin"`, `"smelter"`, `"solar_generator"`. Stable forever; use this for branching logic.

- **Returns** `string`

##### `.outpost_id`

Id of the outpost this building is deployed at.

- **Returns** `string`

##### `.outpost`

Snapshot back-reference to the owning outpost as an `OutpostRef` (or `None` if the link can't be resolved).

- **Returns** `Optional[OutpostRef]`

##### `.powered`

`True` when the building's power toggle was on as this ref was returned. For live power/production reads, call `get_component(id)`.

- **Returns** `boolean`

##### `.position`

World coordinates as `[x, y]`. For most buildings this is the deploy anchor; doesn't move.

- **Returns** `[number, number]`

*Types / World & Sites*

---

## HarvestingMachineRef

**Returned by:** outpost.harvesting_machines() / outpost_network.home().harvesting_machines()

### Properties

##### `.id`

Stable component id. Use with `get_component(id)` to reach the full Grow Lamp, Sprinkler, Dispenser, or Crop Automator API.

- **Returns** `string`

##### `.name`

Display name when this ref was returned. Call `get_component(id)` for current machine state.

- **Returns** `string`

##### `.type_id`

Fixed Harvesting-field machine type id: `"grow_lamp"`, `"sprinkler"`, `"dispenser"`, or `"crop_automator"`.

- **Returns** `string`
- **Possible values** `"grow_lamp"`, `"sprinkler"`, `"dispenser"`, `"crop_automator"`

##### `.powered`

`True` when the machine's power toggle was on as this ref was returned. Call `get_component(id)` for live status and supply reads.

- **Returns** `boolean`

##### `.position`

Harvesting-field sector occupied by the fixed machine, such as `"B22"`.

- **Returns** `string`

*Types / World & Sites*

---

## Planet

**Returned by:** transmitter.list_planets()

### Properties

##### `.id`

Planet id: pass this to transmitter.connect().

- **Returns** `string`

##### `.name`

Display name.

- **Returns** `string`

##### `.description`

Short planet description.

- **Returns** `string`

*Types / World & Sites*

---

## ScanResult

**Returned by:** scanner.scan(), harvester.collect()

### Properties

##### `.status`

Stable outcome code. Scanner results use `"ok"` / `"empty"`; Harvester results can also report `"holding"`, `"overheated"`, `"moving"` (in transit), `"busy"` (occupied by another action), or `"collecting"`.

- **Returns** `string`
- **Possible values** `"ok"`, `"empty"`, `"holding"`, `"overheated"`, `"moving"`, `"busy"`, `"collecting"`

##### `.message`

Player-readable explanation of the scan or collection outcome.

- **Returns** `string`

##### `.id`

Item ID at the scanned sector (empty string if nothing).

- **Returns** `string`

##### `.name`

Item display name.

- **Returns** `string`

##### `.value`

Credit value of the item.

- **Returns** `number`

*Types / World & Sites*

---

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

##### `.id`

Unique site identifier.

- **Returns** `string`

##### `.name`

Human-readable display name.

- **Returns** `string`

##### `.x`

Site X coordinate in meters from base.

- **Returns** `number`

##### `.y`

Site Y coordinate in meters from base.

- **Returns** `number`

##### `.surveyed`

Survey flag captured when this object was returned; resolved inert contacts also report `True`. The property never updates. Mining-site fields are snapshots. Well, vent and exotic-deposit methods read live, except on pre-survey sonar results: those keep their hidden values, so obtain a new object after surveying.

- **Returns** `boolean`

### Methods

##### `.kind()`

One of `"mineral"` / `"thermal"` / `"water"` / `"oil"` / `"exotic"` / `"inert"`. Use it to narrow to the concrete subtype: after `if site.kind() == "mineral":` the editor surfaces `MiningSite`-specific fields on `site`. `"inert"` means sonar resolved a physical formation with no extractable signal.

- **Returns** `string`
- **Possible values** `"mineral"`, `"thermal"`, `"water"`, `"oil"`, `"exotic"`, `"inert"`

##### `.position()`

`Position` snapshot with `.x` / `.y` world coordinates.

- **Returns** `Position`

*Types / World & Sites*

---

## ExoticDeposit

Extends `Site`

**Returned by:** any Site-returning API where `kind() == "exotic"` (e.g. `exotic_gas_cap.deposit()`, `exotic_spring_tap.deposit()`, sonar / journal queries)

### Properties

##### `.id`

Unique site identifier.

- **Returns** `string`

##### `.name`

Human-readable display name.

- **Returns** `string`

##### `.x`

Site X coordinate in meters from base.

- **Returns** `number`

##### `.y`

Site Y coordinate in meters from base.

- **Returns** `number`

##### `.surveyed`

Survey flag captured when this object was returned; resolved inert contacts also report `True`. The property never updates. Mining-site fields are snapshots. Well, vent and exotic-deposit methods read live, except on pre-survey sonar results: those keep their hidden values, so obtain a new object after surveying.

- **Returns** `boolean`

### Methods

##### `.kind()`

One of `"mineral"` / `"thermal"` / `"water"` / `"oil"` / `"exotic"` / `"inert"`. Use it to narrow to the concrete subtype: after `if site.kind() == "mineral":` the editor surfaces `MiningSite`-specific fields on `site`. `"inert"` means sonar resolved a physical formation with no extractable signal.

- **Returns** `string`
- **Possible values** `"mineral"`, `"thermal"`, `"water"`, `"oil"`, `"exotic"`, `"inert"`

##### `.position()`

`Position` snapshot with `.x` / `.y` world coordinates.

- **Returns** `Position`

##### `.fluid()`

Fluid id this deposit emits, e.g. `"ammonia"` (common, usable direct) or `"raw_chlorine"` (rare, needs the Refiner). `None` until `surveyed`.

- **Returns** `Optional[string]`
- **Possible values** `"ammonia"`, `"swamp_gas"`, `"raw_sulfur_gas"`, `"raw_chlorine"`, `"brine"`, `"raw_cryofluid"`, `"raw_quicksilver"`

##### `.medium()`

`"gas"` (tap with an **Exotic Gas Cap**) or `"liquid"` (tap with an **Exotic Spring Tap**). `None` until `surveyed`.

- **Returns** `Optional[string]`
- **Possible values** `"gas"`, `"liquid"`

##### `.rarity()`

`"common"` emits the usable fluid with no refining; `"uncommon"` and `"rare"` emit a raw feedstock the Refiner converts with tar. Rarer deposits are sparser and stay dormant longer. `None` until `surveyed`.

- **Returns** `Optional[string]`
- **Possible values** `"common"`, `"uncommon"`, `"rare"`

##### `.survey_level()`

Highest survey tier achieved on this deposit: `"basic"` / `"wide"` / `"deep"`, or `None` if not yet surveyed. Reads live: a deeper re-survey upgrades held Site objects too. Higher tiers unlock more fields below. A pre-survey sonar result stays unrevealed; obtain a new object after surveying.

- **Returns** `Optional[string]`
- **Possible values** `"basic"`, `"wide"`, `"deep"`

##### `.current_phase()`

The deposit's phase right now: `"active"` (emitting) or `"dormant"` (idle). Reads live: poll it from a held Site object and it follows the cycle. Returns `None` before the deposit is surveyed. A pre-survey sonar result stays unrevealed; obtain a new object after surveying.

- **Returns** `Optional[string]`
- **Possible values** `"active"`, `"dormant"`

##### `.cycle_active_minutes()`

Duration of the active phase in minutes. Requires **deep** survey: returns `None` otherwise.

- **Returns** `Optional[number]`

##### `.cycle_dormant_minutes()`

Duration of the dormant phase in minutes (rare deposits stay dormant longest). Requires **deep** survey: returns `None` otherwise.

- **Returns** `Optional[number]`

##### `.next_phase_in()`

Game-minutes until the next phase flip. Reads live: poll it in a control loop to act before dormancy hits. Requires **deep** survey: returns `None` otherwise. A pre-survey sonar result stays unrevealed; obtain a new object after surveying.

- **Returns** `Optional[number]`

##### `.base_rate()`

Peak output rate during the active phase (t/h). Requires **wide** survey: returns `None` at basic.

- **Returns** `Optional[number]`

##### `.current_rate()`

Output rate right now (t/h: **0** during dormant). Reads live. Requires **wide** survey: returns `None` at basic. A pre-survey sonar result stays unrevealed; obtain a new object after surveying.

- **Returns** `Optional[number]`

##### `.has_cap()`

Boolean: `True` if an Exotic Gas Cap or Exotic Spring Tap is currently deployed on this deposit. Reads live. A pre-survey sonar result stays unrevealed; obtain a new object after surveying.

- **Returns** `boolean`

##### `.cap_id()`

Machine id of the currently deployed cap/tap, or empty string when none is present. Reads live. A pre-survey sonar result stays unrevealed; obtain a new object after surveying.

- **Returns** `string`

*Types / World & Sites*

---

## GeologicalAnomaly

Extends `Site`

**Returned by:** any Site-returning API where `kind() == "inert"`

### Properties

##### `.id`

Unique site identifier.

- **Returns** `string`

##### `.name`

Human-readable display name.

- **Returns** `string`

##### `.x`

Site X coordinate in meters from base.

- **Returns** `number`

##### `.y`

Site Y coordinate in meters from base.

- **Returns** `number`

##### `.surveyed`

Survey flag captured when this object was returned; resolved inert contacts also report `True`. The property never updates. Mining-site fields are snapshots. Well, vent and exotic-deposit methods read live, except on pre-survey sonar results: those keep their hidden values, so obtain a new object after surveying.

- **Returns** `boolean`

### Methods

##### `.kind()`

One of `"mineral"` / `"thermal"` / `"water"` / `"oil"` / `"exotic"` / `"inert"`. Use it to narrow to the concrete subtype: after `if site.kind() == "mineral":` the editor surfaces `MiningSite`-specific fields on `site`. `"inert"` means sonar resolved a physical formation with no extractable signal.

- **Returns** `string`
- **Possible values** `"mineral"`, `"thermal"`, `"water"`, `"oil"`, `"exotic"`, `"inert"`

##### `.position()`

`Position` snapshot with `.x` / `.y` world coordinates.

- **Returns** `Position`

*Types / World & Sites*

---

## MiningSite

Extends `Site`

**Returned by:** any Site-returning API where `kind() == "mineral"`

### Properties

##### `.id`

Unique site identifier.

- **Returns** `string`

##### `.name`

Human-readable display name.

- **Returns** `string`

##### `.x`

Site X coordinate in meters from base.

- **Returns** `number`

##### `.y`

Site Y coordinate in meters from base.

- **Returns** `number`

##### `.surveyed`

Survey flag captured when this object was returned; resolved inert contacts also report `True`. The property never updates. Mining-site fields are snapshots. Well, vent and exotic-deposit methods read live, except on pre-survey sonar results: those keep their hidden values, so obtain a new object after surveying.

- **Returns** `boolean`

##### `.item_id`

Item id this site yields when drilled (e.g. `"iron_ore"`, `"silicon"`). `None` until `surveyed`.

- **Returns** `Optional[string]`
- **Possible values** `"iron_ore"`, `"silicon"`, `"titanium"`, `"cobalt"`, `"rare_earth"`, `"neutronium"`, `"lead_ore"`

##### `.hardness`

Hardness rating (**1-4**): gates drill compatibility. `None` until `surveyed`.

- **Returns** `Optional[number]`

##### `.purity`

Yield multiplier tier: `"standard"` (**1×**) / `"rich"` (**2×**) / `"pure"` (**3×**). `None` until `surveyed`.

- **Returns** `Optional[string]`
- **Possible values** `"standard"`, `"rich"`, `"pure"`

### Methods

##### `.kind()`

One of `"mineral"` / `"thermal"` / `"water"` / `"oil"` / `"exotic"` / `"inert"`. Use it to narrow to the concrete subtype: after `if site.kind() == "mineral":` the editor surfaces `MiningSite`-specific fields on `site`. `"inert"` means sonar resolved a physical formation with no extractable signal.

- **Returns** `string`
- **Possible values** `"mineral"`, `"thermal"`, `"water"`, `"oil"`, `"exotic"`, `"inert"`

##### `.position()`

`Position` snapshot with `.x` / `.y` world coordinates.

- **Returns** `Position`

*Types / World & Sites*

---

## OilWell

Extends `Site`

**Returned by:** any Site-returning API where `kind() == "oil"` (e.g. `oil_pump.well()`, sonar / journal queries)

### Properties

##### `.id`

Unique site identifier.

- **Returns** `string`

##### `.name`

Human-readable display name.

- **Returns** `string`

##### `.x`

Site X coordinate in meters from base.

- **Returns** `number`

##### `.y`

Site Y coordinate in meters from base.

- **Returns** `number`

##### `.surveyed`

Survey flag captured when this object was returned; resolved inert contacts also report `True`. The property never updates. Mining-site fields are snapshots. Well, vent and exotic-deposit methods read live, except on pre-survey sonar results: those keep their hidden values, so obtain a new object after surveying.

- **Returns** `boolean`

### Methods

##### `.kind()`

One of `"mineral"` / `"thermal"` / `"water"` / `"oil"` / `"exotic"` / `"inert"`. Use it to narrow to the concrete subtype: after `if site.kind() == "mineral":` the editor surfaces `MiningSite`-specific fields on `site`. `"inert"` means sonar resolved a physical formation with no extractable signal.

- **Returns** `string`
- **Possible values** `"mineral"`, `"thermal"`, `"water"`, `"oil"`, `"exotic"`, `"inert"`

##### `.position()`

`Position` snapshot with `.x` / `.y` world coordinates.

- **Returns** `Position`

##### `.yield_tier()`

One of `"standard"` (**1×**) / `"rich"` (**2×**) / `"pure"` (**3×**). `None` until surveyed. Checks current survey progress, except on a pre-survey sonar result, which keeps returning `None`; obtain a new object after surveying.

- **Returns** `Optional[string]`
- **Possible values** `"standard"`, `"rich"`, `"pure"`

##### `.flow_rate()`

Peak tons of oil per hour. **8 / 16 / 24** for standard / rich / pure. Oil wells pulse through active and dormant phases: a dormant well delivers nothing at any throttle (read the pump's `well_active()`). `None` until surveyed. Reads live, except on a pre-survey sonar result, which keeps returning `None`; obtain a new object after surveying.

- **Returns** `Optional[number]`

##### `.has_pump()`

Boolean: `True` if an Oil Pump is currently deployed on this well. A pre-survey sonar result always returns `False`; obtain a new object after surveying for live readings.

- **Returns** `boolean`

##### `.pump_id()`

Current machine id of the Oil Pump deployed on this well, or empty string when no pump is present. A pre-survey sonar result always returns empty string; obtain a new object after surveying for live readings.

- **Returns** `string`

*Types / World & Sites*

---

## ThermalVent

Extends `Site`

**Returned by:** any Site-returning API where `kind() == "thermal"` (e.g. `thermal_cap.vent()`, sonar / journal queries)

### Properties

##### `.id`

Unique site identifier.

- **Returns** `string`

##### `.name`

Human-readable display name.

- **Returns** `string`

##### `.x`

Site X coordinate in meters from base.

- **Returns** `number`

##### `.y`

Site Y coordinate in meters from base.

- **Returns** `number`

##### `.surveyed`

Survey flag captured when this object was returned; resolved inert contacts also report `True`. The property never updates. Mining-site fields are snapshots. Well, vent and exotic-deposit methods read live, except on pre-survey sonar results: those keep their hidden values, so obtain a new object after surveying.

- **Returns** `boolean`

### Methods

##### `.kind()`

One of `"mineral"` / `"thermal"` / `"water"` / `"oil"` / `"exotic"` / `"inert"`. Use it to narrow to the concrete subtype: after `if site.kind() == "mineral":` the editor surfaces `MiningSite`-specific fields on `site`. `"inert"` means sonar resolved a physical formation with no extractable signal.

- **Returns** `string`
- **Possible values** `"mineral"`, `"thermal"`, `"water"`, `"oil"`, `"exotic"`, `"inert"`

##### `.position()`

`Position` snapshot with `.x` / `.y` world coordinates.

- **Returns** `Position`

##### `.survey_level()`

Highest survey tier achieved on this vent: `"basic"` / `"wide"` / `"deep"`, or `None` if not yet surveyed. Reads live: a deeper re-survey upgrades held Site objects too. Higher tiers unlock more fields below. A pre-survey sonar result stays unrevealed; obtain a new object after surveying.

- **Returns** `Optional[string]`
- **Possible values** `"basic"`, `"wide"`, `"deep"`

##### `.cycle_active_minutes()`

Duration of the active phase in minutes. Requires **deep** survey: returns `None` otherwise.

- **Returns** `Optional[number]`

##### `.cycle_dormant_minutes()`

Duration of the dormant phase in minutes. Requires **deep** survey: returns `None` otherwise.

- **Returns** `Optional[number]`

##### `.current_phase()`

The vent's phase right now: `"active"` or `"dormant"`. Reads live: poll it from a held Site object and it follows the cycle. Returns `None` before the vent is surveyed. A pre-survey sonar result stays unrevealed; obtain a new object after surveying.

- **Returns** `Optional[string]`
- **Possible values** `"active"`, `"dormant"`

##### `.next_phase_in()`

Game-minutes until the next phase flip. Reads live: poll it in a control loop to act before dormancy hits. Requires **deep** survey: returns `None` otherwise. A pre-survey sonar result stays unrevealed; obtain a new object after surveying.

- **Returns** `Optional[number]`

##### `.base_steam_rate()`

Peak steam rate during active phase (t/h). Requires **wide** survey: returns `None` at basic.

- **Returns** `Optional[number]`

##### `.current_steam_rate()`

Steam rate right now (t/h: **0** during dormant phase). Reads live. Requires **wide** survey: returns `None` at basic. A pre-survey sonar result stays unrevealed; obtain a new object after surveying.

- **Returns** `Optional[number]`

##### `.has_cap()`

Boolean: `True` if a Thermal Cap is currently deployed on this vent. Reads live. A pre-survey sonar result stays unrevealed; obtain a new object after surveying.

- **Returns** `boolean`

##### `.cap_id()`

Machine id of the currently deployed Thermal Cap, or empty string when no cap is present. Reads live. A pre-survey sonar result stays unrevealed; obtain a new object after surveying.

- **Returns** `string`

*Types / World & Sites*

---

## WaterWell

Extends `Site`

**Returned by:** any Site-returning API where `kind() == "water"` (e.g. `water_pump.well()`, sonar / journal queries)

### Properties

##### `.id`

Unique site identifier.

- **Returns** `string`

##### `.name`

Human-readable display name.

- **Returns** `string`

##### `.x`

Site X coordinate in meters from base.

- **Returns** `number`

##### `.y`

Site Y coordinate in meters from base.

- **Returns** `number`

##### `.surveyed`

Survey flag captured when this object was returned; resolved inert contacts also report `True`. The property never updates. Mining-site fields are snapshots. Well, vent and exotic-deposit methods read live, except on pre-survey sonar results: those keep their hidden values, so obtain a new object after surveying.

- **Returns** `boolean`

### Methods

##### `.kind()`

One of `"mineral"` / `"thermal"` / `"water"` / `"oil"` / `"exotic"` / `"inert"`. Use it to narrow to the concrete subtype: after `if site.kind() == "mineral":` the editor surfaces `MiningSite`-specific fields on `site`. `"inert"` means sonar resolved a physical formation with no extractable signal.

- **Returns** `string`
- **Possible values** `"mineral"`, `"thermal"`, `"water"`, `"oil"`, `"exotic"`, `"inert"`

##### `.position()`

`Position` snapshot with `.x` / `.y` world coordinates.

- **Returns** `Position`

##### `.yield_tier()`

One of `"standard"` (**1×**) / `"rich"` (**2×**) / `"pure"` (**3×**). `None` until surveyed. Checks current survey progress, except on a pre-survey sonar result, which keeps returning `None`; obtain a new object after surveying. Wells reveal fully on basic survey.

- **Returns** `Optional[string]`
- **Possible values** `"standard"`, `"rich"`, `"pure"`

##### `.flow_rate()`

Tons of water per hour this well produces. **10 / 20 / 30** for standard / rich / pure. `None` until surveyed. Reads live, except on a pre-survey sonar result, which keeps returning `None`; obtain a new object after surveying.

- **Returns** `Optional[number]`

##### `.has_pump()`

Boolean: `True` if a Water Pump is currently deployed on this well. A pre-survey sonar result always returns `False`; obtain a new object after surveying for live readings.

- **Returns** `boolean`

##### `.pump_id()`

Current machine id of the Water Pump deployed on this well, or empty string when no pump is present. A pre-survey sonar result always returns empty string; obtain a new object after surveying for live readings.

- **Returns** `string`

*Types / Storage & Inventory*

---
