# Rough time model: Plants to Wildlife unlock, then Plants + Wildlife to 5M

First rough estimate (2026-10-06). Model: `devtools/plants_wildlife_timeline.py` (`python devtools/plants_wildlife_timeline.py [--forage N] [--habitats N]`), reusing `devtools/wildlife_optimizer.py` and `WILDLIFE_SCHEDULES`.

## Assumptions

- **Clock starts at Field Automation (Plants 620,000 km²).** Before that, the earlier field study (project notes, early field optimization) gives about 15 days from 0 to 620k with the hand-care starter.
- **Forage supply** = the full `crowncap` layout (14-species garden + Crowncap fill, 8 Crop Automators): 2,831 Forage/h (`field_layout.forage_per_hour(full_layout(9))`: 151 Crowncap x 60/48 h x 15 diversity). No Yield Amplifier, no Fertilizer on crops. Ramp: starter rate (380/h) for 48 h until the first Crowncap matures, linear to full by 120 h.
- **Phase A** (620k to 2.25M): every Forage goes to Terraformers. 8 Mk I (3,200/h capacity) so the field, not the Terraformers, is the limit.
- **Phase B** (after 2.25M): Wildlife takes Forage first (planner `forage_reserve`), Terraformers get the rest. 16 Habitats, `WILDLIFE_SCHEDULES[16]`, full fluid support with the optimizer's lead times (common fluids 120 h, refined 240 h after 1,000 Wildlife; deep 240 h after 500k; Habitat Mk II 72 h after 600k), finished colonies released. Feed Makers unlimited (count reported below).
- Fluids, salt hauling, life forms, kits and cash are always available. Habitat/Terraformer slots not checked.

## Timeline (hours from Field Automation)

| Hours | Day | Milestone |
|---:|---:|---|
| 0 | 0 | Field Automation (620k). Buy 8 Crop Automators, plant Crowncap. |
| 48 / 120 | 2 / 5 | First Crowncap harvest / field at full 2,830 Forage/h |
| 96 | 4 | Plants 1.0M |
| 118 | 4.9 | Plants 1.25M: **Terraformer Mk II research unlocks**, salt needed from here |
| 329 | 13.7 | **Plants 2.25M: Wildlife unlocks, Mk I Terraformers stop** |
| 638 | 26.6 | Wildlife 1,000 (Exotic Husbandry) |
| 771 | 32 | Plants 3.5M (Growth Accelerant band) |
| 1,650 | 69 | Wildlife 250k (Feed Maker Mk II) |
| 1,861 | 78 | Wildlife 500k (Deep Exotics) |
| 1,922 | 80 | Wildlife 600k (Habitat Mk II) |
| 2,489 | 104 | Wildlife 2M |
| **2,709** | **113** | **Plants 5M (pillar complete)** |
| **3,827** | **159** | **Wildlife 5M (pillar complete)** |

From a fresh game add ~15 days: Plants 5M ~128 days, Wildlife 5M ~174 days.

**Mk II timing.** With 8 Mk I the field is the limit, so Mk II gives no speed-up before 2.25M. It is a hard deadline instead: at 2.25M every Mk I stops, so at least 2 Mk II packs (2 x 2,200 = 4,400/h > 2,830/h) plus a Fertilizer stock must be ready by hour 329. The window from the unlock is ~210 h, so it is not tight. Upgrading 2 at 1.25M and retiring the other 6 Mk I then also works (4,400/h capacity).

**Wildlife vs Plants.** Wildlife is never Forage-bound: its demand peaks at ~1,180 Forage/h (236 feed/h) around hour 2,000-2,500 after unlock, under half the field. It only slows Plants: 5M takes 2,380 h after unlock instead of 2,031 h with all Forage (+349 h, ~15 days). Wildlife's own time (3,498 h after unlock) is the same as the optimizer's no-feed-limit run, so the field is not what gates it; Habitat count and fluids are.

Forage split after Wildlife unlock (Forage/h, average over the window):

| Hours after 2.25M | Wildlife avg (peak) | Terraformers |
|---|---:|---:|
| 0-500 | ~5 (13) | 2,825 |
| 500-1,000 | 58 (135) | 2,773 |
| 1,000-1,500 | 317 (579) | 2,514 |
| 1,500-2,000 | 806 (991) | 2,025 |
| 2,000-2,500 | 1,060 (1,182) | 1,771 |
| 2,500-3,500 | 520-820 (1,106) | 2,000-2,300 (Plants done at 2,380) |

## Usage

| | Phase A (to 2.25M) | Phase B (Plants + Wildlife) |
|---|---|---|
| Terraformers | 8 Mk I: avg ~1,270 W, peak 1,440 W | 2 Mk II: avg ~670 W, peak 1,800 W |
| Crop Automators | 8 x 60 = 480 W | 480 W |
| Habitats | - | avg ~1,750 W, peak 2,690 W (16 x Mk II 168 W) |
| Feed Makers | - | 5 Mk II needed at peak (236 feed/h; 7-8 Mk I): avg ~125 W, peak ~300 W |
| **Total (these machines)** | **avg ~1.75 kW, peak ~1.9 kW** | **avg ~3.0 kW, peak ~5.3 kW** (all coincident) |
| Salt | 1,200 total, ~5.7/h from 1.25M (11 % of the 50/h cap, ~0.3 Pioneer trips/h) | ~11,500 total, avg ~4.8/h, max 5.7/h |
| Water (Terraformers) | 0.05 t/Forage from 500k: ~140 t/h, ~36,000 t | ~120-140 t/h until Plants 5M |
| Fertilizer / Accelerant | - | ~23,000 potency (~770 Fertilizer Mk II), ~680 Accelerant (1 per Mk II batch) |
| Life forms: Crowncap seeds | 1 seed per harvest (900 Forage): ~3.1 seeds/h = ~9.4 t/h, ~3.1 t/h of each of the blend's 3 forms | same, while the field runs |
| Life forms: feed | - | 3 t per craft: avg ~15 t/h, peak ~35 t/h over 16 recipes' forms |
| Exotic fluids | - | ~100,000 t over the run ([wildlife.md §1l](../cheatsheet/wildlife.md) Mk II totals, untreated), ~29 t/h avg |

Power excludes Refiners, Exotic Caps/Taps (30-48 W each), pumps and everything else on the grid.

## Sensitivity

- **Yield Amplifier always on (x3, ~8,500 Forage/h):** 2.25M at 166 h (6.9 d), Plants 5M 679 h after unlock. Needs 4 Mk II and ~17 salt/h. Wildlife unchanged.
- **10 Habitats instead of 16:** Wildlife 5M at 5,265 h after unlock (+1,770 h); Plants 5M slightly sooner (2,179 h after unlock).

## Risks the model ignores

- **Crowncap seed forms:** ~3.1 t/h of each of its 3 blend forms, for the whole run. If one is a rare form (site ceiling ~2.0 t/h), the fill cannot be kept at 2,830/h. Check the save's Crowncap blend.
- Drone trips for ~10-45 t/h of life forms, Fertilizer crafting (~770 Mk II), and Habitat/Feed Maker slot caps are assumed solved.
- Wildlife numbers come from the optimizer's full-support model (strict schedule order); the planner's out-of-order Breakthroughs make it a bit faster.

## Yield Amplifier timing

Apply it from its unlock until Plants reach 5M (the Harvester already applies a dose whenever one is at home, [bio_seeds_planting.md §1k](../cheatsheet/bio_seeds_planting.md)). It has no Plants threshold: the blueprint unlocks with the Spire order "Neutron Capacitor Order", and each dose needs a Neutron Capacitor, so Neutronium (Heavy Drill at Oxygen 2,500, Deep Sonar at Pressure 60) and the "Neutronium Order" / "Cobalt Stockpile" orders come first ([recipes_fabricator.md](../database/recipes_fabricator.md)). The walkthrough places that around Wildlife 500k (~day 78 here). From there, with ~1.6M Forage left (Plants ~4.5M), the x3 field (~7,600 Forage/h left after Wildlife) finishes Plants in ~215 h instead of ~855 h: ~27 days sooner, ~9 doses, 4 Mk II Terraformers, ~15 salt/h. Open question: whether finishing Plants earlier reaches the nuclear reactor sooner; to verify.
