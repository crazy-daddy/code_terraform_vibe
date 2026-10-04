# Models: Earth Orders & Logistics Demands Models

Granular data models and return types extracted from `__builtins__.pyi`.

## `Order`

```python
class Order:
    """orders.list_orders() / orders.list_upcoming_orders() / orders.list_weekly_orders() / orders.get_order() / orders.completed_orders() (Earth Orders)"""
    id: _str
    name: _str
    requires: _dict[_str, _int]
    shipped: _dict[_str, _int]
    reward_credits: _int
    reward_kind: Literal["recipe", "tech"] | None
    reward_label: _str | None
    status: Literal["upcoming", "active", "completed"]
    kind: Literal["campaign", "weekly"]
    expires_day: _int | None
    contractor_id: Literal["helios_orbital", "spire_research", "vestibule_logistics"] | None
    contractor_name: _str | None
```

## `Orders`

```python
class Orders(Component):
    """Earth Orders: Read Earth's current orders, future campaign requirements and rewards, and completed campaign history through `get_component(\"orders\")`. Supply Dock scripts can use campaign and Weekly Orders to decide what to ship, while dashboards can show progress. Scripts cannot create or cancel Earth Orders. Bio Orders come from a Bio Exchange instead."""
    name: _str
    def list_orders(self) -> _list[Order]:
        """Current contractor campaign Orders as a stable list of `Order` objects. These orders never expire and disappear from this list when fully shipped. Empty means no contractor shipment is currently available. See `Order`."""
        ...
    def list_upcoming_orders(self) -> _list[Order]:
        """Plan future production and reward paths with upcoming contractor campaign Orders, in campaign declaration order, preserving each contractor's queue sequence. Excludes current orders, completed orders, and Weekly Earth Orders. Upcoming orders cannot be assigned to Supply Docks until they become current. See `Order`."""
        ...
    def list_weekly_orders(self) -> _list[Order]:
        """The current five Weekly Earth Orders, including offers already fulfilled during this cycle. Returns an empty list until an eligible production chain is available. Weekly objects have `.kind == \"weekly\"`, `.expires_day`, no contractor, credits-only rewards, and `.status` of `\"active\"` or `\"completed\"`. The whole list is replaced every seven days."""
        ...
    def get_order(self, order_id: _str) -> Order | None:
        """Look up a specific Earth Order by id, including upcoming campaign orders for planning. Upcoming orders cannot be assigned to Supply Docks until they become current. Unknown or expired weekly ids return `None`; weekly completions remain visible only until their board refreshes. See `Order`."""
        ...
    def completed_orders(self) -> _list[Order]:
        """Permanent contractor campaign history, ordered by completion time (oldest first). Weekly completions stay on the current Weekly board and are intentionally excluded from this ledger."""
        ...
```
