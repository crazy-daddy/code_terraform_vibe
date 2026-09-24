# Data Types: Biosphere

Complete property specifications, descriptions, units, and return types from the official documentation.

## Index

- [`AnalyzeResult`](#analyzeresult) (BIOSPHERE)
- [`BioExtractionResult`](#bioextractionresult) (BIOSPHERE)
- [`BioScanResult`](#bioscanresult) (BIOSPHERE)
- [`Cell`](#cell) (BIOSPHERE)
- [`LifeFormScanResult`](#lifeformscanresult) (BIOSPHERE)
- [`LifeFormSample`](#lifeformsample) (BIOSPHERE)
- [`PlantRequirement`](#plantrequirement) (BIOSPHERE)
- [`PortableBioExtractor`](#portablebioextractor) (BIOSPHERE)
- [`PortableBioScanner`](#portablebioscanner) (BIOSPHERE)
- [`SeedRecipe`](#seedrecipe) (BIOSPHERE)
- [`SeedResult`](#seedresult) (BIOSPHERE)

---

## AnalyzeResult

**Returned by:** bio_lab.analyze()

### Properties

##### `.status: str`

`"ok"`, `"busy"`, `"input_empty"`, or `"invalid_specimen"`.

- **Returns** `str`
- **Possible values** `"ok"`, `"busy"`, `"input_empty"`, `"invalid_specimen"`, `"output_full"`

##### `.message: str`

Player-readable explanation of the analysis outcome.

- **Returns** `str`

##### `.info: AnalyzeInfo | None`

Completed `AnalyzeInfo`, or `None` when analysis was rejected.

- **Returns** `AnalyzeInfo | None`

*Types / Biosphere*

## BioExtractionResult

**Returned by:** PortableBioExtractor.extract()

### Properties

##### `.status: str`

`"ok"`, `"not_mounted"`, `"scrambled"`, `"busy"`, `"not_at_location"`, `"not_scanned"`, `"cooling"`, or `"no_cargo_space"`.

- **Returns** `str`
- **Possible values** `"ok"`, `"not_mounted"`, `"scrambled"`, `"busy"`, `"not_at_location"`, `"not_scanned"`, `"cooling"`, `"no_cargo_space"`

##### `.message: str`

Player-readable explanation of the biological extraction outcome.

- **Returns** `str`

##### `.extracted: float`

Tons committed to drone cargo by this extraction; **0** for every rejection.

- **Returns** `float`

*Types / Biosphere*

## BioScanResult

**Returned by:** PortableBioScanner.scan()

### Properties

##### `.status: str`

`"ok"`, `"not_mounted"`, `"scrambled"`, `"busy"`, or `"not_at_location"`.

- **Returns** `str`
- **Possible values** `"ok"`, `"not_mounted"`, `"scrambled"`, `"busy"`, `"not_at_location"`

##### `.message: str`

Player-readable explanation of the biological scan outcome.

- **Returns** `str`

##### `.scan: LifeFormScanResult | None`

Completed `LifeFormScanResult`, or `None` when the scan was rejected.

- **Returns** `LifeFormScanResult | None`

*Types / Biosphere*

## Cell

**Returned by:** self.cell(sector) / self.cells()

### Properties

##### `.id: str`

Sector id, e.g. `"E13"` (row letter A-H + column 1-24). Parse it to compute the four orthogonal neighbors yourself: the grid hands you no `neighbors()` helper.

- **Returns** `str`

##### `.plant: str | None`

Species id of the planted flora, such as `"sunpetal"`, or `None` when the cell has no plant. This is the species id, not the `"seed_sunpetal"` item id. An empty cell may still contain a provider or uncollected item, so also check `.status`. It matches `SeedRecipe.species` and the species part of `"seed:<species>"`.

- **Returns** `str | None`
- **Possible values** `"sunpetal"`, `"shadeleaf"`, `"dewmoss"`, `"lonethorn"`, `"packfern"`, `"twinvine"`, `"spitebud"`, `"sunspur"`, `"glowvine"`, `"crowncap"`, `"pondmoss"`, `"saltbloom"`, `"brinethorn"`, `"saltmate"`, `"grandbloom"`

##### `.growth: float`

Crop growth progress **0-1**. **1.0** means ready to harvest. Advances only while every requirement is met and pauses (never regresses) otherwise. Clearing the crop returns it to **0**; a partial Harvester harvest leaves the crop mature at **1.0** with its remaining forage.

- **Returns** `float`

##### `.status: str`

What occupies the sector or what its crop is doing: `"unknown"` until natural ground is scanned, `"empty"` (bare plantable ground), `"item"` (an uncollected surface item), `"base"` (the Harvester depot), `"provider"` (field equipment), `"growing"`, `"stalled"`, or `"mature"`. Player-created plants and providers remain visible. Only `"empty"` accepts planting or deployment.

- **Returns** `str`
- **Possible values** `"unknown"`, `"empty"`, `"item"`, `"base"`, `"growing"`, `"stalled"`, `"mature"`, `"provider"`

##### `.lit: bool`

`True` while the cell has an active 24-hour Harvester light treatment or a powered Grow Lamp covers it. Satisfies the **Light** requirement; **Shade** plants need this `False`.

- **Returns** `bool`

##### `.watered: bool`

`True` while the cell has an active 24-hour Harvester water treatment, or while a powered, supplied Sprinkler covers it. Satisfies the **Water** requirement. A plant pauses when neither source is active.

- **Returns** `bool`

##### `.salted: bool`

`True` while the cell has an active 24-hour Harvester salt treatment, or while a powered, supplied Dispenser covers it. Satisfies the **Salt** requirement. A plant pauses when neither source is active.

- **Returns** `bool`

##### `.manual_light_remaining: float`

Hours remaining on the Harvester-applied light treatment, in the **0-24** range. This excludes Grow Lamp coverage. Each successful `light()` resets it to **24 hours**, replacing any remaining time.

- **Returns** `float`

##### `.manual_water_remaining: float`

Hours remaining on the Harvester-applied water treatment, in the **0-24** range. This excludes Sprinkler coverage. Each successful `water()` resets it to **24 hours**, replacing any remaining time.

- **Returns** `float`

##### `.manual_salt_remaining: float`

Hours remaining on the Harvester-applied salt treatment, in the **0-24** range. This excludes Dispenser coverage. Each successful `dispense_salt()` resets it to **24 hours**, replacing any remaining time.

- **Returns** `float`

##### `.fertilized: bool`

`True` while any Fertilizer dose remains on this cell. `False` when undosed or fully drained.

- **Returns** `bool`

##### `.fertilizer_remaining: float`

Hours of Fertilizer effect remaining. Each applied unit adds **8 hours**; reads **0** when none remains.

- **Returns** `float`

##### `.fertilizer_tier: int`

Active Fertilizer tier: **1**, **2**, or **3**. Reads **0** when no Fertilizer remains.

- **Returns** `int`

##### `.accelerated: bool`

`True` while any Growth Accelerant dose remains on this cell. `False` when undosed or fully drained.

- **Returns** `bool`

##### `.accelerant_remaining: float`

Hours of Growth Accelerant effect remaining. Each applied unit adds **8 hours**; reads **0** when none remains.

- **Returns** `float`

##### `.forage: int`

Whole **forage** banked by this crop. It rises with visible growth while requirements are met, includes diversity and field bonuses, and freezes at `growth == 1.0`. The Harvester moves as much as Inventory can hold and leaves any remainder on the crop. A Crop Automator moves what fits in its output, discards the remainder, and clears the cell; a completely full output blocks the job without changing the crop. Forage feeds Wildlife production and Plant Terraformer batches.

- **Returns** `int`

*Types / Biosphere*

## LifeFormScanResult

**Returned by:** PortableBioScanner.scan().scan after status == "ok" / journal biosite queries

### Related object types

- `LifeFormSample`

### Properties

##### `.coord: list[int]`

`[x, y]` whole-number coordinate of the scanned location.

- **Returns** `list[int]`

##### `.life_forms: list[LifeFormSample]`

List of `LifeFormSample` entries: 0-3 items per tile. Empty list means "scanned, nothing here."

- **Returns** `list[LifeFormSample]`

##### `.is_empty: bool`

`True` if no life forms found at this tile.

- **Returns** `bool`

*Types / Biosphere*

## LifeFormSample

**Returned by:** PortableBioScanner.scan().scan.life_forms[i] after status == "ok"

### Properties

##### `.type: str`

Life-form item id (e.g. `"ice_algae"`, `"snow_moss"`).

- **Returns** `str`
- **Possible values** `"ice_algae"`, `"snow_moss"`, `"frost_lichen"`, `"cold_spores"`, `"ice_crust"`, `"frost_fungus"`, `"sea_algae"`, `"tide_moss"`, `"shore_lichen"`, `"brine_plankton"`, `"salt_crust"`, `"coral_fungus"`, `"vent_algae"`, `"steam_moss"`, `"heat_lichen"`, `"hot_spores"`, `"heat_crust"`, `"vent_fungus"`, `"sulfur_moss"`, `"cinder_lichen"`, `"ash_spores"`, `"lava_algae"`, `"magma_crust"`, `"black_fungus"`, `"cave_moss"`, `"stone_lichen"`, `"crystal_spores"`, `"deep_algae"`, `"stone_mat"`, `"cave_fungus"`

##### `.tons: float`

Tons of this life-form available at the tile at scan time (peak value, not current state).

- **Returns** `float`

##### `.remaining_tons: float`

Tons currently available. Partial drone harvests reduce this; it returns to `.tons` after the coordinate's cooldown.

- **Returns** `float`

##### `.rarity: str`

Rarity tier: `"common"`, `"uncommon"`, or `"rare"`. Determines both essence produced per ton at the Essence Liquifier and the cooldown after extraction.

- **Returns** `str`
- **Possible values** `"common"`, `"uncommon"`, `"rare"`

##### `.biome: str`

Native biome this species belongs to: `"frozen"`, `"coastal"`, `"geothermal"`, `"volcanic"`, or `"deep"`. Fixed per species (never the terrain it grows on), and exactly the biome whose Essence Liquifier consumes it. Same value as `nocturna.life_form_biome(sample.type)`.

- **Returns** `str`
- **Possible values** `"frozen"`, `"coastal"`, `"geothermal"`, `"volcanic"`, `"deep"`

*Types / Biosphere*

## PlantRequirement

**Returned by:** SeedRecipe.requirements

### Properties

##### `.kind: str`

Cultivation condition: `"light"`, `"shade"`, `"water"`, `"salt"`, `"spacer"`, `"cluster"`, `"companion"`, or `"antagonist"`. Every entry in `SeedRecipe.requirements` is required; combined species expose multiple entries.

- **Returns** `str`
- **Possible values** `"light"`, `"shade"`, `"water"`, `"salt"`, `"spacer"`, `"cluster"`, `"companion"`, `"antagonist"`

##### `.species: str | None`

Related species key for relational conditions: the required neighbor for `"companion"`, or the forbidden neighbor for `"antagonist"`. `None` for all other kinds.

- **Returns** `str | None`
- **Possible values** `"sunpetal"`, `"shadeleaf"`, `"dewmoss"`, `"lonethorn"`, `"packfern"`, `"twinvine"`, `"spitebud"`, `"sunspur"`, `"glowvine"`, `"crowncap"`, `"pondmoss"`, `"saltbloom"`, `"brinethorn"`, `"saltmate"`, `"grandbloom"`

*Types / Biosphere*

## PortableBioExtractor

**Returned by:** self.bio_extractor (drones)

### Methods

##### `.extract() → BioExtractionResult`

Yielding harvest at the discovered permanent biosite under a hovering drone. The drone stays occupied until completion, including across a script stop and restart. The module has a 25 t chamber for one life-form type; Cargo Pods add capacity. Partial depletion persists and cooldown starts only when the site is empty.

- **Returns** `BioExtractionResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.extracted`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Biological material extracted into drone cargo: `.extracted` t. |
| `"not_mounted"` | rejection | The drone has no Portable Bio Extractor mounted. |
| `"scrambled"` | transient | The drone's electronics are radiation-scrambled and cannot extract. |
| `"busy"` | transient | Biological extraction is already in progress for this drone or at this site. |
| `"not_at_location"` | rejection | The drone must finish its route and hover at a biological site. |
| `"not_scanned"` | rejection | There is no scanned and recorded biological site under the drone. |
| `"cooling"` | transient | The depleted biological site is still replenishing. |
| `"no_cargo_space"` | rejection | Cannot extract the remaining life forms: every compatible container is full or already assigned to another type. Each extractor chamber and Cargo Pod holds one life-form type at a time. |

*Types / Biosphere*

## PortableBioScanner

**Returned by:** self.bio_scanner (drones)

### Methods

##### `.scan() → BioScanResult`

Yielding scan at the hovering drone's current whole-number coordinate. A valid non-site coordinate completes with an empty biological scan. Repeat scans are free.

- **Returns** `BioScanResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.scan`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The biological scan completed at the drone's current coordinate. |
| `"not_mounted"` | rejection | The drone has no Portable Bio Scanner mounted. |
| `"scrambled"` | transient | The drone's electronics are radiation-scrambled and cannot scan. |
| `"busy"` | transient | The drone is occupied by another biological operation. |
| `"not_at_location"` | rejection | The drone must finish its route and hover at a whole-number biological survey coordinate. |

*Types / Biosphere*

## SeedRecipe

**Returned by:** self.recipes() (Seed Maker)

### Properties

##### `.tier: int`

Production tier for this discovered Seed Maker recipe. Seed recipes are Tier 1 because their inputs are harvested source materials.

- **Returns** `int`

##### `.species: str`

Bare flora species id this recipe produces, such as `"sunpetal"`. It matches `Cell.plant` and identifies the biological species, not the physical seed item used by planting commands.

- **Returns** `str`
- **Possible values** `"sunpetal"`, `"shadeleaf"`, `"dewmoss"`, `"lonethorn"`, `"packfern"`, `"twinvine"`, `"spitebud"`, `"sunspur"`, `"glowvine"`, `"crowncap"`, `"pondmoss"`, `"saltbloom"`, `"brinethorn"`, `"saltmate"`, `"grandbloom"`

##### `.seed_id: str`

Physical seed item id produced by this recipe, such as `"seed_sunpetal"`. Pass this value to the Harvester's `load_seed()` and `plant()`, or to a Crop Automator's `plant()` after loading the same item into its input.

- **Returns** `str`
- **Possible values** `"seed_sunpetal"`, `"seed_shadeleaf"`, `"seed_dewmoss"`, `"seed_lonethorn"`, `"seed_packfern"`, `"seed_twinvine"`, `"seed_spitebud"`, `"seed_sunspur"`, `"seed_glowvine"`, `"seed_crowncap"`, `"seed_pondmoss"`, `"seed_saltbloom"`, `"seed_brinethorn"`, `"seed_saltmate"`, `"seed_grandbloom"`

##### `.blend: list[str]`

The exact list of 3 life-form ids that yields this seed (e.g. `["ice_algae", "sea_algae", "vent_moss"]`). Order doesn't matter: combine these three again to reproduce the seed.

- **Returns** `list[str]`

##### `.requirements: list[PlantRequirement]`

Lists every cultivation condition as a `PlantRequirement`. Each entry has a `.kind` and optional `.species`, identifying required companions or forbidden antagonists. Every listed requirement must be satisfied for growth to advance.

- **Returns** `list[PlantRequirement]`

##### `.requirement: str`

Compact summary of the requirement kinds, e.g. `"light"`, `"light+water"`, or `"salt+companion"`. Use `.requirements` for programmable layout decisions because this summary intentionally omits the companion/antagonist species identity.

- **Returns** `str`
- **Possible values** `"light"`, `"shade"`, `"water"`, `"spacer"`, `"cluster"`, `"companion"`, `"antagonist"`, `"light+spacer"`, `"light+water"`, `"shade+cluster"`, `"water+cluster"`, `"salt"`, `"salt+spacer"`, `"salt+companion"`, `"light+water+spacer"`

##### `.growth_time: float`

Hours of met-requirement time to reach maturity (`growth == 1.0`). Longer-growing species are the harder, higher-value ones; growth only advances while all requirements hold.

- **Returns** `float`

##### `.base_yield: int`

Whole forage units this species yields before diversity, treatment, and field bonuses. Compare this with `.growth_time` and `.requirements` when choosing a crop.

- **Returns** `int`

*Types / Biosphere*

## SeedResult

**Returned by:** seed_maker.combine()

### Properties

##### `.status: str`

`"seed_found"`, `"sludge"`, `"locked"`, `"busy"`, `"missing_life_forms"`, or `"output_full"`.

- **Returns** `str`
- **Possible values** `"seed_found"`, `"sludge"`, `"locked"`, `"busy"`, `"missing_life_forms"`, `"output_full"`

##### `.message: str`

Player-readable explanation of the combine trial outcome.

- **Returns** `str`

##### `.seed_id: str | None`

Stable seed item id deposited into output, or `None` when no seed was produced.

- **Returns** `str | None`
- **Possible values** `"seed_sunpetal"`, `"seed_shadeleaf"`, `"seed_dewmoss"`, `"seed_lonethorn"`, `"seed_packfern"`, `"seed_twinvine"`, `"seed_spitebud"`, `"seed_sunspur"`, `"seed_glowvine"`, `"seed_crowncap"`, `"seed_pondmoss"`, `"seed_saltbloom"`, `"seed_brinethorn"`, `"seed_saltmate"`, `"seed_grandbloom"`

##### `.species: str | None`

Stable discovered flora species id, or `None` when no seed was produced.

- **Returns** `str | None`
- **Possible values** `"sunpetal"`, `"shadeleaf"`, `"dewmoss"`, `"lonethorn"`, `"packfern"`, `"twinvine"`, `"spitebud"`, `"sunspur"`, `"glowvine"`, `"crowncap"`, `"pondmoss"`, `"saltbloom"`, `"brinethorn"`, `"saltmate"`, `"grandbloom"`

*Types / Built-in Modules*
