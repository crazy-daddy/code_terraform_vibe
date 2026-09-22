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

from tree_console import TreeConsole

log = TreeConsole(module="fluid_routing")


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


def discover_network_buildings(type_ids, resolve=True):
    """
    Every building across every known outpost matching type_ids (a single
    type_id string, or an iterable of them -- e.g. Water Pump's Liquid
    Tank/Large Liquid Tank, or Steam Turbine's Gas Tank/Thermal Cap), walking
    outpost_network.outposts() -> outpost.buildings(type_id). Returns
    [(building_or_id, outpost_id), ...] in discovery order, deduplicated by
    id within this call.

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
                        seen_ids.add(b_id)
                        if resolve:
                            try:
                                resolved = get_component(b_id) or building
                            except Exception:
                                resolved = building
                            pairs.append((resolved, outpost_id))
                        else:
                            pairs.append((b_id, outpost_id))
        except Exception:
            pass
    log.trace(f"discover_network_buildings({type_ids}): found {len(pairs)} building(s)")
    return pairs


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
                 rescan_interval_ticks, discovery_cache_interval_steps):
        self.type_ids = type_ids
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
            self._cached_targets = [b for b, _ in discover_network_buildings(self.type_ids)]
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
        # scan, and no fresh component resolution either.
        if current_id and not self.blacklist.is_blacklisted(current_id, curr_tick) and fill_pct_of(self._resolve_target(current_id)) < self.rebalance_fill_fraction:
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
