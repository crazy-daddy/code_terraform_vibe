# Night guard for solar-only grids (power phase "solar", lib/power.py).
#
# Batteries are the only store on such a grid, and the sun is the only
# generator, so the dry spell is the night and its length is known. At sunset
# this checks whether the battery can carry the night; through the night it
# forecasts the remaining need from the live draw blended with the grid's
# historical overnight Wh, and sheds shedding tiers when the battery cannot
# cover it. Shed loads come back progressively: at night once the battery
# clears the need by a margin, by day once solar carries them. Both restore
# checks add back each shed machine's draw (read from the grid members when it
# was shed): the live draw no longer holds it. Without it a night restore
# follows every shed one evaluation later, and the day restore puts the whole
# load back at first light, draining the battery until the morning peak.
#
# Grids with steam, oil or a reactor use PowerGridManager's combined-reserve
# guard instead: there, night is not a dry spell while tanks still hold steam.
# Shed state lives in the PowerGridManager that owns this guard, so a phase
# change hands every shed machine to the other strategy's restore path.
from archive import archive
from swallow import swallowed

# Exact day/night schedule from the decompiled simworker (`daylight: {...}`),
# fractions of a day mapped onto elapsed_game_hours()'s 0-24 scale.
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
MORNING_PEAK_HOUR = DAYLIGHT_FRACTIONS["morning_peak_start"] * 24.0  # 9.12 -- full solar output
NIGHT_DURATION_HOURS = 24.0 - SUNSET_HOUR + SUNRISE_HOUR  # 10.08, exact and constant

# Forecast safety factor on the remaining night's Wh need.
NIGHT_NEED_MARGIN = 1.15
# Battery fractions: below EMERGENCY sheds tier 1 even without a forecast
# deficit; below SEVERE (or under half the need) sheds every tier.
NIGHT_EMERGENCY_FRACTION = 0.20
NIGHT_SEVERE_FRACTION = 0.15


def _notify(text, level="warn", duration=8.0):
    try:
        notify(text, level=level, duration_seconds=duration)
    except Exception as error:
        swallowed("power_solar._notify: notify", error)


class SolarNightGuard:
    """Day/night shedding for one solar-only grid; `manager` is its PowerGridManager."""

    def __init__(self, manager, elevation):
        self.manager = manager
        self.log = manager.log
        self.last_elevation = elevation
        self.has_observed_day = elevation > 0
        self.sunset_hour = archive.get("power.sunset_hour", None)
        self.peak_day_battery_wh = 0.0
        self.last_advisory_day = manager.clock.get_day() if manager.clock else 1
        self.last_night_battery_advisory_day = None
        self.historical_night_wh = archive.get("power.night_wh", None)
        self.night_wh_accumulated = 0.0
        self.last_energy_sample_hour = None
        # Shed machine id -> its draw in W when shed. Machines shed elsewhere
        # (adopted list, another strategy) are missing and count 0 W.
        self.shed_draw_w = {}

    def _hist_key(self):
        anchor = self.manager.grid_anchor
        return f"power.night_wh:{anchor}" if anchor else "power.night_wh"

    # ------------------------------------------------------------------
    def handle_sunset(self, current_day, current_hour, grid_id_str, capacity_wh, consumed_w):
        """Starts night accounting and posts once-a-day battery/solar sizing advisories."""
        self.log.start(f"[POWER] Sunset on '{grid_id_str}'")
        self.sunset_hour = current_hour
        self.night_wh_accumulated = 0.0
        self.last_energy_sample_hour = current_hour
        archive.set("power.sunset_hour", self.sunset_hour)
        self.log.print(f"[POWER] Sunset on '{grid_id_str}' at day {current_day} (hour {current_hour:.1f}). Night mode active.")

        if self.has_observed_day and current_day != self.last_advisory_day:
            self.last_advisory_day = current_day
            hist_wh = archive.get(self._hist_key(), archive.get("power.night_wh", None))
            if hist_wh is not None and hist_wh > 50.0:
                baseline_wh = hist_wh * 1.05
            else:
                baseline_wh = max(consumed_w, 25.0) * NIGHT_DURATION_HOURS
            self.log.debug(f"[POWER] Night baseline for '{grid_id_str}': {baseline_wh:.0f} Wh (history {hist_wh}).")

            if capacity_wh < baseline_wh:
                bats_needed = int((baseline_wh - capacity_wh) // 500) + 1
                hist_tag = f" (Historical night: {hist_wh:.0f} Wh)" if hist_wh else ""
                msg = f"Battery capacity ({capacity_wh:.0f} Wh) on '{grid_id_str}' insufficient for night loads ({baseline_wh:.0f} Wh needed{hist_tag}). Recommend {bats_needed}x Battery at Shop."
                self.log.level("warn").print(f"[POWER ADVISORY] {msg}")
                _notify(f"[Power Advisory - {grid_id_str}] {msg}")

            if capacity_wh > 0 and self.peak_day_battery_wh < capacity_wh * 0.90:
                charge_pct = self.peak_day_battery_wh / capacity_wh * 100
                msg = f"Solar generation deficit on '{grid_id_str}'! Batteries only reached {charge_pct:.0f}% charge. Recommend 1x Solar Generator (500 cr) at Shop."
                self.log.level("warn").print(f"[POWER ADVISORY] {msg}")
                _notify(f"[Power Advisory - {grid_id_str}] {msg}")
        self.log.end()

    def handle_sunrise(self, current_hour, grid_id_str):
        """Folds the night's consumed Wh into the per-grid history (EMA)."""
        self.log.start(f"[POWER] Sunrise on '{grid_id_str}'")
        if self.sunset_hour is not None and self.night_wh_accumulated > 10.0:
            curr_hist = archive.get(self._hist_key(), None)
            if curr_hist is not None:
                new_hist = curr_hist * 0.70 + self.night_wh_accumulated * 0.30
            else:
                new_hist = self.night_wh_accumulated
            self.historical_night_wh = new_hist
            archive.set(self._hist_key(), round(new_hist, 1))

        hist_str = f", {self.night_wh_accumulated:.0f} Wh used overnight" if self.night_wh_accumulated > 0 else ""
        self.log.print(f"[POWER] Sunrise on '{grid_id_str}'. Night lasted {NIGHT_DURATION_HOURS:.1f} game hours{hist_str}.")
        self.peak_day_battery_wh = 0.0
        self.has_observed_day = True
        self.night_wh_accumulated = 0.0
        self.last_energy_sample_hour = None
        self.log.end()

    # ------------------------------------------------------------------
    def manage_night_loads(self, current_day, current_hour, grid_id_str, grid_machines, stored_wh, capacity_wh, consumed_w, draws=None):
        """Forecasts the remaining night's need and sheds or restores tiers against it.
        `draws` maps member ids to their live draw in W."""
        m = self.manager
        if self.last_energy_sample_hour is not None and current_hour > self.last_energy_sample_hour:
            dt = current_hour - self.last_energy_sample_hour
            if dt < 2.0:
                self.night_wh_accumulated += consumed_w * dt
        self.last_energy_sample_hour = current_hour

        if self.sunset_hour is not None:
            remaining_night = max(0.5, NIGHT_DURATION_HOURS - max(0.0, current_hour - self.sunset_hour))
        else:
            remaining_night = NIGHT_DURATION_HOURS / 2.0

        grid_hist_wh = archive.get(self._hist_key(), self.historical_night_wh)
        if grid_hist_wh is not None:
            effective_rate = consumed_w * 0.60 + grid_hist_wh / NIGHT_DURATION_HOURS * 0.40
        else:
            effective_rate = consumed_w

        wh_needed = effective_rate * remaining_night * NIGHT_NEED_MARGIN
        battery_pct = stored_wh / capacity_wh if capacity_wh > 0 else 0.0
        deficit = stored_wh < wh_needed
        emergency_low = battery_pct < NIGHT_EMERGENCY_FRACTION
        severe = stored_wh < wh_needed * 0.50 or battery_pct < NIGHT_SEVERE_FRACTION

        tiers = m.get_shedding_tiers()
        num_tiers = len(tiers)
        tier_to_shed = num_tiers if severe else (1 if deficit or emergency_low else 0)
        self.log.debug(
            f"[POWER] Night eval '{grid_id_str}': stored={stored_wh:.0f} Wh ({battery_pct*100:.0f}%), "
            f"effective_rate={effective_rate:.0f} W, remaining_night={remaining_night:.2f}h, "
            f"wh_needed={wh_needed:.0f} Wh -> shed {tier_to_shed}/{num_tiers} tier(s)."
        )

        if tier_to_shed:
            if self.last_night_battery_advisory_day != current_day:
                self.last_night_battery_advisory_day = current_day
                bats_needed = max(1, int((wh_needed - stored_wh) // 500) + 1)
                msg = f"Night deficit on '{grid_id_str}'! Stored energy ({stored_wh:.0f} Wh) cannot survive remaining night ({wh_needed:.0f} Wh needed, {remaining_night:.1f}h left). Recommend {bats_needed}x Battery at Shop."
                self.log.level("warn").print(f"[BATTERY ADVISORY] {msg}")
                _notify(f"[Battery Advisory - {grid_id_str}] {msg}", duration=10.0)
            if severe:
                reason = f"critical night deficit ({stored_wh:.0f} Wh, {battery_pct*100:.0f}% battery)"
            elif emergency_low:
                reason = f"night reserve below {NIGHT_EMERGENCY_FRACTION*100:.0f}%"
            else:
                reason = f"night storage {stored_wh:.0f} Wh < {wh_needed:.0f} Wh needed"
            newly = m.shed_tiers(tiers[:tier_to_shed], grid_machines, reason, grid_id_str)
            for m_id in newly:
                self.shed_draw_w[m_id] = (draws or {}).get(m_id, 0.0)
            if newly:
                _notify(f"[Power Guard] Shed {len(newly)} load(s) on '{grid_id_str}': {reason}", level="error" if severe else "warn")

        # Partial recovery through the night once the battery clears the need, with the
        # tier's shed draw added back, by a margin; later tiers (the more important
        # loads) need less margin. Each restored tier's draw counts for the next one.
        self.shed_draw_w = {i: w for i, w in self.shed_draw_w.items() if i in m.shedded_machines}
        if m.shedded_machines and battery_pct >= 0.30:
            rate_w = effective_rate
            for t_idx in reversed(range(num_tiers)):
                steps = num_tiers - (t_idx + 1)
                back_w = sum(self.shed_draw_w.get(i, 0.0) for i in m.shed_ids(tiers[t_idx], grid_machines))
                need_wh = (rate_w + back_w) * remaining_night * NIGHT_NEED_MARGIN
                if stored_wh < need_wh * (1.10 + steps * 0.15) or battery_pct < 0.30 + steps * 0.10:
                    continue
                if m.restore_tier(tiers[t_idx], grid_machines, f"night battery recovered ({stored_wh:.0f} Wh)", grid_id_str):
                    rate_w += back_w

    def manage_day_recovery(self, grid_id_str, grid_machines, generated_w, consumed_w, stored_wh, current_hour=None):
        """Restores shed tiers progressively once solar carries them, or once the battery
        can bridge the gap until MORNING_PEAK_HOUR (after it: until SUNSET_HOUR)."""
        m = self.manager
        self.shed_draw_w = {i: w for i, w in self.shed_draw_w.items() if i in m.shedded_machines}
        if not (m.shedded_machines and stored_wh > 25.0):
            return
        hour_of_day = (current_hour or 0.0) % 24.0
        bridge_h = (MORNING_PEAK_HOUR if hour_of_day < MORNING_PEAK_HOUR else SUNSET_HOUR) - hour_of_day
        tiers = m.get_shedding_tiers()
        num_tiers = len(tiers)
        load_w = consumed_w
        for t_idx in reversed(range(num_tiers)):
            steps = num_tiers - (t_idx + 1)
            back_w = sum(self.shed_draw_w.get(i, 0.0) for i in m.shed_ids(tiers[t_idx], grid_machines))
            margin_w = 10.0 + steps * 5.0
            gap_w = load_w + back_w + margin_w - generated_w
            if stored_wh < 25.0 + steps * 25.0:
                continue
            if gap_w > 0 and (bridge_h <= 0 or stored_wh < gap_w * bridge_h * NIGHT_NEED_MARGIN):
                continue
            reason = f"solar surplus ({generated_w:.0f} W gen vs {load_w + back_w:.0f} W con)" if gap_w <= 0 else f"battery bridges {gap_w:.0f} W for {bridge_h:.1f} h ({stored_wh:.0f} Wh)"
            if m.restore_tier(tiers[t_idx], grid_machines, reason, grid_id_str):
                load_w += back_w

    # ------------------------------------------------------------------
    def step(self, grid: "PowerGrid", elevation, grid_id_str, grid_machines):
        """One pass: day/night transitions, then night shedding or day recovery."""
        clock = self.manager.clock
        current_hour = clock.elapsed_game_hours() if clock and hasattr(clock, "elapsed_game_hours") else 0.0
        current_day = clock.get_day() if clock else 1
        stored_wh = getattr(grid, "stored", 0.0) or 0.0
        capacity_wh = getattr(grid, "capacity", 0.0) or 0.0
        consumed_w = getattr(grid, "consumed", 0.0) or 0.0
        generated_w = getattr(grid, "generated", 0.0) or 0.0
        elevation = elevation or 0.0

        if elevation > 0:
            self.has_observed_day = True
            self.peak_day_battery_wh = max(self.peak_day_battery_wh, stored_wh)
        if self.last_elevation > 0 and elevation == 0:
            self.handle_sunset(current_day, current_hour, grid_id_str, capacity_wh, consumed_w)
        elif self.last_elevation == 0 and elevation > 0:
            self.handle_sunrise(current_hour, grid_id_str)
        self.last_elevation = elevation

        if elevation == 0:
            draws = {getattr(mb, "id", ""): getattr(mb, "consumed", 0.0) or 0.0 for mb in (getattr(grid, "members", None) or [])}
            self.manage_night_loads(current_day, current_hour, grid_id_str, grid_machines, stored_wh, capacity_wh, consumed_w, draws)
        else:
            self.manage_day_recovery(grid_id_str, grid_machines, generated_w, consumed_w, stored_wh, current_hour)
