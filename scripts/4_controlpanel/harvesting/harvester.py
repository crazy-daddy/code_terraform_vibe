# Harvester 1 Automation Script
# Uses shared HarvesterController library with BFS pathfinding and heat protection.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import harvester as self

from harvesting import HarvesterController

harvester = HarvesterController(self)
harvester.run()

