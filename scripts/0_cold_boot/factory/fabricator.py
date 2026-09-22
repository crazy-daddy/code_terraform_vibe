# Fabricator Automation Script
from fabricator import FabricatorController

TARGET_RECIPE = "${TARGET_RECIPE:circuit}"
fabricator = FabricatorController(self, default_recipe=TARGET_RECIPE)
fabricator.run()

