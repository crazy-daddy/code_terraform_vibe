# Oil Generator automation: last-resort power. Burns oil only while the grid's
# combined reserve is low AND it runs a deficit without oil.

from oil_generator import OilGeneratorController

controller = OilGeneratorController(self)
controller.run()
