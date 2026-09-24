# Component: item_catalog

> **Category:** Storage & Inventory | **Component Name:** Item Catalog

Looks up static identity metadata for any known item id. Use `get_component("item_catalog")` when a script needs to classify an item without maintaining its own data archive.

**Returned by:** `get_component("item_catalog")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.lookup(item_id: str) → ItemInfo | None`

Return an `ItemInfo` with `.id`, `.name`, `.category`, `.stackable`, `.biome`, `.rarity`, and `.production_tier`. Categories distinguish `"mineral"`, `"refined"`, `"crafted"`, `"agriculture"`, `"life_form"`, `"field_resource"`, `"biology_sample"`, `"reagent"`, `"equipment"`, `"module"`, `"portable"`, `"upgrade_pack"`, and `"construction_kit"`. Production tier is `None` for source items and biome and rarity are `None` when they do not apply. An unknown item id returns `None`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `str` | Item id to identify |

- **Returns** `ItemInfo` with identity metadata, or `None` for an unknown item id.

```python
catalog = get_component("item_catalog")
item = catalog.lookup("water_pump")
if item is not None:
    print(item.category, item.production_tier)
```

*Components / Weather & Sky*
