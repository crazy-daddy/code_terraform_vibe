# Essence Liquifier automation: pull native-biome samples from the local Drone
# Depot and route the biome essence to a matching network Liquid Tank.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import essence_liquifier as self

from essence_liquifier import EssenceLiquifierController

controller = EssenceLiquifierController(self)
controller.run()
