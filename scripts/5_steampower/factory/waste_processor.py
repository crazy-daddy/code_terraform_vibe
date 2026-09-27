# Waste Processor automation: destroy surplus at this outpost (after biomass
# completion: life forms above what requests and the creature-feed reserve
# keep). The processor only destroys while this script runs.

from waste_sink import WasteSinkController

controller = WasteSinkController(self)
controller.run()
