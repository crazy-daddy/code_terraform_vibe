# Component: shop

> **Category:** Core Systems | **Component Name:** Shop

Buys from and sells to Earth. Use `get_component("shop")` to automate surplus sales or purchases when a threshold is reached. The same catalogue and prices are used by the Shop UI.

**Returned by:** `get_component("shop")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.sell(item_id: str, quantity: int = 1) → SaleResult`

Sell a positive whole-number `quantity` of `item_id`, defaulting to **1**. The complete quantity is removed from the lowest-indexed matching Inventory slots in one transaction; if Inventory contains fewer units, nothing is sold. Battery products refund their charge percentage, with a **50% minimum**; fully charged batteries refund their full normal value. Use the Inventory page when you need to choose one exact battery instance.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `str` | Item id to sell |
| `quantity` | `int` | Positive whole-number units to sell; defaults to 1 |

- **Returns** `SaleResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.item_id`, `.units`, `.credits`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Sale completed: `.item_id` × `.units`; received `.credits` cr. |
| `"not_sellable"` | rejection | The requested item cannot be sold. |
| `"no_stock"` | rejection | Inventory does not contain the requested quantity of the item. |

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | `quantity` must be a finite whole number. |
| `ValueError` | `quantity` must be greater than zero. |
| `OverflowError` | `quantity` must fit within the supported whole-number range. |

##### `.sell_all(item_id: str) → SaleResult`

Sell every unit of `item_id` currently in Inventory in one transaction. There is no per-unit cooldown. Each battery product is valued from its own retained charge, with a **50% minimum** and full normal value at full charge.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `str` | Item id to sell every stack of |

- **Returns** `SaleResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.item_id`, `.units`, `.credits`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Sale completed: `.item_id` × `.units`; received `.credits` cr. |
| `"not_sellable"` | rejection | The requested item cannot be sold. |
| `"no_stock"` | rejection | Inventory does not contain the requested quantity of the item. |

##### `.buy(item_id: str, quantity: int = 1) → ActionResult`

Buy a positive whole-number `quantity` of `item_id`, defaulting to **1**. The complete quantity must be affordable and fit in base Inventory; otherwise nothing is charged or delivered. Purchases are placed in base Inventory, not delivered directly to a machine or remote outpost.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `str` | Shop item id (machine kit, module, pack, reagent, or equipment) |
| `quantity` | `int` | Positive whole-number units to buy; defaults to 1 |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_found"` | rejection | The requested object, target, or record does not exist. |
| `"locked"` | rejection | The required feature, recipe, or operation is locked. |
| `"insufficient_credits"` | rejection | The available credits are below the total cost of the requested purchase. |
| `"inventory_full"` | rejection | Inventory has no capacity for the result. |

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | `quantity` must be a finite whole number. |
| `ValueError` | `quantity` must be greater than zero. |
| `OverflowError` | `quantity` must fit within the supported whole-number range. |

##### `.get_catalogue() → list[ShopItem]`

Every available catalogue entry as a list of `{id, name, cost}` objects. Use to pick a target dynamically or to show a filtered picker in a script. The Earth shop never runs out of catalogue items; entries hidden by tech gates don't appear.

- **Returns** List of {id, name, cost}

*Components / Core Systems*
