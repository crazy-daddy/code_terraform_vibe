# Grow Lamp automation (8_planting): keeps it supplied and switched on only while a
# layout crop beside it needs it. See lib/field_provider.py.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import grow_lamp as self

from field_provider import FieldProviderController

FieldProviderController(self, "grow_lamp").run()
