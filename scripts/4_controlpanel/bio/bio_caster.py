# Biology Caster Script (Shared Library Variant)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import bio_caster as self

from bio_volcanic import BioCasterController

controller = BioCasterController(self)
controller.run()
