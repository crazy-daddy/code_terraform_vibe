# Component: supply_dock

> **Category:** Logistics & Orders | **Component Name:** Supply Dock

Ships finished goods to Earth at **25 units/h** before throughput research. A script assigns a contractor or Weekly Earth Order, loads what it needs, and enables dispatch; completion or expiry stops the dock until reassigned.

| Field | Value |
| --- | --- |
| Type | Logistics |
| Power in | -15 W (draws from grid) |

### How to obtain

1. Requires the **Supply Logistics** research (Terraform Index 110,000).
2. Buy from the Shop. Price starts at 5,000 cr and rises as you own more.

**Returned by:** `self / get_component(id)`

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

##### `.input`

Load only what the active Order still needs with `connect(...)` and `take(...)`, or push from a parked cargo vehicle. Excess stays at the source, and active-order cargo stays reserved. After `clear_order()` or completion, use `eject(destination, item_id, count)` to recover leftovers to Inventory at Nocturna Base or local freight elsewhere. `flush()` destroys loaded cargo. Requires **Auto Feeders** research. See `InputSlot`.

- **Returns** Order-aware `InputSlot` that accepts only the active Order's remaining need. After the Order clears or completes, `eject(...)` recovers leftover cargo to explicit local freight; `flush()` destroys it.

### Methods

##### `.capacity()`

Total units still owed across every item of the active Order (the dock's remaining demand). Returns **0** when no Order is assigned. Use as the upper bound for how much you still need to load + ship.

- **Returns** Number: total units still owed across the active Order; **0** when idle.

##### `.total()`

Sum of units currently loaded across every slot. Compare to `capacity()` to see how much more the dock still needs to ingest; `total() == 0` means every slot is empty.

- **Returns** Number: current units summed across every slot.

##### `.count(item_id)`

Units of `item_id` currently held across the dock's slots. Returns **0** if the dock holds none of that item. Use before loading more to avoid redundant `take()` calls: `if self.count("iron_ore") < 20: self.input.take("iron_ore", 20)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `string` | Item id to count |

- **Returns** Number: units of `item_id` currently in any slot.

##### `.slots()`

The dock's physical slots as a list of `DockSlot` objects (`.index`, `.item_id`, `.count`). Always **5** entries, indexed **0-4**; slots not opened by the current Order have `.item_id == None` and `.count == 0`. See `DockSlot`.

- **Returns** List of `DockSlot` objects: one per physical slot (indexes **0-4**).

##### `.current_order()`

Returns this dock's active Earth `Order`, or `None` if no Earth Order is assigned. Flips to `None` automatically when the Earth Order completes. Use it to read `.requires` and `.shipped` before deciding what to load.

- **Returns** `Order` currently assigned to this dock, or `None`.

##### `.set_order(order_id)` *(self only)*

Assign an Earth Order to this dock. Discover ids with `orders.list_orders()` or `orders.list_weekly_orders()`, then pass one to `self.set_order(id)`. Several docks may serve the **same** order and share shipped progress. Cargo is physical: drain this dock through a local machine or vehicle before switching orders.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `order_id` | `string` | Earth Order id from `orders.list_orders()` or `orders.list_weekly_orders()`. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"unknown_order"` | rejection | The supplied order is unknown or currently unavailable for assignment. |
| `"completed"` | success | The requested order is already completed and cannot be assigned again. |
| `"cargo_present"` | rejection | Existing cargo prevents the requested configuration change. |

##### `.clear_order()` *(self only)*

Release this dock's assignment and stop dispatch. Loaded cargo stays inside the dock. Recover it directly with `self.input.eject(destination, item_id, count)`, or by connecting a local machine or vehicle input to this Supply Dock.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.set_enabled(on)` *(self only)*

Toggle the continuous dispatcher. `True` resumes shipping; `False` pauses it. Loading is unaffected either way, the input port still accepts material. **Auto-flips off** when the assigned order completes; the script must re-enable after the next `set_order` call.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `on` | `boolean` | `True` to resume dispatch, `False` to pause |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |

##### `.is_enabled()`

`True` while the dispatcher is active. It becomes `False` after `set_enabled(False)` or when the assigned Order completes. A new dock starts enabled, so assigning an Order while cargo is loaded begins shipping immediately.

- **Returns** Boolean: `True` when the dispatcher is active, `False` after `set_enabled(False)`. Newly deployed docks default to enabled.

##### `.dispatch_rate()`

The dispatcher's current effective throughput in **units/h**, already including throughput research and any outpost overcrowding penalty. The base rate is **25** (one unit every **2.4** minutes); **Bulk Logistics II** multiplies it by **4**, and **Bulk Logistics III** by **16**. Multiply this returned value by hours elapsed to predict how much the dock will ship.

- **Returns** Number: current dispatcher throughput in **units/h**.

##### `.current_dispatch()`

The `item_id` the dispatcher is currently emitting, or `None` when idle (no power, no Order, dispatcher paused via `set_enabled(False)`, or no shippable unit loaded). Useful for scripts that want to know which material is flowing right now.

- **Returns** String item id currently being dispatched, or `None` when the dock is idle (no order, dispatcher paused, or no shippable unit loaded).

##### `.dispatch_progress()`

Fraction **0-1** of the current unit's accumulator toward emission. Holds at **0** while the dock has nothing shippable loaded, the charge starts when a shippable unit lands. Drives the perimeter-clock animation on the dock card; scripts can use it to estimate "next launch in X hours."

- **Returns** Number in **0-1**: fraction of the current unit's accumulation toward emission. At **1.0** a unit is emitted and the counter resets.

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Infrastructure & Fluids*
