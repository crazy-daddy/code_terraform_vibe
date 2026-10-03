# Oxygen Generator Script (Shared Library Variant)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import o2gen as self

from terraforming import OxygenController

controller = OxygenController(self)
controller.run()
