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
# Archive shape (one shared dict per concern, CODE_GUIDES.md#archive):
#   logistics.requests = {outpost_id: {item_id: {"target": t, "have": h,
#                                                "min": m, "by": requester,
#                                                "buy": bool, "urgent": bool,
#                                                "tick": n}}}
#   logistics.pickups  = {pickup_key: {"vehicle", "dest", "source",
#                                      "item_id", "units", "tick",
#                                      "aboard"}}
# Two demand tiers per request: "min" is what the requester needs to keep
# working (the need tier), "target" the stock it would like on hand (the
# buffer tier above min). "min" missing or >= target means all need. Need
# deficits are served first everywhere; what supply is left is split between
# buffer deficits in proportion to their size (fair_buffer_caps()). A source
# outpost keeps its own min back from another outpost's need, and its full
# target back from another outpost's buffer (outpost_free_tiers()).
# "have" is the requester's own last-published local stock -- a cheap,
# slightly lagging number for readers that can't afford a live stock walk
# (miner drones). The hauler recomputes local stock live (outpost_stock())
# before planning, since it's physically at the requesting outpost anyway.
# "buy": True (set_requests(buyable=True)) lets a Pioneer pull hauler buy the
# item at the Shop on a home pickup (SHOP_SOURCE_ID) when no free stock covers
# it; unflagged requests are never bought.
# "urgent": True marks a blocker nothing more will arrive for by waiting
# (lib/site_supply.py: a blueprint material no Fabricator is still building).
# A route carrying an urgent item skips the hauler's minimum load and ranks
# first (haul_rank(), urgent_items()).
# "source" (outpost or drill id, None for legacy entries) lets a planner
# debit stock another hauler has already promised itself (reserved_from()),
# so two haulers never plan the same units at the same source.
# "aboard": True once the hauler has loaded the units (reserve_pickup(...,
# aboard=True) after each take); a planned-only entry still has them at the
# source. aboard_units() sums the loaded ones, so stock counts can include
# cargo on the move without counting a planned pickup twice.

from archive import archive
from components import drone_station
from storage import warehouse_stocks, stacks_stock, crop_automator_forage_total, CROP_AUTOMATOR_ITEM_ID
from fleet_status import FLEET_STATUS_KEY
from tree_console import TreeConsole
from swallow import swallowed
from game_clock import now_tick

log = TreeConsole(module="logistics_requests")

REQUESTS_KEY = "logistics.requests"
PICKUPS_KEY = "logistics.pickups"
# Operator switch (vehicles_panel.py FLEET card): when True, ground pull haulers
# leave drone-servable pickups to floating drone haulers (drone_served_source()).
DRONE_YIELD_KEY = "logistics.drone_yield"

# A requester republishes at least this often while alive; older entries are
# ignored and pruned so a stopped/removed requester can't pin stock forever
# (10 ticks/s -> 10 minutes). Longer than the slowest requester's publish
# gap (the field Harvester republishes between care tours, ~5 minutes).
REQUEST_STALE_TICKS = 6000
# publish_requests() rewrites entries that still match the wants once they are
# this old, so they stay fresh and their "have" doesn't lag much further.
REPUBLISH_TICKS = REQUEST_STALE_TICKS // 2

def haul_rank(units, need_units, meters, overhead_m, urgent_units=0.0):
    """
    Planner ranking of one haul/pull candidate: (urgent units, need-tier
    units, all units) per (route m + overhead_m). Compared with
    rank_beats(): urgent throughput decides, then need throughput, all
    units only break a tie, so a trip serving a requester that is about to
    stall always beats filling a buffer however big the buffer load is.
    """
    per = meters + overhead_m
    if per <= 0:
        per = 1.0
    return (urgent_units / per, need_units / per, units / per)


def rank_beats(rank, best):
    """True when haul_rank() `rank` beats `best` (None = no candidate yet)."""
    if best is None:
        return True
    for mine, theirs in zip(rank, best):
        if mine != theirs:
            return mine > theirs
    return False


def urgent_items(outpost_id, curr_tick=None):
    """Item ids whose request at `outpost_id` is flagged urgent."""
    requests = active_requests(curr_tick).get(outpost_id, {})
    return {item_id for item_id, entry in requests.items() if entry.get("urgent")}


def urgent_units(route, urgent):
    """Units of `urgent` items a route [(source, [(item_id, units), ...]), ...] carries."""
    return sum(n for _src, loads in route for i, n in loads if i in urgent)

# A drone hauler counts as present (drone_served_source()) while its
# fleet.status heartbeat is younger than this (10 minutes).
HAULER_FRESH_TICKS = 6000

# Same window as mining_reservations.RESERVATION_STALE_TICKS.
PICKUP_STALE_TICKS = 36000

# Minimum a SOURCE outpost keeps back from its own local consumers
# (Liquifier) for a remote requester -- roughly one extractor load. The
# requester's own target raises it (retain_amount()).
LIFEFORM_STASH_CAP_T = 25

# typeIds, not the "Drone Depot" display name; one per Depot size -- see lib/drone_energy.py
DRONE_DEPOT_TYPE_IDS = ("drone_station", "drone_station_medium", "drone_station_large")

# Pull-source id of the Shop (lib/vehicle_cargo.py _pull_sources()): a
# virtual source at the home outpost, used only for buyable requests.
SHOP_SOURCE_ID = "shop"


def _is_fresh(entry, curr_tick, stale_ticks):
    return isinstance(entry, dict) and curr_tick - entry.get("tick", 0) < stale_ticks


# ------------------------------------------------------------------ requests

def set_requests(outpost_id, requester, wants, curr_tick=None, buyable=False):
    """
    Replaces every request `requester` holds at `outpost_id` with `wants`
    ({item_id: (target, have)}, (target, have, min) or (target, have, min,
    urgent)), in one transaction. Without min the whole target is need
    tier; urgent=True flags the entry "urgent". buyable=True
    marks the entries as Shop-buyable (buyable_deficits()): a Pioneer pull
    hauler may buy them at home instead of finding free stock. An empty
    `wants` just withdraws the requester's entries there. Stale entries of
    any requester are pruned on the way.
    """
    tick = curr_tick if curr_tick is not None else now_tick()

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
            for item_id, values in wants.items():
                target, have = values[0], values[1]
                entry = {"target": target, "have": have, "by": requester, "tick": tick}
                if len(values) > 2 and values[2] is not None and values[2] < target:
                    entry["min"] = max(0, values[2])
                if buyable:
                    entry["buy"] = True
                if len(values) > 3 and values[3]:
                    entry["urgent"] = True
                bucket[item_id] = entry
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


# Foreign owners publish_requests() last logged, {(outpost_id, requester): {item_id: owner}}.
_foreign_logged = {}


def _want_min(values):
    """Need-tier level set_requests() stores for one wants tuple, as request_min() reads it back."""
    target = values[0]
    floor = values[2] if len(values) > 2 else None
    return target if floor is None or floor >= target else max(0, floor)


def _unchanged(existing, wants, tick, buyable):
    """True when the published entries match wants and are young enough to skip a republish."""
    if set(existing) != set(wants):
        return False
    for item_id, values in wants.items():
        entry = existing[item_id]
        if entry.get("target") != values[0] or request_min(entry) != _want_min(values):
            return False
        if bool(entry.get("urgent")) != (len(values) > 3 and bool(values[3])):
            return False
        if bool(entry.get("buy")) != buyable:
            return False
        if not 0 <= tick - entry.get("tick", 0) < REPUBLISH_TICKS:
            return False
    return True


def publish_requests(outpost_id, requester, wants, curr_tick=None, requests=None, buyable=False, skip_foreign=True, have_of=None):
    """
    set_requests() unless the entries `requester` already published at
    `outpost_id` match `wants` (target, min, urgent, buy; "have" is not
    compared) and are younger than REPUBLISH_TICKS. Empty wants withdraws
    them. `requests` is an active_requests() snapshot (read when None).
    skip_foreign drops items another requester owns there, so two
    requesters never take one item from each other. have_of(item_id), when
    given, replaces each "have" on a write only, for a requester whose
    stock read is a live walk. True when written.
    """
    tick = curr_tick if curr_tick is not None else now_tick()
    if requests is None:
        requests = active_requests(tick)
    here = requests.get(outpost_id) or {}
    if skip_foreign:
        foreign = {}
        for item_id in wants:
            entry = here.get(item_id)
            owner = entry.get("by") if isinstance(entry, dict) else None
            if owner not in (None, requester):
                foreign[item_id] = owner
        if foreign != _foreign_logged.get((outpost_id, requester), {}):
            _foreign_logged[(outpost_id, requester)] = foreign
            if foreign:
                log.debug(f"publish_requests({outpost_id!r}, {requester!r}): left to their owners {foreign}.")
        if foreign:
            wants = {i: v for i, v in wants.items() if i not in foreign}
    existing = {i: e for i, e in here.items() if isinstance(e, dict) and e.get("by") == requester}
    if (not wants and not existing) or _unchanged(existing, wants, tick, buyable):
        log.trace(f"publish_requests({outpost_id!r}, {requester!r}): unchanged, {len(wants)} item(s)")
        return False
    if have_of is not None:
        wants = {i: (v[0], have_of(i)) + tuple(v[2:]) for i, v in wants.items()}
    set_requests(outpost_id, requester, wants, tick, buyable)
    return True


def active_requests(curr_tick=None):
    """{outpost_id: {item_id: entry}} of every non-stale request (read-only)."""
    tick = curr_tick if curr_tick is not None else now_tick()
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


def reserve_pickup(vehicle_name, dest_outpost_id, item_id, units, curr_tick=None, source_id=None, aboard=False):
    """
    Debits `units` of item_id headed for dest_outpost_id (and, with
    source_id, taken from that outpost/drill) until released (or stale).
    Re-reserving the same (vehicle, dest, item, source) overwrites, so the
    planned amount can be corrected to what actually got loaded; pass
    aboard=True then, so aboard_units() counts them.
    """
    tick = curr_tick if curr_tick is not None else now_tick()
    key = pickup_key(vehicle_name, dest_outpost_id, item_id, source_id)

    def updater(pickups):
        if not isinstance(pickups, dict):
            pickups = {}
        if units > 0:
            pickups[key] = {"vehicle": vehicle_name, "dest": dest_outpost_id, "source": source_id, "item_id": item_id, "units": units, "tick": tick}
            if aboard:
                pickups[key]["aboard"] = True
        else:
            pickups.pop(key, None)
        return pickups

    archive.transaction(PICKUPS_KEY, {}, updater)
    log.debug(f"reserve_pickup({key!r}): {units}x {item_id}.")


def pickups_snapshot():
    """
    Current logistics.pickups. Take one BEFORE planning a trip and pass it to
    claim_pickups(), which then only has to account for what other haulers
    reserved after this point.
    """
    raw = archive.get(PICKUPS_KEY, {})
    return dict(raw) if isinstance(raw, dict) else {}


def _other_units(pickups, vehicle_name, tick, match):
    """{(field value, item_id): units} over fresh entries of OTHER vehicles, grouped by match ("source" or "dest")."""
    totals = {}
    for entry in pickups.values():
        if not _is_fresh(entry, tick, PICKUP_STALE_TICKS) or entry.get("vehicle") == vehicle_name:
            continue
        group = (entry.get(match), entry.get("item_id"))
        totals[group] = totals.get(group, 0) + (entry.get("units", 0) or 0)
    return totals


def claim_pickups(vehicle_name, dest_outpost_id, legs, seen, curr_tick=None):
    """
    Atomically reserves a planned trip. `legs` is [(source_id, item_id, units)],
    planned against `seen` (pickups_snapshot() taken before planning). Inside
    one transaction, every leg is trimmed by what other haulers reserved
    since `seen`, both from the same source and towards the same destination.
    Without this, two haulers that plan on the same tick (e.g. all scripts
    restarting together on save load) both see the same free stock and demand,
    and both take all of it.

    Returns [(source_id, item_id, granted_units)] in leg order; a leg granted
    0 is not reserved.
    """
    log.start(f"claim_pickups({vehicle_name!r} -> {dest_outpost_id!r})", level="debug")
    tick = curr_tick if curr_tick is not None else now_tick()
    granted = []

    def updater(pickups):
        if not isinstance(pickups, dict):
            pickups = {}
        del granted[:]
        src_before = _other_units(seen, vehicle_name, tick, "source")
        src_now = _other_units(pickups, vehicle_name, tick, "source")
        dest_before = _other_units(seen, vehicle_name, tick, "dest")
        dest_now = _other_units(pickups, vehicle_name, tick, "dest")
        dest_cut = {}
        for (dest, item_id), units in dest_now.items():
            if dest == dest_outpost_id:
                dest_cut[item_id] = max(0, units - dest_before.get((dest, item_id), 0))
        src_cut = {g: max(0, units - src_before.get(g, 0)) for g, units in src_now.items()}
        for source_id, item_id, units in legs:
            cut_src = src_cut.get((source_id, item_id), 0)
            cut_dest = dest_cut.get(item_id, 0)
            grant = max(0, int(units) - max(cut_src, cut_dest))
            # What this leg gave up counts against both cuts, so later legs
            # aren't trimmed twice for the same competing reservation.
            given_up = int(units) - grant
            src_cut[(source_id, item_id)] = max(0, cut_src - given_up)
            dest_cut[item_id] = max(0, cut_dest - given_up)
            key = pickup_key(vehicle_name, dest_outpost_id, item_id, source_id)
            if grant > 0:
                pickups[key] = {"vehicle": vehicle_name, "dest": dest_outpost_id, "source": source_id, "item_id": item_id, "units": grant, "tick": tick}
            else:
                pickups.pop(key, None)
            granted.append((source_id, item_id, grant))
        return pickups

    if not archive.transaction(PICKUPS_KEY, {}, updater):
        log.debug(f"{PICKUPS_KEY} write rejected; nothing reserved.")
        log.end()
        return [(source_id, item_id, 0) for source_id, item_id, _u in legs]
    trimmed = [(s, i, u, g) for (s, i, u), (_s, _i, g) in zip(legs, granted) if g < u]
    if trimmed:
        log.debug(f"claim_pickups({vehicle_name!r} -> {dest_outpost_id!r}): trimmed by newer reservations: " + ", ".join(f"{s}:{i} {u}->{g}" for s, i, u, g in trimmed))
    _ret = list(granted)
    log.end()
    return _ret


def release_pickups(vehicle_name):
    """Drops every pickup reservation owned by vehicle_name (after delivery), plus any stale entries."""
    tick = now_tick()

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
    tick = curr_tick if curr_tick is not None else now_tick()
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


def aboard_units(curr_tick=None):
    """{item_id: units} loaded aboard a hauler and not delivered yet, any destination."""
    tick = curr_tick if curr_tick is not None else now_tick()
    raw = archive.get(PICKUPS_KEY, {})
    totals = {}
    if not isinstance(raw, dict):
        return totals
    for entry in raw.values():
        if not entry.get("aboard") or not _is_fresh(entry, tick, PICKUP_STALE_TICKS):
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
    tick = curr_tick if curr_tick is not None else now_tick()
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


def _group_units(pickups, tick, field, exclude_vehicle=None):
    """{field value: {item_id: units}} over fresh `pickups` entries (except exclude_vehicle's), grouped by field ("dest" or "source"); in_flight() and reserved_from() for every id in one pass."""
    groups = {}
    if not isinstance(pickups, dict):
        return groups
    for entry in pickups.values():
        if not _is_fresh(entry, tick, PICKUP_STALE_TICKS):
            continue
        if exclude_vehicle is not None and entry.get("vehicle") == exclude_vehicle:
            continue
        item_id = entry.get("item_id")
        if item_id:
            totals = groups.setdefault(entry.get(field), {})
            totals[item_id] = totals.get(item_id, 0) + (entry.get("units", 0) or 0)
    return groups


class PlanReads:
    """
    One planning pass's shared reads, so a planner that touches many
    outposts reads each thing once: active requests, logistics.pickups
    (`pickups`: the pickups_snapshot() taken before planning, which
    claim_pickups() later trims against), in_flight()/reserved_from() for
    every id from one pass over it, and each outpost's stock including Drone
    Depots (outpost_stock()) over every requested item. Pass it as `reads=`
    to outpost_deficits_tiered(), outpost_free_tiers() and fair_buffer_caps().
    Built per plan and dropped after it: stock is read live once per plan.
    """

    def __init__(self, curr_tick=None, pickups=None):
        self.tick = curr_tick if curr_tick is not None else now_tick()
        self.requests = active_requests(self.tick)
        self.pickups = pickups if pickups is not None else pickups_snapshot()
        items = set()
        for wants in self.requests.values():
            items.update(wants.keys())
        self.items = items
        self._by_dest = None
        self._by_source = {}
        self._stock = {}

    def in_flight(self, dest_outpost_id):
        """in_flight(dest_outpost_id) over self.pickups."""
        if self._by_dest is None:
            self._by_dest = _group_units(self.pickups, self.tick, "dest")
        return self._by_dest.get(dest_outpost_id, {})

    def reserved_from(self, source_id, exclude_vehicle=None):
        """reserved_from(source_id, exclude_vehicle=...) over self.pickups."""
        groups = self._by_source.get(exclude_vehicle)
        if groups is None:
            groups = _group_units(self.pickups, self.tick, "source", exclude_vehicle)
            self._by_source[exclude_vehicle] = groups
        return groups.get(source_id, {})

    def stock(self, outpost: "OutpostRef", item_ids):
        """{item_id: units} at `outpost` per outpost_stock() (Warehouses + Drone Depots, + home Inventory/Forage), read once per outpost over every requested item plus `item_ids`."""
        outpost_id = getattr(outpost, "id", None)
        cached = self._stock.get(outpost_id)
        if cached is None:
            wanted = set(self.items)
            wanted.update(item_ids)
            cached = outpost_stock(list(wanted), outpost)
            self._stock[outpost_id] = cached
        else:
            missing = [i for i in item_ids if i not in cached]
            if missing:
                cached.update(outpost_stock(missing, outpost))
        return cached


# --------------------------------------------------------------------- stock

def local_depots(outpost: "OutpostRef"):
    """Resolved Drone Depots at `outpost` (an OutpostRef)."""
    if not outpost or not hasattr(outpost, "buildings"):
        return []
    refs = []
    for type_id in DRONE_DEPOT_TYPE_IDS:
        try:
            refs.extend(outpost.buildings(type_id))
        except Exception as error:
            swallowed("logistics_requests.local_depots: refs.extend", error)
            continue
    depots = []
    for ref in refs:
        try:
            depot = drone_station(ref.id)
        except Exception as error:
            swallowed("logistics_requests.local_depots: get_component", error)
            depot = None
        if depot:
            depots.append(depot)
    return depots


def drone_yield_enabled():
    """Operator switch: ground pull haulers skip drone-servable sources (default off)."""
    return bool(archive.get(DRONE_YIELD_KEY, False))


def set_drone_yield_enabled(enabled):
    archive.set(DRONE_YIELD_KEY, bool(enabled))


def drone_haulers_present(curr_tick=None):
    """True when fleet.status holds a hauler-role drone heard from within
    HAULER_FRESH_TICKS. Ground vehicles publish a role too; only drone
    entries carry "engine"."""
    tick = curr_tick if curr_tick is not None else now_tick()
    status = archive.get(FLEET_STATUS_KEY, {})
    if not isinstance(status, dict):
        return False
    for entry in status.values():
        if isinstance(entry, dict) and entry.get("role") == "hauler" and entry.get("engine") and tick - (entry.get("tick", 0) or 0) < HAULER_FRESH_TICKS:
            return True
    return False


def drone_served_source(source, dest_outpost):
    """
    Reason string when a pull source (lib/vehicle_cargo.py _pull_sources()
    dict) is left to drone haulers, else None. Only while drone_yield_enabled(),
    dest_outpost has a Drone Depot (drones can't deliver elsewhere) and at
    least one hauler drone is alive (drone_haulers_present()). Then field
    Mining Drills and outposts with their own Drone Depot are skipped; Water
    Pump salt stays (DroneCargo.load() can't take it).
    """
    if not drone_yield_enabled() or not local_depots(dest_outpost):
        return None
    if not drone_haulers_present():
        log.debug("drone_served_source(): drone yield on, but no hauler drone reported in the last "
                  f"{HAULER_FRESH_TICKS} ticks; keeping every source for ground haulers.")
        return None
    kind = source.get("kind")
    if kind == "drill":
        return "drill, drone-servable"
    if kind == "outpost" and local_depots(source.get("outpost")):
        return "outpost has a Drone Depot"
    return None


def depot_stock(depot):
    """{item_id: units} in one Drone Depot's shared stockpile."""
    stock = {}
    port = getattr(depot, "output", None)
    if not port or not hasattr(port, "stacks"):
        return stock
    try:
        for stack in port.stacks():
            stock[stack.id] = stock.get(stack.id, 0) + stack.count
    except Exception as error:
        swallowed("logistics_requests.depot_stock: port.stacks", error)
        return {}
    return stock


def take_from_depots(port: "InputSlot | VehicleInputSlot", item_id, amount, outpost: "OutpostRef"):
    """
    take()s up to `amount` x `item_id` into `port` (an InputSlot) from the
    Drone Depots at `outpost`, depot by depot, asking each only for what its
    stockpile holds. Returns units moved. No retain rules: callers that must
    hold back requested stock (Essence Liquifier) do their own loop.
    """
    moved_total = 0
    for depot in local_depots(outpost):
        if moved_total >= amount:
            break
        want = min(amount - moved_total, depot_stock(depot).get(item_id, 0))
        if want <= 0:
            continue
        try:
            if port.connected_id() != depot.id:
                port.connect(depot.id)
            res = port.take(item_id, want)
        except Exception as error:
            swallowed("logistics_requests.take_from_depots: port.take", error)
            continue
        moved = getattr(res, "moved", 0) or 0
        log.trace(f"take {item_id} x{want} from depot '{depot.id}': {getattr(res, 'status', None)}, moved {moved}.")
        moved_total += moved
    return moved_total


def outpost_stock(item_ids, outpost: "OutpostRef | None"):
    """
    {item_id: units} held at `outpost`: its Warehouses + Drone Depots, plus
    home Inventory and Crop Automator Forage when `outpost` is the home
    outpost -- everything a local machine's InputSlot can take() from.
    """
    totals = {item_id: 0 for item_id in item_ids}
    if not item_ids or outpost is None:
        return totals
    for item_id, units in warehouse_stocks(item_ids, outpost).items():
        totals[item_id] += units
    for depot in local_depots(outpost):
        stock = depot_stock(depot)
        for item_id in item_ids:
            totals[item_id] += stock.get(item_id, 0)
    if getattr(outpost, "is_home", False):
        try:
            for item_id, units in stacks_stock(get_component("inventory"), item_ids).items():
                totals[item_id] += units
        except Exception as error:
            swallowed("logistics_requests.outpost_stock: get_component", error)
        if CROP_AUTOMATOR_ITEM_ID in totals:
            totals[CROP_AUTOMATOR_ITEM_ID] += crop_automator_forage_total(outpost)
    return totals


def request_min(entry):
    """Need-tier level of one request entry: its "min", capped at "target" (whole target when unset)."""
    target = entry.get("target", 0) or 0
    floor = entry.get("min")
    return target if floor is None else min(floor, target)


def _tier_split(entry, have, flying):
    """(need, buffer) units missing for one request entry, given stock and in-flight units."""
    target = entry.get("target", 0) or 0
    arriving = have + flying
    need = max(0, request_min(entry) - arriving)
    buffer = max(0, target - arriving) - need
    return need, max(0, buffer)


def outpost_deficits_tiered(outpost: "OutpostRef | None", curr_tick=None, live=True, reads=None):
    """
    ({item_id: need units}, {item_id: buffer units}) still missing for
    requests at `outpost` (OutpostRef): need = min - local stock - in-flight,
    buffer = the rest up to target. Positive entries only. live=True counts
    local stock now; live=False trusts the requester's last published "have".
    `reads` (PlanReads) supplies requests, stock and in-flight units instead
    of reading them here.
    """
    tick = curr_tick if curr_tick is not None else now_tick()
    outpost_id = getattr(outpost, "id", None)
    requests = (reads.requests if reads is not None else active_requests(tick)).get(outpost_id, {})
    if not requests:
        return {}, {}
    if not live:
        have = {i: e.get("have", 0) for i, e in requests.items()}
    elif reads is not None:
        have = reads.stock(outpost, requests.keys())
    else:
        have = outpost_stock(list(requests.keys()), outpost)
    flying = reads.in_flight(outpost_id) if reads is not None else in_flight(outpost_id, tick)
    need, buffer = {}, {}
    for item_id, entry in requests.items():
        n, b = _tier_split(entry, have.get(item_id, 0), flying.get(item_id, 0))
        if n > 0:
            need[item_id] = n
        if b > 0:
            buffer[item_id] = b
    return need, buffer


def buyable_deficits(outpost: "OutpostRef", need, buffer, curr_tick=None):
    """
    ({item_id: need units}, {item_id: buffer units}): the part of `outpost`'s
    deficits (outpost_deficits_tiered() output) whose request is flagged
    buyable (set_requests(buyable=True)), i.e. what a pull hauler may buy
    at the Shop for it.
    """
    tick = curr_tick if curr_tick is not None else now_tick()
    requests = active_requests(tick).get(getattr(outpost, "id", None), {})
    flagged = {item_id for item_id, entry in requests.items() if entry.get("buy")}
    return ({i: u for i, u in need.items() if i in flagged},
            {i: u for i, u in buffer.items() if i in flagged})


def outpost_deficits(outpost: "OutpostRef | None", curr_tick=None, live=True):
    """
    {item_id: units still missing} for requests at `outpost` (OutpostRef):
    target - local stock - in-flight pickups (need + buffer tier, see
    outpost_deficits_tiered()), positive entries only.
    """
    need, buffer = outpost_deficits_tiered(outpost, curr_tick, live)
    deficits = dict(need)
    for item_id, units in buffer.items():
        deficits[item_id] = deficits.get(item_id, 0) + units
    return deficits


def fair_buffer_caps(dest_outpost_id, buffer, supply, curr_tick=None, reads=None):
    """
    {item_id: units} dest may plan from its buffer-tier deficit `buffer`,
    given `supply` ({item_id: units} the planner can see for the buffer tier,
    after need tiers were served). Split in proportion to every requesting
    outpost's buffer deficit for that item (other outposts read from their
    published "have", minus in-flight). The largest deficit gets the
    rounding remainder, so the supply is never stranded by flooring.
    `reads` (PlanReads) supplies requests and in-flight units.
    """
    tick = curr_tick if curr_tick is not None else now_tick()
    others = {}
    for o_id, items in (reads.requests if reads is not None else active_requests(tick)).items():
        if o_id == dest_outpost_id:
            continue
        if not any(item_id in buffer for item_id in items):
            continue
        flying = reads.in_flight(o_id) if reads is not None else in_flight(o_id, tick)
        for item_id, entry in items.items():
            if item_id not in buffer:
                continue
            _n, b = _tier_split(entry, entry.get("have", 0) or 0, flying.get(item_id, 0))
            if b > 0:
                others.setdefault(item_id, []).append(b)
    caps = {}
    for item_id, mine in buffer.items():
        available = max(0, int(supply.get(item_id, 0)))
        rivals = others.get(item_id, [])
        total = mine + sum(rivals)
        if not rivals or total <= available:
            caps[item_id] = min(mine, available)
            continue
        share = available * mine // total
        if mine >= max(rivals):
            share = available - sum(available * r // total for r in rivals)
        caps[item_id] = max(0, min(mine, share))
        log.debug(f"fair_buffer_caps({dest_outpost_id!r}, {item_id}): supply {available} vs buffer deficits mine={mine}, others={rivals} -> {caps[item_id]}.")
    return caps


def plan_take(source, item_id, need_left, buffer_left, cap):
    """
    (need units, buffer units) to plan from one source for item_id. A source
    dict carries "available" (free for another outpost's need) and optionally
    "available_buffer" (free for a buffer top-up, <= available; defaults to
    "available"). Need is taken first; buffer only from what stays above the
    source's own target after that.
    """
    avail = source["available"].get(item_id, 0)
    avail_buffer = source.get("available_buffer", source["available"]).get(item_id, 0)
    need = max(0, min(need_left.get(item_id, 0), avail, cap))
    buffer = max(0, min(buffer_left.get(item_id, 0), avail_buffer - need, cap - need))
    return need, buffer


def source_useful(source, need_left, buffer_left, cap):
    """True when plan_take() would plan any units from `source` for some item
    it holds: with cap > 0, an item with need left and units available, or
    buffer left and buffer units available. Pure; route planners run it
    inside lib/atomic.py calls."""
    if cap <= 0:
        return False
    available = source["available"]
    available_buffer = source.get("available_buffer", available)
    for item_id, units in available.items():
        if units > 0 and need_left.get(item_id, 0) > 0:
            return True
        if buffer_left.get(item_id, 0) > 0 and available_buffer.get(item_id, 0) > 0:
            return True
    return False


# Upper-bound cost of one route-planner candidate (drone_haul_plan._haul_candidate(),
# vehicle_cargo._pull_candidate()) in CPython opcodes, fitted on
# devtools/step_profile.py worst cases: per source (three stops' usefulness
# and chain checks) plus per item on the fullest source (sorting and planning
# its loads). A candidate runs as one lib/atomic.py call only when the
# estimate is within ROUTE_ATOMIC_MAX_COST: a game step costs 1.6-3 opcodes,
# so that stays well under the 10,000-step callback cap.
ROUTE_COST_PER_SOURCE = 600
ROUTE_COST_PER_ITEM = 560
ROUTE_ATOMIC_MAX_COST = 10000


def route_atomic_ok(sources):
    """True when one route candidate over `sources` is small enough for a lib/atomic.py call (ROUTE_ATOMIC_MAX_COST)."""
    items = max([len(s["available"]) for s in sources] or [0])
    return len(sources) * ROUTE_COST_PER_SOURCE + items * ROUTE_COST_PER_ITEM <= ROUTE_ATOMIC_MAX_COST


def network_deficits(curr_tick=None):
    """
    {item_id: units still missing} summed over every requesting outpost,
    from published "have" values (cheap -- no stock walk). For miner drones
    deciding which biosite is worth visiting first.
    """
    tick = curr_tick if curr_tick is not None else now_tick()
    totals = {}
    for o_id, items in active_requests(tick).items():
        flying = in_flight(o_id, tick)
        for item_id, entry in items.items():
            missing = entry.get("target", 0) - entry.get("have", 0) - flying.get(item_id, 0)
            if missing > 0:
                totals[item_id] = totals.get(item_id, 0) + missing
    return totals


def outpost_free_tiers(outpost: "OutpostRef", item_ids, requests=None, curr_tick=None, exclude_vehicle=None, include_depots=False, reads=None):
    """
    ({item_id: free for another outpost's need}, {item_id: free for a buffer
    top-up}) -- an outpost's "free stock", computed live (no per-outpost
    script needed): Warehouse stock (+ Inventory when it's home, + Crop
    Automators for forage, + Drone Depot stockpiles with include_depots)
    minus what the outpost keeps for itself (its own request's min for the
    need tier, its full target for the buffer tier), minus what other haulers
    already reserved from it. Depots are left out for ground haulers: a
    vehicle can only take() from Warehouses; a docked drone loads straight
    from the Depot stockpile. `reads` (PlanReads) supplies requests and
    reservations, and with include_depots the stock (its stock() has the same
    composition).
    """
    if reads is not None:
        requests = reads.requests
    requests = requests if requests is not None else active_requests(curr_tick)
    outpost_id = getattr(outpost, "id", None)
    own = requests.get(outpost_id, {})
    if reads is not None:
        taken = reads.reserved_from(outpost_id, exclude_vehicle)
    else:
        taken = reserved_from(outpost_id, curr_tick, exclude_vehicle)
    if reads is not None and include_depots:
        stock = reads.stock(outpost, item_ids)
    else:
        stock = _free_tier_stock(outpost, item_ids, include_depots)
    for_need, for_buffer = {}, {}
    for item_id in item_ids:
        units = stock[item_id]
        units -= taken.get(item_id, 0)
        entry = own.get(item_id)
        keep_need = request_min(entry) if entry else 0
        keep_buffer = (entry.get("target", 0) or 0) if entry else 0
        if units - keep_need > 0:
            for_need[item_id] = units - keep_need
        if units - keep_buffer > 0:
            for_buffer[item_id] = units - keep_buffer
    return for_need, for_buffer


def _free_tier_stock(outpost: "OutpostRef", item_ids, include_depots):
    """{item_id: units} outpost_free_tiers() counts: Warehouses (+ Depots with include_depots, + home Inventory/Forage)."""
    stock = warehouse_stocks(item_ids, outpost)
    if include_depots:
        for depot in local_depots(outpost):
            for item_id, units in depot_stock(depot).items():
                if item_id in stock:
                    stock[item_id] += units
    if getattr(outpost, "is_home", False):
        try:
            for item_id, units in stacks_stock(get_component("inventory"), item_ids).items():
                stock[item_id] += units
        except Exception as error:
            swallowed("logistics_requests.outpost_free_tiers: inventory stacks", error)
        if CROP_AUTOMATOR_ITEM_ID in stock:
            stock[CROP_AUTOMATOR_ITEM_ID] += crop_automator_forage_total(outpost)
    return stock


def outpost_free_stock(outpost: "OutpostRef", item_ids, requests=None, curr_tick=None, exclude_vehicle=None):
    """{item_id: units} an outpost can give to a buffer top-up (outpost_free_tiers() buffer tier, Warehouses only)."""
    return outpost_free_tiers(outpost, item_ids, requests, curr_tick, exclude_vehicle)[1]


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
