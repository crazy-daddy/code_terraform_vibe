# Reactor controller: one per Reactor (thin nuclear/reactor.py).
# Reactor (docs/components/reactor.md): up to 5,000 W from Fuel Rods and
# cooling water. Output follows core temperature: 0 below 300 °C, 50% at
# 600 °C, 100% at exactly 900 °C, back to 0 across the 900-950 °C red band;
# 950 °C overheats (shutdown until it cools to 600 °C). Fuel use follows the
# commanded heat, not the output, so the most energy per rod comes from
# holding the core just under 900 °C.
#
# Core model (simworker reactor step):
#   steady temperature = heat x gain, gain = 1200 °C x a hidden condition
#   multiplier in [0.7, 1.25] (GAIN_MIN_C..GAIN_MAX_C). The condition is
#   redrawn every 12 game h, at whole multiples of elapsed_game_hours().
#   The core approaches the steady temperature as a first-order lag at
#   LAG_PER_GH per game hour, so between two readings dt game h apart with
#   constant heat:  T1 = S + (T0 - S) * exp(-LAG_PER_GH * dt).
# Control:
#   - Gain: solved for S from two running readings with the same heat at
#     least MIN_SAMPLE_GH apart, gain = S / heat, clamped to the physical
#     range, blended per condition window (an estimate GAIN_JUMP_FRACTION off
#     the current one replaces it). Forgotten at every 12 h boundary.
#   - Heat = TARGET_C / gain. Unknown gain, or within BOUNDARY_LEAD_GH before
#     a boundary: SAFE_HEAT = TARGET_C / GAIN_MAX_C, which cannot pass
#     TARGET_C under any condition.
#   - Trip guard: temperature >= TRIP_C drops to SAFE_HEAT and forgets the
#     gain, so a bad estimate or a missed boundary cannot reach 950 °C.
#   - Poll: every POLL_GH game h while settling or near a boundary,
#     STEADY_POLL_GH once within STEADY_BAND_C of the target, scaled by
#     clock.real_seconds_per_hour() so game speed doesn't change the timing.
# Supplies:
#   - Fuel Rods: keeps ROD_STAGE rods in `input` from this outpost's Lead
#     Casks (lead_cask.take_from_casks(); hot cargo never crosses outposts),
#     checked every ROD_CHECK_INTERVAL_TICKS and on "no_fuel". The Fuel
#     Assembler counts these staged rods in its rod target.
#   - Fuel alert: each rod check writes this Reactor's entry in
#     lead_cask.REACTOR_FUEL_KEY (spare rods = staged + local casks, game hours
#     left = (fuel_level() + spare) x ROD_LIFE_GH / heat). "warn" with no spare
#     rod, "error" when out of fuel; each start is a warning line and a sticky
#     notify(), and the Status panel lists it under ALERTS. Written on a level
#     change and at least every ROD_CHECK_INTERVAL_TICKS; entries of Reactors no
#     longer on the network are pruned.
#   - Cooling water: `water_in` kept on a water source by FluidInputRouter
#     (production.FLUID_SOURCE_TYPE_IDS["water_in"], own outpost first);
#     starved = status "no_coolant". 0.5-1 t/h.
#   - Water reservation: the lowest-id Reactor on the network publishes
#     fluid_routing.WATER_RESERVE_KEY every WATER_RESERVE_PUBLISH_TICKS. It
#     holds while the pooled water tanks (fluid_routing.fluid_reserve_tons())
#     are below the floor = WATER_RESERVE_HOURS of full-heat cooling per
#     Reactor, capped at WATER_RESERVE_MAX_FRACTION of tank capacity, and
#     releases at WATER_RESERVE_RELEASE_FACTOR x floor. While it holds, every
#     other water consumer's FluidInputRouter disconnects and Harvesters skip
#     refills. No water tank: never holds (nothing to measure).
#     A starved Reactor does not overheat (no heating, no fuel use, cools at
#     60 °C/h); the reservation keeps its output.
# Not parked: heat returns to 0 when the script stops. No archive state; the
# gain is re-measured within a few polls after a restart.

import math

import fluid_routing
import lead_cask
from archive import archive
from production import discover_fluid_sources
from version_guard import validate_game_version
from tree_console import TreeConsole, flush_all, reset_all
from swallow import swallowed

# Simworker reactor constants (`reactor` block).
TEMP_SCALE_C = 1200.0
GAIN_MIN_C = TEMP_SCALE_C * 0.7
GAIN_MAX_C = TEMP_SCALE_C * 1.25
LAG_PER_GH = 0.6
CONDITION_PERIOD_GH = 12.0
FULL_OUTPUT_C = 900.0
OVERHEAT_C = 950.0

# Held core temperature: 97% output, 20 °C below the red band for estimate error.
TARGET_C = 880.0
# Above the target's band, under the red band's start plus a few degrees.
TRIP_C = 910.0
SAFE_HEAT = TARGET_C / GAIN_MAX_C

# Gain estimation.
MIN_SAMPLE_GH = 0.03
MIN_HEAT_FOR_GAIN = 0.05
GAIN_BLEND = 0.5
GAIN_JUMP_FRACTION = 0.10
HEAT_DEADBAND = 0.005

# Timing (game hours) and the fallback when the clock can't say.
BOUNDARY_LEAD_GH = 0.15
POLL_GH = 0.04
STEADY_POLL_GH = 0.1
STEADY_BAND_C = 15.0
FALLBACK_SECONDS_PER_GH = 25.0

# Supplies.
ROD_STAGE = 1
ROD_CHECK_INTERVAL_TICKS = 600
ROD_LIFE_GH = 72.0
WATER_STALL_STREAK_BLACKLIST_THRESHOLD = 5
WATER_RESCAN_INTERVAL_TICKS = 150
WATER_DISCOVERY_CACHE_INTERVAL_TICKS = 100
WATER_NEUTRAL_GRACE_STEPS = 5

# Water reservation (see header).
COOLANT_MAX_T_PER_GH = 1.0
WATER_RESERVE_HOURS = 48.0
WATER_RESERVE_MAX_FRACTION = 0.5
WATER_RESERVE_RELEASE_FACTOR = 1.25
WATER_RESERVE_PUBLISH_TICKS = 300
REACTOR_DISCOVERY_TICKS = 600
REACTOR_TYPE_ID = "reactor"

RUNNING = "running"


def steady_state(t0, t1, dt_gh):
    """Temperature the core is heading to, from two readings dt_gh apart under constant heat. None if dt_gh is too short."""
    if dt_gh < MIN_SAMPLE_GH:
        return None
    decay = math.exp(-LAG_PER_GH * dt_gh)
    return (t1 - t0 * decay) / (1.0 - decay)


def condition_window(game_hours):
    """Index of the 12 game h window the hidden condition is drawn for."""
    return int(math.floor(max(0.0, game_hours) / CONDITION_PERIOD_GH))


def hours_to_boundary(game_hours):
    return CONDITION_PERIOD_GH * (condition_window(game_hours) + 1) - game_hours


def heat_for(gain):
    """Heat that holds TARGET_C at this gain; SAFE_HEAT when unknown."""
    if not gain:
        return SAFE_HEAT
    return min(1.0, max(0.0, TARGET_C / gain))


def _notify(text, level="warn", duration=8.0):
    try:
        notify(text, level=level, duration_seconds=duration)
    except Exception as error:
        swallowed("reactor._notify: notify", error)


class ReactorController:
    """Holds a Reactor just under full output with a measured gain, and keeps it fuelled and cooled."""

    def __init__(self, reactor):
        self.reactor = reactor
        self.name = getattr(reactor, "id", "reactor")
        self.clock = get_component("clock")
        self.log = TreeConsole(module="reactor")
        self.gain = None
        self.window = None
        self.anchor = None
        self.heat = None
        self.status = None
        self.temp = 0.0
        self.last_rod_check = None
        self.rods_warned = False
        self.water_warned = False
        self.fuel_alert = ""
        self.fuel_publish_tick = None
        self.reactor_ids = []
        self.reactor_ids_tick = None
        self.reserve_tick = None
        self.reserve_hold = False
        self.router = fluid_routing.FluidInputRouter(
            discover=self._discover_water,
            rescan_interval_ticks=WATER_RESCAN_INTERVAL_TICKS,
            discovery_cache_interval_ticks=WATER_DISCOVERY_CACHE_INTERVAL_TICKS,
            stall_streak_threshold=WATER_STALL_STREAK_BLACKLIST_THRESHOLD,
            neutral_grace_steps=WATER_NEUTRAL_GRACE_STEPS,
            label=f"{self.name}.water_in",
        )

    # ------------------------------------------------------------------
    # Clock
    # ------------------------------------------------------------------
    def tick(self):
        if self.clock is None:
            return 0
        try:
            return self.clock.tick()
        except Exception as error:
            swallowed("reactor.ReactorController.tick: clock.tick", error)
            return 0

    def seconds_per_gh(self):
        if self.clock is None:
            return FALLBACK_SECONDS_PER_GH
        try:
            seconds = float(self.clock.real_seconds_per_hour())
            if seconds > 0:
                return seconds
        except Exception as error:
            swallowed("reactor.ReactorController.seconds_per_gh: clock.real_seconds_per_hour", error)
        return FALLBACK_SECONDS_PER_GH

    def game_hours(self):
        if self.clock is not None:
            try:
                return float(self.clock.elapsed_game_hours())
            except Exception as error:
                swallowed("reactor.ReactorController.game_hours: clock.elapsed_game_hours", error)
        return self.tick() * 0.1 / FALLBACK_SECONDS_PER_GH

    # ------------------------------------------------------------------
    # Heat control
    # ------------------------------------------------------------------
    def forget_gain(self, reason):
        if self.gain is not None:
            self.log.debug(f"[{self.name}] Gain {self.gain:.0f} °C forgotten: {reason}.")
        self.gain = None
        self.anchor = None

    def measure(self, now_gh, temp, heat, running):
        """Updates the gain from the anchor reading, then re-anchors on this one."""
        anchor = self.anchor
        if not running or heat is None or heat < MIN_HEAT_FOR_GAIN:
            self.anchor = None
            return
        if anchor is None or anchor["heat"] != heat or now_gh < anchor["gh"]:
            self.anchor = {"gh": now_gh, "temp": temp, "heat": heat}
            return
        target = steady_state(anchor["temp"], temp, now_gh - anchor["gh"])
        if target is None:
            return
        sample = min(GAIN_MAX_C, max(GAIN_MIN_C, target / heat))
        if self.gain is None or abs(sample - self.gain) > GAIN_JUMP_FRACTION * self.gain:
            self.gain = sample
        else:
            self.gain = self.gain * (1.0 - GAIN_BLEND) + sample * GAIN_BLEND
        if self.log.verbose:
            self.log.trace(f"[{self.name}] {anchor['temp']:.1f} -> {temp:.1f} °C in {now_gh - anchor['gh']:.3f} gh at heat {heat:.3f}: heading {target:.0f} °C, gain sample {sample:.0f}, gain {self.gain:.0f}.")
        self.anchor = {"gh": now_gh, "temp": temp, "heat": heat}

    def choose_heat(self, now_gh, temp):
        """(heat, reason)."""
        if temp >= TRIP_C:
            self.forget_gain(f"core {temp:.0f} °C >= trip {TRIP_C:.0f} °C")
            return SAFE_HEAT, "trip"
        if hours_to_boundary(now_gh) <= BOUNDARY_LEAD_GH:
            return min(SAFE_HEAT, heat_for(self.gain)), "boundary"
        if self.gain is None:
            return SAFE_HEAT, "measuring"
        return heat_for(self.gain), "hold"

    def set_heat(self, heat):
        if self.heat is not None and abs(heat - self.heat) < HEAT_DEADBAND:
            return
        try:
            result = self.reactor.set_heat(heat)
        except Exception as error:
            swallowed("reactor.ReactorController.set_heat: reactor.set_heat", error)
            return
        if getattr(result, "status", "ok") == "ok":
            self.heat = heat
            self.anchor = None

    def read_heat(self):
        try:
            return float(self.reactor.heat())
        except Exception as error:
            swallowed("reactor.ReactorController.read_heat: reactor.heat", error)
            return self.heat

    # ------------------------------------------------------------------
    # Supplies
    # ------------------------------------------------------------------
    def _discover_water(self):
        own = getattr(getattr(self.reactor, "outpost", None), "id", None)
        ranked = discover_fluid_sources("water_in", own)
        self.log.debug(f"[{self.name}] water_in sources (own outpost '{own}' first): {ranked}.")
        return ranked

    def ensure_water(self):
        port = getattr(self.reactor, "water_in", None)

        def on_dropped(source_id, reason):
            self.log.level("warn").print(f"[{self.name}] Dropping water source '{source_id}': {reason}.")

        def on_connect_notice(source_id, status, message):
            self.log.level("warn").print(f"[{self.name}] water_in connect notice for '{source_id}': {status} - {message}")

        event = self.router.ensure(port, self.tick(), self.status == "no_coolant", on_dropped, on_connect_notice)
        if event.kind == "connected":
            self.water_warned = False
            self.log.print(f"[{self.name}] Connected water_in -> '{event.source_id}'.")
        elif event.kind in ("not_found", "exhausted") and not self.water_warned:
            self.water_warned = True
            self.log.level("warn").print(f"[{self.name}] No reachable water source for cooling (Water Pump, Steam Condenser or water tank).")

    def ensure_rods(self, force=False):
        now = self.tick()
        if not force and self.last_rod_check is not None and 0 <= now - self.last_rod_check < ROD_CHECK_INTERVAL_TICKS:
            return
        self.last_rod_check = now
        try:
            port = self.reactor.input
            staged = int(port.count())
        except Exception as error:
            swallowed("reactor.ReactorController.ensure_rods: reactor.input", error)
            return
        outpost = getattr(self.reactor, "outpost", None)
        casks = lead_cask.casks_at(outpost)
        missing = ROD_STAGE - staged
        if missing > 0:
            moved = lead_cask.take_from_casks(port, lead_cask.ROD_ITEM, missing, outpost, casks)
            staged += moved
            if moved > 0:
                self.rods_warned = False
                self.log.print(f"[{self.name}] Loaded {moved} Fuel Rod(s) ({staged} staged).")
            elif not self.rods_warned:
                self.rods_warned = True
                self.log.level("warn").print(f"[{self.name}] {staged} Fuel Rod(s) staged and no Lead Cask at '{getattr(outpost, 'id', '?')}' holds any.")
        self.report_fuel(now, staged + lead_cask.cask_stock(lead_cask.ROD_ITEM, casks=casks), getattr(outpost, "id", None))

    def fuel_state(self, spare):
        """(level, alert, hours): level "" / "warn" / "error", hours = game hours of fuel left at the current heat."""
        try:
            active = float(self.reactor.fuel_level())
        except Exception as error:
            swallowed("reactor.ReactorController.fuel_state: reactor.fuel_level", error)
            active = 0.0
        heat = max(self.heat or SAFE_HEAT, MIN_HEAT_FOR_GAIN)
        hours = (active + spare) * ROD_LIFE_GH / heat
        if self.status == "no_fuel":
            return "error", "OUT OF FUEL RODS", hours
        if spare <= 0:
            return "warn", f"no spare Fuel Rod, ~{hours:.0f} h left", hours
        return "", "", hours

    def report_fuel(self, now, spare, outpost_id):
        """Warns and notifies when the fuel level changes; publishes this Reactor's REACTOR_FUEL_KEY entry."""
        level, alert, hours = self.fuel_state(spare)
        changed = level != self.fuel_alert
        if changed:
            where = f"Fuel Assembler and Lead Casks at '{outpost_id}'"
            if level == "error":
                self.log.level("error").print(f"[{self.name}] OUT OF FUEL RODS: no power from this Reactor. Check the {where}.")
                _notify(f"[Power] Reactor '{self.name}' is OUT OF FUEL RODS: main power lost. Check the {where}.", level="error", duration=0)
            elif level == "warn":
                self.log.level("warn").print(f"[{self.name}] No spare Fuel Rod: ~{hours:.0f} game h of fuel left. Check the {where}.")
                _notify(f"[Power] Reactor '{self.name}' has no spare Fuel Rod: ~{hours:.0f} game h of fuel left. Check the {where}.", level="warn", duration=0)
            else:
                self.log.print(f"[{self.name}] Fuel supply restored: {spare} spare Fuel Rod(s).")
            self.fuel_alert = level
        if not changed and self.fuel_publish_tick is not None and 0 <= now - self.fuel_publish_tick < ROD_CHECK_INTERVAL_TICKS:
            return
        self.fuel_publish_tick = now
        live = set(self.network_reactors(now))
        entry = {"outpost": outpost_id, "status": self.status, "spare": spare, "hours": round(hours, 1),
                 "alert": alert, "level": level, "tick": now}

        def updater(stored):
            stored = {k: v for k, v in stored.items() if k in live} if isinstance(stored, dict) else {}
            stored[self.name] = entry
            return stored

        try:
            archive.transaction(lead_cask.REACTOR_FUEL_KEY, {}, updater)
        except Exception as error:
            swallowed("reactor.ReactorController.report_fuel: archive.transaction", error)

    def network_reactors(self, now):
        """Reactor ids network-wide, rediscovered every REACTOR_DISCOVERY_TICKS."""
        if self.reactor_ids_tick is None or not 0 <= now - self.reactor_ids_tick < REACTOR_DISCOVERY_TICKS:
            pairs = fluid_routing.discover_network_buildings(REACTOR_TYPE_ID, resolve=False)
            self.reactor_ids = sorted({str(b_id) for b_id, _ in pairs if b_id} | {self.name})
            self.reactor_ids_tick = now
        return self.reactor_ids

    def water_floor(self, reactors, capacity):
        """Tons held back for the Reactors' cooling."""
        return min(WATER_RESERVE_HOURS * COOLANT_MAX_T_PER_GH * reactors, WATER_RESERVE_MAX_FRACTION * capacity)

    def publish_water_reserve(self):
        """Leader only: writes the reservation verdict (fluid_routing.WATER_RESERVE_KEY)."""
        now = self.tick()
        if self.reserve_tick is not None and 0 <= now - self.reserve_tick < WATER_RESERVE_PUBLISH_TICKS:
            return
        self.reserve_tick = now
        reactors = self.network_reactors(now)
        if reactors[0] != self.name:
            return
        tons = fluid_routing.fluid_reserve_tons("water")
        if tons is None:
            hold, level, floor = False, 0.0, 0.0
        else:
            level, capacity = tons
            floor = self.water_floor(len(reactors), capacity)
            line = floor * WATER_RESERVE_RELEASE_FACTOR if self.reserve_hold else floor
            hold = level < line
        if hold != self.reserve_hold:
            self.reserve_hold = hold
            if hold:
                self.log.level("warn").print(f"[{self.name}] Water reserve ON: tanks {level:.0f} t < {floor:.0f} t floor; only Reactors draw water.")
                _notify(f"[Power] Water reserved for {len(reactors)} Reactor(s): tanks at {level:.0f} t.")
            else:
                self.log.print(f"[{self.name}] Water reserve OFF: tanks {level:.0f} t (release at {floor * WATER_RESERVE_RELEASE_FACTOR:.0f} t).")
        try:
            archive.set(fluid_routing.WATER_RESERVE_KEY, {"hold": hold, "level_t": round(level, 1), "floor_t": round(floor, 1), "tick": now, "by": self.name})
        except Exception as error:
            swallowed("reactor.ReactorController.publish_water_reserve: archive.set", error)

    # ------------------------------------------------------------------
    # Loop
    # ------------------------------------------------------------------
    def read(self):
        """(status, temperature) or (None, None) when unreadable."""
        try:
            return str(self.reactor.status()), float(self.reactor.temperature())
        except Exception as error:
            swallowed("reactor.ReactorController.read: reactor.status", error)
            return None, None

    def on_status(self, status, temp):
        if status == self.status:
            return
        previous = self.status
        self.status = status
        if status == RUNNING:
            self.log.print(f"[{self.name}] Running ({temp:.0f} °C).")
            return
        if status == "overheated":
            self.forget_gain("overheated")
            self.log.level("warn").print(f"[{self.name}] Overheated at {temp:.0f} °C, cooling to 600 °C.")
            _notify(f"[Power] Reactor '{self.name}' overheated and is cooling down.")
        elif status == "no_fuel":
            self.log.level("warn").print(f"[{self.name}] Out of Fuel Rods.")
        elif status == "no_coolant":
            self.log.level("warn").print(f"[{self.name}] Cooling water starved.")
        else:
            self.log.level("warn").print(f"[{self.name}] Status '{status}' (was '{previous}').")

    def step(self):
        """Returns the game hours until the next poll."""
        status, temp = self.read()
        if status is None or temp is None:
            return POLL_GH
        self.temp = temp
        self.on_status(status, temp)
        now_gh = self.game_hours()
        window = condition_window(now_gh)
        if window != self.window:
            if self.window is not None:
                self.forget_gain(f"condition window {window} began")
            self.window = window
        self.measure(now_gh, temp, self.read_heat(), status == RUNNING)
        heat, reason = self.choose_heat(now_gh, temp)
        if self.log.verbose:
            gain = f"{self.gain:.0f}" if self.gain else "?"
            self.log.trace(f"[{self.name}] {status}, {temp:.1f} °C, gain {gain} -> heat {heat:.3f} ({reason}).")
        self.set_heat(heat)
        self.ensure_rods(force=status == "no_fuel")
        self.ensure_water()
        self.publish_water_reserve()
        settled = reason == "hold" and abs(temp - TARGET_C) <= STEADY_BAND_C
        return STEADY_POLL_GH if settled else POLL_GH

    def run(self):
        self.log.print(f"Reactor Controller ({self.name}) online. Holds {TARGET_C:.0f} °C with a measured gain.")
        validate_game_version()
        while True:
            reset_all()
            poll_gh = POLL_GH
            try:
                poll_gh = self.step()
            except Exception as error:
                self.log.level("error").print(f"[{self.name}] Reactor exception: {error}")
            flush_all()
            sleep(poll_gh * self.seconds_per_gh())
