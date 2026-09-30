# What a vehicle/drone is doing and for whom, as one short line for the
# FLEET/DRONE FLEET cards (fleet.status[name]["intent"], lib/fleet_status.py).
# E.g. "hauling iron_ore from outpost_1 to outpost_home for supply_dock_1".
#
# Production demand is pooled: lib/production.py folds every source into one
# target per item, so a hauler knows home is short of iron_ore but not who
# wants it. demand_root() walks the recipe tree down from each demand root
# and names the first one whose tree reaches the item, so the label is the
# origin of the chain (supply_dock_1), not the next consumer (smelter_1).
# Roots are tried in lib/fabricator.py choose_recipe() priority order:
#   "manual_order"          fabricator.manual_orders
#   "blueprint <kind>"      pending/paused Construction Blueprint jobs
#   "upgrade <requester>"   fabricator.upgrade_orders
#   "<dock id>"             Supply Dock active orders
#   "<requester>"           logistics.requests "by" (seed_maker, ...)
#   "stock_target"          fabricator.stock_targets
#   "ore_buffer"            home raw-ore floor (outpost_mining.ore_stock_target())
# Two passes: first only along items still short of stock (the path demand
# actually propagates), then along any recipe path.

import logistics_requests
from archive import archive
from production import SourceCache, _recipe_inputs_for, _all_dock_orders, _dock_order_remaining, get_manual_orders, get_fabricator_stock_targets, UPGRADE_ORDERS_KEY
from outpost_mining import RAW_ORE_ITEM_IDS, HOME_OUTPOST_ID
from tree_console import TreeConsole
from swallow import swallowed

log = TreeConsole(module="fleet_intent")

# Same generous bound as production.py's demand cascades.
ROOT_WALK_DEPTH = 6


def _add(bucket, item_id, units):
    if item_id and units > 0:
        bucket[item_id] = bucket.get(item_id, 0) + units


def _blueprint_roots():
    roots = {}
    try:
        bp = get_component("construction_blueprint")
    except Exception as error:
        swallowed("fleet_intent._blueprint_roots: get_component", error)
        return []
    if not bp:
        return []
    seen = set()
    for getter_name in ("pending_constructions", "paused_constructions"):
        getter = getattr(bp, getter_name, None)
        if not getter:
            continue
        try:
            for job in getter():
                job_id = getattr(job, "id", None)
                if job_id in seen:
                    continue
                seen.add(job_id)
                label = f"blueprint {getattr(job, 'kind', None) or 'job'}"
                _add(roots.setdefault(label, {}), getattr(job, "required_item", None), getattr(job, "required_count", 0) or 0)
        except Exception as error:
            swallowed("fleet_intent._blueprint_roots: getter", error)
    return [(label, items) for label, items in roots.items() if items]


def _upgrade_roots():
    stored = archive.get(UPGRADE_ORDERS_KEY, {})
    if not isinstance(stored, dict):
        return []
    roots = []
    for requester, items in stored.items():
        if isinstance(items, dict):
            wanted = {i: q for i, q in items.items() if isinstance(q, (int, float)) and q > 0}
            if wanted:
                roots.append((f"upgrade {requester}", wanted))
    return roots


def _dock_roots():
    remaining = _dock_order_remaining()
    roots, seen = [], set()
    for dock, order in _all_dock_orders():
        order_id = getattr(order, "id", None)
        if order_id in seen:
            continue
        seen.add(order_id)
        items = {i: u for i, u in remaining.get(order_id, {}).items() if u > 0}
        if items:
            roots.append((str(getattr(dock, "id", None) or order_id), items))
    return roots


def _request_roots(requests):
    by_requester = {}
    for items in requests.values():
        for item_id, entry in items.items():
            requester = entry.get("by") or "request"
            _add(by_requester.setdefault(requester, {}), item_id, max(0, (entry.get("target", 0) or 0) - (entry.get("have", 0) or 0)))
    return [(r, items) for r, items in by_requester.items() if items]


def demand_roots(curr_tick=None):
    """[(label, {item_id: units})] of every demand root, in attribution priority order."""
    roots = []
    manual = get_manual_orders()
    if manual:
        roots.append(("manual_order", manual))
    roots.extend(_blueprint_roots())
    roots.extend(_upgrade_roots())
    roots.extend(_dock_roots())
    roots.extend(_request_roots(logistics_requests.active_requests(curr_tick)))
    stock_targets = {i: q for i, q in get_fabricator_stock_targets().items() if q > 0}
    if stock_targets:
        roots.append(("stock_target", stock_targets))
    return roots


def _path_to(seeds, item_id, cache, shortfall_only):
    """Recipe path [item_id, ..., seed] from one root's seeds down to item_id, or None."""
    frontier = dict(seeds)
    parent = {i: None for i in seeds}
    seen = set()
    for _depth in range(ROOT_WALK_DEPTH + 1):
        if not frontier:
            return None
        next_frontier = {}
        for current, want in frontier.items():
            if current in seen:
                continue
            seen.add(current)
            short = want - cache.stock(current)
            if shortfall_only and short <= 0:
                continue
            if current == item_id:
                path = [current]
                while parent.get(path[-1]) is not None:
                    path.append(parent[path[-1]])
                return path
            carried = short if shortfall_only else want
            for input_id, ratio in (_recipe_inputs_for(current, cache) or {}).items():
                if input_id not in parent:
                    parent[input_id] = current
                next_frontier[input_id] = next_frontier.get(input_id, 0) + carried * ratio
        frontier = next_frontier
    return None


def demand_root(item_id, roots=None, cache=None, curr_tick=None):
    """Label of the demand root whose recipe tree reaches item_id (see module header), or None."""
    log.start(f"demand_root({item_id})", level="debug")
    cache = cache if cache is not None else SourceCache()
    roots = roots if roots is not None else demand_roots(curr_tick)
    for shortfall_only in (True, False):
        for label, seeds in roots:
            path = _path_to(seeds, item_id, cache, shortfall_only)
            if path:
                log.debug(f"{label} via {' <- '.join(path)}{'' if shortfall_only else ' (no shortfall on path)'}.")
                log.end()
                return label
    if item_id in RAW_ORE_ITEM_IDS:
        log.debug("no root reaches it; home ore buffer floor.")
        log.end()
        return "ore_buffer"
    log.debug("no root reaches it.")
    log.end()
    return None


def haul_root(items, dest_outpost_id=None, curr_tick=None):
    """
    Label for who a load of `items` ({item_id: units} or ids) is ultimately
    for. A logistics request at dest_outpost_id (any outpost when None)
    names its requester; at home (or with no dest) anything else goes
    through demand_root(). Different roots across items read "a +N".
    """
    ordered = sorted(items, key=lambda i: -items.get(i, 0)) if isinstance(items, dict) else list(items)
    if not ordered:
        return None
    labels = []
    roots = cache = None
    try:
        requests = logistics_requests.active_requests(curr_tick)
        for item_id in ordered:
            label = None
            for o_id, wanted in requests.items():
                if (dest_outpost_id is None or o_id == dest_outpost_id) and item_id in wanted:
                    label = wanted[item_id].get("by")
                    break
            if label is None and dest_outpost_id in (None, HOME_OUTPOST_ID):
                if roots is None:
                    roots, cache = demand_roots(curr_tick), SourceCache()
                label = demand_root(item_id, roots, cache, curr_tick)
            if label and label not in labels:
                labels.append(label)
    except Exception as error:
        swallowed("fleet_intent.haul_root", error)
    if not labels:
        return None
    return labels[0] + (f" +{len(labels) - 1}" if len(labels) > 1 else "")


def describe(verb, items=None, source=None, dest=None, root=None, at=None):
    """ "hauling iron_ore +1 from outpost_1 to outpost_home for supply_dock_1",
    "mining titanium at poi_12_40 for blueprint thermal_cap"; every part but verb optional."""
    text = verb
    if items:
        ordered = sorted(items, key=lambda i: -items.get(i, 0)) if isinstance(items, dict) else list(items)
        text += f" {ordered[0]}" + (f" +{len(ordered) - 1}" if len(ordered) > 1 else "")
    if at:
        text += f" at {at}"
    if source:
        text += f" from {source}"
    if dest:
        text += f" to {dest}"
    if root:
        text += f" for {root}"
    return text
