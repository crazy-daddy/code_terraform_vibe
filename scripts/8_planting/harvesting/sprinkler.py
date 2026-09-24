# Sprinkler automation (8_planting): keeps it supplied and switched on only while a
# layout crop beside it needs it. See lib/field_provider.py.

from field_provider import FieldProviderController

FieldProviderController(self, "sprinkler").run()
