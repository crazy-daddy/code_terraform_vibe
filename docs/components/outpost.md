# Component: outpost

> **Category:** Infrastructure & Fluids | **Component Name:** Outpost

Represents a home or player-founded outpost. Look one up by stable id with `get_component("outpost_1")` or by display name with `get_component_by_name("Mining Camp")`. Players can rename outposts from the Computer System tab, so use the id for scripts that must survive renames.

**Returned by:** `get_component("outpost")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id: str`

Immutable instance id (e.g. `"outpost_home"`, `"outpost_1"`). Use this in scripts that need to outlive renames.

- **Returns** String (immutable instance id, e.g. "outpost_home", "outpost_1")

### Methods

##### `.name() → str`

Display name. The home outpost starts as `"Nocturna Base"`; player-founded outposts start as `"Outpost N"`. Freely renameable from the Computer System tab. Mutable, prefer `id` for stable references.

- **Returns** String (outpost display name, freely renameable)

##### `.coords() → list[int]`

World coordinates as `[x, y]`. Home outpost sits at `[0, 0]`.

- **Returns** List [x, y] (world coordinates of the outpost anchor)

##### `.buildings_used() → int`

Number of buildings deployed at this outpost. Sensors, mobile units, structural hubs, and POI extraction don't count.

- **Returns** Number (buildings deployed at this outpost)

##### `.buildings_capacity() → int`

Soft building threshold at this outpost. Each counted building above it reduces productive and service throughput. Nocturna Base has a few extra starter slots; player-founded outposts use the standard threshold.

- **Returns** Number (soft building threshold at this outpost)

##### `.is_full() → bool`

Returns `True` when this outpost has reached or exceeded its soft building threshold. The threshold itself does not block ordinary deployment.

- **Returns** Boolean (true if the soft building threshold is reached or exceeded)

##### `.is_home() → bool`

Returns `True` when this is the home outpost.

- **Returns** Boolean (true if this is the home outpost)

##### `.buildings(type_id?: str) → list[BuildingRef]`

Lists buildings deployed at this outpost as `BuildingRef` snapshots. Call `self.outpost.buildings()` for all of them or pass a building `type_id` to filter. Each ref has `.id`, `.name`, `.type_id`, `.outpost`, `.powered`, and `.position`; use `get_component(ref.id)` for type-specific live reads. The list covers machines that count toward building capacity, not sensors, mobile units, POI extraction, or fixed Harvesting-field machines. Use `harvesting_machines()` for those field machines.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `type_id` | `str` | Optional building type id used to filter the returned list. |

- **Returns** List of BuildingRef: one per building deployed here. Pass type_id (e.g. "storage_bin") to filter, or omit for every building. Empty list if no buildings match.

##### `.harvesting_machines(type_id?: str) → list[HarvestingMachineRef]`

Lists fixed machines deployed on this outpost's Harvesting field as `HarvestingMachineRef` snapshots. Call without an argument for every Grow Lamp, Sprinkler, Dispenser, and Crop Automator there, or pass one of those `type_id` values to filter. They occupy field cells, do not use building capacity, and do not appear in `buildings()`. This excludes the mobile Harvester, crops, loose items, Water Wells, and other POI extractors. Only Nocturna Base currently has a Harvesting field, so founded outposts return an empty list. Use `get_component(ref.id)` for type-specific live reads.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `type_id` | `str` | Optional fixed Harvesting-field machine type id used to filter the returned list. |

- **Returns** List of HarvestingMachineRef snapshots for fixed machines on this outpost's Harvesting field. Pass type_id to filter, or omit for Grow Lamps, Sprinklers, Dispensers, and Crop Automators. Only Nocturna Base has this field; founded outposts return an empty list.

*Components / Infrastructure & Fluids*
