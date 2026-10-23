# Shared Library Module Map & Interpreter Limits (§0)

Part of [`AI_CHEATSHEET.md`](../AI_CHEATSHEET.md). Logging (§0a) and `swallowed()` (§0b) live in [`logging_errors.md`](logging_errors.md).

## §0 Shared Library Module Map (`lib/`)

> Physical location: `scripts/<tier>/lib/<module>.py` (tiered, see §9 in [`cheatsheet/dev_workflow.md`](dev_workflow.md)) — not flat top-level `lib/`. `devtools/scripts_sync.py` resolves right copy per module per active tier, mirrors into save folder's `lib/`. Module names below logical; nearly all currently under `scripts/4_controlpanel/lib/` — tier codebase actually written/tested against (see §9).

### Terraforming, power & vehicle base

| Concern | Module(s) |
| :--- | :--- |
| Terraforming (heat/pressure/O2) | `terraforming.py` (`HeatController`, `PressureController`, `OxygenController`; `Mk3FluidFeed` routes Mk III `steam_in`/`water_in`, §1c-3) |
| Power grid & brownout | `power.py` (`PowerGridManager` — per-grid power phase solar/steam/oil/reactor, see §1a; owned centrally by orchestrator_automation.py, one instance per grid, no election — see §1a-1); `power_solar.py` (`SolarNightGuard` — night forecast shedding for solar-only grids); `solar.py` (`SolarController` — pure sun tracking, no grid supervision) |
| Vehicles (Rover/Pioneer base) | `vehicle.py` (`VehicleController`, composes mixins below) |
| &nbsp;&nbsp;↳ driving / stall recovery; `brake_if_able(where)` (brake, swallow a failure) | `vehicle_navigation.py` |
| &nbsp;&nbsp;↳ battery accounting / trip budgeting (station wrappers); `energy_for_distance(dist, wh_per_meter=None)` (drive Wh with margin and reserve, cruise rate by default) | `vehicle_energy.py` |
| &nbsp;&nbsp;↳ charging: `recharge_at_station`, `balance_dock`, `drive_with_recharge`, `recharge_at_nearest`, `drive_to_nearest_station` (detour leg: station coords or None) | `vehicle_charging.py` (`VehicleChargingMixin`) |
| &nbsp;&nbsp;↳ charging-station discovery (all / nearest / by outpost / home slot / queue load; `STATION_DISCOVERY_TTL_TICKS`) | `charging_stations.py` — functions, no vehicle mixin imports |
| &nbsp;&nbsp;↳ fleet-wide target claims & hardware blacklist; sole writer of `self.mission` (`begin_mission`/`adopt_mission`/`end_mission`); module readers `sonar_range(vehicle, where)`, `module_hardness_limit(vehicle, kind, where, default=1.0)` | `vehicle_claims.py` |
| &nbsp;&nbsp;↳ blacklist Planet Map markers; target-key parser `key_coords(key)` (`poi_X_Y` / legacy `X:Y` to unrounded floats, None otherwise) | `unsupported_markers.py` |
| &nbsp;&nbsp;↳ `Mission` record (current job target: kind, target_key, target, prio, source, budget, tick, reserved_yield; `to_record`/`from_record`) | `mission.py` — dataclass, no vehicle imports |
| &nbsp;&nbsp;↳ recall return to base & decommission prep (`handle_recall_if_active`, `_prepare_decommission`, `_strip_and_sell_parts`) | `vehicle_recall.py` (`VehicleRecallMixin`) |
| &nbsp;&nbsp;↳ role loop: `FleetUnitMixin.run_job_loop(job)` (`job.hold()`, recall, error `stop_moving()` + `job.on_error()`, `next_job()` swap, sleep), shared by vehicles and drones; `Job` = one role's state + `step()` (default `prepare()` → `pick()` → `execute(mission)`, idle at base) | `job_base.py` (`Job`), loop in `fleet_unit.py` |

### Vehicle roles: hauling, scouting, mining, construction

| Concern | Module(s) |
| :--- | :--- |
| Hardware tier ladders (sonar, drill, holders, racks, portables, drone chassis/pods/tanks, Depot kits/types) | `item_tiers.py` — the one home of every ladder; no game calls |
| Deep oil under inert formations (Seismic Sonar): prospect state, targets, reservoir odds | `deep_oil.py` — pure; used by `vehicle_survey.py` and `pioneer_upgrade.py`, see fleet_lifecycle.md §2b-1 |
| &nbsp;&nbsp;↳ cargo offload into Inventory / Warehouse, pull-hauler loading at a source (stores, Drone Depots, drill/pump, Shop buy) | `vehicle_cargo.py` — no planning, no loop |
| &nbsp;&nbsp;↳ pull-hauler trip planning: home deficits, sources, unviable-source cooldown, Shop source, multi-stop route (`PULL_*` constants) | `pull_plan.py` — functions `(host, ...)`, chain math pure; see §2i |
| &nbsp;&nbsp;↳ Hauler role: cargo-aboard delivery, plan + claim pickups, pick the destination, drive the stops, deliver there (`PullJob`, run by `run_job_loop(PullJob(pioneer))`; state `unviable`, `warned_drills`) | `job_pull.py` (`PullJob`) — see §2f, §2i |
| &nbsp;&nbsp;↳ sonar field work: scan & survey, POI discovery, known-contact routes, spiral waypoints (`survey.spiral`) | `vehicle_survey.py` (`VehicleSurveyMixin`) — no loop |
| &nbsp;&nbsp;↳ Scout role: known-contact route first, else spiral pass (`spiral_fallback`), else idle 30 s (`SurveyJob`, run by `run_job_loop(SurveyJob(pioneer))`) | `job_survey.py` (`SurveyJob`) |
| &nbsp;&nbsp;↳ scan stops: next stand point by weighted contacts covered per metre (contact weight 1, `OUTPOST_WEIGHT` 3.0 within `outposts.resource_assignment_range_m` of any outpost, so a lone contact there can beat a far cluster; candidates = contacts + reach-circle crossings, counted by an angular sweep, exact scores best bound first, pulled toward the vehicle; reach = sonar range × `COVER_MARGIN` 0.85, + `SCAN_COST_M` 50 m per stop, `HOME_WEIGHT` 0.3 × added distance from home, nearest `MAX_CONTACTS` 30 by distance / weight) | `scan_groups.py` — pure, `plan_stops_atomic()` in `lib/atomic.py` chunks (~15–70 ticks typical, ~250 for 30 contacts all within 2 × reach); used by `vehicle_survey.survey_known_pois()`, replanned after every sweep |
| &nbsp;&nbsp;↳ mineral-site discovery, priority-sorted claiming & drill execution | `vehicle_mining.py` (`VehicleMiningMixin`) — shared Rover + Pioneer, no loop; see §2b |
| &nbsp;&nbsp;↳ Rover expedition and Miner Pioneer roles: resume/cargo-aboard handling, one trip (scan `poi` / mine `mine`), return, release, unload; `targets` strategy `RoverTargets` (POIs + mineral sites for home demand, idle 10 s) or `OutpostStockpile(outpost_id)` (stockpile candidates, idle 30 s) (`MineJob`, run by `run_job_loop(MineJob(...))`) | `job_mine.py` (`MineJob`) — see §2b |
| &nbsp;&nbsp;↳ in-flight mining yield reservation (non-exclusive, overmining guard) | `mining_reservations.py` — see §2b |
| &nbsp;&nbsp;↳ shared live telemetry dict `fleet.status` (vehicles + drones), plus the fleet cards' drawing helpers (`draw_intent`, `draw_assignment`, `synced_switch`, `outpost_names`; take `panel`) | `fleet_status.py` — see §4 |
| &nbsp;&nbsp;↳ card loop pacing: `pace(panel, mouse=None)` sleeps one tick while the cursor is over the card, else `IDLE_SLEEP_S` (`panel_pace.py`) | end of every `control_panel/*.py` and `autoplay/build_panel.py` loop — see [panels.md](panels.md) cost of a card |
| &nbsp;&nbsp;↳ fleet card views: tabs, roster list + detail split, shared detail body `draw_detail_body()` (`fleet_card.py`); Ground, Drones, Commission, Roles views (`vehicles_card.py`, `drones_card.py`, `commission_card.py`, `roles_card.py`; take `panel` and a content box) | used by `vehicles_panel.py` (tabbed FLEET) — see [panels.md](panels.md) sizing |
| &nbsp;&nbsp;↳ what Drone and Vehicle controllers share: intent, `fleet.status` telemetry, recall flag, mission save/load (`FleetUnitMixin`) | `fleet_unit.py` |
| &nbsp;&nbsp;↳ job intent line + demand-root attribution ("hauling X from A to B for supply_dock_1") | `fleet_intent.py` — see §4 |
| &nbsp;&nbsp;↳ auto Pioneer hardware tier upgrades (Sonar/Drill/Holder/Rack) + manual Sport Nav request | `pioneer_upgrade.py` — Pioneer-only, mixed into `PioneerController` only, never `VehicleController`; see §2b-1. Miner/hauler Pioneer holder/rack split: pure math in `pioneer_split.py`, §2b-2 |
| &nbsp;&nbsp;↳ Constructor role: blueprint job selection, claims, lots, restock, trip throttle (`BuildJob.step()`, run by `run_job_loop(BuildJob(pioneer))`; state `failed_jobs`, `material_waits`, `base_cruise_throttle`) | `job_build.py` (`BuildJob`) — see §2a construction entries |
| &nbsp;&nbsp;↳ Constructor build action: drive to blueprint, `execute()` with on-site recharge/resume, `wh_per_progress` calibration, progress read (`TARGET_CONSTRUCTION_PROGRESS_PER_TRIP`) | `pioneer_construction.py` (`PioneerConstructionMixin`) — Pioneer-only; pure planning math in `construction_plan.py` |
| &nbsp;&nbsp;↳ Constructor material stocking at home (batch, fair share, top-up, wait reason, cargo counts) | `pioneer_stock.py` (`ConstructionStockMixin`) — Pioneer-only |
| &nbsp;&nbsp;↳ Constructor archive I/O: `construction.lots`/`priority`/`hold`/`power_tiles`, dead-claim sweep, blueprint list reads | `construction_lots.py` — functions `(name, tick, ..., log)`, no vehicle mixin imports |

### Rover, Pioneer, harvesting & production planning

| Concern | Module(s) |
| :--- | :--- |
| Rover / Pioneer specializations | `rover.py`, `pioneer.py` — thin `VehicleController` subclasses (Rover energy model + loadout; Pioneer role detection and dispatch to `run_job_loop`); **no** shared vehicle logic here |
| Harvester base (position/heat/cells reads, held slot, collect) | `harvesting.py` (`HarvesterController`, layer 0 of `FieldKeeperController`) |
| Smelting | `smelter.py` |
| &nbsp;&nbsp;↳ per-outpost recipe claims + soft-shed check shared with the Fabricator | `recipe_claims.py` — see §2c |
| Production planning (demand-driven) | `production.py` — facade re-exporting the `production_*.py` modules below; callers import from it. Module state (memos, TTLs, `log`) is patched/reset in the defining module |
| &nbsp;&nbsp;↳ craft timing, memoized building discovery, site ids, shared `log` | `production_core.py` |
| &nbsp;&nbsp;↳ Supply Dock orders, units still owed, consuming sites | `production_docks.py` |
| &nbsp;&nbsp;↳ fluid source types, buffer-tank latch rule, `can_source_fluid()`, `discover_fluid_sources()` | `production_fluids.py` |
| &nbsp;&nbsp;↳ `SourceCache`, `can_source_item()`, `can_fulfill_order()` | `production_source.py` |
| &nbsp;&nbsp;↳ archive order books: manual orders + transit, the prioritized `fabricator.orders` book | `production_orders.py` |
| &nbsp;&nbsp;↳ recipe index, demand cascades, network-wide Fabricator targets | `production_cascade.py` |
| &nbsp;&nbsp;↳ per-fab-site targets, site plan split, shared site targets, ship-before-craft, active recipe | `production_sites.py` |
| &nbsp;&nbsp;↳ material/Smelter demand, fab-site ingot buffer, Smelter peers, raw-ore reasons | `production_demand.py` |
| Supply Dock logistics | `supply_dock.py` |

### Biology & drones

| Concern | Module(s) |
| :--- | :--- |
| Biology, shared pipeline (collector/lab/exchange controllers) | `bio.py` — outpost-aware (Warehouse-only outposts, no Inventory) throughout, biome-agnostic; see §1g/§2g |
| &nbsp;&nbsp;↳ shared order/stock helpers (biome, sibling and biome-processor discovery, local stock snapshot, order focus/demand, `MAX_LOCAL_BIO_ARTIFACTS`) | `bio_orders.py` — imported by `bio.py` and the biome processors below; see §1f/§1g |
| &nbsp;&nbsp;↳ biome processor base (sample loading, Lab heartbeat, per-step order/stock fetch, run loop) | `bio_processor.py` (`BioProcessorController`) — subclassed by the four below; hooks `_classify_stack()` (raw/finished/ignore), `_candidate_fragments()`, `_load()`, `_on_only_nonraw_staged()`, `_chamber_empty()`; at most one `self.input` take/eject per cycle, then `STAGE_SETTLE_TICKS = 20` ticks before the next (see §1g) |
| &nbsp;&nbsp;↳ Coastal biome processor (glow-tint) | `bio_coastal.py` (`BioLuminizerController`) — see §1e/§1g |
| &nbsp;&nbsp;↳ Volcanic biome processor (forge-cast) | `bio_volcanic.py` (`BioCasterController`) — see §1g |
| &nbsp;&nbsp;↳ Geothermal biome processor (gene-splice) | `bio_geothermal.py` (`DnaSequencerController`) — see §1g |
| &nbsp;&nbsp;↳ Deep biome processor (QC quiz, automated) | `bio_deep.py` (`BioConditionerController`) — see §1g |
| Outpost reagent stock-target scaffolding (Bio Lab resupply) | `outpost_reagents.py` — see §2g |
| Vehicle charging stations | `charging.py` |
| &nbsp;&nbsp;↳ station base shared with `drone_service.py`: nearest-awake-station arbitration, rescue loop `manage_fleet_rescues()` (hooks per station kind), power gate, step/run poll loop | `station_controller.py` — see §2a |
| Drones (scout/miner/hauler base) | `drone.py` (`DroneController`, composes mixins below — see §2h) |
| &nbsp;&nbsp;↳ go_to()/go_to_station()/go_to_drill() wrappers, arrival polling | `drone_navigation.py` |
| &nbsp;&nbsp;↳ drone_service/drone_depot discovery, heli-capable services, pinned homes (`HOME_DEPOTS_KEY`), free-depot pick — functions, no drone mixin | `drone_depots.py` — see §2h |
| &nbsp;&nbsp;↳ engine auto-detect (electric/heli), linear per-meter trip budgeting; thin wrappers over `drone_depots.py` | `drone_energy.py` — see §2h |
| &nbsp;&nbsp;↳ charge/refuel trips to a drone_service (`return_to_service_for_charge()`, `hold_for_launch_charge()`, `refuel()`), `LAUNCH_MIN_SOC`, `REFUEL_*` | `drone_charging.py` — see §2h |
| &nbsp;&nbsp;↳ exclusive biosite claims + scout empty-POI cache + mission persistence (sole writer of `self.mission`) | `drone_claims.py` — see §2h |
| &nbsp;&nbsp;↳ archive helpers shared with `vehicle_claims.py`: claim race/heartbeat/release/stale drop, mission store with legacy-key migration, recall flags | `fleet_claims_common.py` |
| &nbsp;&nbsp;↳ cargo accounting/load-unload + home-biome filtering + home-Depot unload trip (`return_and_unload()`, `DepotFull` backoff) | `drone_cargo.py` |
| &nbsp;&nbsp;↳ drone role jobs: `DroneJob` (hold while stranded, upgrade request, `defer()`/`idle()`, charge helpers) and `ScoutJob`, `BiositeJob`, `HaulJob`, `AftermathJob`, run by `DroneController.run()` → `run_job_loop()` | `drone_job.py`, `job_scout.py`, `job_biosite.py`, `job_haul.py`, `job_aftermath.py` |
| &nbsp;&nbsp;↳ scout abilities (POI candidates, fly-and-scan) | `drone_scout.py` |
| Survey request areas scouts serve first (`autoplay.survey_requests`) + sonar `wrong_scanner` contacts as known biomass | `survey_requests.py` — see `docs/cheatsheet/autoplay_outposts.md` §11j |
| What an unresolved sonar contact can still be (blacklist reason + scan research on record + biome at the contact, `BIOME_KINDS`) | `contact_inference.py` — see `docs/gameknowledge/survey_contacts.md` |
| &nbsp;&nbsp;↳ miner abilities (biosite candidates, claim, extract) | `drone_mining.py` |
| &nbsp;&nbsp;↳ floating hauler legs (drills and Depot outposts → Depots, no home): dock, load, deliver, hover idle | `drone_hauler.py` `DroneHaulerMixin` — see §2j |
| &nbsp;&nbsp;↳ floating hauler job planning: demand, sources, route scoring, fuel budget, stall cooldowns | `drone_haul_plan.py` (module functions, `HaulMemory`) — see §2j |
| &nbsp;&nbsp;↳ aftermath abilities (sites, claims, Lead Cask room, fly-wait-collect; plated drone: Raw Uranium + Storm Glass) and the hauler's Storm Glass pickup | `drone_weather.py` — see §2j-1 |
| &nbsp;&nbsp;↳ fleet-upgrade handshake, new-chassis fitting, in-place module upgrades (+ shared `fleet.upgrade` state helpers) | `drone_upgrade.py` — see §2k |

### Fleet upgrades, swaps & cash

| Concern | Module(s) |
| :--- | :--- |
| Fleet hardware upgrade coordinator (Depot in-place upgrades + drone chassis swaps), run by the `builder_automation.py` Automation | `fleet_upgrade.py` — see §2k |
| One Depot kit + one Service Station kit in stock while an outpost lacks that building (`drone_kit_stock` orders-book requester), run by the Supply Dock planner | `drone_kit_stock.py` — see §2a-1 item 4 |
| New Pioneers and drones from the FLEET card's Commission tab (queue, buy or craft, deploy, wait for script), run by the `builder_automation.py` Automation | `fleet_commission.py` — see §2k-2 |
| &nbsp;&nbsp;↳ Constructor Pioneer job scan (pure, atomic slices: claim/lot/cargo filter, `construction.priority` then own-lot then nearest-first order, lot chain growth, station range check, progress lookup) | `construction_plan.py` — see `docs/cheatsheet/vehicles_drones.md` §2a |
| &nbsp;&nbsp;↳ Pioneer role presets, shared `fleet.commission` state, `LoadoutFittingMixin` (a new Pioneer or Rover mounts/installs its own parts), `commission_name()`/`rename_vehicle()` | `pioneer_commission.py` — see §2k-2 |
| &nbsp;&nbsp;↳ Pioneer refit to another role in place (service-area park, surplus sale, refit job on `fleet.commission`), `PioneerRefitMixin` | `pioneer_refit.py` — see §2f-1 |
| Pioneer role demand (`fleet.role_demand`, published by the `orchestrator_automation.py` Automation), role slots (`fleet.role_claims`), switch candidates for `PioneerController.next_job()` | `role_demand.py` — see §2f-1 |
| &nbsp;&nbsp;↳ mission pool: read-only index of the open work per demand (`fleet.missions`, published with the role demand), holders derived from the reservations, `oldest_open()` | `mission_pool.py` — see §2f-1 |
| &nbsp;&nbsp;↳ drone presets (best craftable chassis + `LOADOUTS` modules), `fleet_commission` orders-book requester | `drone_commission.py` — see §2k-2 |
| Retiring Pioneers and drones from the FLEET card retire buttons (recall, unload, undeploy, sell Pioneer parts, archive cleanup), run by the `builder_automation.py` Automation | `fleet_decommission.py` — see §2k-4 |
| Pillar swap from the PRODUCTION card (replace every generator of one terraforming pillar with another, same outpost and tier up to Mk III), run by the `builder_automation.py` Automation | `pillar_swap.py` — see [panels.md §7](panels.md) |
| Warehouse pair → Large Warehouse swap (buy, deploy, greedy drain, undeploy, sell), plus interim Storage Bins → Warehouse by slot plan (`BinUpgrader`), run by the `builder_automation.py` Automation | `warehouse_upgrade.py` — see §2k-1 |
| Cash manager: `can_spend()`/`spent()` gate for every Shop purchase, income + floor pass in the `orchestrator_automation.py` Automation | `cash.py` — see §2l |
| Liquid Tanks (≤ 5 of one liquid) → Large Liquid Tank swap (buy, deploy, retire via `tank_assignments`, pipe drain, undeploy, sell), same `builder_automation.py` Automation | `tank_upgrade.py` — see §2k-3 |
| &nbsp;&nbsp;↳ shared swap state machine (gate, buy, deploy/adopt, refusals, kit sale) for both upgrades above | `building_swap_upgrade.py` — see §2k-1 |
| Fabricator/Smelter Mk II/III packs (order, apply in place) and Oil Pump Mk II installs (plan for a Pioneer), same `builder_automation.py` Automation | `machine_pack_upgrade.py` — see §2k-6 |
| Storage outpost expansion (warn and buy one more Warehouse when a storage outpost runs low on empty slots), same `builder_automation.py` Automation | `storage_expand.py` — see §2k-5 |

### Depots, logistics, seeds, plants & wildlife

| Concern | Module(s) |
| :--- | :--- |
| Drone Service Station (charging/refuelling/rescue) | `drone_service.py` — see §2h |
| Drone Depot (cargo logistics endpoint) | `drone_depot.py` — see §2h; drains freight to local storage, buffers life forms in a local Warehouse (two stacks per form), stages hauler pickups, flushes surplus |
| Depot staging requests (hauler → source Depot) | `depot_stage.py` — see §2j; `depot.stage` archive dict |
| One priority scale for every demand on the network (bands `BLOCKER` … `STOCK` + fine value, ladders `[[prio, cum_units], ...]` and their helpers) | `priority.py` — see §2a-p (pure, no game calls; used by production, `logistics_requests`, `site_supply`, `supply_dock`, the miners) |
| Pull logistics (outpost item requests as priority ladders, per-band deficits and free stock, fair share, in-flight pickups, source retention) | `logistics_requests.py` — see §2i; reverse hauler: `job_pull.py` `PullJob`, planning `pull_plan.py`; shared tier deficit/free record: `logistics_snapshot.py` (drones.md Plan) |
| Factory outpost site supply (per-outpost ingot/ore/finished-root requests), run by the `orchestrator_automation.py` Automation | `site_supply.py` — see §2i-1 |
| Stranded stock eviction (ore, ingots/intermediates, stragglers, lab reagents; storage outposts as the dump), run from `site_supply.publish_site_requests()`; `sell_stranded_reagents()` from the `orchestrator_automation.py` Automation | `site_evict.py` — see §2i-1 |
| Fab site plan (which fab outposts build each root target's tree), run by the `orchestrator_automation.py` Automation | `site_plan.py` — see §2a-0-6 |
| Seed Maker (fair recipe sweep, stage A) | `seed_maker.py` — see §1i |
| Seed Maker on-demand seed production (stage B, once all 15 recipes are known) | `seed_supply.py` — see §1k (`bio/seed_maker.py` dispatches on `len(recipes())`) |
| Field layout (species rules, starter block, full-field layout in automator chunks, rarity-weighted expansion; pure logic) | `field_layout.py` — see §1k |
| Plant Terraformer (feed Forage/Water/Salt/Fertilizer/Accelerant, batch run policy) | `plant_terraformer.py` composes `plant_terraformer_water.py` (`PlantTerraformerWaterMixin`: `water_in` router) + `plant_terraformer_demand.py` (`PlantTerraformerDemandMixin`: local stock requests, Fabricator need/backlog orders); shared keys and ladder math `plant_terraformer_common.py` — see §1k |
| Building executor: deploy / upgrade / retire jobs (`build.jobs`, retire handshake `build.retire`), the shared `undeploy()`, `deploy_new()` (restart adoption) and `upgrade()` with one status table `classify()` and `CALL_FAILED_STATUSES` (calls that could not ask) | `building_ops.py` — see `docs/cheatsheet/autoplay.md` §11k |
| Game phase: fronts, phase name, locked research thresholds, pillar rates and ETAs over one snapshot (`phase.history`); thresholds generated from the research catalog | `game_phase.py`, `research_thresholds.py` — see `docs/cheatsheet/autoplay.md` §11m |
| Plants completion: undeploy emptied Plant Terraformers | `plants_retire.py` — see §1k (driven by `orchestrator_automation.py`, idles until a Terraformer reports `complete`) |
| Planting Harvester (plant, tend, harvest the layout) | `field_keeper.py` (`FieldKeeperController`: the pass, ability composites `work_on_pass()`/`harvest_current()`) composes, by layer: `harvesting.py` `HarvesterController` (0: sensors, held slot, collect) → `harvester_heat.py` (`HarvesterHeatMixin`, 1: heat model, just-in-time rests, heat-cheapest routes, `nearest()`, `move_to()`) → `harvester_hub.py` (`HarvesterHubMixin`, 2: `act`, `stage`, `stock_count`, `note_action`, layout state, deployed-machine reads, cell views; module functions `field_fill()`, `desired_chunks()`, `stored_chunk_count()`, `load_rules()`) → abilities (3, never call each other): `harvester_paving.py` (`HarvesterPavingMixin`: items dropped on a path joining the plant patches), `harvester_planting.py` (`HarvesterPlantingMixin`: layout, seed demand, plant, harvest), `harvester_care.py` (`HarvesterCareMixin`: light/water/salt, `row_scan()`), `harvester_machines.py` (`HarvesterMachinesMixin`: field-machine kits) — see §1k; `harvester_pass.py` (`FieldPass`: one `step()`'s cell read, plan-note phases, chosen `Choice`, `last_action`) |
| Field machines (kit orders/pre-orders + deploy on reserved cells; Grow Lamp / Sprinkler / Dispenser controller; Crop Automator job controller) | `harvester_machines.py` (`HarvesterMachinesMixin`, mixed into `field_keeper.py`) + `harvester_amplify.py` (`HarvesterAmplifyMixin`, Yield Amplifier apply + order) + `field_provider.py` (`FieldProviderController`, thin `harvesting/grow_lamp.py`/`sprinkler.py`/`dispenser.py`) + `crop_automator.py` (`CropAutomatorController`, thin `harvesting/crop_automator.py`) — see §1k |
| Wildlife model (game constants, growth/Insight/bonus model, revival schedule; pure) | `wildlife_data.py` (constants, `WILDLIFE_SCHEDULES` per Habitat count) + `wildlife_model.py` (rate, stages, fluids, bonuses, Insight, `schedule_for()`); schedule solved offline by `devtools/simulation/wildlife_optimizer.py` — see §1l |
| Wildlife automation (revival schedule walk, feed demand, Forage reserve, life-form requests; Habitat revival/feed/fluid bands/parking; demand-driven feed crafting) | `wildlife_planner.py` (run by `orchestrator_automation.py`) + `habitat.py` + `feed_maker.py` (thin `bio/habitat.py`, `bio/feed_maker.py`), shared keys/tunables `wildlife_common.py` — see §1l-2 |
| &nbsp;&nbsp;↳ Wildlife retirement at `WILDLIFE_COMPLETE_POPULATION` (release/empty/undeploy Habitats, Feed Makers, Refiners, exotic tanks; caps/taps to deconstruction; kit sales, feed drop) | `wildlife_retire.py` (`retire_pass()`, called by `wildlife_planner.plan_if_due()` through a function-level import) — see §1l-2 |
| Outpost flow statistic (`logistics.outpost_flow`, units sent/received per outpost, decayed) and idle Pioneer hauler dispersal choice | `outpost_flow.py` — see §2i, §2f |
| Water Pump byproduct salt as pull-hauler source; home salt request (field + Terraformers to 5m km²) | `pump_salt.py` — see §2i and §1k Salt budget (tier 4 lib, imported by `pull_plan.py`, `vehicle_cargo.py` and the orchestrator Automation) |
| Field Mining Drill telemetry (fill, time-to-full, stall warnings, pickup advert) | `mining_drill.py` — see §1j |
| Weather Station signal decoding (storm aftermath coordinates for Raw Uranium / Storm Glass) | `weather_signals.py` — see §1m |
| Fuel Assembler (Fuel Rods for local Reactors / Mk IV generators, then Nuclear Batteries; reserve-gated bursts) | `fuel_assembler.py` — see §1n |
| Reactor (measured-gain heat control just under 900 °C, rod feed from local Lead Casks, cooling water routing, water reservation publisher) | `reactor.py` — see §1c-4 |
| Lead Cask roles (`lead_cask.roles`), hot-cargo stock/room/take, misfiled-uranium repair | `lead_cask.py` — see §1n (tier 4 lib; used by `drone_weather`, `supply_dock`, `terraforming`, `production`) |
| Field Mining Drills as pull-hauler sources (recorded positions, connect/take) | `drill_sites.py` — see §2i (lives in tier 4 lib, since the hauler imports it at every tier) |

### Machine controllers: fabrication, steam, fluids, biomass

| Concern | Module(s) |
| :--- | :--- |
| Fabrication | `fabricator.py` |
| Thermal Cap (steam capture, anti-overpressure) | `thermal_cap.py` |
| Thermal vent cycle log (times active/dormant phases of vents without a Deep survey; orchestrator Automation) | `vent_cycles.py` — see `docs/cheatsheet/power_fluids.md` §1b |
| Steam Turbine (steam-to-grid power) | `steam_turbine.py` |
| Water Pump / Oil Pump (route well output to network Liquid Tanks) | `fluid_pump.py` `FluidPumpController(pump, fluid_id)` — see §1c, simpler cousin of `thermal_cap.py` (no overpressure/relief); `water_pump.py` = compat shim for old save slots |
| Exotic Gas Cap / Exotic Spring Tap (route deposit fluid to network tanks) | `exotic_cap.py` `ExoticCapController(cap)` (tier 9): `FluidPumpController` subclass, Gas Tanks for a Cap, Liquid Tanks / Large Liquid Tanks for a Tap, `fluid_id` = `deposit().fluid()`; valve always open; parks only through a long dormant phase (see dev_workflow.md §1d-2) |
| Refiner (purify raw exotic gas/liquid + tar into creature-grade fluids) | `refiner.py` `RefinerController(refiner)` (tier 9): refines the fluid with the emptiest tanks among those with raw stock (dwell + margin against flip-flop), routes raw from and refined to network tanks, tar from local storage (stockpile via `site_supply`); soft-shed Tier 2 by `clear_recipe()`; parks when idle — see wildlife.md |
| Oil Generator (last-resort power) | `oil_generator.py` — see §1c-1 |
| Steam Condenser (steam → water, steam-reserve and water-fill guards) | `steam_condenser.py` — see §1c-2 |
| Essence Liquifier (Depot → sample feed, essence → Liquid Tank) | `essence_liquifier.py` — see §1h |
| Biomass Mixer (keep all five essence inputs sourced) | `biomass_mixer.py` — see §1h |
| Biomass Mixer duty-cycle gate (breaker pause until all expected essences refilled) | `biomass_mixer_gate.py` — see §1h (driven by the single `orchestrator_automation.py`, idles without Mixers) |
| Biomass completion: retire and sell Liquifiers/Mixers | `biomass_retire.py` — see §1h-1 (imported by `drone_mining.py`/`drone_depot.py`/`orchestrator_automation.py`) |
| Bio chain completion: per biome, drain and sell Collectors/Labs/processors/Exchanges once all its Bio Orders are complete | `bio_retire.py` — see §1g-1 (imported by `bio.py`/`bio_processor.py`/`orchestrator_automation.py`) |
| Waste Processor base (idle: switched off, staged input returned; destroys no items) | `waste_sink.py` — see §1h-1 |
| Waste Processor water overflow (last-resort drain when every Water tank at the outpost is full and a Water Pump stalls) | `water_sink.py` — see §1c |
| Shared network-wide fluid-target discovery/blacklist/reconnect | `fluid_routing.py` — `FluidOutputRouter` (`thermal_cap.py`/`fluid_pump.py`/`essence_liquifier.py`/`steam_condenser.py`), `FluidInputRouter` (`steam_turbine.py`/`fabricator.py`/`biomass_mixer.py`/`oil_generator.py`/`steam_condenser.py`/`terraforming.py`); see §1b |
| Two-threshold on/off latch (heater steam guard, Condenser steam/water gates, Oil Generator surplus, Reactor water reserve, turbine all-on and steam surplus) | `hysteresis.py` — `HysteresisLatch`; state in memory, kept across breaker parking/shedding, reset on script restart |
| Repeating machine warning (pump/Cap/Turbine stall, Cap relief venting, Fabricator byproduct full, Liquifier host-biome wait) | `status_warning.py` — `StatusWarning.update(active, message)`: one warn line on start, one info "cleared after N s (since tick T)" line on end, script status (`set_status()`, no game-time cost) in between; a script's active warnings share one status |
| Storage data layer (discovery, snapshot, capacity, busy registry) | `storage.py` — see §2c |
| Take path: holder search over Inventory, Warehouses, Storage Bins and clogged Crop Automators, `take_item()` | `storage_take.py` — see §2c |
| Unload path: `best_unload_target()` scoring, port drains, direct delivery `push_to_targets()`, bin top-up | `storage_unload.py` — see §2c |
| Storage housekeeping sweeps (Inventory rebalancing and its reverse, bin and Warehouse stray consolidation, fleet part parking), run by the `orchestrator_automation.py` Automation | `storage_sweeps.py` — see §2c |
| One stores read per outpost, stock scopes `LOCAL`/`HELD`/`DEPOTS`/`STORES` | `stock_scan.py` — see §2a-1b stock scopes |
| Outpost ore-assignment & stock-target scaffolding (multi-outpost mining) | `outpost_mining.py` — see §2d |

### Core utilities, parking & activity

| Concern | Module(s) |
| :--- | :--- |
| Data Archive persistence layer | `archive.py` |
| Game version safety gate (halt on build change until operator confirms) | `version_guard.py` — see §4's `system.good_version`/`system.version_confirmed` entries and §7 |
| Wildcard pattern matching helpers | `patterns.py` |
| Straight-line metres between two (x, y) points (`distance(a, b)`) | `geometry.py` — no imports |
| Per-script tick-cost profiling | `profiling.py` — see §1d |
| Structured, indented console logging (`debug()`-level decision tracing) | `tree_console.py` (`TreeConsole`) — see §0a |
| Logging caught-and-recovered exceptions (`swallowed(where, error)`) | `swallow.py` — see §0b; imports nothing, so even `archive.py` uses it |
| Run loop of a single-machine controller (`MachineController`: `LABEL`, `POLL_S`, `STEP_DELAY`, `ERROR_POLL_S`, `PARK_IDLE_S`, `next_sleep()` hook) and `port_counts(port, where)` | `machine_controller.py` — subclass it instead of writing a `run()` loop; bio controllers and loops with a start-up phase (seed maker, plant terraformer, bio exchange) keep their own |
| Current simulation tick (`now_tick()`, 0 without a readable clock); elapsed game hours (`now_hours(default=0.0)`); staleness of a tick-stamped archive entry (`is_fresh(entry, tick, stale_ticks)`: non-dict or no stamp = stale); values reused for N ticks (`TickCache(ttl_ticks, keep_empty, single)`: `get(compute, key, tick)`, `peek()`, `invalidate()`, `clear()`); live game hour length (`real_seconds_per_hour(clock)`, falls back to `game_rules.SECONDS_PER_GAME_HOUR`) | `game_clock.py` — imports only `swallow` and `game_rules`; use it instead of a local `clock.tick()` or `elapsed_game_hours()` wrapper, an inline `tick - entry.get("tick")` check or a `(tick, value)` memo |
| Fixed game facts, grouped by section: timing (`DAY_CYCLE_DURATION_SECONDS = 600`, `TICKS_PER_SECOND = 10`, `SECONDS_PER_GAME_HOUR = 25`, `TICKS_PER_GAME_HOUR = 250`, `TICKS_PER_REAL_HOUR = 36000`), ores (`RAW_ORE_ITEM_IDS`, `SMELT_PRODUCTS` {ore: product}), world (`BIOMES`, `TILE_M = 10`), buildings (`LIQUID_TANK_TYPE_IDS`, `WAREHOUSE_SLOT_UNITS = 2000`, `CROP_AUTOMATOR_OUTPUT_CAP = 50000`) | `game_rules.py` — imports nothing (tested); look here before adding a constant for a game fact; tunables never go here |
| Typed component lookups by runtime id (`tank(id)`, `battery(id)`, ...; `component(id)` = `get_component` with a swallowed() guard); home outpost (`home_outpost()`, `home_outpost_id()`: `outpost_network.home()`, else the `is_home` entry of `outposts()`); every outpost (`outposts()`, `[]` when the network is missing or raises); research gates (`research_unlocked(id, where)`, `all_research_unlocked(ids, where)`: False when missing, raising, or an empty id list); installed Mk tier (`machine_tier(id)`, 1 when unreadable); `start_script(id)` (`run_control.start()`, `already_running` counts as ok) and `set_powered(power, id, on, log)` (breaker switch, True on ok) | `components.py` — imports only `swallow`; accessors need their class in `COMPONENT_EXPORTS` (`devtools/self_typing.py`) |
| Heavy pure computations as one unit (`run_atomic(fn, *args)`, `run_batched(fn, items, size, *args)`, `run_chunked(step_fn, state)`, `ATOMIC_ENABLED` switch) | `atomic.py` — see `docs/cheatsheet/dev_workflow.md` §1d-1 |
| Turbine commitment (runs just enough Steam Turbines, parks the rest; per-turbine steam aware; called from `PowerGridManager.supervise_grid()` before the guard) | `turbine_commit.py` — see `docs/cheatsheet/power_fluids.md` Steam Turbine |
| Script parking (idle machines' breakers off, solar scripts stopped at night, stray dark machines warned about then switched on; `ScriptParking` in `orchestrator_automation.py`; client side for machine scripts and wakers in `parking_client.py`: keys, `ParkRequester`, `wake_for_visit()` / `wake_kind()` / `wake_on_rise()`, `parked_ids()`, `parked_nearest()`, `stray_alerts()` for the Status panel) | `script_parking.py`, `parking_client.py` — see dev_workflow.md §1d-2 |
| Retired machines registry (machines switched off for good by a retirement; script parking leaves them dark) | `retired_machines.py` — see dev_workflow.md §1d-2 |
| Script restart requests (a machine whose upgrade port the game left unbound files a request; `orchestrator_automation.py` `park_if_due()` stops and starts it, at most `MAX_RESTARTS` per reason) | `script_restart.py` — see power_fluids.md §1c-3 |
| Script census (counts running scripts every `CENSUS_TICK_INTERVAL = 300` ticks, logs `scripts running: N of M machines, allowance A steps/tick` for `devtools/perf/log_block_timing.py`; called from `orchestrator_automation.py` `park_if_due()`) | `script_census.py` — see dev_workflow.md §1d-1 |
| Machine activity (per-machine and per-group active/waiting/idle/running/parked/off time shares and `retire` candidates, archive `machine.activity`; sampled from each census snapshot by `orchestrator_automation.py`) | `machine_activity.py` — see dev_workflow.md §1d-3 |

### Root scripts & interpreter limits

Root executable scripts (`solar_1.py`, `rover_1.py`, `orchestrator_automation.py`, etc.) stay thin entrypoints: import + run controller from `lib/`. No own copies of tier lists, thresholds, budgeting formulas.

**No real stdlib — only the game's executable built-in modules** (`docs/guide/programming_language_reference.md`'s "Imports & Libraries" section authoritative; the exact allowlist is in [`cheatsheet/stub_tests.md` §10](stub_tests.md), enforced by `tests/test_game_imports.py`). They are small in-game reimplementations, not CPython modules: check a function exists in `docs/guide/builtins_and_commands.md` before using it. `sys`, `os`, `time`, `copy` etc. **don't** exist at runtime. `typing`, `types`, `collections.abc`, `user_stubs` exist ONLY for editor/Pyright annotations — erased at runtime (`typing.TYPE_CHECKING` always `False` in-game; `typing.NamedTuple` is the one that runs).

**Type tests**: after `from __builtins__ import Smelter` (any game class, incl. `Component`), `isinstance`/`issubclass` work on machines; `type_id` names the type and can't be written. `match` supports class patterns (`case Circle(radius=r):`, `case int(n) | float(n):`). The in-game editor honours `# type: ignore` / `# noqa` per line (a top-of-file `# type: ignore` quiets the whole script).

**Parser/builtin limits**: no multi-line parenthesized imports — `from x import (a, b)` is a `SyntaxError` in-game, write one-line imports. No `frozenset` — use tuples; check a builtin against existing `lib/` usage before relying on it.

**Remote writes are blocked** (decompiled simworker, `api.remote_write_blocked`): on a component fetched with `get_component()` for another machine, every non-read-only method raises `PermissionError` ("hardware methods only work from the machine's own script"), and so does every state-changing method of its sub-objects: `NavModule.set_target`/`set_throttle`/`brake`, `FluidPort.connect`/`disconnect`, `InputSlot`/`OutputSlot` `connect`/`disconnect`/`take`/`eject`/`flush`/`send`, `DroneCargo.load`/`unload`/`discard`, `SonarModule`, `DrillModule`, `ConstructorModule`. Reads work. Exempt (`allowsRemoteWrites`): `shop`, `power_control`, `run_control`, `inventory`, `transmitter`, `storage_bin`, `comms`, `console`, `markers`, `notebook` (archive), `construction_blueprint`, `computer`, gas/liquid tanks, bulk reservoir, Warehouse, Large Warehouse, Lead Cask. The *(self only)* badge in docs marks exactly these. So cross-machine control goes through a signal the target's own script reads (archive, Signal Bus) or through the breaker (`power_control`, exempt).

**Breaker** (`power_control`, decompiled): `can_power_off(id)` is a fixed per-type flag. True for, among others, every factory, dock, generator, pump, turbine, condenser, thermal cap, terraformer, drill, bio machine, seed maker, plant terraformer, crop automator, grow lamp, sprinkler, dispenser, garbage disposal, charging station, drone service station, every drone depot size, and `solar_generator`; false for batteries, scanner, harvester, sensors, vehicles, drones, warehouses and tanks. Off: the machine's running scripts are paused (remembered per machine) and only transient outputs are zeroed (e.g. a machine's running flag, a thermal cap's flows); script setpoints such as `set_enabled` stay. On: only the scripts paused by that power-off resume. Stopping or ending a script instead resets its setpoints (e.g. `set_enabled` → off).

**Import depth limit**: interpreter caps nested import-resolution stack at `maxImportDepth = 256` (`interpreter.maxImportDepth`, confirmed from decompiled simworker — see `internals/` [private submodule, not authoritative game docs]), raises `RecursionError` / `error.import_depth` if exceeded. Current `lib/` chain (entrypoint → `vehicle.py` → mixins, max 2-3 levels) nowhere close — see this error → look for real import cycle.
