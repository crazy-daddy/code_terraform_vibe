# Component: sonar_module

> **Category:** Vehicles & Modules | **Component Name:** Sonar Module

Finds and surveys world sites through `self.sonar`. A scan checks the area around the vehicle; driving alone does not scan. Use `get_component("nocturna").points_of_interest()` to find unscanned "?" markers, travel near one, then call `scan()` and `survey(site)`. Basic Sonar reaches **50 m** and minerals up to hardness **1**; Wide reaches **180 m** and hardness **3**; Deep reaches **280 m** and hardness **4**. Research unlocks thermal vents, wells, and exotic deposits. Results are saved in the Journal. Local Harvester sectors, biological sites, and radiation fields use different scanners.

**Returned by:** `self.sonar`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.scan()` *(self only)*

Sweep for compatible `Site`s within range of the vehicle's current position. Contact types include `MiningSite`, `ThermalVent`, `WaterWell`, `OilWell`, `ExoticDeposit`, and `GeologicalAnomaly`. A completed sweep updates the Journal with newly classified contacts.

- **Returns** `SonarScanResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.sites`, `.blocked`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The sonar sweep completed. `result.sites` contains every compatible contact found; an empty list means there were no compatible contacts in range. |
| `"too_hard"` | partial | The completed sweep detected a nearby unresolved contact above the mounted sonar's hardness limit. |
| `"tier_too_low"` | partial | The completed sweep detected a nearby unresolved contact that the mounted sonar tier cannot classify. |
| `"research_required"` | partial | The completed sweep detected a nearby unresolved contact whose classification research is not unlocked. |
| `"wrong_scanner"` | partial | The completed sweep detected a nearby contact that vehicle sonar cannot classify. |
| `"busy"` | transient | Another field action currently occupies the vehicle. |
| `"no_power"` | rejection | The vehicle battery does not contain enough energy for a sonar sweep. |

*Raises*

| Exception | Condition |
| --- | --- |
| `ReferenceError` | This SonarModule reference is stale because its module is no longer mounted. Read self.sonar again after mounting a sonar. |

##### `.survey(site)` *(self only)*

Reveal the details available for a productive `Site`. Pass either its string id or a `Site` from `scan()`. A repeat survey is free and instant unless a better sonar tier can reveal more. Inert `GeologicalAnomaly` contacts are already resolved by scanning.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `site` | `any` | A site id (string), a `Site` from `scan().sites`, or a dictionary or class instance with its string `id` field. The site must still be discovered, in range, and within this sonar's capability. |

- **Returns** `SurveyResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.site`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Surveyed `site_id` successfully. |
| `"busy"` | transient | Another field action currently occupies the vehicle. |
| `"not_discovered"` | rejection | Site `site_id` is not in this planet's discovered-site journal. |
| `"research_required"` | rejection | Site `site_id` requires research that is not currently unlocked. |
| `"tier_too_low"` | rejection | The mounted sonar tier cannot survey site `site_id`. |
| `"out_of_range"` | rejection | Site `site_id` is outside the mounted sonar's current range. |
| `"too_hard"` | rejection | Site `site_id` exceeds the mounted sonar's mineral hardness limit. |
| `"no_power"` | rejection | The vehicle battery does not contain enough energy to survey site `site_id`. |

*Raises*

| Exception | Condition |
| --- | --- |
| `ValueError` | survey() requires a non-empty site id or a Site object. |
| `ReferenceError` | This SonarModule reference is stale because its module is no longer mounted. Read self.sonar again after mounting a sonar. |

##### `.range()`

Current sonar range in meters.

- **Returns** Number (meters): **50** basic, **180** Wide, **280** Deep. A stale captured module reference raises `ReferenceError`.

*Raises*

| Exception | Condition |
| --- | --- |
| `ReferenceError` | This SonarModule reference is stale because its module is no longer mounted. Read self.sonar again after mounting a sonar. |

##### `.hardness_limit()`

Maximum mineral hardness this sonar can identify.

- **Returns** Number: **1** basic, **3** Wide, **4** Deep. A stale captured module reference raises `ReferenceError`.

*Raises*

| Exception | Condition |
| --- | --- |
| `ReferenceError` | This SonarModule reference is stale because its module is no longer mounted. Read self.sonar again after mounting a sonar. |

##### `.tier()`

Survey-depth tier granted by this sonar: `"basic"` / `"wide"` / `"deep"`. Controls how much of a thermal vent or exotic deposit is revealed by `survey()`; `"deep"` is also required for oil-well discovery.

- **Returns** Survey-depth tier granted by this sonar: `"basic"` / `"wide"` / `"deep"`. Controls thermal/exotic detail; `"deep"` is required for oil-well discovery. A stale captured module reference raises `ReferenceError`.
- **Possible values** `"basic"`, `"wide"`, `"deep"`

*Raises*

| Exception | Condition |
| --- | --- |
| `ReferenceError` | This SonarModule reference is stale because its module is no longer mounted. Read self.sonar again after mounting a sonar. |

*Components / Logistics & Orders*
