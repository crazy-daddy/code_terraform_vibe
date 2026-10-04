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

**Enclosure buffer.** Intake adds to the gas/liquid buffer; a different fluid replaces the buffer (old contents lost). Every buffer bleeds 0.5 t/h while non-empty, active or not, and also while the colony starves. Bleed outweighs consumption (0.12 t/h at the 150/h ceiling), so fluid cost scales with time spent in a stage: faster breeding saves fluid. Keep inactive buffers empty. Intake and bleed run in one step (simworker `meterInputs`), only for a powered Habitat that is rearing or below its capacity: an **unpowered Habitat's buffers are frozen** (no intake, no bleed), and so are a colony's **at capacity** (capped).

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

Constants and the model live in `lib/wildlife_data.py` / `lib/wildlife_model.py` (pure, shared with `devtools/wildlife_optimizer.py`). The goal is the Wildlife pillar, the *Wildlife Teeming* achievement at 5,000,000. The most possible is 16 x 350,000 = 5,600,000, so at most 600,000 can be missing: every species but about one must grow nearly full. That needs the Refiner (sulfur_gas/cryofluid) and Deep Exotics (chlorine/quicksilver for the Legendaries' later stages). Refined fluids are used by Habitats only; no other recipe or order consumes them.

The optimizer beam-searches the order of revivals, Adaptations and Breakthroughs and scores a schedule by hours to 5,000,000. The model assumes:
- Full support, and feed limited only by Feed Maker output (2 Feed Makers, Mk II at 250k). A Feed Maker is feeder-bound, not craft-bound: `feed_cycle_hours()` = max(craft, Auto Feeder time for 100 Forage + 3 forms + 20 feed out at `FEEDER_HOURS_PER_UNIT = 0.01` h/unit × `FAST_FEEDERS_MULTIPLIER = 0.5`) / Mk II speed = 0.615 h Mk I (32.5 feed/h), 0.41 h Mk II (48.8 feed/h).
- Fluids ready at fixed lead times: common 120 h and refined 240 h after Exotic Husbandry (1,000 Wildlife); deep 240 h after Deep Exotics (500,000). The lead time covers building caps, taps and pipes.
- Habitat Mk II 72 h after 600,000.
- Parking: a colony at the Mk I ceiling (175,000) frees its Habitat until Mk II, then is rehoused before any revival; a colony at 350,000 frees its Habitat for good.

The results are `WILDLIFE_SCHEDULES`, one per Habitat count (5, 10, 16). `schedule_for(habitats)` picks the entry with the largest key not above the live count.

Policy: `magmatic_annelid` and `salt_tortoise` revive first, without an Adaptation (`WILDLIFE_BOOTSTRAP`). Each later revival either buys its Adaptation first (`revive`) or skips it (`revive_raw`), whichever the optimizer found faster. The optimizer runs steps strictly in order, so a `break` step holds Insight until its source colony has 10,000 individuals; the planner lets later purchases pass a held step from Insight above its cost (§1l-2).

Results (2026-09-30, beam width 6):

| Habitats | Schedule | Default order (rarity, founding first) | 600k / 2M reached | Peak feed / Forage per h |
|---|---|---|---|---|
| 5 | 9,925 h (414 d) | 15,055 h | 2,745 / 5,000 h | 84 / 419 |
| 10 | 5,267 h (219 d) | 7,842 h | 1,829 / 2,714 h | 203 / 1,017 |
| 16 | 3,517 h (147 d) | 4,025 h | 1,593 / 2,161 h | 236 / 1,180 |

What the runs show:
- Habitat count is the big lever: 16 Habitats reach 5M in two thirds of the time 10 need.
- The Legendaries and other slow Rares are revived early, because the slowest colonies set the finish.
- Holding Insight early for a Breakthrough costs 4-10 % (the gut-order baseline in the optimizer output).
- Insight stops being scarce after about 1,000 h; by 5M every node is bought and about 26 Insight is left over.
- Parking at the Mk I ceiling saves 1-2 % with 5-10 Habitats and nothing with 16.
- Feed demand reaches 200+ feed/h and means about 1,000-1,200 Forage/h. 2 Mk II Feed Makers make 98 feed/h: enough up to 600k, too few for 5M (16 Habitats, default order: 5,114 h with 2, 4,284 h with 3, 4,043 h with 4, 4,013 h with 5 or unlimited). Plan 4 Feed Makers for 5M, within the home slot cap. Forage supply is the other limit.
- For 600k alone (the Mk II gate), skipping the Refiner costs only about 5 %. For 5M the Refiner is required.

Re-run by hand when an assumption changes: `python devtools/wildlife_optimizer.py --help`.

### 1l-2. Wildlife automation (`9_wildlife`)

Three parts. Habitat and Feed Maker methods are self-only, so each machine runs a thin script (`bio/habitat.py`, `bio/feed_maker.py`); the decisions are made once per game hour by the planner inside `control_room_automation.py`. Shared keys and tunables: `lib/wildlife_common.py`. Time: one game hour = 25 s of script time = 250 ticks.

**Planner** (`lib/wildlife_planner.py`, `plan_if_due()` every `PLAN_TICK_INTERVAL = 250` ticks; no-op without Habitats). It reads a snapshot (Habitats on the network, `wildlife.status`, Feed Maker recipes from `wildlife.feed`, cataloged creatures, home stock), runs the pure `build_plan()` as a chain of `atomic.run_atomic()` calls, each bounded by the Habitat count (one whole plan would exceed the 10,000-step callback cap, `docs/cheatsheet/dev_workflow.md` §1d-1): the schedule walk, the colony model slices, the fluid ration, then feed demand with life-form targets, wakes and alerts (worst case 16 colonies with every node bought: largest call ~3,800 steps, `devtools/step_profile.py wildlife_plan`). Feed multipliers come from `wildlife_common.feed_multipliers()`, which computes the Breakthrough part shared by every species once. It then writes `wildlife.plan` and publishes.
- **Schedule walk**: bootstrap `revive_raw` of `WILDLIFE_BOOTSTRAP`, then `schedule_for(live Habitat count)`, in order like the optimizer. A step that can never run is skipped and listed in `progress.skipped` with its reason (`not_cataloged`, `no_recipe`, `no_habitat`; species already revived or node already bought are dropped silently). A step that can run later (`insight x < cost`, Breakthrough source below 10,000, adapt of a species not revived, its Habitat already buying this pass) is held with its cost reserved; the first is `progress.waiting`. Revivals stop at the first held step. A later Adaptation or Breakthrough still runs from Insight above the reserve, so a population-gated Breakthrough holds only its own 4 Insight. A revive takes the lowest free Habitat (`assign[habitat] = {species, adapt_first}`); a `revive` step also queues `buy[habitat] = "adaptation"` and commits 1 Insight. One purchase per Habitat per pass. An assignment stays until the colony is established. Operator `wildlife.targets` puts its species' revivals first and drops all other revivals.
- **Completion**: `WILDLIFE_COMPLETE_POPULATION = 5,000,000` (`wildlife_data.py`; the game's Wildlife pillar complete, no more Terraform Index). `plan_if_due()` reads `wildlife_sensor.get_value()` before the snapshot; at or above it the pass is skipped for the rest of the run (latched, sensor no longer read; a missing or failing sensor is swallowed and planning continues). The first time, it logs one info line, withdraws the planner's life-form requests (`clear_requests(REQUESTER_ID)`) and writes an empty plan (`assign`/`buy`/`feed_demand`/`form_targets`/`fluid_ration` `{}`, `forage_reserve` 0, `complete` true). The AUTOMATION card shows `COMPLETE_SUMMARY` ("Wildlife complete"). Habitats then keep their established colonies until feed runs out (`no_feed` park), empty ones park `empty`; Feed Makers see no deficit and park.
- **No parking**: colonies are never undeployed at the Mk I ceiling (the optimizer's schedules assume it; it gains 1–2 % at 5–10 Habitats, nothing at 16). With every Habitat housed, later revive steps are skipped as `no_habitat`.
- **Colony model rank**: per established colony, hours to its Mk I/II ceiling at the full-support model rate (`wildlife_model.breeding_rate`, efficiency 1, bought nodes). The live rate is not used: a starved or rationed colony's live rate drops and would reorder the ranks every pass. Runs atomically in `MODEL_CHUNK = 4`-colony slices (`run_batched`); one `breeding_rate` with every node bought is ~600 steps. Feed demand and the fluid ration both rank by it, slowest first.
- **Feed demand** `feed_demand[feed_item] = [home stock target, priority, short]`, listed while home stock (Warehouses + Depots + Inventory) is below the target. Priority (lower first): `PRIO_RESERVE = 0` revival staging (target = `REVIVE_FEED_REQUIRED` 2 + `REARING_FEED_EXTRA = 3` − bin); `PRIO_URGENT = 1` established with bin + home stock below its cover = max(`FEED_TOPUP_TARGET`, `FEED_URGENT_H = 4` game hours of its use), target = cover − bin (an empty bin asks for 50, which is also the parked `no_feed` wake level); `PRIO_FLUID_HELD = 2` established with a non-empty gas or liquid buffer (it bleeds while starved, until it parks); `PRIO_REARING = 3` (target = `FEED_TOPUP_TARGET` − bin, ready for the first top-up); `PRIO_GROWING = 4` established, feed-only. Ranked classes: `PRIO × PRIO_RANK_SCALE (100) + rank`; urgent ranks emptiest bin first, then slowest, the two buffer classes by the model rank. Once a colony's cover is met it drops back to its buffer class, so no colony starves while others build their 24 h buffers. Established target = `FEED_BUFFER_H = 24` game hours of its feed use (live rate × 0.1 × feed multiplier from bought nodes; the model rate when the live rate reads 0, since `breeding_rate()` is 0 while blocked, an empty bin included), at least one craft (20), plus what the bin lacks to `FEED_TOPUP_TARGET`. A capped colony (rate 0) has no target. Feed Makers are woken (`wake_kind`) while any item is short.
- **Fluid ration** `fluid_ration = {habitat: [denied fluids]}` (empty while supply covers every colony) and `fluid_supply = {fluid: [tank stock t, inflow t/h, tick, total need t/h]}`. Consumers: established colonies below their ceiling whose band (or pre-fill) needs the fluid, from the status `gas`/`liquid` entries. Need = model rate × 0.0008 + bleed 0.5 + (band centre − level, if positive) / `RATION_RUNWAY_H = 24`. Stock = `level()` of every tank eligible for the fluid (`discover_network_buildings(..., fluid_id=...)`). Gross inflow = stock change since the last pass + the Habitats' port `flow_rate()`, smoothed (EMA `RATION_INFLOW_ALPHA = 0.3`); taps cycle in under a game hour, so the hourly pass sees a near-steady inflow. Budget = inflow + stock / `RATION_RUNWAY_H`. Colonies are granted slowest first while the summed need fits; the walk stops at the first that does not, so stock banks up for it instead of going to faster colonies. A colony denied last pass must fit in budget × (1 − `RATION_HYSTERESIS = 0.1`). The first pass (no inflow estimate yet) grants all. Runs as one atomic call (worst case 16 colonies × 2 media ~2,900 steps, `devtools/step_profile.py wildlife_ration`).
- **Forage reserve** `forage_reserve` = 100 Forage per craft that covers the shortfall, plus one craft. The home Plant Terraformer's `available()` leaves it: feed comes before Plants.
- **Life forms**: `form_targets` = per form, (`FORM_BUFFER_H = 48` game hours of each active species' crafts + its open shortfall in crafts, at least `FORM_REQUEST_MIN_CRAFTS = 20`) × units per craft, capped at `FORM_REQUEST_CAP = 1900` (one Warehouse slot). Published as home requests by requester `feed_maker` (`logistics_requests.publish_requests()`, §2i). A form another requester owns at home (the Seed Maker's) is left to it.
- **Wakes and alerts**: a parked Habitat is woken when it has a queued purchase (`buy`; only the source species' Habitat can buy its nodes), when it gets an assignment, when its feed is back in home stock (≥ `FEED_TOPUP_TARGET`, parked `no_feed`), when a `habitat_upgrade_pack_mk2` is in Inventory (parked `capped`), or when its fluid is granted again (parked `rationed`). Habitats parked `capped` / `no_feed` and every Habitat denied a fluid (`rationed`) go into `alerts`, the AUTOMATION card summary ("wildlife: N capped at Mk I (Mk II needed), N without feed, N fluid-rationed, N feed recipe(s) locked"; `IDLE_SUMMARY` hides it) and a `notify()` on change. Ration changes are logged at info level, the per-fluid budget at `debug()`. `wildlife.readiness` lists uncataloged species and locked recipes (warned on change).

**Habitat** (`lib/habitat.py`, `HabitatController`). State is read live each step.
- Assigned, empty: `set_revival_target()`; buys `plan.buy` (node id from the live `get_bonus_tree()` by slot); with `adapt_first` it waits (`awaiting_insight`) until the Adaptation is bought. Stages `REVIVE_FEED_REQUIRED + REARING_FEED_EXTRA` feed in its own bin (the reservation: nothing else can take it; wrong feed is ejected) and the reagents (`revive_reagents` from the journal; shortfall bought through the cash manager, consumer `wildlife_reagents:<id>`, operating), then `revive()`. A failed rearing (`rearing_failed()`) is retried up to `MAX_REVIVE_RETRIES = 3` (each retry spends reagents), then blocker `rearing_failed`.
- Rearing (12 game hours = 300 s): keeps feed ≥ 1; no fluids at stage 0. Rearing eats no feed (no births).
- Established: tops the bin up to `FEED_TOPUP_TARGET = 50` (input buffer) below `FEED_TOPUP_AT = 30`; buys queued nodes. Gas and liquid each: band `[]` → intake 0; held fluid ≠ required → intake 0, `purge_reserve` + `purge_intake`; level > high + `PURGE_MARGIN_T = 100` → purge and refill; fluid in its `plan.fluid_ration` entry → intake 0, no purge (the held buffer keeps it breeding while in band), blocker `fluid_rationed`; else route a tank holding the required fluid (a declared source whose link carries, or whose tank is assigned to, another fluid is disconnected first and the inlet purged: the router accepts any flowing link; `FluidInputRouter`, `discover_network_buildings(tank types, fluid_id=...)`, own outpost first; none → blocker `no_<fluid>_source`) and set intake = births × 0.0008 + bleed 0.5 + `REGULATOR_GAIN_PER_H = 0.5` × (centre − level), clamped to [0, `MAX_INTAKE_T_PER_H = 50`]. A medium that opens at the next stage is filled toward its next band once the stage is less than `PREFILL_LEAD_H = 12` game hours away.
- Poll: established → in time for the next top-up (`next_poll()`: 0.8 × time until `FEED_TOPUP_AT` at the current burn, within [`POLL_MIN_S = 5`, `POLL_MAX_S = 60`] s; at the 150/h ceiling with no feed reduction a full bin lasts ~83 s); staging/rearing `POLL_STAGING_S = 10` s.
- Status `gas` / `liquid` entry: `[held fluid, level t, band, required fluid, port flow_rate() t/h]` (`wc.MEDIUM_*` indices); the required fluid includes a pre-fill.
- Parks (`ParkRequester(id, "habitat")`, `WAKE_AFTER_TICKS["habitat"] = 6000`) when empty and unassigned (`empty`), established without feed in the bin or at home (`no_feed`; both intakes set to 0 first), at the Mk I ceiling (tier 1, headroom 0, population ≥ 175,000: `capped`), or rationed with an active buffer out of its band (`rationed`). Never while staging or rearing. An unpowered Habitat only pauses (no breeding, no rearing progress, no failure, buffers frozen: no intake and no bleed, §1l "Enclosure buffer").
- Power: base Mk I 40 W / Mk II 144 W + min(24, population / 1,000 × 2) W, drawn whenever powered, even empty (simworker `Jhe`). 16 Habitats: 640 W empty, 1,024 W at Mk I ≥ 12,000 each, 2,688 W at Mk II. Shed last (tier 3, §1a-0).

**Feed Maker** (`lib/feed_maker.py`, `FeedMakerController`). Publishes its unlocked recipes (`{recipe_id: inputs}`, refreshed every `RECIPE_REFRESH_TICKS = 1200`). Deficit per recipe = plan target − home stock − its own output bin, home stock from one `logistics_requests.outpost_stock()` walk over every demanded feed and recipe input. Picks the lowest priority, then the largest deficit, among recipes whose inputs are all in its stockpile or at home; the set recipe stays while it is short and nothing in a better class (priority // `PRIO_RANK_SCALE`) is, so rank changes inside a class don't switch it. **Spread**: each maker publishes its pick (`picked`, `None` while idle); a recipe is skipped once `min(MAX_MAKERS_PER_RECIPE = 2, crafts in its deficit)` other fresh makers picked it (two crafts fill a Habitat's 50-feed bin; more makers only queue on its feeder). On its current recipe a maker counts only makers with a lower id, so of a crowd the lowest ids keep it. While a craft of the picked recipe runs, the stock walk and the pick are skipped. Switching waits for the running craft (and any progress), then `set_recipe()` directly: it accepts a loaded stockpile and is blocked only by a different feed in the output bin (simworker; `clear_recipe()` needs an empty output bin, not an empty stockpile). The loaded Forage carries over; items the new recipe doesn't use are ejected only when they leave no room for its craft, or when a `take()` returns `slots_full` (8 distinct materials, §2a-0-2 Material slots; single leftover forms from partial loads fill it). Loads one craft (1 of each form, then 100 Forage) and preloads the next when the 200-unit stockpile has room. Stock lands when a transfer starts and the feeder then cools down for the units moved, with input and output sharing one feeder endpoint; loading Forage last lets the craft run during its cooldown (100 units, longer than the craft). The Forage is taken only once every form is in (a busy or short form holds it back to the next step), so its landing always starts the craft. Inputs stay in the stockpile until the craft ends, so a 103-unit preload never fits during a craft. Feed goes first straight into the local Habitat housing its species (`habitat_targets()`: Habitat ids at the Feed Maker's outpost, re-listed every `HABITAT_MAP_REFRESH_TICKS = 3000`, joined with fresh `wildlife.status` entries whose `feed_item` matches and `parked` is empty, capped at `FEED_TOPUP_TARGET` − published `feed_level`; a parked Habitat is skipped because the planner wakes it on storage stock only), via `storage.push_to_targets()`; the rest drains to a home Warehouse (`drain_port_storage_first`), Inventory as fallback. The planner sees the bin rise only at the Habitat's next publish, so up to one extra craft can land in storage. Soft-shed (`power.shedded`, tier 2): starts nothing new. `take()`/drain calls return once their feeder transfer ends, and the craft runs during the Forage transfer, so a step that moved or drained items polls again after `FAST_POLL_S = 0.2` s; otherwise `ACTIVE_POLL_S = 2` s while busy (a craft is 0.3 game h = 7.5 s), `IDLE_POLL_S = 20` s. `wildlife.feed[id]` is rewritten when recipe, run state or blocker change, else every `PUBLISH_REFRESH_TICKS = 600`. Parked after 3 idle steps (`WAKE_AFTER_TICKS["feed_maker"] = 3000`). Draw 30 W while crafting (Mk II 60 W).

**Refiner** (`lib/refiner.py`, `RefinerController`). Raw exotic fluid + tar → creature-grade fluid (`refine_sulfur_gas`, `refine_cryofluid`: 2 tar, 0.3 h, 30 W; `refine_chlorine`, `refine_quicksilver`: 5 tar, 0.4 h, 48 W; 4 t in, 4 t out). Exotic Caps/Taps stand in the field, outside any outpost, and fill raw tanks (`lib/exotic_cap.py`); the Refiner draws only from tanks. What to refine: one network tank sweep every `TOTALS_REFRESH_TICKS = 300` sums level/capacity per fluid over tanks latched or assigned to it (`fluid_totals()`). Candidates (`recipe_candidates()`): raw fluid ≥ `RAW_MIN_TONS = 4` t in tanks (or a craft already in the input port) and refined tanks below `REFINED_FULL_FRACTION = 0.95` with free room ≥ (1 + other Refiners on that recipe) × out port capacity (read from the port, `OUT_PORT_FALLBACK_T = 20`; others counted by `recipe_counts()` from `refiner.status` under their recipe and their `switching_to` target, refreshed with the totals every `TOTALS_REFRESH_TICKS` and re-read on each new switch decision), so output left in a port can drain before the next `set_recipe()`; the lowest refined fill wins. `choose_recipe()`: a recipe runs at least `MIN_RECIPE_TICKS = 1200`; then another candidate takes over when its fill is `SWITCH_MARGIN = 0.20` lower, or after `MAX_RECIPE_TICKS = 6000` so no fluid starves; no candidate → the recipe stays set and the Refiner parks. Switch (`switch_step()`): disconnect the old input and craft out the staged feedstock (≤ `SWITCH_DRAIN_TICKS = 600`), drain a shared output port through the old router (`set_recipe()` rejects `output_busy`), purge a shared input port (ports latch to their first fluid and report no fluid id), then `set_recipe()`. Routing: `FluidInputRouter` from tanks eligible for the raw fluid, own outpost first, only while the recipe has raw supply (else blocker `no_raw_supply`, input left alone); `FluidOutputRouter(local_outpost_id=...)` to tanks eligible for the refined fluid, own outpost's first (power_fluids §1c-5); it is told of a stall once the output port cannot fit another craft (level > capacity − recipe output, 4 t) while `is_stalled()`. Tar: bin refilled to full via `take_item()` from local storage at ≤ `TAR_REFILL_AT = 20`; the outpost stockpile (2,000, of which 150 at need tier) comes from `site_supply.SITE_STOCK_TARGETS["refiner"]` / `SITE_STOCK_NEED["refiner"]`. Soft-shed (`power.shedded`, tier 2): `clear_recipe()` after the running craft; picked again on recovery. Commands: `recipe <id>` pins, `auto`, `purge`. Status in `refiner.status` (`{id: {recipe, switching_to, blocker, outpost, tick}}`, `switching_to` = switch target or `""`, written on change or every `STATUS_REFRESH_TICKS = 600`). Poll `ACTIVE_POLL_S = 2` s busy, `IDLE_POLL_S = 15` s, parked after 3 idle steps (`WAKE_AFTER_TICKS["refiner"] = 3000`).

**Home Warehouse slots** (one item per 2,000-unit slot): the end state needs about 30 life forms (the 16 recipes use all 30), 1 per housed species of feed, Crowncap seed, salt (8 slots falling to 1), Fertilizer/Accelerant 2–3, ~6 for home crafting: ~57–64 slots, plus up to 14 for the garden seed buffer. Tar and Forage do not belong in home Warehouses.
