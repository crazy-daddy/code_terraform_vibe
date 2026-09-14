# Pioneer constructor role.

from pioneer import PioneerController

controller = PioneerController(self, home_coords=(0, 0), cruise_throttle=0.5)
controller.run_construction_loop()