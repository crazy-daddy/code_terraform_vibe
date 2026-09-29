# Site supply requests for factory outposts: every outpost with Smelters or
# Fabricators publishes what its machines need hauled in, as pull-logistics
# requests (lib/logistics_requests.py, requester SITE_SUPPLY_REQUESTER). Pull
# haulers homed at that outpost (lib/vehicle_cargo.py run_pull_loop()) serve
# them. Run once per storage tick by the headless automation_panel.py.
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
# requested. Ore that still sits at a non-home outpost with no Smelter, that
# the outpost does not mine (outpost_mining.assigned_ores_for()) and does not
# request, for EVICT_AFTER_TICKS (first seen in STRANDED_KEY) is evicted: home
# requests it (requester EVICT_REQUESTER) until it is gone.

from archive import archive
from logistics_requests import active_requests, set_requests, in_flight, outpost_stock, outpost_free_tiers, request_min, REQUEST_STALE_TICKS
from production import discover_smelter_ids, discover_fabricator_ids, fab_site_gross_need, fabricator_root_targets, get_site_ship_plan, ship_units, SourceCache
from storage import outpost_is_home
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
# How long ore sits stranded before home requests it.
EVICT_AFTER_TICKS = REQUEST_STALE_TICKS


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


def site_ore_outputs(smelter_ids):
    """{ore: output_item} for every raw ore one of these Smelters has an
    unlocked recipe for (list_recipes() is tech-gated, identical per Smelter,
    so the first one that answers stands in for all)."""
    for smelter_id in smelter_ids:
        smelter = _component(smelter_id)
        if not smelter or not hasattr(smelter, "list_recipes"):
            continue
        try:
            recipes = list(smelter.list_recipes())
        except Exception as error:
            swallowed("site_supply.site_ore_outputs: smelter.list_recipes", error)
            continue
        result = {}
        for recipe in recipes:
            output_item = getattr(recipe, "output_item", None)
            for ore in (getattr(recipe, "inputs", {}) or {}):
                if ore in RAW_ORE_ITEM_IDS and output_item:
                    result[ore] = output_item
        return result
    return {}


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
    site_id = getattr(outpost, "id", None)
    flying = in_flight(site_id, tick)
    wants = consumer_wants(outpost, consumers or {}, sources or [], requests, tick, flying)
    smelter_ids = discover_smelter_ids(outpost)
    fabricator_ids = discover_fabricator_ids(outpost)
    if not smelter_ids and not fabricator_ids:
        return wants
    at_home = outpost_is_home(outpost)
    ore_outputs = site_ore_outputs(smelter_ids)
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
        log.debug(f"plan_site({site_id}): {ingot} gross={units} local_ingots={local_ingots} local_ore={local_ore} -> shipped first={first}, D={deficit}, free elsewhere={free}, ingots from remote={remote_ingots}, ore short={deficit - (remote_ingots - first) if ore else 0}")

    if not at_home:
        for ore, output in sorted(ore_outputs.items()):
            local = have.get(ore, 0) + flying.get(ore, 0)
            floor = local + ore_short.get(ore, 0) if output in gross else 0
            target = max(ore_stock_target(ore), floor)
            wants[ore] = (target, have.get(ore, 0), floor)
            log.debug(f"plan_site({site_id}): ore {ore} local={local} need level={floor} target={target}")
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
        return False
    set_requests(site_id, requester, wants, tick)
    return True


def stranded_ore(outposts, requests):
    """{outpost_id: {ore: units}} ore at a non-home outpost with no Smelter
    that the outpost neither mines nor requests."""
    result = {}
    for outpost in outposts:
        site_id = getattr(outpost, "id", None)
        if site_id is None or outpost_is_home(outpost) or discover_smelter_ids(outpost):
            continue
        kept = set(assigned_ores_for(site_id)) | set(requests.get(site_id, {}))
        ores = sorted(o for o in RAW_ORE_ITEM_IDS if o not in kept)
        held = {ore: units for ore, units in outpost_stock(ores, outpost).items() if units > 0}
        if held:
            result[site_id] = held
    return result


def evict_stranded(outposts, requests, tick):
    """Tracks stranded ore (STRANDED_KEY) and publishes home's evict request
    for what sat there EVICT_AFTER_TICKS. Returns that request's wants."""
    stranded = stranded_ore(outposts, requests)
    stored = archive.get(STRANDED_KEY, {})
    stored = stored if isinstance(stored, dict) else {}
    seen = {}
    for site_id, held in stranded.items():
        previous = stored.get(site_id)
        previous = previous if isinstance(previous, dict) else {}
        seen[site_id] = {ore: previous.get(ore, tick) for ore in held}
    if seen != stored:
        archive.set(STRANDED_KEY, seen)

    home = next((o for o in outposts if outpost_is_home(o)), None)
    home_id = getattr(home, "id", None)
    if home is None or home_id is None:
        return {}
    ripe = {}
    for site_id, first_seen in seen.items():
        for ore, first_tick in first_seen.items():
            if tick - first_tick >= EVICT_AFTER_TICKS:
                ripe.setdefault(ore, []).append(site_id)
    home_requests = requests.get(home_id, {})
    ores = sorted(o for o in ripe if home_requests.get(o, {}).get("by", EVICT_REQUESTER) == EVICT_REQUESTER)
    wants = {}
    if ores:
        have = outpost_stock(ores, home)
        flying = in_flight(home_id, tick)
        sources = [o for o in outposts if getattr(o, "id", None) in {s for ore in ores for s in ripe[ore]}]
        free = {}
        for outpost in sources:
            for_need, _for_buffer = outpost_free_tiers(outpost, [ore for ore in ores if getattr(outpost, "id", None) in ripe[ore]], requests, tick)
            for ore, units in for_need.items():
                free[ore] = free.get(ore, 0) + units
        for ore in ores:
            if free.get(ore, 0) > 0 or flying.get(ore, 0) > 0:
                level = have.get(ore, 0) + flying.get(ore, 0) + free.get(ore, 0)
                wants[ore] = (level, have.get(ore, 0), level)
                log.debug(f"evict_stranded: {ore} stranded at {sorted(ripe[ore])}, free={free.get(ore, 0)} in flight={flying.get(ore, 0)} -> home level {level}")
    if _publish(home_id, EVICT_REQUESTER, wants, requests, tick):
        if wants:
            described = ", ".join(ore + " from " + "/".join(sorted(ripe[ore])) for ore in sorted(wants))
            log.print(f"Evicting stranded ore to home: {described}.")
        else:
            log.print("Stranded ore evicted.")
    return wants


def publish_site_requests(curr_tick):
    """Plans and publishes every outpost's site requests (withdrawing them
    where nothing is needed any more) and home's stranded-ore evict request.
    Returns {outpost_id: wants}."""
    outposts = _outposts()
    requests = active_requests(curr_tick)
    cache = SourceCache()
    _roots, consumers, _outputs = fabricator_root_targets(cache)
    sources = [o for o in outposts if discover_smelter_ids(o) or discover_fabricator_ids(o)]
    published = {}
    for outpost in outposts:
        site_id = getattr(outpost, "id", None)
        if site_id is None:
            continue
        wants = plan_site(outpost, outposts, requests, cache, curr_tick, consumers, sources)
        if wants or any(e.get("by") == SITE_SUPPLY_REQUESTER for e in requests.get(site_id, {}).values()):
            published[site_id] = wants
        if not _publish(site_id, SITE_SUPPLY_REQUESTER, wants, requests, curr_tick):
            continue
        if wants:
            log.print(f"Site supply at '{site_id}': {', '.join(f'{i} {t}' for i, (t, _h, _m) in sorted(wants.items()))}.")
        else:
            log.print(f"Site supply at '{site_id}': withdrawn (no Smelter/Fabricator demand).")
    # Re-read: this pass's withdrawals free ore for eviction right away.
    evict_stranded(outposts, active_requests(curr_tick), curr_tick)
    return published
