# Code: Terraform — Planetary Terraforming Roadmap & Task Tracker

This document tracks our strategic progress from initial boot to full terraformation of Nocturna.

---

## 📌 Status Summary
- **Sensors Online**: Pressure Sensor (Repaired), Oxygen Sensor (Calibrated), Thermometer (Active).
- **Core Generators**: Solar Tracker (`solar_1.py`), Battery buffer, Oxygen Generator (`o2gen_1.py`).
- **Milestones Reached**: First Contact, Contracts unlocked, Auto Feeders research unlocked.
- **Current Focus**: Phase 1 — Tri-pillar atmospheric foundation & full Biology automation.
- **Operational Focus**: Demand-driven production, inventory capacity protection, and recipe-aware Rover missions.
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
  - [ ] Add runtime capability probing and graceful optional-component fallbacks.
  - [ ] Add stale-aware Signal Bus heartbeats with direct-read fallbacks.
  - [ ] Add unified vehicle status including battery, position, target, docked state, return, rescue, and stale state.
  - [x] Expand the demand dependency graph across Rover, Smelter, Supply Dock, and Fabricator planning.
  - [ ] Publish Earth demand, add production reservations, recipe/source explanations, and local storage routing.
  - [x] Persist per-vehicle Wh/meter calibration with conservative defaults and shared legacy fallback.
  - [ ] Add mission lifecycle records and reservation reasons covering material, consumer, order/recipe, shortfall, distance, and energy cost.
  - [ ] Expose power mode, budget, shedding, recovery, and subnet diagnostics through shared telemetry.
  - [ ] Add read-only Control Room telemetry for status, terraforming, production, fleet, and Earth order views.
    - [x] Implement initial read-only Status, Fleet, and Production cards (`panel_1.py`, `panel_2.py`, `panel_3.py`).
    - [ ] Add Terraform and Earth order cards.
    - [ ] Add shared readout helpers and stale-data presentation across all cards.
  - [ ] Add compact Data Archive summaries for operator dashboards and scripts that cannot draw panels.

---

## 🏭 Phase 2: Logistics, Infrastructure & Outpost Networks
- [x] Fulfill Contractor Campaign Orders (Helios Orbital, Spire Research, Vestibule Logistics) at Supply Docks.
- [ ] Unlock and fabricate crucial blueprints:
  - [x] Pipe segments (Liquid Pipe, Gas Pipe) and Power Line segments.
  - [ ] Smelter blueprints (Glass, Titanium Ingots, Cobalt Ingots).
  - [ ] Drones, Drone Depots, and Service Stations.
- [ ] Build a complete recipe-aware manufacturing loop:
  - [x] Add a Fabricator controller that selects only unlocked recipes with an active downstream need (`lib/fabricator.py`, `fabricator_1.py`).
  - [x] Maintain minimum Gas Pipe and Power Line Segment stock while prioritizing active Supply Dock orders.
  - [x] Track Fabricator stockpile and output buffer before loading another batch.
  - [ ] Track Fabricator fluids and byproduct buffers for recipes that require them.
  - [x] Add production reservations so multiple machines do not claim the same Inventory stock.
  - [x] Verify each new recipe unlock in `list_recipes()` before enabling its inputs or mining demand.
- [ ] Harden home storage and transfer behavior:
  - [ ] Add separate bins for raw ores, refined materials, fabricated parts, and overflow.
  - [ ] Route Smelter input/output explicitly and handle `partial`, `busy`, `target_full`, and `slots_full` results.
  - [ ] Add an overflow policy: sell, warehouse, or pause production; never silently discard useful materials.
  - [ ] Keep Inventory as a home-only freight endpoint and use local storage at remote outposts.
- [x] Extract Unified Vehicle Architecture: [`lib/vehicle.py`](lib/vehicle.py) (`VehicleController`) powering both Rover and Pioneer fleets.
- [x] Deploy **Pioneer** equipped with **Constructor Module** ([`lib/pioneer.py`](lib/pioneer.py)):
  - [x] Architecture ready: modular chassis slot inspection (`inspect_slots()`) and construction blueprint execution (`execute_construction()`).
  - [ ] Practice a small nearby blueprint before remote construction.
  - [ ] Construct chassis, mount Nav, Battery Holder, Cargo Rack, and Constructor Module.
  - [ ] Install at least one charged Portable Battery and verify cargo capacity before dispatch.
  - [ ] Query pending construction jobs and verify required kit/segments are physically loaded before execution.
- [ ] Tap local **Water Wells** and **Thermal Vents** (Geothermal steam power).
  - Water wells come later
- [ ] Lay power lines and liquid/gas transport pipes to satellite Outposts.
- [ ] Configure autonomous Drone freight routes between Outpost storage bins and Base Inventory:
  - [ ] Fabricate and deploy a Drone Depot into an outpost.
  - [ ] Commission electric drones, then mount thruster, battery, Cargo Pod, and logistics modules through service controls.
  - [ ] Add service-station charging, rescue, exposure, and `cargo.space_for()` checks to route scripts.
- [ ] Make production explicitly multi-outpost-safe:
  - [x] Add a Pioneer Transport role with persisted source/destination/item/count routes (`lib/pioneer.py`, `pioneer_2.py`).
  - [x] Add a Pioneer Mining role (`lib/pioneer.py` `run_mining_loop()`, `pioneer_3.py`) for hardness > 1 mineral sites via `lib/mining.py`.
  - [ ] Keep the home base as the production hub and use local Warehouses/Bins at remote outposts.
  - [ ] Extend Rover unloading so missions can target the nearest local store instead of always home Inventory.
  - [ ] Publish transport requests when the hub is short of remote materials.
  - [ ] Add route feasibility checks for battery, charging stations, cargo capacity, local storage, and service-area parking.
  - [ ] Add transport priority so order-critical materials outrank building-stock replenishment.
- [ ] Verify power subnet topology after every remote build:
  - [ ] Confirm every line/bridge is complete and physically touches the intended service footprints.
  - [ ] Compare subnet generation, demand, conventional battery storage, and Lightning Rod reserve.
  - [ ] Test recovery after a split route and after a remote outpost brownout.

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

## 🌿 Phase 3: Biosphere Tier 1 — Planetary Biomass (Unlocks at 210k Index)
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

## 🌾 Phase 4: Biosphere Tier 2 — Agriculture & Plant Terraformers
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

## 🐾 Phase 5: Biosphere Tier 3 — Wildlife Husbandry & Endgame
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

## 🧪 Phase 6: Reliability, Diagnostics & Operations
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
- [ ] **Long-term: investigate an interrupt/event-driven pattern instead of `sleep(X) -> rescan full state -> sleep(X)`.** Many controllers currently re-check everything from scratch every poll cycle regardless of whether anything changed, which scales poorly as more scripts run concurrently. Candidates once profiling data shows where it matters most: Signal Bus push notifications for state changes instead of polling, splitting "cheap per-tick check" from "expensive periodic rescan" (the pattern just applied to Thermal Cap/Turbine) more broadly across other controllers, and/or longer default `poll_interval`s for controllers whose state changes slowly. Should be driven by actual `profiling.report()` data, not guesswork.

