# Seed Maker automation. Stage A: fair brute-force sweep of untried life-form
# triples until every seed species is discovered (lib/seed_maker.py).
# Stage B, once all are known: make seeds on demand for the field
# (lib/seed_supply.py).

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import seed_maker as self

from seed_maker import SeedMakerController, SEED_SPECIES_TOTAL
from seed_supply import SeedSupplyController

if len(self.recipes()) >= SEED_SPECIES_TOTAL:
    SeedSupplyController(self).run()
else:
    SeedMakerController(self).run()
