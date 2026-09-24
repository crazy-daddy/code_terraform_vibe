# Guide: biosphere_plants_tier

## Biosphere, Plants

**Plants** is an active crop chain. The field grows one-shot **Forage** harvests for Wildlife and industry. The **Plant Terraformer fleet** processes that physical stock in visible batches to create permanent Plants km². Nothing in the field increases km² by itself.

### 1. Discover and make seeds

At **500 t Biomass**, fabricate and deploy a **Seed Maker**. Each `combine(...)` trial consumes **1 t each of three different life forms**. A successful blend places one physical species seed in its result bay and records the recipe in the Flora journal. Repeat known blends whenever you want more seeds.

### 2. Plant and maintain the field

Send seeds to home Inventory. Call `load_seed(seed_id)` anywhere on the local grid to put one physical seed in the Harvester's held slot, move to an empty cell, and call `plant(seed_id)`. Sowing finishes after **0.5 hours**. Every species has visible requirements such as light, shade, water, salt, spacing, clusters, companions, or antagonists. Growth pauses safely while any requirement is missing.

**Beside means orthogonally adjacent: directly above, below, left, and right. Diagonals never count for plant relationships.** Every rule about neighbouring plants reads those four and only those four, so a **cluster** species needs a **2×2 block**, the smallest shape where all four cells have two of their own kind beside them. A row of three leaves both ends stalled forever.

A **Spacer** plant needs all four neighboring cells to be free of **other plants**. Machines, including Grow Lamps, Sprinklers, Dispensers, and Crop Automators, are allowed beside it. For example, a Sprinkler directly to its left does not block growth as long as the plant's other requirements are met. Diagonal plants are allowed, so Spacer plants can form a checkerboard.

**Companion** and **antagonist** read the same four cells. Fixed Grow Lamps, Sprinklers, and Dispensers also serve the four orthogonally adjacent cells (directly above, below, left, and right); diagonals do not count.

Each crop's Forage rises across its visible growth stages and freezes when ready. The Harvester can provide early manual light, water, and salt care for 24 hours per visit. Later, Grow Lamps, Sprinklers, and Dispensers maintain crop conditions while Crop Automators harvest, plant, and apply treatments. Hover any of these machines on the field to see its service area.

### 3. Build productive diversity

Each distinct supported species multiplies crop yield. One productive species gives **×1**, five give **×5**, ten give **×10**, and all fifteen give **×15**. Harder species also have larger base harvest values.

### 4. Grow Lamp and Sprinkler upgrades

Each upgrade pack improves one deployed provider. Both machines keep the same four-cell coverage: directly above, below, left, and right. Tiers increase Forage accumulated during growth; they do not change growth speed or add diagonal coverage.

| Tier | Forage factor on its own | Power per provider | Sprinkler Water use |
| --- | ---: | ---: | ---: |
| Mk I | ×1 | 5 W | 2 t/h |
| Mk II | ×2 | 25 W | 4 t/h |
| Mk III | ×4 | 100 W | 8 t/h |
| Mk IV | ×8 | 500 W | 16 t/h |

Power draw applies while enabled. A Sprinkler consumes Water while supplied, even with no crops beside it. The crop must require the provider's service: a Grow Lamp boosts light-requiring crops and a Sprinkler boosts water-requiring crops. All of the crop's other requirements must also be met. Providers must be powered, enabled, and supplied. The Dispenser stays at Mk I and supplies salt with no yield bonus.

Only the strongest covering provider for each required condition counts. Two sprinklers do not stack. Bonuses from different required services add above the ×1 baseline, with a **×12 cap on the combined provider factor**. For a crop requiring both light and water, a Mk II lamp plus a Mk II sprinkler gives **×3**: one baseline plus two +100% bonuses. A Mk IV lamp plus a Mk IV sprinkler reaches the **×12** cap.

### 5. Fertilizer, Growth Accelerant, and Yield Amplifier

Fertilizer Mk I, II, and III give **×2, ×3, and ×5** base Forage yield on their own for **8 hours per dose**. More of the same tier extends duration; wait for the active dose to expire before switching tiers. These field bonuses are separate from the **10, 30, and 50 potency** values used in Plant Terraformer recipes.

Growth Accelerant gives **×2 growth speed for 8 hours per dose**, reaching the same yield sooner while the crop's requirements are met. Fertilizer and Growth Accelerant time drains while the crop is immature, including while missing requirements stall it, and stops draining at maturity. Yield Amplifier gives **×3** base Forage yield on its own to growing crops across the whole field for **24 hours per dose**; its timer runs continuously. Additional doses extend duration.

Provider, Fertilizer, and Yield Amplifier bonuses add above the ×1 baseline. For example, a Mk II sprinkler (+100%), Mk III Fertilizer (+400%), and Yield Amplifier (+200%) give **×8**, before species diversity multiplies the result. This example requires a water-requiring crop with all its other conditions met. Bonuses apply only to Forage earned while they are active. Already banked Forage stays unchanged, and a mature crop gains no more until it is harvested and replaced.

### 6. Harvest and replant

A ready crop stays in its cell until explicitly harvested. The mobile Harvester works for **0.5 hours**. Each Crop Automator job works for **0.1 hours** at 100% outpost efficiency. Submitting a job returns immediately; one physical executor then processes up to 50 jobs total, counting its active and pending jobs, in strict FIFO order (first in, first out, so the oldest job runs first). It never runs two jobs at once or bypasses a blocked queue head on its own, and it pauses about **1 second** between jobs while its arm resets. A script can inspect the active and pending work, then use `move_job(job_id, position)` to implement another scheduling policy. Jobs whose targets no longer match fail immediately when they reach the executor and do not spend work time. The mobile Harvester transfers as much as Base Inventory can accept and leaves any remainder banked on the crop. A Crop Automator moves whatever fits in its local output, discards the remainder, and clears the cell. A completely full output blocks the job without changing the crop. Several automators can still work their separate service areas in parallel.

### 7. Run the Plant Terraformer fleet

At **2,000 t Biomass**, fabricate and deploy one or more **Plant Terraformers** at operational outposts. Connect each Terraformer's standard `input` to a local Crop Automator output, store, or home Inventory, then use `take(...)` or send from the source. Connect Water through `water_in`, then call `self.set_enabled(True)`. Item transfers use ordinary feeder cooldowns; the Terraformer handles **16 items per step** at Mk I and **80** at Mk II. Each machine commits the largest proportional loaded batch, performs **3 hours** of work, and delivers km². Mk I stops at **2,250,000 km²**; Mk II handles the final two bands.

> The complete flow is: discover seeds, load and plant, maintain conditions, diversify, harvest and clear, replant, then transfer Forage into the Terraformer.

*Guide / World & Infrastructure*
