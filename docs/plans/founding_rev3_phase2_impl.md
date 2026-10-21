# Founding planner rev3 phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the second outpost spread outward and look ahead to the steam outpost: two new site score terms (`reach_gain`, `future`), a `power` need that forms on a discovered vent, then replay both recorded runs and tune the weights.

**Architecture:** Both terms live in `autoplay/lib/outpost_sites.py`. Their inputs are precomputed once per ranking (`prepare()` / `prepare_want()`), so the per-anchor cost in `_finish()` stays a short loop over a few points. `outpost_needs` names the future fluids and `outpost_plan._rank()` passes them in with the phase 1 geothermal scout areas.

**Tech Stack:** Python (game interpreter subset), `unittest`, Ruff, Pyright; replay via `devtools/simulation/planner_replay.py`.

**Spec:** [founding_rev3_phase2_handoff.md](founding_rev3_phase2_handoff.md) and [outpost_founding_planner.md](outpost_founding_planner.md) "Revision 3" (decisions B, C).

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
3. Late game, when drones haul (no new Charging Station at the candidate): `reach_gain` still assumes a station. Accepted (spec); pin that the term is the same with `reach=None` in Task 1, so a later change is deliberate.
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

- [ ] **Step 1: Write the failing tests** (class `ReachGainTests`, use the `world()` / `prepare()` helpers)
  - `test_reach_gain_rewards_new_ground`: home at (0, 0) with `home=True`; 4 POIs at (1500, 0) region; candidate A at (1000, 0), candidate B at (-300, 0). `score(ctx, A...)["terms"]["reach_gain"] == WEIGHTS["reach_gain"] * 1.0`; B's term `== 0.0`.
  - `test_reach_gain_share_of_remote`: 2 remote POIs east, 2 remote POIs west, candidate east reaches only the east pair: term `== WEIGHTS["reach_gain"] * 0.5`.
  - `test_reach_gain_zero_without_starts_or_remote`: no outposts: 0; all POIs within 600 m of home: 0.
  - `test_reach_gain_ignores_stuck`: the only remote contact is blocked (stuck): term 0 and `ctx["remote_n"] == 0`.
  - `test_reach_gain_out_of_confidence`: two ctx differing only in remote POIs give equal `confidence`.
  - Extend `BudgetTests.test_score_step_fits` (or add `test_score_step_fits_with_remote`): dense ctx plus 200 POIs beyond 600 m of home spread over the map; worst slice `< ATOMIC_STEP_BUDGET`.
- [ ] **Step 2: Run, expect FAIL** (`KeyError: 'reach_gain'`).
- [ ] **Step 3: Implement.** In `prepare()`: build `remote`/`remote_n` from `rows` and `starts` (no starts: empty). Weights `"reach_gain": 3.0` in `WEIGHTS` (so `WEIGHTS_EARLY` inherits). In `_finish()`: `terms["reach_gain"] = weights.get("reach_gain", 0.0) * (sum of n over clusters within CONSTRUCTOR_REACH_M of (cx, cy)) / remote_n`, 0 when `remote_n == 0`. In `score_step()`: charge one new `REACH_UNITS` (start at 1) per cluster on top of `FINISH_UNITS`, so many clusters split slices.
- [ ] **Step 4: Run tests, Ruff, Pyright: PASS.**
- [ ] **Step 5: Docs.** §11i table row `reach_gain | 3 | share of out-of-reach contacts (any kind, not stuck) the candidate's Charging Station would bring within CONSTRUCTOR_REACH_M`; note it is outside `RESOURCE_TERMS`.
- [ ] **Step 6: Commit** `feat(outposts): reach_gain site term`.

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

- [ ] **Step 1: Write the failing tests**
  - needs: `test_future_fluids_steam_until_power_host` (no host: `["steam"]`; outpost with `roles=["power"]`: `[]`); `test_future_fluids_skip_proposed_power` (a `power` need at `"soon"` in `needs`: no `"steam"`); `test_future_fluids_water_when_nuclear_ahead`; `test_plan_hosts_carries_future`.
  - sites (`FutureTests`): `test_future_pulls_to_discovered_vent` (level-2 thermal site at (500, 0), candidate at (250, 0): term `== 3.0 * 0.5` within 0.01; candidate 600 m away: 0); `test_future_unknown_poi_needs_geothermal_biome` (unknown POI in a geothermal biome scores > 0, same POI in frozen scores 0); `test_future_falls_back_to_geothermal_cell` (no contacts, `geothermal=[(400, 0)]`, candidate at (0, 0): `3.0 * 0.5 * (1 - 400/500)`); `test_future_empty_is_zero`; `test_future_ignores_stuck`; `test_future_out_of_confidence`; budget test with 8 spots × 2 fluids under `ATOMIC_STEP_BUDGET`.
  - plan: `test_rank_reranks_on_future_change` (same bundles, `plan["future"]` changes from `[]` to `["steam"]`: `_rank()` rebuilds `self.ranked`).
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** the interfaces above; weights `"future": 3.0`; `_rank()` adds `plan.get("future")` to the signature, passes `geothermal=self.geo_areas or []` (the phase 1 scout areas: ≤ `GEOTHERMAL_SCOUTS` points, cheap, nearest home) and `future=plan.get("future", [])` to `wants()`. `score_step()` charges `REACH_UNITS` per spot.
- [ ] **Step 4: Run tests, Ruff, Pyright (run `devtools/scripts_sync.py resolve-preview` first only if a `scripts/*/lib` file changed): PASS.**
- [ ] **Step 5: Docs.** §11i row `future | 3 | closeness (1 − d/FUTURE_RANGE_M) to the best contact of each look-ahead fluid: known fluid 1, unknown by biome prior, else a geothermal scout area at 0.5`; constants `FUTURE_RANGE_M`, `FUTURE_TOP`, `FUTURE_CELL_VALUE`; §11h one line on `future_fluids()`. Note the deviation from the handoff: the fallback uses the scout areas, not all probe cells.
- [ ] **Step 6: Commit** `feat(outposts): future site term for look-ahead fluids`.

### Task 3: `power` need on a discovered vent

**Files:**
- Modify: `autoplay/lib/outpost_needs.py` (`snapshot()` :763, `lookahead()` power block :288-291)
- Modify: `autoplay/lib/outpost_plan.py` (survey flag where proposals are made, :438 area, and `recheck()`)
- Test: `tests/test_autoplay_outpost_needs.py`, `tests/test_autoplay_outpost_plan.py`
- Docs: §11h power line

**Interfaces:**
- Produces: `snap["thermal_sites"]`: `[{"id", "x", "y"}]` of `journal.discovered_sites("nocturna")` rows of kind `thermal` not in `snap["fluid_sites"]` (by id). The `power` need from a discovered-only vent carries `survey_first=True`. A found proposal whose bundle has a need with `survey_first` gets `survey = True` regardless of confidence.

- [ ] **Step 1: Write the failing tests**: `test_power_on_discovered_vent` (no fluid sites, one `thermal_sites` row, no outpost within `NEAR_TILES` of its `extractor_box`: `power` need with `site_fluid == "steam"`, `survey_first` True, urgency from Thermal Cap ETA); `test_power_discovered_vent_hosted` (outpost next to it: no need); `test_surveyed_vent_no_survey_first` (existing test path keeps `survey_first` absent); plan: `test_survey_first_forces_survey`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** `snapshot()` reads discovered sites once (follow `fluid_outlook.discovered_fluid_rows()` :277 for the join, surveyed wins). In `lookahead()`, a vent counts when it is surveyed (as now) or in `thermal_sites`; the hosted check uses `gap(outpost_box, [extractor_box(x, y)])` for discovered vents. `_site_ok()` / `near_fluid()` keep requiring surveyed sites.
- [ ] **Step 4: Run tests, Ruff, Pyright: PASS.**
- [ ] **Step 5: Docs** §11h; **Commit** `feat(outposts): power need on a discovered vent`.

### Task 4: Replay, tuning, docs

**Files:**
- Modify: `autoplay/lib/outpost_sites.py` (weights only), `docs/plans/planner_rev2_results.md` (new section "## Revision 3"), `docs/plans/outpost_founding_planner.md` (phase 9 line), `TODO.md` ("Outpost founding planner" line), cheatsheet rows if weights change.

- [ ] **Step 1:** Run `python devtools/simulation/planner_replay.py C:/Users/Adrian/Code_Terraform/internals/sample_saves/20261007_c5f9ebf --out <scratchpad>/rev3_run1` and the same for `20261018_4c29716` (check `-h` first; `RUN_DIR` must be a `decision_recorder.py` run folder; use `--limit` if a run is slow).
- [ ] **Step 2:** Read the second-factory proposals per kept save. Expected: run 2's second outpost leaves the western iron cluster when no vent is known nearby (toward the east deposit or the geothermal area); with a north-west vent it stays. Note term breakdowns of the top 3.
- [ ] **Step 3:** If not as expected, tune `WEIGHTS_EARLY` `reach_gain` / `future` (and only then `WEIGHTS`), rerun, keep at most 3 iterations; record each try.
- [ ] **Step 4:** Write "## Revision 3" in `planner_rev2_results.md` (same format as the Run sections: save, top site, terms, verdict), update the plan phase 9 line ("Code done", replay result), TODO.md line, cheatsheet weights.
- [ ] **Step 5:** Full checks; `caveman:cavecrew-reviewer` on the branch diff; fix findings; **Commit** `docs(outposts): rev3 replay results and weights`.
