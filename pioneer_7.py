from pioneer import PioneerController

DESTINATION_OUTPOST_ID = "outpost_2"
SOURCE_OUTPOST_ID = "outpost_home"

pioneer = PioneerController(self, home_base=SOURCE_OUTPOST_ID, cruise_throttle=1.0)
pioneer.run(dest_outpost_id=DESTINATION_OUTPOST_ID)
