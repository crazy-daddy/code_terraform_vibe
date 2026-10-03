# Code: Terraform — AI Agent Quick Reference Cheat Sheet

Dense ref: physics, formulas, component specs, bus channels, data conventions.
**Single source of truth for tunable numbers and definitions** for every agent on project — this hub plus the topic files in [`cheatsheet/`](cheatsheet/). Change tunable constant in code (safety margins, tiers, thresholds, stale-tick counts, budgets, etc.) → update the section that documents it, same change. Other docs (`CLAUDE.md`, `TODO.md`) point at constant/module name, not restate value — one place to keep current.

**Current state only.** Describe what the code does now — no "previously", "was changed", "bug fixed on …", "found live" narration. *Why* behind design (postmortems, rejected approaches, history) → **[`DESIGN_HISTORY.md`](DESIGN_HISTORY.md)** and commit messages.

### Section index

Section numbers are stable; code comments cite them as `AI_CHEATSHEET.md §2c` etc. Find the file here.

| § | Topic | File |
| :--- | :--- | :--- |
| 0, 0a, 0b | `lib/` module map, runtime limits, `TreeConsole` logging, `swallowed()` | this file |
| 1 | Terraforming formula table | this file |
| 1a, 1a-0, 1a-1 | Brownout load-shedding, steam-aware Power Guard, grid ownership | [`cheatsheet/power_fluids.md`](cheatsheet/power_fluids.md) |
| 1b, 1c, 1c-1, 1c-2, 1c-3, 1c-4 | Steam loop, fluid routing, Fluid Pump, Oil Generator, Steam Condenser, Mk III terraforming fluid feed, Mk IV rod magazine, Reactor heat control | [`cheatsheet/power_fluids.md`](cheatsheet/power_fluids.md) |
| 1d, 1d-1, 1d-2, 1d-3 | Tick-cost profiling, script cost model (cost scales with running-script count), script parking, machine activity (retire candidates) | [`cheatsheet/dev_workflow.md`](cheatsheet/dev_workflow.md) |
| 1e–1h-1 | Bio pipeline (Luminizer, backlog gate, biomes, essence/Mixer, biomass-complete retirement) | [`cheatsheet/bio_seeds_planting.md`](cheatsheet/bio_seeds_planting.md) |
| 1i, 1k | Seed discovery sweep, planting (layout, Harvester, field machines, Terraformer) | [`cheatsheet/bio_seeds_planting.md`](cheatsheet/bio_seeds_planting.md) |
| 1l | Wildlife game data: revival, stages, per-species fluids, bands, Insight, traits; revival/Insight schedule (§1l-1); Wildlife automation: planner, Habitat, Feed Maker (§1l-2) | [`cheatsheet/wildlife.md`](cheatsheet/wildlife.md) |
| 1j, 1m, 1n | Field Mining Drill telemetry, Weather Station signal decoding, Fuel Assembler + Lead Cask roles | [`cheatsheet/production_logistics.md`](cheatsheet/production_logistics.md) |
| 2, 2a | Vehicle table, vehicle energy budgeting, claims, recall, navigation | [`cheatsheet/vehicles_drones.md`](cheatsheet/vehicles_drones.md) |
| 2a-0 … 2a-3 | Supply Dock, demand cascade, multi-Fabricator/Smelter/Dock, per-site order trees, `SourceCache` | [`cheatsheet/production_logistics.md`](cheatsheet/production_logistics.md) |
| 2b, 2b-1 | Vehicle mining, Pioneer roles, Pioneer auto-upgrade | [`cheatsheet/vehicles_drones.md`](cheatsheet/vehicles_drones.md) |
| 2c, 2d | Storage management, outpost ore assignment | [`cheatsheet/production_logistics.md`](cheatsheet/production_logistics.md) |
| 2e, 2f, 2g | Stationed mining, hauler role (pulls to HOME_BASE), remote Bio Lab reagent resupply | [`cheatsheet/vehicles_drones.md`](cheatsheet/vehicles_drones.md) |
| 2h, 2j, 2j-1, 2k, 2k-2, 2k-4 | Drones (energy, home, claims, depot, service), drone hauler, aftermath collector, fleet upgrade, fleet commissioning, fleet decommissioning | [`cheatsheet/vehicles_drones.md`](cheatsheet/vehicles_drones.md) |
| 2i, 2i-1, 2k-1, 2k-3 | Pull logistics + reverse hauler, factory outpost site supply requests + stranded ore/goods eviction, Warehouse → Large Warehouse, Liquid Tank → Large Liquid Tank | [`cheatsheet/production_logistics.md`](cheatsheet/production_logistics.md) |
| 2l | Cash manager (budget owner for every Shop purchase: floor, priority, savings goal, income/ETA) | [`cheatsheet/production_logistics.md`](cheatsheet/production_logistics.md) |
| 3, 5, 6 | Biome colors, hardware catalog, invocation pattern | this file |
| 4 | Signal Bus channels, Data Archive keys | [`cheatsheet/archive_ipc.md`](cheatsheet/archive_ipc.md) |
| 7 | Control Room panels | [`cheatsheet/panels.md`](cheatsheet/panels.md) |
| 8, 8a, 9, 10 | Live debugging, sim fast-forward via WebView2 DevTools, tiered `scripts/` + `scripts_sync.py`, offline stub tests (`tests/`) | [`cheatsheet/dev_workflow.md`](cheatsheet/dev_workflow.md) |
| 11–11j | Autoplay infrastructure planner (`autoplay/`): map tile geometry, footprints, router, utility-layer occupancy, power pass, blueprint queue, power-line ledger, fluid pass, outpost roles, extractor pass and urgency tiers (plan-ahead chunks), outpost needs, site scoring and proposals with marker approval (founding planner) | [`cheatsheet/autoplay.md`](cheatsheet/autoplay.md) |

## 🗺️ Progression Walkthroughs & Speedrun Guides

High-level workflows, progression roadmaps, automation orchestration → dedicated walkthrough guides:

- **[`manual_walkthrough.md`](../early_game_runner/manual_walkthrough.md)**: **Manual Progression Roadmap (0 $\rightarrow$ 1,000,000 TP Victory)**
  - Manual progression playbook: First Contact onboarding, Earth Clearance contract solvers (+3,750 cr & +22,500 cr), research prereqs, critical bottleneck matrix, chronological phases from Phase 0 (Cold Boot) to Phase 7 (Deep Biome, Nuclear Reactor Recovery & Endgame Victory).
- **[`auto_walkthrough.md`](../early_game_runner/auto_walkthrough.md)**: **Autonomous Architecture & Early Speedrunner (0 $\rightarrow$ 150,000 TP)**
  - Hands-off automation blueprint: Master Automation Architecture, revised 25-slot Nocturna Base speedrun, `solar_1.py` master building-buyer (auto buy/deploy/sell cycles), `early_game_runner/early_game.py` speedrunner daemon & machine watcher, Earth Clearance contract solvers, 150k TP mid-game migration protocol to `lib/`.
- *(Top-level nav hub: [`walkthrough.md`](../early_game_runner/walkthrough.md))*

## 🧱 0. Shared Library Module Map (`lib/`)

> Physical location: `scripts/<tier>/lib/<module>.py` (tiered, see §9 in [`cheatsheet/dev_workflow.md`](cheatsheet/dev_workflow.md)) — not flat top-level `lib/`. `devtools/scripts_sync.py` resolves right copy per module per active tier, mirrors into save folder's `lib/`. Module names below logical; nearly all currently under `scripts/4_controlpanel/lib/` — tier codebase actually written/tested against (see §9).

| Concern | Module(s) |
| :--- | :--- |
| Terraforming (heat/pressure/O2) | `terraforming.py` (`HeatController`, `PressureController`, `OxygenController`; `Mk3FluidFeed` routes Mk III `steam_in`/`water_in`, §1c-3) |
| Power grid & brownout | `power.py` (`PowerGridManager` — generic, solar/oil/reactor/turbine grids, owned centrally by control_room_automation.py, one instance per grid, no election — see §1a-1); `solar.py` (`SolarController` — pure sun tracking, no grid supervision) |
| Vehicles (Rover/Pioneer base) | `vehicle.py` (`VehicleController`, composes mixins below) |
| &nbsp;&nbsp;↳ driving / stall recovery | `vehicle_navigation.py` |
| &nbsp;&nbsp;↳ battery accounting / trip budgeting / charging-station discovery | `vehicle_energy.py` |
| &nbsp;&nbsp;↳ fleet-wide target claims & hardware blacklist | `vehicle_claims.py` |
| &nbsp;&nbsp;↳ cargo offload into Inventory / Warehouse | `vehicle_cargo.py` |
| &nbsp;&nbsp;↳ sonar survey loop (POI discovery) | `vehicle_survey.py` |
| &nbsp;&nbsp;↳ mineral-site discovery & drill execution | `vehicle_mining.py` — shared Rover + Pioneer; see §2b |
| &nbsp;&nbsp;↳ in-flight mining yield reservation (non-exclusive, overmining guard) | `mining_reservations.py` — see §2b |
| &nbsp;&nbsp;↳ shared live telemetry dict `fleet.status` (vehicles + drones) | `fleet_status.py` — see §4 |
| &nbsp;&nbsp;↳ job intent line + demand-root attribution ("hauling X from A to B for supply_dock_1") | `fleet_intent.py` — see §4 |
| &nbsp;&nbsp;↳ auto Pioneer hardware tier upgrades (Sonar/Drill/Holder/Rack) + manual Sport Nav request | `vehicle_upgrade.py` — Pioneer-only, mixed into `PioneerController` only, never `VehicleController`; see §2b-1 |
| Rover / Pioneer specializations | `rover.py`, `pioneer.py` — thin `VehicleController` subclasses; **no** shared vehicle logic here |
| Harvesting (grid survey/collection) | `harvesting.py` (`HarvesterController`) |
| Smelting | `smelter.py` |
| Production planning (demand-driven) | `production.py` |
| Supply Dock logistics | `supply_dock.py` |
| Biology, shared pipeline (collector/lab/exchange + biome-processor discovery) | `bio.py` — outpost-aware (Warehouse-only outposts, no Inventory) throughout, biome-agnostic; see §1g/§2g |
| &nbsp;&nbsp;↳ Coastal biome processor (glow-tint) | `bio_coastal.py` (`BioLuminizerController`) — see §1e/§1g |
| &nbsp;&nbsp;↳ Volcanic biome processor (forge-cast) | `bio_volcanic.py` (`BioCasterController`) — see §1g |
| &nbsp;&nbsp;↳ Geothermal biome processor (gene-splice) | `bio_geothermal.py` (`DnaSequencerController`) — see §1g |
| &nbsp;&nbsp;↳ Deep biome processor (QC quiz, automated) | `bio_deep.py` (`BioConditionerController`) — see §1g |
| Outpost reagent stock-target scaffolding (Bio Lab resupply) | `outpost_reagents.py` — see §2g |
| Vehicle charging stations | `charging.py` |
| Drones (scout/miner/hauler base) | `drone.py` (`DroneController`, composes mixins below — see §2h) |
| &nbsp;&nbsp;↳ go_to()/go_to_station()/go_to_drill() wrappers, arrival polling | `drone_navigation.py` |
| &nbsp;&nbsp;↳ engine auto-detect (electric/heli), linear per-meter trip budgeting, drone_service/drone_depot discovery | `drone_energy.py` — see §2h |
| &nbsp;&nbsp;↳ exclusive biosite claims + scout empty-POI cache + mission persistence | `drone_claims.py` — see §2h |
| &nbsp;&nbsp;↳ cargo accounting/load-unload + home-biome filtering | `drone_cargo.py` |
| &nbsp;&nbsp;↳ scout role loop (POI bio-scanning) | `drone_scout.py` |
| Survey request areas scouts serve first (`autoplay.survey_requests`) + sonar `wrong_scanner` contacts as known biomass | `survey_requests.py` — see `docs/cheatsheet/autoplay.md` §11j |
| &nbsp;&nbsp;↳ miner role loop (biosite extraction) | `drone_mining.py` |
| &nbsp;&nbsp;↳ floating hauler role loop (drills and Depot outposts → Depots, no home) | `drone_hauler.py` — see §2j |
| &nbsp;&nbsp;↳ aftermath collector role loop (plated drone: Raw Uranium + Storm Glass) and the hauler's Storm Glass pickup | `drone_weather.py` — see §2j-1 |
| &nbsp;&nbsp;↳ fleet-upgrade handshake, new-chassis fitting, in-place module upgrades (+ shared `fleet.upgrade` state helpers) | `drone_upgrade.py` — see §2k |
| Fleet hardware upgrade coordinator (Depot + drone chassis swaps), run by the `control_room_automation.py` Automation | `fleet_upgrade.py` — see §2k |
| New Pioneers and drones from the COMMISSION card (queue, buy or craft, deploy, wait for script), run by the `control_room_automation.py` Automation | `fleet_commission.py` — see §2k-2 |
| &nbsp;&nbsp;↳ Constructor Pioneer job scan (pure, atomic slices: claim/cargo filter, `construction.priority` then nearest-first order, station range check, progress lookup) | `construction_plan.py` — see `docs/cheatsheet/vehicles_drones.md` §2a |
| &nbsp;&nbsp;↳ Pioneer role presets, shared `fleet.commission` state, `PioneerFittingMixin` (the new Pioneer mounts/installs its own parts) | `pioneer_commission.py` — see §2k-2 |
| &nbsp;&nbsp;↳ drone presets (best craftable chassis + `LOADOUTS` modules), `fleet_commission` upgrade-order requester | `drone_commission.py` — see §2k-2 |
| Retiring Pioneers and drones from the FLEET / DRONE FLEET retire buttons (recall, unload, undeploy, sell Pioneer parts, archive cleanup), run by the `control_room_automation.py` Automation | `fleet_decommission.py` — see §2k-4 |
| Warehouse pair → Large Warehouse swap (buy, deploy, greedy drain, undeploy, sell), run by the `warehouse_upgrade_automation.py` Automation | `warehouse_upgrade.py` — see §2k-1 |
| Cash manager: `can_spend()`/`spent()` gate for every Shop purchase, income + floor pass in the `control_room_automation.py` Automation | `cash.py` — see §2l |
| Liquid Tanks (≤ 5 of one liquid) → Large Liquid Tank swap (buy, deploy, retire via `tank_assignments`, pipe drain, undeploy, sell), same `warehouse_upgrade_automation.py` Automation | `tank_upgrade.py` — see §2k-3 |
| Drone Service Station (charging/refuelling/rescue) | `drone_service.py` — see §2h |
| Drone Depot (cargo logistics endpoint) | `drone_depot.py` — see §2h; drains freight to local storage, buffers life forms in a local Warehouse (two stacks per form), stages hauler pickups, flushes surplus |
| Depot staging requests (hauler → source Depot) | `depot_stage.py` — see §2j; `depot.stage` archive dict |
| Pull logistics (outpost item requests, need/buffer tiers, fair share, in-flight pickups, source retention) | `logistics_requests.py` — see §2i; reverse hauler lives in `vehicle_cargo.py` `run_pull_loop()` |
| Factory outpost site supply (per-outpost ingot/ore/finished-root requests, stranded ore and ingot/intermediate eviction), run by the `control_room_automation.py` Automation | `site_supply.py` — see §2i-1 (tier 5 lib, deployed at every tier) |
| Fab site plan (which fab outposts build each root target's tree), run by the `control_room_automation.py` Automation | `site_plan.py` — see §2a-0-6 (tier 5 lib, deployed at every tier) |
| Seed Maker (fair recipe sweep, stage A) | `seed_maker.py` — see §1i (tier `6_seeds`) |
| Seed Maker on-demand seed production (stage B, once all 15 recipes are known) | `seed_supply.py` — see §1k (tier `6_seeds`; `bio/seed_maker.py` dispatches on `len(recipes())`) |
| Field layout (species rules, starter block, full-field layout in automator chunks, rarity-weighted expansion; pure logic) | `field_layout.py` — see §1k (tier `8_planting`) |
| Plant Terraformer (feed Forage/Water/Salt/Fertilizer/Accelerant, batch run policy) | `plant_terraformer.py` — see §1k (tier `8_planting`) |
| Plants completion: undeploy emptied Plant Terraformers | `plants_retire.py` — see §1k (tier `8_planting` lib, deployed from `2_libunlock` on like every new-only module; driven by `control_room_automation.py`, idles until a Terraformer reports `complete`) |
| Planting Harvester (plant, tend, harvest the layout) | `field_keeper.py` composes `harvester_heat.py` (`HarvesterHeatMixin`: heat-cheapest routes, just-in-time rests, live heat calibration; overrides `move_to()`/`cool_down()`) + `harvester_paving.py` (`HarvesterPavingMixin`: items dropped on a path joining the plant patches) + `harvester_planting.py` (`HarvesterPlantingMixin`: layout, seed demand, plant, harvest) + `harvester_care.py` (`HarvesterCareMixin`: light/water/salt, salt request) + `harvester_machines.py` (`HarvesterMachinesMixin`: field-machine kits) + `harvesting.py` `HarvesterController` (movement, heat, loose-item sweep) — see §1k (tier `8_planting`) |
| Field machines (kit orders/pre-orders + deploy on reserved cells; Grow Lamp / Sprinkler / Dispenser controller; Crop Automator job controller) | `harvester_machines.py` (`HarvesterMachinesMixin`, mixed into `field_keeper.py`) + `harvester_amplify.py` (`HarvesterAmplifyMixin`, Yield Amplifier apply + order) + `field_provider.py` (`FieldProviderController`, thin `harvesting/grow_lamp.py`/`sprinkler.py`/`dispenser.py`) + `crop_automator.py` (`CropAutomatorController`, thin `harvesting/crop_automator.py`) — see §1k (tier `8_planting`) |
| Wildlife model (game constants, growth/Insight/bonus model, revival schedule; pure) | `wildlife_data.py` (constants, `WILDLIFE_SCHEDULES` per Habitat count) + `wildlife_model.py` (rate, stages, fluids, bonuses, Insight, `schedule_for()`); schedule solved offline by `devtools/wildlife_optimizer.py` — see §1l (tier `9_wildlife`) |
| Wildlife automation (revival schedule walk, feed demand, Forage reserve, life-form requests; Habitat revival/feed/fluid bands/parking; demand-driven feed crafting) | `wildlife_planner.py` (run by `control_room_automation.py`) + `habitat.py` + `feed_maker.py` (thin `bio/habitat.py`, `bio/feed_maker.py`), shared keys/tunables `wildlife_common.py` — see §1l-2 (tier `9_wildlife`) |
| Water Pump byproduct salt as pull-hauler source; home salt request (field + Terraformers to 5m km²) | `pump_salt.py` — see §2i and §1k Salt budget (tier 4 lib, imported by `vehicle_cargo.py` and the Control Room Automation) |
| Field Mining Drill telemetry (fill, time-to-full, stall warnings, pickup advert) | `mining_drill.py` — see §1j (tier `7_miningdrills`) |
| Weather Station signal decoding (storm aftermath coordinates for Raw Uranium / Storm Glass) | `weather_signals.py` — see §1m (tier `7_miningdrills`) |
| Fuel Assembler (Fuel Rods for local Reactors / Mk IV generators, then Nuclear Batteries; reserve-gated bursts) | `fuel_assembler.py` — see §1n (tier `10_nuclear`) |
| Reactor (measured-gain heat control just under 900 °C, rod feed from local Lead Casks, cooling water routing, water reservation publisher) | `reactor.py` — see §1c-4 (tier `10_nuclear`) |
| Lead Cask roles (`lead_cask.roles`), hot-cargo stock/room/take, misfiled-uranium repair | `lead_cask.py` — see §1n (tier 4 lib; used by `drone_weather`, `supply_dock`, `terraforming`, `production`) |
| Field Mining Drills as pull-hauler sources (recorded positions, connect/take) | `drill_sites.py` — see §2i (lives in tier 4 lib, since the hauler imports it at every tier) |
| Fabrication | `fabricator.py` |
| Thermal Cap (steam capture, anti-overpressure) | `thermal_cap.py` |
| Steam Turbine (steam-to-grid power) | `steam_turbine.py` |
| Water Pump / Oil Pump (route well output to network Liquid Tanks) | `fluid_pump.py` `FluidPumpController(pump, fluid_id)` — see §1c, simpler cousin of `thermal_cap.py` (no overpressure/relief); `water_pump.py` = compat shim for old save slots |
| Exotic Gas Cap / Exotic Spring Tap (route deposit fluid to network tanks) | `exotic_cap.py` `ExoticCapController(cap)` (tier 9): `FluidPumpController` subclass, Gas Tanks for a Cap, Liquid Tanks / Large Liquid Tanks for a Tap, `fluid_id` = `deposit().fluid()`; valve always open; parks only through a long dormant phase (see dev_workflow.md §1d-2) |
| Refiner (purify raw exotic gas/liquid + tar into creature-grade fluids) | `refiner.py` `RefinerController(refiner)` (tier 9): refines the fluid with the emptiest tanks among those with raw stock (dwell + margin against flip-flop), routes raw from and refined to network tanks, tar from local storage (stockpile via `site_supply`); soft-shed Tier 2 by `clear_recipe()`; parks when idle — see wildlife.md |
| Oil Generator (last-resort power) | `oil_generator.py` — see §1c-1 (tier 5+) |
| Steam Condenser (steam → water, steam-reserve and water-fill guards) | `steam_condenser.py` — see §1c-2 (tier 5+) |
| Essence Liquifier (Depot → sample feed, essence → Liquid Tank) | `essence_liquifier.py` — see §1h (tier 5+) |
| Biomass Mixer (keep all five essence inputs sourced) | `biomass_mixer.py` — see §1h (tier 5+) |
| Biomass Mixer duty-cycle gate (breaker pause until all expected essences refilled) | `biomass_mixer_gate.py` — see §1h (lives in tier 5 lib, deployed from `2_libunlock` on like every new-only module; driven by the single `control_room_automation.py`, idles without Mixers) |
| Biomass completion: retire Liquifiers/Mixers, sell button | `biomass_retire.py` — see §1h-1 (tier 5 lib; imported by `drone_mining.py`/`drone_depot.py`/`status_panel.py`/`control_room_automation.py`) |
| Waste Processor base (idle: switched off, staged input returned; destroys no items) | `waste_sink.py` — see §1h-1 (tier 5) |
| Waste Processor water overflow (last-resort drain when every Water tank at the outpost is full and a Water Pump stalls) | `water_sink.py` — see §1c (tier 5) |
| Shared network-wide fluid-target discovery/blacklist/reconnect | `fluid_routing.py` — `FluidOutputRouter` (`thermal_cap.py`/`fluid_pump.py`/`essence_liquifier.py`/`steam_condenser.py`), `FluidInputRouter` (`steam_turbine.py`/`fabricator.py`/`biomass_mixer.py`/`oil_generator.py`/`steam_condenser.py`/`terraforming.py`); see §1b |
| Storage management (Warehouse-aware sourcing/unloading, Inventory rebalancing) | `storage.py` — see §2c |
| Outpost ore-assignment & stock-target scaffolding (multi-outpost mining) | `outpost_mining.py` — see §2d |
| Data Archive persistence layer | `archive.py` |
| Game version safety gate (halt on build change until operator confirms) | `version_guard.py` — see §4's `system.good_version`/`system.version_confirmed` entries and §7 |
| Wildcard pattern matching helpers | `patterns.py` |
| Per-script tick-cost profiling | `profiling.py` — see §1d |
| Structured, indented console logging (`debug()`-level decision tracing) | `tree_console.py` (`TreeConsole`) — see §0a |
| Logging caught-and-recovered exceptions (`swallowed(where, error)`) | `swallow.py` — see §0b; imports nothing, so even `archive.py` uses it |
| Heavy pure computations as one unit (`run_atomic(fn, *args)`, `run_batched(fn, items, size, *args)`, `run_chunked(step_fn, state)`, `ATOMIC_ENABLED` switch) | `atomic.py` — see `docs/cheatsheet/dev_workflow.md` §1d-1 |
| Turbine commitment (runs just enough Steam Turbines, parks the rest; per-turbine steam aware; called from `PowerGridManager.supervise_grid()` before the guard) | `turbine_commit.py` (tier 5) — see `docs/cheatsheet/power_fluids.md` Steam Turbine |
| Script parking (idle machines' breakers off, solar scripts stopped at night; `ParkRequester` machine side, `ScriptParking` in `control_room_automation.py`) | `script_parking.py` — see dev_workflow.md §1d-2 |
| Script census (counts running scripts every `CENSUS_TICK_INTERVAL = 300` ticks, logs `scripts running: N of M machines, allowance A steps/tick` for `devtools/log_block_timing.py`; called from `control_room_automation.py` `park_if_due()`) | `script_census.py` — see dev_workflow.md §1d-1 |
| Machine activity (per-machine and per-group active/waiting/idle/running/parked/off time shares and `retire` candidates, archive `machine.activity`; sampled from each census snapshot by `control_room_automation.py`) | `machine_activity.py` — see dev_workflow.md §1d-3 |

Root executable scripts (`solar_1.py`, `rover_1.py`, `control_room_automation.py`, etc.) stay thin entrypoints: import + run controller from `lib/`. No own copies of tier lists, thresholds, budgeting formulas.

**No real stdlib — only the game's executable built-in modules** (`docs/guide/programming_language_reference.md`'s "Imports & Libraries" section authoritative; the exact allowlist is in [`cheatsheet/dev_workflow.md` §10](cheatsheet/dev_workflow.md), enforced by `tests/test_game_imports.py`). They are small in-game reimplementations, not CPython modules: check a function exists in `docs/guide/builtins_and_commands.md` before using it. `sys`, `os`, `time`, `copy` etc. **don't** exist at runtime. `typing`, `types`, `collections.abc`, `user_stubs` exist ONLY for editor/Pyright annotations — erased at runtime (`typing.TYPE_CHECKING` always `False` in-game; `typing.NamedTuple` is the one that runs).

**Type tests**: after `from __builtins__ import Smelter` (any game class, incl. `Component`), `isinstance`/`issubclass` work on machines; `type_id` names the type and can't be written. `match` supports class patterns (`case Circle(radius=r):`, `case int(n) | float(n):`). The in-game editor honours `# type: ignore` / `# noqa` per line (a top-of-file `# type: ignore` quiets the whole script).

**Parser/builtin limits**: no multi-line parenthesized imports — `from x import (a, b)` is a `SyntaxError` in-game, write one-line imports. No `frozenset` — use tuples; check a builtin against existing `lib/` usage before relying on it.

**Remote writes are blocked** (decompiled simworker, `api.remote_write_blocked`): on a component fetched with `get_component()` for another machine, every non-read-only method raises `PermissionError` ("hardware methods only work from the machine's own script"), and so does every state-changing method of its sub-objects: `NavModule.set_target`/`set_throttle`/`brake`, `FluidPort.connect`/`disconnect`, `InputSlot`/`OutputSlot` `connect`/`disconnect`/`take`/`eject`/`flush`/`send`, `DroneCargo.load`/`unload`/`discard`, `SonarModule`, `DrillModule`, `ConstructorModule`. Reads work. Exempt (`allowsRemoteWrites`): `shop`, `power_control`, `run_control`, `inventory`, `transmitter`, `storage_bin`, `comms`, `console`, `markers`, `notebook` (archive), `construction_blueprint`, `computer`, gas/liquid tanks, bulk reservoir, Warehouse, Large Warehouse, Lead Cask. The *(self only)* badge in docs marks exactly these. So cross-machine control goes through a signal the target's own script reads (archive, Signal Bus) or through the breaker (`power_control`, exempt).

**Breaker** (`power_control`, decompiled): `can_power_off(id)` is a fixed per-type flag. True for, among others, every factory, dock, generator, pump, turbine, condenser, thermal cap, terraformer, drill, bio machine, seed maker, plant terraformer, crop automator, grow lamp, sprinkler, dispenser, garbage disposal, charging station, drone service station, every drone depot size, and `solar_generator`; false for batteries, scanner, harvester, sensors, vehicles, drones, warehouses and tanks. Off: the machine's running scripts are paused (remembered per machine) and only transient outputs are zeroed (e.g. a machine's running flag, a thermal cap's flows); script setpoints such as `set_enabled` stay. On: only the scripts paused by that power-off resume. Stopping or ending a script instead resets its setpoints (e.g. `set_enabled` → off).

**Import depth limit**: interpreter caps nested import-resolution stack at `maxImportDepth = 256` (`interpreter.maxImportDepth`, confirmed from decompiled simworker — see `internals/` [gitignored, not authoritative game docs]), raises `RecursionError` / `error.import_depth` if exceeded. Current `lib/` chain (entrypoint → `vehicle.py` → mixins, max 2-3 levels) nowhere close — see this error → look for real import cycle.

### 0a. Structured Console Logging (`lib/tree_console.py` `TreeConsole`)

Console output: three detail levels, all same tree format:

- **Overview (info, always visible)** — major blocks + outcomes, beautified, skimmable, no opt-in needed.
- **Reasoning trail (debug, opt-in, always written)** — the *why*: which branch decision took, candidates considered/rejected, computed threshold/estimate values. Hidden from normal ALL view (`docs/components/console.md`'s `console.debug()`), so no spam for non-opted players — reading with debug on should tell whole run story without in-game breakpoint/watch debugger (`§8`). Every console call costs 0.1 s of simulation time, shown or hidden (`docs/BENCHMARK.md`), so consecutive debug lines are buffered into one message (see *Buffering* below). Not for per-item work inside hot loops: that is `trace`.
- **Trace (opt-in per module, gated before reaching `console`)** — truly high-volume noise: method entry/exit, per-item loop detail. `TreeConsole.trace()` true no-op (no `console` call, no disk write) unless `TreeConsole(module=...)`'s module listed `"verbose"` in `console.log_levels` archive dict (`{module_name: "normal"|"verbose"}`, default `"normal"`). Level read once at construction — restart script after editing archive key via Data Archive Notebook, no per-tick re-check. `module` must be passed explicitly (sandbox has no `inspect`/frame introspection); convention: `lib/` filename without extension (e.g. `"power"`, `"vehicle_energy"`). Hot loops and per-item detail belong here, not in `debug()`. When fires, still emits at **debug** level (not custom `"trace"` badge) — `docs/components/console.md`'s `console.print()` only treats `info`/`warn`/`error`/`debug` as filter-feeding; other strings = colored badge in normal ALL view, defeating opt-in gating.

`lib/tree_console.py`'s `TreeConsole` wraps `get_component("console")` with tree-drawn indentation (inspired by `inspirations/discord-panels/`) so levels read like call stack, not flat scroll:

```python
from tree_console import TreeConsole

# Create once in __init__ (or once before a run_*_loop()'s `while True:`), store as
# self.log — never re-construct per call/per tick, since __init__ reads the
# console.log_levels archive dict. Variable/attribute name is `log`, not `tree`
# (the tree-drawing is just formatting, `log` is what it's used for).
self.log = TreeConsole(module="power")  # default_level="info"; grabs get_component("console") itself

self.log.start("Creating tasks")                              # info: visible overview
for task_type in candidates:
    self.log.trace(f"Evaluating candidate {task_type.__name__}")  # trace: no-op unless "power" is "verbose"
    self.log.debug(f"Considering {task_type.__name__}: score={score:.2f}")  # debug: reasoning trail
    self.log.print(f"Creating task {task_type.__name__}")      # info: outcome
self.log.end("Task creation success")

self.log.color("#FF0000").end("Task creation failed")          # one-off color override, next line only
self.log.level("warn").print("Battery below safety floor, aborting trip")  # one-off level override
```

- `start(msg)` / `end(msg)` open/close block, print `┏━`/`┗━` line, indent (`┃   ` per level) everything between — default level **info**.
- `print(msg)` logs one line at current indent, at `default_level` (info) unless overridden via `.level(...)`.
- `debug(msg)` = shorthand for `.level("debug").print(msg)` — in-depth opt-in reasoning trail, nested under info-level blocks. Always written.
- `trace(msg)` same shape at **debug** level (not custom `"trace"` badge — see above), but short-circuits before `console` unless `module=` passed to `TreeConsole(...)` is `"verbose"` in `console.log_levels` (default `"normal"` if `module` omitted/unlisted). Use for method entry/exit + per-item loop noise wanted during active debugging only.
- **Convention**: one `TreeConsole` per controller instance, in `__init__` (or once before `run_*_loop()`'s `while True:` for bare function, not inside), stored as `self.log`/`log` — never re-construct per call/tick, since `__init__` reads `console.log_levels` archive dict. Name it `log` (not `tree` — tree-drawing just formatting, `log` names purpose).
- **Blocks**: one `start()`/`end()` pair per coherent unit of work (trip, order/recipe cycle, build/upgrade/commission, sweep, active tick phase); the `end()` message carries the outcome. Every `start()` is closed on every path (early `return`, error branch, `continue`/`break`), enforced statically by `tests/test_log_blocks_balanced.py` (per-branch depth must match; a loop body must be net zero). No block on idle ticks; no `with` (unsupported in-game) and no reliance on `finally` (a stopped script is killed without unwinding). Mixins log through `self._host.log`. An exception escaping a block leaves its indent open, so each top-level `run*` loop's first statement is `reset_all()` (`from tree_console import reset_all`; drops every instance's open blocks; `tests/test_reset_in_run_loops.py`). Polling loops nested inside a function must not call it.
- **Debug blocks**: `start(msg, level="debug")` … `end()` wraps a function's decision trail. The header is written only once a line is logged inside (an idle block prints nothing), `end()` writes `┗━ END <name>` when the header was shown (nothing otherwise; a message replaces `END <name>`), and the outermost debug `end()` does not flush the buffer (consecutive blocks share one `console.print`). Lines inside drop their own `function_name:` / `[name]` prefix, since the header names it. Convention: any function that can log two or more debug/trace lines in one call opens a debug block as its first statement (after the docstring) and closes it before every `return` (`_ret = expr; log.end(); return _ret` when the expression calls something). `step()`, `run*` loops and functions with their own info block are exempt. For a function with several returns, wrap it: public method does `start` / `_impl()` / `end`. Blocks nest (outer headers are written first, once).
- **Collapsing**: a debug block that logs exactly one line is written as `name: message` (at that line's level) instead of header + line + END. The line carries the time it was logged, plus ` (+4m05s)` for the game time the block then took (omitted when 0). The first line is held back until a second line, a nested block, `end("msg")`, `flush()`, a line from another `TreeConsole` or `reset()` shows it must expand. `console.now()` is a normal cheap call (`docs/BENCHMARK.md`); only `print()`/`debug()`/`sleep()` cost 0.1 s.
- **Warn/error lines are not indented** (the console's own level badge precedes the message, so an indent would not line up); their block's `┏━`/`┗━` lines still frame them. `end()` at warn/error keeps its `┗━`.
- `color(c)` / `level(lvl)` set one-shot override (CSS color / `info`\|`warn`\|`error`\|`debug`\| custom) consumed by *next* `print`/`start`/`end`/`debug`/`trace` call only, then reset to instance default.
- **Buffering** (`tree_console._BUFFER`, one buffer for every `TreeConsole` in the script): `debug`/`trace` lines collect and are written as one multi-line `console.print`; info, `warn` and `error` print immediately after flushing pending debug lines, so order is kept. A run also flushes at a level/channel/color change or a different console object (instances built without `console=` share one cached `get_component("console")`, `_DEFAULT_CONSOLE`), when the outermost `start()`/`end()` block closes, at the size cap, and on `log.flush()` / `tree_console.flush_all()`. `swallowed()` flushes before it prints. Cap = half the interpreter string limit (read once from the `OverflowError` message), at most `MAX_BUFFER_CHARS=20000`, `FALLBACK_BUFFER_CHARS=4000` if unreadable; a longer single line is truncated. A script stopped from the UI is killed without unwinding (`finally` blocks do not run), so lines still buffered then are lost: call `flush_all()` before every `sleep()` and comms wait (`tests/test_flush_before_sleep.py` enforces it for tier 4+). `TreeConsole(buffered=False)` prints its debug lines immediately.
- Info/warn/error lines go through `console.print(..., timestamp=True)`. Buffered debug/trace lines are stamped by `TreeConsole` itself (`console.now()` when the line is logged, `"HH:MM:SS "` prefix) and printed without `timestamp`, so every line of a multi-line message has its own time; works with Console channel/level filters.
- Reserve plain `warn`/`error` for real status changes player should notice without debug output; `debug()`/`trace()` purely detail, never attention-needing.

### 0b. No Silent `except Exception` (`lib/swallow.py` `swallowed()`)

Every broad handler that recovers (returns a default, `continue`s, keeps looping) calls `swallowed()` as its first line:

```python
from swallow import swallowed

try:
    count = port.count()
except Exception as error:
    swallowed("storage.crop_automator_forage: port.count", error)
    continue
```

- `where` = `"module.Class.function: call"`. Append ` #2`, ` #3` when one function has several sites calling the same thing. It is the dedupe key, so keep it unique per site.
- Every caught error → one **debug** line. Identical consecutive errors at one site are logged once, so a per-tick handler can't flood the log.
- "Code bug" types (`TypeError`, `AttributeError`, `NameError`, `KeyError`, `IndexError`, `ZeroDivisionError`) → also one **warn** per site per script run, visible without debug output on. Exception: `AttributeError` on `NoneType`, which is how a missing component (a `None` from `get_component()`) usually surfaces.
- Why: a broad except can't tell "game said no" from "our code is wrong" (e.g. a `TypeError` from a wrong API signature silently reads as "empty").
- **Allowed to stay silent** (with a comment saying why):
  - inside an `archive.transaction()` updater: any log call there rejects the transaction;
  - `swallowed()` itself;
  - narrow handlers that fully handle their case, e.g. `except (TypeError, ValueError)` around a `float()` parse with a fallback, or `except IndexError` as a loop escape.
- Tiers without `lib/` (`0_cold_boot`, `1_early`) use a local `_swallowed()` stand-in (debug only) defined in the script itself.

## ⚡ 1. Core Terraforming & Physics Formulas

| System | Component | Key Formula / Setpoint | Limits & Constraints |
| :--- | :--- | :--- | :--- |
| **Solar Tracking** | `solar_generator` | `tilt = round(sun_elevation)` | 0° (flat) to 90° (vertical). Night output = 0 W. Peak = 50 W. |
| **Oxygen Generation** | `oxygen_generator` | `intake = atmosphere.get_co2() / 10.0` | Power: -8 W. Dump waste when `50 <= waste < 60` (clean dump, 0 penalty). Stalls at 100 waste. |
| **Heat Calibration** | `heat_generator` | `power = 1..10 W` (sweep / cache by weather) | Power: -10 W max. Re-eval optimal power on day/weather change. |
| **Pressure Sync** | `pressure_generator` | Sync pulse with resonance window peak | Power: -10 W max. 100% efficiency on exact resonance window hit. |
| **Power Grid & Brownout** | `power_control`, `battery` | Battery = 500 Wh (300 cr). Safe floor: 15-20% | Configurable shedding tiers (`power.shedding_tiers`) — see §1a for full tier/threshold breakdown. |

## 🗺️ 3. Planet Map Biome Colors (player-observed, verify with `nocturna.biome_at(x, y)`)

| Map Color | Biome |
| :--- | :--- |
| Blue (incl. base's slightly-green patch) | `frozen` |
| Green | `coastal` |
| Dark brown / red | `volcanic` |
| Light brown | `geothermal` |
| Purple | `deep` |

## 🏭 5. Hardware Catalog & Production Specs

| Machine | Price | Power Profile | Storage / Capacity | Primary Function |
| :--- | :--- | :--- | :--- | :--- |
| `solar_generator` | 500 cr | +50 W (Day peak) | N/A | Primary green power gen. |
| `battery` | 300 cr | 0 W (Buffer) | 500 Wh | Grid buffer & night survival. |
| `heat_generator` | 800 cr | -10 W max | N/A | Surface warming. |
| `oxygen_generator` | 1,000 cr | -8 W | 4 units input | Atmospheric CO2 -> O2 conversion. |
| `pressure_generator` | 1,000 cr | -10 W | N/A | Atmospheric pressure builder. |
| `smelter` | 1,500 cr | -20 to -45 W (per active recipe; 0 W idle/not running) | In/Out slots | Ore -> ingots (Iron, Glass, Titanium). No breaker cycling needed. |
| `bio_collector` | 2,500 cr | -5 W | 30 units | Autonomous bio specimen harvesting. |
| `bio_lab` | 5,000 cr | -5 W | 30 in / 30 stock | Specimen analysis, sample extraction. |
| `bio_exchange` | 2,000 cr | -5 W | Orders queue | Earth bio order fulfillment & credit rewards. |
| `bio_luminizer` | 60,000 cr | -12 W | 10 in / 10 out | Coastal glow-tinting (3-lamp mix solve, §1e). |
| `bio_caster` | 150,000 cr | -15 W | 30 out, 20t steam/water buffers | Volcanic forge-casting (heat/cool band control, §1g). |
| `bio_conditioner` | 225,000 cr | -25 W | 10 in / 10 out | Deep QC quiz (automated, §1g). |
| `dna_sequencer` | 100,000 cr | -20 W | 10 in / 10 out | Geothermal gene-splicing (§1g). |
| `supply_dock` | 3,000 cr | -15 W | 50 units | Earth / Contractor campaign bulk order shipping. |
| `vehicle_charging_station`| 2,000 cr | -50 W max | Pad + Rescue drone| Vehicle fast-charge & auto rescue dispatch. |

## 🧩 6. Standard Component Invocation Patterns

```python
# 1. Connect to standard components
atmosphere = get_component("atmosphere")
clock = get_component("clock")
power = get_component("power_control")
comms = get_component("comms")

# 2. Reusable controller pattern
from terraforming import HeatController, OxygenController, PressureController
from solar import SolarController
from power import PowerGridManager
from rover import RoverController
from bio import BioCollectorController, BioLabController, BioExchangeController
from bio_coastal import BioLuminizerController
from harvesting import HarvesterController

# Execute main loop
controller = SolarController(self)
controller.run()
```
