# Stranded stock eviction, split out of lib/site_supply.py: ore, goods,
# stragglers and lab reagents left at an outpost that no longer uses them.
# site_supply.publish_site_requests() runs evict_stranded() once per pass
# and raises each destination's wants by the result (add_evicted()).
#
# Role switch drain: removing a site's Smelters drops its ore request, so its
# leftover ore becomes free stock that pull haulers take wherever it is
# requested. Ore that still sits at an outpost with no Smelter (home
# included), that the outpost does not mine (an active ore its stationed miners
# reach, outpost_mining.mineable_ores_by_outpost()),
# request or consume (a Supply Dock order there), for EVICT_AFTER_TICKS
# (first seen in STRANDED_KEY) is evicted.
#
# Stranded goods: ingots and intermediates (item_catalog category in
# EVICT_GOODS_CATEGORIES) that some Fabricator recipe takes as input are
# evicted the same way from an outpost with no Fabricator (home included)
# that neither requests nor consumes them. Deployables stay put:
# construction kits are another category, storage.must_stay_in_inventory()
# items (the Warehouse sweep's Inventory-only list) are skipped, and so are
# CONSTRUCTION_ITEM_IDS (Constructor materials, moved by blueprint demand) and
# EVICT_HOLD_ITEM_IDS.
#
# Stragglers: a leftover of at most STRAGGLER_MAX_UNITS of a finished good
# (EVICT_GOODS_CATEGORIES, plus deployables already in storage there:
# STRAGGLER_KIT_CATEGORIES and storage.INVENTORY_ONLY_ITEM_IDS, such as the
# tail of a kit or cargo pod order) at an outpost other than home or a storage
# outpost, that the outpost neither requests, consumes nor still builds with
# (its Fabricators' site targets and staged inputs; a root built here for
# another site counts only while a local Fabricator is making it), holds a
# whole Storage Bin or Warehouse slot and is below every hauler's minimum
# load. STRAGGLER_ANY_SIZE_ITEM_IDS (tar, the Fabricators' byproduct) count
# at any size: they wait for a Refiner in storage, not in a fab site's slot.
# After EVICT_AFTER_TICKS it is evicted as a BLOCKER request, so haulers skip
# their minimum load. Stranded goods keep their own rule where both match.
#
# Stranded reagents: lab reagents (outpost_reagents.LAB_REAGENT_ITEM_IDS) at
# an outpost with no Bio Lab that neither requests nor consumes them go home
# when home has a Bio Lab or no outpost has one. With only remote Labs they
# stay: a remote Lab's pull hauler takes free stock before it buys at the
# Shop. With no Bio Lab anywhere for EVICT_AFTER_TICKS,
# sell_stranded_reagents() sells home's reagents (they sell at the Shop
# price, so a later Lab buys them back at no loss).
#
# Destinations (evict_candidates()), first with room first: a user of the
# item (ore: home when a home Smelter refines it, then the smelting sites;
# goods: home when home has a Fabricator, then the fab sites; Constructor
# stragglers: the Constructor's home only), then the storage outposts
# (storage_outposts(): storage, a Drone Depot and no building that loses
# throughput over the outpost cap), nearest first. Reagents go home only.
# Home is never a fallback for anything else: with no candidate the stock
# is not stranded and stays. Room (evict_room())
# is slot-bound: the slots already holding the item, or its planned target
# rounded up to whole slots, else one empty slot while EVICT_FREE_SLOTS_KEEP
# stay empty; what finds no room stays. A storage outpost is the dump for
# leftovers: it takes every slot to capacity (storage.open_room()), and
# lib/storage_expand.py buys it another Warehouse before it runs out.
# Home as a user is not capped and requests the units itself (requester
# EVICT_REQUESTER); another destination's site-supply target is raised by
# them (add_evicted()). Requested until gone.

import components
import fleet_status
from archive import STATUS_STALE_TICKS, archive
from components import component
from game_clock import is_fresh
from game_rules import RAW_ORE_ITEM_IDS
from geometry import distance
from item_tiers import DEPOT_TYPE_TIERS
from logistics_requests import REQUEST_STALE_TICKS, active_requests, depot_stock, in_flight, local_depots, outpost_free_tiers, outpost_stock, publish_requests, request_target
from outpost_mining import active_ores, mineable_ores_by_outpost
from outpost_reagents import BIO_LAB_TYPE_ID, LAB_REAGENT_ITEM_IDS
from priority import BLOCKER, NEED, ladder_total
from production import SourceCache, discover_building_ids, discover_fabricator_ids, discover_smelter_ids, fab_site_gross_need, get_fabricator_pipeline, get_site_fabricator_targets, smelter_ores
from storage import INVENTORY_ONLY_ITEM_IDS, PENALIZED_TYPES, STAGING_FREE_SLOTS_KEEP, STORAGE_TYPE_IDS, discover_storage_buildings, inventory_count, inventory_room, must_stay_in_inventory, open_room, outpost_is_home, slot_layout, slot_room
from swallow import swallowed
from tree_console import TreeConsole

log = TreeConsole(module="site_supply")  # the evict lines keep site_supply's log level

# Role switch drain: {outpost_id: {ore: first tick seen stranded}}, pruned to
# what is stranded now.
STRANDED_KEY = "site_supply.stranded"
# Tick since no outpost has a Bio Lab (sell_stranded_reagents()); None while one has.
_labless_since = None
EVICT_REQUESTER = "site_evict"
# How long ore or goods sit stranded before they are evicted.
EVICT_AFTER_TICKS = REQUEST_STALE_TICKS
# item_catalog categories of stranded goods: ingots and intermediates.
EVICT_GOODS_CATEGORIES = ("refined", "crafted")
# Constructor materials (docs/components/constructor_module.md): never
# evicted; a pending blueprint's consumer request moves them to the
# Constructor's home (production.construction_site_id()).
CONSTRUCTION_ITEM_IDS = (
    "gas_pipe_segment",
    "liquid_pipe_segment",
    "power_line_segment",
    "gas_pipe_bridge",
    "liquid_pipe_bridge",
    "power_line_bridge",
)
# Goods never evicted as stranded goods (to a fab site) although a Fabricator
# recipe takes them: tar is mainly the Refiner's reagent
# (docs/database/recipes_refiner.md), and where the Refiner will stand is
# open. Off home it leaves as a straggler (STRAGGLER_ANY_SIZE_ITEM_IDS).
EVICT_HOLD_ITEM_IDS = ("tar",)
# Largest leftover of a finished good evicted as a straggler (see module comment).
STRAGGLER_MAX_UNITS = 50
# item_catalog categories of deployables that are stragglers too: a kit left
# in a Warehouse after its order holds a slot like any other leftover.
STRAGGLER_KIT_CATEGORIES = ("construction_kit",)
# Stragglers at any size: tar piles up as the Fabricators' byproduct and would
# hold a fab site's Warehouse slot until a Refiner (often elsewhere) asks.
STRAGGLER_ANY_SIZE_ITEM_IDS = ("tar",)
# Empty storage slots an eviction leaves free at a user site (evict_room()).
# At an outpost whose Drone Depot stages life forms (a miner drone is homed
# there) it leaves one more than the Depot keeps, so the Depot can still open
# a life-form slot.
EVICT_FREE_SLOTS_KEEP = 1
EVICT_STAGING_SLOTS_KEEP = STAGING_FREE_SLOTS_KEEP + 1


def smelting_sites(outposts):
    """{site_id: set of ores its Smelters refine} for every outpost with a Smelter."""
    return {getattr(o, "id", None): set(smelter_ores(o)) for o in outposts if discover_smelter_ids(o)}


def stranded_ore(outposts, requests, smelt_ores, consumers=None, tick=None):
    """{outpost_id: {ore: units}} ore at an outpost with no Smelter that the
    outpost neither mines (an active ore its stationed miners reach, so a
    mining outpost keeps its buffer), requests nor consumes (a Supply Dock order
    there). evict_stranded() keeps what has somewhere to go."""
    consumers = consumers or {}
    active = active_ores()
    mined = mineable_ores_by_outpost(tick)
    result = {}
    for outpost in outposts:
        site_id = getattr(outpost, "id", None)
        if site_id is None or site_id in smelt_ores:
            continue
        kept = (mined.get(site_id, set()) & active) | set(requests.get(site_id, {}))
        kept |= {o for o in RAW_ORE_ITEM_IDS if ladder_total((consumers.get(o) or {}).get(site_id, [])) > 0}
        ores = sorted(o for o in RAW_ORE_ITEM_IDS if o not in kept)
        held = {ore: units for ore, units in outpost_stock(ores, outpost).items() if units > 0}
        if held:
            result[site_id] = held
    return result


def fab_sites(outposts):
    """Sorted ids of every outpost with a Fabricator."""
    return sorted(getattr(o, "id", None) for o in outposts if getattr(o, "id", None) is not None and discover_fabricator_ids(o))


def lab_sites(outposts):
    """Sorted ids of every outpost with a Bio Lab."""
    return sorted(getattr(o, "id", None) for o in outposts if getattr(o, "id", None) is not None and discover_building_ids(BIO_LAB_TYPE_ID, o))


def stranded_reagents(outposts, requests, lab_ids, consumers=None):
    """{outpost_id: {item_id: units}} lab reagents at an outpost with no Bio
    Lab that it neither requests nor consumes. evict_stranded() keeps what
    has somewhere to go."""
    consumers = consumers or {}
    result = {}
    for outpost in outposts:
        site_id = getattr(outpost, "id", None)
        if site_id is None or site_id in lab_ids:
            continue
        kept = set(requests.get(site_id, {}))
        items = [i for i in LAB_REAGENT_ITEM_IDS if i not in kept and ladder_total((consumers.get(i) or {}).get(site_id, [])) <= 0]
        held = {item_id: units for item_id, units in outpost_stock(items, outpost).items() if units > 0}
        if held:
            result[site_id] = held
    return result


def storage_outposts(outposts):
    """Storage outposts: not home, at least one Warehouse or Storage Bin and
    a Drone Depot (the drone haulers' only destination), and no building of
    a type that loses throughput over the outpost cap (storage.PENALIZED_TYPES):
    such an outpost may hold more buildings than the cap at no cost."""
    stores = []
    for outpost in outposts:
        if outpost_is_home(outpost):
            continue
        try:
            types = {getattr(b, "type_id", None) for b in outpost.buildings()}
        except Exception as error:
            swallowed("site_supply.storage_outposts: outpost.buildings", error)
            continue
        if types & set(STORAGE_TYPE_IDS) and types & set(DEPOT_TYPE_TIERS) and not types & set(PENALIZED_TYPES):
            stores.append(outpost)
    return stores


def _distance(a, b):
    """Metres between two outpost anchors, 0 when either is unknown."""
    if a is None or b is None:
        return 0.0
    return distance((getattr(a, "x", 0.0) or 0.0, getattr(a, "y", 0.0) or 0.0), (getattr(b, "x", 0.0) or 0.0, getattr(b, "y", 0.0) or 0.0))


def evict_candidates(item_id, kind, source, home_id, smelt_ores, fab_ids, stores, build_site, lab_ids=()):
    """Outpost ids stranded item_id at `source` (OutpostRef) may go to, best
    first; kind is "ore", "goods", "reagent" or "straggler". Users first: ore
    to home when a home Smelter refines it, then every smelting site that
    does (by id); goods to home when home has a Fabricator, then every fab
    site; Constructor items (stragglers) to the Constructor's home
    (build_site) only. Then the storage outposts (`stores`,
    storage_outposts()), nearest first, unless the source is one. Reagents
    go to home only, when home is in `lab_ids` (lab_sites()) or that is
    empty. Never the source itself."""
    source_id = getattr(source, "id", None)
    if kind == "reagent":
        # Home uses or sells them; a remote Lab's pull hauler takes them as free stock.
        return [home_id] if home_id is not None and home_id != source_id and (home_id in lab_ids or not lab_ids) else []
    if kind == "ore":
        sites = ([home_id] if item_id in smelt_ores.get(home_id, ()) else []) + sorted(s for s in smelt_ores if item_id in smelt_ores[s])
    elif kind == "goods":
        sites = ([home_id] if home_id in fab_ids else []) + list(fab_ids)
    elif item_id in CONSTRUCTION_ITEM_IDS:
        return [build_site] if build_site is not None and build_site != source_id else []
    else:
        sites = []
    store_ids = [getattr(o, "id", None) for o in stores]
    if source_id not in store_ids:
        sites += [getattr(o, "id", None) for o in sorted(stores, key=lambda o: (_distance(o, source), getattr(o, "id", "")))]
    result = []
    for site_id in sites:
        if site_id is not None and site_id != source_id and site_id not in result:
            result.append(site_id)
    return result


def _category(catalog: "ItemCatalog", item_id):
    try:
        info = catalog.lookup(item_id)
    except Exception as error:
        swallowed("site_supply._category: catalog.lookup", error)
        return None
    return getattr(info, "category", None) if info else None


def evictable_goods(cache: "SourceCache"):
    """Item ids that may be evicted as stranded goods: Fabricator recipe
    inputs in EVICT_GOODS_CATEGORIES, minus storage.must_stay_in_inventory(),
    Constructor items and EVICT_HOLD_ITEM_IDS. Empty without an item_catalog."""
    catalog = component("item_catalog")
    if not catalog or not hasattr(catalog, "lookup"):
        return set()
    inputs = set()
    for recipe in cache.fabricator_recipes():
        inputs |= set(getattr(recipe, "inputs", {}) or {})
    skip = set(CONSTRUCTION_ITEM_IDS) | set(EVICT_HOLD_ITEM_IDS)
    candidates = {i for i in inputs if i not in skip and _category(catalog, i) in EVICT_GOODS_CATEGORIES}
    return {i for i in candidates if not must_stay_in_inventory(i)}


def held_item_ids(outpost: "OutpostRef"):
    """Item ids in an outpost's Warehouses and Drone Depots (what a hauler can load)."""
    held = set()
    for building in discover_storage_buildings(outpost):
        component = building["component"]
        try:
            held |= set(component.materials() or [])
        except Exception as error:
            swallowed("site_supply.held_item_ids: component.materials", error)
    for depot in local_depots(outpost):
        held |= {i for i, units in depot_stock(depot).items() if units > 0}
    return held


def stranded_goods(outposts, requests, fab_ids, goods, consumers=None):
    """{outpost_id: {item_id: units}} evictable goods (evictable_goods()) at
    an outpost with no Fabricator that it neither requests nor consumes.
    evict_stranded() keeps what has somewhere to go."""
    consumers = consumers or {}
    result = {}
    if not goods:
        return result
    for outpost in outposts:
        site_id = getattr(outpost, "id", None)
        if site_id is None or site_id in fab_ids:
            continue
        kept = set(requests.get(site_id, {}))
        items = sorted(i for i in held_item_ids(outpost) & goods if i not in kept and ladder_total((consumers.get(i) or {}).get(site_id, [])) <= 0)
        held = {item_id: units for item_id, units in outpost_stock(items, outpost).items() if units > 0}
        if held:
            result[site_id] = held
    return result


def stragglers(outposts, requests, home_id, cache: "SourceCache", consumers=None, roots=()):
    """{outpost_id: {item_id: units}} small leftovers of finished goods (see
    the module comment): category in EVICT_GOODS_CATEGORIES, at most
    STRAGGLER_MAX_UNITS at an outpost other than home that neither requests
    nor consumes them, nor holds them in its Fabricators' site targets or
    staged inputs. A root target (`roots`) in the site targets is kept only
    while a local Fabricator is making it (get_fabricator_pipeline()):
    leftovers of an export batch leave once the batch is done.
    Deployables count too (STRAGGLER_KIT_CATEGORIES and
    storage.INVENTORY_ONLY_ITEM_IDS): a held one already sits in storage.
    Other storage.must_stay_in_inventory() items and EVICT_HOLD_ITEM_IDS are
    skipped, except STRAGGLER_ANY_SIZE_ITEM_IDS, which count at any size.
    Empty without an item_catalog."""
    catalog = component("item_catalog")
    if not catalog or not hasattr(catalog, "lookup"):
        return {}
    consumers = consumers or {}
    result = {}
    for outpost in outposts:
        site_id = getattr(outpost, "id", None)
        if site_id is None or site_id == home_id:
            continue
        kept = set(requests.get(site_id, {})) | (set(EVICT_HOLD_ITEM_IDS) - set(STRAGGLER_ANY_SIZE_ITEM_IDS))
        fabricator_ids = discover_fabricator_ids(outpost)
        if fabricator_ids:
            building = {i for i, units in get_fabricator_pipeline(cache, site_id).items() if units > 0}
            kept |= {i for i, units in get_site_fabricator_targets(site_id, cache).items() if units > 0 and (i not in roots or i in building)}
            kept |= set(fab_site_gross_need(fabricator_ids, None, cache))
        candidates = sorted(i for i in held_item_ids(outpost) if i not in kept and ladder_total((consumers.get(i) or {}).get(site_id, [])) <= 0)
        items = [i for i in candidates if i in INVENTORY_ONLY_ITEM_IDS or (_category(catalog, i) in EVICT_GOODS_CATEGORIES + STRAGGLER_KIT_CATEGORIES and not must_stay_in_inventory(i))]
        held = {item_id: units for item_id, units in outpost_stock(items, outpost).items() if 0 < units and (units <= STRAGGLER_MAX_UNITS or item_id in STRAGGLER_ANY_SIZE_ITEM_IDS)}
        if held:
            result[site_id] = held
    return result


def evict_stranded(outposts, requests, tick, consumers=None, smelt_ores=None, goods=None, straggling=None, build_site=None):
    """Tracks stranded ore, goods, reagents and stragglers that have somewhere to go
    (evict_candidates(); STRANDED_KEY), sends what sat there
    EVICT_AFTER_TICKS to the first candidates with room (evict_room()),
    leaves the rest where it is, publishes home's evict request for what is
    headed home, and returns (that request's wants, {site_id: {item_id:
    units}} free stranded units headed to each other site, {site_id: set of
    straggler item ids headed there}: their requests there are BLOCKER, home
    included). goods = evictable_goods(), straggling = stragglers() (none
    when omitted); build_site = the Constructor's home."""
    eviction = _Eviction(outposts, requests, tick, smelt_ores, build_site)
    stranded, kinds = eviction.gather(consumers, goods, straggling)
    routes, stranded = eviction.route(stranded, kinds)
    seen = _track_first_seen(stranded, tick)
    if eviction.home is None or eviction.home_id is None:
        return {}, {}, {}
    ripe = _ripe_items(seen, tick)
    free, rush = eviction.allocate(ripe, routes, kinds)
    wants = eviction.publish_home(ripe, routes, free, rush)
    return wants, {site_id: extra for site_id, extra in free.items() if site_id != eviction.home_id}, rush


def _track_first_seen(stranded, tick):
    """{site_id: {item_id: first tick seen stranded}} (STRANDED_KEY), saved when changed."""
    stored = archive.get(STRANDED_KEY, {})
    stored = stored if isinstance(stored, dict) else {}
    seen = {}
    for site_id, held in stranded.items():
        previous = stored.get(site_id)
        previous = previous if isinstance(previous, dict) else {}
        seen[site_id] = {item_id: previous.get(item_id, tick) for item_id in held}
    if seen != stored:
        archive.set(STRANDED_KEY, seen)
    return seen


def _ripe_items(seen, tick):
    """{site_id: [item_id]} stranded for EVICT_AFTER_TICKS or longer."""
    ripe = {}
    for site_id, first_seen in seen.items():
        for item_id, first_tick in first_seen.items():
            if tick - first_tick >= EVICT_AFTER_TICKS:
                ripe.setdefault(site_id, []).append(item_id)
    return ripe


class _Eviction:
    """One evict_stranded() pass: the outposts' roles and the phases that use them."""

    def __init__(self, outposts, requests, tick, smelt_ores, build_site):
        self.outposts = outposts
        self.requests = requests
        self.tick = tick
        self.build_site = build_site
        self.home = next((o for o in outposts if outpost_is_home(o)), None)
        self.home_id = getattr(self.home, "id", None)
        if smelt_ores is None:
            smelt_ores = smelting_sites(outposts)
        self.smelt_ores = smelt_ores
        self.fab_ids = fab_sites(outposts)
        self.lab_ids = lab_sites(outposts)
        self.stores = storage_outposts(outposts)
        self.store_ids = {getattr(o, "id", None) for o in self.stores}
        self.by_id = {getattr(o, "id", None): o for o in outposts}

    def gather(self, consumers, goods, straggling):
        """({site_id: {item_id: units}} stranded, {(site_id, item_id): kind})."""
        outposts, requests = self.outposts, self.requests
        stranded = {}
        kinds = {}
        found_by_kind = (
            ("ore", stranded_ore(outposts, requests, self.smelt_ores, consumers, self.tick)),
            ("goods", stranded_goods(outposts, requests, self.fab_ids, goods or set(), consumers)),
            ("reagent", stranded_reagents(outposts, requests, self.lab_ids, consumers)),
        )
        for kind, found in found_by_kind:
            for site_id, held in found.items():
                stranded.setdefault(site_id, {}).update(held)
                kinds.update({(site_id, item_id): kind for item_id in held})
        other_rules = {i for held in stranded.values() for i in held}
        for site_id, held in (straggling or {}).items():
            if site_id in self.store_ids:
                continue  # a storage outpost holds leftovers by design
            extra = {i: units for i, units in held.items() if i not in other_rules}
            stranded.setdefault(site_id, {}).update(extra)
            kinds.update({(site_id, item_id): "straggler" for item_id in extra})
        return stranded, kinds

    def route(self, stranded, kinds):
        """({(site_id, item_id): candidate destinations}, stranded with somewhere to go)."""
        routes = {}
        for site_id, held in stranded.items():
            for item_id in held:
                routes[(site_id, item_id)] = evict_candidates(item_id, kinds[(site_id, item_id)], self.by_id.get(site_id), self.home_id, self.smelt_ores, self.fab_ids, self.stores, self.build_site, self.lab_ids)
        stranded = {site_id: {i: u for i, u in held.items() if routes[(site_id, i)]} for site_id, held in stranded.items()}
        stranded = {site_id: held for site_id, held in stranded.items() if held}
        return routes, stranded

    def allocate(self, ripe, routes, kinds):
        """Sends each ripe item's free units to its first destinations with
        room. Returns ({dest: {item_id: units}}, {dest: straggler item ids})."""
        requests, tick, by_id = self.requests, self.tick, self.by_id
        rooms = {}
        free = {}
        rush = {}
        staging = lifeform_staging_sites(tick) if ripe else set()
        for site_id in sorted(ripe):
            for_need, _for_buffer = outpost_free_tiers(by_id[site_id], sorted(ripe[site_id]), requests, tick)
            for item_id, units in sorted(for_need.items()):
                for dest in routes[(site_id, item_id)]:
                    if (dest, item_id) not in rooms:
                        rooms[(dest, item_id)] = evict_room(by_id.get(dest), item_id, requests, tick, self.home_id, dest in self.store_ids, dest in staging)
                    room = rooms[(dest, item_id)]
                    take = units if room is None else min(units, room)
                    if take <= 0:
                        continue
                    if room is not None:
                        rooms[(dest, item_id)] = room - take
                    bucket = free.setdefault(dest, {})
                    bucket[item_id] = bucket.get(item_id, 0) + take
                    if kinds[(site_id, item_id)] == "straggler":
                        rush.setdefault(dest, set()).add(item_id)
                    log.debug(f"evict_stranded: {take} {item_id} stranded at {site_id} -> {dest}")
                    units -= take
                    if units <= 0:
                        break
                if units > 0:
                    log.debug(f"evict_stranded: {units} {item_id} stay at {site_id}, no room at {routes[(site_id, item_id)]}")
        return free, rush

    def publish_home(self, ripe, routes, free, rush):
        """Publishes home's evict request for the ripe items headed home; its wants."""
        from site_supply import as_requests, want_raise  # cycle: site_supply imports site_evict

        home_id, requests, tick = self.home_id, self.requests, self.tick
        home_requests = requests.get(home_id, {})
        home_free = free.get(home_id, {})
        home_bound = {i for (site_id, i), dests in routes.items() if home_id in dests and i in ripe.get(site_id, ())}
        items = sorted(i for i in home_bound if home_requests.get(i, {}).get("by", EVICT_REQUESTER) == EVICT_REQUESTER)
        wants = {}
        if items:
            have = outpost_stock(items, self.home)
            flying = in_flight(home_id, tick)
            for item_id in items:
                if home_free.get(item_id, 0) > 0 or flying.get(item_id, 0) > 0:
                    level = have.get(item_id, 0) + flying.get(item_id, 0) + home_free.get(item_id, 0)
                    # Stragglers are a BLOCKER (below every hauler's minimum load); other stranded stock a NEED.
                    want_raise(wants, item_id, BLOCKER if item_id in rush.get(home_id, ()) else NEED, level, have.get(item_id, 0))
                    log.debug(f"evict_stranded: {item_id} free={home_free.get(item_id, 0)} in flight={flying.get(item_id, 0)} -> home level {level}")
        if publish_requests(home_id, EVICT_REQUESTER, as_requests(wants), tick, requests, skip_foreign=False):
            if wants:
                log.print(f"Evicting stranded stock to home: {', '.join(sorted(wants))}.")
            else:
                log.print("Stranded stock evicted.")
        return wants


def sell_stranded_reagents(curr_tick):
    """Sells home's lab reagents once no outpost has had a Bio Lab for
    EVICT_AFTER_TICKS (see the module comment). Warehouse and Storage Bin
    stock moves to Inventory first (up to storage.inventory_room()), then the
    Shop sells what Inventory holds. Reagents home requests (other than the
    evict request that brought them) stay. Returns the credits earned."""
    global _labless_since
    if discover_building_ids(BIO_LAB_TYPE_ID):
        _labless_since = None
        return 0
    if _labless_since is None:
        _labless_since = curr_tick
    if curr_tick - _labless_since < EVICT_AFTER_TICKS:
        return 0
    home = next((o for o in components.outposts() if outpost_is_home(o)), None)
    shop = component("shop")
    if home is None or not shop:
        return 0
    requests = active_requests(curr_tick).get(getattr(home, "id", None), {})
    kept = {i for i, entry in requests.items() if isinstance(entry, dict) and entry.get("by") != EVICT_REQUESTER}
    credits = 0
    sold = []
    for item_id in LAB_REAGENT_ITEM_IDS:
        if item_id in kept:
            continue
        units, earned = _stage_and_sell(home, shop, item_id)
        if units:
            credits += earned
            sold.append(f"{units} {item_id}")
    if sold:
        log.print(f"No Bio Lab anywhere: sold stranded reagents {', '.join(sold)} for {credits} cr.")
    return credits


def _stage_and_sell(home, shop, item_id):
    """Moves home's Warehouse and Storage Bin stock of item_id to Inventory (up
    to storage.inventory_room()), then sells all Inventory holds. Returns
    (units sold, credits earned); (0, 0) when nothing sold."""
    for building in discover_storage_buildings(home):
        store = building["component"]
        try:
            units = min(int(store.count(item_id) or 0), inventory_room(item_id))
            if units > 0:
                store.transfer_to("inventory", item_id, units)
        except Exception as error:
            swallowed("site_evict._stage_and_sell: transfer_to inventory", error)
    units = inventory_count(item_id)
    if units <= 0:
        return 0, 0
    try:
        res = shop.sell(item_id, units)
    except Exception as error:
        swallowed("site_evict._stage_and_sell: shop.sell", error)
        return 0, 0
    if getattr(res, "status", "") != "ok":
        log.level("warn").print(f"sell('{item_id}', {units}) -> {getattr(res, 'status', '?')}: {getattr(res, 'message', '')}. Left in Inventory.")
        return 0, 0
    return units, getattr(res, "credits", 0) or 0


def lifeform_staging_sites(tick):
    """Outpost ids where a Drone Depot stages life forms: homes of fresh miner drones (fleet.status)."""
    return {entry.get("home") for entry in fleet_status.get_all().values() if isinstance(entry, dict) and entry.get("unit") and entry.get("role") == "miner" and entry.get("home") and is_fresh(entry, tick, STATUS_STALE_TICKS)}


def evict_room(outpost: "OutpostRef | None", item_id, requests, tick, home_id, store=False, staging=False):
    """Units of item_id evict_stranded() may still send to `outpost`: its
    storage slot room (storage.slot_room(): slots already holding the item,
    or its planned request target rounded up to whole slots, else one empty
    slot while EVICT_FREE_SLOTS_KEEP stay empty, EVICT_STAGING_SLOTS_KEEP at a
    life-form `staging` site; a storage outpost (`store`) is a dump and takes
    storage.open_room(): every slot to capacity, empty ones included) minus
    units already in flight there. None (no cap) for
    home: it is a destination only as a user, and its Inventory is managed by
    the storage sweep."""
    outpost_id = getattr(outpost, "id", None)
    if outpost_id == home_id:
        return None
    if outpost is None:
        return 0
    if store:
        room = open_room(item_id, slot_layout(outpost))
    else:
        entry = requests.get(outpost_id, {}).get(item_id)
        planned = request_target(entry) if isinstance(entry, dict) else 0
        room = slot_room(item_id, slot_layout(outpost), planned, EVICT_STAGING_SLOTS_KEEP if staging else EVICT_FREE_SLOTS_KEEP)
    return max(0, room - in_flight(outpost_id, tick).get(item_id, 0))
