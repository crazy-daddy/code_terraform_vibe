# Pioneer constructor role.

from pioneer import PioneerController

controller = PioneerController(self, cruise_throttle=0.5)
controller.run_construction_loop()