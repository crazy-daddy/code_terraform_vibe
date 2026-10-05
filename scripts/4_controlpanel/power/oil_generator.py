# Oil Generator automation: last-resort power. Burns oil only while the grid's
# combined reserve is low AND it runs a deficit without oil.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import oil_generator as self

from oil_generator import OilGeneratorController

controller = OilGeneratorController(self)
controller.run()
