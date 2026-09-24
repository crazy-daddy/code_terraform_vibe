# Drone Depot (Large) Automation Script -- same controller as drone_station.py.
# The Large kit deploys its own type (drone_station_large) with
# drone_station_lrg_N script slots, so devtools/scripts_sync.py needs this
# separate template to match them.

from drone_depot import DroneDepotController

station = DroneDepotController(self)
station.run()
