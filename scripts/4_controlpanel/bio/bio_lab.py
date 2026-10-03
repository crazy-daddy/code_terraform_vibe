# Biology Lab Script (Shared Library Variant)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import bio_lab as self

from bio import BioLabController

controller = BioLabController(self)
controller.run()
