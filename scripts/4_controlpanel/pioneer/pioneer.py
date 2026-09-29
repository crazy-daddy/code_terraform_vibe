# Pioneer Automation Script (Unified)
from pioneer import PioneerController

HOME_BASE = "${HOME_BASE:None}"
CRUISE_THROTTLE = "${CRUISE_THROTTLE:None}"

HOME_BASE = None if HOME_BASE in ("None", "") else HOME_BASE
CRUISE_THROTTLE = float(CRUISE_THROTTLE) if CRUISE_THROTTLE not in ("None", "") else None

pioneer = PioneerController(self, home_base=HOME_BASE, cruise_throttle=CRUISE_THROTTLE)
pioneer.run()
