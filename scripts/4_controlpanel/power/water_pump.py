# Water Pump automation: keep water_out routed to a reachable network Liquid
# Tank / Large Liquid Tank, rebalancing across whichever has room.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import water_pump as self

from fluid_pump import FluidPumpController

controller = FluidPumpController(self, "water")
controller.run()
