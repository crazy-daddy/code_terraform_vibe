# Planning-phase performance (2026-10-22)

Follow-up to [performance_optimization.md](performance_optimization.md) (the 2026-10-03 to 10-12 sweeps). This round measures the planning code paths that the dynamic Pioneer and drone roles added or grew, and ranks optimization vectors by measured cost. Nothing here is implemented yet.

## Method

- All numbers are headless (`devtools/perf/tick_profile.py`, real saves, current scripts). The live save's logs predate the current scripts, so `log_block_timing.py` on them was only used for cadence and for the autoplay planner, which the profiler cannot wrap yet (see "Tool gaps").
- Save A (Pioneer era): `internals/sample_saves/20261007_c5f9ebf/saves/0262_t349372.json.gz` (day 59, 4 outposts, 12 Pioneers, no drones).
- Save B (drone era): `internals/sample_saves/20261008_7e5e168/saves/0839_t1038072.json.gz` (day 174, drone stations incl. the first large one, 7 outposts).
- Ticks are inclusive game ticks per call with the profiler's wrappers on, which inflate by ~40 % (more with many modules wrapped). Read them as shares, and the unwrapped block timings as absolutes. Windows: 0.3 to 0.4 game hours.
- Raw outputs: session scratchpad `agentB/run{1,2,3,4b,5,6}.txt`, `blk{1,5}.txt` (not committed).
- Log level: from 2026-10-22 on, measurement runs use info (the `tick_profile.py` default since `d74a0e9`); older rows ran at debug. Building debug lines costs steps: the drone plan on 0839 measured 303 ticks at debug against 210 at info.

## Measured cost per planning phase

| Phase | Entry (gate) | Save | Cadence | Median ticks/call (wrapped) | Unwrapped block | Top items inside |
|---|---|---|---|---|---|---|
| Drone haul plan | `drone_haul_plan.plan_haul_job` | B | every idle drone pick (37 in 0.4 h) | 342 (171-409) | 222, max ~390 | `haul_destinations` 110, `outpost_sources` 99, `PlanReads.stock` 41/6, `PlanReads.scan` 26/12, `haul_candidate` 23/18, `_cap_fair_tiers` 17 |
| Fleet commission step | `FleetCommissionCoordinator.step` | B | every ~180 ticks (80 in 0.4 h; `FLEET_TICK_INTERVAL`=100, every loop while fast) | 124 (115-149) | `_advance_drone` block 70 | `_advance_chain` 72, `_kit_wait_text` 65, `SourceCache.network_stock` 59/2, `held_stock` 53/12, `SourceCache.scan` 34/6, `_backlog_parts` 31, `discover_storage_buildings` 13/12 |
| Role demand publish | `role_demand.publish` | A | every `ROLE_DEMAND_TICK_INTERVAL`=600 | 88 (68-124) | no block | `compute` 75, `outpost_tier_deficits` 36/4, `tier_deficits` 24/19, `survey_requests.read_scout_work` 24, `blocked_targets` 12, `mission_pool.publish` 11 |
| Pioneer pull plan | `PullJob.pick` | A | every pull trip (17 in 0.4 h) | 62 (5-112) | `pull_sources` block 6 | `outpost_tier_deficits` 32/4, `pull_destinations` 32, `tier_deficits` 26/22, `plan_pull_route` 19, `pull_sources` 12 |
| Demand refresh, network task | `Refresh.run_next` | A | one task per `DEMAND_SLICE_TICKS`=400 | 48 | `fabricator_target_ladders` 12 | `fabricator_target_ladders` 47, `_cascade_fabricator_output_demand` 28, `fabricator_root_targets` 18 |
| Demand refresh, site task | same | A | same | 32-33 per site | `get_site_fabricator_targets` 19 | `_compute_site_fabricator_targets` 28, `_site_seed` 16-21, `root_deficits` 8-13 |
| Demand refresh, site task | same | B | same | not profiled | `get_site_fabricator_targets` 80, max 183 | |
| Pioneer `next_job` | `PioneerController.next_job` | A | per idle pick (186 in 0.4 h) | 0 (max 1) | none | only slot refresh/claim archive calls |
| Pioneer refit | `PioneerRefitMixin` | B | rare (1 in 0.4 h) | | `Refit builder -> miner` 232 | unmeasured breakdown; `switch_candidates` never ran in the windows |
| Founding planner | `OutpostPlanner.run_pass` | live logs only | `PASS_SLEEP_S`=60 s / `WATCH_SLEEP_S`=300 s; full re-rank on signature change or `RERANK_TICKS`=36000 | not profiled (tool gap) | `Outpost proposals` 2, `Building proposals` 3, extractor passes 1-2 | fluid steam routing 350 median, max 2.2 h, is the heavy autoplay block |

Reading: the Pioneer role machinery itself is cheap (`next_job` 0 ticks, publish 88 ticks per 600). The drone haul plan and the fleet commission step are the new heavy hitters, and both recompute outpost-wide state per call. The demand refresh is smaller than in the 2026-10-12 profile on save A, but on save B its site tasks are 4x larger (80 vs 19 ticks per site) and the record never reaches FRESH (see finding 3).

## Findings

1. **`outpost_tier_deficits` / `outpost_tier_free` are the shared bottleneck.** They are recomputed from the requests archive for every outpost in: `role_demand.compute` (4 calls, 36 of 88 ticks), `drone_haul_plan.haul_destinations` + `outpost_sources` (209 of 342 ticks, per drone pick), `pull_plan.pull_destinations` (32 of 62 ticks, per Pioneer trip), and `_cap_fair_tiers`. Every drone and Pioneer recomputes the same network view a few ticks apart. `PlanReads` memoizes only inside one plan.
2. **Fleet commission runs at a high duty cycle.** 124 ticks per step every ~180 ticks on save B is most of one script's budget. Half is log text (`_kit_wait_text` 65 ticks per step, built whether or not the line is logged) and a `SourceCache` rebuilt per step with `scan` 6x and `discover_storage_buildings` 12x.
3. **The demand record is never FRESH on save B.** All 988 machine reads in 0.4 h were `from the stale demand record`; refresh rounds completed every 1,000 to 1,700 ticks against `DEMAND_FRESH_TICKS`=600 (`DEMAND_MAX_STALE_TICKS`=3000). With 7 outposts, one task per 400-tick slice puts a round above the fresh window. Machines then walk themselves when the record goes MISSING: smelter `get_smelter_demands` 196 ticks (7 walks in 0.4 h), fabricator-side `get_site_fabricator_targets` 136 ticks (31 blocks; path not confirmed).
4. **Drone haul plan sits near the step cap.** With wrappers on, `plan_haul_job` crashed `drone_7`/`drone_8` with `script exceeded step limit (10,000)` (run 4). The unwrapped plan is at 222 ticks median, 390 max, so one of its inner atomic chunks (`_dest_prep`, `distance_table`, `haul_candidate`, `_cap_one`) is within ~40 % of the cap on a 7-outpost save. `_orders` (`drone_haul_plan.py:542-550`) enumerates stop permutations per candidate.
5. **`fleet_intent.haul_root` rebuilds `demand_roots` and a fresh `SourceCache` per `set_intent`** (`fleet_intent.py:174-184`), called from every haul, pull, mine and biosite job. Not in the profiled gates; static repeat-read score 2.3e7.
6. **`role_demand.claim_slot` issues up to `MAX_ROLE_SLOTS`=16 archive transactions per claim** (`role_demand.py:438`). Cheap today (0 ticks measured) because most claims hit slot 0; scales with fleet size.
7. **Founding planner structure.** Already chunked (`run_chunked`/`run_batched`) and signature-gated, so no cap risk. Costs that scale with map and outposts: coarse grid rebuilt per bundle (`outpost_sites.py:965`), per-anchor linear scans over `centres`, `starts`, `remote` (≤40) and `future` spots (≤8) (`outpost_sites.py:815-825`), `demand_factors` recomputed per anchor (`:798`), `presets()` archive read per call (`autoplay_roles.py:164`). Contact and survey changes are not in the signature, so only `RERANK_TICKS` catches them. Not measurable until the profiler can wrap `autoplay/lib`.
8. **Side finding, save B at load:** `automation_3` crashes with `StepLimitError: in library 'wildlife_model', line 198` and `panel_7` with `'wildlife_common', line 53` (step limit 10,000) in every headless run of this save, before any wrapper is active. Pre-existing; not a profiler artifact.

## Optimization vectors, ranked by measured payoff

1. **Publish a tier-deficit / tier-free snapshot once, consume everywhere.** The orchestrator already owns a slice loop; add a `logistics` record (per outpost: tier deficits, tier free per item, reserved yields) refreshed every slice or on `REQUESTS_KEY` change, and make `haul_destinations`, `outpost_sources`, `pull_destinations` and `role_demand.compute` read it when fresh (same FRESH/STALE/MISSING contract as the demand record). Expected: drone plan 342 to ~130 ticks, pull plan 62 to ~30, role publish 88 to ~50, and the step-cap margin in finding 4 widens. Risk: staleness of live stock between snapshot and pick; keep `live=True` only for the drone's own destination after the snapshot pre-filters candidates.
2. **Fleet commission: build log text lazily, one `SourceCache` per step.** `_kit_wait_text` only when the line will be logged (or cache it per job until `short` changes); build the `SourceCache` once in `step` and pass it to `_advance_chain`, `_backlog_parts`, `_sync_craft_order`; memoize `discover_storage_buildings` per step. Expected: 124 to ~40 ticks per step, no behavior change.
3. **Demand refresh on larger saves: make a round fit the fresh window.** Options: `DEMAND_FRESH_TICKS` derived from outpost count x `DEMAND_SLICE_TICKS` (keeps "stale" meaningful), or shorter slices when the previous round overran, or two tasks per slice when the task is small. Plus: never let a machine do the full walk while a STALE record exists (it does today only when MISSING; check the fabricator path behind the 31 `get_site_fabricator_targets` blocks). Expected: removes the 136 to 196 tick machine-side walks on save B.
4. **Drone route search: bound `_orders`.** Cap stop count per candidate or replace the permutation with nearest-neighbour plus one 2-opt pass; keep `distance_table` per dest (not per first stop). Expected: `haul_candidate` 23x18 and `plan_route_for` 17x18 shrink, and the cap margin grows. Pairs with vector 1.
5. **`fleet_intent.haul_root`: cache `demand_roots` per tick.** Memoize `demand_roots` and the `SourceCache` in the job's `PlanReads` (or a module-level `(tick, roots)` pair). Measure first with `--gate fleet_intent:haul_root`.
6. **Founding planner (after the profiler covers it):** build the coarse grid once per rank and share across bundles; hoist `demand_factors` and the `weights` lookup out of `_finish`; bucket `centres`/`starts`/`remote` like `near()` already does for outposts and POIs; cache `presets()` per pass. Add contacts and survey state to the signature so re-ranks happen on change instead of every `RERANK_TICKS`.
7. **Role slots: claim by free-slot hint.** `claim_slot` tries slots 0..15 in order; keep a per-role "first free" hint in the claims map so a claim is one transaction. Low priority until fleets exceed ~8 per role.

Do not pursue: Pioneer `next_job` (0 ticks), the role refresh interval (88 ticks per 600 is already under 1 % of one script), and the founding proposal blocks (2 to 3 ticks each in the live logs).

## Tool gaps

- `tick_profile.py` cannot wrap or gate `autoplay/lib` modules (it copies scripts without autoplay). Needed for vector 6.
- `log_block_timing.py` reads only save `logs/<script>.log`; headless `console.log` needs a converter (prototype in the session scratchpad, `agentB/conv_log.py`).
- `role_demand.publish`, `PioneerController.next_job` and the `Refresh` task boundaries have no TreeConsole block, so they are invisible to `log_block_timing.py`.
- Wrapping many modules pushes atomic chunks over the step cap (finding 4); profile drone and autoplay paths with one or two modules at a time.
- No tool reports the real peak steps per atomic callback on a real save (later item). Smallest fix: an optional patch in `devtools/simulation/headless/simhost.mjs` `patchSimworker` at the step-limit check in `executeUserFunctionSync`, recording peak steps per callback per script with library and line, written by `run.mjs` into `summary.json`. Check whether it can also count the import chain (the import-cap TODO), and watch the no-snapshot fallback `fair_rival_bands`, the riskiest callback left. The game counts a callback's steps from the start of the tick, so steps the script already used that tick come out of the 10,000.

Implementation plan for these: see "Tool plan" below.

## Tool plan

### `tick_profile.py --preset founding --include-autoplay`

Root cause: `tick_profile.py:264-268` calls `save_scripts.py` without `--include-autoplay`, so `autoplay/lib/*.py` never lands in `<out>/scripts/lib` and `_read()` (`:173`) exits with "no lib module". Second blocker: `run.mjs:204` throws when `--include-autoplay` is combined with `--scripts`/`--libs` (which the profiler always passes, `:280-283`), so the planner Automation (`run.mjs:206-208`) never starts and the gate is never hit.

1. `main()`: add `--include-autoplay` (store_true) and `--preset {refresh,founding}`; pass `--include-autoplay` to the `save_scripts.py` subprocess (`:265`). `save_scripts.py:93-94` already merges `autoplay/lib` via `sync.merge_autoplay`, so `patch_libs`/`_read` resolve the copied modules unchanged.
2. Preset `founding`: modules `outpost_plan,outpost_sites,outpost_needs`, classes `outpost_plan:OutpostPlanner`, gate `outpost_plan:OutpostPlanner._replan` (`autoplay/lib/outpost_plan.py:686`; `_rank` at `:709` is the narrower alternative), label from `args[1]` (the tick), skip `log,_ceil,_rank,_fmt_price` and `_replan` itself (gated, not wrapped). Preset `refresh` keeps today's `DEFAULT_*`. The preset appends `--include-autoplay` to the `run.mjs` command.
3. `run.mjs:204`: relax the guard to throw only when neither the staged default nor `--libs` is given; with `--libs`, check `existsSync(join(a.libs, "outpost_plan.py"))` and throw a clear message otherwise. Update the header comment (`:67-68`).
4. Step cap: wrapping every top-level function of `outpost_sites` also wraps the atomic callbacks (`score_step` `:846`, `detail_slice`, `value_rows`, `future_rows`, filter slices) and the per-item helpers they call. `STEP_UNITS`=50 (~2,250 ops), `VALUE_CHUNK`=15, `FILTER_CHUNK`=4 survive 40 % overhead; `outpost_needs.SITE_CHUNK`=8 and any slice near 5,000 steps are at risk. Mitigations: the preset's skip list excludes per-item helpers (`score`, `check`); add `--chunk-scale F` to `patch_libs` that rewrites `^(\w*_CHUNK|STEP_UNITS) = (\d+)` lines in the copied modules only (the game interpreter has no environment, so no env route); document that wrapped slice callbacks inflate call counts.
5. Test: new `tests/test_tick_profile.py` (none exists): a temp lib dir with a fake `outpost_plan.py` holding `class OutpostPlanner` with `_replan`; assert `patch_libs` appends the gate tail and wrapper lines; assert preset resolution builds the expected argv with `subprocess.run` mocked. README `perf/` row: add the preset.

Risks: a stale `--libs` dir without autoplay libs (mitigated by the `existsSync` check); `_replan` wrapped twice if listed in `--classes` and gated (skip it in the wrapper).

### `log_block_timing.py --headless`

Current: `main()` (`:330-357`) builds `paths = log_files(<save>/logs)`; `calibrate()` and `collect()` open those paths (`:125-127`, `:192-194`). Headless format (`run.mjs:187`): `[tick N] [level] [scriptId] <text>`, continuation lines bare `HH:MM:SS ...`.

1. Add `headless_lines(console_log) -> {script: [lines]}`: port the prototype's loop (tagged/bare regexes, last tick/level/script carry-over, synthetic ISO from a fixed epoch plus tick/10 s) producing `[iso] [level] [script.py] [tick=N] clock body` strings grouped by script. Drop lines without a script id (`approve`, `lib-tier`) instead of attributing them to the last script.
2. Refactor `calibrate(paths)` and `collect(paths, ...)` to accept `{base: [sources]}` where a source is a path or an in-memory list; helper `_lines(source)` opens or iterates. Existing callers and `tests/test_log_block_timing.py` stay valid.
3. CLI: `--headless PATH` (run dir or `console.log`; a dir resolves `<dir>/run/console.log`, then `<dir>/console.log`), mutually exclusive with `--save`. Header prints the console path. `--since` is tick-derived in this mode; say so in `-h`.
4. Calibration unchanged (last debug clock per flush tick vs tick; TreeConsole stamps the game clock headless too). Add `--sec-per-tick F` override for runs with too few debug flushes; print the pair count or "override".
5. Census: headless census lines come from `script_census` via the automation script, same text, so the steps column works when the run included it.
6. Tests: `test_headless_console_lines` (tagged line, bare continuation, untagged junk; assert script/tick/level and that `collect()` pairs the block) and `test_headless_path_resolution`.

Risk: headless level names (`output`, `debug`, `crash`, `approve`) may differ from the game's; ISO ordering across scripts relies on tick only.

### Timing visibility for untimed planning calls

Wrap `role_demand.publish` (`role_demand.py:245`), `PioneerController.next_job` (`pioneer.py:164`) and the `Refresh` task kinds (`demand_publisher.py:136`) in `log.run(label, fn)` debug blocks (`tree_console.py:375`). A debug block costs nothing until a line is logged inside it (`tree_console.py:342-352` buffers headers), and `log_block_timing.py` then gets `[tick=N]` pairs. A `trace()` pair is a no-op unless the module level is "trace", so it is the wrong tool here.

## Rollout (agreed 2026-10-22)

One session per item, each in its own worktree (`python devtools/agent_worktree.py new <topic>`), merged only after operator approval. Reviews: `cavecrew-reviewer` per step, a final review by the session's model. Every session appends a row to "Results" below with the same save, gate and window as its baseline; a different window makes the comparison noise.

Wave 0, before anything else:
- **Side bug.** Save 0839 crashes `automation_3` (`wildlife_model` line 198) and `panel_7` (`wildlife_common` line 53) on the step cap at load. Find which scripts those slots hold on that save and whether the crash distorts the fleet commission baseline (run 5). Small session.

Wave 1, parallel (no shared files):
- **Tool 1** `tick_profile.py --preset founding --include-autoplay` plus the `run.mjs` guard (plan above). Touches `devtools/perf/tick_profile.py`, `devtools/simulation/headless/run.mjs`, new `tests/test_tick_profile.py`, README row.
- **Tool 2** `log_block_timing.py --headless` (plan above). Touches `devtools/perf/log_block_timing.py`, `tests/test_log_block_timing.py`, README row. Shared with Tool 1: README and `tests/` only.
- **Vector 2** fleet commission: lazy `_kit_wait_text`, one `SourceCache` per `step` passed to `_advance_chain`, `_backlog_parts`, `_sync_craft_order`, `discover_storage_buildings` memoized per step. One file. Baseline and remeasure: `tick_profile.py --save internals/sample_saves/20261008_7e5e168/saves/0839_t1038072.json.gz --hours 0.4 --gate fleet_commission:FleetCommissionCoordinator.step --modules fleet_commission,pioneer_commission,drone_commission,drone_upgrade,fleet_status,cash,production,storage,logistics_requests,priority --classes fleet_commission:FleetCommissionCoordinator,production_source:SourceCache`. Target: 124 to ~40 ticks per step. Outcome: 105; only the backlog spec hoist applied. The other three items rested on wrong premises: `_kit_wait_text` is the card's live status text, there is already one `SourceCache` per step, and the 12 `discover_storage_buildings` calls are 12 different keys under an existing 20-tick memo. The rest is `network_stock` over 6 outposts; re-check against the Vector 1 snapshot at the break.
- **Vector 5** fleet intent. Step 1 is a measurement, not code: `tick_profile.py --save internals/sample_saves/20261007_c5f9ebf/saves/0262_t349372.json.gz --hours 0.4 --gate fleet_intent:haul_root --modules fleet_intent,production_source,production`. Stop condition: under ~10 ticks per call, close the item with the number. Otherwise memoize `demand_roots` and the `SourceCache` per tick and remeasure.
- **Vector 1 plan** (read-only session): the tier-deficit snapshot design. Must settle: record shape (per outpost: tier deficits, tier free per item, reserved yields), FRESH/STALE/MISSING contract, which consumers keep `live=True` for their own destination, and whether a new automation is needed. Default is a new `Refresh` task kind in the orchestrator's slice loop; a separate `logistics_orchestrator` costs every script ~0.6 % allowance (§1d-1) and is justified only if the measured orchestrator round on save 0839 cannot deliver the snapshot within its fresh window. That measurement is part of the plan.

Wave 2, sequential:
- **Vector 1 implementation** (plan: [vector1_tier_snapshot_2026-10.md](done/vector1_tier_snapshot_2026-10.md)) after Vector 5 landed (both touch `PlanReads` in `logistics_requests.py`). Consumers: `drone_haul_plan.haul_destinations`, `outpost_sources`, `_cap_fair_tiers`, `pull_plan.pull_destinations`, `role_demand.compute`. Remeasure with run 2, run 4b and run 6 commands. Targets: drone plan 342 to ~130, pull plan 62 to ~30, role publish 88 to ~50. Outcome: pull and role publish met; drone plan missed (rows below; baselines rebuilt with narrower wraps, so absolutes differ from 342/62/88). `haul_destinations` fell 110 to 21; `outpost_sources` stays ~95; building debug lines is only ~19 of those ticks, and at info it still costs ~68. The rest is not investigated (likely `view.free`/`most_free`). Closed by measurement (2026-10-24, row below): the ~95 is the live path, taken only until the first snapshot publish (7 of 49 picks, `outpost_tier_free` ~120 of 137 ticks with live wraps). On the snapshot `outpost_sources` costs ~21 (`TierView.free` ~22 over 6 outposts in a deeper-wrapped run, `most_free` ~3); `read_snapshot` (`archive.get`) sits in the ~12 untimed ticks of `plan_haul_job`'s own body, so the record trim is not worth it. The publisher step (~105 on 0839) cancels the role saving inside the orchestrator. Fair-share splits now sum to the supply (before ~95 %). `LOGISTICS_FRESH_TICKS` raised 3000 to 5000: a 6-outpost round spans two `between_steps()` calls, ages reached ~3,900. Record ~16 KB, 88 % `free`; trim to `FAIR_BANDS` plus the top band only if the `archive.get` cost shows.

Break, re-evaluate with the Results table.

Wave 3:
- **Vector 3** demand refresh, after Vector 1 (the snapshot decision also decides where the refresh lives). Open question first: the 7 smelter full walks on save 0839 happened mid-run (ticks 1044585, 1044611) while refresh rounds completed every 1,000 to 1,700 ticks, so the record should never have been MISSING. Find the real trigger before touching `DEMAND_FRESH_TICKS` or `DEMAND_MAX_STALE_TICKS`. Outcome: two triggers.
  - (a) The demand record is stamped at round start; the gap from stamp to the next publish reached 3,032-3,389 ticks, beyond `DEMAND_MAX_STALE_TICKS`, which opened MISSING windows. Fixed by raising it 3000 to 5000 (`49079d2`): smelter full walks 4 to 0 (0839, 0.4 h).
  - (b) A site-plan change invalidates the record for every fabricator until the next publish: 22 walks per 0.4 h on 0839. Dropped: two fabricator outposts is the normal case, so a per-site check would save little.
  - `network_stock` can't use the tier snapshot: it needs raw `held_stock` at every outpost plus `aboard_units()`. The refresh stays in the orchestrator.
- **Vector 4** route search, after Vector 1's remeasure says the step-cap margin is still thin. Changes route quality, so it needs a headless A/B (pattern: `docs/headless/ab_results.md`), not only a tick count. Outcome: closed, not needed. The "thin margin" was never a step number, only finding 4's wrap-set crash. That crash still happens on `59a8df8` at debug and info, but only with `logistics_requests` and `priority` wrapped together, and it stops in the fair-tier path (likely `_cap_fair_tiers`), not route search. Unwrapped runs never crash. `_orders` sees at most `HAUL_MAX_STOPS_PER_TRIP` stops, larger cases run stepped, and `step_profile.py haul` peaks at ~2,224 steps (22 % of the cap), unchanged since before Vector 1. Caveat: the real-save peak steps per callback are unmeasured (see Tool gaps).
- **Vector 6** founding planner, after Tool 1: profile with the `founding` preset on save 0061 (sample saves `20261008_7e5e168`; 0839 has no founding bundle, `_rank` costs 0 ticks there), then hoist per the vector list. The full preset does not fit: the `outpost_plan` import chain uses 9,637 of the 10,000-step import cap unwrapped, and its 144 wrappers add ~1,300. Gate `outpost_plan:OutpostPlanner._rank` (nearly all of `_replan`'s cost) with a narrow `--modules` list. Outcome: done (`f50ef15`, review fixes `9af116d`); rankings identical, pinned by a test. The gain came from re-costing the slice units to the measured work and raising `STEP_UNITS` 50 to 64: ticks follow the number of atomic slices, not the work done in them. Open:
  - `_replan` costs 276 ticks on 0839 outside `_rank` (likely `snapshot`, `needs` or `plan_hosts`).
  - The coarse filter (~155 ticks) is the next lever. `FILTER_CHUNK` cannot grow: the dense-pipe worst case is 3355 ops.
  - The 9,637-step import-chain count has no committed method that measures it (relevant to the import-cap TODO). Closed 2026-10-24: `devtools/perf/import_steps.py` (Results, last row).
- **Drone plan debug lines** (Vector 1 follow-up): build the planner's debug lines and log blocks in `drone_haul_plan` only while debug logging is on, then remeasure with the Vector 1 drone command (row below). Outcome: done (`5ad1bba`); debug lines are built only when `log.debugging` is set. Gain ~14 ticks at info, none at the default debug level. Debug logging as a whole costs the drone plan ~93 ticks per call.

## Results

| Date | Item | Save | Gate | Window | Before | After | Commit |
|---|---|---|---|---|---|---|---|
| 2026-10-22 | baseline | 0262 / 0839 | see table above | 0.4 h | see table above | | |
| 2026-10-22 | Vector 2 fleet commission | 0839 | fleet_commission:FleetCommissionCoordinator.step | 0.4 h | 124 (115-149), n=80 | 105 (98-130), n=89 | 065c2a8 |
| 2026-10-22 | Vector 5 fleet intent (closed, no code) | 0262 | fleet_intent:haul_root | 0.4 h | 1 (1-2), n=46 | | |
| 2026-10-22 | Tool 1 founding baseline (`--modules ""`) | 0839 | outpost_plan:OutpostPlanner._replan | 0.4 h | 276 (268-293), n=7 | | 153af26 |
| 2026-10-22 | Vector 1 tier snapshot (`--modules drone_haul_plan --classes logistics_requests:PlanReads`) | 0839 | drone_haul_plan:plan_haul_job | 0.4 h | 352 (168-419), n=34 | 320 (81-459), n=39 | aa72616 |
| 2026-10-22 | Vector 1 tier snapshot (`--modules pull_plan,logistics_requests --classes ""`) | 0262 | job_pull:PullJob.pick | 0.4 h | 38 (5-86), n=17 | 6 (5-106), n=20 | d35a168 |
| 2026-10-22 | Vector 1 tier snapshot (`--modules role_demand,logistics_requests --classes ""`) | 0262 | role_demand:publish | 0.4 h | 46 (36-67), n=18 | 30 (25-43), n=19 | d35a168 |
| 2026-10-22 | Vector 1 tier snapshot (same) | 0839 | role_demand:publish | 0.4 h | 189 (115-195), n=13 | 55 (38-191), n=13 | d35a168 |
| 2026-10-22 | Drone plan debug lines (Vector 1 cmd; drone log level info) | 0839 | drone_haul_plan:plan_haul_job | 0.4 h | 210 (81-338), n=39 | 196 (72-319), n=40 | 5ad1bba |
| 2026-10-22 | Vector 3 smelter full walks, count (probe in smelter.demands) | 0839 | smelter.demands | 0.4 h | 4 walks | 0 walks | 49079d2 |
| 2026-10-22 | Vector 6 founding planner (`--modules "" --classes "" --skip "" --min-total 5 --include-autoplay`; log level info) | 0061 (7e5e168) | outpost_plan:OutpostPlanner._rank | 0.4 h | 741 (721-745), n=3 | 645 (576-693), n=3 | f50ef15 |
| 2026-10-22 | Vector 4 gate: run-4 wrap-set crash probe | 0839 | drone_haul_plan:plan_haul_job | 0.4 h | crash drone_7/8 (debug) | crash drone_7-9 (debug), drone_7-11 (info); needs logistics_requests+priority wrapped; step_profile haul peak ~2,224 steps, unchanged | 59a8df8 |
| 2026-10-24 | `outpost_sources` (closed, no code; Vector 1 drone cmd, info) | 0839 | drone_haul_plan:plan_haul_job | 0.4 h | 84 (80-317), n=49; `outpost_sources` 21 (18-74) on the snapshot, n=42; 95 (86-97) live before the first publish, n=7 | | |
| 2026-10-24 | Import-cap margin: wildlife tables imported at first use in `outpost_needs` (`import_steps.py --save`; steps at the end of an outermost import, cap 10,000; these loads finish in the first seconds of a run, so the window does not change them) | 0839 | import chain peak per slot | before 0.01 h, after 0.1 h | automation_4 `outpost_plan` 9,622 (96.2 %); panel_7 `building_plan` 8,422 (0.01 h) | automation_4 7,628 (76.3 %); panel_7 6,428; the wildlife modules now load in the planner's `power_plan` group (2,896) (0.1 h) | a6c204e5 |

The Vector 1 drone row's 320 (81-459) ran at debug, so it is not a "before" value for the info row.
