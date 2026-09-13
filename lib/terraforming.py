# Shared Library for Terraforming Machine Automation
# Reusable controllers for Heat Generators, Pressure Generators, Oxygen Generators, and Solar Trackers/Power Grids.

from archive import archive

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

    def step(self):
        current_day = self.clock.get_day() if self.clock else None
        current_state = self.machine.thermal_state()

        if current_day != self.last_day or current_state != self.last_state:
            self.last_day = current_day
            self.last_state = current_state

            if current_state in self.learned_optimal:
                best_p = self.learned_optimal[current_state]
                self.machine.set_power(best_p)
                print(f"[{self.name}] Applied cached power {best_p} W for '{current_state}' (Eff: {self.machine.efficiency():.0f}%, {self.machine.output():.3f} heat/h)")
            else:
                best_p = 5
                best_eff = -1
                for p in range(1, 11):
                    self.machine.set_power(p)
                    eff = self.machine.efficiency()
                    if eff > best_eff:
                        best_eff = eff
                        best_p = p
                    if eff >= 99.0:
                        break
                self.machine.set_power(best_p)
                self.learned_optimal[current_state] = best_p
                archive.set("heat.optimal_setpoints", self.learned_optimal)
                print(f"[{self.name}] Calibrated '{current_state}': {best_p} W ({best_eff:.0f}% eff, {self.machine.output():.3f} heat/h) [Saved to Data Archive]")

    def run(self, poll_interval=2.0):
        print(f"Heat Generator ({self.name}) online via Shared Library.")
        while True:
            self.step()
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

    def step(self):
        gauge = self.machine.gauge()
        low = self.machine.next_window_low()
        high = self.machine.next_window_high()

        # Gauge wrap detection (~100 to ~0) resets the sync flag for the new sweep
        if gauge < self.last_gauge and (self.last_gauge - gauge) > 20:
            self.synced_this_sweep = False

        self.last_gauge = gauge

        in_window = (low <= gauge <= high) if low <= high else (gauge >= low or gauge <= high)

        if not self.synced_this_sweep and in_window:
            res = self.machine.sync()
            if res.status == "ok":
                self.synced_this_sweep = True
                eff = self.machine.efficiency()
                print(f"[{self.name}] Sync hit! Gauge: {gauge:.1f} in [{low:.1f}, {high:.1f}] -> Eff: {eff:.0f}%, Output: {self.machine.output():.4f} kPa/h")
            elif res.status != "busy":
                print(f"[{self.name}] Sync status:", res.status, "-", res.message)

    def run(self, poll_interval=0.1):
        print(f"Pressure Generator ({self.name}) online via Shared Library.")
        while True:
            self.step()
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

    def step(self):
        if self.atmo:
            co2 = self.atmo.get_co2()
            target_intake = co2 / 10.0
            self.machine.set_intake(target_intake)

        current_waste = self.machine.waste()
        if current_waste >= 50:
            res = self.machine.dump_waste()
            penalty = getattr(res, "penalty", 0.0)
            print(f"[{self.name}] Dumped waste at {current_waste:.1f}. Penalty: {penalty}")

    def run(self, poll_interval=1.0):
        print(f"Oxygen Generator ({self.name}) online via Shared Library.")
        while True:
            self.step()
            sleep(poll_interval)


class SolarController:
    """
    Manages solar tracking and central power grid management.
    Features automatic Master/Follower election:
    - Master: tracks Sun, monitors entire multi-battery pool, executes automated load shedding
      and recovery, and issues sunset battery/solar deficit advisories.
    - Follower: tracks Sun tilt angle with zero redundant grid polling.
    - Automatic Failover: If the active master is stopped or disappears, the lowest ID running panel
      seamlessly promotes itself to Master.
    """
    # Tier 1 (Non-critical): First to shed, last to restore
    NON_CRITICAL_MACHINES = [
        "bio_collector_1",
        "bio_lab_1",
        "bio_exchange_1",
        "smelter_1",
        "smelter",
    ]

    # Tier 2 (Terraforming): Only shed under severe deficit or emergency battery level (<20%)
    # Restored before non-critical machines once solar surplus or safe battery reserve returns
    TERRAFORMING_MACHINES = [
        "heater_1", "heater_2", "heater_3",
        "pressure_1", "pressure_2", "pressure_3",
        "o2gen_1", "o2gen_2", "o2gen_3", "o2gen_4",
    ]

    def __init__(self, machine, clock=None, power=None, run_ctrl=None):
        self.machine = machine
        self.name = getattr(machine, "id", "solar")
        self.clock = clock or get_component("clock")
        self.power = power or get_component("power_control")
        self.run_ctrl = run_ctrl or get_component("run_control")

        self.is_master = False
        self.shedded_machines = set()
        self.last_elevation = self.clock.get_elevation() if self.clock else 0.0
        self.has_observed_day = (self.last_elevation > 0)
        self.night_duration = archive.get("power.night_duration", 10.0)
        self.sunset_hour = archive.get("power.sunset_hour", None)
        self.last_advisory_day = self.clock.get_day() if self.clock else 1
        self.peak_day_battery_wh = 0.0
        self.last_night_battery_advisory_day = None

        # Historical & accumulated night energy tracking
        self.historical_night_wh = archive.get("power.night_wh", None)
        self.night_wh_accumulated = 0.0
        self.last_energy_sample_hour = None

    def check_master(self):
        """
        Elects a single Master among all running solar generators.
        If this panel is solar_1, or if solar_1's script is not running, the lowest running solar id becomes Master.
        """
        if self.name == "solar_1":
            return True

        if self.run_ctrl:
            try:
                # If solar_1 is running, solar_1 is the master
                if self.run_ctrl.is_running("solar_1"):
                    return False
                # If solar_1 is offline, find the lowest running solar panel id
                for i in range(1, 10):
                    cand = f"solar_{i}"
                    if self.run_ctrl.is_running(cand):
                        return (self.name == cand)
            except Exception:
                pass

        # Fallback if run_control is unavailable: default solar_1 to master
        return (self.name == "solar_1")

    def get_battery_info(self, grid):
        """Aggregates all batteries deployed on the grid into a single pool."""
        total_stored = 0.0
        total_cap = 0.0
        found_ids = set()

        if grid and hasattr(grid, "members"):
            for member in grid.members:
                m_id = getattr(member, "id", "")
                roles = getattr(member, "roles", [])
                if "battery" in m_id.lower() or "battery" in roles:
                    try:
                        b = get_component(m_id)
                        if b and hasattr(b, "get_level") and m_id not in found_ids:
                            total_stored += b.get_level()
                            total_cap += b.get_capacity()
                            found_ids.add(m_id)
                    except Exception:
                        pass

        for i in range(1, 11):
            for bid in [f"battery_{i}", f"battery{i}"]:
                if bid not in found_ids:
                    try:
                        b = get_component(bid)
                        if b and hasattr(b, "get_level"):
                            total_stored += b.get_level()
                            total_cap += b.get_capacity()
                            found_ids.add(bid)
                    except Exception:
                        pass

        if "battery" not in found_ids:
            try:
                b = get_component("battery")
                if b and hasattr(b, "get_level"):
                    total_stored += b.get_level()
                    total_cap += b.get_capacity()
                    found_ids.add("battery")
            except Exception:
                pass

        if not found_ids and grid is not None:
            for s_attr in ["battery_stored", "stored_wh", "battery_level", "stored"]:
                if hasattr(grid, s_attr) and getattr(grid, s_attr) is not None:
                    val = getattr(grid, s_attr)
                    cap = getattr(grid, "battery_capacity", 500.0) or 500.0
                    return val, cap

        if found_ids:
            return total_stored, total_cap

        return 0.0, 500.0

    def step(self):
        # 1. Closed-loop solar elevation tracking (both Master and Follower)
        elevation = self.clock.get_elevation() if self.clock else 0.0
        tilt = max(0, min(90, 90 - elevation))
        self.machine.set_tilt(tilt)

        # 2. Master / Follower role check
        was_master = self.is_master
        self.is_master = self.check_master()
        if self.is_master and not was_master:
            print(f"[{self.name}] Promoted to Power Grid Master.")

        if not self.is_master:
            return

        # 3. Master Grid Supervision
        current_hour = self.clock.elapsed_game_hours() if hasattr(self.clock, "elapsed_game_hours") else 0.0
        current_day = self.clock.get_day() if self.clock else 1

        grid = None
        if self.power:
            try:
                grid = self.power.grid(self.name)
                if grid is None:
                    grids = self.power.grids()
                    if grids:
                        grid = grids[0]
            except Exception:
                pass

        stored_wh, capacity_wh = self.get_battery_info(grid)
        consumed_w = getattr(grid, "consumed", 0.0) if grid else 0.0
        generated_w = getattr(grid, "generated", 0.0) if grid else 0.0
        is_night = (elevation == 0)

        if elevation > 0:
            self.has_observed_day = True
            self.peak_day_battery_wh = max(self.peak_day_battery_wh, stored_wh)

        # 4. Day/Night transitions & dynamic night length calibration
        if self.last_elevation > 0 and elevation == 0:
            # Sunset
            self.sunset_hour = current_hour
            self.night_wh_accumulated = 0.0
            self.last_energy_sample_hour = current_hour
            archive.set("power.sunset_hour", self.sunset_hour)
            print(f"[POWER] Sunset detected at day {current_day} (hour {current_hour:.1f}). Night mode active.")

            if self.has_observed_day and current_day != self.last_advisory_day:
                self.last_advisory_day = current_day

                # Estimate baseline night load using historical night energy if available
                if self.historical_night_wh is not None and self.historical_night_wh > 50.0:
                    baseline_wh = self.historical_night_wh * 1.05
                else:
                    baseline_wh = max(consumed_w, 25.0) * self.night_duration

                if capacity_wh < baseline_wh:
                    shortfall = baseline_wh - capacity_wh
                    bats_needed = int(shortfall // 500) + 1
                    hist_tag = f" (Historical night: {self.historical_night_wh:.0f} Wh)" if self.historical_night_wh else ""
                    msg = f"Battery capacity ({capacity_wh:.0f} Wh) insufficient for night loads ({baseline_wh:.0f} Wh needed{hist_tag}). Recommend {bats_needed}x Battery at Shop."
                    print(f"[POWER ADVISORY] {msg}")
                    try:
                        notify(f"[Power Advisory] {msg}", level="warn", duration_seconds=8.0)
                    except Exception:
                        pass

                if capacity_wh > 0 and self.peak_day_battery_wh < (capacity_wh * 0.90):
                    charge_pct = (self.peak_day_battery_wh / capacity_wh) * 100
                    msg = f"Solar generation deficit! Batteries only reached {charge_pct:.0f}% charge. Recommend 1x Solar Generator (500 cr) at Shop."
                    print(f"[POWER ADVISORY] {msg}")
                    try:
                        notify(f"[Power Advisory] {msg}", level="warn", duration_seconds=8.0)
                    except Exception:
                        pass

        elif self.last_elevation == 0 and elevation > 0:
            # Sunrise
            if self.sunset_hour is not None:
                measured_night = current_hour - self.sunset_hour
                if 2.0 < measured_night < 20.0:
                    self.night_duration = measured_night
                    archive.set("power.night_duration", self.night_duration)

                    # Persist total energy used overnight to Data Archive
                    if self.night_wh_accumulated > 10.0:
                        if self.historical_night_wh is not None:
                            # Exponential moving average: 70% history, 30% recent night
                            self.historical_night_wh = (self.historical_night_wh * 0.70) + (self.night_wh_accumulated * 0.30)
                        else:
                            self.historical_night_wh = self.night_wh_accumulated
                        archive.set("power.night_wh", round(self.historical_night_wh, 1))
                        archive.set("power.last_night_wh", round(self.night_wh_accumulated, 1))

                    hist_str = f", {self.night_wh_accumulated:.0f} Wh used overnight" if self.night_wh_accumulated > 0 else ""
                    print(f"[POWER] Sunrise detected. Night lasted {self.night_duration:.1f} game hours{hist_str} [Saved to Data Archive].")
            self.peak_day_battery_wh = 0.0
            self.has_observed_day = True
            self.night_wh_accumulated = 0.0
            self.last_energy_sample_hour = None

        self.last_elevation = elevation

        # 5. Night endurance calculation & load shedding
        if is_night:
            # Integrate energy consumption across elapsed time slices
            if self.last_energy_sample_hour is not None and current_hour > self.last_energy_sample_hour:
                dt = current_hour - self.last_energy_sample_hour
                if dt < 2.0:  # Ignore massive clock jumps or disconnects
                    self.night_wh_accumulated += consumed_w * dt
            self.last_energy_sample_hour = current_hour

            if self.sunset_hour is not None:
                hours_into_night = max(0.0, current_hour - self.sunset_hour)
                remaining_night = max(0.5, self.night_duration - hours_into_night)
            else:
                remaining_night = self.night_duration / 2.0

            # Calculate remaining Wh needed using both instantaneous load and historical average rate
            instant_rate = consumed_w
            if self.historical_night_wh is not None and self.night_duration > 0:
                hist_rate = self.historical_night_wh / self.night_duration
                # Blend instantaneous load (60%) with historical average rate (40%) for stability
                effective_rate = (instant_rate * 0.60) + (hist_rate * 0.40)
            else:
                effective_rate = instant_rate

            wh_needed = effective_rate * remaining_night * 1.15
            battery_pct = (stored_wh / capacity_wh) if capacity_wh > 0 else 0.0

            deficit_detected = (stored_wh < wh_needed)
            emergency_low = (battery_pct < 0.20)
            severe_deficit = (stored_wh < (wh_needed * 0.50)) or (battery_pct < 0.15)

            # Step 1: Shed Tier 1 non-critical loads (Biology, Smelter)
            if deficit_detected or emergency_low:
                # Real-time advisory recommendation to buy batteries (once per night)
                if self.last_night_battery_advisory_day != current_day:
                    self.last_night_battery_advisory_day = current_day
                    shortfall = wh_needed - stored_wh
                    bats_needed = max(1, int(shortfall // 500) + 1)
                    adv_msg = f"Night deficit! Stored energy ({stored_wh:.0f} Wh) cannot survive remaining night ({wh_needed:.0f} Wh needed, {remaining_night:.1f}h left). Recommend {bats_needed}x Battery (300 cr each) at Shop."
                    print(f"[BATTERY ADVISORY] {adv_msg}")
                    try:
                        notify(f"[Battery Advisory] {adv_msg}", level="warn", duration_seconds=10.0)
                    except Exception:
                        pass

                for m_id in self.NON_CRITICAL_MACHINES:
                    try:
                        if self.power and self.power.can_power_off(m_id) and self.power.is_powered(m_id):
                            res = self.power.set_powered(m_id, False)
                            if res.status == "ok":
                                self.shedded_machines.add(m_id)
                                reason = "Emergency reserve guard (<20%)" if emergency_low else f"Insufficient storage ({stored_wh:.0f} Wh < {wh_needed:.0f} Wh needed)"
                                print(f"[POWER GUARD] Shed Tier 1 load: disabled {m_id}. Reason: {reason}.")
                                try:
                                    notify(f"[Power Guard] Shed load: disabled {m_id} ({reason})", level="warn", duration_seconds=6.0)
                                except Exception:
                                    pass
                    except Exception:
                        pass

            # Step 2: Under severe deficit or critical reserve (<15%), shed Tier 2 (Terraforming equipment)
            if severe_deficit or battery_pct < 0.15:
                for m_id in self.TERRAFORMING_MACHINES:
                    try:
                        if self.power and self.power.can_power_off(m_id) and self.power.is_powered(m_id):
                            res = self.power.set_powered(m_id, False)
                            if res.status == "ok":
                                self.shedded_machines.add(m_id)
                                reason = f"Critical power deficit ({stored_wh:.0f} Wh, {battery_pct*100:.0f}% battery)"
                                print(f"[POWER GUARD] Shed Tier 2 (Terraforming) load: disabled {m_id}. Reason: {reason}.")
                                try:
                                    notify(f"[Power Guard CRITICAL] Shed Terraforming: disabled {m_id} ({reason})", level="error", duration_seconds=8.0)
                                except Exception:
                                    pass
                    except Exception:
                        pass

            # Step 3: Nighttime partial recovery if battery stabilizes above requirement + safety margin
            if self.shedded_machines and stored_wh >= (wh_needed * 1.10) and battery_pct >= 0.30:
                # Restore Tier 2 (Terraforming) first
                for m_id in self.TERRAFORMING_MACHINES:
                    if m_id in self.shedded_machines:
                        try:
                            if self.power and self.power.can_power_off(m_id) and not self.power.is_powered(m_id):
                                res = self.power.set_powered(m_id, True)
                                if res.status == "ok":
                                    self.shedded_machines.discard(m_id)
                                    print(f"[POWER GUARD] Restored {m_id} (Terraforming) — battery pool recovered ({stored_wh:.0f} Wh).")
                        except Exception:
                            pass
                # Restore Tier 1 (Non-critical) if surplus is generous
                if stored_wh >= (wh_needed * 1.25) and battery_pct >= 0.40:
                    for m_id in self.NON_CRITICAL_MACHINES:
                        if m_id in self.shedded_machines:
                            try:
                                if self.power and self.power.can_power_off(m_id) and not self.power.is_powered(m_id):
                                    res = self.power.set_powered(m_id, True)
                                    if res.status == "ok":
                                        self.shedded_machines.discard(m_id)
                                        print(f"[POWER GUARD] Restored {m_id} (Non-critical) — battery pool sufficient ({stored_wh:.0f} Wh).")
                            except Exception:
                                pass
        else:
            # Daytime recovery: Restore Terraforming loads first, then Non-critical loads
            if self.shedded_machines and generated_w > (consumed_w + 10.0) and stored_wh > 25.0:
                # Priority 1: Terraforming machines
                for m_id in self.TERRAFORMING_MACHINES:
                    if m_id in self.shedded_machines:
                        try:
                            if self.power and self.power.can_power_off(m_id) and not self.power.is_powered(m_id):
                                res = self.power.set_powered(m_id, True)
                                if res.status == "ok":
                                    self.shedded_machines.discard(m_id)
                                    print(f"[POWER GUARD] Restored {m_id} (Terraforming) — solar surplus active ({generated_w:.0f} W gen vs {consumed_w:.0f} W con).")
                        except Exception:
                            pass

                # Priority 2: Non-critical machines (if generation still comfortably exceeds consumption)
                if generated_w > (consumed_w + 15.0) and stored_wh > 50.0:
                    for m_id in self.NON_CRITICAL_MACHINES:
                        if m_id in self.shedded_machines:
                            try:
                                if self.power and self.power.can_power_off(m_id) and not self.power.is_powered(m_id):
                                    res = self.power.set_powered(m_id, True)
                                    if res.status == "ok":
                                        self.shedded_machines.discard(m_id)
                                        print(f"[POWER GUARD] Restored {m_id} (Non-critical) — solar surplus ample ({generated_w:.0f} W gen vs {consumed_w:.0f} W con).")
                            except Exception:
                                pass

    def run(self, poll_interval=1.0):
        role = "Master" if self.check_master() else "Follower"
        print(f"Solar Tracker ({self.name}) online via Shared Library as {role}.")
        while True:
            self.step()
            sleep(poll_interval)
