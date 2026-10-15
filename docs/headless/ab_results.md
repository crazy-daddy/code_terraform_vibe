# A/B results

A stand-in mode ships with a row here: the same save, the same game time, the real run against the mode, both on current repo scripts. Columns: what the test target would read (TP, atmosphere, credits), script health, and speed. Earlier tables (passive-machine parking, the late-save profile) are in [../plans/headless_sim.md](../plans/headless_sim.md).

Canonical saves: `internals/sample_saves/20261007_c5f9ebf/saves/0262_t349372.json.gz` (day 59, 24 pressure generators, 8 turbines, 10 smelters, 12 pioneers) and `internals/sample_saves/save_mtzkzly3_4ww80o.midlate_2026-10-05.json` (the main save, mid-late, heaters and Mk III machines). Record the `latest scripts:` line and any `skip` lines once per save: both saves run the repo's current scripts by default, and the 20261007 run predates some role renames.

## Phase 0: parity of the scenario engine with the 306e188 hack (2026-10-14)

Save 0262, `--only-scripts harvester_1 --stock seeds_basic=40 --drain forage:600 --hours 0.25`, old `run.mjs` (commit 306e188) against the scenario engine.

| | 306e188 | scenario engine |
| :--- | ---: | ---: |
| `metrics.jsonl` (wall time fields removed) | identical | identical |
| `stocked.seeds_basic` / `drained.forage` | 40 / 0 | 40 / 0 |
| TP, credits at the end | 240,924 / 25,148 | 240,924 / 25,148 |
| scripts running / errored | 1 / 0 | 1 / 0 |
| harvester allowance (steps per tick) | 1,000 | 694 (71 ghosts; the full base's value) |
| × real time | 100 | 118 |

The harvester sleeps most of the time, so the lower allowance changed nothing here; it matters for a busy target.

## Phase 1: terraforming `standin` vs real (2026-10-14)

Midlate save, `--hours 0.33 --report-every 5` (11,880 ticks), everything else real; 9 slots replaced (3 Mk III heaters, 3 Mk III O2 generators, 3 Mk III pressure generators), 134 scripts running in both runs.

| | real | `--standin terraforming=standin` |
| :--- | ---: | ---: |
| heat gained | 310.11 | 310.97 (+0.28 %) |
| O2 gained | 284.47 | 283.80 (-0.24 %) |
| pressure gained | 14.256 | 14.256 |
| TP at the end | 826,587 | 826,581 |
| errored / crashed | 0 / none | 0 / none |
| steam guard | open (pool 100 %) | open (`pool` 1, `guardOff` []) |
| × real time | 1.85 | 1.81 |

Notes: the save's O2 generators start on a dry `steam_condenser_1`; the real router moves them to `bulk_liquid_reservoir_8` within ~80 ticks, the `_feed.py` keeper after ~210 (two checks 5 s apart), which is the O2 gap. Two earlier attempts are the reason for two rules in the code: the guard read the port buffer keys (`gas_in_level`) instead of the tank's `data.level` and closed on a 100 % pool (heat +11 instead of +310), and without the feed keeper the stand-ins kept the dry source (O2 +122). No speed gain is expected on this save (9 of 134 scripts); the mode exists so a later `scale` and the other groups' modes can run with the atmosphere still moving. Still open: the same pair on 0262 (24 pressure generators, no heaters) and `park` in the same table.

## Phase 2: terraforming `scale` vs real (2026-10-14)

Midlate save, `--hours 0.33 --report-every 5` (11,880 ticks), everything else real; `--standin terraforming=scale,max=50`: 9 Mk III machines into 3 records (`heater_10`, `o2gen_10`, `pressure_10`, `data.scale` 3 each), 6 undeployed, 18 kit and upgrade-pack units removed from the Inventory, no refusal, no stall (`minLevel` 7.95 / 4.97 / 4.98 t, the ports' capacity). 134 scripts running in the real run, 128 plus 6 ghosts in the scaled one (allowance 370 steps at the end in both).

| | real | `--standin terraforming=scale,max=50` |
| :--- | ---: | ---: |
| heat gained | 310.13 | 310.97 (+0.27 %) |
| O2 gained | 284.47 | 283.71 (-0.27 %) |
| pressure gained | 14.256 | 14.256 |
| TP at the end | 826,552 | 826,507 |
| errored / crashed | 0 / none | 0 / none |
| `power.consumed` at the 5-minute reports | 5393 / 5533 / 5736 / 4519 W | 5301 / 5355 / 5724 / 4376 W (-1.7 / -3.2 / -0.2 / -3.2 %) |
| net worth at the end | 5,081,621 | 5,052,221 (the 6 machines' value) |
| × real time | 1.55 | 1.61 |

The `power.consumed` gap is not the terraformers: with every other group `off` (power real, 3 game minutes, `iso_real` / `iso_scale` scenarios), `consumed` is identical at every report (3482.4 / 3320.4 / 3310.4 / 3190.5 W in both), so the scaled draw of a record equals its N machines' draw. In the full pair the other loads drift (running scripts 125-136 vs 124-129 between reports, drones charging and fabricators on different schedules). The heat and O2 deltas are the Level-1 stand-in's (phase 1 above: the O2 generators' dry-condenser gap); `scale` adds nothing measurable. No speed gain on this save (9 of 134 scripts); the mode pays off on saves with dozens of identical terraformers.

## Phase 3: logistics `mover` vs real (2026-10-14)

Save 0262 (`internals/sample_saves/20261007_c5f9ebf/saves/0262_t349372.json.gz`, 4 outposts, factory real), `--hours 0.33 --report-every 5` (11,880 ticks), everything else real; `--standin logistics=mover` stops 14 scripts (12 Pioneers, 2 Supply Docks). 59 scripts running in the real run, 39 plus 14 ghosts in the mover run (allowance 847 vs 943 steps at the end: the mover run has fewer real scripts for the same budget).

| | real | `--standin logistics=mover` |
| :--- | ---: | ---: |
| trips / units moved | Pioneer trips not counted | 45 / 620 (`gas_pipe_segment` 154, `silicon` 182, `titanium_ingot` 116, `liquid_pipe_segment` 94, `iron_ingot` 60, `power_line_segment` 14) |
| `titanium_ingot` at outpost 2 (requested 100 at band 400) | 0 | 100 |
| pipe segments at outpost 2 (gas / liquid) | 181 / 117 | 300 / 233 |
| `titanium_ingot` at outpost 3 (smelted there) | 1,728 | 1,336 |
| `iron_ingot` at outpost 3 | 940 | 862 |
| credits / net worth at the end | 38,598 / 183,898 | 28,648 / 171,948 |
| TP, pressure at the end | 244,735, 5.2745 | 244,735, 5.2745 |
| errored / crashed | 0 / none | 0 / none |
| fleet warnings | none | none (only the fabricator recipe and thermal cap warnings of the real run) |
| × real time | 3.70 | 4.69 |

Notes: the mover serves requests faster than the fleet (outpost 2's titanium ingots and pipe segments land; the real fleet is still on its way), as an upper bound should. Two gaps are the boundary of the group, not the mover: the stopped Supply Docks ship no orders, which is the credits gap, and the stopped miner Pioneers bring no ore, which is the ingot gap at outpost 3 (`GROUPS.logistics` lists "ore at smelters" and "order shipping"; keep the docks with `keep` or feed the smelters with a `flows` row). Silicon ping-pongs between outposts 2 and 3 over the run (each outpost's band-600 shortfall pulls from the other's band-200 surplus); the real tier rules allow the same, the Pioneers are only slower at it. The 12,250-tick-old pickups of the stopped Pioneers seen in this run's final save are the reason the mover now drops a stopped hauler's pickups at setup.

## Phase 4: plants target with the rest stood in (2026-10-14)

Saves 0142 (`0142_t248069.json.gz`, midlate) and 0262 (`0262_t349372.json.gz`), `--hours 0.33 --report-every 5` (11,880 ticks), real against `scenarios/plants_target.json` (`factory`, `biolab`, `wildlife`, `biomass` off, `logistics=mover`, `terraforming=scale`, plants / power / orchestrator / weather real, no flows). The intended target, credits per hour from the harvester, does not exist on either save: `plant.status` shows the harvester in `starter` mode, `planted 0`, `last_action pave@A4`, in all four runs, with the same stamp tick in each pair (252,084 on 0142; 353,385 real / 353,389 stand-in on 0262), so the plants group behaved identically with the rest stood in. `produce` / `cash` were not exercised here (plants real is the target); their tests are `test/producers.test.mjs`.

| | 0142 real | 0142 stand-in | 0262 real | 0262 stand-in |
| :--- | ---: | ---: | ---: | ---: |
| scripts running at start / ghosts | 72 / 0 | 33 / 39 | 72 / 0 | 21 / 51 |
| allowance steps at the end | 714 | 694 | 847 | 724 |
| credits start, end | 62,828, 61,428 | 62,828, 62,828 | 25,148, 38,598 | 25,148, 25,148 |
| net worth start, end | 189,978, 187,078 | 170,778, 170,778 | 168,448, 183,898 | 149,548, 149,548 |
| heat / O2 / pressure at the end | 57.7478 / 60.3418 / 4.6271 | 57.7544 / 60.3418 / 4.6271 | 90.5852 / 162.375 / 5.2745 | 90.5852 / 162.375 / 5.2733 |
| `scale` records (undeployed, refused, stalled) | | 4 (24 heaters, 0, none) | | 3 (21 pressure generators, 0, none) |
| `mover` trips | | 4 | | 3 |
| stubs | | `wildlife.plan`, `biomass.retire` | | `wildlife.plan`, `biomass.retire` |
| errored / crashed | 0 / none | 0 / none | 0 / none | 0 / none |
| wall s, × real time | 257, 4.63 | 164, 7.26 | 333, 3.56 | 173, 6.87 |

Gaps, all at the boundaries of the groups that are off or stood in: the 0142 real run's −1,400 cr are Pioneer upgrades (`[cash] pioneer_upgrade:pioneer_6 spent 650 cr`, logistics group, stopped by `mover`); the 0262 real run's +13,450 cr are Supply Dock orders (stopped by `mover`, as in the phase 3 row); net worth starts 19,200 / 18,900 lower in the stand-in runs because `scale` takes the undeployed machines' kits out of the Inventory. Pillars within 0.01 % (`scale`'s Level-1 heater on 0142, pressure on 0262). The stand-in runs are 1.6-1.9× faster than real on these saves; `cash.budget` is not stubbed because the orchestrator stays real.

## Phase 5: the open rows (2026-10-14)

Runs of this phase went 6-9 at a time on one 12-core machine, so wall times compare within a pair, not with the tables above. Saves 0262 and 0142 as in phase 4 (`--hours 0.33 --report-every 5`), real baselines rerun on the current scripts (`out/ab5_0262_real`, `out/ab5_0142_real`; the 0142 log also skips `automation_2` as above). Neither save runs a heater or O2 generator script, so on 0262 only pressure moves and on 0142 only heat.

### Terraforming `park` and `standin` on 0262

| | real | `--standin terraforming=park` | `--standin terraforming=standin` |
| :--- | ---: | ---: | ---: |
| pressure gained | 0.5551 | 0.5552 | 0.5551 |
| TP at the end | 244,735 | 244,736 | 244,735 |
| credits / net worth at the end | 38,598 / 183,898 | same | same |
| errored / crashed | 0 / none | 0 / none | 0 / none |
| stand-in detail | | | 24 pressure scripts replaced, `pool` 0.99, `guardOff` [], `failed` [] |
| wall s, × real time | 551, 2.16 | 539, 2.21 | 504, 2.36 |

Accept: the ≤ 1 % deviation the open row asked for holds for both (pressure within 0.02 %; heat was verified on the midlate save in phase 1).

### Orchestrator `off` on 0262

| | real | `--standin orchestrator=off` |
| :--- | ---: | ---: |
| stopped / stubs | | `automation_1`, `automation_3`, `panel_1/2/3/5/7` (7 ghosts) / `power.shedded`, `cash.budget` |
| `can_spend()` grants (`[cash]` debug lines) | `pioneer_upgrade:pioneer_6` 650 cr at tick 349,393, `pioneer_13` 650 cr at 349,790, both `True: ok` | the same two, same ticks, same outcome; "free after" 23,498 vs 4,498 (the stub plans nothing, the real manager's pipeline reserved 19,000) |
| `power.shedded` at the end | `[]` | `[]` |
| pressure gained / TP at the end | 0.5551 / 244,735 | 0.5551 / 244,735 |
| credits / net worth at the end | 38,598 / 183,898 | 31,848 / 177,148 |
| running at the end / allowance steps | 61 / 819 | 66 / 684 |
| errored / crashed | 0 / none | 0 / none |
| wall s, × real time | 551, 2.16 | 551, 2.16 |

Gaps are the group's boundary: no central order plan (`supply_dock.order_plan`), so the Supply Docks fall back to `pick_best_order()` and finish fewer Earth orders (credits −6,750); no `ScriptParking`, so the 14 slots the real orchestrator parks stay running (66 instead of 61, and the allowance counts the 7 stopped slots as ghosts).

### Plants `cash` on 0022 (early, `0_cold_boot` tier)

Save `internals/sample_saves/20261008_7e5e168/saves/0022_t16826.json.gz` (tick 16,826, 13 heaters, the harvester selling; `latest scripts: tier 0_cold_boot: 43 slot(s) written, 0 lib module(s)`), `--hours 0.5 --report-every 5`. The real harvester sold 18 collections (8 Basic Plant at 125 cr, 10 Soil Sample at 50 cr) = 1,500 cr in 0.5 h, so the stated rate is 3,000 cr/h.

| | real | `--standin plants=cash,creditsPerHour=3000` |
| :--- | ---: | ---: |
| credits start / end | 77,276 / 149,498 | 77,276 / 149,498 |
| credits at 0.083 / 0.25 / 0.417 h | 105,260 / 105,858 / 149,653 | 105,385 / 105,583 / 149,403 |
| harvester income | 1,500 cr (18 sales) | 1,500 cr (`cash.added`) |
| other income (both) | Bio Exchange payouts (Bone Walker Forage Index, 28,000 cr each) | same |
| heat gained | 6.9603 | 6.9603 |
| running start / end | 23 / 10 (the heaters go idle at ~0.4 h in both runs) | 22 / 9 |
| errored / crashed | 0 / none | 0 / none |
| wall s, × real time | 45, 39.7 | 22, 81.0 |

### Power `trim`

0262: one subnet, `peak 715 W, 108 W per generator, keeping 8 of 8, stopped 0` (ceil(715 × 1.25 / 108) = 9 > 8), so the run equals the real one in every column (pressure 0.5551, credits 38,598, brownout 0 s, wall 521 s). 0142: only solar generators run a script (`turbine_1` is set, not started), `kept {}`, nothing to trim, every column but wall equal to real (heat 13.313, brownout 0 s; wall 399 s against 362 s real). A row with an effect needs surplus generators: 1160 below has 25, and `trim` still keeps them all.

### Save 1160: plants `produce` and power `trim`

Save `internals/sample_saves/20261008_7e5e168/saves/1160_t1707503.json.gz` (day 285, `plants_fields` achievement; 1 harvester, 8 Crop Automators with `harvest_yield` 2,104-2,519, 3 Plant Terraformers, 17 steam turbines and 8 oil generators on one subnet; `latest scripts: tier 4_controlpanel: 0 slot(s) written, 170 already current`, skips `automation_3` (`outpost_planner_automation`) and `panel_7` (`build_panel`)). `--hours 0.33 --report-every 10`; the real run was stopped after its 0.333 h report (`out/ab5_1160_real`, no `summary.json`), so its last column is 120 ticks later than the stand-ins' end and the shared comparison point is the 0.167 h report. The field grid is empty at this age: every unit of Forage comes from the automators, whose `harvest <sector> ok +N Forage` lines (plus one `output full, kept 2004, discarded 313`) summed over the 0.33 h window give 30 harvests, 69,284 Forage, all in the first 10 minutes (output room runs out: the automators hold 324,103 Forage at the start and the terraformers are idle, `switched off: fertilizer supports N/N Forage`). Stated rate: 210,000 Forage/h.

| | real | `--standin plants=produce,forage_h=210000` | `--standin power=trim` |
| :--- | ---: | ---: | ---: |
| heat / TP / running at 0.167 h | 37,552.5967 / 597,853 / 139 | 37,552.5967 / 597,853 / 125 | 37,552.5967 / 597,853 / 138 |
| credits at 0.167 h | 2,256,661 | 2,161,181 | 2,261,221 |
| heat gained at the end | 871.97 (12,000 ticks) | 862.24 (11,880 ticks) | 862.19 (11,880 ticks) |
| Forage produced | 69,284 harvested (68,971 kept, 313 discarded; the automators' output stacks grow 324,103 → 392,374, 700 of the kept units left them) | 68,833 added to the Inventory (`produce.added`; 210,000 × 0.33 = 69,300) | 69,284 harvested |
| plants scripts | 13 running | 13 stopped (harvester, seed maker, 3 terraformers, 8 automators), 13 ghosts, allowance 396 | 13 running, allowance 375 |
| `trim` | | | `peak 5053 W, 215 W per generator, keeping 25 of 25, stopped 0` (ceil(5053 × 1.25 / 215) = 30) |
| brownout s | 0 | 0 | 0 |
| errored / crashed | 0 / none | 0 / none | 0 / none |
| wall s to 0.167 h | 575 | 292 | 319 |

`produce` lands the stated Forage within 0.7 % of the real harvest and the rest of the world (heat, TP) is identical at the shared report; the credit gap is the group's boundary (the stopped terraformers place no fertilizer orders and the stopped automators no seed demand, so the factory and cash manager do other things). `trim` keeps every generator on all three saves: peak × `margin` exceeds the installed capacity (0262: 715 × 1.25 = 894 W > 8 × 108 W; 1160: 5,053 × 1.25 = 6,316 W > 25 × 215 W), so the script set matches the real run's. On 1160 the shared report still differs by one running script and +4,560 cr; the stopped set is empty, so that is run-to-run noise of the real world (orders, parking), not the mode. A row with an effect needs a save with surplus generators. Phase 7 below: the rule measured demand, not capacity; `trim` now rates generators by `power_output / throttle` and has its row on 1220.

## Phase 6: power `topup` and construction `instant` (2026-10-14)

Runs went 4 at a time (then 2); wall times compare within a pair. Real baselines rerun on the current scripts (`out/ab6_*`, never committed). `--hours 0.33 --report-every 5` as in phase 5.

### Power `topup` on 0142

Save 0142 (14 batteries of 500 Wh on four subnets; the metrics' `stored` is the home subnet's bank, 2,500 Wh). In the real run the bank cycles 1,182-2,449 Wh and the orchestrator's Power Guard sheds at night (`[POWER] Night eval ... shed 3/3 tier(s)` 19 times, `shed 1/3` 7 times); with `topup` it never sheds (`shed 0/3` on every eval).

| | real | `--standin power=topup` |
| :--- | ---: | ---: |
| `stored` at 0 / 0.083 / 0.167 / 0.25 / 0.33 h | 1,403 / 2,217 / 1,183 / 2,449 / 2,250 | 1,403 / 2,500 / 2,500 / 2,500 / 2,500 |
| brownout s | 0 | 0 |
| heat gained | 13.3198 | 13.9324 (+4.6 %) |
| TP at the end | 198,922 | 199,140 |
| credits / net worth at the end | 61,428 / 187,078 | same |
| running at the end / errored / crashed | 70 / 0 / none | 68 / 0 / none |
| `topup` detail | | 14 batteries, `addedWh` 8,988 |
| wall s, × real time | 251, 4.73 | 247, 4.81 |

The heat gap is the group's boundary, as intended: a bank that never drains means the Power Guard sheds no heater tier at night, so the heaters run through. `addedWh` (8,988 Wh over 0.33 h, ~27 kW·h per game day) is the energy the real grid lacked. Use `topup` for a target that must not be cut by power, never to size generators or batteries.

### Construction `instant` on 0262 and 0393

0262 (16 pending blueprints: 14 pipes, 1 power line, 1 outpost; 12 Pioneers): both runs build the same 15 jobs (pipes and the power line, `pioneer_3`) and finish each at the same tick (first `Build 'power_line_blueprint_235' finished` at tick 351,360, last `pipe_blueprint_98` at 357,179), every other column identical (pressure 5.2745, TP 244,735, credits 35,348, errored 0). `instant` reports `jobs` 15, `savedS` 17 (clock seconds): a pipe or line segment builds in 0.05 planet-hours = 1.25 s, below the builder's own poll cadence, so skipping it changes nothing. The outpost (4 planet-hours = 100 s) stays `pending` in both runs: no builder starts it within the window.

0393 (`20261008_7e5e168/saves/0393_t579655.json.gz`, day ~97; one `active` outpost job, `outpost_blueprint_5` by `pioneer_4`, progress 0.208, 79 s left at the start; 12 Pioneers, no other blueprint):

| | real | `--standin construction=instant` |
| :--- | ---: | ---: |
| `Build 'outpost_blueprint_5' finished` at tick | 580,471 (790 ticks after the start, the 79 s left) | 579,681 (9 ticks after the start) |
| `instant` detail | | `jobs` 1, `savedS` 79.1, `wait` true |
| heat gained / TP at the end | 16.4378 / 293,518 | 16.4378 / 293,518 |
| credits / net worth at the end | 35,192 / 176,692 | 30,792 / 168,292 |
| `[cash] pioneer_upgrade` purchases | 16, 21,100 cr | 24, 30,700 cr |
| running at the end / errored / crashed | 71 / 0 / none | 70 / 0 / none |
| wall s, × real time | 289, 4.12 | 352, 3.38 (ran alone against 4 parallel runs; not comparable) |

The first `instant` run had no builder-wait patch and finished the outpost at the same tick as real: the builder's construction command sleeps for the whole remaining build time, whatever the job's state (now the `instantBuild` anchor, [standins.md](standins.md) `instant` row). With the patch the outpost exists 790 ticks earlier, and the atmosphere is unchanged. The credit gap is downstream of the earlier outpost: the fleet manager buys eight more Pioneer upgrades (+9,600 cr) in the window, the reagent purchases are the same. Accept: the mode removes the build time and nothing else; for a target that reads the fleet's spending, read the later world as a shifted timeline, not a different one.

## Phase 7: power `trim` by rated output, `topup` per subnet (2026-10-14)

Runs went 4 at a time; wall times compare within a pair. `--hours 0.33 --report-every 5` as before. Outputs in `out/ab7_*` (never committed).

### Power `trim` on 1220

Phase 5 kept every generator because `perGen` was `generated / n`: the generator scripts throttle to demand, so that is the demand, not the capacity. `trim` now rates each running turbine or oil generator by `data.power_output / data.throttle` (the worker's output is linear in the throttle; 108 W per tier-1 turbine, 700 W per oil generator on this save) and keeps the highest-rated until the kept rating covers `peak × margin` ([standins.md](standins.md) `trim` row).

Save 1220 (`20261008_7e5e168/saves/1220_t1809758.json.gz`, day ~302; one subnet, 13 turbines and 8 oil generators, 12 batteries, 30,000 Wh; 21 generator scripts running in the save, 12 at the trim decision under the current scripts). Trim line: `peak 4067 W, rated 6032 W over 12 generators (0 pinned), keeping 8 (5600 W), stopped 4` (4 turbines; 4,067 × 1.25 = 5,084 W, the 8 oil generators cover it).

| | real | `--standin power=trim` |
| :--- | ---: | ---: |
| `consumed` W at 0 / 0.083 / 0.167 / 0.25 / 0.33 h | 3,550 / 3,826 / 3,736 / 6,454 / 6,667 | 3,550 / 3,712 / 3,886 / 6,712 / 6,716 |
| `generated` W | 3,932 / 4,075 / 2,804 / 7,004 / 7,004 | 3,932 / 3,790 / 6,572 / 6,572 / 6,572 |
| `stored` Wh | 30,000 / 30,000 / 13,456 / 11,540 / 18,245 | 30,000 / 29,962 / 8,763 / 13,030 / 12,904 |
| brownout s | 0 | 0 |
| O2 gained / heat gained | 860.112 / 0 | 860.112 / 0 |
| TP at the end | 667,169 | 667,061 |
| credits / net worth at the end | 356,308 / 427,008 | same |
| running at the end / errored / crashed | 149 / 0 / none | 143 (+4 ghosts) / 0 / none |
| wall s, × real time | 736, 1.62 | 732, 1.62 |

The effect is real and bounded: demand rises to 6.7 kW after the warm-up (the day's load, above the 4.1 kW warm-up peak), the trimmed grid tops out at 6,572 W (the real one at 7,004 W: the 9 turbines the scripts start later stay real in both runs), the bank drains 5.3 kWh more and no brownout lands in the window. The atmosphere is identical; the TP gap (−108) is run-to-run noise (credits and net worth are the same). `trim` runs once: a warm-up that misses the day's peak under-keeps, so set `warmupTicks` to cover one, or use `topup` for a target that must not be cut.

### Power `topup` on one subnet (0142)

Save 0142 as in phase 6 (four subnets: `subnet_3` is the home bank the metrics' `stored` reports, 5 batteries and 12 heaters; `subnet_0` is Outpost 1, 3 batteries and 10 heaters; `subnet_1` Outpost 2, `subnet_2` Outpost 3). `--standin power=topup,subnets=subnet_0`: 3 batteries, `addedWh` 2,304 (the full-planet run in phase 6: 14 batteries, 8,988).

| | real | `--standin power=topup,subnets=subnet_0` | phase 6 `--standin power=topup` (all) |
| :--- | ---: | ---: | ---: |
| `stored` (home bank) at 0 / 0.083 / 0.167 / 0.25 / 0.33 h | 1,403 / 2,217 / 1,183 / 2,449 / 2,250 | 1,403 / 2,215 / 1,177 / 2,449 / 2,252 | 1,403 / 2,500 / 2,500 / 2,500 / 2,500 |
| heat gained | 13.3190 | 13.9324 (+4.6 %) | 13.9324 |
| TP at the end | 198,921 | 199,140 | 199,140 |
| credits / net worth at the end | 61,428 / 187,078 | same | same |
| running at the end / errored / crashed | 70 / 0 / none | 70 / 0 / none | 68 / 0 / none |
| wall s, × real time | 275, 4.31 | 275, 4.32 | 247, 4.81 |

The home bank cycles as in the real run (the other three grids stay real), and the heat gain equals the full-planet `topup`: on this save the whole phase 6 boundary (+4.6 % heat) is Outpost 1's night shed, the home grid sheds nothing that reaches the atmosphere. `subnets` is the way to keep the grid a target reads real and still remove another outpost's power limit.

## Phase 8: power `trim` re-evaluation (2026-10-14)

Phase 7's `trim` was one-shot: on 1220 the warm-up peak (4.1 kW) missed the day's load (6.7 kW) and the 8 kept generators capped the grid at 6,572 W for the rest of the run. `trim` now re-evaluates every `reevalTicks` (default `warmupTicks`, 600) and restarts stopped generators, highest-rated first, until the window's peak `consumed × margin` is covered ([standins.md](standins.md) `trim` row). Same pair as phase 7: `--save internals/sample_saves/20261008_7e5e168/saves/1220_t1809758.json.gz --hours 0.33 --report-every 5`, default `--log-levels` (none given, so `{"*": "debug"}`); the two runs went in parallel. Outputs in `out/ab8_*` (never committed).

Trim lines: `peak 4067 W, rated 6032 W over 12 generators (0 pinned), keeping 8 (5600 W), stopped 4`, then before the 0.083 h report `window peak 4693 W over kept 5600 W, restarted 3 (turbine_13, turbine_14, turbine_18) to 5924 W, 1 still stopped`, and between 0.167 h and 0.25 h `window peak 5120 W over kept 5924 W, restarted 1 (turbine_2) to 6032 W, 0 still stopped`. Summary: `kept 12, rated {total 6032, kept 6032}, stopped 0, restarted 4, evals 18`, ghosts 0.

| | real | `--standin power=trim` (re-evaluating) | phase 7 `trim` (one-shot) |
| :--- | ---: | ---: | ---: |
| `consumed` W at 0 / 0.083 / 0.167 / 0.25 / 0.33 h | 3,550 / 3,826 / 3,736 / 6,454 / 6,667 | 3,550 / 3,712 / 3,886 / 6,712 / 6,716 | 3,550 / 3,712 / 3,886 / 6,712 / 6,716 |
| `generated` W | 3,932 / 4,075 / 2,804 / 7,004 / 7,004 | 3,932 / 4,114 / 1,296 / 7,004 / 7,004 | 3,932 / 3,790 / 6,572 / 6,572 / 6,572 |
| `stored` Wh | 30,000 / 30,000 / 13,456 / 11,540 / 18,245 | 30,000 / 30,000 / 11,884 / 13,898 / 18,747 | 30,000 / 29,962 / 8,763 / 13,030 / 12,904 |
| brownout s | 0 | 0 | 0 |
| O2 gained / heat gained | 860.112 / 0 | 860.112 / 0 | 860.112 / 0 |
| TP at the end | 667,169 | 667,061 | 667,061 |
| credits / net worth at the end | 356,308 / 427,008 | same | same |
| running at the end / errored / crashed | 149 / 0 / none | 147 (+0 ghosts) / 0 / none | 143 (+4 ghosts) / 0 / none |
| wall s, × real time | 689, 1.72 | 692, 1.72 | 732, 1.62 |

The re-evaluation closes phase 7's gap: the first window after the trim already carries a higher peak (4.7 kW), three turbines come back, the second rise (5.1 kW) brings the last one, and from 0.25 h the grid makes the real run's 7,004 W. The bank ends above the real run's (+0.5 kWh) and the atmosphere, credits and net worth are identical; the TP gap (−108) is the same run-to-run noise as in phase 7. The cost is the speed-up: with every generator restarted the ghosts are 0, so the run is as expensive as the real one. `trim` therefore saves scripts only while the load stays under the warm-up peak; its value is a safe cut that undoes itself when the day's load arrives, not a lasting one. The `generated` dip at 0.167 h (1,296 W against 2,804 W real) is a snapshot of the solar night with the generators throttled against a full-ish bank (both runs' `consumed` is 3.7-3.9 kW there and neither browns out), not a trim effect: the trimmed grid at that report had 11 of 12 generators running.

## Phase 9: power `trim` hysteresis (2026-10-14)

Phase 8's re-evaluation only restarted: on a daily load the kept set grows to the full count at the first day peak and stays there. `trim` now takes `quietWindows` (default 0 = phase 8 behaviour): after each re-evaluation a restarted generator stops again, lowest-rated first, when the kept rating without it still covers the highest window peak of the last k windows × `margin`; the trim's own kept set is the floor ([standins.md](standins.md) `trim` row). Same save as phases 7 and 8, twice as long: `--save internals/sample_saves/20261008_7e5e168/saves/1220_t1809758.json.gz --hours 0.67 --report-every 5`, default `--log-levels` (`{"*": "debug"}`, no `[POWER] Night eval` line in either console log), stand-in `--standin power=trim,quietWindows=3` (3 × 600 ticks = 7.2 planet-hours); the two runs went in parallel. Outputs in `out/ab9_*` (never committed).

Trim lines, in order: `peak 4067 W, rated 6032 W over 12 generators (0 pinned), keeping 8 (5600 W), stopped 4` at tick 600; `window peak 4693 W over kept 5600 W, restarted 3 (turbine_13, turbine_14, turbine_18) to 5924 W, 1 still stopped` before the 0.083 h report; `3 quiet windows, peak 4346 W under kept 5924 W, stopped again 3 (turbine_18, turbine_14, turbine_13) to 5600 W, 4 stopped` before 0.167 h; `window peak 7016 W over kept 5600 W, restarted 4 (turbine_13, turbine_14, turbine_18, turbine_2) to 6032 W, 0 still stopped` before 0.25 h; nothing after. Summary: `kept 12, rated {total 6032, kept 6032}, stopped 0, restarted 7, restopped 3, evals 39`, ghosts 0, no warning.

| | real | `--standin power=trim,quietWindows=3` |
| :--- | ---: | ---: |
| `consumed` W at 0 / 0.083 / 0.167 / 0.25 / 0.333 / 0.417 / 0.5 / 0.583 / 0.667 h | 3,550 / 3,826 / 3,820 / 6,814 / 3,557 / 3,487 / 6,422 / 3,766 / 7,059 | 3,550 / 3,712 / 3,970 / 6,574 / 6,557 / 5,387 / 7,325 / 5,013 / 7,390 |
| `generated` W | 3,932 / 4,075 / 2,804 / 4,179 / 5,261 / 3,811 / 7,004 / 5,515 / 5,552 | 3,932 / 4,114 / 972 / 7,004 / 7,004 / 5,304 / 7,004 / 5,312 / 7,004 |
| `stored` Wh | 30,000 / 30,000 / 13,429 / 18,610 / 16,637 / 30,000 / 11,663 / 21,191 / 28,033 | 30,000 / 30,000 / 9,534 / 13,496 / 20,536 / 11,975 / 18,162 / 21,082 / 11,746 |
| brownout s | 0 | 0 |
| TP at the end | 669,990 | 672,392 |
| credits / net worth at the end | 881,308 / 952,008 | 884,308 / 955,008 |
| running at the end / errored / crashed | 147 / 0 / none | 146 (+0 ghosts) / 0 / none |
| wall s, × real time | 1,575, 1.53 | 1,606, 1.50 |

The hysteresis works as designed: the three turbines the first window restarted (4.7 kW peak) stop again three quiet windows later (peaks ≤ 4.3 kW), so the run carries 4 ghosts through the warm night instead of phase 8's 1, and the day peak (7.0 kW) restarts all four. After that nothing stops again: with `margin` 1.25 a second stop of the smallest turbine (108 W) needs three consecutive windows with peaks ≤ 4,739 W, and the trimmed run's load never fell below 5.0 kW at a report. The real run's load did (3.5-3.8 kW at the 0.333, 0.417 and 0.583 h reports), with lower generation and a draining bank in between; the trimmed run holds 7,004 W (every generator up) and a higher load, and ends 2,400 TP and 3,000 credits ahead. Not a trim effect to tune against: this real run differs from phase 8's real run at the same ticks (0.25 h: 4,179 W generated and 18,610 Wh stored here against 7,004 W and 11,540 Wh there, 0.333 h TP 666,689 against 667,169), so the run-to-run spread of a real 1220 run is as large as the pair's gap. Wall time differs between pairs too (1.53× here, 1.72× in phase 8), and some scripts read real time (`game_clock.real_seconds_per_hour()`). Net: `quietWindows` returns a restart to the ghosts when a short peak passes, costs nothing when the load stays up, and never browns out; on 1220 the speed-up is still none once the day load arrives.

## Phase 10: power `trim` `floor` `keepMin` (2026-10-14)

Phase 9's second stop only applied to restarted generators: a warm-up that sees the day's peak keeps the day's generators all night. `trim` now takes `floor` (default `warmup` = phase 9 behaviour): with `floor` `keepMin` the trim's own kept generators are second-stop candidates too, under the same hysteresis, down to `keepMin` rated unpinned generators per subnet ([standins.md](standins.md) `trim` row). Same save and length as phase 9: `--save internals/sample_saves/20261008_7e5e168/saves/1220_t1809758.json.gz --hours 0.67 --report-every 5`, default `--log-levels` (`{"*": "debug"}`, no `[POWER] Night eval` line in any console log), stand-in `--standin power=trim,quietWindows=3,floor=keepMin`. Each run went alone (nothing else running), the real one twice, every run on the c652412 scripts (`diff -rq --strip-trailing-cr` over the runs' `latest_scripts` is empty). Outputs in `out/ab10_*` (never committed).

**Run-to-run spread: none.** The two real runs are byte-identical (`cmp` on the two `console.log` files, 120,561 lines each, every metric at every report), and both match phase 9's real run at every report (TP 669,990). The trimmed run matches phase 9's trimmed run the same way (same four trim lines, TP 672,392, `restarted 7, restopped 3`). The phase 9 handoff's "noise" (phase 8's real run differing at the same ticks) came from the scripts, not the sim: a run deploys the repo's working-tree `scripts/`, and 8a532c5 (storage outposts) and c40119a (sim speed log) landed between the phase 8 and phase 9 runs. A 1220 TP or credit gap between two runs of the same scripts is a real effect. Wall time alone: 1,203 s and 1,178 s real (2.0× real time), 1,263 s trimmed, against 1,575 s and 1,606 s in phase 9's parallel pair.

**The floor never fired on this pair.** The trimmed run is phase 9's run: 4 stopped at the trim (kept 5,600 W), 3 restarted at the 4.7 kW window, stopped again three quiet windows later, all 4 restarted at the 7.0 kW day peak, nothing after. For the floor to cut the warm-up's lowest kept generator (the 700 W oil generator) in the first night, three consecutive windows need peaks ≤ 3,920 W (`(5,600 − 700) / 1.25`); the night's windows peaked at 4,346 W. After the day peak the smallest cut (a 108 W turbine) needs peaks ≤ 4,739 W, and the load stayed ≥ 5.0 kW at every later report. So the A/B row equals phase 9's row (see there); the floor costs nothing when it has nothing to cut.

| | real (both runs) | `--standin power=trim,quietWindows=3,floor=keepMin` |
| :--- | ---: | ---: |
| `consumed` W at 0 / 0.083 / 0.167 / 0.25 / 0.333 / 0.417 / 0.5 / 0.583 / 0.667 h | 3,550 / 3,826 / 3,820 / 6,814 / 3,557 / 3,487 / 6,422 / 3,766 / 7,059 | 3,550 / 3,712 / 3,970 / 6,574 / 6,557 / 5,386 / 7,325 / 5,012 / 7,390 |
| `generated` W | 3,932 / 4,075 / 2,804 / 4,179 / 5,261 / 3,811 / 7,004 / 5,515 / 5,552 | 3,932 / 4,114 / 972 / 7,004 / 7,004 / 5,304 / 7,004 / 5,312 / 7,004 |
| brownout s | 0 | 0 |
| TP at the end | 669,990 | 672,392 |
| credits / net worth at the end | 881,308 / 952,008 | 884,308 / 955,008 |
| running at the end / errored / crashed | 147 / 0 / none | 146 (+0 ghosts) / 0 / none |
| wall s, × real time | 1,203 and 1,178, 2.0 | 1,263, 1.91 |

**The floor firing (not a row).** A first trimmed run (`out/ab10_1220_trim_mixedlibs`) went with a parallel session's uncommitted `lib/fluid_routing.py` in the deployed scripts, so it is not comparable to the real runs; its load pattern differed enough to show the mechanism: `3 quiet windows, peak 3889 W under kept 5600 W, stopped again 1 (oil_generator_8) to 4900 W, 5 stopped` in the first night, one window later `window peak 4227 W over kept 4900 W, restarted 1 (oil_generator_8) to 5600 W`, and after the day peak `3 quiet windows, peak 4280 W under kept 6032 W, stopped again 4 (turbine_2, turbine_18, turbine_14, turbine_13) to 5600 W` with the four restarted two by two over the next windows; summary `restarted 12, restopped 8`, no brownout, no warning, ghosts 0 at the end. The oil-generator cut had 39 W of slack over `margin` 1.25 and flapped once (one stop, one restart: the hysteresis bound holds, the cut bought nothing). A margin or window count tuned for the floor is open.

## Phase 11: power `trim` `stopMargin`, the floor fires (2026-10-14)

Phase 10's second stop and restart shared one `margin`, so a cut that lands just over the line is one dip away from a restart, and a lower `margin` alone would restart what it stops. `trim` now takes `stopMargin` (default `margin`): the second stop needs `max peak × stopMargin`, the restart `peak × margin`, the gap is the hysteresis band in watts ([standins.md](standins.md) `trim` row and design note). Same save as phases 7 to 10, 1 h instead of 0.67 (two more load cycles): `--save internals/sample_saves/20261008_7e5e168/saves/1220_t1809758.json.gz --hours 1 --report-every 5`, default `--log-levels`, stand-in `--standin power=trim,quietWindows=3,floor=keepMin,margin=1.05,stopMargin=1.1` (the margin lowered so the floor has something to cut: at 1.25 the first night's 4,346 W peaks never let the 700 W oil generator go, see phase 10). Each run alone, both on the 6a601b3 scripts (`diff -rq --strip-trailing-cr` over the two `latest_scripts` is empty; the phase 10 rows ran on c652412, so their TP is not this real run's: 670,749 here against 669,990 at 0.667 h). Outputs in `out/ab11_*` (never committed).

**The floor fires, and the band is too narrow for a 700 W step.** 14 trim lines over 58 re-evaluations: the warm-up keeps 7 of 12 (4,900 W at 1.05 over the 4,067 W peak; phase 10 kept 8 at 1.25); each night the floor cuts the oil generators one by one (`3 quiet windows, peak 3718 W under kept 4900 W, stopped again 1 (oil_generator_7) to 4200 W`), each day peak (7.2 kW) restarts all, and three quiet windows later the turbines go first and the oil generators after. Summary `restarted 19, restopped 14`, no brownout, no warning, ghosts 0 at the end (the last day peak restarted everything). Flaps: `oil_generator_8` stopped and restarted on a sub-day dip three times (`window peak 4783 W over kept 4900 W, restarted 1`), `oil_generator_7` once right after its cut (`window peak 4335 W over kept 4200 W`): a 5 % band at a 4.3 kW load is about 215 W, under the 700 W step of the generator it gates, so the cut lands inside the restart's reach. For a step of r W at a peak of p W the band must satisfy `stopMargin − margin ≥ r / p` (0.16 here), or `quietWindows` carries the hysteresis alone, as in phases 9 and 10.

| | real | `--standin power=trim,quietWindows=3,floor=keepMin,margin=1.05,stopMargin=1.1` |
| :--- | ---: | ---: |
| `consumed` W at 0 / 0.167 / 0.25 / 0.417 / 0.5 / 0.667 / 0.75 / 0.917 / 1 h | 3,550 / 3,783 / 6,934 / 3,799 / 6,576 / 7,096 / 5,453 / 4,528 / 4,161 | 3,550 / 3,446 / 6,612 / 3,701 / 3,260 / 3,861 / 4,051 / 7,312 / 4,409 |
| `generated` W | 3,932 / 1,404 / 7,004 / 5,368 / 1,797 / 7,004 / 7,004 / 2,236 / 4,676 | 3,932 / 972 / 7,004 / 4,238 / 2,372 / 4,562 / 3,072 / 7,004 / 4,977 |
| brownout s | 0 | 0 |
| TP at 0.667 h / at the end | 670,749 / 674,812 | 670,536 / 673,838 |
| credits / net worth at the end | 1,235,958 / 1,306,658 | 1,077,448 / 1,148,148 |
| running at the end / errored / crashed | 149 / 0 / none | 141 (+0 ghosts) / 0 / none |
| wall s, × real time | 1,768, 2.04 | 1,882, 1.91 |

The TP gap is 0.14 %. The credit gap is sale timing: both runs sit near 1.07 M at 0.917 h, the real run books one more sale (+168,750) before the hour, the trimmed run's lands later (the day peaks and the sales fall at different ticks once the load pattern differs; phase 10 had the same +3,000 offset the other way). The trimmed run's load pattern drifts from the real one's from 0.5 h on (3,260 W against 6,576 W at the 0.5 h report, 7,312 W against 4,528 W at 0.917 h): the day peaks (7.2 to 7.3 kW) and the nights (3.7 to 4.4 kW) match, their timing does not. Not traced; phases 8 to 10 showed the same drift at a smaller scale.

## Phase 12: power `trim` `stopMargin` `step`, the open floor rows (2026-10-14)

Phase 11's 5 % band was under the 700 W oil-generator step it gated, and the right numeric band depends on which generator is lowest-rated at the time. `trim` now takes `stopMargin` `step`: the second stop of a generator rated r needs `max peak × margin + r`, so the band in watts is the step it gates, derived per cut ([standins.md](standins.md) `trim` row and design note). Same save and length as phase 11: `--save internals/sample_saves/20261008_7e5e168/saves/1220_t1809758.json.gz --hours 1 --report-every 5`, default `--log-levels`, each run alone, one after the other. The real column is phase 11's run: `scripts/` did not move between 6a601b3 and b354494 and `diff -rq --strip-trailing-cr` over the four `latest_scripts` is empty. Three trimmed rows: `--standin power=trim,quietWindows=3,floor=keepMin,margin=1.05,stopMargin=step`, the phase 11 open row `--standin power=trim,quietWindows=3,floor=keepMin,margin=1.05,stopMargin=1.25` (band 0.2 ≥ 700 / 4,300) and the other open row `--standin power=trim,reevalTicks=300,quietWindows=6,floor=keepMin,margin=1.05,stopMargin=step` (the same 1,800-tick hysteresis, a window of 300). Outputs in `out/ab12_*` (never committed).

**The step band holds the floor at the first cut.** All three rows warm up to the phase 11 kept set (7 of 12, 4,900 W over the 4,067 W peak) and restart `oil_generator_8` on the first sub-day peak (4,728 W). From there the `step` row cuts it again three quiet windows later (`peak 3718 W under kept 5600 W, stopped again 1 (oil_generator_8) to 4900 W`) and never cuts `oil_generator_7`: 4,200 W would have to cover 3,718 × 1.05 + 700 = 4,604 W. Phase 11 cut it and restarted it the next window. Each day peak (6.7 to 7.3 kW) restarts all five, three quiet windows later the four turbines go, and the oil generator only once the night peak is under 4,000 W. 11 trim lines over 58 re-evaluations, `restarted 19, restopped 14` (the same totals as phase 11 by coincidence: there the four extra events were the `oil_generator_7` and `oil_generator_8` flaps, here they are the day cycles), no brownout, no warning, ghosts 0 at the end. The 1.25 row behaves the same with one difference: after the first day peak the night (3,910 W) cuts all five at once (3,910 × 1.25 = 4,888 ≤ 4,900), where `step` cut the turbines first and the oil generator a window later; 8 trim lines, `restarted 15, restopped 10`. Both rows are flap-free: no generator is restarted in the window after its cut. The `reevalTicks` 300 row (`quietWindows` 6) restarts a window of 300 sooner at the day ramp (6,168 W at the first day restart against 7,272 W for the 600-tick windows, so the restart comes before the peak) and ends the hour in the night with 5 stopped (`restarted 10, restopped 10, evals 117`, ghosts 5). Its first-night battery low is 8,856 Wh against 7,711 Wh for the 600-tick rows (the 0.25 h report); the 0.75 h low (7,774 Wh) is the same as theirs, so the shorter window buys one dip, not the pattern.

| | real (phase 11) | `stopMargin=step` | `stopMargin=1.25` | `reevalTicks=300,quietWindows=6,stopMargin=step` |
| :--- | ---: | ---: | ---: | ---: |
| `consumed` W at 0 / 0.167 / 0.25 / 0.417 / 0.5 / 0.667 / 0.75 / 0.917 / 1 h | 3,550 / 3,783 / 6,934 / 3,798 / 6,576 / 7,096 / 5,453 / 4,528 / 4,161 | 3,550 / 3,446 / 6,702 / 4,959 / 3,615 / 3,926 / 7,287 / 6,607 / 3,750 | 3,550 / 3,446 / 6,702 / 4,959 / 3,615 / 3,902 / 7,449 / 6,852 / 3,654 | 3,550 / 3,446 / 6,744 / 6,574 / 3,930 / 7,187 / 6,972 / 3,599 / 3,597 |
| `generated` W | 3,932 / 1,404 / 7,004 / 5,368 / 1,797 / 7,004 / 7,004 / 2,236 / 4,676 | 3,932 / 972 / 7,004 / 5,670 / 5,175 / 4,279 / 7,004 / 7,004 / 1,404 | 3,932 / 972 / 7,004 / 5,670 / 972 / 4,381 / 7,004 / 7,004 / 1,404 | 3,932 / 972 / 7,004 / 7,004 / 4,560 / 5,727 / 7,004 / 4,118 / 4,893 |
| `stored` Wh minimum (at) | 9,704 (0.917 h) | 7,711 (0.25 h) | 7,711 (0.25 h) | 7,774 (0.75 h) |
| trim restarted / restopped / evals | | 19 / 14 / 58 | 15 / 10 / 58 | 10 / 10 / 117 |
| brownout s | 0 | 0 | 0 | 0 |
| TP at 0.667 h / at the end | 670,749 / 674,812 | 671,450 / 674,812 | 671,450 / 674,757 | 671,196 / 674,795 |
| credits / net worth at the end | 1,235,958 / 1,306,658 | 703,798 / 774,498 | 535,608 / 606,308 | 927,968 / 998,668 |
| running at the end / errored / crashed | 149 / 0 / none | 142 (+0 ghosts) / 0 / none | 137 (+0 ghosts) / 0 / none | 120 (+5 ghosts) / 0 / none |
| wall s, × real time | 1,768, 2.04 | 1,593, 2.26 | 1,390, 2.59 | 1,637, 2.20 |

TP is within 0.01 % in every row (the `step` row ends on the real run's 674,812 exactly). **The credit gap is the `spire_25` sale.** The real run books 349,000 at 0.167 h, 525,000 (`spire_25`, glass 4,000 and silicon 20,000) at 0.417 h, 200,300 at 0.833 h and 168,750 at 1 h. Every trimmed row books the 349,000 at 0.25 h. The `reevalTicks` 300 row books `spire_25` with the next sale at 0.75 h (579,220), the two 600-tick rows end the hour with `spire_25` open at silicon 19,964 (`final_save.json` `orders`) and only the small sales after it (135,800 at 0.75 h, 59,300 at 0.833 h, the `step` row 164,390 at 1 h). Phase 11's trimmed run booked it at 0.75 h. Silicon is mined ore (rover drills), not a Smelter product, and no row has a brownout, so the power served is not the cause; the trimmed rows' vehicle and sale timing drifts from the real run's (open item 5 of the phase 11 handoff, now with a 36-unit shipment as the visible symptom). The two 600-tick rows are metric-identical up to 0.5 h and diverge after the first night's cut (the turbines go a window apart), so the drift is seeded by the first stop at the warm-up, not by the band.

## Phase 13: power `trim` refused stops, the open rows (2026-10-15)

Code: `#stop` read only the command envelope's `ok`, but the game's `script.stop` answers a refusal inside the result (`{ok: false}`), so a refused stop counted as stopped and the refused-stop branch of the re-evaluation never ran. It now reads the result; a refusal at the first trim stop keeps the generator counted as kept and makes it a second-stop candidate, and a rating-0 pool entry (the stopped slots of a part-refused generator) no longer moves the kept count ([standins.md](standins.md) `trim` row). No row below logs a refused stop, so the change has no effect on them. Same save, length and flags as phase 12 (`--save internals/sample_saves/20261008_7e5e168/saves/1220_t1809758.json.gz --hours 1 --report-every 5`, default `--log-levels`, each run alone, one after the other). `scripts/` moved since phase 12 (f59b9aa, c6de389, 57b630f), so the real column is a new run; `diff -rq --strip-trailing-cr` over the four `latest_scripts` is empty. Rows: the open phase 12 row `--standin power=trim,reevalTicks=300,quietWindows=6,floor=keepMin,margin=1.05,stopMargin=1.25` (the 300-tick window with the numeric band), `--standin power=trim,warmupTicks=10000,quietWindows=3,floor=keepMin,margin=1.05,stopMargin=step` and the same with `reevalTicks=600` (a warm-up that sees the first day peak, so no stop at the warm-up and the floor does all the cutting). Outputs in `out/ab13_*` (never committed).

**A trim that stops nothing adds no drift.** The `warmupTicks=10000` row sees a 7,357 W peak over 7,004 W rated (21 generators by then) and keeps all of them. Its `reevalTicks` defaults to `warmupTicks`, so three quiet windows (30,000 ticks) do not fit in the rest of the hour: nothing is stopped, and its `console.log` is byte-identical to the real run's (metrics identical, not in the table). With `reevalTicks=600` the floor cuts from 0.33 h on (`turbine_4` first, then 7 and 5 turbines over the next quiet windows down to 5,600 W), restarts all 12 for the day ramp (6,056 W, then 7,532 W) and cuts 12 again in the night: `restarted 12, restopped 25, evals 43`, 13 ghosts at the end. One restart is refused: `turbine_4` answers `offline` and is dropped from the pool (its slot stays a ghost), the existing restart branch. The 300-tick `1.25` row follows the phase 12 pattern (warm-up cut to 4,900 W, `oil_generator_8` back on the first sub-day peak and cut six quiet windows later, all five back at the day ramp) and then cuts the turbines one or two at a time: `restarted 8, restopped 7, evals 117`, 4 ghosts.

| | real | `reevalTicks=300,quietWindows=6,stopMargin=1.25` | `warmupTicks=10000,reevalTicks=600,stopMargin=step` |
| :--- | ---: | ---: | ---: |
| `consumed` W at 0 / 0.167 / 0.25 / 0.417 / 0.5 / 0.667 / 0.75 / 0.917 / 1 h | 3,550 / 3,500 / 6,697 / 6,254 / 6,762 / 4,232 / 4,376 / 3,869 / 4,519 | 3,550 / 3,693 / 6,633 / 4,288 / 6,694 / 4,574 / 6,881 / 4,124 / 3,882 | 3,550 / 3,500 / 6,697 / 6,254 / 6,685 / 4,283 / 7,457 / 3,942 / 4,255 |
| `generated` W | 3,932 / 3,138 / 7,004 / 5,125 / 6,572 / 6,078 / 6,073 / 4,098 / 5,137 | 3,932 / 1,090 / 6,304 / 5,672 / 6,022 / 5,956 / 6,304 / 4,882 / 972 | 3,932 / 3,138 / 7,004 / 5,125 / 5,924 / 5,868 / 6,896 / 4,108 / 4,758 |
| `stored` Wh minimum (at) | 8,686 (0.583 h) | 8,948 (0.583 h) | 8,031 (0.75 h) |
| trim restarted / restopped / evals | | 8 / 7 / 117 | 12 / 25 / 43 |
| brownout s | 0 | 0 | 0 |
| TP at 0.667 h / at the end | 673,000 / 674,771 | 671,505 / 674,778 | 672,578 / 674,766 |
| credits / net worth at the end | 1,135,288 / 1,205,988 | 1,426,758 / 1,497,458 | 1,062,608 / 1,133,308 |
| running at the end / errored / crashed | 136 / 0 / none | 137 (+4 ghosts) / 0 / none | 132 (+13 ghosts) / 0 / none |
| wall s, × real time | 1,235, 2.92 | 1,268, 2.84 | 1,199, 3.00 |

TP is within 0.01 % at the end in every row, no brownout, no warning besides the `turbine_4` restart. **The `spire_25` shortfall does not come back.** Every row, the real one included, books `spire_25` (about 524,000) at 0.417 h and ends with it complete; phase 12's 600-tick rows ended 36 silicon short. The first log differences in the phase 12 pair (`out/ab11_1220_real`, `out/ab12_1220_trim_step`) are not vehicle lines: from about 600 ticks on the stopped turbines no longer log, and in the trimmed run `thermal_cap_3` reports `gas_tank_16 stalled while full` and opens its release valve (the steam the stopped turbines no longer take, tick about 1,810,375). The first vehicle fork comes later: at tick 1,811,707 `drone_9` delivers only its titanium at `drone_station_2` (glass and iron "still aboard", Depot not draining) and retries at 1,812,111, where the real run delivers the full load at 1,812,067; no depot or power line explains it. From there the 2,000-silicon load the real run's `drone_9` hauls (1,822,492) comes from `drone_10` in the trimmed run (1,500 and 1,379). The credit timing differs between rows in both directions (the 300-tick row ends 291,000 above the real run, the `reevalTicks=600` row 73,000 below), so this is timing drift after the first stop, not a deficit of the stand-in.

## Phase 14: left-over sweep, revival guard, profile; the 1631 factory rows (2026-10-15)

Code: a stopped or undeployed script's archive records stay behind and the real scripts read them as live (readers age by `tick` only; the game's `ArchiveCleaner` runs from a button). `standins.mjs` now sweeps them by shape ([standins.md](standins.md) "Left-overs": id-keyed entries, owner fields, `<prefix>.<id>` keys; a key a running writer keeps filling is left alone after three passes in a row), re-stops a stopped script a real script started again (revival guard), and reads what is specific to this repo's scripts from `profiles/code_terraform.json` ("Profile"; `--script-set none` for a foreign script set). Save `internals/sample_saves/20261008_7e5e168/saves/1631_t2294802.json.gz` (late game, 153 running scripts), `--hours 1 --report-every 10 --paid-debug --sticky-fluids`, three runs in parallel then two, `diff -rq --strip-trailing-cr` over the five `latest_scripts` empty. The real column is a new run: `scripts/` moved since the phase 14 handoff's field report (fabricator and smelter backstop 1200 to 3000), so its fabricator numbers differ from that report's (73 units). Outputs in `out/ab14_1631_*` (never committed).

| | real | `terraforming=scale` | `biomass=off` | both | both, `sweep=false` |
| :--- | ---: | ---: | ---: | ---: | ---: |
| wall s | 1,325 | 1,207 | 1,262 | 1,091 | 1,093 |
| allowance at the end (`n` / ghosts / steps) | 153 / 0 / 326 | 133 / 28 / 310 | 166 / 9 / 285 | 112 / 37 / 335 | 109 / 37 / 342 |
| O2 gained | 13,105 | 11,295 (−14 %) | 13,105 | 11,295 | 11,295 |
| biomass gained | 16,050 | 16,184 | 6,501 | 6,501 | 6,538 |
| TP at the end | 789,572 | 789,407 | 788,643 | 788,319 | 788,321 |
| credits at the end | 615,063 | 615,063 | 615,063 | 615,063 | 615,063 |
| fabricator `Sent` units | 43 (`lead_plate` 23, `machine_frame` 10, `control_unit` 10) | 42 (`lead_plate` 18, `machine_frame` 11, `control_unit` 10, `mining_drill_kit` 3) | 34 (`lead_plate` 25, `control_unit` 9) | 30 (`lead_plate` 20, `control_unit` 10) | 57 (`machine_frame` 22, `lead_plate` 18, `control_unit` 13, `mining_drill_kit` 4) |
| smelter `Sent` units | 90 (`lead_ingot` 62, `iron_ingot` 28) | 80 (`lead_ingot` 53, `iron_ingot` 19, `glass` 8) | 87 (`lead_ingot` 68, `iron_ingot` 19) | 82 (`lead_ingot` 63, `iron_ingot` 19) | 80 (`lead_ingot` 53, `iron_ingot` 20, `glass` 7) |
| swept keys (`leftovers`) | | `machine.activity` ×28 | `machine.activity` ×9, `essence_liquifier.status` ×7, `biomass_mixer.status` ×2, `biomass_mixer.gate.*` ×20, `script.parked` ×2, `script.stray_dark` ×79 | the union, ×37 for `machine.activity` | none |
| `sweepLive` / `revived` | | [] / {} | [] / {} | [] / {} | |
| errored / crashed | 0 / none | 0 / none | 0 / none | 0 / none | 0 / none |

Findings:

1. **The sweep works and costs nothing.** Every stopped machine's status records, the orchestrator's per-mixer gate keys and the parking entries went at setup; the gate keys came back at the orchestrator's cadence and were swept again (never three passes in a row, so not marked live). No revival in any row (`revived` empty), no error, wall time within 0.2 % of the `sweep=false` row.
2. **The O2 gap is `scale`'s, not a left-over.** −14 % in every row with `scale`, with and without the sweep, and absent in the `biomass=off` row. Open item 6 of the phase 14 handoff stays: the per-record `minLevel` and `stalled` were clean (no stall warning), so the gap is elsewhere in the scaled record (candidates: the Mk II output path, the power draw of 8 records against 36 machines on a shed grid).
3. **The fabricator count is not a usable 1 h metric on this save.** Five configurations, 30 to 57 units, in both directions around real (43): the pair that differs only by the sweep gives 30 against 57, more than any group boundary. The `machine_frame` demand itself (40 units, the drones' `biosite_candidates()` requests) is in every run's log, so no demand was swept; what differs is which recipes the fabricator reached in the hour, and that follows the smelter's glass (the two rows with glass are the two with `mining_drill_kit`). Phase 13 saw the same drift in credits. A factory target needs a longer run or a direct measure (the orders book, `fabricator.orders`, against the recipe cascade's blueprint demand) rather than units sent in an hour.
4. **A new left-over interaction, fixed in the profile.** Sweeping `script.parked` made this repo's parking manager see the stopped mixers (parked by the mixer gate before the stop) as stray dark: 80 `[PARKING] ... switched off at its breaker` warnings in the hour, each resetting through the sweep so the switch-on never came. `script.parked` is now in the repo profile's `sweep.skipKeys` (a stopped script that keeps its parked entry reads as parked, the nearer truth; the revival guard covers the sunrise restart of parked solar scripts). The rows above ran before that change.
5. **Speed.** 18 % less wall time for 37 ghosts of 153 scripts, as in the field report.

Open (from this phase): rerun the `both` row with the profile's `script.parked` skip (expect no stray warnings; the fabricator column stays noisy); the O2 gap under `scale` (finding 2); a factory metric that survives an hour of timing drift (finding 3).

## Open rows

Phase 13: a refused stop under `off`, `park`, `produce`, `cash` or `mover` only warns (the script keeps running next to the stand-in); no row has hit one. Phase 14's revival guard counts a refused re-stop (`reviveRefused`); the first stop's refusal is still a warning only. Phase 5's `trim` paragraph describes the old `generated / n` rule; phase 7 replaces it. Phase 14's open rows are listed under its findings.
