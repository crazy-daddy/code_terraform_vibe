# Pioneer 5 -- Dedicated Supply Run Transporter (TODO.md Phase 3, Phase D)
# One transporter per mining outpost: hauls a stationed outpost's stockpiled
# ore back to home only when home's live demand actually needs it (no
# preemptive top-off). Adjust SOURCE_OUTPOST_ID / ITEM_ID below to match
# which outpost this specific Pioneer is assigned to haul from.
#
# Pioneer, not Rover, for this role: Rover's integrated hold is fixed at 10
# units (docs/components/rover.md) -- far too small for bulk ore hauling.
# Pioneer's cargo comes from Portable Bins across its Cargo Racks, scaling
# with loadout, and exposes the identical Cargo/VehicleInputSlot/OutputSlot
# interface run_supply_run_loop() already uses, so no code changes were
# needed to move this role off Rover. Requires: Nav Module (Universal slot),
# at least one Cargo Rack + Portable Bin (Universal slots), Auto Feeders
# research (already unlocked this save) for the input/output ports.

from pioneer import PioneerController

SOURCE_OUTPOST_ID = "outpost_3"
ITEM_ID = "titanium"

# home_base=SOURCE_OUTPOST_ID stations this Pioneer AT the mining outpost --
# it idles/recharges there between runs and only drives to home explicitly
# for each delivery leg (see VehicleCargoMixin.run_supply_run_loop()).
pioneer = PioneerController(self, home_base=SOURCE_OUTPOST_ID, cruise_throttle=0.5)
pioneer.run_supply_run_loop(ITEM_ID)
