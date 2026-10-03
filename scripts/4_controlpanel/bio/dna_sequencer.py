# DNA Sequencer Script (Shared Library Variant)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import dna_sequencer as self

from bio_geothermal import DnaSequencerController

controller = DnaSequencerController(self)
controller.run()
