# Tier-Deficit Snapshot (Vector 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute every outpost's tier deficits and drone-loadable free stock once per orchestrator round, publish them as one archive record, and let the drone haul planner, the Pioneer pull planner and the role demand publisher read that record instead of recomputing it per call.

**Architecture:** A new lib module `logistics_snapshot.py` holds the record (build, publish, read with FRESH/STALE/MISSING) and a read-side `TierView` that corrects the record for pickups claimed since it was built. A `SnapshotPublisher` in the same module builds the record one outpost per task inside the orchestrator's `between_steps()`, like `DemandPublisher`. Consumers take an optional view; without one (STALE for planners, MISSING for all) they run today's live code unchanged. The claim step re-reads the chosen destination live before reserving.

**Tech Stack:** game-interpreter Python (`scripts/4_controlpanel/lib`), host `unittest` with `tests/harness.py` stubs, `devtools/perf/tick_profile.py` on save 0839.

**Spec:** [performance_planning_2026-10.md](performance_planning_2026-10.md), "Findings" 1 and 4, "Optimization vectors" 1, "Rollout" Vector 1 bullets. This file carries the design decisions (section "Design") and the plan.

## Global Constraints

- Start only after Vector 5 has merged: both change code around `PlanReads` in `logistics_requests.py`. This plan adds no method to `PlanReads`.
- Game interpreter rules apply (CODE_GUIDES.md "Game interpreter"). No `run_atomic()` around a task: `outpost_tier_free()` calls `stock_scan.scan()`, which runs its own atomic batches.
- Archive: one key for the whole record, written only by the orchestrator (`archive.set`), JSON-safe (CODE_GUIDES.md#archive). New key documented in `docs/cheatsheet/archive_ipc.md` §4 in the same change.
- New constants go into a cheatsheet section in the same change (CLAUDE.md "Docs"): the drone **Plan** part of `docs/cheatsheet/vehicles_drones.md`.
- Hold `devtools/.sync-backups/holds/<session id>` around multi-hunk edits under `scripts/` (CLAUDE.md "Boundaries").
- Checks per task: `python -m unittest discover -s tests`, `.venv/Scripts/python.exe -m ruff check` and `ruff format` on touched paths, `npx pyright` after `devtools/scripts_sync.py resolve-preview`.
- Targets (Results table, same save, gate and window as the baseline): drone plan 342 to ~130 ticks, pull plan 62 to ~30, role publish 88 to ~50.

## Review Focus

1. A delivery that lands between the build and a plan must not reappear as a deficit (stock in the record is old, the pickup is gone live). Expected: no phantom deficit. Pinned by `test_delivered_pickup_keeps_deficit_covered` (Task 1).
2. Two drones planning inside one snapshot window must not both fill the same deficit. Expected: the second sees the first's claim. Pinned by `test_new_pickup_cuts_top_band_first` (Task 1) and the claim-time trim (Task 3).
3. A planner reading a STALE record must plan live, never from the record. Pinned by `test_stale_snapshot_plans_live` (Task 3).
4. The orchestrator must not stall grid supervision while building: at most one outpost task past `LOGISTICS_SLICE_TICKS` per call. Pinned by `test_step_stops_after_slice` (Task 2).
5. A request that appears after the build (new outpost demand) is invisible until the next round. Expected: at most one round late, no crash on unknown outpost ids. Pinned by `test_unknown_outpost_reads_empty` (Task 1).

---

## Measurements (2026-10-22, save 0839, 0.4 game h, wrapped ticks)

Save: `internals/sample_saves/20261008_7e5e168/saves/0839_t1038072.json.gz`. No step-limit crash in any of the three runs.

**Orchestrator round.** `tick_profile.py --save <0839> --hours 0.4 --gate demand_publisher:DemandPublisher.step --modules demand_publisher --classes "" --label "args[0]"` (the label is the call tick; `DemandPublisher.step` runs once per `between_steps()`). 21 calls between ticks 1038402 and 1051689. Gaps between calls: median ~330 ticks (149 to 387 within one loop pass), ~800 to 900 between passes, max 1,992 (three gaps of 1,861 to 1,992). The demand step itself costs 6 to 8 ticks when idle and 400 to 504 when a refresh slice runs.

**Snapshot cost proxy.** `--gate role_demand:publish --modules role_demand,logistics_requests,mining_reservations --classes logistics_requests:PlanReads --label "'role'"`: n=13, total median 197. `outpost_tier_deficits` 149 (6 calls), of which `tier_deficits` 77 (91 calls), `request_levels` 32, `PlanReads.stock` 42, `PlanReads.scan` 24, `get_reserved_yield_totals` 4.

**Drone plan split.** `--gate drone_haul_plan:plan_haul_job --modules logistics_requests,mining_reservations --classes logistics_requests:PlanReads --label "'drone'"`: n=34, total median 451. `outpost_tier_deficits` 143 (6), `outpost_tier_free` 122 (6), `tier_deficits` 79 (127), `tier_free` 67 (76), `request_levels` 62 (171), `PlanReads.stock` 36, `PlanReads.scan` 25, `get_reserved_yield_totals` 2.

Reading: the per-item tier math, not the stock scans or the reserved-yield reads, is most of the cost. The wrappers inflate the many small calls, so the real share is smaller, but a record of raw inputs (stock, yields) would leave the larger part in every consumer. So the record stores computed tiers.

## Design

### Decisions

1. **Producer: the orchestrator, not a new automation.** A `SnapshotPublisher` runs from `between_steps()` in `orchestrator_automation.py`, before `publish_demand_if_due()`. It is not a `Refresh` task kind of the demand publisher: that refresh is signature-gated, backstopped at `DEMAND_BACKSTOP_TICKS`, and its rounds take 1,000 to 1,700 ticks on save 0839 (finding 3), so a snapshot built there would be older than its window. With its own interval in the same loop, the measured worst age (below) fits `LOGISTICS_FRESH_TICKS`, so a separate `logistics_orchestrator` automation (~0.6 % allowance for every script, §1d-1) is not justified.
2. **Constants** (`logistics_snapshot.py`):
   - `LOGISTICS_SNAPSHOT_TICKS = 600`: a new round starts this long after the last one started. Same cadence as `ROLE_DEMAND_TICK_INTERVAL`; a drone picks about every 400 ticks on save 0839.
   - `LOGISTICS_SLICE_TICKS = 100`: one `step()` runs outpost tasks while fewer ticks than this have passed (at least one task). One outpost task is ~25 wrapped ticks, so a 7-outpost round takes one or two calls.
   - `LOGISTICS_FRESH_TICKS = 3000`: worst measured age at read = interval 600 + a spill across the worst `between_steps()` gap 1,992 + build ~200 = ~2,800.
   - `LOGISTICS_MAX_STALE_TICKS = 6000` (`REQUEST_STALE_TICKS`): older records are MISSING.
3. **Record stores computed tiers, corrected on read by pickups.** Stock in the record is up to `LOGISTICS_FRESH_TICKS` old. Pickups change faster and are read live by every planner anyway (`PlanReads.pickups`, the `seen` snapshot). The record keeps the in-flight and reserved units it was built with. A reader subtracts only what grew since: for a destination, units claimed towards it since the build cut its deficits from the most urgent band down (cover fills the top band first, `priority.ladder_deficits()`); for a source, units reserved from it since the build cut every band's free units by the same amount (for `LOADER_DRONE`, `tier_free()` is linear in claimed units). Units that left the in-flight set (delivered or released) are ignored: a delivered unit is in the record's in-flight figure, so the deficit stays covered.
4. **Reserved mining yields are folded into the deficits at build time** (as `outpost_tier_deficits()` does today) and not corrected on read. A miner that reserves after the build is caught by the live destination trim at claim time (decision 6).
5. **Fair-share rivals come from the record.** `_cap_fair_tiers()` builds its rival index from the record's deficits at `FAIR_BANDS` (live stock, in-flight and yields) instead of each request's published `"have"` plus in-flight. Behavior change: an outpost with mining yield on the way counts as a smaller rival.
6. **`live=True` stays only for the destination being claimed.** Before `claim_pickups()`, `job_haul._claim_route()` and `PullJob.pick()` cap each leg item at the destination's live deficit (`outpost_tier_deficits(live=True)`, one outpost) when the plan came from the record. Then the existing "units < wanted: release and drop/replan" path runs. Sources are not re-read: a short pickup self-corrects (the drone takes what is there and the leg is released). `role_demand.compute()` and `_cap_fair_tiers()` never read live.
7. **Free stock is recorded for the drone loader only**, over every item requested anywhere in the network. `pull_plan.pull_sources()` (vehicle loader, `_vehicle_reach()`) stays live; it is not in the Vector 1 consumer list.

### Record

Key `logistics.tier_snapshot`, one dict, written whole by the orchestrator:

```
{"v": 1, "tick": T0,                      round start: PlanReads(T0) requests and pickups
 "outposts": {outpost_id: {
     "deficits": {band: {item_id: units}}, outpost_tier_deficits(live=True, reads), with in-flight and reserved yields
     "free":     {band: {item_id: units}}, outpost_tier_free(loader=LOADER_DRONE, no exclude_vehicle), every requested item
     "flying":   {item_id: units},         reads.in_flight(outpost_id) at T0
     "taken":    {item_id: units}}}}       reads.reserved_from(outpost_id) at T0
```

Band keys are written as `str(band)` and parsed back to `int` per outpost on first use (archive values are JSON). Outposts with nothing in any field are left out.

### FRESH / STALE / MISSING

Age = reader tick minus `"tick"`. FRESH: age ≤ `LOGISTICS_FRESH_TICKS`. STALE: up to `LOGISTICS_MAX_STALE_TICKS`. MISSING: none, another `"v"`, or older.

| Consumer | FRESH | STALE | MISSING |
|---|---|---|---|
| `drone_haul_plan.haul_destinations` | `view.deficits()` per Depot outpost | live (today) | live |
| `drone_haul_plan.outpost_sources` | `view.free()` per Depot outpost | live | live |
| `drone_haul_plan._cap_fair_tiers` | rivals from `view.rivals()` | live rivals (today) | live |
| `job_haul._claim_route` | live trim of the claimed dest, then claim | claim as today | claim as today |
| `pull_plan.pull_destinations` | `view.deficits()` per outpost | live | live |
| `job_pull.PullJob.pick` | live trim of the chosen dest, then claim | claim as today | claim as today |
| `role_demand.compute` | `view.deficits()` per outpost | `view.deficits()` | live |

`role_demand.compute()` accepts STALE: it runs in the producer's own script, so a STALE record means that script is lagging, and recomputing there adds to the lag. Planners log one debug line when they fall back on a STALE record.

### Expected effect

Drone plan: `outpost_tier_deficits` + `outpost_tier_free` (265 of 451 wrapped) become one archive read plus the pickup correction; the claim adds one live outpost deficit (~25 wrapped). Pull plan: `pull_destinations` and its 4 deficit calls become the read. Role publish: `outpost_tier_deficits` (149 of 197 wrapped on save 0839) goes. The orchestrator gains ~one role-publish worth of work per 600 ticks (the build) and loses the same in `role_demand.compute()`; net about zero.

### Operator to confirm

1. Producer in the orchestrator loop, no new automation (decision 1), on the measured worst age ~2,800 ticks.
2. `LOGISTICS_FRESH_TICKS = 3000`: drones may rank destinations on stock up to ~5 game minutes old; the claim-time trim guards over-delivery.
3. Fair-share rivals from the record (decision 5) changes split results when miners are inbound.
4. Sources are never re-read live (decision 6): a drone can fly to a source that emptied since the build.
5. Reserved yields are not corrected on read (decision 4).

### Risks

- Under-estimated free stock at a source the planning drone itself reserved from at build time (its old reservation is in `"taken"` and cannot be told apart); lasts one round.
- Archive record size: free stock over every requested item at every band. Measure `archive.get` of the record in the remeasure run; if it shows, store free only at `FAIR_BANDS` plus the top band per item.
- Mixed build ticks: outposts later in a round are scanned up to one `between_steps()` gap after T0 while in-flight units are from T0; a delivery in between counts twice (deficit too small, under-delivery for one round).
- Step cap: the consumers lose their largest atomic pre-work, so finding 4's margin should grow; Vector 4 decides after the remeasure.

---

## File Structure

- Create `scripts/4_controlpanel/lib/logistics_snapshot.py`: constants, `build_entry()`, `publish_snapshot()`, `read_snapshot()`, `TierView`, `view()`, `trim_to_live()`, `SnapshotPublisher`, `PUBLISHER`.
- Modify `scripts/4_controlpanel/automation/orchestrator_automation.py`: `publish_logistics_if_due()` in `between_steps()`; `publish_role_demand_if_due()` passes the view.
- Modify `scripts/4_controlpanel/lib/drone_haul_plan.py` (`haul_destinations`, `outpost_sources`, `_cap_fair_tiers`, `plan_haul_job`), `scripts/4_controlpanel/lib/job_haul.py` (`_claim_route`).
- Modify `scripts/4_controlpanel/lib/pull_plan.py` (`pull_destinations`), `scripts/4_controlpanel/lib/job_pull.py` (`PullJob.pick`).
- Modify `scripts/4_controlpanel/lib/role_demand.py` (`compute`, `publish`).
- Create `tests/test_logistics_snapshot.py`; extend `tests/test_plan_reads.py` for consumer equivalence.
- Docs: `docs/cheatsheet/archive_ipc.md` §4 (key), `docs/cheatsheet/vehicles_drones.md` drone **Plan** (constants, contract), `docs/design_history/logistics_production.md` (decisions 1, 3, 5, 6), Results rows in `performance_planning_2026-10.md`.

### Task 1: Record, reader and pickup correction

**Files:**
- Create: `scripts/4_controlpanel/lib/logistics_snapshot.py`
- Test: `tests/test_logistics_snapshot.py`

**Interfaces:**
- Produces:
  - `LOGISTICS_SNAPSHOT_KEY = "logistics.tier_snapshot"`, `LOGISTICS_SNAPSHOT_VERSION = 1`, the four tick constants (Design 2), `FRESH`, `STALE`, `MISSING` (import from `production_demand_record`, same strings).
  - `build_entry(outpost, reads, item_ids) -> dict`: one outpost's record entry (keys per "Record", band keys `str`).
  - `publish_snapshot(entries: dict, tick: int) -> bool`: `archive.set` of `{"v", "tick", "outposts"}`; False without a clock.
  - `read_snapshot(now=None) -> tuple[dict | None, str]`: `(record, state)`, record None when MISSING.
  - `class TierView(record, reads, exclude_vehicle=None)`: `deficits(outpost_id) -> {int band: {item_id: units}}`, `free(outpost_id, item_ids, tiers=TIERS) -> {band: {item_id: units}}` (every `TIERS` key present, like `outpost_tier_free()`), `rivals(item_ids) -> {item_id: [(outpost_id, {band: units})]}` (shape of `fair_rivals_index()`, `FAIR_BANDS` only).
  - `view(reads, now=None, allow_stale=False, exclude_vehicle=None) -> TierView | None`: None unless FRESH (or STALE with `allow_stale`).

- [ ] **Step 1: Write the failing tests** (harness `StubTestCase` world as in `tests/test_plan_reads.py`)
  - `test_entry_matches_live_reads`: for every outpost, `build_entry(o, reads, items)` parsed back equals `outpost_tier_deficits(o, t, live=True, reads=reads)` and `outpost_tier_free(o, items, None, t, loader=LOADER_DRONE, reads=reads)`.
  - `test_read_states`: age 3000 FRESH, 3001 STALE, 6000 STALE, 6001 MISSING; `"v": 2` MISSING; nothing stored MISSING.
  - `test_new_pickup_cuts_top_band_first`: record deficit `{BLOCKER: {"x": 5}, NEED: {"x": 10}}`, `"flying": {}`; a live pickup of 8 x to that outpost; `view.deficits()` is `{NEED: {"x": 7}}`.
  - `test_delivered_pickup_keeps_deficit_covered`: record `"flying": {"x": 10}`, deficits `{NEED: {"x": 4}}`; live pickups empty; `view.deficits()` stays `{NEED: {"x": 4}}`.
  - `test_new_reservation_cuts_every_free_band`: record free `{NEED: {"x": 6}, STOCK: {"x": 20}}`, `"taken": {}`; a live pickup of 8 x from that source by another vehicle; `view.free(o, ["x"])` has `STOCK: {"x": 12}` and no x at NEED. The same pickup by `exclude_vehicle` changes nothing.
  - `test_unknown_outpost_reads_empty`: `deficits("nope") == {}`, `free("nope", ["x"])` has every `TIERS` key, all empty.
  - `test_view_none_unless_fresh`: STALE gives None, with `allow_stale=True` a view; MISSING None either way.

- [ ] **Step 2: Run them, expect ImportError**
  Run: `python -m unittest tests.test_logistics_snapshot -v` (from repo root with the `tests` path setup the suite uses: `python -m unittest discover -s tests -p test_logistics_snapshot.py -v`). Expected: errors, module missing.

- [ ] **Step 3: Implement** the Interfaces above. `build_entry` calls the existing `outpost_tier_deficits(..., live=True, reads=reads)` and `outpost_tier_free(..., loader=LOADER_DRONE, reads=reads)` (no `exclude_vehicle`), plus `reads.in_flight()` and `reads.reserved_from()`. `TierView` parses an outpost's entry once and caches it; the live side is `reads.in_flight(outpost_id)` and `reads.reserved_from(outpost_id, exclude_vehicle)`. Correction per item: `extra = max(0, live - recorded)`; destination: subtract `extra` walking `TIERS` in order, drop zeros; source: subtract `extra` from every band, drop ≤ 0.

- [ ] **Step 4: Run the tests, expect PASS**; then ruff, pyright.

- [ ] **Step 5: Commit** `feat(logistics): tier snapshot record and reader`.

### Task 2: Publisher and orchestrator hook

**Files:**
- Modify: `scripts/4_controlpanel/lib/logistics_snapshot.py`
- Modify: `scripts/4_controlpanel/automation/orchestrator_automation.py` (`between_steps()`, new `publish_logistics_if_due()`)
- Test: `tests/test_logistics_snapshot.py`
- Docs: `docs/cheatsheet/archive_ipc.md` §4, `docs/cheatsheet/vehicles_drones.md` drone **Plan**

**Interfaces:**
- Consumes: `build_entry`, `publish_snapshot` (Task 1).
- Produces: `class SnapshotPublisher` with `step(now) -> bool` (True when it published this call), `PUBLISHER = SnapshotPublisher()`.

- [ ] **Step 1: Write the failing tests**
  - `test_not_due_before_interval`: after a publish at t, `step(t + 599)` builds nothing and returns False; `step(t + 600)` starts a round.
  - `test_step_stops_after_slice`: with a clock stub that advances 60 ticks per outpost task and 7 outposts, the first `step()` runs 2 tasks and returns False; later calls finish and the last returns True; the record's `"tick"` is the round's start tick.
  - `test_round_publishes_every_outpost`: the published `"outposts"` has an entry for each outpost with a deficit or free stock.
  - `test_task_error_skips_outpost`: an outpost whose `build_entry` raises is left out, the round still publishes (logged through `swallowed()`).

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement.** A round: at start `reads = PlanReads(now)`, `item_ids` = every item in `reads.requests` over all outposts, outposts from `outpost_network.outposts()`; one task per outpost; loop `while pending` with at least one task, break when `now_tick() - call_start >= LOGISTICS_SLICE_TICKS`; publish stamped with the round start. `publish_logistics_if_due()` in the orchestrator wraps `logistics_snapshot.PUBLISHER.step(now_tick())` in `try/except` with `report_error("Logistics snapshot", e)`, called in `between_steps()` before `publish_demand_if_due()`.

- [ ] **Step 4: Run tests, expect PASS**; ruff, pyright. Add the key row to archive_ipc.md §4 and the constants and FRESH/STALE/MISSING table to vehicles_drones.md drone **Plan**.

- [ ] **Step 5: Commit** `feat(orchestrator): publish logistics tier snapshot`.

### Task 3: Drone haul planner and claim

**Files:**
- Modify: `scripts/4_controlpanel/lib/drone_haul_plan.py` (`haul_destinations`, `outpost_sources`, `_cap_fair_tiers`, `plan_haul_job`)
- Modify: `scripts/4_controlpanel/lib/job_haul.py` (`_claim_route`)
- Modify: `scripts/4_controlpanel/lib/logistics_snapshot.py` (`trim_to_live`)
- Test: `tests/test_plan_reads.py`, `tests/test_logistics_snapshot.py`

**Interfaces:**
- Consumes: `view()`, `TierView` (Task 1).
- Produces:
  - `haul_destinations(drone, curr_tick, reads=None, layout=None, view=None)`, `outpost_sources(..., tiers=TIERS, view=None)`, `_cap_fair_tiers(dests, sources, curr_tick, reads, view=None)`.
  - `plan_haul_job()` builds `view = logistics_snapshot.view(reads, curr_tick, exclude_vehicle=drone.name)` once and passes it; the returned plan and each alternate carry `"snapshot": True` when the view was used.
  - `trim_to_live(dest_outpost, legs, curr_tick) -> list[tuple[source_id, item_id, units]]`: legs with each item's units capped, in leg order, at the sum over bands of `outpost_tier_deficits(dest_outpost, curr_tick, live=True)`.

- [ ] **Step 1: Write the failing tests**
  - `test_fresh_snapshot_matches_live_plan` (test_plan_reads): a world with a FRESH record built from the same state gives the same `haul_destinations()` tiers and `outpost_sources()` tiers as the live path, and `PlanReads.scan` is never called.
  - `test_stale_snapshot_plans_live`: with a STALE record, `plan_haul_job` reads stock (scan called) and logs the fallback line.
  - `test_rivals_from_snapshot`: `_cap_fair_tiers` with a view caps a destination at its share against the record's `FAIR_BANDS` deficits of another outpost.
  - `test_trim_to_live_caps_legs`: live deficit x=5 at dest, legs `[("a", "x", 4), ("b", "x", 4)]` give `[("a", "x", 4), ("b", "x", 1)]`; live deficit 0 gives both legs 0.
  - `test_claim_route_trims_snapshot_plan` (job_haul with harness stubs): a `"snapshot": True` plan whose dest is now full claims nothing and returns None; a plan without the flag claims as before.

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement.** Each consumer uses the view when given, else today's code. `_claim_route()` calls `trim_to_live()` on its legs only for `"snapshot"` plans, before `claim_pickups()`; zero legs are dropped before the claim. The `_warn_if_home_has_no_depot()` `live=False` read and `drone_hauler.py`'s cargo-drop `haul_destinations()` call stay as they are.

- [ ] **Step 4: Run tests, expect PASS**; ruff, pyright.

- [ ] **Step 5: Commit** `perf(drone): plan hauls from the tier snapshot`.

### Task 4: Pull planner and Pioneer claim

**Files:**
- Modify: `scripts/4_controlpanel/lib/pull_plan.py` (`pull_destinations`), `scripts/4_controlpanel/lib/job_pull.py` (`PullJob.pick`)
- Test: `tests/test_logistics_snapshot.py`

**Interfaces:**
- Consumes: `view()`, `trim_to_live()` (Tasks 1, 3).
- Produces: `pull_destinations(curr_tick, reads=None, view=None)`; `PullJob.pick()` builds the view with `exclude_vehicle=host.name`.

- [ ] **Step 1: Write the failing tests**
  - `test_pull_destinations_from_snapshot`: FRESH record gives the same band groups as the live path without a stock scan.
  - `test_pull_pick_trims_to_live`: a destination filled since the build makes `pick()` release and return None (`claimed < wanted` path).

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement**: `pull_deficits_tiered()` stays the live function; `pull_destinations()` uses `view.deficits(outpost.id)` when given. In `pick()`, when the view was used, run `trim_to_live()` on the route legs before `claim_pickups()`.
- [ ] **Step 4: Run tests, expect PASS**; ruff, pyright.
- [ ] **Step 5: Commit** `perf(pull): plan pulls from the tier snapshot`.

### Task 5: Role demand

**Files:**
- Modify: `scripts/4_controlpanel/lib/role_demand.py` (`compute`, `publish`), `scripts/4_controlpanel/automation/orchestrator_automation.py` (`publish_role_demand_if_due`)
- Test: `tests/test_logistics_snapshot.py`

**Interfaces:**
- Consumes: `view(reads, now, allow_stale=True)` (Task 1).
- Produces: `compute(curr_tick, reads=None, view=None)`, `publish(curr_tick, reads=None, view=None)`; `parts["deficits"]` keeps its shape for `mission_pool`.

- [ ] **Step 1: Write the failing tests**
  - `test_role_compute_uses_stale_snapshot`: a STALE record's deficits appear in `compute()["parts"]["deficits"]` and no stock scan runs.
  - `test_role_compute_missing_is_live`: MISSING gives today's result.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement**: `compute()` takes `view.deficits(o.id)` per outpost when a view is given. The orchestrator builds `reads = PlanReads(now)` and `view(reads, now, allow_stale=True)` and passes both.
- [ ] **Step 4: Run tests, expect PASS**; ruff, pyright.
- [ ] **Step 5: Commit** `perf(roles): role demand from the tier snapshot`.

### Task 6: Remeasure and document

**Files:**
- Modify: `docs/plans/performance_planning_2026-10.md` ("Results"), `docs/design_history/logistics_production.md`

- [ ] **Step 1: Baselines.** Rerun on `main` (before the merge) and on the branch, save 0839, `--hours 0.4`, the three commands under "Measurements" above (drone and role gates), plus `--gate job_pull:PullJob.pick --modules pull_plan,logistics_requests --label "'pull'"` on save A (`internals/sample_saves/20261007_c5f9ebf/saves/0262_t349372.json.gz`) and `--gate role_demand:publish` on save A. Same modules and window before and after.
- [ ] **Step 2: Check the record age.** Add `--gate logistics_snapshot:SnapshotPublisher.step --label "args[0]"` on save 0839; worst age between published `"tick"` and the next publish must stay under `LOGISTICS_FRESH_TICKS`. If not, report it; do not raise the window without the operator.
- [ ] **Step 3: Results rows** (one per gate) in `performance_planning_2026-10.md`; design reasons (decisions 1, 3, 5, 6 and the measurements) into `docs/design_history/logistics_production.md`.
- [ ] **Step 4: Full checks** (`python -m unittest discover -s tests`, ruff, pyright), `caveman:cavecrew-reviewer` on the branch with the session's model, fix findings.
- [ ] **Step 5: Commit** `docs(perf): vector 1 results`.
