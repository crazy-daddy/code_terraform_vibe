# Fabricator automation: maintain pipe/power-line stock and fulfill Supply Dock orders.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import fabricator as self

from fabricator import FabricatorController

controller = FabricatorController(self)
controller.run()