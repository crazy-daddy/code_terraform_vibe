# Shared Library for Central Power Grid Management & Automated Load Shedding
# Generic master controller that can oversee any power grid (solar, oil, reactor, turbine).
from archive import archive
from patterns import is_wildcard_pattern, filter_wildcard_matches
from tree_console import TreeConsole

# Default shedding tiers (configurable via archive key 'power.shedding_tiers')
# Tier 1: Passive background terraforming machinery (shed first)
# Tier 2: Critical active production & logistics (shed only under severe deficit)
#
# Vehicle Charging Stations are deliberately never included here: they're also
# what dispatches the fleet rescue drone (lib/charging.py manage_fleet_rescues()).
# Shedding them "only under severe deficit" means losing rescue capability at
# exactly the moment a vehicle is most likely to be stranded and need it --
# dispatch_rescue() returns "station_offline" and the drone never launches.
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

# Patterns that are tracked as shedded (added to power.shedded / the archive's
# per-grid mirror) but never actually powered off. A Smelter/Fabricator only
# draws its recipe's power_draw while a craft is actively running -- idle draw
# is already 0 W (see lib/smelter.py's SmelterController docstring) -- so
# cutting its breaker saves nothing it wasn't already going to save by simply
# not starting new work, while ALSO losing leader-election status (the
# "inventory manager" sweep) and needing external intervention to power it
# back on and restart its script -- deliberately NOT automated (see
# lib/vehicle_cargo.py's module docstring): if the operator stopped it
# themselves, nothing should override that just because a delivery arrived.
# Soft-shed instead: still listed in power.shedded so
# SmelterController/FabricatorController's own step() can see it and pause
# starting/topping-up production, but set_powered() is never called on it.
# Only smelter_*/fabricator_* are soft-shed -- a Tier 1 pattern
# like heater_*/pressure_* draws power continuously regardless of whether it's
# "producing" anything, so cutting its breaker is the only way to actually
# reduce its draw.
SOFT_SHED_PATTERNS = {"smelter_*", "fabricator_*"}

# Exact day/night cycle timings from the decompiled simworker (its
# `dayCycleDuration: 600` / `daylight: {...}` schedule, fractions of a full
# day mapped onto elapsed_game_hours()'s 0-24 scale by multiplying by 24).
# Replaces the old empirically-calibrated `power.night_duration` archive value
# (measured sunset->sunrise gap, EMA-smoothed) with the fixed real schedule --
# the sun always sets/rises at the same hour every day, so there was never
# anything to calibrate; the old approach only ever drifted toward this same
# constant while being wrong immediately after every script restart. See
# docs/AI_CHEATSHEET.md.
DAY_CYCLE_DURATION_SECONDS = 600
DAYLIGHT_FRACTIONS = {
    "dawn_start": 0.25,
    "dawn_end": 0.30,
    "morning_peak_start": 0.38,
    "peak_end": 0.54,
    "afternoon_end": 0.71,
    "day_end": 0.75,
    "dusk_end": 0.83,
}
SUNRISE_HOUR = DAYLIGHT_FRACTIONS["dawn_start"] * 24.0  # 6.0 -- sun elevation goes > 0
SUNSET_HOUR = DAYLIGHT_FRACTIONS["dusk_end"] * 24.0  # 19.92 -- sun elevation returns to 0
NIGHT_DURATION_HOURS = 24.0 - SUNSET_HOUR + SUNRISE_HOUR  # 10.08, exact and constant


class PowerGridManager:
    """
    Supervises a single power grid -- one instance per grid, owned centrally by
    panel_1.py's AUTOMATION section (see docs/AI_CHEATSHEET.md) rather than by
    any individual generator, so there's no Master/Follower election needed:
    - Monitors generation, consumption, and battery storage directly via PowerGrid snapshot.
    - Calibrates day/night cycles and historical overnight energy usage.
    - Issues predictive battery and generation advisories at sunset and during nighttime deficits.
    - Manages progressive multi-tier load shedding under deficit conditions.
    - Restores shedded machinery progressively when battery/surplus recovers.
    """

    def __init__(self, grid, clock=None, power=None):
        self.clock = clock or get_component("clock")
        self.power = power or get_component("power_control")
        self.log = TreeConsole(module="power")

        # Identity is bound once, from the grid snapshot this manager was
        # created for -- not left None until the first supervise_grid() call
        # sets it as a side effect (this manager is 1:1 with one grid for its
        # entire lifetime; the caller re-passes a fresh snapshot each call
        # only because PowerGrid readings are point-in-time, not because the
        # grid identity itself is expected to change).
        self.grid_anchor = getattr(grid, "anchor_id", None)
        self.shedded_machines = set()

        # Day/Night cycle tracking
        self.last_elevation = self.clock.get_elevation() if self.clock else 0.0
        self.has_observed_day = (self.last_elevation > 0)
        self.night_duration = NIGHT_DURATION_HOURS
        self.sunset_hour = archive.get("power.sunset_hour", None)
        self.peak_day_battery_wh = 0.0
        self.last_advisory_day = self.clock.get_day() if self.clock else 1
        self.last_night_battery_advisory_day = None

        # Overnight energy accounting
        self.historical_night_wh = archive.get("power.night_wh", None)
        self.night_wh_accumulated = 0.0
        self.last_energy_sample_hour = None

    def release_all(self):
        """
        Call when this manager's grid has stopped being reported by
        power_control.grids() entirely (two grids merged into one via a new
        power line, orphaning one of the two old anchor_ids). The caller is
        about to drop this manager -- without this, anything still recorded
        in shedded_machines would be stranded shed forever, since the merged
        grid's own manager starts fresh with an empty shedded_machines and has
        no way to know about it.
        """
        for m_id in list(self.shedded_machines):
            try:
                if self.power and self.power.can_power_off(m_id) and not self.power.is_powered(m_id):
                    self.power.set_powered(m_id, True)
            except Exception:
                pass
            self.shedded_machines.discard(m_id)
        self.update_archive_shedded()

    def get_shedding_tiers(self):
        """
        Retrieves shedding tiers list-of-lists from archive ('power.shedding_tiers').
        Supports per-grid override ('power.shedding_tiers:<grid_anchor>').
        Falls back to DEFAULT_SHEDDING_TIERS.
        """
        grid_key = f"power.shedding_tiers:{self.grid_anchor}" if self.grid_anchor else None
        tiers = archive.get(grid_key) if grid_key else None
        if not tiers:
            tiers = archive.get("power.shedding_tiers")
        if isinstance(tiers, list) and len(tiers) > 0 and isinstance(tiers[0], list):
            return tiers
        return DEFAULT_SHEDDING_TIERS

    def resolve_pattern_machines(self, pattern, grid_machines):
        """
        Resolves a machine identifier or wildcard pattern (e.g. 'smelter_*') into machine IDs.
        Matches against machines connected to this power grid via regex.
        Falls back to a numbered-guess component lookup if grid_machines is not populated -- this manager
        has no single "owning" machine/outpost of its own to fall back through first (it's centrally owned,
        one instance per grid, not tied to any one generator), so grid_machines (the grid snapshot's own
        machine_ids/members, always populated for a real grid) is the only real source; this is a last resort.
        """
        if not is_wildcard_pattern(pattern):
            return [pattern]

        candidates = set(grid_machines) if grid_machines is not None else set()
        if not candidates:
            prefix = pattern.split("*")[0]
            for i in range(1, 9):
                cand = f"{prefix}{i}"
                try:
                    if get_component(cand) is not None:
                        candidates.add(cand)
                except Exception:
                    pass

        return filter_wildcard_matches(pattern, candidates)

    def update_archive_shedded(self):
        """Publishes currently shedded machines to the Data Archive for inter-process
        coordination -- e.g. a soft-shed SmelterController/FabricatorController
        (SOFT_SHED_PATTERNS above) checking it each step() to pause starting new
        production. ("power.shedded_machines" used to also be
        written here as a duplicate of "power.shedded" -- nothing ever read it; retired,
        see ArchiveCleaner.clean_power_grid_state())."""
        shed_list = sorted(list(self.shedded_machines))
        archive.set("power.shedded", shed_list)
        if self.grid_anchor:
            archive.set(f"power.shedded:{self.grid_anchor}", shed_list)

    def handle_sunset(self, current_day, current_hour, grid_id_str, capacity_wh, consumed_w):
        """Handles sunset detection, night duration calibration, and daytime capacity advisories."""
        self.sunset_hour = current_hour
        self.night_wh_accumulated = 0.0
        self.last_energy_sample_hour = current_hour
        archive.set("power.sunset_hour", self.sunset_hour)
        self.log.print(f"[POWER] Sunset detected on '{grid_id_str}' at day {current_day} (hour {current_hour:.1f}). Night mode active.")
        self.log.debug(f"[POWER] Sunset calibration on '{grid_id_str}': elevation crossed 0 at hour {current_hour:.2f} (fixed sunset hour is {SUNSET_HOUR:.2f}); capacity={capacity_wh:.0f} Wh, consumed={consumed_w:.0f} W.")

        if self.has_observed_day and current_day != self.last_advisory_day:
            self.last_advisory_day = current_day

            hist_key = f"power.night_wh:{self.grid_anchor}" if self.grid_anchor else "power.night_wh"
            hist_wh = archive.get(hist_key, archive.get("power.night_wh", None))
            if hist_wh is not None and hist_wh > 50.0:
                baseline_wh = hist_wh * 1.05
                self.log.debug(f"[POWER] Baseline night draw for '{grid_id_str}' derived from history: {hist_wh:.0f} Wh x1.05 = {baseline_wh:.0f} Wh.")
            else:
                baseline_wh = max(consumed_w, 25.0) * self.night_duration
                self.log.debug(f"[POWER] No usable history for '{grid_id_str}' (hist_wh={hist_wh}); baseline night draw estimated from current consumption: max({consumed_w:.0f}, 25.0) x {self.night_duration:.2f}h = {baseline_wh:.0f} Wh.")

            if capacity_wh < baseline_wh:
                shortfall = baseline_wh - capacity_wh
                bats_needed = int(shortfall // 500) + 1
                hist_tag = f" (Historical night: {hist_wh:.0f} Wh)" if hist_wh else ""
                msg = f"Battery capacity ({capacity_wh:.0f} Wh) on '{grid_id_str}' insufficient for night loads ({baseline_wh:.0f} Wh needed{hist_tag}). Recommend {bats_needed}x Battery at Shop."
                self.log.level("warn").print(f"[POWER ADVISORY] {msg}")
                try:
                    notify(f"[Power Advisory - {grid_id_str}] {msg}", level="warn", duration_seconds=8.0)
                except Exception:
                    pass

            if capacity_wh > 0 and self.peak_day_battery_wh < (capacity_wh * 0.90):
                charge_pct = (self.peak_day_battery_wh / capacity_wh) * 100
                msg = f"Solar generation deficit on '{grid_id_str}'! Batteries only reached {charge_pct:.0f}% charge. Recommend 1x Solar Generator (500 cr) at Shop."
                self.log.level("warn").print(f"[POWER ADVISORY] {msg}")
                try:
                    notify(f"[Power Advisory - {grid_id_str}] {msg}", level="warn", duration_seconds=8.0)
                except Exception:
                    pass

    def handle_sunrise(self, current_hour, grid_id_str):
        """Handles sunrise detection and historical overnight energy averaging.
        Night duration itself is fixed (NIGHT_DURATION_HOURS) -- nothing to
        calibrate here any more, just the actual Wh consumed overnight."""
        if self.sunset_hour is not None and self.night_wh_accumulated > 10.0:
            hist_key = f"power.night_wh:{self.grid_anchor}" if self.grid_anchor else "power.night_wh"
            curr_hist = archive.get(hist_key, None)
            if curr_hist is not None:
                new_hist = (curr_hist * 0.70) + (self.night_wh_accumulated * 0.30)
                self.log.debug(f"[POWER] Night-Wh EMA update for '{grid_id_str}': (prev {curr_hist:.0f} x0.70) + (observed {self.night_wh_accumulated:.0f} x0.30) = {new_hist:.0f} Wh.")
            else:
                new_hist = self.night_wh_accumulated
                self.log.debug(f"[POWER] First night-Wh sample for '{grid_id_str}': seeding history at {new_hist:.0f} Wh.")
            self.historical_night_wh = new_hist
            archive.set(hist_key, round(new_hist, 1))

        hist_str = f", {self.night_wh_accumulated:.0f} Wh used overnight" if self.night_wh_accumulated > 0 else ""
        self.log.print(f"[POWER] Sunrise detected on '{grid_id_str}'. Night lasted {self.night_duration:.1f} game hours (fixed schedule){hist_str}.")

        self.peak_day_battery_wh = 0.0
        self.has_observed_day = True
        self.night_wh_accumulated = 0.0
        self.last_energy_sample_hour = None

    def manage_night_loads(self, current_day, current_hour, grid_id_str, grid_machines, stored_wh, capacity_wh, consumed_w):
        """Calculates night energy endurance and sheds loads as required."""
        if self.last_energy_sample_hour is not None and current_hour > self.last_energy_sample_hour:
            dt = current_hour - self.last_energy_sample_hour
            if dt < 2.0:
                self.night_wh_accumulated += consumed_w * dt
        self.last_energy_sample_hour = current_hour

        if self.sunset_hour is not None:
            hours_into_night = max(0.0, current_hour - self.sunset_hour)
            remaining_night = max(0.5, self.night_duration - hours_into_night)
        else:
            remaining_night = self.night_duration / 2.0

        instant_rate = consumed_w
        hist_key = f"power.night_wh:{self.grid_anchor}" if self.grid_anchor else "power.night_wh"
        grid_hist_wh = archive.get(hist_key, self.historical_night_wh)
        if grid_hist_wh is not None and self.night_duration > 0:
            hist_rate = grid_hist_wh / self.night_duration
            effective_rate = (instant_rate * 0.60) + (hist_rate * 0.40)
        else:
            effective_rate = instant_rate

        wh_needed = effective_rate * remaining_night * 1.15
        battery_pct = (stored_wh / capacity_wh) if capacity_wh > 0 else 0.0

        deficit_detected = (stored_wh < wh_needed)
        emergency_low = (battery_pct < 0.20)
        severe_deficit = (stored_wh < (wh_needed * 0.50)) or (battery_pct < 0.15)

        tiers = self.get_shedding_tiers()
        num_tiers = len(tiers)

        tier_to_shed = 0
        if severe_deficit or battery_pct < 0.15:
            tier_to_shed = num_tiers
        elif deficit_detected or emergency_low:
            tier_to_shed = 1 if num_tiers == 1 else max(1, num_tiers - 1)

        self.log.debug(
            f"[POWER] Night eval '{grid_id_str}': stored={stored_wh:.0f} Wh ({battery_pct*100:.0f}%), "
            f"capacity={capacity_wh:.0f} Wh, instant_rate={instant_rate:.0f} W, effective_rate={effective_rate:.0f} W "
            f"(hist_rate={'n/a' if grid_hist_wh is None else f'{grid_hist_wh / self.night_duration:.0f} W'}), "
            f"remaining_night={remaining_night:.2f}h, wh_needed={wh_needed:.0f} Wh -> "
            f"deficit={deficit_detected}, emergency_low={emergency_low}, severe_deficit={severe_deficit}, "
            f"tier_to_shed={tier_to_shed}/{num_tiers}."
        )

        if tier_to_shed > 0:
            if self.last_night_battery_advisory_day != current_day:
                self.last_night_battery_advisory_day = current_day
                shortfall = wh_needed - stored_wh
                bats_needed = max(1, int(shortfall // 500) + 1)
                adv_msg = f"Night deficit on '{grid_id_str}'! Stored energy ({stored_wh:.0f} Wh) cannot survive remaining night ({wh_needed:.0f} Wh needed, {remaining_night:.1f}h left). Recommend {bats_needed}x Battery at Shop."
                self.log.level("warn").print(f"[BATTERY ADVISORY] {adv_msg}")
                try:
                    notify(f"[Battery Advisory - {grid_id_str}] {adv_msg}", level="warn", duration_seconds=10.0)
                except Exception:
                    pass

            shed_changed = False
            for t_idx in range(tier_to_shed):
                t_num = t_idx + 1
                patterns = tiers[t_idx]
                is_critical_tier = (t_num == num_tiers and num_tiers > 1)
                for pattern in patterns:
                    soft = pattern in SOFT_SHED_PATTERNS
                    target_ids = self.resolve_pattern_machines(pattern, grid_machines)
                    for m_id in target_ids:
                        if grid_machines is not None and m_id not in grid_machines:
                            continue

                        if soft:
                            # Never touches the breaker -- just flags m_id as
                            # shedded so its own controller pauses starting
                            # new production (see SOFT_SHED_PATTERNS above).
                            if m_id not in self.shedded_machines:
                                self.shedded_machines.add(m_id)
                                shed_changed = True
                                self.log.print(f"[POWER GUARD] Marked {m_id} shedded (Tier {t_num}) on '{grid_id_str}' -- production paused, power stays on.")
                            else:
                                self.log.debug(f"[POWER GUARD] {m_id} (Tier {t_num}, soft-shed) already flagged shedded on '{grid_id_str}'; skipping.")
                            continue

                        if m_id in self.shedded_machines:
                            self.log.debug(f"[POWER GUARD] {m_id} (Tier {t_num}, hard-shed) already shedded on '{grid_id_str}'; skipping breaker toggle.")
                            continue

                        try:
                            if self.power and self.power.can_power_off(m_id) and self.power.is_powered(m_id):
                                res = self.power.set_powered(m_id, False)
                                if res.status == "ok":
                                    self.shedded_machines.add(m_id)
                                    shed_changed = True
                                    if is_critical_tier:
                                        reason = f"Critical power deficit ({stored_wh:.0f} Wh, {battery_pct*100:.0f}% battery)"
                                        self.log.level("error").print(f"[POWER GUARD] Shed Tier {t_num} load ({m_id}) on '{grid_id_str}'. Reason: {reason}.")
                                        try:
                                            notify(f"[Power Guard CRITICAL] Shed load ({m_id}) on {grid_id_str}: {reason}", level="error", duration_seconds=8.0)
                                        except Exception:
                                            pass
                                    else:
                                        reason = "Emergency reserve guard (<20%)" if emergency_low else f"Insufficient storage ({stored_wh:.1f} Wh < {wh_needed:.1f} Wh needed)"
                                        self.log.level("warn").print(f"[POWER GUARD] Shed Tier {t_num} load ({m_id}) on '{grid_id_str}'. Reason: {reason}.")
                                        try:
                                            notify(f"[Power Guard] Shed load ({m_id}) on {grid_id_str}: {reason}", level="warn", duration_seconds=6.0)
                                        except Exception:
                                            pass
                        except Exception:
                            pass

            if shed_changed:
                self.update_archive_shedded()

        # Nighttime partial recovery if battery stabilizes above requirement + safety margin
        if self.shedded_machines and stored_wh >= (wh_needed * 1.10) and battery_pct >= 0.30:
            recovered_any = False
            for t_idx in reversed(range(num_tiers)):
                t_num = t_idx + 1
                margin = 1.10 + ((num_tiers - t_num) * 0.15)
                min_bat = 0.30 + ((num_tiers - t_num) * 0.10)
                if stored_wh < (wh_needed * margin) or battery_pct < min_bat:
                    continue
                patterns = tiers[t_idx]
                for pattern in patterns:
                    soft = pattern in SOFT_SHED_PATTERNS
                    target_ids = self.resolve_pattern_machines(pattern, grid_machines)
                    for m_id in target_ids:
                        if m_id in self.shedded_machines:
                            if grid_machines is not None and m_id not in grid_machines:
                                continue
                            if soft:
                                self.shedded_machines.discard(m_id)
                                recovered_any = True
                                self.log.print(f"[POWER GUARD] Cleared shed flag on {m_id} (Tier {t_num}) on '{grid_id_str}' — battery pool recovered ({stored_wh:.0f} Wh), resuming production.")
                                continue
                            try:
                                if self.power and self.power.can_power_off(m_id) and not self.power.is_powered(m_id):
                                    res = self.power.set_powered(m_id, True)
                                    if res.status == "ok":
                                        self.shedded_machines.discard(m_id)
                                        recovered_any = True
                                        self.log.print(f"[POWER GUARD] Restored {m_id} (Tier {t_num}) on '{grid_id_str}' — battery pool recovered ({stored_wh:.0f} Wh).")
                            except Exception:
                                pass
            if recovered_any:
                self.update_archive_shedded()

    def manage_day_recovery(self, grid_id_str, grid_machines, generated_w, consumed_w, stored_wh):
        """Restores shedded machinery progressively when surplus solar/generation is available."""
        if not (self.shedded_machines and generated_w > (consumed_w + 10.0) and stored_wh > 25.0):
            if self.shedded_machines:
                self.log.debug(f"[POWER] Day recovery skipped for '{grid_id_str}': generated={generated_w:.0f} W, consumed={consumed_w:.0f} W, stored={stored_wh:.0f} Wh -- surplus/reserve threshold not yet met for {len(self.shedded_machines)} shedded machine(s).")
            return

        tiers = self.get_shedding_tiers()
        num_tiers = len(tiers)
        recovered_any = False
        for t_idx in reversed(range(num_tiers)):
            t_num = t_idx + 1
            gen_surplus_needed = 10.0 + ((num_tiers - t_num) * 5.0)
            stored_needed = 25.0 + ((num_tiers - t_num) * 25.0)
            if generated_w < (consumed_w + gen_surplus_needed) or stored_wh < stored_needed:
                self.log.debug(f"[POWER] Day recovery: Tier {t_num}/{num_tiers} on '{grid_id_str}' not yet eligible (need gen>={consumed_w + gen_surplus_needed:.0f} W [have {generated_w:.0f}], stored>={stored_needed:.0f} Wh [have {stored_wh:.0f}]).")
                continue
            self.log.debug(f"[POWER] Day recovery: Tier {t_num}/{num_tiers} on '{grid_id_str}' eligible for restoration (gen={generated_w:.0f} W >= {consumed_w + gen_surplus_needed:.0f} W, stored={stored_wh:.0f} Wh >= {stored_needed:.0f} Wh).")
            patterns = tiers[t_idx]
            for pattern in patterns:
                soft = pattern in SOFT_SHED_PATTERNS
                target_ids = self.resolve_pattern_machines(pattern, grid_machines)
                for m_id in target_ids:
                    if m_id in self.shedded_machines:
                        if grid_machines is not None and m_id not in grid_machines:
                            continue
                        if soft:
                            self.shedded_machines.discard(m_id)
                            recovered_any = True
                            self.log.print(f"[POWER GUARD] Cleared shed flag on {m_id} (Tier {t_num}) on '{grid_id_str}' — solar surplus active, resuming production.")
                            continue
                        try:
                            if self.power and self.power.can_power_off(m_id) and not self.power.is_powered(m_id):
                                res = self.power.set_powered(m_id, True)
                                if res.status == "ok":
                                    self.shedded_machines.discard(m_id)
                                    recovered_any = True
                                    self.log.print(f"[POWER GUARD] Restored {m_id} (Tier {t_num}) on '{grid_id_str}' — solar surplus active ({generated_w:.0f} W gen vs {consumed_w:.0f} W con).")
                        except Exception:
                            pass
        if recovered_any:
            self.update_archive_shedded()

    def supervise_grid(self, grid, elevation):
        """Core supervision cycle for this grid."""
        entry_tick = self.clock.tick() if self.clock and hasattr(self.clock, "tick") else 0
        self.log.trace(f"[POWER] supervise_grid() enter: anchor={self.grid_anchor}, elevation={elevation:.1f}, tick={entry_tick}.")
        if grid:
            self.grid_anchor = getattr(grid, "anchor_id", None)

        grid_id_str = self.grid_anchor or "unknown_grid"
        current_hour = self.clock.elapsed_game_hours() if self.clock and hasattr(self.clock, "elapsed_game_hours") else 0.0
        current_day = self.clock.get_day() if self.clock else 1

        # Use PowerGrid's native stored and capacity fields directly
        stored_wh = getattr(grid, "stored", 0.0) if grid else 0.0
        capacity_wh = getattr(grid, "capacity", 500.0) if grid else 500.0
        consumed_w = getattr(grid, "consumed", 0.0) if grid else 0.0
        generated_w = getattr(grid, "generated", 0.0) if grid else 0.0

        # A grid with no battery at all (e.g. Steam Turbine-only, no Battery
        # built) has nothing this class's night-shedding math can reason
        # about -- battery_pct = stored_wh / capacity_wh would divide by a
        # real zero and read as a permanent 0% "severe deficit" every single
        # night. This never came up before centralizing supervision (only
        # solar-paired grids -- which always have a battery, since solar needs
        # night storage -- ever got supervised); now that every grid is
        # covered, skip battery-less ones outright rather than guess at a
        # generation-vs-consumption strategy this class doesn't implement.
        if capacity_wh <= 0:
            self.log.debug(f"[POWER] supervise_grid() skipping '{grid_id_str}': capacity_wh={capacity_wh:.0f} (no battery on this grid, nothing to shed/restore against).")
            return

        self.log.debug(f"[POWER] Grid snapshot '{grid_id_str}': generated={generated_w:.0f} W, consumed={consumed_w:.0f} W, stored={stored_wh:.0f} Wh / {capacity_wh:.0f} Wh, elevation={elevation:.1f}.")

        grid_machines = None
        if grid:
            if hasattr(grid, "machine_ids") and grid.machine_ids:
                grid_machines = set(grid.machine_ids)
            elif hasattr(grid, "members") and grid.members:
                grid_machines = {getattr(m, "id", "") for m in grid.members if hasattr(m, "id")}

        if elevation > 0:
            self.has_observed_day = True
            self.peak_day_battery_wh = max(self.peak_day_battery_wh, stored_wh)

        # Day/night transition checks
        if self.last_elevation > 0 and elevation == 0:
            self.handle_sunset(current_day, current_hour, grid_id_str, capacity_wh, consumed_w)
        elif self.last_elevation == 0 and elevation > 0:
            self.handle_sunrise(current_hour, grid_id_str)

        self.last_elevation = elevation

        # Load shedding at night vs recovery during day
        if elevation == 0:
            self.manage_night_loads(current_day, current_hour, grid_id_str, grid_machines, stored_wh, capacity_wh, consumed_w)
        else:
            self.manage_day_recovery(grid_id_str, grid_machines, generated_w, consumed_w, stored_wh)

        exit_tick = self.clock.tick() if self.clock and hasattr(self.clock, "tick") else 0
        self.log.trace(f"[POWER] supervise_grid() exit: '{grid_id_str}', elapsed_ticks={exit_tick - entry_tick}, shedded_count={len(self.shedded_machines)}.")
