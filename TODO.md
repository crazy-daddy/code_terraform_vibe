# Code: Terraform — Planetary Terraforming Roadmap & Task Tracker

This document tracks our strategic progress from initial boot to full terraformation of Nocturna.

---

## 📌 Status Summary
- **Sensors Online**: Pressure Sensor (Repaired), Oxygen Sensor (Calibrated), Thermometer (Active).
- **Core Generators**: Solar Tracker (`solar_1.py`), Battery buffer, Oxygen Generator (`o2gen_1.py`), Thermal Cap / Steam Turbine geothermal power (`lib/thermal_cap.py`, `lib/steam_turbine.py`).
- **Milestones Reached**: First Contact, Contracts unlocked, Auto Feeders research unlocked.
- **Current Focus**: Phase 1 — Tri-pillar atmospheric foundation & full Biology automation; Phase 3 — Multi-Outpost Coordination now underway.
- **Operational Focus**: Demand-driven production (multi-smelter/multi-fabricator aware), inventory capacity protection, recipe-aware Rover/Pioneer missions, and the emerging multi-outpost mining network.
- **Selected Work from Inspirations (other ppls code)**: Capability discovery, stale-aware coordination, vehicle recovery, production planning, survey persistence, and dashboard telemetry are selected for implementation from `TODO_inspirations.md`.

---

## 🧭 Phase 1: Early Automation & Industrial Bootstrapping
- [x] Boot system, activate power grid & sensors (`boot.py`, `planet_power.py`, `planet_sensors.py`).
- [x] Calibrate Oxygen Sensor & stabilize Pressure Sensor (`oxygen_sensor.py`, `pressure_sensor.py`).
- [x] Deploy and script Solar Generator with elevation tracking (`solar_1.py`).
- [x] Deploy automated **Power Grid Manager & Brownout Protection** (`lib/power.py` `PowerGridManager`, driven by `lib/solar.py` `SolarController`):
  - Continuous solar elevation tracking.
  - Dynamic night duration calibration and multi-battery endurance calculation.
  - **Tiered Load Shedding** with prioritized dawn/night recovery — current tier assignment and thresholds are tunable and documented in [`docs/AI_CHEATSHEET.md`](docs/AI_CHEATSHEET.md#1a-brownout-load-shedding-detail-libpowerpy-powergridmanager), not restated here.
  - Real-time night deficit detection recommending battery purchases (exact shortfall & recommended units at each battery's price/capacity) alongside sunset capacity advisories.
- [x] Deploy and script Oxygen Generator with dynamic CO2 sweet-spot intake & clean waste dump (`o2gen_1.py`).
- [x] Complete Earth contracts for starting credits:
  - `relay_hack.py` (Completed)
  - `xenogenetics.py` (Completed)
  - `corrupted_archive.py` (Completed)
  - `sealed_vault.py` (Maze DFS traversal & key transmitter)
  - `terminal_breach.py` (Mastermind iterative probe solver)
  - `data_tablet.py` (2D grid probe & reading-order string decoder)
  - **Version 2 (Signal Bus & Shared Library Pipeline)**:
    - [x] Extracted reusable biology controllers into [`lib/bio.py`](lib/bio.py): `BioCollectorController`, `BioLabController`, and `BioExchangeController`.
    - [x] Integrated **Signal Bus** (`get_component("comms")`):
      - Channel `bio_orders`: Real-time order demand broadcasting so Collector only harvests what is needed.
      - Channel `sample_ready`: Instant notification from Lab to Exchange for immediate delivery without polling delays.
    - [x] Aggressive Inventory Sweep: Automatically sweeps and delivers ANY matching inventory sample to ANY incomplete order (local or foreign) to keep inventory completely decluttered.
- [x] Deploy **Heat Generators** (`heater_1.py`, `heater_2.py`, `heater_3.py`) and **Pressure Generators** (`pressure_1.py`, `pressure_2.py`, `pressure_3.py`):
  - `heater_*.py`: Weather tracking & daily dynamic power calibration for 100% thermal efficiency (dynamic machine id).
  - `pressure_*.py`: Resonance sweep gauge tracking & precision sync window hits for 100% compression efficiency (dynamic machine id).
- [x] Shared Library unlocked (`lib/`):
  - `lib/terraforming.py`: Implemented `HeatController`, `PressureController`, and `OxygenController`.
  - `lib/power.py` / `lib/solar.py`: `PowerGridManager` (generic, grid-type-agnostic shedding/recovery) and `SolarController` (sun tracking + Master/Follower election on top of it).
  - `SolarController`: Auto-elects single Master (`solar_1` or lowest running ID) per independent power grid for grid monitoring & load shedding; all other panels run lightweight sun tracking with automatic failover.
  - Variant 1 on `heater_1.py`, `pressure_1.py`, `o2gen_1.py`, and `solar_1.py` converted to shared library imports.
- [x] Unlock **Mining & Rover Operations** (Thresholds: Pressure 0.10–0.20 kPa):
  - [x] Shared Library [`lib/vehicle_energy.py`](lib/vehicle_energy.py) (mixed into `VehicleController` via [`lib/vehicle.py`](lib/vehicle.py), specialized by [`lib/rover.py`](lib/rover.py)) with 'there-and-back' energy budgeting — current safety margin, reserve floor, and Wh/m calibration are tunable and documented in [`docs/AI_CHEATSHEET.md`](docs/AI_CHEATSHEET.md#2a-vehicle-energy-budgeting-detail-libvehicle_energypy-vehicleenergymixin).
    - [x] Replace the flat `MINE_WH_PER_UNIT = 2.5` mining-cost average with an exact per-ore/per-drill/per-purity `mine_wh_per_unit(item_id, purity)`, derived from documented dig times (`docs/database/items_minerals.md`), drill Watts by hardness tier (`docs/components/drill_module.md`), and the purity yield multiplier (`docs/types/world_and_sites.md`). *(Found while validating whether Pioneers stay energy-safe at higher speed: the flat constant only matched the cheapest case and under-reserved by up to ~3.6x for a Heavy drill on Neutronium — independent of throttle, a real pre-existing risk. All real mining call sites now pass the candidate's own `harvest_item`/`purity`. See `docs/AI_CHEATSHEET.md` §2a.)*
    - [x] Replaced the binary `vehicle.speedmode` ("conserve"/"highspeed") archive flag with a single numeric fleet-wide default: `default_cruise_throttle()` reads a `vehicle.default_cruise_throttle` archive value (clamped to `[MIN_SPEEDMODE_THROTTLE, MAX_SPEEDMODE_THROTTLE]`, falling back to `0.5`), used whenever a vehicle is constructed with `cruise_throttle=None` (now every general-purpose `rover_1-3.py`/`pioneer_1-4.py`, so raising the one archive value speeds up the whole fleet at once — the demand-driven transporter role still passes an explicit `cruise_throttle=1.0` and is unaffected). The old dedicated "highspeed" branch in `select_cruise_throttle()` was removed as fully redundant: it always throttled down from a requested baseline for a safe return reserve and never up, so setting `cruise_throttle=1.0` already reproduces its exact behavior through the one remaining formula — no separate code path needed. Verified via stub tests (archive default read/fallback/clamp/garbage-value handling; a safe leg returns the full requested throttle; an unsafe leg throttles down; a lower baseline is never scaled up). Now also settable live via a `panel.slider()` on `panel_2.py`'s FLEET card, not just the Data Archive Notebook. See `docs/AI_CHEATSHEET.md` §2a.
  - [x] Multi-Rover Fleet Coordination:
    - Atomic site reservation (`archive.transaction("rover.claims", ...)`) to prevent duplicate missions.
    - Automatic stale claim expiration (see `CLAIM_STALE_TICKS` in `docs/AI_CHEATSHEET.md`) and claim heartbeat renewal.
    - Staggered base staging slots (`(0,0)`, `(2.5,0)`, `(-2.5,0)`, etc.) preventing parking and charging pad collisions.
    - Deadlock / terrain stall detection and yielding logic.
    - **Capability-Aware Target Blacklisting & Dynamic Re-evaluation**:
      - Records scanner type, tier (`basic`/`wide`/`deep`), hardness limit (`1.0`/`3.0`/`4.0`), and research counts on failure (`wrong_scanner`, `too_hard`, `tier_too_low`, `research_required`).
      - Prevents infinite retry loops while automatically allowing upgraded rovers (Wide/Deep Sonar, Bio Scanners, or new tech) to re-evaluate and explore those contacts. Industrial/Heavy Drills are Pioneer-universal-slot items, not a Rover upgrade path — see the Pioneer mining role below.
      - Automatically clears entries from the archive once successfully scanned or mined.
  - [x] **Shared Mining Library & Pioneer Mining Role** ([`lib/mining.py`](lib/mining.py) `MiningMixin`, mixed into `VehicleController`): mineral-site discovery and drill execution live in one place instead of duplicated between `rover.py` and `pioneer.py`. Capability read live via `hardness_limit()`, never assumed from vehicle type. `pioneer_3.py` runs a Pioneer's mining role (requires an operator-mounted Industrial/Heavy Drill — never auto-mounted) for hardness > 1 sites a Rover's basic drill can't reach; Rovers are softly preferred for hardness ≤ 1 (iron/silicon) sites via priority-sort, not hard exclusion — see [`docs/AI_CHEATSHEET.md`](docs/AI_CHEATSHEET.md#2b-mining-libminingpy-miningmixin).
- [x] Deploy **Harvesting & Grid Survey System**:
  - [x] Scanner Automation ([`scanner_1.py`](scanner_1.py)): Systematically sweeps all 192 local grid sectors (A1..H24) to discover surface items and persist map knowledge.
  - [x] Shared Library [`lib/harvesting.py`](lib/harvesting.py):
    - 8x24 grid BFS shortest-path routing (`find_path`).
    - Active heat protection (pauses travel and cools down above `HEAT_SAFE_CEILING`, resumes at `HEAT_RESUME_LEVEL` — see `docs/AI_CHEATSHEET.md`, to avoid the 100 heat limit).
    - Automated surface item collection and immediate offload into Base Inventory.
    - Mature crop harvesting and idle base depot parking.
  - [x] Harvester Automation Script ([`harvester_1.py`](harvester_1.py)).
- [x] Set up automated Smelter loop ([`lib/smelter.py`](lib/smelter.py), [`smelter_1.py`](smelter_1.py)):
  - Ore refinement into metal ingots (`smelt_iron_ingot`, `smelt_glass`, `smelt_titanium_ingot`, etc.).
  - Automatic recipe clearing and idle power shutoff via `power.set_powered("smelter_1", False)`.
  - Cooperative wake-up: `rover_1` automatically powers on the smelter whenever fresh ore is deposited into Base Inventory.
  - Multi-Smelter aware: see Phase 3's Multi-Outpost Production Network entry — leader election + per-recipe claims now support 2+ physical Smelters.
- [x] Add demand-driven production planning ([`lib/production.py`](lib/production.py)):
  - Read active Fabricator recipe inputs and stockpile deficits.
  - Read active Supply Dock order deficits and subtract Inventory/Dock stock.
  - Convert refined-material demand into raw-ore demand through unlocked Smelter recipes only.
  - Prevent Rover mining and Smelter processing when Inventory already has surplus material.
  - Handle full Inventory without discarding Rover cargo or Bio Lab output.
- [x] Deploy **Supply Dock Logistics** ([`lib/supply_dock.py`](lib/supply_dock.py), [`supply_dock_1.py`](supply_dock_1.py)):
  - Priority assignment for recipe/tech-unlocking Contractor Campaign Orders (Helios, Spire, Vestibule) and Weekly Earth Orders.
  - Automated inventory loading and continuous dispatch at 25+ units/h.

- [ ] Implement selected inspiration-derived coordination and observability improvements:
  - [x] Add runtime capability probing and graceful optional-component fallbacks — pervasive throughout every controller written this project (`hasattr()`/`try`/`except` guards on every optional component read, e.g. `mining.py`, `vehicle.py`, `thermal_cap.py`, `steam_turbine.py`, `storage.py`, `production.py`), not a single isolated task remaining.
  - [ ] Add stale-aware Signal Bus heartbeats with direct-read fallbacks.
  - [ ] Add unified vehicle status including battery, position, target, docked state, return, rescue, and stale state.
  - [x] Expand the demand dependency graph across Rover, Smelter, Supply Dock, and Fabricator planning.
  - [ ] Publish Earth demand, add production reservations, recipe/source explanations, and local storage routing.
    - [x] Production reservations (`get_construction_material_reservations()`), recipe/source explanations (`get_raw_material_reason()`, `target_reason()`), and local storage routing (`lib/storage.py`) are done — only "publish Earth demand" (to Signal Bus) remains.
  - [x] Persist per-vehicle Wh/meter calibration with conservative defaults and shared legacy fallback.
  - [ ] Add mission lifecycle records and reservation reasons covering material, consumer, order/recipe, shortfall, distance, and energy cost.
  - [ ] Expose power mode, budget, shedding, recovery, and subnet diagnostics through shared telemetry.
  - [ ] Add read-only Control Room telemetry for status, terraforming, production, fleet, and Earth order views.
    - [x] Implement initial read-only Status, Fleet, and Production cards (`panel_1.py`, `panel_2.py`, `panel_3.py`).
    - [ ] Add Terraform and Earth order cards.
    - [ ] Add shared readout helpers and stale-data presentation across all cards.
  - [ ] Add compact Data Archive summaries for operator dashboards and scripts that cannot draw panels.

---

## 🏭 Phase 2: Logistics & Manufacturing Infrastructure
- [x] Fulfill Contractor Campaign Orders (Helios Orbital, Spire Research, Vestibule Logistics) at Supply Docks.
- [ ] Unlock and fabricate crucial blueprints:
  - [x] Pipe segments (Liquid Pipe, Gas Pipe) and Power Line segments.
  - [ ] Smelter blueprints (Glass, Titanium Ingots, Cobalt Ingots). *(Recipe code for these already exists in `lib/smelter.py`'s `RECIPE_MAP`/`docs/database/recipes_smelter.md` — this item tracks in-game blueprint unlock status, not code, so left unconfirmed here.)*
  - [ ] Drones, Drone Depots, and Service Stations.
- [ ] Build a complete recipe-aware manufacturing loop:
  - [x] Add a Fabricator controller that selects only unlocked recipes with an active downstream need (`lib/fabricator.py`, `fabricator_1.py`).
  - [x] Maintain minimum Gas Pipe and Power Line Segment stock while prioritizing active Supply Dock orders.
  - [x] Track Fabricator stockpile and output buffer before loading another batch.
  - [x] Recover stranded/excess input-stockpile material back into circulation instead of leaving it stuck until consumed. *(`FabricatorController.eject_excess_inputs()` in `lib/fabricator.py`, run every `step()`: ejects (via `InputSlot.eject()`, never the destructive `.flush()`) any staged item the active recipe no longer needs at all — leftover from a prior recipe, or from no recipe being set — plus any staged amount beyond `required_per_craft * crafts_remaining` for the active recipe, e.g. after the stock target dropped or another producer covered part of the shortfall. Found via a screenshot showing `fabricator_1` idling at 145/200 stockpile used while its active recipe needed only a fraction of that. See `docs/AI_CHEATSHEET.md` §2a-2.)*
  - [x] Track Fabricator fluids and byproduct buffers for recipes that require them. *(`can_source_fluid()`/`recipe_is_sourceable()` in `lib/production.py`/`lib/fabricator.py` confirm a fluid source exists before selecting such a recipe at all — see Phase 3's water-blocked-Circuit-Panel fix. The remaining gap — the Fabricator never actually connecting `.water_in`/`.steam_in`/`.oil_in` to a real source once a fluid-needing recipe was set — is now fixed: `ensure_fluid_connections(recipe)` discovers reachable source buildings network-wide per `production.FLUID_SOURCE_TYPE_IDS` and connects each fluid_input's port, mirroring `lib/steam_turbine.py`'s `ensure_input_connection()` (same discover/connect/blacklist pattern, an INPUT port declaring its own upstream source). No `is_stalled()` exists on the Fabricator itself, so reachability is inferred instead from `flow_rate()` staying `0` for `FLUID_STALL_STREAK_BLACKLIST_THRESHOLD=5` consecutive ticks while the port still has room to receive (`level() < capacity()`) — a legitimately full port reading zero flow is not mistaken for a stall. Verified via a stub test (connects to a discovered source; no reconnect while flow is healthy; a full-but-idle port is correctly NOT treated as starved; genuine starvation blacklists the source and reconnects to another; per-entry blacklist expiry). Byproduct buffer (`.byproduct`, e.g. Tar Bin for oil-refining recipes) monitoring remains open.)*
  - [x] Add production reservations so multiple machines do not claim the same Inventory stock.
  - [x] Verify each new recipe unlock in `list_recipes()` before enabling its inputs or mining demand.
- [ ] Harden home storage and transfer behavior:
  - [ ] Add separate bins for raw ores, refined materials, fabricated parts, and overflow.
  - [ ] Route Smelter input/output explicitly and handle `partial`, `busy`, `target_full`, and `slots_full` results.
  - [x] Add an overflow policy: sell, warehouse, or pause production; never silently discard useful materials — Warehouse routing (`lib/storage.py`'s `rebalance_inventory_to_warehouses()`/`best_unload_target()`) is the implemented policy.
  - [x] **Consolidate an item already split across Inventory and a Warehouse (found from real play).** `rebalance_inventory_to_warehouses()` only used to move an item out once it spanned more than `INVENTORY_REBALANCE_SLOT_THRESHOLD=2` Inventory slots on its own, so a small quantity already ALSO sitting in a Warehouse (e.g. `gas_pipe_segment`, stock target 10, ended up 10 in Inventory + 10 already in a Warehouse — double the target, split across both) never got merged. Fixed with `_warehouse_item_ids()` — the sweep now also consolidates an item regardless of Inventory slot count whenever a Warehouse already holds some of it too, since a further remainder in Inventory serves no purpose once an item has a Warehouse home. Verified via stub tests (original bulk-threshold rule unchanged; a not-already-split single-slot item still left alone; an already-split single-slot item gets fully consolidated; property-bearing items still never touched). See `docs/AI_CHEATSHEET.md` §2c.
- [x] Extract Unified Vehicle Architecture: [`lib/vehicle.py`](lib/vehicle.py) (`VehicleController`) powering both Rover and Pioneer fleets.
- [x] Deploy **Pioneer** equipped with **Constructor Module** ([`lib/pioneer.py`](lib/pioneer.py)):
  - [x] Architecture ready: modular chassis slot inspection (`inspect_slots()`) and construction blueprint execution (`execute_construction()`).
  - [ ] Practice a small nearby blueprint before remote construction.
  - [ ] Construct chassis, mount Nav, Battery Holder, Cargo Rack, and Constructor Module.
  - [ ] Install at least one charged Portable Battery and verify cargo capacity before dispatch.
  - [ ] Query pending construction jobs and verify required kit/segments are physically loaded before execution.
- [x] Tap local **Thermal Vents** (Geothermal steam power) — `lib/thermal_cap.py` + `lib/steam_turbine.py`, including network-wide Gas Tank discovery/load-balancing and stall-driven blacklisting for unreachable pipe routes. Two compounding bugs fixed here: (1) a single shared "clear everything at once" blacklist timer could wipe elimination progress against 2+ simultaneously-unreachable candidates before ever reaching the actually-reachable target — fixed by tracking each blacklist entry's own expiry tick independently, same pattern as `vehicle_claims.py`/the Smelter/Fabricator recipe claims; (2) the deeper root cause, found by the player debugging in-game: `discover_network_buildings()` returned raw `BuildingRef` snapshots (no `fill_pct()` — see `docs/components/outpost.md`) instead of resolving them via `get_component()`, so fill-based sorting silently degenerated into a discovery-order tie and the fast path never engaged, alternating forever between whichever two candidates sat adjacent in that fixed order. Fixed by resolving via `get_component(ref.id) or ref`, the same pattern `storage.py`/`vehicle_energy.py`'s discovery helpers already used correctly. See `docs/AI_CHEATSHEET.md`.
- [x] Route water from the first **Water Pump** to network Liquid Tanks — new `lib/water_pump.py` (`WaterPumpController`, entrypoint `water_pump_1.py`), mirroring `lib/thermal_cap.py`'s network-wide tank discovery/load-balancing/stall-driven blacklisting almost exactly (same constants/reasoning), but deliberately simpler: a Water Pump has no internal buffer to overpressure at all (no `pressure()`/`is_overpressured()`/`relief()` in `docs/components/water_pump.md`), so there's no proportional release-valve logic to mirror — `step()` just keeps `water_out` pointed at a reachable, non-full tank and holds throttle at `1.0` unconditionally. Discovers both `"liquid_tank"` and `"large_liquid_tank"` building types (a Water Pump can fill either), a small generalization of `discover_network_buildings()` to accept an iterable of type_ids rather than the single one Thermal Cap needed. Verified via stub tests (discovers/resolves both tank types from raw `BuildingRef`s, connects to the least-full tank first, fast-path skips reconnects while healthy, a stalled connection gets blacklisted and reconnects to the other tank, per-entry blacklist expiry). See `docs/AI_CHEATSHEET.md` §1c.
  - [ ] Tap local **Water Wells** — deferred; confirmed no Water source built yet in this save (blocks any recipe/blueprint needing Water, e.g. Circuit Panel — see `can_source_fluid()` in `lib/production.py`).

- [ ] Implement selected Pioneer and survey improvements:
  - [ ] Separate Scout Pioneer behavior from human-approved construction intent; never auto-found an Outpost without approval.
  - [ ] Persist spiral survey progress, shortlist candidates, unresolved contacts, and archived survey points.
  - [ ] Deduplicate and rank survey candidates by resource/utility value, distance, and current demand.
  - [ ] Publish survey shortlists to the Data Archive and Signal Bus for operator review.
  - [ ] Probe outpost placement legality through the construction API and retract temporary planning ghosts.
  - [ ] Persist map markers for shortlisted, unresolved, claimed, and founded locations.
  - [ ] Clamp survey waypoints to planet bounds and resume from completed spiral points.
  - [ ] Add construction departure gates, cargo-bin compatibility checks, retry classification, blocked-job warnings, and save/load/rescue recovery.
  - [ ] Decide whether to adopt a generic construction queue worker for approved non-Outpost jobs; Outpost construction remains explicitly human-approved.

---

## 🌐 Phase 3: Multi-Outpost Coordination & Production Network

The save has grown past a single production base: multiple outposts are founded, several sit near ore deposits home doesn't have easy access to, and home itself is about to run more than one Smelter/Fabricator. This phase covers everything needed to coordinate production/logistics across that — split out of what used to be Phase 2's "Outpost Networks" scope because it has grown large enough to deserve its own phase. Full design for the mining-network half in `C:\Users\Adrian\.claude\plans\agile-frolicking-flurry.md` (Multi-Outpost Mining Network + Multi-Smelter Leader Election section).

### Outpost Infrastructure & Freight
- [X] Lay power lines and liquid/gas transport pipes to satellite Outposts.
- [ ] Configure autonomous Drone freight routes between Outpost storage bins and Base Inventory:
  - [ ] Fabricate and deploy a Drone Depot into an outpost.
  - [ ] Commission electric drones, then mount thruster, battery, Cargo Pod, and logistics modules through service controls.
  - [ ] Add service-station charging, rescue, exposure, and `cargo.space_for()` checks to route scripts.
- [ ] Verify power subnet topology after every remote build:
  - [ ] Confirm every line/bridge is complete and physically touches the intended service footprints.
  - [ ] Compare subnet generation, demand, conventional battery storage, and Lightning Rod reserve.
  - [ ] Test recovery after a split route and after a remote outpost brownout.

### Multi-Outpost Production Network
Two correctness/scaling problems tackled together: every production-demand function used to hardcode the literal id `"smelter_1"`/`"fabricator_1"` (breaks the moment a second Smelter/Fabricator exists), and every mining vehicle funnels ore back to the single home base regardless of outposts founded near other ore deposits.

- [x] **Phase A — Multi-Smelter Leader Election + Multi-Fabricator Claim Coordination.** `production.discover_smelter_ids()`/`discover_fabricator_ids()` replace every hardcoded `"smelter_1"`/`"fabricator_1"` fallback across `production.py`'s demand-cascade functions; `mining.py`/`rover.py` drop their explicit `smelter_1` args. `SmelterController` (`lib/smelter.py`) gets leader election mirroring `solar.py`'s `check_master()` (Archive+`run_control`, not Signal Bus) — only the Leader runs the Inventory→Warehouse rebalance sweep. Both `SmelterController` and `FabricatorController` gained a `claim_recipe()`/`release_recipe()` pair (separate archive keys, same shape, mirrors `vehicle_claims.py`) so multiple instances of either machine split simultaneously-demanded recipes instead of racing for the same one — Fabricator didn't need leader election on top since it has no shared per-cycle task to gate (the rebalance sweep is Smelter-only). Verified via stub tests (leader election, claim split across two simultaneously-demanded ores/recipes for both machines, claim refresh). See `docs/AI_CHEATSHEET.md`'s Multi-Smelter Support note and §2a-0-2.
  - [x] **Multi-Dock Support (found late, same bug class).** `get_fabricator_targets()`/`get_material_demands()`/`get_raw_material_reason()` all read a single hardcoded `"supply_dock_1"` — the identical bug Phase A fixed for Smelter/Fabricator, just not caught for Supply Dock at the time; a second dock's own active order was completely invisible to demand tracking. Fixed with `production.discover_supply_dock_ids()`/`_all_dock_orders()`/`find_dock_order_requiring()`, looped by every demand-cascade function instead of one hardcoded dock; `lib/fabricator.py`'s `target_reason()` now shares the same `find_dock_order_requiring()` instead of its own separate hardcoded read. No claim coordination needed (order fulfillment is inherently per-dock, no race to guard). Verified via a stub test (two docks with different single-item orders both register demand; reason attribution finds the correct dock). See `docs/AI_CHEATSHEET.md` §2a-0-3.
  - [x] **Recipe/ore claims didn't split a single large order across idle Smelters/Fabricators (found from real play).** With only ONE recipe/ore ever demanded, the claim mechanism's "spread across distinct demanded recipes" logic left every Smelter/Fabricator past the first idle forever — there was never a second demanded item for them to fall back to, so e.g. "fabricator_2 slaves away on 100 circuit boards while fabricator_1 sits idle" instead of splitting the work. Fixed in both `select_needed_ore()` (`lib/smelter.py`) and `choose_recipe()` (`lib/fabricator.py`): collect every sourceable/demanded candidate first, try to exclusively claim each same as before, but if NONE can be claimed (every one already fresh-claimed by a peer), join the best one anyway instead of returning idle. Fabricator additionally needed an explicit even split (Smelter didn't, since its ore intake already self-throttles via demand netting against `total_stock()` each cycle): `production._fabricator_worker_count(recipe_id)` — a live headcount of every Fabricator currently on the same recipe — divides `get_fabricator_active_recipe()`'s `crafts_remaining` across every joined worker, so piling on doesn't also cause each one to independently pre-load the FULL remaining shortfall. Verified via stub tests (sole-demand pile-on for both Smelter and Fabricator; crafts_remaining correctly split across worker count; worker-counting isolates by recipe id and floors at 1). See `docs/AI_CHEATSHEET.md` §2a-0-2.
  - [x] **One Fabricator/Smelter could still monopolize a contested shared item in a single grab (found from a screenshot: fabricator_1 showed 44/1 Glass staged, fabricator_2 sat at 0/2).** `load_inputs()`/the Smelter's ore top-up used to request their entire remaining need (up to several dozen/50 units) in one `take_item()` call, so whichever instance polled first could take the whole available stock before a peer's own poll ever got a turn. Fixed by capping each call to `FABRICATOR_LOAD_CHUNK_SIZE`/`SMELTER_LOAD_CHUNK_SIZE = 10` units, spreading a heavy batch across several `step()` cycles so a peer can interleave and grab its own share in between. Supply Dock's own loading deliberately keeps loading its full need in one call (no sibling competes for the same order's materials, so there's nothing to share). Verified via stub tests (a single call never exceeds the chunk size; two Fabricators alternating turns against a shared, contested pool end up with a fair split instead of all-or-nothing; repeated Smelter steps keep topping up in the same chunk size). See `docs/AI_CHEATSHEET.md` §2a-0-2.
- [x] **Phase B — Outpost Ore-Assignment & Stock-Target Scaffolding.** New `lib/outpost_mining.py`: `assigned_ores_for(outpost_id)` auto-seeds (nearest-surveyed-site-to-outpost via `outpost_network.nearest()`, capped to that outpost's Warehouse slot count) once per outpost and never overwrites afterward — the player can hand-edit the archived list (e.g. after adding a second Warehouse). `reseed_ore_assignment(outpost_id)` is a separate, never-auto-called rebuild for a future Control Panel button to pick up newly-surveyed POIs without clobbering manual edits. `stock_target_for(outpost_id, item_id)` same seed-once-editable shape, default 1 Warehouse slot (2000 units). Verified via stub tests (ranking/cap, no silent re-seed after new POIs, manual edits respected, explicit reseed picks up new POIs). See `docs/AI_CHEATSHEET.md` §2d.
- [x] **Phase C — Stationed Mining Role.** `VehicleController.__init__`'s `home_coords=(0, 0)` param replaced by `home_base=None` (an outpost id) so a vehicle's "home" can be any outpost — resolved to live objects exactly **once** at construction (`self.home_outpost`, `self.home_charging_station`) rather than re-walking `outpost_network.outposts()` by id on every lookup, same redundant-network-walk class of cost the Thermal Cap/Turbine profiling work fixed earlier this session. `MiningMixin.build_local_stockpile_candidates(outpost_id)` + `run_stationed_mining_loop(outpost_id)`: mine this outpost's assigned ores up to their stock targets, independent of home's live demand (stockpiling ahead of it), unloading into the local Warehouse (`unload_cargo()` now outpost-aware via the cached `self.home_outpost`; `wake_smelter()` gated to home-based vehicles only). All 7 thin entrypoint scripts (`rover_1-3.py`, `pioneer_1-4.py`) updated to drop the now-redundant `home_coords=(0, 0)` kwarg. Verified via stub tests (home_base resolution to charging station/outpost-coords/literal fallback across 3 scenarios; zero additional network walks across 10 repeated reads; stockpile-candidate filtering excludes non-nearest sites and empties out once stock target is met). See `docs/AI_CHEATSHEET.md` §2e. *(Resolves the old "keep home base as hub, use local Warehouses at remote outposts" and "extend Rover unloading to nearest local store" goals below.)*
- [x] **Phase D — Demand-Driven Transporter Role.** Deleted `pioneer.py`'s old ad hoc `find_outpost_coords()`/`find_local_store()`/`transport_once()`/`run_transport_loop()` (no thin script referenced them) in favor of `VehicleCargoMixin.run_supply_run_loop(poll_interval=10.0)` (shared by Rover/Pioneer — a dedicated hauler needs neither drill nor construction slots). Construct with `home_base=<mining outpost id>` (reuses Phase C's caching directly — the transporter idles/recharges at that *stationed* outpost between runs; note this makes its own `self.home_base`/`self.home_outpost` mean the stationed mining outpost, NOT the production outpost, unlike every other vehicle — see the terminology note in `docs/AI_CHEATSHEET.md` §2f). Takes no fixed `item_id` — **the load can mix several different assigned ores in one trip** (e.g. 50 titanium + 30 silicon), decided dynamically every cycle (`_plan_supply_load(capacity)`: ranks the stationed outpost's `outpost_mining.assigned_ores_for()` by the production outpost's unmet demand descending, keeping only ores that actually have stock on hand, then greedily fills up to cargo capacity across however many qualify), since an outpost can have several assigned ores and limiting one transporter to a single fixed item per run would leave the others piling up unused or waste spare capacity. Cargo already aboard (resuming after a reload) is identified from the cargo itself (`_current_supply_items()`, all stacks, not just one) rather than re-planned mid-delivery. Loads each planned `(item_id, amount)` via `storage.take_item(outpost=self.home_outpost)` (the stationed outpost, where the ore is), drives explicitly to the production outpost (resolved once via `self.get_outpost_ref(None)` into a `production_outpost` variable — deliberately not named `home_outpost`, to avoid exactly the ambiguity this note is correcting), delivers (`unload_cargo()` already sends each stack to its own destination independently, so the mixed load needed no delivery-side changes), `unload_cargo(outpost=production_outpost)` (new explicit-override param), then **recharges fully at the production outpost before heading back** (`recharge_at_station()`, resolved by current position not `home_base`, so it correctly targets the production outpost's own station) — lets the return leg run at full throttle instead of a conservative one, in addition to the existing recharge back at the stationed outpost — then returns to its station. `unload_cargo()`'s `wake_smelter()` gate switched from `self.home_base is None` to the resolved delivery target's `.is_home` flag. Pioneer, not Rover, for this role: Rover's integrated hold is a fixed `capacity() == 10` (`docs/components/rover.md`), far too small for bulk hauling, while Pioneer's Cargo Rack/Portable Bin capacity scales with loadout and exposes the identical interface; a working example lives in a thin entrypoint script in the project root (not named here since those get renumbered/edited often — search for `run_supply_run_loop`). One instance per mining outpost, configured at the thin-entrypoint-script level. Bugfix found live in-game: the loop used to jump straight from planning a load to `take_item()` without first checking it was physically at the stationed outpost, so a transporter left at the production outpost after its last delivery (or freshly started elsewhere) would fail every load attempt and just sit there printing "Could not load any planned item" forever instead of ever driving back — fixed by an `is_at_base()` check + `return_to_base()` right before loading. Verified via stub tests (mixed load planning correctly spans two qualifying ores in one trip, excludes a much-higher-demand ore with zero stock, and fills the higher-ranked ore first when capacity is tight; full loop idles with no stock at the stationed outpost; repeated hauling trips correctly capped by cargo capacity until the stationed outpost's stock drains; zero drive calls when the production outpost's demand is 0 despite available stock at the stationed outpost; recharges exactly twice per completed trip, once at the production outpost before the return leg and once at the stationed outpost after returning; drives back to the stationed outpost before loading when not already parked there). See `docs/AI_CHEATSHEET.md` §2f. *(Directly resolves the "publish transport requests" goal below via a direct demand check instead of a publish/subscribe round trip.)*

Older multi-outpost-production goals this phase's lettered plan above directly targets or will subsume as it's implemented:
- [x] Add a Pioneer Transport role with persisted source/destination/item/count routes (`lib/pioneer.py`, `pioneer_2.py`) — the original single-route mechanism; **superseded and removed** in favor of Phase D's demand-driven `run_supply_run_loop()` (`lib/vehicle_cargo.py`).
- [x] Add a Pioneer Mining role (`lib/pioneer.py` `run_mining_loop()`, `pioneer_3.py`) for hardness > 1 mineral sites via `lib/mining.py`.
- [ ] Keep the home base as the production hub and use local Warehouses/Bins at remote outposts. *(→ Phase B/C)*
- [x] Extend Rover unloading so missions can target the nearest local store instead of always home Inventory. *(Resolved by Phase C — `unload_cargo()` defaults to `outpost=self.home_outpost`, and by Phase D's explicit `outpost=` override for the transporter's home-delivery leg.)*
- [x] Publish transport requests when the hub is short of remote materials. *(Resolved by Phase D — `run_supply_run_loop()` checks `get_raw_material_demands()` directly each cycle instead of a publish/subscribe round trip.)*
- [ ] Add route feasibility checks for battery, charging stations, cargo capacity, local storage, and service-area parking. *(→ Phase C/D implementation detail)*
- [ ] Add transport priority so order-critical materials outrank building-stock replenishment. *(→ Phase D)*

---

## 🌿 Phase 4: Biosphere Tier 1 — Planetary Biomass (Unlocks at 210k Index)
- [ ] Deploy **Drone Biosurvey** fleet:
  - [ ] Equip drones with **Bio Scanners** to classify all 35 permanent biosites (7 per biome).
  - [ ] Equip drones with **Bio Extractors** to harvest native fauna specimens.
  - [ ] Persist biosite coordinates and specimen demand in the Journal/Data Archive.
  - [ ] Respect drone cargo space, service range, battery/oil, and rescue thresholds.
- [ ] Construct regional **Essence Liquifiers** at biome outposts to produce localized Biome Essences.
  - [ ] Connect local storage to each Liquifier and drain output before its buffer blocks production.
- [ ] Connect multi-biome essence pipeline to central **Biomass Mixers**.
  - [ ] Confirm each pipe route is complete, conflict-free, and connected to the correct fluid ports.
- [ ] Add biomass telemetry and threshold alerts for 500 t and 2,000 t milestones.
- [ ] Reach **500 t Biomass** threshold (unlocks Seed Maker).
- [ ] Reach **2,000 t Biomass** threshold (unlocks Plant Terraformers).

---

## 🌾 Phase 5: Biosphere Tier 2 — Agriculture & Plant Terraformers
- [ ] Deploy **Seed Maker** and blend 3-specimen combinations to discover all 15 species seeds.
  - [ ] Record successful combinations in the Flora Journal and avoid repeating failed blends unnecessarily.
- [ ] Design and construct orthogonal farm layout:
  - [ ] 2x2 blocks for Cluster species.
  - [ ] Checkerboard spacing for Spacer species.
  - [ ] Install **Grow Lamps** (Light), **Sprinklers** (Piped Water), and **Dispensers** (Salt).
- [ ] Deploy and script **Crop Automators** to harvest, clear, and replant autonomously.
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
- [x] Add lightweight per-script tick-cost profiling (`lib/profiling.py`, using `clock.tick()` deltas per docs/components/clock.md) and use it to find/fix a real hotspot: Thermal Cap / Steam Turbine's `ensure_output_connection()`/`ensure_input_connection()` were re-running a full `outpost_network`-wide building discovery walk every single `step()` even while already healthily connected. Fixed with a fast path (a healthy connection is confirmed with one cheap `fill_pct()`/`is_stalled()` read, no walk) plus a TTL cache for the cases that do still need discovery. See `docs/AI_CHEATSHEET.md`.
- [ ] **Long-term: investigate an interrupt/event-driven pattern instead of `sleep(X) -> rescan full state -> sleep(X)`.** Evaluated: the game exposes no real interrupt/callback primitive for scripts, so "interrupt-driven" in practice means a leader computing an expensive shared fact once and followers reading a cached broadcast instead of redundantly recomputing it — exactly `lib/solar.py`'s Master/Follower pattern, generalized. Best candidate identified: `production.py`'s demand cascade, independently recomputed by every Rover/Pioneer/Smelter/Fabricator/Supply Dock every cycle. First application of this pattern is now in progress — see Phase 3's Multi-Outpost Production Network (Smelter leader election gates the "inventory manager" sweep so N smelters don't redundantly sweep the same Inventory/Warehouse set). Widening this further should still be driven by actual `profiling.report()` data, not guesswork.
