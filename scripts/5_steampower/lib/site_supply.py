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
#     ingots > remote ore. In-flight units count on both sides, so a split
#     that flips after a hauler commits can't double-order (no hysteresis).
#   - Smelting site (>= 1 Smelter, not home): one ore request per ore it has
#     an unlocked Smelter recipe for. Buffer tier up to
#     outpost_mining.ore_stock_target(ore); need tier = local + in-flight ore
#     + the D - S ore shortfall above, 0 when no local Fabricator needs it.
#   - Home publishes ingot requests only, and only while free remote ingots
#     cover part of its D: its ore comes from the standing home ore floor
#     (production.get_raw_material_demands()), so with every machine at home
#     nothing is published.
# Removing a site's Smelters drops its ore request; leftover ore becomes free
# stock that pull haulers take wherever it is requested.

from logistics_requests import active_requests, set_requests, in_flight, outpost_stock, outpost_free_tiers, request_min, REQUEST_STALE_TICKS
from production import discover_smelter_ids, discover_fabricator_ids, get_fabricator_active_recipe, SourceCache
from storage import outpost_is_home
from outpost_mining import ore_stock_target, RAW_ORE_ITEM_IDS
from tree_console import TreeConsole
from swallow import swallowed

log = TreeConsole(module="site_supply")

SITE_SUPPLY_REQUESTER = "site_supply"

# An unchanged request is republished once it is this old, well inside
# logistics_requests.REQUEST_STALE_TICKS, instead of every pass (one archive
# write per site per storage tick otherwise).
REPUBLISH_TICKS = REQUEST_STALE_TICKS // 2


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


def fab_site_gross_need(fabricator_ids, smelter_outputs, cache):
    """{smelter_output: units} the Fabricators' active recipes still need
    staged: inputs x crafts_remaining (their split share) - stockpile."""
    need = {}
    for fabricator_id in fabricator_ids:
        fabricator = _component(fabricator_id)
        if not fabricator:
            continue
        recipe, crafts_remaining = get_fabricator_active_recipe(fabricator, cache)
        if not recipe or crafts_remaining <= 0:
            continue
        try:
            stockpile = fabricator.get_stockpile() or {}
        except Exception as error:
            swallowed("site_supply.fab_site_gross_need: fabricator.get_stockpile", error)
            stockpile = {}
        for item_id, per_craft in (getattr(recipe, "inputs", {}) or {}).items():
            if item_id not in smelter_outputs:
                continue
            missing = per_craft * crafts_remaining - stockpile.get(item_id, 0)
            if missing > 0:
                need[item_id] = need.get(item_id, 0) + missing
    return need


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


def plan_site(outpost, outposts, requests, cache, tick):
    """{item_id: (target, have, min)} this outpost should request, {} when it
    has no Smelter/Fabricator (or needs nothing). See the module comment."""
    smelter_ids = discover_smelter_ids(outpost)
    fabricator_ids = discover_fabricator_ids(outpost)
    if not smelter_ids and not fabricator_ids:
        return {}
    site_id = getattr(outpost, "id", None)
    at_home = outpost_is_home(outpost)
    ore_outputs = site_ore_outputs(smelter_ids)
    ore_for = {output: ore for ore, output in ore_outputs.items()}
    smelter_outputs = {getattr(r, "output_item", None) for r in cache.smelter_recipes()} - {None}

    gross = fab_site_gross_need(fabricator_ids, smelter_outputs, cache)
    item_ids = sorted(set(gross) | set(ore_outputs) | {ore_for[i] for i in gross if i in ore_for})
    have = outpost_stock(item_ids, outpost)
    flying = in_flight(site_id, tick)
    spare = free_elsewhere(sorted(gross), site_id, outposts, requests, tick)

    wants = {}
    ore_short = {}
    for ingot, units in sorted(gross.items()):
        ore = ore_for.get(ingot)
        local_ingots = have.get(ingot, 0) + flying.get(ingot, 0)
        local_ore = (have.get(ore, 0) + flying.get(ore, 0)) if ore else 0
        deficit = max(0, units - local_ingots - local_ore)
        remote_ingots = min(deficit, spare.get(ingot, 0)) if ore else deficit
        if ore:
            ore_short[ore] = ore_short.get(ore, 0) + deficit - remote_ingots
        level = local_ingots + remote_ingots
        if not at_home or remote_ingots > 0:
            wants[ingot] = (level, have.get(ingot, 0), level)
        log.debug(f"plan_site({site_id}): {ingot} gross={units} local_ingots={local_ingots} local_ore={local_ore} -> D={deficit}, free elsewhere={spare.get(ingot, 0)}, ingots from remote={remote_ingots}, ore short={deficit - remote_ingots if ore else 0}")

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


def publish_site_requests(curr_tick):
    """Plans and publishes every outpost's site requests (withdrawing them
    where nothing is needed any more). Returns {outpost_id: wants}."""
    outposts = _outposts()
    requests = active_requests(curr_tick)
    cache = SourceCache()
    published = {}
    for outpost in outposts:
        site_id = getattr(outpost, "id", None)
        if site_id is None:
            continue
        wants = plan_site(outpost, outposts, requests, cache, curr_tick)
        existing = {i: e for i, e in requests.get(site_id, {}).items() if e.get("by") == SITE_SUPPLY_REQUESTER}
        if not wants and not existing:
            continue
        if _unchanged(existing, wants, curr_tick):
            published[site_id] = wants
            continue
        set_requests(site_id, SITE_SUPPLY_REQUESTER, wants, curr_tick)
        published[site_id] = wants
        if wants:
            log.print(f"Site supply at '{site_id}': {', '.join(f'{i} {t}' for i, (t, _h, _m) in sorted(wants.items()))}.")
        else:
            log.print(f"Site supply at '{site_id}': withdrawn (no Smelter/Fabricator demand).")
    return published
