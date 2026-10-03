# Plant Terraformer automation (8_planting): feeds harvested Forage (plus
# Water / Salt / Fertilizer / Growth Accelerant as the Plants phase needs
# them) and runs the machine in batches. See lib/plant_terraformer.py.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import plant_terraformer as self

from plant_terraformer import PlantTerraformerController

PlantTerraformerController(self).run()
