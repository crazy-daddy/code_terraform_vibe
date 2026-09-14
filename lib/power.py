# Shared Library for Solar Generator Automation & Power Grid Management
# Features:
# - Sun elevation tracking for solar panels.
# - Multi-outpost power grid awareness (independent grids elect their own master; unified grids demote followers).
# - Battery pool aggregation across independent grids.
# - Automated Tier 1 and Tier 2 load shedding and recovery.
# - Sunset & sunrise energy accounting and Data Archive persistence.

from archive import archive

class SolarController:
    """
    Manages solar tracking and central power grid management.
    Features automatic Master/Follower election:
    - Master: tracks Sun, monitors entire multi-battery pool for its grid, executes automated load shedding
      and recovery, and issues sunset battery/solar deficit advisories.
    - Follower: tracks Sun tilt angle with zero redundant grid polling.
    - Grid-Aware Master Election:
      * Discovers all solar generators connected to THIS generator's power grid via power_control.grid().
      * Elects the lowest numeric ID running solar generator on this grid as Master.
      * If grids join up via power lines, all panels join the same grid and elect a single Master.
      * If grids are separate (e.g. unjoined outpost), each grid elects its own independent Master.
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
        self.grid_anchor = None
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

    def get_grid(self):
        """Fetches the PowerGrid containing this solar generator."""
        if self.power and hasattr(self.power, "grid"):
            try:
                grid = self.power.grid(self.name)
                if grid:
                    return grid
            except Exception:
                pass
        return None

    def check_master(self):
        """
        Elects a single Master per independent power grid:
        - Discovers all solar generators connected to THIS generator's power grid.
        - Elects the lowest numeric ID running solar generator on this grid as Master.
        - If grids join up via power lines, all panels join the same grid and elect a single Master.
        - If grids are separate (e.g. unjoined outpost), each grid elects its own independent Master.
        """
        grid = self.get_grid()
        grid_solars = []

        if grid:
            self.grid_anchor = getattr(grid, "anchor_id", None)
            if hasattr(grid, "machine_ids") and grid.machine_ids:
                for mid in grid.machine_ids:
                    if mid.startswith("solar"):
                        grid_solars.append(mid)
            elif hasattr(grid, "members") and grid.members:
                for member in grid.members:
                    mid = getattr(member, "id", "")
                    m_type = getattr(member, "type_id", "")
                    roles = getattr(member, "roles", [])
                    if mid.startswith("solar") or m_type == "solar_generator" or "solar" in roles:
                        grid_solars.append(mid)

        # Fallback: if power_control.grid() didn't resolve, check outpost buildings
        if not grid_solars:
            outpost = getattr(self.machine, "outpost", None)
            if outpost and hasattr(outpost, "buildings"):
                try:
                    for b in outpost.buildings("solar_generator"):
                        b_id = getattr(b, "id", "")
                        if b_id:
                            grid_solars.append(b_id)
                except Exception:
                    pass

        # If still not found, default to self
        if not grid_solars:
            grid_solars = [self.name]

        def solar_sort_key(s_id):
            try:
                return int(s_id.split('_')[-1])
            except Exception:
                return 9999

        grid_solars = sorted(list(set(grid_solars)), key=solar_sort_key)

        if self.run_ctrl and hasattr(self.run_ctrl, "is_running"):
            try:
                for cand in grid_solars:
                    if self.run_ctrl.is_running(cand):
                        return (self.name == cand)
            except Exception:
                pass

        # Fallback: lowest ID in this grid is master
        return (self.name == grid_solars[0])

    def get_battery_info(self, grid):
        """Aggregates all batteries deployed on this specific power grid."""
        total_stored = 0.0
        total_cap = 0.0
        found_ids = set()

        if grid and hasattr(grid, "members") and grid.members:
            for member in grid.members:
                m_id = getattr(member, "id", "")
                roles = getattr(member, "roles", [])
                m_type = getattr(member, "type_id", "")
                if "battery" in m_id.lower() or "battery" in roles or m_type == "battery":
                    try:
                        b = get_component(m_id)
                        if b and hasattr(b, "get_level") and m_id not in found_ids:
                            total_stored += b.get_level()
                            total_cap += b.get_capacity()
                            found_ids.add(m_id)
                    except Exception:
                        pass

        # If members weren't readable directly, check grid.stored and grid.capacity
        if not found_ids and grid is not None:
            for s_attr in ["stored", "battery_stored", "stored_wh", "battery_level"]:
                if hasattr(grid, s_attr) and getattr(grid, s_attr) is not None:
                    stored = getattr(grid, s_attr)
                    cap = getattr(grid, "capacity", getattr(grid, "battery_capacity", 500.0)) or 500.0
                    return stored, cap

        if found_ids:
            return total_stored, total_cap

        # Single base fallback if standalone batteries
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
        if found_ids:
            return total_stored, total_cap

        return 0.0, 500.0

    def step(self):
        # 1. Closed-loop solar elevation tracking (both Master and Follower)
        elevation = self.clock.get_elevation() if self.clock else 0.0
        tilt = max(0, min(90, 90 - elevation))
        self.machine.set_tilt(tilt)

        # 2. Master / Follower role check per independent grid
        was_master = self.is_master
        self.is_master = self.check_master()
        if self.is_master and not was_master:
            grid_tag = f" on grid '{self.grid_anchor}'" if self.grid_anchor else ""
            print(f"[{self.name}] Promoted to Power Grid Master{grid_tag}.")
        elif was_master and not self.is_master:
            grid_tag = f" on grid '{self.grid_anchor}'" if self.grid_anchor else ""
            print(f"[{self.name}] Demoted to Follower{grid_tag} (unified with upstream master).")

        if not self.is_master:
            return

        # 3. Master Grid Supervision
        current_hour = self.clock.elapsed_game_hours() if hasattr(self.clock, "elapsed_game_hours") else 0.0
        current_day = self.clock.get_day() if self.clock else 1

        grid = self.get_grid()
        if grid:
            self.grid_anchor = getattr(grid, "anchor_id", None)
        elif self.power and hasattr(self.power, "grids"):
            try:
                grids = self.power.grids()
                if grids:
                    grid = grids[0]
                    self.grid_anchor = getattr(grid, "anchor_id", None)
            except Exception:
                pass

        grid_machines = None
        if grid:
            if hasattr(grid, "machine_ids") and grid.machine_ids:
                grid_machines = set(grid.machine_ids)
            elif hasattr(grid, "members") and grid.members:
                grid_machines = {getattr(m, "id", "") for m in grid.members if hasattr(m, "id")}

        stored_wh, capacity_wh = self.get_battery_info(grid)
        consumed_w = getattr(grid, "consumed", 0.0) if grid else 0.0
        generated_w = getattr(grid, "generated", 0.0) if grid else 0.0
        is_night = (elevation == 0)

        if elevation > 0:
            self.has_observed_day = True
            self.peak_day_battery_wh = max(self.peak_day_battery_wh, stored_wh)

        # 4. Day/Night transitions & dynamic night length calibration
        grid_id_str = self.grid_anchor or self.name
        if self.last_elevation > 0 and elevation == 0:
            # Sunset
            self.sunset_hour = current_hour
            self.night_wh_accumulated = 0.0
            self.last_energy_sample_hour = current_hour
            archive.set("power.sunset_hour", self.sunset_hour)
            print(f"[POWER] Sunset detected on '{grid_id_str}' at day {current_day} (hour {current_hour:.1f}). Night mode active.")

            if self.has_observed_day and current_day != self.last_advisory_day:
                self.last_advisory_day = current_day

                # Estimate baseline night load using historical night energy if available
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

        elif self.last_elevation == 0 and elevation > 0:
            # Sunrise
            if self.sunset_hour is not None:
                measured_night = current_hour - self.sunset_hour
                if 2.0 < measured_night < 20.0:
                    self.night_duration = measured_night
                    archive.set("power.night_duration", self.night_duration)

                    # Persist total energy used overnight to Data Archive
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

        self.last_elevation = elevation

        # 5. Night endurance calculation & load shedding
        if is_night:
            # Integrate energy consumption across elapsed time slices
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

            # Calculate remaining Wh needed using both instantaneous load and historical average rate
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

            # Step 1: Shed Tier 1 non-critical loads on this grid
            if deficit_detected or emergency_low:
                # Real-time advisory recommendation to buy batteries (once per night)
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

                for m_id in self.NON_CRITICAL_MACHINES:
                    if grid_machines is not None and m_id not in grid_machines:
                        continue
                    try:
                        if self.power and self.power.can_power_off(m_id) and self.power.is_powered(m_id):
                            res = self.power.set_powered(m_id, False)
                            if res.status == "ok":
                                self.shedded_machines.add(m_id)
                                reason = "Emergency reserve guard (<20%)" if emergency_low else f"Insufficient storage ({stored_wh:.0f} Wh < {wh_needed:.0f} Wh needed)"
                                print(f"[POWER GUARD] Shed Tier 1 load ({m_id}) on '{grid_id_str}'. Reason: {reason}.")
                                try:
                                    notify(f"[Power Guard] Shed load ({m_id}) on {grid_id_str}: {reason}", level="warn", duration_seconds=6.0)
                                except Exception:
                                    pass
                    except Exception:
                        pass

            # Step 2: Under severe deficit or critical reserve (<15%), shed Tier 2 (Terraforming equipment) on this grid
            if severe_deficit or battery_pct < 0.15:
                for m_id in self.TERRAFORMING_MACHINES:
                    if grid_machines is not None and m_id not in grid_machines:
                        continue
                    try:
                        if self.power and self.power.can_power_off(m_id) and self.power.is_powered(m_id):
                            res = self.power.set_powered(m_id, False)
                            if res.status == "ok":
                                self.shedded_machines.add(m_id)
                                reason = f"Critical power deficit ({stored_wh:.0f} Wh, {battery_pct*100:.0f}% battery)"
                                print(f"[POWER GUARD] Shed Tier 2 load ({m_id}) on '{grid_id_str}'. Reason: {reason}.")
                                try:
                                    notify(f"[Power Guard CRITICAL] Shed load ({m_id}) on {grid_id_str}: {reason}", level="error", duration_seconds=8.0)
                                except Exception:
                                    pass
                    except Exception:
                        pass

            # Step 3: Nighttime partial recovery if battery stabilizes above requirement + safety margin
            if self.shedded_machines and stored_wh >= (wh_needed * 1.10) and battery_pct >= 0.30:
                # Restore Tier 2 (Terraforming) first
                for m_id in self.TERRAFORMING_MACHINES:
                    if m_id in self.shedded_machines:
                        if grid_machines is not None and m_id not in grid_machines:
                            continue
                        try:
                            if self.power and self.power.can_power_off(m_id) and not self.power.is_powered(m_id):
                                res = self.power.set_powered(m_id, True)
                                if res.status == "ok":
                                    self.shedded_machines.discard(m_id)
                                    print(f"[POWER GUARD] Restored {m_id} (Terraforming) on '{grid_id_str}' — battery pool recovered ({stored_wh:.0f} Wh).")
                        except Exception:
                            pass
                # Restore Tier 1 (Non-critical) if surplus is generous
                if stored_wh >= (wh_needed * 1.25) and battery_pct >= 0.40:
                    for m_id in self.NON_CRITICAL_MACHINES:
                        if m_id in self.shedded_machines:
                            if grid_machines is not None and m_id not in grid_machines:
                                continue
                            try:
                                if self.power and self.power.can_power_off(m_id) and not self.power.is_powered(m_id):
                                    res = self.power.set_powered(m_id, True)
                                    if res.status == "ok":
                                        self.shedded_machines.discard(m_id)
                                        print(f"[POWER GUARD] Restored {m_id} (Non-critical) on '{grid_id_str}' — battery pool sufficient ({stored_wh:.0f} Wh).")
                            except Exception:
                                pass
        else:
            # Daytime recovery: Restore Terraforming loads first, then Non-critical loads
            if self.shedded_machines and generated_w > (consumed_w + 10.0) and stored_wh > 25.0:
                # Priority 1: Terraforming machines
                for m_id in self.TERRAFORMING_MACHINES:
                    if m_id in self.shedded_machines:
                        if grid_machines is not None and m_id not in grid_machines:
                            continue
                        try:
                            if self.power and self.power.can_power_off(m_id) and not self.power.is_powered(m_id):
                                res = self.power.set_powered(m_id, True)
                                if res.status == "ok":
                                    self.shedded_machines.discard(m_id)
                                    print(f"[POWER GUARD] Restored {m_id} (Terraforming) on '{grid_id_str}' — solar surplus active ({generated_w:.0f} W gen vs {consumed_w:.0f} W con).")
                        except Exception:
                            pass

                # Priority 2: Non-critical machines (if generation still comfortably exceeds consumption)
                if generated_w > (consumed_w + 15.0) and stored_wh > 50.0:
                    for m_id in self.NON_CRITICAL_MACHINES:
                        if m_id in self.shedded_machines:
                            if grid_machines is not None and m_id not in grid_machines:
                                continue
                            try:
                                if self.power and self.power.can_power_off(m_id) and not self.power.is_powered(m_id):
                                    res = self.power.set_powered(m_id, True)
                                    if res.status == "ok":
                                        self.shedded_machines.discard(m_id)
                                        print(f"[POWER GUARD] Restored {m_id} (Non-critical) on '{grid_id_str}' — solar surplus ample ({generated_w:.0f} W gen vs {consumed_w:.0f} W con).")
                            except Exception:
                                pass

    def run(self, poll_interval=1.0):
        role = "Master" if self.check_master() else "Follower"
        grid_tag = f" on grid '{self.grid_anchor}'" if self.grid_anchor else ""
        print(f"Solar Tracker ({self.name}) online via Shared Library as {role}{grid_tag}.")
        while True:
            self.step()
            sleep(poll_interval)

