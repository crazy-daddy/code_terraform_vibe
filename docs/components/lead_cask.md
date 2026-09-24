# Component: lead_cask

> **Category:** Production & Storage | **Component Name:** Lead Cask

The only safe stationary home for hot radioactive cargo. Drones drop Raw Uranium into it, the Fuel Assembler draws from it and returns finished Fuel Rods, and the Reactor pulls its fuel from it.

| Field | Value |
| --- | --- |
| Type | Mining |
| Storage | 100 units |

### How to obtain

1. The recipe unlocks when you complete **Helios, Plate Order**.
2. Requires the **Shielded Logistics** research (Oxygen 3,000).
3. Fabricate a **Lead Cask** on a **Fabricator**: 3× Lead Plate and 1× Machine Frame.
4. Deploy it from your Inventory.

**Returned by:** `get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

##### `.outpost: OutpostRef`

The outpost where this building is deployed. The returned `OutpostRef` includes its stable id, display name, biome, position, capacity, and `buildings()` query. Read the property again when you need current values.

- **Returns** `OutpostRef` for the outpost where this building is deployed.

### Methods

##### `.count(item_id: str) → int`

Units of `item_id` currently casked. Returns **0** when the cask is empty or latched to the other hot item. Inventory, Storage Bins, and Warehouses expose the same `count(item_id)` query.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `str` | Hot item id to count |

- **Returns** Number: units of that hot item currently casked.

##### `.fill_percent() → float`

Fill fraction **0-1**, watch your strategic reserve.

- **Returns** Number (**0-1**).

##### `.capacity() → int`

Maximum hot units (**100**).

- **Returns** Number: maximum capacity (**100**).

##### `.material() → str`

What the cask is latched to, `"raw_uranium"`, `"fuel_rod"`, or empty. One material per cask, like every stock bin.

- **Returns** String: `"raw_uranium"`, `"fuel_rod"`, or empty when unassigned. Casks accept ONLY hot items; everything else refuses them.
- **Possible values** `""`, `"raw_uranium"`, `"fuel_rod"`

##### `.transfer_to(target: str, item_id: str, count: int, properties: ItemProperties | None = None, property_match: str | None = None) → TransferResult`

Requires **Auto Feeders** research. Move up to whole-number `count` units of `item_id` from this storage endpoint to another Storage Bin, Warehouse, Large Warehouse, Lead Cask, or Inventory. Pass a storage building's display name or instance id, or `"inventory"`. Inventory participates only at **Nocturna Base**. The call waits for the physical store's feeder cycle to finish, and every participating storage building remains busy during that cycle. Exact item properties are preserved; optional `properties` and `property_match` select a variant. The calling script may run anywhere, but cargo never crosses outpost boundaries through this method.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `target` | `str` | Display name or instance id of another storage endpoint at the same outpost |
| `item_id` | `str` | Item id to move |
| `count` | `int` | Whole-number max units to transfer |
| `properties` | `ItemProperties \| None` | Optional property dict, matched as a subset by default. Omitted or `None` matches any properties; use `None` with `property_match="exact"` to select propertyless items only. |
| `property_match` | `str \| None` | Optional selection mode: any, subset, or exact |

- **Returns** `TransferResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.requested`, `.moved`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Moved all `.moved` requested units. |
| `"partial"` | partial | Moved `.moved` of `.requested` requested units; source availability or destination capacity limited the transfer. |
| `"no_op"` | success | No units were requested, so no state changed. |
| `"research_required"` | rejection | The required material-transfer research is not unlocked. |
| `"busy"` | transient | This material endpoint is already handling another material operation. |
| `"invalid_properties"` | rejection | The item property selector has an invalid shape or value. |
| `"invalid_property_match"` | rejection | The requested property matching mode is invalid. |
| `"target_missing"` | rejection | The configured target no longer exists. |
| `"unsupported_target"` | rejection | The configured target cannot accept compatible cargo. |
| `"same_storage"` | rejection | The source and destination are the same storage endpoint. |
| `"target_not_local"` | rejection | The configured target belongs to another outpost. |
| `"source_under_construction"` | transient | The configured source is still under construction. |
| `"source_wrong_material"` | rejection | The source contains a different material from the one requested. |
| `"source_empty"` | rejection | The source has no matching units available. |
| `"source_changed"` | transient | The source changed between transfer planning and commit. |
| `"target_under_construction"` | transient | The configured target is still under construction. |
| `"target_wrong_material"` | rejection | The destination is latched to or accepts a different material. |
| `"hot_cargo_requires_cask"` | rejection | This hot cargo must move through a compatible Lead Cask. |
| `"cask_accepts_hot_only"` | rejection | Lead Casks accept only supported hot cargo. |
| `"slots_full"` | rejection | The destination has capacity but no slot for this material identity. |
| `"target_full"` | rejection | The destination has no capacity for matching units. |
| `"target_changed"` | transient | The destination changed between transfer planning and commit. |

*Components / Production & Storage*
