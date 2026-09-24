# Drone Depot (Medium) Automation Script -- same controller as drone_station.py.
# The Medium kit deploys its own type (drone_station_medium) with
# drone_station_med_N script slots, so devtools/scripts_sync.py needs this
# separate template to match them.

from drone_depot import DroneDepotController

station = DroneDepotController(self)
station.run()
