# Planner revision 2: replay and headless results (2026-10-17)

How the outpost planner revision 2, the atmosphere focus and the building planner draft 1 compare with the
two recorded runs (`internals/sample_saves/20261007_c5f9ebf`, 20 kept saves; `20261008_7e5e168`, 41 kept
saves). Tool: `devtools/simulation/planner_replay.py` (offline, over `replay_snapshot.py`'s save-to-snapshot
adapters); per-save tables in `internals/sample_saves/<run>/planner_replay_<commit>[_accept].md`.

## How to read the numbers

Each real decision between two kept saves (a new outpost, a machine type count up or down at an outpost, a
tier count up, a generator-type shift = pillar swap, a fleet role count change) is matched against the
planner's proposals at the earlier save or the three saves before it. `match` = proposed at that save,
`early` = proposed before, `missed` = never proposed in the window, `early buyer` = a building or swap before
the Control Room (`lib/early_buyer.py` owns that order, the planners stay out), `extra` = a proposal the
operator never acted on within the window. A `missed` deploy is often a machine no provider models yet (bio
chain, Seed Makers at home, Habitats, Feed Makers, tanks beyond one per producer); it is not a wrong call.

Counting caveats: matches are per decision and per save, not one-to-one (several identical real deploys match one
proposal key; a proposal that stays open over several saves is an `extra` at each of them; an action the planner
first proposes one save later is `missed` there and `extra` here). A founding matched by any found proposal of
that save (other biome) counts as `loose` in the tool's current output; the tables below predate that column and
fold it into `match`. Accept mode appends a virtual outpost every save a bundle is proposed and never reconciles
it with the real outpost the operator founds, so its `found` matches drop and its `deploy` extras balloon (role
gaps at virtual outposts); read accept mode for the coverage effect of designations, not for its counts. The
report files are stamped with the parent commit (`2278444`) but were made from the working tree that became the
next commit.

Offline limits (the game would answer live): `TerraformPillar.target` is not in a save, so even-growth
shares use the highest catalog threshold per pillar; mineral contacts are the fixed site table filtered to the
surveyed ids (no unknown-contact guesses, no survey requests); `machine.activity` exists only where the
Control Room ran; `TerraformPillar.complete` is unknown for the atmosphere pillars.

## Run 2 (`20261008_7e5e168`, day 1 to 417)

Plain (the planner sees only the operator's state):

| kind | match | early | missed | early buyer | extra |
|---|---|---|---|---|---|
| deploy | 21 | 3 | 173 | 18 | 20 |
| fleet | 2 | 1 | 29 | 0 | 16 |
| found | 5 | 0 | 3 | 0 | 8 |
| retire | 8 | 2 | 105 | 1 | 3 |
| swap | 1 | 0 | 8 | 2 | 13 |
| upgrade | 2 | 1 | 30 | 0 | 6 |

Accept mode (the planner's designations and foundings carried forward as virtual outposts):

| kind | match | early | missed | early buyer | extra |
|---|---|---|---|---|---|
| deploy | 71 | 5 | 121 | 18 | 120 |
| found | 1 | 0 | 7 | 0 | 2 |

(fleet, retire, swap and upgrade rows are the same as plain.)

Foundings, one by one (operator's why-notes in `log.md`):

| real outpost | day | operator | planner |
|---|---|---|---|
| outpost_1 smelt/fab/dock, coastal (170, 80) | 16 | near iron and silicon, 2nd biome | the first-factory need appears at save 0050 (TP 140k; outposts unlock at 120k, between saves 0040 and 0050): `found factory, smelter, terraform, drone_depot (now)` at (-140, -120) coastal, score 23.7. Same biome, 2.5x closer to home, next to rust_hollow and home_basin iron. The operator later rated a deep site near iron best; the early weights (home −4/km, demand share iron 0.6) land on the coastal iron pair instead. |
| outpost_2 geothermal, vents (200, -440) | 18 | planned from the start | missed: no thermal vent was surveyed before save 0080 (day 24), so the `power` look-ahead had no site. Live, the survey request path (`survey: True` proposals) and `contact_inference` (a research-locked contact in geothermal is a vent) are what would place it. |
| outpost_3 second fab, deep (-460, 280) | 24 | 4th biome, second fabrication outpost | match by biome: `found terraform (soon)` at (-300, 100) deep (no outpost keeps 2 free slots). The 2nd-factory rule (full and busy) never fired: `machine.activity` is empty before the Control Room ran. |
| outpost_4 volcanic (30, 420) | 68 | biome + oil, way too early (undeployed day 79) | missed as a founding; the planner wanted `terraform` at (-180, -520) volcanic from save 0288 on. |
| outpost_5 volcanic (30, 420) | 97 | replaces outpost_4, terraforming + caster | match: `found terraform (soon)` volcanic (-180, -520) since save 0288, 29 days ahead. |
| outpost_6 storage, coastal (200, 0) | 157 | storage outpost | match: `found mining, drone_depot` coastal (580, 40) (neutronium out of range; the operator put a drill on it instead, which the rule now honours) and `found terraform` coastal (40, -360). The `storage` need did not fire: the crowded outposts held fewer than `STORAGE_TANKS_MIN` tanks in the kept saves. |
| outpost_7 nuclear + refiner (-, day 320) | 320 | bad idea: too few slots | match: `found reactor (now)` coastal (20, -280) with water in reach, from save 1086 (day 272) on, as an exclusive bundle (no Refiner there). |
| outpost_8 pure terraforming | 337 | pure terraforming | match (other biome): `found terraform (soon)` coastal (40, -360). |

Other signals worth keeping:
- `found liquifier_frozen, drone_depot (now)` at (-20, 60) from save 1160 (Wildlife research reached): the move of the essence chain off home the operator wished for at #1247 but never made.
- The neutronium `mining` founding (saves 0712 to 1672) was the operator's rejection #1294 (a drill on the site, drones fetch from it); `unreached_ores()` skips ores with a drilled site, so the row stops once the drill stands (save 1266 on in the report).
- Pillar swaps: 1 match (heat → o2 at save 0393), 8 missed. The focus's research mode ranks the Industrial Drill (oxygen) above water (pressure) around day 38 to 44 where the operator went for water (#176: "not sure if still most important or water first"); after the research chain is done the even-growth mode needs real pillar targets to be fair (offline limit above). The 13 extra swap rows are the same proposal repeated over consecutive saves.
- Atmosphere generator proposals are mostly `blocked: power` on the saves' grids: the operator's grids ran near their headroom.

## Run 1 (`20261007_c5f9ebf`, day 1 to 59)

| kind | match | early | missed | early buyer | extra |
|---|---|---|---|---|---|
| deploy | 11 | 3 | 37 | 19 | 4 |
| fleet | 0 | 0 | 13 | 0 | 0 |
| found | 2 | 0 | 1 | 0 | 3 |
| retire | 5 | 2 | 22 | 3 | 0 |
| swap | 1 | 0 | 3 | 3 | 1 |
| upgrade | 2 | 0 | 2 | 1 | 3 |

Accept mode: deploy 27 match / 22 missed / 18 extra, found 2 match / 1 missed / 0 extra; the rest as plain.

## Headless (`run.mjs --include-autoplay --auto-approve`)

Save `0562_t760867` (day 127, biomass phase, 60 surveyed sites), 0.5 game hours, approvals every 3,000 ticks:

```
node devtools/simulation/headless/run.mjs --save internals/sample_saves/20261008_7e5e168/saves/0562_t760867.json.gz --hours 0.5 --include-autoplay --auto-approve 3000 --out <dir>
```

- The planner Automation starts and stays up (no crash, `errored` 0 in `metrics.jsonl`). Two fixes came out of the first attempts: the planner's lib import chain exceeded the 10,000-step import cap (`planner_loop` now imports the planner modules in groups with a yield between them), and `outpost_needs.snapshot()` read 60 sites in one go (`SITE_CHUNK` atomic slices now).
- Founding pass: `d-outpost_1 +liquifier_coastal` (next biomass phase) and `f-general terraform` at (120, -280) coastal, `cash: wait`; after the auto-OK the designation is written (`changed`) and the founding is `approved`; the next pass proposes `f-geothermal liquifier_geothermal, drone_depot`. Pass time 115 sim s for the first full pass, 13 to 80 s after.
- Building pass: focus `heat` then `o2` (research mode, no swap), three battery retires on the steam grid (approved: 3 jobs queued), then three `oxygen_upgrade_pack_mk2` upgrades on home generators (approved: 3 jobs queued, waiting for the pack in `kit`). Pass time 17 to 20 sim s.
- Not reached in 0.5 h: a swap row, fleet rows (no essence outpost designated yet at the start), the pipeline after `kit` (kit sourcing is phase 4 of the building planner).

Save `0040_t58844` (day 10, before the Control Room): the planner runs, founding proposals are off (`Map Markers locked (Cartography)`), the power survey starts; no proposals, as intended (`early` phase).

## Follow-ups the replay suggests
1. Site choice for the first factory outpost: weigh the operator's "a deep site near iron" against the planner's coastal pick with the ore_outpost cost model (Pioneer hours per unit) instead of the demand-share ore term alone.
2. Providers for the machines the replay misses most: Seed Makers (there), Habitats and Feed Makers (wildlife planner), tanks per fluid beyond the producer rule, Crop Automators.
3. Fleet rows: 29 missed are Pioneer and drone commissions the operator made without a rule the draft has (constructor and hauler counts by backlog, miners before drills).
4. The focus needs live pillar targets and a live A/B before its swap rows are trusted.

## Revision 3 (2026-10-21): `reach_gain` and `future`

Question: does the second factory outpost leave the first one's cluster when no vent is known nearby, and stay
when one is? Saves: `20261018_4c29716` (the operator's 2026-10-18 run, "run 2" of the revision 3 findings) and
`20261007_c5f9ebf`. `planner_replay.py` over both (summary rows unchanged by the tuning: run 2 found 1 match / 1
loose / 1 early / 12 extra, run 1 found 1 / 1 / 0 early / 1 missed / 8 extra). The tool ranks with neither the
look-ahead fluids nor the geothermal scout areas (`future` is 0 in its tables) and ranks the second factory only
after the operator founded it, so the second outpost was ranked with a scratch probe over the same adapters: the
planner's own state carried forward (outpost_1 designated factory + smelter, with its `charging` station), live
`plan["future"]` and `geothermal_areas()`, top 3 with terms. Needs `CT_SIMWORKER` pointed at the main checkout's
simworker when run from a worktree. The probe (`probe_second.py`) is not kept in the repo, so the second-factory
top-3 tables and the "stays" claims below are not reproducible from the repo tools; extending `planner_replay.py`
to cover them is a TODO.md follow-up.

Run 2, saves 0052 to 0055 (day 18, early weights, Thermal Cap reached at 0055). outpost_1 stands at (-420, 120)
deep on the western iron cluster; the operator put outpost_2 beside it at (-450, 70) and regretted it. No vent is
known (the nearest, vent_4 at (-570, 200), is unscanned). The geothermal scout areas are (220, -400) and
(-420, -400) until 0055.

| try | `WEIGHTS_EARLY` `reach_gain` | top site (save 0052) | terms | verdict |
|---|---|---|---|---|
| 0 | 3 (start) | (-420, 20) coastal 22.6 | ore 20.0, biome_new 3.0, room 1.8, future 0.3, reach_gain 0.1, grid −0.6, travel −0.3, home −1.7 | stays in the western cluster (2nd (-420, 40), 3rd (-400, 20)); best east site (400, 240) 19.0 (grid −3.8, reach_gain 1.1) |
| 1 | 12 | (240, -220) coastal 26.9 | ore 20.0, reach_gain 6.0, biome_new 3.0, room 2.0, future 1.0, grid −2.8, home −1.3, travel −1.0 | leaves; 2nd (320, -120) 26.6, 3rd (320, -100) 26.2 |
| 2 | 6 | (320, -120) coastal 23.6 | ore 20.0, reach_gain 3.0, biome_new 3.0, room 2.0, future 0.6, grid −2.6, home −1.4, travel −1.0 | leaves, margin under 1 point over the cluster |
| 3 (kept) | 9 | (320, -120) coastal 25.1 | ore 20.0, reach_gain 4.5, biome_new 3.0, room 2.0, future 0.6, grid −2.6, home −1.4, travel −1.0 | leaves; 2nd (300, -80) 24.8, 3rd (320, -100) 24.8; the cluster's best ~22.8 |

At 0055 (no scout areas, `future` 0) try 3 keeps (320, -120) 24.5, (300, -80) 24.3, (320, -100) 24.3. The pick lies
east of home between the east iron deposit (590, 220) and the south-east geothermal area: the bridge the operator
asked for, not on the deposit itself (`grid` −6/km keeps it nearer the base). With vent_4 surveyed (hypothetical,
north-west) every try stays: (-540, 180) geothermal 31.2 (ore 20.0, fluid 6.9, future 2.7, biome_new 3.0, room 2.0,
reach_gain 0.4, grid −1.1, home −2.3, travel −0.4), 2nd (-540, 200) 31.1, 3rd (-540, 220) 31.0. Without outpost_1's
Charging Station (the save as the operator left it) home is the only reach point, the cluster and the east gain the
same share, and every try stays west: `reach_gain` needs the first outpost's station, which the `charging` role
deploys before drones.

Run 1, save 0060 (day 20, outpost_1 power at (150, -430), outpost_2 factory at (-540, 40)): the second factory bundle
ranks (140, -340) coastal 25.3 at try 3 (ore 20.0, biome_new 3.0, reach_gain 2.5, room 1.8, future 1.2, grid −0.6,
travel −1.1, home −1.5; 2nd (100, -320) 25.3, 3rd (80, -340) 25.2), beside the power outpost, away from the factory
outpost; at the start weights (140, -340) led too (23.7). The replay table, without `future`, moves this row to
(-420, 0) (24.3 against 24.1): the live `future` term decides that tie. Other moved rows at try 3: run 1's `power`
bundle at 0073 (0, 300) → (560, 180), run 2's `terraform` bundle (-540, 180) geothermal → (440, -260) volcanic from
0089 on; neither changes a verdict.

Verdict: as expected with `WEIGHTS_EARLY["reach_gain"]` = 9; `future` (3) and the late `WEIGHTS` unchanged.
