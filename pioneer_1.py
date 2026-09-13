# Battery-safe Pioneer planetary survey script.
# Requires Nav Module, Battery Holder with charged batteries, and Sonar Module.

from pioneer import PioneerController

controller = PioneerController(self, home_coords=(0, 0), cruise_throttle=0.5)
controller.run_survey_loop()
