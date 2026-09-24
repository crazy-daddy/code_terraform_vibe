# Component: bio_exchange

> **Category:** Terraforming | **Component Name:** Bio Exchange

Delivers biology samples to fulfill a Bio Order, the biology counterpart to the Supply Dock. A script assigns an order and delivers its required fragments until the reward pays out.

| Field | Value |
| --- | --- |
| Type | Atmosphere |
| Power in | -8 W (draws from grid) |
| Input buffer | 10 units |
| Output buffer | 10 units |

### How to obtain

1. Buy from the Shop for 4,000 cr.

**Returned by:** `self / get_component(id)`

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

##### `self.input: InputSlot`

The `InputSlot` for `deliver()` samples. Holds one item id until emptied by `deliver()` or `eject()`. `stacks()` lists property variants, not multiple fragment types. Connect local storage: Inventory at home, a Storage Bin or Warehouse elsewhere. Exact sample properties are preserved. Recover unused samples with `self.input.eject(destination, item_id, count, properties, "exact")`; the destination must be local. Active deliveries keep their samples reserved.

- **Returns** `InputSlot` for property-bearing samples. Inventory is available only at Nocturna Base; remote Exchanges use local freight. Recover an unused exact sample with `eject(destination, item_id, count, properties, "exact")`.

##### `self.output: OutputSlot`

The `OutputSlot` that safely receives a surplus in-transit sample when another Exchange completes the shared order first. Drain it with `send(...)`; exact sample properties are preserved.

- **Returns** `OutputSlot` for a surplus in-transit sample returned because another Exchange completed the shared order first.

### Methods

##### `self.orders() → list[BioOrder]`

Lists every `BioOrder`, including orders you cannot fill yet. Each order includes its id, biome, requirements, reward, status, delivered samples, samples already `in_transit`, completion percent, and any required `target_glow`. Progress is shared by every Bio Exchange serving that order. Use `requires - delivered - in_transit` to avoid making samples that are already committed, then pass the chosen `order.id` to `set_order(...)`. From another script, call `get_component("bio_exchange_1").orders()`. `get_component("orders")` is for Earth Orders.

- **Returns** List of every `BioOrder`. Delivered and in-transit counts are shared across all Bio Exchanges. Other scripts can query a deployed Exchange; Earth Orders come from `get_component("orders")` instead.

##### `self.set_order(order_id: str) → ActionResult` *(self only)*

Pick the Bio Order this Exchange will fill. `self.set_order("bio_order_03")`. Several Exchanges may activate the **same** Bio Order, they cooperate on one shared delivery count, so big Bio Orders can be served from multiple outposts at once.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `order_id` | `str` | Id of a Bio Order from `orders()` (e.g. `"bio_order_01"`). |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"unknown_order"` | rejection | The supplied order is unknown or currently unavailable for assignment. |
| `"completed"` | success | The requested Bio Order is already filled and cannot be assigned again. The order object's own `.status` reads `complete`, and `deliver()` reports `complete` for the delivery that finishes it; `completed` here is the assignment refusal. |

##### `self.clear_order() → ActionResult` *(self only)*

Clear this Exchange's active Bio Order assignment. Already delivered progress stays recorded on the Bio Order, completed Bio Orders stay completed, and no samples are moved.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"busy"` | transient | The component is already performing another operation. |
| `"output_full"` | rejection | Finished work is waiting for space in this machine's output, so nothing else can start. Free the output and the wait ends on its own. |

##### `self.active_order() → BioOrder | None`

A snapshot of the active `BioOrder` object, its `requires`, completed `delivered` progress, live `in_transit` commitments, `percent`, and `target_glow` (coastal infusion target) at the moment you call it, or `None` if no order is set. `in_transit` includes qualifying samples already staged in serving Exchange inputs plus active timed deliveries. Call `active_order()` again to read fresh progress.

- **Returns** A snapshot of the active `BioOrder` object, or `None` if no order is set. Re-query it to read fresh `delivered`, committed `in_transit`, and `percent` progress.

##### `self.matches_order(item_id: str, properties: ItemProperties | None = None) → bool`

Check whether one exact item matches this Exchange's active Bio Order without moving it. Pass the `id` and `properties` from an `ItemStack`. `True` means that variant satisfies the order's glow, genes, Forged, Conditioned, or plain-sample requirement. Use it with Inventory, Storage Bin, or Warehouse `stacks()` before an exact `self.input.take(...)`. Returns `False` when there is no active order, the order is complete, or the item does not qualify.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `str` | Candidate fragment id from an `ItemStack`. |
| `properties` | `ItemProperties \| None` | Exact property dict from the same `ItemStack`, or None for a propertyless sample. |

- **Returns** Boolean. `True` when this exact item-property identity satisfies the active Bio Order's current sample contract. Use it while iterating a storage component's `stacks()` before calling `self.input.take(..., properties, "exact")`. Returns `False` with no active order, for completed orders, or for an invalid/wrong variant.

##### `self.deliver() → ActionResult` *(self only)*

Send one matching sample from `self.input` toward the active Bio Order. `self.deliver()` moves a single sample per call and takes a short time, so a script calls it in a loop until the order is filled. A sample only counts if it satisfies the order's exact requirement, which for some biomes means a specific glow, gene set, or processed variant and not just the right fragment id; `self.matches_order(item_id, properties)` tests one stack before it is taken. Progress is **shared across every Bio Exchange** serving the same Bio Order, so another Exchange may land the final sample first and a surplus sample is refunded.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The sample was accepted toward the active Bio Order, which still requires more samples. |
| `"complete"` | success | The active Bio Order is now filled and its reward has been paid. Shared progress means another Exchange may have contributed the final sample. The order can no longer be assigned. |
| `"no_input"` | rejection | No input material is available. |
| `"output_full"` | rejection | The output has no capacity for the result. |
| `"no_active"` | rejection | There is no active operation of the requested kind. |
| `"busy"` | transient | The component is already performing another operation. |

##### `self.lifetime_credits() → int`

Total credits this Exchange has earned across every completed Bio Order.

- **Returns** Total credits this Exchange has earned across every completed Bio Order.

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Terraforming*
