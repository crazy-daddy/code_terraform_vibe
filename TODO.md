# Code: Terraform — Planetary Terraforming Roadmap & Task Tracker

This document tracks our strategic progress from initial boot to full terraformation of Nocturna.

Finished items live in [TODO_done.md](TODO_done.md). When an item and all of its sub-items are checked off, move it there under the same section heading.

---

## 📌 Status Summary
- **Current Focus**: Autoplay
- **Selected Work from Inspirations (other ppls code)**: Capability discovery, stale-aware coordination, vehicle recovery, production planning, survey persistence, and dashboard telemetry are selected for implementation from `TODO_inspirations.md`.

---

## 🌱 Manual run on a new seed (operator, 2026-10-07)

Findings A-G from the operator's hand-played run with our scripts. Unlock data: [docs/gameknowledge/unlock_paths.md](docs/gameknowledge/unlock_paths.md).

- [ ] **D. Earth Orders: key unlocks first.** Done: `EARLY_UNLOCK_ORDER_IDS` rank first and the next key order per contractor is stocked ahead in idle Fabricator/Smelter time ([production_logistics.md](docs/cheatsheet/production_logistics.md) "Key unlock orders"). Next:
  - [ ] Validate live: one Depot kit and one Service Station kit get built after `helios_06` / `spire_10` (`lib/drone_kit_stock.py`) and the building planner proposes deploying them. Headless 2026-10-11: the Service Station kit is built, but `pioneer_11` can't unload it at home (home Warehouses full; `drain_port_inventory_first()` keeps `INVENTORY_FREE_SLOTS_KEEP` (4) Inventory slots free, `vehicle_cargo.py` "no local storage at destination has room"). A deployable kit belongs in Inventory: let kits (`must_stay_in_inventory()` items) use the kept slots. No planner proposal seen yet.
- [ ] **E. 2-3 scout Pioneers, then retire some.** Done: `early_buyer.SCOUTS = 3` from 100k TP ([production_logistics.md §2m](docs/cheatsheet/production_logistics.md)). Next:
  - [x] Scout count vs survey work: superseded by dynamic Pioneer roles (2026-10-20). `role_demand.scout_demand()` counts survey requests, unscanned POIs and unsurveyed sites; an idle scout above the `keep` floor refits ([fleet_lifecycle.md §2f-1](docs/cheatsheet/fleet_lifecycle.md)); the autoplay scout retire rule is gone.
  - [ ] Buyer timing: the live scouts behaved well, but the operator found the early buyer (`PIONEER_TP` = Pioneer Chassis unlock) not ideal.

Operator walkthrough of the saves (2026-10-08; saves in `internals/sample_saves/20261007_c5f9ebf/`). The operator's choices are a baseline, not rules ([save_database.md](docs/plans/save_database.md)):

- [ ] **K. Pillar choice by blocker.** Done as the atmosphere focus (`autoplay/lib/focus_plan.py` on `lib/game_phase.py`, [autoplay.md §11l](docs/cheatsheet/autoplay.md) "focus"): research wants by ETA, even growth after, swap proposals on the BUILD card. Open: validate the swap rows live and tune `SWAP_MARGIN` / `MIN_SWAP_SCORE` against the recorded runs' swaps (#443, #663, #707, #910, #1191).

## 🌱 Manual run 2026-10-18 (seed 270102838, commit 4c29716)

Findings from the operator's notes in `internals/sample_saves/20261018_4c29716/log.md` (note and why entries).

- [ ] **B. Nothing proposes deploying mining Pioneers.** Day 20: deployed by hand (#71). `build_providers.miner_wants()` now proposes a miner per outpost on `NEED` ore, cap 4 per outpost / 12 in all; idle miners refit or re-station instead of retiring (dynamic roles Stage 3) ([autoplay.md §11l](docs/cheatsheet/autoplay.md) "fleet").
  - [ ] Validate live: a `fleet:pioneer:miner:+:<outpost>` row appears on the BUILD card; approve commissions a miner stationed there.
- [ ] **C. Mining markers (`resource.*`) aren't set automatically.** Fix: markers dropped (planners, stationed miners and the STOCK floor gate run on NEED demand plus a latched buffer); plan: [resource_markers_removal.md](docs/plans/resource_markers_removal.md).
  - [ ] Validate live (plan "Verification"), then move this item and the plan to done.
- [ ] **D. Unpowered building never re-checked.** A cap placed before its power line was done stayed off; nothing starts it once the line finishes (#112). Fix in: `scripts_sync.py` holds an `offline` run refusal like `under_construction`; the panel's stray pass starts the idle script of a stray once it gets power ([dev_workflow.md §1d-2](docs/cheatsheet/dev_workflow.md)). Open: validate live (place a scripted building before its power line).

---

## 🧱 Mixin Refactor (2026-10-11)

Plan: [docs/plans/mixin_refactor/README.md](docs/plans/mixin_refactor/README.md). Abilities stay controller methods (one mixin per ability, downward dependencies), jobs become objects on one `run_job_loop()`, math and archive I/O become module functions.

- [ ] **Dynamic roles** (2026-10-19): [docs/plans/dynamic_roles/README.md](docs/plans/dynamic_roles/README.md). Floating haulers, local refits (idle Pioneer takes the role with the highest open band), autoplay loses its retire rules. One session per stage, `/clear` between.
  - [x] Stage 1a: `set_base`, floating `PullJob` destination (Opus).
  - [x] Stage 1b: `logistics.outpost_flow`, dispersal, autoplay/card/docs, headless A/B (Opus).
  - [ ] Foundation: refit probe done (worktree `role-foundation`, spec [foundation.md](docs/plans/dynamic_roles/foundation.md)); `fleet.role_demand`, `fleet.role_claims`, `pioneer_refit`, `next_job` (Opus edits).
  - [ ] Stage 2: constructor ↔ hauler, scouts refit, FLEET work queue (Opus).
  - [x] Stage 3: miners, ore STOCK A/B (worktree `role-stage3`, [stage3.md](docs/plans/dynamic_roles/stage3.md), [ab_results_roles.md](docs/headless/ab_results_roles.md)).
  - [ ] Mission pool index `fleet.missions` (spec [mission_pool.md](docs/plans/dynamic_roles/mission_pool.md), 2026-10-20): session A publisher + tests, session B card Queue view, tie-break, autoplay `why`; drones later.
  - [ ] `HOME_BASE` only where a role works for it (2026-10-21; after building planner phase 4). Builders move to `constructor_base()` at script start, haulers float, scouts drive to home ("good enough"); only miners still need `HOME_BASE` as their first base. Commission card and `queue_pioneer()` set it for miners only; `fleet.status` keeps the current base for every role and a reload restores it (as `_restore_base()` does for miners); `fleet_commission._wrong_home` matches without it if possible. Deployed entry scripts carry the constant: plan the template change.
  - [ ] "Naked" Pioneer commission (2026-10-21): commission a Pioneer without a role; on its first start it takes the top `role_demand.switch_candidates()` role at once (no `REFIT_IDLE_TICKS` wait, no keep-floor check) and fits that role's parts through the refit path. Needs an explicit marker (a commission job or lineage flag), since no role module already means hauler. Autoplay then commissions "a Pioneer" and the role is picked at launch, not at queue time.

---

## 🗂️ Dev Tooling: Tiered `scripts/` Migration (2026-09-22)

Repo moved to a dev root (`C:\Users\<user>\Code_Terraform`) separate from the live save folder, with source of truth reorganized under `scripts/<tier>/<category>/` and synced in via `devtools/scripts_sync.py`. See [`docs/cheatsheet/dev_workflow.md` §9](docs/cheatsheet/dev_workflow.md) for the full scheme. Follow-ups from that migration, not yet done:

- [ ] **Simworker diff e1986ce, "Added (code)":** 3,728 lines in `devtools/game_update/.simworker-diff/63ecada_working.md` (`devtools/game_update/simworker_diff.py`), only skimmed by chunk heading (Battery Charger, status reports, typing module). Read the part a behaviour needs when it comes up.

---

## 🧪 Headless stand-ins (2026-10-14, [docs/headless/standins.md](docs/headless/standins.md))

Focused headless runs: one subsystem real, the rest stood in or off, inputs and outputs kept flowing, the step allowance held at the full base's value. Phase status and design notes per phase in the doc; A/B rows in [docs/headless/ab_results.md](docs/headless/ab_results.md).

## 🧹 Handler Unification (2026-10-03)

Plans (done): [handler_unification.md](docs/plans/done/handler_unification.md), [controller_unification.md](docs/plans/done/controller_unification.md); finished items are in [TODO_done.md](TODO_done.md). Find new candidates with `devtools/code_scan/clean_code_scan.py clones` (duplicates) and `features` (interpreter features, see below).

- [ ] Optional, deferred: `storage.drain_and_report`. Smelter aggregates one line per drain; Fabricator and Fuel Assembler log per item and call `consume_manual_order()`, so a shared loop saves little.

## 🧼 Code Quality (2026-10-22)

Plan: [docs/plans/code_quality.md](docs/plans/code_quality.md). Duplicated helpers plus the `size_scan.py` triage (9 long files, 139 complex functions). One session per step, `/clear` between.

- [ ] Helpers: open candidates (`_notify`, deploy/undeploy onto `building_ops`): [notify_building_ops.md](docs/plans/notify_building_ops.md).
- [ ] Helpers: next sweep: [helpers_sweep.md](docs/plans/helpers_sweep.md).
- [x] Size 1: bugs and rule breaks (`get_raw_material_reason` reread, duplicate `survey.unsupported_targets` and `TRANSIENT_UNDEPLOY_STATUSES`, copied `fabricator_unlocked_outputs`).
- [x] Size 2: `@method_block` pass on the log-inflated functions, rescan.
- [x] Size 3: shared helpers, one family per commit.
- [x] Size 4: file splits (`script_parking` first, then `storage`, `site_supply`, `bio`, `wildlife_planner`).
- [x] Size 5: long functions still over the limits.
- [x] Size 6: fill `size_scan_ignore.txt`, record the rescan counts in the plan.

## ⏱️ Script Load (2026-09-30, see `docs/cheatsheet/dev_workflow.md` §1d-1)

Above 50 running scripts the game splits 50,000 steps per tick evenly: allowance = `min(1000, 50000 / N)` per script (165 running → 303 steps, 3.3× slower than ≤ 50).

- [ ] **Planning-phase performance** ([docs/plans/performance_planning_2026-10.md](docs/plans/performance_planning_2026-10.md), 2026-10-22 headless profile of the dynamic-role planners): drone haul plan 222 ticks per pick near the step cap, fleet commission step 124 ticks per ~180, demand record never FRESH on a 7-outpost save. Vectors ranked there: shared tier-deficit snapshot, lazy commission log text, refresh round within the fresh window, bounded route permutations. Tool gaps closed 2026-10-22 (`tick_profile.py --preset founding`, `log_block_timing.py --headless`).
- [ ] **Import-cap margin**: a script's top-level imports run under one 10,000-step cap (`stepsLimit*10`, live game too). `infra_planner_automation`'s `outpost_plan` chain uses 9,637 (3.6 % headroom, 2026-10-22); `building_plan` 7,931. Add a check that fails as a chain nears the cap, then trim the `outpost_plan` chain (move work out of module bodies, lazy imports).
- [ ] **More atomic work**: the Harvester's `publish` phase (seed demand, status counts: pure part only) and the demand cascade on a prefetched snapshot.
- [ ] **Centralize Smelter/Fabricator demand** ([DESIGN_HISTORY §2a-q](docs/DESIGN_HISTORY.md)): the demand record (`production.demand`) published by the orchestrator, machines on a plan/feed split. In progress (2026-10-11): record, publisher and Smelter split; open: Fabricator split, readers, intermediate netting, headless A/B measurement.
- [ ] **Event-driven Automation** ([docs/plans/event_driven_automation.md](docs/plans/event_driven_automation.md)): wakes and fleet events reported where they happen instead of polled. Phase 1 (wakes at the cause, long backstop timers; bf20ec8) passed the headless A/B; live remeasure 2026-10-15 (7e5e168 run): wakes 341 → 123 per 11k ticks, 83-87% of fabricator/smelter re-checks fruitless. Backoff tuning is closed (fix A deployed, wake churn unchanged; fix B dropped). Backstops: dock-order wake follows the publish (`demand_publisher.wake_risen()`), fabricator/smelter/Supply Dock 3000, Thermal Cap parks until just before the vent turns active. Vehicle pausing (5057aaf) is folded in as 1.6; Phase 4 is superseded by the builder split (489df5f). 1.3, 1.6 and Phase 2 (`next_due`, idle fast pass) are done; the headless A/B (2026-10-23) did not show fewer parking ticks (nearly every pass is full). Open: live confirm of Phase 2, Phase 3.2 solar timer.
  - [ ] (2026-10-23) Deferred review minors from Phase 2 (`script_parking`, `logistics_requests`). Tests: `within=set()` wakes nothing (`None` = all); the `mode == "paused"` guard in `wake_role`/`resume_vehicle` skips a breaker entry; a second requester adding an already-held key, a stale-then-rewritten key, and a refused `machine_pack` plan do not wake; an idle fast pass leaves no debug block. Test cleanup: `_FakePower.reserve_is_low` reimplements the threshold compare; import `logistics_requests` directly instead of via `harness`. Code: a `_fresh_item_ids` helper shared with `active_requests()`; `request_decommission`'s `resume_vehicle` duplicates the wake from `_set_recalled`. Known: a fresh manager on an already-low grid wakes its Oil Generators once on the first supervise (`reserve_low` starts `False`).
- [ ] **Consider splitting `orchestrator_automation.py`** (grid supervision vs. storage sweeps/planning) if storage passes measurably delay grid supervision; costs one running script (~0.6% of everyone's allowance at N ≈ 165). (2026-10-11): Partly split; most building/upgrades outsourced - renamed both.
  - [ ] (2026-10-12) One orchestrator pass still takes ~2-6k ticks: site supply published a manual-order kit's haul home ~12k ticks after the build (a restart mid-pass reset the pass). Optimization pass on the pass length, and/or move site-supply publishing (`publish_site_requests()`) into its own Automation or let `consume_manual_order()` trigger an early publish.
- [ ] **Player decisions on script count**: retire solar trackers if steam covers power (19 scripts: 303 → 342 steps per tick, +13%); merge Control Room cards into tabs (8 cards); check whether all 20 steam turbines are needed. (2026-10-11): Steam turbines scale down - get "parked" - automatically. Solar Panels get retired on steam unlock (92W continuous vs ~20W due to night -> 4x reduction in scripts). Merging control room cards parly done (commission&drones&fleet -> 1 card)
- [ ] **Panels**: heavy cards re-read the fleet and archive every frame; refresh data every 10–20 frames (only helps the card itself).

---

## 🧭 Phase 1: Early Automation & Industrial Bootstrapping
- [x] Unlock **Mining & Rover Operations** (Thresholds: Pressure 0.10–0.20 kPa):
  - [x] Multi-Rover Fleet Coordination:
    - Atomic site reservation (`archive.transaction("rover.claims", ...)`) to prevent duplicate missions.
    - Automatic stale claim expiration (see `CLAIM_STALE_TICKS` in `docs/AI_CHEATSHEET.md`) and claim heartbeat renewal.
    - Staggered base staging slots (`(0,0)`, `(2.5,0)`, `(-2.5,0)`, etc.) preventing parking and charging pad collisions.
    - Deadlock / terrain stall detection and yielding logic.
    - **Capability-Aware Target Blacklisting & Dynamic Re-evaluation**:
      - Records scanner type, tier (`basic`/`wide`/`deep`), hardness limit (`1.0`/`3.0`/`4.0`), and research counts on failure (`wrong_scanner`, `too_hard`, `tier_too_low`, `research_required`).
      - Prevents infinite retry loops while automatically allowing upgraded rovers (Wide/Deep Sonar, Bio Scanners, or new tech) to re-evaluate and explore those contacts. Industrial/Heavy Drills are Pioneer-universal-slot items, not a Rover upgrade path — see the Pioneer mining role below.
      - Automatically clears entries from the archive once successfully scanned or mined.
    - [x] **Range-aware sonar scanning**: `survey_known_pois()` picks its next stop with `lib/scan_groups.py`. Candidates are the contacts plus every crossing of two contacts' reach circles. Each is pulled back toward the vehicle while its contacts stay in reach, so a single contact only drives up to reach. Score = contacts covered / (drive + per-stop cost + share of the added distance from home); best affordable stop first, replanned after every sweep. All covered contacts are claimed for the leg. The spiral fallback is unchanged.
      - [ ] Validate live: a Wide/Deep scout stops short of contacts and resolves a group with one sweep; no peer drives to a contact it claimed. Tune `SCAN_COST_M`/`HOME_WEIGHT` from the logs.
      - [ ] Score by value too: +20 per POI in a non-home biome, +1 otherwise.

- [ ] **Pressure Mk II in the early tail:** since build e1986ce a pack gives 25x output (was 5x). The headless search gives 2.97 h to 150k TP instead of 4.21 h with 8 `pressure_upgrade_pack_mk2` packs and 10 solar / 5 batteries from 1.2 kPa ([early_optimization.md](docs/autoplay/early_optimization.md#pressure-mk-ii-in-the-tail-checkpoint-h2-build-e1986ce-2026-10-08)). `computer.upgrade(item_id, machine)` applies a pack by script. The 1.2 kPa gate is now the bottleneck: test plans that reach it sooner.
  - [ ] **Night storage for the Mk II load after 150k TP.** pw10/5 with 6 Mk II generators draws about 258 W; a full night (10.08 h) needs about 2,600 Wh against 2,500 Wh of batteries, and the first sunset found only 1,767 Wh (71 %). The headless tail (2026-10-08) ran in daylight only; the next night the solar night guard shed all Mk II generators and the Bio-Loop. The phase after 150k (early_buyer idle) must add storage, or solar plus storage, for this load.
  - [ ] **Tail timing vs. time of day:** re-run `--suite mk2` with the tail starting near sunset. The 2.97 h result may depend on the tail falling in daylight.

- [ ] **Test past 150k TP: does one Storage Bin for rover ore pay off?** Rovers idle once the base Inventory is full of ore and ingots. A bin would let them keep unloading, so iron is banked before the next phase, at the cost of a base slot (and with it a little speed to 150k TP). Owner's guess: no. Untested. Compare the 150k-TP time and the iron on hand with and without a bin, then the time to the next phase gate, in the headless run from [early_optimization.md](docs/autoplay/early_optimization.md).

- [ ] Implement selected inspiration-derived coordination and observability improvements:
  - [ ] Add stale-aware Signal Bus heartbeats with direct-read fallbacks.
  - [ ] Expose power mode, budget, shedding, recovery, and subnet diagnostics through shared telemetry.
  - [ ] Add read-only Control Room telemetry for status, terraforming, production, fleet, and Earth order views.
    - [ ] Test a heavier UI card on e1986ce (report to the dev). The engine fix (cards whose loop is not a literal `while True:` now publish every iteration) never touched our panels, and the busy-call card wedge no longer matters for the calculator (it is an Automation with no card).
    - [ ] Add Terraform and Earth order cards.
    - [ ] Add shared readout helpers and stale-data presentation across all cards.

---

## 🌐 Phase 3: Multi-Outpost Coordination & Production Network

The save has grown past a single production base: multiple outposts are founded, several sit near ore deposits home doesn't have easy access to, and home itself is about to run more than one Smelter/Fabricator. This phase covers everything needed to coordinate production/logistics across that — split out of what used to be Phase 2's "Outpost Networks" scope because it has grown large enough to deserve its own phase. Full design for the mining-network half in `C:\Users\<user>\.claude\plans\agile-frolicking-flurry.md` (Multi-Outpost Mining Network + Multi-Smelter Leader Election section).

### Outpost Infrastructure & Freight
- [ ] Building planner: deploy structures from inventory via script, Outposts included (see CODE_GUIDES.md#scope).
  - Ship Computer deploy/undeploy/upgrade are documented (`docs/components/ship_computer.md`); the shared executor is `lib/building_ops.py`.
  - [ ] Infrastructure planner (`autoplay/`: extractors, one power grid, one pipe network per fluid). Plan and phase status: [docs/plans/autoplay_infra_planner.md](docs/plans/autoplay_infra_planner.md). Phases 0–6 done (geometry, occupancy, blueprint priority, power pass, fluid networks + outpost roles, extractors with urgency tiers and plan-ahead chunks, `--include-autoplay` sync flag); First run done headless (2026-10-11, the 2026-10-10 save, 0.6 game h): power survey 32,400 tiles in 445 s (400 with power, 7 probe jobs cancelled); power pass queued an 18-tile link to `water_pump_3`, Pioneers built 8 of 18 by the end; water pipe pass waits for stock (`liquid_pipe_segment 25/26`); drill extractors answer `locked`. Next: the same run in game, then relic cleanup (phase 5b).
    - [ ] Later, when outposts get deeper roles: compare fluid supply (t/h of the tapped sites) with what each outpost's machines draw, instead of only distance + tier (`supply_tiers`). Fine as is for now.
    - [ ] Power pass check: verify subnet topology after every remote build:
      - [ ] Confirm every line/bridge is complete and physically touches the intended service footprints.
      - [ ] Compare subnet generation, demand, conventional battery storage, and Lightning Rod reserve.
      - [ ] Test recovery after a split route and after a remote outpost brownout.
  - [ ] Outpost founding planner (`autoplay/`: needs now/later, site scoring from in-game data only, proposals as map markers approved by `OK` in the label, kit via cash manager, role designation). Plan and phase status: [docs/plans/outpost_founding_planner.md](docs/plans/outpost_founding_planner.md). Phases 1-4b code done; phase 4 ran live in the operator's 2026-10-07 run (proposals placed as markers, rejected by deleting them). Revision 3 phase 1 (2026-10-21) code done: second factory look-ahead need, `charging` role with Charging Stations before drones, geothermal scout requests. Revision 3 phase 2 code done: `reach_gain` and `future` score terms, `power` need on a discovered vent, drone takeover switch; replay: the second factory outpost leaves the first one's cluster unless a vent is known nearby (`WEIGHTS_EARLY` `reach_gain` 9, [planner_rev2_results.md](docs/plans/planner_rev2_results.md)), but only when outpost_1 has its Charging Station (the recorded run has none; then it stays west at every weight tried); from a scratch probe, not the replay tool. Next: live run of revision 3, then phase 5 (kit purchase, blueprint, built detection).
    - [ ] Make the revision 3 tuning reproducible: extend `devtools/simulation/planner_replay.py` to feed the look-ahead `future` fluids (`plan["future"]`) and the geothermal scout areas into the site ranking, and to rank a planner-driven second-factory founding (the planner's own designation and Charging Station carried forward), so the `reach_gain` result in [planner_rev2_results.md](docs/plans/planner_rev2_results.md) comes from the repo tools instead of a scratch probe.
    - [ ] Revision 2 (2026-10-17, branch `planner-rev2`): look-ahead needs by research ETA, full-and-busy factory rule, phase site weights, replay against both recorded runs ([planner_rev2_results.md](docs/plans/planner_rev2_results.md)). Next: live run of the new proposals (ask first), lead-time tuning, the first-factory site choice against the ore_outpost cost model.
    - [ ] Re-rank a found proposal when a survey lands in its area. Today sites re-rank only when the founding bundles change or after `RERANK_TICKS`, so a fresh survey leaves the marker's score, confidence and reasons stale for up to ~1 sim h (2026-10-18 run: `f-general` ranked at tick 83315 with confidence 0; `black_rim` iron surveyed at ~84058 inside its range, no re-rank). Trigger: a new surveyed site or biomass scan inside an open proposal's `survey_requests` area.
  - [ ] Building planner (`autoplay/`: deploy and retire machines inside outposts through one shared executor, `lib/building_ops.py`). Plan: [docs/plans/building_planner.md](docs/plans/building_planner.md); phases 1-3 done (executor, undeploy call sites, propose-only decider with BUILD card), draft providers and the atmosphere focus done 2026-10-17 (`build_providers.py`, `focus_plan.py`, [autoplay.md §11l](docs/cheatsheet/autoplay.md)), next phase 4 (kit sourcing, execution behind approval) and the capacity metrics per domain.
    - [ ] Undeploy must clear the machine's orders. Before `building_ops.undeploy()` reports success, drop the machine's entries: `clear_order(machine_id)` for a per-machine requester, and its `logistics.requests` / pickup reservations. Only `fleet_decommission` does this today (`clear_order(machine_id)`); `fleet_upgrade` drone swaps rely on `_prune()`. `building_ops.undeploy()`, `pillar_swap`, `early_buyer`, `harvester_machines` and cold-boot `solar.py` clean nothing up. A shared, type-level requester (`bio_caster`, `fuel_assembler`, `plant_terraformer`) can't be cleared when one machine goes, since a sibling may still need it. Those three already carry a heartbeat (`set_order(stale_ticks=ORDER_STALE_TICKS)`). A new shared requester needs one too, and a writer that parks must wake inside the window.
    - [ ] Validate live: Fabricator/Smelter Mk II/III packs (`lib/machine_pack_upgrade.py`, §2k-6): order book crafts the packs, `computer.upgrade()` applies them, `not_enough_power` refusals sit out; a Pioneer picks up the Oil Pump `"upgrade"` blueprint and fetches the pack from Inventory.
- [ ] **Slot planning per outpost.** Stock targets assume one slot per item (`BIN_STOCK_TARGET` / `WAREHOUSE_STOCK_TARGET`, 400 / 1800) and hope the outpost has enough slots. Eviction already stays inside planned or held slots (`storage.slot_room()`, [production_logistics.md](docs/cheatsheet/production_logistics.md) "Destinations"). Next: count the slots every request and stockpile plans per outpost, refuse or shrink what does not fit, and let the storage outposts' free slots decide where surplus goes.
- [ ] Configure autonomous Drone freight routes between Outpost storage bins and Base Inventory:
  - [ ] Validate live: heli engine detection, `refuel()` at a station with `oil_in` wired (and the `no_oil`
    warning without), `go_to_drill()` + `cargo.load()` at a drill, multi-round unload into a 50/100/200-unit
    Depot while `drain_freight()` empties it, drone + Pioneer pull hauler sharing one ore deficit without
    overshoot. Retune `HAUL_MIN_LOAD_UNITS` / `HAUL_TRIP_OVERHEAD_M` / `HELI_MIN_EMERGENCY_RESERVE_T` from
    observed trips. Measure the fixed minimal burn per `go_to*()` call (confirmed live: hovering is free, but every route call burns a little even for a 0 m leg) and add it as a per-leg term in `_route_fuel()` if it matters.
  - [ ] Give other buffer-style requesters a `min` (Seed Maker base stock vs forms needed for the next blend, Plant Terraformer's second batch).
  - [ ] Dynamic Warehouse slot allocation for life-form stashes: compare free Warehouse slots at the outpost against the forms competing for them (and ore/cargo needs) instead of the fixed `LIFEFORM_BUFFER_SLOTS`; flush only once that allocation is exhausted.
- [ ] **Fleet commissioning: launch new vehicles from a Control Room card** (step towards semi-auto play; `docs/cheatsheet/fleet_lifecycle.md` §2k-2). Phases A (Pioneers), B (drones) and C (parameters chosen in game) are done.
  - [ ] **Phase D: semi-auto.** Target count per role (`fleet.commission["targets"]`) + auto switch: the coordinator queues a job when the live count is below target; later demand-driven targets (pickup backlog age, unserved ore demand). Matching "−" = the retire flow (`fleet_decommission.request_decommission()`, §2k-4).
- [ ] **Cash manager: one budget owner for every Shop purchase** (`lib/cash.py`, CASH card `cash_panel.py`; see `docs/cheatsheet/production_logistics.md` §2l). Replaces the flat 100k reserves: reagents (Bio Lab, Pioneer Shop pulls) first down to 0, capital buys above a dynamic floor in operator-set priority with a savings goal (small buys may skip), no prespending of forecast income; income/burn measured from the balance history, Earth Order pipeline and per-ask ETAs on the card. Stub-tested only.
  - [ ] Potential improvement: score capital asks by payoff (e.g. Forage/h or throughput per credit) instead of the static priority list.
  - [ ] Early tier (`0_cold_boot/bio/bio_lab.py` `CREDIT_FLOOR`, `0_cold_boot/power/solar.py` buyer, `lib/early_buyer.py` buildings and Rovers) still use their own credit checks, outside the cash manager.
- [ ] **Priority ladder follow-ups** (one 0-999 priority from order to ore, [DESIGN_HISTORY §2a-p](docs/DESIGN_HISTORY.md), `lib/priority.py`):
  - [ ] **Measure the re-ranking live and headless.** Earth orders now rank above fleet upgrades and below autoplay construction; plan-ahead construction ranks below machine needs. On the mid-late checkpoint (`internals/sample_saves/`), run ~1 game hour before and after and compare the Commission tab ETA, plan-ahead blueprint age and the top order's crafted-units timeline. Add phase checkpoints as [headless_sim.md](docs/plans/done/headless/headless_sim.md) step 1 provides them.
  - [ ] **Tune the Smelter preempt preload.** A higher band preempts once it is worth one craft, then loads at most one prefill window; loading one unit at a time wastes production time in poll/sleep overhead. Tune `SMELTER_PREFILL_SECONDS` / `SMELTER_LOAD_CHUNK_SIZE` on the checkpoint (metric: ingots/h per Smelter, recipe switches/h).
  - [ ] **Refit `ROUTE_COST_PER_SOURCE` / `ROUTE_COST_PER_ITEM`** with `devtools/perf/step_profile.py`: the planners loop nine bands per item now (worst case every band present); limit the loops to the bands a pass's requests use if it binds.
  - [ ] **Per-requester request merge.** One owner per (outpost, item) stays (`skip_foreign`); merging several requesters' ladders would end the overwrite between `site_supply`, `site_evict`, `salt_reserve` and the Seed Maker's two writers.
  - [ ] **Fine prio for the feed classes and the drone miners.** Feed Maker classes (`wildlife.plan.feed_demand`) and `stock_urgency()` above STOCK could use the fine value (400-499) instead of a flat 1.0.
- [ ] **Chase down hardcoded demand outside `logistics.requests`**: stock wants hidden in constants or side channels at the supplier/consumer instead of a requester (example: `plant.seed_demand["priority"]`, the garden seed list the Seed Maker makes first). Move each onto the requester logic: e.g. the field_keeper requests garden seeds at buffer tier during its build phase while the seeds it is actively planting get need tier. Sweep `scripts/` for similar cases (stock targets read by one specific consumer, special-cased idle jobs like the former salt reserve).

### Multi-Outpost Production Network
Production demand and logistics across several Smelters, Fabricators and outposts (no hardcoded `"smelter_1"`/`"fabricator_1"`; mining vehicles serve outposts, not only home). Finished work: [TODO_done.md](TODO_done.md) Phase 3.

  - [ ] **Phase E — factory outposts: remote smelting + multi-site fabrication (tier `5_steampower`).** Goal: Fabricator throughput for orders needing 100s of crafted parts, limited by home building slots (reserved for Plant Terraformers, Feed Makers and actively worked Habitats) and Warehouse feeder time (each outpost's Warehouses add feeder capacity only if inputs are local). Tiers 1-4 stay home-only.
    - **Roles come from buildings, no outpost designation.** A Smelter makes a smelting site, a Fabricator a fab site, `resource.*` markers a mining site. Early: Smelters sit inside fab outposts (or home). Mid-late: smelt at mining outposts and haul ingots to fab outposts (2 feeder interactions per unit at the fab site instead of 3). Code must work for any combination.
    - **Code placement:** location-aware changes go into the existing `4_controlpanel` modules (no-op while every machine is at home); only genuinely new modules go into `5_steampower/lib`. Avoids tier-override copies of `production.py`/`smelter.py`/`fabricator.py` (see `docs/cheatsheet/dev_workflow.md` §9 "No duplicate files across tiers").
    - [ ] E3 follow-up: adapt the archive cleaner to `mining.ore_stock_targets`: prune entries that aren't a `RAW_ORE_ITEM_IDS` ore or hold a non-numeric/negative value.
    - [ ] Tar is held out of eviction (`EVICT_HOLD_ITEM_IDS`): once the Refiner is placed, its controller requests tar at its outpost and the hold goes.
- [ ] **Straggler stacks**: outpost Warehouses hold 1-7 unit slots of overproduced items (oil_tank_small, control_unit, cargo_pod_medium, turbine_rotor at outpost_5), each a material-locked slot. Find the overshoot source and consolidate or evict leftovers.
  - [ ] Validate live: outpost_3 bins (gas/liquid pipe, titanium_ingot 2) clear within ~2 storage passes after `EVICT_AFTER_TICKS`; Pioneer unloads log "Topped up"; `[storage] Consolidated` lines; no hauler churn on 1-3 unit urgent trips.
  - [ ] Seeded archive targets keep 2000 (`mining.ore_stock_targets`, `production.ingot_stock_targets`): lower them to 1800 by hand in saves seeded before this change, if wanted.
- [ ] **Ore and Smelter product in separate Warehouses** (2026-10-03): `storage_unload.best_unload_target()` keeps each ore away from its Smelter product (`SMELT_PARTNERS`, heat by `ORE_HEAT_ORDER`), splitting at most once per item, never by busy state; the Smelter drains output and recovered input storage-first, home included (§2c, §2a-0).
  - [ ] Measure the transfer time of a send into a machine input vs into Inventory/Warehouse (assumed ~0.25 s/unit, §2c) to confirm the Direct delivery saving (`storage_unload.push_to_targets()`).
  - [ ] Drain old mixed stacks first: `_holder_candidates()` takes from a holder that also holds the partner before a clean holder, so the leftover slot frees sooner.
  - [ ] Extend partners to Fabricator recipe inputs/outputs only if logs show Fabricator take/send blocking each other.

- [ ] **Storage Bins in the autoplay builder** (2026-10-07). `lib/storage_unload.py` routes into Storage Bins (`BinStore`, §2c), so an early outpost without a Warehouse can take Pioneer/drone unloads. The builder still plans only Warehouses (`autoplay/lib/outpost_needs.py` `per_warehouse`, `autoplay_roles.warehouse_slots()`).
  - [ ] Count deployed bins as storage slots (1 material each) and plan bins for an outpost's stock roles before Warehouses are researched or affordable.
  - [ ] Upgrade bins to Warehouses by storage-slot demand: when an outpost's roles need more material slots than its bins give (or its building cap is tight, 1 slot per building vs 5/15), deploy a Warehouse, drain the bins into it, and sell the bins (compare `lib/warehouse_upgrade.py` / `building_swap_upgrade.py`). Interim: `warehouse_upgrade.BinUpgrader` swaps bins for a Warehouse (same-material bins share a slot); retire it once this lands.
  - [ ] Validate live: a vehicle `output.connect()`/`send()` into a remote Storage Bin, and `take_item()` from one. Send done headless (2026-10-11, sample save 0237: Pioneers transferred titanium and rare_earth into remote `storage_bin_*`; Smelter `take_item()` from bins ok). A vehicle take from a bin did not come up in 2 h.

- [ ] **Idea (2026-10-13): ORDERS card switchable to other queues.** Buttons on the card pick the queue; +10 / -10 / Top / Reset act on the selected row. Same pattern as orders (`supply_dock.py` `PRIORITY_OVERRIDE_KEY`): one adapter per queue with `rows()`, `set_override(id, prio)` and stale-override cleanup, with the override applied where the queue's prio is computed. Haulers rank by band only (`haul_rank()`), so the fine value only breaks ties.
  - [ ] Construction blueprints: new override map `{blueprint_id: prio}` checked before `blueprint_prio()` (`production_cascade.py` `blueprint_required_ladders()`), dropped once the blueprint is no longer pending or paused. Don't reuse `construction.priority`: it is the autobuilder's run-order rank (0 urgent, `PLAN_AHEAD_PRIO` 1), read by builders (`construction_lots.py`) and `blueprint_prio()`, and it can't reach other bands. Operator-placed blueprints (not in `autoplay.planned`) stay `MANUAL` whatever it says.
  - [ ] Order book (`fabricator.orders`: fleet_upgrade, drone_upgrade, drone_kit_stock, bio_volcanic): requesters rewrite their entries every pass, so apply the override on read in `get_orders()`/`order_ladders()`, keyed by requester or (requester, item).
  - [ ] Fleet commission jobs: the queue runs head-first per kind (kits behind the head at `BACKLOG_PRIO`), so a prio override barely helps. Offer reorder only ("Top" moves the job to the head in `update_commission()`).
- [ ] **Revisit the ORDER band (operator, 2026-10-14).** ORDER (600, `lib/priority.py`) ranks every Earth order a Supply Dock holds above UPGRADE and NEED, so a cash-only order (e.g. Spire `spire_25`: ~23,000 raw silicon + 3,387 glass) starves NEED work such as `fertilizer_mk2` for the home Plant Terraformers. Split it into an order for research (a key unlock on the early-unlock list) and an order just for cash, and rank the cash one below NEED. Check every ORDER reader: dock planner fine score, `get_smelter_demands()`, site-supply dock wants (`dock_owed_prios()`), the Smelter raw dock hold (`SmelterController.dock_held()`), and ORDER_AHEAD.

---

## 🌡️ Atmosphere (the main save's last pillar)

- [ ] **Autoplay: atmosphere build-out strategy (heat / O2 / pressure to max).** Atmosphere is the long pole. The panel bars reach 100 % at the top phase (heat 360,000 "Springtime" = 22 °C, O2 380,000 ppt "Full Lungs", pressure 19,000 kPa "True Atmosphere"; decompiled sensor phase table). Main save 2026-10-04 (day 1758, many hand-built Mk III): heat 106k (+736/day), O2 85.7k (+530/day), pressure 4.3k (+31/day) → still ~345 / ~555 / ~470 game days (~57 / ~92 / ~78 game h, ~1.5× that in wall time at the observed ~0.65× sim speed). O2 is the bottleneck. Decide when and at which tier autoplay builds terraforming machines:
  - Mk III is cheap but needs many units ("spammy"). Every unit is one more running script, which competes with the script-heavy mid-late logistics (life forms for seeds, feed, drone freight; see Script Load). Build the Mk III fleet early, before that phase, rather than during it?
  - Mk IV needs a steady fuel-rod supply (`terraforming.Mk4RodFeed`, Phase 10). It uses fewer scripts, but costs logistics. Since build ca19829 a Mk IV makes 2.5× more than before: 12.5× a Mk III (heat 12.4×) for 5× its power and 0.1 Fuel Rod/day ([ca19829.md](ca19829.md) §3). Re-weigh Mk IV in this mix.
  - Measure per-unit rate per tier (heat/O2/pressure per game day) and script cost, then pick the mix that reaches all three maxima first under a script budget. Weight O2 highest. Retire each type at max (Phase 7 retire item).
  - Since build e1986ce a Pressure Mk II pack gives 25x output for 5x power (was 5x / 5x), so Mk II pressure costs 5x less per kPa than before. Re-weigh pressure Mk II in this mix.

---

## 🌱 Biosphere: next runs (Biomass, Plants, Wildlife)
Biomass, Plants and Wildlife are complete in the main save (2026-10-06). Full history and details: [TODO_done.md](TODO_done.md) Phases 4, 5 and 9; Wildlife plan [done/phase9_wildlife.md](docs/plans/done/phase9_wildlife.md). What is left matters only for new runs:

- **Biomass**
  - [ ] Cross-outpost drone ferrying of foreign-biome samples (deferred until a concrete need; template: a pull request at the processing outpost).
  - [ ] Biomass telemetry and alerts at 500 t / 2,000 t.
  - [ ] Water overflow Waste Processor at home (`lib/water_sink.py`), then check salt pickup keeps up.
  - [ ] After the essence chain retires: drain or repurpose its Liquid Tanks.
- **Plants**
  - [ ] Seed Maker sweep progress card (`seed_maker.status`).
  - [ ] Validate live: drill `connect()`/`take()` from a parked Pioneer, 1 stockpile unit = 1 t, pull + normal hauler sharing one ore deficit without overshoot.
  - [ ] Field phase 3: order and apply Grow Lamp / Sprinkler Mk packs (`computer.upgrade()` exists since e1986ce), then switch the fill automatically.
  - [ ] Salt budget: count Dispenser buffers in the home salt need tier.
  - [ ] Forage throughput panel line (`plant.automators[*].forage`); seeds in automator inputs vs Seed Maker demand (only if overproduction shows); Sprinkler water budget vs home supply.
  - [ ] Field layout v2: rarity-weighted expansion (`expand_layout()`, off by default).
  - [ ] Remote Terraformer Forage delivery by the drone hauler; Plant Terraformer card; Terraformer placement vs home slots.
  - [ ] New saves: leave cheap loose items on the Harvester field as paving instead of selling them.
  - [ ] Field yield: per-cell Fertilizer from idle Fabricator time after the Terraformer backlog.
- **Wildlife**
  - [ ] Parking and rehousing (housed vs parked, rehouse ordering, current target and demotion, target set size): not needed with 16 Habitats and the offline schedule; revisit for a run with fewer Habitat slots.
  - [ ] Missing fragments or feed recipes at tier start: verify the Earth-orders-first rule covers the Bio Orders that unlock them; Volcanic may lag (expected, self-heals).
  - [ ] Decide whether a feed-only form counts in the "partly drained site is finished" logic (`wanted_types`).
  - [ ] Wildlife Control Panel card (telemetry `wildlife.status` exists).
  - [ ] Optimizer: cap breeding by each feed recipe's life-form supply.
  - [ ] Bio Order focus: weigh `rewardUnlock` by live demand. `focus_local_order()` (`lib/bio_orders.py`) takes the first incomplete local order (local stock first), so orders sharing fragments fill in `exchange.orders()` order. Seen 2026-10-14: 3 Mk II Terraformers idle in phase 5 on `growth_accelerant`. `craft_growth_accelerant` unlocks via `bio_order_82` (Volcanic Grand Compendium), but `gw_jaw_fang`/`sd_tail_barb` went to `bio_order_81` first (credit + sulfur-gas unlock only). Rank an order up when its unlock feeds an open order (`fabricator.orders`, Terraformer `blocker`). Also: a requester ordering a locked recipe's item (Terraformer `growth_accelerant`) still posts haul deficits.
- **Seeds**
  - [ ] Seed quality: stage-A sweep cost per seed ([scoring_map_seeds.md](docs/plans/scoring_map_seeds.md)).
  - [ ] Supply-aware Crowncap/Grandbloom fill from in-game readings.

---

## ☢️ Phase 10: Nuclear power (in progress)

Chain: Weather Stations decode storm aftermaths → drones collect Raw Uranium → Fuel Assembler makes Fuel Rods → Reactor (5,000 W, cooling water). Nuclear Program is researched.

- [ ] **Power phases, sizing and reactor site** ([docs/plans/power_phase_reactor_site.md](docs/plans/power_phase_reactor_site.md)): `game_phase.power_phase()` (solar → steam → steam + oil → nuclear + oil; a phase opens on unlock, the old source retires only once the new one carries the grid), split `power` into `power_steam`/`power_oil`, reactor role = Reactor + Lead Casks + Fuel Assembler at one site (no nuclear hauler), sell the turbines in phase 4 (caps and condensers stay, oil is the fallback) and repurpose their outpost as the reactor host, size generators to measured demand bounded by the fluid supply.
  - [ ] Nuclear prep track in the tier 4+ decision engine: Weather Station in every biome and uranium stockpiling from Weather Program (TI 330,000), plated drone, Fuel Assembler + lead mining, Hot Freight Proof order for the Fuel Rod blueprint, all done before TI 650,000.
  - [ ] Cash manager consumer for the Reactor (750,000 cr), ranked ahead of tier upgrades and saved for before the gate.
  - [ ] Before the gate, add power as Oil Generators only (700 W per script), never more turbines or solar.
  - [ ] Size power to demand: 7-day peak of `power.daily_hist` plus designated draw, capped by `steam.plan` and a new `oil.plan` (persist the oil inflow EMA); retire surplus turbines and gas tanks.
  - [ ] Retire solar trackers early.
- [ ] Validate live (Fuel Assembler/Mk IV): `lead_cask.transfer_to()` cask to cask for uranium, Supply Dock `input.connect(cask)` + `take("fuel_rod")`, Mk IV `input.count()`/`take()` from a cask. Not triggered in 0.5 h headless (2026-10-06 state); needs a hot order, a misfiled cask or a Mk IV machine.
- [ ] *(Deferred, not this save)* **Lightning Rods as a power source**: ~250–500 W from 4 rods, only via a risky battery-at-0 "rod drain mode". Mechanics, yield estimate and plan in `docs/DESIGN_HISTORY.md` §1 "Lightning Rods Evaluated, Deferred".

## 🔄 Game build follow-ups (from the v0.1.29–v0.1.34 adoption notes)
Open items left when `3b1b03e.md`, `d12ec2f.md` and `58191a1.md` were deleted (full notes: `git show 906f906:<build>.md`), and `fe9a45c.md` (`git show 504d9cb:fe9a45c.md`).
- [ ] Throwaway save: edit a matched slot in game, then push it with `scripts_sync.py once`. Does the game now open a conflict bar instead of taking the push, and does the following `run` still start the file's version? Same for a Library and `apply-library` (expect `source_changed` while a conflict is open). If the push no longer wins, document it in dev_workflow.md §9.
- [ ] Decide: make `--apply-libs` the default.
- [ ] Live check (Electron engine since v0.1.34): the next large `--apply-libs` run applies every pending lib (`APPLY_CONFIRM_TIMEOUT_S`, dev_workflow.md §9).
- [ ] Decide whether `script_parking.py` should `pause`/`resume` machines without a breaker (keep breakers where load shedding needs them). Paused vehicles don't charge while docked.
- [ ] Live check `vehicle_energy.balance_dock()` once an outpost has a second Vehicle Charging Station.
- [ ] Live check `drone_upgrade._read_slots()` (`drone.modules()`) on the next in-place upgrade or chassis fitting.
- [ ] Optional: Control Room cards use the `progress_bar`/`vertical_bar` gradient presets (`"good-high"`, `"good-low"`, `"neutral"`) for battery charge, waste and progress.
- [ ] Optional: `RESEARCH_NAMES` in `scripts/4_controlpanel/lib/contact_inference.py` (and its comment) still uses the old research names. Cosmetic.
- [ ] Optional: panel list-comprehension workarounds can go back to `any()`/`next()` where that reads better.

## 🧪 Phase 7: Reliability, Diagnostics & Operations
- [ ] Standardize every long-running script:
  - [ ] Wrap the main loop with exception reporting and a bounded retry/backoff path.
  - [ ] Branch on result `.status`; never use localized `.message` text for control flow.
  - [ ] Treat `busy` as a retryable state and preserve payload fields such as `.moved`, `.sites`, and `.info`.
- [ ] Add shared telemetry for machine state, queue depth, battery/energy, storage pressure, and last successful action.
- [ ] Use Signal Bus queues for one-time work and broadcasts for latest-state coordination; document channel ownership.
- [ ] Add Data Archive schemas for claims, production reservations, discovered sites, recipe unlocks, and recovery state.
- [ ] Build a diagnostics checklist for every outpost:
  - [ ] Power subnet complete and funded.
  - [ ] Fluid routes connected and conflict-free.
  - [ ] Storage capacity available at every producer and consumer.
  - [ ] Required research, blueprint, module, and service range verified.
- [ ] **Stray dark machines: script parking warns, notifies, then switches on breakers nobody owns** (`ScriptParking._strays()`, `lib/script_parking.py`; see `docs/cheatsheet/dev_workflow.md` §1d-2). Machines built before their grid had power come up switched off, and their script never starts. Three stages by time since first seen: warn line, then `notify()` + Status panel alert, then breaker on + idle script started. Opt-out: `script.manual_off`. Stub-tested only.
  - [ ] `machine_activity` classifies registered machines as "retired", not "off", so they stay out of the spare/retire statistics (`activity_panel.py` needs a colour for it).
  - Retirements:
    - [ ] Essence chain: deconstruct its tanks and (maybe) pipes after the sale.
    - [ ] Bio chain per biome (Collector / Lab / Exchange / processor): retire once that biome has nothing left to catalog or deliver (not automated yet).
    - [ ] Habitat/Feed Maker Mk II packs (`habitat_upgrade_pack_mk2`, `feed_maker_pack_mk2`) stay in Inventory after the retire: not sellable, only droppable. Drop them once nothing can use them (recrafting is costly).
    - [ ] Oxygen Generators / Heaters / Pressure machines: retire each type once its atmosphere value is at maximum (not automated yet).
- [ ] Exercise failure scenarios: full Inventory, full output buffer, missing recipe, stale Rover claim, disconnected pipe, split power subnet, and stranded vehicle.
- [ ] Keep scripts and documentation aligned with the component/API guides after each major unlock.
- [ ] **Consolidate remaining per-entity archive keys into shared dicts** (archive key-count cap, see CODE_GUIDES.md#archive): remaining: `biomass_mixer.gate.<id>` (bounded by mixer count, do when next touching `biomass_mixer_gate.py`) and per-grid `power.shedded:`/`power.daily:`/`power.daily_hist:`/`power.night_wh:<anchor>` (4 keys per grid; deferred until 8+ separate grids — two `power.py` tiers, and global `power.shedded` must stay flat).
- [ ] **Archive cleaner: prune more per-entity dicts** (`lib/archive_cleaner.py`; `clean_building_entries()` already covers `script.parked`/`script.park_requests`/`script.park_holds`/`fluid_routing.tank_assignments` via `BUILDING_ID_KEYS`). Each prune skips when its live-id lookup comes back empty, so a failed query never wipes a dict.
  - [ ] Outpost-keyed dicts `logistics.requests` and `site_supply.stranded`: drop entries whose outpost is no longer in `outpost_network.outposts()` (outposts can be decommissioned). Needs an outpost-id set beside `get_live_building_ids()`.
  - [ ] `biomass_mixer.gate.<id>`: delete legacy per-entity keys whose mixer is no longer on the network (typeId `biomass_mixer`); superseded if the keys are consolidated into one dict (item above).
  - [ ] `fleet.decommission`: prune entries for vehicles/drones gone from the fleet, like `clean_missions()`, but keep entries whose `state` is still needed by the coordinator (check `fleet_decommission` before dropping any).
  - [ ] Test file for `ArchiveCleaner` (none exists): dry-run vs live, empty-lookup skip, `get_component()` confirmation for machines the network listing omits.
- [ ] Sweep `lib/` files and add liberal `trace()`/`debug()` calls per CODE_GUIDES.md#logging (per-file levels via `console.log_levels` exist, `docs/AI_CHEATSHEET.md` §0a). Not yet done.
- [ ] **Fleet hardware upgrade background task** (`lib/fleet_upgrade.py` coordinator in the `builder_automation.py` Automation + `lib/drone_upgrade.py` drone side; see `docs/AI_CHEATSHEET.md` §2k). Code done, not yet exercised live:
  - [ ] **Apply building tier upgrade packs by script.** The API exists since e1986ce (`computer.upgrade()`; the UI command checks `locked`, `target_not_found`, `not_at_service_point`); only the Automation work is open:
    - Extend the `builder_automation.py` Automation to order packs through `fabricator.upgrade_orders` (one requester, count = machines below the tier minus packs in Inventory) and apply them. Rename it (e.g. `building_upgrade_automation.py`; scripts_sync role-matches by name, so update matching and docs together).
    - First set (Fabricator-crafted): Feed Maker Mk II (`feed_maker_pack_mk2`), Habitat Mk II (`habitat_upgrade_pack_mk2`; Wildlife already wakes `capped` Habitats on one in Inventory), Plant Terraformer Mk II (`plant_terraformer_upgrade_pack_mk2`).
    - Later: Grow Lamp / Sprinkler Mk II-III (Fabricator; each tier doubles power and Sprinkler water), Charging Station Mk II-III (Shop buy through the cash manager). Oxygen / Heater / Pressure stay manual (only Mk IV has a Fabricator recipe). Skip the Biomass Mixer (the essence chain retires).
    - Build it on `lib/building_swap_upgrade.py` `BuildingSwapUpgrader` (gate, restart-safe state, status line, `_refused()`, `_buy()` for Shop-only packs). Add one overridable step after `buying` in `_advance_state()`: swap subclasses keep deploy+drain, a pack subclass applies the pack in place (same building id, nothing to drain, undeploy or sell). For Fabricator-crafted packs, `buying` becomes "ordered": `set_upgrade_order(REQUESTER, {pack: n})` until the pack is in Inventory, then clear it, like `fleet_upgrade._advance_depot()`.
  - [ ] Validate live: electric → heli. Done in code: drone_service `oil_in` routing after `research_heli_drones`, the Drones tab "-> heli" button (in-place swap at the next Depot unload) and the "heli on unlock" switch (new commissions and chassis swaps), all gated on `heli_ready()` ([vehicles_drones.md](docs/cheatsheet/vehicles_drones.md) "In-place module upkeep"). Check: whether a new Oil Tank starts empty (a converted drone then needs a rescue to its first refuel), stations without a pipe route blacklist instead of looping, the returned electric thrusters reach a Warehouse.
  - [ ] Long term: stop reading the save file in `scripts_sync.py` (tier gating via `read_save_state()`, and now the `fleet.upgrade` lineage handoff) — reading the save is a workaround, not a game API. Revisit with in-game signals once the game offers more.
  - [ ] Blocked in the current game version: attach scripts in-game via `run_control.apply_variant(machine_id, variant_id)` to shared variants. Scripts cannot create variants, and a variant saved from `drone_small` is not compatible with `drone_large` (per UI), so the operator would have to save one variant per machine type by hand. Revisit if the game adds variant creation or cross-size compatibility — then the attach step works without scripts_sync.
- [ ] **Long-term: interrupt/event-driven pattern instead of `sleep(X) -> rescan -> sleep(X)`.** The game has no interrupt/callback primitive for scripts; in practice a leader computes an expensive shared fact once and followers read a cached broadcast. Best candidate: `production.py`'s demand cascade, recomputed by every Rover/Pioneer/Smelter/Fabricator/Supply Dock each cycle (see Script Load, "Centralize Smelter/Fabricator demand"). Widen only with `profiling.report()` data.
