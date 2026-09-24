# Generic "pull" logistics: an outpost announces items it wants stocked
# locally (a request), and a reverse hauler (lib/vehicle_cargo.py
# run_pull_loop()) parked there fetches them from wherever they sit on the
# network. Nothing on the source side has to advertise stock -- the hauler
# reads remote Warehouses live. Sources only need to hold requested items
# back from local consumers (retain_amount(), used by lib/drone_depot.py and
# the Essence Liquifier), and miner drones use network_deficits() to prefer
# biosites holding requested forms.
#
# First consumer: the Seed Maker (lib/seed_maker.py). Anything else that
# needs material pulled to a specific outpost (e.g. ore from remote mining
# drills) can register requests the same way.
#
# Archive shape (one shared dict per concern, CLAUDE.md rule 7):
#   logistics.requests = {outpost_id: {item_id: {"target": t, "have": h,
#                                                "by": requester, "tick": n}}}
#   logistics.pickups  = {pickup_key: {"vehicle", "dest", "source",
#                                      "item_id", "units", "tick"}}
# "have" is the requester's own last-published local stock -- a cheap,
# slightly lagging number for readers that can't afford a live stock walk
# (miner drones). The hauler recomputes local stock live (outpost_stock())
# before planning, since it's physically at the requesting outpost anyway.
# "source" (outpost or drill id, None for legacy entries) lets a planner
# debit stock another hauler has already promised itself (reserved_from()),
# so two haulers never plan the same units at the same source.

from archive import archive
from storage import warehouse_stock
from tree_console import TreeConsole

log = TreeConsole(module="logistics_requests")

REQUESTS_KEY = "logistics.requests"
PICKUPS_KEY = "logistics.pickups"

# A requester republishes at least this often while alive; older entries are
# ignored and pruned so a stopped/removed requester can't pin stock forever
# (10 ticks/s -> 5 minutes).
REQUEST_STALE_TICKS = 3000

# Same window as mining_reservations.RESERVATION_STALE_TICKS.
PICKUP_STALE_TICKS = 36000

# Minimum a SOURCE outpost keeps back from its own local consumers
# (Liquifier) for a remote requester -- roughly one extractor load. The
# requester's own target raises it (retain_amount()).
LIFEFORM_STASH_CAP_T = 25

# typeIds, not the "Drone Depot" display name; one per Depot size -- see lib/drone_energy.py
DRONE_DEPOT_TYPE_IDS = ("drone_station", "drone_station_medium", "drone_station_large")

# Accepted DESTINATION_OUTPOST_ID values that mean "pick up anywhere, bring to
# my HOME_BASE" (lib/pioneer.py run()).
PULL_DESTINATION_WILDCARDS = ("*", "any", "%")


def _now_tick():
    try:
        clock = get_component("clock")
        return clock.tick() if clock else 0
    except Exception:
        return 0


def _is_fresh(entry, curr_tick, stale_ticks):
    return isinstance(entry, dict) and curr_tick - entry.get("tick", 0) < stale_ticks


# ------------------------------------------------------------------ requests

def set_requests(outpost_id, requester, wants, curr_tick=None):
    """
    Replaces every request `requester` holds at `outpost_id` with `wants`
    ({item_id: (target, have)}), in one transaction. An empty `wants` just
    withdraws the requester's entries there. Stale entries of any requester
    are pruned on the way.
    """
    tick = curr_tick if curr_tick is not None else _now_tick()

    def updater(requests):
        if not isinstance(requests, dict):
            requests = {}
        for o_id, items in list(requests.items()):
            if not isinstance(items, dict):
                del requests[o_id]
                continue
            for item_id, entry in list(items.items()):
                mine = o_id == outpost_id and isinstance(entry, dict) and entry.get("by") == requester
                if mine or not _is_fresh(entry, tick, REQUEST_STALE_TICKS):
                    del items[item_id]
            if not items:
                del requests[o_id]
        if wants:
            bucket = requests.get(outpost_id, {})
            for item_id, pair in wants.items():
                target, have = pair
                bucket[item_id] = {"target": target, "have": have, "by": requester, "tick": tick}
            requests[outpost_id] = bucket
        return requests

    archive.transaction(REQUESTS_KEY, {}, updater)
    log.debug(f"set_requests({outpost_id!r}, {requester!r}): {len(wants)} item(s) at tick {tick}.")


def clear_requests(requester, outpost_id=None):
    """Withdraws every request by `requester` (at `outpost_id`, or everywhere)."""
    def updater(requests):
        if not isinstance(requests, dict):
            return {}
        for o_id in list(requests.keys()):
            if outpost_id is not None and o_id != outpost_id:
                continue
            items = requests.get(o_id)
            if not isinstance(items, dict):
                del requests[o_id]
                continue
            for item_id in list(items.keys()):
                entry = items[item_id]
                if isinstance(entry, dict) and entry.get("by") == requester:
                    del items[item_id]
            if not items:
                del requests[o_id]
        return requests

    archive.transaction(REQUESTS_KEY, {}, updater)
    log.debug(f"clear_requests({requester!r}, outpost_id={outpost_id!r}).")


def active_requests(curr_tick=None):
    """{outpost_id: {item_id: entry}} of every non-stale request (read-only)."""
    tick = curr_tick if curr_tick is not None else _now_tick()
    raw = archive.get(REQUESTS_KEY, {})
    result = {}
    if not isinstance(raw, dict):
        return result
    for o_id, items in raw.items():
        if not isinstance(items, dict):
            continue
        fresh = {i: e for i, e in items.items() if _is_fresh(e, tick, REQUEST_STALE_TICKS)}
        if fresh:
            result[o_id] = fresh
    return result


# ------------------------------------------------------------------- pickups

def pickup_key(vehicle_name, dest_outpost_id, item_id, source_id=None):
    base = f"pull:{vehicle_name}:{dest_outpost_id}:{item_id}"
    return f"{base}:{source_id}" if source_id else base


def reserve_pickup(vehicle_name, dest_outpost_id, item_id, units, curr_tick=None, source_id=None):
    """
    Debits `units` of item_id headed for dest_outpost_id (and, with
    source_id, taken from that outpost/drill) until released (or stale).
    Re-reserving the same (vehicle, dest, item, source) overwrites, so the
    planned amount can be corrected to what actually got loaded.
    """
    tick = curr_tick if curr_tick is not None else _now_tick()
    key = pickup_key(vehicle_name, dest_outpost_id, item_id, source_id)

    def updater(pickups):
        if not isinstance(pickups, dict):
            pickups = {}
        if units > 0:
            pickups[key] = {"vehicle": vehicle_name, "dest": dest_outpost_id, "source": source_id, "item_id": item_id, "units": units, "tick": tick}
        else:
            pickups.pop(key, None)
        return pickups

    archive.transaction(PICKUPS_KEY, {}, updater)
    log.debug(f"reserve_pickup({key!r}): {units}x {item_id}.")


def release_pickups(vehicle_name):
    """Drops every pickup reservation owned by vehicle_name (after delivery), plus any stale entries."""
    tick = _now_tick()

    def updater(pickups):
        if not isinstance(pickups, dict):
            return {}
        for key in list(pickups.keys()):
            entry = pickups[key]
            if not isinstance(entry, dict) or entry.get("vehicle") == vehicle_name or not _is_fresh(entry, tick, PICKUP_STALE_TICKS):
                del pickups[key]
        return pickups

    archive.transaction(PICKUPS_KEY, {}, updater)
    log.debug(f"release_pickups({vehicle_name!r}).")


def in_flight(dest_outpost_id, curr_tick=None):
    """{item_id: units} currently being hauled towards dest_outpost_id."""
    tick = curr_tick if curr_tick is not None else _now_tick()
    raw = archive.get(PICKUPS_KEY, {})
    totals = {}
    if not isinstance(raw, dict):
        return totals
    for entry in raw.values():
        if not _is_fresh(entry, tick, PICKUP_STALE_TICKS) or entry.get("dest") != dest_outpost_id:
            continue
        item_id = entry.get("item_id")
        if item_id:
            totals[item_id] = totals.get(item_id, 0) + (entry.get("units", 0) or 0)
    return totals


def reserved_from(source_id, curr_tick=None, exclude_vehicle=None):
    """
    {item_id: units} other haulers have planned to take from source_id (an
    outpost or drill id) and not delivered yet. The planning vehicle passes
    its own name as exclude_vehicle so its previous trip's leftovers don't
    count against it.
    """
    tick = curr_tick if curr_tick is not None else _now_tick()
    raw = archive.get(PICKUPS_KEY, {})
    totals = {}
    if not isinstance(raw, dict):
        return totals
    for entry in raw.values():
        if not _is_fresh(entry, tick, PICKUP_STALE_TICKS) or entry.get("source") != source_id:
            continue
        if exclude_vehicle is not None and entry.get("vehicle") == exclude_vehicle:
            continue
        item_id = entry.get("item_id")
        if item_id:
            totals[item_id] = totals.get(item_id, 0) + (entry.get("units", 0) or 0)
    return totals


# --------------------------------------------------------------------- stock

def local_depots(outpost):
    """Resolved Drone Depots at `outpost` (an OutpostRef)."""
    if not outpost or not hasattr(outpost, "buildings"):
        return []
    refs = []
    for type_id in DRONE_DEPOT_TYPE_IDS:
        try:
            refs.extend(outpost.buildings(type_id))
        except Exception:
            continue
    depots = []
    for ref in refs:
        try:
            depot = get_component(ref.id)
        except Exception:
            depot = None
        if depot:
            depots.append(depot)
    return depots


def depot_stock(depot):
    """{item_id: units} in one Drone Depot's shared stockpile."""
    stock = {}
    port = getattr(depot, "output", None)
    if not port or not hasattr(port, "stacks"):
        return stock
    try:
        for stack in port.stacks():
            stock[stack.id] = stock.get(stack.id, 0) + stack.count
    except Exception:
        return {}
    return stock


def outpost_stock(item_ids, outpost):
    """
    {item_id: units} held at `outpost`: its Warehouses + Drone Depots, plus
    home Inventory when `outpost` is the home outpost -- everything a local
    machine's InputSlot can take() from.
    """
    totals = {item_id: 0 for item_id in item_ids}
    if not item_ids or outpost is None:
        return totals
    for item_id in item_ids:
        totals[item_id] += warehouse_stock(item_id, outpost)
    for depot in local_depots(outpost):
        stock = depot_stock(depot)
        for item_id in item_ids:
            totals[item_id] += stock.get(item_id, 0)
    if getattr(outpost, "is_home", False):
        try:
            inventory = get_component("inventory")
            if inventory:
                for item_id in item_ids:
                    totals[item_id] += inventory.count(item_id)
        except Exception:
            pass
    return totals


def outpost_deficits(outpost, curr_tick=None, live=True):
    """
    {item_id: units still missing} for requests at `outpost` (OutpostRef):
    target - local stock - in-flight pickups, positive entries only. live=True
    counts local stock now (hauler at the requesting outpost); live=False
    trusts the requester's last published "have".
    """
    tick = curr_tick if curr_tick is not None else _now_tick()
    outpost_id = getattr(outpost, "id", None)
    requests = active_requests(tick).get(outpost_id, {})
    if not requests:
        return {}
    have = outpost_stock(list(requests.keys()), outpost) if live else {i: e.get("have", 0) for i, e in requests.items()}
    flying = in_flight(outpost_id, tick)
    deficits = {}
    for item_id, entry in requests.items():
        missing = entry.get("target", 0) - have.get(item_id, 0) - flying.get(item_id, 0)
        if missing > 0:
            deficits[item_id] = missing
    return deficits


def network_deficits(curr_tick=None):
    """
    {item_id: units still missing} summed over every requesting outpost,
    from published "have" values (cheap -- no stock walk). For miner drones
    deciding which biosite is worth visiting first.
    """
    tick = curr_tick if curr_tick is not None else _now_tick()
    totals = {}
    for o_id, items in active_requests(tick).items():
        flying = in_flight(o_id, tick)
        for item_id, entry in items.items():
            missing = entry.get("target", 0) - entry.get("have", 0) - flying.get(item_id, 0)
            if missing > 0:
                totals[item_id] = totals.get(item_id, 0) + missing
    return totals


def outpost_free_stock(outpost, item_ids, requests=None, curr_tick=None, exclude_vehicle=None):
    """
    {item_id: units} an outpost can give away to a pull hauler -- its
    advertised "free stock", computed live (no per-outpost script needed):
    Warehouse stock (+ Inventory when it's home) minus the outpost's own
    request target for that item, minus what other haulers already reserved
    from it. Drone Depot stock is left out on purpose -- lib/drone_depot.py
    stages requested items into a Warehouse, which vehicles can take() from.
    """
    requests = requests if requests is not None else active_requests(curr_tick)
    outpost_id = getattr(outpost, "id", None)
    own = requests.get(outpost_id, {})
    taken = reserved_from(outpost_id, curr_tick, exclude_vehicle)
    inventory = None
    if getattr(outpost, "is_home", False):
        try:
            inventory = get_component("inventory")
        except Exception:
            inventory = None
    free = {}
    for item_id in item_ids:
        units = warehouse_stock(item_id, outpost)
        if inventory is not None:
            try:
                units += inventory.count(item_id)
            except Exception:
                pass
        units -= own.get(item_id, {}).get("target", 0) + taken.get(item_id, 0)
        if units > 0:
            free[item_id] = units
    return free


def retain_amount(item_id, outpost_id, requests=None):
    """
    Units of item_id that local consumers (Liquifier) at outpost_id must leave
    alone: the full target when outpost_id itself requests it, else -- while
    any other outpost requests it at all -- the largest such remote target,
    at least LIFEFORM_STASH_CAP_T, else 0. Held regardless of whether the
    requester is currently topped up: a continuous consumer (Seed Maker)
    drains its stash again soon, and the hauler should find a batch waiting
    instead of stock the Liquifier burnt in between.
    """
    requests = requests if requests is not None else active_requests()
    own = requests.get(outpost_id, {}).get(item_id)
    if own:
        return own.get("target", 0)
    retain = 0
    for o_id, items in requests.items():
        if o_id == outpost_id:
            continue
        entry = items.get(item_id)
        if entry:
            retain = max(retain, LIFEFORM_STASH_CAP_T, entry.get("target", 0))
    return retain
