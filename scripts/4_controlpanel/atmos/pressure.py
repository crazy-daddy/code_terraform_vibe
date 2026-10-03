# Pressure Generator Script (Shared Library Variant)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import pressure as self

from terraforming import PressureController

controller = PressureController(self)
controller.run()
