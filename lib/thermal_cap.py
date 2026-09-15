# Shared Thermal Cap automation: keep the vent's steam chamber from
# overpressurizing (which blows the whole chamber to atmosphere, losing
# everything banked -- see docs/components/thermal_cap.md .is_overpressured()).
# The job is purely reactive: open the release valve (steam_out) proportional
# to how close pressure() is to the 1.0 ceiling, and fall back to the relief
# valve (dumping to atmosphere) only when a downstream jam (full Gas Tank,
# stalled Steam Turbine, disconnected pipe) means the release valve alone
# can't keep up even wide open.

# Pressure bands for the release-valve throttle -- proportional control, not
# on/off, so the valve doesn't hunt between fully open/closed every tick.
# Kept intentionally cautious (opens well before the 1.0 overpressure ceiling)
# since blowing the chamber loses everything banked, while over-releasing
# just costs a bit of downstream buffer headroom.
PRESSURE_BAND_CRITICAL = 0.90   # throttle 1.0 (wide open)
PRESSURE_BAND_HIGH = 0.60       # throttle 0.6
PRESSURE_BAND_MODERATE = 0.30   # throttle 0.3
THROTTLE_TRICKLE = 0.1          # below PRESSURE_BAND_MODERATE: gentle trickle,
                                 # keeps the pipe/downstream buffer topped up
                                 # without needlessly draining banked steam

# Relief valve only opens once the release valve is already wide open and
# still can't prevent pressure climbing past this point -- a small relief
# bleed is far cheaper than an overpressure blowoff (which dumps the entire
# chamber, not just the surplus).
PRESSURE_RELIEF_THRESHOLD = 0.95

# Only abandon the currently-targeted Gas Tank once it's essentially full
# (not merely "over 85%") -- this is re-evaluated every single step(), so a
# softer threshold can ping-pong between two tanks that are both hovering
# above it (each reads as "less full" than the other depending on the tick),
# reconnecting steam_out every cycle and never giving flow a chance to
# actually establish on either one. Pressure then climbs unchecked with
# nowhere actually receiving it -- a real overpressure blowoff, worse than
# imperfect load-balancing across tanks. Only ever leaving a target once it's
# truly saturated guarantees no oscillation.
GAS_TANK_REBALANCE_FILL_FRACTION = 0.98

# Skip trusting is_stalled() as "target unreachable" evidence for this many
# ticks right after (re)connecting -- flow can take a tick to actually
# register after a fresh connection, and treating that brief lag as proof of
# an unreachable target would blacklist a perfectly good tank and force
# another switch immediately, compounding the same churn this threshold
# change is meant to avoid.
CONNECTION_GRACE_TICKS = 2

# A target blacklisted as unreachable might become reachable later (the
# player builds a new Gas Pipe route to it) -- clear the blacklist this often
# so it gets a fresh chance without waiting for every other candidate to also
# go bad first. Counts step() calls, not real time -- with the default
# poll_interval=1.0s that's roughly 5 minutes.
RESCAN_INTERVAL_TICKS = 300

# discover_network_building_ids() walks outpost_network.outposts() and every
# outpost's buildings(type_id) -- real work, and (see profiling.py /
# docs/AI_CHEATSHEET.md) the actual cost driver of this controller's step().
# ensure_output_connection() only *needs* that walk when it's genuinely
# picking a new target (no current connection, current is blacklisted, or
# current just became full); a healthy connection is confirmed with a single
# fill_pct() read on the one id already in use (see the fast path below),
# so in steady state this cache barely ever gets exercised at all. It exists
# as a ceiling for the remaining cases (bootstrap, every candidate blacklisted
# at once) so repeated reselection attempts in a short window don't each pay
# the full network walk. Counts step() calls, same units as
# RESCAN_INTERVAL_TICKS above.
DISCOVERY_CACHE_INTERVAL_STEPS = 20


def discover_network_buildings(type_id):
    """
    All building *objects* of type_id across every known outpost (not just
    ids -- see discover_network_building_ids() for that). A Thermal Cap has
    no .outpost of its own (built directly on a thermal vent out in the
    field, not necessarily inside a founded outpost -- unlike Gas Tank/Steam
    Turbine, docs/components/thermal_cap.md lists no .outpost property at
    all), so candidate Gas Tanks must be discovered network-wide rather than
    scoped to "this building's outpost". Physical Gas Pipe topology (not
    outpost membership) ultimately decides which candidates actually succeed
    via connect() -- this only gathers objects to try.

    Returning the live objects (not re-deriving them from ids later via a
    fresh get_component(id) call) matters: outpost.buildings(type_id) already
    handed back a usable reference, so a caller that keeps it avoids paying a
    second component-resolution round trip for the exact same building --
    see ThermalCapController's per-id lookup cache, which is what this exists
    to feed.
    """
    buildings = []
    network = get_component("outpost_network")
    if network and hasattr(network, "outposts"):
        try:
            for outpost in network.outposts():
                for building in outpost.buildings(type_id):
                    if getattr(building, "id", None):
                        buildings.append(building)
        except Exception:
            pass
    return buildings


def discover_network_building_ids(type_id):
    """Ids only, for callers (e.g. port.connect(id)) that need a plain id rather than the object -- see discover_network_buildings()."""
    return [b.id for b in discover_network_buildings(type_id)]


def _fill_pct_of_building(building):
    """fill_pct() of an already-resolved Gas Tank object, or 1.0 (treated as "full, deprioritize") if unreadable."""
    if not building or not hasattr(building, "fill_pct"):
        return 1.0
    try:
        return building.fill_pct()
    except Exception:
        return 1.0


class ThermalCapController:
    """Keeps a Thermal Cap's chamber pressure off the overpressure ceiling."""

    def __init__(self, cap):
        self.cap = cap
        self.name = getattr(cap, "id", "thermal_cap")
        self.last_phase = None
        # connect()'s "ok" status only means the pairing was logically
        # accepted -- docs/guide/infrastructure_and_pipes.md is explicit that
        # a remote target needs a *completed* Gas Pipe route, which connect()
        # never checks. is_stalled() is the only live signal that a target
        # isn't actually reachable, so unreachable targets get blacklisted --
        # but only until the next periodic rescan (see RESCAN_INTERVAL_TICKS),
        # since a newly built pipe can make a blacklisted target reachable.
        self.unreachable_targets = set()
        self.ticks_since_rescan = 0
        self.ticks_since_connect = 0
        self._cached_tanks = None
        self._ticks_since_discovery = 0
        # id -> resolved building object. Populated from discovery (which
        # already holds live references -- see discover_network_buildings()),
        # so the steady-state fast path below never needs to re-resolve the
        # current tank id via a fresh get_component() call. Profiling showed
        # this get_component() round trip -- not the network walk itself --
        # was this controller's actual per-step cost (docs/AI_CHEATSHEET.md
        # §1c): Steam Turbine's equivalent fast path touches zero external
        # id-keyed lookups when healthy, while this one used to do exactly
        # one every single step. Entries persist across rediscovery (merged,
        # never wholesale-cleared) since a building's identity doesn't change
        # between scans -- only the candidate *list* goes stale, not a
        # previously resolved object.
        self._tank_lookup = {}
        # Tracked locally instead of re-querying port.connected_to() every
        # step -- mirrors SteamTurbineController's self.connected_input,
        # which never calls a port method at all in its healthy fast path.
        # Profiling still showed a *sustained* per-step cost here even after
        # the get_component() fix above, with no periodicity matching any
        # cache/rescan interval -- the remaining unconditional port call was
        # connected_to() itself (docs/AI_CHEATSHEET.md §1b/§1c). Seeded once
        # from the real port state (see _sync_connected_tank_id()) so a
        # script reload recovers an already-working connection instead of
        # assuming a fresh start; kept in sync thereafter purely by this
        # controller's own connect()/blacklist calls, since nothing else
        # (no other script, no passive Gas Tank) ever repoints steam_out.
        self._connected_tank_id = None
        self._tank_id_synced = False

    def _discover_tanks_cached(self):
        """
        Gas Tank objects network-wide, refreshed at most every
        DISCOVERY_CACHE_INTERVAL_STEPS calls. Only called from the slow path
        of ensure_output_connection() (see comment there) -- the common case
        of "keep the current healthy connection" never reaches this at all.
        """
        if self._cached_tanks is None or self._ticks_since_discovery >= DISCOVERY_CACHE_INTERVAL_STEPS:
            self._cached_tanks = discover_network_buildings("gas_tank")
            for building in self._cached_tanks:
                self._tank_lookup[building.id] = building
            self._ticks_since_discovery = 0
        else:
            self._ticks_since_discovery += 1
        return self._cached_tanks

    def _resolve_tank(self, tank_id):
        """
        Building object for tank_id, preferring the cache filled by discovery
        over a fresh get_component() round trip. Only actually calls
        get_component() the first time a given id is ever seen (e.g. right
        after a fresh connect(), before that id's own discovery batch has run)
        -- every subsequent lookup for the same id is a plain dict read.
        """
        building = self._tank_lookup.get(tank_id)
        if building is not None:
            return building
        try:
            building = get_component(tank_id)
        except Exception:
            building = None
        if building:
            self._tank_lookup[tank_id] = building
        return building

    def ensure_output_connection(self):
        """
        Declares/rebalances steam_out's destination among known Gas Tanks
        (discovered network-wide -- see discover_network_building_ids()).
        A Gas Tank has no script of its own (purely passive -- see
        docs/components/gas_tank.md), so nothing ever calls connect() on its
        side of the pipe; this Cap's own script must declare the link, and
        steam_out only ever holds one destination at a time (per
        docs/components/thermal_cap.md), so serving several tanks means
        periodically re-pointing it rather than a simultaneous fan-out.

        Steam Turbines (and any other scripted consumer) are deliberately
        NOT a target here: docs/guide/infrastructure_and_pipes.md's Thermal
        Vents section describes the opposite direction for those -- "additional
        consumers may connect their own steam_in ports to this Cap" -- so a
        Turbine's own script (see lib/steam_turbine.py) independently pulls
        from this Cap regardless of whatever steam_out is currently pointed
        at, no coordination needed here.
        """
        port = getattr(self.cap, "steam_out", None)
        if not port or not hasattr(port, "connect"):
            return

        # Periodic rescan: give blacklisted targets a fresh chance in case a
        # new Gas Pipe route was built since they were marked unreachable.
        # This never disconnects a currently working target -- it only
        # widens the candidate pool for the next time a switch is warranted.
        self.ticks_since_rescan += 1
        if self.ticks_since_rescan >= RESCAN_INTERVAL_TICKS:
            self.ticks_since_rescan = 0
            if self.unreachable_targets:
                print(f"[{self.name}] Periodic rescan: clearing {len(self.unreachable_targets)} blacklisted target(s) to retry.")
                self.unreachable_targets.clear()

        # Query the port itself only once, ever, to recover state after a
        # reload -- every call after that trusts the locally tracked id (see
        # __init__), since this controller is the only writer of steam_out's
        # destination.
        if not self._tank_id_synced:
            try:
                self._connected_tank_id = port.connected_to() if hasattr(port, "connected_to") else None
            except Exception:
                self._connected_tank_id = None
            self._tank_id_synced = True
        current_id = self._connected_tank_id

        self.ticks_since_connect += 1

        # A stalled cap with an open throttle and steam available means the
        # currently connected target can't actually be reached by pipe --
        # connect() never verified that, it only accepted the pairing.
        # Blacklist it and force a reselect below rather than sitting stalled
        # on the same bad target forever. Skipped for the first
        # CONNECTION_GRACE_TICKS after connecting -- flow can take a tick to
        # register, and treating that lag as proof of unreachability would
        # blacklist a perfectly good tank.
        is_stalled = False
        if hasattr(self.cap, "is_stalled"):
            try:
                is_stalled = self.cap.is_stalled()
            except Exception:
                is_stalled = False
        if is_stalled and current_id and current_id not in self.unreachable_targets and self.ticks_since_connect >= CONNECTION_GRACE_TICKS:
            self.unreachable_targets.add(current_id)
            print(f"[{self.name}] '{current_id}' reported stalled (steam available, valve open, nothing transferred) -- likely no completed Gas Pipe route. Blacklisting and picking a different target.")
            current_id = None
            self._connected_tank_id = None

        # Fast path: a connection already judged healthy needs no network
        # scan, and no fresh component resolution either -- _resolve_tank()
        # is a plain dict read once the id has been seen once (see
        # __init__). This is what actually removes nearly all of this
        # method's cost in steady state, since discovery (below) only runs
        # when a target genuinely needs to be (re)picked -- see
        # DISCOVERY_CACHE_INTERVAL_STEPS and docs/AI_CHEATSHEET.md §1b/§1c.
        if current_id and current_id not in self.unreachable_targets and _fill_pct_of_building(self._resolve_tank(current_id)) < GAS_TANK_REBALANCE_FILL_FRACTION:
            return

        tanks = [t for t in self._discover_tanks_cached() if t.id not in self.unreachable_targets]
        if not tanks:
            # Every known tank is blacklisted (or none exist) -- give
            # blacklisted ones a fresh chance rather than sitting dead
            # forever if e.g. a pipe route gets completed later.
            tanks = self._discover_tanks_cached()
            if tanks and self.unreachable_targets:
                print(f"[{self.name}] Every known Gas Tank was blacklisted; clearing the list to retry.")
                self.unreachable_targets.clear()
        if not tanks:
            if not current_id:
                print(f"[{self.name}] No Gas Tank found network-wide yet; steam_out has no destination.")
            return

        # Try the least-full known tank first (load-balances across several),
        # falling through to the next since not every tank is necessarily
        # physically pipe-reachable from this Cap's field location.
        for tank in sorted(tanks, key=_fill_pct_of_building):
            if tank.id == current_id:
                continue
            try:
                res = port.connect(tank.id)
            except Exception:
                continue
            if res.status == "ok":
                self.ticks_since_connect = 0
                self._connected_tank_id = tank.id
                print(f"[{self.name}] Connected steam_out -> '{tank.id}' ({_fill_pct_of_building(tank)*100:.0f}% full).")
                return
            elif res.status != "busy":
                print(f"[{self.name}] steam_out connect notice for '{tank.id}': {res.status} - {res.message}")

    def release_throttle_for_pressure(self, pressure):
        """Proportional release-valve setting for the given chamber pressure."""
        if pressure >= PRESSURE_BAND_CRITICAL:
            return 1.0
        if pressure >= PRESSURE_BAND_HIGH:
            return 0.6
        if pressure >= PRESSURE_BAND_MODERATE:
            return 0.3
        return THROTTLE_TRICKLE

    def step(self):
        self.ensure_output_connection()

        phase = self.cap.phase() if hasattr(self.cap, "phase") else None
        if phase != self.last_phase and phase is not None:
            print(f"[{self.name}] Vent phase changed: {self.last_phase} -> {phase}.")
            self.last_phase = phase

        pressure = self.cap.pressure() if hasattr(self.cap, "pressure") else 0.0

        throttle = self.release_throttle_for_pressure(pressure)
        if hasattr(self.cap, "set_throttle"):
            self.cap.set_throttle(throttle)

        # Relief valve: only engage once the release valve is already wide
        # open (throttle == 1.0) and pressure is still climbing toward the
        # ceiling -- a downstream jam (full Gas Tank, stalled Turbine,
        # disconnected pipe) that steam_out alone can't route around.
        if hasattr(self.cap, "set_relief"):
            if throttle >= 1.0 and pressure >= PRESSURE_RELIEF_THRESHOLD:
                relief = min(1.0, (pressure - PRESSURE_RELIEF_THRESHOLD) / (1.0 - PRESSURE_RELIEF_THRESHOLD))
                self.cap.set_relief(relief)
                if relief > 0:
                    print(f"[{self.name}] Downstream can't keep up at {pressure*100:.0f}% pressure; venting {relief*100:.0f}% to atmosphere to avoid an overpressure blowoff.")
            else:
                self.cap.set_relief(0.0)

        if hasattr(self.cap, "is_stalled") and self.cap.is_stalled():
            print(f"[{self.name}] Stalled: release valve open with steam available but nothing downstream is accepting it. Check steam_out connection / Gas Tank / Steam Turbine.")

        if hasattr(self.cap, "is_overpressured") and self.cap.is_overpressured():
            print(f"[{self.name}] WARNING: Chamber overpressured -- banked steam was lost to atmosphere. Releasing sooner next cycle.")
            try:
                notify(f"[{self.name}] Thermal Cap overpressured; banked steam lost.", level="warn", duration_seconds=8.0)
            except Exception:
                pass

    def run(self, poll_interval=1.0):
        print(f"Thermal Cap Controller ({self.name}) online. Guarding against overpressure.")
        while True:
            try:
                self.step()
            except Exception as error:
                print(f"[{self.name}] Thermal Cap exception: {error}")
            sleep(poll_interval)
