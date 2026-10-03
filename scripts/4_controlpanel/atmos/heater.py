# Heat Generator Script (Shared Library Variant)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import heater as self

from terraforming import HeatController

controller = HeatController(self)
controller.run()