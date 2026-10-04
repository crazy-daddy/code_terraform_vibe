# Production planning base: craft timing, memoized building discovery (Smelter,
# Fabricator, Fuel Assembler, Supply Dock), machine/outpost site ids and the
# shared `log` every production_*.py module writes to (one TreeConsole, so
# nested blocks across modules indent as one tree).
from archive import archive
from outpost_mining import HOME_OUTPOST_ID, RAW_ORE_ITEM_IDS
from power import DAY_CYCLE_DURATION_SECONDS
from tree_console import TreeConsole
from components import component, fabricator, smelter
from swallow import swallowed
import fleet_status

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
    clock = component("clock")
    if clock and hasattr(clock, "tick"):
        try:
            return clock.tick()
        except Exception as error:
            swallowed("production_core._current_tick: clock.tick", error)
    return 0


SMELTER_TYPE_ID = "smelter"


def _all_outposts():
    """Every owned OutpostRef (outpost_network.outposts()), or just home when
    the network can't be listed."""
    network = component("outpost_network")
    if network and hasattr(network, "outposts"):
        try:
            return list(network.outposts())
        except Exception as error:
            swallowed("production_core._all_outposts: network.outposts", error)
    home = _home_outpost()
    return [home] if home else []


# Building discovery is called a dozen times per Smelter/Fabricator step (recipe lists, dock orders,
# worker counts, pipelines), each an outposts() + buildings(type) sweep. Results are reused for this
# many ticks (~2 s), so a newly placed building is seen at most that late.
DISCOVERY_TTL_TICKS = 20

# {(type_id, outpost_id or None): (tick, [ids])}
_DISCOVERY_MEMO = {}


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
            swallowed("production_core._discover_building_ids: outpost.buildings", error)
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


# {fabricator_id: {"site": outpost_id, "wants": {item_id: units}, "tick": n}}:
# input units each Fabricator's load_inputs() is still short of (up to its
# prefill window), so a local Smelter can push output straight into it.
# Written by the Fabricator when its wanted items change or a want shrinks
# (a delivery or its own take), else every WANTS_REFRESH_TICKS while it wants
# anything; readers skip entries older than WANTS_STALE_TICKS.
FABRICATOR_WANTS_KEY = "fabricator.wants"
WANTS_REFRESH_TICKS = 300
WANTS_STALE_TICKS = 900


def fabricator_wants_for(item_id, site_id, now=None):
    """[(fabricator_id, units, entry tick)] for fresh FABRICATOR_WANTS_KEY
    entries at site_id wanting item_id, largest want first."""
    wants = archive.get(FABRICATOR_WANTS_KEY, {})
    if not isinstance(wants, dict):
        return []
    now = _current_tick() if now is None else now
    rows = [(fab_id, int((entry.get("wants") or {}).get(item_id, 0)), entry.get("tick") or 0) for fab_id, entry in wants.items()
            if isinstance(entry, dict) and entry.get("site") == site_id and 0 <= now - (entry.get("tick") or 0) < WANTS_STALE_TICKS]
    return sorted([row for row in rows if row[1] > 0], key=lambda row: -row[1])


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
    network = component("outpost_network")
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
        smelter = component(smelter_id)
        if not smelter or not hasattr(smelter, "list_recipes"):
            continue
        try:
            recipes = list(smelter.list_recipes())
        except Exception as error:
            swallowed("production_core.smelter_ores: smelter.list_recipes", error)
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
        return smelter(ids[0])
    return smelter("smelter_1")  # last-resort fallback if discovery finds nothing (e.g. outpost_network unavailable)


FABRICATOR_TYPE_ID = "fabricator"


def discover_fabricator_ids(outpost=None):
    """All Fabricator building ids at `outpost`, or network-wide when omitted. Same shape/reasoning as discover_smelter_ids()."""
    return _discover_building_ids(FABRICATOR_TYPE_ID, outpost)


def _default_fabricator():
    """First discovered Fabricator component (dynamic stand-in for the old hardcoded 'fabricator_1')."""
    ids = discover_fabricator_ids()
    if ids:
        return fabricator(ids[0])
    return fabricator("fabricator_1")  # last-resort fallback if discovery finds nothing


FUEL_ASSEMBLER_TYPE_ID = "fuel_assembler"
# Fuel Assembler outputs (10_nuclear/lib/fuel_assembler.py builds them, not a Fabricator).
FUEL_ASSEMBLER_OUTPUTS = ("fuel_rod", "nuclear_battery")
# weather.aftermaths (lib/weather_signals.py); a live uranium site makes Raw Uranium sourceable.
AFTERMATHS_KEY = "weather.aftermaths"


def _default_fuel_assembler():
    ids = _discover_building_ids(FUEL_ASSEMBLER_TYPE_ID)
    return component(ids[0]) if ids else None


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


def _add_demand(demands, item_id, quantity):
    if item_id and quantity > 0:
        demands[item_id] = demands.get(item_id, 0) + quantity
