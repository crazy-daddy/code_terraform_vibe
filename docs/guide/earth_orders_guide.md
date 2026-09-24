# Guide: earth_orders_guide

## Earth Orders

Earth requests materials through **contractor campaign orders** and the separate **Weekly Earth Orders** board. Both use Supply Docks and the same `Order` API. Orders are supply lines; Contracts are puzzles.

### Contractor campaign orders

Helios Orbital, Spire Research, and Vestibule Logistics each expose the first unfinished order in their authored queue. These orders never expire. `orders.list_orders()` returns only the three current contractor slots, and completed campaign orders enter the permanent Completed Orders ledger. Contractor Reputation can increase their credit payout, and some campaign orders unlock technology or recipes.

### Planning ahead

The Order Manifest and `orders.list_upcoming_orders()` reveal upcoming campaign requirements and rewards. The list preserves campaign declaration order, including each contractor's queue sequence, and excludes current orders, completed orders, and Weekly Earth Orders. Use `.contractor_id` to focus on one reward path. `orders.get_order(id)` also reads an upcoming order directly.

Upcoming orders have `.status == "upcoming"` and empty `.shipped` counts. Their credit rewards are quoted at your current reputation and may increase before fulfillment. Reading an order does not make it assignable: Supply Docks still accept only current orders.

### Weekly Earth Orders

The Weekly Orders tab is a dedicated full-width board with **five** progressive offers. It waits until you have uncovered an eligible mining or production chain, so `orders.list_weekly_orders()` can initially be empty. Once available, higher production tiers appear as your save uncovers their chains, and unavailable tiers fall back to earlier materials. An offer is an opportunity, not a guaranteed weekly completion: a known chain may still require machinery or infrastructure you have not built yet. The board starts on the day that an eligible chain appears and refreshes as a whole when its **seventh later day begins**. For example, a board created on Day 40 refreshes when Day 47 begins.

Weekly orders are credits-only. Their combined base payout stays at or below **20,000 credits**, or **40,000 credits** once **Bulk Orders** research doubles the board, Contractor Reputation does not multiply it, and fulfilled weekly rows remain visible until refresh. They do not enter the permanent campaign ledger. Read the board with `orders.list_weekly_orders()`; weekly objects have `.kind == "weekly"`, an `.expires_day`, and no contractor.

At refresh, every unfinished weekly order and all shipped progress expire permanently. Supply Docks assigned to the old board are unassigned and disabled. Cargo that was loaded but had not shipped remains inside its dock. The game posts a warning toast only when at least one unit actually shipped toward an unfinished weekly order; assigning or loading a dock without shipping stays silent. The toast remains available in **Computer > Notifications**, and scheduled refreshes do not create navigation badges.

### Supply Dock workflow

1. **Pick an order.** Read `orders.list_orders()` or `orders.list_weekly_orders()`, then call `self.set_order(order.id)`.
2. **Load it.** Iterate `self.current_order().requires` and call `self.input.take(item_id, count)`. The dock refuses overshoot.
3. **Enable dispatch.** Call `self.set_enabled(True)`. Several docks may serve the same order and share shipped progress.
4. **React to release.** Completion or weekly expiry clears `current_order()` and disables dispatch, so the script must choose again and re-enable.

Each dock dispatches continuously at `self.dispatch_rate()` units/h. `self.current_dispatch()` reports the item leaving now and `self.dispatch_progress()` reports the next-unit fraction. Loaded units always remain physical cargo. `clear_order()` releases the assignment but leaves those units in the dock; a different `set_order(...)` produces an `ActionResult` with `.status == "cargo_present"` until a local machine or vehicle drains them.

### Rewards and identity

Credits and unlocks apply automatically when the final required unit lands. Recipe rewards unlock the named recipe at its stated machine. Technology rewards make the named upgrade pack available for purchase in the Shop; they do not place a free pack in Inventory. Campaign objects have `.kind == "campaign"`, contractor identity, and no expiry. Weekly objects have `.kind == "weekly"`, `contractor_id == None`, `contractor_name == None`, and a board expiry day. Use `orders.get_order(id)` for upcoming or current orders and permanent campaign completions; unknown or expired weekly ids return `None`.

*Guide / Automation Systems*
