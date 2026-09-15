# Heat Generator Automation Script
#
# Functions:
# 1. Inspects daily weather conditions via self.thermal_state().
# 2. Sweeps power setpoints (1-10 W) on day transitions to find 100% efficiency.
# 3. Caches learned optimal power settings per thermal state.
# 4. Monitors heat production rate and efficiency.

clock = get_component("clock")

# Cached optimal power setpoints for each weather condition
learned_optimal = {}

last_day = None
last_state = None

name = getattr(self, "id", "heater")
print(f"Heat Generator ({name}) online.")

while True:
    current_day = clock.get_day() if clock else None
    current_state = self.thermal_state()

    # If day changed or weather state changed, calibrate power setpoint
    if current_day != last_day or current_state != last_state:
        last_day = current_day
        last_state = current_state

        if current_state in learned_optimal:
            best_p = learned_optimal[current_state]
            self.set_power(best_p)
            print(f"[{name}] Applied cached optimal power: {best_p} W for '{current_state}' (Eff: {self.efficiency():.0f}%, Output: {self.output():.3f} heat/h)")
        else:
            # Sweep power from 1 to 10 to discover 100% efficiency setting
            best_p = 5
            best_eff = -1

            for p in range(1, 11):
                self.set_power(p)
                eff = self.efficiency()
                if eff > best_eff:
                    best_eff = eff
                    best_p = p
                if eff >= 99.0:
                    break

            self.set_power(best_p)
            learned_optimal[current_state] = best_p
            print(f"[{name}] Calibrated thermal state '{current_state}': optimal power is {best_p} W ({best_eff:.0f}% efficiency, {self.output():.3f} heat/h)")

    sleep(2.0)
