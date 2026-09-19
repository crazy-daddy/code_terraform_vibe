# Self-contained early Heat Generator controller (no lib/ imports)
# Discovers the daily optimal power level (1-10) for 100% thermal efficiency

clock = get_component("clock")

ORDER = (5, 6, 4, 7, 3, 8, 2, 9, 1, 10)
optimal_power = None
last_day = -1

while True:
    current_day = int(clock.get_days())
    
    # Thermal state changes daily: re-scan when a new day arrives
    if current_day != last_day or optimal_power is None or self.efficiency() < 95.0:
        last_day = current_day
        best_power = 5
        best_eff = 0.0
        
        for p in ORDER:
            self.set_power(p)
            sleep(0.2)
            eff = self.efficiency()
            if eff > best_eff:
                best_eff = eff
                best_power = p
            if eff >= 99.0:
                break
                
        optimal_power = best_power
        self.set_power(optimal_power)
        print(f"[{self.id}] Calibrated day {current_day}: power={optimal_power} eff={self.efficiency()}%")

    sleep(1.0)

