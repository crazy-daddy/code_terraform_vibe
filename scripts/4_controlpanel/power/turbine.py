# Steam Turbine automation: throttle for buffer health, grid demand, and night carry-over.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import turbine as self

from steam_turbine import SteamTurbineController

controller = SteamTurbineController(self)
controller.run()
