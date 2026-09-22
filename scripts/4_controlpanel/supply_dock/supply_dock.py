# Supply Dock 1 Automation Script
# Uses shared SupplyDockController library to fulfill Earth Contractor & Weekly Orders.

from supply_dock import SupplyDockController

dock = SupplyDockController(self)
dock.run()

