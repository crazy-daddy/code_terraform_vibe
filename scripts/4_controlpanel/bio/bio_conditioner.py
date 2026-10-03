# Biology Conditioner Script (Shared Library Variant) -- automated QC, see lib/bio_deep.py

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import bio_conditioner as self

from bio_deep import BioConditionerController

controller = BioConditionerController(self)
controller.run()
