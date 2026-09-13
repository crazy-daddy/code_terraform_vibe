# Component: outpost

> **Category:** Infrastructure & Fluids | **Component Name:** Outpost

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
