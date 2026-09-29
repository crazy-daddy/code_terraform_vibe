# Shared Library for Terraforming Machine Automation
# Reusable controllers for Heat Generators, Pressure Generators, and Oxygen Generators.
# Note: Solar Generators and Power Grid Management have been moved to lib/power.py.

from archive import archive
from version_guard import validate_game_version
from tree_console import TreeConsole, flush_all
from swallow import swallowed
from production import FLUID_SOURCE_TYPE_IDS, fluid_building_is_viable
import fluid_routing
import power

# Mk III fluid feed (docs/components/heat_generator.md, pressure_generator.md,
# oxygen_generator.md):
#   - Heat Generator Mk III: steam_in (Thermal Cap / steam Gas Tank).
#   - Pressure / Oxygen Generator Mk III: water_in (Water Pump, Steam
#     Condenser, water Liquid / Large Liquid Tank).
# A starved Mk III runs as Mk II (is_degraded()), it never stops, so the feed
# is a bonus, not a requirement. Mk IV burns Fuel Rods and below Mk III the
# port does nothing: routing runs only while tier() == 3.
#
# Each controller's step() runs one Mk3FluidFeed pass, at most every
# FLUID_CHECK_INTERVAL_TICKS (the Pressure Generator polls every 0.1 s for its
# sync window; routing that often buys nothing).
#
# Steam guard (heater only): steam is the grid's main power source, and the
# turbines need the pool to carry them through vent dormancy. Below
# STEAM_POOL_STOP_FRACTION of the grid's banked steam (power.measure_grid(),
# the number the tier-5 Power Guard reads) the heater disconnects steam_in
# and runs as Mk II; it reconnects at STEAM_POOL_START_FRACTION. A grid with
# no measurable steam tank, or a power.py without measure_grid() (below tier
# 5), leaves the guard open. Water has no guard: water is not a power reserve.

FLUID_CHECK_INTERVAL_TICKS = 20

STEAM_POOL_STOP_FRACTION = 0.50
STEAM_POOL_START_FRACTION = 0.70

# FluidInputRouter constants, same values as the Plant Terraformer's water router.
FLUID_STALL_STREAK_BLACKLIST_THRESHOLD = 5
FLUID_RESCAN_INTERVAL_TICKS = 150
FLUID_DISCOVERY_CACHE_INTERVAL_TICKS = 100
FLUID_NEUTRAL_GRACE_STEPS = 5

MK3_TIER = 3


def _current_tick(clock):
    if clock and hasattr(clock, "tick"):
        try:
            return clock.tick()
        except Exception as error:
            swallowed("terraforming._current_tick: clock.tick", error)
    return 0


def _port_starved(port):
    """flow_rate() == 0 with room left -- a full port also reads 0, not a stall."""
    try:
        level = port.level() if hasattr(port, "level") else 0
        capacity = port.capacity() if hasattr(port, "capacity") else 0
        flow = port.flow_rate() if hasattr(port, "flow_rate") else 0
        return flow == 0 and (not capacity or level < capacity)
    except Exception as error:
        swallowed("terraforming._port_starved: port.level", error)
        return False


class Mk3FluidFeed:
    """
    Keeps one Mk III input port (steam_in or water_in) on a reachable source,
    network-wide, own outpost first. step() is called every controller poll;
    it routes at most every FLUID_CHECK_INTERVAL_TICKS and logs is_degraded()
    transitions at info level.
    """

    def __init__(self, machine, fluid_key, name, log, steam_guard=False):
        self.machine = machine
        self.fluid_key = fluid_key
        self.name = name
        self.log = log
        self.steam_guard = steam_guard
        self.clock = get_component("clock")
        self.power = get_component("power_control") if steam_guard else None
        self.guard_open = True
        self.last_check_tick = None
        self.last_degraded = None
        self.router = fluid_routing.FluidInputRouter(
            discover=self._discover_sources,
            rescan_interval_ticks=FLUID_RESCAN_INTERVAL_TICKS,
            discovery_cache_interval_ticks=FLUID_DISCOVERY_CACHE_INTERVAL_TICKS,
            stall_streak_threshold=FLUID_STALL_STREAK_BLACKLIST_THRESHOLD,
            neutral_grace_steps=FLUID_NEUTRAL_GRACE_STEPS,
            label=f"{name}.{fluid_key}",
        )

    def _own_outpost_id(self):
        return getattr(getattr(self.machine, "outpost", None), "id", None)

    def _discover_sources(self):
        own_outpost_id = self._own_outpost_id()
        if self.fluid_key == "steam_in":
            # Same candidates and order as the Steam Turbine / Condenser: steam Gas Tanks, then Caps.
            ranked = []
            for type_id in ("gas_tank", "thermal_cap"):
                pairs = fluid_routing.discover_network_buildings(type_id, resolve=False, fluid_id="steam")
                ranked.extend(fluid_routing.rank_own_outpost_first(pairs, own_outpost_id))
            self.log.debug(f"[{self.name}] steam_in: sources (steam tanks, then Caps; own outpost first): {ranked}.")
            return ranked
        pairs = []
        network = get_component("outpost_network")
        if network and hasattr(network, "outposts"):
            try:
                for outpost in network.outposts():
                    o_id = getattr(outpost, "id", None)
                    for type_id in FLUID_SOURCE_TYPE_IDS[self.fluid_key]:
                        for building in outpost.buildings(type_id):
                            b_id = getattr(building, "id", None)
                            if b_id and fluid_building_is_viable(self.fluid_key, type_id, building):
                                pairs.append((b_id, o_id))
            except Exception as error:
                swallowed("terraforming.Mk3FluidFeed._discover_sources: network.outposts", error)
        ids = fluid_routing.rank_own_outpost_first(pairs, own_outpost_id)
        self.log.debug(f"[{self.name}] {self.fluid_key}: sources (own outpost first): {ids}.")
        return ids

    def _tier(self):
        try:
            return self.machine.tier()
        except Exception as error:
            swallowed("terraforming.Mk3FluidFeed._tier: machine.tier", error)
            return None

    def _steam_pool_fraction(self):
        """Banked steam fraction of this machine's grid (0-1), or None when unreadable."""
        measure_grid = getattr(power, "measure_grid", None)
        steam_tank_ids = getattr(power, "grid_steam_tank_ids", None)
        if not measure_grid or not steam_tank_ids:
            return None
        if not self.power or not hasattr(self.power, "grid"):
            return None
        try:
            grid = self.power.grid(self.name)
        except Exception as error:
            swallowed("terraforming.Mk3FluidFeed._steam_pool_fraction: power.grid", error)
            return None
        if not grid:
            return None
        now = measure_grid(grid, steam_tank_ids(grid))
        if now["steam_cap"] <= 0:
            return None
        return now["steam_t"] / now["steam_cap"]

    def _update_guard(self, port):
        fraction = self._steam_pool_fraction()
        if fraction is None:
            self.log.debug(f"[{self.name}] No measurable steam pool on this grid; steam guard stays open.")
            self.guard_open = True
            return
        if self.guard_open and fraction < STEAM_POOL_STOP_FRACTION:
            self.guard_open = False
            self.log.print(f"[{self.name}] Grid steam pool {fraction*100:.0f}% < {STEAM_POOL_STOP_FRACTION*100:.0f}% -- releasing steam_in to the turbines, running as Mk II.")
            self._disconnect(port)
        elif not self.guard_open and fraction >= STEAM_POOL_START_FRACTION:
            self.guard_open = True
            self.log.print(f"[{self.name}] Grid steam pool back to {fraction*100:.0f}% (>= {STEAM_POOL_START_FRACTION*100:.0f}%) -- reconnecting steam_in.")
        else:
            self.log.debug(f"[{self.name}] Steam pool {fraction*100:.0f}%, guard {'open' if self.guard_open else 'closed'} (stop < {STEAM_POOL_STOP_FRACTION*100:.0f}%, start >= {STEAM_POOL_START_FRACTION*100:.0f}%).")

    def _disconnect(self, port):
        if not hasattr(port, "disconnect"):
            return
        try:
            res = port.disconnect()
            self.log.debug(f"[{self.name}] steam_in.disconnect() -> {res.status}.")
        except Exception as error:
            swallowed("terraforming.Mk3FluidFeed._disconnect: port.disconnect", error)

    def _report_degraded(self):
        try:
            degraded = bool(self.machine.is_degraded())
        except Exception as error:
            swallowed("terraforming.Mk3FluidFeed._report_degraded: machine.is_degraded", error)
            return
        if degraded == self.last_degraded:
            return
        if self.last_degraded is not None or degraded:
            if degraded:
                self.log.level("warn").print(f"[{self.name}] Mk III starved of {self.fluid_key} -- running as Mk II.")
            else:
                self.log.print(f"[{self.name}] Mk III {self.fluid_key} supplied -- full Mk III output.")
        self.last_degraded = degraded

    def step(self):
        curr_tick = _current_tick(self.clock)
        if self.last_check_tick is not None and curr_tick and curr_tick - self.last_check_tick < FLUID_CHECK_INTERVAL_TICKS:
            return
        self.last_check_tick = curr_tick

        tier = self._tier()
        if tier != MK3_TIER:
            self.log.debug(f"[{self.name}] tier {tier}, not Mk III; no {self.fluid_key} routing.")
            return
        port = getattr(self.machine, self.fluid_key, None)
        if not port:
            self.log.debug(f"[{self.name}] Mk III but no {self.fluid_key} port.")
            return

        if self.steam_guard:
            self._update_guard(port)
            if not self.guard_open:
                self._report_degraded()
                return

        def on_dropped(source_id, reason):
            self.log.level("warn").print(f"[{self.name}] Dropping {self.fluid_key} source '{source_id}': {reason}. Picking another.")

        def on_connect_notice(source_id, status, message):
            self.log.level("warn").print(f"[{self.name}] {self.fluid_key} connect notice for '{source_id}': {status} - {message}")

        event = self.router.ensure(port, curr_tick, _port_starved(port), on_dropped, on_connect_notice)
        if event.kind == "connected":
            self.log.print(f"[{self.name}] Connected {self.fluid_key} -> '{event.source_id}'.")
        elif event.kind == "not_found":
            self.log.debug(f"[{self.name}] No {self.fluid_key} source on the network.")
        elif event.kind == "waiting":
            self.log.debug(f"[{self.name}] Every known {self.fluid_key} source is still blacklisted; waiting.")
        self._report_degraded()


class HeatController:
    """
    Manages optimal power setpoint calibration for Heat Generators.
    Tracks day / weather condition changes, sweeps 1-10W to find 100% efficiency,
    and caches learned optimal setpoints per thermal state locally and in the Data Archive.
    """
    def __init__(self, machine, clock=None):
        self.machine = machine
        self.clock = clock or get_component("clock")
        self.name = getattr(machine, "id", "heater")
        self.learned_optimal = archive.get("heat.optimal_setpoints", {})
        self.last_day = None
        self.last_state = None
        self.log = TreeConsole(module="terraforming")
        self.feed = Mk3FluidFeed(machine, "steam_in", self.name, self.log, steam_guard=True)

    def step(self):
        self.feed.step()
        current_day = self.clock.get_day() if self.clock else None
        current_state = self.machine.thermal_state()

        if current_day != self.last_day or current_state != self.last_state:
            self.log.debug(f"[{self.name}] State change detected: day {self.last_day}->{current_day}, thermal_state '{self.last_state}'->'{current_state}'; re-evaluating power setpoint.")
            self.last_day = current_day
            self.last_state = current_state

            if current_state in self.learned_optimal:
                best_p = self.learned_optimal[current_state]
                self.machine.set_power(best_p)
                self.log.print(f"[{self.name}] Applied cached power {best_p} W for '{current_state}' (Eff: {self.machine.efficiency():.0f}%, {self.machine.output():.3f} heat/h)")
            else:
                best_p = 5
                best_eff = -1
                self.log.start(f"[{self.name}] Calibrating '{current_state}'")
                self.log.debug(f"[{self.name}] No cached setpoint for '{current_state}'; sweeping 1-10 W to find peak efficiency.")
                for p in range(1, 11):
                    self.machine.set_power(p)
                    eff = self.machine.efficiency()
                    if eff > best_eff:
                        self.log.debug(f"[{self.name}] Sweep candidate {p} W -> {eff:.0f}% eff, new best (previous best {best_eff:.0f}% at {best_p} W).")
                        best_eff = eff
                        best_p = p
                    else:
                        self.log.debug(f"[{self.name}] Sweep candidate {p} W -> {eff:.0f}% eff, rejected (best remains {best_eff:.0f}% at {best_p} W).")
                    if eff >= 99.0:
                        self.log.debug(f"[{self.name}] Sweep stopped early at {p} W: {eff:.0f}% eff already >= 99% threshold.")
                        break
                self.machine.set_power(best_p)
                self.learned_optimal[current_state] = best_p
                archive.set("heat.optimal_setpoints", self.learned_optimal)
                self.log.print(f"[{self.name}] Calibrated '{current_state}': {best_p} W ({best_eff:.0f}% eff, {self.machine.output():.3f} heat/h) [Saved to Data Archive]")
                self.log.end(f"[{self.name}] Calibration done: {best_p} W")

    def run(self, poll_interval=2.0):
        self.log.print(f"Heat Generator ({self.name}) online via Shared Library.")
        validate_game_version()
        while True:
            self.step()
            flush_all()
            sleep(poll_interval)


class PressureController:
    """
    Manages resonance sweep gauge synchronization for Pressure Generators.
    Identifies the sync window [next_window_low, next_window_high] and triggers
    self.sync() inside the window for 100% compression efficiency.
    """
    def __init__(self, machine):
        self.machine = machine
        self.name = getattr(machine, "id", "pressure")
        self.synced_this_sweep = False
        self.last_gauge = self.machine.gauge()
        self.log = TreeConsole(module="terraforming")
        self.feed = Mk3FluidFeed(machine, "water_in", self.name, self.log)

    def step(self):
        self.feed.step()
        gauge = self.machine.gauge()
        low = self.machine.next_window_low()
        high = self.machine.next_window_high()

        # Gauge wrap detection (~100 to ~0) resets the sync flag for the new sweep
        if gauge < self.last_gauge and (self.last_gauge - gauge) > 20:
            self.synced_this_sweep = False
            self.log.debug(f"[{self.name}] Gauge wrap detected ({self.last_gauge:.1f} -> {gauge:.1f}); resetting synced flag for new sweep, next window [{low:.1f}, {high:.1f}].")

        self.last_gauge = gauge

        in_window = (low <= gauge <= high) if low <= high else (gauge >= low or gauge <= high)

        if not self.synced_this_sweep and in_window:
            self.log.debug(f"[{self.name}] Resonance window hit: gauge {gauge:.1f} within [{low:.1f}, {high:.1f}]; attempting sync().")
            res = self.machine.sync()
            if res.status == "ok":
                self.synced_this_sweep = True
                eff = self.machine.efficiency()
                self.log.print(f"[{self.name}] Sync hit! Gauge: {gauge:.1f} in [{low:.1f}, {high:.1f}] -> Eff: {eff:.0f}%, Output: {self.machine.output():.4f} kPa/h")
            elif res.status != "busy":
                self.log.level("warn").print(f"[{self.name}] Sync status: {res.status} - {res.message}")

    def run(self, poll_interval=0.1):
        self.log.print(f"Pressure Generator ({self.name}) online via Shared Library.")
        validate_game_version()
        while True:
            self.step()
            flush_all()
            sleep(poll_interval)


class OxygenController:
    """
    Manages intake optimization and carbon waste dumping for Oxygen Generators.
    Sets intake to peak sweet spot (CO2 / 10), and dumps carbon waste inside the
    clean window (50-60 units) to avoid penalties or production stalling at 100.
    """
    def __init__(self, machine, atmo=None):
        self.machine = machine
        self.atmo = atmo or get_component("atmosphere")
        self.name = getattr(machine, "id", "o2gen")
        self.log = TreeConsole(module="terraforming")
        self.feed = Mk3FluidFeed(machine, "water_in", self.name, self.log)

    def step(self):
        self.feed.step()
        if self.atmo:
            co2 = self.atmo.get_co2()
            target_intake = co2 / 10.0
            self.machine.set_intake(target_intake)
            self.log.trace(f"[{self.name}] CO2={co2:.2f} -> intake set to {target_intake:.2f} (sweet spot = CO2/10).")

        current_waste = self.machine.waste()
        if current_waste >= 50:
            res = self.machine.dump_waste()
            penalty = getattr(res, "penalty", 0.0)
            self.log.print(f"[{self.name}] Dumped waste at {current_waste:.1f}. Penalty: {penalty}")
        else:
            self.log.trace(f"[{self.name}] Waste at {current_waste:.1f}, below 50 dump threshold; no action.")

    def run(self, poll_interval=1.0):
        self.log.print(f"Oxygen Generator ({self.name}) online via Shared Library.")
        validate_game_version()
        while True:
            self.step()
            flush_all()
            sleep(poll_interval)
