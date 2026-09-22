# Self-contained early Oxygen Generator controller (no lib/ imports)
# Sets intake to ambient CO2 / 10 and dumps waste inside the clean window [50, 60]

atm = get_component("atmosphere")

while True:
    co2 = atm.get_co2()
    # Optimal intake ratio is co2 / 10
    target_intake = max(0.1, co2 / 10.0)
    self.set_intake(target_intake)

    waste = self.waste()
    if 50 <= waste <= 60:
        self.dump_waste()
    elif waste > 60:
        # Emergency dump to prevent shutdown
        self.dump_waste()

    sleep(0.5)

