# Shared Library for Central Power Grid Management & Automated Load Shedding
# Generic master controller that can oversee any power grid (solar, oil, reactor, turbine).
import re
from archive import archive
from solar import SolarController

# Default shedding tiers (configurable via archive key 'power.shedding_tiers')
# Tier 1: Passive background terraforming machinery (shed first)
# Tier 2: Critical active production & logistics (shed only under severe deficit)
DEFAULT_SHEDDING_TIERS = [
    [
        "heater_*",
        "pressure_*",
        "o2gen_*",
        "bio_collector_*",
        "bio_lab_*",
        "bio_exchange_*",
    ],
    [
        "smelter_*",
        "fabricator_*",
        "vehicle_charging_station*",
        "charging_station_*",
    ],
]


class PowerGridManager:
    """
    Supervises a single power grid:
    - Monitors generation, consumption, and battery storage directly via PowerGrid snapshot.
    - Calibrates day/night cycles and historical overnight energy usage.
    - Issues predictive battery and generation advisories at sunset and during nighttime deficits.
    - Manages progressive multi-tier load shedding under deficit conditions.
    - Restores shedded machinery progressively when battery/surplus recovers.
    """

    def __init__(self, machine, clock=None, power=None):
        self.machine = machine
        self.name = getattr(machine, "id", "generator")
        self.clock = clock or get_component("clock")
        self.power = power or get_component("power_control")

        self.grid_anchor = None
        self.shedded_machines = set()

        # Day/Night cycle tracking
        self.last_elevation = self.clock.get_elevation() if self.clock else 0.0
        self.has_observed_day = (self.last_elevation > 0)
        self.night_duration = archive.get("power.night_duration", 10.0)
        self.sunset_hour = archive.get("power.sunset_hour", None)
        self.peak_day_battery_wh = 0.0
        self.last_advisory_day = self.clock.get_day() if self.clock else 1
        self.last_night_battery_advisory_day = None

        # Overnight energy accounting
        self.historical_night_wh = archive.get("power.night_wh", None)
        self.night_wh_accumulated = 0.0
        self.last_energy_sample_hour = None

    def get_grid(self):
        """Fetches the PowerGrid snapshot containing this generator or anchor."""
        if self.power and hasattr(self.power, "grid"):
            try:
                grid = self.power.grid(self.name)
                if grid:
                    return grid
            except Exception:
                pass
        elif self.power and hasattr(self.power, "grids"):
            try:
                grids = self.power.grids()
                if grids:
                    return grids[0]
            except Exception:
                pass
        return None

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
        Falls back to outpost buildings or registered components if grid_machines is not populated.
        """
        if "*" in pattern or "?" in pattern:
            matched = []
            candidates = set(grid_machines) if grid_machines is not None else set()
            if not candidates:
                outpost = getattr(self.machine, "outpost", None)
                if outpost and hasattr(outpost, "buildings"):
                    try:
                        prefix = pattern.split("*")[0].rstrip("_")
                        buildings = outpost.buildings(prefix) if prefix else outpost.buildings()
                        for b in buildings:
                            b_id = getattr(b, "id", "")
                            if b_id:
                                candidates.add(b_id)
                    except Exception:
                        pass
            if not candidates:
                prefix = pattern.split("*")[0]
                for i in range(1, 9):
                    cand = f"{prefix}{i}"
                    try:
                        if get_component(cand) is not None:
                            candidates.add(cand)
                    except Exception:
                        pass

            regex_pat = "^" + re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".") + "$"
            for m_id in sorted(candidates):
                if re.match(regex_pat, m_id):
                    matched.append(m_id)
            return matched
        return [pattern]

    def update_archive_shedded(self):
        """Publishes currently shedded machines to the Data Archive for inter-process coordination."""
        shed_list = sorted(list(self.shedded_machines))
        archive.set("power.shedded", shed_list)
        archive.set("power.shedded_machines", shed_list)
        if self.grid_anchor:
            archive.set(f"power.shedded:{self.grid_anchor}", shed_list)

    def handle_sunset(self, current_day, current_hour, grid_id_str, capacity_wh, consumed_w):
        """Handles sunset detection, night duration calibration, and daytime capacity advisories."""
        self.sunset_hour = current_hour
        self.night_wh_accumulated = 0.0
        self.last_energy_sample_hour = current_hour
        archive.set("power.sunset_hour", self.sunset_hour)
        print(f"[POWER] Sunset detected on '{grid_id_str}' at day {current_day} (hour {current_hour:.1f}). Night mode active.")

        if self.has_observed_day and current_day != self.last_advisory_day:
            self.last_advisory_day = current_day

            hist_key = f"power.night_wh:{self.grid_anchor}" if self.grid_anchor else "power.night_wh"
            hist_wh = archive.get(hist_key, archive.get("power.night_wh", None))
            if hist_wh is not None and hist_wh > 50.0:
                baseline_wh = hist_wh * 1.05
            else:
                baseline_wh = max(consumed_w, 25.0) * self.night_duration

            if capacity_wh < baseline_wh:
                shortfall = baseline_wh - capacity_wh
                bats_needed = int(shortfall // 500) + 1
                hist_tag = f" (Historical night: {hist_wh:.0f} Wh)" if hist_wh else ""
                msg = f"Battery capacity ({capacity_wh:.0f} Wh) on '{grid_id_str}' insufficient for night loads ({baseline_wh:.0f} Wh needed{hist_tag}). Recommend {bats_needed}x Battery at Shop."
                print(f"[POWER ADVISORY] {msg}")
                try:
                    notify(f"[Power Advisory - {grid_id_str}] {msg}", level="warn", duration_seconds=8.0)
                except Exception:
                    pass

            if capacity_wh > 0 and self.peak_day_battery_wh < (capacity_wh * 0.90):
                charge_pct = (self.peak_day_battery_wh / capacity_wh) * 100
                msg = f"Solar generation deficit on '{grid_id_str}'! Batteries only reached {charge_pct:.0f}% charge. Recommend 1x Solar Generator (500 cr) at Shop."
                print(f"[POWER ADVISORY] {msg}")
                try:
                    notify(f"[Power Advisory - {grid_id_str}] {msg}", level="warn", duration_seconds=8.0)
                except Exception:
                    pass

    def handle_sunrise(self, current_hour, grid_id_str):
        """Handles sunrise detection, night duration calculation, and historical energy averaging."""
        if self.sunset_hour is not None:
            measured_night = current_hour - self.sunset_hour
            if 2.0 < measured_night < 20.0:
                self.night_duration = measured_night
                archive.set("power.night_duration", self.night_duration)

                if self.night_wh_accumulated > 10.0:
                    hist_key = f"power.night_wh:{self.grid_anchor}" if self.grid_anchor else "power.night_wh"
                    curr_hist = archive.get(hist_key, None)
                    if curr_hist is not None:
                        new_hist = (curr_hist * 0.70) + (self.night_wh_accumulated * 0.30)
                    else:
                        new_hist = self.night_wh_accumulated
                    self.historical_night_wh = new_hist
                    archive.set(hist_key, round(new_hist, 1))

                hist_str = f", {self.night_wh_accumulated:.0f} Wh used overnight" if self.night_wh_accumulated > 0 else ""
                print(f"[POWER] Sunrise detected on '{grid_id_str}'. Night lasted {self.night_duration:.1f} game hours{hist_str}.")

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

        if tier_to_shed > 0:
            if self.last_night_battery_advisory_day != current_day:
                self.last_night_battery_advisory_day = current_day
                shortfall = wh_needed - stored_wh
                bats_needed = max(1, int(shortfall // 500) + 1)
                adv_msg = f"Night deficit on '{grid_id_str}'! Stored energy ({stored_wh:.0f} Wh) cannot survive remaining night ({wh_needed:.0f} Wh needed, {remaining_night:.1f}h left). Recommend {bats_needed}x Battery at Shop."
                print(f"[BATTERY ADVISORY] {adv_msg}")
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
                    target_ids = self.resolve_pattern_machines(pattern, grid_machines)
                    for m_id in target_ids:
                        if grid_machines is not None and m_id not in grid_machines:
                            continue
                        try:
                            if self.power and self.power.can_power_off(m_id) and self.power.is_powered(m_id):
                                res = self.power.set_powered(m_id, False)
                                if res.status == "ok":
                                    self.shedded_machines.add(m_id)
                                    shed_changed = True
                                    if is_critical_tier:
                                        reason = f"Critical power deficit ({stored_wh:.0f} Wh, {battery_pct*100:.0f}% battery)"
                                        print(f"[POWER GUARD] Shed Tier {t_num} load ({m_id}) on '{grid_id_str}'. Reason: {reason}.")
                                        try:
                                            notify(f"[Power Guard CRITICAL] Shed load ({m_id}) on {grid_id_str}: {reason}", level="error", duration_seconds=8.0)
                                        except Exception:
                                            pass
                                    else:
                                        reason = "Emergency reserve guard (<20%)" if emergency_low else f"Insufficient storage ({stored_wh:.0f} Wh < {wh_needed:.0f} Wh needed)"
                                        print(f"[POWER GUARD] Shed Tier {t_num} load ({m_id}) on '{grid_id_str}'. Reason: {reason}.")
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
                    target_ids = self.resolve_pattern_machines(pattern, grid_machines)
                    for m_id in target_ids:
                        if m_id in self.shedded_machines:
                            if grid_machines is not None and m_id not in grid_machines:
                                continue
                            try:
                                if self.power and self.power.can_power_off(m_id) and not self.power.is_powered(m_id):
                                    res = self.power.set_powered(m_id, True)
                                    if res.status == "ok":
                                        self.shedded_machines.discard(m_id)
                                        recovered_any = True
                                        print(f"[POWER GUARD] Restored {m_id} (Tier {t_num}) on '{grid_id_str}' — battery pool recovered ({stored_wh:.0f} Wh).")
                            except Exception:
                                pass
            if recovered_any:
                self.update_archive_shedded()

    def manage_day_recovery(self, grid_id_str, grid_machines, generated_w, consumed_w, stored_wh):
        """Restores shedded machinery progressively when surplus solar/generation is available."""
        if not (self.shedded_machines and generated_w > (consumed_w + 10.0) and stored_wh > 25.0):
            return

        tiers = self.get_shedding_tiers()
        num_tiers = len(tiers)
        recovered_any = False
        for t_idx in reversed(range(num_tiers)):
            t_num = t_idx + 1
            gen_surplus_needed = 10.0 + ((num_tiers - t_num) * 5.0)
            stored_needed = 25.0 + ((num_tiers - t_num) * 25.0)
            if generated_w < (consumed_w + gen_surplus_needed) or stored_wh < stored_needed:
                continue
            patterns = tiers[t_idx]
            for pattern in patterns:
                target_ids = self.resolve_pattern_machines(pattern, grid_machines)
                for m_id in target_ids:
                    if m_id in self.shedded_machines:
                        if grid_machines is not None and m_id not in grid_machines:
                            continue
                        try:
                            if self.power and self.power.can_power_off(m_id) and not self.power.is_powered(m_id):
                                res = self.power.set_powered(m_id, True)
                                if res.status == "ok":
                                    self.shedded_machines.discard(m_id)
                                    recovered_any = True
                                    print(f"[POWER GUARD] Restored {m_id} (Tier {t_num}) on '{grid_id_str}' — solar surplus active ({generated_w:.0f} W gen vs {consumed_w:.0f} W con).")
                        except Exception:
                            pass
        if recovered_any:
            self.update_archive_shedded()

    def supervise_grid(self, grid, elevation):
        """Core supervision cycle for a master generator on its grid."""
        if grid:
            self.grid_anchor = getattr(grid, "anchor_id", None)

        grid_id_str = self.grid_anchor or self.name
        current_hour = self.clock.elapsed_game_hours() if hasattr(self.clock, "elapsed_game_hours") else 0.0
        current_day = self.clock.get_day() if self.clock else 1

        # Use PowerGrid's native stored and capacity fields directly
        stored_wh = getattr(grid, "stored", 0.0) if grid else 0.0
        capacity_wh = getattr(grid, "capacity", 500.0) if grid else 500.0
        consumed_w = getattr(grid, "consumed", 0.0) if grid else 0.0
        generated_w = getattr(grid, "generated", 0.0) if grid else 0.0

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
