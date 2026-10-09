# Shared Library for Terraforming Machine Automation
# Reusable controllers for Heat Generators, Pressure Generators, and Oxygen Generators.
# Note: Solar Generators and Power Grid Management have been moved to lib/power.py.

from archive import archive
from tree_console import TreeConsole
from swallow import swallowed
from production import discover_fluid_sources
import fluid_routing
import lead_cask
from hysteresis import HysteresisLatch
import power
import script_restart
from game_clock import now_tick
from machine_controller import MachineController

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
# the number the Power Guard reads) the heater disconnects steam_in
# and runs as Mk II; it reconnects at STEAM_POOL_START_FRACTION. A grid with
# no measurable steam tank leaves the guard open. Water has no guard: water is not a power reserve.
# The pool is read every STEAM_GUARD_INTERVAL_TICKS, not every feed pass: a
# heater draws at most 12 t/h of steam, so a late guard costs it ~1 t per
# 5 game minutes against a pool of thousands of tons.

FLUID_CHECK_INTERVAL_TICKS = 20

STEAM_POOL_STOP_FRACTION = 0.50
STEAM_POOL_START_FRACTION = 0.70
STEAM_GUARD_INTERVAL_TICKS = 3000

# FluidInputRouter constants, same values as the Plant Terraformer's water router.
FLUID_STALL_STREAK_BLACKLIST_THRESHOLD = 5
FLUID_RESCAN_INTERVAL_TICKS = 150
FLUID_DISCOVERY_CACHE_INTERVAL_TICKS = 100
FLUID_NEUTRAL_GRACE_STEPS = 5

MK3_TIER = 3

# Mk IV rod magazine (Mk4RodFeed): a Mk IV generator burns one Fuel Rod per
# 240 game h from its `input` magazine (4 slots) and stops without one. The
# feed keeps MK4_MAGAZINE_TARGET rods staged, taken from this outpost's Lead
# Casks (lib/lead_cask.py), checked every MK4_CHECK_INTERVAL_TICKS.
MK4_TIER = 4
MK4_MAGAZINE_TARGET = 1
MK4_CHECK_INTERVAL_TICKS = 600


MK3_PORT_RESTART_REASON = "mk3_port_unbound"
MK4_INPUT_RESTART_REASON = "mk4_input_unbound"


class UnboundPortRestart:
    """
    The game binds an upgrade's port (steam_in / water_in, Mk IV input) on
    `self` only when the script starts, so a pack applied under a running
    script leaves it missing. missing() asks orchestrator_automation.py for a
    restart once per script run (lib/script_restart.py); present() drops this
    machine's request once the port is there.
    """

    def __init__(self, name, port_name, reason, log: "TreeConsole"):
        self.name = name
        self.port_name = port_name
        self.reason = reason
        self.log = log
        self.requested = False
        self.cleared = False

    def missing(self, tick):
        if self.requested:
            return
        self.requested = True
        state = script_restart.request_restart(self.name, self.reason, tick)
        warn = self.log.level("warn")
        if state == script_restart.STATE_GAVE_UP:
            warn.print(f"[{self.name}] {self.port_name} still unbound after {script_restart.MAX_RESTARTS} restarts -- restart the script by hand.")
        elif state == script_restart.STATE_REQUESTED:
            warn.print(f"[{self.name}] {self.port_name} unbound (the game binds it at script start) -- restart requested from the orchestrator Automation.")
        else:
            warn.print(f"[{self.name}] {self.port_name} unbound and the restart request could not be written -- restart the script by hand.")

    def present(self):
        if self.cleared:
            return
        self.cleared = True
        entry = script_restart.clear_restart(self.name, self.reason)
        if entry:
            self.log.print(f"[{self.name}] {self.port_name} bound after {entry.get('restarts', 0)} restart(s).")


class Mk3FluidFeed:
    """
    Keeps one Mk III input port (steam_in or water_in) on a reachable source,
    network-wide, own outpost first. step() is called every controller poll;
    it routes at most every FLUID_CHECK_INTERVAL_TICKS and logs is_degraded()
    transitions at info level.
    """

    def __init__(self, machine: "OxygenGenerator | TempHeater | PressureGenerator", fluid_key, name, log: "TreeConsole", steam_guard=False):
        self.machine = machine
        self.fluid_key = fluid_key
        self.name = name
        self.log = log
        self.steam_guard = steam_guard
        self.clock = get_component("clock")
        self.power = get_component("power_control") if steam_guard else None
        # Active = guard closed (steam_in released to the turbines); an unreadable pool opens it.
        self.guard = HysteresisLatch(STEAM_POOL_STOP_FRACTION, STEAM_POOL_START_FRACTION, on_above=False)
        self.last_check_tick = None
        self.last_guard_tick = None
        self.last_degraded = None
        self.restart = UnboundPortRestart(name, fluid_key, MK3_PORT_RESTART_REASON, log)
        self.router = fluid_routing.FluidInputRouter(
            discover=self._discover_sources,
            rescan_interval_ticks=FLUID_RESCAN_INTERVAL_TICKS,
            discovery_cache_interval_ticks=FLUID_DISCOVERY_CACHE_INTERVAL_TICKS,
            stall_streak_threshold=FLUID_STALL_STREAK_BLACKLIST_THRESHOLD,
            neutral_grace_steps=FLUID_NEUTRAL_GRACE_STEPS,
            label=f"{name}.{fluid_key}",
            reserve_fluid="water" if fluid_key == "water_in" else None,
        )

    def _own_outpost_id(self):
        return getattr(getattr(self.machine, "outpost", None), "id", None)

    def _discover_sources(self):
        self.log.start(f"[{self.name}] _discover_sources", level="debug")
        own_outpost_id = self._own_outpost_id()
        if self.fluid_key == "steam_in":
            # Same candidates and order as the Steam Turbine / Condenser: steam Gas Tanks, then Caps.
            ranked = fluid_routing.discover_ranked(fluid_routing.STEAM_SOURCE_TIERS, own_outpost_id)
            self.log.debug(f"steam_in: sources (steam tanks, then Caps; own outpost first): {ranked}.")
            self.log.end()
            return ranked
        ids = discover_fluid_sources(self.fluid_key, own_outpost_id)
        self.log.debug(f"{self.fluid_key}: sources (own outpost first): {ids}.")
        self.log.end()
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
        if not measure_grid:
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
        now = measure_grid(grid)
        if now["steam_cap"] <= 0:
            return None
        return now["steam_t"] / now["steam_cap"]

    @property
    def guard_open(self):
        return not self.guard.active

    def _update_guard(self, port: "FluidPort"):
        self.log.start(f"[{self.name}] _update_guard", level="debug")
        fraction = self._steam_pool_fraction()
        flip = self.guard.update(fraction)
        if fraction is None:
            self.log.debug("No measurable steam pool on this grid; steam guard stays open.")
        elif flip == "on":
            self.log.print(f"[{self.name}] Grid steam pool {fraction*100:.0f}% < {STEAM_POOL_STOP_FRACTION*100:.0f}% -- releasing steam_in to the turbines, running as Mk II.")
            self._disconnect(port)
        elif flip == "off":
            self.log.print(f"[{self.name}] Grid steam pool back to {fraction*100:.0f}% (>= {STEAM_POOL_START_FRACTION*100:.0f}%) -- reconnecting steam_in.")
        else:
            self.log.debug(f"Steam pool {fraction*100:.0f}%, guard {'open' if self.guard_open else 'closed'} (stop < {STEAM_POOL_STOP_FRACTION*100:.0f}%, start >= {STEAM_POOL_START_FRACTION*100:.0f}%).")
        self.log.end()

    def _disconnect(self, port: "FluidPort"):
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
        curr_tick = now_tick()
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
            self.restart.missing(curr_tick)
            return
        self.restart.present()

        if self.steam_guard:
            if self.last_guard_tick is None or not curr_tick or not 0 <= curr_tick - self.last_guard_tick < STEAM_GUARD_INTERVAL_TICKS:
                self.last_guard_tick = curr_tick
                self._update_guard(port)
            if not self.guard_open:
                self._report_degraded()
                return
        fluid_routing.ensure_input_logged(self.router, port, curr_tick, fluid_routing.port_starved(port), self.log, self.name, self.fluid_key,
                                          f"No {self.fluid_key} source on the network.")
        self._report_degraded()


class Mk4RodFeed:
    """Keeps a Mk IV generator's Fuel Rod magazine stocked from the outpost's Lead Casks."""

    def __init__(self, machine: "OxygenGenerator | TempHeater | PressureGenerator", name, log: "TreeConsole"):
        self.machine = machine
        self.name = name
        self.log = log
        self.clock = get_component("clock")
        self.last_check = None
        self.warned = False
        self.restart = UnboundPortRestart(name, "input", MK4_INPUT_RESTART_REASON, log)

    def step(self):
        now = now_tick()
        if self.last_check is not None and 0 <= now - self.last_check < MK4_CHECK_INTERVAL_TICKS:
            return
        self.last_check = now
        try:
            if int(self.machine.tier()) < MK4_TIER:
                return
            port = getattr(self.machine, "input", None)
            if port is None:
                self.restart.missing(now)
                return
            self.restart.present()
            staged = int(port.count())
        except Exception as error:
            swallowed("terraforming.Mk4RodFeed.step: machine.tier", error)
            return
        missing = MK4_MAGAZINE_TARGET - staged
        if missing <= 0:
            return
        outpost = getattr(self.machine, "outpost", None)
        moved = lead_cask.take_from_casks(port, lead_cask.ROD_ITEM, missing, outpost)
        if moved > 0:
            self.warned = False
            self.log.print(f"[{self.name}] Loaded {moved} Fuel Rod(s) into the Mk IV magazine ({staged + moved} staged).")
        elif not self.warned:
            self.warned = True
            self.log.level("warn").print(f"[{self.name}] Mk IV magazine has {staged} Fuel Rod(s) and no Lead Cask at '{getattr(outpost, 'id', '?')}' holds any.")


class HeatController(MachineController):
    """
    Manages optimal power setpoint calibration for Heat Generators.
    Tracks day / weather condition changes, sweeps 1-10W to find 100% efficiency,
    and caches learned optimal setpoints per thermal state locally and in the Data Archive.
    """
    LABEL = "Heat Generator"
    POLL_S = 2.0

    def online_message(self):
        return f"Heat Generator ({self.name}) online via Shared Library."

    def __init__(self, machine: "TempHeater", clock: "Clock | None" = None):
        self.machine = machine
        self.clock = clock or get_component("clock")
        self.name = getattr(machine, "id", "heater")
        self.learned_optimal = archive.get("heat.optimal_setpoints", {})
        self.last_day = None
        self.last_state = None
        self.log = TreeConsole(module="terraforming")
        self.feed = Mk3FluidFeed(machine, "steam_in", self.name, self.log, steam_guard=True)
        self.rods = Mk4RodFeed(machine, self.name, self.log)

    def step(self):
        self.feed.step()
        self.rods.step()
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


# PressureController pacing: poll every tick only near the sync window, otherwise sleep most of the way
# to it (the gauge rises a fixed amount per tick, measured from two reads).
TICKS_PER_SECOND = 10
PRESSURE_MIN_POLL_S = 0.1
PRESSURE_MAX_POLL_S = 5.0
PRESSURE_WAKE_FRACTION = 0.7


class PressureController(MachineController):
    """
    Manages resonance sweep gauge synchronization for Pressure Generators.
    Identifies the sync window [next_window_low, next_window_high] and triggers
    self.sync() inside the window for 100% compression efficiency.
    """
    LABEL = "Pressure Generator"
    STEP_DELAY = True
    POLL_S = PRESSURE_MIN_POLL_S

    def online_message(self):
        return f"Pressure Generator ({self.name}) online via Shared Library."

    def __init__(self, machine: "PressureGenerator"):
        self.machine = machine
        self.name = getattr(machine, "id", "pressure")
        self.synced_this_sweep = False
        self.last_gauge = self.machine.gauge()
        self.clock = get_component("clock")
        self.last_tick = self.get_current_tick()
        self.gauge_per_tick = 0.0  # measured sweep speed (gauge units per tick), 0 until two reads a tick apart
        self.log = TreeConsole(module="terraforming")
        self.feed = Mk3FluidFeed(machine, "water_in", self.name, self.log)
        self.rods = Mk4RodFeed(machine, self.name, self.log)

    def step(self):
        """One poll. Returns the seconds to sleep before the next one (see next_poll_seconds())."""
        self.feed.step()
        self.rods.step()
        gauge = self.machine.gauge()
        low = self.machine.next_window_low()
        high = self.machine.next_window_high()
        tick = self.get_current_tick()

        # Gauge wrap detection (~100 to ~0) resets the sync flag for the new sweep
        if gauge < self.last_gauge and (self.last_gauge - gauge) > 20:
            self.synced_this_sweep = False
            self.log.debug(f"[{self.name}] Gauge wrap detected ({self.last_gauge:.1f} -> {gauge:.1f}); resetting synced flag for new sweep, next window [{low:.1f}, {high:.1f}].")
        elif tick > self.last_tick and gauge > self.last_gauge:
            self.gauge_per_tick = (gauge - self.last_gauge) / (tick - self.last_tick)

        self.last_gauge = gauge
        self.last_tick = tick

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
        return self.next_poll_seconds(gauge, low, high)

    def next_poll_seconds(self, gauge, low, high):
        """
        Sleep that wakes just before the gauge reaches the next target: the
        window's low edge while this sweep is unsynced, else (synced, or the window
        already passed) the wrap at 100.
        PRESSURE_WAKE_FRACTION of the predicted time, at least
        PRESSURE_MIN_POLL_S and at most PRESSURE_MAX_POLL_S; PRESSURE_MIN_POLL_S
        while the sweep speed is unknown or the gauge is at/inside the target.
        """
        rate = self.gauge_per_tick
        if rate <= 0:
            return PRESSURE_MIN_POLL_S
        if self.synced_this_sweep or (low <= high and gauge > high):  # synced, or this sweep's window already passed
            distance = 100.0 - gauge
        elif gauge < low:
            distance = low - gauge
        elif low > high and gauge > high:  # window wraps past 100; low edge still ahead
            distance = low - gauge
        else:
            return PRESSURE_MIN_POLL_S
        seconds = distance / rate / TICKS_PER_SECOND * PRESSURE_WAKE_FRACTION
        return min(PRESSURE_MAX_POLL_S, max(PRESSURE_MIN_POLL_S, seconds))


class OxygenController(MachineController):
    """
    Manages intake optimization and carbon waste dumping for Oxygen Generators.
    Sets intake to peak sweet spot (CO2 / 10), and dumps carbon waste inside the
    clean window (50-60 units) to avoid penalties or production stalling at 100.
    """
    LABEL = "Oxygen Generator"
    POLL_S = 1.0

    def online_message(self):
        return f"Oxygen Generator ({self.name}) online via Shared Library."

    def __init__(self, machine: "OxygenGenerator", atmo=None):
        self.machine = machine
        self.atmo = atmo or get_component("atmosphere")
        self.name = getattr(machine, "id", "o2gen")
        self.log = TreeConsole(module="terraforming")
        self.feed = Mk3FluidFeed(machine, "water_in", self.name, self.log)
        self.rods = Mk4RodFeed(machine, self.name, self.log)

    def step(self):
        self.feed.step()
        self.rods.step()
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
