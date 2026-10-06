# Scoring map seeds

Goal: rate a world seed before playing it, using the parts of the world the seed decides that change a speedrun. Each part gets its own score; a combined score comes later, once we know how much each part costs or gains in game hours.

Status: part 1 (Harvester field) has a tool and first results. The other parts are open.

## Parts of the world a seed decides

| Part | Matters for | Status |
| :--- | :--- | :--- |
| Harvester surface field (`state.harvesting.grid`) | early credits, before the Bio-Loop earns (about the first 0.2 game hours) | tool: `devtools/headless/field.mjs`, `run.mjs --field-seed` |
| Seed recipes (15 random life-form triples, cheatsheet §1i) | life-form demand vs the fixed biosite supply (feed, Forage seeds, fertilizer) | idea only: TODO "World seed quality tool" |
| Mining sites and POIs | rover and Pioneer ore, outpost founding | to check: which of them come from the seed |
| Weather | heater efficiency (about 93 % average) | to check: game `GK()` seeds by `planet.clock.dayNumber`; whether the world seed enters too |

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

## Next steps

- [ ] Field score from a short sim: run `--field-seed` to 0.3 game hours for the top seeds by static value plus a random sample, and rank by Harvester income at 0.1 h and 0.2 h. A driver (`devtools/seed_quality.py field`) would run them in parallel like `buildorder_search.py`.
- [ ] A new game starts before onboarding (0 cr, no scripts), and nothing plays onboarding headlessly yet. To score a seed's whole world, either automate onboarding from `sim.newGame(seed)`, or swap each part into a checkpoint as done for the field.
- [ ] Find out which other parts come from the seed (mining sites, POIs, weather), with their generator functions in the simworker.
- [ ] Seed recipes: the TODO "World seed quality tool" item (life-form demand vs supply).
- [ ] Note: the Harvester script is vakermit's value-density script. Its route, not just the field, sets early income; a better route would raise every field's early credits.
