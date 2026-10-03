# Refiner automation (9_wildlife): purifies raw exotic feedstock into
# creature-grade gas or liquid using tar. See lib/refiner.py.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import refiner as self

from refiner import RefinerController

RefinerController(self).run()
