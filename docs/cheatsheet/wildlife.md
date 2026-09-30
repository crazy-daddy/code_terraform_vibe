# Wildlife (Habitats, stages, Insight, traits)

Game data read from the decompiled simworker (`internals/terraform_decompiled/simworker/deobfuscated.js`); the split `docs/` pages only describe it in prose. These are game constants, not our tunables. Live reads stay authoritative: `journal.cataloged_creatures()` (rarity, feed, `revive_reagents`), Habitat `required_*()` / `*_band()` / `next_*()`, `get_bonus_tree()`.

### 1l. Wildlife reference

**Revival.** `set_revival_target(id)` (spends nothing, grants no Insight; from here the species' Adaptation can be bought with Insight already earned elsewhere) → stage `revive_feed_required` (2) feed + reagents → `revive()`. Reagents = the five Shop lab reagents (`alkaline_buffer`, `cryo_solvent`, `protein_marker`, `chelating_agent`, `enzyme_solution`), same quantity of each: common 1, uncommon 2, rare 3, legendary 5 (one set 1,243 cr). Shop purchases land at home; only a home Habitat's `reagents` input can connect Base Inventory. Rearing 12 world hours with every active input healthy; founding population 4 (+ founding bonuses). Habitat kit 100,000 cr; Mk I 175,000 capacity, Mk II pack (fabricated, unlocks at 600,000 Wildlife) 350,000.

**Capacity and overcrowding.** Base capacity by stage (`dE`): 500 / 5,000 / 50,000 / 175,000 / 175,000, × 2 at Mk II, × the outpost overcrowding factor. Habitat, Feed Maker and Refiner are slot-using `throughput` buildings. Soft cap: home 25, founded outpost 20, +5 with `outpost_expansion_unlock`, +1 at home with `weather_program_unlock` (compensates the free Weather Station; the +1 is tied to the unlock and the home outpost, not to where the station stands). Each slot-using building over the cap costs every `throughput` building there 10 % (floor 20 %); for a Habitat that lowers capacity, not breeding speed. Each capacity is 2× its next stage threshold, so below a factor of 0.5 a colony can't reach the next stage. Tanks and warehouses use a slot but are `exempt` from the penalty. Treat the cap as hard: one building over already costs 10 % everywhere.

**Rarity** (static creature table `ak`, same on every world, hidden until cataloged):
- Common: `salt_tortoise`, `magmatic_annelid`
- Uncommon: `mantle_strider`, `glasswing_mantis`, `mycelial_husk`, `veil_mantle`
- Rare: `ferric_sea_lily`, `tidal_cephalopod`, `hollow_choir`, `bone_walker`, `hive_sentinel`, `vent_drifter`, `vault_crab`, `crustal_echo`
- Legendary: `glacial_wyrm`, `spire_drake`

Breeding rate multiplier by rarity: 1.0 / 0.75 / 0.5 / 0.3.

**Stages** (`kq`, thresholds 250 / 2,500 / 25,000 / 175,001): 0 Founded, 1 First Breeding, 2 Self-Sustaining, 3 Thriving, 4 Abundant (Mk II only). Population never falls; unmet inputs only stop breeding.

**Consumption per new individual** (before trait reductions): 0.1 feed (one 100-Forage recipe = 20 feed = 200 individuals), 0.0008 t gas, 0.0008 t liquid, only while that input is active. A full Mk II colony: ~35,000 feed, ~280 t of each fluid.

**Breeding rate** (individuals/h) = 0.0144 × F(population) × rarity multiplier × efficiency × (1 + speed bonus) × (1 + momentum bonus × momentum) × (1 + brood bonus). Speed bonuses multiply each other ((1+a)(1+b)…, then capped); brood, momentum and ceiling bonuses add. F(p) = p up to 10, 10 × (p/10)^0.85 up to 5,000, then saturates so the rate tops out at 150/h (× (1 + rate-ceiling bonus)). Untreated full-support hours per stage (0 → 4):

| Rarity | Founded | First Breeding | Self-Sustaining | Thriving | Abundant | Total |
|---|---|---|---|---|---|---|
| Common | 351 | 310 | 464 | 1,123 | 1,169 | 3,417 h (142 d) |
| Uncommon | 468 | 413 | 619 | 1,497 | 1,559 | 4,556 h |
| Rare | 702 | 619 | 929 | 2,246 | 2,338 | 6,834 h |
| Legendary | 1,170 | 1,032 | 1,548 | 3,743 | 3,897 | 11,390 h |

4 → 10 individuals (the first Insight) takes ~64 h for a Common, longer by rarity; founding bonuses skip part of it.

**Enclosure buffer.** Intake adds to the gas/liquid buffer; a different fluid replaces the buffer (old contents lost). Every buffer bleeds 0.5 t/h while non-empty, active or not. Bleed outweighs consumption (0.12 t/h at the 150/h ceiling), so fluid cost scales with time spent in a stage: faster breeding saves fluid. Keep inactive buffers empty.

**Fluid totals, untreated** (band-low fill + 0.5 t/h bleed + 0.0008 t per birth, summed over the stages each fluid is active; traits that speed breeding cut these):

| To | swamp_gas | ammonia | sulfur_gas | chlorine | brine | cryofluid | quicksilver |
|---|---|---|---|---|---|---|---|
| Mk I (175k) all 16 | 6,686 | 6,686 | 19,821 | 4,683 | 16,417 | 6,167 | 0 |
| Mk II (350k) all 16 | 9,329 | 9,329 | 30,614 | 8,940 | 20,295 | 19,040 | 4,877 |

Per species to 350k, t: Common ~1,660 of its gas. Uncommon ~2,710 gas + ~2,090 brine. Rare ~560 base gas + ~3,420 sulfur_gas + ~1,490 brine + ~1,610 cryofluid. Legendary ~1,610 sulfur_gas + ~4,470 chlorine + ~3,080 cryofluid + ~2,440 quicksilver.

**Bands.** Centre 450 t in the enclosure; half-width by tightness 0–4: ±200 / ±150 / ±100 / ±60 / ±40 t, × (1 + band-tolerance bonus). In band → input efficiency 1; outside, linear to 0 over 200 t; wrong fluid → 0. Breeding efficiency = min over active inputs (feed present → 1, absent → 0).

**Fluid per species** (`bk`: base → apex):

| Species | Rarity | Gas base → apex | Liquid base → apex |
|---|---|---|---|
| salt_tortoise | common | swamp_gas | none |
| magmatic_annelid | common | ammonia | none |
| mycelial_husk | uncommon | swamp_gas | brine |
| mantle_strider | uncommon | ammonia | brine |
| glasswing_mantis | uncommon | swamp_gas | brine |
| veil_mantle | uncommon | ammonia | brine |
| tidal_cephalopod, vent_drifter, hollow_choir, crustal_echo | rare | swamp_gas → sulfur_gas | brine → cryofluid |
| vault_crab, bone_walker, hive_sentinel, ferric_sea_lily | rare | ammonia → sulfur_gas | brine → cryofluid |
| glacial_wyrm, spire_drake | legendary | sulfur_gas → chlorine | cryofluid → quicksilver |

**Which input is active per stage** (`Hq`; value = band tightness, "apex" = apex fluid):

| Rarity | Stage 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| Common | feed | feed | feed | gas 0 | gas 0 |
| Uncommon | feed | gas 0 | gas 1 | gas 2, liquid 0 | gas 3, liquid 1 |
| Rare | feed | gas 0 | apex gas 1 | apex gas 2, liquid 0 | apex gas 3, apex liquid 1 |
| Legendary | feed | gas 0 | gas 1, liquid 0 | apex gas 2, liquid 1 | apex gas 3, apex liquid 2 |

Stage 0 needs feed only for every species, so all 16 can be revived and grown to 249 without fluids. Sulfur gas / cryofluid need the Refiner + tar; chlorine / quicksilver need Deep Exotics (500,000 Wildlife).

**Insight.** One shared pool, earned by each colony's population growth along (population → cumulative Insight, linear between): 4 → 0, 10 → 1, 100 → 1.5, 1,000 → 2.25, 10,000 → 3, 50,000 → 4, 175,000 → 5.5, 350,000 → 7. A founding bonus is credited at establishment: a colony founded at 10 (crustal_echo's +6) earns its first Insight the moment rearing ends. 16 × 7 = 112 total; all 32 nodes cost 80. Adaptation: 1 Insight, this species only. Breakthrough: 4 Insight + that species at 10,000 population, all species. Buy with `unlock_bonus(node_id)`; results `ok`, `unknown_node`, `already_purchased`, `population_locked`, `insufficient_insight`.

Global caps on stacked bonuses (`xG`): breeding speed +150 %, brood yield +35 %, momentum +30 %, natural rate ceiling +50 %, band tolerance +50 %, feed demand at least 25 % of base.

**Life-form supply vs feed demand.** Biosites are a static table (`Sy`/`hy`): 7 per biome at fixed coordinates, same forms and tons on every world; scanning only reveals them. Per biome the 6 forms are 3 common (3 sites, ~93–101 t total), 2 uncommon (2 sites, ~87–94 t), 1 rare (1 site, 72 t, shared with a common form). A site regrows only after it is fully emptied, after 9 / 18 / 36 h (rarest form on the site). Theoretical ceiling per form (every site drained the moment it regrows): common ~6.4–6.9 t/h, uncommon ~4.8–5.2 t/h, rare 2.0 t/h. Feed demand: 1 t of each ingredient per recipe run (20 feed = 200 individuals), 1,750 t per ingredient per species to 350k untreated (~70,000 t for all 16). Per form that averages ~0.15–1 t/h and peaks under ~0.8 t/h with every colony at the 150/h ceiling, well inside the ceilings; the real limit is drone trips and hauling forms home.

**Traits** (`MG`, texts from the game strings):

| Species | Adaptation (species, 1 Insight) | Breakthrough (global, 4 Insight + 10k) |
|---|---|---|
| salt_tortoise | Saltwise Digestion: feed −60 % | Ancient Nest: +15 % speed below 2,500 population |
| magmatic_annelid | Efficient Gut: +15 % offspring | Chain Fission: +5 % offspring |
| mycelial_husk | Symbiotic Digestion: feed −40 %, bands +25 % | Planetary Mycelium: +1 % speed per other established species (max 12 %) |
| mantle_strider | Lean Grazer: +35 % speed below 2,500 | Continental Stride: natural rate ceiling +10 % |
| glasswing_mantis | Prismatic Tolerance: bands +40 % | Perfect Stillness: up to +8 % speed over one day of full support |
| veil_mantle | Pliable Enclosure: up to +18 % speed over one day of full support | Complete Veil: bands +15 %, +2 founding |
| vault_crab | Sealed Rations: feed −60 % | Ancestral Vault: feed −15 % |
| tidal_cephalopod | Tidal Recycling: keeps base liquid (brine), liquid band +25 % | Ocean Mind: +10 % speed above 10,000 |
| bone_walker | Adaptive Marrow: keeps base gas and liquid (ammonia + brine) | Walking Colony: +1.5 % speed per stage (max 6 %) |
| vent_drifter | Vent Exchange: keeps base gas (swamp_gas), gas band +25 % | Endless Current: up to +7 % speed over one day |
| hive_sentinel | Many Chambers: feed −50 %, +4 founding, +20 % offspring | Planetary Sentinel: +2 founding, +1 % speed per other established species (max 12 %) |
| hollow_choir | Harmonic Structure: +30 % speed | Worldsong: +10 % speed |
| ferric_sea_lily | Ferric Recycling: feed −50 %, bands +20 % | Iron Garden: bands +10 % |
| crustal_echo | Recorded Generation: +6 founding, +3 % speed per stage (max 12 %) | Recursive Brood: +5 % offspring |
| glacial_wyrm | Sealed Metabolism: feed −50 %, keeps base liquid (cryofluid) | Worldcoil: natural rate ceiling +10 % |
| spire_drake | Spire Nursery: +2 founding, +45 % speed below 2,500 | Sky Dominion: +12 % speed |

"Keeps base fluid" Adaptations skip the apex switch: `bone_walker` reaches full size on ammonia + brine (no Refiner), `tidal_cephalopod` never needs cryofluid, `vent_drifter` never needs sulfur_gas, `glacial_wyrm` never needs quicksilver.

### 1l-1. Revival and Insight schedule (`9_wildlife`)

Constants and the model live in `lib/wildlife_data.py` / `lib/wildlife_model.py` (pure, shared with `devtools/wildlife_optimizer.py`). The optimizer beam-searches the order of revivals, Adaptations and Breakthroughs. It assumes full support, feed never short, and fluids ready at fixed lead times after their research. It scores a schedule by hours until Wildlife reaches 600,000 (Habitat Mk II). The result is `WILDLIFE_SCHEDULE`.

Policy: `magmatic_annelid` and `salt_tortoise` revive first, without an Adaptation (`WILDLIFE_BOOTSTRAP`). Every other revival buys its Adaptation first. Steps run strictly in order, so a `break` step holds Insight until its source colony has 10,000 individuals.

Optimizer defaults: 10 Habitats (Mk I), common fluids 72 h and refined fluids 168 h after Exotic Husbandry (1,000 Wildlife), deep fluids 168 h after Deep Exotics, 2 Feed Makers. Results (2026-09-30):

| Scenario | Hours to 600k | 1k / 250k / 500k at |
|---|---|---|
| Schedule (beam) | 1,763 (73 d) | 380 / 1,406 / 1,680 h |
| Default order (rarity, founding first) | 1,959 | 414 / 1,534 / 1,836 h |
| Hold Insight early for the `salt_tortoise` Breakthrough | 2,149 | 399 / 1,566 / 2,006 h |
| 16 Habitats | 1,670 | 375 / 1,386 / 1,606 h |
| Revive without Adaptation allowed (`--allow-unadapted`) | 1,675 | 337 / 1,350 / 1,603 h |
| Fluid leads 24/72 h or 240/480 h | 1,760 | ~same |
| 1 Feed Maker | 1,762 | ~same |

What the runs show:
- Filling every Habitat early matters most. The order among the early revivals changes the result by under 1 %.
- Holding Insight early for a Breakthrough costs about 20 %: it blocks revivals for hundreds of hours.
- Breakthroughs come late on their own. The Commons reach 10,000 first, at about 830 h (`magmatic_annelid`) and 920 h (`salt_tortoise`).
- Reviving without the Adaptation saves about 5 %, even for crustal_echo's +6 founding, because breadth earns Insight sooner.
- Fluid timing barely matters to 600k. Commons need gas only from 25,000, and the others stall at 250 while still earning Insight.
- Peak feed demand is about 100 feed/h, which is 2 Feed Makers but about 500 Forage/h. Forage, not Feed Maker count, is the likely real limit.

Re-run by hand when an assumption changes: `python devtools/wildlife_optimizer.py --help`.
