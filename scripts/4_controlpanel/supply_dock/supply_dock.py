# Supply Dock 1 Automation Script
# Uses shared SupplyDockController library to fulfill Earth Contractor & Weekly Orders.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import supply_dock as self

from supply_dock import SupplyDockController

dock = SupplyDockController(self)
dock.run()

