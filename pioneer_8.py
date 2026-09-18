# Dedicated Supply Run Transporter (TODO.md Phase 3, Phase D)
# One transporter per mining outpost: hauls this stationed outpost's
# stockpiled ore back to the production outpost only when the production
# outpost's live demand actually needs it (no preemptive top-off). Adjust
# SOURCE_OUTPOST_ID below to match which outpost this specific Pioneer is
# assigned to haul from -- the load can mix several different ores in one
# trip (e.g. 50 titanium + 30 silicon), decided dynamically every cycle
# (whichever of this outpost's assigned ores currently has the largest
# unmet demand AND stock on hand, filled up to cargo capacity), not fixed
# here, since an outpost can have several assigned ores at once.
#
# Pioneer, not Rover, for this role: Rover's integrated hold is fixed at 10
# units (docs/components/rover.md) -- far too small for bulk ore hauling.
# Pioneer's cargo comes from Portable Bins across its Cargo Racks, scaling
# with loadout, and exposes the identical Cargo/VehicleInputSlot/OutputSlot
# interface run_haul_loop() already uses, so no code changes were needed to
# move this role off Rover. Requires: Nav Module (Universal slot), at least
# one Cargo Rack + Portable Bin (Universal slots), Auto Feeders research
# (already unlocked this save) for the input/output ports.

from pioneer import PioneerController

SOURCE_OUTPOST_ID = "outpost_3"
DESTINATION_OUTPOST_ID = "outpost_home"

# home_base=SOURCE_OUTPOST_ID stations this Pioneer AT the mining outpost --
# it idles/recharges there between runs (this makes self.home_base/
# self.home_outpost mean the STATIONED outpost, not the production one,
# unlike every other vehicle) and only drives to the production outpost
# (dest_outpost_id=None) explicitly for each delivery leg, recharging fully
# there too before heading back so the return leg can run at full throttle
# (cruise_throttle below) -- see VehicleCargoMixin.run_haul_loop().
pioneer = PioneerController(self, home_base=SOURCE_OUTPOST_ID, cruise_throttle=1.0)
pioneer.run(dest_outpost_id=DESTINATION_OUTPOST_ID)