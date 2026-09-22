# Oxygen Generator Script
# Docs specification:
# - Draws 8 W from grid.
# - Intake sweet spot: atmosphere.get_co2() / 10
# - Carbon waste sweet spot for dump_waste(): between 50 and 60 (clean dump without penalty)
# - Production stalls at 100 waste.

atmo = get_component("atmosphere")

while True:
    # 1. Dynamically set intake to the peak-efficiency sweet spot (CO2 / 10)
    co2 = atmo.get_co2()
    target_intake = co2 / 10.0
    self.set_intake(target_intake)

    # 2. Check carbon waste accumulation and dump within the clean window (50 - 60)
    current_waste = self.waste()
    if current_waste >= 50:
        res = self.dump_waste()
        print(f"Dumped waste at {current_waste:.1f}. Penalty: {res.penalty}")

    sleep(1.0)

