# Shared production-demand planning for mining and refining automation.
from archive import archive
from storage import total_stock, discover_storage_buildings, outpost_is_home, crop_automator_forage_total, CROP_AUTOMATOR_ITEM_ID
from outpost_mining import RAW_ORE_ITEM_IDS, HOME_OUTPOST_ID
from power import DAY_CYCLE_DURATION_SECONDS
from logistics_requests import active_requests, in_flight, outpost_free_tiers, aboard_units, DRONE_DEPOT_TYPE_IDS
from tree_console import TreeConsole
from swallow import swallowed
import fleet_status
import lead_cask

log = TreeConsole(module="production")

# Recipe.duration_game_hours -> real seconds, from the fixed day-cycle
# schedule lib/power.py's DAY_CYCLE_DURATION_SECONDS already derives from
# (see docs/AI_CHEATSHEET.md) -- reused here, not redefined, so there's
# exactly one place this constant lives.
SECONDS_PER_GAME_HOUR = DAY_CYCLE_DURATION_SECONDS / 24.0

# How far ahead a Smelter/Fabricator should prefill its input buffer, in real
# seconds of continuous crafting -- see craft_prefill_units(). Deliberately
# time-based, not a fixed unit count: a fast recipe (a few seconds/craft)
# still gets several crafts' worth staged so the Auto Feeder isn't paid
# every single craft, while a slow recipe (tens of minutes/craft) only ever
# prefills what it needs for its next craft or two, instead of reflexively
# filling toward the machine's full hardware buffer cap regardless of how
# long that material would then sit idle.
INPUT_PREFILL_SECONDS = 30

# Ship-before-craft (ship_units()): a site short of an item that sits spare at
# another outpost has it hauled in instead of making it, unless it can make
# it from local stock in under SHIP_OVER_CRAFT_SECONDS real seconds (its own
# crafts plus making its locally missing inputs). Spare of at least
# SHIP_SURPLUS_FACTOR x the shortfall always ships (surplus piles like tar).
SHIP_OVER_CRAFT_SECONDS = 300
SHIP_SURPLUS_FACTOR = 10


def _ceil(x):
    """Ceiling without the math module -- this sandboxed script environment
    doesn't permit `import math`. Plain arithmetic: int(x) truncates toward
    zero, so for a non-negative x that's floor(x); bump by 1 whenever x has
    a fractional remainder above that. Only ever called here with
    non-negative x (seconds/unit ratios)."""
    i = int(x)
    return i + 1 if x > i else i


def craft_seconds(recipe):
    """Real-world seconds per craft for `recipe`, converted from its
    `.duration_game_hours` via the fixed day-cycle schedule. Floors at 1
    second if the recipe reports a missing/zero duration, so dividing
    against it (craft_prefill_units()) never blows up."""
    hours = getattr(recipe, "duration_game_hours", None)
    if not hours or hours <= 0:
        return 1.0
    return hours * SECONDS_PER_GAME_HOUR


def craft_prefill_units(recipe, item_id, prefill_seconds=INPUT_PREFILL_SECONDS):
    """
    How many units of `item_id` (one of recipe.inputs) a Smelter/Fabricator
    should keep staged to cover roughly the next `prefill_seconds` of real
    time spent crafting -- ceil(prefill_seconds / craft_seconds(recipe))
    crafts' worth, floored at one craft's own requirement (staging less than
    a single craft needs would be pointless -- the craft can't start until
    the full per-craft amount is present anyway). Returns 0 if item_id isn't
    one of this recipe's inputs.

    Deliberately per-recipe/time-based rather than a fixed unit chunk: this
    is what makes the buffer target scale correctly whether a recipe crafts
    every few seconds (many crafts fit in the window, more staged) or takes
    tens of minutes (one craft's worth is already more than the window asks
    for). Used as a cap on top-up size by both lib/smelter.py's ore intake
    and lib/fabricator.py's load_inputs() -- see docs/AI_CHEATSHEET.md.
    """
    inputs = getattr(recipe, "inputs", {}) or {}
    per_craft = inputs.get(item_id)
    if not per_craft:
        return 0
    crafts = max(1, _ceil(prefill_seconds / craft_seconds(recipe)))
    return int(_ceil(crafts * per_craft))


def _current_tick():
    """Module-level tick read (mirrors VehicleController.get_current_tick()) for callers with no vehicle instance."""
    clock = _component("clock")
    if clock and hasattr(clock, "tick"):
        try:
            return clock.tick()
        except Exception as error:
            swallowed("production._current_tick: clock.tick", error)
    return 0


def _component(component_id):
    try:
        return get_component(component_id)
    except Exception as error:
        swallowed("production._component: get_component", error)
        return None


SMELTER_TYPE_ID = "smelter"


def _all_outposts():
    """Every owned OutpostRef (outpost_network.outposts()), or just home when
    the network can't be listed."""
    network = _component("outpost_network")
    if network and hasattr(network, "outposts"):
        try:
            return list(network.outposts())
        except Exception as error:
            swallowed("production._all_outposts: network.outposts", error)
    home = _home_outpost()
    return [home] if home else []


# Building discovery is called a dozen times per Smelter/Fabricator step (recipe lists, dock orders,
# worker counts, pipelines), each an outposts() + buildings(type) sweep. Results are reused for this
# many ticks (~2 s), so a newly placed building is seen at most that late.
DISCOVERY_TTL_TICKS = 20

# {(type_id, outpost_id or None): (tick, [ids])}
_DISCOVERY_MEMO = {}

# Recipe input table ({output_item: {input_item: qty per output unit}}), built from the
# Fabricator + Smelter recipe lists. Recipes only change when research unlocks new ones,
# which changes the list lengths; the table is rebuilt then, or after this many ticks.
RECIPE_INDEX_TTL_TICKS = 6000

# {"index": (tick, (fabricator count, smelter count), table)}
_RECIPE_INDEX_MEMO = {}


def _discover_building_ids(type_id, outpost=None):
    """Ids of every `type_id` building at `outpost`, or at every outpost when
    `outpost` is None (home first, then outpost_network order). Memoized for
    DISCOVERY_TTL_TICKS."""
    key = (type_id, getattr(outpost, "id", None) if outpost is not None else None)
    now = _current_tick()
    memo = _DISCOVERY_MEMO.get(key)
    if memo is not None and 0 <= now - memo[0] < DISCOVERY_TTL_TICKS:
        return list(memo[1])
    ids = _scan_building_ids(type_id, outpost)
    _DISCOVERY_MEMO[key] = (now, ids)
    return list(ids)


def _scan_building_ids(type_id, outpost):
    outposts = [outpost] if outpost is not None else _all_outposts()
    ids = []
    for candidate in outposts:
        if not candidate or not hasattr(candidate, "buildings"):
            continue
        try:
            for building in candidate.buildings(type_id):
                b_id = getattr(building, "id", None)
                if b_id and b_id not in ids:
                    ids.append(b_id)
        except Exception as error:
            swallowed("production._discover_building_ids: outpost.buildings", error)
    return ids


def discover_building_ids(type_id, outpost=None):
    """Ids of every `type_id` building at `outpost`, or network-wide when omitted (memoized discovery)."""
    return _discover_building_ids(type_id, outpost)


def discover_smelter_ids(outpost=None):
    """
    All Smelter building ids at `outpost`, or network-wide when omitted --
    a Smelter at a factory outpost is a peer like any home one. Recipe
    *availability* is tech-gated and identical across same-type buildings,
    so any one discovered smelter's list_recipes() is a representative
    stand-in everywhere that just needs "a" smelter. Demand-cascade functions
    use discovery, not a hardcoded id.
    """
    return _discover_building_ids(SMELTER_TYPE_ID, outpost)


def machine_outpost_id(machine):
    """Id of the outpost a Smelter/Fabricator is deployed at (its .outpost
    OutpostRef), or None when the component doesn't expose one."""
    return getattr(getattr(machine, "outpost", None), "id", None)


def claim_site_id(machine):
    """Outpost id a machine's recipe claim is filed under (smelter/fabricator
    .recipe_claims): its own outpost, HOME_OUTPOST_ID when not exposed."""
    return machine_outpost_id(machine) or HOME_OUTPOST_ID


def site_recipe_claims(claims, owner_field):
    """
    Copy of a stored recipe-claims dict in its per-site shape
    {outpost_id: {recipe_id: {owner_field: machine_id, "tick": n}}}, with
    empty sites and flat-shaped entries ({recipe_id: {owner_field: ...}},
    keyed by recipe network-wide) dropped. Claims are short-lived (a fresh
    claim is renewed every step), so a dropped flat entry is simply re-claimed.
    """
    result = {}
    if not isinstance(claims, dict):
        return result
    for site_id, site in claims.items():
        if not isinstance(site, dict) or owner_field in site:
            continue
        entries = {recipe_id: dict(claim) for recipe_id, claim in site.items() if isinstance(claim, dict)}
        if entries:
            result[site_id] = entries
    return result


def _home_outpost():
    network = _component("outpost_network")
    if network and hasattr(network, "home"):
        return network.home()
    return None


def home_outpost_id():
    """Id of the home outpost (outpost_network.home()), HOME_OUTPOST_ID when unavailable."""
    return getattr(_home_outpost(), "id", None) or HOME_OUTPOST_ID


def construction_site_id():
    """Outpost a Constructor Pioneer loads its materials at: the home_base of
    the most recently reporting "constructor" in fleet_status, home_outpost_id()
    when none reports. Assumes every Constructor shares one home."""
    best_tick, site_id = None, None
    for entry in fleet_status.get_all().values():
        if not isinstance(entry, dict) or entry.get("role") != "constructor" or not entry.get("home"):
            continue
        tick = entry.get("tick", 0) or 0
        if best_tick is None or tick > best_tick:
            best_tick, site_id = tick, entry["home"]
    return site_id or home_outpost_id()


def smelter_ores(outpost):
    """{ore: output_item} for every raw ore a Smelter at `outpost` has an
    unlocked recipe for, {} without a Smelter there. list_recipes() is
    tech-gated and identical per Smelter, so the first one that answers
    stands in for all."""
    for smelter_id in discover_smelter_ids(outpost):
        smelter = _component(smelter_id)
        if not smelter or not hasattr(smelter, "list_recipes"):
            continue
        try:
            recipes = list(smelter.list_recipes())
        except Exception as error:
            swallowed("production.smelter_ores: smelter.list_recipes", error)
            continue
        result = {}
        for recipe in recipes:
            output_item = getattr(recipe, "output_item", None)
            for ore in (getattr(recipe, "inputs", {}) or {}):
                if ore in RAW_ORE_ITEM_IDS and output_item:
                    result[ore] = output_item
        return result
    return {}


def _default_smelter():
    """First discovered Smelter component (dynamic stand-in for the old hardcoded 'smelter_1')."""
    ids = discover_smelter_ids()
    if ids:
        return _component(ids[0])
    return _component("smelter_1")  # last-resort fallback if discovery finds nothing (e.g. outpost_network unavailable)


FABRICATOR_TYPE_ID = "fabricator"


def discover_fabricator_ids(outpost=None):
    """All Fabricator building ids at `outpost`, or network-wide when omitted. Same shape/reasoning as discover_smelter_ids()."""
    return _discover_building_ids(FABRICATOR_TYPE_ID, outpost)


def _default_fabricator():
    """First discovered Fabricator component (dynamic stand-in for the old hardcoded 'fabricator_1')."""
    ids = discover_fabricator_ids()
    if ids:
        return _component(ids[0])
    return _component("fabricator_1")  # last-resort fallback if discovery finds nothing


FUEL_ASSEMBLER_TYPE_ID = "fuel_assembler"
# Fuel Assembler outputs (10_nuclear/lib/fuel_assembler.py builds them, not a Fabricator).
FUEL_ASSEMBLER_OUTPUTS = ("fuel_rod", "nuclear_battery")
# weather.aftermaths (lib/weather_signals.py); a live uranium site makes Raw Uranium sourceable.
AFTERMATHS_KEY = "weather.aftermaths"


def _default_fuel_assembler():
    ids = _discover_building_ids(FUEL_ASSEMBLER_TYPE_ID)
    return _component(ids[0]) if ids else None


def _uranium_aftermath_pending():
    """True while weather.aftermaths holds a uranium site not yet exhausted."""
    sites = archive.get(AFTERMATHS_KEY, {})
    if not isinstance(sites, dict):
        return False
    return any(isinstance(s, dict) and s.get("kind") == "uranium" and not s.get("exhausted") for s in sites.values())


SUPPLY_DOCK_TYPE_ID = "supply_dock"


def discover_supply_dock_ids(outpost=None):
    """
    All Supply Dock building ids at outpost (default: every outpost, like
    Smelter/Fabricator discovery -- a dock at a fab outpost ships what that
    site builds). A second dock's own active order must count toward
    Fabricator targets/raw-material demand, not just whichever order the
    first dock is running.
    """
    return _discover_building_ids(SUPPLY_DOCK_TYPE_ID, outpost)


def _all_dock_orders():
    """
    [(dock_component, order), ...] for every discovered Supply Dock currently
    holding an active order (docks with no order, or that can't be reached,
    are simply absent from the list). Single source of truth for "every
    current order across the whole dock fleet" -- every demand-cascade
    function below loops this instead of reading one hardcoded dock.
    """
    ids = discover_supply_dock_ids()
    if not ids:
        ids = ["supply_dock_1"]  # last-resort fallback if discovery finds nothing
    pairs = []
    for dock_id in ids:
        dock = _component(dock_id)
        if not dock or not hasattr(dock, "current_order"):
            continue
        try:
            order = getattr(dock, "current_order")()
        except Exception as error:
            swallowed("production._all_dock_orders: getattr(dock, 'current_order')", error)
            continue
        if order:
            pairs.append((dock, order))
    return pairs


def _dock_order_remaining():
    """
    {order_id: {item_id: units}} still owed per active order:
    required - shipped - units already loaded into every dock serving it.

    Deduplicated per order: several docks may serve the same order and share
    its shipped progress (docs/components/supply_dock.md), so looping
    _all_dock_orders() pairs and adding each dock's remaining counted a
    shared order once per dock (seen live: spire_13 on two docks demanded
    120 Neutronium Bars for a 60-bar order). Loaded-but-undispatched units
    are in neither Inventory nor order.shipped, so every dock's count() is
    summed and subtracted -- without that, producers re-craft whatever sits
    in the dock and overshoot the order by that much (seen live: 104 Heli
    Thrusters / 204 small Oil Tanks for 100/200 orders, the extras stranded
    in Inventory, one slot each). Negative remainders are kept; callers clamp.
    """
    loaded_by_order = {}
    orders_by_id = {}
    for dock, order in _all_dock_orders():
        if not hasattr(order, "requires"):
            continue
        order_id = getattr(order, "id", None)
        orders_by_id[order_id] = order
        loaded = loaded_by_order.setdefault(order_id, {})
        if not hasattr(dock, "count"):
            continue
        try:
            for item_id in order.requires:
                loaded[item_id] = loaded.get(item_id, 0) + dock.count(item_id)
        except Exception as error:
            swallowed("production._dock_order_remaining: loaded.get", error)

    result = {}
    for order_id, order in orders_by_id.items():
        try:
            shipped = getattr(order, "shipped", {}) or {}
            loaded = loaded_by_order.get(order_id, {})
            result[order_id] = {
                item_id: required - shipped.get(item_id, 0) - loaded.get(item_id, 0)
                for item_id, required in (getattr(order, "requires", {}) or {}).items()
            }
        except Exception as error:
            swallowed("production._dock_order_remaining: loaded_by_order.get", error)
    log.trace(f"_dock_order_remaining: {len(orders_by_id)} distinct active order(s) -> {result}")
    return result


def _dock_order_sites():
    """{order_id: [outpost ids of every dock holding it]} -- where each active
    order's items are consumed."""
    sites = {}
    for dock, order in _all_dock_orders():
        order_id = getattr(order, "id", None)
        site_id = machine_outpost_id(dock) or home_outpost_id()
        bucket = sites.setdefault(order_id, [])
        if site_id not in bucket:
            bucket.append(site_id)
    return sites


def find_dock_order_requiring(item_id):
    """
    First (dock, order) pair, across every discovered Supply Dock, whose
    active order still requires item_id (regardless of how much has already
    shipped -- callers that care about remaining-vs-shipped check that
    themselves). (None, None) if no current order anywhere requires it.
    Shared by get_raw_material_reason() below and lib/fabricator.py's
    target_reason(), so "which dock wants this" is answered in one place.
    """
    for dock, order in _all_dock_orders():
        if item_id in (getattr(order, "requires", {}) or {}):
            return dock, order
    return None, None


# A Fabricator recipe's water/steam/oil requirement (recipe.fluid_inputs,
# e.g. {"water_in": 1.0}) is a *separate* field from its solid .inputs
# (docs/components/fabricator.md) -- delivered by connecting the matching
# FluidPort (self.water_in / .steam_in / .oil_in) to one of these building
# types, not by taking an Inventory/Warehouse item. can_source_item() used to
# only ever look at .inputs, so a recipe needing Water was waved through as
# "sourceable" purely on its solid ingredients (Iron Ingot, Glass) even with
# no Water Pump anywhere on the network -- the Fabricator would then set that
# recipe and stall forever, and Supply Dock would commit to an Earth Order
# that could never actually complete.
FLUID_SOURCE_TYPE_IDS = {
    "water_in": ("water_pump", "steam_condenser", "liquid_tank", "bulk_liquid_reservoir"),
    "oil_in": ("oil_pump", "liquid_tank", "bulk_liquid_reservoir"),
    "steam_in": ("thermal_cap", "gas_tank"),
}

# liquid_tank/bulk_liquid_reservoir/gas_tank are generic multi-fluid buffers --
# they latch onto whichever exact fluid is piped into them FIRST and hold
# only that until drained to 0 (docs/components/liquid_tank.md,
# docs/components/gas_tank.md). Their mere existence on the network says
# nothing about which fluid they hold, or whether anything will ever fill
# one with the fluid we actually need -- e.g. a Liquid Tank latched to Water,
# or sitting empty with no Oil Pump anywhere to ever feed it, is not a
# usable Oil source even though the tank itself is real. Every other type in
# FLUID_SOURCE_TYPE_IDS is a dedicated producer (oil_pump, water_pump,
# steam_condenser, thermal_cap) that only ever emits its one fixed fluid, so
# its existence alone is sufficient.
BUFFER_FLUID_TYPE_IDS = ("liquid_tank", "bulk_liquid_reservoir", "gas_tank")
# Expected building.fluid() latch id for each fluid_key -- see both docs
# pages' `.fluid()` method above.
FLUID_LATCH_IDS = {"water_in": "water", "oil_in": "oil", "steam_in": "steam"}


def fluid_building_is_viable(fluid_key, type_id, building):
    """
    Whether this specific discovered building can actually deliver
    fluid_key, not just "this building type could in principle carry it".
    Shared by can_source_fluid() below and lib/fabricator.py's connection
    candidate discovery, so both apply the exact same buffer-latch rule --
    see BUFFER_FLUID_TYPE_IDS' comment for why existence alone isn't enough
    for a tank. Deliberately does NOT consult fluid_routing.tank_assignments
    -- that registry only gates which tank a producer may establish a NEW
    connection to (see fluid_routing.tank_is_eligible_target()); a tank's
    own .fluid() latch is already the complete, authoritative answer to "can
    it deliver fluid_key right now" regardless of the registry's state.
    """
    if type_id not in BUFFER_FLUID_TYPE_IDS:
        return True
    expected = FLUID_LATCH_IDS.get(fluid_key)
    if not expected:
        return True
    # `building` here is whatever outpost.buildings(type_id) handed us -- a
    # bare BuildingRef snapshot (.id/.name/.type_id/.outpost/.powered/
    # .position only, no .fluid()/.level()/etc, per docs/components/
    # outpost.md) when called from discovery loops, but the full live
    # component when called directly with one (e.g. from a unit test). A
    # BuildingRef has no .fluid() of its own -- must resolve the real
    # component via get_component(ref.id) first, or this always raises and
    # every buffer tank looks permanently non-viable regardless of what it
    # actually holds.
    if not hasattr(building, "fluid"):
        b_id = getattr(building, "id", None)
        if not b_id:
            return False
        building = _component(b_id)
        if not building:
            return False
    try:
        return getattr(building, "fluid")() == expected
    except Exception as error:
        swallowed("production.fluid_building_is_viable: getattr(building, 'fluid')", error)
        return False


def can_source_fluid(fluid_key, cache=None):
    """
    Whether a building that could feed this FluidPort right now exists
    anywhere on the outpost network -- a dedicated producer of this exact
    fluid, or a buffer tank already latched to it (see
    fluid_building_is_viable()). Deliberately checks existence/latch state
    only, not an actual completed pipe route or fluid level -- matching
    can_source_item()'s own "known source" bar (a surveyed site doesn't
    guarantee a working claim either) -- so this only rules out the "not
    (yet) able to supply this fluid at all" case, not "built but not yet
    piped/full".

    Pass a shared `cache` (SourceCache) when checking several
    recipes/items/orders in one pass -- see SourceCache's docstring for why
    that matters; the outpost.buildings() scan this does is a real game call
    per fluid_key, otherwise repeated once per recipe that needs it.
    """
    log.start(f"can_source_fluid({fluid_key})", level="debug")
    if cache is not None and fluid_key in cache._fluid_results:
        log.trace(f"cache hit -> {cache._fluid_results[fluid_key]}")
        log.end()
        return cache._fluid_results[fluid_key]

    type_ids = FLUID_SOURCE_TYPE_IDS.get(fluid_key)
    if not type_ids:
        result = True  # unrecognized fluid key -- don't block on something we don't model
        log.trace("unrecognized fluid key, not blocking")
    else:
        result = False
        network = _component("outpost_network")
        if network and hasattr(network, "outposts"):
            try:
                for outpost in network.outposts():
                    for type_id in type_ids:
                        for building in outpost.buildings(type_id):
                            if fluid_building_is_viable(fluid_key, type_id, building):
                                result = True
                                log.trace(f"viable source found -> {getattr(building, 'id', type_id)} ({type_id})")
                                break
                        if result:
                            break
                    if result:
                        break
            except Exception as error:
                swallowed("production.can_source_fluid: network.outposts", error)
        if not result:
            log.trace(f"no viable source among {type_ids}")

    if cache is not None:
        cache._fluid_results[fluid_key] = result
    log.end()
    return result


def _add_demand(demands, item_id, quantity):
    if item_id and quantity > 0:
        demands[item_id] = demands.get(item_id, 0) + quantity


# Defaults only seed the Data Archive once; edit the archived key afterward
# (Data Archive Notebook) to change stock targets without touching this file.
FABRICATOR_STOCK_TARGETS_KEY = "fabricator.stock_targets"
DEFAULT_FABRICATOR_STOCK_TARGETS = {
    "gas_pipe_segment": 10,
    "power_line_segment": 10,
    "liquid_pipe_segment": 10,
}


def get_fabricator_stock_targets():
    """Seeds the Data Archive with default stock targets on first run, then reads them back."""
    if not archive.has(FABRICATOR_STOCK_TARGETS_KEY):
        archive.set(FABRICATOR_STOCK_TARGETS_KEY, dict(DEFAULT_FABRICATOR_STOCK_TARGETS))
    stored = archive.get(FABRICATOR_STOCK_TARGETS_KEY, DEFAULT_FABRICATOR_STOCK_TARGETS)
    if not isinstance(stored, dict):
        return dict(DEFAULT_FABRICATOR_STOCK_TARGETS)
    return {
        item_id: int(qty) for item_id, qty in stored.items()
        if isinstance(qty, (int, float)) and qty >= 0
    }


MANUAL_ORDERS_KEY = "fabricator.manual_orders"


def get_manual_orders():
    """{item_id: quantity_still_wanted} -- ad-hoc Fabricator build requests, edited directly in the
    Data Archive Notebook (e.g. {"drone_small": 2}) on top of the standing stock targets/orders
    get_fabricator_targets() already covers. No default is seeded (unlike
    get_fabricator_stock_targets()) -- an empty manual order list is the normal state. Counted down
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


def consume_manual_order(item_id, quantity, outpost=None):
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
        swallowed("production.consume_manual_order: archive.transaction", error)


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
        swallowed("production._record_manual_transit: SourceCache.stock", error)
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
        swallowed("production._record_manual_transit: archive.transaction", error)
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


def _settle_transit(entries, cache):
    """{item_id: (units, base)} with arrived units removed (see MANUAL_TRANSIT_KEY)."""
    settled = {}
    for item_id, (units, base) in entries.items():
        home = cache.stock(item_id)
        if home < base + units and cache.network_stock(item_id) > home:
            settled[item_id] = (units, base)
    return settled


def manual_transit_wants(cache=None):
    """{item_id: units wanted at home} for manual-order units still off home."""
    entries = _manual_transit_entries()
    if not entries:
        return {}
    cache = SourceCache() if cache is None else cache
    return {item_id: base + units for item_id, (units, base) in _settle_transit(entries, cache).items()}


def reconcile_manual_transit(cache=None):
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
# ONE shared dict {requester_id: {item_id: quantity}} (CLAUDE.md rule 7), so
# each requester -- the coordinator, or a drone wanting a bigger Cargo Pod --
# owns and clears only its own entry. Quantities are "keep at least this many
# in stock" floors, summed across requesters. Ranked below manual orders AND
# blueprint demand in lib/fabricator.py's choose_recipe() (building new
# things beats upgrading working old ones), above everything else.
UPGRADE_ORDERS_KEY = "fabricator.upgrade_orders"
# Requesters in UPGRADE_ORDERS_KEY that aren't drones. fleet_upgrade._prune()
# drops every other entry whose drone no longer exists, so a standing order
# from another script must be listed here. "field_keeper" = the Harvester's
# field-machine kits (8_planting/lib/harvester_machines.py). "bio_caster" = the
# Bio Caster's forge materials for all open Volcanic bio orders (lib/bio_volcanic.py).
# "fleet_commission" = a drone kit the COMMISSION card queued (lib/drone_commission.py).
# "plant_terraformer" = the Plant Terraformers' next NEED_BATCHES batches of Fertilizer /
# Growth Accelerant (8_planting/lib/plant_terraformer.py). "fuel_assembler" = the
# Fuel Assemblers' Lead Plates for their next crafts (10_nuclear/lib/fuel_assembler.py).
# "field_amplifier" = the Harvester's Yield Amplifier doses (8_planting/lib/harvester_amplify.py).
STANDING_ORDER_REQUESTERS = ("field_keeper", "bio_caster", "fleet_commission", "plant_terraformer", "fuel_assembler", "field_amplifier")
# Standing requesters whose order is a recurring consumable buffer, not a
# one-off part a job waits on: their items are never hauled urgently
# (lib/site_supply.py settled_items()), so a hauler waits for a full load.
# The Fuel Assemblers' Lead Plates stay urgent (reactor fuel); their outposts
# keep a stockpile instead (site_supply.SITE_STOCK_TARGETS).
RECURRING_ORDER_REQUESTERS = ("plant_terraformer", "field_amplifier")

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


def get_backlog_orders():
    """{item_id: quantity} summed across every requester's entry in BACKLOG_ORDERS_KEY."""
    return _summed_orders(BACKLOG_ORDERS_KEY)


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
    if (current or {}) == wanted:
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


def fabricator_unlocked_outputs(cache=None):
    """Set of item ids the default Fabricator can craft today (list_recipes()
    only lists unlocked recipes, docs/components/fabricator.md)."""
    if cache is not None:
        recipes = cache.fabricator_recipes()
    else:
        fabricator = _default_fabricator()
        try:
            recipes = fabricator.list_recipes() if fabricator and hasattr(fabricator, "list_recipes") else []
        except Exception as error:
            swallowed("production.fabricator_unlocked_outputs: fabricator.list_recipes", error)
            recipes = []
    return {getattr(r, "output_item", None) for r in recipes} - {None}


def blueprint_demand_items(cache=None):
    """Item ids any pending/paused Construction Blueprint needs, directly or via
    the recipe cascade (_cascade_blueprint_demand()). choose_recipe()'s tier 2."""
    return set(_cascade_blueprint_demand(cache).keys())


def _stock_fn(cache):
    """cache.stock when a SourceCache is threaded through, else the uncached
    storage.total_stock() -- lets every demand helper below take an optional
    `cache` without changing behavior for callers that don't pass one."""
    return cache.stock if cache is not None else total_stock


def _recipe_lists(cache=None):
    """[Fabricator recipes, Smelter recipes] (a cache's memoized lists, else one list_recipes() each)."""
    if cache is not None:
        return [cache.fabricator_recipes(), cache.smelter_recipes()]
    lists = []
    for component in (_default_fabricator(), _default_smelter()):
        if not component or not hasattr(component, "list_recipes"):
            lists.append([])
            continue
        try:
            lists.append(list(component.list_recipes()))
        except Exception as error:
            swallowed("production._recipe_lists: component.list_recipes", error)
            lists.append([])
    return lists


def _build_recipe_index(recipe_lists):
    """{output_item: {input_item: qty / output_count}}; the first recipe per output wins (Fabricator before Smelter)."""
    index = {}
    for recipes in recipe_lists:
        for recipe in recipes:
            output = getattr(recipe, "output_item", None)
            if not output or output in index:
                continue
            output_count = max(1, getattr(recipe, "output_count", 1))
            inputs = getattr(recipe, "inputs", {}) or {}
            index[output] = {in_id: qty / output_count for in_id, qty in inputs.items()}
    return index


def _recipe_index(cache=None):
    """
    The recipe input table, kept per script for RECIPE_INDEX_TTL_TICKS and rebuilt
    early when a recipe list's length changes (a research unlock). Memoized on
    `cache` for the rest of its pass. Shared: treat it and its dicts as read-only.
    """
    if cache is not None and cache._recipe_index is not None:
        return cache._recipe_index
    lists = _recipe_lists(cache)
    signature = tuple(len(recipes) for recipes in lists)
    now = _current_tick()
    memo = _RECIPE_INDEX_MEMO.get("index")
    if memo is not None and memo[1] == signature and 0 <= now - memo[0] < RECIPE_INDEX_TTL_TICKS:
        index = memo[2]
    else:
        index = _build_recipe_index(lists)
        _RECIPE_INDEX_MEMO["index"] = (now, signature, index)
    if cache is not None:
        cache._recipe_index = index
    return index


def _recipe_inputs_for(item_id, cache=None):
    """{input_item_id: qty_per_output_unit} for whichever of Fabricator/
    Smelter builds item_id, or None if neither does. Shared by
    _cascade_blueprint_demand(), _cascade_fabricator_output_demand() and
    get_smelter_demands(). Reads the long-lived recipe table (_recipe_index());
    the returned dict is shared, treat it as read-only."""
    return _recipe_index(cache).get(item_id)


def _cascade_fabricator_output_demand(seed_targets, fabricator_outputs, cache=None, stock=None, supply=None):
    """
    Breadth-first demand cascade seeded from seed_targets (Fabricator stock
    targets/Supply Dock orders, restricted to items the Fabricator itself
    builds), propagated down through Fabricator recipe inputs that are
    THEMSELVES a Fabricator output -- e.g. Control Unit needs Circuit Panel,
    which is its own Fabricator recipe. Without this, a target set only on
    Control Unit (the order's own required item) never tells any Fabricator
    to build Circuit Panel, so Control Unit -- and every other Fabricator
    recipe needing it -- stalls forever on an input nothing ever produces.
    Same shortfall-only propagation and depth bound as
    _cascade_blueprint_demand(); intermediate raw/refined materials (e.g.
    iron_ingot) are left to the Smelter demand (get_smelter_demands()) and
    the site supply ore requests (lib/site_supply.py), not duplicated here.

    Returns {item_id: target_quantity} for every reached item still short of
    stock, restricted to fabricator_outputs (Smelter-built intermediates
    aren't Fabricator targets -- get_smelter_demands() handles those).
    `stock` overrides the stock read (item_id -> units), e.g. one site's
    local stock for get_site_fabricator_targets().
    `supply(item_id, shortfall) -> units` (optional) says how much of a
    non-seed item's shortfall arrives from elsewhere (in flight or to be
    shipped, see get_site_fabricator_targets()): those units come off that
    item's target and are not cascaded into its inputs.
    """
    log.start("_cascade_fabricator_output_demand", level="debug")
    stock = stock or _stock_fn(cache)
    seeds = set(seed_targets)
    targets = {}
    frontier = dict(seed_targets)
    depth = 0
    while frontier and depth < 6:  # same generous bound as _cascade_blueprint_demand()
        depth += 1
        next_frontier = {}
        for item_id, want in frontier.items():
            shortfall = max(0, want - stock(item_id))
            covered = 0
            if supply is not None and shortfall > 0 and item_id not in seeds:
                covered = min(shortfall, supply(item_id, shortfall))
                shortfall -= covered
            if item_id in fabricator_outputs:
                targets[item_id] = max(targets.get(item_id, 0), want - covered)
            if shortfall <= 0:
                log.trace(f"_cascade_fabricator_output_demand depth={depth}: {item_id} has no shortfall (want={want}), not cascading further")
                continue
            inputs = _recipe_inputs_for(item_id, cache)
            if not inputs:
                continue
            for input_id, ratio in inputs.items():
                if input_id not in fabricator_outputs:
                    continue  # only cascade through other Fabricator-built intermediates
                next_frontier[input_id] = next_frontier.get(input_id, 0) + (shortfall * ratio)
                log.trace(f"_cascade_fabricator_output_demand depth={depth}: {item_id} shortfall={shortfall:.2f} cascades {ratio:.2f}x into {input_id} -> {next_frontier[input_id]:.2f}")
        frontier = next_frontier
    if depth >= 6 and frontier:
        log.debug(f"hit depth bound (6) with frontier still non-empty: {list(frontier.keys())}")
    log.end()
    return targets


def get_manual_order_blocking_items(fabricator_outputs, orders=None, cache=None):
    """
    Set of Fabricator-output item_ids that an active manual build order
    (get_manual_orders(), or the `orders` dict given instead -- e.g.
    get_upgrade_orders()) transitively needs as an INPUT -- e.g. machine_frame
    when a manual order asks for drone_service_station_kit -- excluding the
    manually-ordered item itself. Same shortfall-only breadth-first walk as
    _cascade_fabricator_output_demand(), just seeded from manual orders only
    and returning the reached item_ids rather than their quantities.

    A manual order jumps every other demanded recipe in choose_recipe()
    regardless of shortfall size (see get_fabricator_targets()'s docstring),
    but a manual order for e.g. drone_service_station_kit can't itself be
    built while machine_frame stock is 0 and nothing is producing it --
    can_source_item() only checks that SOME recipe path exists, not that
    anything is actually in flight, so a Fabricator holding that manual
    order kept re-selecting it forever instead of ever pivoting to build the
    missing intermediate. Items in this set outrank even the manual orders
    themselves in choose_recipe()'s priority order, since the manual order
    is provably stuck without them first.
    """
    log.start("get_manual_order_blocking_items", level="debug")
    manual_items = get_manual_orders() if orders is None else orders
    frontier = {item_id: qty for item_id, qty in manual_items.items() if item_id in fabricator_outputs}
    stock = _stock_fn(cache)
    blocking = set()
    depth = 0
    while frontier and depth < 6:  # same generous bound as the sibling cascades
        depth += 1
        next_frontier = {}
        for item_id, want in frontier.items():
            shortfall = max(0, want - stock(item_id))
            if shortfall <= 0:
                log.trace(f"get_manual_order_blocking_items depth={depth}: {item_id} has no shortfall (want={want}), not cascading further")
                continue
            inputs = _recipe_inputs_for(item_id, cache)
            if not inputs:
                continue
            for input_id, ratio in inputs.items():
                if input_id not in fabricator_outputs:
                    continue  # only cascade through other Fabricator-built intermediates
                blocking.add(input_id)
                next_frontier[input_id] = next_frontier.get(input_id, 0) + (shortfall * ratio)
                log.trace(f"get_manual_order_blocking_items depth={depth}: {item_id} shortfall={shortfall:.2f} cascades {ratio:.2f}x into {input_id} -> {next_frontier[input_id]:.2f}")
        frontier = next_frontier
    if depth >= 6 and frontier:
        log.debug(f"hit depth bound (6) with frontier still non-empty: {list(frontier.keys())}")
    log.end()
    return blocking


def _vehicle_cargo_counts(item_ids):
    """{item_id: units} of the given items currently aboard any ground
    vehicle (fleet.vehicles() + each vehicle's live cargo.stacks()). Only
    items with a non-zero count are returned."""
    counts = {}
    fleet = _component("fleet")
    if not fleet or not hasattr(fleet, "vehicles"):
        return counts
    try:
        refs = fleet.vehicles()
    except Exception as error:
        swallowed("production._vehicle_cargo_counts: fleet.vehicles", error)
        return counts
    for ref in refs:
        vehicle = _component(getattr(ref, "id", None))
        cargo = getattr(vehicle, "cargo", None) if vehicle else None
        if not cargo or not hasattr(cargo, "stacks"):
            continue
        try:
            for stack in cargo.stacks():
                item_id = getattr(stack, "id", None)
                if item_id in item_ids:
                    counts[item_id] = counts.get(item_id, 0) + (getattr(stack, "count", 0) or 0)
        except Exception as error:
            swallowed("production._vehicle_cargo_counts: cargo.stacks", error)
            continue
    return {k: v for k, v in counts.items() if v > 0}


def blueprint_required_items(cache=None):
    """{item_id: units} pending/paused Construction Blueprints still need as
    their own required_item (summed across jobs, deduped by job id), minus
    units already aboard vehicles. The seed of _walk_blueprint_demand().
    Memoized on `cache`."""
    if cache is not None and cache._blueprint_seeds is not None:
        return dict(cache._blueprint_seeds)
    frontier = {}
    bp = _component("construction_blueprint")
    if bp:
        seen_jobs = set()
        for getter_name in ("pending_constructions", "paused_constructions"):
            getter = getattr(bp, getter_name, None)
            if not getter:
                continue
            try:
                for job in getter():
                    job_id = getattr(job, "id", None)
                    if job_id and job_id in seen_jobs:
                        continue
                    item_id = getattr(job, "required_item", None)
                    count = getattr(job, "required_count", 0)
                    if not item_id or count <= 0:
                        continue
                    if job_id:
                        seen_jobs.add(job_id)
                    frontier[item_id] = frontier.get(item_id, 0) + count
            except Exception as error:
                swallowed("production.blueprint_required_items: getter", error)

    # A constructor Pioneer loads a whole batch for chained jobs before
    # driving out, and every job stays pending until actually built -- so
    # while the materials ride in its cargo they're in neither Inventory nor
    # a Warehouse, and the Fabricator re-crafted the full batch (seen live:
    # 3 Oil Pump blueprints -> 6 pumps built, 3 left over). Net those out.
    if frontier:
        for item_id, carried in _vehicle_cargo_counts(frontier).items():
            frontier[item_id] = max(0, frontier[item_id] - carried)
            log.trace(f"{carried}x {item_id} already aboard vehicles -> seed demand {frontier[item_id]}")
    if cache is not None:
        cache._blueprint_seeds = dict(frontier)
    return frontier


def _cascade_blueprint_demand(cache=None):
    """Memoized on `cache` (one blueprint + fleet cargo walk per pass) -- see _walk_blueprint_demand()."""
    if cache is None:
        return _walk_blueprint_demand(None)
    if cache._blueprint_demand is None:
        cache._blueprint_demand = _walk_blueprint_demand(cache)
    return dict(cache._blueprint_demand)


def _walk_blueprint_demand(cache):
    """
    Breadth-first demand cascade seeded from pending/paused Construction
    Blueprint required_item/required_count (summed across jobs, deduped by
    job id), then propagated down through Fabricator and Smelter recipe
    inputs -- e.g. a Thermal Cap build's thermal_cap_kit demand cascades into
    titanium_ingot demand, which cascades into titanium_ore demand.

    At each tier, only that tier's *shortfall* (demand beyond current total
    stock of that exact item, across Inventory and every Warehouse -- see
    storage.total_stock()) propagates further down -- so a build that's
    mostly already satisfied by existing stock at some tier doesn't overstate
    demand for the tiers beneath it. Returns {item_id: total_demand}, the
    gross demand accumulated for every item reached at any tier (not yet
    netted against its own stock -- see get_construction_material_reservations()
    for that).

    Known limitation: an item reachable via more than one distinct path
    (e.g. two different blueprint items both consuming iron_ingot) nets its
    shortfall against the same stock snapshot independently at each
    occurrence, which can slightly overstate demand for a shared
    intermediate under a diamond-shaped recipe dependency. Not worth a full
    MRP-style low-level-code solve for this game's shallow (2-3 tier)
    recipe chains.
    """
    log.start("_cascade_blueprint_demand", level="debug")
    frontier = blueprint_required_items(cache)

    stock = _stock_fn(cache)
    total_needed = {}
    depth = 0
    while frontier and depth < 6:  # generous bound against an accidental recipe cycle
        depth += 1
        next_frontier = {}
        for item_id, want in frontier.items():
            total_needed[item_id] = total_needed.get(item_id, 0) + want
            shortfall = max(0, want - stock(item_id))
            if shortfall <= 0:
                log.trace(f"_cascade_blueprint_demand depth={depth}: {item_id} has no shortfall (want={want}), not cascading further")
                continue
            inputs = _recipe_inputs_for(item_id, cache)
            if not inputs:
                continue
            for input_id, ratio in inputs.items():
                next_frontier[input_id] = next_frontier.get(input_id, 0) + (shortfall * ratio)
                log.trace(f"_cascade_blueprint_demand depth={depth}: {item_id} shortfall={shortfall:.2f} cascades {ratio:.2f}x into {input_id} -> {next_frontier[input_id]:.2f}")
        frontier = next_frontier

    if depth >= 6 and frontier:
        log.debug(f"hit depth bound (6) with frontier still non-empty: {list(frontier.keys())}")
    log.end()
    return total_needed


def get_construction_material_reservations(cache=None):
    """
    Returns {item_id: units} to protect (Inventory + every Warehouse -- see
    storage.total_stock()) for active Construction Blueprints, cascading down
    through Fabricator/Smelter recipes to intermediate materials and raw ore
    (see _cascade_blueprint_demand()) -- not just each blueprint's own
    required_item. Capped at min(current stock, total demand) per item: never
    reserves more than what's both actually on hand and actually still needed.

    Used to stop the Supply Dock from shipping away stock an active build (or
    the production chain feeding it) is waiting on -- see supply_dock.py
    step()/pick_best_order(). With a `cache`, reads its stock snapshot and
    memoized blueprint cascade.
    """
    reservations = {}
    stock_of = _stock_fn(cache)
    for item_id, want in _cascade_blueprint_demand(cache).items():
        stock = stock_of(item_id)
        reserve = min(stock, want)
        if reserve > 0:
            reservations[item_id] = reserve
    return reservations


_WARNED_UNKNOWN_MANUAL_ITEMS = set()


def get_fabricator_targets(cache=None):
    """Returns desired finished-goods quantities for Fabricator planning.

    With a `cache` (SourceCache), the result is memoized on it for the rest
    of that pass: this is the single most expensive demand helper (manual
    orders, every dock order, the blueprint cascade and the Fabricator output
    cascade, each walking stock), and get_material_demands() alone used to
    rebuild it once per Fabricator via get_fabricator_active_recipe(). A copy
    is returned so a caller mutating its result can't poison the memo."""
    log.start("get_fabricator_targets", level="debug")
    if cache is not None and cache._fabricator_targets is not None:
        _ret = dict(cache._fabricator_targets)
        log.end()
        return _ret

    targets, _consumers, fabricator_outputs = fabricator_root_targets(cache)

    # Cascade demand for a targeted Fabricator output down through its own
    # recipe inputs when those inputs are themselves Fabricator-built (e.g.
    # Control Unit needs Circuit Panel) -- see
    # _cascade_fabricator_output_demand(). Without this, an order/blueprint
    # target set only on the top-level item (Control Unit) never becomes a
    # target for the intermediate (Circuit Panel), so no Fabricator ever
    # builds it and the top-level item stalls forever waiting on stock that
    # nothing produces.
    for item_id, count in _cascade_fabricator_output_demand(targets, fabricator_outputs, cache).items():
        targets[item_id] = max(targets.get(item_id, 0), count)
        log.trace(f"output-demand cascade raises target for {item_id} -> {targets[item_id]} (cascaded={count})")

    log.trace(f"final targets={targets}")
    if cache is not None:
        cache._fabricator_targets = dict(targets)
    log.end()
    return targets


def fabricator_root_targets(cache=None):
    """
    (roots, consumers, fabricator_outputs): the root Fabricator targets
    before the intermediate cascade -- standing stock targets, manual orders,
    upgrade and backlog orders, Supply Dock orders and blueprint demand, max()-folded per
    item into {item_id: qty} -- plus {item_id: {site_id: qty}}, where each
    root is consumed (its Supply Dock's outpost for dock orders,
    construction_site_id() for a blueprint's own required_item, home for
    everything else; dock order items the Fabricator can't build and
    blueprint items included, for hauling), plus the set of
    Fabricator-buildable item ids.
    Memoized on `cache`.
    """
    log.start("fabricator_root_targets", level="debug")
    if cache is not None and cache._root_targets is not None:
        roots, consumers, outputs = cache._root_targets
        _ret = dict(roots), {i: dict(c) for i, c in consumers.items()}, set(outputs)
        log.end()
        return _ret

    targets = get_fabricator_stock_targets()
    home_id = home_outpost_id()
    home_wants = dict(targets)  # the non-dock roots, all consumed at home

    fabricator_outputs = set()
    if cache is not None:
        recipes = cache.fabricator_recipes()
    else:
        fabricator = _default_fabricator()
        try:
            recipes = fabricator.list_recipes() if fabricator and hasattr(fabricator, "list_recipes") else []
        except Exception as error:
            swallowed("production.get_fabricator_targets: fabricator.list_recipes", error)
            recipes = []
    for recipe in recipes:
        output_item = getattr(recipe, "output_item", None)
        if output_item:
            fabricator_outputs.add(output_item)

    # Manual build orders (get_manual_orders()) max()'d in like every other source below -- they
    # don't add to a standing target, they just guarantee at least this many exist. Priority over
    # other demanded recipes (build these first regardless of shortfall size) is handled separately
    # in lib/fabricator.py's choose_recipe(), which needs get_manual_orders() itself, not just the
    # folded-in quantity, to tell which candidates to jump ahead.
    #
    # A manual order is hand-typed straight into the Data Archive Notebook (no validation on
    # write), so a typo'd/renamed item_id (e.g. "small_drone" instead of "drone_small") silently
    # never matches any recipe's output_item -- it still gets folded into targets here, but no
    # Fabricator ever produces a candidate for it, and since nothing else was set either, the
    # machine prints nothing at all (see lib/fabricator.py's step()/choose_recipe()). Warn once per
    # script run so a bad key doesn't fail completely silently. fabricator_outputs only reflects
    # the default Fabricator's currently unlocked recipes, so this can false-positive for an item
    # only a different Fabricator (or a not-yet-unlocked recipe) can build -- it's a heads-up, not
    # proof the order is unfulfillable.
    for item_id, quantity in get_manual_orders().items():
        targets[item_id] = max(targets.get(item_id, 0), quantity)
        home_wants[item_id] = max(home_wants.get(item_id, 0), quantity)
        log.trace(f"get_fabricator_targets: manual order raises target for {item_id} -> {targets[item_id]}")
        if fabricator_outputs and item_id not in fabricator_outputs and item_id not in FUEL_ASSEMBLER_OUTPUTS and item_id not in _WARNED_UNKNOWN_MANUAL_ITEMS:
            _WARNED_UNKNOWN_MANUAL_ITEMS.add(item_id)
            log.level("warn").print(f"[production] Warning: fabricator.manual_orders has '{item_id}' ({quantity}x), which "
                  f"doesn't match any known Fabricator recipe output. Check for a typo/renamed item_id.")

    # Fleet upgrade orders (get_upgrade_orders()): same max() fold as manual
    # orders; their lower priority is again choose_recipe()'s job.
    for item_id, quantity in get_upgrade_orders().items():
        targets[item_id] = max(targets.get(item_id, 0), quantity)
        home_wants[item_id] = max(home_wants.get(item_id, 0), quantity)
        log.trace(f"get_fabricator_targets: fleet upgrade order raises target for {item_id} -> {targets[item_id]}")

    # Backlog orders (get_backlog_orders()): same fold; choose_recipe() ranks
    # the part above every other floor last (tier 5).
    for item_id, quantity in get_backlog_orders().items():
        targets[item_id] = max(targets.get(item_id, 0), quantity)
        home_wants[item_id] = max(home_wants.get(item_id, 0), quantity)
        log.trace(f"get_fabricator_targets: backlog order raises target for {item_id} -> {targets[item_id]}")

    order_sites = _dock_order_sites()
    consumers = {}
    for order_id, remaining_by_item in _dock_order_remaining().items():
        for item_id, remaining in remaining_by_item.items():
            for site_id in order_sites.get(order_id, (home_id,)):
                site = consumers.setdefault(item_id, {})
                site[site_id] = max(site.get(site_id, 0), remaining)
            # Only order items the Fabricator can actually build become
            # targets; other order items (raw/mined) are handled by
            # the dock demand loop in get_material_demands() and must
            # not be double-counted here.
            if item_id not in targets and item_id not in fabricator_outputs:
                continue
            targets[item_id] = max(targets.get(item_id, 0), remaining)
            log.trace(f"get_fabricator_targets: dock order {order_id} raises target for {item_id} -> {targets[item_id]} (remaining={remaining})")

    # Fold in Construction Blueprint demand for items the Fabricator can
    # actually build (e.g. thermal_cap_kit) -- a queued build could otherwise
    # sit forever with nothing ever telling the Fabricator to craft it. Uses
    # the raw demand cascade, not get_construction_material_reservations()'s
    # netted (capped-at-current-stock) numbers -- a target must reflect how
    # much still needs to exist, not how much can currently be reserved.
    # max()'d against the existing target, same as the Supply Dock order
    # handling above -- targets are a steady-state "keep at least N in
    # Inventory" floor, not additive per demand source: the standing stock
    # buffer IS what a blueprint (or order) draws from, and choose_recipe()
    # already nets target-vs-current to rebuild it after that draw, so
    # adding would just over-target and waste materials/time.
    for item_id, count in _cascade_blueprint_demand(cache).items():
        if item_id in fabricator_outputs:
            targets[item_id] = max(targets.get(item_id, 0), count)
            log.trace(f"get_fabricator_targets: blueprint cascade raises target for {item_id} -> {targets[item_id]} (cascaded={count})")

    # Stock targets and manual/upgrade/backlog orders are consumed at home
    # (Inventory side). A blueprint's own required_item is consumed where the
    # Constructor Pioneer loads it (construction_site_id()); the intermediates
    # beneath it are Fabricator inputs, consumed at whichever fab site builds
    # the item, so they are no consumer root.
    # Manual-order units built off home stay wanted at home until they arrive
    # (MANUAL_TRANSIT_KEY); no build target, they already exist.
    for item_id, qty in manual_transit_wants(cache).items():
        home_wants[item_id] = max(home_wants.get(item_id, 0), qty)
    for item_id, qty in home_wants.items():
        site = consumers.setdefault(item_id, {})
        site[home_id] = max(site.get(home_id, 0), qty)
    seeds = {i: n for i, n in blueprint_required_items(cache).items() if n > 0}
    if seeds:
        builder_site = construction_site_id()
        for item_id, qty in seeds.items():
            site = consumers.setdefault(item_id, {})
            site[builder_site] = max(site.get(builder_site, 0), qty)
            log.trace(f"fabricator_root_targets: blueprint needs {qty}x {item_id} at {builder_site}")

    if cache is not None:
        cache._root_targets = (dict(targets), {i: dict(c) for i, c in consumers.items()}, set(fabricator_outputs))
    log.end()
    return targets, consumers, fabricator_outputs


def get_fabricator_worker_ids(recipe_id, site_id=None):
    """
    Sorted ids of every discovered Fabricator currently holding recipe_id
    (get_recipe() == recipe_id) right now, only those at `site_id`
    (claim_site_id()) when given -- demand is per fab site
    (get_site_fabricator_targets()), so its split is too. A live roster, not
    an archive-tracked one, so it reflects joiners too (lib/fabricator.py's
    choose_recipe() lets a Fabricator "join" a recipe another one already
    holds the coordination claim on, when no other demanded recipe is
    available -- see its pile-on fallback). Sorted so every worker computes
    the same order, which get_fabricator_active_recipe() uses to hand out
    the split's remainder deterministically.
    """
    ids = []
    for fabricator_id in discover_fabricator_ids():
        candidate = _component(fabricator_id)
        if not candidate or not hasattr(candidate, "get_recipe"):
            continue
        try:
            if candidate.get_recipe() != recipe_id:
                continue
            if site_id is not None and claim_site_id(candidate) != site_id:
                continue
            ids.append(fabricator_id)
        except Exception as error:
            swallowed("production.get_fabricator_worker_ids: candidate.get_recipe", error)
    return sorted(ids)


def get_fabricator_worker_count(recipe_id, site_id=None):
    """
    How many discovered Fabricators (at `site_id` when given) currently have
    recipe_id selected -- see get_fabricator_worker_ids(). Used to split
    crafts_remaining fairly below: without this, every Fabricator working the
    same recipe would each independently load_inputs() for the FULL remaining
    shortfall, overshooting the target well before total_stock() catches up
    on the next poll. Returns at least 1 (the caller itself, even if the
    network walk finds nothing -- e.g. outpost_network unavailable).
    """
    return max(1, len(get_fabricator_worker_ids(recipe_id, site_id)))


def _pipeline_by_site(cache=None):
    """{site_id: {item_id: units}} finished or being finished inside the
    Fabricators at each site (claim_site_id()) but not yet in storage."""
    if cache is not None and cache._pipeline_by_site is not None:
        return cache._pipeline_by_site
    by_site = {}
    for fabricator_id in discover_fabricator_ids():
        fabricator = _component(fabricator_id)
        if not fabricator:
            continue
        pipeline = by_site.setdefault(claim_site_id(fabricator), {})
        try:
            output = getattr(fabricator, "output", None)
            if output and hasattr(output, "stacks"):
                for stack in output.stacks():
                    stack_item_id = getattr(stack, "id", None)
                    if stack_item_id:
                        pipeline[stack_item_id] = pipeline.get(stack_item_id, 0) + (getattr(stack, "count", 0) or 0)
            if hasattr(fabricator, "is_running") and fabricator.is_running():
                recipe_id = fabricator.get_recipe()
                recipe = fabricator.find_recipe(recipe_id) if recipe_id and hasattr(fabricator, "find_recipe") else None
                output_item = getattr(recipe, "output_item", None) if recipe else None
                if output_item:
                    pipeline[output_item] = pipeline.get(output_item, 0) + max(1, getattr(recipe, "output_count", 1))
        except Exception as error:
            swallowed("production._pipeline_by_site: output.stacks", error)
    log.trace(f"_pipeline_by_site: {by_site}")
    if cache is not None:
        cache._pipeline_by_site = by_site
    return by_site


def get_fabricator_pipeline(cache=None, site_id=None):
    """
    {item_id: units} already finished or being finished inside ANY Fabricator
    on the network (only those at `site_id` when given) but not yet in
    storage: every Fabricator's output-buffer stacks, plus one craft's output
    for each craft in progress (is_running()). Netted out of every "still
    needed" figure alongside total_stock().

    Used to be each Fabricator's OWN get_output_count() only. Peers' output
    buffers and every in-progress craft were invisible, so each Fabricator on
    a recipe kept building past the order (seen live: 7 surplus Oil Tank
    (Medium) after vestibule_15). Worst when Inventory is full: finished
    data-bearing items (oil tanks carry oilTons, one slot each) pile up in
    output bins where only their own Fabricator counted them.

    Memoized on `cache` (SourceCache) for the pass, like
    get_fabricator_targets() -- get_material_demands() asks once per
    Fabricator.
    """
    by_site = _pipeline_by_site(cache)
    if site_id is not None:
        return dict(by_site.get(site_id, {}))
    pipeline = {}
    for site_pipeline in by_site.values():
        for item_id, units in site_pipeline.items():
            pipeline[item_id] = pipeline.get(item_id, 0) + units
    return pipeline


# Fab sites (outposts with >= 1 Fabricator) and the per-site plan of which
# sites build each root target's tree -- written by the 5_steampower lib
# site_plan.py planner, read here by every Fabricator.
# Shape {root_item_id: [site_id, ...]}; a site listed first gets the remainder.
SITE_PLAN_KEY = "fabricator.site_plan"


def fab_site_counts(cache=None):
    """{site_id: Fabricators there} for every outpost with a Fabricator."""
    if cache is not None and cache._fab_sites is not None:
        return dict(cache._fab_sites)
    counts = {}
    for fabricator_id in discover_fabricator_ids():
        fabricator = _component(fabricator_id)
        if fabricator:
            site_id = claim_site_id(fabricator)
            counts[site_id] = counts.get(site_id, 0) + 1
    if cache is not None:
        cache._fab_sites = dict(counts)
    return counts


def split_units(units, site_ids, counts):
    """{site_id: whole units} splitting `units` across site_ids by Fabricator
    count (counts), floor plus remainder in site_ids order; sums to units."""
    weights = [(site_id, max(1, counts.get(site_id, 1))) for site_id in site_ids]
    total = sum(w for _s, w in weights)
    shares = {site_id: units * w // total for site_id, w in weights}
    left = units - sum(shares.values())
    for site_id, _w in weights:
        if left <= 0:
            break
        shares[site_id] += 1
        left -= 1
    return shares


def default_root_sites(consumer_sites, fab_sites):
    """Fallback site list for a root the planner hasn't placed yet: the fab
    site consuming it, else home when it has Fabricators, else the first fab
    site by id."""
    for site_id in sorted(consumer_sites or {}):
        if site_id in fab_sites:
            return [site_id]
    home_id = home_outpost_id()
    if home_id in fab_sites:
        return [home_id]
    return sorted(fab_sites)[:1]


def outpost_by_site_id(site_id):
    """OutpostRef with this id, None when not found."""
    for outpost in _all_outposts():
        if getattr(outpost, "id", None) == site_id:
            return outpost
    return None


def root_remaining(item_id, target, cache):
    """Units of a root target still to build anywhere: target minus stock
    anywhere on the network (cargo aboard haulers included) and every
    Fabricator's pipeline."""
    return max(0, target - cache.network_stock(item_id) - get_fabricator_pipeline(cache).get(item_id, 0))


def get_site_fabricator_targets(site_id, cache=None):
    """
    {item_id: target} for the Fabricators at one fab site, in the same
    "keep at least N" shape as get_fabricator_targets(). With Fabricators at
    home only, that is get_fabricator_targets() itself. Otherwise each root
    target (fabricator_root_targets()) builds at the sites SITE_PLAN_KEY
    lists for it (default_root_sites() until planned): its remaining units
    (root_remaining()) split by split_units(), and this site's share becomes
    a target of local stock + local pipeline + share. Intermediates cascade
    from those against this site's local stock only, so a site's stock
    counts only for its own trees. Memoized on `cache`.

    Ship-before-craft: an intermediate short at this site that sits spare
    at another outpost is hauled in instead of built when ship_units() says
    so. Units in flight to the site and units to ship come off its target;
    the units to ship are this site's ship plan (get_site_ship_plan(), which
    lib/site_supply.py publishes as requests). Roots are never shipped here.
    """
    cache = SourceCache() if cache is None else cache
    if site_id in cache._site_targets:
        return dict(cache._site_targets[site_id])
    if _single_fab_site(cache):
        targets = get_fabricator_targets(cache)
        cache._site_targets[site_id] = dict(targets)
        cache._site_ship_plan[site_id] = {}
        return targets

    log.start(f"get_site_fabricator_targets({site_id})", level="debug")
    seed, fabricator_outputs, outpost = _site_seed(site_id, cache)
    flying = in_flight(site_id)
    ship_plan = {}

    def local(item_id):
        return cache.held_stock(item_id, outpost)

    def supply(item_id, shortfall):
        coming = min(shortfall, flying.get(item_id, 0))
        ship = ship_units(item_id, shortfall - coming, outpost, site_id, cache)
        if ship > 0:
            ship_plan[item_id] = max(ship_plan.get(item_id, 0), ship)
        return coming + ship

    targets = dict(seed)
    for item_id, count in _cascade_fabricator_output_demand(seed, fabricator_outputs, cache, stock=local, supply=supply).items():
        targets[item_id] = max(targets.get(item_id, 0), count)
    cache._site_targets[site_id] = dict(targets)
    cache._site_ship_plan[site_id] = ship_plan
    if ship_plan:
        log.debug(f"ship plan {ship_plan}")
    log.end()
    return targets


def get_site_ship_plan(site_id, cache=None):
    """{item_id: units} this site should have hauled in rather than build --
    see get_site_fabricator_targets()."""
    cache = SourceCache() if cache is None else cache
    get_site_fabricator_targets(site_id, cache)
    return dict(cache._site_ship_plan.get(site_id, {}))


def _single_fab_site(cache):
    """True when every Fabricator is at home (site targets = global targets)."""
    return set(fab_site_counts(cache)) <= {home_outpost_id(), HOME_OUTPOST_ID}


def _site_seed(site_id, cache):
    """(seed, fabricator_outputs, outpost): this site's root targets -- each
    root's remaining units split across the sites planned for it, as local
    stock + local pipeline + share."""
    fab_sites = fab_site_counts(cache)
    roots, consumers, fabricator_outputs = fabricator_root_targets(cache)
    plan = archive.get(SITE_PLAN_KEY, {}) or {}
    outpost = outpost_by_site_id(site_id)
    pipeline = get_fabricator_pipeline(cache, site_id)
    seed = {}
    for item_id, target in roots.items():
        if item_id not in fabricator_outputs:
            continue
        remaining = root_remaining(item_id, target, cache)
        if remaining <= 0:
            continue
        planned = plan.get(item_id) if isinstance(plan, dict) else None
        sites = [s for s in (planned or []) if s in fab_sites] or default_root_sites(consumers.get(item_id), fab_sites)
        share = split_units(remaining, sites, fab_sites).get(site_id, 0)
        if share > 0:
            seed[item_id] = cache.held_stock(item_id, outpost) + pipeline.get(item_id, 0) + share
            log.debug(f"root {item_id} remaining={remaining} sites={sites} -> share={share}, target={seed[item_id]}")
    return seed, fabricator_outputs, outpost


def _site_base_targets(site_id, cache):
    """A site's targets without ship-before-craft (only local stock nets):
    what that site keeps for its own trees when another site asks for its
    spare (site_spare_elsewhere()). Memoized on `cache`."""
    if site_id in cache._site_base_targets:
        return cache._site_base_targets[site_id]
    if _single_fab_site(cache):
        targets = get_fabricator_targets(cache)
    else:
        seed, fabricator_outputs, outpost = _site_seed(site_id, cache)
        targets = dict(seed)
        for item_id, count in _cascade_fabricator_output_demand(seed, fabricator_outputs, cache, stock=lambda i: cache.held_stock(i, outpost)).items():
            targets[item_id] = max(targets.get(item_id, 0), count)
    cache._site_base_targets[site_id] = targets
    return targets


def _recipe_for_output(item_id, cache):
    """("fabricator"|"smelter", Recipe) building item_id, (None, None) when none does."""
    for kind, recipes in (("fabricator", cache.fabricator_recipes()), ("smelter", cache.smelter_recipes())):
        for recipe in recipes:
            if getattr(recipe, "output_item", None) == item_id:
                return kind, recipe
    return None, None


def _site_has_machine(kind, outpost, cache):
    """True when `outpost` has at least one Fabricator/Smelter (kind). Memoized on `cache`."""
    key = f"{getattr(outpost, 'id', None)}|{kind}"
    if key not in cache._site_machines:
        ids = discover_fabricator_ids(outpost) if kind == "fabricator" else discover_smelter_ids(outpost)
        cache._site_machines[key] = bool(ids)
    return cache._site_machines[key]


def local_make_seconds(item_id, units, outpost, cache, depth=0):
    """
    Real seconds to make `units` of item_id at `outpost` from its local
    stock: crafts x craft_seconds() of its Fabricator/Smelter recipe, plus
    making every input the site doesn't hold enough of the same way. None
    when the site can't (no machine of that kind there, or an input that no
    recipe makes -- raw ore -- is missing). Fluid inputs count as available.
    One machine's time: parallel Fabricators are not credited.
    """
    if units <= 0:
        return 0.0
    if depth >= 6:
        return None
    kind, recipe = _recipe_for_output(item_id, cache)
    if recipe is None or not _site_has_machine(kind, outpost, cache):
        return None
    crafts = _ceil(units / max(1, getattr(recipe, "output_count", 1) or 1))
    seconds = crafts * craft_seconds(recipe)
    for input_id, per_craft in (getattr(recipe, "inputs", {}) or {}).items():
        missing = crafts * per_craft - cache.local_stock(input_id, outpost)
        if missing <= 0:
            continue
        sub = local_make_seconds(input_id, missing, outpost, cache, depth + 1)
        if sub is None:
            return None
        seconds += sub
    return seconds


def site_spare_elsewhere(item_id, site_id, cache):
    """
    Units of item_id free for site_id at every other outpost: the
    outpost_free_tiers() need tier (storage minus what that outpost's own
    requests keep and other haulers reserved), minus what another fab site
    keeps for its own targets (_site_base_targets()). Memoized on `cache`.
    """
    key = f"{site_id}|{item_id}"
    if key in cache._spare_elsewhere:
        return cache._spare_elsewhere[key]
    if cache._requests is None:
        cache._requests = active_requests()
    fab_sites = fab_site_counts(cache)
    total = 0
    for outpost in _all_outposts():
        other_id = getattr(outpost, "id", None)
        if other_id is None or other_id == site_id:
            continue
        for_need, _for_buffer = outpost_free_tiers(outpost, [item_id], cache._requests)
        free = for_need.get(item_id, 0)
        if free > 0 and other_id in fab_sites:
            keep = min(cache.local_stock(item_id, outpost), _site_base_targets(other_id, cache).get(item_id, 0))
            free -= keep
        total += max(0, int(free))
    cache._spare_elsewhere[key] = total
    return total


def ship_units(item_id, shortfall, outpost, site_id, cache):
    """
    Units of a site's shortfall of item_id to haul in instead of making
    them: min(shortfall, spare elsewhere) when spare >= SHIP_SURPLUS_FACTOR
    x shortfall, or when the site can't make it locally
    (local_make_seconds() None) or only in >= SHIP_OVER_CRAFT_SECONDS;
    0 otherwise (make it locally). Delivery time is not estimated.
    """
    log.start(f"ship_units({site_id})", level="debug")
    shortfall = _ceil(shortfall) if shortfall > 0 else 0
    if shortfall <= 0:
        log.end()
        return 0
    spare = site_spare_elsewhere(item_id, site_id, cache)
    if spare <= 0:
        log.debug(f"{item_id} short={shortfall}, nothing spare elsewhere -> make")
        log.end()
        return 0
    ship = min(shortfall, spare)
    if spare >= SHIP_SURPLUS_FACTOR * shortfall:
        log.debug(f"{item_id} short={shortfall} spare={spare} >= {SHIP_SURPLUS_FACTOR}x -> ship {ship} (surplus)")
        log.end()
        return ship
    seconds = local_make_seconds(item_id, shortfall, outpost, cache)
    if seconds is None:
        log.debug(f"{item_id} short={shortfall} spare={spare}, can't make locally -> ship {ship}")
        log.end()
        return ship
    if seconds >= SHIP_OVER_CRAFT_SECONDS:
        log.debug(f"{item_id} short={shortfall} spare={spare}, local make {seconds:.0f}s >= {SHIP_OVER_CRAFT_SECONDS}s -> ship {ship}")
        log.end()
        return ship
    log.debug(f"{item_id} short={shortfall} spare={spare}, local make {seconds:.0f}s < {SHIP_OVER_CRAFT_SECONDS}s -> make")
    log.end()
    return 0


def get_smelter_worker_count(recipe_id):
    """
    Live headcount of discovered Smelters currently holding recipe_id
    (get_recipe() == recipe_id) right now -- mirrors get_fabricator_worker_count()
    exactly, same reasoning, for lib/smelter.py's ore-intake cap: with several
    Smelters "joined" on the same recipe (select_needed_ore()'s pile-on
    fallback, used whenever only one ore is currently demanded), each one
    independently topping its own 50-unit ore buffer up to the FULL current
    demand overshoots badly once you have more than one -- e.g. two Smelters
    each independently filling to a demand of 50 produces 100, not 50. Public
    (like get_fabricator_worker_count(), which lib/fabricator.py uses) since
    lib/smelter.py needs it directly. Returns at least 1.
    """
    count = 0
    for smelter_id in discover_smelter_ids():
        candidate = _component(smelter_id)
        if not candidate or not hasattr(candidate, "get_recipe"):
            continue
        try:
            if candidate.get_recipe() == recipe_id:
                count += 1
        except Exception as error:
            swallowed("production.get_smelter_worker_count: candidate.get_recipe", error)
    return max(1, count)


def get_fabricator_active_recipe(fabricator=None, cache=None):
    """Returns (recipe, crafts_remaining) for the Fabricator's selected recipe,
    where crafts_remaining covers the full remaining shortfall against its
    site's output target (get_site_fabricator_targets(), not just one craft's
    worth), net of the site's local stock and its Fabricators' pipeline
    (get_fabricator_pipeline()), divided across every Fabricator at the same
    site currently working this same recipe (see get_fabricator_worker_ids())
    so several Fabricators piled onto one large order split its remaining
    work instead of each independently re-loading the full shortfall. The
    split is floor-plus-remainder: the first (crafts % workers) ids in
    sorted order get one extra craft, so the shares sum to exactly
    crafts_remaining. A worker can get 0 and idles until demand changes."""
    if fabricator is None:
        fabricator = _default_fabricator()
    if not fabricator or not hasattr(fabricator, "get_recipe") or not hasattr(fabricator, "list_recipes"):
        return None, 0
    try:
        current_recipe_id = fabricator.get_recipe()
        if not current_recipe_id:
            return None, 0
        recipe = next((r for r in fabricator.list_recipes() if getattr(r, "id", None) == current_recipe_id), None)
        if not recipe:
            return None, 0
        cache = SourceCache() if cache is None else cache
        site_id = claim_site_id(fabricator)
        output_item = getattr(recipe, "output_item", None)
        output_count = max(1, getattr(recipe, "output_count", 1))
        current = cache.held_stock(output_item, getattr(fabricator, "outpost", None))
        in_pipeline = get_fabricator_pipeline(cache, site_id).get(output_item, 0)
        fabricator_id = getattr(fabricator, "id", None)
        log.start(f"get_fabricator_active_recipe({fabricator_id or '?'})", level="debug")
        target = get_site_fabricator_targets(site_id, cache).get(output_item, 0)
        still_needed = max(0, target - current - in_pipeline)
        crafts_remaining = -(-still_needed // output_count)  # ceil division
        worker_ids = get_fabricator_worker_ids(current_recipe_id, site_id)
        if len(worker_ids) > 1:
            pre_split = crafts_remaining
            if fabricator_id in worker_ids:
                share, extra = divmod(crafts_remaining, len(worker_ids))
                crafts_remaining = share + (1 if worker_ids.index(fabricator_id) < extra else 0)
            else:
                crafts_remaining = -(-crafts_remaining // len(worker_ids))  # id unknown: old ceil split, overshoots at most workers-1
            log.debug(f"recipe={current_recipe_id} split {pre_split} crafts across {len(worker_ids)} workers {worker_ids} -> {crafts_remaining} for this one")
        log.debug(f"site={site_id} recipe={current_recipe_id} output={output_item} target={target} current={current} in_pipeline={in_pipeline} still_needed={still_needed} crafts_remaining={crafts_remaining}")
        log.end()
        return recipe, crafts_remaining
    except Exception as error:
        swallowed("production.get_fabricator_active_recipe: fabricator.get_recipe", error)
        return None, 0


def get_material_demands(cache=None):
    """Returns material quantities currently requested by production and shipping.

    NOTE: for Smelter outputs (ingots, glass, ...) this only sees the direct
    inputs of each Fabricator's *currently selected* recipe -- lib/smelter.py
    uses get_smelter_demands() instead, which follows the whole order tree."""
    log.start("get_material_demands", level="debug")
    stock = _stock_fn(cache)
    demands = {}

    # Finished fabricated goods have a standing building-stock target and
    # may also be required by the active Supply Dock order.
    for item_id, target in get_fabricator_targets(cache).items():
        current = stock(item_id)
        deficit = max(0, target - current)
        _add_demand(demands, item_id, deficit)
        if deficit > 0:
            log.trace(f"{item_id} stock={current} target={target} -> deficit={deficit}")

    # Every Fabricator's own selected recipe is an explicit production
    # intention; scale by every remaining craft still needed to reach the
    # target, not just one craft's worth, or demand collapses to 0 as soon as
    # a single unit of an input is on hand even though hundreds more crafts
    # remain. Looping every discovered Fabricator (not just _default_fabricator())
    # matters as soon as a second one exists: with several Fabricators each
    # holding a DIFFERENT claimed recipe (see lib/fabricator.py's
    # claim_recipe()), only ever reading the first one's active recipe left
    # every other Fabricator's own input demand invisible here -- e.g.
    # fabricator_2 running craft_gas_pipe_segment (needs iron_ingot) never
    # registered any iron_ingot demand while fabricator_1 was busy on a
    # different recipe, so the Smelter never saw a reason to refine more,
    # even with raw ore sitting in a Warehouse. So every discovered Fabricator
    # counts here, like Smelter/Supply Dock discovery elsewhere in this file.
    fabricator_ids = discover_fabricator_ids() or ["fabricator_1"]
    for fabricator_id in fabricator_ids:
        fabricator = _component(fabricator_id)
        if not fabricator:
            continue
        recipe, crafts_remaining = get_fabricator_active_recipe(fabricator, cache)
        if not recipe or crafts_remaining <= 0:
            log.trace(f"{fabricator_id} has no active recipe/crafts remaining, skipping input demand")
            continue
        try:
            stockpile = fabricator.get_stockpile() or {}
            for item_id, required in (getattr(recipe, "inputs", {}) or {}).items():
                missing = (required * crafts_remaining) - stockpile.get(item_id, 0)
                missing -= stock(item_id)
                missing = max(0, missing)
                _add_demand(demands, item_id, missing)
                if missing > 0:
                    log.trace(f"{fabricator_id} recipe={getattr(recipe, 'id', '?')} needs {item_id} -> deficit={missing} (crafts_remaining={crafts_remaining})")
        except Exception as error:
            swallowed("production.get_material_demands: fabricator.get_stockpile", error)

    # Every dock's active order is a current downstream shipping requirement.
    for order_id, remaining_by_item in _dock_order_remaining().items():
        for item_id, remaining in remaining_by_item.items():
            missing = max(0, remaining - stock(item_id))
            _add_demand(demands, item_id, missing)
            if missing > 0:
                log.trace(f"order {order_id} needs {item_id} -> deficit={missing}")

    log.trace(f"final demands={demands}")
    log.end()
    return demands


def get_smelter_demands(cache=None):
    """
    {smelter_output_item: units_still_to_refine} -- what lib/smelter.py
    should actually produce, following the WHOLE order tree down to Smelter
    outputs (ingots, glass, ...), not just the direct inputs of whatever
    recipe a Fabricator happens to have selected right now.

    get_material_demands() only sees ingot demand through each Fabricator's
    get_fabricator_active_recipe() (already split per worker, each share
    netted against the full total_stock() separately), and
    _cascade_fabricator_output_demand() stops at Smelter outputs. So a large
    order reads as ~1 ingot there. This walks the whole order tree instead,
    so Smelters see the real ore demand.

    Gross-then-net-once:
      1. Every get_fabricator_targets() entry (manual orders, stock targets,
         docks, blueprints, and the Fabricator-intermediate cascade -- which
         already propagates a top-level order's shortfall into every
         Fabricator-built intermediate's own target) with a deficit D
         contributes D x ratio for each of its recipe inputs that is a
         Smelter output. Each Fabricator output's own direct ingot use is
         distinct, so summing these doesn't double-count.
      2. A target set directly on a Smelter output (a standing stock target,
         or a dock order get_fabricator_targets() already folded in) counts
         as gross need as-is.
      3. Dock orders for Smelter outputs NOT already covered by (2).
      4. Net once: minus stock anywhere on the network (home Inventory +
         every outpost's Warehouses + hauler cargo, SourceCache.network_stock(), so ingots
         a remote Smelter made aren't refined again at home) and minus what's
         already staged in every Fabricator's stockpile.

    Pass the step's SourceCache -- this walks the full target set, so it is
    not cheap uncached.
    """
    cache = SourceCache() if cache is None else cache
    smelter_outputs = {getattr(r, "output_item", None) for r in cache.smelter_recipes()}
    smelter_outputs.discard(None)
    if not smelter_outputs:
        return {}

    log.start("get_smelter_demands", level="debug")
    gross = {}
    targets = get_fabricator_targets(cache)
    for item_id, target in targets.items():
        if item_id in smelter_outputs:
            _add_demand(gross, item_id, target)
            log.trace(f"direct target on smelter output {item_id} -> gross += {target}")
            continue
        deficit = target - cache.network_stock(item_id)
        if deficit <= 0:
            continue
        for input_id, ratio in (_recipe_inputs_for(item_id, cache) or {}).items():
            if input_id in smelter_outputs:
                need = _ceil(deficit * ratio)
                _add_demand(gross, input_id, need)
                log.trace(f"{item_id} deficit={deficit} x {ratio:.2f} -> {input_id} gross += {need}")

    for order_id, remaining_by_item in _dock_order_remaining().items():
        for item_id, remaining in remaining_by_item.items():
            if item_id not in smelter_outputs or item_id in targets:
                continue  # not ours, or already counted via get_fabricator_targets()
            _add_demand(gross, item_id, remaining)
            if remaining > 0:
                log.trace(f"order {order_id} still needs {remaining}x {item_id}")

    staged = {}
    for fabricator_id in discover_fabricator_ids():
        fabricator = _component(fabricator_id)
        if not fabricator or not hasattr(fabricator, "get_stockpile"):
            continue
        try:
            for item_id, count in (fabricator.get_stockpile() or {}).items():
                if item_id in gross:
                    staged[item_id] = staged.get(item_id, 0) + count
        except Exception as error:
            swallowed("production.get_smelter_demands: (fabricator.get_stockpile() or {}).items", error)

    demands = {}
    for item_id, qty in gross.items():
        stock = cache.network_stock(item_id)
        net = qty - stock - staged.get(item_id, 0)
        if net > 0:
            demands[item_id] = net
        log.debug(f"{item_id} gross={qty} network_stock={stock} staged_in_fabricators={staged.get(item_id, 0)} -> net={max(0, net)}")
    log.end()
    return demands


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
            swallowed("production.fab_site_gross_need: fabricator.get_stockpile", error)
            stockpile = {}
        for item_id, per_craft in (getattr(recipe, "inputs", {}) or {}).items():
            if item_id not in smelter_outputs:
                continue
            missing = per_craft * crafts_remaining - stockpile.get(item_id, 0)
            if missing > 0:
                need[item_id] = need.get(item_id, 0) + missing
    return need


def site_smelter_demands(outpost, cache=None):
    """
    {smelter_output: units} a site's own Fabricators still need
    (fab_site_gross_need()) minus that output's local stock and units in
    flight to the site. lib/smelter.py merges it (per item max) with
    get_smelter_demands() for every Smelter, home included: the network-wide
    figure nets against stock anywhere, so it misses a site short of an
    output that sits at another outpost.
    """
    cache = SourceCache() if cache is None else cache
    smelter_outputs = {getattr(r, "output_item", None) for r in cache.smelter_recipes()}
    smelter_outputs.discard(None)
    if not smelter_outputs:
        return {}
    gross = fab_site_gross_need(discover_fabricator_ids(outpost), smelter_outputs, cache)
    if not gross:
        return {}
    flying = in_flight(getattr(outpost, "id", None))
    demands = {}
    log.start(f"site_smelter_demands({getattr(outpost, 'id', None)})", level="debug")
    for item_id, units in gross.items():
        local = cache.local_stock(item_id, outpost)
        net = units - local - flying.get(item_id, 0)
        if net > 0:
            demands[item_id] = net
        log.debug(f"{item_id} gross={units} local={local} in_flight={flying.get(item_id, 0)} -> net={max(0, net)}")
    log.end()
    return demands


# Fab-site ingot buffer: every outpost with a Fabricator keeps each Smelter
# output a Fabricator recipe takes on hand, so a recipe switch finds its
# ingots staged instead of waiting on single Smelter crafts. "target" is the
# buffer tier (local Smelters refill it in idle time, site_supply requests
# it), "need" the need tier hauled ahead of other sites' buffers. Seeded once
# per item, then editable: {item_id: {"target": n, "need": n}}.
INGOT_STOCK_TARGETS_KEY = "production.ingot_stock_targets"
INGOT_STOCK_TARGET = 2000
INGOT_STOCK_NEED = 100


def _ingot_level(entry, key, default):
    """entry[key] as a non-negative int (one INGOT_STOCK_TARGETS_KEY entry), else default."""
    value = entry.get(key) if isinstance(entry, dict) else None
    if value is None or not isinstance(value, (int, float)) or value < 0:
        return default
    return int(value)


def ingot_stock_levels(item_ids):
    """{item_id: (target, need)} from INGOT_STOCK_TARGETS_KEY, seeding the
    INGOT_STOCK_TARGET/INGOT_STOCK_NEED defaults for any item not stored yet."""
    stored = archive.get(INGOT_STOCK_TARGETS_KEY, {})
    stored = stored if isinstance(stored, dict) else {}
    missing = [i for i in item_ids if not isinstance(stored.get(i), dict)]
    if missing:
        def updater(levels):
            levels = dict(levels) if isinstance(levels, dict) else {}
            for item_id in missing:
                if not isinstance(levels.get(item_id), dict):
                    levels[item_id] = {"target": INGOT_STOCK_TARGET, "need": INGOT_STOCK_NEED}
            return levels
        archive.transaction(INGOT_STOCK_TARGETS_KEY, {}, updater)
        log.debug(f"ingot_stock_levels: seeded defaults for {missing}")
        stored = archive.get(INGOT_STOCK_TARGETS_KEY, {})
        stored = stored if isinstance(stored, dict) else {}
    levels = {}
    for item_id in item_ids:
        target = _ingot_level(stored.get(item_id), "target", INGOT_STOCK_TARGET)
        need = _ingot_level(stored.get(item_id), "need", INGOT_STOCK_NEED)
        levels[item_id] = (target, min(need, target))
    return levels


def fab_site_ingot_targets(outpost, cache):
    """{smelter_output: (target, need)} the ingot buffer this outpost keeps:
    every Smelter output some Fabricator recipe takes as input, {} when the
    outpost has no Fabricator."""
    if not discover_fabricator_ids(outpost):
        return {}
    smelter_outputs = {getattr(r, "output_item", None) for r in cache.smelter_recipes()}
    smelter_outputs.discard(None)
    inputs = set()
    for recipe in cache.fabricator_recipes():
        inputs |= set(getattr(recipe, "inputs", {}) or {})
    items = sorted(smelter_outputs & inputs)
    return ingot_stock_levels(items) if items else {}


def site_ingot_refill(outpost, cache):
    """{smelter_output: units} this fab site's ingot buffer still lacks:
    target - local stock - units in flight here. lib/smelter.py works it only
    when no real demand is sourceable."""
    targets = fab_site_ingot_targets(outpost, cache)
    if not targets:
        return {}
    flying = in_flight(getattr(outpost, "id", None))
    refill = {}
    for item_id, (target, _need) in targets.items():
        units = target - cache.local_stock(item_id, outpost) - flying.get(item_id, 0)
        if units > 0:
            refill[item_id] = units
    return refill


def dock_remaining_requirements(outpost_id=None):
    """{item_id: units} still owed (required - shipped - already loaded into
    the dock) across every active Supply Dock order. With `outpost_id`, only
    orders held by a dock at that outpost (_dock_order_sites(); an order held
    at two outposts counts at both). lib/smelter.py subtracts its own site's
    figure from raw ore it may refine, so real ingot demand can't eat ore a
    dock order ships raw."""
    sites = _dock_order_sites() if outpost_id is not None else None
    remaining_by_item = {}
    for order_id, remaining_for_order in _dock_order_remaining().items():
        if sites is not None and outpost_id not in sites.get(order_id, ()):
            continue
        for item_id, remaining in remaining_for_order.items():
            _add_demand(remaining_by_item, item_id, remaining)
    return remaining_by_item


def smelter_recipe_peers(recipe_id, outpost_id=None):
    """(worker_count, buffered_units) across every discovered Smelter currently
    holding recipe_id -- get_smelter_worker_count() plus the sum of their
    input buffers, in one walk. With `outpost_id`, only Smelters deployed at
    that outpost count: they draw from the same local ore pool, which is what
    lib/smelter.py's fair-share cap splits ((available ore + everything
    already buffered by these peers) // workers). Without it, every Smelter
    on the network counts, which is what splitting network-wide demand
    needs. worker_count is at least 1."""
    count = 0
    buffered = 0
    for smelter_id in discover_smelter_ids():
        candidate = _component(smelter_id)
        if not candidate or not hasattr(candidate, "get_recipe"):
            continue
        try:
            if candidate.get_recipe() != recipe_id:
                continue
            if outpost_id is not None and machine_outpost_id(candidate) != outpost_id:
                continue
            count += 1
            buffered += candidate.get_input_count() if hasattr(candidate, "get_input_count") else 0
        except Exception as error:
            swallowed("production.smelter_recipe_peers: candidate.get_recipe", error)
    return max(1, count), buffered


class SourceCache:
    """
    Per-pass memo for can_source_item()/can_source_fluid()'s underlying
    game-API lookups (Smelter/Fabricator discovery + list_recipes(),
    outpost.buildings() for fluid sources, journal.surveyed_sites(), a
    one-shot Inventory+Warehouse stock snapshot) plus the
    can_source_item()/can_source_fluid() results themselves.

    Each of those lookups is a real call across the script/game boundary.
    Threading a shared SourceCache through multiple checks (Supply Dock's
    plan_dock_assignments() across every order and dock, Fabricator's
    choose_recipe() across every candidate recipe) means each underlying
    game call happens at most once per pass. A sub-item shared by several
    recipes/orders (e.g. Steel) gets resolved once instead of re-walked from
    scratch down every branch.

    Discard it once the pass finishes -- it's a snapshot of build/tech state
    that can change between ticks, not something to hold onto across calls.
    """

    def __init__(self):
        self._smelter_recipes = None
        self._fabricator_recipes = None
        self._fluid_results = {}
        self._item_results = {}
        self._item_stack = set()
        self._surveyed_sites = None
        self._surveyed_minerals = None  # surveyed_minerals() memo
        self._sourcing_index = None  # {output_item: [recipes]}, sourcing_recipes() memo
        self._stock_map = None
        self._building_stock = None  # {source_id: {item_id: units}}, filled alongside _stock_map
        self._fabricator_targets = None  # get_fabricator_targets() memo -- see its docstring
        self._root_targets = None  # fabricator_root_targets() memo
        self._site_targets = {}  # {site_id: get_site_fabricator_targets()} memo
        self._site_base_targets = {}  # {site_id: _site_base_targets()} memo
        self._site_ship_plan = {}  # {site_id: {item_id: units}}, filled by get_site_fabricator_targets()
        self._spare_elsewhere = {}  # {"site_id|item_id": units}, site_spare_elsewhere() memo
        self._site_machines = {}  # {"outpost_id|kind": bool}, _site_has_machine() memo
        self._requests = None  # logistics_requests.active_requests() snapshot
        self._fab_sites = None  # fab_site_counts() memo
        self._pipeline_by_site = None  # {site_id: {item_id: units}}, get_fabricator_pipeline() memo
        self._outpost_stock = {}  # {outpost_id: {item_id: units}} for non-home outposts, see local_stock()
        self._depot_stock = {}  # {outpost_id: {item_id: units}} in Drone Depot stockpiles, see held_stock()
        self._remote_outposts = None  # non-home OutpostRefs, see network_stock()
        self._aboard = None  # logistics_requests.aboard_units() snapshot, see network_stock()
        self._blueprint_demand = None  # _cascade_blueprint_demand() memo
        self._blueprint_seeds = None  # blueprint_required_items() memo
        self._recipe_index = None  # _recipe_index() for this pass
        self._fuel_assembler_recipes = None
        self._cask_stock = {}  # {item_id: units in every Lead Cask}

    def _build_stock_map(self):
        log.start("SourceCache._build_stock_map", level="debug")
        log.trace("one-shot stock scan across Inventory + Warehouses starting")
        """One .stacks() call per Inventory/Warehouse -- each returns that
        building's ENTIRE contents in one shot -- summed by item id into a
        single {item_id: total_units} snapshot for the whole pass. Calling
        stock(item_id) per distinct item instead (total_stock()'s normal
        per-item .count(item_id) shape) would still cost one call per
        building per distinct item; a single .stacks() sweep per building up
        front replaces that with one call per building, period, no matter how
        many distinct items this pass ends up checking. The same sweep also
        fills the per-building breakdown building_stock() serves (used by
        storage.take_item() to pick which holder to pull from), at no extra
        game calls."""
        totals = {}
        per_building = {}
        sources = [("inventory", _component("inventory"))] + [(b["id"], b["component"]) for b in discover_storage_buildings()]
        for source_id, component in sources:
            if not component or not hasattr(component, "stacks"):
                continue
            held = per_building.setdefault(source_id, {})
            try:
                for stack in component.stacks():
                    stack_item_id = getattr(stack, "id", None)
                    if stack_item_id:
                        count = getattr(stack, "count", 0)
                        totals[stack_item_id] = totals.get(stack_item_id, 0) + count
                        held[stack_item_id] = held.get(stack_item_id, 0) + count
            except Exception as error:
                swallowed("production.SourceCache._build_stock_map: component.stacks", error)
        # Crop Automators keep their Forage in their own output (lib/storage.py),
        # which take_item() pulls from directly. Counted in totals only:
        # building_stock() stays Inventory/Warehouse.
        forage = crop_automator_forage_total()
        if forage > 0:
            totals[CROP_AUTOMATOR_ITEM_ID] = totals.get(CROP_AUTOMATOR_ITEM_ID, 0) + forage
        self._building_stock = per_building
        log.trace(f"scanned {len(sources)} storage components, {len(totals)} distinct items")
        log.end()
        return totals

    def stock(self, item_id):
        """Item's total units across Inventory + every Warehouse (+ Crop
        Automator outputs for Forage), from this pass's one-shot stock
        snapshot -- see _build_stock_map()."""
        if self._stock_map is None:
            self._stock_map = self._build_stock_map()
        return self._stock_map.get(item_id, 0)

    def building_stock(self, item_id):
        """[(source_id, units), ...] for every home storage endpoint ("inventory"
        or a Warehouse id) holding item_id, from the same one-shot snapshot as
        stock(). Unordered -- storage.take_item() applies its own priority."""
        if self._stock_map is None:
            self._stock_map = self._build_stock_map()
        return [
            (source_id, held[item_id])
            for source_id, held in (self._building_stock or {}).items()
            if held.get(item_id, 0) > 0
        ]

    def local_stock(self, item_id, outpost=None):
        """Units of item_id a machine at `outpost` can reach: stock() at home
        (Inventory + home Warehouses), only that outpost's own Warehouses
        elsewhere (Inventory is home-only). One .stacks() sweep per remote
        outpost per pass, like _build_stock_map()."""
        if outpost_is_home(outpost):
            return self.stock(item_id)
        outpost_id = getattr(outpost, "id", None)
        held = self._outpost_stock.get(outpost_id)
        if held is None:
            held = {}
            for building in discover_storage_buildings(outpost):
                component = building["component"]
                if not component or not hasattr(component, "stacks"):
                    continue
                try:
                    for stack in component.stacks():
                        stack_item_id = getattr(stack, "id", None)
                        if stack_item_id:
                            held[stack_item_id] = held.get(stack_item_id, 0) + getattr(stack, "count", 0)
                except Exception as error:
                    swallowed("production.SourceCache.local_stock: component.stacks", error)
            self._outpost_stock[outpost_id] = held
        return held.get(item_id, 0)

    def depot_stock(self, item_id, outpost=None):
        """Units of item_id in the Drone Depot stockpiles at `outpost` (home
        when None). One .stacks() sweep per outpost per pass."""
        outpost_id = HOME_OUTPOST_ID if outpost_is_home(outpost) else getattr(outpost, "id", None)
        held = self._depot_stock.get(outpost_id)
        if held is None:
            held = {}
            for depot in discover_storage_buildings(outpost, DRONE_DEPOT_TYPE_IDS):
                port = getattr(depot["component"], "output", None)
                if not port or not hasattr(port, "stacks"):
                    continue
                try:
                    for stack in port.stacks():
                        stack_item_id = getattr(stack, "id", None)
                        if stack_item_id:
                            held[stack_item_id] = held.get(stack_item_id, 0) + getattr(stack, "count", 0)
                except Exception as error:
                    swallowed("production.SourceCache.depot_stock: port.stacks", error)
            self._depot_stock[outpost_id] = held
        return held.get(item_id, 0)

    def held_stock(self, item_id, outpost=None):
        """local_stock() plus the outpost's Drone Depot stockpiles: units
        already made and sitting at `outpost`. For netting demand; a loader
        uses local_stock(), since take_item() doesn't reach Depots."""
        return self.local_stock(item_id, outpost) + self.depot_stock(item_id, outpost)

    def network_stock(self, item_id):
        """held_stock() at every outpost (Warehouses, Drone Depots, home
        Inventory) plus cargo loaded aboard a hauler
        (logistics_requests.aboard_units()): units anywhere on the network,
        moving ones included."""
        if self._remote_outposts is None:
            self._remote_outposts = [o for o in _all_outposts() if not outpost_is_home(o)]
        if self._aboard is None:
            self._aboard = aboard_units()
        total = self.held_stock(item_id) + self._aboard.get(item_id, 0)
        for outpost in self._remote_outposts:
            total += self.held_stock(item_id, outpost)
        return total

    def smelter_recipes(self):
        if self._smelter_recipes is None:
            component = _default_smelter()
            try:
                self._smelter_recipes = list(component.list_recipes()) if component and hasattr(component, "list_recipes") else []
            except Exception as error:
                swallowed("production.SourceCache.smelter_recipes: component.list_recipes", error)
                self._smelter_recipes = []
        return self._smelter_recipes

    def fabricator_recipes(self):
        if self._fabricator_recipes is None:
            component = _default_fabricator()
            try:
                self._fabricator_recipes = list(component.list_recipes()) if component and hasattr(component, "list_recipes") else []
            except Exception as error:
                swallowed("production.SourceCache.fabricator_recipes: component.list_recipes", error)
                self._fabricator_recipes = []
        return self._fabricator_recipes

    def fuel_assembler_recipes(self):
        """The first Fuel Assembler's unlocked recipes ([] without one). Only can_source_item() reads
        them: the recipe index and the Fabricator cascades stay Fabricator/Smelter-only."""
        if self._fuel_assembler_recipes is None:
            component = _default_fuel_assembler()
            try:
                self._fuel_assembler_recipes = list(component.list_recipes()) if component and hasattr(component, "list_recipes") else []
            except Exception as error:
                swallowed("production.SourceCache.fuel_assembler_recipes: component.list_recipes", error)
                self._fuel_assembler_recipes = []
        return self._fuel_assembler_recipes

    def sourcing_recipes(self, item_id):
        """Smelter, Fabricator and Fuel Assembler recipes that output item_id, in that order.
        The output index is built once per pass."""
        if self._sourcing_index is None:
            index = {}
            for recipes in (self.smelter_recipes(), self.fabricator_recipes(), self.fuel_assembler_recipes()):
                for recipe in recipes:
                    index.setdefault(getattr(recipe, "output_item", None), []).append(recipe)
            self._sourcing_index = index
        return self._sourcing_index.get(item_id, [])

    def cask_stock(self, item_id):
        if item_id not in self._cask_stock:
            self._cask_stock[item_id] = lead_cask.network_cask_stock(item_id)
        return self._cask_stock[item_id]

    def surveyed_sites(self):
        if self._surveyed_sites is None:
            journal = _component("journal")
            try:
                self._surveyed_sites = list(journal.surveyed_sites("nocturna")) if journal and hasattr(journal, "surveyed_sites") else []
            except Exception as error:
                swallowed("production.SourceCache.surveyed_sites: journal.surveyed_sites", error)
                self._surveyed_sites = []
        return self._surveyed_sites

    def surveyed_minerals(self):
        """Item ids of every surveyed mineral site, read once per pass (one kind() call per site)."""
        if self._surveyed_minerals is None:
            try:
                self._surveyed_minerals = {
                    getattr(site, "item_id", None)
                    for site in self.surveyed_sites()
                    if getattr(site, "kind", lambda: "")() == "mineral"
                }
            except Exception as error:
                swallowed("production.SourceCache.surveyed_minerals: site.kind", error)
                self._surveyed_minerals = set()
        return self._surveyed_minerals


def _has_surveyed_mineral(item_id, cache):
    return item_id in cache.surveyed_minerals()


def can_source_item(item_id, cache=None):
    """Whether an item has storage (Inventory/Warehouse), surveyed-source, or unlocked recipe supply.

    Pass a shared `cache` (SourceCache) when checking several items/recipes/
    orders in one pass -- see SourceCache's docstring for why that matters.
    """
    log.start(f"can_source_item({item_id})", level="debug")
    cache = SourceCache() if cache is None else cache
    if item_id in cache._item_results:
        log.trace(f"cache hit -> {cache._item_results[item_id]}")
        log.end()
        return cache._item_results[item_id]
    if cache.stock(item_id) > 0 or (item_id in lead_cask.HOT_ITEMS and cache.cask_stock(item_id) > 0):
        log.trace(f"already in stock ({cache.stock(item_id)}, casks {cache.cask_stock(item_id) if item_id in lead_cask.HOT_ITEMS else 0}) -> sourceable")
        cache._item_results[item_id] = True
        log.end()
        return True
    if item_id in cache._item_stack:
        log.trace("recipe cycle guard hit, treating as not-yet-sourceable")
        log.end()
        return False  # cycle guard -- not memoized, this item's own answer is still being computed higher up
    cache._item_stack.add(item_id)

    try:
        result = _has_surveyed_mineral(item_id, cache)
        if result:
            log.trace("surveyed mineral site found -> sourceable")
        if not result and item_id == lead_cask.URANIUM_ITEM and _uranium_aftermath_pending():
            result = True
            log.trace("live uranium aftermath site -> sourceable")
        if not result:
            for recipe in cache.sourcing_recipes(item_id):
                inputs = getattr(recipe, "inputs", {}) or {}
                fluid_inputs = getattr(recipe, "fluid_inputs", {}) or {}
                if all(can_source_fluid(fk, cache) for fk in fluid_inputs) and all(can_source_item(input_id, cache) for input_id in inputs):
                    result = True
                    log.trace(f"sourceable via recipe {getattr(recipe, 'id', '?')} (inputs={list(inputs.keys())}, fluids={list(fluid_inputs.keys())})")
                    break
            if not result:
                log.trace("no stock, no surveyed mineral, no sourceable recipe -> not sourceable")
    finally:
        cache._item_stack.discard(item_id)

    cache._item_results[item_id] = result
    log.end()
    return result


def can_fulfill_order(order, cache=None):
    """Checks whether every remaining order item has a currently known source.

    Pass a shared `cache` (SourceCache) when checking several orders in one
    pass (e.g. Supply Dock's plan_dock_assignments()) -- see SourceCache's
    docstring for why that matters.
    """
    log.start("can_fulfill_order", level="debug")
    if not order or not hasattr(order, "requires"):
        log.end()
        return False
    cache = SourceCache() if cache is None else cache
    shipped = getattr(order, "shipped", {}) or {}
    for item_id, required in order.requires.items():
        remaining = max(0, required - shipped.get(item_id, 0))
        if remaining > 0 and not can_source_item(item_id, cache):
            log.debug(f"{item_id} (remaining={remaining}) has no known source -> order not fulfillable")
            log.end()
            return False
    log.debug("all remaining requirements have a known source -> fulfillable")
    log.end()
    return True


def get_raw_material_reason(raw_item, smelter=None):
    """Describes the active downstream consumer driving a raw-material demand."""
    fabricator = _default_fabricator()

    _, order = find_dock_order_requiring(raw_item)
    if order:
        return f"Supply Dock Order {getattr(order, 'name', getattr(order, 'id', 'active'))}"

    if smelter is None:
        smelter = _default_smelter()
    if smelter and hasattr(smelter, "list_recipes"):
        try:
            for recipe in smelter.list_recipes():
                inputs = getattr(recipe, "inputs", {}) or {}
                if raw_item not in inputs:
                    continue
                output_item = getattr(recipe, "output_item", None)
                _, output_order = find_dock_order_requiring(output_item)
                if output_order:
                    return f"Supply Dock Order {getattr(output_order, 'name', getattr(output_order, 'id', 'active'))} via {getattr(recipe, 'id', 'Smelter')}"
                if fabricator and hasattr(fabricator, "get_recipe_inputs"):
                    fabricator_inputs = fabricator.get_recipe_inputs() or {}
                    if output_item in fabricator_inputs:
                        return f"Fabricator via {getattr(recipe, 'id', 'Smelter')}"
        except Exception as error:
            swallowed("production.get_raw_material_reason: smelter.list_recipes", error)

    if fabricator and hasattr(fabricator, "get_recipe_inputs"):
        try:
            if raw_item in (fabricator.get_recipe_inputs() or {}):
                return f"Fabricator recipe {getattr(fabricator, 'get_recipe', lambda: 'active')()}"
        except Exception as error:
            swallowed("production.get_raw_material_reason: fabricator.get_recipe_inputs", error)

    if total_stock(raw_item) > 0:
        return "existing storage demand"
    return "active production demand"