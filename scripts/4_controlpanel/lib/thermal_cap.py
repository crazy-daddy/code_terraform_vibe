import fluid_routing
from version_guard import validate_game_version
from tree_console import TreeConsole, flush_all, reset_all
from swallow import swallowed
from script_parking import ParkRequester

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
THROTTLE_TRICKLE = 0.3          # below PRESSURE_BAND_MODERATE: steady release into the
                                 # Gas Tank / Turbines; steam moved downstream is not lost,
                                 # and a lower chamber leaves more time between polls

# Relief valve only opens once the release valve is already wide open and
# still can't prevent pressure climbing past this point -- a small relief
# bleed is far cheaper than an overpressure blowoff (which dumps the entire
# chamber, not just the surplus).
PRESSURE_RELIEF_THRESHOLD = 0.95
POLL_SECONDS = 1.0       # pressure at/above PRESSURE_BAND_MODERATE: chamber can reach the ceiling quickly
POLL_SECONDS_LOW = 3.0   # pressure below PRESSURE_BAND_MODERATE: far from overpressure
# Once a pressure rise has been seen, the sleep is CAP_WAKE_FRACTION of the time the
# fastest rise seen so far would take to reach PRESSURE_BAND_CRITICAL, clamped to
# POLL_SECONDS .. CAP_MAX_POLL_SECONDS. Worst-case rate, so a vent turning active
# mid-sleep cannot outrun it.
CAP_WAKE_FRACTION = 0.5
CAP_MAX_POLL_SECONDS = 30.0
# Breaker parking (lib/script_parking.py) while the vent is dormant and the chamber is
# drained to at most CAP_PARK_MAX_PRESSURE. Parked for CAP_PARK_WAKE_FRACTION of the time
# left until the vent turns active (Deep-surveyed vents, next_phase_in()), else of the
# time the fastest confirmed rise needs from empty to PRESSURE_BAND_CRITICAL; never
# without a known rise rate or phase timing.
CAP_PARK_MAX_PRESSURE = 0.02
CAP_PARK_WAKE_FRACTION = 0.5

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
# player builds a new Gas Pipe route to it) -- an entry expires and becomes
# retryable again once it's been blacklisted for this many *simulation*
# ticks (not step() calls -- see get_current_tick()/clock.tick()), tracked
# per-entry (self._router.blacklist maps tank_id -> the tick it was
# blacklisted at, see lib/fluid_routing.py's PerEntryBlacklist), not as one
# shared "clear everything at once" timer. That distinction
# matters: with 2+ simultaneously-bad candidates ranked ahead of the one
# genuinely-reachable tank (by fill_pct/discovery-order ties), eliminating
# all of them can take longer than this window -- a single shared clock that
# wipes the *whole* blacklist at once would undo that progress and restart
# the elimination from scratch before ever reaching the reachable tank,
# producing exactly the infinite ping-pong between the bad candidates this
# was meant to prevent. Per-entry expiry means each bad candidate's own
# timer runs independently, so forward progress toward the untried
# reachable one is never erased by an unrelated entry's clock.
RESCAN_INTERVAL_TICKS = 300

# fluid_routing.discover_network_buildings() walks outpost_network.outposts()
# and every outpost's buildings(type_id) -- real work, and (see profiling.py /
# docs/AI_CHEATSHEET.md) the actual cost driver of this controller's step().
# ensure_output_connection() only *needs* that walk when it's genuinely
# picking a new target (no current connection, current is blacklisted, or
# current just became full); a healthy connection is confirmed with a single
# fill_pct() read on the one id already in use (see the fast path below),
# so in steady state this cache barely ever gets exercised at all. It exists
# as a ceiling for the remaining cases (bootstrap, every candidate blacklisted
# at once) so repeated reselection attempts in a short window don't each pay
# the full network walk. Simulation ticks (same units as RESCAN_INTERVAL_TICKS
# above), not step() calls -- see FluidOutputRouter._discovered_at_tick for why:
# ~10 s at normal speed, so a newly built/assigned tank is seen that fast.
DISCOVERY_CACHE_INTERVAL_TICKS = 100


class ThermalCapController:
    """Keeps a Thermal Cap's chamber pressure off the overpressure ceiling."""

    def __init__(self, cap):
        self.cap = cap
        self.name = getattr(cap, "id", "thermal_cap")
        self.last_phase = None
        self.last_pressure = None
        self.last_pressure_tick = None
        self.max_rise_per_tick = 0.0  # fastest confirmed chamber rise (fraction per tick)
        self.last_rise = 0.0
        self.parker = ParkRequester(self.name, "thermal_cap")
        self.clock = get_component("clock")
        self.log = TreeConsole(module="thermal_cap")
        # See lib/fluid_routing.py's FluidOutputRouter/PerEntryBlacklist for
        # the full rationale (per-entry blacklist expiry, BuildingRef
        # resolution, id-lookup/connected-id-sync caching) -- this router
        # owns all of it; ThermalCapController only supplies its own tuning
        # constants and print wording.
        self._router = fluid_routing.FluidOutputRouter(
            type_ids="gas_tank",
            rebalance_fill_fraction=GAS_TANK_REBALANCE_FILL_FRACTION,
            connection_grace_ticks=CONNECTION_GRACE_TICKS,
            rescan_interval_ticks=RESCAN_INTERVAL_TICKS,
            discovery_cache_interval_ticks=DISCOVERY_CACHE_INTERVAL_TICKS,
            fluid_id="steam",
        )

    def get_current_tick(self):
        if self.clock and hasattr(self.clock, "tick"):
            try:
                return self.clock.tick()
            except Exception as error:
                swallowed("thermal_cap.ThermalCapController.get_current_tick: self.clock.tick", error)
        return 0

    def ensure_output_connection(self):
        """
        Declares/rebalances steam_out's destination among known Gas Tanks
        (discovered network-wide -- see fluid_routing.discover_network_buildings()).
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

        curr_tick = self.get_current_tick()
        is_stalled = fluid_routing.safe_is_stalled(self.cap)
        self.log.trace(f"[{self.name}] Evaluating steam_out connection at tick {curr_tick} (stalled={is_stalled}, known candidates cached={len(self._router._cached_targets) if self._router._cached_targets is not None else 0}).")

        def on_blacklisted(target_id):
            self.log.level("warn").print(f"[{self.name}] '{target_id}' reported stalled (steam available, valve open, nothing transferred) -- likely no completed Gas Pipe route. Blacklisting and picking a different target.")

        def on_connect_notice(target_id, status, message):
            self.log.level("warn").print(f"[{self.name}] steam_out connect notice for '{target_id}': {status} - {message}")

        event = self._router.ensure_connection(port, curr_tick, is_stalled, on_blacklisted, on_connect_notice)
        if event.kind == "connected":
            self.log.print(f"[{self.name}] Connected steam_out -> '{event.target_id}' ({event.fill_pct*100:.0f}% full).")
        elif event.kind == "healthy":
            self.log.trace(f"[{self.name}] Current steam_out target still healthy; no rebalance needed this cycle.")
        elif event.kind == "waiting":
            # The relief valve (step()) is the safety net for this window,
            # not a forced reconnect attempt here.
            self.log.debug(f"[{self.name}] Every known Gas Tank is still within its blacklist window; waiting for one to expire.")
            for tid, blacklisted_at in self._router.blacklist._blacklisted_at.items():
                remaining = max(0, self._router.blacklist.rescan_interval_ticks - (curr_tick - blacklisted_at))
                self.log.debug(f"[{self.name}] Blacklisted target '{tid}': {remaining} tick(s) remaining until retry-eligible.")
        elif event.kind == "not_found":
            self.log.debug(f"[{self.name}] No Gas Tank found network-wide yet; steam_out has no destination.")

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
            self.log.print(f"[{self.name}] Vent phase changed: {self.last_phase} -> {phase}.")
            self.last_phase = phase

        pressure = self.cap.pressure() if hasattr(self.cap, "pressure") else 0.0

        throttle = self.release_throttle_for_pressure(pressure)
        if hasattr(self.cap, "set_throttle"):
            self.cap.set_throttle(throttle)
        if self.log.verbose:
            self.log.trace(f"[{self.name}] Pressure {pressure*100:.0f}% -> release throttle {throttle:.1f}.")

        # Relief valve: only engage once the release valve is already wide
        # open (throttle == 1.0) and pressure is still climbing toward the
        # ceiling -- a downstream jam (full Gas Tank, stalled Turbine,
        # disconnected pipe) that steam_out alone can't route around.
        if hasattr(self.cap, "set_relief"):
            if throttle >= 1.0 and pressure >= PRESSURE_RELIEF_THRESHOLD:
                relief = min(1.0, (pressure - PRESSURE_RELIEF_THRESHOLD) / (1.0 - PRESSURE_RELIEF_THRESHOLD))
                self.cap.set_relief(relief)
                if relief > 0:
                    self.log.level("warn").print(f"[{self.name}] Downstream can't keep up at {pressure*100:.0f}% pressure; venting {relief*100:.0f}% to atmosphere to avoid an overpressure blowoff.")
            else:
                self.cap.set_relief(0.0)
                if self.log.verbose:
                    self.log.trace(f"[{self.name}] Relief valve closed: pressure {pressure*100:.0f}% (need throttle==1.0 and >= {PRESSURE_RELIEF_THRESHOLD*100:.0f}% to engage relief); release throttle is {throttle:.1f}.")

        if hasattr(self.cap, "is_stalled") and self.cap.is_stalled():
            self.log.level("warn").print(f"[{self.name}] Stalled: release valve open with steam available but nothing downstream is accepting it. Check steam_out connection / Gas Tank / Steam Turbine.")

        if hasattr(self.cap, "is_overpressured") and self.cap.is_overpressured():
            self.log.level("error").print(f"[{self.name}] WARNING: Chamber overpressured -- banked steam was lost to atmosphere. Releasing sooner next cycle.")
            try:
                notify(f"[{self.name}] Thermal Cap overpressured; banked steam lost.", level="warn", duration_seconds=8.0)
            except Exception as error:
                swallowed("thermal_cap.ThermalCapController.step: notify", error)
        return self.next_poll_seconds(pressure)

    def park_wake_ticks(self):
        """Ticks this cap may stay parked, or None while it must keep running (see CAP_PARK_MAX_PRESSURE)."""
        if self.last_phase != "dormant" or self.last_pressure is None or self.last_pressure > CAP_PARK_MAX_PRESSURE:
            return None
        minutes = None
        if hasattr(self.cap, "next_phase_in"):
            try:
                minutes = self.cap.next_phase_in()
            except Exception as error:
                swallowed("thermal_cap.ThermalCapController.park_wake_ticks: self.cap.next_phase_in", error)
        if minutes is not None:
            seconds_per_hour = 25.0
            if self.clock and hasattr(self.clock, "real_seconds_per_hour"):
                try:
                    seconds_per_hour = float(self.clock.real_seconds_per_hour())
                except Exception as error:
                    swallowed("thermal_cap.ThermalCapController.park_wake_ticks: clock.real_seconds_per_hour", error)
            return int(minutes / 60.0 * seconds_per_hour * 10 * CAP_PARK_WAKE_FRACTION)
        if self.max_rise_per_tick <= 0:
            return None
        return int(PRESSURE_BAND_CRITICAL / self.max_rise_per_tick * CAP_PARK_WAKE_FRACTION)

    def next_poll_seconds(self, pressure):
        """Sleep before the next poll (see CAP_WAKE_FRACTION); learns the fastest rise from successive reads."""
        tick = self.get_current_tick()
        rise = 0.0
        if self.last_pressure is not None and tick > self.last_pressure_tick:
            rise = (pressure - self.last_pressure) / (tick - self.last_pressure_tick)
        # A rise only counts as a rate once the interval before it rose too: the first
        # rising interval after dormancy may have been active for only part of its length.
        confirmed = rise > 0 and self.last_rise > 0
        if confirmed:
            self.max_rise_per_tick = max(self.max_rise_per_tick, rise)
        self.last_rise = rise
        self.last_pressure = pressure
        self.last_pressure_tick = tick
        band_seconds = POLL_SECONDS if pressure >= PRESSURE_BAND_MODERATE else POLL_SECONDS_LOW
        if self.max_rise_per_tick <= 0 or (rise > 0 and not confirmed):
            return band_seconds
        headroom = max(0.0, PRESSURE_BAND_CRITICAL - pressure)
        seconds = headroom / max(self.max_rise_per_tick, rise) / 10.0 * CAP_WAKE_FRACTION
        return min(CAP_MAX_POLL_SECONDS, max(POLL_SECONDS, seconds))

    def run(self, poll_interval=None):
        self.log.print(f"Thermal Cap Controller ({self.name}) online. Guarding against overpressure.")
        validate_game_version()
        while True:
            reset_all()
            interval = POLL_SECONDS
            wake_ticks = None
            try:
                interval = self.step()
                wake_ticks = self.park_wake_ticks()
            except Exception as error:
                self.log.level("error").print(f"[{self.name}] Thermal Cap exception: {error}")
            self.parker.update(wake_ticks is not None and wake_ticks > 0, wake_ticks)
            flush_all()
            sleep(poll_interval if poll_interval is not None else interval)
