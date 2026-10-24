# Outpost mining scaffolding for the multi-outpost network (docs/AI_CHEATSHEET.md,
# TODO.md Phase 3). Answers, for a vehicle stationed at an outpost and for the
# planners that route ore: "which ores are worth a buffer?" (active_ores()),
# "which ores can this outpost's miners reach?" (mineable_ores_by_outpost())
# and "how much of each to stockpile?" (ore_stock_target()).
#
# A stationed miner mines NEED demand plus a STOCK buffer of each active ore
# (active_ores(), an add-only latch: an ore joins on its first NEED), from any
# surveyed site its drill cuts and a full battery reaches. Each miner
# publishes that reach (publish_reach()); site_supply.py and supply_dock.py
# read it here, so they need not import vehicle code. Map markers no longer
# take part (DESIGN_HISTORY "resource markers"); the leftover "resource."
# markers are cleared by lib/unsupported_markers.py.
#
# ore_stock_target() is seed-once-then-editable: once Warehouses are unlocked,
# the first lookup of an ore writes the default to the archive and every read
# after that returns the stored value untouched, so a player's manual edit is
# never clobbered by a background loop. Before the unlock the Storage Bin
# default is returned without seeding (storage.default_stock_target()).

from components import component
from game_clock import is_fresh, now_tick
from game_rules import RAW_ORE_ITEM_IDS
from storage import default_stock_target, slot_layout, slot_room
from swallow import swallowed
from tree_console import TreeConsole

log = TreeConsole(module="outpost_mining")

# One {ore_item_id: units} dict for every outpost: a mining outpost's
# stockpile target, home's standing ore floor and a smelting site's ore
# buffer (lib/site_supply.py) all read the same number.
ORE_STOCK_TARGETS_KEY = "mining.ore_stock_targets"

# Ores demanded at NEED or above at least once (site_supply plan pass, a
# stationed miner's bands): [ore_item_id, ...], add-only. Only these keep a
# STOCK buffer, so an ore no recipe has asked for yet is never mined ahead.
ACTIVE_ORES_KEY = "mining.active_ores"
# What each stationed miner can mine: {vehicle: {"outpost", "ores", "tick"}},
# ores with a surveyed site its drill cuts and a full battery reaches from its
# outpost. Published by the miner (vehicle_mining.py), read by planners so
# they need not import vehicle code. Refreshed every REACH_REFRESH_TICKS
# (= logistics_requests.REQUEST_STALE_TICKS); an entry older than
# REACH_STALE_TICKS (= archive.STATUS_STALE_TICKS, a long mining trip
# included) no longer counts.
MINING_REACH_KEY = "mining.reach"
REACH_REFRESH_TICKS = 6000
REACH_STALE_TICKS = 36000
# Empty store slots an ore STOCK buffer leaves free (ore_buffer_fits()).
ORE_BUFFER_FREE_SLOTS = 1

# How close (meters) a site needs to be to an outpost to count as minable
# without a long haul (survey stop weights, autoplay's outpost needs).
# Archive-configurable (player-tunable without a code change) rather than a
# bare constant.
RESOURCE_ASSIGNMENT_RANGE_KEY = "outposts.resource_assignment_range_m"
DEFAULT_RESOURCE_ASSIGNMENT_RANGE_M = 200.0

# Canonical home outpost id (docs/components/outpost.md; also hardcoded as a
# literal in a few tier-1 scripts, e.g. power/solar.py).
HOME_OUTPOST_ID = "outpost_home"


def _archive():
    from archive import archive

    return archive


def _outpost_network():
    return component("outpost_network")


def outpost_by_id(outpost_id):
    """Resolves an outpost id string to its live OutpostRef/Outpost object, or None."""
    network = _outpost_network()
    if not network or not hasattr(network, "outposts"):
        return None
    try:
        for outpost in network.outposts():
            if getattr(outpost, "id", None) == outpost_id:
                return outpost
    except Exception as error:
        swallowed("outpost_mining.outpost_by_id: network.outposts", error)
    return None


def nearest_outpost_id(x, y):
    """Id of the outpost nearest to world coords (x, y), or None if unavailable."""
    network = _outpost_network()
    if not network or not hasattr(network, "nearest"):
        return None
    try:
        nearest = network.nearest(x, y)
        return getattr(nearest, "id", None) if nearest else None
    except Exception as error:
        swallowed("outpost_mining.nearest_outpost_id: network.nearest", error)
        return None


def resource_assignment_range_m():
    """Player-tunable auto-assignment radius (meters), archive-backed, default DEFAULT_RESOURCE_ASSIGNMENT_RANGE_M."""
    return _archive().get(RESOURCE_ASSIGNMENT_RANGE_KEY, DEFAULT_RESOURCE_ASSIGNMENT_RANGE_M)


def outpost_positions():
    """[(id, x, y)] of every live outpost, home included."""
    network = _outpost_network()
    if not network or not hasattr(network, "outposts"):
        return []
    try:
        outposts = network.outposts()
    except Exception as error:
        swallowed("outpost_mining.outpost_positions: network.outposts", error)
        return []
    out = []
    for outpost in outposts:
        outpost_id = getattr(outpost, "id", None)
        ox, oy = getattr(outpost, "x", None), getattr(outpost, "y", None)
        if ox is not None and oy is not None:
            out.append((outpost_id, ox, oy))
    return out


def ore_bands(bands):
    """{band: {ore: units}}: the raw-ore entries of `bands` (outpost_tier_deficits()
    output, already net of in-flight mining yield). Positive entries only."""
    out = {}
    for band, items in bands.items():
        for item_id in sorted(items):
            if item_id in RAW_ORE_ITEM_IDS and items[item_id] > 0:
                out.setdefault(band, {})[item_id] = items[item_id]
    return out


def active_ores():
    """Ores latched active (ACTIVE_ORES_KEY): demanded at NEED or above once,
    so they keep a STOCK buffer from then on. Empty before the first need."""
    value = _archive().get(ACTIVE_ORES_KEY, [])
    return {ore for ore in value if isinstance(ore, str)} if isinstance(value, list) else set()


def latch_active_ores(ores):
    """Adds `ores` to the active set (never removes one). Writes only when
    one is new; returns the newly latched ores, sorted."""
    new = sorted(set(ores) - active_ores())
    if not new:
        return []

    def updater(current):
        current = [ore for ore in current if isinstance(ore, str)] if isinstance(current, list) else []
        return sorted(set(current) | set(new))

    _archive().transaction(ACTIVE_ORES_KEY, [], updater)
    log.print(f"Mining: ore now active, buffered from here on: {', '.join(new)}.")
    return new


def publish_reach(vehicle_name, outpost_id, ores, tick):
    """Records that vehicle_name, stationed at outpost_id, can mine `ores`
    (MINING_REACH_KEY). Writes when the entry changes or its stamp is
    REACH_REFRESH_TICKS old."""
    ores = sorted(ores)
    current = _archive().get(MINING_REACH_KEY, {})
    entry = current.get(vehicle_name) if isinstance(current, dict) else None
    if isinstance(entry, dict) and entry.get("outpost") == outpost_id and entry.get("ores") == ores and is_fresh(entry, tick, REACH_REFRESH_TICKS):
        return False
    fresh = {"outpost": outpost_id, "ores": ores, "tick": tick}

    return _archive().set_entry(MINING_REACH_KEY, vehicle_name, fresh)


def mineable_ores_by_outpost(tick=None):
    """{outpost_id: set of ores} a stationed miner there can reach and cut
    (publish_reach()), from entries fresher than REACH_STALE_TICKS."""
    reach = _archive().get(MINING_REACH_KEY, {})
    if not isinstance(reach, dict):
        return {}
    tick = now_tick() if tick is None else tick
    out = {}
    for entry in reach.values():
        if not is_fresh(entry, tick, REACH_STALE_TICKS) or not isinstance(entry.get("ores"), list):
            continue
        out.setdefault(entry.get("outpost"), set()).update(ore for ore in entry["ores"] if isinstance(ore, str))
    return out


def mineable_ores(outpost_id, tick=None):
    """Ores a stationed miner at outpost_id can reach and cut (mineable_ores_by_outpost())."""
    return mineable_ores_by_outpost(tick).get(outpost_id, set())


def ore_buffer_fits(outpost, item_id):
    """True when a STOCK buffer of ore item_id has room at `outpost`
    (storage.slot_room()): room left in the slots already holding it (each
    filled to slot_fill(), about the stock target), or, with none, an empty
    slot while more than ORE_BUFFER_FREE_SLOTS others stay empty. An outpost
    with no store building passes: the rule only keeps an ore buffer from
    taking the last free slots of existing stores."""
    layout = slot_layout(outpost)
    return not layout or slot_room(item_id, layout, keep_free=ORE_BUFFER_FREE_SLOTS) > 0


def ore_stock_target(item_id):
    """
    Stock target (units) for raw ore item_id, the same at every outpost --
    seed-once-then-editable under ORE_STOCK_TARGETS_KEY, default
    storage.default_stock_target() (seeded only once Warehouses are
    unlocked). Read as a stationed
    miner's stockpile target at its mining outpost and as every smelting
    site's ore buffer tier, home included (lib/site_supply.py).
    """
    archive = _archive()
    targets = archive.get(ORE_STOCK_TARGETS_KEY, {}) or {}
    if not isinstance(targets, dict):
        targets = {}
    value = targets.get(item_id)
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)

    default, final = default_stock_target()
    if not final:
        return default
    targets = dict(targets)
    targets[item_id] = default
    archive.set(ORE_STOCK_TARGETS_KEY, targets)
    log.debug(f"ore_stock_target({item_id}): seeding default target {default} (first lookup)")
    return default
