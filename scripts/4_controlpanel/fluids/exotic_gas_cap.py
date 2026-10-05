# Exotic Gas Cap automation: keep gas_out routed to a network Gas Tank reserved
# for the deposit's gas, parking while the deposit is dormant. See lib/exotic_cap.py.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import exotic_gas_cap as self

from exotic_cap import ExoticCapController

ExoticCapController(self).run()
