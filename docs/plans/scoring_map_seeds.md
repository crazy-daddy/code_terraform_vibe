# Scoring map seeds

Goal: rate a world seed before playing it, using the parts of the world the seed decides that change a speedrun. Each part gets its own score; a combined score comes later, once we know how much each part costs or gains in game hours.

Status: part 1 (Harvester field) and part 2 (seed recipes) have tools and first results; the Harvester route is optimised, the seed rescan with it is pending. Part 3 (exotics, vents, oil): only total oil counts; exotics, steam and distance are no criterion.

## Parts of the world a seed decides

| Part | Matters for | Status |
| :--- | :--- | :--- |
| Harvester surface field (`state.harvesting.grid`) | early credits, before the Bio-Loop earns (about the first 0.2 game hours) | tool: `devtools/headless/field.mjs`, `run.mjs --field-seed` |
| Seed recipes (15 random life-form triples, cheatsheet §1i) | life-form demand vs the fixed biosite supply (feed, Forage seeds) | tool: `devtools/seed_quality.py recipes` |
| Exotic deposits (15: position, active/dormant minutes, phase, peak rate; [exotics.md](../gameknowledge/exotics.md)) | Wildlife fluids | part 3: not a criterion |
| Thermal vents (5: position, active 6480–7920 / dormant 2160–3600 min, phase, peak steam 800–1200 t/h) | Thermal Cap steam | part 3: tiebreaker (rates ±7 %, in Pioneer range) |
| Water and oil wells | pumps | part 3: tiers and rates fixed; positions and oil cycles seeded, score: total oil mean (±6 %, ~4 turbines p10–p90); tool: `devtools/headless/sources.mjs` |
| Geological anomalies | | position only |
| Mining sites and POIs | rover and Pioneer ore, outpost founding | not seeded: fixed table (`Ov`) |
| Weather | heater efficiency (about 93 % average) | seeded: `GK()` rolls the day's weather from `mp(seed + dayNumber × 7919)`. Not scored |

## Part 1: Harvester field

**Game logic** (simworker `wE(seed)`, item table `$p`):
- 8 × 24 sectors, start cell E13. Each sector is empty with chance 0.65; otherwise it gets one item, picked by rarity weight from the items allowed at its distance.
- An item type spawns only at a Manhattan distance of at least its `maxDistance` from the start (the game's name; it works as a minimum). So no high-value item can sit next to the base:

| Item | Value | Rarity weight | Minimum distance |
| :--- | ---: | ---: | ---: |
| Soil Sample | 50 | 200 | 0 |
| Basic Plant | 125 | 150 | 0 |
| Organic Matter | 250 | 100 | 2 |
| Mineral Fragment | 425 | 80 | 3 |
| Rare Fungi | 850 | 50 | 5 |
| Crystal Shard | 1,700 | 35 | 7 |
| Alien Fossil | 2,500 | 20 | 9 |
| Exotic Compound | 5,000 | 5 | 12 |

- The field never respawns. Its total value is all the Harvester ever earns from it.
- The field is a pure function of the seed. On load, the game rebuilds it from the seed and keeps the saved grid's cells over it, so collected cells stay empty.

**Tools:**
- `node devtools/headless/field.mjs --seeds 1-20000 [--top N]`: value statistics over many seeds, without the sim (about 1 s).
- `node devtools/headless/field.mjs --show SEED`: prints one field as a map.
- `node devtools/headless/field.mjs --check SAVE`: checks the port against a save's grid. Run it after a game update.
- `node devtools/headless/run.mjs --save SAVE --field-seed SEED ...`: swaps the save's field for that seed's fresh field, keeping the rest of the world. Only the field changes, so runs on different fields are a clean A/B of the field.

**Field value over seeds 1–20,000:**

| | Min | p10 | Median | p90 | Max |
| :--- | ---: | ---: | ---: | ---: | ---: |
| Total value | 7,125 | 14,850 | 19,850 | 25,825 | 40,700 |
| Value within 6 sectors of the start | 1,250 | 3,100 | 4,450 | 6,050 | 10,100 |

The main save (seed 420526420) has 18,275 in total and 3,125 near the start.

**Sim results (2026-10-06):** checkpoint h2 (tick 1193, 550 cr; 3 items already collected), plan `feeders2.2: heat>o2>pressure 12/10/0.3 pw6/3` ([early_optimization.md](../autoplay/early_optimization.md)), each field swapped in fresh. Milestones are read from metrics every 3 game minutes.

| Field seed | Field value | Harvester by 0.1 h | by 0.2 h | by 0.5 h | 10k TP at | 150k TP at | Net worth |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 12412 (best of 20k) | 40,700 | 11,600 | 16,350 | 34,875 | 0.20 h | 3.98 h | 255,757 |
| 3498 | 39,900 | 3,025 | 10,875 | 24,525 | 0.25 h | 4.02 h | 254,972 |
| 4 | 35,050 | 5,675 | 9,500 | 18,400 | 0.20 h | 4.01 h | 249,962 |
| 1 | 26,750 | 3,475 | 5,725 | 23,950 | 0.25 h | 4.03 h | 241,839 |
| 7416 | 24,475 | 3,875 | 7,325 | 13,375 | 0.25 h | 4.02 h | 239,517 |
| 420526420 (main save) | 18,275 | 7,675 | 10,750 | 13,100 | 0.20 h | 4.00 h | 233,321 |
| 3 | 18,700 | 4,475 | 7,000 | 13,350 | 0.25 h | 4.02 h | 233,640 |
| 2 | 17,350 | 2,400 | 8,850 | 15,075 | 0.25 h | 4.04 h | 232,400 |
| 5 | 14,175 | 2,075 | 4,875 | 11,050 | 0.25 h | 4.05 h | 229,234 |

Findings:
- **Time to 150k TP hardly depends on the field:** 3.98–4.05 h over all fields. Net worth follows the field value.
- **The early credits do depend on it:** 4.9k to 16.4k by 0.2 h. Before 10k TP (Ship Computer) the player buys by hand, so a rich early field means fewer waits. The fixed plan in these runs does not show that.
- **Static value is a poor predictor of early income.** Seed 7416 has the most value near the start, but its Harvester earns only 3.9k by 0.1 h; the main save's field earns 7.7k by then with less. The route the Harvester script takes decides it, so score a field by running the script (`--field-seed`, a few seconds to 0.3 h), not by counting.
- Most of a rich field's extra value comes late (0.5 h and after), when the Bio-Loop already earns far more.

**Fresh-game score** (`harvest_model.mjs` fresh mode, `seedscan.mjs --score reach`): run hours from a new game until the Harvester has earned the 25/25 slot build-out. Up to then, the Harvester is the only income, because the Bio-Loop comes online at 1.0 ppt O2, around the time 25/25 is reached. The field's value after that point is only a tiebreaker.
- **Assumption, the opening:** go full O2 until 10k TP, where `solar.py` takes over buying. The build-out is 6 Solar (500) + 3 Batteries (300) + 13 O2 Generators (1,000) = 16,900 cr, minus the 2,500 cr uplink reward and the 3 intro contracts (relay_hack 1,250, xenogenetics 1,400, corrupted_archive 1,500 = 4,150 cr; simworker `Th("intro", …)`) = **10,250 cr from the Harvester**. The contracts are assumed to be clicked before the money is needed. Selling O2 Generators for Heaters right after 1.0 ppt O2 is not planned, to keep operator clicks down. A different opening changes the threshold: rescan with the new figure.
- **Start:** scripts from tick ~50 (about 5 s after the new game, when the sync runner starts). The Scanner sweep follows `scanner.py`. The Harvester waits for 60 scanned sectors (value-density script) or 10 (current script). Clearing mode is left out, because it starts at 25/25, after the threshold.

**Full scan with the value-density script (2026-10-06, superseded by the route below):** all 2,147,483,647 seeds (the game rolls `floor(random × 2147483647)`), Crowncap load ≤ 0.8, scored by time to 10,250 cr. The scan took 1,034 s on 12 threads, and 603M seeds passed the recipe filter. The top 10,000 are in `devtools/headless/.cache/seedscan_reach_script.jsonl` and span 3.6–4.5 min to 10,250 cr. For comparison, the main save takes 19.1 min, and seed 12412 (the richest field in 1–20,000) takes 10.9 min.

Checked with fresh headless games (`run.mjs --seed N --deploy-templates scripts/0_cold_boot`, 0.5 h). Times in run minutes:

| Seed | Crowncap load | to 10,250 | to 14,400 | to 20,000 | cr by 0.5 h | Field total |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1028454550 | 0.76 | 3.9 | 4.2 | 7.5 | 36,700 | 39,700 |
| 2014851714 | 0.65 | 3.9 | 4.3 | 8.8 | 35,925 | 40,400 |
| 311671524 | 0.79 | 3.8 | 4.7 | 10.3 | 29,825 | 32,425 |
| 1119519681 | 0.61 | 3.7 | 4.3 | 10.3 | 26,525 | 27,625 |
| 307438010 | 0.63 | 3.9 | 4.5 | 10.9 | 25,975 | 37,025 |
| 1184249605 | 0.79 | 3.6 | 8.5 | 15.6 | 29,725 | 31,275 |
| 550699579 | 0.63 | 3.6 | 6.8 | 18.1 | 23,475 | 27,300 |

The model matched the sim on 18 of 19 checked seeds, to 0.1 min. Seed 1780449987 is the exception: the model gives 3.7 min, the sim 7.4. The two routes split at the first targets, probably because an item became visible a tick earlier or later during the scan. So before picking a seed, always confirm it in the sim.

The seed can't be chosen in the game UI. To start on one, use `devtools/swap_seed.py` on a fresh save: it sets `seed` and regenerates `planet.plants.recipeMap`, `harvesting.grid`, `planet.sources` and `planet.geologicalAnomalies`.

### Harvester route

The route search (`devtools/headless/harvest_policies.mjs`) replaced vakermit's value-density script with policy "hybrid", now `scripts/0_cold_boot/harvesting/harvester.py`. Rules and constants: [vehicles_drones.md §2, "Early Harvester"](../cheatsheet/vehicles_drones.md).

Fresh games on 20,000 random fields, run minutes to 10,250 cr and credits by 0.5 h (model, planning ticks included):

| Policy | Mean | p10 | Median | p90 | cr by 0.5 h (mean) | Faster / slower than the old script |
| :--- | ---: | ---: | ---: | ---: | ---: | :--- |
| Value-density script (old) | 19.5 | 10.3 | 16.2 | 27.7 | 15,868 | |
| Hybrid, waits for 60 sectors | 13.2 | 7.3 | 12.1 | 17.9 | 17,506 | 17,129 / 2,423 |
| **Hybrid (current)** | **13.0** | **7.2** | **11.9** | **17.7** | **17,535** | 17,477 / 2,090 |

Steps of the search, mean minutes to 10,250 cr on 2,000 fields (no planning cost unless noted):
- Credits per tick over a heat-priced Dijkstra route, skipping cheap items (`rate`): 13.3. The heat price matters: without it (lam1 = 0) 19.2. Skipping items worth less than half a collect at the best rate: k = 0.5 beats 1 and 2.
- Two-item lookahead over the 6 best targets (`pair`): 12.6. A cluster bonus instead: 13.2.
- Manhattan distances instead of routes (`lite`, cheap in game): 13.6. Monotone routes by DP instead of Dijkstra: 12.7, at about a quarter of the interpreter steps.
- In game, a plain-Python Dijkstra plus lookahead took 30–44 ticks per hop (~1,000 steps per tick). Each tick of planning per hop costs about 0.06 min. Planning as `map()` callbacks brought it to 6–7 ticks; with that cost included: 13.2 (60 sectors), 13.0 (10 sectors).
- Parameter grids (heat price 10–40 cold, 60–150 hot; k 0.35–0.75; 3 or 6 candidates) are flat within 0.05 min.

The model plays the script's route collect for collect: 29 of 30 headless fresh games match, mean reach error < 0.01 min (`harvest_policies.mjs --check`). Seed 12412 splits at the 2nd collect during the scan phase.

Rescan: `seedscan.mjs --score reach` now scores the hybrid route. It costs ~150 µs per field instead of ~9, so it skips fields that `reachPossible()` proves can't reach 10,250 cr by the current cutoff (an admissible bound; ~75–80 % of fields at a 3.4–3.6 min cutoff, 0 misses on 100,000 fields). The old script's score is a poor prefilter: of the exact top 100 over seeds 0–20M, only 12 are in its top 5,000. Seeds 0–20M take 134 s on 12 threads; the best there is seed 1723621 at 3.41 min (old script's best over all seeds: 3.6 min).

**Full scan with the hybrid route (2026-10-06):** all seeds, Crowncap load ≤ 0.8, about 2 h 15 min on 12 threads. The top 10,000 are in `devtools/headless/.cache/seedscan_reach.jsonl`. They span 3.29–3.56 min to 10,250 cr (median 3.54), and they barely overlap with the old script's list: 4 of the top 100 and 240 of the top 10,000.

Confirmed with fresh headless games, using `seedconfirm.mjs --in devtools/headless/.cache/seedscan_reach.jsonl --top 100` (scan order), then `--rank cr --top 30` and `--rank 20k --top 15`. The tool runs `run.mjs --seed N --deploy-templates scripts/0_cold_boot --hours 0.5`, reads credits every tick, and compares them with the model:
- **Top 100 by scan rank:** for 97 seeds, the model's time to 10,250 cr matches the sim within 0.1 min. The sim times are 3.27–3.30 min. Three seeds split at scan-phase ties: 1962692701 and 131126888 take +0.44 min, and 2012258857 takes +0.92 min. The model's credits by 0.5 h are within 0.1 % of the sim.
- **The 10,250 cr target is saturated.** The whole top 10,000 lies within 16 s of run time. What comes after differs a lot (model, top 10,000):

| | p10 | Median | p90 | Max |
| :--- | ---: | ---: | ---: | ---: |
| Credits by 0.5 h | 21,600 | 25,725 | 31,075 | 42,675 |
| Minutes to 20,000 cr | 9.9 | 13.8 | 20.1 | best 4.3 |

  The fastest seeds to 10,250 cr are average later on. For example, scan rank 1 (1706038543) has only 29,575 cr by 0.5 h.
- **Re-ranked by later income:** the top 30 of the 10,000 by credits at 0.5 h and the top 15 by time to 20,000 cr, 42 seeds in all, were run in the sim. The model matches on 41. Seed 2116527766 splits: +1.1 min to 10,250 cr and −1,950 cr by 0.5 h. Best picks (sim results):

| Seed | Scan rank | to 10,250 | to 20,000 | cr by 0.1 / 0.2 / 0.5 h | Crowncap load | Grandbloom load | Field total |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2021208502 | 1,800 | 3.44 | 5.13 | 21,000 / 27,200 / 42,675 | 0.76 | 0.80 | 47,800 |
| 270102838 | 1,724 | 3.42 | 4.33 | 23,475 / 28,725 / 36,975 | 0.79 | 0.55 | 40,250 |
| 1831033811 | 8,920 | 3.54 | 5.25 | 23,500 / 28,300 / 40,650 | 0.72 | 0.55 | 42,725 |
| 479328245 | 8,521 | 3.54 | 5.25 | 22,300 / 31,300 / 40,550 | 0.79 | 0.62 | 44,575 |
| 1658131409 | 5,491 | 3.52 | 4.77 | 21,875 / 27,700 / 35,275 | 0.52 | 0.80 | 40,500 |
| 1648352375 | 865 | 3.40 | 7.15 | 18,275 / 24,900 / 41,925 | 0.79 | 0.83 | 45,500 |
| 1706038543 | 1 | 3.27 | 7.78 | 15,300 / 22,225 / 29,575 | 0.57 | 0.18 | 32,225 |

  By Harvester income alone, seed 2021208502 is the best all-round pick: within 0.17 min of the fastest to 10,250 cr, 0.8 min behind the fastest to 20,000 cr, and the most credits by 0.5 h. Seed 270102838 is the fastest to 20,000 cr. With the full plan and power sources added, the pick is 1831033811 (see "Shortlist re-check").
- **Limit:** the scan kept only seeds that reach 10,250 cr within 3.564 min. A seed a few seconds slower but richer afterwards was cut. A rescan with a later target can find better seeds than these (see Next steps).

## Part 2: Seed recipes

**Game logic** (simworker; offline only, in-game code must not use it):
- `Bp(seed)` deals the 15 recipes. The PRNG is `mp(seed ^ 1347174734)`, the same `mp` as the field. It runs a partial shuffle over all 4060 triples of the 30 life forms and skips a triple when one of its forms is already in 4 recipes. Recipe *i* goes to species *i* in the game's order (Crowncap 10th, Grandbloom 15th).
- Biosites are the same on every world: 7 per biome, each common form at 3 sites, each uncommon at 2, the rare at 1 (72 t). A site cools down by its rarest form (common 9 h, uncommon 18 h, rare 36 h) once every form there is at 0, then refills to full. Upper-bound supply per form: common 6.4–6.9 t/h, uncommon 4.8–5.2 t/h, rare 2.0 t/h.
- Feed recipes are fixed. Each takes 1 t of each of its 2–4 forms per 20 feed. Fertilizer and accelerant use no life forms.
- A full field needs, per form of its recipe, about 3.15 t/h for Crowncap (151 cells, 48 h) and 1.3 t/h for Grandbloom (72 h). Seeds/h depend only on growth time: field machine tiers raise Forage per harvest, not growth speed, and the field uses no Growth Accelerant (×2 growth). So a rare form in the Crowncap recipe can't feed a full Crowncap field even without feed.

**Model** (`seed_quality.py recipes`): available supply per form = upper-bound supply − the form's peak feed demand. The feed peak comes from the 16-Habitat wildlife schedule (`wildlife_optimizer.py`) run to the Wildlife pillar (5M), without a Feed Maker cap. Per-form peaks are taken separately, so this assumes the worst overlap of feed and field. For each fill, the share of the full field its seed forms can feed gives Forage/h. "Best mix" is an ideal Crowncap/Grandbloom split of the field (linear in the share, border cells ignored).

Biggest feed loads: cave_moss 2.8 t/h, stone_mat 2.3, hot_spores 2.0, cold_spores 1.8, lava_algae 1.8; rare forms 0.2–0.8 t/h. That leaves rare forms 1.2–1.8 t/h for seeds.

**Results, seeds 1–20,000, 16 Habitats:**

| | Min | p10 | Median | p90 | Max |
| :--- | ---: | ---: | ---: | ---: | ---: |
| Best mix Forage/h | 2,260 | 2,442 | 2,768 | 2,831 | 2,831 |
| Crowncap load (need ÷ available, bottleneck form) | 0.51 | 0.65 | 1.10 | 2.59 | 2.59 |
| Grandbloom load | 0.16 | 0.20 | 0.34 | 0.80 | 0.83 |

| Class | Rule | Seeds |
| :--- | :--- | ---: |
| GOOD | full Crowncap field is fed | 33 % |
| OK | capped, best mix ≥ 95 % of a full Crowncap field | 24 % |
| MID | best mix 85–95 % | 40 % |
| BAD | best mix < 85 % | 3 % |

Without feed, 57 % of seeds feed a full Crowncap field. Feed halves that.

The main save (seed 1893323207): Crowncap = heat_crust (uncommon), shore_lichen, stone_lichen, load 0.77, so it is GOOD (67th percentile of best mix).

Findings:
- **Grandbloom is always fed** (load ≤ 0.83), so "both bad" does not happen at this field size. The question is how much of the field Crowncap can hold.
- A capped Crowncap is rare-bound in 64 % of capped seeds and uncommon-bound (after feed) in the rest.
- The spread is at most −20 % Forage/h with the best mix, and only 3 % of seeds lose more than 15 %. The planter needs the mix for that, though: today's single fill loses up to 22 % (Grandbloom only).

Limits: supply ignores drone travel and count. The feed peak is per form, not a time series against the Plants phase. The stage-A sweep (when the recipes are found) is not scored yet.

## Part 3: Exotic deposits, thermal vents, oil wells

**Game logic** (simworker `generateThermalVents()`, `generateExoticDeposits()`, `generateFluidWells()`, called in that order on a new world; oil well cycles from `i_e()`, `mp(seed ^ hp(well id) ^ 1165217)`). Each is a pure function of the seed with no sim needed: calling the game's own generators from the headless sim module on an empty planet (no outposts) reproduces the main save's vents, deposits and wells exactly, at ~44 µs per seed. A source's mean supply = peak rate × active ÷ (active + dormant). Home is fixed at (0, 0).

**Exotics: not a seed criterion.** The 16-Habitat schedule (`wildlife_optimizer.py`, stored schedule, target 5M) never fills the legendaries: the pillar comes with `spire_drake` at ~146k and `glacial_wyrm` at ~112k, both in stage 3. So no quicksilver is drawn, and chlorine is only a 350 t band fill per legendary at stage 3 plus ~0.5 t/h bleed each:

| Feed Makers | 5M at | Chlorine ready | First draw | Chlorine to 5M |
|---|---|---|---|---|
| unlimited | 3,488 h | 1,696 h | 2,260 h | 1,941 t |
| 4 | 3,537 h | 1,696 h | 2,274 h | 1,960 t |
| 2 | 4,801 h | 1,714 h | 2,883 h | 2,449 t |

Chlorine deposit mean over seeds 1–20,000: min 2.37, p10 4.03, p50 6.15, p90 9.04, max 13.5 t/h. Even the worst seed covers the ~1.2 t/h sustained peak and banks both fills in the 560+ h between unlock and first draw; unbanked, a fill stalls one legendary 350 ÷ rate h (26–148 h). The old "chlorine is short" verdict in [phase9_wildlife.md](phase9_wildlife.md) assumed all 16 species at 350k (8,940 t). It holds only for a run that fills every species.

**Steam and oil: rates barely vary, only geometry does.** Seeds 1–20,000:

| Metric | min | p10 | p50 | p90 | max |
|---|---|---|---|---|---|
| Nearest vent from home (m) | 420 | 474 | 567 | 627 | 778 |
| Nearest vent mean steam (t/h) | 519 | 597 | 715 | 837 | 940 |
| All 5 vents mean steam (t/h) | 2,842 | 3,322 | 3,576 | 3,834 | 4,314 |
| Nearest oil well from home (m) | 402 | 470 | 555 | 636 | 799 |
| 2nd-nearest oil well (m) | 444 | 561 | 631 | 712 | 828 |
| All 5 oil wells mean (t/h) | 34.4 | 39.2 | 41.6 | 43.9 | 47.6 |

- One vent (≥ 519 t/h mean) feeds 5+ Steam Turbines (90 t/h each); its 36–60 h dormant phase needs tanks or a second vent either way. Total steam varies ±7 % (p10–p90).
- Oil well tiers and peak rates are a fixed list; only positions and cycles (active 8–14 h, dormant 6–10 h) roll. Total oil varies ±6 %.
- So a steam/oil score can only be distance: how far the first vent and the first oil wells sit from home or from a viable outpost site. It needs a cost model (pipe length, outpost founding, Pioneer travel) before it means anything.

**Tool:** `node devtools/headless/sources.mjs --seed N` (every vent and well) · `--seeds A-B` · `--in FILE.jsonl [--top N] [--out FILE.jsonl]` (adds `oil`, `steam`, `vent_m`, `vent_steam` per row; the 10,000-seed reach list takes ~1 s). It calls the generators through the sim shim (`simhost.mjs` `findWorldGen()`, `__ctWorldGen`, `generateWorld()`); `--emit N` prints a fresh world's sources and anomalies (matches the main save exactly). In game the UI thread places them, not the worker, so headless `newGame()` and `swap_seed.py` now generate them too (before 2026-10-07, fresh headless games had none and swapped saves kept the old seed's).

**Score (proposal).** Turbines and Oil Generators carry power until the Reactor. Steam has never run dry in play; oil was short only briefly, during a Tar demand peak that can probably be avoided. More oil means fewer Steam Turbines for the same power:
1. **Total oil mean** (all 5 wells, peak × active share). One Oil Generator burns 8 t/h for 700 W, so 1 t/h of oil ≈ 87.5 W ≈ 0.81 Steam Turbines (108 W). p10 → p90 (39.2 → 43.9 t/h) is ~410 W, ~3.8 turbines fewer. Worst vs best seed is ~1.1 kW, ~10 turbines.
2. **Early hookup: Pioneer range, not segment count (resolved: not a criterion).** Power is what must connect early (the reason for the first Thermal Caps); pipes can wait (planner TODO), and a segment buffer built in otherwise idle time hides most per-segment crafting time. So the early cost is the power line to the first vent, and mainly whether the Constructor Pioneer reaches the far end on one charge. Pioneer travel (cheatsheet `vehicles_drones.md` §2a): Wh per metre = (3 + 8 × active modules + 0.04 × cargo units) × throttle^0.5 / 100. A constructor (Nav + Constructor, ~50 cargo units) draws ~21 W at full throttle, so ~0.105 Wh/m at the 25 % throttle floor. One construction job costs ~40 Wh (`CONSTRUCTION_WH_PER_PROGRESS_DEFAULT`, calibrated live). Round-trip radius with one job, 25 % throttle:

   | Battery | Radius |
   |---|---|
   | 100 Wh (2 small holders, base batteries) | ~290 m |
   | 150 Wh (3 × 50 Wh) | ~520 m |
   | 200 Wh (constructor preset `battery×4`, small holders, base batteries) | ~760 m |
   | 300 Wh | ~1,240 m |

   At 50 % throttle the radii shrink to ~200 / ~370 / ~540 / ~880 m. The nearest vent is 474–627 m (p10–p90, straight line; max 778) and the nearest oil well 470–636 m. With the 4-battery constructor preset (2026-10-07; was 2 batteries, ~290 m) the first vent is in one-charge range at 25 % throttle on nearly every seed, so range is no longer a seed criterion; at most a tiebreaker for how much throttle the first trip can afford. The Manhattan-based segment count (~0.2 min per metre for the power line alone, 2 min per segment) is a secondary, upper-bound cost.
3. **Total steam mean:** tiebreaker only.

The vent, deposit and well streams are independent of the field and the recipes. The top 10,000 of `seedscan_reach.jsonl` have the same oil/steam/distance spread as random seeds (oil p10/p50/p90 39.2/41.6/43.9 t/h). So filtering on oil keeps the expected share of the reach list: oil ≥ p90 keeps ~1,000 seeds. Current picks (oil t/h, straight-line m to the nearest vent / oil well): 2021208502 42.6, 584 / 444; 270102838 44.1, 604 / 570; 1706038543 42.7, 537 / 590.

## Shortlist re-check (2026-10-07)

The 7 best picks from part 1, run three ways:
- Fresh: the part 1 sim table (fresh game, Harvester only).
- Plan: `run.mjs --save .cache/checkpoints/early_h2.json --field-seed N` with the feeders2.2 plan, `--lib-tier scripts/4_controlpanel --park --until-tp 150000 --until-pioneer` (the `buildorder_search.py` flags). `--field-seed` swaps only the Harvester field; vents, wells and recipes stay the checkpoint's.
- Sources: `sources.mjs --seed N` (part 3).

| Seed | Fresh: to 20k cr (min) | Fresh: cr by 0.5 h | Plan: 10k / 70k / 150k TP (h) | Plan: cr by 0.5 h | Plan: net worth at 1 h | Oil t/h | Steam t/h | Nearest vent | CC / GB load |
| :--- | ---: | ---: | :--- | ---: | ---: | ---: | ---: | :--- | :--- |
| 1831033811 | 5.25 | 40,650 | 0.20 / 1.00 / 4.03 | 80,243 | 179,401 | 44.16 | 3,794 | 452 m | 0.72 / 0.55 |
| 270102838 | 4.33 | 36,975 | 0.15 / 0.95 / 4.02 | 102,046 | 175,825 | 44.09 | 3,357 | 604 m | 0.79 / 0.55 |
| 2021208502 | 5.13 | 42,675 | 0.20 / 1.00 / 4.05 | 78,650 | 181,055 | 42.59 | 3,758 | 584 m | 0.76 / 0.80 |
| 479328245 | 5.25 | 40,550 | 0.25 / 1.05 / 4.10 | 76,802 | 179,177 | 43.36 | 3,424 | 506 m | 0.79 / 0.62 |
| 1648352375 | 7.15 | 41,925 | 0.20 / 1.00 / 4.06 | 58,890 | 182,361 | 42.60 | 3,900 | 502 m | 0.79 / 0.83 |
| 1658131409 | 4.77 | 35,275 | 0.20 / 1.00 / 4.04 | 67,538 | 177,528 | 39.72 | 3,876 | 595 m | 0.52 / 0.80 |
| 1706038543 | 7.78 | 29,575 | 0.25 / 1.05 / 4.06 | 47,365 | 169,255 | 42.68 | 3,099 | 537 m | 0.57 / 0.18 |

Findings:
- The field barely moves 150k TP (4.02–4.10 h, as in part 1) or net worth at 1 h (±4 %). It matters only for the early ramp, before the Bio-Loop dominates. Credits at a fixed time are noisy in plan runs, because the plan spends in lumps.
- Harvester credits by 0.5 h (the old ranking key) say little: 270102838 is mid-table there but leads every plan milestone.
- 1831033811 and 270102838 tie on total oil. For the midgame, geometry decides:
  - 1831033811: pure well (14.9 t/h) and a standard well at 482 / 481 m, about 180 m apart (19.7 t/h on one pipe run). Vents 4 and 1 (452 / 613 m, 1,456 t/h mean) are about 160 m apart, so one power line reaches both and they cover each other's dormant phases.
  - 270102838: pure well at 570 m, next well at 665 m in another direction. Nearest vent at 604 m; best close pair 1,298 t/h. Total steam 437 t/h lower (~5 Steam Turbines).
- **Pick for a midgame focus: 1831033811.** It gives up the early ramp (fresh game to 20,000 cr in 5.25 vs 4.33 min, 10k TP at 0.20 vs 0.15 h). 270102838 is the pick for the fastest opening. 2021208502 is ~1.5 t/h short on oil. 1658131409 (oil below p10) and 1706038543 (slow ramp, least steam) are out.

## Next steps

- [x] Field score from the route: `harvest_model.mjs` (route-exact port of the Harvester script, `--check` against headless runs) and `seedscan.mjs --score reach` over all seeds.
- [x] Fresh headless games work (`run.mjs --seed N --deploy-templates scripts/0_cold_boot`: Scanner and Harvester from tick ~50), but nothing plays the rest of onboarding or the build plan from tick 0 yet.
- [x] Find out which other parts come from the seed (mining sites, POIs, weather), with their generator functions in the simworker.
- [x] Seed recipes: `seed_quality.py recipes` (part 2).
- [ ] Seed recipes: score the stage-A sweep per seed (hours until the Crowncap/Grandbloom recipes are known).
- [ ] In game: supply-aware Crowncap/Grandbloom ratio from in-game readings (TODO "Supply-aware field fill").
- [x] Optimise the Harvester route: policy "hybrid" in `scripts/0_cold_boot/harvesting/harvester.py` (see "Harvester route").
- [x] Rescan all seeds with the new route and confirm the top seeds in headless fresh games (see "Full scan with the hybrid route").
- [ ] **Next: score by a later target.** Time to 10,250 cr is nearly the same for every top seed. Pick a later target (credits by 0.5 h, or time to 20,000 cr), add it as a `seedscan.mjs` score with its own `reachPossible`-style bound, and rescan. Decide first what the credits after the 25/25 build-out buy, so the target matches a real purchase. *2026-10-07 Partially done* Now first a "cutoff" with CC/GB+Wildlife feedability then early credits by harvester then overall harvester credits. Total oil (part 3): `sources.mjs --in` scores, merge into the ranking still open
