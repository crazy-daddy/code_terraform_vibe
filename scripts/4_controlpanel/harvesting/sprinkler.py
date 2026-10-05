# Sprinkler automation: keeps it supplied and switched on only while a
# layout crop beside it needs it. See lib/field_provider.py.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import sprinkler as self

from field_provider import FieldProviderController

FieldProviderController(self, "sprinkler").run()
