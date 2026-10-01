# Site supply requests for factory outposts: every outpost with Smelters or
# Fabricators publishes what its machines need hauled in, as pull-logistics
# requests (lib/logistics_requests.py, requester SITE_SUPPLY_REQUESTER). Pull
# haulers homed at that outpost (lib/vehicle_cargo.py run_pull_loop()) serve
# them. Run once per storage tick by the headless control_room_automation.py.
#
# Outpost roles come from the buildings deployed there, never a setting:
#   - Fab site (>= 1 Fabricator): ingot deficit D per Smelter output =
#     what its Fabricators' active recipes still need (inputs x
#     crafts_remaining - stockpile) minus local ingots, local ore a local
#     Smelter can refine (1:1, every Smelter recipe is 1 ore -> 1 unit) and
#     in-flight ingots *and* ore. S = free ingots at every other outpost
#     (outpost_free_tiers() need tier). Ingot request for min(D, S), the rest
#     D - S as an ore request -- or all of D as ingots when no local Smelter
#     can refine that ore. Preference: local ingots > local ore > remote
#     ingots > remote ore, except remote ingots go ahead of local ore when
#     production.ship_units() says ship (slow local smelt or big surplus).
#     In-flight units count on both sides, so a split that flips after a
#     hauler commits can't double-order (no hysteresis).
#     Its ship plan (production.get_site_ship_plan(): intermediates spare
#     elsewhere that it hauls in instead of building) is requested too,
#     level = local + in flight + to ship, kept while units are in flight.
#   - Smelting site (>= 1 Smelter, not home): one ore request per ore it has
#     an unlocked Smelter recipe for. Buffer tier up to
#     outpost_mining.ore_stock_target(ore); need tier = local + in-flight ore
#     + the D - S ore shortfall above, 0 when no local Fabricator needs it.
#   - Home publishes ingot requests only, and only while free remote ingots
#     cover part of its D: its ore comes from the standing home ore floor
#     (production.get_raw_material_demands()), so with every machine at home
#     nothing is published.
#   - Consumer site: finished root targets (production.fabricator_root_targets()
#     consumers: a Supply Dock order at the dock's outpost, everything else at
#     home) are pulled in from the other supply sites (outposts with a Smelter
#     or Fabricator) that built them: request local + in-flight + min(short,
#     free there), kept while units are in flight. With every Fabricator at
#     home there is nothing to pull, so nothing is published.
#
# Role switch drain: removing a site's Smelters drops its ore request, so its
# leftover ore becomes free stock that pull haulers take wherever it is
# requested. Ore that still sits at an outpost with no Smelter (home
# included), that the outpost does not mine (outpost_mining.assigned_ores_for()),
# request or consume (a Supply Dock order there), for EVICT_AFTER_TICKS
# (first seen in STRANDED_KEY) is evicted to evict_destination(): home when a
# home Smelter refines it (home requests it, requester EVICT_REQUESTER), else
# the first smelting site by id that does (its site-supply ore target is
# raised by that ore), else home. Requested until it is gone.
#
# Stranded goods: ingots and intermediates (item_catalog category in
# EVICT_GOODS_CATEGORIES) that some Fabricator recipe takes as input are
# evicted the same way from an outpost with no Fabricator (home included)
# that neither requests nor consumes them, to goods_destination(): home when
# home has a Fabricator, else the first fab site by id. Deployables stay put:
# construction kits are another category, storage.must_stay_in_inventory()
# items (the Warehouse sweep's Inventory-only list) are skipped, and so are
# CONSTRUCTION_ITEM_IDS (what a Pioneer's Constructor loads at home) and
# EVICT_HOLD_ITEM_IDS.

from archive import archive
from logistics_requests import active_requests, set_requests, in_flight, outpost_stock, outpost_free_tiers, request_min, local_depots, depot_stock, REQUEST_STALE_TICKS
from production import discover_smelter_ids, discover_fabricator_ids, smelter_ores, fab_site_gross_need, fabricator_root_targets, get_site_ship_plan, ship_units, SourceCache
from storage import outpost_is_home, discover_storage_buildings, must_stay_in_inventory
from outpost_mining import ore_stock_target, assigned_ores_for, RAW_ORE_ITEM_IDS
from tree_console import TreeConsole
from swallow import swallowed

log = TreeConsole(module="site_supply")

SITE_SUPPLY_REQUESTER = "site_supply"

# An unchanged request is republished once it is this old, well inside
# logistics_requests.REQUEST_STALE_TICKS, instead of every pass (one archive
# write per site per storage tick otherwise).
REPUBLISH_TICKS = REQUEST_STALE_TICKS // 2

# Role switch drain: {outpost_id: {ore: first tick seen stranded}}, pruned to
# what is stranded now.
STRANDED_KEY = "site_supply.stranded"
EVICT_REQUESTER = "site_evict"
# How long ore or goods sit stranded before they are evicted.
EVICT_AFTER_TICKS = REQUEST_STALE_TICKS
# item_catalog categories of stranded goods: ingots and intermediates.
EVICT_GOODS_CATEGORIES = ("refined", "crafted")
# Constructor materials (docs/components/constructor_module.md): a Pioneer
# loads them at home for pipe/power line jobs, so they stay there like kits.
CONSTRUCTION_ITEM_IDS = (
    "gas_pipe_segment", "liquid_pipe_segment", "power_line_segment",
    "gas_pipe_bridge", "liquid_pipe_bridge", "power_line_bridge",
)
# Goods never evicted although a Fabricator recipe takes them: tar is also the
# Refiner's reagent (docs/database/recipes_refiner.md), and where the Refiner
# will stand is open, so tar stays where it is until a Refiner requests it.
EVICT_HOLD_ITEM_IDS = ("tar",)


def _component(component_id):
    try:
        return get_component(component_id)
    except Exception as error:
        swallowed("site_supply._component: get_component", error)
        return None


def _outposts():
    network = _component("outpost_network")
    if not network or not hasattr(network, "outposts"):
        return []
    try:
        return list(network.outposts())
    except Exception as error:
        swallowed("site_supply._outposts: network.outposts", error)
        return []


def free_elsewhere(item_ids, site_id, outposts, requests, tick):
    """{item_id: units} free for another outpost's need at every outpost but site_id."""
    totals = {}
    if not item_ids:
        return totals
    for outpost in outposts:
        if getattr(outpost, "id", None) == site_id:
            continue
        for_need, _for_buffer = outpost_free_tiers(outpost, item_ids, requests, tick)
        for item_id, units in for_need.items():
            totals[item_id] = totals.get(item_id, 0) + units
    return totals


def consumer_wants(outpost, consumers, sources, requests, tick, flying):
    """{root_item: (target, have, min)} finished root targets consumed at
    this outpost that it pulls in from the other supply sites. See the
    module comment."""
    site_id = getattr(outpost, "id", None)
    item_ids = sorted(i for i, sites in consumers.items() if (sites or {}).get(site_id, 0) > 0)
    others = [o for o in sources if getattr(o, "id", None) != site_id]
    if not item_ids or not others:
        return {}
    have = outpost_stock(item_ids, outpost)
    spare = free_elsewhere(item_ids, site_id, others, requests, tick)
    wants = {}
    for item_id in item_ids:
        local = have.get(item_id, 0) + flying.get(item_id, 0)
        short = max(0, consumers[item_id][site_id] - local)
        pull = min(short, spare.get(item_id, 0))
        if pull > 0 or flying.get(item_id, 0) > 0:
            wants[item_id] = (local + pull, have.get(item_id, 0), local + pull)
            log.debug(f"consumer_wants({site_id}): {item_id} consumed={consumers[item_id][site_id]} local={local} free at other sites={spare.get(item_id, 0)} -> pull {pull}")
    return wants


def ship_wants(outpost, requests, cache, flying, smelter_outputs, wants):
    """Adds this fab site's ship plan (production.get_site_ship_plan():
    intermediates spare elsewhere it hauls in instead of building) to wants,
    level = local + in flight + to ship, all need tier. An item this
    requester already asked for stays requested while units are in flight."""
    site_id = getattr(outpost, "id", None)
    plan = get_site_ship_plan(site_id, cache)
    own = requests.get(site_id, {})
    kept = {i for i, e in own.items() if e.get("by") == SITE_SUPPLY_REQUESTER and flying.get(i, 0) > 0}
    kept = {i for i in kept if i not in smelter_outputs and i not in RAW_ORE_ITEM_IDS}
    item_ids = sorted(set(plan) | kept)
    if not item_ids:
        return
    have = outpost_stock(item_ids, outpost)
    for item_id in item_ids:
        level = have.get(item_id, 0) + flying.get(item_id, 0) + plan.get(item_id, 0)
        if level > 0 and level >= wants.get(item_id, (0,))[0]:
            wants[item_id] = (level, have.get(item_id, 0), level)
        log.debug(f"ship_wants({site_id}): {item_id} local={have.get(item_id, 0)} in_flight={flying.get(item_id, 0)} ship={plan.get(item_id, 0)} -> level {level}")


def plan_site(outpost, outposts, requests, cache, tick, consumers=None, sources=None):
    """{item_id: (target, have, min)} this outpost should request, {} when it
    has no Smelter/Fabricator and consumes no root built elsewhere (or needs
    nothing). See the module comment."""
    log.start("plan_site", level="debug")
    site_id = getattr(outpost, "id", None)
    flying = in_flight(site_id, tick)
    wants = consumer_wants(outpost, consumers or {}, sources or [], requests, tick, flying)
    smelter_ids = discover_smelter_ids(outpost)
    fabricator_ids = discover_fabricator_ids(outpost)
    if not smelter_ids and not fabricator_ids:
        log.end()
        return wants
    at_home = outpost_is_home(outpost)
    ore_outputs = smelter_ores(outpost)
    ore_for = {output: ore for ore, output in ore_outputs.items()}
    smelter_outputs = {getattr(r, "output_item", None) for r in cache.smelter_recipes()} - {None}

    if fabricator_ids:
        ship_wants(outpost, requests, cache, flying, smelter_outputs, wants)

    gross = fab_site_gross_need(fabricator_ids, smelter_outputs, cache)
    item_ids = sorted(set(gross) | set(ore_outputs) | {ore_for[i] for i in gross if i in ore_for})
    have = outpost_stock(item_ids, outpost)
    spare = free_elsewhere(sorted(gross), site_id, outposts, requests, tick)

    ore_short = {}
    for ingot, units in sorted(gross.items()):
        ore = ore_for.get(ingot)
        local_ingots = have.get(ingot, 0) + flying.get(ingot, 0)
        local_ore = (have.get(ore, 0) + flying.get(ore, 0)) if ore else 0
        short = max(0, units - local_ingots)
        free = spare.get(ingot, 0)
        # Ship-before-craft: remote ingots ahead of local ore when smelting
        # them here is slow or the spare is a big surplus (ship_units()).
        first = 0
        if ore and short > 0 and free > 0 and ship_units(ingot, short, outpost, site_id, cache) > 0:
            first = min(short, free)
        deficit = max(0, short - first - local_ore)
        remote_ingots = first + (min(deficit, free - first) if ore else deficit)
        if ore:
            ore_short[ore] = ore_short.get(ore, 0) + deficit - (remote_ingots - first)
        level = local_ingots + remote_ingots
        if (not at_home or remote_ingots > 0) and level >= wants.get(ingot, (0,))[0]:
            wants[ingot] = (level, have.get(ingot, 0), level)
        log.debug(f"{ingot} gross={units} local_ingots={local_ingots} local_ore={local_ore} -> shipped first={first}, D={deficit}, free elsewhere={free}, ingots from remote={remote_ingots}, ore short={deficit - (remote_ingots - first) if ore else 0}")

    if not at_home:
        for ore, output in sorted(ore_outputs.items()):
            local = have.get(ore, 0) + flying.get(ore, 0)
            floor = local + ore_short.get(ore, 0) if output in gross else 0
            target = max(ore_stock_target(ore), floor)
            wants[ore] = (target, have.get(ore, 0), floor)
            log.debug(f"ore {ore} local={local} need level={floor} target={target}")
    log.end()
    return wants


def _unchanged(existing, wants, tick):
    """True when the published entries match wants and are young enough to skip a republish."""
    if set(existing) != set(wants):
        return False
    for item_id, (target, _have, floor) in wants.items():
        entry = existing[item_id]
        if entry.get("target") != target or request_min(entry) != min(floor, target):
            return False
        if tick - entry.get("tick", 0) >= REPUBLISH_TICKS:
            return False
    return True


def _publish(site_id, requester, wants, requests, tick):
    """set_requests() unless the published entries already match; True when written."""
    existing = {i: e for i, e in requests.get(site_id, {}).items() if e.get("by") == requester}
    if (not wants and not existing) or _unchanged(existing, wants, tick):
        log.trace(f"_publish({site_id}, {requester}): unchanged, {len(wants)} item(s)")
        return False
    set_requests(site_id, requester, wants, tick)
    return True


def planned_requests(requests, planned, tick):
    """requests with each site's SITE_SUPPLY_REQUESTER entries replaced by
    this pass's plan ({site_id: wants}), as set_requests() would write them."""
    result = {}
    for site_id, items in requests.items():
        kept = {i: e for i, e in items.items() if e.get("by") != SITE_SUPPLY_REQUESTER}
        if kept:
            result[site_id] = kept
    for site_id, wants in planned.items():
        if not wants:
            continue
        bucket = result.setdefault(site_id, {})
        for item_id, (target, have, floor) in wants.items():
            entry = {"target": target, "have": have, "by": SITE_SUPPLY_REQUESTER, "tick": tick}
            if floor is not None and floor < target:
                entry["min"] = max(0, floor)
            bucket[item_id] = entry
    return result


def smelting_sites(outposts):
    """{site_id: set of ores its Smelters refine} for every outpost with a Smelter."""
    return {getattr(o, "id", None): set(smelter_ores(o)) for o in outposts if discover_smelter_ids(o)}


def evict_destination(ore, source_id, home_id, smelt_ores):
    """Outpost stranded ore goes to: home when a home Smelter refines it,
    else the first other smelting site (by id) that does, else home.
    smelt_ores = smelting_sites()."""
    if ore in smelt_ores.get(home_id, ()):
        return home_id
    for site_id in sorted(smelt_ores):
        if site_id != source_id and ore in smelt_ores[site_id]:
            return site_id
    return home_id


def stranded_ore(outposts, requests, home_id, smelt_ores, consumers=None):
    """{outpost_id: {ore: units}} ore at an outpost with no Smelter that the
    outpost neither mines, requests nor consumes (a Supply Dock order
    there), and that has somewhere else to go (evict_destination())."""
    consumers = consumers or {}
    result = {}
    for outpost in outposts:
        site_id = getattr(outpost, "id", None)
        if site_id is None or site_id in smelt_ores:
            continue
        kept = set(assigned_ores_for(site_id)) | set(requests.get(site_id, {}))
        kept |= {o for o in RAW_ORE_ITEM_IDS if (consumers.get(o) or {}).get(site_id, 0) > 0}
        ores = sorted(o for o in RAW_ORE_ITEM_IDS if o not in kept and evict_destination(o, site_id, home_id, smelt_ores) != site_id)
        held = {ore: units for ore, units in outpost_stock(ores, outpost).items() if units > 0}
        if held:
            result[site_id] = held
    return result


def fab_sites(outposts):
    """Sorted ids of every outpost with a Fabricator."""
    return sorted(getattr(o, "id", None) for o in outposts if getattr(o, "id", None) is not None and discover_fabricator_ids(o))


def goods_destination(source_id, home_id, fab_ids):
    """Outpost stranded goods go to: home when home has a Fabricator, else
    the first other fab site by id; None when there is none."""
    if home_id in fab_ids:
        return home_id
    for site_id in fab_ids:
        if site_id != source_id:
            return site_id
    return None


def _category(catalog, item_id):
    try:
        info = catalog.lookup(item_id)
    except Exception as error:
        swallowed("site_supply._category: catalog.lookup", error)
        return None
    return getattr(info, "category", None) if info else None


def evictable_goods(cache):
    """Item ids that may be evicted as stranded goods: Fabricator recipe
    inputs in EVICT_GOODS_CATEGORIES, minus storage.must_stay_in_inventory(),
    Constructor items and EVICT_HOLD_ITEM_IDS. Empty without an item_catalog."""
    catalog = _component("item_catalog")
    if not catalog or not hasattr(catalog, "lookup"):
        return set()
    inputs = set()
    for recipe in cache.fabricator_recipes():
        inputs |= set(getattr(recipe, "inputs", {}) or {})
    skip = set(CONSTRUCTION_ITEM_IDS) | set(EVICT_HOLD_ITEM_IDS)
    candidates = {i for i in inputs if i not in skip and _category(catalog, i) in EVICT_GOODS_CATEGORIES}
    return {i for i in candidates if not must_stay_in_inventory(i)}


def held_item_ids(outpost):
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


def stranded_goods(outposts, requests, home_id, fab_ids, goods, consumers=None):
    """{outpost_id: {item_id: units}} evictable goods (evictable_goods()) at
    an outpost with no Fabricator that it neither requests nor consumes,
    when some fab site can take them (goods_destination())."""
    consumers = consumers or {}
    result = {}
    if not goods:
        return result
    for outpost in outposts:
        site_id = getattr(outpost, "id", None)
        if site_id is None or site_id in fab_ids or goods_destination(site_id, home_id, fab_ids) is None:
            continue
        kept = set(requests.get(site_id, {}))
        items = sorted(i for i in held_item_ids(outpost) & goods if i not in kept and (consumers.get(i) or {}).get(site_id, 0) <= 0)
        held = {item_id: units for item_id, units in outpost_stock(items, outpost).items() if units > 0}
        if held:
            result[site_id] = held
    return result


def evict_stranded(outposts, requests, tick, consumers=None, smelt_ores=None, goods=None):
    """Tracks stranded ore and goods (STRANDED_KEY), publishes home's evict
    request for what sat there EVICT_AFTER_TICKS and is headed home, and
    returns (that request's wants, {site_id: {item_id: units}} free stranded
    units headed to each other site). goods = evictable_goods() (none when
    omitted)."""
    home = next((o for o in outposts if outpost_is_home(o)), None)
    home_id = getattr(home, "id", None)
    if smelt_ores is None:
        smelt_ores = smelting_sites(outposts)
    fab_ids = fab_sites(outposts)

    def destination(item_id, source_id):
        if item_id in RAW_ORE_ITEM_IDS:
            return evict_destination(item_id, source_id, home_id, smelt_ores)
        return goods_destination(source_id, home_id, fab_ids)

    stranded = stranded_ore(outposts, requests, home_id, smelt_ores, consumers)
    for site_id, held in stranded_goods(outposts, requests, home_id, fab_ids, goods or set(), consumers).items():
        stranded.setdefault(site_id, {}).update(held)
    stored = archive.get(STRANDED_KEY, {})
    stored = stored if isinstance(stored, dict) else {}
    seen = {}
    for site_id, held in stranded.items():
        previous = stored.get(site_id)
        previous = previous if isinstance(previous, dict) else {}
        seen[site_id] = {item_id: previous.get(item_id, tick) for item_id in held}
    if seen != stored:
        archive.set(STRANDED_KEY, seen)

    if home is None or home_id is None:
        return {}, {}
    by_id = {getattr(o, "id", None): o for o in outposts}
    ripe = {}
    for site_id, first_seen in seen.items():
        for item_id, first_tick in first_seen.items():
            if tick - first_tick >= EVICT_AFTER_TICKS:
                ripe.setdefault(item_id, []).append(site_id)
    free = {}
    for site_id in sorted({s for sites in ripe.values() for s in sites}):
        items = [item_id for item_id in sorted(ripe) if site_id in ripe[item_id]]
        for_need, _for_buffer = outpost_free_tiers(by_id[site_id], items, requests, tick)
        for item_id, units in for_need.items():
            dest = destination(item_id, site_id)
            bucket = free.setdefault(dest, {})
            bucket[item_id] = bucket.get(item_id, 0) + units
            log.debug(f"evict_stranded: {units} {item_id} stranded at {site_id} -> {dest}")

    home_requests = requests.get(home_id, {})
    home_free = free.get(home_id, {})
    items = sorted(i for i in ripe if destination(i, None) == home_id and home_requests.get(i, {}).get("by", EVICT_REQUESTER) == EVICT_REQUESTER)
    wants = {}
    if items:
        have = outpost_stock(items, home)
        flying = in_flight(home_id, tick)
        for item_id in items:
            if home_free.get(item_id, 0) > 0 or flying.get(item_id, 0) > 0:
                level = have.get(item_id, 0) + flying.get(item_id, 0) + home_free.get(item_id, 0)
                wants[item_id] = (level, have.get(item_id, 0), level)
                log.debug(f"evict_stranded: {item_id} stranded at {sorted(ripe[item_id])}, free={home_free.get(item_id, 0)} in flight={flying.get(item_id, 0)} -> home level {level}")
    if _publish(home_id, EVICT_REQUESTER, wants, requests, tick):
        if wants:
            described = ", ".join(item_id + " from " + "/".join(sorted(ripe[item_id])) for item_id in sorted(wants))
            log.print(f"Evicting stranded stock to home: {described}.")
        else:
            log.print("Stranded stock evicted.")
    return wants, {site_id: extra for site_id, extra in free.items() if site_id != home_id}


def add_evicted(outpost, wants, extra, tick):
    """Raises this site's request targets by the stranded ore or goods
    headed here (buffer tier: need level unchanged)."""
    site_id = getattr(outpost, "id", None)
    items = sorted(extra)
    have = outpost_stock(items, outpost)
    flying = in_flight(site_id, tick)
    for item_id in items:
        target, _have, floor = wants.get(item_id, (0, 0, 0))
        level = have.get(item_id, 0) + flying.get(item_id, 0) + extra[item_id]
        if level > target:
            wants[item_id] = (level, have.get(item_id, 0), floor)
            log.debug(f"add_evicted({site_id}): {item_id} +{extra[item_id]} stranded -> target {level} (need level {floor})")


def publish_site_requests(curr_tick):
    """Plans and publishes every outpost's site requests (withdrawing them
    where nothing is needed any more, raised by stranded ore or goods headed
    to that site) and home's evict request. Returns
    {outpost_id: wants}."""
    outposts = _outposts()
    requests = active_requests(curr_tick)
    cache = SourceCache()
    _roots, consumers, _outputs = fabricator_root_targets(cache)
    sources = [o for o in outposts if discover_smelter_ids(o) or discover_fabricator_ids(o)]
    planned = {}
    for outpost in outposts:
        site_id = getattr(outpost, "id", None)
        if site_id is not None:
            planned[site_id] = plan_site(outpost, outposts, requests, cache, curr_tick, consumers, sources)
    # Stranded check against this pass's plan: a site that just lost its
    # Smelters frees its ore for eviction right away.
    _home_wants, evicted = evict_stranded(outposts, planned_requests(requests, planned, curr_tick), curr_tick, consumers, smelting_sites(outposts), evictable_goods(cache))
    published = {}
    notes = []
    for outpost in outposts:
        site_id = getattr(outpost, "id", None)
        if site_id is None:
            continue
        wants = planned[site_id]
        if evicted.get(site_id):
            add_evicted(outpost, wants, evicted[site_id], curr_tick)
        if wants or any(e.get("by") == SITE_SUPPLY_REQUESTER for e in requests.get(site_id, {}).values()):
            published[site_id] = wants
        if not _publish(site_id, SITE_SUPPLY_REQUESTER, wants, requests, curr_tick):
            continue
        if wants:
            notes.append(f"Site supply at '{site_id}': {', '.join(f'{i} {t}' for i, (t, _h, _m) in sorted(wants.items()))}.")
        else:
            notes.append(f"Site supply at '{site_id}': withdrawn (no Smelter/Fabricator demand).")
    if notes:
        log.start(f"Publishing site supply requests ({len(notes)} site(s) changed)")
        for note in notes:
            log.print(note)
        log.end(f"Published {len(notes)} site supply update(s)")
    return published
