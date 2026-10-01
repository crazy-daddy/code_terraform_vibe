# Pioneer Automation Script (Unified)
from pioneer import PioneerController

HOME_BASE = "${HOME_BASE:None}"

HOME_BASE = None if HOME_BASE in ("None", "") else HOME_BASE

pioneer = PioneerController(self, home_base=HOME_BASE)
pioneer.run()
