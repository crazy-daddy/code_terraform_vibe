# Vehicle Charging Station Automation Script
# Automatically fast-charges docked vehicles and dispatches rescue drones to stranded vehicles in the field.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import charging_station as self

from charging import ChargingStationController

station = ChargingStationController(self, target_charge_level=1.0)
station.run()

