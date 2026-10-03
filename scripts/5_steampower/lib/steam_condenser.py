import fluid_routing
import power
from version_guard import validate_game_version
from tree_console import TreeConsole, flush_all, reset_all
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
#   - water gate: the pooled fill (total level / total capacity) of the
#     water tanks water_out can reach -- the router's discovered targets
#     minus blacklisted ones -- is at or above WATER_POOL_STOP_FRACTION.
#     Pooled, not per tank: the router moves water_out to the least-full
#     tank once the current one reaches WATER_TANK_SWITCH_FRACTION, so every
#     reachable tank fills before the Condenser idles. Resumes below
#     WATER_POOL_START_FRACTION: wide hysteresis, since at 250 t/h the
#     Condenser refills fast and would otherwise cycle on and off. Routing
#     pauses while this gate is closed, so water_out doesn't hop between
#     tanks that are all past the switch line.
#   - sink gate: a Waste Processor at the water_out tank's outpost is
#     draining that tank (enabled, "liquid" mode, liquid_in on the tank);
#     condensing then would feed the drain. Read live from the processor,
#     not the waste_sink.status archive entry: is_enabled() drops to False
#     when the sink script stops, the archive entry does not.
#   - local: steam_in empty or water_out buffer full.
#
# No archive state: the game resets the throttle to 0 when the script stops,
# and both gates re-evaluate from live readings on the first step.

STEAM_POOL_STOP_FRACTION = 0.85
STEAM_POOL_START_FRACTION = 0.95

WATER_POOL_STOP_FRACTION = 0.85
WATER_POOL_START_FRACTION = 0.50

WASTE_PROCESSOR_TYPE_ID = "garbage_disposal"

# steam_in routing -- same meaning as lib/steam_turbine.py's constants.
STALL_STREAK_BLACKLIST_THRESHOLD = 5
STEAM_RESCAN_INTERVAL_TICKS = 150
STEAM_DISCOVERY_CACHE_INTERVAL_TICKS = 100
NEUTRAL_GRACE_STEPS = 5

# water_out routing -- same meaning as lib/fluid_pump.py's constants, except
# the switch line: the Condenser leaves a tank at the pool stop line instead
# of 0.98, so it spreads water across tanks rather than topping one up.
LIQUID_TANK_TYPE_IDS = ("liquid_tank", "bulk_liquid_reservoir")
WATER_TANK_SWITCH_FRACTION = WATER_POOL_STOP_FRACTION
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
            rebalance_fill_fraction=WATER_TANK_SWITCH_FRACTION,
            connection_grace_ticks=CONNECTION_GRACE_TICKS,
            rescan_interval_ticks=WATER_RESCAN_INTERVAL_TICKS,
            discovery_cache_interval_ticks=WATER_DISCOVERY_CACHE_INTERVAL_TICKS,
            fluid_id="water",
            label=f"{self.name}.water_out",
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
        ranked = fluid_routing.discover_ranked(fluid_routing.STEAM_SOURCE_TIERS, own_outpost_id)
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

    def water_pool_fraction(self):
        """Pooled fill (0-1) of the reachable water tanks, or None when there are none."""
        curr_tick = self.get_current_tick()
        router = self._water_router
        tanks = router.blacklist.filter_reachable(router._discover_targets_cached(curr_tick), curr_tick, key=lambda tank: tank.id)
        level = 0.0
        capacity = 0.0
        for tank in tanks:
            try:
                level += tank.level()
                capacity += tank.capacity()
            except Exception as error:
                swallowed("steam_condenser.SteamCondenserController.water_pool_fraction: tank.level", error)
        if capacity <= 0:
            return None
        self.log.trace(f"[{self.name}] Water pool {level:.0f}/{capacity:.0f} t over {len(tanks)} reachable tank(s).")
        return level / capacity

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
        self.log.trace(f"[{self.name}] Grid steam pool {now['steam_t']:.0f}/{now['steam_cap']:.0f} t over {now['tanks']} tank(s).")
        return now["steam_t"] / now["steam_cap"]

    def update_steam_gate(self):
        self.log.start(f"[{self.name}] update_steam_gate", level="debug")
        fraction = self.steam_pool_fraction()
        if fraction is None:
            self.log.debug("No measurable steam pool on this grid; steam gate stays open.")
            self.steam_gate_open = True
            self.log.end()
            return
        if self.steam_gate_open and fraction < STEAM_POOL_STOP_FRACTION:
            self.steam_gate_open = False
            self.log.print(f"[{self.name}] Grid steam pool {fraction*100:.0f}% < {STEAM_POOL_STOP_FRACTION*100:.0f}% -- pausing condensation to keep the dormancy buffer for the turbines.")
        elif not self.steam_gate_open and fraction >= STEAM_POOL_START_FRACTION:
            self.steam_gate_open = True
            self.log.print(f"[{self.name}] Grid steam pool back to {fraction*100:.0f}% (>= {STEAM_POOL_START_FRACTION*100:.0f}%) -- resuming condensation.")
        else:
            self.log.trace(f"Steam pool {fraction*100:.0f}%, gate {'open' if self.steam_gate_open else 'closed'} (stop < {STEAM_POOL_STOP_FRACTION*100:.0f}%, start >= {STEAM_POOL_START_FRACTION*100:.0f}%).")
        self.log.end()

    def update_water_gate(self):
        self.log.start(f"[{self.name}] update_water_gate", level="debug")
        fill = self.water_pool_fraction()
        if fill is None:
            self.log.debug(f"No reachable water tank; water gate stays {'open' if self.water_gate_open else 'closed'}.")
            self.log.end()
            return
        if self.water_gate_open and fill >= WATER_POOL_STOP_FRACTION:
            self.water_gate_open = False
            self.log.print(f"[{self.name}] Water tanks {fill*100:.0f}% full (>= {WATER_POOL_STOP_FRACTION*100:.0f}%) -- pausing condensation.")
        elif not self.water_gate_open and fill < WATER_POOL_START_FRACTION:
            self.water_gate_open = True
            self.log.print(f"[{self.name}] Water tanks down to {fill*100:.0f}% (< {WATER_POOL_START_FRACTION*100:.0f}%) -- resuming condensation.")
        else:
            self.log.trace(f"Water pool {fill*100:.0f}%, gate {'open' if self.water_gate_open else 'closed'} (stop >= {WATER_POOL_STOP_FRACTION*100:.0f}%, start < {WATER_POOL_START_FRACTION*100:.0f}%).")
        self.log.end()

    def sink_draining_target(self):
        """Id of a Waste Processor draining the current water_out tank, else None."""
        target_id = self._water_router._connected_id
        if not target_id:
            return None
        target = self._water_router._resolve_target(target_id)
        outpost = getattr(target, "outpost", None)
        if not outpost or not hasattr(outpost, "buildings"):
            return None
        try:
            refs = list(outpost.buildings(WASTE_PROCESSOR_TYPE_ID))
        except Exception as error:
            swallowed("steam_condenser.SteamCondenserController.sink_draining_target: outpost.buildings", error)
            return None
        for ref in refs:
            try:
                processor = get_component(ref.id)
                if (processor and processor.is_enabled() and processor.mode() == "liquid"
                        and processor.liquid_in.connected_id() == target_id):
                    return ref.id
            except Exception as error:
                swallowed("steam_condenser.SteamCondenserController.sink_draining_target: processor.is_enabled", error)
        return None

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
        self.update_water_gate()
        if self.water_gate_open:
            self.ensure_water_output(water_full)

        if not self.steam_gate_open:
            reason = "steam reserve low"
        elif not self.water_gate_open:
            reason = "water tanks near full"
        elif self.sink_draining_target():
            reason = "Waste Processor draining the water tank"
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
        self.log.trace(f"[{self.name}] steam_in {steam_level:.0f} t, water_out {water_level:.0f}/{water_cap:.0f} t, throttle {throttle}, rate {self.rate():.0f} t/h.")

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
            reset_all()
            try:
                self.step()
            except Exception as error:
                self.log.level("error").print(f"[{self.name}] Steam Condenser exception: {error}")
            flush_all()
            sleep(poll_interval)
