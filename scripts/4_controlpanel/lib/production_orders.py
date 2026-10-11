# Archive-backed Fabricator order books: manual orders (and their units in
# transit home), fleet upgrade and backlog orders.
from archive import archive
from storage import outpost_is_home
from swallow import swallowed
from production_core import log
from production_source import SourceCache
from script_parking import wake_on_rise
from priority import clamp, ladder_total, STOCK, UPGRADE


MANUAL_ORDERS_KEY = "fabricator.manual_orders"


def get_manual_orders():
    """{item_id: quantity_still_wanted} -- ad-hoc Fabricator build requests, edited directly in the
    Data Archive Notebook (e.g. {"drone_small": 2}) on top of the standing orders
    get_fabricator_targets() already covers. No default is seeded: an empty manual
    order list is the normal state. Counted down
    to 0 (then dropped entirely) as the Fabricator actually delivers finished units -- see
    consume_manual_order(), called from lib/fabricator.py's drain_output()."""
    if not archive.has(MANUAL_ORDERS_KEY):
        archive.set(MANUAL_ORDERS_KEY, {})
    stored = archive.get(MANUAL_ORDERS_KEY, {})
    if not isinstance(stored, dict):
        return {}
    return {
        item_id: int(qty) for item_id, qty in stored.items()
        if isinstance(qty, (int, float)) and qty > 0
    }


def consume_manual_order(item_id, quantity, outpost: "OutpostRef | None" = None):
    """Counts down an active manual build order (see get_manual_orders()) by quantity actually
    drained from a machine's output, dropping the entry entirely once it reaches zero. No-ops if
    item_id has no active manual order or quantity <= 0. Units drained off home (`outpost` given
    and not home) are recorded in MANUAL_TRANSIT_KEY, which keeps them wanted at home until they
    arrive there (manual_transit_wants())."""
    if not item_id or quantity <= 0:
        return
    # Plain read first: archive.transaction() always writes the key back, even when the updater
    # returns it unchanged, which locks out manual Notebook edits of fabricator.manual_orders.
    # Only transact when item_id actually has an active order to count down.
    wanted = get_manual_orders().get(item_id, 0)
    if wanted <= 0:
        return
    if outpost is not None and not outpost_is_home(outpost):
        _record_manual_transit(item_id, min(wanted, quantity))

    def updater(stored):
        stored = dict(stored or {})
        remaining = stored.get(item_id)
        if not isinstance(remaining, (int, float)):
            remaining = None
        if remaining is None or remaining <= 0:
            return stored
        remaining -= quantity
        if remaining <= 0:
            del stored[item_id]
        else:
            stored[item_id] = remaining
        return stored

    try:
        archive.transaction(MANUAL_ORDERS_KEY, {}, updater)
    except Exception as error:
        swallowed("production_orders.consume_manual_order: archive.transaction", error)


# Manual-order units built off home and not yet at home: {item_id: {"units": n,
# "base": home stock when recorded}}. Home wants base + units of the item
# (fabricator_root_targets() consumers), so site_supply hauls them home. An
# entry ends once home stock reaches base + units, or once none of the item is
# left off home (remote Warehouses + cargo aboard haulers): nothing more can
# arrive.
MANUAL_TRANSIT_KEY = "fabricator.manual_transit"


def _record_manual_transit(item_id, units):
    try:
        base = SourceCache().held_stock(item_id)
    except Exception as error:
        swallowed("production_orders._record_manual_transit: SourceCache.held_stock", error)
        base = 0

    def updater(stored):
        stored = dict(stored) if isinstance(stored, dict) else {}
        # Earlier units still on their way: keep the first base so they stay
        # counted on top of it.
        earlier = _parse_transit(stored).get(item_id)
        if earlier:
            stored[item_id] = {"units": earlier[0] + units, "base": earlier[1]}
        else:
            stored[item_id] = {"units": units, "base": base}
        return stored

    try:
        archive.transaction(MANUAL_TRANSIT_KEY, {}, updater)
    except Exception as error:
        swallowed("production_orders._record_manual_transit: archive.transaction", error)
    log.debug(f"manual order: {units}x {item_id} built off home, wanted at home until home stock reaches {base} + units")


def _manual_transit_entries():
    return _parse_transit(archive.get(MANUAL_TRANSIT_KEY, {}))


def _parse_transit(stored):
    """{item_id: (units, base)} from a stored MANUAL_TRANSIT_KEY value."""
    if not isinstance(stored, dict):
        return {}
    entries = {}
    for item_id, entry in stored.items():
        if not isinstance(entry, dict):
            continue
        units = entry.get("units")
        base = entry.get("base", 0)
        if isinstance(units, (int, float)) and units > 0 and isinstance(base, (int, float)):
            entries[item_id] = (int(units), max(0, int(base)))
    return entries


def _settle_transit(entries, cache: "SourceCache"):
    """{item_id: (units, base)} with arrived units removed (see MANUAL_TRANSIT_KEY)."""
    settled = {}
    for item_id, (units, base) in entries.items():
        home = cache.held_stock(item_id)
        if home < base + units and cache.network_stock(item_id) > home:
            settled[item_id] = (units, base)
    return settled


def manual_transit_wants(cache: "SourceCache | None" = None):
    """{item_id: units wanted at home} for manual-order units still off home."""
    entries = _manual_transit_entries()
    if not entries:
        return {}
    cache = SourceCache() if cache is None else cache
    return {item_id: base + units for item_id, (units, base) in _settle_transit(entries, cache).items()}


def reconcile_manual_transit(cache: "SourceCache | None" = None):
    """Writes MANUAL_TRANSIT_KEY back without arrived units. Writes only on change."""
    stored = archive.get(MANUAL_TRANSIT_KEY, {})
    if not stored:
        return
    cache = SourceCache() if cache is None else cache
    entries = _manual_transit_entries()
    settled = _settle_transit(entries, cache)
    updated = {item_id: {"units": units, "base": base} for item_id, (units, base) in settled.items()}
    if updated == stored:
        return
    for item_id in entries:
        if item_id not in settled:
            log.print(f"[production] Manual order {item_id}: no units left to haul home.")
    archive.set(MANUAL_TRANSIT_KEY, updated)


# The Fabricator order book: ONE shared dict (CODE_GUIDES.md#archive)
#   fabricator.orders = {requester_id: {item_id: [units, prio]}}
# Each requester -- the fleet coordinator, a drone wanting a bigger Cargo Pod,
# the Harvester, a Plant Terraformer, site supply -- owns and clears only its
# own entry. `units` is a "keep at least this many in stock" floor, `prio`
# the priority band of that floor (lib/priority.py). An item entry may hold
# several pairs (order_levels(): a need floor at one prio and a stock
# buffer at a lower one). Floors of one item are summed per prio across
# requesters and accumulated down the prios into a ladder (order_ladders()).
ORDERS_KEY = "fabricator.orders"
# Requesters in ORDERS_KEY that aren't drones. fleet_upgrade._prune() drops
# every other entry whose drone no longer exists, so a standing order from
# another script must be listed here. "field_keeper" = the Harvester's
# field-machine kits (lib/harvester_machines.py). "bio_caster" = the Bio
# Caster's forge materials for all open Volcanic bio orders
# (lib/bio_volcanic.py). "fleet_commission" = a drone kit the FLEET card's
# Commission tab queued (lib/drone_commission.py). "plant_terraformer" = the
# Plant Terraformers' Fertilizer / Growth Accelerant batches
# (lib/plant_terraformer_demand.py). "fuel_assembler" = the Fuel Assemblers'
# Lead Plates for their next crafts (lib/fuel_assembler.py).
# "field_amplifier" = the Harvester's Yield Amplifier doses
# (lib/harvester_amplify.py). "site_stock" / "construction_stock" = the
# crafted site stockpiles and the construction stock (lib/site_supply.py).
# "drone_kit_stock" = one Depot / Service Station kit while an outpost lacks
# one (lib/drone_kit_stock.py). "key_unlock_ahead" = the next key unlock
# orders' items (lib/supply_dock.py publish_key_ahead()).
STANDING_ORDER_REQUESTERS = ("field_keeper", "bio_caster", "fleet_commission", "plant_terraformer", "fuel_assembler", "field_amplifier", "site_stock", "construction_stock", "drone_kit_stock", "key_unlock_ahead")
# Requesters whose items are consumed at the outposts that request them
# through site supply (lib/site_supply.py SITE_STOCK_TARGETS and the
# construction stock), not at home: they raise the Fabricator targets but
# make home no consumer (lib/production_cascade.py fabricator_root_targets()),
# so home doesn't pull the stockpiles back.
SITE_ORDER_REQUESTERS = ("site_stock", "construction_stock")


def order_levels(need=0, need_prio=UPGRADE, stock=0, stock_prio=STOCK):
    """[units, prio] pairs for one item of a requester's order: `need` units
    at need_prio and `stock` more at stock_prio, as a list of pairs
    (set_order() takes several per item). Zero parts are left out."""
    levels = []
    if need > 0:
        levels.append([int(need), need_prio])
    if stock > 0:
        levels.append([int(stock), stock_prio])
    return levels


def get_orders(skip=()):
    """{requester: {item_id: [[units, prio], ...]}} of every valid entry in ORDERS_KEY, except the requesters in `skip`."""
    stored = archive.get(ORDERS_KEY, {})
    if not isinstance(stored, dict):
        return {}
    orders = {}
    for requester, items in stored.items():
        if requester in skip or not isinstance(items, dict):
            continue
        parsed = {}
        for item_id, levels in items.items():
            pairs = _order_pairs(levels)
            if pairs:
                parsed[item_id] = pairs
        if parsed:
            orders[requester] = parsed
    return orders


def _order_pairs(levels):
    """Valid [units, prio] pairs of one stored item entry ([units, prio] or a list of them)."""
    if isinstance(levels, (list, tuple)) and len(levels) == 2 and isinstance(levels[0], (int, float)) and isinstance(levels[1], (int, float)):
        levels = [levels]
    if not isinstance(levels, (list, tuple)):
        return []
    pairs = []
    for pair in levels:
        if isinstance(pair, (list, tuple)) and len(pair) == 2 and isinstance(pair[0], (int, float)) and isinstance(pair[1], (int, float)) and pair[0] > 0:
            pairs.append([int(pair[0]), clamp(pair[1])])
    return pairs


def order_ladders(skip=()):
    """{item_id: ladder} (lib/priority.py) over every requester's order
    except `skip`: units of one item at one prio are summed across
    requesters, then accumulated down the prios (a floor at a higher prio
    is also wanted at every lower one)."""
    per_prio = {}
    for items in get_orders(skip).values():
        for item_id, pairs in items.items():
            bucket = per_prio.setdefault(item_id, {})
            for units, prio in pairs:
                bucket[prio] = bucket.get(prio, 0) + units
    ladders = {}
    for item_id, bucket in per_prio.items():
        levels = []
        cum = 0
        for prio in sorted(bucket, reverse=True):
            cum += bucket[prio]
            levels.append([prio, cum])
        ladders[item_id] = levels
    return ladders


def order_items(skip=()):
    """{item_id: units} summed over every level of every requester's order except `skip` (the flat floor)."""
    return {item_id: ladder_total(levels) for item_id, levels in order_ladders(skip).items()}


def set_order(requester, items):
    """Replaces requester's order with `items` ({item_id: [units, prio]} or
    {item_id: [[units, prio], ...]}, order_levels()); empty or None clears
    it. Plain read first, so an unchanged order costs no archive write."""
    wanted = {}
    for item_id, levels in (items or {}).items():
        pairs = _order_pairs(levels)
        if pairs:
            wanted[item_id] = pairs
    stored = archive.get(ORDERS_KEY, {})
    current = stored.get(requester) if isinstance(stored, dict) else None
    current = current if isinstance(current, dict) else {}
    if current == wanted:
        return

    def updater(orders):
        if not isinstance(orders, dict):
            orders = {}
        if wanted:
            orders[requester] = wanted
        else:
            orders.pop(requester, None)
        return orders

    archive.transaction(ORDERS_KEY, {}, updater)
    before = {i: sum(p[0] for p in _order_pairs(l)) for i, l in current.items()}
    after = {i: sum(p[0] for p in pairs) for i, pairs in wanted.items()}
    wake_on_rise(("fabricator",), before, after, f"{ORDERS_KEY} from {requester}:")


def clear_order(requester):
    """set_order(requester, None)."""
    set_order(requester, None)
