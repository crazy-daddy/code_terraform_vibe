# Component: inventory

> **Category:** Production & Storage | **Component Name:** Inventory

Inventory is the physical storeroom at **Nocturna Base**. Its page and read-only script methods are visible planet-wide, but ordinary freight to machines or vehicles reaches it only at the home outpost; remote sites use local storage and vehicles. Purchases land here.

Deploy, undeploy, decommission, upgrade, and empty-rig hardware controls are explicit commissioning or service orders, not freight routes. Manual Biology uses Inventory at home and a selected same-outpost Warehouse elsewhere; Habitat reagents are staged locally.

| Field | Value |
| --- | --- |
| Type | Storage |

**Returned by:** `get_component("inventory")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.stacks() → list[ItemStack]`

Lists every occupied item stack as an `ItemStack` with `.id`, `.count`, and exact `.properties`. Items with the same id but different properties appear separately. Storage Bins and Warehouses use the same format, so routing scripts can inspect all three in one way and pass exact properties to transfer methods.

- **Returns** List of occupied property-distinct `ItemStack` snapshots. This is the common storage view also exposed by Storage Bins and Warehouses.

##### `.get_slots() → list[Slot]`

Lists every current Inventory slot. Inventory starts with **36** slots, and Cargo Expansion can increase it to **60**. Stackable items hold **10** units per slot, or **20** after **Bigger Stacks**. Each `Slot` has a zero-based index from `0` through `get_size() - 1`, plus its item id, name, value, count, and properties. Properties are an exact identity dict, or `None` for ordinary items. Use them to distinguish variants with the same id and to select an exact item during transfers.

- **Returns** List of `Slot` snapshots including each stack's exact `.properties` identity.

##### `.count(item_id: str) → int`

How many units of `item_id` are currently stored across all slots. Returns **0** if no slot holds that item. Storage Bins, Warehouses, and Lead Casks expose the same `count(item_id)` query, so one helper can search every store.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `str` | Item id to count |

- **Returns** Number: units of that item across all slots.

##### `.has_space(item_id: str | None = None, properties: ItemProperties | None = None) → bool`

Check whether Inventory has room. With no argument, `has_space()` is `True` when any slot is free. Passing an item id and properties checks that exact variant: a partial stack counts only when both match, while an empty slot accepts it. Pass `slot.properties` when checking an item with properties.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `str \| None` | Optional item id, makes the check stack-aware for that exact variant |
| `properties` | `ItemProperties \| None` | Exact property dict from a `Slot` or `ItemStack`; None selects the propertyless variant |

- **Returns** Boolean, using exact property identity when an item id is supplied.

##### `.space_for(item_id: str, properties: ItemProperties | None = None) → int`

How many units of one exact item identity fit **right now**: remaining room in partial stacks with the same id and properties, plus empty slots times the current stack size. **Bigger Stacks** raises that size from **10** to **20** for stackable items. Use `inventory.space_for(slot.id, slot.properties)` for a property-bearing item. Omitting properties checks the ordinary propertyless variant.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `str` | Item id to size remaining room for |
| `properties` | `ItemProperties \| None` | Exact property dict from a `Slot` or `ItemStack`; None selects the propertyless variant |

- **Returns** Number of units of this exact property variant that fit right now.

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

##### `.drop(slot: int) → ItemResult`

Remove **1** unit from a specific slot by its zero-based index. Valid indexes run from `0` through `get_size() - 1`, including slots added by Cargo Expansion. Dropped items are deleted, not returned to the world; use `shop.sell(item_id)` if you want credits.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `slot` | `int` | Whole-number inventory slot index |

- **Returns** `ItemResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.item_id`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation affected item `.item_id`. |
| `"empty"` | success | The selected item source was already empty. |
| `"invalid_slot"` | rejection | The requested inventory slot does not exist. |

##### `.drop_all(item_id: str) → CountResult`

Remove every unit of `item_id` from inventory. For credits, use `shop.sell_all(item_id)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `str` | Item id to drop every stack of |

- **Returns** `CountResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.count`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The command affected `.count` entries or units. |
| `"no_op"` | success | The command affected no entries or units. |

##### `.get_size() → int`

Current number of Inventory slots. Inventory starts with **36**, and Cargo Expansion can increase it one slot at a time to **60**. Use this value instead of hardcoding a slot count.

- **Returns** Current number of slots (starts at 36, maximum 60)

##### `.get_used() → int`

Number of occupied slots. `get_used() == get_size()` means inventory is full.

- **Returns** Number

*Components / Production & Storage*
