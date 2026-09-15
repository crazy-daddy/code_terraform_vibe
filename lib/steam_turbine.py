# Shared Steam Turbine automation: throttle for peak power while a healthy
# steam buffer is available, ease off before the buffer runs dry (avoid
# is_stalled()), and keep running through the night since steam is the only
# generation source while solar is out.
#
# Reads grid state the same way lib/power.py's PowerGridManager does
# (power_control.grid(self.name)), but does not run shedding/master-election
# itself -- that's the grid's existing solar Master's job (see lib/power.py,
# lib/solar.py). This controller only decides its own throttle.

# Buffer-health bands, read as a fraction of steam_in.capacity() (not a fixed
# tonnage) so they hold regardless of any future buffer-capacity upgrades.
STEAM_BUFFER_LOW_FRACTION = 0.15       # below this: ease off to avoid a dry stall
STEAM_BUFFER_HEALTHY_FRACTION = 0.40   # above this: safe to run at full/peak
THROTTLE_LOW_BUFFER = 0.15             # gentle draw while buffer is thin
THROTTLE_MARGINAL_BUFFER = 0.5         # moderate draw while buffer is rebuilding

# Daytime easing: once the grid's battery is this full and generation already
# meets consumption, there's no benefit to burning banked steam for power
# nobody needs -- ease off to save it for the night instead.
BATTERY_FULL_FRACTION = 0.98
THROTTLE_DEMAND_MET = 0.3

# is_stalled() alone isn't reliable proof the connected source is physically
# unreachable -- it's equally true, harmlessly, whenever the feeding vent is
# just in its dormant phase. Require this many *consecutive* stalled ticks
# (dormancy is temporary; a genuinely missing pipe route stalls forever)
# before treating the current source as unreachable and blacklisting it.
STALL_STREAK_BLACKLIST_THRESHOLD = 5

# A source blacklisted as unreachable might become reachable later (the
# player builds a new Gas Pipe route to it) -- clear the blacklist this often
# so it gets a fresh chance without waiting for the current connection to
# also go bad first. Counts step() calls, not real time -- with the default
# poll_interval=2.0s that's roughly 5 minutes.
RESCAN_INTERVAL_TICKS = 150

# discover_network_building_ids() walks every outpost's buildings for both
# "gas_tank" and "thermal_cap" -- the real cost of ensure_input_connection().
# It's already skipped entirely while connected_input is True and the stall
# streak is below threshold (see the early return below), so this cache only
# matters for the remaining cases: bootstrap, or every candidate blacklisted
# at once. Counts step() calls, same units as RESCAN_INTERVAL_TICKS above.
DISCOVERY_CACHE_INTERVAL_STEPS = 20


def discover_network_building_ids(type_id):
    """
    All building ids of type_id across every known outpost. Same pattern as
    lib/thermal_cap.py's helper of the same name -- a reachable Gas Tank or
    Thermal Cap isn't guaranteed to share this Turbine's own outpost (a
    Thermal Cap in particular may have no outpost at all, built directly on
    a vent out in the field), so candidates are gathered network-wide;
    physical Gas Pipe topology, not outpost membership, decides which
    actually succeed via connect().
    """
    ids = []
    network = get_component("outpost_network")
    if network and hasattr(network, "outposts"):
        try:
            for outpost in network.outposts():
                for building in outpost.buildings(type_id):
                    b_id = getattr(building, "id", None)
                    if b_id:
                        ids.append(b_id)
        except Exception:
            pass
    return ids


class SteamTurbineController:
    """Throttles a Steam Turbine based on its own steam buffer and grid state."""

    def __init__(self, turbine):
        self.turbine = turbine
        self.name = getattr(turbine, "id", "steam_turbine")
        self.clock = get_component("clock")
        self.power = get_component("power_control")
        self.connected_input = False
        # connect()'s "ok" status only means the pairing was logically
        # accepted -- it never verifies a completed Gas Pipe route actually
        # exists (docs/guide/infrastructure_and_pipes.md). is_stalled() is
        # the only live signal a source isn't reachable, but it's ambiguous
        # on its own (also true, harmlessly, whenever the feeding vent is
        # just dormant) -- see stall_streak below.
        self.unreachable_sources = set()
        self.stall_streak = 0
        self.ticks_since_rescan = 0
        self._cached_candidate_ids = None
        self._ticks_since_discovery = 0

    def _discover_candidates_cached(self):
        """
        Gas Tank + Thermal Cap ids network-wide, refreshed at most every
        DISCOVERY_CACHE_INTERVAL_STEPS calls. Only reached from
        ensure_input_connection()'s slow path (see comment there).
        """
        if self._cached_candidate_ids is None or self._ticks_since_discovery >= DISCOVERY_CACHE_INTERVAL_STEPS:
            self._cached_candidate_ids = [s for t in ("gas_tank", "thermal_cap") for s in discover_network_building_ids(t)]
            self._ticks_since_discovery = 0
        else:
            self._ticks_since_discovery += 1
        return self._cached_candidate_ids

    def ensure_input_connection(self):
        """
        Declares steam_in's source, discovering candidates network-wide and
        rechecking reachability via is_stalled() rather than trusting
        connect()'s "ok" status alone (see __init__). A Gas Tank has no
        script of its own (purely passive -- see docs/components/gas_tank.md),
        so nothing ever calls connect() on its side of the pipe; this Turbine's
        own script must declare the link instead, same as it declares its own
        source for any other input port. Per docs/guide/infrastructure_and_pipes.md,
        a Turbine is exactly the kind of "additional consumer" that may connect
        its own steam_in straight to a Thermal Cap, independent of whatever the
        Cap's own steam_out currently points at -- so this tries every known
        Gas Tank first (the larger, shared buffer), then falls through to
        every known Thermal Cap directly if no tank connection succeeds.
        """
        port = getattr(self.turbine, "steam_in", None)
        if not port or not hasattr(port, "connect"):
            return

        # Periodic rescan: give blacklisted sources a fresh chance in case a
        # new Gas Pipe route was built since they were marked unreachable.
        # This never disconnects a currently working source -- it only
        # widens the candidate pool for the next time a switch is warranted.
        self.ticks_since_rescan += 1
        if self.ticks_since_rescan >= RESCAN_INTERVAL_TICKS:
            self.ticks_since_rescan = 0
            if self.unreachable_sources:
                print(f"[{self.name}] Periodic rescan: clearing {len(self.unreachable_sources)} blacklisted source(s) to retry.")
                self.unreachable_sources.clear()

        is_stalled = False
        if hasattr(self.turbine, "is_stalled"):
            try:
                is_stalled = self.turbine.is_stalled()
            except Exception:
                is_stalled = False
        self.stall_streak = self.stall_streak + 1 if is_stalled else 0

        if self.connected_input:
            if self.stall_streak < STALL_STREAK_BLACKLIST_THRESHOLD:
                return
            current_id = None
            try:
                current_id = port.connected_id() if hasattr(port, "connected_id") else None
            except Exception:
                pass
            if current_id:
                self.unreachable_sources.add(current_id)
                print(f"[{self.name}] '{current_id}' stalled for {self.stall_streak} consecutive ticks -- likely no completed Gas Pipe route (not just vent dormancy). Blacklisting and picking a different source.")
            self.connected_input = False
            self.stall_streak = 0

        candidates = [s for s in self._discover_candidates_cached() if s not in self.unreachable_sources]
        if not candidates:
            candidates = self._discover_candidates_cached()
            if candidates and self.unreachable_sources:
                print(f"[{self.name}] Every known source was blacklisted; clearing the list to retry.")
                self.unreachable_sources.clear()

        for source_id in candidates:
            try:
                res = port.connect(source_id)
            except Exception:
                continue
            if res.status == "ok":
                self.connected_input = True
                print(f"[{self.name}] Connected steam_in -> '{source_id}'.")
                return
            elif res.status != "busy":
                print(f"[{self.name}] steam_in connect notice for '{source_id}': {res.status} - {res.message}")

    def buffer_fraction(self):
        """Fraction (0-1) of steam_in's own buffer currently filled."""
        port = getattr(self.turbine, "steam_in", None)
        if not port or not hasattr(port, "level") or not hasattr(port, "capacity"):
            return 0.0
        try:
            capacity = port.capacity()
            if not capacity:
                return 0.0
            return port.level() / capacity
        except Exception:
            return 0.0

    def get_grid(self):
        if self.power and hasattr(self.power, "grid"):
            try:
                return self.power.grid(self.name)
            except Exception:
                pass
        return None

    def is_night(self):
        if self.clock and hasattr(self.clock, "get_elevation"):
            try:
                return self.clock.get_elevation() <= 0
            except Exception:
                pass
        return False

    def choose_throttle(self):
        fraction = self.buffer_fraction()

        # A thin buffer always wins -- running flat out against a near-empty
        # pipe is exactly what produces is_stalled(), regardless of day/night
        # or grid demand.
        if fraction < STEAM_BUFFER_LOW_FRACTION:
            return THROTTLE_LOW_BUFFER
        if fraction < STEAM_BUFFER_HEALTHY_FRACTION:
            return THROTTLE_MARGINAL_BUFFER

        # Buffer is healthy: steam is the only generator at night, so run flat
        # out to carry the grid regardless of current battery/demand state.
        if self.is_night():
            return 1.0

        # Daytime with a healthy buffer: ease off once the battery is full and
        # generation already covers consumption, so banked steam isn't burned
        # for power nobody currently needs -- save it for the coming night.
        grid = self.get_grid()
        if grid:
            stored = getattr(grid, "stored", 0.0)
            capacity = getattr(grid, "capacity", 0.0)
            generated = getattr(grid, "generated", 0.0)
            consumed = getattr(grid, "consumed", 0.0)
            battery_full = capacity > 0 and stored >= (capacity * BATTERY_FULL_FRACTION)
            demand_met = generated >= consumed
            if battery_full and demand_met:
                return THROTTLE_DEMAND_MET

        return 1.0

    def step(self):
        self.ensure_input_connection()

        throttle = self.choose_throttle()
        if hasattr(self.turbine, "set_throttle"):
            self.turbine.set_throttle(throttle)

        if hasattr(self.turbine, "is_stalled") and self.turbine.is_stalled():
            print(f"[{self.name}] Stalled: throttle is up but no steam is arriving. Check the feeding Cap's vent phase and the steam_in connection.")

    def run(self, poll_interval=2.0):
        print(f"Steam Turbine Controller ({self.name}) online.")
        while True:
            try:
                self.step()
            except Exception as error:
                print(f"[{self.name}] Steam Turbine exception: {error}")
            sleep(poll_interval)
