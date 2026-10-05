# Field Mining Drill telemetry: publishes rate, stockpile fill and
# time-to-full to drill.status (also its pull-hauler pickup advert) and
# warns when extraction stops.
# See lib/mining_drill.py.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import mining_drill as self

from mining_drill import MiningDrillController

controller = MiningDrillController(self, drill_type="mining_drill")
controller.run()
