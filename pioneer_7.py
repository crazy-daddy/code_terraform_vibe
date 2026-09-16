# Pioneer 7 -- Dedicated Reagent Resupply Transporter (TODO.md Phase 4)
# Repurposed from its original ore-hauling role: outpost_1 (Coastal) no longer
# mines, and this Pioneer is instead the "standing order" that keeps the relocated
# Bio Lab stocked -- buys any Bio Lab reagent shortfall at the Shop (home only has
# direct Shop delivery) and hauls it out to DESTINATION_OUTPOST_ID whenever
# lib/outpost_reagents.py's per-reagent stock targets there show a deficit. No
# preemptive top-off: it only drives out when there's an actual shortfall.
#
# Stations at home (home_base=None, the default) between runs, unlike the old
# ore-hauling role -- see VehicleCargoMixin.run_haul_loop() for the shared
# mechanics with the ore-hauler role (pioneer_5.py/pioneer_6.py).

from pioneer import PioneerController

DESTINATION_OUTPOST_ID = "outpost_1"

pioneer = PioneerController(self, cruise_throttle=1.0)
pioneer.run_haul_loop(dest_outpost_id=DESTINATION_OUTPOST_ID)
