# Code: Terraform — Planetary Terraforming Roadmap & Task Tracker

This document tracks our strategic progress from initial boot to full terraformation of Nocturna.

Finished items live in [TODO_done.md](TODO_done.md). When an item and all of its sub-items are checked off, move it there under the same section heading.

---

## 📌 Status Summary
- **Sensors Online**: Pressure Sensor (Repaired), Oxygen Sensor (Calibrated), Thermometer (Active).
- **Core Generators**: Solar Tracker (`solar_1.py`), Battery buffer, Oxygen Generator (`o2gen_1.py`), Thermal Cap / Steam Turbine geothermal power (`lib/thermal_cap.py`, `lib/steam_turbine.py`).
- **Milestones Reached**: First Contact, Contracts unlocked, Auto Feeders research unlocked.
- **Current Focus**: Phase 8 — Planting (next: Phase 9 — Wildlife, tier `9_wildlife`, planned)
- **Operational Focus**: Demand-driven production (multi-smelter/multi-fabricator aware), inventory capacity protection, recipe-aware Rover/Pioneer missions, and the emerging multi-outpost mining network.
- **Selected Work from Inspirations (other ppls code)**: Capability discovery, stale-aware coordination, vehicle recovery, production planning, survey persistence, and dashboard telemetry are selected for implementation from `TODO_inspirations.md`.

---

## 🗂️ Dev Tooling: Tiered `scripts/` Migration (2026-09-22)

Repo moved to a dev root (`C:\Users\Adrian\Code_Terraform`) separate from the live save folder, with source of truth reorganized under `scripts/<tier>/<category>/` and synced in via `devtools/scripts_sync.py`. See [`docs/cheatsheet/dev_workflow.md` §9](docs/cheatsheet/dev_workflow.md#-9-dev-workflow-tiered-scripts--devtoolsscripts_syncpy) for the full scheme. Follow-ups from that migration, not yet done:

- [ ] **`weather_station`** had no non-empty instance to seed a canonical script from — still needs one written at whatever tier it belongs.
- [x] **`7_miningdrills` tier (2026-09-23)** — gated on the first deployed Mining Drill of any variant via the new OR-key `"buildings_any"` (`criteria_met()` in `devtools/scripts_sync.py`). Telemetry controller written (`7_miningdrills/lib/mining_drill.py`, thin `mining/mining_drill{,_industrial,_heavy}.py`; publishes `drill.status`, warns on full/stalled/near-full — see `docs/AI_CHEATSHEET.md` §1j). Not yet live-verified; confirm 1 stockpile unit = 1 t for the time-to-full estimate.
- [ ] **Extend `.criteria` beyond `tech`/`outpost_count`** if a future tier needs a Terraform-Progress-style numeric threshold — no plain "total TP" field was found in the save state on a quick pass this session; would need another look at `state.planet` or elsewhere in the save schema.
- [ ] **Adopt `inspirations/vakermit`'s `build_docs.py` workflow** *(partly covered 2026-09-24: `devtools/split_docs_manual.py` now regenerates `docs/` from an in-game DOCS Manual export — the remaining gain would be skipping the manual export step)* (extracts `docs/` straight from the game's own binary, keyed by content not byte offsets) as a maintenance utility for refreshing `docs/` after game updates. Deferred this session since `docs/` isn't currently known to be stale and this is a separate side quest from the scripts/ restructuring. See `inspirations/vakermit/tools/build_docs.py`, `jsparse.py`, `pe.py` for the reference implementation.
- [ ] **External "apply library" command — expected in the next external-ide release.** The dev closed the ticket on 2026-09-25; the newest installed external-ide build (`%APPDATA%\io.codeterraform.game\external-ide\server\`) is from 2026-09-24, so the command is likely just not published yet. As of that build, "Apply & restart all" (`applyAllPending`) exists only as an in-game Libraries-view button: 28 probed `command.json` action names (`apply-libraries`, `library_apply_all`, `apply-all`, `restart-libraries`, ...) all return `invalid_action`, while a control `rename-library` gets past the action check. **After each game update:** check `server.cjs` for a new `codeTerraform.*` command in its allowed list (`w=[...]` next to `codeTerraform.renameLibrary`) and the README's "Debugging in the game" section. Once found, have `devtools/scripts_sync.py` send it after `sync_lib()` changes a lib (in place of `report_unapplied_libs()`'s manual-Apply message), then restart the dependents that were held back.

---

## ⏱️ Script Load (2026-09-30, see `docs/cheatsheet/dev_workflow.md` §1d-1)

Every running script slows every other by ~1.4% (165 running → 3.25× slower than one alone).

- [ ] **On-demand script scheduler** in the headless automation panel: machine scripts end themselves when their machine has nothing to do; the panel restarts them with `run_control.start()` (hysteresis against flapping). Candidates where the idle state is acceptable: solar at night (19), oil generators without a power deficit (7), Smelters/Fabricators without demand (18; recipe and loaded material survive), Supply Docks without an order (5), pumps on a dormant well (10). Estimated 25–35 fewer running scripts on average (325 → ~284 µs per step).
- [ ] **Centralize Smelter/Fabricator demand — only if their reaction time is still a problem**: computing `get_smelter_demands()` / site Fabricator targets once in the headless panel would speed up the 18 machines but move the work onto the panel that also runs grid supervision and dock planning (duplicated work costs only the duplicating scripts, §1d-1). Measure first.
- [ ] **Consider splitting the headless panel** (grid supervision vs. storage sweeps/planning) if storage passes measurably delay grid supervision; costs one running script (~1.4%).
- [ ] **Player decisions on script count**: retire solar trackers if steam covers power (19 scripts ≈ 26%); merge Control Room cards into tabs (8 cards); check whether all 20 steam turbines are needed.
- [ ] **Panels**: heavy cards re-read the fleet and archive every frame; refresh data every 10–20 frames (only helps the card itself).

---

## 🧭 Phase 1: Early Automation & Industrial Bootstrapping
- [x] Complete Earth contracts for starting credits:
  - `relay_hack.py` (Completed)
  - `xenogenetics.py` (Completed)
  - `corrupted_archive.py` (Completed)
  - `sealed_vault.py` (Maze DFS traversal & key transmitter)
  - `terminal_breach.py` (Mastermind iterative probe solver)
  - `data_tablet.py` (2D grid probe & reading-order string decoder)
  - **Version 2 (Signal Bus & Shared Library Pipeline)**:
  - **Relocated to the Coastal outpost (`outpost_1`) + Bio Luminizer** (`docs/AI_CHEATSHEET.md` §1e, §2g): `lib/bio.py`'s Collector/Lab/Exchange were home-Inventory-hardcoded (`.connect("inventory")`, `get_component("inventory")`) — broken the moment they sit at a Warehouse-only outpost. Now outpost-aware throughout via new `storage.warehouse_stock()`/`drain_port_to_storage()` and `bio.local_stock()`. Exchange's sweep now checks `matches_order()` against each candidate stack before an exact `take()`, required for a coastal order's exact `target_glow` requirement (previously took blindly, which only ever worked for plain-fragment orders). New `BioLuminizerController` (`bio_luminizer_1.py`) solves the 3-lamp mix (`_solve_3x3()`) to hit each order's `target_glow` and infuses/discards accordingly.
  - **Reagent resupply** (`docs/AI_CHEATSHEET.md` §2g): new `lib/outpost_reagents.py` (seed-once-editable per-reagent stock targets, default 100/100/60/20/10 for `alkaline_buffer`/`cryo_solvent`/`protein_marker`/`chelating_agent`/`enzyme_solution` respectively, dialed down for the pricier ones). `lib/vehicle_cargo.py`'s ore-hauler and reagent-hauler both reduce to the same demand-driven haul/unload/recharge mechanics, buying any shortfall at the Shop stack-by-stack when the source is home — the old role-specific `run_supply_run_loop()`/`run_reagent_delivery_loop()` wrappers were later removed in favor of every thin entrypoint script calling `run_haul_loop(dest_outpost_id)` directly (`dest_outpost_id` alone disambiguates the role). `pioneer_7.py` repurposed from its old ore-hauling role (outpost_1 no longer mines) to this.
  - [x] Live-verify in game once Bio Luminizer is deployed at `outpost_1`: relocated Lab/Exchange operate correctly with no Inventory; `set_lamps`/`glow`/`infuse` produce a sample `deliver()` actually accepts; the reagent transporter buys/hauls/tops up the coastal Warehouse.
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
    - [ ] **Range-aware sonar scanning**: `survey_known_pois()`/spiral survey currently `drive_to()` each unscanned POI and park directly on top of it before scanning, but Wide/Deep Sonar reach 180m/280m — no need to stand on the exact marker. Scan from the nearest point still within the mounted sonar's `range()` of the target (or, better, a point chosen to cover several nearby unscanned POIs in range at once) to cut travel distance/energy per survey pass. See `docs/components/sonar_module.md` for range/tier numbers.
      - Clustering approach from vakermit's `best_hub()` ([inspirations/vakermit/scripts/lib/scout.py](inspirations/vakermit/scripts/lib/scout.py)). Seed a group from every unscanned POI. Take all POIs within `sonar.range() * 0.85` (margin keeps members inside the sweep), move the centre to the group's centroid, and regroup until membership stops changing (max ~6 passes). Groups with identical membership collapse into one. If the centroid falls off the map, snap it to a member. Then drive to the centroid, run one `scan()`, and survey every member.
      - Rank groups by value, not by the nearest member: +20 per POI in a non-home biome, +1 otherwise, minus distance/100. Filter out groups that fail the there-and-back energy budget before ranking.
      - A single isolated POI is a group of one, so it falls back to the current behaviour. Keep the POI blacklist/retry handling per member, not per group.

- [ ] Implement selected inspiration-derived coordination and observability improvements:
  - [ ] Add stale-aware Signal Bus heartbeats with direct-read fallbacks.
  - [x] Add mission lifecycle records and reservation reasons covering material, consumer, order/recipe, shortfall, distance, and energy cost.
  - [ ] Expose power mode, budget, shedding, recovery, and subnet diagnostics through shared telemetry.
  - [ ] Add read-only Control Room telemetry for status, terraforming, production, fleet, and Earth order views.
    - [ ] **Engine fix incoming (next experimental build, not yet released):** dev confirmed+fixed the bug where a card whose main loop wasn't a literal `while True:` (e.g. `while running:`) and paced itself via the clock instead of `sleep()` never got a frame boundary and stayed blank; it will now publish at the end of every drawing loop iteration regardless of in-loop work duration. None of our panels (`status_panel.py`, `vehicles_panel.py`, `production_panel.py`, `automation_panel.py`) hit this — all already use literal `while True:`. Once the build ships, test whether it also resolves the *other* bug that motivated the status_panel/automation_panel split above (a busy per-tick call, e.g. `supply_dock.plan_dock_assignments()`, wedging the card's rendering while the script kept executing underneath) — that's a different failure mode from the one just fixed, so don't assume it's covered. If testing shows the wedge is gone, re-merging automation_panel back into status_panel becomes an option (not decided either way yet); report results back to the dev regardless. Don't change anything until then.
    - [ ] Add Terraform and Earth order cards.
    - [ ] Add shared readout helpers and stale-data presentation across all cards.
  - [x] Add compact Data Archive summaries for operator dashboards and scripts that cannot draw panels.

---

## 🏭 Phase 2: Logistics & Manufacturing Infrastructure
- [x] Build a complete recipe-aware manufacturing loop:
  - [ ] **Tar byproduct sink.** Lubricant/Plastic/Rubber crafts emit Tar that `drain_byproduct()` parks in home Warehouses with no consumer unlocked (4,349 Tar / 2+ Warehouse slots on 2026-09-24). Research Waste Processing, deploy a Waste Processor, and script it to destroy Tar above a stock cap (keep a buffer for future Coolant Loop / Fertilizer / Refiner use). Add it as a second surplus stream in `lib/waste_sink.py` (built for biomass-completion life forms).
- [ ] Harden home storage and transfer behavior:
  - [ ] Add separate bins for raw ores, refined materials, fabricated parts, and overflow.
  - [ ] Route Smelter input/output explicitly and handle `partial`, `busy`, `target_full`, and `slots_full` results.
- [x] **Simplified Power Guard for steam-backed grids** (`scripts/5_steampower/lib/power.py`, `docs/AI_CHEATSHEET.md` §1a-0). The old guard sheds every night on battery alone while Gas Tanks still hold steam for the Turbines. The new one treats battery + steam tanks as one reserve, records the net gain/loss of each per day, and sends one `notify()` a day when either pool lost >20% of its capacity. It sheds only when the combined reserve is under 10%. Stub-tested. Tier 5 `.criteria` now gates on built buildings (`thermal_cap` >= 2, `steam_turbine` >= 5) via the new `buildings` key in `scripts_sync.py`, so the module deploys once the steam grid exists. Also verify live that Gas Tanks appear in `grid.members`.
- [x] **Oil Pump + last-resort Oil Generator** (tier `5_steampower`). `lib/water_pump.py` generalized into `lib/fluid_pump.py` `FluidPumpController(pump, fluid_id)` for both Water and Oil Pumps (old name kept as a shim for already-filled save slots); the Oil Pump idles at throttle 0 while `well_active()` is False. New `5_steampower/lib/oil_generator.py` burns oil only when the combined reserve (same `power.reserve_fraction()` the tier-5 guard uses) is below 15% AND the grid runs a deficit without oil, covers only that deficit (shared across all Oil Generators), stops at 30%. Stub-tested. Open: live-verify that Oil Pumps/Oil Generators appear in `outpost.buildings()` and `grid.members`, and assign the first oil Liquid Tank in `fluid_routing.tank_assignments`. See `docs/AI_CHEATSHEET.md` §1c/§1c-1.

---

## 🌐 Phase 3: Multi-Outpost Coordination & Production Network

The save has grown past a single production base: multiple outposts are founded, several sit near ore deposits home doesn't have easy access to, and home itself is about to run more than one Smelter/Fabricator. This phase covers everything needed to coordinate production/logistics across that — split out of what used to be Phase 2's "Outpost Networks" scope because it has grown large enough to deserve its own phase. Full design for the mining-network half in `C:\Users\Adrian\.claude\plans\agile-frolicking-flurry.md` (Multi-Outpost Mining Network + Multi-Smelter Leader Election section).

### Outpost Infrastructure & Freight
- [ ] Building planner: deploy structures from inventory via script. Once built, it may place Outposts without per-instance human approval — decommissioning now exists, so founding is no longer permanent (see CLAUDE.md's Outpost Construction Safety Rule).
  - **Unblocked by v0.1.25** (`changelog.txt`): "Scripts can deploy, undeploy, decommission and rename hardware through the Ship Computer" — this is the missing script-side API this task has been waiting on. The `docs/` snapshot in this repo has not been refreshed for v0.1.25 yet (no `ship_computer`/deploy-related doc exists, and the new `json`/`heapq`/`traceback` builtins and custom-exception support from the same release aren't in `docs/models/python_builtins.md` either) — re-export DOCS from the in-game manual first, then read whatever new component/guide page covers the Ship Computer's deploy/undeploy/decommission/rename calls before writing the planner.
- [ ] Configure autonomous Drone freight routes between Outpost storage bins and Base Inventory:
  - [ ] Validate live: heli engine detection, `refuel()` at a station with `oil_in` wired (and the `no_oil`
    warning without), `go_to_drill()` + `cargo.load()` at a drill, multi-round unload into a 50/100/200-unit
    Depot while `drain_freight()` empties it, drone + Pioneer pull hauler sharing one ore deficit without
    overshoot. Retune `HAUL_MIN_LOAD_UNITS` / `HAUL_TRIP_OVERHEAD_M` / `HELI_MIN_EMERGENCY_RESERVE_T` from
    observed trips. Measure the fixed minimal burn per `go_to*()` call (confirmed live: hovering is free, but every route call burns a little even for a 0 m leg) and add it as a per-leg term in `_route_fuel()` if it matters.
  - [x] **Floating drone hauler, phase 2: Depot → Depot freight.** Outpost sources (`_outpost_sources()`), Depot
    staging via `depot.stage` (`lib/depot_stage.py`, fulfilled by `DroneDepotController.fulfil_stage()`), load in
    rounds (`_load_at_depot()`), stall cooldowns, hover instead of holding a bay. See `docs/cheatsheet/vehicles_drones.md`
    §2h/§2j. Stub-tested only.
    - [x] Validate live: drone_13 plans `outpost_6 -> outpost_home` for Seed Maker forms, lrg_3 logs `Staged ...
      for a hauler drone`, multi-round load at a 200-unit Depot, delivery at lrg_7; a stalled Depot goes on
      cooldown after 3 failures; `leave to drones` on + no hauler alive keeps outposts with pioneer_11.
  - [x] **Two-tier demand + fair share** (`logistics_requests`: request `min` = need tier, `fair_buffer_caps()`,
    `plan_take()`, `outpost_free_tiers()`), used by both pull hauler and drone hauler. Salt request 2000 buffer /
    30 need. See `docs/cheatsheet/production_logistics.md` §2i. Stub-tested only.
    - [ ] Validate live: pioneer_11 fetches salt with a 6-unit deficit (reachable minimum), home salt climbs
      towards 2000, and an outpost Terraformer's salt need is served from home stock above 30.
    - [ ] Give other buffer-style requesters a `min` (Seed Maker base stock vs forms needed for the next blend,
      Plant Terraformer's second batch).
  - [x] **Depot surplus flush** (`DroneDepotController.flush_surplus()`, `LIFEFORM_BUFFER_SLOTS = 2`).
    - [ ] Validate live: `input.flush()` result shape/status, lrg_3 flushes crystal_spores once drone_10 reports
      `WAITING_DEPOT_SPACE`, drone_10 then unloads its cave_fungus.
    - [ ] Dynamic Warehouse slot allocation for life-form stashes: compare free Warehouse slots at the outpost
      against the forms competing for them (and ore/cargo needs) instead of the fixed `LIFEFORM_BUFFER_SLOTS`;
      flush only once that allocation is exhausted.
  - [ ] Drones can self-locate unmapped drills: `go_to_drill(id)` needs no coordinates, so a hauler with a
    full tank could fly to an unlocated advertised drill and record `drone.position()` into `drill.positions`
    on arrival (`drill_sites.confirm_position()`). Needs an in-flight fuel abort in `fly_to_drill()` first.
- [ ] **Fleet commissioning: launch new vehicles from a Control Room card** (step towards semi-auto play). See `docs/cheatsheet/vehicles_drones.md` §2k-2.
  - [x] **Phase A: Pioneers.** COMMISSION card (`fleet_commission_panel.py`: role buttons, HOME_BASE picker, queue with cancel) → `lib/fleet_commission.py` in headless `automation_panel.py` buys chassis + best-unlocked preset parts (credit reserve shared with §2k-1), deploys at home, waits for scripts_sync to attach the script; the new Pioneer fits itself (`lib/pioneer_commission.py` `PioneerFittingMixin`, before `detect_role()`). Stub-tested only.
    - [ ] Validate live (ask first): create the `fleet_commission_panel` Custom Panel; one hauler end to end. Confirm `deploy("pioneer")` lands inside the home service area so `mount()` works right away, whether `mount()`/`install()` complete synchronously (fitting polls 5 s), whether Pioneers have a `deploy_limit`, and that scripts_sync fills the new `pioneer_N` slot. Retune `PIONEER_PRESETS` from real trips.
  - [x] **Phase B: drones.** Drone row on the card (hauler/miner + deploy-outpost picker limited to outposts with a Depot); `lib/drone_commission.py` picks the best craftable chassis + `LOADOUTS` modules, crafted via `fabricator.upgrade_orders` (requester `fleet_commission`), deployed at the picked outpost, fitted by `drone_upgrade.fit_loadout_if_new()` through a `fleet.upgrade` lineage entry with `job` and `from: None`. Stub-tested only.
    - [ ] Validate live (ask first): one hauler drone at a remote Depot end to end. Confirm the kit is built at home and stays in Inventory, `deploy(chassis, outpost)` docks the new drone at that Depot so `couple()` works, and scripts_sync fills `HOME_DEPOT`.
  - [x] **Phase C: parameters chosen in game.** Card's HOME_BASE picker → `fleet.commission.lineage[id].home_base`; drone outpost → lineage `params.HOME_DEPOT`. `devtools/scripts_sync.py` reads both from the save (`upgrade_fill_for()`/`commission_fill_for()`) and fills the slot without prompting; a Pioneer job only finishes once `fleet.status[id].home` matches. Stub-tested only.
  - [ ] **Phase D: semi-auto.** Target count per role (`fleet.commission["targets"]`) + auto switch: the coordinator queues a job when the live count is below target; later demand-driven targets (pickup backlog age, unserved ore demand). Matching "−" button = `recall_home_and_decommission()` below.
- [ ] **Cash manager: one budget owner for every Shop purchase** (`lib/cash.py`, CASH card `cash_panel.py`; see `docs/cheatsheet/production_logistics.md` §2l). Replaces the flat 100k reserves: reagents (Bio Lab, Pioneer Shop pulls) first down to 0, capital buys above a dynamic floor in operator-set priority with a savings goal (small buys may skip), no prespending of forecast income; income/burn measured from the balance history, Earth Order pipeline and per-ask ETAs on the card. Stub-tested only.
  - [ ] Validate live (ask first): create the `cash_panel` Custom Panel; check income/h and reagent burn/h against the credit history, and that a saving Crop Automator/Warehouse ask holds back lower-priority buys.
  - [ ] Potential improvement: score capital asks by payoff (e.g. Forage/h or throughput per credit) instead of the static priority list.
  - [ ] Early tiers (`1_early/bio/bio_lab.py` `CREDIT_FLOOR`, `1_early/power/solar.py` buyer) still use their own credit checks, outside the cash manager.
- [ ] **Every Pioneer hauler pulls to its HOME_BASE** (no `DESTINATION_OUTPOST_ID`, no push hauler, no floating Pioneers; see `docs/cheatsheet/vehicles_drones.md` §2f/§2g). Remote Bio Lab reagents are buyable pull requests, bought at the Shop by the hauler homed at the lab. Stub-tested only.
  - [ ] Validate live: scripts_sync re-homes the old ore hauler to home and the reagent hauler to its lab outpost (`note ... re-homed` lines); the home hauler keeps home ore stocked; the lab hauler buys reagents at home (`Bought Nx ...` debug) and the remote Lab loads them.
- [ ] **Pioneer `recall_home_and_decommission()`**: as drone haulers take over freight, retire Pioneers in an
  orderly way. Recall to `outpost_home`, unload cargo, uncouple modules to Inventory, sell modules and any
  leftover cargo, then undeploy/sell the chassis (Ship Computer deploy/undeploy API, v0.1.25). Operator-triggered
  (Control Panel switch or script command), never automatic. Release its reservations and archive entries
  (`vehicle.mission`, `vehicle.recall`, `fleet.status`, pickups/yield).
- [ ] **Semi-retire Pioneer haulers once drone freight is proven (target tier ~`8_`).** Drones carry far more
  per trip, so most Pioneer haulers become dead weight. Gate: drone hauler phases 1 + 2 validated live. Keep a
  small residual Pioneer fleet only for jobs drones can't serve: outposts without a Drone Depot, and Water Pump
  `salt_out` pickup (`DroneCargo.load()` -> `not_at_source`, see Phase 5). Plan: route selection prefers drones
  wherever a Depot exists at both ends; Pioneers keep only the uncovered jobs; retire the surplus via
  `recall_home_and_decommission()` above (operator-triggered, never automatic). Re-check the residual set
  whenever a Depot is built at an outpost.
  - [ ] Validate live: switch on, pull hauler skips drills + Depot outposts, drone haulers pick the ore up.
- [ ] Verify power subnet topology after every remote build:
  - [ ] Confirm every line/bridge is complete and physically touches the intended service footprints.
  - [ ] Compare subnet generation, demand, conventional battery storage, and Lightning Rod reserve.
  - [ ] Test recovery after a split route and after a remote outpost brownout.

### Multi-Outpost Production Network
Two correctness/scaling problems tackled together: every production-demand function used to hardcode the literal id `"smelter_1"`/`"fabricator_1"` (breaks the moment a second Smelter/Fabricator exists), and every mining vehicle funnels ore back to the single home base regardless of outposts founded near other ore deposits.

- [x] **Smelter starvation: demand never reached the Smelters (found live 2026-09-22: 400 drone_small + 200 drone_medium on manual order, both iron Smelters loading 1 ore per poll next to ~2000 iron ore).** `get_material_demands()` only saw ingot demand via each Fabricator's *currently selected* recipe (per-worker split, each share netted against full stock separately) and `_cascade_fabricator_output_demand()` stops at Smelter outputs. New `production.get_smelter_demands(cache)` follows the whole order tree (gross-then-net-once against stock + staged Fabricator stockpiles); `SmelterController.step()` now builds one `SourceCache` per step (targets memoized on it), never refines raw ore an active dock order still owes (`dock_remaining_requirements()`), and caps intake with a fair-share cap over available ore + peers' buffers (`smelter_recipe_peers()`) — fixes one Smelter grabbing a whole scarce silicon stock. `storage.take_item()` now tries only holders (Inventory first — never locks — then Warehouses by most stock, recently-`busy` ones last via `TAKE_BUSY_COOLDOWN_TICKS`), with an optional `report`. Temporary time-weighted diagnostics at `smelter.diag.<id>`. Verified via stub tests (order-tree demand 3480 vs old 0; 30 silicon split 10/10/10 across 3 Smelters; plentiful ore fills to prefill cap; dock-owed ore untouched; take_item ordering/busy fallback/report; bounded diag writes). See `docs/AI_CHEATSHEET.md` §2a-0-2, §2c, §4.
  - [ ] **Unify mining and smelting demand**: switch `get_raw_material_demands()`'s refined-demand expansion onto `get_smelter_demands()` so miners and Smelters agree on one number (left separate this pass to limit blast radius).
  - **Shelved (2026-09-22): Inventory as lock-free hot-item hub** — live data after the demand fix showed lock starvation (`busy_starving`) at only ~0–12% per Smelter, and Inventory is already often quite full in practice, so reserving ~20 slots isn't realistic. Original idea kept for reference: (Inventory has no Auto Feeder of its own, so it never locks — only the machine/Warehouse on the other side does). Constraint: only ~20 of Inventory's 32–60 slots can be reserved (stack size 10, or 20 with Bigger Stacks — `storage.inventory_stack_size()`); the rest must stay free for modules/portables/equipment. Idea: `rebalance_inventory_to_warehouses()` exempts in-demand intermediates (Smelter outputs + ores currently being smelted + active Fabricator inputs) within that slot budget, prioritized by demand; a single panel-side batch replenisher tops up the ore being smelted from Warehouses so Smelters stop contending for Warehouse locks.
  - [ ] **Direct Smelter → Fabricator handoff**: a Smelter's `output.connect()` accepts a machine input (`docs/types/storage_and_inventory.md` OutputSlot.connect), so ingots can go straight into a Fabricator's stockpile with no storage lock at all. **Never overfeed**: cap each send at that Fabricator's `craft_prefill_units() − stockpile` for its claimed recipe, only while that recipe is stable — a Fabricator keeps leftover stockpile across recipe changes and would otherwise have to eject it later. Fall back to Inventory on `target_wrong_material`/`target_unconfigured`/`buffer_full`/`busy`.
  - [ ] **Phase E — factory outposts: remote smelting + multi-site fabrication (tier `5_steampower`).** Goal: Fabricator throughput for orders needing 100s of crafted parts, limited by home building slots (reserved for Plant Terraformers, Feed Makers and actively worked Habitats) and Warehouse feeder time (each outpost's Warehouses add feeder capacity only if inputs are local). Tiers 1-4 stay home-only.
    - **Roles come from buildings, no outpost designation.** A Smelter makes a smelting site, a Fabricator a fab site, `resource.*` markers a mining site. Early: Smelters sit inside fab outposts (or home). Mid-late: smelt at mining outposts and haul ingots to fab outposts (2 feeder interactions per unit at the fab site instead of 3). Code must work for any combination.
    - **Code placement:** location-aware changes go into the existing `4_controlpanel` modules (no-op while every machine is at home); only genuinely new modules go into `5_steampower/lib`. Avoids tier-override copies of `production.py`/`smelter.py`/`fabricator.py` (see `docs/cheatsheet/dev_workflow.md` §9 "No duplicate files across tiers").
    - [x] **E0 Stub test harness** for `production.py`/`smelter.py`/`fabricator.py` (fake outposts, Warehouses, machines, archive) before the refactor: `production.py` is read by rovers, Pioneers, docks, Smelters and panels, and the repo has no test suite.
    - [x] **E1 Outpost-aware plumbing.** `SmelterController`/`FabricatorController` connect ports to a local Warehouse off-home (`smelter.py` `ensure_connections()`/`recover_input()`, `fabricator.py` `ensure_connection()`), pass `outpost=` to `take_item()`, read local stock. `discover_smelter_ids()`/`discover_fabricator_ids()` walk every outpost; peers and fair-share caps count only machines drawing from the same outpost's stock; demand splits (Fabricator `crafts_remaining`, Smelter demand share) stay network-wide while demand itself is. Harness: `tests/` (§10).
    - [x] **E2 Per-site recipe claims.** `smelter.recipe_claims`/`fabricator.recipe_claims` are keyed by recipe id network-wide, so a remote machine and a home machine on the same recipe block each other. Key by `(outpost, recipe)`; prune/migrate the old shape.
    - [x] **E3 Single ore stock target dict.** Replace `outposts.ore_stock_targets` (`{outpost: {ore: n}}`) with one global `{ore: amount}` under `mining.ore_stock_targets`, each ore seeded 2000 on first lookup. Readers: `vehicle_mining.py` (stationed miners), `production.get_raw_material_demands()` (home floor). Archive cleaner drops the old key. Cheatsheet in the same change.
      - [ ] Adapt the archive cleaner to `mining.ore_stock_targets`: prune entries that aren't a `RAW_ORE_ITEM_IDS` ore or hold a non-numeric/negative value, so a bad Notebook edit or a typo'd ore id doesn't linger. (Purging the retired `outposts.ore_stock_targets` key is already in `RETIRED_KEY_PREFIXES`.)
    - [x] **E4 Site supply requests** (new `5_steampower/lib` module). A smelting site publishes `logistics.requests` for ores it has an unlocked Smelter recipe for: buffer tier = that ore's stock target, need tier = its ingot shortfall. A fab site's ingot deficit D (its trees' need, net of local ingots, local smeltable ore 1:1, and in-flight ingots *and* ore) is split: ingot request for min(D, free ingots elsewhere), ore request for the rest. Preference: local ingots > local ore > remote ingots > remote ore. No hysteresis needed since in-flight counts on both sides. Remote ingots count in `get_smelter_demands()` netting so home doesn't re-refine them. Haulers: a Pioneer homed at the site (PR #7 model) serves it; the home-only raw-ore branch in `_pull_deficits_tiered()`/drone hauler can fold into these requests. Done: `5_steampower/lib/site_supply.py` (§2i-1); home ore still uses the home floor, the fold-in is open.
    - [x] **E5 Role switch drain (handcrafted).** Removing a site's Smelters drops its ore request; leftover ore becomes free stock that pull haulers take wherever demand exists. Drains only as fast as demand elsewhere; add a temporary "evict" request only if ore sits. Done: `site_supply.evict_stranded()` (§2i-1): ore at an outpost without Smelters that it neither mines nor requests is requested by home after `EVICT_AFTER_TICKS`.
    - [x] **E6 Per-site demand and order trees.** Root targets carry where they are consumed; each root order's whole tree is built at one site; stock at site A counts only for A's trees. Large root orders split across sites by whole units, sized by site capacity (sticky plan in one shared archive dict). Done: `production.get_site_fabricator_targets()` + `5_steampower/lib/site_plan.py` (`fabricator.site_plan`, §2a-0-6); finished roots are pulled to where they are consumed (§2i-1).
    - [x] **E7 Supply Docks at fab outposts.** The game allows remote docks (`.outpost`, per-outpost overcrowding); ours discovers home only (`production.discover_supply_dock_ids()`, `supply_dock.py`). `plan_dock_assignments()` hands an order to the dock at the site building its tree. Done: docks discovered network-wide, load/drain at their own outpost; a dock's order items are consumed there, so the plan builds their tree there, and the dock planner breaks ties toward the dock site holding or building the order's items (§2a-0-5).
    - [ ] **Validate live (ask first):** remote Smelter/Fabricator/Supply Dock ports on a local Warehouse (connect, `take()`, per-ingredient source switching the Fabricator doc mentions), and feeder lock behaviour with several machines on one outpost's Warehouses. Pilot: iron at Outpost 2.
  - **Shelved**: Warehouse layout by usage frequency (pair most/least-used items per building). Warehouse lock time per unit is fixed (~0.25 s), so layout only reshuffles who waits; and usage shifts heavily whenever a different order is taken. Revisit only if Warehouse lock starvation grows again (Inventory hub shelved too, see above).

Older multi-outpost-production goals this phase's lettered plan above directly targets or will subsume as it's implemented:

---

## 🌿 Phase 4: Biosphere Tier 1 — Planetary Biomass (Unlocks at 210k Index)
- [x] Deploy **Drone Biosurvey** fleet — first working slice: `lib/drone.py` (`DroneController` base,
  fresh hierarchy not a `VehicleController` subclass), `lib/drone_scout.py`/`lib/drone_mining.py`
  (scout/miner roles), `lib/drone_service.py`/`lib/drone_depot.py` (station controllers), entrypoints
  `drone_1.py`/`drone_service_1.py`/`drone_station_1.py`. Electric drones only this pass; heli support
  can follow the same pattern later. See `docs/AI_CHEATSHEET.md` §2h.
  - [ ] **Deferred: cross-outpost drone ferrying of foreign-biome samples.** v1 skips any biosite whose
    tile carries a non-home-biome sample alongside a home-biome one (`PortableBioExtractor.extract()`
    takes no species argument, so it can't be told to pull only the matching one) and never ferries an
    already-extracted foreign sample to the outpost that could process it. Revisit once there's a
    concrete need — a pull request at the processing outpost (`logistics_requests`, served by the
    drone hauler / Pioneer pull hauler, §2i) is the likely template. See `docs/AI_CHEATSHEET.md` §2h.
- [x] Connect multi-biome essence pipeline to central **Biomass Mixers**. (scripted side done: `lib/biomass_mixer.py`; physical pipes still manual)
  - [ ] Validate gate live once tier 5 is active: pause/resume transitions, buffers refilling while breaker off, give-up/backpressure escapes; retune `PAUSE_LEVEL_T`/`RESUME_LEVEL_T`/`NO_PROGRESS_TICKS` from observed Liquifier rates.
- [ ] Add biomass telemetry and threshold alerts for 500 t and 2,000 t milestones.
- [x] Retire the essence chain once biomass reaches **250,000 t** ("Full Biomass", pillar complete): Liquifiers stop feeding + eject input, Mixer gate/routing stop, breakers off (`lib/biomass_retire.py`, driven by `automation_panel.py`); miner drones only fetch requested (Seed Maker) forms and finish partly drained sites; each outpost keeps one Warehouse slot per form, a Waste Processor destroys the rest; "Sell Biomass Chain" button on `status_panel.py` undeploys + sells Liquifiers, Mixer and Mk II pack. See `docs/cheatsheet/bio_seeds_planting.md` §1h-1.
  - [ ] Deploy the updated libs by hand (`essence_liquifier.py`, `biomass_mixer.py`, `drone_mining.py`, `drone_depot.py`, `archive_cleaner.py`) plus `status_panel.py`/`automation_panel.py`; `biomass_retire.py`/`waste_sink.py` are new and sync.
  - [ ] Validate live: Liquifier eject (does `eject()` accept while the bin is mid-liquify?), breakers off, `biomass.retire` readiness, sell button (undeploy returns kit + Mk II pack, full-price resale), drone candidate filter.
  - [ ] Waste Processing is researched: deploy one Waste Processor per outpost with miner drones (`5_steampower/factory/garbage_disposal.py`, `lib/waste_sink.py`), outpost_6 first (Depot full of crystal_spores blocks stone_lichen hauls home, which starves Crowncap seeds). Until then the Depot's `flush_surplus()` (hand-deploy updated `drone_depot.py`) clears forms it can't stage.
  - [ ] Deploy a Waste Processor at home for Water overflow (`lib/water_sink.py`, new, syncs): drains one tank to 80 % only when every Water tank there is >= 90 % and a Water Pump stalls, so the pumps keep making salt. Then check salt pickup keeps up — pumps 3/4 already vent salt (full 20-unit bins).
  - [ ] Steam Condenser (`5_steampower/lib/steam_condenser.py`, new, syncs; slot `steam_condenser_1`): condense steam into water, idle when the grid steam pool is low or the water tank is near full (§1c-2). Validate live: `water_out` spreads across water tanks, steam/water/sink guards trigger, steam pool stays >= 85 % through dormancy. Hand-deploy updated `steam_condenser.py`/`water_sink.py` (already in save lib).
  - [ ] Mk III terraforming fluid feed (`lib/terraforming.py` `Mk3FluidFeed`): Mk III heater `steam_in`, pressure/O2 `water_in`, heater releases steam below 50 % grid steam pool (§1c-3). Hand-deploy updated `terraforming.py`. Validate live: ports exist and connect, `is_degraded()` clears, steam guard disconnect works, retune 0.50/0.70 against turbine dormancy.
  - [ ] Drain or repurpose the essence Liquid Tanks (leftover essence; `fluid_routing.tank_assignments` entries) — e.g. Waste Processor `"liquid"` mode or reassign for Wildlife supply fluids.

---

## 🌾 Phase 5: Biosphere Tier 2 — Agriculture & Plant Terraformers
- [x] Deploy **Seed Maker** and blend 3-specimen combinations to discover all 15 species seeds.
  - [ ] Verify `vehicle.input.take()` can't pull from a Drone Depot (current assumption: Warehouses only; Depot staging covers it).
  - [ ] Control Panel card for sweep progress (`seed_maker.status`: found/15, tried/4060, stock gaps).
  - [ ] Drill positions: recorded on construction (`record_built_drill()`); existing 4 heavy drills to be seeded by hand via Playground. Switch to the game API once the dev adds drill occupancy to `MiningSite` (ticket filed 2026-09-23).
    - [ ] **Watch patch notes / refreshed `docs/` for drill location APIs**: `MiningSite.has_drill()`/`drill_id()` (like `WaterWell.pump_id()`), a position on the Mining Drill component or `PowerGridMember`, or drills showing up in `outpost.buildings()`. When one lands, replace `drill.positions` (construction hook + hand seeding in `lib/drill_sites.py`) with the live lookup and drop the key.
  - [ ] Validate live: drill `connect()`/`take()` from a parked Pioneer, `record_built_drill()` on a real build, 1 stockpile unit = 1 t, pull + normal hauler sharing one ore deficit without overshoot.
  - [ ] Stage B: craft seeds from `recipes()` blends → plant → harvest. Tier `scripts/8_planting/`. Code done and offline/Pyright-checked only; see §1k in `docs/AI_CHEATSHEET.md`. Needs manual lib redeploy of the edited existing lib `vehicle_cargo.py` (plus `seed_supply.py` if already registered).
    - [x] Starter / full layouts (`lib/field_layout.py`, `LAYOUT_VERSION = 3`): starter = 6x8 block, 13 species by hand (keepers cared for but never harvested, ~17 Crowncap + salt trio/Glowvine/Grandbloom harvested; searched against the real care tour), rebuilt only on a `STARTER_VERSION` bump; once Field Automation is researched, one switch to the full layout (diversity garden + fill, 12 Crop Automators), grown in automator chunks sized to Plant Terraformer Forage demand. Fill phase 2 = searched hand-cared garden (`CROWNCAP_GARDEN`, columns 1-4, no machines, never harvested) + solid Crowncap (1.25 Forage/cell-h, no machines), 8 automators, ~2,830 Forage/h; stray machines from an older layout are stopped, emptied and undeployed by the Harvester; built in `work_order()` (garden snake, then fill chunk by chunk; the Harvester plants one fill chunk ahead of its Crop Automator, kits auto-bought from the Shop above a 100k cr reserve); phase 3 = Grandbloom checkerboard once Mk II+ lamps/sprinklers pay (operator sets `plant.field_fill = "grandbloom"`).
      - [ ] Phase 3 automation: Grow Lamp / Sprinkler upgrade packs (order + apply), then an automatic fill switch when they are in.
      - [ ] Validate live: `uproot()` result, `crop_automator_kit` shows in `deployables()` after the research (the switch trigger), the Plants Sensor id `plants_sensor`.
    - [x] Field machines: standing kit order, capped at `KIT_STOCK_CAP` per kit, pre-ordered from 550k km² for the full layout, deploys only in the full layout (`fabricator.upgrade_orders["field_keeper"]`, kept by `fleet_upgrade._prune()` via `production.STANDING_ORDER_REQUESTERS`), Harvester deploys Grow Lamp / Sprinkler / Dispenser kits on the reserved cells (`lib/harvester_machines.py`); machine scripts `harvesting/grow_lamp.py`, `sprinkler.py`, `dispenser.py` (`lib/field_provider.py`): on only while a neighbour needs the service, Sprinkler water via `FluidInputRouter`, Dispenser salt top-up.
      - [ ] Validate live: kit ids from `deployables()`, `deploy()` on an item/unknown cell, script slot names of the new machines (scripts_sync matching), Sprinkler `water_in` link to a Water Pump, Dispenser `input.connect()` to a Warehouse/Inventory for salt, cell `lit`/`watered`/`salted` flags with 0 manual time once covered.
      - [ ] Salt budget: `SALT_STOCK_TARGET` doesn't count Dispenser buffers yet.
    - [x] Crop Automator controller (`lib/crop_automator.py`, thin `harvesting/crop_automator.py`): owns the layout cells nearest to it, harvests mature crops, plants open cells once their providers are deployed (seeds batch-loaded into its input, netted against queued jobs), unblocks a stuck head job, keeps Forage in its output (the home Plant Terraformer and pull haulers take it from there; no drain to Warehouses), republishes `plant.seed_demand` if the Harvester's goes stale, `plant.automators` telemetry. Kits are Shop items (30,000 cr), auto-bought by the Harvester above a credit reserve; `automators_wanted` in `plant.status`.
      - [ ] Validate live: job results (`next_result()` fields), `cells()` ids match sectors, `input` accepts seeds via `take_item()`, CropJob `state`/`blocker` values (`"blocked"`, `"no_seed"`, `"output_full"`), the Plant Terraformer's `input.connect()` + `take("forage")` from an automator output.
      - [ ] Validate live: a Plant Terraformer `input.connect(<automator id>)` + `take("forage")` works, and `harvesting_machines("crop_automator")` refs carry the id `get_component()` accepts.
      - [ ] Validate live: drones go for garden forms first (`supply requests` debug, `Garden forms short`).
      - [ ] Forage throughput: the full field (~3,175/h) outruns one Plant Terraformer (Mk I 400/h, Mk II 2,200/h); more consumers are handled in game. Show `plant.automators[*].forage` fill on a panel to watch how fast automators clog.
      - [ ] Optional: count seeds sitting in automator inputs (up to `SEED_PULL_BATCH` per species each) against Seed Maker demand, if live logs show overproduction.
      - [ ] Water budget: phase 2 needs 8 Sprinklers (garden), phase 3 up to 37 x 2 t/h at Mk I (x2 per tier) vs home water supply.
    - [ ] Field layout v2: rarity-weighted expansion (extra cells favour species whose blends use common life forms), gated by a Harvester care-time budget. Off by default until v1 is proven live. Implemented (`expand_layout()`), enable via `LAYOUT_EXPANSION_ENABLED` and bump `LAYOUT_VERSION`.
    - [x] Plant Terraformer controller (`8_planting/lib/plant_terraformer.py`, thin `bio/plant_terraformer.py`): feeds Forage/Salt/Fertilizer/Accelerant per `batch_requirements()`, Water router, start at `MIN_START_FORAGE`, restart recovery, demand advert as local stock targets in `logistics.requests` (Forage away from home, Salt/Fertilizer/Accelerant per phase) read by the pull/drone haulers, Depot fallback loader, home holds back remote targets, `plant.terraformer` telemetry. Stub-tested only; see §1k.
      - [ ] Validate live: `input.stacks()` shows holder contents, batch start at the threshold, preload while running, `is_enabled()`/restart resume, power draw while enabled-but-blocked vs running.
      - [ ] Remote Terraformer Forage delivery: validate live that the floating drone hauler carries home Forage to a remote Terraformer's Depot outpost (home Crop Automator Forage counts as free stock; the home Depot stages it via `take_item()`).
      - [ ] Fertilizer / Growth Accelerant supply for Mk II phases (needs a code-written Fabricator order channel that `fleet_upgrade._prune()` doesn't wipe).
      - [ ] Control Panel card: phase, km² to next phase, batch progress, onboard Forage.
    - [ ] Plant Terraformer placement: the farm itself uses 0 building slots (field machines occupy field cells, not building capacity), so only Terraformers compete for home's slots. Inventory is location-bound for ordinary I/O (only deployment works from Inventory anywhere), so Harvester Forage (lands in home Inventory) feeds a Terraformer at home, or has to be hauled to an outpost Warehouse. Band 1 (0–500k km²) needs Forage only (25,000).
    - [ ] New saves: leave cheap loose items on the harvesting field instead of selling them (little cash) -- an item cell costs +1 heat to enter vs +7 empty, and they're free paving for the planting path (`harvester_paving.py`). Needs a value threshold in the early sweep (`lib/harvesting.py` `find_best_target()`), and ideally carrying the items onto the future path cells instead of leaving them where they spawned.
    - [ ] Validate live: Harvester can enter/stand on plant cells, heat cost on plant cells (read the calibrated `plant.status[<id>]["heat"]`: move cost per cell status, cooling rate vs the assumed 3/h; heat cost of plant/harvest/treatment actions), planting on `unknown` cells, repeat `combine()` of a known blend, Pioneer `connect()`/`take()` on a pump's `salt_out`, staging a seed/salt from a Warehouse into Inventory right before `load_seed()`/`dispense_salt()`.
- [ ] Design and construct orthogonal farm layout:
  - [ ] 2x2 blocks for Cluster species.
  - [ ] Checkerboard spacing for Spacer species.
- [x] Deploy and script **Crop Automators** to harvest, clear, and replant autonomously. (see Crop Automator controller above; validate live)
  - [ ] Verify water, light, salt, storage, and seed inputs before starting each plot.
  - [ ] Prevent harvest deadlocks when storage is full or a crop is not ready.
- [ ] Reach maximum Species Diversity Multiplier (up to x15 for all 15 active crops).
- [ ] Deploy **Plant Terraformer** fleet:
  - [ ] Feed batch Forage + Water via Auto Feeders.
  - [ ] Progress through Mk I band (0 to 2,250,000 km²).
  - [ ] Upgrade to Mk II and inject Fertilizer + Growth Accelerant (2,250,000 to 5,000,000 km²).
  - [ ] Monitor area, batch progress, input buffers, and power draw; pause cleanly when any input is missing.

---

## 🐾 Phase 6: Biosphere Tier 3 — Wildlife Husbandry & Endgame
- [ ] Catalog all 5 DNA fragments per target creature in Bio Lab to unlock their feed recipes.
  - [ ] Use Bio Orders to drive specimen collection and keep completed samples out of Inventory through Exchange delivery.
  - [ ] Bio Caster bulk material demand (`lib/bio_volcanic.py`, requester `bio_caster`, §1g): deploy `bio_volcanic.py` + `production.py` by hand; live-verify `find_recipe()` returns materials for never-analyzed fragments, forged stacks carry a property (forged-stock subtraction), Fabricator builds the floor and a hauler serves the Volcanic outpost; steam_in/water_in connect via `FluidInputRouter` (steam source must be reachable by gas pipe if not local).
- [ ] Deploy **Habitats** and assign target species (`set_revival_target(creature_id)`).
  - [ ] Stage at least 2 of each required creature's samples before attempting revival.
- [ ] Produce species-specific feed in **Feed Makers**.
  - [ ] Select only unlocked feed recipes and track forage, algae, moss, essences, and output demand.
- [ ] Prospect, cap, and pipe exotic fluid feeds:
  - [ ] Common: Ammonia, Swamp Gas, Brine.
  - [ ] Uncommon/Rare (Refined with Tar): Sulfur Gas, Cryofluid, Chlorine, Quicksilver.
  - [ ] Add Tar production and storage capacity before enabling Refiner recipes.
- [ ] Script closed-loop regulation for Habitat gas/liquid intake to maintain health and breeding cycles.
  - [ ] Keep local tanks above feed thresholds and avoid overfilling Habitat inputs.
- [ ] Accumulate shared **Insight** points and unlock creature trait nodes.
- [ ] Upgrade Habitats to **Mk II** (350,000 capacity per species) to achieve full planetary biodiversity.

---

## 🦎 Phase 9: Wildlife automation (tier `9_wildlife`, plan only)
Automates Phase 6 end to end as a new `scripts/9_wildlife/` tier (thin entrypoints in `bio/`, shared logic in `lib/`; **tier unlock = the first deployed Feed Maker**: `.criteria` `"buildings": {"feed_maker": 1}` in `devtools/scripts_sync.py`, the same mechanism `7_miningdrills` uses; the project's current-focus phase shifts to Phase 9 at that moment). Nothing here is built yet. Design rules: portable (auto-discover outposts/biomes/buildings), one shared archive dict per concern, demand published through the existing channels (`logistics.requests` for materials, `bio_orders` for fragments), every recovering `except` calls `swallowed()`, `TreeConsole` logging.
- [ ] **Placement policy (home vs outposts).** One `lib/` module owns it; scripts stay thin.
  - [ ] Home outpost keeps only the **current rearing targets** (species being revived or actively grown) in Habitats, plus the Feed Makers; home building slots are scarce (Plant Terraformers, Feed Makers, worked Habitats).
  - [ ] Any established species that is **not a current target** is moved out with `rehouse()` to a Habitat at another outpost (destination capacity must fit the whole colony; `"insufficient_capacity"` moves nothing). Pick the destination by free building slots, fluid availability, and how few Habitats it already holds.
  - [ ] Ordering: rehouse only when the destination Habitat is powered, has its feed/gas/liquid connections, and the colony is not mid-rearing. Restart-safe placement state in one archive dict `wildlife.placement` `{creature_id: outpost_id}`, pruned for removed Habitats.
  - [ ] Define "current target" (archive `wildlife.targets`, operator-editable from the Control Panel) and when a target is demoted (reached the stage the operator asked for, or capped and Insight-farmed out).
  - [ ] Home does not need the Habitat outposts stocked with Forage: only feed travels (see Feed below), so remote Habitats are requester-driven pulls like any other outpost stock.
- [ ] **Feed is made at home.** Feed needs **Forage**, which is produced at home (Crop Automators / Harvester, §Phase 8), so Feed Makers stay at home.
  - [ ] `lib/feed_maker.py` controller: `list_recipes()` (only unlocked recipes), pick the recipe by demand (below), stock `input` from Crop Automator Forage + local life forms with `storage.take_item()`, drain `output` to a local Warehouse, Mk II aware.
  - [ ] Demand-driven: feed target per species = what its Habitats (home and remote) need, published as `logistics.requests` under a `feed_maker`/`habitat` requester, so haulers move feed to remote Habitats the same way as other stock. Do not overproduce when output/storage is full.
  - [ ] Ingredient planning: recipes use cross-biome life forms; compute per-recipe ingredient deficits and publish them like other material demand; life-form retention rules (§2h/§2i) already keep stock on hand.
  - [ ] Validate live: recipe ids/inputs from `list_recipes()`, `input.take()` of Forage and life forms, the Feed Maker's 200-unit shared stockpile and 50-unit output buffer.
- [ ] **Bio Labs reactivated, at least one outpost per biome.** The fragment pipeline (Collector → Lab → processor → Exchange, `lib/bio.py` + per-biome modules) already exists; it is currently not running for wildlife.
  - [ ] Reinstate (deploy and re-enable) one Collector + Lab (+ the biome processor) at one outpost in each of the five biomes; the outpost must actually be in that biome (`get_my_biome()` reads live), so this is auto-discovered, not hardcoded. Human approval still gates founding any new Outpost (CLAUDE.md rule 5); reuse existing outposts unless the building planner exists.
  - [ ] Check which biome already has a usable outpost and list the biomes that would need a new one (operator decision, no auto-founding).
  - [ ] Note the Bio Lab is shed **first** under brownout (`docs/cheatsheet/power_fluids.md` §1a); confirm the chosen outposts have power.
  - [ ] Reagents at remote Labs are buyable pull requests (see the Pioneer HOME_BASE item above).
- [ ] **Target species selection** (`lib/wildlife_targets.py`, pure scoring over `journal.cataloged_creatures()` + Feed Maker `list_recipes()`; creature rarity, gas and liquid are only readable at runtime, not in `docs/`). Suggested policy, phases by shared Wildlife total:
  - [ ] **Ranking score**, lowest cost first: (1) feed recipe unlocked (expected for all 16; a missing one ranks last and is reported by the readiness check), (2) rarity (breeding rate x1.0 / 0.75 / 0.50 / 0.30, revival reagent cost scales with it, gas/liquid tier escalates with it), (3) ingredient access: worst ingredient rarity and how many biomes the recipe spans (the Frozen/Deep/... life forms come from biosites via miner drones), (4) fluid readiness: `next_required_gas()`/`next_required_liquid()` tank already exists or is a common fluid (`swamp_gas`, `ammonia`, `brine`), (5) species not yet colonized (breadth pays Insight).
  - [ ] **Phase A, bootstrap** (0 to 250,000 Wildlife, unlocks Feed Maker Mk II): 2 to 3 Common species with only common/uncommon ingredients (e.g. `salt_tortoise` Sea Algae + Snow Moss, `crustal_echo`, `vault_crab`, `hive_sentinel`, `hollow_choir`, `veil_mantle`, `bone_walker`). Common colonies need no liquid and a common gas only.
  - [ ] **Phase B, breadth for Insight**: Insight is 1.00 by 10 population and 1.50 by 100, so found every affordable species early and push each to about 10 to 100 individuals, spending the 1-Insight Adaptations first; then push the fastest-growing Common to 10,000 for the 4-Insight Breakthrough (3 Insight by 10,000 pop). The standby species leave home (placement policy above), so the wide roster costs no home slots.
  - [ ] **Phase C, fluids**: Uncommon species after Exotic Husbandry (raw + tar Refiner), Rare after tar/chlorine/quicksilver capacity, Deep Exotics at 500,000 Wildlife, Habitat Mk II at 600,000. Hard-ingredient species last: `mycelial_husk` (3 Rare fungi), `ferric_sea_lily` (Vent Fungus), `glacial_wyrm` (Black Fungus), `spire_drake`. The 2 Legendaries go last (0.3x breeding rate, rarest fluids at the tightest bands).
  - [ ] **Target set size**: cap by Habitat slots at home and by feed throughput; a target is demoted (rehoused out) when it reaches the operator's stage goal or its next transition needs a fluid we cannot supply yet.
- [ ] **Fragments and recipes are assumed unlocked by the Feed Maker stage, with a guard.** Earth Bio Orders come first in the demand ordering and give credits early, so the Bio Order pipeline (Collector → Lab → processor → Exchange, `lib/bio.py`) has already cataloged the fragments and unlocked the feed recipes by the time tier `9_wildlife` starts. No separate wildlife fragment demand is built.
  - [ ] **Readiness check** at tier start and on a slow poll: compare `journal.cataloged_creatures()` (all 16) and `feed_maker.list_recipes()` against the full creature list; log missing creatures/recipes once and publish them as `wildlife.readiness` `{missing_creatures, missing_recipes}` for the Control Panel card.
  - [ ] **If something is missing**, rely on the existing Earth-orders-first rule to fetch it. Verify that rule still covers the Bio Orders that unlock the missing recipe (`docs/database/recipes_feed_maker.md` names each order, e.g. Reef Fragment Survey); do not add a second demand path. Fallback only if an order is not surfaced by Earth: publish the missing fragments on the existing `bio_orders` shape.
  - [ ] **Volcanic may still be outstanding** when the tier starts: its Bio Caster forging needs many Fabricator orders (`lib/bio_volcanic.py` material demand, Phase 6), so Volcanic fragments and their creatures' recipes can lag. That is expected and self-heals through the Earth-orders-first rule; no wildlife-specific expedite. The readiness check reports it as pending (not an error), species with missing recipes are simply not selectable yet, and the rest of the roster proceeds.
  - [ ] Stage at least 2 samples of each creature to revive (Bio Orders and Exchange delivery keep samples out of Inventory, see Phase 6).
- [ ] **Revisit miner drone life-form priorities for wildlife.** Once biomass completed (`biomass_complete()`), `lib/drone_mining.py` `_biosite_candidates()` only visits biosites holding a life form some outpost *requests* (today only the Seed Maker, via `logistics_requests`), and the Waste Processor/Depot `flush_surplus()` destroy the rest. Feed recipes use all 30 life forms across biomes, so those forms matter again.
  - [ ] The Feed Maker controller publishes its missing ingredients as `logistics.requests` under its own requester, so `network_deficits()`/`active_requests()` make drones visit those biosites again (rarity weighting `RARITY_REQUEST_WEIGHT` already prefers rare forms; check the weights against feed recipes that need rare forms).
  - [ ] Retention: forms the Feed Maker wants must not be discarded by `waste_sink` or Depot `flush_surplus()`; `retain_amount()`/`lifeform_buffer_cap()` must count the feed requester (§2i, §2h).
  - [ ] Decide whether a form requested by a feed recipe but not the Seed Maker also counts in the "partly drained site is finished" logic (`wanted_types`).
  - [ ] Confirm the reading of the request: the message was garbled dictation; I assumed "extraction drones" = miner drones and "fragments" = life forms.
- [ ] **Habitat controller** (`lib/habitat.py`): `set_revival_target()`, stage feed + rarity-scaled reagents, `revive()` and branch on `.status`, then per-stage gas/liquid regulation using the two-sided-band pattern from the Husbandry guide (`next_*` fields to prep upcoming fluids, `purge_reserve()` on overfill). Insight spending via `unlock_bonus()`. Fluid supply and tank routing follow Phase 6 (exotic prospecting) and `FluidInputRouter`.
- [ ] **Telemetry and Control Panel card**: per-species stage, population, breeding rate, efficiency, current outpost, blocker; archive `wildlife.status`, bounded.
- [ ] **Docs**: new cheatsheet section for the constants above and the `9_wildlife` module map entry in `docs/AI_CHEATSHEET.md`, updated in the same change as each constant.
- [ ] **Open questions for later:** which biome outposts exist today; confirm the Feed Maker's building type id for the `.criteria` key (check a save's `state.planet.outposts` buildings).

---

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
- [ ] Exercise failure scenarios: full Inventory, full output buffer, missing recipe, stale Rover claim, disconnected pipe, split power subnet, and stranded vehicle.
- [ ] Keep scripts and documentation aligned with the component/API guides after each major unlock.
- [ ] **Consolidate remaining per-entity archive keys into shared dicts** (archive key-count cap, see CLAUDE.md rule 7): remaining: `biomass_mixer.gate.<id>` (bounded by mixer count, do when next touching `biomass_mixer_gate.py`) and per-grid `power.shedded:`/`power.daily:`/`power.daily_hist:`/`power.night_wh:<anchor>` (4 keys per grid; deferred until 8+ separate grids — two `power.py` tiers, and global `power.shedded` must stay flat).
- [x] **Per-file debug verbosity levels for `TreeConsole`**, so `debug()` coverage can safely widen across most `lib/` files (CLAUDE.md rule 6) without the disk-write cost of leaving high-volume tracing on everywhere. New `console.log_levels` archive dict (`{module_name: "normal"|"verbose"}`, default `"normal"`, toggled manually via the Data Archive Notebook), read once at `TreeConsole.__init__` via an explicit `module=` kwarg (no `inspect`/frame introspection available in the sandbox to auto-detect a caller — found live: `import inspect` is rejected) — not re-checked per tick, so a script needs restarting after an archive edit. `debug()` is unchanged (always written, cheap "why" narration). New `TreeConsole.trace()` is for the genuinely high-volume stuff (method entry/exit, per-item loop detail): a true no-op — never calls `console` at all — unless the module is `"verbose"`. See `docs/AI_CHEATSHEET.md` §0a.
  - [ ] Sweep `lib/` files and add liberal `trace()`/`debug()` calls per CLAUDE.md rule 6, now that every call site is correctly keyed and named `self.log`. Not yet done.
- [ ] **Fleet hardware upgrade background task** (`lib/fleet_upgrade.py` coordinator in headless `automation_panel.py` + `lib/drone_upgrade.py` drone side; see `docs/AI_CHEATSHEET.md` §2k). Code done, not yet exercised live:
  - [ ] Live verification (ask before each run): large Depot at Outpost 5 seen by drones; one Depot swap end to end; one hauler swap end to end (also with scripts_sync stopped); in-place Cargo Pod upgrade; `automation_panel` restart mid-swap. Also confirm on the first swap whether `undeploy` of a Depot is refused with `docked_drone` for drones merely *assigned* (not docked) there, and whether `couple()`/`uncouple()` complete synchronously (the slot survey polls Inventory up to 5 s for the uncoupled module).
  - [ ] Tank upgrade live verification (ask first): confirm `deploy("bulk_liquid_reservoir")` over the outpost building count is accepted, `liquid_in.connect(<old tank>)` pulls the old tank dry, producers move to the new tank, and whether `undeploy()` of a tank with liquid left answers `cargo_present`. Redeploy `fluid_routing.py` by hand first (existing lib).
  - [ ] Warehouse upgrade live verification (ask first): create the `warehouse_upgrade_panel` Custom Panel (empty; scripts_sync fills it); confirm `deploy("large_warehouse")` over the outpost building count is accepted, the drain keeps other consumers off the old Warehouse, and undeploy returns a sellable `warehouse` kit. Show `warehouse_status` on `drones_panel.py`.
  - [ ] Later stage: switch electric drones to heli (`heli_thruster` + oil tanks), gated on a check that every outpost the drone serves has oil at its drone_service. Engine type deliberately never changes today.
  - [ ] Long term: stop reading the save file in `scripts_sync.py` (tier gating via `read_save_state()`, and now the `fleet.upgrade` lineage handoff) — reading the save is a workaround, not a game API. Revisit with in-game signals once the game offers more.
  - [ ] Blocked in the current game version: attach scripts in-game via `run_control.apply_variant(machine_id, variant_id)` to shared variants. Scripts cannot create variants, and a variant saved from `drone_small` is not compatible with `drone_large` (per UI), so the operator would have to save one variant per machine type by hand. Revisit if the game adds variant creation or cross-size compatibility — then the attach step works without scripts_sync.
- [ ] **Long-term: investigate an interrupt/event-driven pattern instead of `sleep(X) -> rescan full state -> sleep(X)`.** Evaluated: the game exposes no real interrupt/callback primitive for scripts, so "interrupt-driven" in practice means a leader computing an expensive shared fact once and followers reading a cached broadcast instead of redundantly recomputing it — exactly `lib/solar.py`'s Master/Follower pattern, generalized. Best candidate identified: `production.py`'s demand cascade, independently recomputed by every Rover/Pioneer/Smelter/Fabricator/Supply Dock every cycle. First application of this pattern is now in progress — see Phase 3's Multi-Outpost Production Network (Smelter leader election gates the "inventory manager" sweep so N smelters don't redundantly sweep the same Inventory/Warehouse set). Widening this further should still be driven by actual `profiling.report()` data, not guesswork.
