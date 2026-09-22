# Shared "network-wide reachable-fluid-target" mechanism used by
# lib/thermal_cap.py, lib/water_pump.py, and lib/steam_turbine.py -- each
# independently implemented "discover Gas/Liquid Tank or Thermal Cap
# candidates network-wide, try to connect, verify reachability via
# is_stalled() (connect()'s "ok" status never confirms a completed physical
# pipe route exists -- see docs/guide/infrastructure_and_pipes.md), and
# blacklist an unreachable target with per-entry (not shared-clock) expiry."
# Thermal Cap and Water Pump's versions were ~100% identical copy-paste
# (same fields, same method bodies, differing only in type-id string(s)/
# port name/fill-fraction constant/print wording) -- FluidOutputRouter below
# is that shared state machine. Steam Turbine's consumer-side selection has
# real behavioral differences (streak-based blacklist criterion instead of a
# grace period, no proactive fill-based rebalancing, no id-lookup/
# connected-id-sync optimizations, own-outpost-first candidate ranking) and
# deliberately keeps its own ensure_input_connection() body, composing only
# the smaller primitives below (PerEntryBlacklist, discover_network_buildings(),
# safe_is_stalled()) rather than being forced through FluidOutputRouter.
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

from archive import archive
from tree_console import TreeConsole

log = TreeConsole(module="fluid_routing")

TANK_ASSIGNMENTS_KEY = "fluid_routing.tank_assignments"


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


def tank_matches_assignment(building_id, fluid_id):
    """True only if building_id is explicitly assigned to exactly fluid_id; False if assigned to a
    different fluid_id OR not assigned at all. Deliberately deny-by-default on no entry -- see the
    module docstring for why "unrestricted until proven otherwise" was rejected. This is the pure
    registry check; it has no way to know a tank is already safely latched to fluid_id (that needs
    the live building object, not just its id) -- callers that have a resolved building should use
    tank_is_eligible_target() below instead, which checks that first and only falls back to this
    for a tank that isn't already latched to anything."""
    return get_tank_assignments().get(building_id) == fluid_id


def tank_is_eligible_target(building, fluid_id):
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
    """
    current_fluid = None
    if building is not None and hasattr(building, "fluid"):
        try:
            current_fluid = building.fluid()
        except Exception:
            current_fluid = None
    if current_fluid:
        return current_fluid == fluid_id
    b_id = getattr(building, "id", None)
    if not b_id:
        return False
    return tank_matches_assignment(b_id, fluid_id)


def safe_is_stalled(building):
    """hasattr-guarded, exception-swallowed building.is_stalled() probe. See module docstring for why is_stalled() is the only live reachability signal."""
    if not building or not hasattr(building, "is_stalled"):
        return False
    try:
        return building.is_stalled()
    except Exception:
        return False


def fill_pct_of(building):
    """fill_pct() of an already-resolved building object, or 1.0 ("full, deprioritize") if unreadable/missing."""
    if not building or not hasattr(building, "fill_pct"):
        return 1.0
    try:
        return building.fill_pct()
    except Exception:
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

    def is_blacklisted(self, entry_id, curr_tick):
        blacklisted_at = self._blacklisted_at.get(entry_id)
        if blacklisted_at is None:
            return False
        age = curr_tick - blacklisted_at
        still_blacklisted = curr_tick == 0 or age < self.rescan_interval_ticks
        if not still_blacklisted:
            log.debug(f"PerEntryBlacklist: '{entry_id}' blacklist expired (age={age} >= {self.rescan_interval_ticks}), eligible again")
        return still_blacklisted

    def blacklist(self, entry_id, curr_tick):
        log.debug(f"PerEntryBlacklist: blacklisting '{entry_id}' at tick={curr_tick} (expires after {self.rescan_interval_ticks} ticks)")
        self._blacklisted_at[entry_id] = curr_tick

    def filter_reachable(self, entries, curr_tick, key=lambda e: e):
        return [e for e in entries if not self.is_blacklisted(key(e), curr_tick)]


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
                            except Exception:
                                resolved = building

                        if fluid_id is not None and not tank_is_eligible_target(resolved, fluid_id):
                            continue

                        seen_ids.add(b_id)
                        pairs.append((resolved if resolve else b_id, outpost_id))
        except Exception:
            pass
    log.trace(f"discover_network_buildings({type_ids}): found {len(pairs)} building(s)")
    return pairs


# liquid_tank/large_liquid_tank/gas_tank -- mirrors production.BUFFER_FLUID_TYPE_IDS, not
# imported from there to avoid a circular import (production.py already imports from this
# module). Kept in sync by hand; both lists are short and rarely change.
TANK_TYPE_IDS = ("liquid_tank", "large_liquid_tank", "gas_tank")


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
    current .fluid() -- e.g. after re-plumbing a tank onto a different network.

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
        except Exception:
            fluid = None
        if not fluid:
            skipped_empty += 1
            continue
        if not overwrite and b_id in existing:
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
    across scripts (see CLAUDE.md's Data Archive rule).

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
    blocked = sorted({
        building.id for building, _outpost_id in tanks
        if not (hasattr(building, "fluid") and _safe_fluid(building)) and building.id not in get_tank_assignments()
    })
    if blocked:
        message = (
            f"{len(blocked)} tank(s) are idle -- not latched to any fluid and not in "
            f"fluid_routing.tank_assignments, so no router will connect to them: {blocked} -- "
            "designate them in the Data Archive Notebook (see docs/AI_CHEATSHEET.md)."
        )
        log.level("warn").print(message)
        notify(message)


def _safe_fluid(building):
    try:
        return building.fluid()
    except Exception:
        return None


class FluidOutputEvent:
    """Result of FluidOutputRouter.ensure_connection(). .kind is one of "no_port"/"healthy"/"waiting"/"not_found"/"connected"/"exhausted". .target_id/.fill_pct are only meaningful for "connected" (default None/0.0 otherwise)."""

    def __init__(self, kind, target_id=None, fill_pct=0.0):
        self.kind = kind
        self.target_id = target_id
        self.fill_pct = fill_pct


class FluidOutputRouter:
    """
    Shared "declare/rebalance a single-destination output FluidPort among
    reachable same-type buildings, network-wide" state machine, used
    identically by ThermalCapController.ensure_output_connection() (steam_out
    -> Gas Tank) and WaterPumpController.ensure_output_connection() (water_out
    -> Liquid Tank/Large Liquid Tank).

    Steam Turbine's ensure_input_connection() is deliberately NOT built on
    this class: it blacklists on a STALL_STREAK_BLACKLIST_THRESHOLD-tick
    consecutive-stall streak rather than a single stalled tick + grace
    period (a Turbine's is_stalled() is ambiguous -- also harmlessly true
    whenever the feeding vent is dormant, unlike Cap/Pump's), has no
    proactive fill_pct-based rebalancing at all (a consumer doesn't care
    about a source's fill level, only reachability), and its healthy fast
    path touches zero port methods (no id-lookup cache, no
    connected-id-sync) where this class's does both. Forcing Turbine through
    this class's parameters would either drop that behavior or bloat this
    class with turbine-only branches for something used by exactly one
    caller -- it instead composes PerEntryBlacklist and
    discover_network_buildings() directly. See lib/steam_turbine.py.

    This class does no printing -- Cap and Pump report the same events in
    different domain vocabulary ("steam available" vs "well water
    available", "Gas Pipe" vs "Liquid Pipe", "Gas Tank" vs "Liquid Tank or
    Large Liquid Tank"). Callers pass on_blacklisted(target_id) /
    on_connect_notice(target_id, status, message) callbacks invoked
    synchronously, in order, for side-events that can occur in addition to
    the single terminal event returned from a call -- mirrors the original
    methods' shape exactly.
    """

    def __init__(self, type_ids, rebalance_fill_fraction, connection_grace_ticks,
                 rescan_interval_ticks, discovery_cache_interval_steps, fluid_id=None):
        self.type_ids = type_ids
        self.fluid_id = fluid_id
        self.rebalance_fill_fraction = rebalance_fill_fraction
        self.connection_grace_ticks = connection_grace_ticks
        self.discovery_cache_interval_steps = discovery_cache_interval_steps
        self.blacklist = PerEntryBlacklist(rescan_interval_ticks)
        self.ticks_since_connect = 0
        self._cached_targets = None
        self._ticks_since_discovery = 0
        # id -> resolved building object, merged across rediscovery, never
        # wholesale-cleared -- a building's identity doesn't change between
        # scans, only the candidate list goes stale.
        self._target_lookup = {}
        # Tracked locally instead of re-querying the port every step.
        # Synced from the port's stable id exactly once, at bootstrap (via
        # connected_id(), not connected_to() -- connected_to() returns the
        # renameable display name, which would desync from the id every
        # other lookup here keys on if the player ever renames the target),
        # then only ever updated by this router's own connect() calls.
        self._connected_id = None
        self._id_synced = False

    def _discover_targets_cached(self):
        """Target objects network-wide, refreshed at most every discovery_cache_interval_steps calls."""
        if self._cached_targets is None or self._ticks_since_discovery >= self.discovery_cache_interval_steps:
            self._cached_targets = [b for b, _ in discover_network_buildings(self.type_ids, fluid_id=self.fluid_id)]
            for building in self._cached_targets:
                self._target_lookup[building.id] = building
            self._ticks_since_discovery = 0
            log.debug(f"FluidOutputRouter({self.type_ids}): rediscovered {len(self._cached_targets)} candidate target(s)")
        else:
            self._ticks_since_discovery += 1
        return self._cached_targets

    def _resolve_target(self, target_id):
        """Building object for target_id, preferring the cache filled by discovery over a fresh get_component() round trip."""
        building = self._target_lookup.get(target_id)
        if building is not None:
            return building
        try:
            building = get_component(target_id)
        except Exception:
            building = None
        if building:
            self._target_lookup[target_id] = building
        return building

    def ensure_connection(self, port, curr_tick, is_stalled, on_blacklisted=None, on_connect_notice=None):
        """Returns a FluidOutputEvent. See class docstring for callback timing. Caller is responsible for the port-null guard before calling (matches the original methods' early-return ordering)."""
        warn_about_unassigned_tanks(curr_tick)

        if not self._id_synced:
            try:
                self._connected_id = port.connected_id() if hasattr(port, "connected_id") else None
            except Exception:
                self._connected_id = None
            self._id_synced = True
        current_id = self._connected_id

        self.ticks_since_connect += 1

        if is_stalled and current_id and not self.blacklist.is_blacklisted(current_id, curr_tick) and self.ticks_since_connect >= self.connection_grace_ticks:
            log.debug(f"FluidOutputRouter({self.type_ids}): '{current_id}' stalled past grace period ({self.ticks_since_connect} >= {self.connection_grace_ticks} ticks), blacklisting")
            self.blacklist.blacklist(current_id, curr_tick)
            if on_blacklisted:
                on_blacklisted(current_id)
            current_id = None
            self._connected_id = None

        # Fast path: a connection already judged healthy needs no network
        # scan, just the cached (not necessarily fresh) resolved target --
        # see _resolve_target(). Still re-checks tank_is_eligible_target()
        # every call so an operator reassigning this exact tank to a
        # different fluid is caught immediately, not only whenever it next
        # happens to stall. In the overwhelmingly common case this target is
        # already latched to self.fluid_id, so the check is a cheap "read
        # one cached building's .fluid()", not a registry lookup at all.
        if (current_id and not self.blacklist.is_blacklisted(current_id, curr_tick)
                and (self.fluid_id is None or tank_is_eligible_target(self._resolve_target(current_id), self.fluid_id))
                and fill_pct_of(self._resolve_target(current_id)) < self.rebalance_fill_fraction):
            return FluidOutputEvent("healthy")

        all_known_targets = self._discover_targets_cached()
        targets = self.blacklist.filter_reachable(all_known_targets, curr_tick, key=lambda t: t.id)
        if not targets:
            # Every known target is still within its own blacklist window
            # (or none exist at all) -- deliberately do NOT wipe the
            # blacklist here; each entry expires on its own schedule.
            log.debug(f"FluidOutputRouter({self.type_ids}): {'every known target still blacklisted' if all_known_targets else 'no known targets at all'}")
            return FluidOutputEvent("waiting") if all_known_targets else FluidOutputEvent("not_found")

        # Try the least-full known target first (load-balances across
        # several), falling through to the next since not every target is
        # necessarily physically pipe-reachable from this port's location.
        log.debug(f"FluidOutputRouter({self.type_ids}): current='{current_id}' not healthy, rebalancing among {len(targets)} reachable candidate(s) (least-full first)")
        for target in sorted(targets, key=fill_pct_of):
            if target.id == current_id:
                continue
            try:
                res = port.connect(target.id)
            except Exception:
                continue
            if res.status == "ok":
                self.ticks_since_connect = 0
                self._connected_id = target.id
                log.debug(f"FluidOutputRouter({self.type_ids}): connected -> '{target.id}' (fill={fill_pct_of(target):.2f})")
                return FluidOutputEvent("connected", target_id=target.id, fill_pct=fill_pct_of(target))
            elif res.status != "busy":
                if on_connect_notice:
                    on_connect_notice(target.id, res.status, res.message)

        log.debug(f"FluidOutputRouter({self.type_ids}): every candidate rejected or busy this pass -- exhausted")
        return FluidOutputEvent("exhausted")
