# Inspiration TODO: Ideas to Pick and Choose

This is a separate idea backlog based on the current roadmap in [TODO.md](TODO.md) and the `graviaDaemon` reference implementation in [inspirations/graviadaemon](inspirations/graviadaemon). Nothing here is assumed to be required. Select items when they fit the current save, unlocked research, and desired automation style.

The inspiration repository is a reference for patterns, not a drop-in replacement. Keep our existing game-specific behavior, demand planner, recovery policy, and spiral survey unless an item below explicitly improves them.

Ideas marked with an X here are **not** yet implemented; the X means "Copy/Adapt this into the main TODO"

## Viability Review Against Local Docs

Reviewed against the local component and guide documentation on 2026-09-13. The inspiration ideas are generally viable as patterns, but several need to respect this save's exact API boundaries.

- **Viable now:** capability probing, JSON-safe Data Archive state, stale-aware Signal Bus broadcasts, read-only telemetry panels, sampled trend charts, and generic construction-queue prioritization.
- **Viable with an authority layer:** interactive panel controls. The docs provide `button`, `switch`, `slider`, and `toggle` widgets, but a panel has `panel` rather than machine `self`; commands must go through Signal Bus queues or documented shared authorities. Panels should not directly call vehicle movement, recipe selection, or mining actions.
- **Viable with save-specific discovery:** outpost/store discovery, nearest charging station routing, expansion candidates, and map markers. Do not copy the inspiration repository's ids, coordinates, research gates, or assumptions.
- **Needs bounded persistence:** trend history, mission ledgers, reservations, and unresolved contacts must stay within Data Archive value limits. Prefer compact summaries and fixed-size histories over unbounded append-only records.
- **Not automatically portable:** the inspiration repository's helper modules and panel readout APIs. Reimplement against this save's existing component APIs before marking those items complete.

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
  - [O] Constructor Pioneer: consume the shared construction queue and build approved jobs. # O = Maybe; see below
  - [x] Keep the one-kit decision human-visible instead of silently founding the first candidate.
    - [X] Approve jobs via Control Panel, not automatically! Never automatically build an Outpost!
      (Superseded pending the building planner phase — see TODO.md. Outposts can now be decommissioned, so founding is no longer permanent; once the planner exists it may place outposts without per-instance approval. This gate still applies to any manual/ad-hoc founding outside the planner.)
  - References: [inspirations/graviadaemon/pioneer_1.py](inspirations/graviadaemon/pioneer_1.py), [inspirations/graviadaemon/pioneer_2.py](inspirations/graviadaemon/pioneer_2.py), [inspirations/graviadaemon/lib/scout.py](inspirations/graviadaemon/lib/scout.py)
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
  - Reference: [inspirations/graviadaemon/lib/pioneer.py](inspirations/graviadaemon/lib/pioneer.py)
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
- [ ] Add a fleet manager that limits simultaneous long missions based on available charging bays and grid budget.
  - Reference: [inspirations/graviadaemon/lib/fleet.py](inspirations/graviadaemon/lib/fleet.py)

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

## Biology and Logistics

- [ ] Add Bio machine heartbeats and status broadcasts:
  - [ ] Collector target and collection result.
  - [ ] Lab specimen stage and reagent shortfall.
  - [ ] Exchange active order and delivery throughput.
- [ ] Add freshness-aware demand fallback so a stopped Exchange does not leave stale `bio.wanted` demand active forever.
- [ ] Add reusable port/storage routing helpers for Bio Lab, Smelter, Fabricator, and Supply Dock.
  - Reference: [inspirations/graviadaemon/lib/ports.py](inspirations/graviadaemon/lib/ports.py)
- [ ] Add Supply Dock source explanations:
  - [ ] Already in Inventory.
  - [ ] Can be made from unlocked recipes.
  - [ ] Requires an unsurveyed node.
  - [ ] Requires unavailable research.
  - [ ] Blocked by storage or transport capacity.
- [ ] Add contract scoring that balances reward value against time-to-deliver, energy cost, surveyed sources, and current production capacity.
- [ ] Add a generic storage rebalance job for home bins, warehouses, and outpost stores.

## Control Room and Operator UX

- [X] Add five read-only panel scripts modeled on the inspiration Control Room:
  - [X] STATUS: warnings, stale publishers, blocked jobs, and rescue state.
  - [X] TERRAFORM: atmosphere, biomass, plants, wildlife, and milestone progress.
  - [X] PRODUCTION: recipes, buffers, demand, and output rates.
  - [X] FLEET: vehicle positions, battery, missions, claims, and nearest station.
  - [X] EARTH: active contract, required items, deliverability, and reward.
  - References: `panel_2.py` through `panel_6.py` in [inspirations/graviadaemon](inspirations/graviadaemon)
- [ ] Keep panels read-only and make shared libraries the sole owners of machine actions.
- [X] Show stale data explicitly instead of repeating old values as if they were current.
- [X] Add compact operator summaries to Data Archive keys for scripts that cannot draw panels.

### Additional Panel Inspirations

The attached panel designs suggest a useful second layer beyond read-only monitoring: a small number of intentional controls that publish operator intent while shared libraries remain the only owners of machine actions.

#### Colony Strategy

- [ ] Add a card:
  - [ ] Provide a bounded strategy selector such as `atmosphere`, `production`, `outposts`, `drones`, or `biosphere`.
  - [ ] Show the current strategic goal, the next unlock or milestone, the active bottleneck, and the recommended priority order.
  - [ ] Show the current campaign requirements that block the selected goal.
  - [ ] Persist the selected goal in the Data Archive and broadcast it as operator intent.
  - [ ] Keep the selector advisory until a controller explicitly consumes it.
#### Atmosphere Operations Control

- [ ] Add a card: # good idea - merge with cards mentioned above
  - [x] Show Terraform Index, current atmosphere values, rates, efficiency, and next milestone.
  - [ ] Add `auto_power` and `auto_hardware` toggles that publish requests to the Terraforming supervisor.  # auto_hardware means auto buy stuff from shop?
  - [x] Add a priority selector for heat, pressure, and oxygen work.
  - [ ] Show current outpost/subnet headroom and the next planned upgrade.
  - [ ] Require the power/terraforming library to validate every requested action before applying it.
#### Vehicle Operations Control

- [ ] Add a card:
  - [ ] Choose Pioneer mission policy: `auto`, `scout`, `constructor`, `nearest_outpost`, or `hold`.
  - [ ] Toggle directional exploration, water scouting, explorer fit, and rescue-dependent range policy.
  - [ ] Add commands for `resume`, `clear survey retries`, and `refresh outpost sites`.
  - [x] `recall`: per-vehicle `vehicle.recall:<name>` archive flag (`lib/vehicle_claims.py` `is_recalled()`/`handle_recall_if_active()`), toggled via `panel_2.py`'s Fleet card switch. On -> abandons the current target and returns to base now; off -> resumes normal operations. Wired into every vehicle run loop plus `drive_to()` itself (guarded so it never blocks the trip home it's asking for).
  - [x] ~~Add a `vehicle.speedmode` toggle (`conserve`/`highspeed`)~~ Superseded by a single numeric fleet-wide default cruise_throttle (`vehicle.default_cruise_throttle` archive key, `default_cruise_throttle()` in `lib/vehicle_energy.py`) — strictly more expressive than a binary flag (any value, not just two presets), and needs no separate "highspeed" branch since `select_cruise_throttle()` already scales any requested throttle down per-leg for a safe return reserve. Now settable live from `panel_2.py`'s FLEET card (a `panel.slider()`, same pure-intent-publish pattern as the per-vehicle recall switch), not just the Data Archive Notebook.
  - [ ] Display every ground vehicle's current mission, battery, rescue state, and reason for its target.
  - [ ] Route commands through a queue with acknowledgements; panels must not call vehicle actions directly.
#### Production Operations Control

- [ ] Add a card:
  - [ ] Show `AUTO` versus manual-priority mode and the currently selected high-priority target.
  - [ ] Let the operator choose an unlocked recipe or output target from a bounded list.
  - [ ] Show the dependency chain, for example `raw ore -> ingot -> fabricator component -> Earth order`.
  - [ ] Add `apply high priority` and `auto` commands that take effect at the next safe recipe change.
  - [ ] Refuse locked recipes, unavailable raw sources, and changes while incompatible input is buffered.
  - [ ] Show storage readiness, input/output buffers, duty cycle, and the reason production is idle.
#### Expansion Candidates

- [ ] Add a region to the Vehicle or Strategy card:
  - [ ] Rank candidate outposts by newly reachable site kinds, resource density, distance, power potential, and current demand.
  - [ ] Show the top candidates with coordinates, site count, new resource types, and construction feasibility.
  - [ ] Let the operator accept, reject, or defer a candidate without silently founding it.
#### Power History

- [ ] Add a dedicated card:
  - [ ] Plot hourly or tick-sampled stored Wh, generation, demand, and net power.
  - [ ] Shade forecast night, conserve, and critical intervals differently.
  - [ ] Mark load-shed and recovery events on the timeline.
  - [ ] Display current stored/capacity values and time until dawn over the chart.
  - [ ] Keep chart history in a panel-local ring buffer or Data Archive series, sampled at a fixed interval rather than every repaint.
- [ ] Standardize panel interaction and visual language:
  - [ ] Use status dots for healthy/warning/error states and meters for battery, completion, and storage.
  - [ ] Use compact controls with explicit current values and a visible acknowledgement/result state.
  - [ ] Show stale publisher data as `stale`, never as a current command or mission.
  - [ ] Keep read-only telemetry separate from operator commands in both the UI and Signal Bus channels.
  - [ ] Add overflow counts when a card cannot show every vehicle, alert, machine, or order.
- [ ] Add command ownership and safety rules:
  - [ ] One controller owns each concern: Terraforming owns power/hardware, Production owns recipes, Fleet owns vehicle missions.
  - [ ] Panels publish intent only; controllers validate research, capacity, energy, and current state.
  - [ ] Persist the last command, issuer, tick, result status, and rejection reason.
  - [ ] Add a clear `manual override active` indicator and an expiry/return-to-auto policy.

References for these patterns:

- Baseline read-only cards: `panel_2.py` through `panel_6.py` in [inspirations/graviadaemon](inspirations/graviadaemon)
- Strategy and operator controls: attached Control Room concepts; adapt to this save's panel command API
- Power history visualization: attached `Nocturna power` concept; sample history at a stable game-time interval

## Developer Workflow Tooling (Outside Game Scripts, Reviewed 2026-09-16)

Two more community repos were reviewed for the first time this pass: `cyber-f0x` and `vakermit`. Both are much smaller than `graviadaemon`; most of their in-game automation (solar, o2gen, heater, bio_lab, harvester, relay-hack, etc.) is a simpler version of patterns already implemented here, so no new game-automation ideas were found in the files sampled. One item stood out as worth flagging, but it lives outside the `lib/`-architecture rules in `CLAUDE.md` entirely — it is a local dev tool that runs beside the game, not a script that runs inside it.

- [ ] Consider a save-directory sync watcher for our own workflow (external tool, NOT a `lib/` module or in-game script):
  - Watches `%APPDATA%/io.codeterraform.game/save_*_scripts/` for empty script slots the game creates and fills them from a version-controlled `scripts/` tree by matching base name (ignoring a trailing `_<number>`), rewriting only the script's own numbered id to match the slot.
  - A `xyz` marker on a file's first line force-fills it (even non-empty); a `zyx` marker pulls a game-tuned file back into the repo tree instead, backing up whatever it replaces.
  - Supports named variants of a script (e.g. an `early`/`mid` tier of `bio_lab_1.py`) picked via marker, a per-directory `.current` file, or a `--variant` flag.
  - This workspace *is* the save's script directory already, so the closest fit would be a separate sibling tool/repo that treats our root `*_<n>.py` entrypoints as the sync source — not something to build inside this repo, and not a priority; only worth doing if manually re-pasting thin entrypoint scripts into new slots becomes a real recurring cost.
  - Reference: [inspirations/vakermit/bin/ct_sync.py](inspirations/vakermit/bin/ct_sync.py), [inspirations/vakermit/bin/README.md](inspirations/vakermit/bin/README.md)
- Reviewed and found not actionable:
  - [inspirations/cyber-f0x/README.md](inspirations/cyber-f0x/README.md) — personal repo blurb, no patterns.
  - [inspirations/cyber-f0x/libraries/coordinate_handling.py](inspirations/cyber-f0x/libraries/coordinate_handling.py) — a bare `Coord(row, col)` class (`toString()` only); far less capable than what our own `lib/` coordinate handling already does, nothing to adopt.
  - [inspirations/vakermit/README.md](inspirations/vakermit/README.md) — repo overview; describes the `ct_sync.py`/`build_docs.py` tooling covered above, no game-automation content itself.
  - [inspirations/vakermit/scripts/power/power.py](inspirations/vakermit/scripts/power/power.py) — a one-line `activate_power()` entrypoint; same thin-entrypoint-calls-shared-lib pattern we already follow, nothing new.

## Contract Puzzle Solvers (Future Reference, Reviewed 2026-09-16)

`vakermit/scripts/contract/` has algorithm solutions for several Earth contract puzzle types we have not yet encountered in this save (our own completed set per [TODO.md](TODO.md) is `relay_hack`, `xenogenetics`, `corrupted_archive`, `sealed_vault`, `terminal_breach`, `data_tablet`). These are pure self-contained algorithms with no shared-library dependency, so nothing to adopt into `lib/` now — logged only so that if/when one of these contract types appears in our own save, we have a starting algorithm to adapt (never copy verbatim without confirming the exact rules/format match, since contract wording can vary run to run):

- [ ] `buried_five` — message wrapped N times, each layer expanding every token into 5; `analyzer.read()` collapses one aligned group of 5 back to its source token, peeled layer by layer left-to-right. Reference: [inspirations/vakermit/scripts/contract/buried_five.py](inspirations/vakermit/scripts/contract/buried_five.py)
- [ ] `cold_boot` — an Intcode-style bytecode VM (opcode in low two digits, parameter modes above; add/mul/out/jump-if-true/jump-if-false/less-than/equals/halt), decoding numeric outputs as letters (`1 = A`). Reference: [inspirations/vakermit/scripts/contract/cold_boot.py](inspirations/vakermit/scripts/contract/cold_boot.py)
- [ ] `core_sample` — ten damaged byte-record cores with `None` holes; constraint propagation (mutual partner links, `kind + partner.kind = 5`, `sum = (kind+load+partner) mod 256`, and a lock byte that is the XOR of every record's sum) fixed-pointed until no field changes, then submitted per-core. Reference: [inspirations/vakermit/scripts/contract/core_sample.py](inspirations/vakermit/scripts/contract/core_sample.py)
- Skipped by operator decision (2026-09-16): `beat_the_system`, `crosstalk`, `drifting_signal`, `lattice`, `the_loom`, `three_echoes` in the same directory. These are one-off contract puzzle scripts for contract types we already solve with our own (less elegant but working) code — not worth the review time. Do not re-queue these for future batches.

## cyber-f0x Core Automation Scripts (Reviewed 2026-09-16, Not Actionable)

Reviewed the remainder of `inspirations/cyber-f0x/` not already covered (`atmosphere/heater_1.py`, `atmosphere/o2gen_1.py`, `atmosphere/psigen_1.py`, `station_components/solar_1.py`, `harvesting/harvester_1.py`, `harvesting/scanner_1.py`, `bio_lab/bio_collector_1.py`, `bio_lab/bio_exchange_1.py`, `bio_lab/bio_lab_1.py`). All are early-stage, single-file, author-flagged-incomplete scripts (e.g. `bio_collector_1.py` has an explicit `# There is a bug here # Todo fix` around its collection loop) using simple heuristics (CO2/10 intake ratio, brute-force 0-999 wattage probe, flat elevation-based tilt with no master/follower). Every one of these concerns already has a materially more advanced implementation in our own `lib/` (weather-tracked heater calibration, resonance-sweep pressure sync, Signal-Bus-driven bio pipeline with aggressive inventory sweep, `SolarController` master/follower election, full BFS-routed harvester with heat protection). No new patterns worth adopting. `contracts/relay-hack.py` skipped per the contract-script policy above.

## vakermit Power & Rover Scripts (Reviewed 2026-09-16, Not Actionable)

Reviewed `vakermit/scripts/power/{boot,charging_station_1,solar_1}.py` and `vakermit/scripts/rover/rover_1.py`. `rover_1.py` is a well-written single-file rover (explore/mine/charge/unload state machine with an EMA-learned Wh/meter estimate) and is the most polished script found in either new repo so far, but every one of its ideas is already matched or exceeded by our own split architecture:
- "Dock at the charging station's own position, not the outpost footprint" — already how `VehicleController.__init__` resolves `self.home_charging_station` via `find_charging_station()` (`lib/vehicle.py`).
- "Charging jobs belong to the station; one rescue drone, lowest battery first" — our `lib/charging.py` `ChargingStationController` already does this plus more (nearest-of-multiple-stations dispatch via `is_nearest_station_to()`, a per-vehicle `return_floor_wh()` computed from `rescue_wh_per_meter_for()`, and pre-rescue redirect-to-station before ever paging the drone).
- EMA-learned Wh/meter and there-and-back budgeting — matches the shape of `lib/vehicle_energy.py`, which already went further with per-vehicle persisted calibration (see the "High priority" item in Rover and Vehicle Safety above).
- `comms.broadcast("rover.status", ...)` — same idea as our existing per-vehicle heartbeat broadcasts.
No new patterns worth adopting from this set.

## Oxygen Generator: Overshoot-Penalty Gap Found (Reviewed 2026-09-16)

`vakermit/scripts/atmos/o2gen_1.py`'s header documents a real failure mode that our own `OxygenController.step()` ([lib/terraforming.py:108-118](lib/terraforming.py)) has not addressed: waste rises with intake, so on a rich atmosphere a single tick's `co2/10` intake can carry waste from just under the clean-dump window (50) straight past its top (60) in one step — the dump that follows is penalized, and "the penalty lingers until the NEXT dump, so it is not a one-off cost: it taxes the whole cycle that follows." Our current code sets full-rate intake unconditionally and only checks `current_waste >= 50` to trigger a dump — it has no notion of trimming intake to land inside the window, so on any CO2 level rich enough for one tick's waste production to exceed the ~10-unit window width, every single dump cycle would be a dirty one.

- [ ] Add overshoot-aware intake trimming to `OxygenController`:
  - [ ] Learn waste-produced-per-unit-intake (`wpi`) as an exponential moving average from consecutive `waste()` deltas (skip ticks where waste did not move).
  - [ ] Let the first overshoot go through and price the real penalty-per-unit-over-window (`ppu`) from `dump_waste()`'s `.penalty` result, rather than assuming a cost.
  - [ ] Before setting intake, check whether a full-rate tick would carry current waste past the dump window's top; if so, compare the cost of trimming intake this tick (lost production) against `ppu * (projected overshoot)` averaged over the cycle, and only trim when trimming is cheaper.
  - [ ] Keep it self-adapting per-machine/per-CO2-regime rather than a fixed threshold, since the answer depends on the (undocumented) penalty severity, which can only be learned empirically.
  - Reference: [inspirations/vakermit/scripts/atmos/o2gen_1.py](inspirations/vakermit/scripts/atmos/o2gen_1.py) (`trim_to()`, `wpi`/`ppu` learning)

## Harvester: Heat-Priced Routing (Reviewed 2026-09-16, Worth Evaluating)

`vakermit/scripts/harvesting/harvester_1.py` takes a different strategy from our `HarvestingMixin` ([lib/harvesting.py](lib/harvesting.py)): rather than BFS-shortest-pathing to a target and reactively pausing to cool once heat crosses `HEAT_SAFE_CEILING`, it prices each candidate hop by its heat cost (a hop onto an item sector costs 1 heat, an empty sector costs 7 — measured from the machine's own heat rules) and greedily prefers routes that thread through item cells, since "on a scattered map the hours spent cooling outnumber the hours spent moving about 3 to 1." It also selects the next target by value-per-Manhattan-step rather than nearest-first, and experimented with (then measured against and disabled) a "leave junction cells standing as cheap road" heuristic — worth reading as a documented negative result, not just the positive pattern.

- [ ] Consider whether `find_path`/target selection in `lib/harvesting.py` could reduce total cooldown time by preferring hops that land on item sectors (1 heat) over empty ones (7 heat) when a route has a choice of equally-short paths, and by ranking candidate targets on value-per-distance instead of pure distance — a proactive heat budget instead of the current reactive pause-at-ceiling/resume-at-floor policy. Only pursue if `docs/components/harvester.md` confirms the same 1/7/9 heat-per-action figures this reference used (these may be specific to that reference's own measurements, not necessarily an official constant), and only if real playtesting shows meaningful idle-cooldown time on our own map density.
  - Reference: [inspirations/vakermit/scripts/harvesting/harvester_1.py](inspirations/vakermit/scripts/harvesting/harvester_1.py) (`is_bridge()`, `choose()`, `go()`)

## Biology: Signal-Bus Job-Queue Economics (Reviewed 2026-09-16)

`vakermit/scripts/bio/mid/*.py` implements a materially more advanced 3-machine biology pipeline than its own `early/` tier (which is close to our current design): the Exchange becomes an explicit planner publishing `bio.plan` (active order + net remaining) and `bio.jobs` (one queued collection job per still-needed sample, consumed exactly once so multiple Collectors across outposts split the work without double-collecting), while the Lab publishes `bio.prices` (real reagent cost per fragment, learned from `analyze()` and persisted to the Data Archive) so the Exchange can rank orders by **actual margin** (reward minus reagent cost) instead of a rarity proxy — falling back to the rarity-weighted proxy only for not-yet-analyzed fragments, and switching a `scout` flag to bias the Collector toward pricing unknowns when an order's margin is still an estimate. It also gates order selection on `serviceable_biomes()` (only bid on an order whose biome has a *powered* Bio Collector at some outpost) and degrades cleanly to the early-tier's read-the-Exchange's-active-order-directly behavior when the Signal Bus is absent.

This lines up with several already-open items in Biology and Logistics above (bio heartbeats, freshness-aware demand fallback, contract scoring) and adds one further idea:
- [ ] Consider a `bio.prices` channel — reagent cost per fragment learned from `analyze()`, persisted in `archive`/Data Archive and broadcast — so a Bio Exchange can score competing Bio Orders by real margin (reward minus reagent cost) rather than the current implicit "first incomplete order" or a rarity-only proxy. Use the learned price only once known; fall back to a rarity-weighted estimate (average learned cost per rarity point) for anything not yet analyzed, and bias collection toward unpriced fragments while an order's margin is still an estimate.
- [ ] Consider gating Bio Order selection on biome coverage: only activate an order whose required fragment's biome has an actual powered Bio Collector, discovered via `outpost_network` rather than assumed.
  - Reference: [inspirations/vakermit/scripts/bio/mid/bio_exchange_1.py](inspirations/vakermit/scripts/bio/mid/bio_exchange_1.py), [inspirations/vakermit/scripts/bio/mid/bio_lab_1.py](inspirations/vakermit/scripts/bio/mid/bio_lab_1.py), [inspirations/vakermit/scripts/bio/mid/bio_collector_1.py](inspirations/vakermit/scripts/bio/mid/bio_collector_1.py)
- `vakermit/scripts/bio/early/*.py` reviewed too: close to our current bio pipeline's shape (Collector reads the Exchange's active order directly, no persisted pricing) — nothing further to adopt from that tier specifically.

## vakermit Factory & Sensor Scripts (Reviewed 2026-09-16, Not Actionable)

- `scripts/factory/{fabricator_1,smelter_1}.py` — a recursive bill-of-materials resolver (Fabricator) and demand-vs-floor batch chooser (Smelter) over `factory.needs`/`factory.ore` Signal Bus channels. Same shape as our already-completed dependency-graph demand cascade (`lib/production.py`, `lib/fabricator.py`, `lib/smelter.py`) and multi-machine claim coordination (Phase 3 Phase A) — nothing new to adopt.
- `scripts/harvesting/scanner_1.py` — full-grid sweep skipping already-`get_scanned()` sectors; matches our own `scanner_1.py`'s behavior per TODO.md.
- `scripts/sensor/{oxygen_sensor,pressure_sensor,uplink}.py` — trivial one-off calibration scripts; equivalents already completed per TODO.md Phase 1.
- `scripts/atmos/{heater_1,pressure_1}.py` — a probe-and-learn state→power table (heater) and a plain sync-window loop with rate learning (pressure); both less capable than our weather-tracked `HeatController` and resonance-sweep `PressureController` (`lib/terraforming.py`). Not actionable, though `pressure_1.py`'s "warn when the gauge's measured per-tick rate exceeds the window width — no script could hit it" is a reasonable defensive check to consider adding to our own `PressureController` if a save ever produces an unusually fast sweep.
- `tools/README.md` (`build_docs.py`) — a separate offline tool that extracts the game's embedded API/manual docs from the game's own executable into Markdown, located by content-anchored search (never by filename/offset, so it survives game updates) rather than a fixed binary layout. Purely informational: useful only if `docs/` in this workspace ever needs refreshing after a game update, and is a standalone tool outside this repo's `lib/` scope — not something to build here. Not run (would require pointing it at the live game install, an action outside this workspace).
- `tools/{build_docs,jsparse,pe}.py` (the extractor's actual code) — skipped by operator decision: pure reverse-engineering/binary-parsing utility code, not game automation, not worth review time.

## Engineering Quality

- [ ] Adopt a capability-first import convention for new libraries:
  - [ ] Machine scripts remain tiny entry points.
  - [ ] Libraries receive the machine object explicitly.
  - [ ] Optional components degrade cleanly.
  - [ ] No new hardcoded machine ids when discovery is available.
- [ ] Add result-status groups/helpers for common transient, capacity, research, and capability failures.
  - Reference: [inspirations/graviadaemon/lib/results.py](inspirations/graviadaemon/lib/results.py)
  - A standalone (unattributed) reference file, [inspirations/classes](inspirations/classes), sketches one concrete way to shape this: a `CommandStatusWrapper(callbacks={...})` decorator that wraps a machine action, returns `True` on `status == "ok"`, dispatches to a named per-status callback (e.g. `"complete": OrderWasCompletedCallback`) when one is registered, and otherwise falls through to a generic once-per-failure `notify(...)`. That is a more declarative shape than a chain of `if res.status == ...` branches and pairs naturally with a `lib/results.py`-style status-group helper — the wrapper's callback dict would key off group names instead of exact statuses. The same file's `BaseMachine` (postInit/tick/InputCommandLoop hooks around a `while True` loop with a broad `except Exception` per tick) is a reasonable shape for a single OOP class-based controller, but does not fit cleanly with this codebase's existing convention of thin functional entrypoints calling `lib/` controller objects — not recommended as a wholesale replacement, only the decorator idea is worth lifting.
- [ ] Add once-per-session warning helpers for recurring blocked conditions.
- [ ] Add focused test doubles or offline validation for:
  - [ ] Empty/missing optional components.
  - [ ] Stale Signal Bus values.
  - [ ] Full Inventory and full output buffers.
  - [ ] Locked recipes and missing source nodes.
  - [ ] Paused construction jobs.
  - [ ] Vehicle rescue and return-to-station transitions.
- [ ] Add a documentation convention for every shared library:
  - [ ] Public entry points.
  - [ ] Required modules/research.
  - [ ] Status handling.
  - [ ] Persistence keys and bus channels.
  - [ ] Recovery behavior.
  - Reference: [inspirations/graviadaemon/docs/libraries.md](inspirations/graviadaemon/docs/libraries.md)
- [ ] Keep the inspiration submodule pinned and review upstream changes deliberately before adopting them.

## Ideas to Defer or Adapt Carefully

- [ ] Consider replacing hardcoded `rover_1`, `smelter_1`, and `supply_dock_1` lookups only after a discovery helper can preserve current behavior.
- [ ] Consider a full five-panel Control Room only after the game save has the required panel support and dashboard APIs.
- [ ] Consider splitting `lib/vehicle.py` into smaller vehicle, navigation, energy, and recovery libraries only when the current file becomes difficult to test.
- [ ] Do not copy the inspiration repository's coordinates, research assumptions, or machine ids into this save.
- [ ] Do not replace working game-specific loops solely to match the inspiration repository's naming or layout.

## Source Notes

- Inspiration repository: [inspirations/graviadaemon](inspirations/graviadaemon)
- Current roadmap: [TODO.md](TODO.md)
- Inspiration commit reviewed: `3f6118a` (`Added new changes, and documentation`)
- Primary inspiration files reviewed:
  - [README.md](inspirations/graviadaemon/README.md)
  - [lib/caps.py](inspirations/graviadaemon/lib/caps.py)
  - [lib/bus.py](inspirations/graviadaemon/lib/bus.py)
  - [lib/scout.py](inspirations/graviadaemon/lib/scout.py)
  - [lib/pioneer.py](inspirations/graviadaemon/lib/pioneer.py)
