# Pioneer mining role (requires an Industrial/Heavy Drill Module mounted
# by the operator; this script never mounts one itself).

from pioneer import PioneerController

controller = PioneerController(self, home_base="outpost_4", cruise_throttle=0.5)
controller.run_mining_loop()
