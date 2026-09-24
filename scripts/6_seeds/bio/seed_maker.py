# Seed Maker automation. Stage A: fair brute-force sweep of untried life-form
# triples until every seed species is discovered (lib/seed_maker.py).
# Stage B, once all are known: make seeds on demand for the field
# (lib/seed_supply.py).

from seed_maker import SeedMakerController, SEED_SPECIES_TOTAL
from seed_supply import SeedSupplyController

if len(self.recipes()) >= SEED_SPECIES_TOTAL:
    SeedSupplyController(self).run()
else:
    SeedMakerController(self).run()
