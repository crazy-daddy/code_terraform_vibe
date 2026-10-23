# Helper sweep: candidate families

Raw candidates for [helpers_sweep.md](helpers_sweep.md), merged 2026-10-23 from four harvest angles. No verdicts here; the judge (Task 3) decides per family: extract, keep, or drop. No code was changed.

Angles (the `Found by` letters):
- **A** scan pairs: `devtools/code_scan/clone_scan.py --min-ratio 0.85 --min-lines 3 --top 0` (130 clusters, all triaged).
- **B** game API anchors: callers of `research.is_unlocked`, `archive.get`, `get_component`.
- **C** bypassed discovery: per-outpost building filters that skip `discover_storage_buildings` / `discover_network_buildings` / `production_core.discover_building_ids`.
- **D** known families refresh: 2026-10-09 families re-read in live code.

Path key: `L/` = `scripts/4_controlpanel/lib/`, `au/` = `scripts/4_controlpanel/automation/`, `ap/` = `autoplay/lib/`, `s0/` = `scripts/0_cold_boot/`. Sites are `path:line qualname`, def lines unless noted. `(?)` = harvests disagree on the line. Order: DRIFT families first, then the rest, then `keep?` and gaps. Tier note: tier 0 cannot import tier 4; autoplay already imports scripts libs (`ap/power_survey.py:63` calls `construction_plan.clean_power_ledger`).

## Research unlock guards (`research.is_unlocked` wrappers)
- Sites:
  - `L/early_buyer.py:96 is_unlocked` (generic id arg; internal callers :194 :237 :279 :338; no outside importer)
  - `L/drone_depots.py:83 heli_unlocked` (?85 per B)
  - `L/drone_scout.py:23 _exotic_research_done` (`all()` over `SURVEY_RESEARCH["exotic"]`)
  - `L/drone_weather.py:130 hot_cargo_unlocked`
  - `L/pioneer_upgrade.py:76 sport_nav_unlocked`
  - `L/pioneer_upgrade.py:171 PioneerUpgradeMixin._seismic_wanted` (inline, `all()` over `SEISMIC_RESEARCH_IDS`; D says def 163, guard 173)
  - `L/storage.py:606 inventory_stack_size`, `L/storage.py:677 warehouses_unlocked`
  - `L/survey_requests.py:149 unlocked_scan_research` (returns list)
  - `L/vehicle_claims.py:72 scan_research_snapshot` (?66 per D; list, also `research.unlocked()` count)
  - `L/vehicle_claims.py:507 VehicleClaimsMixin.can_attempt_target` (inline per-id loop at :515)
  - `L/site_supply.py:~380 _stock_table` (?378; inline, lazy `component("research")`)
  - `L/game_phase.py:250 read_research` (set-valued; prefers `research.unlocked()`, per-id fallback; None on failure)
  - `L/building_swap_upgrade.py:125 BuildingSwapUpgrader._large_unlocked` (researched OR inventory)
  - `L/storage_expand.py:69 StorageExpander._unlocked` (researched OR inventory)
  - `s0/power/solar.py:95 is_tech_unlocked` (tier 0)
  - `ap/`: 0 sites.
- Rule: resolve the research component, guard it, call `research.is_unlocked(id)`, `bool()` it; a missing or raising component logs `swallowed` and reads as not unlocked. Two copies add "or one sits in inventory" (`inventory_count(type) > 0`); could be one `unlocked_or_held(research_id, type_id)`.
- Differences: **DRIFT** `s0/power/solar.py:29` binds `research = get_component("research")` once at import; all other copies resolve per call. If absent at import, `is_tech_unlocked` stays False for the process (D, medium confidence bug; B found no drift in tier 4). Lookup spelling varies: `component("research")` (early_buyer, storage_expand, site_supply), `get_component` (drone_*, pioneer_upgrade, survey_requests, vehicle_claims), `components.component` (storage x2), `self._component` (building_swap_upgrade). Guard varies: `not research`, `is None` (drone_weather:132, survey_requests:153, game_phase:257), `hasattr(research, "is_unlocked")` (storage x2, vehicle_claims:72/80/515). `not` vs `is None` differs only for falsy component objects (unverified). Exception result varies: False, fall to inventory, skip id, try id variants (solar:98, dead weight now), whole read None (game_phase:273). No shared helper exists.
- Found by: A, B, D

## Depot walks (DEPOT_TYPE_TIERS: drone_station, drone_station_medium, drone_station_large)
- Sites:
  - `L/logistics_requests.py:614 local_depots` (per outpost, resolves via `drone_station()`, drops unresolved)
  - `L/fleet_upgrade.py:106 FleetUpgradeCoordinator._depots` (network, per tier, dicts id/name/type_id/outpost_id)
  - `L/fleet_decommission.py:146 FleetDecommissionCoordinator._depot_ids` (network, per tier, id set)
  - `L/commission_card.py:47 read_outposts` (membership on `ref.buildings()`, line 63)
  - `L/drone_depots.py:150 _scan_drone_buildings` (behind `discover_drone_depots`, listed for comparison)
- Rule: every building at an outpost whose type_id is in DEPOT_TYPE_TIERS.
- Differences: **DRIFT** `commission_card.read_outposts:63` counts unresolved depot refs as depots; `logistics_requests.local_depots` drops them, so one outpost can read has_depot True in one and False in the other. **DRIFT** `drone_depots._scan_drone_buildings` drops refs with no coords; `fleet_upgrade._depots` and `fleet_decommission._depot_ids` keep them. Fleets could call `discover_drone_depots()` and filter `outpost_id` only if the coords-less drop is accepted. `local_depots` cannot call the drone helper (network-wide, returns coords dicts).
- Found by: C

## Network-wide machine walks (one or more types)
- Sites:
  - `ap/outpost_needs.py:663 _machines` (walk :671; components, drops None)
  - `ap/building_plan.py:385 read_machines` (walk :400; rows (machine_id, outpost_id, tier))
  - `ap/focus_plan.py:215 read_generators` (walk :224; tiers per PILLARS type; `{}` on any error)
- Rule: every building of the type(s) across `outpost_network`.
- Differences: **DRIFT** `outpost_needs._machines` drops a building whose `get_component` is None; `discover_network_buildings(resolve=True)` falls back to the raw BuildingRef (no `fill_pct()`), so swapping in the helper changes what the caller gets. `building_plan.read_machines` can call `discover_network_buildings(type, resolve=False)` as is. `focus_plan.read_generators` needs all-or-nothing; the helper tolerates per-outpost errors (needs param, or keep?).
- Found by: C

## Survey spiral progress reads (SURVEY_SPIRAL_KEY)
- Sites:
  - `L/job_survey.py:116 spiral start` (`archive.get(K, {}) or {}`, then `.get("next_index", 0)`, no isinstance)
  - `L/job_survey.py:179 SURVEY_COMPLETE telemetry` (same, `spiral_data.get("next_index", start_index)`)
  - `L/archive_cleaner.py:529-534` (validates: `if not isinstance(spiral_data, dict)`)
- Rule: read the spiral progress dict, use `next_index`.
- Differences: **DRIFT** job_survey calls `.get` on the raw value; a stored truthy non-dict (a list) raises `AttributeError` instead of falling back, while `archive_cleaner:534` treats it as invalid.
- Found by: B

## Guarded component read with default (power state, grids, balances)
- Sites:
  - `L/biomass_mixer_gate.py:192 MixerGate._is_powered` (True)
  - `L/station_controller.py:194 StationController.is_station_powered` (True)
  - `L/script_parking.py:898 ScriptParking._is_powered` (False), `:908 _can_power_off` (False), `:920 _is_running` (False)
  - `L/oil_generator.py:183 OilGeneratorController.get_grid` (None), `L/steam_turbine.py:139 SteamTurbineController.get_grid` (None)
  - `L/game_phase.py:277 read_tp` (0.0), `L/weather_signals.py:150 WeatherController.now_gh` (0.0)
  - `L/drone_depot.py:348 DroneDepotController._is_life_form` (False), `L/essence_liquifier.py:122 EssenceLiquifierController.sample_biome` (None)
  - `L/cash.py:89 balance` (0), `L/components.py:147 machine_tier` (1)
  - `L/building_swap_upgrade.py:107 BuildingSwapUpgrader._credits` (0), `L/fleet_commission.py:298 FleetCommissionCoordinator._space_for` (0)
- Rule: read a game component by name; a missing component or raised call logs `swallowed` and returns a per-site fallback. (Research sites moved to the research family.)
- Differences: **DRIFT** "is powered" reads disagree on unknown power state: `biomass_mixer_gate._is_powered` and `station_controller.is_station_powered` fail open (True); `script_parking._is_powered`, `_can_power_off`, `_is_running` fail closed (False). Possibly intentional. Fallback value otherwise per site.
- Found by: A

## Depth-6 BFS over the recipe graph
- Sites:
  - `L/production_cascade.py:149 _cascade_fabricator_output_demand` (shortfall-only; `supply` callback; seeds exempt; skips unsourced inputs; only `fabricator_outputs`; `ladder_max` into `targets`)
  - `L/production_cascade.py:370 _cascade_blueprint_demand` calls `:379 _walk_blueprint_demand` (shortfall-only; no supply; walks Fabricator and Smelter inputs; gross into `total_needed`)
  - `L/production_cascade.py:249 compute_recipe_depths` (depth relaxation, no shortfall, `fabricator_outputs` only)
  - `L/fleet_intent.py:110 _path_to` (bound `ROOT_WALK_DEPTH`=6 at :30; `seen` set + parent map; returns one path)
  - Not walker: `L/production_demand.py:159 get_smelter_demands` (one hop, `_ceil` at :174). Shared accessor `L/production_cascade.py:140 _recipe_inputs_for`; bound `CASCADE_MAX_DEPTH`=6 at :33.
- Rule: walk `_recipe_inputs_for(item)` level by level to depth 6; parent shortfall x ratio is the child demand; at the cap, log and stop.
- Differences: **DRIFT** float carry (`missing * ratio`) in the cascade walkers vs `_ceil` in `get_smelter_demands` for the same Smelter-output demand (may be intentional; check). **DRIFT (latent)** `CASCADE_MAX_DEPTH` and `ROOT_WALK_DEPTH` are separate constants, both 6, no link. Cascade walkers have no visited set (nodes re-expand per level); `_path_to` uses `seen`. Shortfall test, stock source and output filter all differ per walker. Blueprint walker expanding Smelter inputs is documented intent, not drift. `get_manual_order_blocking_items` named in code_quality.md:156-158 no longer exists (nearest `production_cascade.py:636 _fold_manual_orders`, not walked).
- Found by: D

## Shop catalogue price read
- Sites:
  - `ap/building_plan.py:602 read_prices` and `ap/focus_plan.py:232 read_prices` ({id: int(cost)}, identical)
  - `ap/outpost_plan.py:581 kit_price`
  - `L/building_swap_upgrade.py:115 BuildingSwapUpgrader._price`, `L/storage_expand.py:78 StorageExpander._price`, `L/harvester_machines.py:84 shop_price` (one id, fallback)
  - `L/pillar_swap.py:189 PillarSwap._prices` ({id: int(cost)})
  - `L/fleet_commission.py:193 FleetCommissionCoordinator._catalogue` ({id: raw cost})
- Rule: `shop.get_catalogue()`, find the entry for an id (or map all), return cost as int, else a fallback.
- Differences: **DRIFT** (mild) `fleet_commission._catalogue` keeps the raw `cost`, no `int()`. Fallbacks differ.
- Found by: A

## Bio flush then sleep, and run loops
- Sites:
  - `L/bio_processor.py:140 BioProcessorController._idle`, `L/bio.py:412 BioLabController._pause` (flush_all then sleep)
  - `L/bio.py:599 BioLabController.run` (reset, retire, step, flush_all, sleep 0.5)
  - `L/bio.py:761 BioCollectorController.run` (reset, retire, step; no flush, no sleep)
- Rule: flush outgoing signals before every sleep (`tree_console` docstring).
- Differences: **DRIFT** candidate: the collector loop neither flushes nor sleeps. Possibly intentional, not verified.
- Found by: A

## Archive dict read, non-dict to empty (read-and-validate shapes)
- Sites (A, def level; 247 `archive.get(` lines in all: 231 in 90 scripts files, 16 in 8 autoplay files):
  - `L/drone_upgrade.py:118 fleet_upgrade_state`, `L/fleet_decommission.py:65 decommission_state`, `L/pioneer_commission.py:78 commission_state`, `L/cash.py:115 budget`, `L/fleet_status.py:156 get_all`, `L/lead_cask.py:81 roles`, `L/role_demand.py:293 read_claims`, `L/storage.py:283 _retiring_entries`, `L/vent_cycles.py:80 _read_entries`, `L/game_phase.py:288 read_history`, `L/plants_retire.py:33 _telemetry`, `L/biomass_retire.py:76 retire_state`, `L/building_ops.py:185 jobs`, `L/drone_claims.py:254 DroneClaimsMixin.get_biosite_claims`, `L/drone_weather.py:92 aftermath_entries`, `L/early_buyer.py:180 EarlyBuyer.config`, `L/production_demand_record.py:51 _stored`, `L/production_demand_record.py:208 demand_signature.stored`, `L/seed_maker.py:187 SeedMakerController._refresh_tried` (also writes `_tried`)
  - try-guarded: `L/machine_activity.py:213 _read_dict`, `L/retired_machines.py:20 retired`, `L/script_parking.py:807 ScriptParking._vehicle_commands.stored`
  - other: `L/pillar_swap.py:76 swap_state` (None default), `L/logistics_snapshot.py:179 TierView._entry`, `L/plant_terraformer.py:161 _was_running` and `:169 _last_batch_km2` (keyed by `self.name`), `L/construction_lots.py:43 read_priorities`, `:52 read_hold`, `L/fluid_routing.py:63 get_tank_assignments`, `L/production_orders.py:15 get_manual_orders` (both `archive.has` + set + get, then filter values), `ap/autoplay_roles.py:337 outpost_roles`, `ap/blueprint_queue.py:271 planned`, `ap/building_plan.py:310 load`
- Sites (B, line level): `L/archive_cleaner.py:386` (isinstance :390), `:722 consolidate recall`, `L/site_plan.py:55`, `L/bio_retire.py:214 step` (redundant `or {}`), `L/drone_depots.py:289`, `L/drone_energy.py:158 default_cruise_throttle` (None check), `L/archive_cleaner.py:529-532`, `L/fleet_claims_common.py:63 read_mission` (legacy key, None then isinstance), `L/production_demand_record.py:60` (0 default), `L/archive_cleaner.py:728` (False flag), `L/wildlife_planner.py:706` (`[]`).
- Shapes (B regex estimates; 31 multi-line calls unparsed; "no validation" is an upper bound): S1 `get(K, {})` then isinstance, no `or {}` ~86; S2 `get(K, {}) or {}` then isinstance ~36; S3 `or {}` then raw `.get`, no isinstance (small, count unreliable; real instance is the spiral DRIFT); S4 `get(K, None)` then None/truthy test ~15; S5 raw value into a cleaner helper ~8 (`construction_lots.py:46`, `:63 ledger` and `ap/power_survey.py:63` via `clean_power_ledger`, `L/survey_requests.py:53`, `:183`); S6 write-side `_reset_if_not_dict` 4 (`archive_cleaner.py:626`, `:655`, `:811`, `:888`; :811/:888 bodies unread); S7 other defaults ~10.
- Rule: archive key holds a dict; a missing or non-dict reads as `{}` (or None for entry lookups).
- Differences: try-guarded variants also swallow a raised `archive.get`, but `ArchiveClient.get` (`L/archive.py:53`) already returns the default on notebook error and on None. `or {}` before isinstance is redundant. No shared "read dict" helper in lib; closest is private `machine_activity._read_dict`. Per-key cleaners exist (`construction_plan.clean_*`, `survey_requests.clean_requests`).
- Found by: A, B

## Archive read, then per-entry filter or normalise
- Sites: `L/production_docks.py:16 dock_order_prios`, `L/supply_dock.py:209 order_overrides` (identical body), `L/logistics_snapshot.py:129 _units_in`, `L/construction_plan.py:74 clean_priorities`, `L/lead_cask.py:262 _live_inbound`, `L/fluid_routing.py:221 _prune_conflicts`, `L/outpost_flow.py:40 read`, `L/production_orders.py:265 order_consumer_sites`, `L/site_supply.py:489 construction_rush`, `ap/outpost_plan.py:519 load`
- Rule: read a dict key, `{}` when not a dict, keep valid entries (numeric, int, fresh, live), normalise each.
- Differences: predicate varies (`clamp(prio)`, `is_fresh`, `_order_live`, `decayed`).
- Found by: A

## Archive transaction updater coerces non-dict to empty
- Sites:
  - `L/archive.py:133 ArchiveClient.set_entry.updater`, `:176 pop_entry.updater`
  - `ap/autoplay_roles.py:401 prune_roles.updater`; `ap/blueprint_queue.py:50 _record.planned_updater`, `:61 priority_updater`, `:87 cancel.updater`, `:285 prune_planned.updater`
  - `L/construction_lots.py:32 release_finished_claims.updater`, `:146 prune_priorities.updater`; `L/fleet_claims_common.py:40 set_flagged.updater`; `L/production_orders.py:333 set_order.updater`; `L/supply_dock.py:220 set_order_override.updater`
  - `L/biomass_mixer_gate.py:224 MixerGate._record_parked.updater`; `L/turbine_commit.py:296 _heartbeat.updater`, `:308 _record.updater`; `L/outpost_mining.py:170 publish_reach.updater`; `L/seed_maker.py:212 _mark_tried.updater`
  - `L/vehicle_claims.py:347 VehicleClaimsMixin.blacklist_target.updater` (body unread by B); `L/parking_client.py:109 _unpark.unpark`; `L/retired_machines.py:61 release.updater`; `L/script_parking.py:444 ScriptParking._commit.updater`
  - `L/fleet_status.py:145 publish.updater`, `:171 forget.updater` (no coerce); `L/fleet_upgrade.py:312 _advance_depot.drop`, `:480 _migrate_drone_keys.repin`; `L/fleet_decommission.py:318 forget_machine.drop_upgrade`
  - `L/cash.py:261 keep.updater`; `L/building_ops.py:171 mark_retire_ready.updater`, `:255 _patch.updater`
  - `L/pioneer_upgrade.py:91 request_sport_nav.updater`, `:102 clear_sport_nav_request.updater`
  - `L/fabricator.py:713 FabricatorController.publish_wants.updater`, `L/smelter.py:331 SmelterController.publish_want.updater`, `L/fluid_routing.py:242 yield_pipe_conflict.updater`, `L/lead_cask.py:298 set_inbound.updater`
- Rule: `transaction(KEY, {}, updater)` starts from a dict (non-dict becomes `{}`), then sets or pops keys or fields.
- Differences: shapes are set key, pop key, drop-keys comprehension, patch entry field, stamp nested entry. `fleet_status.forget` skips the coerce (pop on non-dict is a no-op). One transaction helper with set/pop args could cover most.
- Found by: A

## Keyed-state mutate wrapper (identical bodies)
- Sites: `L/drone_upgrade.py:124 update_fleet_upgrade` (updater :127), `L/fleet_decommission.py:76 _update` (:77), `L/pillar_swap.py:81 _update` (:82), `L/pioneer_commission.py:83 update_commission` (:86)
- Rule: `archive.transaction(KEY, {}, updater)`, updater coerces to dict then `mutate(state)`.
- Differences: none in bodies; only the archive key.
- Found by: A

## Archive sub-entry lookup and patch
- Sites: lookup `L/drone_upgrade.py:215 drone_swap_entry`, `:220 lineage_entry`, `L/pioneer_commission.py:95 lineage_entry`, `L/fleet_decommission.py:71 decommission_entry`, `L/fleet_status.py:162 get`; patch `L/building_ops.py:252 _patch` (stamps `tick`, calls `archive.transaction` directly), `L/fleet_decommission.py:189 FleetDecommissionCoordinator._patch`, `L/pillar_swap.py:95 _patch_job`; requested-state `L/building_ops.py:161 retire_requested`, `L/fleet_decommission.py:118 is_decommission_requested`
- Rule: lookup `(state().get(section) or {}).get(id)` returns the entry if a dict else None; patch does `entry.update(fields)` on a dict entry; requested-state tests `entry["state"] == "requested"`.
- Differences: state source and section key vary; `retire_requested` reads `archive.get_entry`, the other `decommission_entry`.
- Found by: A

## try around archive.get (double guard)
- Sites: `L/machine_activity.py:213 _read_dict` (try around `get(key, {}) or {}`), `L/construction_lots.py:44 read_priorities` (try around `clean_priorities(archive.get(...))`)
- Rule: `archive.get` already swallows notebook errors (`archive.py:53-62`); the outer try only adds a second `swallowed`. In `read_priorities` the try also covers cleaner exceptions, so not redundant there.
- Differences: only these two sites read; no full `try:` grep.
- Found by: B

## Survey archive reads (unsupported targets, requests, blocked, biomass)
- Sites:
  - `L/survey_requests.py:175 read_unsupported` (shared; reserved-guard first; `archive.available` guard) (B says :171 for the helper)
  - `L/survey_requests.py:48 read_requests`, `:164 read_blocked` (B: :168, passes raw to `blocked_targets` :121), `:179 read_known_biomass` (B: :183, `known_biomass` validates :105)
  - Bypassing `read_unsupported`: `L/drone_scout.py:44`, `L/unsupported_markers.py:156`, `:261` (`or {}` then isinstance)
  - `L/vehicle_claims.py:342`, `:444` (grep only, bodies unread); `L/archive_cleaner.py:438` (raw into `_merge_unsupported`, validation unread)
- Rule: `if not archive or not archive.available: return default`; one `archive.get`; one clean helper. Unsupported-targets variant: dict of blacklisted survey targets, `{}` on non-dict.
- Differences: default `{}` vs `(set(), set())` vs `[]`; some return `set()` or False on bad values. Only `read_unsupported` has the `archive.available` guard; no validation drift found.
- Found by: A, B

## Guarded get_component wrapper copies
- Sites: `L/building_swap_upgrade.py:55 component` (adds a `where` label), `L/components.py:108 _component`
- Rule: `get_component(id)` wrapped so a raised lookup logs `swallowed` and returns None.
- Differences: building_swap takes a label; `components.component` is the documented home. Generic `get_component` call sites (hundreds) not enumerated.
- Found by: A, B

## Guarded game-object method read with default
- Sites:
  - `L/fluid_routing.py:140 safe_is_stalled`, `:160 port_connections`, `:274 fill_pct_of`, `:618 _safe_fluid`, `:725 tank_fill`
  - `L/refiner.py:251 RefinerController._capacity`, `L/script_parking.py:585 ScriptParking._well_active`, `L/supply_dock.py:655 _dock_loaded`, `L/profiling.py:41 begin`, `L/tree_console.py:191 _stamp`
  - `L/drone_cargo.py:67 cargo_capacity`, `:74 cargo_full`, `L/drone_haul_plan.py:555 item_room`, `L/drone_navigation.py:59 status`, `:80 current_station`, `:87 current_drill`, `L/drone_weather.py:382 _exposure`
  - `L/essence_liquifier.py:113 stall_reason`, `L/field_provider.py:81 sector`, `L/crop_automator.py:128 _read_sector`, `L/charging_stations.py:168 current`, `L/harvester_amplify.py:54 amplifier_hours`
  - `L/harvesting.py:46 detect_base_sector` ("E13"), `:54 get_position`, `:70 get_heat`
  - `L/pioneer_commission.py:236 LoadoutFittingMixin._slots`, `L/pioneer_stock.py:141 ConstructionStockMixin._cargo_space_for`, `L/vehicle_mining.py:67 cargo_full_for_resume`, `L/vehicle_survey.py:128 sonar_tier`, `L/vehicle_claims.py:399 _mounted_tier`
  - `L/reactor.py:256 ReactorController.read_heat`, `L/seed_maker.py:149 _read_life_forms`, `:156 _recipes`, `:301 _output_count`, `:700 _safe_is_running`, `L/steam_condenser.py:291 rate`, `L/storage_unload.py:36 _holder_count`, `L/terraforming.py:157 Mk3FluidFeed._tier`, `L/thermal_cap.py:207 read_rate`
  - `ap/fluid_outlook.py:249 read_hazards.biome_of`, `:294 read_contacts.biome_of`
- Rule: `try: return host.method()` with `swallowed` and a per-site default; many pre-check `hasattr`, truthiness or None.
- Differences: default and pre-check vary; `harvesting.detect_base_sector` hard-codes "E13".
- Found by: A

## Guarded getattr-by-name or thunk call helper
- Sites: `L/biomass_mixer.py:147 BiomassMixerController._read`, `L/biomass_mixer_gate.py:162 MixerGate._call`, `L/biomass_retire.py:81 _call`, `L/plants_retire.py:43 _call` (getattr by name); `ap/building_plan.py:593 _safe`, `ap/outpost_needs.py:632 _call`, `au/builder_automation.py:88 run_step` (thunk)
- Rule: call a game read, log on exception, return a fallback; each module re-implements the wrapper.
- Differences: `run_step` logs via `report_error`; the rest via `swallowed` with a label.
- Found by: A

## Sensor value read
- Sites: `L/biomass_retire.py:61 biomass_tons` (0.0), `L/plant_terraformer_common.py:45 plants_km2` (None), `L/wildlife_planner.py:957 _population` (None)
- Rule: `get_component(sensor).get_value()`, guarded, with fallback.
- Differences: fallback 0.0 vs None.
- Found by: A

## Network outposts list guard
- Sites: `L/drone_kit_stock.py:24 _outposts`, `L/lead_cask.py:70 _all_outposts`, `L/site_supply.py:174 _outposts`, `L/building_swap_upgrade.py:89 BuildingSwapUpgrader._outposts`, `L/pillar_swap.py:160 PillarSwap._outposts`, `L/storage_expand.py:61 StorageExpander._outposts`, `L/drone_haul_plan.py:138 outposts_by_id` (dict), `L/fleet_upgrade.py:133 FleetUpgradeCoordinator._drones` (fleet as id dict)
- Rule: `get_component("outpost_network").outposts()` (or fleet) in a guard; list or id dict, `[]`/`{}` on miss.
- Differences: some check `hasattr(network, "outposts")`; `storage_expand` and `pillar_swap` use `component()`; two return dicts.
- Found by: A

## Outpost-by-id lookup
- Sites: `L/outpost_mining.py:74 outpost_by_id` (via `_outpost_network()`), `L/production_sites.py:139 outpost_by_site_id` (via `_all_outposts()`), `ap/blueprint_queue.py:25 _construction_outpost` (matches construction site id)
- Rule: scan outposts for the matching id; return ref or None.
- Differences: as listed.
- Found by: A

## Components of one type at one outpost (resolve, drop None)
- Sites:
  - `L/lead_cask.py:124 _components_at` (walk :128; `[]` for None outpost), `L/fuel_assembler.py:146 FuelAssemblerController._buildings` (walk :151); same body
  - `L/bio_orders.py:28 local_sibling` (walk :44; first resolved only)
  - `L/drone_depot.py:139 DroneDepotController._find_local_liquifier` (walk :149; exactly one or None)
- Rule: `outpost.buildings(type_id)` then `get_component(ref.id)`, keep non-None.
- Differences: lead_cask and fuel_assembler agree (no drift). `bio_orders.local_sibling` ~ `discover_building_ids(type, outpost)[0]` then get_component. `_find_local_liquifier` can call `production_core.discover_building_ids(LIQUIFIER_TYPE_ID, outpost)` as is (drone_depot.py:44 already imports production_core). lead/fuel need an `if outpost is None: return []` guard (helper goes network-wide with None). `discover_building_ids` memo is 20 ticks (~2 s); check reads that must see a just-placed building. Import cycle for lead_cask / bio_orders unverified.
- Found by: A, C

## Per-outpost building ids of one type (no resolve)
- Sites:
  - `L/water_sink.py:53 WaterAwareWasteSinkController._water_duty` (walk :59; True on failure)
  - `L/steam_condenser.py:227 SteamCondenserController.sink_draining_target` (walk :237)
  - `L/building_swap_upgrade.py:100 BuildingSwapUpgrader._ids_of` (walk :102; sorted, drops empty ids)
  - `L/pillar_swap.py:168 PillarSwap._ids_at` (walk :172; sorted), `:177 _machines` (walk :182; network (outpost_id, id) sorted)
  - `L/building_ops.py:283 _ids_at` (walk :297; read only)
  - `L/feed_maker.py:250 FeedMakerController._read_habitat_ids` (walk :253)
- Rule: ids of one type_id at one outpost, sorted by the caller.
- Differences: all can call `production_core.discover_building_ids(type_id, outpost)` as is, except `pillar_swap._machines` (needs outpost_id per id: use `discover_network_buildings(type, resolve=False)`). Swap flows run right after deploys and the 20-tick memo can lag (possible keep?). `fleet_*` and `outpost_mining` import cycles unverified.
- Found by: C

## Storage stores
- Sites: `L/site_evict.py:186 storage_outposts` (outpost has STORAGE_TYPE_IDS and DEPOT_TYPE_TIERS and no PENALIZED_TYPES)
- Rule: outpost holds a storage store (warehouse, large_warehouse, storage_bin).
- Differences: reads unfiltered `outpost.buildings()` and intersects type-id sets; can call `discover_storage_buildings(outpost)` for the storage half; depot and penalized halves stay set checks.
- Found by: C

## Charging stations (CHARGING_STATION_TYPE_ID)
- Sites: `L/charging.py:27 ChargingStationController.all_station_refs` (walk :41), `L/charging_stations.py:43 _scan_stations` (all outposts, dedupe by id, `coords_of`; canonical `all_stations` at :32)
- Rule: every charging_station with a position across outposts, dedup by id.
- Differences: `all_stations()` returns {id, coords, outpost, component}; charging.py keeps {id, coords} and reads only coords (call at charging.py:62), so it can call `all_stations` as is. No drift. `coords_of` vs `drone_depots._extract_coords` not compared.
- Found by: A, C

## Per-outpost site lists (fab and lab sites)
- Sites: `L/site_evict.py:148 fab_sites`, `:153 lab_sites`
- Rule: outposts with a fabricator or bio lab, sorted ids.
- Differences: both use `discover_*` already.
- Found by: A

## Water tanks (LIQUID_TANK_TYPE_IDS)
- Sites: `L/water_sink.py:66 WaterAwareWasteSinkController._water_tanks` (walk :75; own outpost, `tank_is_eligible_target(tank, WATER_FLUID_ID, assignments)`), `L/wildlife_planner.py:661 _tank_refs` (walk :668; network-wide, skip retiring, dedup; inside `run_atomic`)
- Rule: every liquid tank latched to the fluid and not retiring.
- Differences: `water_sink` can call `discover_network_buildings(LIQUID_TANK_TYPE_IDS, fluid_id=WATER_FLUID_ID)` and filter own outpost; same eligibility, no drift. `wildlife_planner` can call it per type with `resolve=False`; whether the helper's reads are pure inside `run_atomic` unverified.
- Found by: C

## Network-wide ids and records (non-machine)
- Sites: `L/weather_signals.py:97 discover_stations` (walk :105; (station_id, biome, powered)), `L/wildlife_planner.py:578 network_habitats` (walk :589; sorted ids + home from is_home)
- Rule: every building of one type across `outpost_network`.
- Differences: `network_habitats` can use `discover_building_ids(type_id)`; home via `components.home_outpost()` (equivalence unchecked). `discover_stations` needs snapshot `powered` and outpost biome, which the helper does not return (needs param, or keep?).
- Found by: C

## Supply dock walk (per outpost)
- Sites: `L/storage.py:716 _items_demanded_by_active_dock_orders` (walk :739)
- Rule: every supply_dock at an outpost, components with `current_order`.
- Differences: `production_core.discover_supply_dock_ids(outpost)` (production_core.py:373) is the same walk; storage.py:725 avoids importing production.py for circularity. production_core imports (archive, components, game_clock, game_rules, outpost_mining, swallow, tree_console) exclude storage, but outpost_mining's imports unchecked.
- Found by: C

## Tier-0 building walks
- Sites: `s0/atmos/heater.py:39 get_battery_pct` (walk :45), `s0/power/solar.py:84 get_master_solar_id`, `:109 get_building_ids`
- Rule: buildings of one type at home or own outpost.
- Differences: discovery helpers are tier 4; tier 0 cannot import them. Would need a tier-0 helper.
- Found by: C

## _dist(ax, ay, bx, by) copies
- Sites: `ap/outpost_needs.py:198 _dist`, `ap/outpost_plan.py:96 _dist`, `ap/outpost_sites.py:167 _dist`, inline `ap/outpost_sites.py:814` and `:851` (comments say "_dist() inlined"), `L/geometry.py:4 distance(a, b)` (tuples), `L/site_evict.py:195 _distance(a, b)` (wraps `geometry.distance`; 0.0 on None). Not copies: `ap/outpost_sites.py:171 _rect_dist`, `ap/grid_geom.py:221` (Manhattan).
- Rule: `sqrt((ax-bx)^2 + (ay-by)^2)` metres, no clamping.
- Differences: arg shape (4 scalars vs 2 tuples); `** 2`/`** 0.5` vs `dx*dx`/`sqrt` (same up to rounding); None handling only in `site_evict._distance`. outpost_needs and outpost_plan define their own instead of importing `outpost_sites._dist` (outpost_plan imports from outpost_sites but not `_dist`). Autoplay copies cannot share with `geometry.py` across the tier boundary. No drift.
- Found by: D

## Game clock tick copies
- Sites: `ap/building_plan.py:94 _tick`, `ap/outpost_plan.py:510 _tick`, `ap/planner_loop.py:36 _tick`, `ap/power_survey.py:44 _now_tick`; canonical `L/game_clock.py:36 now_tick`
- Rule: current tick via the clock component; 0 if unreadable; `swallowed` on error.
- Differences: only the swallowed label; the four copies can import `game_clock.now_tick`.
- Found by: A

## Stale-stamp prune then set
- Sites: `L/fabricator.py:713 FabricatorController.publish_wants.updater`, `L/smelter.py:331 SmelterController.publish_want.updater`, `L/fluid_routing.py:242 yield_pipe_conflict.updater` (via `_prune_conflicts`), `L/lead_cask.py:298 set_inbound.updater` (via `_live_inbound`)
- Rule: drop entries older than a TTL, store one entry, in one archive transaction.
- Differences: fabricator and smelter inline `now - (tick or 0) >= STALE` instead of `is_fresh`. Checked: same semantics as `game_clock.is_fresh`, no bug. Done row "is_fresh for Smelter/Fabricator wants" names production_core, so may not cover these.
- Found by: A

## Sport-nav request flag
- Sites: `L/pioneer_upgrade.py:68 is_sport_nav_requested`, `:88 request_sport_nav` (also `resume_vehicle`), `:101 clear_sport_nav_request`
- Rule: per-vehicle flag in one archive dict. Shared helpers exist: `fleet_claims_common.is_flagged` (:29), `set_flagged` (:37).
- Differences: the rest duplicate `is_flagged`/`set_flagged` with another key.
- Found by: A

## Recall flag setter
- Sites: `L/drone_claims.py:44 set_drone_recalled`, `L/vehicle_claims.py:113 set_vehicle_recalled`
- Rule: `common.set_flagged(KEY, name, recalled)`, then `resume_vehicle` when recalled.
- Differences: key and name only.
- Found by: A

## Small families (A, one line each)
One bullet per family: sites, rule, differences.
- **Own-outpost-first fluid source discovery**: `L/fabricator.py:176 FabricatorController._discover_fluid_candidates`, `L/steam_turbine.py:103 SteamTurbineController._discover_candidates`, `L/reactor.py:266 ReactorController._discover_water`, `L/steam_condenser.py:127 SteamCondenserController._discover_steam_sources`. Rediscover ranked sources, own outpost first, debug-log. Fabricator and reactor use `production_fluids.discover_fluid_sources`; turbine and condenser use `fluid_routing.discover_ranked(STEAM_SOURCE_TIERS, own)`; reactor fixes "water_in".
- **Tanks and producers ranked discovery**: `L/habitat.py:288 HabitatController._discover.discover`, `L/refiner.py:366 RefinerController.routers.discover`. `discover_network_buildings` + `discover_producers` + `rank_sources`. Types from `MEDIA[medium]` vs `in_types` and `RAW_PRODUCER_TYPE_IDS`.
- **Keyed sum or count accumulate**: `L/harvester_pure.py:136 merge_counts`, `L/vehicle_mining.py:51 sum_bands`, `L/logistics_requests.py:809 sum_tiers`, `L/priority.py:269 band_deficits`, `L/role_demand.py:314 claimed_counts`, `L/fleet_intent.py:33 _add`, `L/production_core.py:384 _add_demand`. `out[key] = out.get(key, 0) + n`. `_add`/`_add_demand` skip empty ids and non-positive units; `sum_tiers` iterates fixed TIERS; `claimed_counts` counts entries.
- **Positive remainder dict**: `L/logistics_snapshot.py:151 _new_reservations`, `L/seed_supply.py:117 SeedSupplyController._deficits`, `L/production_cascade.py:464 remote_dock_reservations`. `{k: want - have if > 0}`; inputs differ.
- **Per-pass memo get-or-compute**: `L/field_layout.py:585 _full_parts`, `L/harvester_hub.py:141 HarvesterHubMixin.stock_count`, `L/logistics_requests.py:575 PlanReads.depot_holds`, `:589 reserved_from`, `:597 scan`, `L/production_source.py:133 SourceCache.scan`. `get`, compute on None, store. Cache on module, host or plan object; `PlanReads.scan` and `SourceCache.scan` identical; `TickCache` covers tick-scoped memos.
- **Lazy-once SourceCache attributes**: `L/production_source.py:153 outposts`, `:226 smelter_holdings`, `:332 fuel_assembler_recipes`, `:360 surveyed_sites`. `if self._x is None: compute`. The last two also swallow and store `[]`.
- **Lazy dict attribute via hasattr**: `L/harvester_machines.py:193 _deploy_failures`, `L/harvester_planting.py:496 _plant_failures`. Attribute name only.
- **Pickup ledger totals**: `L/logistics_requests.py:482 in_flight`, `:498 aboard_units`, `:514 reserved_from`. Sum `units` by item over fresh PICKUPS, one filter field each.
- **Commission home sentinel**: `L/fleet_commission.py:154 queue_pioneer`, `:159 queue_drone`, `L/commission_card.py:126 order_pioneer`, `:131 order_drone`. HOME_OUTPOST_ID to None before queueing. `home_base` vs `outpost`; log wording differs.
- **Card status badge**: `L/drones_card.py:143 badge`, `L/vehicles_card.py:62 badge`. Precedence rescue, retire blocked, retiring, recalled; drones add "upgrading", vehicles add "sport nav pending".
- **Card id-of**: `L/drones_card.py:33 drone_id_of`, `L/vehicles_card.py:78 vehicle_id_of`. `str(getattr(x, "id", getattr(x, "name", default)))`; default differs.
- **Poll sleep after step**: `L/fabricator.py:88 next_sleep`, `L/smelter.py:75 next_sleep`. Identical bodies (`parker.update(not active)`).
- **Ladder point update**: `L/priority.py:144 ladder_raise` (max), `:172 ladder_add` (sum). Insert/merge into sorted ladder, `_normalize`.
- **Ladder totals map**: `L/production_cascade.py:51 totals`, `L/production_orders.py:299 order_items` (adds `skip`). `{item: ladder_total(levels)}`.
- **Highest obtainable on a ladder**: `L/drone_commission.py:51 _best`, `L/drone_upgrade.py:301 _best_in_inventory`, `:307 _best_obtainable`, `L/pioneer_upgrade.py:241 _top_tier`. Walk from top, first held/unlocked; predicate differs.
- **Stranded items per outpost**: `L/site_evict.py:272 stranded_goods`, `:158 stranded_reagents`. Held items with no kept request or live consumer; goods vs `LAB_REAGENT_ITEM_IDS`.
- **Cask stock free and held split**: `L/lead_cask.py:172 rods_for_orders`, `:190 rods_free_for_mk4`. `(max(0, stock - held), min(stock, held))`; held source differs.
- **Mission circle lookup**: `L/mission_pool.py:146 _outpost_in`, `L/survey_requests.py:67 request_at`. First id-sorted entry whose circle contains the point; founded tuple (sort `key=str`) vs request dicts.
- **Plan complete flag**: `L/feed_maker.py:120 FeedMakerController.complete`, `L/wildlife_common.py:146 wildlife_complete`. `bool(archive.get(PLAN, {}).get("complete"))`; plan key differs.
- **All inputs covered by stock**: `L/feed_maker.py:150 has_inputs`, `L/fuel_assembler.py:254 can_stage`. `all(held + stock >= qty)`; dict vs `stockpile()`/`available()`.
- **Power shed membership**: `L/crop_automator.py:180 is_shedded`, `L/field_provider.py:130 is_shedded`, `L/fuel_assembler.py:412 shed`. `self.name in archive.get("power.shedded", [])`; three repeat the literal; `L/biomass_mixer_gate.py:85` has `SHEDDED_KEY`.
- **Mission target accessors**: `L/drone.py:162 current_target`, `:171 current_target_key`, `L/vehicle.py:130`, `:139`. Identical on two controllers.
- **Adopt mission**: `L/drone_claims.py:229`, `L/vehicle_claims.py:278` `adopt_mission`. Trivial identical bodies.
- **Docked at station**: `L/drone_charging.py:113 docked_at_service`, `L/drone_upgrade.py:356 _docked_at_depot`. Services vs depots list.
- **Controller init boilerplate**: `L/bio.py:34`, `:307`, `:620`, `L/harvesting.py:33`, `L/waste_sink.py:31` `__init__`. `self.name = getattr(machine, "id", default)`; `TreeConsole(module=...)`.
- **Coordinator init with warned map**: `L/building_swap_upgrade.py:80`, `L/fleet_decommission.py:127`, `L/fleet_upgrade.py:96`, `L/pillar_swap.py:154` `__init__`. `self.log` + `self.warned = {}`; pillar_swap takes log from module scope.
- **Lazy archive import**: `L/outpost_mining.py:64 _archive`, `L/outpost_reagents.py:45 _archive`. Deferred import to avoid a cycle; identical.
- **Automation step guard and report_error**: `au/orchestrator_automation.py:216 plan_wildlife_if_due`, `:314 buy_early_if_due`, `:322 publish_logistics_if_due`, `au/builder_automation.py:81 report_error`, `au/orchestrator_automation.py:182 report_error`. Generic form is `run_step`. The two `report_error` copies differ only in tag (`[BUILDER]` vs `[AUTOMATION]`).
- **rc_to_sector duplicate**: `L/field_layout.py:275 rc_to_sector`, `L/harvesting.py:40 HarvesterController.rc_to_sector`. harvesting repeats `ROWS`, `NUM_ROWS`, `NUM_COLS` (:21-23) instead of importing field_layout (:59-61); same values today.
- **ceil_int duplicate**: `ap/grid_geom.py:125 _ceil_int` (`int(value // 1)`), `L/plant_terraformer_common.py:55 ceil_int` (`int(value)`). Both correct for negatives; shared helper must live in a scripts lib.
- **Archive cleaner stale prune**: `L/archive_cleaner.py:609 clean_telemetry` (legacy-prefix delete first), `:647 clean_mining_reach`. Drop entries not in the active fleet or malformed, `_prune_dict_key`.
- **Drone haul destination and source walk**: `L/drone_haul_plan.py:155 haul_destinations`, `:242 outpost_sources`. Walk depot outposts, skip missing and stall-cooldown, append dict on demand/availability; `tier_deficits`/`sum_tiers` vs `outpost_tier_free`/`most_free`.
- **Free stock elsewhere**: `L/site_supply.py:185 free_elsewhere`, `:201 free_elsewhere_tiers`. Sum free stock over other outposts; flat vs per-tier.
- **Hysteresis gate update with flip logging**: `L/steam_condenser.py:199 update_steam_gate`, `:213 update_water_gate`, `L/terraforming.py:187 Mk3FluidFeed._update_guard`. `latch.update(fraction)`, log on flips. `_update_guard` also disconnects the port on "on"; water gate message comparisons inverted. `HysteresisLatch` exists (`L/hysteresis.py`).
- **Category to tier ladder**: `L/drone_commission.py:40 _ladder`, `L/drone_upgrade.py:291 _category_ladder`. Energy/cargo/role to ladder; `engine` arg vs `self._host.engine`.
- **Record sub-dict parse**: `L/production_demand_record.py:140 depths_entry`, `:146 blueprint_entry`. Key name only.

## keep? (same shape, different intent)
From A (scan pairs), judge decides:
- `L/charging_stations.py:123 station_at` <-> `L/outpost_mining.py:74 outpost_by_id`: first building with coords vs outpost by id.
- `L/drone_commission.py:89 drone_craft_parts` <-> `:95 drone_buy_parts`: complementary halves of one split.
- `ap/infra_topology.py:200 walls` <-> `:205 held`: complementary partitions of one layer by fluid label.
- `L/production_cascade.py:443 outranking_order_wants` <-> `L/pump_salt.py:109 salt_sources`: positive filters over different inputs.
- `L/logistics_requests.py:840 outpost_deficits_tiered` <-> `:898 outpost_deficits`: split vs summed output of one tier read.
- `L/vehicle_energy.py:268 active_modules_count` <-> `:298 nav_power_multiplier`: thin delegations to `*_for` helpers; vehicle energy kept separate by design.
- `L/oil_generator.py:174 ensure_input_connection` <-> `L/steam_turbine.py:117 ensure_input_connection`: glue over `fluid_routing.ensure_input_logged`; messages and starved source differ.
- `L/steam_condenser.py:134 ensure_steam_input` <-> `L/oil_generator.py:174`: same glue, different messages.
- `L/role_demand.py:455 refresh_slot` <-> `:461 release_slot`: refresh vs release on one claim key; already on common claim helpers.
- `L/vehicle_claims.py:225 refresh_claim` <-> `L/drone_claims.py:203 refresh_biosite_claim`: glue over `common.refresh_claim`; keys differ.
- `L/drone_navigation.py:66 is_stranded` <-> `L/vehicle_navigation.py:48 is_at_base`: status-set test vs distance threshold.
- `L/job_mine.py:35 MineJob.__init__` <-> `L/job_survey.py:31 SurveyJob.__init__`: different fields.
- `L/bio_coastal.py:23 BioLuminizerController.__init__` <-> `L/bio_geothermal.py:24 DnaSequencerController.__init__`: per-machine cache-once init, different fields.
- `L/logistics_snapshot.py:200 TierView.deficits` <-> `:66 _bands_out`: copy-out of nested dicts, different filters.
- `L/feed_maker.py:90 recipes` <-> `L/refiner.py:290 unlocked_recipes`: both already TickCache glue.
- `L/construction_plan.py:152 at_priority` <-> `:272 ids_needing`: one list filter per field.
- `L/bio_retire.py:72 biome_retired` <-> `L/lead_cask.py:245 network_cask_stock`: any vs sum over the same outpost walk.

From C (bypassed discovery):
- `s0/atmos/heater.py:39 get_battery_pct`, `s0/power/solar.py:84`, `:109`: tier boundary; keep unless a tier-0 helper is wanted.
- `L/building_swap_upgrade.py:100 _ids_of`, `L/pillar_swap.py:168 _ids_at`, `:177 _machines`: 20-tick memo may lag a just-deployed or swapped building; keep unless the memo is bypassed for swaps.
- `ap/focus_plan.py:215 read_generators`: strict all-or-nothing read vs the helper's partial-tolerant walk.
- `L/weather_signals.py:97 discover_stations`: snapshot powered flag and outpost biome not in the helper's return.
- `L/commission_card.py:47 read_outposts` (line 63): may count unresolved depots on purpose; confirm before aligning with `local_depots`.

## Harvest gaps
What the harvesters did not finish; the judge should look here.
- A: clusters c32 (~90 one-line accessors) and c72 checked only for the listed families; stubs skipped (`NotImplementedError` bodies in c92, default hooks `Job.hold`, `Job.prepare_cargo`, `PullJob.on_error` in c37); `coords_of` vs `_extract_coords` not compared; `building_swap_upgrade._large_unlocked` unread by A (B and D read it).
- B: `archive.get` shape counts are regex estimates (31 multi-line calls unparsed); `L/vehicle_claims.py:342`/`:444` and `L/archive_cleaner.py:811`/`:888` bodies unread; generic `get_component` sites not enumerated; `real_seconds_per_hour` not reported (Done row, no bare readers left).
- C: `L/storage_take.py:65` loop top unread (post-filter on `ref.type_id`); `control_panel/production_panel.py:176` is a count, skipped; import cycles (lead_cask, bio_orders, fleet_*, outpost_mining) unverified; wildlife `run_atomic` pure-read requirement unverified.
- D: `get_manual_order_blocking_items` no longer exists (nearest `_fold_manual_orders`, not walked).
