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
  - [X] Then process pending jobs. # See above - never automatically build outposts, as the cost increases permanently!
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
  - [ ] Add a `vehicle.speedmode` toggle (`conserve`/`highspeed`) driving the throttle formulas in `lib/vehicle_energy.py`.
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

## Engineering Quality

- [ ] Adopt a capability-first import convention for new libraries:
  - [ ] Machine scripts remain tiny entry points.
  - [ ] Libraries receive the machine object explicitly.
  - [ ] Optional components degrade cleanly.
  - [ ] No new hardcoded machine ids when discovery is available.
- [ ] Add result-status groups/helpers for common transient, capacity, research, and capability failures.
  - Reference: [inspirations/graviadaemon/lib/results.py](inspirations/graviadaemon/lib/results.py)
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
