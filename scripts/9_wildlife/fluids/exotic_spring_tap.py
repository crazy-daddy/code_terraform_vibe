# Exotic Spring Tap automation: keep liquid_out routed to a network Liquid Tank
# reserved for the spring's liquid, parking while the deposit is dormant. See lib/exotic_cap.py.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import exotic_spring_tap as self

from exotic_cap import ExoticCapController

ExoticCapController(self).run()
