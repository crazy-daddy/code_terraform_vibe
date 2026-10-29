# Founding planner rev3 phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the second outpost spread outward and look ahead to the steam outpost: two new site score terms (`reach_gain`, `future`), a `power` need that forms on a discovered vent, the drone takeover switch with Charging Station retirement, then replay both recorded runs and tune the weights.

**Architecture:** Both terms live in `autoplay/lib/outpost_sites.py`. Their inputs are precomputed once per ranking (`prepare()` / `prepare_want()`), so the per-anchor cost in `_finish()` stays a short loop over a few points. `outpost_needs` names the future fluids and `outpost_plan._rank()` passes them in with the phase 1 geothermal scout areas.

**Tech Stack:** Python (game interpreter subset), `unittest`, Ruff, Pyright; replay via `devtools/simulation/planner_replay.py`.

**Spec:** [founding_rev3_phase2_handoff.md](founding_rev3_phase2_handoff.md) and [outpost_founding_planner.md](../outpost_founding_planner.md) "Revision 3" (decisions B, C).

## Global Constraints

- Work only in `.claude/worktrees/founding-rev3-p2` (branch `agent/founding-rev3-p2`); read `internals/` from the main checkout.
- All inputs from in-game data (§11i "Knowledge levels"); biome map and `contact_inference.BIOME_KINDS` are allowed. No bearing heuristic.
- `reach_gain` and `future` stay out of `RESOURCE_TERMS`; `confidence` must not change.
- New terms in both `WEIGHTS` and `WEIGHTS_EARLY`, start value `3.0` each; tune `WEIGHTS_EARLY` first. The second outpost is ranked long before the first mining drill and before the drill that unlocks hardness 3 (operator, 2026-10-21), so the early weights and the hardness penalty both apply in the replay.
- New constants: `FUTURE_RANGE_M = 500.0`; the half value of a geothermal-cell fallback `FUTURE_CELL_VALUE = 0.5`.
- Every per-anchor cost goes through `score_step()` unit accounting; `BudgetTests` must stay under `ATOMIC_STEP_BUDGET` (`construction_plan.py`).
- A changed constant updates its cheatsheet row in `docs/cheatsheet/autoplay_outposts.md` in the same task.
- Checks per task: `python -m unittest discover -s tests` (the discover form; single modules importing `autoplay_roles` before `harness` fail standalone), `.venv/Scripts/python.exe -m ruff check autoplay tests`, `.venv/Scripts/python.exe -m ruff format autoplay tests`, `npx pyright`.
- Commits: Conventional Commits, no AI attribution; multi-line messages via a scratchpad file and `git commit -F`.

## Review Focus

1. No reach points (`ctx["starts"]` empty) or no contacts out of reach: `reach_gain` = 0, no division by zero. Test in Task 1.
2. Stuck contacts (`row["stuck"]`) count for neither term: a scout cannot resolve them, so they must not draw outposts. Test in Task 1 and Task 2.
3. Drones haul (`snap["drones"]`): the candidate gets no Charging Station, so `reach_gain` must be 0 then, early and late weights alike. Test in Task 1.
4. `future` with an empty fluid list, or with only fluids that have no contact and no geothermal cell, gives 0, not an error. Test in Task 2.
5. Ranking cache: a change of the future fluids must re-rank (signature), or a newly formed `power` need never moves the second outpost. Test in Task 2.

---

### Task 1: `reach_gain` score term

**Files:**
- Modify: `autoplay/lib/outpost_sites.py` (`WEIGHTS` :129, `prepare()` :377, `_finish()` :654, `score_step()` :703 unit accounting, module header comment on terms)
- Test: `tests/test_autoplay_outpost_sites.py`
- Docs: `docs/cheatsheet/autoplay_outposts.md` §11i table (L129-142) and constants

**Interfaces:**
- Produces: `ctx["remote"]`: list of `(x, y, n)` clusters, the non-stuck contacts (`ctx["rows"]`) farther than `CONSTRUCTOR_REACH_M` from every `ctx["starts"]` point, grouped per `CELL_M` cell (`x, y` = mean position, `n` = count); `ctx["remote_n"]` = total count. `row["terms"]["reach_gain"]` in every scored row.

- [x] **Step 1: Write the failing tests** (class `ReachGainTests`, use the `world()` / `prepare()` helpers)
  - `test_reach_gain_rewards_new_ground`: home at (0, 0) with `home=True`; 4 POIs at (1500, 0) region; candidate A at (1000, 0), candidate B at (-300, 0). `score(ctx, A...)["terms"]["reach_gain"] == WEIGHTS["reach_gain"] * 1.0`; B's term `== 0.0`.
  - `test_reach_gain_share_of_remote`: 2 remote POIs east, 2 remote POIs west, candidate east reaches only the east pair: term `== WEIGHTS["reach_gain"] * 0.5`.
  - `test_reach_gain_zero_without_starts_or_remote`: no outposts: 0; all POIs within 600 m of home: 0.
  - `test_reach_gain_ignores_stuck`: the only remote contact is blocked (stuck): term 0 and `ctx["remote_n"] == 0`.
  - `test_reach_gain_out_of_confidence`: two ctx differing only in remote POIs give equal `confidence`.
  - `test_reach_gain_off_when_drones_haul`: `phase_inputs(outposts, early, drones=True)` gives `weights["reach_gain"] == 0.0` for `early` True and False; `drones=False` keeps 3.0.
  - Extend `BudgetTests.test_score_step_fits` (or add `test_score_step_fits_with_remote`): dense ctx plus 200 POIs beyond 600 m of home spread over the map; worst slice `< ATOMIC_STEP_BUDGET`.
- [x] **Step 2: Run, expect FAIL** (`KeyError: 'reach_gain'`).
- [x] **Step 3: Implement.** In `prepare()`: build `remote`/`remote_n` from `rows` and `starts` (no starts: empty). Weights `"reach_gain": 3.0` in `WEIGHTS` (so `WEIGHTS_EARLY` inherits). In `_finish()`: `terms["reach_gain"] = weights.get("reach_gain", 0.0) * (sum of n over clusters within CONSTRUCTOR_REACH_M of (cx, cy)) / remote_n`, 0 when `remote_n == 0`. In `score_step()`: charge one new `REACH_UNITS` (start at 1) per cluster on top of `FINISH_UNITS`, so many clusters split slices. `phase_inputs(outposts, early, drones=False)` (:948) sets `reach_gain` to 0 in the returned weights when `drones`; `outpost_plan._rank()` passes `snap.get("drones")`.
- [x] **Step 4: Run tests, Ruff, Pyright: PASS.**
- [x] **Step 5: Docs.** §11i table row `reach_gain | 3 | share of out-of-reach contacts (any kind, not stuck) the candidate's Charging Station would bring within CONSTRUCTOR_REACH_M`; note it is outside `RESOURCE_TERMS`.
- [x] **Step 6: Commit** `feat(outposts): reach_gain site term`.

### Task 2: `future` score term

**Files:**
- Modify: `autoplay/lib/outpost_sites.py` (`read_world()` :897, `prepare()`, `wants()` :361, `prepare_want()` :551, `_finish()`, `score_step()`)
- Modify: `autoplay/lib/outpost_needs.py` (new `future_fluids()`; `plan_hosts()` :462 adds `plan["future"]`)
- Modify: `autoplay/lib/outpost_plan.py` (`_rank()` :705: signature, `read_world()` call, `wants()` call)
- Test: `tests/test_autoplay_outpost_sites.py`, `tests/test_autoplay_outpost_needs.py`, `tests/test_autoplay_outpost_plan.py`
- Docs: §11i table row + constants, §11h (`future_fluids`)

**Interfaces:**
- Consumes: Task 1's unit-accounting pattern in `score_step()`.
- Produces:
  - `outpost_needs.future_fluids(snap, needs) -> list[str]`, sorted: `"steam"` when no outpost hosts `power` and no need of role `power` has an urgency in `PROPOSE_URGENCIES`; `"water"` when `game_phase.nuclear_ahead(phase)`, no `reactor` host and no proposed `reactor` need. `[]` before `OUTPOSTS_RESEARCH`.
  - `plan_hosts()` result gains `"future": future_fluids(snap, open_needs)`.
  - `read_world(..., geothermal=())`: new keyword, stored as `world["geothermal"]` (list of `(x, y)`).
  - `wants(bundle, role_presets, future=())` adds `"future": list(future)`.
  - `prepare_want()` adds `want["future_spots"]`: `{fluid: [(x, y, value), ...]}`, at most `FUTURE_TOP = 8` best spots per fluid.
  - `row["terms"]["future"]` in every scored row.

Spot values (`prepare_want`, through `run_batched` over `ctx["rows"]` with `VALUE_CHUNK`, non-stuck rows only):
- known fluid (`row["fluid"] == fluid`, any level, KIND_FLUID covers discovered vents): `1.0`;
- unknown contact (`level == 1`): its `kinds` weight of the fluid's kind if set; else `prior["kind"][kind]` renormalised over the kinds that can spawn in the contact's biome (`biome(ctx, x, y)`; kinds absent from every `BIOME_KINDS` value spawn everywhere), `0` when the biome rules the kind out;
- no spot with value > 0 for `steam`: each `world["geothermal"]` point at `FUTURE_CELL_VALUE`.

Term: `weights["future"] * mean over want["future"] of max over spots of value * (1 - d / FUTURE_RANGE_M)` (d from the candidate centre, clamped at 0); 0 when `want["future"]` is empty.

- [x] **Step 1: Write the failing tests**
  - needs: `test_future_fluids_steam_until_power_host` (no host: `["steam"]`; outpost with `roles=["power"]`: `[]`); `test_future_fluids_skip_proposed_power` (a `power` need at `"soon"` in `needs`: no `"steam"`); `test_future_fluids_water_when_nuclear_ahead`; `test_plan_hosts_carries_future`.
  - sites (`FutureTests`): `test_future_pulls_to_discovered_vent` (level-2 thermal site at (500, 0), candidate at (250, 0): term `== 3.0 * 0.5` within 0.01; candidate 600 m away: 0); `test_future_unknown_poi_needs_geothermal_biome` (unknown POI in a geothermal biome scores > 0, same POI in frozen scores 0); `test_future_falls_back_to_geothermal_cell` (no contacts, `geothermal=[(400, 0)]`, candidate at (0, 0): `3.0 * 0.5 * (1 - 400/500)`); `test_future_empty_is_zero`; `test_future_ignores_stuck`; `test_future_out_of_confidence`; budget test with 8 spots × 2 fluids under `ATOMIC_STEP_BUDGET`.
  - plan: `test_rank_reranks_on_future_change` (same bundles, `plan["future"]` changes from `[]` to `["steam"]`: `_rank()` rebuilds `self.ranked`).
- [x] **Step 2: Run, expect FAIL.**
- [x] **Step 3: Implement** the interfaces above; weights `"future": 3.0`; `_rank()` adds `plan.get("future")` to the signature, passes `geothermal=self.geo_areas or []` (the phase 1 scout areas: ≤ `GEOTHERMAL_SCOUTS` points, cheap, nearest home) and `future=plan.get("future", [])` to `wants()`. `score_step()` charges `REACH_UNITS` per spot.
- [x] **Step 4: Run tests, Ruff, Pyright (run `devtools/scripts_sync.py resolve-preview` first only if a `scripts/*/lib` file changed): PASS.**
- [x] **Step 5: Docs.** §11i row `future | 3 | closeness (1 − d/FUTURE_RANGE_M) to the best contact of each look-ahead fluid: known fluid 1, unknown by biome prior, else a geothermal scout area at 0.5`; constants `FUTURE_RANGE_M`, `FUTURE_TOP`, `FUTURE_CELL_VALUE`; §11h one line on `future_fluids()`. Note the deviation from the handoff: the fallback uses the scout areas, not all probe cells.
- [x] **Step 6: Commit** `feat(outposts): future site term for look-ahead fluids`.

### Task 3: `power` need on a discovered vent

**Files:**
- Modify: `autoplay/lib/outpost_needs.py` (`snapshot()` :763, `lookahead()` power block :288-291)
- Modify: `autoplay/lib/outpost_plan.py` (survey flag where proposals are made, :438 area, and `recheck()`)
- Test: `tests/test_autoplay_outpost_needs.py`, `tests/test_autoplay_outpost_plan.py`
- Docs: §11h power line

**Interfaces:**
- Produces: `snap["thermal_sites"]`: `[{"id", "x", "y"}]` of `journal.discovered_sites("nocturna")` rows of kind `thermal` not in `snap["fluid_sites"]` (by id). The `power` need from a discovered-only vent carries `survey_first=True`. A found proposal whose bundle has a need with `survey_first` gets `survey = True` regardless of confidence.

- [x] **Step 1: Write the failing tests**: `test_power_on_discovered_vent` (no fluid sites, one `thermal_sites` row, no outpost within `NEAR_TILES` of its `extractor_box`: `power` need with `site_fluid == "steam"`, `survey_first` True, urgency from Thermal Cap ETA); `test_power_discovered_vent_hosted` (outpost next to it: no need); `test_surveyed_vent_no_survey_first` (existing test path keeps `survey_first` absent); plan: `test_survey_first_forces_survey`.
- [x] **Step 2: Run, expect FAIL.**
- [x] **Step 3: Implement.** `snapshot()` reads discovered sites once (follow `fluid_outlook.discovered_fluid_rows()` :277 for the join, surveyed wins). In `lookahead()`, a vent counts when it is surveyed (as now) or in `thermal_sites`; the hosted check uses `gap(outpost_box, [extractor_box(x, y)])` for discovered vents. `_site_ok()` / `near_fluid()` keep requiring surveyed sites.
- [x] **Step 4: Run tests, Ruff, Pyright: PASS.**
- [x] **Step 5: Docs** §11h; **Commit** `feat(outposts): power need on a discovered vent`.

### Task 3.5: One fixed constructor base after refits

Operator, 2026-10-21: since the "Pioneers refit into new roles" rework, a builder's base may follow the Pioneer it was refit from. That breaks the construction-material STOCK at the constructors' home base and Task 4's station keepers. Unknown cause and extent: use `superpowers:systematic-debugging` before any edit.

Lead: `pioneer_refit.refit(role, spec=None, base=None)` (`scripts/4_controlpanel/lib/pioneer_refit.py:160`) moves the base to `base`, `None` = the unit's own launch `HOME_BASE`; `queue_pioneer()` sets `HOME_BASE` from the commission row's outpost, and miner rows carry one (`building_plan.py:43`). So a miner commissioned at outpost X and refit to builder is likely based at X.

**Files:** found in Step 1. Likely `scripts/4_controlpanel/lib/pioneer_refit.py`, `scripts/4_controlpanel/lib/pioneer.py` (:144-210, base restore), `autoplay/lib/build_providers.py` / `building_plan.py` (refit callers, `pioneer_surplus_wants()`), and the construction-stock code. Test: the matching `tests/test_*pioneer*` / `tests/test_autoplay_building_plan.py`.

**Interfaces:**
- Produces: `constructor_base()` (in the lib that owns the construction stock): the one outpost id where builders live and construction materials are stocked (today home, `HOME_OUTPOST_ID`, unless Step 1 finds a configured one). Every refit or commission to role `builder` passes `base=constructor_base()`. Task 4's keepers read builder bases from `fleet.status` and so get this one outpost.

- [x] **Step 1: Investigate** (`caveman:cavecrew-investigator`, read-only): (a) where the construction-material STOCK picks its outpost (does it read `HOME_BASE`, a builder's `base`, or home?); (b) every path that sets a builder's base: commission, refit from another role, `pioneer.py:144` restore, decommission; (c) the git commit of the refit rework (`git log -S "refit" --oneline -- scripts/4_controlpanel/lib/pioneer_refit.py`) and what base builders had before it. In the main checkout, check the live save's `fleet.status` for builders based away from home (reading a save is fine).
- [x] **Step 2: Report** the root cause and the base paths to the operator before changing anything. If builders cannot drift (the lead is wrong), stop here and drop the task.
- [x] **Step 3: Failing tests**: `test_refit_to_builder_uses_constructor_base` (a miner with launch `HOME_BASE` = X refit to builder: base = `constructor_base()`); `test_builder_restore_keeps_constructor_base` (the `pioneer.py` restore path does not send a builder to its old miner base); `test_construction_stock_at_constructor_base`.
- [x] **Step 4: Implement** the smallest fix: builder refits and commissions pass `base=constructor_base()`; the stock reads `constructor_base()`. Other roles keep their current base logic.
- [x] **Step 5: Run tests, Ruff, `scripts_sync.py resolve-preview`, Pyright: PASS.**
- [x] **Step 6: Docs**: the cheatsheet section on Pioneer bases/refits (via `docs/AI_CHEATSHEET.md`); design reason to `docs/design_history/` (one fixed constructor base: stock and charging depend on it). **Commit** `fix(pioneer): builders keep one constructor base across refits`.

### Task 4: Drone takeover switch and Charging Station retirement

Operator, 2026-10-21: the goal is full automation; the FLEET switch is for play without autoplay. With autoplay active, the planner turns drone yield on itself; then the Pioneer-era stations go, except one.

**Files:**
- Modify: `autoplay/lib/build_providers.py` (`drones_haul()` :423, `kit_wants()` charging rows), `autoplay/lib/building_plan.py` (ctx :644; the switch flip), `autoplay/lib/autoplay_roles.py` (charging retirement next to `RETIRED_WITH` :131), `autoplay/lib/outpost_needs.py` (`with_charging()` keeps the keeper only)
- Test: `tests/test_autoplay_building_plan.py`, `tests/test_autoplay_outpost_needs.py`
- Docs: cheatsheet section that documents `kit_wants()` / charging (find via `docs/AI_CHEATSHEET.md`), §11h charging line, `production_logistics.md` if it describes the drone yield switch as operator-only

**Interfaces:**
- Produces:
  - `TAKEOVER_HAULERS = 3` (`build_providers`).
  - `drone_takeover(ctx) -> bool`: at least one outpost has role `drone_depot`, every such outpost has a deployed depot (`DEPOTS` types > 0), and flying hauler drones ≥ `TAKEOVER_HAULERS` (flying only: `ctx["fleet"]["drone"]["hauler"]`, not `fleet_count()`, which adds queued jobs).
  - The autoplay pass calls `logistics_requests.set_drone_yield_enabled(True)` once when `drone_takeover(ctx)` and the switch is off, with one info log line. It never turns the switch off.
  - Consumes Task 3.5's `constructor_base()`; after it, all builders share one base.
  - `station_keepers(outposts, fleet_status) -> set[str]` (`autoplay_roles` or `outpost_needs`, wherever both callers already import): the base of every `builder`-role unit in `fleet.status` (`entry.get("base") or entry.get("home") or HOME_OUTPOST_ID`, as `building_plan.py:551`; constructors charge at their base). When that set holds neither home nor a salt keeper, add the salt keeper: the nearest non-home outpost of biome `frozen` within `HOME_NEAR_M` (300 m, `outpost_sites`) of home, else home (pump-salt haulers).
  - Once `drones_haul(ctx)`: `kit_wants()` emits undeploy rows for `charging_station` at every outpost outside the keepers; a keeper's station is never undeployed, and home's goes only after every other keeper's is deployed. The `charging` role is removed from every outpost outside the keepers (follow the existing `RETIRED_WITH` removal path) and set on every keeper (a builder refit to another base moves the keeper). `with_charging()` adds the role to no new bundle (already).

- [x] **Step 1: Write the failing tests**: `test_drone_takeover_needs_depots_and_three_haulers` (2 depot-role outposts, one without a depot: False; both deployed, 2 haulers flying + 1 queued: False; 3 flying: True; no depot-role outpost: False); `test_takeover_flips_switch_once` (switch off + takeover: one `set_drone_yield_enabled(True)` call; switch on: none; never a False call); `test_station_keepers_builder_base` (builders based at home: `{home}` only, no salt keeper added; one builder based at outpost B, frozen outpost F at 250 m: `{B, F}`; F at 350 m: `{B, home}`; a hauler's base never counts); `test_charging_retired_except_keepers` (drones haul: undeploy rows for the other outposts; home row only once every other keeper has `charging_station` > 0); `test_charging_role_follows_keepers` (role removed outside the keepers, added to a new keeper after a builder base move).
- [x] **Step 2: Run, expect FAIL.**
- [x] **Step 3: Implement** the interfaces above. Locate the role removal path (`RETIRED_WITH` users) and the undeploy row format with `caveman:cavecrew-investigator` before editing.
- [x] **Step 4: Run tests, Ruff, Pyright (`scripts_sync.py resolve-preview` first if `scripts/*/lib` changed): PASS.**
- [x] **Step 5: Docs** (handoff's "Deferred" station items now done; the pressure metric stays deferred); **Commit** `feat(outposts): drone takeover switch, retire charging stations`.

### Task 5: Replay, tuning, docs

**Files:**
- Modify: `autoplay/lib/outpost_sites.py` (weights only), `docs/plans/planner_rev2_results.md` (new section "## Revision 3"), `docs/plans/outpost_founding_planner.md` (phase 9 line), `TODO.md` ("Outpost founding planner" line), cheatsheet rows if weights change.

- [x] **Step 1:** Run `python devtools/simulation/planner_replay.py C:/Users/Adrian/Code_Terraform/internals/sample_saves/20261007_c5f9ebf --out <scratchpad>/rev3_run1` and the same for `20261018_4c29716` (check `-h` first; `RUN_DIR` must be a `decision_recorder.py` run folder; use `--limit` if a run is slow).
- [x] **Step 2:** Read the second-factory proposals per kept save. Expected: run 2's second outpost leaves the western iron cluster when no vent is known nearby (toward the east deposit or the geothermal area); with a north-west vent it stays. Note term breakdowns of the top 3.
- [x] **Step 3:** If not as expected, tune `WEIGHTS_EARLY` `reach_gain` / `future` (and only then `WEIGHTS`), rerun, keep at most 3 iterations; record each try.
- [x] **Step 4:** Write "## Revision 3" in `planner_rev2_results.md` (same format as the Run sections: save, top site, terms, verdict), update the plan phase 9 line ("Code done", replay result), TODO.md line, cheatsheet weights.
- [x] **Step 5:** Full checks; `caveman:cavecrew-reviewer` on the branch diff; fix findings; **Commit** `docs(outposts): rev3 replay results and weights`.
