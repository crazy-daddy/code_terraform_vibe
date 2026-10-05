# Crop Automator automation: harvests and replants the full
# field layout's cells in its 5 x 5 area. See lib/crop_automator.py.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import crop_automator as self

from crop_automator import CropAutomatorController

CropAutomatorController(self).run()
