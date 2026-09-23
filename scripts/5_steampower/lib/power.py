# Simplified Power Guard for multi-source grids (solar + Steam Turbines).
#
# Replaces 4_controlpanel's lib/power.py from this tier up. Same import
# surface (PowerGridManager with supervise_grid()/release_all(), and
# DAY_CYCLE_DURATION_SECONDS for lib/production.py), so panel_4.py drives it
# unchanged.
#
# Why a rewrite instead of a patch: the old manager modelled "night" as
# "sun elevation == 0" and "reserve" as "battery Wh" only. Once Steam
# Turbines carry most of the load that is wrong twice over -- night is not a
# dry spell while Gas Tanks still hold steam, and the real dry spell (vent
# dormancy) has nothing to do with the sun. It shed loads every night with
# thousands of tons of steam still banked.
#
# This version treats both stores as one energy reserve:
#   - Battery pool: grid.stored/.capacity plus Lightning Rod reserve.
#   - Steam pool:   every steam Gas Tank on the grid's outposts, converted to
#                   Wh at the Steam Turbine's own rate (108 W per 90 t/h).
# It does two things only:
#   1. Daily balance: snapshot both pools at each day rollover, record the
#      net gain/loss per day (bounded history), and notify() once per day
#      when either pool lost more than DAILY_LOSS_WARN_FRACTION of its
#      capacity -- i.e. the grid is running a deficit and draining.
#   2. Emergency guard: shed DEFAULT_SHEDDING_TIERS only when the COMBINED
#      reserve is nearly empty, restore once it has recovered. No day/night
#      logic, no forecasting.
from archive import archive
from patterns import is_wildcard_pattern, filter_wildcard_matches
from tree_console import TreeConsole

# lib/production.py imports this. Decompiled simworker's dayCycleDuration.
DAY_CYCLE_DURATION_SECONDS = 600

# Same tier lists and soft-shed rule as 4_controlpanel's lib/power.py -- see
# there for why Charging Stations are never shed and why Smelters/Fabricators
# are only flagged (they idle at 0 W anyway). Archive override keys
# 'power.shedding_tiers' / 'power.shedding_tiers:<anchor>' still apply.
DEFAULT_SHEDDING_TIERS = [
    [
        "heater_*",
        "pressure_*",
        "o2gen_*",
        "bio_collector_*",
        "bio_lab_*",
        "bio_exchange_*",
        "bio_luminizer_*",
    ],
    [
        "smelter_*",
        "fabricator_*",
    ],
]
SOFT_SHED_PATTERNS = {"smelter_*", "fabricator_*"}

# Steam Turbine: 108 W from 90 t/h (docs/components/steam_turbine.md).
STEAM_WH_PER_TON = 108.0 / 90.0

# Warn when a pool ends the day more than this fraction of its capacity
# lower than it started.
DAILY_LOSS_WARN_FRACTION = 0.20
DAILY_HISTORY_LENGTH = 7

# Emergency guard on the combined reserve fraction (battery + steam, in Wh).
# Tier 1 sheds below the first value, all tiers below the second; everything
# restores once the reserve is back above RESTORE (hysteresis, so a grid
# hovering at the threshold does not toggle breakers every second).
EMERGENCY_SHED_TIER1_FRACTION = 0.10
EMERGENCY_SHED_ALL_FRACTION = 0.05
EMERGENCY_RESTORE_FRACTION = 0.25

# Gas Tanks normally appear in grid.members (buildings at a connected outpost
# are members with an empty roles list). The outpost walk below is only a
# fallback for when they do not; throttle it, in supervise_grid() calls
# (~1s each from panel_4.py).
TANK_FALLBACK_SCAN_INTERVAL_CALLS = 60

# Today's running snapshot lives in memory; it is written to the archive on
# day rollover and every this many supervise_grid() calls (~30s), so a restart
# loses at most that much of the day's gen/con integral.
DAILY_STATE_PERSIST_INTERVAL_CALLS = 30

DAILY_STATE_KEY_PREFIX = "power.daily:"
DAILY_HISTORY_KEY_PREFIX = "power.daily_hist:"


def _notify(text, level="warn", duration=8.0):
    try:
        notify(text, level=level, duration_seconds=duration)
    except Exception:
        pass


def steam_pool(tank_ids):
    """(stored_t, capacity_t, tank_count) over the steam Gas Tanks among
    tank_ids. An unlatched (empty) tank counts only when fluid_routing's
    tank_assignments reserves it for steam -- a drained steam tank unlatches
    at 0, and dropping its capacity would hide the loss."""
    assignments = archive.get("fluid_routing.tank_assignments", {}) or {}
    stored_t = 0.0
    capacity_t = 0.0
    count = 0
    for tank_id in tank_ids:
        try:
            tank = get_component(tank_id)
            if tank is None:
                continue
            fluid = tank.fluid()
            if fluid != "steam" and not (fluid == "" and assignments.get(tank_id) == "steam"):
                continue
            stored_t += tank.level()
            capacity_t += tank.capacity()
            count += 1
        except Exception:
            pass
    return stored_t, capacity_t, count


def grid_steam_tank_ids(grid):
    """Gas Tank ids listed in grid.members (buildings at a connected outpost
    are members with an empty roles list). PowerGridManager adds a throttled
    outpost-walk fallback on top of this for grids where they are missing."""
    return [m.id for m in (getattr(grid, "members", None) or []) if getattr(m, "type_id", "") == "gas_tank"]


def measure_grid(grid, tank_ids):
    """Battery + steam snapshot of one grid, the shape reserve_fraction() reads."""
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
    """Supervises one power grid: daily reserve balance + emergency shedding."""

    def __init__(self, grid, clock=None, power=None):
        self.clock = clock or get_component("clock")
        self.power = power or get_component("power_control")
        self.log = TreeConsole(module="power")
        self.grid_anchor = getattr(grid, "anchor_id", None)
        self.shedded_machines = set()
        self.last_sample_hours = None
        self.fallback_tank_ids = []
        self.calls_since_tank_scan = TANK_FALLBACK_SCAN_INTERVAL_CALLS
        self.day_state = None
        self.calls_since_persist = 0

        # The old manager may have left machines shed (it sheds at night by
        # battery alone). Its in-memory set died with the script, but it
        # mirrored it to the archive -- adopt those so the emergency guard's
        # restore path releases them on the first supervise_grid() call.
        adopted = set(archive.get(f"power.shedded:{self.grid_anchor}", []) or []) if self.grid_anchor else set()
        adopted |= set(archive.get("power.shedded", []) or [])
        self.adopted_machines = adopted
        if adopted:
            self.log.debug(f"[POWER] Adopting {len(adopted)} previously shed machine(s) for release check: {sorted(adopted)}.")

    # ------------------------------------------------------------------
    # Reserve measurement
    # ------------------------------------------------------------------
    def _steam_tank_ids(self, grid):
        ids = grid_steam_tank_ids(grid)
        if ids:
            return ids

        self.calls_since_tank_scan += 1
        if self.calls_since_tank_scan >= TANK_FALLBACK_SCAN_INTERVAL_CALLS:
            self.calls_since_tank_scan = 0
            outpost_ids = set(getattr(grid, "outpost_ids", None) or [])
            found = []
            for outpost_id in outpost_ids:
                try:
                    outpost = get_component(outpost_id)
                    for ref in outpost.buildings("gas_tank") if outpost else []:
                        found.append(ref.id)
                except Exception:
                    pass
            self.fallback_tank_ids = found
            self.log.debug(f"[POWER] Gas Tanks not in grid members for '{self.grid_anchor}'; outpost walk over {len(outpost_ids)} outpost(s) found {len(found)}.")
        return self.fallback_tank_ids

    def _measure(self, grid):
        return measure_grid(grid, self._steam_tank_ids(grid))

    # ------------------------------------------------------------------
    # Daily balance
    # ------------------------------------------------------------------
    def _integrate(self, state, grid):
        """Adds this sample's generated/consumed energy to today's totals."""
        hours = self.clock.elapsed_game_hours() if self.clock and hasattr(self.clock, "elapsed_game_hours") else None
        if hours is None:
            return
        if self.last_sample_hours is not None:
            dt = hours - self.last_sample_hours
            if 0 < dt < 2.0:
                state["gen_wh"] = round(state.get("gen_wh", 0.0) + getattr(grid, "generated", 0.0) * dt, 1)
                state["con_wh"] = round(state.get("con_wh", 0.0) + getattr(grid, "consumed", 0.0) * dt, 1)
        self.last_sample_hours = hours

    def _close_day(self, start, now, grid_id_str):
        """Records the finished day's balance and warns on a >20% drain."""
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

    def _track_day(self, grid, now, grid_id_str):
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
                self.log.debug(f"[POWER] Discarding stale day-{state.get('day')} snapshot on '{grid_id_str}' (now day {current_day}).")
            state = dict(now)
            state["day"] = current_day
            state["gen_wh"] = 0.0
            state["con_wh"] = 0.0
            self.log.debug(f"[POWER] Day {current_day} start snapshot on '{grid_id_str}': battery {now['bat_wh']:.0f}/{now['bat_cap']:.0f} Wh, steam {now['steam_t']:.0f}/{now['steam_cap']:.0f} t ({now['tanks']} tank(s)).")

        self._integrate(state, grid)
        self.day_state = state
        self.calls_since_persist += 1
        if day_changed or self.calls_since_persist >= DAILY_STATE_PERSIST_INTERVAL_CALLS:
            self.calls_since_persist = 0
            archive.set(key, state)

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
        except Exception:
            pass
        return False

    def _restore(self, m_id, soft):
        """True once m_id is no longer held shed by this manager."""
        if soft:
            return True
        try:
            if self.power and self.power.can_power_off(m_id) and not self.power.is_powered(m_id):
                return self.power.set_powered(m_id, True).status == "ok"
        except Exception:
            return False
        return True

    def release_all(self):
        """Grid vanished (merged into another) -- give back everything shed."""
        for m_id in list(self.shedded_machines):
            soft = any(filter_wildcard_matches(p, [m_id]) for p in SOFT_SHED_PATTERNS)
            if self._restore(m_id, soft):
                self.shedded_machines.discard(m_id)
        self.update_archive_shedded()

    def _guard(self, now, grid_machines, grid_id_str):
        total_wh, total_cap = reserve_totals(now)
        frac = reserve_fraction(now)
        if frac is None:
            self.log.debug(f"[POWER] Guard idle on '{grid_id_str}': no battery or steam storage to measure.")
            return
        tiers = self.get_shedding_tiers()

        if frac < EMERGENCY_SHED_ALL_FRACTION:
            tiers_to_shed = len(tiers)
        elif frac < EMERGENCY_SHED_TIER1_FRACTION:
            tiers_to_shed = 1
        else:
            tiers_to_shed = 0
        self.log.debug(
            f"[POWER] Guard '{grid_id_str}': reserve {total_wh:.0f}/{total_cap:.0f} Wh ({frac*100:.1f}%) "
            f"[battery {now['bat_wh']:.0f} Wh + steam {now['steam_t']:.0f} t x{STEAM_WH_PER_TON:.2f}] -> shed {tiers_to_shed}/{len(tiers)} tier(s)."
        )

        changed = False
        if tiers_to_shed:
            reason = f"combined reserve {frac*100:.0f}%"
            newly = []
            for t_idx in range(tiers_to_shed):
                for pattern in tiers[t_idx]:
                    soft = pattern in SOFT_SHED_PATTERNS
                    for m_id in self._resolve(pattern, grid_machines):
                        if self._shed(m_id, soft, reason, grid_id_str):
                            newly.append(m_id)
            if newly:
                changed = True
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

    # ------------------------------------------------------------------
    def supervise_grid(self, grid, elevation=None):
        """One supervision cycle. `elevation` is accepted for panel_4.py's
        call signature and ignored -- sun position no longer matters here."""
        if not grid:
            return
        self.grid_anchor = getattr(grid, "anchor_id", None) or self.grid_anchor
        grid_id_str = self.grid_anchor or "unknown_grid"
        grid_machines = set(getattr(grid, "machine_ids", None) or [])

        now = self._measure(grid)
        self.log.debug(
            f"[POWER] Grid '{grid_id_str}': gen={getattr(grid, 'generated', 0.0):.0f} W, con={getattr(grid, 'consumed', 0.0):.0f} W, "
            f"battery {now['bat_wh']:.0f}/{now['bat_cap']:.0f} Wh, steam {now['steam_t']:.0f}/{now['steam_cap']:.0f} t in {now['tanks']} tank(s)."
        )
        if now["bat_cap"] <= 0 and now["steam_cap"] <= 0:
            return

        self._track_day(grid, now, grid_id_str)
        self._guard(now, grid_machines, grid_id_str)
