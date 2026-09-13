# Vehicle Charging Station Automation Script
# Automatically fast-charges docked vehicles and dispatches rescue drones to stranded vehicles in the field.

from charging import ChargingStationController

station = ChargingStationController(self, target_charge_level=1.0)
station.run()

