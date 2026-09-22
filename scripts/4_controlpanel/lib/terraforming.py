# Shared Library for Terraforming Machine Automation
# Reusable controllers for Heat Generators, Pressure Generators, and Oxygen Generators.
# Note: Solar Generators and Power Grid Management have been moved to lib/power.py.

from archive import archive
from version_guard import validate_game_version
from tree_console import TreeConsole

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
        self.log = TreeConsole(module="terraforming")

    def step(self):
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

    def run(self, poll_interval=2.0):
        self.log.print(f"Heat Generator ({self.name}) online via Shared Library.")
        validate_game_version()
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
        self.log = TreeConsole(module="terraforming")

    def step(self):
        gauge = self.machine.gauge()
        low = self.machine.next_window_low()
        high = self.machine.next_window_high()

        # Gauge wrap detection (~100 to ~0) resets the sync flag for the new sweep
        if gauge < self.last_gauge and (self.last_gauge - gauge) > 20:
            self.synced_this_sweep = False
            self.log.debug(f"[{self.name}] Gauge wrap detected ({self.last_gauge:.1f} -> {gauge:.1f}); resetting synced flag for new sweep, next window [{low:.1f}, {high:.1f}].")

        self.last_gauge = gauge

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

    def run(self, poll_interval=0.1):
        self.log.print(f"Pressure Generator ({self.name}) online via Shared Library.")
        validate_game_version()
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
        self.log = TreeConsole(module="terraforming")

    def step(self):
        if self.atmo:
            co2 = self.atmo.get_co2()
            target_intake = co2 / 10.0
            self.machine.set_intake(target_intake)
            self.log.debug(f"[{self.name}] CO2={co2:.2f} -> intake set to {target_intake:.2f} (sweet spot = CO2/10).")

        current_waste = self.machine.waste()
        if current_waste >= 50:
            res = self.machine.dump_waste()
            penalty = getattr(res, "penalty", 0.0)
            self.log.print(f"[{self.name}] Dumped waste at {current_waste:.1f}. Penalty: {penalty}")
        else:
            self.log.debug(f"[{self.name}] Waste at {current_waste:.1f}, below 50 dump threshold; no action.")

    def run(self, poll_interval=1.0):
        self.log.print(f"Oxygen Generator ({self.name}) online via Shared Library.")
        validate_game_version()
        while True:
            self.step()
            sleep(poll_interval)
