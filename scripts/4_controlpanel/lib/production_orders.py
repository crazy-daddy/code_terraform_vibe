# Archive-backed Fabricator order books: manual orders (and their units in
# transit home), fleet upgrade and backlog orders.
from archive import archive
from storage import outpost_is_home
from swallow import swallowed
from production_core import log
from production_source import SourceCache
from script_parking import wake_on_rise


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
        base = SourceCache().stock(item_id)
    except Exception as error:
        swallowed("production_orders._record_manual_transit: SourceCache.stock", error)
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
        home = cache.stock(item_id)
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


# Fleet hardware upgrade orders (lib/fleet_upgrade.py, lib/drone_upgrade.py):
# ONE shared dict {requester_id: {item_id: quantity}} (CODE_GUIDES.md#archive), so
# each requester -- the coordinator, or a drone wanting a bigger Cargo Pod --
# owns and clears only its own entry. Quantities are "keep at least this many
# in stock" floors, summed across requesters. Ranked below manual orders AND
# blueprint demand in lib/fabricator.py's choose_recipe() (building new
# things beats upgrading working old ones), above everything else.
UPGRADE_ORDERS_KEY = "fabricator.upgrade_orders"
# Requesters in UPGRADE_ORDERS_KEY that aren't drones. fleet_upgrade._prune()
# drops every other entry whose drone no longer exists, so a standing order
# from another script must be listed here. "field_keeper" = the Harvester's
# field-machine kits (lib/harvester_machines.py). "bio_caster" = the
# Bio Caster's forge materials for all open Volcanic bio orders (lib/bio_volcanic.py).
# "fleet_commission" = a drone kit the FLEET card's Commission tab queued (lib/drone_commission.py).
# "plant_terraformer" = the Plant Terraformers' next NEED_BATCHES batches of Fertilizer /
# Growth Accelerant (lib/plant_terraformer_demand.py). "fuel_assembler" = the
# Fuel Assemblers' Lead Plates for their next crafts (lib/fuel_assembler.py).
# "field_amplifier" = the Harvester's Yield Amplifier doses (lib/harvester_amplify.py).
# "site_stock_need" = the need tier of the crafted site stockpiles (lib/site_supply.py).
# "construction_stock_need" = the need tier of the construction stock (lib/site_supply.py).
STANDING_ORDER_REQUESTERS = ("field_keeper", "bio_caster", "fleet_commission", "plant_terraformer", "fuel_assembler", "field_amplifier", "site_stock_need", "construction_stock_need")
# Standing requesters whose order is a recurring consumable buffer, not a
# one-off part a job waits on: their items are never hauled urgently
# (lib/site_supply.py settled_items()), so a hauler waits for a full load.
# The Fuel Assemblers' Lead Plates stay urgent (reactor fuel); their outposts
# keep a stockpile instead (site_supply.SITE_STOCK_TARGETS).
RECURRING_ORDER_REQUESTERS = ("plant_terraformer", "field_amplifier", "site_stock_need", "construction_stock_need")
# Upgrade/backlog requesters whose items are consumed at the outposts that
# request them through site supply (lib/site_supply.py SITE_STOCK_TARGETS and
# the construction stock), not at home: they raise the Fabricator targets but
# make home no consumer (lib/production_cascade.py fabricator_root_targets()),
# so home doesn't pull the stockpiles back.
SITE_ORDER_REQUESTERS = ("site_stock", "site_stock_need", "construction_stock", "construction_stock_need")

# Backlog orders: same {requester_id: {item_id: quantity}} shape as
# UPGRADE_ORDERS_KEY, but filler work. The quantity is folded into the
# Fabricator targets like any floor, and choose_recipe() ranks a backlog
# item below every other demand (tier 5) once its non-backlog floors are
# met, so it only uses otherwise idle Fabricator time. A requester owns and
# clears its own entry.
BACKLOG_ORDERS_KEY = "fabricator.backlog_orders"


def get_upgrade_orders(skip=()):
    """{item_id: quantity} summed across every requester's entry in UPGRADE_ORDERS_KEY, except the requesters in `skip`."""
    return _summed_orders(UPGRADE_ORDERS_KEY, skip)


def get_backlog_orders(skip=()):
    """{item_id: quantity} summed across every requester's entry in BACKLOG_ORDERS_KEY, except the requesters in `skip`."""
    return _summed_orders(BACKLOG_ORDERS_KEY, skip)


def _summed_orders(key, skip=()):
    stored = archive.get(key, {})
    if not isinstance(stored, dict):
        return {}
    totals = {}
    for requester, items in stored.items():
        if requester in skip or not isinstance(items, dict):
            continue
        for item_id, qty in items.items():
            if isinstance(qty, (int, float)) and qty > 0:
                totals[item_id] = totals.get(item_id, 0) + int(qty)
    return totals


def set_upgrade_order(requester, items):
    """Replaces requester's upgrade order with items ({item_id: qty}); empty or None
    clears it. Plain read first, so an unchanged order costs no archive write."""
    _set_requester_order(UPGRADE_ORDERS_KEY, requester, items)


def set_backlog_order(requester, items):
    """set_upgrade_order() for BACKLOG_ORDERS_KEY."""
    _set_requester_order(BACKLOG_ORDERS_KEY, requester, items)


def _set_requester_order(key, requester, items):
    wanted = {i: int(q) for i, q in (items or {}).items() if q and q > 0}
    stored = archive.get(key, {})
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

    archive.transaction(key, {}, updater)
    wake_on_rise(("fabricator",), current, wanted, f"{key} from {requester}:")
