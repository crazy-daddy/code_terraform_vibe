# Performance Optimization (follow-up notes)

Working notes from the 2026-10-03 perf pass. They let a later session measure the deployed fixes and pick up the open leads without re-deriving them. The script cost model is in `docs/cheatsheet/dev_workflow.md` §1d-1. The tools are described in the same file, after the `step_profile.py` entry.

## Why

The game is CPU-bound. Host CPU sits at about 30–40% (likely two cores at full load), and raising game speed changes almost nothing. This changes how fixes should be judged:

- **Total interpreter steps** across all scripts are what cost real CPU. Cutting work in any script helps, including work duplicated across instances.
- **Atomic execution** (`lib/atomic.py`) does not cut CPU. It packs the same steps into fewer ticks and can make frames longer. Use it where one script's latency matters - eg if the script slowing down would make a machine idle - don't use it as a CPU fix.
- **The running-script count N** sets the per-script allowance, `min(floor(50000 / N) , 1000)` steps per tick. A block's cost in ticks therefore grows with N. Compare costs in steps, not ticks, whenever N differs between two measurements.
- **Reduce N** reducing the number of concurrently running scripts (=machines) thus becomes imperative for general script performance. `lib/script_parking.py` tries to park idle machines; however they need to be woken in a timely fassion once they have new work. Some decisions have to be (currently) made by the operator (later autoplay) and weighed (eg using turbines vs oil generators -> former need 1 machine for 100W latter 1 for 700W but the latter use oil - a more restricted resource compared to steam for the former). However you can make recommendations where you see fit; these will later drive the autoplay-decision-engine. 

## Method

1. Find candidates with both tools, run on logs from after the last deploy (`--since <ISO UTC deploy time>`):
   - `python devtools/log_block_timing.py --since <T> --sort steps --top 40 --exclude "(?i)fly|leg|drive|extract|mining|recharg|unload|_load|care tour|stockpile run|construction|take_item|move |returning|delivering|pull trip|haul job"`
   - `python devtools/repeat_read_scan.py --since <T> --exclude "(?i)fly|leg|drive|extract|mining|recharg|unload|_load|care tour|stockpile run|construction|take_item|move |returning|delivering|pull trip|haul job|build '" --blocks 12 --per-block 4 --top 15`
   - Each run takes about 30 s, mostly log parsing.
2. Before reworking a block, run `git log` on its code. Compare against the figures in earlier perf commit messages and do not redo old work.
3. Cut repeated work first: one snapshot per pass, memo per cache, shared results across instances. Consider atomic execution only after that, for read-only, non-logging code that needs lower latency.
4. Reading the log numbers:
   - Durations are wall game time and include sleeps and waits.
   - Debug lines carry the tick at which they were flushed, so only their clock time is exact.
   - The calibrated ratio is about 14.4 game seconds per tick.
   - Rank blocks within one window; different windows can have different N.
5. Edit shared lib files with `devtools/.sync-backups/hold` in place, because the watcher auto-deploys. Worktree subagents (`isolation: worktree`) also work well. They keep half-finished edits away from the watcher; cherry-pick their commits afterwards.

## Baseline (before the fixes)

Window 2026-10-02T22:37 to 2026-10-03T04:55 UTC, about 6.3 h. The running-script count was not logged yet, so these figures are in ticks only.

| Script kind | Block | Runs | Median ticks | Share of script time |
|---|---|---|---|---|
| fabricator (10) | `get_fabricator_active_recipe(fabricator_#)` | 3,416 | 78 | 11.3% |
| fabricator | `get_site_fabricator_targets(outpost_#)` (self ~32 ticks) | 3,241 | 76 | 10.9% |
| smelter (7) | `get_site_fabricator_targets(outpost_#)` | 1,225 | 80 | 6.1% |
| fabricator | `_cascade_fabricator_output_demand` → `ship_units` | 2,142 / 1,785 | 29 / 23 | 4.2% / 2.0% |
| fabricator | `choose_recipe` | 3,552 | 27 | 4.8% |
| drone (5) | `_plan_haul_job` | 2,237 | 82 | 5.5% |
| exotic_gas_cap (8) | `ensure_connection` | 21,230 | 2 | 6.0% |
| thermal_cap (5) | `ensure_connection` | 21,268 | 3 | 8.0% |
| water_pump (6) | `ensure_connection` | 21,131 | 3 | 4.3% |
| refiner (5) | `ensure_connection` | 8,998 | 5 | 6.9% |
| exotic_spring_tap (5) | `ensure_connection` | 12,454 | 2 | 4.5% |
| seed_maker (1) | `Crafting 'seed_crowncap' ...` | 1,988 | 34 | 27.3% |
| automation | `script parking` | 1,307 | 26 | 17.2% |
| supply_dock | `desired_order_id` | 143 | 77 | — |
| automation | `plan_dock_assignments` | 111 | 50 | 4.9% |
| pioneer (2) | `_pull_sources` | 1,954 | 7 | ~2% |

Notes on the baseline:

- Fabricator site-target work nearly stopped after about 01:40 UTC: `ship_units` ran 1,785 times in the first 3 h and 0 times after. Most likely the Fabricators were parked or idle. This was not checked.
- Logs from before 2026-10-02 22:37 UTC showed about 52 ticks for site targets and about 76 for `_plan_haul_job`. The rise to 77 and 82 ticks is probably a higher N, not a regression. The census below can confirm it.
- In the fluid scripts, about 49k of the ~84k `ensure_connection` blocks come from thermal_cap and water_pump switching between equally full tanks (see open item 2).

## Done (commits on main, deployable from 2026-10-03 05:16 UTC)

| Commit | Change |
|---|---|
| `9dc1143` | `lib/script_census.py`: the automation script logs `scripts running: N of M machines, allowance A steps/tick` every 300 ticks. `log_block_timing.py` adds `med_N` and `med_st` (median steps) columns and `--sort steps`. |
| `7e19507` | Fabricator: a `can_source_item`/`can_source_fluid` memo hit returns before any log block. The memo already existed; the debug block cost about 10× the lookup. `choose_recipe` reads the recipe claims once per pass (`foreign_claims()`) and skips recipes a peer holds fresh, with no archive transaction per candidate. |
| `3ac722c` | Site targets shared across the Fabricator, Smelter and panel scripts through archive key `production.site_targets` (see `docs/cheatsheet/production_logistics.md`, Shared site targets). Results are reused for 150 ticks. One script recomputes a stale result under a 300-tick lease while the others use the stale copy for up to 600 ticks. An entry is keyed on the site plan it was computed under. `get_site_ship_plan()` always recomputes. |
| `590955b` | Drone haul plan: `logistics_requests.PlanReads` reads requests, pickups and per-outpost stock once per plan. Before, outposts in both roles had their stock walked twice, and requests and pickups were read per outpost, drill and destination. Pioneer `_pull_sources` shares requests and reservations the same way. Planning now uses the same pickups snapshot that `claim_pickups` trims against, so a mid-plan reservation is no longer subtracted twice. |
| `5543ec2` | Fluid output router: the network walk is cached per script for `NETWORK_WALK_INTERVAL_TICKS = 600`, with an immediate new walk on a tank error or a `not_found` from connect. Each tank's fill is read once for the rebalance sort. A full current tank costs no archive read. Expired blacklist entries are pruned. |

## Measurement 2 (after the fixes)

Window 2026-10-03T05:16 to 13:40 UTC, about 8.4 h. The refactors from `8c2d0f5` to `8da0839` (handler unification) were deployed during this window, so a few blocks changed code mid-window.

Census:

- 383 `scripts running:` lines, no `swallowed` line from the census.
- Running scripts ranged from 66 to 109 of 206 machines. Hourly averages were 81–87, so the allowance was about 530–600 steps per tick.
- The `med_N` of most blocks is 94–96. Blocks run more often in the busy windows, so their median N is above the hourly average.
- Running scripts per machine kind are already in the archive (`machine.activity`, `lib/machine_activity.py`), and the latest control panel shows them on the MACHINE ACTIVITY card.
- **The census undercounts N.** `script_census.machine_refs()` lists `outpost.buildings()`, `outpost.harvesting_machines()` and `fleet.mobile_units()`. Extractors at points of interest are in none of these lists, and neither are the harvester or the panel and automation scripts. The save at tick 9,906,070 had 121 running scripts, while the census lines around that time said 83–94. True N was therefore about 25–30 higher than logged, and the allowance about 410 steps per tick, not 530. The `med_N` and `med_st` figures above are too high in N and too high in steps by the same factor.

Running scripts per machine kind, from the save at tick 9,906,070 (status `running`; 35 more were `paused` by script parking):

| Kind | Running / built | In `machine.activity` |
|---|---|---|
| drone_large | 17 / 17 | yes |
| habitat | 13 / 16 | yes |
| exotic_gas_cap | 9 / 9 | no |
| panel and automation scripts | 9 | no |
| drone_station_large | 7 / 7 | yes |
| water_pump | 6 / 6 | no |
| exotic_spring_tap | 6 / 6 | no |
| smelter | 6 / 7 | yes |
| thermal_cap | 5 / 5 | no |
| drone_service_station | 5 / 7 | yes |
| oil_generator | 5 / 5 | yes |
| oil_pump | 4 / 5 | no |
| pioneer, fabricator, feed_maker | 4 each | yes |
| temp_heater, oxygen_generator, pressure_generator | 3 each | yes |
| 9 other kinds | 1 each | harvester: no |

The 30 POI extractors (gas caps, spring taps, water pumps, thermal caps, oil pumps) are a quarter of N, and none of them can park. The 7 panel scripts are another 6%. The turbines in the log file list no longer exist in this save.

Results, compared with the baseline. The baseline has no N, so only ticks can be compared. At the same tick cost, a block at N≈95 costs fewer steps than at a lower N.

| Script kind | Block | Baseline runs / med ticks | Now runs / med ticks / med steps | Share now | Verdict |
|---|---|---|---|---|---|
| fabricator | `get_fabricator_active_recipe` | 3,416 / 78 | 569 / 2 / 1.1k | 1.1% | Fixed |
| fabricator | `get_site_fabricator_targets` | 3,241 / 76 | 245 / 142 / 80.4k | 1.4% | Runs 13× less often. One recompute is expensive (see below) |
| smelter | `get_site_fabricator_targets` | 1,225 / 80 | 97 / 150 / 79.5k | 0.8% | Same as the fabricator |
| fabricator | `_cascade_fabricator_output_demand` | 2,142 / 29 | 234 / 117 / 53.8k | 1.2% | Now runs only inside a recompute. It is about 2/3 of a recompute's cost |
| fabricator | `choose_recipe` | 3,552 / 27 | 1,212 / 7 / 3.7k | 0.4% | Fixed |
| drone | `_plan_haul_job` | 2,237 / 82 | 2,297 / 68 / 34.3k | 4.4% | About 17% fewer ticks, at an N that is probably higher. Still the top drone block |
| thermal_cap | `ensure_connection` | 21,268 / 3 | 25,737 / 3 / 1.4k | 8.0% | Unchanged. Open item 2 |
| water_pump | `ensure_connection` | 21,131 / 3 | 26,875 / 2 / 1.1k | 3.8% | Unchanged in count. Open item 2 |
| exotic_gas_cap | `ensure_connection` | 21,230 / 2 | 20,573 / 2 / 1.1k | 3.1% (was 6.0%) | Cheaper per call |
| exotic_spring_tap | `ensure_connection` | 12,454 / 2 | 12,890 / 2 / 1.2k | 2.7% (was 4.5%) | Cheaper per call |
| refiner | `ensure_connection` | 8,998 / 5 | not in the top 40 | — | Fixed |
| seed_maker | `Crafting 'seed_crowncap'` | 1,988 / 34 | 1,440 / 31 / 13.2k | 13.8% (was 27.3%) | Not worked on. Includes waits |
| automation | `script parking` | 1,307 / 26 | 1,015 / 31 / 18.4k | 18.6% | Not worked on. Largest automation block |
| supply_dock | `desired_order_id` | 143 / 77 | 361 / 10 / 5.3k | 0.9% | Much cheaper, probably through the sourceability memo in `7e19507` |
| automation | `plan_dock_assignments` | 111 / 50 | not in the top 40 | — | Cheaper |
| pioneer | `_pull_sources` | 1,954 / 7 | 1,956 / 7 / 3.8k | 1.4% | Unchanged |

New in the top 40, or larger than before:

| Script kind | Block | Runs / med ticks / med steps | Share | Static hit |
|---|---|---|---|---|
| automation | `[storage] Rebalancing Inventory` | 87 / 68 / 34.4k | 4.0% | not matched |
| automation | `plan_site` | 272 / 38 / 22.0k | 4.3% | `fab_site_gross_need` calls `get_fabricator_active_recipe` per Fabricator. `plan_site` calls `ship_units` per ingot |
| automation | `[WILDLIFE] plan` | 425 / 16 / 9.3k | 3.9% | not matched |
| drone_station_lrg | `stage_life_forms` | 3,441 / 3 / 1.8k | 0.9% | `buffer_target(item_id, outpost)` per life form, and each call walks the outpost's storage buildings |
| smelter | `get_smelter_demands` | 831 / 11 / 5.9k | 0.7% | `cache.network_stock` in two loops (`production_demand.py` lines 155 and 186). Was 8 ticks |
| drone_station_lrg | `Making stockpile room` | 197 / 30 / 16.1k | 0.3% | not matched |

Cost of one site-target recompute: the `supply(item_id, shortfall)` call per frontier item in `production_cascade.py:148` is the top static hit. `site_spare_elsewhere` calls `_site_base_targets` for every other outpost (`production_sites.py:481`), so each site's recompute rebuilds the base targets of all sites.

Follow-up checks on 2026-10-03:

- **`med_st` overstates blocks that wait.** It is median ticks × allowance. A block marked `[waits]` spends most of its ticks suspended in world calls (`take_item`, `transfer_to`), not running steps.
- **seed_maker crafting is mostly waiting.** One craft loads three blend items with `take_item` (about one game minute each), then calls `combine()`. The script uses few steps. One real defect: the finished seed is sent to the Warehouse the blend was just taken from. That Warehouse is still busy, so `drain_port_storage_first` falls back to Inventory ("Seed 'seed_crowncap' sent to Inventory"). The rebalance sweep then moves the seed to a Warehouse again.
- **Storage rebalancing:**
  - `warehouse.compact()` works on one Warehouse's own slots (decompiled `compact` calls `Wme(Fe)` on that building only). The docstring of `consolidate_cross_warehouse_stock` says it works across buildings; that is wrong.
  - `compact()` returns `already_compact` at once when nothing would move, so an idle call only costs the call. No `Compacted` line appeared in the window: it moved nothing in 8.4 h.
  - Most rebalance moves are small: newly made feed and seeds that producers put into Inventory although a Warehouse already holds the item. Fixing the producers' output routing cuts most of the sweep's work.
- **Park and wake churn.** Parks in the window: fabricator 2,735, smelter 1,784, crop_automator 865, supply_dock 839, drone_service_station 264, charging_station 220, refiner 206, oil_pump 199, thermal_cap 68. That is about 33 parks per Fabricator per hour. Each wake restarts the script, which repeats its discovery and startup reads.
- **Extractors and parking.** Oil pumps and thermal caps already park while dormant. Exotic caps park only when the dormant phase leaves at least `EXOTIC_PARK_MIN_TICKS` (600) of parked time, and none did in the window. Water pumps have no dormant phase. No extractor parks while its targets are full.
- **Wildlife.** The game marks the Wildlife pillar complete at a population of 5,000,000 (`wildlife_sensor.get_value()`; achievement `wildlife_teeming` in the decompiled code), and established populations never decay. After that, the planner has nothing left to reach. The 13 running Habitat scripts are then also candidates to stop, which would lower N by 13.

Tool notes:

- The harvester `Move X -> Y` and pioneer `Delivering`, `Returning` and `Pull trip` blocks are travel. The exclude patterns under Method now leave them out.
- `repeat_read_scan.py` matched the drone `_plan_haul_job` block to `field_keeper.act`. The block moved into a mixin in `b2ddddc`, and the scanner found the wrong function. Fix the matching before relying on that row.
- `log_block_timing.py` dropped 1,840 unclosed blocks. Most of them are probably blocks cut off at log rotation or by a script restart, but this was not checked.

## Sweep 3 plan

Decided on 2026-10-03:

- Fix the fluid router behaviour (open item 2).
- Find work in the logs and through a static sweep of every `lib/` module.
- Haiku agents scan and Sonnet agents fix. Each fix is made in a worktree, reviewed, and cherry-picked onto main.
- Reduce N: fix the census coverage, find more parkable kinds and write build advice. The per-kind numbers come from `machine.activity`, shown on the control panel's MACHINE ACTIVITY card.

Rules for every fix agent:

- Work in a worktree (`isolation: worktree`), so the sync watcher does not deploy half-finished edits.
- Edit the highest tier that defines the module (`scripts/<tier>/lib/x.py`).
- Run `git log` on the code first and do not redo earlier perf work.
- Run `pytest` and Pyright before committing. Write the commit message with the `caveman-commit` skill.
- Keep the AGENTS.md rules: no stdlib imports, `swallowed()` in every recovering `except Exception`, balanced `log.start()`/`log.end()`, and constant changes documented in `docs/cheatsheet/`.

### Phase A: log-driven fixes (Sonnet, one worktree each, parallel)

| # | Fix | Files |
|---|---|---|
| A1 | Fluid router: switch only to a strictly emptier tank, and do not count a stall caused by a full tank. Log the switch at debug, not info. Add tests with the shared fakes. | `fluid_routing.py` |
| A2 | Site-target recompute: compute each outpost's `_site_base_targets` once per recompute and pass it to `site_spare_elsewhere`. Reduce the `supply()` calls per frontier item in the cascade. | `production_sites.py`, `production_cascade.py` |
| A3 | `script parking`: measure each grid once per pass in `_low_reserve_grids`, or reuse the grid supervisor's last measurement from the archive. | `script_parking.py`, `control_room_automation.py` |
| A4 | Small hoists: `stage_life_forms` walks storage once per call, `get_smelter_demands` reads `network_stock` once per item, and `get_material_demands` reads the active recipes once. | `drone_depot.py`, `production_demand.py` |
| A5 | Output routing: a drain does not pick a Warehouse that is busy from this script's own `take_item`, and it retries before it falls back to Inventory. Check the feed_maker and other producers whose output the rebalance sweep moves. | `storage.py`, `seed_supply.py`, `feed_maker.py` |
| A6 | Census coverage: add the POI extractors, the harvester, and the panel and automation scripts to the census count, so N is right. The harvester, panels and automation always run; count them, but do not park them. | `script_census.py`, `machine_activity.py` |
| A7 | Storage sweep, semi-retired: rebalance only at the home outpost (Inventory to Warehouses and back), and call `compact()` about once per game day. Fix the `consolidate_cross_warehouse_stock` docstring. | `storage.py`, `control_room_automation.py` |
| A8 | Park churn: find why Fabricators and Smelters park and wake about 33 times per hour, and add hysteresis to the wake (or the park) decision. | `script_parking.py`, `fabricator.py`, `smelter.py` |
| A9 | Wildlife planner: stop planning once `wildlife_sensor.get_value()` reaches 5,000,000. The decompiled game marks the Wildlife pillar complete there, and established populations never decay. | `wildlife_planner.py` |

A2 and A4 both touch the `production_*` modules. Run A2 first, or merge the two agents.

### Phase A results (commits on main, 2026-10-03, not yet deployed)

| Commit | Item | Change |
|---|---|---|
| `e4eec23` | A2, A4 | `site_spare_elsewhere` memoizes each other outpost's share per item on the `SourceCache` (`_spare_contribution`), so the sites of one recompute share it. `network_stock` is memoized per item, which also covers both loops of `get_smelter_demands`. `get_material_demands` is unchanged: it has no per-pass memo of the active recipe, and adding one could change behaviour. The rest of a recompute (cascade, `local_make_seconds`) is unchanged, so expect a few thousand to about 10k steps saved per recompute, not most of the 80k. |
| `d6eeb92` | A4 | `stage_life_forms` and `flush_surplus` read the storage layout once (`storage_layout()`) and read it again only after a send. |
| `41eb1fc` | A9 | The Wildlife planner stops at `WILDLIFE_COMPLETE_POPULATION` (5,000,000): it withdraws the Feed Maker life-form requests, writes an empty `wildlife.plan` with `complete: True`, and shows "Wildlife complete" on the AUTOMATION card. Habitats keep their colonies and park once out of feed; Feed Makers park idle. |
| `322e291` | A6 | The census also counts the POI extractors (power grid members of `POI_TYPE_IDS`), the harvester (`HARVESTER_ID`, a fixed id, because no API lists it) and the panel and automation scripts (probed by id, counted toward N only). Sensor and planet scripts are still not counted, so N is a lower bound. |
| `060d84f` | A5 | `drain_port_to_storage` tries the next-best Warehouse, up to `BUSY_TARGET_RETRIES` (3) times, when the picked one answers `busy`. Feed Maker output takes the same path. |
| `060d84f` | A7 | `compact()` runs every `COMPACT_TICK_INTERVAL` (6000 ticks, one game day). Rebalance and reclaim already ran at home only. |
| `87f125e` | A3, A8 | Every Fabricator and Smelter wake was a timed `re-check due` (462 of 462), so a machine that parks again within `FRUITLESS_REPARK_TICKS` (150) of such a wake gets its next re-check doubled, up to `WAKE_BACKOFF_MAX_TICKS` (Fabricator and Smelter 1200, crop_automator and supply_dock 1800). The worst-case delay before an idle Fabricator sees new work grows from 300 to 1200 ticks. The low-reserve verdict per grid is cached for `RESERVE_CACHE_TICKS` (150), and tank ids come from the member rows already read. |
| `f582cb9` | A1 | The output router leaves a full tank only for one emptier by more than `OUTPUT_REBALANCE_MARGIN` (0.02). Otherwise it returns `full` and stays connected. A stall on a full tank does not blacklist it. A routine rebalance logs at debug in `ensure_output_logged`. |
| `fb50c80` | A8 | The parking pass wakes parked Fabricators and Smelters when their demand rises. It compares a signature built from archive reads only: manual, upgrade and backlog orders, Fabricator stock targets and the site plan wake Fabricators; ingot stock targets wake Smelters; a new order id in the dock plan wakes both. A demand wake resets the re-check backoff, so the 1200-tick cap only applies while demand is unchanged. It wakes the whole kind, not only the machines that can make the item. |
| `9066282` | A6 | The panel and automation probe reaches 40 ids past the highest one found. |

Open points from Phase A:

- `HARVESTER_ID = "harvester_1"` is a fixed id. Replace it if an API or an archive entry ever lists the harvester.
- Check in the logs how often `demand changed:` wakes fire. Upgrade and backlog orders are republished by their requesters, so an amount that rises and falls would wake Fabricators each time.
- Measure the effect: run the tools with `--since` set to the deploy time of these commits.

### Phase B: static sweep (Haiku, read-only, parallel)

- Split the 131 `lib/` modules into about 10 batches by concern: fluids, power, production, logistics, drones, vehicles, pioneers, bio and planting, wildlife, and the rest.
- Each agent gets the `repeat_read_scan.py` output for its modules and the Method rules above.
- Each agent reports at most 5 candidates. A candidate states the file and line, the repeated read, the loop it sits in, an estimated cost per pass, and a proposed fix. Agents do not edit files.
- I rank the candidates by calls per hour × cost per call, and drop the ones that are already fixed or that sit in travel blocks.
- The top candidates go to Sonnet fix agents, the same way as Phase A.

### Phase C: fewer running scripts

The harvester, the panels and the automation scripts always run and cannot be parked. Habitats and drones are busy. The work here is the POI extractors:

1. Park an extractor while every tank it feeds is full and its buffer holds, and wake it when a target tank drops below a fill threshold. This applies to water pumps, exotic gas caps and spring taps. The parking pass reads the tank fills it needs.
2. Habitats after the Wildlife pillar is complete: retiring them (releasing the colonies into the wild) is planned separately, outside this perf plan.
3. Write the build advice into a new section of this file: the scripts per unit of output for each machine kind (for example oil generators against turbines, or fewer but larger extractors), and the scripts each consolidation would remove. The advice feeds the autoplay decision engine later.

### Phase D: measure

- After all fixes are deployed, run the tools again with the deploy time as `--since`.
- Add a Measurement 3 section, and record the next `--since` time.
- Then start the atomic pass (open item 7).

Tool fixes go into Phase A as needed: the `repeat_read_scan.py` block matching for mixin methods, and a check of the 1,840 dropped unclosed blocks.

## Open items

1. **Next measurement.** Run both tools with `--since` set to the deploy time of the Phase A commits (`e4eec23` to `f582cb9`). Until they are deployed, `--since 2026-10-03T13:40` measures the handler-unification refactors only.
2. **Fluid router switching between equally full tanks.** Decided: fix it (Phase A1). With every tank full, thermal_cap and water_pump switch tanks on each call.
   - Each switch prints a `Connected ...` info line (0.1 s of game time per console call) and resets `ticks_since_connect`, so the stall blacklist never kicks in.
   - The fix would be not to switch when no candidate is emptier than the current tank.
   - The stall rule must then ignore a stall caused by a full tank. Otherwise it blacklists full tanks with "no Gas Pipe route" warnings.
   - This changes behaviour, so it was not done.
3. **Drone haul plan, sharing across drones.** Share the source-side stock across the 5 drones through one archive key, such as `logistics.plan_reads` = `{tick, stock: {outpost_id: {item: units}}}`, reused for about 50 ticks with a live-read fallback. Keep destination deficits live, or a drone over-serves a destination that was just unloaded. Measure the effect of `590955b` first.
4. **Drone haul plan, skip when nothing changed.** Hash requests, pickups and drill status, and skip re-planning on an idle tick when the hash is unchanged.
5. **Pioneer `run_pull_loop`.** Build one `PlanReads` from `seen` and pass it to `_pull_deficits_tiered`, `fair_buffer_caps`, `urgent_items` (called twice) and `buyable_deficits`. That saves about 4 requests reads per cycle. Low priority: Pioneers are semi-retired.
6. **Not yet examined** (figures from Measurement 2):
   - **automation `script parking`:** 31 ticks (18.4k steps) per 50-tick pass, 18.6% of the automation script. Static hit: `_low_reserve_grids` calls `grid_power.measure_grid` per grid. Earlier work: `ae539d0` (awake stations built once, batched member reads).
   - **seed_maker crafting:** 31 ticks, 13.8% of its time. Static hits are `_craft` → `_eject_chamber` / `_load_one` per blend item, and `best_unload_target` per stack. The block includes waits.
   - **Site-target recompute:** 80k steps per run. See the recompute note under Measurement 2.
   - **automation `plan_site`, `[storage] Rebalancing Inventory` and `[WILDLIFE] plan`:** together about 12% of the automation script.
   - **drone_station_lrg `stage_life_forms`:** hoist `buffer_target`'s storage walk out of the per-form loop.
   - **smelter `get_smelter_demands`:** 11 ticks; `cache.network_stock` is called in two loops (`production_demand.py` lines 155 and 186). Small.
   - **Static-only top hits** (no timed block):
     - `control_room_automation.supervise_grids_if_due` (`supervise_grid` per grid)
     - `mining_drill.publish_all_drills` (`controller.step()` per drill)
     - `production_demand.get_material_demands` (`get_fabricator_active_recipe` per Fabricator)
     - `fleet_intent.haul_root` (`demand_root` per item)
7. **Atomic pass (later, separately).** Once the repeated work is cut, list the remaining pure-read blocks that need lower latency. Add a static test that guards atomic callbacks: no `log.*`, archive writes, `sleep` or state-changing calls inside code reached from `run_atomic`/`run_batched`/`run_chunked`. `repeat_read_scan.py` already marks functions reachable from these runners as `atomic`.
8. **Fewer running scripts** is the whole-base lever for steps per tick (§1d-1). The save had 121 running scripts at the end of Measurement 2. See Phase C.
