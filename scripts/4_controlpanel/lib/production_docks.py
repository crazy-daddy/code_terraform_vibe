# Supply Dock orders: every active order across the dock fleet, the units each
# still owes, and where each order is consumed.
from swallow import swallowed
from production_core import discover_supply_dock_ids, home_outpost_id, log, machine_outpost_id, _add_demand, _component


def _all_dock_orders():
    """
    [(dock_component, order), ...] for every discovered Supply Dock currently
    holding an active order (docks with no order, or that can't be reached,
    are simply absent from the list). Single source of truth for "every
    current order across the whole dock fleet" -- every demand-cascade
    function loops this instead of reading one hardcoded dock.
    """
    ids = discover_supply_dock_ids()
    if not ids:
        ids = ["supply_dock_1"]  # last-resort fallback if discovery finds nothing
    pairs = []
    for dock_id in ids:
        dock = _component(dock_id)
        if not dock or not hasattr(dock, "current_order"):
            continue
        try:
            order = getattr(dock, "current_order")()
        except Exception as error:
            swallowed("production_docks._all_dock_orders: getattr(dock, 'current_order')", error)
            continue
        if order:
            pairs.append((dock, order))
    return pairs


def _dock_order_remaining():
    """
    {order_id: {item_id: units}} still owed per active order:
    required - shipped - units already loaded into every dock serving it.

    Deduplicated per order: several docks may serve the same order and share
    its shipped progress (docs/components/supply_dock.md), so looping
    _all_dock_orders() pairs and adding each dock's remaining counted a
    shared order once per dock (seen live: spire_13 on two docks demanded
    120 Neutronium Bars for a 60-bar order). Loaded-but-undispatched units
    are in neither Inventory nor order.shipped, so every dock's count() is
    summed and subtracted -- without that, producers re-craft whatever sits
    in the dock and overshoot the order by that much (seen live: 104 Heli
    Thrusters / 204 small Oil Tanks for 100/200 orders, the extras stranded
    in Inventory, one slot each). Negative remainders are kept; callers clamp.
    """
    loaded_by_order = {}
    orders_by_id = {}
    for dock, order in _all_dock_orders():
        if not hasattr(order, "requires"):
            continue
        order_id = getattr(order, "id", None)
        orders_by_id[order_id] = order
        loaded = loaded_by_order.setdefault(order_id, {})
        if not hasattr(dock, "count"):
            continue
        try:
            for item_id in order.requires:
                loaded[item_id] = loaded.get(item_id, 0) + dock.count(item_id)
        except Exception as error:
            swallowed("production_docks._dock_order_remaining: loaded.get", error)

    result = {}
    for order_id, order in orders_by_id.items():
        try:
            shipped = getattr(order, "shipped", {}) or {}
            loaded = loaded_by_order.get(order_id, {})
            result[order_id] = {
                item_id: required - shipped.get(item_id, 0) - loaded.get(item_id, 0)
                for item_id, required in (getattr(order, "requires", {}) or {}).items()
            }
        except Exception as error:
            swallowed("production_docks._dock_order_remaining: loaded_by_order.get", error)
    log.trace(f"_dock_order_remaining: {len(orders_by_id)} distinct active order(s) -> {result}")
    return result


def _dock_order_sites():
    """{order_id: [outpost ids of every dock holding it]} -- where each active
    order's items are consumed."""
    sites = {}
    for dock, order in _all_dock_orders():
        order_id = getattr(order, "id", None)
        site_id = machine_outpost_id(dock) or home_outpost_id()
        bucket = sites.setdefault(order_id, [])
        if site_id not in bucket:
            bucket.append(site_id)
    return sites


def find_dock_order_requiring(item_id):
    """
    First (dock, order) pair, across every discovered Supply Dock, whose
    active order still requires item_id (regardless of how much has already
    shipped -- callers that care about remaining-vs-shipped check that
    themselves). (None, None) if no current order anywhere requires it.
    Shared by production_demand.get_raw_material_reason() and lib/fabricator.py's
    target_reason(), so "which dock wants this" is answered in one place.
    """
    for dock, order in _all_dock_orders():
        if item_id in (getattr(order, "requires", {}) or {}):
            return dock, order
    return None, None


def dock_remaining_requirements(outpost_id=None):
    """{item_id: units} still owed (required - shipped - already loaded into
    the dock) across every active Supply Dock order. With `outpost_id`, only
    orders held by a dock at that outpost (_dock_order_sites(); an order held
    at two outposts counts at both). lib/smelter.py subtracts its own site's
    figure from raw ore it may refine, so real ingot demand can't eat ore a
    dock order ships raw."""
    sites = _dock_order_sites() if outpost_id is not None else None
    remaining_by_item = {}
    for order_id, remaining_for_order in _dock_order_remaining().items():
        if sites is not None and outpost_id not in sites.get(order_id, ()):
            continue
        for item_id, remaining in remaining_for_order.items():
            _add_demand(remaining_by_item, item_id, remaining)
    return remaining_by_item


def dock_owed_at(item_id, outpost=None):
    """[(dock_id, units)] for every Supply Dock at `outpost` (None = home)
    whose active order still owes item_id: required - shipped - what this
    outpost's docks on that order already hold. Docks sharing an order each
    get the order's whole remainder; the dock input takes only what the
    order still needs, so a second dock is a fallback, not extra demand."""
    if outpost is None:
        network = _component("outpost_network")
        try:
            outpost = network.home() if network else None
        except Exception as error:
            swallowed("production_docks.dock_owed_at: network.home", error)
            outpost = None
    if outpost is None:
        return []
    rows = []
    loaded_by_order = {}
    for dock_id in discover_supply_dock_ids(outpost):
        dock = _component(dock_id)
        if dock is None:
            continue
        try:
            order = dock.current_order()
            required = ((getattr(order, "requires", None) or {}).get(item_id, 0)) if order else 0
            if required <= 0:
                continue
            order_id = getattr(order, "id", None)
            loaded_by_order[order_id] = loaded_by_order.get(order_id, 0) + dock.count(item_id)
            rows.append((dock_id, order_id, required - (getattr(order, "shipped", None) or {}).get(item_id, 0)))
        except Exception as error:
            swallowed("production_docks.dock_owed_at: dock order read", error)
    return [(dock_id, owed - loaded_by_order.get(order_id, 0)) for dock_id, order_id, owed in rows if owed - loaded_by_order.get(order_id, 0) > 0]
