# Biology Lab Script (Shared Library Variant)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import bio_collector as self

from bio import BioCollectorController

controller = BioCollectorController(self)
controller.run()
