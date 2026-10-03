# Oil Pump automation: keep oil_out routed to a reachable network Liquid
# Tank / Large Liquid Tank reserved for oil, idling while the well is dormant.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import oil_pump as self

from fluid_pump import FluidPumpController

controller = FluidPumpController(self, "oil")
controller.run()
