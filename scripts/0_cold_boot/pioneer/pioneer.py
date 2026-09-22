# Pioneer Automation Script (Unified)
from pioneer import PioneerController

HOME_BASE = "${HOME_BASE:None}"
DESTINATION_OUTPOST_ID = "${DESTINATION_OUTPOST_ID:None}"
CRUISE_THROTTLE = "${CRUISE_THROTTLE:None}"

HOME_BASE = None if HOME_BASE in ("None", "") else HOME_BASE
DESTINATION_OUTPOST_ID = None if DESTINATION_OUTPOST_ID in ("None", "") else DESTINATION_OUTPOST_ID
CRUISE_THROTTLE = float(CRUISE_THROTTLE) if CRUISE_THROTTLE not in ("None", "") else None

pioneer = PioneerController(self, home_base=HOME_BASE, cruise_throttle=CRUISE_THROTTLE)
pioneer.run(dest_outpost_id=DESTINATION_OUTPOST_ID)

