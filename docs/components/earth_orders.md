# Component: earth_orders

> **Category:** Logistics & Orders | **Component Name:** Earth Orders

Read Earth's current orders, future campaign requirements and rewards, and completed campaign history through `get_component("orders")`. Supply Dock scripts can use campaign and Weekly Orders to decide what to ship, while dashboards can show progress. Scripts cannot create or cancel Earth Orders. Bio Orders come from a Bio Exchange instead.

**Returned by:** `get_component("orders")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.list_orders()`

Current contractor campaign Orders as a stable list of `Order` objects. These orders never expire and disappear from this list when fully shipped. Empty means no contractor shipment is currently available. See `Order`.

- **Returns** List of current contractor campaign `Order` objects.

##### `.list_upcoming_orders()`

Plan future production and reward paths with upcoming contractor campaign Orders, in campaign declaration order, preserving each contractor's queue sequence. Excludes current orders, completed orders, and Weekly Earth Orders. Upcoming orders cannot be assigned to Supply Docks until they become current. See `Order`.

- **Returns** List of future campaign `Order` objects with status `"upcoming"`, in campaign declaration order. Empty when no upcoming campaign orders remain.

##### `.list_weekly_orders()`

The current five Weekly Earth Orders, including offers already fulfilled during this cycle. Returns an empty list until an eligible production chain is available. Weekly objects have `.kind == "weekly"`, `.expires_day`, no contractor, credits-only rewards, and `.status` of `"active"` or `"completed"`. The whole list is replaced every seven days.

- **Returns** The current five Weekly Earth `Order` objects, including offers already fulfilled this cycle; an empty list until an eligible production chain is available.

##### `.get_order(order_id)`

Look up a specific Earth Order by id, including upcoming campaign orders for planning. Upcoming orders cannot be assigned to Supply Docks until they become current. Unknown or expired weekly ids return `None`; weekly completions remain visible only until their board refreshes. See `Order`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `order_id` | `string` | Earth Order id from `list_orders()`, `list_upcoming_orders()`, `list_weekly_orders()`, or `completed_orders()` |

- **Returns** Campaign `Order` with status `"upcoming"`, `"active"`, or `"completed"`, or a Weekly Earth Order from the current board. Unknown or expired weekly ids return `None`. Bio Order ids are read from a Bio Exchange.

##### `.completed_orders()`

Permanent contractor campaign history, ordered by completion time (oldest first). Weekly completions stay on the current Weekly board and are intentionally excluded from this ledger.

- **Returns** List of Earth `Order` objects already delivered, in order of completion.

*Components / Logistics & Orders*
