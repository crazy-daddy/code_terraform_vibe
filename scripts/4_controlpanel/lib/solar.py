from tree_console import TreeConsole, flush_all, reset_all
from version_guard import validate_game_version

# Shared Library for Solar Generator Automation
# Pure closed-loop sun tracking -- Power Grid supervision (brownout
# load-shedding, day/night calibration) is owned centrally by status_panel.py's
# AUTOMATION section (lib/power.py's PowerGridManager, one instance per grid),
# not by any individual solar generator -- see docs/AI_CHEATSHEET.md. With
# supervision centralized in the Control Room panel, each generator handles
# only sun tracking.


SOLAR_POLL_SECONDS = 10.0        # sun elevation drifts slowly; 10 s keeps tilt within a fraction of a degree
SOLAR_NIGHT_POLL_SECONDS = 30.0  # output is 0 W at night, tilt only needs to be ready by sunrise
TILT_DEADBAND_DEG = 0.5          # skip set_tilt when the target moved less than this


class SolarController:
    """Tracks the sun for one solar generator. Nothing else -- see module docstring."""

    def __init__(self, machine, clock=None):
        self.machine = machine
        self.name = getattr(machine, "id", "solar")
        self.clock = clock or get_component("clock")
        self.log = TreeConsole(module="solar")
        self._last_tilt = None

    def track_sun(self):
        """Adjusts tilt angle based on current sun elevation."""
        elevation = self.clock.get_elevation() if self.clock else 0.0
        tilt = max(0, min(90, 90 - elevation))
        if self._last_tilt is None or abs(tilt - self._last_tilt) >= TILT_DEADBAND_DEG:
            self.machine.set_tilt(tilt)
            self._last_tilt = tilt
            if self.log.verbose:
                self.log.trace(f"[{self.name}] Sun elevation {elevation:.1f} deg -> tilt set to {tilt:.1f} deg.")
        return elevation

    def step(self):
        elevation = self.track_sun()
        return SOLAR_NIGHT_POLL_SECONDS if elevation <= 0 else SOLAR_POLL_SECONDS

    def run(self, poll_interval=None):
        self.log.print(f"Solar Tracker ({self.name}) online via Shared Library.")
        validate_game_version()
        while True:
            reset_all()
            interval = self.step()
            flush_all()
            sleep(poll_interval if poll_interval is not None else interval)
