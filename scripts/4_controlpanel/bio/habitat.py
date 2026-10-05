# Habitat automation: revives the species the Wildlife planner
# assigns, keeps feed and the gas/liquid bands, buys queued Insight nodes.
# See lib/habitat.py.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import habitat as self

from habitat import HabitatController

HabitatController(self).run()
