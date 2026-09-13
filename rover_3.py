# Rover 1 Expedition & Mining Automation Script
# Uses the shared RoverController library with strict round-trip battery safety.

from rover import RoverController

# Create controller for this rover instance
rover = RoverController(self, home_coords=(0, 0), cruise_throttle=0.5)
rover.run()

