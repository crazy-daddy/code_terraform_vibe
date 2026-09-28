import fluid_routing
import power
from version_guard import validate_game_version
from tree_console import TreeConsole
from swallow import swallowed

# Steam Condenser automation: turn banked steam into clean water (1:1 by
# mass, 250 t/h and 150 W at throttle 1 -- docs/components/steam_condenser.md).
#
# Both ports are routed with the shared lib/fluid_routing.py routers:
#   - steam_in: FluidInputRouter, same candidates and constants as
#     lib/steam_turbine.py (steam Gas Tanks, then Thermal Caps, own outpost
#     first).
#   - water_out: FluidOutputRouter, same targets and constants as
#     lib/fluid_pump.py (water-eligible Liquid / Large Liquid Tanks,
#     least-full first). Direct consumers (Plant Terraformer, Sprinkler,
#     Fabricator) connect their own water_in to the Condenser; nothing to do
#     for them here.
#
# Throttle is 1.0 or 0.0. The Condenser draws power in proportion to its
# throttle even while blocked, so it idles at 0 whenever it can't condense:
#   - steam gate: the grid's banked steam pool (power.measure_grid(), the
#     same number the tier-5 Power Guard reads) is below
#     STEAM_POOL_STOP_FRACTION. Steam is the grid's main power source and
#     the pool has to carry the turbines through long vent dormancy phases,
#     so the Condenser only takes the surplus of a nearly full pool (active
#     vent phase). Hysteresis: resumes at STEAM_POOL_START_FRACTION. A grid
#     with no measurable steam tank skips this gate.
#   - water gate: the current water_out tank is at or above
#     WATER_TARGET_STOP_FRACTION. That stays below lib/water_sink.py's
#     WATER_SINK_HIGH_FILL (0.90), so condensed water is never piped into a
#     tank the Waste Processor is draining. Resumes at
#     WATER_TARGET_START_FRACTION.
#   - local: steam_in empty or water_out buffer full.
#
# No archive state: the game resets the throttle to 0 when the script stops,
# and both gates re-evaluate from live readings on the first step.

STEAM_POOL_STOP_FRACTION = 0.85
STEAM_POOL_START_FRACTION = 0.95

WATER_TARGET_STOP_FRACTION = 0.85
WATER_TARGET_START_FRACTION = 0.80

# steam_in routing -- same meaning as lib/steam_turbine.py's constants.
STALL_STREAK_BLACKLIST_THRESHOLD = 5
STEAM_RESCAN_INTERVAL_TICKS = 150
STEAM_DISCOVERY_CACHE_INTERVAL_TICKS = 100
NEUTRAL_GRACE_STEPS = 5

# water_out routing -- same meaning as lib/fluid_pump.py's constants.
LIQUID_TANK_TYPE_IDS = ("liquid_tank", "large_liquid_tank")
LIQUID_TANK_REBALANCE_FILL_FRACTION = 0.98
CONNECTION_GRACE_TICKS = 2
WATER_RESCAN_INTERVAL_TICKS = 300
WATER_DISCOVERY_CACHE_INTERVAL_TICKS = 100


def _port_fill(port):
    """(level, capacity) of a FluidPort, (0.0, 0.0) when unreadable."""
    if not port:
        return 0.0, 0.0
    try:
        return port.level(), port.capacity()
    except Exception as error:
        swallowed("steam_condenser._port_fill: port.level", error)
        return 0.0, 0.0


class SteamCondenserController:
    """Routes a Steam Condenser's steam_in/water_out and condenses only while steam and water room allow."""

    def __init__(self, condenser):
        self.condenser = condenser
        self.name = getattr(condenser, "id", "steam_condenser")
        self.clock = get_component("clock")
        self.power = get_component("power_control")
        self.log = TreeConsole(module="steam_condenser")
        self.steam_gate_open = True
        self.water_gate_open = True
        self._last_reason = None
        self._steam_router = fluid_routing.FluidInputRouter(
            discover=self._discover_steam_sources,
            rescan_interval_ticks=STEAM_RESCAN_INTERVAL_TICKS,
            discovery_cache_interval_ticks=STEAM_DISCOVERY_CACHE_INTERVAL_TICKS,
            stall_streak_threshold=STALL_STREAK_BLACKLIST_THRESHOLD,
            neutral_grace_steps=NEUTRAL_GRACE_STEPS,
            label=f"{self.name}.steam_in",
        )
        self._water_router = fluid_routing.FluidOutputRouter(
            type_ids=LIQUID_TANK_TYPE_IDS,
            rebalance_fill_fraction=LIQUID_TANK_REBALANCE_FILL_FRACTION,
            connection_grace_ticks=CONNECTION_GRACE_TICKS,
            rescan_interval_ticks=WATER_RESCAN_INTERVAL_TICKS,
            discovery_cache_interval_ticks=WATER_DISCOVERY_CACHE_INTERVAL_TICKS,
            fluid_id="water",
        )

    def get_current_tick(self):
        if self.clock and hasattr(self.clock, "tick"):
            try:
                return self.clock.tick()
            except Exception as error:
                swallowed("steam_condenser.SteamCondenserController.get_current_tick: self.clock.tick", error)
        return 0

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------
    def _discover_steam_sources(self):
        """Steam Gas Tank ids, then Thermal Cap ids, network-wide, own outpost first within each type."""
        own_outpost_id = getattr(getattr(self.condenser, "outpost", None), "id", None)
        ranked = []
        for type_id in ("gas_tank", "thermal_cap"):
            pairs = fluid_routing.discover_network_buildings(type_id, resolve=False, fluid_id="steam")
            ranked.extend(fluid_routing.rank_own_outpost_first(pairs, own_outpost_id))
        self.log.debug(f"[{self.name}] Rediscovered steam sources (own outpost '{own_outpost_id}' first): {ranked}.")
        return ranked

    def ensure_steam_input(self, starved):
        port = getattr(self.condenser, "steam_in", None)
        curr_tick = self.get_current_tick()

        def on_dropped(source_id, reason):
            self.log.level("warn").print(f"[{self.name}] Dropping steam source '{source_id}': {reason}. Picking a different source.")

        def on_connect_notice(source_id, status, message):
            self.log.level("warn").print(f"[{self.name}] steam_in connect notice for '{source_id}': {status} - {message}")

        event = self._steam_router.ensure(port, curr_tick, starved, on_dropped, on_connect_notice)
        if event.kind == "connected":
            self.log.print(f"[{self.name}] Connected steam_in -> '{event.source_id}'.")
        elif event.kind == "waiting":
            self.log.debug(f"[{self.name}] Every known steam source is still within its blacklist window; waiting for one to expire.")
        elif event.kind == "not_found":
            self.log.debug(f"[{self.name}] No steam-eligible Gas Tank or Thermal Cap found network-wide yet.")

    def ensure_water_output(self, water_full):
        port = getattr(self.condenser, "water_out", None)
        if not port or not hasattr(port, "connect"):
            return
        curr_tick = self.get_current_tick()

        def on_blacklisted(target_id):
            self.log.level("warn").print(f"[{self.name}] '{target_id}' is not taking water (water_out buffer full) -- likely no completed Liquid Pipe route. Blacklisting and picking a different tank.")

        def on_connect_notice(target_id, status, message):
            self.log.level("warn").print(f"[{self.name}] water_out connect notice for '{target_id}': {status} - {message}")

        event = self._water_router.ensure_connection(port, curr_tick, water_full, on_blacklisted, on_connect_notice)
        if event.kind == "connected":
            self.log.print(f"[{self.name}] Connected water_out -> '{event.target_id}' ({event.fill_pct*100:.0f}% full).")
        elif event.kind == "waiting":
            self.log.debug(f"[{self.name}] Every known water tank is still within its blacklist window; waiting for one to expire.")
        elif event.kind == "not_found":
            self.log.debug(f"[{self.name}] No Liquid Tank or Large Liquid Tank eligible for water found network-wide (an empty tank needs a fluid_routing.tank_assignments entry).")

    def water_target_fill(self):
        """Fill fraction of the tank water_out currently points at, or None when unknown."""
        target_id = self._water_router._connected_id
        if not target_id:
            return None
        target = self._water_router._resolve_target(target_id)
        if target is None:
            return None
        return fluid_routing.fill_pct_of(target)

    # ------------------------------------------------------------------
    # Gates
    # ------------------------------------------------------------------
    def steam_pool_fraction(self):
        """Banked steam fraction of this Condenser's grid (0-1), or None when the grid or its steam tanks are unreadable."""
        if not self.power or not hasattr(self.power, "grid"):
            return None
        try:
            grid = self.power.grid(self.name)
        except Exception as error:
            swallowed("steam_condenser.SteamCondenserController.steam_pool_fraction: self.power.grid", error)
            return None
        if not grid:
            return None
        now = power.measure_grid(grid, power.grid_steam_tank_ids(grid))
        if now["steam_cap"] <= 0:
            return None
        self.log.debug(f"[{self.name}] Grid steam pool {now['steam_t']:.0f}/{now['steam_cap']:.0f} t over {now['tanks']} tank(s).")
        return now["steam_t"] / now["steam_cap"]

    def update_steam_gate(self):
        fraction = self.steam_pool_fraction()
        if fraction is None:
            self.log.debug(f"[{self.name}] No measurable steam pool on this grid; steam gate stays open.")
            self.steam_gate_open = True
            return
        if self.steam_gate_open and fraction < STEAM_POOL_STOP_FRACTION:
            self.steam_gate_open = False
            self.log.print(f"[{self.name}] Grid steam pool {fraction*100:.0f}% < {STEAM_POOL_STOP_FRACTION*100:.0f}% -- pausing condensation to keep the dormancy buffer for the turbines.")
        elif not self.steam_gate_open and fraction >= STEAM_POOL_START_FRACTION:
            self.steam_gate_open = True
            self.log.print(f"[{self.name}] Grid steam pool back to {fraction*100:.0f}% (>= {STEAM_POOL_START_FRACTION*100:.0f}%) -- resuming condensation.")
        else:
            self.log.debug(f"[{self.name}] Steam pool {fraction*100:.0f}%, gate {'open' if self.steam_gate_open else 'closed'} (stop < {STEAM_POOL_STOP_FRACTION*100:.0f}%, start >= {STEAM_POOL_START_FRACTION*100:.0f}%).")

    def update_water_gate(self):
        fill = self.water_target_fill()
        if fill is None:
            self.log.debug(f"[{self.name}] water_out target fill unknown; water gate stays {'open' if self.water_gate_open else 'closed'}.")
            return
        if self.water_gate_open and fill >= WATER_TARGET_STOP_FRACTION:
            self.water_gate_open = False
            self.log.print(f"[{self.name}] Water tank {fill*100:.0f}% >= {WATER_TARGET_STOP_FRACTION*100:.0f}% -- pausing condensation (no steam spent on water the sink would drain).")
        elif not self.water_gate_open and fill < WATER_TARGET_START_FRACTION:
            self.water_gate_open = True
            self.log.print(f"[{self.name}] Water tank down to {fill*100:.0f}% (< {WATER_TARGET_START_FRACTION*100:.0f}%) -- resuming condensation.")
        else:
            self.log.debug(f"[{self.name}] Water tank {fill*100:.0f}%, gate {'open' if self.water_gate_open else 'closed'}.")

    # ------------------------------------------------------------------
    # Loop
    # ------------------------------------------------------------------
    def step(self):
        steam_level, _ = _port_fill(getattr(self.condenser, "steam_in", None))
        water_level, water_cap = _port_fill(getattr(self.condenser, "water_out", None))
        steam_empty = steam_level <= 0
        water_full = water_cap > 0 and water_level >= water_cap

        self.update_steam_gate()
        # Starvation only counts while steam is wanted: a closed gate leaves steam_in empty on purpose.
        self.ensure_steam_input(starved=steam_empty and self.steam_gate_open)
        self.ensure_water_output(water_full)
        self.update_water_gate()

        if not self.steam_gate_open:
            reason = "steam reserve low"
        elif not self.water_gate_open:
            reason = "water tank near full"
        elif steam_empty:
            reason = "no steam in buffer"
        elif water_full:
            reason = "water_out buffer full"
        else:
            reason = None
        throttle = 0.0 if reason else 1.0

        if hasattr(self.condenser, "set_throttle"):
            self.condenser.set_throttle(throttle)

        if reason != self._last_reason:
            if reason:
                self.log.print(f"[{self.name}] Idle: {reason}.")
            else:
                self.log.print(f"[{self.name}] Condensing at full throttle.")
            self._last_reason = reason
        self.log.debug(f"[{self.name}] steam_in {steam_level:.0f} t, water_out {water_level:.0f}/{water_cap:.0f} t, throttle {throttle}, rate {self.rate():.0f} t/h.")

    def rate(self):
        try:
            return self.condenser.condensation_rate()
        except Exception as error:
            swallowed("steam_condenser.SteamCondenserController.rate: self.condenser.condensation_rate", error)
            return 0.0

    def run(self, poll_interval=2.0):
        self.log.print(f"Steam Condenser Controller ({self.name}) online.")
        validate_game_version()
        while True:
            try:
                self.step()
            except Exception as error:
                self.log.level("error").print(f"[{self.name}] Steam Condenser exception: {error}")
            sleep(poll_interval)
