from tree_console import TreeConsole
from version_guard import validate_game_version

# Shared Library for Solar Generator Automation
# Pure closed-loop sun tracking -- Power Grid supervision (brownout
# load-shedding, day/night calibration) is owned centrally by panel_1.py's
# AUTOMATION section (lib/power.py's PowerGridManager, one instance per grid),
# not by any individual solar generator -- see docs/AI_CHEATSHEET.md. There is
# no Master/Follower election here any more: with a single always-running
# process (the Control Room panel) already doing the supervision once per
# grid, having every generator independently re-elect the same answer every
# tick was pure duplication.


class SolarController:
    """Tracks the sun for one solar generator. Nothing else -- see module docstring."""

    def __init__(self, machine, clock=None):
        self.machine = machine
        self.name = getattr(machine, "id", "solar")
        self.clock = clock or get_component("clock")
        self.log = TreeConsole(module="solar")

    def track_sun(self):
        """Adjusts tilt angle based on current sun elevation."""
        elevation = self.clock.get_elevation() if self.clock else 0.0
        tilt = max(0, min(90, 90 - elevation))
        self.machine.set_tilt(tilt)
        return elevation

    def step(self):
        self.track_sun()

    def run(self, poll_interval=1.0):
        self.log.print(f"Solar Tracker ({self.name}) online via Shared Library.")
        validate_game_version()
        while True:
            self.step()
            sleep(poll_interval)
