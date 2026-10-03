# Drone Service Station Automation Script
# Automatically fast-charges docked drones and dispatches the recovery
# vehicle to stranded/scrambled/critical-battery drones in the field.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import drone_service as self

from drone_service import DroneServiceController

station = DroneServiceController(self, target_charge_level=1.0)
station.run()
