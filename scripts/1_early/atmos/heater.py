# Self-contained early Heat Generator controller (no lib/ imports)
# Discovers daily optimal power level (1-10) with dynamic night-battery protection

clock = get_component("clock")
battery = get_component("battery_1")

ORDER = (5, 6, 4, 7, 3, 8, 2, 9, 1, 10)
optimal_power = None
last_day = -1
throttled = False

def get_battery_pct():
    if not battery:
        return 1.0
    try:
        cap = battery.get_capacity()
        return (battery.get_level() / cap) if cap > 0 else 1.0
    except Exception:
        return 1.0

while True:
    current_day = int(clock.get_day())
    bat_pct = get_battery_pct()

    # Dynamic Battery Protection: Throttle heater if battery drops below 25%
    if bat_pct < 0.25:
        if not throttled:
            self.set_power(1)
            print(f"[{self.id}] Battery low ({bat_pct*100:.1f}% < 25%) -> Throttling heater to 1W to prevent brownout.")
            throttled = True
        sleep(5.0)
        continue
    elif throttled and bat_pct >= 0.35:
        throttled = False
        if optimal_power is not None:
            self.set_power(optimal_power)
            print(f"[{self.id}] Battery recovered ({bat_pct*100:.1f}%) -> Restored optimal power {optimal_power}W.")

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
        if not throttled:
            self.set_power(optimal_power)
        print(f"[{self.id}] Calibrated day {current_day}: power={optimal_power} eff={self.efficiency()}%")

    sleep(2.0)

