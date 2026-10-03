# Biomass Mixer automation: keep every essence input connected to a reachable
# essence tank (or a same-biome Liquifier directly) and report phase status.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import biomass_mixer as self

from biomass_mixer import BiomassMixerController

controller = BiomassMixerController(self)
controller.run()
