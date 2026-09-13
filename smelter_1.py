# Smelter 1 Automation Script
# Uses shared SmelterController library with automated ore refining and idle power shutoff.

from smelter import SmelterController

smelter = SmelterController(self, target_ore="iron_ore")
smelter.run()

