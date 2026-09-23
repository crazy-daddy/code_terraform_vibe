import fluid_routing
from version_guard import validate_game_version
from tree_console import TreeConsole

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
# player builds a new Gas Pipe route to it) -- an entry expires and becomes
# retryable again once it's been blacklisted for this many *simulation*
# ticks, tracked per-entry (self._router.blacklist maps source_id -> the tick it was
# blacklisted at, see lib/fluid_routing.py's PerEntryBlacklist), NOT as one
# shared "clear everything at once" timer. See PerEntryBlacklist's docstring
# for why per-entry timestamps matter: with 2+ simultaneously-bad candidates
# ranked ahead of the one genuinely-reachable source, a single shared clock
# that wipes the whole blacklist at once can undo elimination progress
# before ever reaching the reachable one, producing an infinite ping-pong
# between the bad candidates -- exactly the bug per-entry expiry fixes.
RESCAN_INTERVAL_TICKS = 150

# fluid_routing.discover_network_buildings() walks every outpost's buildings
# for both "gas_tank" and "thermal_cap" -- the real cost of
# ensure_input_connection(), only reached on FluidInputRouter's slow path.
# Simulation ticks, not calls -- see fluid_routing.TickedDiscoveryCache.
DISCOVERY_CACHE_INTERVAL_TICKS = 100

# A declared link still "neutral" (no fluid established, e.g. an empty
# unlatched tank) after this many step() calls is dropped -- but only when
# another candidate exists. Matches the stall streak window.
NEUTRAL_GRACE_STEPS = 5


class SteamTurbineController:
    """Throttles a Steam Turbine based on its own steam buffer and grid state."""

    def __init__(self, turbine):
        self.turbine = turbine
        self.name = getattr(turbine, "id", "steam_turbine")
        self.clock = get_component("clock")
        self.power = get_component("power_control")
        self.log = TreeConsole(module="steam_turbine")
        # Source selection, reachability and blacklisting live in the shared consumer-side
        # router (lib/fluid_routing.py FluidInputRouter) -- this controller only supplies which
        # buildings count as a steam source, how they rank, and the stall signal.
        self._router = fluid_routing.FluidInputRouter(
            discover=self._discover_candidates,
            rescan_interval_ticks=RESCAN_INTERVAL_TICKS,
            discovery_cache_interval_ticks=DISCOVERY_CACHE_INTERVAL_TICKS,
            stall_streak_threshold=STALL_STREAK_BLACKLIST_THRESHOLD,
            neutral_grace_steps=NEUTRAL_GRACE_STEPS,
            label=f"{self.name}.steam_in",
        )

    def get_current_tick(self):
        if self.clock and hasattr(self.clock, "tick"):
            try:
                return self.clock.tick()
            except Exception:
                pass
        return 0

    def _discover_candidates(self):
        """
        Gas Tank ids, then Thermal Cap ids, network-wide, own outpost first within each type -- a
        same-outpost source is far more likely to already have a completed Gas Pipe route (found
        from a real case: turbine_5/turbine_6 connecting to cross-outpost gas_tank_2, which had no
        completed route to either, instead of trying their own outpost's tank first). Per
        docs/guide/infrastructure_and_pipes.md a Turbine may connect steam_in straight to a Cap,
        independent of the Cap's own steam_out, hence the Cap fallback.
        """
        own_outpost_id = getattr(getattr(self.turbine, "outpost", None), "id", None)
        ranked = []
        for type_id in ("gas_tank", "thermal_cap"):
            pairs = fluid_routing.discover_network_buildings(type_id, resolve=False, fluid_id="steam")
            ranked.extend(fluid_routing.rank_own_outpost_first(pairs, own_outpost_id))
        self.log.debug(f"[{self.name}] Rediscovered steam sources (own outpost '{own_outpost_id}' first): {ranked}.")
        return ranked

    def ensure_input_connection(self):
        """Keeps steam_in on a reachable steam source via fluid_routing.FluidInputRouter. A Gas Tank
        has no script (docs/components/gas_tank.md), so this Turbine must declare the link itself."""
        port = getattr(self.turbine, "steam_in", None)
        curr_tick = self.get_current_tick()
        fluid_routing.warn_about_unassigned_tanks(curr_tick)

        def on_dropped(source_id, reason):
            self.log.level("warn").print(f"[{self.name}] Dropping steam source '{source_id}': {reason}. Picking a different source.")

        def on_connect_notice(source_id, status, message):
            self.log.level("warn").print(f"[{self.name}] steam_in connect notice for '{source_id}': {status} - {message}")

        event = self._router.ensure(port, curr_tick, fluid_routing.safe_is_stalled(self.turbine), on_dropped, on_connect_notice)
        if event.kind == "connected":
            self.log.print(f"[{self.name}] Connected steam_in -> '{event.source_id}'.")
        elif event.kind == "waiting":
            self.log.debug(f"[{self.name}] Every known steam source is still within its blacklist window; waiting for one to expire.")
            for sid, blacklisted_at in self._router.blacklist._blacklisted_at.items():
                remaining = max(0, self._router.blacklist.rescan_interval_ticks - (curr_tick - blacklisted_at))
                self.log.debug(f"[{self.name}] Blacklisted source '{sid}': {remaining} tick(s) remaining until retry-eligible.")
        elif event.kind == "not_found":
            self.log.debug(f"[{self.name}] No steam-eligible Gas Tank or Thermal Cap found network-wide yet.")

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
            self.log.debug(f"[{self.name}] Buffer {fraction*100:.0f}% < low threshold {STEAM_BUFFER_LOW_FRACTION*100:.0f}%; easing to {THROTTLE_LOW_BUFFER} to avoid a dry stall.")
            return THROTTLE_LOW_BUFFER
        if fraction < STEAM_BUFFER_HEALTHY_FRACTION:
            self.log.debug(f"[{self.name}] Buffer {fraction*100:.0f}% below healthy threshold {STEAM_BUFFER_HEALTHY_FRACTION*100:.0f}%; moderate throttle {THROTTLE_MARGINAL_BUFFER} while rebuilding.")
            return THROTTLE_MARGINAL_BUFFER

        # Buffer is healthy: steam is the only generator at night, so run flat
        # out to carry the grid regardless of current battery/demand state.
        if self.is_night():
            self.log.debug(f"[{self.name}] Buffer healthy ({fraction*100:.0f}%) and night -- full throttle 1.0 (only generation source overnight).")
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
                self.log.debug(f"[{self.name}] Buffer healthy ({fraction*100:.0f}%), daytime, battery full ({stored:.0f}/{capacity:.0f} Wh) and demand met ({generated:.0f} W >= {consumed:.0f} W); easing to {THROTTLE_DEMAND_MET} to save steam for night.")
                return THROTTLE_DEMAND_MET
            self.log.debug(f"[{self.name}] Buffer healthy ({fraction*100:.0f}%), daytime, but battery_full={battery_full} demand_met={demand_met} (stored={stored:.0f}/{capacity:.0f} Wh, gen={generated:.0f} W, con={consumed:.0f} W); full throttle 1.0.")

        return 1.0

    def step(self):
        self.ensure_input_connection()

        throttle = self.choose_throttle()
        if hasattr(self.turbine, "set_throttle"):
            self.turbine.set_throttle(throttle)

        if hasattr(self.turbine, "is_stalled") and self.turbine.is_stalled():
            self.log.level("warn").print(f"[{self.name}] Stalled: throttle is up but no steam is arriving. Check the feeding Cap's vent phase and the steam_in connection.")

    def run(self, poll_interval=2.0):
        self.log.print(f"Steam Turbine Controller ({self.name}) online.")
        validate_game_version()
        while True:
            try:
                self.step()
            except Exception as error:
                self.log.level("error").print(f"[{self.name}] Steam Turbine exception: {error}")
            sleep(poll_interval)
