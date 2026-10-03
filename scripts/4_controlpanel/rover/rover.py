from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import rover as self

from rover import RoverController
rover = RoverController(self)
rover.run()

