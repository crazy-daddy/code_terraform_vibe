# Smelter Automation Script
from smelter import SmelterController

TARGET_ORE = "${TARGET_ORE:iron_ore}"
smelter = SmelterController(self, target_ore=TARGET_ORE)
smelter.run()

