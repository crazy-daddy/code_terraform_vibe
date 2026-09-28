# Waste Processor automation: destroy surplus at this outpost (after biomass
# completion: life forms above what requests and the creature-feed reserve
# keep), and drain the outpost's Water tank before it fills so the Water Pumps
# keep pumping (and making salt). The processor only destroys while this
# script runs.

from water_sink import WaterAwareWasteSinkController

controller = WaterAwareWasteSinkController(self)
controller.run()
