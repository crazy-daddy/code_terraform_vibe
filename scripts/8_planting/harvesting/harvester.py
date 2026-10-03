# Harvester automation (8_planting): plants, tends and harvests the field
# layout, falling back to the loose-item sweep when nothing is due.
# See lib/field_keeper.py.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import harvester as self

from field_keeper import FieldKeeperController

FieldKeeperController(self).run()
