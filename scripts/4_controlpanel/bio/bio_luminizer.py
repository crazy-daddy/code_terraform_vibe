# Biology Luminizer Script (Shared Library Variant)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import bio_luminizer as self

from bio_coastal import BioLuminizerController

controller = BioLuminizerController(self)
controller.run()
