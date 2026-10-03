# Drone Depot Automation Script
# Wires the Depot's output to the outpost's Essence Liquifier when
# unambiguous, and publishes bay/slot telemetry for dashboards and drones.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import drone_station as self

from drone_depot import DroneDepotController

station = DroneDepotController(self)
station.run()
