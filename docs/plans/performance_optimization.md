# Performance Optimization (follow-up notes)

Working notes from the 2026-10-03 perf pass. They let a later session measure the deployed fixes and pick up the open leads without re-deriving them. The script cost model is in `docs/cheatsheet/dev_workflow.md` §1d-1. The tools are described in the same file, after the `step_profile.py` entry.

## Why

The game is CPU-bound. Host CPU sits at about 30–40% (likely two cores at full load), and raising game speed changes almost nothing. This changes how fixes should be judged:

- **Total interpreter steps** across all scripts are what cost real CPU. Cutting work in any script helps, including work duplicated across instances.
- **Atomic execution** (`lib/atomic.py`) does not cut CPU. It packs the same steps into fewer ticks and can make frames longer. Use it only where one script's latency matters, never as a CPU fix.
- **The running-script count N** sets the per-script allowance, `floor(50000 / N)` steps per tick. A block's cost in ticks therefore grows with N. Compare costs in steps, not ticks, whenever N differs between two measurements.

## Method

1. Find candidates with both tools, run on logs from after the last deploy (`--since <ISO UTC deploy time>`):
   - `python devtools/log_block_timing.py --since <T> --sort steps --top 30 --exclude "(?i)fly|leg|drive|extract|mining|recharg|unload|_load|care tour|stockpile run|construction|take_item"`
   - `python devtools/repeat_read_scan.py --since <T> --exclude "(?i)fly|leg|drive|extract|mining|recharg|unload|_load|care tour|stockpile run|construction|take_item|move |returning|delivering|build '" --blocks 12 --per-block 4 --top 15`
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

## Open items

1. **Measure the fixes.**
   - Run both tools with `--since 2026-10-03T05:16 --sort steps`, after the watcher has deployed and a few hours of logs exist.
   - Compare against the baseline above, in steps where possible. The baseline has no census, so convert its ticks with a census N from the same time of day if one is available.
   - Check that `scripts running:` lines appear in the automation log. If `run_control.is_running()` is not allowed inside an atomic callback, the census falls back to a direct loop and logs a `swallowed` line each time.
   - Check that `med_N` explains the rise in tick costs.
2. **Decision pending (user): fluid router switching between equally full tanks.** With every tank full, thermal_cap and water_pump switch tanks on each call.
   - Each switch prints a `Connected ...` info line (0.1 s of game time per console call) and resets `ticks_since_connect`, so the stall blacklist never kicks in.
   - The fix would be not to switch when no candidate is emptier than the current tank.
   - The stall rule must then ignore a stall caused by a full tank. Otherwise it blacklists full tanks with "no Gas Pipe route" warnings.
   - This changes behaviour, so it was not done.
3. **Drone haul plan, sharing across drones.** Share the source-side stock across the 5 drones through one archive key, such as `logistics.plan_reads` = `{tick, stock: {outpost_id: {item: units}}}`, reused for about 50 ticks with a live-read fallback. Keep destination deficits live, or a drone over-serves a destination that was just unloaded. Measure the effect of `590955b` first.
4. **Drone haul plan, skip when nothing changed.** Hash requests, pickups and drill status, and skip re-planning on an idle tick when the hash is unchanged.
5. **Pioneer `run_pull_loop`.** Build one `PlanReads` from `seen` and pass it to `_pull_deficits_tiered`, `fair_buffer_caps`, `urgent_items` (called twice) and `buyable_deficits`. That saves about 4 requests reads per cycle. Low priority: Pioneers are semi-retired.
6. **Not yet examined:**
   - **seed_maker crafting:** 34 ticks median, 27% of its time. Static hits are `_drain_output` → `drain_port_to_storage` per stack, and `_craft` → `_eject_chamber` / `_load_one` per blend item. The block includes waits.
   - **automation `script parking`:** 26 ticks every 50-tick pass, 17% of the automation script. Earlier work: `ae539d0` (awake stations built once, batched member reads).
   - **supply_dock `desired_order_id`** (77 ticks) and **automation `plan_dock_assignments`** (50 ticks). Earlier work: `fccfaba`, `e75d6f3`, `894eb6a`. Static hits are `pick_best_order` → `can_fulfill_order` per weekly order and `_dock_affinity` per candidate.
   - **smelter `get_smelter_demands`:** 8 ticks; `cache.network_stock` is called in two loops (production.py, around lines 1933 and 1964). Small.
   - **Static-only top hits** (no timed block):
     - `control_room_automation.supervise_grids_if_due` (`supervise_grid` per grid)
     - `mining_drill.publish_all_drills` (`controller.step()` per drill)
     - `production.get_material_demands` / `fab_site_gross_need` (`get_fabricator_active_recipe` per Fabricator; the shared site targets should already cut this)
     - `fleet_intent.haul_root` (`demand_root` per item)
7. **Atomic pass (later, separately).** Once the repeated work is cut, list the remaining pure-read blocks that need lower latency. Add a static test that guards atomic callbacks: no `log.*`, archive writes, `sleep` or state-changing calls inside code reached from `run_atomic`/`run_batched`/`run_chunked`. `repeat_read_scan.py` already marks functions reachable from these runners as `atomic`.
8. **Fewer running scripts** is the whole-base lever for steps per tick (§1d-1). With census data, look at which windows run at the highest N, and check whether more machine kinds can park.
