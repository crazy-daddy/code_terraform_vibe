# Inspiration TODO: Handled Ideas

Items moved out of [TODO_inspirations.md](TODO_inspirations.md), grouped under the same section headings: every checked item, plus the reviews found not actionable. A checked box here means the idea was either implemented or copied into [TODO.md](TODO.md) for tracking (see that file's header on what X means). It does not always mean the idea is implemented. An unchecked line is the open parent item that stays in TODO_inspirations.md, kept only for context.

---

## Suggested First Picks

- [X] Add a small capability layer for runtime discovery:
  - [X] Probe optional components and research instead of assuming they exist.
  - [X] Discover buildings and stores through `outpost_network`, not fixed ids where practical.
  - [X] Print one startup capability summary per long-running script.
  - Reference: [inspirations/graviadaemon/lib/caps.py](inspirations/graviadaemon/lib/caps.py)
- [X] Add stale-aware Signal Bus helpers:
  - [X] Standardize channel constants and per-vehicle channel naming.
  - [X] Add `latest_info()` age checks for status, demand, and heartbeat data.
  - [X] Fall back to direct component reads when a publisher is absent or stale.
  - Reference: [inspirations/graviadaemon/lib/bus.py](inspirations/graviadaemon/lib/bus.py)
- [X] Add a single fleet status contract:
  - [X] Publish vehicle state, battery Wh, position, docked state, target, and last action.
  - [X] Mark stale vehicles explicitly instead of displaying an old state as current.
  - [X] Include return-to-station and rescue state in the status payload.
  - Reference: [inspirations/graviadaemon/lib/bus.py](inspirations/graviadaemon/lib/bus.py)
- [X] Add a read-only Control Room view for operations:
  - [X] Fleet: position, battery, target, rescue state, and stale heartbeat.
  - [X] Production: active recipe, input/output buffers, and unmet demand.
  - [X] Earth: active order, remaining items, source availability, and blocked reason.
  - [X] Power: generation, demand, storage, shed loads, and recovery state.
  - Reference: `panel_2.py` through `panel_6.py` in [inspirations/graviadaemon](inspirations/graviadaemon)

## Exploration and Outposts

- [ ] Split Pioneer responsibilities into two explicit modes:
  - [x] Scout Pioneer: survey, rank, and report candidate outpost locations only.
  - [x] Keep the one-kit decision human-visible instead of silently founding the first candidate.
    - [X] Approve jobs via Control Panel, not automatically! Never automatically build an Outpost!
      (Superseded pending the building planner phase — see TODO.md. Outposts can now be decommissioned, so founding is no longer permanent; once the planner exists it may place outposts without per-instance approval. This gate still applies to any manual/ad-hoc founding outside the planner.)
- [X] Improve the current spiral survey with a candidate shortlist:
  - [X] Merge Nocturna POIs, Journal sites, unresolved sonar contacts, and archived survey points.
  - [X] Deduplicate contacts within a small coordinate radius.
  - [x] Record unresolved `too_hard`, `tier_too_low`, and `research_required` contacts for future Wide/Deep sonar trips.
  - [x] Rank candidates by resource value, utility value, distance, and current demand.
  - [x] Publish the shortlist to the Data Archive and Signal Bus for operator review.
- [X] Probe outpost legality through the game API instead of maintaining a guessed clearance radius:
  - [X] Plan a temporary outpost structure at a candidate.
  - [X] Record accepted candidates, then retract the unpaid planning ghost.
  - [X] Do not treat a failed placement probe as a permanent site failure.
  - Reference: [inspirations/graviadaemon/lib/scout.py](inspirations/graviadaemon/lib/scout.py)
- [X] Add map markers for shortlisted, unresolved, claimed, and founded sites.
  - Use a script-specific marker prefix so Rover, Pioneer, and Scout entries do not overwrite each other.
- [X] Make the spiral survey bounds-aware:
  - [X] Clamp waypoints to `nocturna.get_bounds()`.
  - [X] Skip points already completed in `pioneer.survey_spiral`.
  - [X] Use the nearest owned outpost as the recovery destination once outposts exist.

## Pioneer Construction Queue

- [ ] Replace the current single-purpose construction loop with a generic queue worker:
  - [X] Read paused jobs first, ordered by completion percentage.
  - [X] Rejoin jobs this Pioneer previously started.
  - [X] Then process pending jobs. # See above - never automatically build outposts outside the (not-yet-built) building planner!
  - [X] Use `required_item` and `required_count` as the source of truth.
- [X] Add construction departure gates:
  - [X] Verify the Pioneer can reach and return before loading cargo.
  - [X] Check exact cargo-bin compatibility, not only `cargo.full()`.
  - [X] Check Auto Feeders, local storage, battery holders, and Constructor Module before departure.
  - [X] Leave a clear, once-per-session reason when a job is blocked.
- [X] Add retry classification for construction results:
  - [X] Retry transient statuses such as `busy`, `paused`, `paused_no_power`, and `not_ready`.
  - [X] Bound repeated `insufficient_materials` results and leave the job for later instead of looping loudly.
  - [X] Treat wrong position as a parking/retry problem before declaring failure.
- [X] Persist Pioneer job ownership, last attempt, blocked reason, and retry count in the Data Archive.
- [X] Make construction resume safe after save/load, rescue, power loss, or script restart.

## Demand and Production

- [X] Expand [lib/production.py](lib/production.py) into a dependency graph:
  - [X] Represent raw, refined, fabricated, and order-required items as nodes.
  - [X] Calculate deficits after Inventory, machine buffers, dock cargo, and in-transit quantities.
  - [X] Stop at locked recipes and report the exact missing unlock or source node. Utilize Control Panel!
  - [x] Share the same graph with Rover, Smelter, Supply Dock, and future Fabricator controllers.
- [x] Publish `earth.demand` as a live Signal Bus broadcast from Supply Dock.
  - Include remaining quantity, source status, and blocked reason per item.
  - Keep direct order reads as a fallback when the broadcast is stale.
  - Reference: Signal Bus conventions in [inspirations/graviadaemon/lib/bus.py](inspirations/graviadaemon/lib/bus.py)
- [x] Add production reservations:
  - [x] Reserve Inventory units for the active order or machine before another worker claims them.
  - [x] Expire reservations with a tick/heartbeat.
  - [x] Show reserved, available, and missing quantities separately on Dashboard.
- [x] Add a recipe helper layer:
  - [x] Centralize unlocked-recipe discovery.
  - [x] Normalize recipe inputs and output names.
  - [x] Expose one function for `can_make(item_id)` and one for `why_blocked(item_id)`.
  - Reference: [inspirations/graviadaemon/lib/recipes.py](inspirations/graviadaemon/lib/recipes.py)
- [X] Add generic storage helpers:
  - [X] Find local stores by outpost and material class.
  - [X] Choose Inventory only at home; choose bins/warehouses at remote outposts.
  - [X] Report capacity pressure before production starts rather than after transfers fail.
  - Reference: [inspirations/graviadaemon/lib/storage.py](inspirations/graviadaemon/lib/storage.py)
- [X] Add an explicit production status payload:
  - [X] Active recipe and unlocked state.
  - [X] Input/output/byproduct buffer counts.
  - [X] Current demand and next required raw material.
  - [X] Blocked reason and last successful operation.

## Rover and Vehicle Safety

- [X] Publish one vehicle heartbeat per vehicle with a freshness window.
  - Include state, battery, position, target, cargo, return reserve, and mission reason.
- [X] **High priority:** move learned Wh/meter calibration to per-vehicle archive keys instead of one shared fleet value.
  - Why: the docs state that Rover and Pioneer have different drivetrain efficiency, throttle penalties, and module loads; one blended value can make one vehicle's round-trip estimate too optimistic.
  - Store a compact key such as `vehicle.wh_per_meter:rover_1` or `vehicle.wh_per_meter:pioneer_1`.
  - Use a conservative per-vehicle default until that vehicle has a valid movement sample.
  - Keep a fleet-wide fallback only for legacy saves or vehicles without their own sample; do not overwrite a vehicle-specific estimate with the shared value.
  - Update `VehicleController`, rescue return budgeting, and any dashboard/readout that reports range to use the same per-vehicle value.
  - Validate after migration with separate Rover/Pioneer trips at the same throttle and confirm that each estimate converges independently.
  - Reference: `vehicle.wh_per_meter:<id>` in the inspiration README; local docs [batteries_and_charging.md](docs/guide/batteries_and_charging.md) and [vehicle_charging_station.md](docs/components/vehicle_charging_station.md)
- [X] Add a single shared return policy:
  - [X] Calculate nearest charging station/outpost.
  - [X] Include current throttle, terrain stalls, scan cost, and cargo work in the estimate.
  - [X] Command a return before rescue when progress is still possible.
  - [X] Dispatch rescue only for stranded, stalled, or irrecoverably low-power vehicles.
- [X] Add a mission lifecycle record:
  - [X] `planned`, `claimed`, `outbound`, `working`, `returning`, `unloading`, `charging`, `complete`, `blocked`, `rescued`.
  - [X] Store timestamps/ticks and the reason for every transition.
- [X] Make Rover reservation messages and telemetry use the same reason object:
  - [X] Raw material.
  - [X] Downstream consumer.
  - [X] Order/recipe id.
  - [X] Required quantity and current shortfall.
  - [X] Site distance and expected energy cost.

## Power and Recovery

- [X] Publish power mode, budget, shed list, and night/day ledger on separate Signal Bus channels.
- [X] Persist shed-load reasons so machines disabled before a restart can be restored intentionally.
- [X] Add a power-aware mission gate:
  - [X] Do not dispatch new Rover/Pioneer missions during a projected overnight deficit.
  - [X] Prefer short mining runs when the grid is in conserve mode.
  - [X] Resume deferred missions after the power budget recovers.
- [X] Add a recovery dashboard that distinguishes:
  - [X] Normal operation.
  - [X] Conserve mode.
  - [X] Critical power mode.
  - [X] Vehicle rescue in progress.
  - [X] Remote outpost offline.
- [X] Add per-subnet diagnosis to the existing outpost checklist:
  - [X] Connected line/bridge pieces.
  - [X] Current generation and demand.
  - [X] Conventional battery reserve.
  - [X] Lightning reserve.
  - [X] Machines paused by full-load failure.
  - Reference: [inspirations/graviadaemon/lib/power.py](inspirations/graviadaemon/lib/power.py)

## Control Room and Operator UX

- [X] Add five read-only panel scripts modeled on the inspiration Control Room:
  - [X] STATUS: warnings, stale publishers, blocked jobs, and rescue state.
  - [X] TERRAFORM: atmosphere, biomass, plants, wildlife, and milestone progress.
  - [X] PRODUCTION: recipes, buffers, demand, and output rates.
  - [X] FLEET: vehicle positions, battery, missions, claims, and nearest station.
  - [X] EARTH: active contract, required items, deliverability, and reward.
  - References: `panel_2.py` through `panel_6.py` in [inspirations/graviadaemon](inspirations/graviadaemon)
- [X] Show stale data explicitly instead of repeating old values as if they were current.
- [X] Add compact operator summaries to Data Archive keys for scripts that cannot draw panels.

### Additional Panel Inspirations

#### Atmosphere Operations Control

- [ ] Add a card: # good idea - merge with cards mentioned above
  - [x] Show Terraform Index, current atmosphere values, rates, efficiency, and next milestone.
  - [x] Add a priority selector for heat, pressure, and oxygen work.

#### Vehicle Operations Control

- [ ] Add a card:
  - [x] `recall`: per-vehicle `vehicle.recall:<name>` archive flag (`lib/vehicle_claims.py` `is_recalled()`/`handle_recall_if_active()`), toggled via `vehicles_panel.py`'s Fleet card switch. On -> abandons the current target and returns to base now; off -> resumes normal operations. Wired into every vehicle run loop plus `drive_to()` itself (guarded so it never blocks the trip home it's asking for).
  - [x] ~~Add a `vehicle.speedmode` toggle (`conserve`/`highspeed`)~~ Superseded by a single numeric fleet-wide default cruise_throttle (`vehicle.default_cruise_throttle` archive key, `default_cruise_throttle()` in `lib/vehicle_energy.py`) — strictly more expressive than a binary flag (any value, not just two presets), and needs no separate "highspeed" branch since `select_cruise_throttle()` already scales any requested throttle down per-leg for a safe return reserve. Now settable live from `vehicles_panel.py`'s FLEET card (a `panel.slider()`, same pure-intent-publish pattern as the per-vehicle recall switch), not just the Data Archive Notebook.

## cyber-f0x Core Automation Scripts (Reviewed 2026-09-16, Not Actionable)

Reviewed the remainder of `inspirations/cyber-f0x/` not already covered (`atmosphere/heater_1.py`, `atmosphere/o2gen_1.py`, `atmosphere/psigen_1.py`, `station_components/solar_1.py`, `harvesting/harvester_1.py`, `harvesting/scanner_1.py`, `bio_lab/bio_collector_1.py`, `bio_lab/bio_exchange_1.py`, `bio_lab/bio_lab_1.py`). All are early-stage, single-file, author-flagged-incomplete scripts (e.g. `bio_collector_1.py` has an explicit `# There is a bug here # Todo fix` around its collection loop) using simple heuristics (CO2/10 intake ratio, brute-force 0-999 wattage probe, flat elevation-based tilt with no master/follower). Every one of these concerns already has a materially more advanced implementation in our own `lib/` (weather-tracked heater calibration, resonance-sweep pressure sync, Signal-Bus-driven bio pipeline with aggressive inventory sweep, `SolarController` master/follower election, full BFS-routed harvester with heat protection). No new patterns worth adopting. `contracts/relay-hack.py` skipped per the contract-script policy above.

## vakermit Power & Rover Scripts (Reviewed 2026-09-16, Not Actionable)

Reviewed `vakermit/scripts/power/{boot,charging_station_1,solar_1}.py` and `vakermit/scripts/rover/rover_1.py`. `rover_1.py` is a well-written single-file rover (explore/mine/charge/unload state machine with an EMA-learned Wh/meter estimate) and is the most polished script found in either new repo so far, but every one of its ideas is already matched or exceeded by our own split architecture:
- "Dock at the charging station's own position, not the outpost footprint" — already how `VehicleController.__init__` resolves `self.home_charging_station` via `find_charging_station()` (`lib/vehicle.py`).
- "Charging jobs belong to the station; one rescue drone, lowest battery first" — our `lib/charging.py` `ChargingStationController` already does this plus more (nearest-of-multiple-stations dispatch via `is_nearest_station_to()`, a per-vehicle `return_floor_wh()` computed from `rescue_wh_per_meter_for()`, and pre-rescue redirect-to-station before ever paging the drone).
- EMA-learned Wh/meter and there-and-back budgeting — matches the shape of `lib/vehicle_energy.py`, which already went further with per-vehicle persisted calibration (see the "High priority" item in Rover and Vehicle Safety above).
- `comms.broadcast("rover.status", ...)` — same idea as our existing per-vehicle heartbeat broadcasts.
No new patterns worth adopting from this set.

## vakermit Factory & Sensor Scripts (Reviewed 2026-09-16, Not Actionable)

- `scripts/factory/{fabricator_1,smelter_1}.py` — a recursive bill-of-materials resolver (Fabricator) and demand-vs-floor batch chooser (Smelter) over `factory.needs`/`factory.ore` Signal Bus channels. Same shape as our already-completed dependency-graph demand cascade (`lib/production.py`, `lib/fabricator.py`, `lib/smelter.py`) and multi-machine claim coordination (Phase 3 Phase A) — nothing new to adopt.
- `scripts/harvesting/scanner_1.py` — full-grid sweep skipping already-`get_scanned()` sectors; matches our own `scanner_1.py`'s behavior per TODO.md.
- `scripts/sensor/{oxygen_sensor,pressure_sensor,uplink}.py` — trivial one-off calibration scripts; equivalents already completed per TODO.md Phase 1.
- `scripts/atmos/{heater_1,pressure_1}.py` — a probe-and-learn state→power table (heater) and a plain sync-window loop with rate learning (pressure); both less capable than our weather-tracked `HeatController` and resonance-sweep `PressureController` (`lib/terraforming.py`). Not actionable, though `pressure_1.py`'s "warn when the gauge's measured per-tick rate exceeds the window width — no script could hit it" is a reasonable defensive check to consider adding to our own `PressureController` if a save ever produces an unusually fast sweep.
- `tools/README.md` (`build_docs.py`) — a separate offline tool that extracts the game's embedded API/manual docs from the game's own executable into Markdown, located by content-anchored search (never by filename/offset, so it survives game updates) rather than a fixed binary layout. Purely informational: useful only if `docs/` in this workspace ever needs refreshing after a game update, and is a standalone tool outside this repo's `lib/` scope — not something to build here. Not run (would require pointing it at the live game install, an action outside this workspace).
- `tools/{build_docs,jsparse,pe}.py` (the extractor's actual code) — skipped by operator decision: pure reverse-engineering/binary-parsing utility code, not game automation, not worth review time.

## vakermit Controller, Pioneer & Storage Update (Reviewed 2026-09-28)

- [x] **Hub-batched survey order.** Merged into TODO.md's existing **Range-aware sonar scanning** item (Rover Automation). The idea: scan from the centroid of a cluster of POIs within sonar range instead of parking on each POI, ranking clusters by new-biome contacts. The POI blacklist already keeps our scout from circling home, so vakermit's biome weighting only affects ranking there.
  - Reference: [inspirations/vakermit/scripts/lib/scout.py](inspirations/vakermit/scripts/lib/scout.py) (`cluster()`, `best_hub()`)
