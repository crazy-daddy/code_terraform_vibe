# Oil Pump automation: keep oil_out routed to a reachable network Liquid
# Tank / Large Liquid Tank reserved for oil, idling while the well is dormant.

from fluid_pump import FluidPumpController

controller = FluidPumpController(self, "oil")
controller.run()
