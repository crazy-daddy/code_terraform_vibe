# Waste Processor automation: drain the outpost's Water tank before it fills
# so the Water Pumps keep pumping (and making salt). No item is destroyed;
# between drains the processor is switched off. The processor only destroys
# while this script runs.

from water_sink import WaterAwareWasteSinkController

controller = WaterAwareWasteSinkController(self)
controller.run()
