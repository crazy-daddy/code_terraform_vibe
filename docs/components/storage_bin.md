# Component: storage_bin

> **Category:** Production & Storage | **Component Name:** Storage Bin

A passive base container that holds one material at a time. The first deposit sets what it stores, and the lock clears only once it drains empty. Other scripts can read and move its contents.

| Field | Value |
| --- | --- |
| Type | Mining |
| Storage | 500 units |

### How to obtain

1. Requires the **Storage Bins** research (Temperature 5).
2. Buy from the Shop for 120 cr.

**Returned by:** `get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

##### `.outpost`

The outpost where this building is deployed. The returned `OutpostRef` includes its stable id, display name, biome, position, capacity, and `buildings()` query. Read the property again when you need current values.

- **Returns** `OutpostRef` for the outpost where this building is deployed.

### Methods

##### `.count(item_id)`

Units of `item_id` currently stored. Returns **0** when the bin is empty or latched to another item. Inventory, Warehouses, and Lead Casks expose the same `count(item_id)` query.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `string` | Item id to count |

- **Returns** Number: units of that item currently stored.

##### `.get_capacity()`

Maximum units the bin holds, **500** by default. Queryable rather than hardcoded so a retune doesn't break scripts. Use `fill_percent()` when you need the current fill ratio.

- **Returns** Number (units max)

##### `.get_material()`

Currently latched material id, or the empty string if the bin is empty (and therefore accepts any material on the next deposit). Use to check a bin's material before routing transfers: `if bin.get_material() in ("", "iron_ore"): # safe to deposit iron`.

- **Returns** String (item id, or empty string if bin is empty)

##### `.stacks()`

Lists the item variants stored in this bin as `ItemStack` values. Items with the same id but different properties remain separate. Call it again when you need current contents.

- **Returns** List of property-distinct `ItemStack` snapshots currently stored.

##### `.is_empty()`

`True` if the bin holds nothing. An empty bin has no material lock, any material can take the slot on the next deposit. Different from `has_space(0)` which is always `True`.

- **Returns** Boolean

##### `.has_space(amount)`

`True` if the bin has room for whole-number `amount` more units. Use before a transfer to avoid partial moves.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `amount` | `number` | Whole-number units of free capacity required |

- **Returns** Boolean

##### `.space()`

Free units of capacity remaining. Sizes a transfer in one call: `n = bin.space()`, then move up to `n`.

- **Returns** Number (free units remaining)

##### `.fill_percent()`

Fraction full in the range **0-1**. Common threshold for rebalance scripts: `if bin.fill_percent() < 0.2: # route more here`.

- **Returns** Number (**0-1**)

##### `.transfer_from_inventory(item_id, count, properties=None, property_match=None)`

Requires **Auto Feeders** research and a Storage Bin at the home outpost. Move up to whole-number `count` units of `item_id` from Inventory into the bin, preserving exact properties. The call waits for the feeder cycle to finish, and the bin cannot start another transfer during that cycle. A property dict selects a subset by default. Pass `"exact"` as `property_match` for a full identity, including `None` for propertyless items.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `string` | Item id to pull from inventory |
| `count` | `number` | Whole-number max units to transfer |
| `properties` | `any` | Optional property dict, matched as a subset by default. Omitted or `None` matches any properties; use `None` with `property_match="exact"` to select propertyless items only. |
| `property_match` | `string` | Optional selection mode: any, subset, or exact |

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
| `"inventory_not_local"` | rejection | This endpoint cannot access the home freight Inventory from its current outpost. |
| `"source_empty"` | rejection | The source has no matching units available. |
| `"source_changed"` | transient | The source changed between transfer planning and commit. |
| `"target_wrong_material"` | rejection | The destination is latched to or accepts a different material. |
| `"hot_cargo_requires_cask"` | rejection | This hot cargo must move through a compatible Lead Cask. |
| `"target_full"` | rejection | The destination has no capacity for matching units. |
| `"target_changed"` | transient | The destination changed between transfer planning and commit. |

##### `.transfer_to_inventory(count, properties=None, property_match=None)`

Requires **Auto Feeders** research and a Storage Bin at the home outpost. Move up to whole-number `count` units back to Inventory, preserving exact properties. The call waits for the feeder cycle to finish, and the bin cannot start another transfer during that cycle. A property dict selects a subset by default. Pass `"exact"` as `property_match` for a full identity, including `None` for propertyless items. If the bin drains completely, its item-id latch clears.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `count` | `number` | Whole-number max units to transfer |
| `properties` | `any` | Optional property dict, matched as a subset by default. Omitted or `None` matches any properties; use `None` with `property_match="exact"` to select propertyless items only. |
| `property_match` | `string` | Optional selection mode: any, subset, or exact |

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
| `"source_empty"` | rejection | The source has no matching units available. |
| `"source_changed"` | transient | The source changed between transfer planning and commit. |
| `"inventory_not_local"` | rejection | This endpoint cannot access the home freight Inventory from its current outpost. |
| `"target_full"` | rejection | The destination has no capacity for matching units. |
| `"target_changed"` | transient | The destination changed between transfer planning and commit. |

##### `.transfer_to(target, item_id, count, properties=None, property_match=None)`

Requires **Auto Feeders** research. Move up to whole-number `count` units of `item_id` from this storage endpoint to another Storage Bin, Warehouse, Large Warehouse, Lead Cask, or Inventory. Pass a storage building's display name or instance id, or `"inventory"`. Inventory participates only at **Nocturna Base**. The call waits for the physical store's feeder cycle to finish, and every participating storage building remains busy during that cycle. Exact item properties are preserved; optional `properties` and `property_match` select a variant. The calling script may run anywhere, but cargo never crosses outpost boundaries through this method.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `target` | `string` | Display name or instance id of another storage endpoint at the same outpost |
| `item_id` | `string` | Item id to move |
| `count` | `number` | Whole-number max units to transfer |
| `properties` | `any` | Optional property dict, matched as a subset by default. Omitted or `None` matches any properties; use `None` with `property_match="exact"` to select propertyless items only. |
| `property_match` | `string` | Optional selection mode: any, subset, or exact |

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
