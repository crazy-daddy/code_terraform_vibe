# Pioneer stationed-mining role (requires an Industrial/Heavy Drill Module
# mounted by the operator; this script never mounts one itself). Mines
# outpost_4's assigned ores (lib/outpost_mining.py's marker-driven
# assigned_ores_for(), see docs/AI_CHEATSHEET.md §2d) up to their stock
# targets, independent of home's live demand -- run_mining_loop() (used by
# mistake here previously) is the home-demand-driven loop and ignores outpost
# marker assignment entirely; run() detects the Drill Module and dispatches
# to run_stationed_mining_loop(self.home_base), which is the one that
# actually respects it.

from pioneer import PioneerController

# No cruise_throttle passed, so this follows the fleet-wide archive default
# (see vehicle_energy.py's DEFAULT_CRUISE_THROTTLE_KEY), settable via the
# Data Archive Notebook.
controller = PioneerController(self, home_base="outpost_4")
controller.run()
