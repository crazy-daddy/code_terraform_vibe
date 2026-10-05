# Reactor automation: holds the core just under full output with
# a measured gain, feeds Fuel Rods from the Lead Casks and cooling water.
# See lib/reactor.py.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import reactor as self

from reactor import ReactorController

ReactorController(self).run()
