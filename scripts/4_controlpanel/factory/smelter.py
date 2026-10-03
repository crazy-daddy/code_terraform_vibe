# Smelter Automation Script
# Uses shared SmelterController library with automated ore refining and idle power shutoff.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import smelter as self

from smelter import SmelterController

smelter = SmelterController(self, target_ore="iron_ore")
smelter.run()

