# Rover 1 Expedition & Mining Automation Script
# Uses the shared RoverController library with strict round-trip battery safety.

from rover import RoverController

# Create controller for this rover instance -- no cruise_throttle passed, so
# it follows the fleet-wide archive default (see vehicle_energy.py's
# DEFAULT_CRUISE_THROTTLE_KEY), settable via the Data Archive Notebook.
rover = RoverController(self)
rover.run()

