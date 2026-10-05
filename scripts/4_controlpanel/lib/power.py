# Power Guard: one PowerGridManager per grid, driven by control_room_automation.py.
#
# What a grid needs depends on its power phase (grid_phase(), from the
# generator types among its members), not on the save's progression:
#   - "solar":   only Solar Generators (and batteries). The night is the dry
#                spell and its length is known: lib/power_solar.py's
#                SolarNightGuard forecasts the night and sheds against it.
#   - "steam":   Steam Turbines join. Night is no dry spell while Gas Tanks
#                still hold steam, and the real dry spell (vent dormancy) has
#                nothing to do with the sun, so a sun-based guard would shed
#                every night with thousands of tons of steam banked.
#   - "oil":     Oil Generators join. lib/oil_generator.py burns oil as last
#                resort and as base load while oil is in surplus.
#   - "reactor": a Reactor is producing. It outshines every other source, so
#                oil surplus burning stops (oil_generator.py and
#                script_parking.py read reactor_carried()); oil stays as the
#                low-reserve last resort only.
#
# Steam, oil and reactor grids share one guard that treats both stores as one
# energy reserve:
#   - Battery pool: grid.stored/.capacity plus Lightning Rod reserve.
#   - Steam pool:   every steam Gas Tank on the grid's outposts, converted to
#                   Wh at the Steam Turbine's own rate (108 W per 90 t/h).
# Every phase runs:
#   0. Turbine commitment (lib/turbine_commit.py): runs just enough Steam
#      Turbines at full output, plus spares, and parks the rest at the breaker
#      (a no-op without turbines).
#   1. Daily balance: snapshot both pools at each day rollover, record the
#      net gain/loss per day (bounded history), and notify() once per day
#      when either pool lost more than DAILY_LOSS_WARN_FRACTION of its
#      capacity -- i.e. the grid is running a deficit and draining. On oil
#      and reactor grids it also flags solar as retirable once its share of
#      the day's generation is below SOLAR_RETIRE_SHARE.
#   2. Shedding: the solar night guard, or the emergency guard that sheds
#      DEFAULT_SHEDDING_TIERS only when the COMBINED reserve is nearly empty
#      and restores once it has recovered.
from archive import archive
from patterns import is_wildcard_pattern, filter_wildcard_matches
from tree_console import TreeConsole
from components import gas_tank
from swallow import swallowed
import fluid_routing
from turbine_commit import TurbineCommitment
from power_solar import SolarNightGuard
from game_clock import now_tick

# lib/production.py imports this. Decompiled simworker's dayCycleDuration.
DAY_CYCLE_DURATION_SECONDS = 600

# Shedding tiers, shed first to last (archive overrides:
# 'power.shedding_tiers' / 'power.shedding_tiers:<anchor>').
# - Tier 1: passive terraforming machinery and Fuel Assemblers. A Fuel
#   Assembler craft draws 1.2-1.8 kW just to build stock, and its progress
#   survives the breaker cut.
# - Tier 2: crafters, soft-shed only (SOFT_SHED_PATTERNS).
# - Tier 3: Habitats. An unpowered Habitat only pauses (no breeding, no rearing
#   progress, no failure; simworker skips unpowered Habitats), so they shed
#   last, below their own lower threshold.
# Vehicle Charging Stations are never shed: they also dispatch the fleet
# rescue drone (lib/charging.py manage_fleet_rescues()), and a shed station
# answers "station_offline" exactly when a stranded vehicle needs it.
DEFAULT_SHEDDING_TIERS = [
    [
        "heater_*",
        "pressure_*",
        "o2gen_*",
        "bio_collector_*",
        "bio_lab_*",
        "bio_exchange_*",
        "bio_luminizer_*",
        "fuel_assembler_*",
    ],
    [
        "smelter_*",
        "fabricator_*",
        "feed_maker_*",
        "refiner_*",
    ],
    [
        "habitat_*",
    ],
]
# Crafters draw power only while a craft runs (idle draw is 0 W), so cutting
# their breaker saves nothing that not starting new work doesn't, and needs
# outside help to power the machine back on and restart its script. They are
# only listed in power.shedded, which their controllers read to pause new
# production; set_powered() is never called on them.
SOFT_SHED_PATTERNS = {"smelter_*", "fabricator_*", "feed_maker_*", "refiner_*"}

# Power phase of a grid, from the generator types among its members.
SOLAR_TYPE_ID = "solar_generator"
STEAM_TURBINE_TYPE_ID = "steam_turbine"
OIL_GENERATOR_TYPE_ID = "oil_generator"
REACTOR_TYPE_ID = "reactor"
PHASE_SOLAR = "solar"
PHASE_STEAM = "steam"
PHASE_OIL = "oil"
PHASE_REACTOR = "reactor"

# On oil and reactor grids, a day whose solar output is below this share of
# the grid's generation notifies once that the solar panels can be retired.
SOLAR_RETIRE_SHARE = 0.05

# Steam Turbine: 108 W from 90 t/h (docs/components/steam_turbine.md).
STEAM_WH_PER_TON = 108.0 / 90.0

# Warn when a pool ends the day more than this fraction of its capacity
# lower than it started.
DAILY_LOSS_WARN_FRACTION = 0.20
DAILY_HISTORY_LENGTH = 7

# Emergency guard on the combined reserve fraction (battery + steam, in Wh).
# Tier N sheds below the Nth value (tiers past the list use the last one);
# everything restores once the reserve is back above RESTORE (hysteresis, so
# a grid hovering at the threshold does not toggle breakers every second).
EMERGENCY_SHED_FRACTIONS = (0.10, 0.05, 0.02)
EMERGENCY_RESTORE_FRACTION = 0.25


def tiers_to_shed(frac, tier_count):
    """How many leading tiers to shed at reserve fraction `frac`."""
    count = 0
    for t_idx in range(tier_count):
        if frac >= EMERGENCY_SHED_FRACTIONS[min(t_idx, len(EMERGENCY_SHED_FRACTIONS) - 1)]:
            break
        count += 1
    return count

# Today's running snapshot lives in memory; it is written to the archive on
# day rollover and every this many supervise_grid() calls (~30s), so a restart
# loses at most that much of the day's gen/con integral.
DAILY_STATE_PERSIST_INTERVAL_CALLS = 30

DAILY_STATE_KEY_PREFIX = "power.daily:"
DAILY_HISTORY_KEY_PREFIX = "power.daily_hist:"


def grid_phase(grid: "PowerGrid"):
    """PHASE_SOLAR / PHASE_STEAM / PHASE_OIL / PHASE_REACTOR for a power_control grid
    snapshot. A Reactor counts only while it produces: a tripped or unfuelled one
    leaves the grid to oil and steam."""
    types = set()
    for member in getattr(grid, "members", None) or []:
        type_id = getattr(member, "type_id", "")
        if type_id == REACTOR_TYPE_ID and (getattr(member, "generated", 0.0) or 0.0) <= 0:
            continue
        types.add(type_id)
    if REACTOR_TYPE_ID in types:
        return PHASE_REACTOR
    if OIL_GENERATOR_TYPE_ID in types:
        return PHASE_OIL
    if STEAM_TURBINE_TYPE_ID in types:
        return PHASE_STEAM
    return PHASE_SOLAR


def reactor_carried(grid: "PowerGrid"):
    """True while a producing Reactor is on grid: oil surplus burning is waste there."""
    return grid is not None and grid_phase(grid) == PHASE_REACTOR


def _member_generated(grid: "PowerGrid", type_id):
    return sum(getattr(m, "generated", 0.0) or 0.0 for m in (getattr(grid, "members", None) or []) if getattr(m, "type_id", "") == type_id)


def _notify(text, level="warn", duration=8.0):
    try:
        notify(text, level=level, duration_seconds=duration)
    except Exception as error:
        swallowed("power._notify: notify", error)


def steam_tanks():
    """Resolved steam Gas Tanks network-wide (one network per fluid, one grid):
    fluid_routing's shared network walk filtered by eligible_targets(), so a
    drained tank that unlatched at 0 still counts while tank_assignments
    reserves it for steam (dropping its capacity would hide the loss)."""
    tick = now_tick()
    tanks = fluid_routing.eligible_targets(fluid_routing.network_buildings("gas_tank", tick), "steam")
    if tanks is None:  # a walked tank stopped answering (removed): walk again
        fluid_routing.invalidate_network_walk("gas_tank")
        tanks = fluid_routing.eligible_targets(fluid_routing.network_buildings("gas_tank", tick), "steam")
    return tanks or []


def steam_pool(tank_ids=None):
    """(stored_t, capacity_t, tank_count) over the steam Gas Tanks: steam_tanks()
    when tank_ids is None, else the steam ones among tank_ids (same rule)."""
    if tank_ids is None:
        tanks = steam_tanks()
    else:
        tanks = []
        for tank_id in tank_ids:
            try:
                tank = gas_tank(tank_id)
            except Exception as error:
                swallowed("power.steam_pool: get_component", error)
                continue
            if tank is not None:
                tanks.append(tank)
        tanks = fluid_routing.eligible_targets(tanks, "steam") or []
    stored_t = 0.0
    capacity_t = 0.0
    for tank in tanks:
        try:
            stored_t += tank.level()
            capacity_t += tank.capacity()
        except Exception as error:
            swallowed("power.steam_pool: tank.level", error)
    return stored_t, capacity_t, len(tanks)


def measure_grid(grid: "PowerGrid", tank_ids=None):
    """Battery + steam snapshot of one grid, the shape reserve_fraction() reads.
    tank_ids None: every steam tank on the network (steam_tanks())."""
    bat_wh = getattr(grid, "stored", 0.0) + getattr(grid, "reserve_stored", 0.0)
    bat_cap = getattr(grid, "capacity", 0.0) + getattr(grid, "reserve_capacity", 0.0)
    steam_t, steam_cap, tanks = steam_pool(tank_ids)
    return {
        "bat_wh": round(bat_wh, 1),
        "bat_cap": round(bat_cap, 1),
        "steam_t": round(steam_t, 1),
        "steam_cap": round(steam_cap, 1),
        "tanks": tanks,
    }


def reserve_totals(now):
    """(total_wh, total_cap_wh) of the combined reserve in a _measure()-shaped
    dict: battery Wh plus banked steam converted at STEAM_WH_PER_TON."""
    total_wh = now["bat_wh"] + now["steam_t"] * STEAM_WH_PER_TON
    total_cap = now["bat_cap"] + now["steam_cap"] * STEAM_WH_PER_TON
    return total_wh, total_cap


def reserve_fraction(now):
    """Combined reserve fraction (0-1), or None when the grid has no battery
    or steam storage to measure. Shared by the emergency guard and
    lib/oil_generator.py so both read the same number."""
    total_wh, total_cap = reserve_totals(now)
    if total_cap <= 0:
        return None
    return total_wh / total_cap


class PowerGridManager:
    """Supervises one power grid: turbine commitment, daily reserve balance, and the
    shedding strategy of the grid's power phase."""

    def __init__(self, grid: "PowerGrid", clock: "Clock | None" = None, power: "PowerControl | None" = None):
        self.clock = clock or get_component("clock")
        self.power = power or get_component("power_control")
        self.log = TreeConsole(module="power")
        self.grid_anchor = getattr(grid, "anchor_id", None)
        self.shedded_machines = set()
        self.last_sample_hours = None
        self.day_state = None
        self.calls_since_persist = 0
        # Runs just enough Steam Turbines and parks the rest (lib/turbine_commit.py).
        self.turbines = TurbineCommitment(self.power)
        self.turbine_status = "no turbines"
        self.phase = None
        self.solar_guard = None  # SolarNightGuard, while the grid is in PHASE_SOLAR

        # A previous run may have left machines shed. Its in-memory set died
        # with the script, but it mirrored it to the archive -- adopt those so
        # the restore path releases them.
        adopted = set(archive.get(f"power.shedded:{self.grid_anchor}", []) or []) if self.grid_anchor else set()
        adopted |= set(archive.get("power.shedded", []) or [])
        self.adopted_machines = adopted
        if adopted:
            self.log.debug(f"[POWER] Adopting {len(adopted)} previously shed machine(s) for release check: {sorted(adopted)}.")

    # ------------------------------------------------------------------
    # Reserve measurement
    # ------------------------------------------------------------------
    def _measure(self, grid: "PowerGrid"):
        return measure_grid(grid)

    # ------------------------------------------------------------------
    # Daily balance
    # ------------------------------------------------------------------
    def _integrate(self, state, grid: "PowerGrid"):
        """Adds this sample's generated/consumed energy to today's totals."""
        hours = self.clock.elapsed_game_hours() if self.clock and hasattr(self.clock, "elapsed_game_hours") else None
        if hours is None:
            return
        if self.last_sample_hours is not None:
            dt = hours - self.last_sample_hours
            if 0 < dt < 2.0:
                state["gen_wh"] = round(state.get("gen_wh", 0.0) + getattr(grid, "generated", 0.0) * dt, 1)
                state["con_wh"] = round(state.get("con_wh", 0.0) + getattr(grid, "consumed", 0.0) * dt, 1)
                state["solar_wh"] = round(state.get("solar_wh", 0.0) + _member_generated(grid, SOLAR_TYPE_ID) * dt, 1)
        self.last_sample_hours = hours

    def _close_day(self, start, now, grid_id_str):
        """Records the finished day's balance and warns on a >20% drain."""
        self.log.start(f"[POWER] Closing day {start.get('day')} on '{grid_id_str}'")
        bat_delta = now["bat_wh"] - start.get("bat_wh", 0.0)
        steam_delta = now["steam_t"] - start.get("steam_t", 0.0)
        bat_cap = max(now["bat_cap"], start.get("bat_cap", 0.0))
        steam_cap = max(now["steam_cap"], start.get("steam_cap", 0.0))
        bat_frac = bat_delta / bat_cap if bat_cap > 0 else 0.0
        steam_frac = steam_delta / steam_cap if steam_cap > 0 else 0.0

        summary = {
            "day": start.get("day"),
            "bat_delta_wh": round(bat_delta, 1),
            "bat_delta_pct": round(bat_frac * 100, 1),
            "steam_delta_t": round(steam_delta, 1),
            "steam_delta_pct": round(steam_frac * 100, 1),
            "gen_wh": start.get("gen_wh", 0.0),
            "con_wh": start.get("con_wh", 0.0),
        }
        hist_key = f"{DAILY_HISTORY_KEY_PREFIX}{self.grid_anchor}"
        history = archive.get(hist_key, []) or []
        history.append(summary)
        archive.set(hist_key, history[-DAILY_HISTORY_LENGTH:])

        self.log.print(
            f"[POWER] Day {summary['day']} balance on '{grid_id_str}': battery {bat_delta:+.0f} Wh ({bat_frac*100:+.0f}%), "
            f"steam {steam_delta:+.0f} t ({steam_frac*100:+.0f}%), generated {summary['gen_wh']:.0f} Wh, consumed {summary['con_wh']:.0f} Wh."
        )

        draining = []
        if bat_frac < -DAILY_LOSS_WARN_FRACTION:
            draining.append(f"batteries {bat_frac*100:.0f}% ({bat_delta:+.0f} Wh)")
        if steam_frac < -DAILY_LOSS_WARN_FRACTION:
            draining.append(f"gas tanks {steam_frac*100:.0f}% ({steam_delta:+.0f} t steam)")
        if draining:
            msg = f"Grid '{grid_id_str}' is draining: {', '.join(draining)} over day {summary['day']}. Add generation or cut load."
            self.log.level("warn").print(f"[POWER ADVISORY] {msg}")
            _notify(f"[Power Advisory] {msg}")
        else:
            self.log.debug(f"[POWER] Day {summary['day']} on '{grid_id_str}': no pool lost more than {DAILY_LOSS_WARN_FRACTION*100:.0f}% of capacity; no advisory.")
        self._solar_retire_advisory(start, grid_id_str)
        self.log.end(f"[POWER] Day {summary['day']} closed on '{grid_id_str}' ({'draining' if draining else 'no advisory'})")

    def _solar_retire_advisory(self, day, grid_id_str):
        """Once per closed day on an oil or reactor grid: notify when solar made less than
        SOLAR_RETIRE_SHARE of the day's generation. Advisory only; nothing is sold."""
        if self.phase not in (PHASE_OIL, PHASE_REACTOR):
            return
        solar_wh = day.get("solar_wh", 0.0) or 0.0
        gen_wh = day.get("gen_wh", 0.0) or 0.0
        if solar_wh <= 0 or gen_wh <= 0 or solar_wh / gen_wh >= SOLAR_RETIRE_SHARE:
            return
        msg = (f"Solar made {solar_wh / gen_wh * 100:.1f}% of '{grid_id_str}' generation on day {day.get('day')} "
               f"({self.phase} phase). The solar panels can be retired to free building slots.")
        self.log.print(f"[POWER ADVISORY] {msg}")
        _notify(f"[Power Advisory] {msg}", level="info")

    def _track_day(self, grid: "PowerGrid", now, grid_id_str):
        self.log.start("[POWER] _track_day", level="debug")
        current_day = self.clock.get_day() if self.clock else 1
        key = f"{DAILY_STATE_KEY_PREFIX}{self.grid_anchor}"
        state = self.day_state
        if state is None:
            state = archive.get(key, None)  # resume mid-day after a restart

        day_changed = not isinstance(state, dict) or state.get("day") != current_day
        if day_changed:
            # Close only a directly preceding day. After a longer gap (script
            # stopped for days) the delta spans an unknown period, so a warning
            # from it would be misleading.
            if isinstance(state, dict) and state.get("day") == current_day - 1:
                self._close_day(state, now, grid_id_str)
            elif isinstance(state, dict):
                self.log.debug(f"Discarding stale day-{state.get('day')} snapshot on '{grid_id_str}' (now day {current_day}).")
            state = dict(now)
            state["day"] = current_day
            state["gen_wh"] = 0.0
            state["con_wh"] = 0.0
            self.log.debug(f"Day {current_day} start snapshot on '{grid_id_str}': battery {now['bat_wh']:.0f}/{now['bat_cap']:.0f} Wh, steam {now['steam_t']:.0f}/{now['steam_cap']:.0f} t ({now['tanks']} tank(s)).")

        self._integrate(state, grid)
        self.day_state = state
        self.calls_since_persist += 1
        if day_changed or self.calls_since_persist >= DAILY_STATE_PERSIST_INTERVAL_CALLS:
            self.calls_since_persist = 0
            archive.set(key, state)
        self.log.end()

    # ------------------------------------------------------------------
    # Emergency guard
    # ------------------------------------------------------------------
    def get_shedding_tiers(self):
        grid_key = f"power.shedding_tiers:{self.grid_anchor}" if self.grid_anchor else None
        tiers = archive.get(grid_key) if grid_key else None
        if not tiers:
            tiers = archive.get("power.shedding_tiers")
        if isinstance(tiers, list) and tiers and isinstance(tiers[0], list):
            return tiers
        return DEFAULT_SHEDDING_TIERS

    def _resolve(self, pattern, grid_machines):
        if not is_wildcard_pattern(pattern):
            return [pattern] if pattern in grid_machines else []
        return filter_wildcard_matches(pattern, grid_machines)

    def update_archive_shedded(self):
        shed_list = sorted(self.shedded_machines)
        archive.set("power.shedded", shed_list)
        if self.grid_anchor:
            archive.set(f"power.shedded:{self.grid_anchor}", shed_list)

    def _shed(self, m_id, soft, reason, grid_id_str):
        if m_id in self.shedded_machines:
            return False
        if soft:
            self.shedded_machines.add(m_id)
            self.log.level("warn").print(f"[POWER GUARD] Flagged {m_id} shedded on '{grid_id_str}' ({reason}) -- production paused, power stays on.")
            return True
        try:
            if self.power and self.power.can_power_off(m_id) and self.power.is_powered(m_id):
                if self.power.set_powered(m_id, False).status == "ok":
                    self.shedded_machines.add(m_id)
                    self.log.level("warn").print(f"[POWER GUARD] Shed {m_id} on '{grid_id_str}' ({reason}).")
                    return True
        except Exception as error:
            swallowed("power.PowerGridManager._shed: self.power.can_power_off", error)
        return False

    def _restore(self, m_id, soft):
        """True once m_id is no longer held shed by this manager."""
        if soft:
            return True
        try:
            if self.power and self.power.can_power_off(m_id) and not self.power.is_powered(m_id):
                return self.power.set_powered(m_id, True).status == "ok"
        except Exception as error:
            swallowed("power.PowerGridManager._restore: self.power.can_power_off", error)
            return False
        return True

    def shed_tiers(self, tiers, grid_machines, reason, grid_id_str):
        """Sheds every grid machine matching the patterns of `tiers` (a list of pattern
        lists). Returns the newly shed ids; the archive mirror is updated when any."""
        newly = []
        for patterns in tiers:
            for pattern in patterns:
                soft = pattern in SOFT_SHED_PATTERNS
                for m_id in self._resolve(pattern, grid_machines):
                    if self._shed(m_id, soft, reason, grid_id_str):
                        newly.append(m_id)
        if newly:
            self.update_archive_shedded()
        return newly

    def restore_tier(self, patterns, grid_machines, reason, grid_id_str):
        """Restores the shed grid machines matching `patterns`. Returns the restored ids."""
        restored = []
        for pattern in patterns:
            soft = pattern in SOFT_SHED_PATTERNS
            for m_id in self._resolve(pattern, grid_machines):
                if m_id in self.shedded_machines and self._restore(m_id, soft):
                    self.shedded_machines.discard(m_id)
                    restored.append(m_id)
                    self.log.print(f"[POWER GUARD] Restored {m_id} on '{grid_id_str}' ({reason}).")
        if restored:
            self.update_archive_shedded()
        return restored

    def release_all(self):
        """Grid vanished (merged into another) -- give back everything shed, and every turbine parked here."""
        self.turbines.release_all()
        for m_id in list(self.shedded_machines):
            soft = any(filter_wildcard_matches(p, [m_id]) for p in SOFT_SHED_PATTERNS)
            if self._restore(m_id, soft):
                self.shedded_machines.discard(m_id)
        self.update_archive_shedded()

    def _guard(self, now, grid_machines, grid_id_str):
        self.log.start("[POWER] _guard", level="debug")
        total_wh, total_cap = reserve_totals(now)
        frac = reserve_fraction(now)
        if frac is None:
            self.log.debug(f"Guard idle on '{grid_id_str}': no battery or steam storage to measure.")
            self.log.end()
            return
        tiers = self.get_shedding_tiers()

        shed_count = tiers_to_shed(frac, len(tiers))
        self.log.trace(
            f"[POWER] Guard '{grid_id_str}': reserve {total_wh:.0f}/{total_cap:.0f} Wh ({frac*100:.1f}%) "
            f"[battery {now['bat_wh']:.0f} Wh + steam {now['steam_t']:.0f} t x{STEAM_WH_PER_TON:.2f}] -> shed {shed_count}/{len(tiers)} tier(s)."
        )

        changed = False
        if shed_count:
            newly = self.shed_tiers(tiers[:shed_count], grid_machines, f"combined reserve {frac*100:.0f}%", grid_id_str)
            if newly:
                _notify(f"[Power Guard] Reserve on '{grid_id_str}' at {frac*100:.0f}% -- shed {len(newly)} load(s): {', '.join(newly)}", level="error")

        restore_ok = frac >= EMERGENCY_RESTORE_FRACTION
        pending = (self.shedded_machines | self.adopted_machines) if restore_ok else set()
        for m_id in sorted(pending):
            if m_id not in grid_machines and m_id not in self.shedded_machines:
                continue  # adopted id from another grid -- its own manager handles it
            soft = any(filter_wildcard_matches(p, [m_id]) for p in SOFT_SHED_PATTERNS)
            if self._restore(m_id, soft):
                self.adopted_machines.discard(m_id)
                if m_id in self.shedded_machines:
                    self.shedded_machines.discard(m_id)
                self.log.print(f"[POWER GUARD] Restored {m_id} on '{grid_id_str}' (reserve {frac*100:.0f}%).")
                changed = True
        if restore_ok and self.adopted_machines:
            # Whatever is left belongs to other grids; stop tracking it here.
            self.adopted_machines = set()
        if changed:
            self.update_archive_shedded()
        self.log.end()

    # ------------------------------------------------------------------
    def _update_phase(self, grid: "PowerGrid", elevation, grid_id_str):
        """Re-reads the grid's phase; logs a change and creates or drops the solar night guard."""
        phase = grid_phase(grid)
        if phase != self.phase:
            if self.phase is not None:
                self.log.print(f"[POWER] Grid '{grid_id_str}' phase {self.phase} -> {phase}.")
            self.phase = phase
        if phase == PHASE_SOLAR and self.solar_guard is None:
            self.solar_guard = SolarNightGuard(self, elevation or 0.0)
        elif phase != PHASE_SOLAR:
            self.solar_guard = None

    def supervise_grid(self, grid: "PowerGrid", elevation=None):
        """One supervision cycle. `elevation` (sun elevation) drives the solar night guard;
        the other phases ignore it."""
        if not grid:
            return
        self.grid_anchor = getattr(grid, "anchor_id", None) or self.grid_anchor
        grid_id_str = self.grid_anchor or "unknown_grid"
        grid_machines = set(getattr(grid, "machine_ids", None) or [])

        now = self._measure(grid)
        self.log.trace(
            f"[POWER] Grid '{grid_id_str}': gen={getattr(grid, 'generated', 0.0):.0f} W, con={getattr(grid, 'consumed', 0.0):.0f} W, "
            f"battery {now['bat_wh']:.0f}/{now['bat_cap']:.0f} Wh, steam {now['steam_t']:.0f}/{now['steam_cap']:.0f} t in {now['tanks']} tank(s)."
        )
        if now["bat_cap"] <= 0 and now["steam_cap"] <= 0:
            return

        self._update_phase(grid, elevation, grid_id_str)
        self._track_day(grid, now, grid_id_str)
        # Turbines first: running more of them is the answer before shedding any load.
        try:
            steam_fraction = now["steam_t"] / now["steam_cap"] if now["steam_cap"] > 0 else None
            self.turbine_status = self.turbines.step(grid, grid_id_str, steam_fraction)
        except Exception as error:
            swallowed("power.PowerGridManager.supervise_grid: self.turbines.step", error)
        if self.solar_guard is not None:
            self._adopt_into_shed(grid_machines)
            self.solar_guard.step(grid, elevation, grid_id_str, grid_machines)
        else:
            self._guard(now, grid_machines, grid_id_str)

    def _adopt_into_shed(self, grid_machines):
        """Hands adopted ids on this grid to shedded_machines, so the solar guard's
        restore paths release them (it has no adopted-id pass of its own)."""
        if not self.adopted_machines:
            return
        self.shedded_machines |= {m_id for m_id in self.adopted_machines if m_id in grid_machines}
        self.adopted_machines = set()
