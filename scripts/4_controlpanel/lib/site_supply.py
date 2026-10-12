# Site supply requests for factory outposts: every outpost with Smelters or
# Fabricators publishes what its machines need hauled in, as pull-logistics
# requests (lib/logistics_requests.py, requester SITE_SUPPLY_REQUESTER). Pull
# haulers homed at that outpost (lib/job_pull.py PullJob) serve
# them. Run once per storage tick by the headless orchestrator_automation.py.
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
#     Raw inputs (no Smelter or Fabricator makes them, e.g. Forage) its
#     Fabricators still need staged are requested the same way, need tier:
#     local + in flight + min(short, free at other outposts).
#     Ingot buffer (production.fab_site_ingot_targets()): every Smelter
#     output a Fabricator recipe takes is requested up to its buffer target,
#     need level at least its need tier, always published so other sites'
#     haulers leave the buffer alone. Local Smelters refill it in idle time.
#   - Smelting site (>= 1 Smelter): one ore request per ore it has
#     an unlocked Smelter recipe for. Buffer tier up to
#     outpost_mining.ore_stock_target(ore); need tier = local + in-flight ore
#     + the D - S ore shortfall above, 0 when no local Fabricator needs it.
#   - Stockpiles (any outpost, home included): an outpost with a building
#     type in SITE_STOCK_TARGETS requests those items as buffer tier, need
#     tier = whatever else it planned for them (ship plan), while some are
#     free at another outpost or in flight. SITE_STOCK_CRAFTED items are also
#     ordered from the Fabricators as a backlog order (idle time only,
#     requester SITE_STOCK_REQUESTER), sized to the summed targets.
#   - Construction stock: the Constructor's home (production.construction_site_id())
#     also requests the archived CONSTRUCTION_STOCK_KEY items (pipe segments,
#     power line segments, gas/liquid bridges; target as buffer tier, need
#     level as need tier) and, per extractor kind, one kit per untapped
#     surveyed fluid site up to CONSTRUCTION_KIT_CAP
#     (construction_stock_targets(); exotic sites not once Wildlife is
#     complete, their caps are deconstructed), buffer tier like the stockpiles. The
#     same items, where a Fabricator can build them, are a backlog order
#     sized to the targets (requester CONSTRUCTION_STOCK_REQUESTER, idle time
#     only) and an upgrade order sized to the need levels (requester
#     CONSTRUCTION_STOCK_NEED_REQUESTER). So work that
#     waits for stock before it is planned (the infrastructure planner's
#     low-priority jobs) finds it, and blueprints start with material at hand.
#   - Home is planned like any other outpost; its only difference is the
#     Inventory, which outpost_stock() counts as home stock.
#   - Consumer site: finished root targets (production.fabricator_root_targets()
#     consumers: a Supply Dock order at the dock's outpost, a blueprint's
#     required_item at the Constructor's home, everything else at home) are
#     pulled in from every other outpost, as far as each holds them above
#     its own request's need level or "keep" (outpost_free_tiers() need
#     tier): request local + in-flight + min(short, free there), kept while
#     units are in flight. One PlanReads per pass reads each outpost once.
#     This is how a Supply Dock gets the order items its own
#     site role doesn't cover (lib/supply_dock.py DockRoles). Every want is
#     a priority ladder (lib/priority.py): a consumer want inherits its
#     root's prio (an order's score, a blueprint's band, a fleet part's
#     UPGRADE), a buffer is STOCK, a need level NEED. A part of band UPGRADE
#     or above that no Fabricator will add more of (settled_items()) and
#     manual-order units built off home (production.manual_transit_wants())
#     are lifted to BLOCKER: haulers skip their minimum load for them, since
#     waiting brings no fuller load and a job waits on them. Lower bands
#     (Terraformer Fertilizer, Yield Amplifier doses, stock) wait for a load.
#   - Dock ore: a Supply Dock order for a Smelter output (iron ingots) with
#     too few units anywhere is no ore request (consumer_wants() only pulls
#     existing units). dock_ore_levels() names the missing units as ore at
#     one smelting site that has the ore assigned, at the order's prio, and
#     plan_site() folds them into that site's ore want; raw ore an order owes
#     itself goes to one site with the ore assigned, the owing dock's site
#     first. Its stationed miners rank that ore by its band
#     (vehicle_mining.stockpile_need()) and haulers bring spare ore.
#   - Dock raw ore: raw ore a Supply Dock at this outpost still owes (e.g.
#     spire_intake_3's titanium) is requested at the order's prio, level =
#     owed (dock_raw_wants()), with or without a Smelter here. Pioneers
#     mining for their home rank it by band, once their drill cuts the ore
#     (vehicle_mining build_mineral_site_candidates()); haulers bring spare
#     units.
#
# Role switch drain: removing a site's Smelters drops its ore request, so its
# leftover ore becomes free stock that pull haulers take wherever it is
# requested. Ore that still sits at an outpost with no Smelter (home
# included), that the outpost does not mine (outpost_mining.assigned_ores_for()),
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
# stay empty (a storage outpost keeps none); what finds no room stays.
# Home as a user is not capped and requests the units itself (requester
# EVICT_REQUESTER); another destination's site-supply target is raised by
# them (add_evicted()). Requested until gone.

from geometry import distance
from archive import archive, STATUS_STALE_TICKS
from logistics_requests import PlanReads, active_requests, publish_requests, in_flight, outpost_stock, outpost_free_tiers, outpost_tier_free, local_depots, depot_stock, request_target, REQUEST_STALE_TICKS
from item_tiers import DEPOT_TYPE_TIERS
from production import get_site_fabricator_targets, set_order, order_levels, order_ladders, construction_site_id, discover_building_ids, discover_smelter_ids, discover_fabricator_ids, smelter_ores, fab_site_gross_need, fabricator_root_targets, blueprint_required_ladders, get_fabricator_pipeline, root_remaining, get_site_ship_plan, ship_units, SourceCache, manual_transit_wants, fab_site_ingot_targets, dock_remaining_requirements  # fmt: skip
from production_docks import dock_owed_prios
from storage import outpost_is_home, discover_storage_buildings, must_stay_in_inventory, INVENTORY_ONLY_ITEM_IDS, slot_layout, slot_room, inventory_count, inventory_room, PENALIZED_TYPES, STORAGE_TYPE_IDS, WAREHOUSE_STOCK_TARGET, STAGING_FREE_SLOTS_KEEP
from outpost_reagents import BIO_LAB_TYPE_ID, LAB_REAGENT_ITEM_IDS
from outpost_mining import ore_stock_target, assigned_ores_for, assigned_ores_by_outpost
from game_rules import RAW_ORE_ITEM_IDS
from construction_plan import EXTRACTOR_KITS
from priority import BLOCKER, NEED, NONE, STOCK, UPGRADE, band, ladder_deficits, ladder_level, ladder_promote, ladder_raise, ladder_total
from tree_console import TreeConsole
from components import component
from demand_publisher import PUBLISHER
from swallow import swallowed
from game_clock import is_fresh
import fleet_status
from wildlife_common import wildlife_complete
from drone_upgrade import upgrade_phase_reached

log = TreeConsole(module="site_supply")

SITE_SUPPLY_REQUESTER = "site_supply"

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
# Standing stockpiles, buffer tier: {building type: {item: target}} at every
# outpost with that building (a full item is one Warehouse slot, WAREHOUSE_STOCK_TARGET).
# A Refiner burns 2-5 tar per craft (lib/refiner.py takes it from local
# storage); a fab site keeps none (its few tar inputs come through its
# Fabricators' demand, the byproduct leaves as a straggler); Lead Plates keep a Fuel Assembler (reactor fuel) from
# waiting on a craft and a haul. Forage grows only on the home field, so a
# fab site keeps some for its Forage recipes (6 per craft) before one starts.
SITE_STOCK_TARGETS = {"fabricator": {"forage": 1000}, "refiner": {"tar": WAREHOUSE_STOCK_TARGET}, "fuel_assembler": {"lead_plate": 200}}
# Need tier inside a stockpile: {building type: {item: need level}}. A Refiner
# stops without tar, so its outpost asks for 150 (30-75 crafts) at need
# priority; the rest of the 2,000 stays buffer tier.
SITE_STOCK_NEED = {"refiner": {"tar": 150}}
# Stockpile items the Fabricators also craft (craft_tar: 5 t Oil -> 2 Tar, on
# top of the Lubricant/Plastic/Rubber byproduct): the summed targets as a
# backlog order (idle time only), the summed need levels as an upgrade order.
# Both are site orders (production.SITE_ORDER_REQUESTERS): home is no consumer.
SITE_STOCK_CRAFTED = ("lead_plate", "tar")
SITE_STOCK_REQUESTER = "site_stock"
# Construction stock at the Constructor's home: {item: {"target": n, "need": n}},
# target as buffer tier + backlog order, need level as need tier + upgrade
# order. Seeded with EARLY_CONSTRUCTION_STOCK (materials are tight early),
# raised to LATE_CONSTRUCTION_STOCK once the mining-drill phase is reached
# (drone_upgrade.upgrade_phase_reached()) unless edited in the archive. Each
# covers one plan-ahead chunk plus its reserve (autoplay supply_tiers
# plan_ahead_limits()) with room to spare. No power line bridge: the power
# network is meant to be one grid.
CONSTRUCTION_STOCK_KEY = "site_supply.construction_stock"
EARLY_CONSTRUCTION_STOCK = {
    "gas_pipe_segment": {"target": 25, "need": 5},
    "liquid_pipe_segment": {"target": 25, "need": 5},
    "power_line_segment": {"target": 25, "need": 5},
    "gas_pipe_bridge": {"target": 2, "need": 0},
    "liquid_pipe_bridge": {"target": 2, "need": 0},
}
LATE_CONSTRUCTION_STOCK = {
    "gas_pipe_segment": {"target": 100, "need": 10},
    "liquid_pipe_segment": {"target": 100, "need": 10},
    "power_line_segment": {"target": 100, "need": 10},
    "gas_pipe_bridge": {"target": 5, "need": 0},
    "liquid_pipe_bridge": {"target": 5, "need": 0},
}
CONSTRUCTION_KIT_CAP = 5  # extractor kits stocked per kind (one per untapped surveyed site, at most this many)
CONSTRUCTION_STOCK_REQUESTER = "construction_stock"
# Surveyed site kind -> extractor construction kind (exotic: by the deposit's medium).
_SITE_EXTRACTORS = {"water": "water_pump", "oil": "oil_pump", "thermal": "thermal_cap"}
_EXOTIC_EXTRACTORS = {"gas": "exotic_gas_cap", "liquid": "exotic_spring_tap"}
_SITE_MACHINE_GETTERS = {"water": "pump_id", "oil": "pump_id", "thermal": "cap_id", "exotic": "cap_id"}


def _outposts():
    network = component("outpost_network")
    if not network or not hasattr(network, "outposts"):
        return []
    try:
        return list(network.outposts())
    except Exception as error:
        swallowed("site_supply._outposts: network.outposts", error)
        return []


def free_elsewhere(item_ids, site_id, outposts, requests, tick, reads=None):
    """{item_id: units} free for another outpost's need at every outpost but
    site_id. `reads` (logistics_requests.PlanReads) reads each outpost once
    per planning pass."""
    totals = {}
    if not item_ids:
        return totals
    for outpost in outposts:
        if getattr(outpost, "id", None) == site_id:
            continue
        for_need, _for_buffer = outpost_free_tiers(outpost, item_ids, requests, tick, reads=reads)
        for item_id, units in for_need.items():
            totals[item_id] = totals.get(item_id, 0) + units
    return totals


def free_elsewhere_tiers(item_ids, site_id, outposts, requests, tick, reads=None):
    """{band: {item_id: units}} free at every outpost but site_id for demand
    at that band (outpost_tier_free(), summed): a holder keeps only its own
    request at that band or above, the same rule haulers take by
    (logistics_requests.plan_take())."""
    totals = {}
    if not item_ids:
        return totals
    for outpost in outposts:
        if getattr(outpost, "id", None) == site_id:
            continue
        for tier, items in outpost_tier_free(outpost, item_ids, requests, tick, reads=reads).items():
            bucket = totals.setdefault(tier, {})
            for item_id, units in items.items():
                bucket[item_id] = bucket.get(item_id, 0) + units
    return totals


# A site's planned wants: {item_id: {"levels": ladder, "have": units, "keep": units?}}
# (lib/priority.py ladders), built by the want builders below with
# want_raise() -- every level carries its prio, so no builder can lose
# another's band -- and published as logistics requests (as_requests()).


def want_raise(wants, item_id, prio, level, have):
    """Raises this site's want of item_id to at least `level` units at `prio` (priority.ladder_raise()); `have` = local stock now."""
    entry = wants.setdefault(item_id, {"levels": [], "have": have})
    entry["have"] = have
    ladder_raise(entry["levels"], prio, level)
    return entry


def want_total(wants, item_id):
    """Flat target of this site's want of item_id (0 when none)."""
    entry = wants.get(item_id)
    return ladder_total(entry["levels"]) if entry else 0


def want_level(wants, item_id, prio):
    """Units this site wants of item_id at `prio` or higher (0 when none)."""
    entry = wants.get(item_id)
    return ladder_level(entry["levels"], prio) if entry else 0


def want_top(wants, item_id, default=NONE):
    """The highest prio of this site's want of item_id (`default` when none)."""
    entry = wants.get(item_id)
    return entry["levels"][0][0] if entry and entry["levels"] else default


def as_requests(wants):
    """{item_id: (levels, have, keep)} for logistics_requests.publish_requests()."""
    return {i: (w["levels"], w["have"], w.get("keep", 0)) for i, w in wants.items() if w["levels"]}


def consumer_wants(outpost: "OutpostRef", consumers, requests, tick, flying, outposts, blocked=(), reads=None):
    """Wants for the finished root targets consumed at this outpost
    (`consumers`: {item: {site: ladder}}) that it pulls in from every other
    outpost, level by level at the consumer's prio: local + in flight + what
    is free elsewhere for each level at its band (free_elsewhere_tiers(): a
    holder's lower-band request doesn't keep units from a higher-band
    consumer), the highest first. Items in `blocked`
    (settled parts a job waits on) have their levels of band UPGRADE and
    above lifted to BLOCKER. See the module comment."""
    site_id = getattr(outpost, "id", None)
    item_ids = sorted(i for i, sites in consumers.items() if ladder_total((sites or {}).get(site_id, [])) > 0)
    if not item_ids or not any(getattr(o, "id", None) != site_id for o in outposts):
        return {}
    have = outpost_stock(item_ids, outpost)
    spare = free_elsewhere_tiers(item_ids, site_id, outposts, requests, tick, reads)
    wants = {}
    for item_id in item_ids:
        levels = consumers[item_id][site_id]
        local = have.get(item_id, 0) + flying.get(item_id, 0)
        deficits = ladder_deficits(levels, local)
        # Free stock only shrinks toward lower bands: a level's band caps the
        # running pull, and the first level with nothing left ends it.
        plan = []
        pull = 0
        for prio, missing in deficits:
            take = min(missing, spare.get(band(prio), {}).get(item_id, 0) - pull)
            if take <= 0:
                break
            pull += take
            plan.append((prio, local + pull))
        if pull <= 0 and flying.get(item_id, 0) <= 0:
            continue
        for prio, cum in plan:
            want_raise(wants, item_id, prio, cum, have.get(item_id, 0))
        if item_id not in wants:
            want_raise(wants, item_id, levels[0][0], local, have.get(item_id, 0))
        if item_id in blocked:
            wants[item_id]["levels"] = ladder_promote(wants[item_id]["levels"], UPGRADE, BLOCKER)
        free_text = {b: spare[b][item_id] for b in sorted(spare, reverse=True) if spare[b].get(item_id)}
        log.debug(f"consumer_wants({site_id}): {item_id} consumed={levels} local={local} free at other sites={free_text} -> pull {pull}{' (blocker)' if item_id in blocked else ''} -> {wants[item_id]['levels']}")
    return wants


def ship_wants(outpost: "OutpostRef", requests, cache: "SourceCache", flying, smelter_outputs, wants):
    """Adds this fab site's ship plan (production.get_site_ship_plan():
    intermediates spare elsewhere it hauls in instead of building) to wants,
    level = local + in flight + to ship at the plan's prio. An item this
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
        units, prio = plan.get(item_id, [0, NEED])
        level = have.get(item_id, 0) + flying.get(item_id, 0) + units
        if level > 0:
            want_raise(wants, item_id, prio if units > 0 else want_top(wants, item_id, NEED), level, have.get(item_id, 0))
        log.debug(f"ship_wants({site_id}): {item_id} local={have.get(item_id, 0)} in_flight={flying.get(item_id, 0)} ship={units} prio={prio} -> level {level}")


def raw_input_wants(outpost: "OutpostRef", raw, outposts, requests, tick, flying, wants, reads=None):
    """Adds the raw inputs this fab site's Fabricators still need staged
    (`raw`: {item_id: ladder}, inputs no Smelter or Fabricator makes, e.g.
    Forage from the home Crop Automators) to wants at the recipe's prio:
    level = local + in flight + min(short, free at other outposts). Kept
    while units are in flight; nothing free and nothing in flight, no
    request."""
    site_id = getattr(outpost, "id", None)
    item_ids = sorted(raw)
    have = outpost_stock(item_ids, outpost)
    spare = free_elsewhere(item_ids, site_id, outposts, requests, tick, reads)
    for item_id in item_ids:
        local = have.get(item_id, 0) + flying.get(item_id, 0)
        pull = min(max(0, ladder_total(raw[item_id]) - local), spare.get(item_id, 0))
        if pull <= 0 and flying.get(item_id, 0) <= 0:
            continue
        want_raise(wants, item_id, raw[item_id][0][0], local + pull, have.get(item_id, 0))
        log.debug(f"raw_input_wants({site_id}): {item_id} staged need={raw[item_id]} local={local} free elsewhere={spare.get(item_id, 0)} -> pull {pull}")


def dock_raw_wants(outpost: "OutpostRef", wants, prios=None):
    """Raises wants to the raw ore Supply Docks at this outpost still owe
    (production.dock_remaining_requirements()) at the owing order's prio
    (production_docks.dock_owed_prios()), so miners and haulers fill it
    whether or not any exists yet. See the module comment."""
    site_id = getattr(outpost, "id", None)
    owed = dock_remaining_requirements(site_id)
    ores = sorted(o for o in RAW_ORE_ITEM_IDS if owed.get(o, 0) > 0)
    if not ores:
        return
    prios = dock_owed_prios(site_id) if prios is None else prios
    have = outpost_stock(ores, outpost)
    for ore in ores:
        prio = prios.get(ore, NEED)
        want_raise(wants, ore, prio, owed[ore], have.get(ore, 0))
        log.debug(f"dock_raw_wants({site_id}): {ore} owed={owed[ore]} local={have.get(ore, 0)} -> level {owed[ore]} at prio {prio}")


def ingot_wants(outpost: "OutpostRef", cache: "SourceCache", wants):
    """Raises this fab site's wants to its ingot buffer
    (production.fab_site_ingot_targets()): the buffer target at STOCK, its
    need level at NEED. Published even with nothing to pull: the request is
    what keeps other sites' haulers from taking the buffer
    (outpost_free_tiers() leaves each level to its band)."""
    targets = fab_site_ingot_targets(outpost, cache)
    if not targets:
        return
    site_id = getattr(outpost, "id", None)
    have = outpost_stock(sorted(targets), outpost)
    for item_id, (target, need) in sorted(targets.items()):
        if need > 0:
            want_raise(wants, item_id, NEED, need, have.get(item_id, 0))
        if target > 0:
            want_raise(wants, item_id, STOCK, target, have.get(item_id, 0))
        log.debug(f"ingot_wants({site_id}): {item_id} local={have.get(item_id, 0)} need level={need} target={target}")


def _stock_table(table, outpost: "OutpostRef"):
    """{item_id: units} a {building type: {item: units}} table asks of this outpost (max over its building types)."""
    out = {}
    for type_id, items in sorted(table.items()):
        if not discover_building_ids(type_id, outpost):
            continue
        for item_id, units in items.items():
            out[item_id] = max(out.get(item_id, 0), units)
    return out


def site_stock_targets(outpost: "OutpostRef"):
    """{item_id: target} SITE_STOCK_TARGETS asks of this outpost (max over its building types)."""
    return _stock_table(SITE_STOCK_TARGETS, outpost)


def site_stock_needs(outpost: "OutpostRef"):
    """{item_id: need level} SITE_STOCK_NEED asks of this outpost (max over its building types)."""
    return _stock_table(SITE_STOCK_NEED, outpost)


def stock_wants(outpost: "OutpostRef", targets, outposts, requests, tick, flying, wants, needs=None):
    """Raises wants to `targets` (site_stock_targets()) at STOCK and `needs`
    (site_stock_needs()) at NEED; levels already planned at a higher prio
    (ship plan) stay. Requested whether or not any is free elsewhere yet:
    the request is netted against local stock, and a crafted item
    (SITE_STOCK_CRAFTED) is on its way from a Fabricator."""
    if not targets:
        return
    needs = needs or {}
    item_ids = sorted(targets)
    have = outpost_stock(item_ids, outpost)
    for item_id in item_ids:
        if needs.get(item_id, 0) > 0:
            want_raise(wants, item_id, NEED, needs[item_id], have.get(item_id, 0))
        want_raise(wants, item_id, STOCK, targets[item_id], have.get(item_id, 0))
        log.debug(f"stock_wants({getattr(outpost, 'id', None)}): {item_id} local={have.get(item_id, 0)} need level={needs.get(item_id, 0)} target={targets[item_id]}")


def untapped_kits(sites):
    """{kit item: untapped surveyed fluid sites it fits} (EXTRACTOR_KITS), counting sites with no
    pump/cap on them; exotic sites only until Wildlife is complete (only Habitats use exotics)."""
    counts = {}
    skip_exotic = wildlife_complete()
    for site in sites:
        try:
            kind = site.kind()
            getter = _SITE_MACHINE_GETTERS.get(kind)
            if getter is None or (skip_exotic and kind == "exotic") or getattr(site, getter)():
                continue
            structure = _EXOTIC_EXTRACTORS.get(site.medium()) if kind == "exotic" else _SITE_EXTRACTORS[kind]
        except Exception as error:
            swallowed("site_supply.untapped_kits: site read", error)
            continue
        kit = EXTRACTOR_KITS.get(structure) if structure else None
        if kit:
            counts[kit] = counts.get(kit, 0) + 1
    return counts


def _stock_level(entry, key):
    """entry[key] as a non-negative int (one CONSTRUCTION_STOCK_KEY entry), else 0."""
    value = entry.get(key) if isinstance(entry, dict) else None
    return int(value) if isinstance(value, (int, float)) and value > 0 else 0


def construction_stock_levels():
    """{item_id: (target, need)} from CONSTRUCTION_STOCK_KEY; need is capped
    at the target. Seeded from EARLY_CONSTRUCTION_STOCK, replaced by
    LATE_CONSTRUCTION_STOCK in the mining-drill phase while still unedited."""
    stored = archive.get(CONSTRUCTION_STOCK_KEY, None) if archive.has(CONSTRUCTION_STOCK_KEY) else None
    if stored is None or stored == EARLY_CONSTRUCTION_STOCK:
        seed = LATE_CONSTRUCTION_STOCK if upgrade_phase_reached() else EARLY_CONSTRUCTION_STOCK
        if stored != seed:
            stored = {item_id: dict(entry) for item_id, entry in seed.items()}
            archive.set(CONSTRUCTION_STOCK_KEY, stored)
    stored = stored if isinstance(stored, dict) else {}
    levels = {}
    for item_id, entry in stored.items():
        target = _stock_level(entry, "target")
        levels[item_id] = (target, min(_stock_level(entry, "need"), target))
    return levels


def construction_stock_targets(cache: "SourceCache"):
    """({item_id: target}, {item_id: need level}) the Constructor's home keeps:
    construction_stock_levels() plus min(untapped sites, CONSTRUCTION_KIT_CAP)
    kits per extractor kind (buffer tier only)."""
    levels = construction_stock_levels()
    targets = {item_id: target for item_id, (target, _need) in levels.items() if target > 0}
    needs = {item_id: need for item_id, (_target, need) in levels.items() if need > 0}
    for kit, count in untapped_kits(cache.surveyed_sites()).items():
        targets[kit] = max(targets.get(kit, 0), min(count, CONSTRUCTION_KIT_CAP))
    return targets, needs


def _stock_order(targets, needs, fabricator_outputs):
    """{item_id: order_levels()} for the items of `targets` a Fabricator builds: the need level at NEED, the rest up to the target at STOCK."""
    order = {}
    for item_id, target in sorted(targets.items()):
        if target <= 0 or item_id not in fabricator_outputs:
            continue
        need = min(target, needs.get(item_id, 0))
        order[item_id] = order_levels(need=need, need_prio=NEED, stock=target - need, stock_prio=STOCK)
    return order


def order_site_stock(outposts, fabricator_outputs, construction=None, construction_need=None):
    """Orders for what a Fabricator can build (production.set_order()):
    SITE_STOCK_CRAFTED items to the summed stockpile targets of every
    outpost (SITE_STOCK_REQUESTER) and the construction stock
    (construction_stock_targets(), CONSTRUCTION_STOCK_REQUESTER), each as
    its need level at NEED and the rest up to the target at STOCK."""
    totals = {}
    needs = {}
    for outpost in outposts:
        for table, out in ((site_stock_targets(outpost), totals), (site_stock_needs(outpost), needs)):
            for item_id, units in table.items():
                if item_id in SITE_STOCK_CRAFTED:
                    out[item_id] = out.get(item_id, 0) + units
    stock = _stock_order(totals, needs, fabricator_outputs)
    set_order(SITE_STOCK_REQUESTER, stock)
    build = _stock_order(construction or {}, construction_need or {}, fabricator_outputs)
    set_order(CONSTRUCTION_STOCK_REQUESTER, build)
    log.debug(f"order_site_stock: site stock {stock or 'none'}, construction {build or 'none'}")


def plan_site(outpost: "OutpostRef", outposts, requests, cache: "SourceCache", tick, consumers=None, blocked=(), extra_stock=None, extra_need=None, reads=None, dock_ore=None):
    """{item_id: want} (want_raise()) this outpost should request, {} when it
    has no Smelter/Fabricator and consumes no root built elsewhere (or needs
    nothing). extra_stock / extra_need: more stockpile targets and need
    levels (the construction stock at the Constructor's home). dock_ore:
    {ore: (units, prio)} a Supply Dock order's missing Smelter output,
    charged to this smelting site as ore (dock_ore_levels()). `reads`
    (logistics_requests.PlanReads) shares stock reads across the pass. See
    the module comment."""
    log.start("plan_site", level="debug")
    site_id = getattr(outpost, "id", None)
    flying = in_flight(site_id, tick)
    wants = consumer_wants(outpost, consumers or {}, requests, tick, flying, outposts, blocked, reads)
    stock = site_stock_targets(outpost)
    for item_id, units in (extra_stock or {}).items():
        if units > 0:
            stock[item_id] = max(stock.get(item_id, 0), units)
    stock_need = site_stock_needs(outpost)
    for item_id, units in (extra_need or {}).items():
        if units > 0:
            stock_need[item_id] = max(stock_need.get(item_id, 0), units)
    smelter_ids = discover_smelter_ids(outpost)
    fabricator_ids = discover_fabricator_ids(outpost)
    if not smelter_ids and not fabricator_ids:
        stock_wants(outpost, stock, outposts, requests, tick, flying, wants, stock_need)
        dock_ore_wants(outpost, wants, dock_ore, flying)
        dock_raw_wants(outpost, wants)
        log.end()
        return wants
    ore_outputs = smelter_ores(outpost)
    ore_for = {output: ore for ore, output in ore_outputs.items()}
    smelter_outputs = {getattr(r, "output_item", None) for r in cache.smelter_recipes()} - {None}

    if fabricator_ids:
        ship_wants(outpost, requests, cache, flying, smelter_outputs, wants)

    staged_need = fab_site_gross_need(fabricator_ids, None, cache)
    gross = {i: u for i, u in staged_need.items() if i in smelter_outputs}
    fabricator_outputs = {getattr(r, "output_item", None) for r in cache.fabricator_recipes()} - {None}
    raw = {i: u for i, u in staged_need.items() if i not in smelter_outputs and i not in fabricator_outputs}
    if raw:
        raw_input_wants(outpost, raw, outposts, requests, tick, flying, wants, reads)
    item_ids = sorted(set(gross) | set(ore_outputs) | {ore_for[i] for i in gross if i in ore_for})
    have = outpost_stock(item_ids, outpost)
    spare = free_elsewhere(sorted(gross), site_id, outposts, requests, tick, reads)

    ore_short = {}
    ore_prio = {}
    for ingot, levels in sorted(gross.items()):
        units = ladder_total(levels)
        prio = levels[0][0]
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
            ore_prio[ore] = max(ore_prio.get(ore, NONE), prio)
        level = local_ingots + remote_ingots
        if level > 0:
            want_raise(wants, ingot, prio, level, have.get(ingot, 0))
        log.debug(f"{ingot} gross={units} prio={prio} local_ingots={local_ingots} local_ore={local_ore} -> shipped first={first}, D={deficit}, free elsewhere={free}, ingots from remote={remote_ingots}, ore short={deficit - (remote_ingots - first) if ore else 0}")

    if fabricator_ids:
        ingot_wants(outpost, cache, wants)

    for ore, output in sorted(ore_outputs.items()):
        local = have.get(ore, 0) + flying.get(ore, 0)
        if output in gross and local + ore_short.get(ore, 0) > 0:
            want_raise(wants, ore, ore_prio.get(ore, NEED), local + ore_short.get(ore, 0), have.get(ore, 0))
        # A consumer request (consumer_wants(): a dock order for the ore here) keeps its levels.
        want_raise(wants, ore, STOCK, ore_stock_target(ore), have.get(ore, 0))
        log.debug(f"ore {ore} local={local} ore short={ore_short.get(ore, 0)} -> {wants[ore]['levels']}")
    dock_ore_wants(outpost, wants, dock_ore, flying)
    stock_wants(outpost, stock, outposts, requests, tick, flying, wants, stock_need)
    dock_raw_wants(outpost, wants)
    log.end()
    return wants


def dock_ore_wants(outpost: "OutpostRef", wants, dock_ore, flying):
    """Raises this site's ore wants by a Supply Dock order's missing Smelter
    output or raw ore charged to it (`dock_ore`: {ore: (units, prio)},
    dock_ore_levels()): level = local + in flight + units at the order's prio."""
    if not dock_ore:
        return
    site_id = getattr(outpost, "id", None)
    have = outpost_stock(sorted(dock_ore), outpost)
    for ore, (units, prio) in sorted(dock_ore.items()):
        local = have.get(ore, 0) + flying.get(ore, 0)
        want_raise(wants, ore, prio, local + units, have.get(ore, 0))
        log.debug(f"dock_ore_wants({site_id}): {ore} +{units} for a dock order at prio {prio} -> {wants[ore]['levels']}")


def settled_items(item_ids, roots, cache: "SourceCache"):
    """The item_ids no Fabricator will add more of: none in any Fabricator's
    pipeline (production.get_fabricator_pipeline()) and no units of its root
    target left to build (production.root_remaining()). Hauling one of
    these cannot wait for a fuller load (BLOCKER)."""
    pipeline = get_fabricator_pipeline(cache)
    settled = set()
    for item_id in sorted(item_ids):
        building = pipeline.get(item_id, 0)
        remaining = root_remaining(item_id, roots.get(item_id, []), cache)
        if building <= 0 and remaining <= 0:
            settled.add(item_id)
        log.debug(f"settled_items: {item_id} pipeline={building} root remaining={remaining} -> {'blocker' if item_id in settled else 'wait for batch'}")
    return settled


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
        for item_id, want in wants.items():
            if not want["levels"]:
                continue
            entry = {"levels": [list(level) for level in want["levels"]], "have": want["have"], "by": SITE_SUPPLY_REQUESTER, "tick": tick}
            if want.get("keep", 0) > 0:
                entry["keep"] = want["keep"]
            bucket[item_id] = entry
    return result


def dock_ore_levels(outposts, cache: "SourceCache"):
    """{site_id: {ore: (units, prio)}}: per Smelter output a Supply Dock
    order still owes (dock_remaining_requirements()), the units not on the
    network yet (SourceCache.network_stock(), Smelter output not yet in
    storage) nor coming from ore already loaded into a Smelter
    (SourceCache.staged_units()), charged as ore at the owing order's prio
    (production_docks.dock_owed_prios()) to the first smelting site by id
    that refines it and has it assigned (assigned_ores_by_outpost()), so its
    stationed miners mine that ore first and haulers bring spare ore. Raw
    ore an order owes itself is charged the same way to the first site by id
    that has it assigned, a site whose dock owes it first. Nothing for an
    ore no such site has. plan_site() folds it into the site's ore want."""
    owed = dock_remaining_requirements()
    if not owed:
        return {}
    prios = dock_owed_prios()
    assigned = assigned_ores_by_outpost()
    levels = {}
    charged = set()
    ordered = sorted(outposts, key=lambda o: str(getattr(o, "id", "")))
    for outpost in ordered:
        site_id = getattr(outpost, "id", None)
        mined = assigned.get(site_id)
        if site_id is None or not mined:
            continue
        for ore, ingot in sorted(smelter_ores(outpost).items()):
            if ore not in mined or ingot in charged or owed.get(ingot, 0) <= 0:
                continue
            coming = cache.network_stock(ingot) + cache.pipeline_units(ingot) + cache.staged_units(ore)
            short = owed[ingot] - coming
            charged.add(ingot)
            if short > 0:
                levels.setdefault(site_id, {})[ore] = (short, prios.get(ingot, NEED))
                log.debug(f"dock_ore_levels: {ingot} owed={owed[ingot]} on network or smelting={coming} -> {short}x {ore} at {site_id} (prio {prios.get(ingot, NEED)})")
    site_ids = [getattr(o, "id", None) for o in ordered]
    for ore in sorted(RAW_ORE_ITEM_IDS):
        short = owed.get(ore, 0) - cache.network_stock(ore)
        mining = [s for s in site_ids if s is not None and ore in assigned.get(s, ())]
        if short <= 0 or not mining:
            continue
        owing = [s for s in mining if dock_remaining_requirements(s).get(ore, 0) > 0]
        site_id = (owing or mining)[0]
        bucket = levels.setdefault(site_id, {})
        before = bucket.get(ore, (0, NEED))
        bucket[ore] = (before[0] + short, max(before[1], prios.get(ore, NEED)))
        log.debug(f"dock_ore_levels: raw {ore} owed={owed[ore]} on network={cache.network_stock(ore)} -> {short}x at {site_id}")
    return levels


def smelting_sites(outposts):
    """{site_id: set of ores its Smelters refine} for every outpost with a Smelter."""
    return {getattr(o, "id", None): set(smelter_ores(o)) for o in outposts if discover_smelter_ids(o)}


def stranded_ore(outposts, requests, smelt_ores, consumers=None):
    """{outpost_id: {ore: units}} ore at an outpost with no Smelter that the
    outpost neither mines, requests nor consumes (a Supply Dock order
    there). evict_stranded() keeps what has somewhere to go."""
    consumers = consumers or {}
    result = {}
    for outpost in outposts:
        site_id = getattr(outpost, "id", None)
        if site_id is None or site_id in smelt_ores:
            continue
        kept = set(assigned_ores_for(site_id)) | set(requests.get(site_id, {}))
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
    home = next((o for o in outposts if outpost_is_home(o)), None)
    home_id = getattr(home, "id", None)
    if smelt_ores is None:
        smelt_ores = smelting_sites(outposts)
    fab_ids = fab_sites(outposts)
    lab_ids = lab_sites(outposts)
    stores = storage_outposts(outposts)
    store_ids = {getattr(o, "id", None) for o in stores}
    by_id = {getattr(o, "id", None): o for o in outposts}

    stranded = {}
    kinds = {}
    found_by_kind = (
        ("ore", stranded_ore(outposts, requests, smelt_ores, consumers)),
        ("goods", stranded_goods(outposts, requests, fab_ids, goods or set(), consumers)),
        ("reagent", stranded_reagents(outposts, requests, lab_ids, consumers)),
    )
    for kind, found in found_by_kind:
        for site_id, held in found.items():
            stranded.setdefault(site_id, {}).update(held)
            kinds.update({(site_id, item_id): kind for item_id in held})
    other_rules = {i for held in stranded.values() for i in held}
    for site_id, held in (straggling or {}).items():
        if site_id in store_ids:
            continue  # a storage outpost holds leftovers by design
        extra = {i: units for i, units in held.items() if i not in other_rules}
        stranded.setdefault(site_id, {}).update(extra)
        kinds.update({(site_id, item_id): "straggler" for item_id in extra})

    routes = {}
    for site_id, held in stranded.items():
        for item_id in held:
            routes[(site_id, item_id)] = evict_candidates(item_id, kinds[(site_id, item_id)], by_id.get(site_id), home_id, smelt_ores, fab_ids, stores, build_site, lab_ids)
    stranded = {site_id: {i: u for i, u in held.items() if routes[(site_id, i)]} for site_id, held in stranded.items()}
    stranded = {site_id: held for site_id, held in stranded.items() if held}

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
        return {}, {}, {}
    ripe = {}
    for site_id, first_seen in seen.items():
        for item_id, first_tick in first_seen.items():
            if tick - first_tick >= EVICT_AFTER_TICKS:
                ripe.setdefault(site_id, []).append(item_id)
    rooms = {}
    free = {}
    rush = {}
    staging = lifeform_staging_sites(tick) if ripe else set()
    for site_id in sorted(ripe):
        for_need, _for_buffer = outpost_free_tiers(by_id[site_id], sorted(ripe[site_id]), requests, tick)
        for item_id, units in sorted(for_need.items()):
            for dest in routes[(site_id, item_id)]:
                if (dest, item_id) not in rooms:
                    rooms[(dest, item_id)] = evict_room(by_id.get(dest), item_id, requests, tick, home_id, dest in store_ids, dest in staging)
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

    home_requests = requests.get(home_id, {})
    home_free = free.get(home_id, {})
    home_bound = {i for (site_id, i), dests in routes.items() if home_id in dests and i in ripe.get(site_id, ())}
    items = sorted(i for i in home_bound if home_requests.get(i, {}).get("by", EVICT_REQUESTER) == EVICT_REQUESTER)
    wants = {}
    if items:
        have = outpost_stock(items, home)
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
    return wants, {site_id: extra for site_id, extra in free.items() if site_id != home_id}, rush


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
    home = next((o for o in _outposts() if outpost_is_home(o)), None)
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
        for building in discover_storage_buildings(home):
            store = building["component"]
            try:
                units = min(int(store.count(item_id) or 0), inventory_room(item_id))
                if units > 0:
                    store.transfer_to("inventory", item_id, units)
            except Exception as error:
                swallowed("site_supply.sell_stranded_reagents: transfer_to inventory", error)
        units = inventory_count(item_id)
        if units <= 0:
            continue
        try:
            res = shop.sell(item_id, units)
        except Exception as error:
            swallowed("site_supply.sell_stranded_reagents: shop.sell", error)
            continue
        if getattr(res, "status", "") != "ok":
            log.level("warn").print(f"sell('{item_id}', {units}) -> {getattr(res, 'status', '?')}: {getattr(res, 'message', '')}. Left in Inventory.")
            continue
        credits += getattr(res, "credits", 0) or 0
        sold.append(f"{units} {item_id}")
    if sold:
        log.print(f"No Bio Lab anywhere: sold stranded reagents {', '.join(sold)} for {credits} cr.")
    return credits


def lifeform_staging_sites(tick):
    """Outpost ids where a Drone Depot stages life forms: homes of fresh miner drones (fleet.status)."""
    return {entry.get("home") for entry in fleet_status.get_all().values() if isinstance(entry, dict) and entry.get("unit") and entry.get("role") == "miner" and entry.get("home") and is_fresh(entry, tick, STATUS_STALE_TICKS)}


def evict_room(outpost: "OutpostRef | None", item_id, requests, tick, home_id, store=False, staging=False):
    """Units of item_id evict_stranded() may still send to `outpost`: its
    storage slot room (storage.slot_room(): slots already holding the item,
    or its planned request target rounded up to whole slots, else one empty
    slot while EVICT_FREE_SLOTS_KEEP stay empty, EVICT_STAGING_SLOTS_KEEP at a
    life-form `staging` site; a storage outpost (`store`) keeps none) minus
    units already in flight there. None (no cap) for
    home: it is a destination only as a user, and its Inventory is managed by
    the storage sweep."""
    outpost_id = getattr(outpost, "id", None)
    if outpost_id == home_id:
        return None
    if outpost is None:
        return 0
    entry = requests.get(outpost_id, {}).get(item_id)
    planned = request_target(entry) if isinstance(entry, dict) else 0
    keep = 0 if store else (EVICT_STAGING_SLOTS_KEEP if staging else EVICT_FREE_SLOTS_KEEP)
    room = slot_room(item_id, slot_layout(outpost), planned, keep)
    return max(0, room - in_flight(outpost_id, tick).get(item_id, 0))


def add_evicted(outpost: "OutpostRef", wants, extra, tick, rush=()):
    """Raises this site's wants by the stranded ore or goods headed here, at
    STOCK; items in `rush` (stragglers, below every hauler's minimum load)
    at BLOCKER."""
    site_id = getattr(outpost, "id", None)
    items = sorted(extra)
    have = outpost_stock(items, outpost)
    flying = in_flight(site_id, tick)
    for item_id in items:
        level = have.get(item_id, 0) + flying.get(item_id, 0) + extra[item_id]
        if item_id in rush or level > want_total(wants, item_id):
            want_raise(wants, item_id, BLOCKER if item_id in rush else STOCK, level, have.get(item_id, 0))
            log.debug(f"add_evicted({site_id}): {item_id} +{extra[item_id]} stranded -> {wants[item_id]['levels']}")


def mark_reserve(wants, reserve):
    """Sets "keep" (logistics_requests.request_keep()) on the construction
    stock wants at the Constructor's home: `reserve` = {item_id: stock
    target} of the construction stock a Fabricator builds. Other outposts'
    demand can't take those units, and a Supply Dock order builds its own
    (production.builder_reserve()). Stock no Fabricator builds stays free:
    a dock order for it would wait forever."""
    for item_id, units in sorted(reserve.items()):
        want = wants.get(item_id)
        if not want or units <= 0 or not want["levels"]:
            continue
        want["keep"] = min(units, ladder_total(want["levels"]))


def publish_site_requests(curr_tick):
    """Plans and publishes every outpost's site requests (withdrawing them
    where nothing is needed any more, raised by stranded ore or goods headed
    to that site) and home's evict request. Returns
    {outpost_id: wants}."""
    outposts = _outposts()
    reads = PlanReads(curr_tick)
    requests = reads.requests
    cache = SourceCache()
    _roots, consumers, _outputs = fabricator_root_targets(cache)
    # Parts a job waits on (a blueprint's own item, a fleet or standing part
    # of band UPGRADE or above) that no Fabricator will add more of are a
    # BLOCKER want: haulers skip their minimum load for them. Buffers and
    # look-ahead stock (lower bands) wait for a full load.
    urgent_roots = {i for i, levels in list(blueprint_required_ladders(cache).items()) + list(order_ladders().items()) if levels and band(levels[0][0]) >= UPGRADE}
    blocked = settled_items(urgent_roots, _roots, cache) | set(manual_transit_wants(cache))
    build_site = construction_site_id()
    build_stock, build_need = construction_stock_targets(cache)
    reserve = {item_id: units for item_id, units in build_stock.items() if item_id in _outputs}
    dock_ore = dock_ore_levels(outposts, cache)
    planned = {}
    for outpost in outposts:
        site_id = getattr(outpost, "id", None)
        if site_id is not None:
            here = site_id == build_site
            planned[site_id] = plan_site(outpost, outposts, requests, cache, curr_tick, consumers, blocked, build_stock if here else None, build_need if here else None, reads, dock_ore.get(site_id))
    order_site_stock(outposts, _outputs, build_stock, build_need)
    # Stranded check against this pass's plan: a site that just lost its
    # Smelters frees its ore for eviction right away.
    planned_view = planned_requests(requests, planned, curr_tick)
    home_id = next((getattr(o, "id", None) for o in outposts if outpost_is_home(o)), None)
    straggling = stragglers(outposts, planned_view, home_id, cache, consumers, set(_roots))
    _home_wants, evicted, rush = evict_stranded(outposts, planned_view, curr_tick, consumers, smelting_sites(outposts), evictable_goods(cache), straggling, build_site)
    published = {}
    notes = []
    for outpost in outposts:
        site_id = getattr(outpost, "id", None)
        if site_id is None:
            continue
        wants = planned[site_id]
        if evicted.get(site_id):
            add_evicted(outpost, wants, evicted[site_id], curr_tick, rush.get(site_id, ()))
        # A straggler headed here that this site already requests (the
        # construction stock at the Constructor's home): its levels of band
        # NEED and above become a BLOCKER, so the leftover moves below the
        # haulers' minimum load; a STOCK buffer above them waits for a load.
        for item_id in sorted(rush.get(site_id, ())):
            want = wants.get(item_id)
            if want and want["levels"]:
                want["levels"] = ladder_promote(want["levels"], NEED, BLOCKER)
        if site_id == build_site:
            mark_reserve(wants, reserve)
        if wants or any(e.get("by") == SITE_SUPPLY_REQUESTER for e in requests.get(site_id, {}).values()):
            published[site_id] = wants
        if not publish_requests(site_id, SITE_SUPPLY_REQUESTER, as_requests(wants), curr_tick, requests, skip_foreign=False):
            continue
        if wants:
            notes.append(f"Site supply at '{site_id}': {', '.join(f'{i} {want_total(wants, i)}' for i in sorted(wants))}.")
        else:
            notes.append(f"Site supply at '{site_id}': withdrawn (no Smelter/Fabricator demand).")
    if notes:
        log.start(f"Publishing site supply requests ({len(notes)} site(s) changed)")
        for note in notes:
            log.print(note)
        log.end(f"Published {len(notes)} site supply update(s)")
    try:
        from supply_dock import ORDER_PLAN_ARCHIVE_KEY

        PUBLISHER.publish_from_cache(cache, curr_tick, archive.get(ORDER_PLAN_ARCHIVE_KEY, {}) or {})
    except Exception as error:
        swallowed("site_supply.publish_site_requests: demand record", error)
    return published
