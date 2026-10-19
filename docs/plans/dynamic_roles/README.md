# Plan: dynamic Pioneer roles

Status: **Stage 1b done** 2026-10-19 (branch `agent/hauler-dispersal`, see Handoff); dispersal gate open (below). Companion: [mission_pool.md](mission_pool.md) (deferred per-entry
pool). Builds on the seam of the [mixin refactor](../mixin_refactor/README.md): `Mission.prio`/`Mission.source`,
`Job.pick()` as the single work intake, `FleetUnitMixin.next_job()`.

## Goal

Fixed roles become superfluous. Haulers float (no HOME_BASE); an idle Pioneer refits itself to the role with
the highest open demand; idle scouts and miners refit instead of being sold. Later the same for drones.
Autoplay is optional, so every decision lives in `scripts/`: the vehicle decides, the control-panel
orchestrator publishes the demand index. Autoplay keeps proposing new Pioneers (`fleet:pioneer:<role>:+`) and
loses its retire rules.

## Facts the design rests on

- Role is set once: `pioneer.py detect_role` (constructor/sonar/drill mounted, else hauler), `run()` dispatches
  one Job to `run_job_loop`. `next_job()` (fleet_unit.py) exists with no override; `park_update` already
  rebuilds the ParkRequester when `host.role` changes.
- Module service: [pioneer.md](../../components/pioneer.md) `.mount(slot, item)` / `.unmount(slot)` work when
  parked in the service area (~2 m) of the home base **or any operational founded outpost**. A holder/rack must
  have its bays emptied (`.uninstall`) before `unmount`. `vehicle_recall._strip_and_sell_parts` is the
  unmount-and-sell precedent (one free Inventory slot, 100 % refund, batteries charged first).
  `pioneer_commission.fit_loadout(spec, label, on_missing)` mounts a spec until met; `build_spec(role,
  catalogue)` picks tiers; `FleetCommissionCoordinator._buy_missing` buys what `lineage[name].missing` reports.
- Home coupling: `vehicle.py` caches `home_outpost`, `home_charging_station`, `assigned_slot_coords`/
  `home_coords` at init from HOME_BASE. `PullJob` plans only home deficits, claims pickups with dest=home,
  delivers through `return_to_base()`; `pull_plan.best_pull_route` scores routes to home coords. The drone
  `drone_haul_plan.haul_destinations` is the floating precedent.
- No per-outpost throughput statistic exists; `logistics.pickups` entries are deleted on release.
- Demand per role already has a function: hauler `logistics_requests.outpost_tier_deficits`, constructor the
  open blueprint list minus `construction_plan.held_kinds`, scout `survey_requests.read_requests` +
  `SurveyJob._known_candidates`, miner `VehicleMiningMixin.home_ore_demand` (a method, Stage 3 turns it into
  a module function).
- Bands: `lib/priority.py` (`band()`, rule 1 lexicographic,
  [production_logistics.md §2a-p](../../cheatsheet/production_logistics.md)).
- Archive cap 2,048 entries ([dev_workflow.md](../../cheatsheet/dev_workflow.md)): every new key below is one dict.

## Design

### Foundation (code lands in Stage 2's session)

1. **Role demand index** `fleet.role_demand = {role: {band, wanted, keep, outposts: {id: band}}, tick}`: the
   mission pool at role granularity. New `lib/role_demand.py` with `compute(tick)` and `publish(tick)`, called
   from the orchestrator's `between_steps()` on its own cadence constant (≥ 600 ticks; share `PlanReads`).
   hauler: `outpost_tier_deficits` over founded outposts. constructor: open blueprints minus held kinds,
   `keep`=1 while any exist. scout: survey requests + unscanned POI count, `keep`=1 until the survey is
   complete. miner (Stage 3): ore NEED per outpost, `keep` per smelting outpost.
2. **Role slots** `fleet.role_claims` through `fleet_claims_common.try_claim`, `target_key=f"{role}:{outpost|*}:{i}"`,
   `i < wanted`; `refresh_claim` while in the role; stale at `CLAIM_STALE_TICKS`. Keeps idle Pioneers from all
   refitting to the same role at once.
3. **Refit** new `lib/pioneer_refit.py` (`PioneerRefitMixin` over `LoadoutFittingMixin`), `refit(role)`:
   `at_service_area()` (distance to the outpost ≤ `SERVICE_AREA_M`, 2.0; measure point confirmed by the probe)
   else drive to the nearest founded outpost; `spec = build_spec(role, catalogue)`; diff `modules()` against
   it; for each surplus slot: charge, `uninstall` every bay, `unmount`, `shop.sell` at once (extract the
   per-slot loop of `_strip_and_sell_parts` into a module function `sell_slot(vehicle, slot, shop,
   keep_nav=True)` and reuse it); `fit_loadout(spec, f"Refit to {role}", on_missing)` with `on_missing` writing
   `lineage[name].missing` (and `fitted=False`) so the coordinator buys. Then `host.role = role`, lineage
   `role`, telemetry, and a rename to `commission_name(role, ...)` through the coordinator's rename helper
   (`computer.rename`; a refused duplicate keeps the old name). Scripts key on `.id`
   ([pioneer.md](../../components/pioneer.md) "Prefer `.id`"); confirm lineage and `fleet.status` are keyed by
   id, else re-key on rename.
4. **Job switch** `PioneerController.next_job(job)`: when the job has been idle `REFIT_IDLE_TICKS`, read
   `fleet.role_demand`; candidates are roles whose band is above the current role's (or the current band is
   0), minus roles at their `keep` floor; `try_claim` a slot; `refit(role)`; return `job_for_role(role)` (the
   dispatch of `run()` extracted into a factory). The old job's `on_leave()` releases its claims.
   `REFIT_COOLDOWN_TICKS` prevents flapping. Hauler is the fallback role when nothing has demand: refit, never
   sell (operator decision).

### Stage 1: floating haulers (needs no foundation)

- `VehicleController.set_base(outpost_id)` recomputes `home_outpost`, `home_charging_station`,
  `assigned_slot_coords`/`home_coords`. `home_base` stays the commission origin (lineage, `_wrong_home`).
  Telemetry gains `"base"`; the FLEET card (`vehicles_card.py`) shows it.
- `PullJob.pick`: destinations = founded outposts with deficits (mirror `haul_destinations`, shared
  `PlanReads`), ranked band-first (rule 1), then `best_pull_route(dest_outpost, origin_coords, ...)` scored from
  the vehicle's position (pull_plan.py loses its `host.home_*` reads). `claim_pickups(dest=dest_id)`,
  `pull_from_source(..., dest_id)`, `shop_source` for the destination. Delivery: `set_base(dest_id)`, then
  today's `return_to_base()`/`unload_cargo` path.
- Dispersal: `logistics.outpost_flow = {outpost_id: {sent, received, tick}}`, written by
  `PullJob._finish_pull_delivery` and the drone delivery in `drone_hauler.py` through `archive.transaction`.
  `PullJob.idle` on NO_DEMAND: target = argmax `(1 + sent) / (1 + idle haulers based there)` over founded
  outposts (idle haulers from `fleet.status`: role hauler, `fleet_status.is_idle`, `base`); ties go to the
  nearest; move only when the target's weight exceeds the current one × `DISPERSE_GAIN`; `set_base` +
  `return_to_base()`.
- Autoplay: the hauler rule (`build_providers.py`, `KEEP_PIONEER_HAULERS`, was `HOME_PIONEER_HAULERS`) counts fleet-wide; `idle_unit` drops
  the home filter for haulers; `building_plan.py` per-HOME_BASE counts exclude haulers. The
  `DESTINATION_OUTPOST_ID` warning in `pioneer.py run()` is reworded.
- Docs: [vehicles_drones.md §2f](../../cheatsheet/vehicles_drones.md),
  [production_logistics.md §2i](../../cheatsheet/production_logistics.md),
  [archive_ipc.md](../../cheatsheet/archive_ipc.md) (`logistics.outpost_flow`, `base` field),
  [DESIGN_HISTORY.md](../../DESIGN_HISTORY.md).

### Stage 2: constructor ↔ hauler, scouts refit

Foundation 1-4. Autoplay drops the scout retire rule and the hauler retire rule; a `MAX_PIONEER_HAULERS` sell
rule replaces them. The commission coordinator treats refit `missing` like a fresh commission. FLEET card shows
`fleet.role_demand` as the work queue (role, band, wanted/claimed).

### Stage 3: miners

`home_ore_demand` becomes `outpost_ore_demand(outpost)` (module function, reused by `MineJob`); a refit to
miner sets `set_base(outpost)` and a fresh `OutpostStockpile(base)`. Autoplay drops the miner retire rule; its
+1 rules stay the only source of new Pioneers. Tuning risk: when every miner leaves as a hauler, ore STOCK is
never reached. Knobs: the miner `keep` floor per smelting outpost and a slightly higher ore NEED level
([§2a-p](../../cheatsheet/production_logistics.md)). Measure headless before raising NEED.

Drones follow later: same `fleet.role_demand` roles, `DroneController.next_job` with the chassis-swap handshake
(`drone_upgrade.py`) as the refit.

## Sessions

One session per row, `/clear` between. Each ends with unittest, ruff, pyright green, `cavecrew-reviewer`
findings fixed, docs updated, commits on an `agent/<topic>` worktree, headless validation, and a handoff
note in this file. The operator merges before the next row.

| # | Session | Model | Why |
|---|---|---|---|
| 0 | This plan. | Fable | design |
| 1 | Stage 1a: `set_base`, floating `PullJob`/`pull_plan` destination, pickups claimed per destination, tests. | Opus orchestrator | mechanical, mapped above |
| 2 | Stage 1b: `logistics.outpost_flow`, dispersal, autoplay and card updates, docs, headless A/B. | Opus | mechanical |
| 3 | Foundation: live probe of `unmount`/`mount`/`rename` at a non-home founded outpost (service-area measure point, bay emptying), then `role_demand`, `role_claims`, `pioneer_refit`, `next_job`. | Fable for the probe and handoff; Opus for the edits | game-API uncertainty, cross-module design |
| 4 | Stage 2 wiring, autoplay rule removal, FLEET work queue. | Opus | mechanical |
| 5 | Stage 3 miners, headless A/B on ore STOCK. | Opus; Fable if the ore-demand extraction fights `OutpostStockpile` | moderate |

## Handoff

**Session 1 (Stage 1a), 2026-10-19, branch `agent/floating-haulers`.** Done: `VehicleController.set_base()`/`base_id`,
telemetry `base`; `pull_plan` takes `dest` + shared `PlanReads` (no `host.home_*` reads), `best_pull_route(...,
origin)` returns `(route, reachable, rank)`, `pull_destinations()` groups outposts by `top_band()`;
`PullJob.pick` plans each destination of the top band group, best `haul_rank` wins, claims with that dest,
`set_base(dest)`, mission `"dest"`; reload restores the base from `logistics_requests.pickup_dest()` or the
mission. Also done (review): the hauler's container split is anchored on `HOME_BASE` (`_haul_split_sites`), the
`DESTINATION_OUTPOST_ID` warning reworded. Docs: §2f, §2i, archive_ipc `base`, DESIGN_HISTORY §2f.
Headless smoke (save `mvdnuhjh_rbjww6`, 1 h, vs main): 0 errors; 33 deliveries vs 21; same TP. Floating
haulers now also carry pipe segments home → `outpost_1` while most flow goes `outpost_1` → home, both for
`site_supply`; main already shuttles `iron_ingot` `outpost_1` ↔ `outpost_2` the same way, so this is the
existing site-supply two-way pattern, now reachable for more pairs. Stage 1b's A/B should count it.
Open for 1b: dispersal, `logistics.outpost_flow`, autoplay hauler counts, FLEET card `base` column; recall
returns a hauler to its current base, not `HOME_BASE` (intended; selling works at any founded outpost).
`pull_destinations()` costs one source walk per destination of the top group: profile with
`devtools/perf/step_profile.py` once dispersal lands.

**Session 2 (Stage 1b), 2026-10-19, branch `agent/hauler-dispersal`.** Done: `lib/outpost_flow.py`
(`logistics.outpost_flow` `{id: {sent, received, tick}}`, half-life `FLOW_HALF_LIFE_TICKS`; `sent` per pickup
source, drill/pump to the nearest outpost, Shop buys to none; `received` per unload), recorded by `PullJob` and by
drone `HaulJob`/`DroneHaulerMixin.deliver()`. `PullJob._disperse()` on `NO_DEMAND`: weight `(1 + sent) / (2 + idle
haulers based there)`, `DISPERSE_GAIN` 1.25, `DISPERSE_COOLDOWN_TICKS` 3000, publishes the new base before
driving. FLEET card and `draw_assignment` show `base` else `home`. Autoplay: `HOME_PIONEER_HAULERS` renamed
`KEEP_PIONEER_HAULERS` (the rule already counted fleet-wide; the per-HOME_BASE counts were already miner-only);
`idle_unit` ignores `home` for haulers. Docs: §2f, §2i, archive_ipc, lib_map, autoplay.md, DESIGN_HISTORY.
Headless A/B ([ab_results.md](../../headless/ab_results.md) "Stage 1b"): 0 errors, 47 vs 44 deliveries, same TP,
**0 dispersal moves**: the three haulers never hit `NO_DEMAND`, only `SHORT` (816 times).
Decided (session 3, 2026-10-19): `SHORT` disperses and parks like `NO_DEMAND` (`PullJob.idle()`; `SHORT` is a
stock condition, not a reach one; DESIGN_HISTORY §2f). A/B rerun (ab_results.md "Rerun with `SHORT`"): 56
deliveries vs 47 / 44 main, 30 moves, 0 errors, same TP. Not done: the `step_profile.py` pass of
`pull_destinations()` (Stage 1a open point). Ready to merge.

## Verification

Headless first ([standins.md](../../headless/standins.md): `logistics` group real, the rest stood in; rows in
[ab_results.md](../../headless/ab_results.md)); live only for the game-API probes the harness cannot model.

- Stage 1: unittests for `best_pull_route(dest, origin)` and the dispersal weight under `tests/`. Headless A/B
  fixed-home vs floating: served-request latency, idle share, `logistics.outpost_flow` growth. Two haulers with
  different HOME_BASE both serve the highest-band deficit; the FLEET card shows `base`.
- Foundation/Stage 2: the live refit probe; then headless: an idle constructor refits to hauler within
  `REFIT_IDLE_TICKS`, lineage role and name update, autoplay `fleet_count` follows, no two idle Pioneers take
  one slot.
- Stage 3: headless A/B with miners free to leave: ore STOCK reached or not; tune `keep`/NEED from the rows.

## Open points

- Service-area measure point (outpost origin vs staging slot): probe in session 3.
- Whether `.unmount` refuses a holder with filled bays in code as it does in the UI: probe in session 3.
- Lineage and `fleet.status` keying (id vs name) before the rename lands.
