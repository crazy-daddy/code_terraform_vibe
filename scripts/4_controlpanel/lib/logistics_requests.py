# Generic "pull" logistics: an outpost announces items it wants stocked
# locally (a request), and a reverse hauler (lib/job_pull.py
# PullJob) parked there fetches them from wherever they sit on the
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
#   logistics.requests = {outpost_id: {item_id: {"levels": ladder, "have": h,
#                                                "by": requester, "buy": bool,
#                                                "keep": k, "tick": n}}}
#   logistics.pickups  = {pickup_key: {"vehicle", "dest", "source",
#                                      "item_id", "units", "tick",
#                                      "aboard"}}
# "levels" is the request's priority ladder (lib/priority.py): [[prio,
# cum_units], ...], the units the requester wants on hand and the band each
# slice of them is wanted at. A requester that needs 30 to keep working and
# would like 2000 on hand writes [[NEED, 30], [STOCK, 2000]]. Deficits of a
# higher band are served first everywhere (haul_rank()); what supply is left
# for the FAIR_BANDS is split between competing outposts in proportion to
# their deficits (fair_share_tiers()). A source outpost keeps its own level
# at a band back from another outpost's demand of that band or below
# (outpost_tier_free()). The band list is TIERS (= priority.BANDS).
# "have" is the requester's own last-published local stock -- a cheap,
# slightly lagging number for readers that can't afford a live stock walk
# (miner drones). The hauler recomputes local stock live (outpost_stock())
# before planning, since it's physically at the requesting outpost anyway.
# "buy": True (set_requests(buyable=True)) lets a Pioneer pull hauler or a
# hauler drone buy the item at the Shop on a home pickup (SHOP_SOURCE_ID) when
# no free stock covers it; unflagged requests are never bought.
# A BLOCKER level (lib/site_supply.py: a settled part a job waits on, a
# straggler, manual-order units built off home) makes a route carrying it
# skip the hauler's minimum load: nothing more arrives by waiting.
# "keep": k (units the outpost holds back from other outposts' demand of any
# band, not only from their buffer top-ups) marks a reserve: lib/site_supply.py
# sets it on the construction stock at the Constructor's home, so a Supply Dock
# order elsewhere builds its own units instead of taking the reserve.
# One owner per (outpost, item): publish_requests() leaves an item another
# requester holds there alone (skip_foreign), unless the caller opts out.
# "source" (outpost or drill id, None for legacy entries) lets a planner
# debit stock another hauler has already promised itself (reserved_from()),
# so two haulers never plan the same units at the same source.
# "aboard": True once the hauler has loaded the units (reserve_pickup(...,
# aboard=True) after each take); a planned-only entry still has them at the
# source. aboard_units() sums the loaded ones, so stock counts can include
# cargo on the move without counting a planned pickup twice.

import depot_stage
import mining_reservations
from archive import archive
from components import drone_station
from fleet_status import FLEET_STATUS_KEY, is_off_duty
from game_clock import is_fresh, now_tick
from item_tiers import DEPOT_TYPE_TIERS
from machine_controller import port_counts
from parking_client import wake_role
from priority import BANDS, BLOCKER, FAIR_BANDS, NEED, STOCK, band_deficits, band_name, ladder, ladder_level, ladder_total
from production_core import smelter_wants_at
from stock_scan import DEPOTS, HELD, LOCAL, scan, scan_key
from swallow import swallowed
from tree_console import TreeConsole

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


def haul_rank(tier_units, meters, overhead_m):
    """
    Planner ranking of one haul/pull candidate carrying `tier_units`
    ({band: units}, route_tier_units()): per TIERS (highest band first) the
    units serving that band or a higher one, per (route m + overhead_m).
    Compared with rank_beats(): BLOCKER throughput decides, then the next
    band's, ..., all units only break a tie, so a trip serving a requester
    that is about to stall always beats filling a buffer however big the
    buffer load is. A band's fine prio plays no part: a trip is scored by
    what it delivers per metre.
    """
    per = meters + overhead_m
    if per <= 0:
        per = 1.0
    rank = []
    served = 0
    for tier in TIERS:
        served += tier_units.get(tier, 0)
        rank.append(served / per)
    return tuple(rank)


def rank_text(rank):
    """haul_rank() `rank` for a log line: "blocker b, manual m, ..." per meter, bands with units only."""
    parts = [f"{band_name(tier)} {rate:.4f}" for tier, rate in zip(TIERS, rank) if rate > 0]
    return (", ".join(parts) or "nothing") + " per m"


def blocker_units(tier_units):
    """Units of a route's `tier_units` ({band: units}) in the BLOCKER band: with any, the hauler's minimum load is waived."""
    return tier_units.get(BLOCKER, 0)


def rank_beats(rank, best):
    """True when haul_rank() `rank` beats `best` (None = no candidate yet)."""
    if best is None:
        return True
    for mine, theirs in zip(rank, best):
        if mine != theirs:
            return mine > theirs
    return False


# A drone hauler counts as present (drone_served_source()) while its
# fleet.status heartbeat is younger than this (10 minutes).
HAULER_FRESH_TICKS = 6000

# Same window as mining_reservations.RESERVATION_STALE_TICKS.
PICKUP_STALE_TICKS = 36000

# Smallest load worth a haul trip, drone or ground (min_load_units()).
HAUL_MIN_LOAD_UNITS = 10


def min_load_units(blockers, reachable):
    """Units a haul trip must carry: 1 with BLOCKER units on board (blocker_units()), else
    HAUL_MIN_LOAD_UNITS or the whole `reachable` outstanding deficit when that is smaller."""
    if blockers > 0:
        return 1
    return HAUL_MIN_LOAD_UNITS if HAUL_MIN_LOAD_UNITS < reachable else reachable


# Minimum a SOURCE outpost keeps back from its own local consumers
# (Liquifier) for a remote requester -- roughly one extractor load. The
# requester's own target raises it (retain_amount()).
LIFEFORM_STASH_CAP_T = 25

# Pull-source id of the Shop (lib/pull_plan.py shop_source(),
# lib/drone_haul_plan.py shop_sources()): a virtual source at the home
# outpost, used only for buyable requests.
SHOP_SOURCE_ID = "shop"


# ------------------------------------------------------------------ requests


def _by(entry, requester):
    """True for a request entry `requester` holds."""
    return isinstance(entry, dict) and entry.get("by") == requester


def _prune_requests(requests, drop):
    """Deletes every request entry with drop(outpost_id, entry) true, then
    any outpost bucket that is not a dict or is left empty. Returns the
    pruned map ({} for a non-dict), for an archive transaction updater."""
    if not isinstance(requests, dict):
        return {}
    for o_id, items in list(requests.items()):
        if not isinstance(items, dict):
            del requests[o_id]
            continue
        for item_id, entry in list(items.items()):
            if drop(o_id, entry):
                del items[item_id]
        if not items:
            del requests[o_id]
    return requests


def _fresh_items(items, tick):
    """{item_id: entry} of the live requests in one outpost's bucket: non-stale dict entries
    with a ladder. Shared by active_requests() and set_requests()'s "already held" check, so
    a key haulers cannot see counts as new work when it is written again."""
    if not isinstance(items, dict):
        return {}
    return {i: e for i, e in items.items() if isinstance(e, dict) and e.get("levels") and is_fresh(e, tick, REQUEST_STALE_TICKS)}


# Outpost id whose bucket set_requests() last swept for stale entries (_sweep_next()).
_SWEEP = {"after": None}


def _sweep_next(requests, outpost_id, tick):
    """Prunes the stale entries of one outpost bucket other than `outpost_id`: the next id
    after the last one swept, in sorted order, wrapping. One bucket per call keeps
    set_requests() inside the step cap however many outposts publish requests; a bucket
    whose requester died is emptied within (outposts - 1) calls of any one calling script,
    since _SWEEP is per-script module state; readers ignore stale entries anyway."""
    others = sorted(o for o in requests if o != outpost_id)
    if not others:
        return
    after = _SWEEP["after"]
    o_id = next((o for o in others if after is None or o > after), others[0])
    _SWEEP["after"] = o_id
    items = requests[o_id]
    if isinstance(items, dict):
        for item_id, entry in list(items.items()):
            if not is_fresh(entry, tick, REQUEST_STALE_TICKS):
                del items[item_id]
    if not isinstance(items, dict) or not items:
        del requests[o_id]


def set_requests(outpost_id, requester, wants, curr_tick=None, buyable=False):
    """
    Replaces every request `requester` holds at `outpost_id` with `wants`
    ({item_id: (levels, have)} or (levels, have, keep); `levels` a
    priority ladder, priority.from_levels() for a plain (target, min)), in
    one transaction. keep > 0 stores "keep" (request_keep()). buyable=True
    marks the entries as Shop-buyable (buyable_deficits()): a Pioneer pull
    hauler or a hauler drone may buy them at home instead of finding free
    stock. An empty
    `wants` just withdraws the requester's entries there; so does an empty
    ladder. Stale entries of any requester are pruned on the way: all of
    them at `outpost_id`, and those of one other outpost per call
    (_sweep_next()).
    """
    tick = curr_tick if curr_tick is not None else now_tick()
    added = []
    # Built outside the transaction: the updater runs as one pure callback
    # under the step cap, and a Seed Maker's many ladders crashed it there.
    entries = {}
    for item_id, values in (wants or {}).items():
        levels = ladder(values[0])
        if not levels:
            continue
        entry = {"levels": levels, "have": values[1], "by": requester, "tick": tick}
        if buyable:
            entry["buy"] = True
        if len(values) > 2 and values[2] and values[2] > 0:
            entry["keep"] = values[2]
        entries[item_id] = entry

    def updater(requests):
        if not isinstance(requests, dict):
            requests = {}
        before = requests.get(outpost_id)
        held = set(_fresh_items(before, tick))
        bucket = {}
        if isinstance(before, dict):
            bucket = {i: e for i, e in before.items() if not _by(e, requester) and is_fresh(e, tick, REQUEST_STALE_TICKS)}
        bucket.update(entries)
        if bucket:
            requests[outpost_id] = bucket
        elif outpost_id in requests:
            del requests[outpost_id]
        _sweep_next(requests, outpost_id, tick)
        added[:] = [i for i in entries if i not in held]
        return requests

    archive.transaction(REQUESTS_KEY, {}, updater)
    if added:
        wake_role("hauler", f"new haul request: {outpost_id} {added[0]}")
    log.debug(f"set_requests({outpost_id!r}, {requester!r}): {len(wants)} item(s) at tick {tick}.")


def clear_requests(requester, outpost_id=None):
    """Withdraws every request by `requester` (at `outpost_id`, or everywhere)."""

    def updater(requests):
        return _prune_requests(requests, lambda o_id, entry: (outpost_id is None or o_id == outpost_id) and _by(entry, requester))

    archive.transaction(REQUESTS_KEY, {}, updater)
    log.debug(f"clear_requests({requester!r}, outpost_id={outpost_id!r}).")


# Foreign owners publish_requests() last logged, {(outpost_id, requester): {item_id: owner}}.
_foreign_logged = {}


def _unchanged(existing, wants, tick, buyable):
    """True when the published entries match wants and are young enough to skip a republish."""
    wants = {i: v for i, v in wants.items() if ladder(v[0])}
    if set(existing) != set(wants):
        return False
    for item_id, values in wants.items():
        entry = existing[item_id]
        if request_levels(entry) != ladder(values[0]):
            return False
        if request_keep(entry) != (values[2] if len(values) > 2 and values[2] and values[2] > 0 else 0):
            return False
        if bool(entry.get("buy")) != buyable:
            return False
        if not 0 <= tick - entry.get("tick", 0) < REPUBLISH_TICKS:
            return False
    return True


def publish_requests(outpost_id, requester, wants, curr_tick=None, requests=None, buyable=False, skip_foreign=True, have_of=None):
    """
    set_requests() unless the entries `requester` already published at
    `outpost_id` match `wants` (levels, keep, buy; "have" is not compared)
    and are younger than REPUBLISH_TICKS. Empty wants withdraws them.
    `requests` is an active_requests() snapshot (read when None).
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
        fresh = _fresh_items(items, tick)
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
    return dict(archive.get_dict(PICKUPS_KEY))


def planning_snapshot(vehicle_name):
    """
    pickups_snapshot() for a hauler about to plan with empty cargo. Its own
    entries are left over from an abandoned plan (script restart, replan
    after a dropped leg): nothing it reserved is aboard, so they are
    released first. Kept, they count as in flight and hide the deficit from
    every hauler, this one included, until PICKUP_STALE_TICKS. Writes only
    when such an entry exists.
    """
    seen = pickups_snapshot()
    if any(isinstance(entry, dict) and entry.get("vehicle") == vehicle_name for entry in seen.values()):
        log.debug(f"planning_snapshot({vehicle_name!r}): releasing pickups left from an abandoned plan.")
        release_pickups(vehicle_name)
        seen = pickups_snapshot()
    return seen


def _other_units(pickups, vehicle_name, tick, match):
    """{(field value, item_id): units} over fresh entries of OTHER vehicles, grouped by match ("source" or "dest")."""
    totals = {}
    for entry in pickups.values():
        if not is_fresh(entry, tick, PICKUP_STALE_TICKS) or entry.get("vehicle") == vehicle_name:
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
            if not isinstance(entry, dict) or entry.get("vehicle") == vehicle_name or not is_fresh(entry, tick, PICKUP_STALE_TICKS):
                del pickups[key]
        return pickups

    archive.transaction(PICKUPS_KEY, {}, updater)
    log.debug(f"release_pickups({vehicle_name!r}).")


def pickup_dest(vehicle_name):
    """
    Destination outpost id of vehicle_name's fresh pickups (aboard
    entries first), None when it holds none. A floating hauler (lib/job_pull.py)
    reads it after a script reload to deliver cargo aboard where it was
    claimed for, not to its HOME_BASE.
    """
    tick = now_tick()
    found = None
    for entry in pickups_snapshot().values():
        if not isinstance(entry, dict) or entry.get("vehicle") != vehicle_name or not entry.get("dest") or not is_fresh(entry, tick, PICKUP_STALE_TICKS):
            continue
        if entry.get("aboard"):
            return entry["dest"]
        found = found or entry["dest"]
    return found


def _pickup_totals(keep, tick):
    """{item_id: units} summed over the fresh PICKUPS entries that pass keep(entry)."""
    totals = {}
    for entry in archive.get_dict(PICKUPS_KEY).values():
        if not is_fresh(entry, tick, PICKUP_STALE_TICKS) or not keep(entry):
            continue
        item_id = entry.get("item_id")
        if item_id:
            totals[item_id] = totals.get(item_id, 0) + (entry.get("units", 0) or 0)
    return totals


def in_flight(dest_outpost_id, curr_tick=None):
    """{item_id: units} currently being hauled towards dest_outpost_id."""
    tick = curr_tick if curr_tick is not None else now_tick()
    return _pickup_totals(lambda entry: entry.get("dest") == dest_outpost_id, tick)


def aboard_units(curr_tick=None):
    """{item_id: units} loaded aboard a hauler and not delivered yet, any destination."""
    tick = curr_tick if curr_tick is not None else now_tick()
    return _pickup_totals(lambda entry: entry.get("aboard"), tick)


def reserved_from(source_id, curr_tick=None, exclude_vehicle=None):
    """
    {item_id: units} other haulers have planned to take from source_id (an
    outpost or drill id) and not delivered yet. The planning vehicle passes
    its own name as exclude_vehicle so its previous trip's leftovers don't
    count against it.
    """
    tick = curr_tick if curr_tick is not None else now_tick()
    return _pickup_totals(lambda entry: entry.get("source") == source_id and (exclude_vehicle is None or entry.get("vehicle") != exclude_vehicle), tick)


def _group_units(pickups, tick, field, exclude_vehicle=None):
    """{field value: {item_id: units}} over fresh `pickups` entries (except exclude_vehicle's), grouped by field ("dest" or "source"); in_flight() and reserved_from() for every id in one pass."""
    groups = {}
    if not isinstance(pickups, dict):
        return groups
    for entry in pickups.values():
        if not is_fresh(entry, tick, PICKUP_STALE_TICKS):
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
    every id from one pass over it, and one stock_scan.scan() per outpost
    serving stock() and outpost_tier_free(). Pass it as `reads=`
    to outpost_tier_deficits(), outpost_tier_free() and fair_share_tiers().
    Built per plan and dropped after it: stock is read live once per plan.
    """

    def __init__(self, curr_tick=None, pickups=None):
        self.tick = curr_tick if curr_tick is not None else now_tick()
        self.requests = active_requests(self.tick)
        self.pickups = pickups if pickups is not None else pickups_snapshot()
        self._by_dest = None
        self._by_source = {}
        self._scans = {}  # {stock_scan.scan_key(outpost): StockScan}
        self._depot_holds = {}  # {depot_id: depot_holds()}, read once per plan

    def depot_holds(self, depot_id, outpost_id):
        """depot_holds(depot_id, outpost_id) at the plan's tick, read once per plan."""
        holds = self._depot_holds.get(depot_id)
        if holds is None:
            holds = depot_holds(depot_id, outpost_id, self.tick)
            self._depot_holds[depot_id] = holds
        return holds

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

    def scan(self, outpost: "OutpostRef"):
        """stock_scan.scan() of `outpost`, read once per plan."""
        key = scan_key(outpost)
        held = self._scans.get(key)
        if held is None:
            held = scan(outpost)
            self._scans[key] = held
        return held

    def stock(self, outpost: "OutpostRef", item_ids):
        """{item_id: units} at `outpost` per outpost_stock() (stock_scan HELD), from the plan's one scan of it."""
        return self.scan(outpost).totals(HELD, item_ids)


# --------------------------------------------------------------------- stock


def local_depots(outpost: "OutpostRef | None"):
    """Resolved Drone Depots at `outpost` (an OutpostRef)."""
    if not outpost or not hasattr(outpost, "buildings"):
        return []
    refs = []
    for type_id in DEPOT_TYPE_TIERS:
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
        if isinstance(entry, dict) and entry.get("role") == "hauler" and entry.get("engine") and not is_off_duty(entry.get("state")) and is_fresh(entry, tick, HAULER_FRESH_TICKS):
            return True
    return False


def drone_served_source(source, dest_outpost):
    """
    Reason string when a pull source (lib/pull_plan.py pull_sources()
    dict) is left to drone haulers, else None. Only while drone_yield_enabled(),
    dest_outpost has a Drone Depot (drones can't deliver elsewhere) and at
    least one hauler drone is alive (drone_haulers_present()). Then field
    Mining Drills and outposts with their own Drone Depot are skipped; Water
    Pump salt stays (DroneCargo.load() can't take it).
    """
    if not drone_yield_enabled() or not local_depots(dest_outpost):
        return None
    if not drone_haulers_present():
        log.debug(f"drone_served_source(): drone yield on, but no hauler drone reported in the last {HAULER_FRESH_TICKS} ticks; keeping every source for ground haulers.")
        return None
    kind = source.get("kind")
    if kind == "drill":
        return "drill, drone-servable"
    if kind == "outpost" and local_depots(source.get("outpost")):
        return "outpost has a Drone Depot"
    return None


def depot_stock(depot):
    """{item_id: units} in one Drone Depot's shared stockpile."""
    return port_counts(getattr(depot, "output", None), "logistics_requests.depot_stock: port.stacks")


def depot_holds(depot_id, outpost_id, curr_tick=None, wants=None):
    """
    {item_id: units} of one Drone Depot's stockpile a ground hauler leaves
    alone: hauler drone stage requests there (lib/depot_stage.py) plus the ore
    same-outpost Smelters asked the Depot to push (production_core.
    smelter_wants_at(); fill_to as an upper bound: what a Smelter turns down
    drains to a Warehouse, where take_item() reaches it). Both are pushes the
    Depot is about to make; a take() racing them finds the stockpile short or
    "busy". `wants`: smelter_wants_at(outpost_id) when already read.
    """
    holds = dict(depot_stage.staged_for(depot_id, curr_tick))
    for ore, fill_to, _prio in (wants if wants is not None else smelter_wants_at(outpost_id, curr_tick)).values():
        holds[ore] = holds.get(ore, 0) + fill_to
    return holds


def take_from_depots(port: "InputSlot | VehicleInputSlot", item_id, amount, outpost: "OutpostRef | None", spare_holds=False, report=None):
    """
    take()s up to `amount` x `item_id` into `port` (an InputSlot, or a
    Pioneer's VehicleInputSlot inside the Depot's service area) from the
    Drone Depots at `outpost`, depot by depot, asking each only for what its
    stockpile holds -- less depot_holds() with spare_holds (ground haulers).
    Returns units moved. No retain rules: callers that must hold back
    requested stock (Essence Liquifier) do their own loop. `report`: optional
    dict, filled with {"sources": [(depot_id, status, moved), ...]}.
    """
    if report is not None:
        report["sources"] = []
    outpost_id = getattr(outpost, "id", None)
    wants = smelter_wants_at(outpost_id) if spare_holds else None
    moved_total = 0
    for depot in local_depots(outpost):
        if moved_total >= amount:
            break
        held = depot_stock(depot).get(item_id, 0)
        if spare_holds:
            held -= depot_holds(depot.id, outpost_id, wants=wants).get(item_id, 0)
        want = min(amount - moved_total, held)
        if want <= 0:
            continue
        try:
            if port.connected_id() != depot.id:
                port.connect(depot.id)
            res = port.take(item_id, want)
        except Exception as error:
            swallowed("logistics_requests.take_from_depots: port.take", error)
            if report is not None:
                report["sources"].append((depot.id, f"error: {error}", 0))
            continue
        moved = getattr(res, "moved", 0) or 0
        status = getattr(res, "status", None)
        log.trace(f"take {item_id} x{want} from depot '{depot.id}': {status}, moved {moved}.")
        if report is not None:
            report["sources"].append((depot.id, status, moved))
        moved_total += moved
    return moved_total


def outpost_stock(item_ids, outpost: "OutpostRef | None"):
    """
    {item_id: units} held at `outpost` (stock_scan HELD): its Warehouses,
    Storage Bins and Drone Depots, plus home Inventory and Crop Automator
    Forage when `outpost` is the home outpost. None (no outpost) = all 0.
    """
    if not item_ids or outpost is None:
        return {item_id: 0 for item_id in item_ids}
    return scan(outpost).totals(HELD, item_ids)


def request_levels(entry):
    """The priority ladder of one request entry ([] when malformed)."""
    return ladder(entry.get("levels"))


def request_target(entry):
    """The flat target of one request entry: its ladder's total."""
    return ladder_total(request_levels(entry))


def request_keep(entry):
    """Reserve of one request entry: its "keep", 0 when unset."""
    keep = entry.get("keep")
    return keep if isinstance(keep, (int, float)) and keep > 0 else 0


# Demand bands, most urgent first (lib/priority.py BANDS). Per band, the
# level a request entry asks for is its ladder's units at that band or
# higher (tier_level(); a band's deficit is what its level misses after the
# bands before it), the keep is what an outpost holds back from another
# outpost's demand at that band (tier_keep(): its own level there, or its
# "keep" reserve when higher), and FAIR_BANDS are the bands whose deficit is
# capped at the destination's fair share of the sources
# (fair_share_tiers()). tier_deficits(), tier_free() and the route planners
# (plan_take(), haul_rank(), route_tier_units()) walk TIERS.
TIERS = BANDS


def tier_level(entry, tier):
    """Units a request entry wants at band `tier` or higher."""
    return ladder_level(request_levels(entry), tier)


def tier_keep(entry, tier):
    """Units a request entry's outpost holds back from another outpost's demand at band `tier`."""
    return max(tier_level(entry, tier), request_keep(entry))


def tier_deficits(entry, have, flying):
    """{band: units missing} for one request entry given stock and in-flight units; bands with a deficit only."""
    return band_deficits(request_levels(entry), have + flying)


def tier_free(entry, units, cap, tiers=TIERS):
    """{band: units} of `units` held (after other haulers' claims) another outpost may take at each band of `tiers` (default every band): above that band's keep for `entry` (the holder's own request, None = none), at most `cap`."""
    if not entry:
        free = min(units, cap)
        return {tier: free for tier in tiers}
    levels = request_levels(entry)
    keep = request_keep(entry)
    return {tier: min(units - max(ladder_level(levels, tier), keep), cap) for tier in tiers}


def sum_tiers(tiers):
    """{item_id: units} over every tier of `tiers` ({tier: {item_id: units}})."""
    total = {}
    for tier in TIERS:
        for item_id, units in tiers.get(tier, {}).items():
            total[item_id] = total.get(item_id, 0) + units
    return total


def most_free(free):
    """{item_id: units}: the most any tier of `free` (outpost_tier_free() output) offers per item -- a tiered source's "available"."""
    available = {}
    for tier in TIERS:
        for item_id, units in free.get(tier, {}).items():
            available[item_id] = max(available.get(item_id, 0), units)
    return available


def split_need_stock(tiers):
    """({item_id: units}, {item_id: units}): a {band: {item_id: units}} dict
    folded into the bands at NEED or above (what keeps a requester working)
    and the bands below it (buffers and look-ahead)."""
    need = {}
    stock = {}
    for tier, items in tiers.items():
        bucket = need if tier >= NEED else stock
        for item_id, units in items.items():
            bucket[item_id] = bucket.get(item_id, 0) + units
    return need, stock


def outpost_deficits_tiered(outpost: "OutpostRef | None", curr_tick=None, live=True, reads=None, exclude_vehicle=None):
    """
    ({item_id: need units}, {item_id: buffer units}): outpost_tier_deficits()
    folded by split_need_stock().
    """
    return split_need_stock(outpost_tier_deficits(outpost, curr_tick, live, reads, exclude_vehicle))


def outpost_tier_deficits(outpost: "OutpostRef | None", curr_tick=None, live=True, reads=None, exclude_vehicle=None):
    """
    {band: {item_id: units}} still missing for requests at `outpost`
    (OutpostRef) per TIERS (tier_deficits(): each band's level minus local
    stock, in-flight and the higher bands' deficits). Bands and items with a
    deficit only. In-flight counts hauler pickups bound there and the yield
    of mining trips stockpiling there (mining_reservations), so a hauler and
    a miner never both fill the same deficit. exclude_vehicle leaves out that
    miner's own reservation. live=True counts local stock now; live=False
    trusts the requester's last published "have". `reads` (PlanReads)
    supplies requests, stock and in-flight pickups instead of reading them
    here.
    """
    tick = curr_tick if curr_tick is not None else now_tick()
    outpost_id = getattr(outpost, "id", None)
    requests = (reads.requests if reads is not None else active_requests(tick)).get(outpost_id, {})
    deficits = {}
    if not requests:
        return deficits
    if not live:
        have = {i: e.get("have", 0) for i, e in requests.items()}
    elif reads is not None:
        have = reads.stock(outpost, requests.keys())
    else:
        have = outpost_stock(list(requests.keys()), outpost)
    flying = dict(reads.in_flight(outpost_id) if reads is not None else in_flight(outpost_id, tick))
    for item_id, units in mining_reservations.get_reserved_yield_totals(tick, outpost_id=outpost_id, exclude_vehicle=exclude_vehicle).items():
        flying[item_id] = flying.get(item_id, 0) + units
    for item_id, entry in requests.items():
        for tier, units in tier_deficits(entry, have.get(item_id, 0), flying.get(item_id, 0)).items():
            if units > 0:
                deficits.setdefault(tier, {})[item_id] = units
    return deficits


def buyable_deficits(outpost: "OutpostRef", deficits, curr_tick=None, requests=None):
    """
    {band: {item_id: units}}: the part of `outpost`'s deficits
    (outpost_tier_deficits() output) whose request is flagged buyable
    (set_requests(buyable=True)), i.e. what a hauler may buy at the
    Shop for it. `requests` is an active_requests() read to reuse
    (PlanReads.requests), else read here.
    """
    if requests is None:
        requests = active_requests(curr_tick if curr_tick is not None else now_tick())
    requests = requests.get(getattr(outpost, "id", None), {})
    flagged = {item_id for item_id, entry in requests.items() if entry.get("buy")}
    return {tier: {i: u for i, u in items.items() if i in flagged} for tier, items in deficits.items()}


def outpost_deficits(outpost: "OutpostRef | None", curr_tick=None, live=True):
    """
    {item_id: units still missing} for requests at `outpost` (OutpostRef):
    target - local stock - in-flight pickups (every tier, see
    outpost_tier_deficits()), positive entries only.
    """
    return sum_tiers(outpost_tier_deficits(outpost, curr_tick, live))


def fair_tier_caps(dest_outpost_id, tier, deficit, supply, curr_tick=None, reads=None):
    """
    {item_id: units} dest may plan from its `tier` deficit `deficit`, given
    `supply` ({item_id: units} the planner can see for that tier). Split in
    proportion to every requesting outpost's deficit at that tier for that
    item (other outposts read from their published "have", minus
    in-flight). The largest deficit gets the rounding remainder, so the
    supply is never stranded by flooring. `reads` (PlanReads) supplies
    requests and in-flight units.
    """
    tick = curr_tick if curr_tick is not None else now_tick()
    others = {}
    for o_id, items in (reads.requests if reads is not None else active_requests(tick)).items():
        if o_id == dest_outpost_id:
            continue
        if not any(item_id in deficit for item_id in items):
            continue
        flying = reads.in_flight(o_id) if reads is not None else in_flight(o_id, tick)
        for item_id, entry in items.items():
            if item_id not in deficit:
                continue
            b = tier_deficits(entry, entry.get("have", 0) or 0, flying.get(item_id, 0)).get(tier, 0)
            if b > 0:
                others.setdefault(item_id, []).append(b)
    caps = {}
    for item_id, mine in deficit.items():
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
        log.debug(f"fair_tier_caps({dest_outpost_id!r}, {tier}, {item_id}): supply {available} vs deficits mine={mine}, others={rivals} -> {caps[item_id]}.")
    return caps


def has_fair_demand(deficits):
    """True when `deficits` ({band: {item_id: units}}) has a deficit at any FAIR_BANDS band."""
    for tier in FAIR_BANDS:
        if deficits.get(tier):
            return True
    return False


def fair_rival_entries(requests, item_ids):
    """[(outpost_id, item_id, entry)] of every request (active_requests() shape) for one of `item_ids`, in requests order. Pure."""
    out = []
    for o_id, items in requests.items():
        for item_id in item_ids:
            entry = items.get(item_id)
            if entry is not None:
                out.append((o_id, item_id, entry))
    return out


def fair_rival_bands(entries, reads):
    """
    [(outpost_id, item_id, {band: units})] per fair_rival_entries() row with
    any deficit (published "have" minus reads.in_flight()). Pure over
    `reads` (PlanReads); lib/atomic.py run_batched() slices it.
    """
    out = []
    for o_id, item_id, entry in entries:
        bands = tier_deficits(entry, entry.get("have", 0) or 0, reads.in_flight(o_id).get(item_id, 0))
        if bands:
            out.append((o_id, item_id, bands))
    return out


def fair_rivals_index(rows):
    """{item_id: [(outpost_id, {band: units})]} from fair_rival_bands() rows, requests order kept."""
    rivals = {}
    for o_id, item_id, bands in rows:
        rivals.setdefault(item_id, []).append((o_id, bands))
    return rivals


def fair_tier_caps_from(dest_outpost_id, tier, deficit, supply, rivals):
    """
    fair_tier_caps() over `rivals` (fair_rivals_index(), built once per
    plan) instead of re-parsing every rival's ladder per destination and
    band. One debug line per (dest, tier). Pure.
    """
    caps = {}
    notes = []
    for item_id, mine in deficit.items():
        available = max(0, int(supply.get(item_id, 0)))
        rival_units = []
        for o_id, bands in rivals.get(item_id, ()):
            b = bands.get(tier, 0)
            if b > 0 and o_id != dest_outpost_id:
                rival_units.append(b)
        total = mine + sum(rival_units)
        if not rival_units or total <= available:
            caps[item_id] = min(mine, available)
            continue
        share = available * mine // total
        if mine >= max(rival_units):
            share = available - sum(available * r // total for r in rival_units)
        caps[item_id] = max(0, min(mine, share))
        notes.append(f"{item_id} {available} vs {mine}/{rival_units} -> {caps[item_id]}")
    if notes:
        log.debug(f"fair_tier_caps({dest_outpost_id!r}, {tier}): supply vs mine/others: " + "; ".join(notes) + ".")
    return caps


def fair_share_tiers(dest_outpost_id, deficits, sources, curr_tick=None, reads=None, rivals=None):
    """
    `deficits` ({band: {item_id: units}}) with every FAIR_BANDS band capped
    at dest's fair share (fair_tier_caps()) of what `sources` other than
    dest itself free for that band (source_tier()). Other bands pass through
    unchanged. `rivals` (fair_rivals_index()) replaces the per-band request
    walk of fair_tier_caps().
    """
    capped = {}
    for tier in TIERS:
        deficit = deficits.get(tier, {})
        if not deficit or tier not in FAIR_BANDS:
            capped[tier] = dict(deficit)
            continue
        supply = {}
        for source in sources:
            if source["id"] == dest_outpost_id:
                continue
            for item_id, units in source_tier(source, tier).items():
                if item_id in deficit:
                    supply[item_id] = supply.get(item_id, 0) + units
        if rivals is not None:
            caps = fair_tier_caps_from(dest_outpost_id, tier, deficit, supply, rivals)
        else:
            caps = fair_tier_caps(dest_outpost_id, tier, deficit, supply, curr_tick, reads)
        capped[tier] = {i: u for i, u in caps.items() if u > 0}
    return capped


def source_tier(source, tier):
    """
    {item_id: units} a planner source dict frees for demand at `tier`: its
    "tiers" entry (outpost sources, outpost_tier_free(), every tier
    present), else "available" (drills, pumps, the Shop hold nothing back).
    """
    tiers = source.get("tiers")
    return tiers[tier] if tiers is not None else source["available"]


def route_left(deficits):
    """
    A route planner's working copy of `deficits` ({tier: {item_id: units}}):
    plan_take()'s `left`. Only the tiers with any deficit, in TIERS order, so
    the planners' per-item tier loops walk the one or two bands a destination
    asks for, not all nine.
    """
    return {tier: dict(deficits[tier]) for tier in TIERS if deficits.get(tier)}


def plan_take(source, item_id, left, cap):
    """
    {tier: units > 0} to plan from one source for item_id, given what each
    tier still misses (`left`, route_left()). Tiers are served in TIERS
    order; each only from what its free stock (source_tier()) leaves after
    the earlier tiers' takes, so a buffer never takes what the source keeps
    for itself. Hot path of every route candidate: kept lean.
    """
    tiers = source.get("tiers")
    takes = {}
    taken = 0
    for tier, wants in left.items():
        missing = wants.get(item_id, 0)
        if missing <= 0:
            continue
        free = (tiers[tier] if tiers is not None else source["available"]).get(item_id, 0)
        units = min(missing, free - taken, cap - taken)
        if units > 0:
            takes[tier] = units
            taken += units
    return takes


def source_useful(source, left, cap, room=None):
    """True when plan_take() would plan any units from `source` for some item
    it holds: with cap > 0, an item some tier still misses (`left`,
    route_left()) that the source frees for that tier. With `room`
    ({item_id: units} the cargo can still take), items without room don't
    count: no stop for material that won't fit. Pure; route planners run it
    inside lib/atomic.py calls."""
    if cap <= 0:
        return False
    available = source["available"]
    tiers = source.get("tiers")
    for item_id in available:
        if room is not None and room.get(item_id, 0) <= 0:
            continue
        for tier, wants in left.items():
            if wants.get(item_id, 0) > 0 and (tiers[tier] if tiers is not None else available).get(item_id, 0) > 0:
                return True
    return False


def route_tier_units(deficits, route):
    """
    {tier: units} of `route` ([(source, [(item_id, units), ...]), ...])
    serving each tier of `deficits` ({tier: {item_id: units}}); planning
    fills the tiers in TIERS order per item, so that order splits the loads.
    Only tiers with any deficit get an entry (read with .get()).
    """
    planned = {}
    for _source, loads in route:
        for item_id, units in loads:
            planned[item_id] = planned.get(item_id, 0) + units
    served = {}
    for tier in TIERS:
        missing = deficits.get(tier)
        if not missing:
            continue
        units = 0
        for item_id, left in list(planned.items()):
            take = min(left, missing.get(item_id, 0))
            planned[item_id] = left - take
            units += take
        served[tier] = units
    return served


def tier_rank(left, item_id):
    """Sort key of item_id at a route stop: largest deficit at the most urgent tier first (`left` as in plan_take())."""
    return [-wants.get(item_id, 0) for wants in left.values()]


# Upper-bound cost of one route-planner candidate (drone_haul_plan.haul_candidate(),
# pull_plan.pull_candidate()) in CPython opcodes, fitted on
# devtools/perf/step_profile.py worst cases (1-12 sources, 1-14 items each,
# 1-5 cargo pods): a base, per source (stop and chain checks), and per item
# summed over all sources (each stop's source_useful() pass walks every item
# of every source left, once per demand tier). Counting only the fullest
# source's items let many-source routes (a home short of 30 life forms) past
# the bound at twice the estimate, over the step cap. A candidate runs as one
# lib/atomic.py call only when the estimate is within
# ROUTE_ATOMIC_MAX_COST: a game step costs 1.6-3 opcodes, so that stays
# well under the 10,000-step callback cap.
ROUTE_COST_BASE = 4000
ROUTE_COST_PER_SOURCE = 240
ROUTE_COST_PER_ITEM = 350
ROUTE_ATOMIC_MAX_COST = 10000


def route_atomic_ok(sources):
    """True when one route candidate over `sources` is small enough for a lib/atomic.py call (ROUTE_ATOMIC_MAX_COST)."""
    items = sum([len(s["available"]) for s in sources])
    return ROUTE_COST_BASE + len(sources) * ROUTE_COST_PER_SOURCE + items * ROUTE_COST_PER_ITEM <= ROUTE_ATOMIC_MAX_COST


def network_band_deficits(curr_tick=None):
    """
    {band: {item_id: units still missing}} summed over every requesting
    outpost, from published "have" values (cheap -- no stock walk). For
    miner drones deciding which biosite is worth visiting first.
    """
    tick = curr_tick if curr_tick is not None else now_tick()
    totals = {}
    for o_id, items in active_requests(tick).items():
        flying = in_flight(o_id, tick)
        for item_id, entry in items.items():
            for tier, missing in tier_deficits(entry, entry.get("have", 0) or 0, flying.get(item_id, 0)).items():
                if missing > 0:
                    bucket = totals.setdefault(tier, {})
                    bucket[item_id] = bucket.get(item_id, 0) + missing
    return totals


def network_deficits(curr_tick=None):
    """{item_id: units still missing} over every band of network_band_deficits()."""
    return sum_tiers(network_band_deficits(curr_tick))


# Who loads at a source outpost (outpost_free_tiers() `loader`): a hauler
# drone loads anything held there (its Depot stages local stores into the
# stockpile first, lib/depot_stage.py); a ground vehicle take()s from the
# LOCAL stores, then from Drone Depot stockpiles less depot_holds().
LOADER_DRONE = "drone"
LOADER_VEHICLE = "vehicle"


def _vehicle_reach(held, outpost_id, item_ids, tick, reads=None):
    """{item_id: units} a ground vehicle can take() from StockScan `held`: LOCAL plus each Depot's
    stockpile above depot_holds() (from `reads` (PlanReads) when given, read once per plan)."""
    reach = held.totals(LOCAL, item_ids)
    holds = {}
    wants = None
    for item_id in item_ids:
        for depot_id, units in held.holders(item_id, DEPOTS):
            if depot_id not in holds:
                if reads is not None:
                    holds[depot_id] = reads.depot_holds(depot_id, outpost_id)
                    continue
                if wants is None:
                    wants = smelter_wants_at(outpost_id, tick)
                holds[depot_id] = depot_holds(depot_id, outpost_id, tick, wants)
            reach[item_id] += max(0, units - holds[depot_id].get(item_id, 0))
    return reach


def outpost_free_tiers(outpost: "OutpostRef", item_ids, requests=None, curr_tick=None, exclude_vehicle=None, loader=LOADER_VEHICLE, reads=None):
    """
    ({item_id: free for another outpost's NEED-band demand}, {item_id: free
    for a STOCK-band top-up}): outpost_tier_free() at the NEED and STOCK bands.
    """
    tiers = outpost_tier_free(outpost, item_ids, requests, curr_tick, exclude_vehicle, loader, reads)
    return tiers.get(NEED, {}), tiers.get(STOCK, {})


def outpost_tier_free(outpost: "OutpostRef", item_ids, requests=None, curr_tick=None, exclude_vehicle=None, loader=LOADER_VEHICLE, reads=None, tiers=TIERS):
    """
    {band: {item_id: units}} -- an outpost's "free stock" per TIERS, computed
    live (no per-outpost script needed): its held stock (stock_scan HELD)
    minus what the outpost keeps for itself at that band (tier_free(): its
    own request's level at that band or higher, or its "keep" reserve when
    higher), minus what other haulers already
    reserved from it. Capped by what `loader`
    can load there: a LOADER_DRONE everything held, a LOADER_VEHICLE
    _vehicle_reach() (Depot units under depot_holds() stay out). Other
    haulers' pickups count against those held-back Depot units first: a
    drone's stage request is its own pickup. `reads` (PlanReads) supplies
    requests, reservations and the stock scan. Only the bands in `tiers`
    are computed; the others stay empty (every TIERS key is present).
    """
    if reads is not None:
        requests = reads.requests
    requests = requests if requests is not None else active_requests(curr_tick)
    tick = reads.tick if reads is not None else (curr_tick if curr_tick is not None else now_tick())
    outpost_id = getattr(outpost, "id", None)
    own = requests.get(outpost_id, {})
    if reads is not None:
        taken = reads.reserved_from(outpost_id, exclude_vehicle)
        held = reads.scan(outpost)
    else:
        taken = reserved_from(outpost_id, tick, exclude_vehicle)
        held = scan(outpost)
    stock = held.totals(HELD, item_ids)
    reach = stock if loader == LOADER_DRONE else _vehicle_reach(held, outpost_id, item_ids, tick, reads)
    free = {tier: {} for tier in TIERS}
    for item_id in item_ids:
        claimed = taken.get(item_id, 0)
        cap = reach[item_id] - max(0, claimed - (stock[item_id] - reach[item_id]))
        # Nothing held net of claims, or nothing loadable: no tier frees any.
        if cap <= 0 or stock[item_id] - claimed <= 0:
            continue
        for tier, units in tier_free(own.get(item_id), stock[item_id] - claimed, cap, tiers).items():
            if units > 0:
                free[tier][item_id] = units
    return free


def outpost_free_stock(outpost: "OutpostRef", item_ids, requests=None, curr_tick=None, exclude_vehicle=None):
    """{item_id: units} an outpost can give to a ground vehicle's STOCK-band top-up (outpost_free_tiers() second value)."""
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
        return request_target(own)
    retain = 0
    for o_id, items in requests.items():
        if o_id == outpost_id:
            continue
        entry = items.get(item_id)
        if entry:
            retain = max(retain, LIFEFORM_STASH_CAP_T, request_target(entry))
    return retain
