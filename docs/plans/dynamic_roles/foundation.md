# Foundation: role demand, role slots, refit, job switch

Implementation spec for session 3's edit half (Opus). Probe results and seams are verified against the live
save `mvdnuhjh_rbjww6`, the game docs and the decompiled sim (2026-10-19). Design rationale:
[README.md](README.md) "Foundation". Work in worktree `.claude/worktrees/role-foundation`, branch
`agent/role-foundation`.

## Probe results (resolve the README's open points)

1. **Service area = the outpost's placement footprint, padded 2 m, not a radius.** The sim checks the
   vehicle position against the rectangle `x ∈ [ox - 2, ox + 22)`, `y ∈ [oy - 22, oy + 2)` where `(ox, oy)` is
   `outpost.coords()` (footprint 2 × 2 tiles of 10 m, origin at the top-left corner; home at `(0, 0)`). The
   outpost must not be under construction. "Parked" = speed ≤ 0.001 and no throttle (or held by the parking
   context). Every Vehicle Charging Station in the save sits exactly on its outpost's origin, and
   `charging_stations.home_slot_coords()` is the station position with no stagger, so a vehicle after
   `return_to_base()` is inside the rectangle. Evidence: `O1_miner_5` mounted all 8 slots at `outpost_1` right
   after deploy (`pioneer_5.log`, tick 118443); parked haulers sit at `(-420, 120)` = `outpost_1.coords()`.
   Script side: `in_service_area(pos, outpost_coords)` as a pure function in the new module, same rectangle;
   use it as the pre-check, and treat `not_at_service_point` from the first `unmount`/`mount` as "park again".
2. **`unmount` refuses a holder with filled bays** in code too: outcome `holder_not_empty` (pioneer.md,
   decompiled outcome contract). Uninstall every bay first, as `_strip_and_sell_parts` and `_swap_container`
   already do.
3. **Keying survives a rename.** `fleet.status` is keyed by `host.name`, which is `vehicle.id`
   (`vehicle.py:61`); `fleet.commission.lineage` is keyed by the vehicle id (`fleet_commission.py:474`). No
   re-key needed. `computer.rename` outcomes: `ok`, `locked`, `not_found`, `name_empty`, `name_too_long`,
   `name_taken` (ship_computer.md). `commission_name()` keeps the id number, so a refit name is unique unless
   the operator renamed something by hand: on `name_taken` keep the old name.
4. **Lineage lifetime.** The coordinator pops the lineage entry and the job when fitting finishes
   (`fleet_commission.py:505-510`), so a running Pioneer has no lineage entry. A refit creates a fresh job
   (below) instead of patching an old one.

## Seams (verified lines, main at 02f879b)

- `fleet_unit.py:42-85` `run_job_loop`: `following = self.next_job(job)` every cycle; `job.on_leave()` then
  `following.announce()` when it differs. `next_job` default `fleet_unit.py:107`. `job_base.py:111`
  `on_leave()` default `host.end_mission()`; `PullJob.on_leave` (`job_pull.py:264`) also releases pickups.
- `pioneer.py:85-130` `run()`: `fit_commissioned_loadout()`, `detect_role()`, `self.role = role`, then the
  role → Job dispatch (`BuildJob(self)`, `SurveyJob(self)` + `can_run()`, `MineJob(self,
  OutpostStockpile(self.home_base))`, `PullJob(self)`).
- `pioneer_commission.py`: `PIONEER_PRESETS` (:61), `build_spec(role, catalogue) -> (spec, None) | (None,
  reason)` (:108), spec `{"modules": [...8 ids], "battery_fill", "bin_fill"}`; `LoadoutFittingMixin` (:141):
  `fit_loadout(spec, label, on_missing)` (:163) loops `_fit_pass` (:207) until `"done"`, calls
  `on_missing({item_id: n})` every pass; `_report_missing(name, missing)` (:180) writes lineage `missing` and
  `passes`; `fit_commissioned_loadout()` (:154) then writes `{"fitted": True, "missing": {}}`. Helpers:
  `commission_state()`, `update_commission(mutate)`, `lineage_entry(vehicle_id)`.
- `fleet_commission.py:428` `_advance(job, pioneers)`: state `"fitting"` (:497-523) reads lineage
  `fitted`/`missing`/`passes`, buys through `_buy_missing(missing, catalogue, label)` (:304) once per
  `FIT_SETTLE_PASSES`, checks `_wrong_home(status, home_base)` (:525), finishes by removing the job and the
  lineage entry. `_name_new(new_id, outpost_id, role, label)` (:281) renames through `computer.rename`, a
  refusal keeps the game's name. `commission_name(new_id, outpost_id, role)` (:119).
- `vehicle_recall.py:101` `_strip_and_sell_parts()`: the uninstall-every-bay → `unmount` → `shop.sell` loop,
  Nav Module kept. `pioneer_upgrade.py:542` `_swap_container()` is the same loop for one slot;
  `_ensure_full_charge_for_sale()` (:495) tops the battery off before holders are sold.
- Claims: `fleet_claims_common.py:81` `try_claim(key, target_key, name, owner_of, record, tick, stale_ticks,
  notes) -> bool`, `:112 refresh_claim(key, target_key, owns, tick)`, `CLAIM_STALE_TICKS = 36000` (:22).
  `vehicle_claims.py:99` `VehicleClaimsMixin` wraps them for survey claims (`claim_target` :132, `_owns`
  :158, `_release_claims` :189).
- Demand sources: `logistics_requests.py:842` `outpost_tier_deficits(outpost, curr_tick=None, live=True,
  reads=None, exclude_vehicle=None) -> {band: {item_id: units}}`; `PlanReads(curr_tick, pickups=None)`
  (:548-559); `construction_lots.py:168` `read_jobs(bp, "pending_constructions"|"paused_constructions") ->
  (jobs, ok)`; `construction_plan.py:486` `held_kinds(raw, tick) -> set`; `survey_requests.py:48`
  `read_requests() -> dict`; `job_survey.py:90` `SurveyJob._known_candidates() -> bool` (unscanned POIs,
  unsurveyed known sites, deep-oil targets; needs a host, so Stage 3 lifts the three reads into
  `survey_requests`); `vehicle_mining.py:124-135` `home_ore_bands()`/`home_ore_demand()` (Stage 3).
- Bands: `priority.py:19-30` `BLOCKER 900 … STOCK 100, NONE 0`, `band(prio)` (:48); `pull_plan.py:58`
  `top_band(tiers)`.
- Founded outposts: `outpost_flow.py:69` `founded_outposts() -> {id: (x, y)}`.
- Orchestrator: `orchestrator_automation.py:318` `between_steps(clock)`; cadence pattern `plan_docks_if_due`
  (:183-201, `last_tick` + `DOCK_PLAN_TICK_INTERVAL`); constants block :127-150.
- Telemetry: `fleet_unit.py:124-144` `publish_telemetry` keys `name, state, wh, level, target, intent, role,
  tick` + `x, y, home, base` (`vehicle.py:189`). FLEET card rows `vehicles_card.py:123-129`, detail :160-174.
- Autoplay: `build_providers.py:383` `fleet_wants` (scout retire :400, miner :403, hauler :408,
  `KEEP_PIONEER_HAULERS = 2` :87); Stage 2 removes the retire rules, not this session.
- Tests: `tests/harness.py:137` `StubTestCase`; `tests/test_job_pull.py:30,123` network/outpost stubs;
  `tests/test_fleet_claims_common.py`, `tests/test_outpost_flow.py` (real `archive`).

## Edits

### 1. `lib/role_demand.py` (new, pure where possible)

- `ROLE_DEMAND_KEY = "fleet.role_demand"`, value `{"tick": t, "roles": {role: {"band": int, "wanted": int,
  "keep": int, "outposts": {outpost_id: band}}}}`. Roles this session: `hauler`, `constructor`, `scout`.
  `miner` is written with `band 0, wanted 0, keep` = number of founded outposts with a Smelter until Stage 3
  replaces it (so Stage 3 only changes the computation).
- `compute(curr_tick, reads=None) -> dict`:
  - hauler: per founded outpost `outpost_tier_deficits(outpost, curr_tick, reads=reads)`; `band` = top band
    with a deficit, `outposts[id]` = that outpost's top band; `wanted` = number of outposts with a deficit at
    `band` (≥ 1 while any deficit), `keep = KEEP_HAULERS` (1).
  - constructor: `read_jobs(blueprint, "pending_constructions")` minus `held_kinds(...)`; `band = BUILD`
    while any open job, `wanted` = min(open jobs, `MAX_CONSTRUCTORS`), `keep = 1` while any open job else 0.
    `outposts` = jobs grouped by nearest outpost (`outpost_mining.nearest_outpost_id` or
    `founded_outposts()` distance).
  - scout: `read_requests()` non-empty or unscanned POIs/unsurveyed sites (lifted from
    `SurveyJob._known_candidates` into module functions in `survey_requests.py`, host-free); `band = NEED`
    for requests, `STOCK` for known candidates; `wanted = 1`, `keep = 1` until nothing is left, then 0.
- `publish(curr_tick, reads=None)`: `archive.set(ROLE_DEMAND_KEY, compute(...))`. `read() -> dict`.
- Orchestrator: `publish_role_demand_if_due()` in `between_steps`, gate `ROLE_DEMAND_TICK_INTERVAL = 600`
  with the `last_tick` pattern; one `PlanReads(now_tick())` per pass.
- Tests: `tests/test_role_demand.py` with stubbed deficits/jobs; archive_ipc gets the key.

### 2. Role slots (`fleet.role_claims`)

- In `role_demand.py` (same module, same cadence reader): `ROLE_CLAIMS_KEY = "fleet.role_claims"`,
  `claim_slot(role, name, tick, wanted) -> str | None`: tries `target_key = f"{role}:{i}"` for `i <
  wanted` through `try_claim(ROLE_CLAIMS_KEY, target_key, name, owner_of=lambda c: c.get("vehicle"),
  record={"vehicle": name, "role": role, "tick": tick}, tick, CLAIM_STALE_TICKS, notes)`; returns the won key.
  `refresh_slot(key, name, tick)`, `release_slot(key, name)` (transaction, pop when owned).
- Per-outpost keys (`role:outpost:i`) are not needed yet: Stage 3 adds them for miners.
- `PioneerController` keeps `self.role_slot` (key or None); the role Job refreshes it from `prepare()` every
  `ROLE_SLOT_REFRESH_TICKS` (3000). Not persisted: a restart re-claims through `next_job`.

### 3. `lib/pioneer_refit.py` (new): `PioneerRefitMixin`

Mixed into `PioneerController` after `LoadoutFittingMixin`. Constants: `REFIT_IDLE_TICKS = 3000`,
`REFIT_COOLDOWN_TICKS = 12000`, `SERVICE_PAD_M = 2.0`, `FOOTPRINT_M = 20.0`.

- `in_service_area(pos, origin)` pure, rectangle from probe 1.
- `refit(role) -> bool`:
  1. `spec, reason = build_spec(role, catalogue)`; `None` → log, return False.
  2. Service point: `host.set_base(nearest founded outpost by distance)` when the current base is farther than
     `FOOTPRINT_M`, `host.return_to_base()` while not `in_service_area(host.get_position(),
     host.home_outpost.coords())`; `recharge_at_station(target_level=1.0)` (`_ensure_full_charge_for_sale`).
  3. Diff: current `modules()` ids vs `spec["modules"]` as multisets; a slot whose module id is in the spec and
     still unmatched stays (match best tier first; the Nav Module always stays). Surplus slots: extract the
     per-slot loop of `vehicle_recall._strip_and_sell_parts` into a module function
     `vehicle_recall.sell_slot(vehicle, slot, shop, log) -> str | None` (bays uninstalled and sold, module
     unmounted and sold, returns the failure text) and call it per surplus slot; a `not_at_service_point`
     failure goes back to step 2 once, then aborts (role unchanged, return False).
  4. Enqueue the coordinator job: `update_commission` appends `{"id": f"refit_{host.name}_{tick}", "kind":
     "pioneer", "role": role, "state": "fitting", "new_id": host.name, "home_base": host.home_base, "spec":
     spec}` to `jobs` and sets `lineage[host.name] = {"role": role, "job": id, "spec": spec, "home_base":
     host.home_base, "fitted": False, "missing": {}}`. The coordinator's `"fitting"` branch then buys and
     finishes unchanged; `_advance` needs one guard: a job whose `state` starts at `"fitting"` skips the
     `queued`/`buying`/`deploying` branches (it already does, states are matched by name).
  5. `fit_loadout(spec, f"Refit to {role}", lambda m: self._report_missing(host.name, m))`, then
     `update_commission` sets `fitted: True, missing: {}` (same as `fit_commissioned_loadout`).
  6. `host.role = role`; rename through a module function `fleet_commission.rename_vehicle(vehicle_id,
     outpost_id, role, log)` extracted from `_name_new` (the coordinator calls it too); `name_taken` keeps the
     old name. `publish_telemetry("REFIT", role)`. `self.refit_tick = tick`. Return True.
- The FLEET card's Commission tab already lists `jobs`; a refit job shows as `fitting` with its label.

### 4. Job switch: `PioneerController.next_job(job)`

- `pioneer.py`: `job_for_role(role) -> Job | None` factory extracted from `run()`'s dispatch (`SurveyJob`
  only when `can_run()`); `run()` uses it.
- `next_job(job)`:
  1. Track idleness: `self.idle_since` set when `fleet_status.is_idle(host.state)` first holds after a
     non-idle cycle, cleared otherwise. Return `job` unless `tick - idle_since >= REFIT_IDLE_TICKS`, `tick -
     refit_tick >= REFIT_COOLDOWN_TICKS`, cargo empty, `host.mission is None`, not recalled/held.
  2. `demand = role_demand.read()`; `current = demand["roles"].get(host.role, {})`. Candidates: roles with
     `band > current band` (or current band 0), `wanted > claimed` (count of fresh claims in
     `fleet.role_claims` for that role), sorted band-desc. Skip the current role while its claimed count ≤
     `keep` (the floor applies to leaving, not to joining).
  3. For the best candidate: `key = claim_slot(role, name, tick, wanted)`; None → next candidate.
     `release_slot(self.role_slot)`; `refit(role)`; on False release the new slot, keep `job`, set
     `refit_tick` (cooldown). On True: `self.role_slot = key`, return `job_for_role(role)`; `run_job_loop`
     calls the old `on_leave()`.
  4. Fallback: when the current role has `band 0` and `wanted 0` (no work) and the hauler role is not
     at `wanted 0`, hauler counts as a candidate even at equal band. A hauler with nothing to do stays a hauler
     (operator decision: refit, never sell).
- `run()` claims a slot for the detected role at start (`claim_slot` with `wanted` from the archive, or `i =
  0..MAX_ROLE_SLOTS` when no record yet) so a restart does not look idle-and-slotless.

### 5. Docs and tests

- cheatsheet: vehicles_drones.md new §2f-1 "Dynamic roles" (refit, switch, constants), archive_ipc.md
  (`fleet.role_demand`, `fleet.role_claims`), lib_map.md rows for `role_demand.py`, `pioneer_refit.py`,
  pull_logistics.md §2i pointer, DESIGN_HISTORY.md entry (why refit over sell, why the coordinator job
  is reused). AI_CHEATSHEET.md index lines.
- Tests: `test_role_demand.py` (compute, claim_slot contention: two names, one slot), `test_pioneer_refit.py`
  (`in_service_area` corners, module diff keeps Nav and matching tiers, `sell_slot` order: bays before
  holder), `test_pioneer_next_job.py` (idle timer, cooldown, keep floor, fallback to hauler).
- Checks: `python -m unittest discover -s tests`, ruff, `resolve-preview` + pyright, `cavecrew-reviewer`.
- Headless (`docs/headless/`): an idle constructor refits to hauler within `REFIT_IDLE_TICKS`; two idle
  Pioneers never take one slot; row in `ab_results.md`.

## Not in this session

Autoplay retire-rule removal, `MAX_PIONEER_HAULERS`, FLEET work-queue column (Stage 2); miner demand and
per-outpost slots (Stage 3); the `step_profile.py` pass of `pull_destinations()` (Stage 1a open point, still
open).
