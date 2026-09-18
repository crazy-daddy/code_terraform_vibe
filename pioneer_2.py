# Pioneer constructor role.

from pioneer import PioneerController

# No cruise_throttle passed, so this follows the fleet-wide archive default
# (see vehicle_energy.py's DEFAULT_CRUISE_THROTTLE_KEY), settable via the
# Data Archive Notebook.
controller = PioneerController(self)
controller.run()