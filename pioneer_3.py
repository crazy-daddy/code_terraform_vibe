# Pioneer mining role (requires an Industrial/Heavy Drill Module mounted
# by the operator; this script never mounts one itself).

from pioneer import PioneerController

# No cruise_throttle passed, so this follows the fleet-wide archive default
# (see vehicle_energy.py's DEFAULT_CRUISE_THROTTLE_KEY), settable via the
# Data Archive Notebook.
controller = PioneerController(self, home_base="outpost_4")
controller.run_mining_loop()
