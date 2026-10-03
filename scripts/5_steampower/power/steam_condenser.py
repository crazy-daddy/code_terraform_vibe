# Steam Condenser automation: condense banked steam into water while the grid's
# steam reserve and the water tank's room allow.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import steam_condenser as self

from steam_condenser import SteamCondenserController

controller = SteamCondenserController(self)
controller.run()
