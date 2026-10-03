# Biology Exchange Script (Shared Library Variant)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import bio_exchange as self

from bio import BioExchangeController

controller = BioExchangeController(self)
controller.run()