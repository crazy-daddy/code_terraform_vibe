# Shared "network-wide reachable-fluid-target" mechanism: discover Gas/Liquid
# Tank (or other source/target) candidates network-wide, try to connect,
# verify reachability (connect()'s "ok" status never confirms a completed
# physical pipe route exists -- see docs/guide/infrastructure_and_pipes.md),
# and blacklist an unreachable one with per-entry (not shared-clock) expiry.
# Two routers, one per port direction, sharing PerEntryBlacklist,
# TickedDiscoveryCache and discover_network_buildings():
#   - FluidOutputRouter (producer side: Thermal Cap, Water Pump, Essence
#     Liquifier) -- rebalances among targets by fill_pct().
#   - FluidInputRouter (consumer side: Steam Turbine, Fabricator, Biomass
#     Mixer) -- only cares whether fluid arrives; accepts peer-declared links.
# See each class's docstring for why they stay separate.
#
# A pre-computed physical pipe-network graph (like power_control's PowerGrid)
# was investigated and rejected: pipes have no engine-side merged-network
# API the way power does, and reconstructing one from list_pipes() geometry
# would need building footprint/size data that doesn't exist in the docs
# (only an ambiguous docking-point position). Everything here still works
# the same way the code it replaces did: gather candidates, try connect(),
# verify via is_stalled(), blacklist on failure.
#
# One thing candidates ARE filtered on before any of that: an operator's
# manual fluid_routing.tank_assignments designation (get_tank_assignments()/
# tank_matches_assignment()/tank_is_eligible_target()) -- a generic Liquid/Gas
# Tank's own .fluid() latch says nothing about which of an outpost's several
# possible, non-merged physical pipe networks it sits on (docs/guide/
# infrastructure_and_pipes.md), and clears to "" the instant it drains to 0,
# so without this an auto-router could steal a tank meant for a different
# fluid the moment it's empty. See fluid_routing.tank_assignments in
# docs/AI_CHEATSHEET.md.
#
# This is a hard gate, deliberately: a tank that is neither already latched
# to the fluid a router wants NOR explicitly assigned to it is NOT eligible,
# full stop -- not "eligible until proven otherwise". A brand-new tank is
# always fill_pct()==0, so it would otherwise be the top-ranked candidate for
# every router's least-full-first sort the instant it's built, before the
# operator ever gets a chance to say what it's for. The cost is a real
# behavior change versus the old "unrestricted by default" version of this
# module: an unassigned, never-latched tank now sits idle, untouched by any
# router, until the operator assigns it (see warn_about_unassigned_tanks()
# below for the nudge) -- accepted deliberately, since a stalled/idle tank is
# recoverable and a silently wrong fill may not be. An already-latched tank
# is a different case entirely -- it's a proven physical fact, not a risk,
# so tank_is_eligible_target() lets it keep working with zero configuration
# regardless of the registry's state, exactly as before.

from functools import lru_cache
from archive import archive
from tree_console import TreeConsole
from swallow import swallowed
from game_clock import now_tick

log = TreeConsole(module="fluid_routing")

TANK_ASSIGNMENTS_KEY = "fluid_routing.tank_assignments"
# Assignment value for a tank being replaced (lib/tank_upgrade.py): never a target for a new
# connection, even while still latched, so producers move off it and it can drain.
RETIRING_ASSIGNMENT = "retiring"


def get_tank_assignments():
    """{building_id: fluid_id} -- operator-designated tank reservations, edited directly in the
    Data Archive Notebook (e.g. {"gas_tank_1": "steam", "gas_tank_3": "ammonia"}), same edit
    convention as production.get_manual_orders(). Empty/absent by default -- an already-latched
    tank never needs an entry here at all (see tank_is_eligible_target()'s escape hatch), only a
    tank that isn't latched to anything yet does. fluid_id values use the exact same vocabulary as
    building.fluid() / production.FLUID_LATCH_IDS ("water", "oil", "steam", or a biome essence id
    once the Essence Liquifier ships) -- not a separate taxonomy."""
    if not archive.has(TANK_ASSIGNMENTS_KEY):
        archive.set(TANK_ASSIGNMENTS_KEY, {})
    stored = archive.get(TANK_ASSIGNMENTS_KEY, {})
    if not isinstance(stored, dict):
        return {}
    return {
        building_id: fluid_id for building_id, fluid_id in stored.items()
        if isinstance(fluid_id, str) and fluid_id
    }


def tank_matches_assignment(building_id, fluid_id, assignments=None):
    """True only if building_id is explicitly assigned to exactly fluid_id; False if assigned to a
    different fluid_id OR not assigned at all. Deliberately deny-by-default on no entry -- see the
    module docstring for why "unrestricted until proven otherwise" was rejected. This is the pure
    registry check; it has no way to know a tank is already safely latched to fluid_id (that needs
    the live building object, not just its id) -- callers that have a resolved building should use
    tank_is_eligible_target() below instead, which checks that first and only falls back to this
    for a tank that isn't already latched to anything. assignments: a get_tank_assignments() result
    the caller already holds, so a loop over many tanks reads the archive once."""
    if assignments is None:
        assignments = get_tank_assignments()
    return assignments.get(building_id) == fluid_id


def tank_assignment(building_id):
    """building_id's get_tank_assignments() value, or None: one archive read, without copying and
    filtering the whole registry (the per-call check on an already-connected tank)."""
    stored = archive.get(TANK_ASSIGNMENTS_KEY, {})
    value = stored.get(building_id) if isinstance(stored, dict) else None
    return value if isinstance(value, str) and value else None


def tank_is_eligible_target(building, fluid_id, assignments=None):
    """
    Whether a resolved Liquid/Gas Tank building (discover_network_buildings(resolve=True) shape --
    has .fluid()/.id) is safe to treat as a candidate for a NEW fluid_id connection right now.

    A tank already latched to fluid_id is always eligible, unconditionally, regardless of the
    tank_assignments registry's state -- that's a proven physical fact, not a risk, and is exactly
    what keeps every already-working connection in an old/simple save running with zero
    configuration after this module started denying-by-default (see module docstring). A tank
    latched to a DIFFERENT fluid is never eligible (an unrelated router should not attempt to
    steal it -- connect() would fail/conflict anyway, this just skips the wasted attempt). Only a
    tank that isn't latched to anything at all (freshly built, or drained to 0 and not yet
    reassigned) falls through to tank_matches_assignment()'s strict registry check -- eligible only
    with an explicit matching entry.

    A tank assigned RETIRING_ASSIGNMENT is never eligible, latched or not -- checked before the
    latch, since a retiring tank keeps its latch until it has drained to 0.

    assignments: as in tank_matches_assignment(); None reads only this tank's entry (tank_assignment()).
    """
    b_id = getattr(building, "id", None)
    if not b_id:
        return False
    if assignments is None:
        assignments = {b_id: tank_assignment(b_id)}
    if assignments.get(b_id) == RETIRING_ASSIGNMENT:
        return False
    current_fluid = None
    if building is not None and hasattr(building, "fluid"):
        try:
            current_fluid = building.fluid()
        except Exception as error:
            swallowed("fluid_routing.tank_is_eligible_target: building.fluid", error)
            current_fluid = None
    if current_fluid:
        return current_fluid == fluid_id
    return tank_matches_assignment(b_id, fluid_id, assignments)


def safe_is_stalled(building):
    """hasattr-guarded, exception-swallowed building.is_stalled() probe. See module docstring for why is_stalled() is the only live reachability signal."""
    if not building or not hasattr(building, "is_stalled"):
        return False
    try:
        return building.is_stalled()
    except Exception as error:
        swallowed("fluid_routing.safe_is_stalled: building.is_stalled", error)
        return False


# Liquid (not gas) buffer types -- the only valid target/source for liquids like water or a biome
# essence. Same pair as water_pump.LIQUID_TANK_TYPE_IDS.
LIQUID_TANK_TYPE_IDS = ("liquid_tank", "bulk_liquid_reservoir")

# FluidConnection.state values (docs/types/infrastructure_and_fluids.md). Unlike is_stalled(),
# these are a direct, per-peer reachability verdict: "local"/"ready" means the link can actually
# move fluid right now; "unreachable"/"conflict"/"incompatible" means it can't, no matter how long
# we wait. "neutral" (no fluid established yet, e.g. an empty tank that isn't latched yet) is
# neither of these and is deliberately in neither tuple -- callers treat it as "pending".
HEALTHY_CONNECTION_STATES = ("local", "ready")
BROKEN_CONNECTION_STATES = ("unreachable", "conflict", "incompatible")


def port_connections(port: "FluidPort"):
    """port.connections() -- every effective peer, including ones the PEER declared -- or [] if unavailable."""
    if not port or not hasattr(port, "connections"):
        return []
    try:
        return list(port.connections())
    except Exception as error:
        swallowed("fluid_routing.port_connections: port.connections", error)
        return []


def healthy_peer_id(port: "FluidPort"):
    """machine_id of the first effective peer in a HEALTHY_CONNECTION_STATES state, or None. Counts
    links declared by either side (declared_by "self"/"peer"/"both"), so a port another machine's
    script already wired up reads as healthy without this side declaring anything."""
    for conn in port_connections(port):
        if getattr(conn, "state", None) in HEALTHY_CONNECTION_STATES:
            return getattr(conn, "machine_id", None)
    return None


def declared_connection(port: "FluidPort"):
    """FluidConnection of this port's OWN declared target (connected_id()), or None if it has none or
    the target isn't in connections() yet."""
    if not port or not hasattr(port, "connected_id"):
        return None
    try:
        own_id = port.connected_id()
    except Exception as error:
        swallowed("fluid_routing.declared_connection: port.connected_id", error)
        return None
    if not own_id:
        return None
    for conn in port_connections(port):
        if getattr(conn, "machine_id", None) == own_id:
            return conn
    return None


def declared_connection_state(port: "FluidPort"):
    """FluidConnection.state of this port's OWN declared target, or None (see declared_connection())."""
    return getattr(declared_connection(port), "state", None)


# A "conflict" link is not like "unreachable": the game assigned it to the one pipe component that
# reaches both ends, and that component already carries a different fluid, so ALL flow on it stops
# -- including every unrelated route already using it (docs/guide/flow_networks_fluids.md). The
# router that caused it disconnects at once and leaves that source alone for this long (~5 min at
# 10 ticks/sec); the operator fixes it by building a separate pipe for the fluid that doesn't touch
# the other one. Retrying sooner would stall the other fluid's pipe again on every attempt.
CONFLICT_BLACKLIST_TICKS = 3000
# A link that was flowing before turning "conflict" was most likely joined by someone else's new
# route; that newcomer yields at once, so the established side waits this many checks before it
# also drops (covers an intruder our routers don't control, e.g. a manual connect()).
ESTABLISHED_CONFLICT_GRACE_STEPS = 5
# {router label: {"source": id, "fluid": id or None, "tick": t}} -- one entry per port that yielded a
# pipe conflict, pruned after CONFLICT_BLACKLIST_TICKS. control_room_automation.py lists the live ones
# on the AUTOMATION card (active_pipe_conflicts()).
PIPE_CONFLICTS_KEY = "fluid_routing.pipe_conflicts"


def _prune_conflicts(stored, curr_tick):
    if not isinstance(stored, dict):
        return {}
    return {
        label: entry for label, entry in stored.items()
        if isinstance(entry, dict) and (curr_tick == 0 or curr_tick - entry.get("tick", 0) < CONFLICT_BLACKLIST_TICKS)
    }


def yield_pipe_conflict(port: "FluidPort", label, source_id, fluid, curr_tick, blacklist):
    """Disconnects port's own declaration onto source_id (the "conflict" link), blacklists source_id
    for CONFLICT_BLACKLIST_TICKS and reports it: warn log, notify() and a PIPE_CONFLICTS_KEY entry.
    Only pipe conflicts are reported this way -- an "unreachable" source is normal with several
    separate pipe networks and stays a quiet debug-level blacklist."""
    try:
        port.disconnect()
    except Exception as error:
        swallowed("fluid_routing.yield_pipe_conflict: port.disconnect", error)
    blacklist.blacklist(source_id, curr_tick, CONFLICT_BLACKLIST_TICKS)
    fluid_text = fluid or "fluid"
    message = (
        f"[Pipe conflict] {label} -> '{source_id}': the only pipe reaching it carries another fluid; "
        f"disconnected, retry in {CONFLICT_BLACKLIST_TICKS} ticks. Build a separate {fluid_text} pipe that doesn't touch it."
    )
    log.level("warn").print(message)
    notify(message, level="warn", duration_seconds=10.0)

    def updater(stored):
        stored = _prune_conflicts(stored, curr_tick)
        stored[label] = {"source": source_id, "fluid": fluid, "tick": curr_tick}
        return stored
    if not archive.transaction(PIPE_CONFLICTS_KEY, {}, updater):
        log.level("warn").print(f"yield_pipe_conflict: archive write failed for {label}.")


def active_pipe_conflicts(curr_tick):
    """["<label> x <source>", ...] for every pipe conflict still inside its blacklist window; prunes
    expired entries from PIPE_CONFLICTS_KEY."""
    stored = archive.get(PIPE_CONFLICTS_KEY, {})
    live = _prune_conflicts(stored, curr_tick)
    if isinstance(stored, dict) and len(live) != len(stored):
        archive.set(PIPE_CONFLICTS_KEY, live)
    return [f"{label} x {entry.get('source')}" for label, entry in sorted(live.items())]


def feeds_remote_route(building):
    """True when building's liquid_out/gas_out has a "ready" peer: it is the source of a
    cross-outpost route, so on that pipe component it pools as a provider and, while it holds
    fluid, no other passive provider fills it (docs/gameknowledge/fluids.md, "Remote (pipe)
    connections"). One connections() read per port."""
    for name in ("liquid_out", "gas_out"):
        port = getattr(building, name, None)
        if port is not None and any(getattr(c, "state", None) == "ready" for c in port_connections(port)):
            return True
    return False


def port_starved(port: "FluidPort"):
    """Input FluidPort reads flow_rate() == 0 with room left -- a full port also reads 0, not a stall.
    The is_starved signal for a FluidInputRouter on a machine without is_stalled()."""
    try:
        level = port.level() if hasattr(port, "level") else 0
        capacity = port.capacity() if hasattr(port, "capacity") else 0
        flow = port.flow_rate() if hasattr(port, "flow_rate") else 0
        return flow == 0 and (not capacity or level < capacity)
    except Exception as error:
        swallowed("fluid_routing.port_starved: port.level", error)
        return False


def fill_pct_of(building):
    """fill_pct() of an already-resolved building object, or 1.0 ("full, deprioritize") if unreadable/missing."""
    if not building or not hasattr(building, "fill_pct"):
        return 1.0
    try:
        return building.fill_pct()
    except Exception as error:
        swallowed("fluid_routing.fill_pct_of: building.fill_pct", error)
        return 1.0


class PerEntryBlacklist:
    """
    id -> the simulation tick it was blacklisted at. NOT a plain set and NOT
    one shared "clear everything at once" timer -- this distinction is
    load-bearing, not stylistic. connect()'s "ok" status only means a
    pairing was logically accepted, never that a completed pipe route
    exists; is_stalled()/starvation is the only live signal a target truly
    isn't reachable. With 2+ simultaneously-unreachable candidates ranked
    ahead of the one genuinely-reachable target (by fill/discovery-order
    ties), eliminating all of them can take longer than one shared expiry
    window -- a single clock wiping the WHOLE blacklist at once would erase
    that elimination progress and restart from the first bad candidate
    before ever reaching the real one, an infinite ping-pong between the
    same bad candidates. This was observed in practice (a Thermal Cap
    repeatedly targeting two unreachable Gas Tanks at a different outpost,
    never once trying the one actually reachable from its own) and fixed by
    tracking each entry's own blacklist tick and expiring independently, so
    forward progress toward an untried reachable one is never erased by an
    unrelated entry's clock.

    curr_tick == 0 (clock unavailable) is treated as "still blacklisted"
    rather than "unknown so allow retry" -- the same convention used for the
    same edge case in lib/vehicle_claims.py's/lib/smelter.py's/
    lib/fabricator.py's own staleness checks; this class continues that
    convention rather than inventing a new one.
    """

    def __init__(self, rescan_interval_ticks):
        self.rescan_interval_ticks = rescan_interval_ticks
        self._blacklisted_at = {}
        # entry_id -> its own expiry when blacklist() was given one (pipe conflicts); else rescan_interval_ticks.
        self._durations = {}

    def is_blacklisted(self, entry_id, curr_tick):
        blacklisted_at = self._blacklisted_at.get(entry_id)
        if blacklisted_at is None:
            return False
        age = curr_tick - blacklisted_at
        duration = self._durations.get(entry_id, self.rescan_interval_ticks)
        still_blacklisted = curr_tick == 0 or age < duration
        if not still_blacklisted:
            log.debug(f"PerEntryBlacklist: '{entry_id}' blacklist expired (age={age} >= {duration}), eligible again")
            self._blacklisted_at.pop(entry_id, None)
            self._durations.pop(entry_id, None)
        return still_blacklisted

    def blacklist(self, entry_id, curr_tick, duration_ticks=None):
        if duration_ticks is None:
            self._durations.pop(entry_id, None)
        else:
            self._durations[entry_id] = duration_ticks
        log.debug(f"PerEntryBlacklist: blacklisting '{entry_id}' at tick={curr_tick} (expires after {self._durations.get(entry_id, self.rescan_interval_ticks)} ticks)")
        self._blacklisted_at[entry_id] = curr_tick

    def filter_reachable(self, entries, curr_tick, key=lambda e: e):
        listed = self._blacklisted_at
        if not listed:
            return list(entries)
        return [e for e in entries if key(e) not in listed or not self.is_blacklisted(key(e), curr_tick)]


def discover_network_buildings(type_ids, resolve=True, fluid_id=None):
    """
    Every building across every known outpost matching type_ids (a single
    type_id string, or an iterable of them -- e.g. Water Pump's Liquid
    Tank/Large Liquid Tank, or Steam Turbine's Gas Tank/Thermal Cap), walking
    outpost_network.outposts() -> outpost.buildings(type_id). Returns
    [(building_or_id, outpost_id), ...] in discovery order, deduplicated by
    id within this call.

    fluid_id, when given, drops any candidate tank_is_eligible_target() rejects -- either latched
    to a different fluid, or unlatched with no matching tank_assignments entry (see that
    function's docstring for why unassigned is deny-by-default). This always resolves the
    candidate first regardless of this call's own resolve= value (tank_is_eligible_target() needs
    the live building, not just its id, to apply its already-latched escape hatch) -- when
    resolve=False was requested, the resolved object is used for the check only and discarded, and
    the bare id is what's actually returned.

    outpost_id is the owning outpost's id, or None when the building has no
    .outpost of its own (Thermal Cap only -- built directly on a thermal
    vent out in the field, not necessarily inside a founded outpost; see
    docs/components/thermal_cap.md). It's returned purely so a caller CAN
    rank by "shares my own outpost" (see steam_turbine.py's
    _discover_candidates_cached()) -- this function itself never excludes or
    scopes by outpost; a Cap/Pump has no .outpost of its own either, and
    physical pipe topology, not outpost membership, ultimately decides which
    candidates actually succeed via connect().

    When resolve=True (default), each raw BuildingRef *snapshot* --
    outpost.buildings(type_id) never hands back more than
    .id/.name/.type_id/.outpost/.powered/.position, see
    docs/components/outpost.md -- is resolved to its full live component via
    get_component(ref.id) or building, same convention as storage.py's
    discover_storage_buildings()/vehicle_energy.py's
    get_all_charging_stations(). This matters more than it looks: an earlier
    version of this exact helper skipped resolution and returned the raw
    BuildingRef, which has no fill_pct() at all -- every fill-based
    sort/threshold silently degenerated to a no-op tie broken by discovery
    order, producing a real, observed infinite ping-pong between two
    unreachable Gas Tanks that never advanced to try a third, reachable one.
    Pass resolve=False when only ids are needed (Steam Turbine tracks
    candidates by id only) to skip the get_component() round trip rather
    than resolve-and-discard.
    """
    if isinstance(type_ids, str):
        type_ids = (type_ids,)

    pairs = []
    seen_ids = set()
    assignments = get_tank_assignments() if fluid_id is not None else None
    network = get_component("outpost_network")
    if network and hasattr(network, "outposts"):
        try:
            for outpost in network.outposts():
                outpost_id = getattr(outpost, "id", None)
                for type_id in type_ids:
                    for building in outpost.buildings(type_id):
                        b_id = getattr(building, "id", None)
                        if not b_id or b_id in seen_ids:
                            continue

                        resolved = None
                        if resolve or fluid_id is not None:
                            try:
                                resolved = get_component(b_id) or building
                            except Exception as error:
                                swallowed("fluid_routing.discover_network_buildings: get_component", error)
                                resolved = building

                        if fluid_id is not None and not tank_is_eligible_target(resolved, fluid_id, assignments):
                            continue

                        seen_ids.add(b_id)
                        pairs.append((resolved if resolve else b_id, outpost_id))
        except Exception as error:
            swallowed("fluid_routing.discover_network_buildings: network.outposts", error)
    log.trace(f"discover_network_buildings({type_ids}): found {len(pairs)} building(s)")
    return pairs


# liquid_tank/bulk_liquid_reservoir/gas_tank -- mirrors production.BUFFER_FLUID_TYPE_IDS, not
# imported from there to avoid a circular import (production.py already imports from this
# module). Kept in sync by hand; both lists are short and rarely change.
TANK_TYPE_IDS = ("liquid_tank", "bulk_liquid_reservoir", "gas_tank")


def fluid_reserve_tons(fluid_id, type_ids=("liquid_tank", "bulk_liquid_reservoir"), curr_tick=None):
    """
    (level t, capacity t) summed over every tank eligible for fluid_id (tank_is_eligible_target())
    network-wide, None when there is no such tank or none is readable. With curr_tick the tanks
    come from the cached network_buildings() walk instead of a fresh one.
    """
    if curr_tick is None:
        tanks = [tank for tank, _outpost_id in discover_network_buildings(type_ids, resolve=True, fluid_id=fluid_id)]
    else:
        tanks = eligible_targets(network_buildings(type_ids, curr_tick), fluid_id)
        if tanks is None:
            invalidate_network_walk(type_ids)
            tanks = eligible_targets(network_buildings(type_ids, curr_tick), fluid_id) or []
    level = capacity = 0.0
    for tank in tanks:
        try:
            cap = float(tank.capacity())
            if cap > 0:
                level += float(tank.level())
                capacity += cap
        except Exception as error:
            swallowed("fluid_routing.fluid_reserve_tons: tank.capacity", error)
    return (level, capacity) if capacity > 0 else None


def fluid_reserve_fraction(fluid_id, type_ids=("liquid_tank", "bulk_liquid_reservoir"), curr_tick=None):
    """Network-wide fill (0-1) of every tank eligible for fluid_id, None when there is no such tank.
    curr_tick: as in fluid_reserve_tons()."""
    tons = fluid_reserve_tons(fluid_id, type_ids, curr_tick)
    return tons[0] / tons[1] if tons else None


# Water reservation for Reactors (§1c-4): while the Reactor controller's
# WATER_RESERVE_KEY entry says "hold" (pooled water tanks below the Reactors'
# floor), every FluidInputRouter built with reserve_fluid="water" disconnects
# its port, and the Harvester skips refill_water(). Only the Reactors keep
# drawing. An entry older than WATER_RESERVE_FRESH_TICKS (no Reactor script
# running) never holds.
WATER_RESERVE_KEY = "fluid_routing.water_reserve"
WATER_RESERVE_FRESH_TICKS = 1200


def water_reserve_holds(curr_tick=None):
    """True while the Reactors' water reserve is held for them alone (read once per tick)."""
    now = now_tick() if curr_tick is None else curr_tick
    try:
        return _water_reserve_holds_at(now)
    except Exception as error:
        swallowed("fluid_routing.water_reserve_holds: archive.get", error)
        return False


@lru_cache(maxsize=1)
def _water_reserve_holds_at(now):
    """water_reserve_holds() for tick `now`. The tick is the cache key, so a new
    tick reads the archive again. No logging here: in game a cache miss runs as a
    pure callback (dev_workflow.md §1d-1); a raised error is not cached."""
    entry = archive.get(WATER_RESERVE_KEY, {}) or {}
    if not (isinstance(entry, dict) and entry.get("hold")):
        return False
    written = entry.get("tick", 0)
    return isinstance(written, (int, float)) and 0 <= now - written < WATER_RESERVE_FRESH_TICKS


def assign_tanks_from_current_fluid(overwrite=False):
    """
    One-shot bootstrap for fluid_routing.tank_assignments: walks every Liquid/Gas Tank
    network-wide (TANK_TYPE_IDS), reads each one's already-latched building.fluid(), and records
    building_id -> fluid_id for every tank that has one. Meant to be run manually, once, by
    pasting a short call into the in-game Playground (there's no machine to deploy a standalone
    script onto for a network-wide utility like this one -- see docs/AI_CHEATSHEET.md), after
    tanks have already latched onto their real-world contents through normal play -- it only ever
    reads .fluid(), never guesses at an empty tank's intended fluid (nothing to infer from "").

    overwrite=False (default) never touches a building_id that already has an assignment entry,
    so a prior manual designation (or an earlier run of this same function) is never silently
    clobbered. Pass overwrite=True to instead resync every already-latched tank's entry to its
    current .fluid() -- e.g. after re-plumbing a tank onto a different network. A
    RETIRING_ASSIGNMENT entry is never overwritten.

    Returns (assigned, skipped_already_set, skipped_empty) counts for the caller to print.
    """
    tanks = discover_network_buildings(TANK_TYPE_IDS, resolve=True)
    existing = get_tank_assignments()

    to_add = {}
    assigned = skipped_already_set = skipped_empty = 0
    for building, _outpost_id in tanks:
        b_id = getattr(building, "id", None)
        if not b_id or not hasattr(building, "fluid"):
            continue
        try:
            fluid = building.fluid()
        except Exception as error:
            swallowed("fluid_routing.assign_tanks_from_current_fluid: building.fluid", error)
            fluid = None
        if not fluid:
            skipped_empty += 1
            continue
        if (not overwrite and b_id in existing) or existing.get(b_id) == RETIRING_ASSIGNMENT:
            skipped_already_set += 1
            continue
        to_add[b_id] = fluid
        assigned += 1

    if to_add:
        def updater(stored):
            stored = dict(stored or {})
            stored.update(to_add)
            return stored
        archive.transaction(TANK_ASSIGNMENTS_KEY, {}, updater)
        log.print(f"assign_tanks_from_current_fluid(): wrote {len(to_add)} assignment(s) -> {to_add}")

    return assigned, skipped_already_set, skipped_empty


# ~60 real seconds at normal speed (10 ticks/sec, docs/components/clock.md) -- same tick-based
# convention as RESCAN_INTERVAL_TICKS/CLAIM_STALE_TICKS elsewhere, not a real-time timer.
UNASSIGNED_TANK_WARNING_INTERVAL_TICKS = 600
LAST_UNASSIGNED_WARNING_TICK_KEY = "fluid_routing.last_unassigned_warning_tick"


def warn_about_unassigned_tanks(curr_tick):
    """
    Prints a warning-level notice, at most once every UNASSIGNED_TANK_WARNING_INTERVAL_TICKS ticks,
    listing every Liquid/Gas Tank network-wide that tank_is_eligible_target() would currently deny
    for every fluid -- i.e. not latched to anything AND no tank_assignments entry. An already-latched
    tank is never listed here even without an entry -- it's not actually blocked (see
    tank_is_eligible_target()'s escape hatch), so flagging it would just be noise.

    The throttle timestamp lives in archive (LAST_UNASSIGNED_WARNING_TICK_KEY), NOT a module-level
    Python global -- a plain global is only shared within one script's own run, not across every
    separately-deployed machine script that imports this Library (same "per-script-run" caveat
    documented for production.py's _WARNED_UNKNOWN_MANUAL_ITEMS, docs/AI_CHEATSHEET.md). With
    several Water Pumps/Thermal Caps/Turbines all calling into this, a module global would let each
    one independently decide "I haven't warned recently" and print its own copy every interval --
    archive is the one state store this codebase already uses specifically because it IS shared
    across scripts (see CODE_GUIDES.md#archive).

    Since tank_matches_assignment() now denies an unassigned, never-latched tank by default (see
    module docstring), this is the operator's only signal that such a tank exists at all: it
    otherwise sits completely idle, invisible to every router, until assigned. curr_tick == 0
    (clock unavailable) always fires -- unlike PerEntryBlacklist's "no live clock == stay
    blacklisted" convention, an extra or duplicate print here is harmless where suppressing a
    genuine notice isn't.
    """
    last_warned = archive.get(LAST_UNASSIGNED_WARNING_TICK_KEY, None)
    if curr_tick != 0 and last_warned is not None and curr_tick - last_warned < UNASSIGNED_TANK_WARNING_INTERVAL_TICKS:
        return
    archive.set(LAST_UNASSIGNED_WARNING_TICK_KEY, curr_tick)

    tanks = discover_network_buildings(TANK_TYPE_IDS, resolve=True)
    assignments = get_tank_assignments()
    blocked = sorted({
        building.id for building, _outpost_id in tanks
        if not (hasattr(building, "fluid") and _safe_fluid(building)) and building.id not in assignments
    })
    if blocked:
        _add_blank_tank_assignments(blocked)
        message = (
            f"{len(blocked)} tank(s) are idle -- not latched to any fluid and not in "
            f"fluid_routing.tank_assignments, so no router will connect to them: {blocked} -- "
            "fill in their blank \"\" entries in the Data Archive Notebook (see docs/AI_CHEATSHEET.md)."
        )
        log.level("warn").print(message)
        notify(message)


def _add_blank_tank_assignments(building_ids):
    """Adds a blank "" tank_assignments entry for every id in building_ids that has no entry yet, so
    the operator only has to type the fluid id into the Notebook. A blank entry still counts as
    unassigned (get_tank_assignments() drops empty and non-string values), and an existing entry --
    blank or filled -- is never overwritten."""
    added = []

    def updater(stored):
        stored = dict(stored) if isinstance(stored, dict) else {}
        missing = [b_id for b_id in building_ids if b_id not in stored]
        for b_id in missing:
            stored[b_id] = ""
        added[:] = missing
        return stored
    if not archive.transaction(TANK_ASSIGNMENTS_KEY, {}, updater):
        log.level("warn").print(f"_add_blank_tank_assignments: archive write failed; no blank entries for {building_ids}.")
    elif added:
        log.debug(f"_add_blank_tank_assignments: added blank entries for {added}")


def _safe_fluid(building):
    try:
        return building.fluid()
    except Exception as error:
        swallowed("fluid_routing._safe_fluid: building.fluid", error)
        return None


class TickedDiscoveryCache:
    """
    Candidate-list cache shared by FluidOutputRouter and FluidInputRouter: recomputed at most every
    interval_ticks *simulation* ticks, and on the next get() after invalidate() (every
    blacklist/drop -- a failed target is exactly when a newly built/assigned tank is most likely the
    answer). curr_tick == 0 (no clock) always recomputes -- a stale list is the failure mode this
    cache must never cause. FluidOutputRouter's compute reads eligibility over the cached
    network_buildings() walk, so there a refresh catches a newly assigned tank at once and a newly
    built one within NETWORK_WALK_INTERVAL_TICKS.

    Tick-based on purpose, NOT counted in slow-path calls: routers only reach discovery on the slow
    path, so a call counter advanced once per rebalance/stall event and a new tank could stay
    invisible for 20 such events -- observed as turbine_10/11 cycling unreachable cross-outpost
    tanks while their own outpost's freshly assigned gas_tank_12/13 were never tried.
    """

    def __init__(self, interval_ticks):
        self.interval_ticks = interval_ticks
        self.value = None
        self._computed_at_tick = None

    def invalidate(self):
        self._computed_at_tick = None

    def get(self, curr_tick, compute):
        stale = (
            self.value is None
            or self._computed_at_tick is None
            or curr_tick == 0
            or curr_tick - self._computed_at_tick >= self.interval_ticks
        )
        if stale:
            self.value = compute()
            self._computed_at_tick = curr_tick
        return self.value


# The FluidOutputRouter network walk (outpost_network.outposts() x buildings(type_id) x
# get_component()) is reused for this many simulation ticks (~60 s at normal speed) by every router
# in the script with the same type ids. Only which buildings exist is cached: eligibility (latch,
# tank_assignments) and fill are read live on every TickedDiscoveryCache refresh / rebalance. A
# newly built tank is seen within this window; a cached building that fails to answer, or a
# connect() answering "not_found", forces a fresh walk at once.
NETWORK_WALK_INTERVAL_TICKS = 600
# tuple(type_ids) -> {"tick": walk tick, "buildings": [resolved component, ...]}
_NETWORK_WALK = {}


def _walk_key(type_ids):
    return (type_ids,) if isinstance(type_ids, str) else tuple(type_ids)


def invalidate_network_walk(type_ids):
    """Drops the cached walk for type_ids, so the next network_buildings() call walks again."""
    _NETWORK_WALK.pop(_walk_key(type_ids), None)


def network_buildings(type_ids, curr_tick):
    """Resolved components of every type_ids building network-wide (discover_network_buildings()
    order), from a walk at most NETWORK_WALK_INTERVAL_TICKS old. curr_tick == 0 (no clock) or a
    clock that went backwards always walks."""
    key = _walk_key(type_ids)
    entry = _NETWORK_WALK.get(key)
    if (entry is None or curr_tick == 0 or curr_tick < entry["tick"]
            or curr_tick - entry["tick"] >= NETWORK_WALK_INTERVAL_TICKS):
        entry = {"tick": curr_tick, "buildings": [b for b, _ in discover_network_buildings(key, resolve=True)]}
        _NETWORK_WALK[key] = entry
        log.debug(f"network walk {key}: {len(entry['buildings'])} building(s)")
    return entry["buildings"]


def eligible_targets(buildings, fluid_id):
    """The buildings tank_is_eligible_target() accepts for fluid_id (all of them for None), in order,
    with one archive read and one .fluid() per building. None when a building's .fluid() raised (it
    was most likely removed): the caller walks again."""
    if fluid_id is None:
        return list(buildings)
    try:
        fluids = [b.fluid() for b in buildings]
    except Exception as error:
        swallowed("fluid_routing.eligible_targets: building.fluid", error)
        return None
    assignments = get_tank_assignments()
    return [
        b for b, fluid in zip(buildings, fluids)
        if assignments.get(b.id) != RETIRING_ASSIGNMENT
        and (fluid == fluid_id if fluid else assignments.get(b.id) == fluid_id)
    ]


def rank_own_outpost_first(pairs, own_outpost_id):
    """Ids from discover_network_buildings(resolve=False)-shaped pairs, own outpost's first (stable
    otherwise). A same-outpost source can link "local" with no pipe at all, so it is far more likely
    reachable than a cross-outpost one."""
    return [b_id for b_id, _ in sorted(pairs, key=lambda p: p[1] != own_outpost_id)]


# Steam Turbine / Condenser / Mk III Heat Generator steam_in candidates: steam Gas Tanks, then Caps.
STEAM_SOURCE_TIERS = (("gas_tank", "steam"), ("thermal_cap", "steam"))


def discover_ranked(tiers, own_outpost_id):
    """Source ids tier by tier: each (type_ids, fluid_id) tier is discover_network_buildings(type_ids,
    resolve=False, fluid_id=fluid_id), own outpost first within the tier. fluid_id None skips the
    tank eligibility filter (a dedicated producer such as an Oil Pump)."""
    ranked = []
    for type_ids, fluid_id in tiers:
        pairs = discover_network_buildings(type_ids, resolve=False, fluid_id=fluid_id)
        ranked.extend(rank_own_outpost_first(pairs, own_outpost_id))
    return ranked


class FluidInputEvent:
    """Result of FluidInputRouter.ensure(). .kind is one of "no_port"/"reserved"/"healthy"/"pending"/"connected"/
    "waiting"/"not_found"/"exhausted". .source_id is set for "healthy" (the healthy peer, if known),
    "pending" (the declared source) and "connected"."""

    def __init__(self, kind, source_id=None):
        self.kind = kind
        self.source_id = source_id


class FluidInputRouter:
    """
    Shared consumer-side state machine: keep ONE input FluidPort pulling from a reachable source,
    network-wide. Used by SteamTurbineController (steam_in), FabricatorController (one per recipe
    fluid port) and the Biomass Mixer (one per <biome>_essence_in).

    Why not FluidOutputRouter: an output port rebalances among tanks by fill_pct() (leave a tank at
    ~98% full, prefer the least full); an input port doesn't care how full a source is, only whether
    fluid actually arrives, and one "healthy" signal is a peer-declared link (a Liquifier or Cap may
    declare itself onto this port). Different questions, different state -- one class per direction.

    Per call (ensure()), in order:
      1. starvation streak: is_starved (caller-supplied, since each machine exposes it differently --
         Turbine is_stalled(), Fabricator flow_rate()==0 with room left, Mixer per-port low buffer with
         flow_rate()==0) counted in consecutive calls; reset on every new connection.
         stall_streak_threshold=None disables starvation drops entirely.
      2. any peer in HEALTHY_CONNECTION_STATES and streak below stall_streak_threshold -> "healthy".
      3. own declared source (connected_id()): link state in BROKEN_CONNECTION_STATES -> drop now
         (FluidConnection.state is a direct reachability verdict, unlike is_stalled(), which is also
         harmlessly true while e.g. a vent is dormant); starved >= stall_streak_threshold -> drop;
         otherwise "neutral"/unknown gets neutral_grace_steps calls, then is dropped only if some
         other candidate exists (an empty unlatched tank may be the only option).
      4. slow path: discover (TickedDiscoveryCache; invalidated on every drop), filter the
         PerEntryBlacklist, connect() to the first candidate whose link state isn't already broken
         right after "ok" ("ok" only records intent -- docs/guide/flow_networks_fluids.md).

    discover is a zero-arg callable returning ranked candidate ids -- each caller owns which
    building types count and how they rank (rank_own_outpost_first() for the common case). Does no
    printing at info level: on_dropped(source_id, reason) / on_connect_notice(source_id, status,
    message) callbacks fire synchronously for side events, like FluidOutputRouter's.
    """

    def __init__(self, discover, rescan_interval_ticks, discovery_cache_interval_ticks,
                 neutral_grace_steps, stall_streak_threshold=None, label="input", reserve_fluid=None):
        self.discover = discover
        # "water": yields the port while water_reserve_holds() (Reactor reservation).
        self.reserve_fluid = reserve_fluid
        self.stall_streak_threshold = stall_streak_threshold
        self.neutral_grace_steps = neutral_grace_steps
        self.label = label
        self.blacklist = PerEntryBlacklist(rescan_interval_ticks)
        self._cache = TickedDiscoveryCache(discovery_cache_interval_ticks)
        self.stall_streak = 0
        # Starts at 0 on (re)start so a link that's merely neutral after a power cycle gets its grace too.
        self.steps_since_connect = 0
        # True once the port has had a healthy link since this router last connected it; decides who
        # yields a pipe conflict (see ESTABLISHED_CONFLICT_GRACE_STEPS).
        self.was_healthy = False
        self.conflict_steps = 0

    @property
    def known_candidates(self):
        """Last discovered candidate ids (empty before first discovery)."""
        return self._cache.value or []

    def _yield_to_reserve(self, port: "FluidPort"):
        """Disconnects the port for the water reservation; the next ensure() after it lifts reconnects."""
        self.stall_streak = 0
        self.steps_since_connect = 0
        self.was_healthy = False
        try:
            own_id = port.connected_id() if hasattr(port, "connected_id") else None
            if own_id and hasattr(port, "disconnect"):
                port.disconnect()
                log.debug(f"FluidInputRouter({self.label}): water reserved for Reactors, disconnected '{own_id}'")
        except Exception as error:
            swallowed("fluid_routing.FluidInputRouter._yield_to_reserve: port.disconnect", error)

    def _drop(self, source_id, curr_tick, reason, on_dropped):
        self.blacklist.blacklist(source_id, curr_tick)
        self._cache.invalidate()
        self.stall_streak = 0
        log.debug(f"FluidInputRouter({self.label}): dropping '{source_id}' ({reason})")
        if on_dropped:
            on_dropped(source_id, reason)

    def ensure(self, port: "FluidPort", curr_tick, is_starved=False, on_dropped=None, on_connect_notice=None):
        log.start("ensure", level="debug")
        if not port or not hasattr(port, "connect"):
            _ret = FluidInputEvent("no_port")
            log.end()
            return _ret

        if self.reserve_fluid == "water" and water_reserve_holds(curr_tick):
            self._yield_to_reserve(port)
            log.end()
            return FluidInputEvent("reserved")

        self.stall_streak = self.stall_streak + 1 if is_starved else 0
        starved_out = self.stall_streak_threshold is not None and self.stall_streak >= self.stall_streak_threshold

        peer = healthy_peer_id(port)
        if peer and not starved_out:
            if self.stall_streak:
                log.debug(f"FluidInputRouter({self.label}): healthy link via '{peer}' but starved {self.stall_streak}/{self.stall_streak_threshold} -- waiting (source may be temporarily dry)")
            self.was_healthy = True
            self.conflict_steps = 0
            _ret = FluidInputEvent("healthy", peer)
            log.end()
            return _ret

        self.steps_since_connect += 1
        try:
            own_id = port.connected_id() if hasattr(port, "connected_id") else None
        except Exception as error:
            swallowed("fluid_routing.FluidInputRouter.ensure: port.connected_id", error)
            own_id = None
        own_conn = declared_connection(port)
        own_state = getattr(own_conn, "state", None)

        if own_id and own_state == "conflict":
            self.conflict_steps += 1
            if self.was_healthy and self.conflict_steps < ESTABLISHED_CONFLICT_GRACE_STEPS:
                log.debug(f"FluidInputRouter({self.label}): established link to '{own_id}' in conflict ({self.conflict_steps}/{ESTABLISHED_CONFLICT_GRACE_STEPS}), waiting for the newcomer to yield")
                _ret = FluidInputEvent("pending", own_id)
                log.end()
                return _ret
            yield_pipe_conflict(port, self.label, own_id, getattr(own_conn, "fluid", None), curr_tick, self.blacklist)
            self._cache.invalidate()
            self.stall_streak = 0
            self.was_healthy = False
            self.conflict_steps = 0
            own_id = None
        else:
            self.conflict_steps = 0

        # The port keeps pointing at a dropped source until a new connect() succeeds -- don't
        # re-drop it every call (that would re-warn, restart its blacklist clock so it never
        # expires, and force a network rescan each step).
        if own_id and self.blacklist.is_blacklisted(own_id, curr_tick):
            own_id_already_dropped = True
        else:
            own_id_already_dropped = False

        if own_id and not own_id_already_dropped:
            if own_state in BROKEN_CONNECTION_STATES:
                self._drop(own_id, curr_tick, f"link state '{own_state}'", on_dropped)
            elif starved_out:
                self._drop(own_id, curr_tick, f"starved {self.stall_streak} consecutive checks (link state '{own_state}')", on_dropped)
            elif self.steps_since_connect < self.neutral_grace_steps:
                log.debug(f"FluidInputRouter({self.label}): '{own_id}' is {own_state!r}, within grace ({self.steps_since_connect}/{self.neutral_grace_steps})")
                _ret = FluidInputEvent("pending", own_id)
                log.end()
                return _ret
            else:
                others = [c for c in self.blacklist.filter_reachable(self._cache.get(curr_tick, self.discover), curr_tick) if c != own_id]
                if not others:
                    log.debug(f"FluidInputRouter({self.label}): '{own_id}' still {own_state!r} but no alternative source; keeping it")
                    _ret = FluidInputEvent("pending", own_id)
                    log.end()
                    return _ret
                self._drop(own_id, curr_tick, f"link still {own_state!r} after {self.steps_since_connect} checks", on_dropped)

        all_known = self._cache.get(curr_tick, self.discover)
        candidates = [c for c in self.blacklist.filter_reachable(all_known, curr_tick) if c != own_id]
        if not candidates:
            # Deliberately never wipe the blacklist here -- each entry expires on its own
            # schedule (see PerEntryBlacklist for the ping-pong this avoids).
            log.debug(f"FluidInputRouter({self.label}): {'every known source still blacklisted' if all_known else 'no known sources at all'}")
            _ret = FluidInputEvent("waiting") if all_known else FluidInputEvent("not_found")
            log.end()
            return _ret

        log.debug(f"FluidInputRouter({self.label}): trying candidates in order {candidates}")
        for source_id in candidates:
            try:
                res = port.connect(source_id)
            except Exception as error:
                swallowed("fluid_routing.FluidInputRouter.ensure: port.connect", error)
                continue
            if res.status == "ok":
                link = declared_connection(port)
                link_state = getattr(link, "state", None)
                if link_state == "conflict":
                    yield_pipe_conflict(port, self.label, source_id, getattr(link, "fluid", None), curr_tick, self.blacklist)
                    continue
                if link_state in BROKEN_CONNECTION_STATES:
                    self.blacklist.blacklist(source_id, curr_tick)
                    log.debug(f"FluidInputRouter({self.label}): '{source_id}' accepted but link state '{link_state}'; blacklisted, trying next")
                    continue
                self.steps_since_connect = 0
                self.stall_streak = 0
                self.was_healthy = False
                log.debug(f"FluidInputRouter({self.label}): connected -> '{source_id}' (link state '{link_state}')")
                _ret = FluidInputEvent("connected", source_id)
                log.end()
                return _ret
            if res.status != "busy" and on_connect_notice:
                on_connect_notice(source_id, res.status, res.message)

        log.debug(f"FluidInputRouter({self.label}): every candidate rejected, busy or broken this pass -- exhausted")
        _ret = FluidInputEvent("exhausted")
        log.end()
        return _ret


def _target_id(target):
    return target.id


# A candidate must be emptier than the full current target by more than this fill fraction for the
# output router to switch to it; equally full tanks never trade places.
OUTPUT_REBALANCE_MARGIN = 0.02
# FluidOutputRouter(local_outpost_id=...): a cross-outpost target is left for an own-outpost one
# below rebalance_fill_fraction minus this margin, so a local tank near full does not flip back and forth.
LOCAL_RETURN_MARGIN = 0.10


class FluidOutputEvent:
    """Result of FluidOutputRouter.ensure_connection(). .kind is one of "no_port"/"healthy"/"full"/"waiting"/"not_found"/"connected"/"exhausted". "full": the current target is full and no candidate is emptier, so it stays connected. .target_id/.fill_pct/.rebalance are only meaningful for "connected" (default None/0.0/False otherwise); .rebalance is True when a still-usable current target was left for an emptier one (routine, debug-level), False for a first or replacement connection."""

    def __init__(self, kind, target_id=None, fill_pct=0.0, rebalance=False):
        self.kind = kind
        self.target_id = target_id
        self.fill_pct = fill_pct
        self.rebalance = rebalance


class FluidOutputRouter:
    """
    Shared "declare/rebalance a single-destination output FluidPort among
    reachable same-type buildings, network-wide" state machine, used
    identically by ThermalCapController.ensure_output_connection() (steam_out
    -> Gas Tank) and FluidPumpController.ensure_output_connection() (water_out/oil_out
    -> Liquid Tank/Large Liquid Tank).

    Consumer-side input ports (Steam Turbine, Fabricator, Biomass Mixer) use
    FluidInputRouter below instead -- see its docstring for why the two
    directions stay separate classes.

    This class does no printing -- Cap and Pump report the same events in
    different domain vocabulary ("steam available" vs "well water
    available", "Gas Pipe" vs "Liquid Pipe", "Gas Tank" vs "Liquid Tank or
    Large Liquid Tank"). Callers pass on_blacklisted(target_id) /
    on_connect_notice(target_id, status, message) callbacks invoked
    synchronously, in order, for side-events that can occur in addition to
    the single terminal event returned from a call -- mirrors the original
    methods' shape exactly.

    local_outpost_id (the producer's own outpost; None for Caps, Pumps and Taps): own-outpost
    targets rank first, another outpost's tank that feeds a cross-outpost route ranks last, and a
    healthy cross-outpost target is left once an own-outpost one has room
    (fill < rebalance_fill_fraction - LOCAL_RETURN_MARGIN). The game moves same-outpost
    links directly; a cross-outpost link from a building that is not a Cap/Pump/Tap goes through
    the pipe network's shared pool, where a tank that also feeds machines over that network and
    holds stock takes nothing (docs/cheatsheet/power_fluids.md §1c-5).
    """

    def __init__(self, type_ids, rebalance_fill_fraction, connection_grace_ticks,
                 rescan_interval_ticks, discovery_cache_interval_ticks, fluid_id=None, label="output",
                 local_outpost_id=None):
        self.type_ids = type_ids
        self.fluid_id = fluid_id
        self.label = label
        self.local_outpost_id = local_outpost_id
        self.rebalance_fill_fraction = rebalance_fill_fraction
        self.connection_grace_ticks = connection_grace_ticks
        self.discovery_cache_interval_ticks = discovery_cache_interval_ticks
        self.blacklist = PerEntryBlacklist(rescan_interval_ticks)
        self.ticks_since_connect = 0
        self._cache = TickedDiscoveryCache(discovery_cache_interval_ticks)
        # id -> resolved building object, merged across rediscovery, never
        # wholesale-cleared -- a building's identity doesn't change between
        # scans, only the candidate list goes stale.
        self._target_lookup = {}
        # Candidate ids of the last refresh; the "rediscovered" debug line is logged only when they change.
        self._last_ids = None
        # Tracked locally instead of re-querying the port every step.
        # Synced from the port's stable id exactly once, at bootstrap (via
        # connected_id(), not connected_to() -- connected_to() returns the
        # renameable display name, which would desync from the id every
        # other lookup here keys on if the player ever renames the target),
        # then only ever updated by this router's own connect() calls.
        self._connected_id = None
        self._id_synced = False
        # True once the current target has flowed unstalled since this router connected it: such a
        # link turning "conflict" was joined by someone else, so this side keeps the plain stall
        # blacklist instead of yielding (FluidInputRouter.was_healthy, same rule).
        self.was_healthy = False

    @property
    def _cached_targets(self):
        """Last discovered target list (None before first discovery) -- read by callers' debug lines."""
        return self._cache.value

    def _discover_targets_cached(self, curr_tick):
        """Eligible target objects network-wide, via TickedDiscoveryCache (tick-based, invalidated on
        blacklist). A refresh re-reads eligibility live over the cached network walk
        (network_buildings()); the walk itself only repeats every NETWORK_WALK_INTERVAL_TICKS."""
        def discover():
            buildings = network_buildings(self.type_ids, curr_tick)
            targets = eligible_targets(buildings, self.fluid_id)
            if targets is None:
                invalidate_network_walk(self.type_ids)
                buildings = network_buildings(self.type_ids, curr_tick)
                targets = eligible_targets(buildings, self.fluid_id)
            if targets is None:
                assignments = get_tank_assignments()
                targets = [b for b in buildings if tank_is_eligible_target(b, self.fluid_id, assignments)]
            ids = [b.id for b in targets]
            self._target_lookup.update(zip(ids, targets))
            if ids != self._last_ids:
                self._last_ids = ids
                log.debug(f"FluidOutputRouter({self.type_ids}): rediscovered {len(targets)} candidate target(s): {ids}")
            return targets
        return self._cache.get(curr_tick, discover)

    def _least_full_first(self, candidates):
        """[(target, fill_pct), ...] least-full first, ties in discovery order (the order of
        sorted(candidates, key=fill_pct_of)), one fill_pct() per candidate."""
        if not candidates:
            return []
        try:
            fills = [t.fill_pct() for t in candidates]
        except Exception as error:
            swallowed("fluid_routing.FluidOutputRouter._least_full_first: fill_pct", error)
            invalidate_network_walk(self.type_ids)
            self._cache.invalidate()
            fills = [fill_pct_of(t) for t in candidates]
        return [(candidates[i], fill) for fill, i in sorted(zip(fills, range(len(candidates))))]

    def _is_local(self, building):
        """Whether building stands in local_outpost_id (False without one)."""
        if self.local_outpost_id is None:
            return False
        return getattr(getattr(building, "outpost", None), "id", None) == self.local_outpost_id

    def _remote_rank(self, building):
        """Sort key with local_outpost_id: own outpost 0, other outposts 1, another outpost's
        tank that feeds a cross-outpost route 2 (this producer's pipe output only reaches that
        tank's consumers, the tank itself never fills; feeds_remote_route())."""
        if self._is_local(building):
            return 0
        return 2 if feeds_remote_route(building) else 1

    def _local_with_room(self, curr_tick):
        """Id of a non-blacklisted own-outpost target below the local return threshold, or None."""
        limit = self.rebalance_fill_fraction - LOCAL_RETURN_MARGIN
        targets = self.blacklist.filter_reachable(self._discover_targets_cached(curr_tick), curr_tick, key=_target_id)
        for target in targets:
            if self._is_local(target) and fill_pct_of(target) < limit:
                return target.id
        return None

    def _resolve_target(self, target_id):
        """Building object for target_id, preferring the cache filled by discovery over a fresh get_component() round trip."""
        building = self._target_lookup.get(target_id)
        if building is not None:
            return building
        try:
            building = get_component(target_id)
        except Exception as error:
            swallowed("fluid_routing.FluidOutputRouter._resolve_target: get_component", error)
            building = None
        if building:
            self._target_lookup[target_id] = building
        return building

    def ensure_connection(self, port: "FluidPort", curr_tick, is_stalled, on_blacklisted=None, on_connect_notice=None):
        """Returns a FluidOutputEvent. See class docstring for callback timing. Caller is responsible for the port-null guard before calling (matches the original methods' early-return ordering)."""
        log.start("ensure_connection", level="debug")
        warn_about_unassigned_tanks(curr_tick)

        if not self._id_synced:
            try:
                self._connected_id = port.connected_id() if hasattr(port, "connected_id") else None
            except Exception as error:
                swallowed("fluid_routing.FluidOutputRouter.ensure_connection: port.connected_id", error)
                self._connected_id = None
            self._id_synced = True
        current_id = self._connected_id

        self.ticks_since_connect += 1

        # A stall on a full target is the tank refusing fluid, not a broken route: no blacklist.
        stalled_on_full = False
        if is_stalled and current_id:
            stalled_current = self._resolve_target(current_id)
            stalled_on_full = bool(stalled_current) and fill_pct_of(stalled_current) >= self.rebalance_fill_fraction
        if stalled_on_full:
            log.debug(f"FluidOutputRouter({self.type_ids}): '{current_id}' stalled while full, not a route failure")

        if is_stalled and not stalled_on_full and current_id and not self.blacklist.is_blacklisted(current_id, curr_tick) and self.ticks_since_connect >= self.connection_grace_ticks:
            link = None if self.was_healthy else declared_connection(port)
            if getattr(link, "state", None) == "conflict":
                yield_pipe_conflict(port, self.label, current_id, getattr(link, "fluid", None), curr_tick, self.blacklist)
            else:
                log.debug(f"FluidOutputRouter({self.type_ids}): '{current_id}' stalled past grace period ({self.ticks_since_connect} >= {self.connection_grace_ticks} ticks), blacklisting")
                self.blacklist.blacklist(current_id, curr_tick)
                if on_blacklisted:
                    on_blacklisted(current_id)
            current_id = None
            self._connected_id = None
            self._cache.invalidate()

        # Fast path: a connection already judged healthy needs no network
        # scan, just the cached (not necessarily fresh) resolved target --
        # see _resolve_target(). Fill first (a full target fails here without
        # the eligibility read), then tank_is_eligible_target() every call so
        # an operator reassigning this exact tank to a different fluid is
        # caught immediately, not only whenever it next happens to stall: one
        # .fill_pct(), one .fluid() and one archive read.
        stay_fill = None  # fill of a usable but full current target
        if current_id and not self.blacklist.is_blacklisted(current_id, curr_tick):
            current = self._resolve_target(current_id)
            current_fill = fill_pct_of(current)
            if self.fluid_id is None or tank_is_eligible_target(current, self.fluid_id):
                local_id = None
                if current_fill < self.rebalance_fill_fraction and self.local_outpost_id is not None and not self._is_local(current):
                    local_id = self._local_with_room(curr_tick)
                if current_fill < self.rebalance_fill_fraction and local_id is None:
                    if not is_stalled:
                        self.was_healthy = True
                    _ret = FluidOutputEvent("healthy")
                    log.end()
                    return _ret
                if local_id is not None:
                    log.debug(f"FluidOutputRouter({self.type_ids}): '{current_id}' is outside {self.local_outpost_id}, own-outpost '{local_id}' has room, rebalancing")
                    stay_fill = 1.0
                elif current:
                    stay_fill = current_fill

        all_known_targets = self._discover_targets_cached(curr_tick)
        targets = self.blacklist.filter_reachable(all_known_targets, curr_tick, key=_target_id)
        if not targets:
            # Every known target is still within its own blacklist window
            # (or none exist at all) -- deliberately do NOT wipe the
            # blacklist here; each entry expires on its own schedule.
            log.debug(f"FluidOutputRouter({self.type_ids}): {'every known target still blacklisted' if all_known_targets else 'no known targets at all'}")
            _ret = FluidOutputEvent("waiting") if all_known_targets else FluidOutputEvent("not_found")
            log.end()
            return _ret

        # Try the least-full known target first (load-balances across
        # several), falling through to the next since not every target is
        # necessarily physically pipe-reachable from this port's location.
        log.debug(f"FluidOutputRouter({self.type_ids}): current='{current_id}' not healthy, rebalancing among {len(targets)} reachable candidate(s) (least-full first)")
        ranked = self._least_full_first([t for t in targets if t.id != current_id])
        if self.local_outpost_id is not None:
            ranked = sorted(ranked, key=lambda pair: self._remote_rank(pair[0]))
        if stay_fill is not None:
            ranked = [(t, f) for t, f in ranked if f < stay_fill - OUTPUT_REBALANCE_MARGIN]
            if not ranked:
                log.debug(f"FluidOutputRouter({self.type_ids}): '{current_id}' full ({stay_fill:.2f}), no emptier candidate, staying")
                _ret = FluidOutputEvent("full")
                log.end()
                return _ret
        for target, fill in ranked:
            try:
                res = port.connect(target.id)
            except Exception as error:
                swallowed("fluid_routing.FluidOutputRouter.ensure_connection: port.connect", error)
                continue
            if res.status == "ok":
                link = declared_connection(port)
                if getattr(link, "state", None) == "conflict":
                    yield_pipe_conflict(port, self.label, target.id, getattr(link, "fluid", None), curr_tick, self.blacklist)
                    self._connected_id = None
                    continue
                self.ticks_since_connect = 0
                self.was_healthy = False
                self._connected_id = target.id
                log.debug(f"FluidOutputRouter({self.type_ids}): connected -> '{target.id}' (fill={fill:.2f})")
                _ret = FluidOutputEvent("connected", target_id=target.id, fill_pct=fill, rebalance=stay_fill is not None)
                log.end()
                return _ret
            elif res.status != "busy":
                if res.status == "not_found":
                    invalidate_network_walk(self.type_ids)
                    self._cache.invalidate()
                if on_connect_notice:
                    on_connect_notice(target.id, res.status, res.message)

        log.debug(f"FluidOutputRouter({self.type_ids}): every candidate rejected or busy this pass -- exhausted")
        _ret = FluidOutputEvent("exhausted")
        log.end()
        return _ret


def _log_waiting(log: "TreeConsole", name, port_label, blacklist, curr_tick):
    log.debug(f"[{name}] Every known {port_label} candidate is still within its blacklist window; waiting for one to expire.")
    for entry_id, blacklisted_at in blacklist._blacklisted_at.items():
        duration = blacklist._durations.get(entry_id, blacklist.rescan_interval_ticks)
        log.trace(f"[{name}] Blacklisted '{entry_id}': {max(0, duration - (curr_tick - blacklisted_at))} tick(s) until retry-eligible.")


def ensure_input_logged(router, port: "FluidPort", curr_tick, starved, log: "TreeConsole", name, port_label, not_found=None):
    """FluidInputRouter.ensure() with the standard lines on the caller's console: drops and connect
    notices warn, a new connection info, healthy trace, waiting debug (blacklist detail trace),
    not_found debug with the caller's `not_found` text (None: no line). Returns the event."""
    def on_dropped(source_id, reason):
        log.level("warn").print(f"[{name}] Dropping {port_label} source '{source_id}': {reason}. Picking another.")

    def on_connect_notice(source_id, status, message):
        log.level("warn").print(f"[{name}] {port_label} connect notice for '{source_id}': {status} - {message}")

    event = router.ensure(port, curr_tick, starved, on_dropped, on_connect_notice)
    if event.kind == "connected":
        log.print(f"[{name}] Connected {port_label} -> '{event.source_id}'.")
    elif event.kind == "healthy":
        log.trace(f"[{name}] {port_label}: healthy via '{event.source_id}'.")
    elif event.kind == "waiting":
        _log_waiting(log, name, port_label, router.blacklist, curr_tick)
    elif event.kind == "not_found" and not_found:
        log.debug(f"[{name}] {not_found}")
    return event


def ensure_output_logged(router, port: "FluidPort", curr_tick, stalled, log: "TreeConsole", name, port_label, blacklist_reason, not_found=None):
    """FluidOutputRouter.ensure_connection() with the standard lines: a blacklisted target warns
    "'<id>' <blacklist_reason>. Blacklisting ...", connect notices warn, a new connection info (with
    fill; debug for a rebalance to an emptier tank), healthy and full trace, waiting debug, not_found debug with `not_found` (None: no line). Returns
    the event."""
    def on_blacklisted(target_id):
        log.level("warn").print(f"[{name}] '{target_id}' {blacklist_reason}. Blacklisting and picking a different target.")

    def on_connect_notice(target_id, status, message):
        log.level("warn").print(f"[{name}] {port_label} connect notice for '{target_id}': {status} - {message}")

    event = router.ensure_connection(port, curr_tick, stalled, on_blacklisted, on_connect_notice)
    if event.kind == "connected":
        (log.debug if event.rebalance else log.print)(f"[{name}] Connected {port_label} -> '{event.target_id}' ({event.fill_pct*100:.0f}% full).")
    elif event.kind == "healthy":
        log.trace(f"[{name}] Current {port_label} target still healthy; no rebalance needed this cycle.")
    elif event.kind == "full":
        log.trace(f"[{name}] Current {port_label} target full and no emptier tank; staying connected.")
    elif event.kind == "waiting":
        _log_waiting(log, name, port_label, router.blacklist, curr_tick)
    elif event.kind == "not_found" and not_found:
        log.debug(f"[{name}] {not_found}")
    return event
