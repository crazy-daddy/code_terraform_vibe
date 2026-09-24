# Component: warehouse

> **Category:** Production & Storage | **Component Name:** Warehouse

Multi-material bulk depot, 5 material-locked slots, 2,000 each (10,000 total). Drone-scale haulage absorption.

| Field | Value |
| --- | --- |
| Type | Mining |
| Storage | 5 slots × 2,000 units |

### How to obtain

1. Requires the **Warehouse** research (Oxygen 150).
2. Buy from the Shop for 3,000 cr.

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

Units of `item_id` held across every slot. Returns **0** if no slot holds it. Inventory, Storage Bins, and Lead Casks expose the same query. `wh.count("iron_ore")`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `str` | Item id to count |

- **Returns** Number: units of that item across all slots.

##### `.total() → int`

Total units across all slots (every material combined). For one material use `count(item_id)`.

- **Returns** Number: total units across every slot.

##### `.capacity() → int`

Total capacity across all physical slots. A Warehouse returns **10,000** (**5** × **2,000**); a Large Warehouse returns **30,000** (**15** × **2,000**). Query this value instead of hardcoding a tier.

- **Returns** Number: total capacity across all slots.

##### `.fill_percent() → float`

Fraction full across the whole warehouse, `total() / capacity()`, in the range **0-1**.

- **Returns** Number (**0-1**).

##### `.is_empty() → bool`

`True` if every slot is empty.

- **Returns** Boolean.

##### `.materials() → list[str]`

List of item ids currently stored (one entry per material with units in a slot). Iterate it: `for m in wh.materials():`.

- **Returns** List of item ids currently stored.

##### `.stacks() → list[ItemStack]`

Lists the item variants stored across all physical slots as `ItemStack` values. Items with the same id but different properties occupy separate slots. Call it again when you need current contents.

- **Returns** List of property-distinct `ItemStack` snapshots across all physical slots.

##### `.space_for(item_id: str, properties: ItemProperties | None = None) → int`

How many more units of one exact item variant fit **right now**, using room in matching-identity slots plus every empty slot. Omit `properties` for ordinary propertyless items, or pass the full `.properties` dict returned by `stacks()`. This never counts room belonging to a different property variant.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `str` | Item id to size remaining room for |
| `properties` | `ItemProperties \| None` | Full property dict for the variant, or None for propertyless items |

- **Returns** Number: units of that exact item variant that fit right now.

##### `.has_space(item_id: str, amount: int, properties: ItemProperties | None = None) → bool`

`True` if at least whole-number `amount` more units of that exact item variant fit. Omit `properties` for propertyless items or pass the full property dict. Use before a transfer to avoid partial moves.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `str` | Item id |
| `amount` | `int` | Whole-number units required |
| `properties` | `ItemProperties \| None` | Full property dict for the variant, or None for propertyless items |

- **Returns** Boolean.

##### `.slots() → list[WarehouseSlot]`

Every physical slot as a `WarehouseSlot` record with `.index`, `.item`, `.count`, `.capacity`, and `.properties`. Property-distinct variants use distinct slots.

- **Returns** List of `WarehouseSlot` records with `.index`, `.item`, `.count`, `.capacity`, and exact `.properties` identity.

##### `.compact() → TransferResult`

Requires **Auto Feeders** research. Consolidate every exact item variant into the fewest Warehouse slots that can hold it. The smallest redundant stacks move into larger compatible stacks, minimizing physical handling; equal item ids with different properties always remain separate. The call waits for time proportional to the units repositioned and locks this Warehouse as a material endpoint for the cycle. Port transfers and manual Biology actions using this Warehouse wait until that cycle finishes.

- **Returns** `TransferResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.requested`, `.moved`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Compacted `.moved` units into fewer Warehouse slots. |
| `"already_compact"` | success | Every exact item variant already occupies the fewest possible Warehouse slots. |
| `"research_required"` | rejection | The required material-transfer research is not unlocked. |
| `"busy"` | transient | This material endpoint is already handling another material operation. |
| `"source_under_construction"` | transient | The configured source is still under construction. |
| `"source_changed"` | transient | The source changed between transfer planning and commit. |
| `"slots_full"` | rejection | The destination has capacity but no slot for this material identity. |
| `"target_full"` | rejection | The destination has no capacity for matching units. |

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
