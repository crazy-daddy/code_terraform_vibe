# Helper sweep: candidate families (judged)

Candidates for [helpers_sweep.md](done/helpers_sweep.md), merged 2026-10-23 from four harvest angles, judged the same day (Task 3: every site re-read; wrong lines corrected in place). No code was changed. Part 2, [helpers_sweep_candidates_2.md](helpers_sweep_candidates_2.md), holds the small families, the `keep?` pairs, the harvest gaps and the families the judge found on its own; the `## Ranking` at the end of this file covers both parts.

Angles (the `Found by` letters):
- **A** scan pairs: `devtools/code_scan/clone_scan.py --min-ratio 0.85 --min-lines 3 --top 0` (130 clusters, all triaged).
- **B** game API anchors: callers of `research.is_unlocked`, `archive.get`, `get_component`.
- **C** bypassed discovery: per-outpost building filters that skip `discover_storage_buildings` / `discover_network_buildings` / `production_core.discover_building_ids`.
- **D** known families refresh: 2026-10-09 families re-read in live code.

Path key: `L/` = `scripts/4_controlpanel/lib/`, `au/` = `scripts/4_controlpanel/automation/`, `ap/` = `autoplay/lib/`, `s0/` = `scripts/0_cold_boot/`. Sites are `path:line qualname`, def lines unless noted. Order: DRIFT families first, then the rest.

Verdict block per family: `merge` (one helper replaces the copies), `keep` (same shape, different intent; its pairs go to `devtools/code_scan/clone_scan_ignore.txt` in Task 4) or `drift-bug` (copies disagree; which one is right and why). Owner is the module the helper lives in; `Apart` names the sites that stay as they are and why; risk `low | medium | high`; size `S | M | L`. Import rules applied: `scripts/<tier>` never imports `autoplay/lib`; tier 0 never imports tier 4 libs; autoplay modules import script libs freely (every `ap/` file already imports `components`, `game_clock`, `storage`, ...), but the planner's import chain runs under the 10,000-step cap (CODE_GUIDES "Game interpreter"), so a helper for an `ap/` site must sit in a small lib. Cycles were checked against the current import lists.

## Research unlock guards (`research.is_unlocked` wrappers)
- Sites:
  - `L/early_buyer.py:96 is_unlocked` (generic id arg; internal callers :194 :237 :279 :338; no outside importer)
  - `L/drone_depots.py:83 heli_unlocked`
  - `L/drone_scout.py:23 _exotic_research_done` (`all()` over `SURVEY_RESEARCH["exotic"]`)
  - `L/drone_weather.py:130 hot_cargo_unlocked`
  - `L/pioneer_upgrade.py:76 sport_nav_unlocked`
  - `L/pioneer_upgrade.py:163 PioneerUpgradeMixin._seismic_wanted` (guard at :171-177, `all()` over `SEISMIC_RESEARCH_IDS`)
  - `L/storage.py:606 inventory_stack_size`, `L/storage.py:677 warehouses_unlocked`
  - `L/survey_requests.py:149 unlocked_scan_research` (returns list)
  - `L/vehicle_claims.py:66 scan_research_snapshot` (list, also `research.unlocked()` count)
  - `L/vehicle_claims.py:460 VehicleClaimsMixin.can_attempt_target` (inline per-id loop at :512-518)
  - `L/site_supply.py:378 _stock_table` (inline at :386-395, lazy `component("research")`)
  - `L/game_phase.py:250 read_research` (set-valued; prefers `research.unlocked()`, per-id fallback; None on failure)
  - `L/building_swap_upgrade.py:125 BuildingSwapUpgrader._large_unlocked` (researched OR inventory)
  - `L/storage_expand.py:69 StorageExpander._unlocked` (researched OR inventory)
  - `s0/power/solar.py:95 is_tech_unlocked` (tier 0; `research` bound at :29)
  - `ap/`: 0 sites.
- Rule: resolve the research component, guard it, call `research.is_unlocked(id)`, `bool()` it; a missing or raising component logs `swallowed` and reads as not unlocked. Two copies add "or one sits in inventory" (`inventory_count(type) > 0`).
- Differences: `s0/power/solar.py:29` binds `research = get_component("research")` once at import; all other copies resolve per call. Lookup spelling varies: `component("research")` (early_buyer, storage_expand, site_supply, game_phase), `get_component` (drone_*, pioneer_upgrade, survey_requests, vehicle_claims), `components.component` (storage x2), `self._component` (building_swap_upgrade). Guard varies: `not research`, `is None`, `hasattr(research, "is_unlocked")`. Exception result varies: False, fall to inventory, skip id, try id variants (solar:98), whole read None (game_phase:273).
- Found by: A, B, D
- Verdict: **merge**, plus one tier-0 cleanup (not a drift-bug, see below).
  - Owner `L/components.py`: `research_unlocked(research_id, where="components.research_unlocked") -> bool` and `all_research_unlocked(research_ids, where=...) -> bool` (`all()` over the first; False on an empty list is fine for both callers).
  - Rule: per-call `component("research")`; `bool(research.is_unlocked(id))`; a missing component or a raised call is `swallowed(where)` and reads False. No `hasattr` guard and no id variants: docs/components/research.md says `is_unlocked` returns False for a locked or unknown id, so a `get_component` result either has the method or is None. `not research` and `is None` are the same test (get_component returns a component or None, docs/guide/builtins_and_commands.md).
  - Sites merged (12): early_buyer.is_unlocked (becomes the helper or a one-line alias for its 4 internal callers), heli_unlocked, _exotic_research_done (all_), hot_cargo_unlocked, sport_nav_unlocked, _seismic_wanted :171-177 (all_), inventory_stack_size, warehouses_unlocked, _stock_table :386-395 (one call per gated item; the lazy resolve goes), _large_unlocked and storage_expand._unlocked (`research_unlocked(rid) or inventory_count(type_id) > 0`; two sites, no `unlocked_or_held` helper), can_attempt_target :512-518 (`research_unlocked(res_id)` per id inside the loop).
  - Apart: `survey_requests.unlocked_scan_research` and `vehicle_claims.scan_research_snapshot` return lists and keep going past a raising id (a blacklist entry needs the partial list); `game_phase.read_research` is set-valued via `research.unlocked()` with None meaning "keep the last snapshot"; `s0/power/solar.py` cannot import tier 4.
  - Behavior change (safer): `drone_depots.py:85`, `drone_scout.py:25`, `drone_weather.py:132`, `pioneer_upgrade.py:78` and `:171` call `get_component("research")` outside their `try`, so a raised lookup escapes today; through `components.component` it is swallowed and reads "not unlocked". The storage, early_buyer, site_supply, game_phase, building_swap and storage_expand copies already go through `component()`; the merge aligns the rest with them, it is not the same behavior at those five sites.
  - Tier-0 cleanup, not a bug: `s0/power/solar.py:29` binds `research` at import, but docs/components/research.md says the component is "Available from the beginning" and `get_component` returns None only for an id no entity has (docs/guide/builtins_and_commands.md:113), so the bind never misses (the `research_computer` gate at :247 is the Ship Computer building, a different thing). What remains: the id-variant loop at :98-106 probes non-public ids that research.md says read False (dead weight), and the import-time bind is style. Nit, low risk, S, no owner change (tier 0).
  - Risk: low. Size: M (12 sites, 2 helpers).
- Landed: Phase 1 (helpers-impl-1), `refactor(components): one research unlock guard`.

## Depot walks (DEPOT_TYPE_TIERS: drone_station, drone_station_medium, drone_station_large)
- Sites:
  - `L/logistics_requests.py:614 local_depots` (per outpost, resolves via `drone_station()`, drops unresolved)
  - `L/fleet_upgrade.py:106 FleetUpgradeCoordinator._depots` (network, per tier, dicts id/name/type_id/outpost_id)
  - `L/fleet_decommission.py:146 FleetDecommissionCoordinator._depot_ids` (network, per tier, id set)
  - `L/commission_card.py:47 read_outposts` (membership on `ref.buildings()`, line 63-64)
  - `L/drone_depots.py:150 _scan_drone_buildings` (behind `discover_drone_depots` :204, memoized by `_DISCOVERY` TickCache :37)
- Rule: every building at an outpost whose type_id is in DEPOT_TYPE_TIERS.
- Differences: `commission_card.read_outposts:63` counts unresolved depot refs as depots; `logistics_requests.local_depots` drops them. `drone_depots._scan_drone_buildings` drops refs with no coords; `fleet_upgrade._depots` and `fleet_decommission._depot_ids` keep them.
- Found by: C
- Verdict: **merge** (two sites); the DRIFT is not a bug.
  - Owner `L/drone_depots.py`, existing `discover_drone_depots() -> list[dict]` (`id`, `name`, `coords`, `outpost`, `outpost_id`).
  - Rule: one memoized network walk over DEPOT_TYPE_TIERS. `fleet_decommission._depot_ids` becomes `{d["id"] for d in discover_drone_depots()}`; `fleet_upgrade._depots` reads `id`/`name`/`outpost_id` from the rows and the tier from `item_tiers` by id prefix or a `type_id` field added to the row (one line in `_scan_drone_buildings`). Both modules import drone_depots already (fleet_upgrade) or can (fleet_decommission imports drone_claims, no cycle: drone_depots imports components/game_clock/swallow only).
  - Not a bug: docs/models/outposts_and_power.md says `buildings()` lists deployed buildings and each ref carries `.position`; `get_component(ref.id)` reaches the live component. So "unresolved" and "no coords" depots do not occur in play; the three copies read the same set. The coords-less drop in `_scan_drone_buildings` is a defensive filter, acceptable for the fleet coordinators.
  - Apart: `logistics_requests.local_depots` needs the resolved `DroneStation` components of one outpost (hauler planning reads their ports); `commission_card.read_outposts` wants "has a depot" from one unfiltered `buildings()` call per outpost (membership test; three memoized type walks would cost more).
  - Risk: medium for `fleet_upgrade._advance_depot` (:312 runs right after a depot deploy; the 20-tick memo can still list the old depot: read `drone_depots.DISCOVERY_TTL_TICKS` and the swap flow before merging). Size: S.

## Network-wide machine walks (one or more types)
- Sites:
  - `ap/outpost_needs.py:663 _machines` (components, drops None)
  - `ap/building_plan.py:385 read_machines` (rows (machine_id, outpost_id, tier))
  - `ap/focus_plan.py:215 read_generators` (tiers per PILLARS type; `{}` on any error)
  - Same prologue (`network = ...; try: list(network.outposts() or [])`): `ap/outpost_needs.py:641 read_outposts`, `ap/extractor_plan.py:119 smelter_outposts`.
- Rule: every building of the type(s) across `outpost_network`.
- Differences: `outpost_needs._machines` drops a building whose `get_component` is None; `discover_network_buildings(resolve=True)` falls back to the raw BuildingRef, so swapping in the helper changes what the caller gets. `focus_plan.read_generators` needs all-or-nothing; the helper tolerates per-outpost errors.
- Found by: C
- Verdict: **keep** the walks; the DRIFT is a contract difference, not a bug.
  - `fluid_routing.discover_network_buildings` returns POI extractors first and `(resolved_or_ref, outpost_id)` pairs; none of the three wants that, and importing `fluid_routing` (~800 lines, imports archive/components/game_clock/...) into the planner chain risks the import-step cap. `read_generators` must fail whole (a partial count names the wrong pillar, :228); `read_machines` needs rows per outpost; `_machines` needs components.
  - Merge only the prologue: the five sites listed read `outpost_network.outposts()` through `components.outposts()` (see "Network outposts list guard").
  - Apart pairs for the ignore file: `autoplay/lib/building_plan.py::read_machines ~ autoplay/lib/focus_plan.py::read_generators` (tolerant rows vs all-or-nothing tiers), `autoplay/lib/outpost_needs.py::_machines ~ autoplay/lib/focus_plan.py::read_generators`.
  - Risk: n/a. Size: n/a.

## Survey spiral progress reads (SURVEY_SPIRAL_KEY)
- Sites:
  - `L/job_survey.py:116 SurveyJob._spiral_mission` (`archive.get(K, {}) or {}`, then `.get("next_index", 0)`, no isinstance)
  - `L/job_survey.py:179 SurveyJob._spiral_pass` SURVEY_COMPLETE telemetry (same, `.get("next_index", start_index)`)
  - `L/archive_cleaner.py:529-534 clean_survey_spiral` (validates: `if not isinstance(spiral_data, dict)`)
  - Writer: `L/vehicle_survey.py:365 update_progress` (`dict(current or {})`: a stored list raises too)
  - Constant defined twice: `L/vehicle_survey.py:23` and `L/archive_cleaner.py:31` (`job_survey` imports it from vehicle_survey)
- Rule: read the spiral progress dict, use `next_index`.
- Differences: job_survey calls `.get` on the raw value; a stored truthy non-dict (a list) raises `AttributeError` instead of falling back, while `archive_cleaner:534` treats it as invalid.
- Found by: B
- Verdict: **drift-bug** (low impact) and **merge**.
  - Right copy: `archive_cleaner` (a non-dict is malformed data, reset to `{"waypoints": [], "next_index": 0}`). Only our own writer touches the key and it always writes a dict, so the crash needs a hand-edited notebook; still, two readers and the writer must not raise where the cleaner repairs.
  - Owner `L/vehicle_survey.py`: `spiral_next_index(default=0) -> int` (`archive.get_dict(SURVEY_SPIRAL_KEY).get("next_index", default)`, see "Archive dict read"); `update_progress` starts from `archive.get_dict`-shaped input (`current if isinstance(current, dict) else {}`). Both job_survey sites call the helper.
  - Constant: one definition (CODE_GUIDES "One definition per constant"): archive_cleaner imports `SURVEY_SPIRAL_KEY` from vehicle_survey (no cycle: vehicle_survey's chain never reaches archive_cleaner), or both import it from a leaf.
  - Risk: low. Size: S.
- Landed: Phase 1 (helpers-impl-1), `fix(survey): read spiral progress as a dict` (`LEGACY_PIONEER_SPIRAL_KEY` moved to vehicle_survey too).

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
- Rule: read a game component by name; a missing component or raised call logs `swallowed` and returns a per-site fallback.
- Differences: "is powered" reads disagree on an unreadable power state: `biomass_mixer_gate._is_powered` and `station_controller.is_station_powered` fail open (True); `script_parking._is_powered`, `_can_power_off`, `_is_running` fail closed (False). Fallback value otherwise per site.
- Found by: A
- Verdict: **keep** (one **merge** inside).
  - Not drift: the fail-open readers gate an action that must not fire on an unreadable read (the mixer gate parks a mixer only when it knows it is unpowered; a station serves drones unless it knows it is dark); the fail-closed readers in `script_parking` keep a parked entry until a re-check, per their docstring (:899). Each default is the safe side of its own action. The rest are one-off reads with their own fallback; a generic `read(component_id, method, default)` would hide the typed accessors `components.py` exists for.
  - Merge: `building_swap_upgrade._credits` -> `cash.balance()` (same int/0 contract; the module imports cash already). The `get_grid` pair stays (two controllers, no shared base, no `power` import in steam_turbine).
  - Apart pairs: `lib/biomass_mixer_gate.py::MixerGate._is_powered ~ lib/script_parking.py::ScriptParking._is_powered`, `lib/station_controller.py::StationController.is_station_powered ~ lib/script_parking.py::ScriptParking._is_powered` (fail open vs fail closed), `lib/oil_generator.py::OilGeneratorController.get_grid ~ lib/steam_turbine.py::SteamTurbineController.get_grid` (two controllers, no shared base), `lib/cash.py::balance ~ lib/components.py::machine_tier`, `lib/game_phase.py::read_tp ~ lib/weather_signals.py::WeatherController.now_gh`, `lib/drone_depot.py::DroneDepotController._is_life_form ~ lib/essence_liquifier.py::EssenceLiquifierController.sample_biome` (bool vs biome id).
  - Risk: low. Size: S (one site).

## Depth-6 BFS over the recipe graph
- Sites:
  - `L/production_cascade.py:149 _cascade_fabricator_output_demand` (shortfall-only; `supply` callback; seeds exempt; skips unsourced inputs; only `fabricator_outputs`; `ladder_max` into `targets`)
  - `L/production_cascade.py:370 _cascade_blueprint_demand` memoizes `:379 _walk_blueprint_demand` (shortfall-only; no supply; walks Fabricator and Smelter inputs; gross into `total_needed`)
  - `L/production_cascade.py:249 compute_recipe_depths` (depth relaxation, no shortfall, `fabricator_outputs` only)
  - `L/fleet_intent.py:110 _path_to` (bound `ROOT_WALK_DEPTH`=6 at :30; `seen` set + parent map; returns one path)
  - Not a walker: `L/production_demand.py:111 get_smelter_demands` (one hop at :170-174, `_ceil`). Shared accessor `L/production_cascade.py:140 _recipe_inputs_for`; bound `CASCADE_MAX_DEPTH`=6 at :33.
- Rule: walk `_recipe_inputs_for(item)` level by level to depth 6; parent shortfall x ratio is the child demand; at the cap, log and stop.
- Differences: float carry (`missing * ratio`) in the cascade walkers vs `_ceil` in `get_smelter_demands`. `CASCADE_MAX_DEPTH` and `ROOT_WALK_DEPTH` are separate constants, both 6. Cascade walkers have no visited set; `_path_to` uses `seen`. `get_manual_order_blocking_items` (code_quality.md:156-158) no longer exists.
- Found by: D
- Verdict: **keep** the walkers; **merge** the constant.
  - Not drift: `get_smelter_demands` is the end consumer of its figure (whole units a Smelter refines; rounding up per parent errs on the side of one spare ingot, Gross-then-net-once in its docstring), while the cascades carry exact fractions so several parents sum before the Fabricator rounds at craft time (`ladder_deficits` against integer stock: any positive remainder is one more craft). Rounding the cascade per parent would over-target shared intermediates. The walkers share a scaffold (frontier dict, depth loop, cap log) but differ in seed, stock source, filter, carry and result; a callback walker would take five parameters to express four six-line loops, so a merge saves nothing readable.
  - Merge: `fleet_intent.ROOT_WALK_DEPTH` -> import `CASCADE_MAX_DEPTH` (fleet_intent already imports from `production`, which fronts production_cascade). One definition per constant.
  - Apart pairs: `lib/production_cascade.py::_cascade_fabricator_output_demand ~ lib/production_cascade.py::_walk_blueprint_demand`, `lib/production_cascade.py::compute_recipe_depths ~ lib/fleet_intent.py::_path_to`.
  - Risk: low. Size: S.

## Shop catalogue price read
- Sites:
  - `ap/building_plan.py:602 read_prices` and `ap/focus_plan.py:232 read_prices` ({id: int(cost)}, identical)
  - `ap/outpost_plan.py:581 kit_price` (one id, None)
  - `L/building_swap_upgrade.py:115 BuildingSwapUpgrader._price`, `L/storage_expand.py:78 StorageExpander._price`, `L/harvester_machines.py:84 shop_price` (one id, fallback)
  - `L/pillar_swap.py:189 PillarSwap._prices` ({id: int(cost)})
  - `L/fleet_commission.py:193 FleetCommissionCoordinator._catalogue` ({id: raw cost})
- Rule: `shop.get_catalogue()`, find the entry for an id (or map all), return cost as int, else a fallback.
- Differences: `fleet_commission._catalogue` keeps the raw `cost`, no `int()` (its users sum and compare it, :326-329; harmless). Fallbacks differ.
- Found by: A
- Verdict: **merge**.
  - Owner `L/cash.py` (imports archive, components, game_clock, swallow; every site imports cash already or may): `shop_prices() -> dict[str, int]` (`{entry.id: int(entry.cost)}` over `shop.get_catalogue()`, `{}` when the shop is missing or raises) and `shop_price(item_id, fallback=None) -> int | None` (one entry).
  - Rule: docs/components/shop.md: `get_catalogue()` lists `{id, name, cost}`; tech-gated entries are absent, so "not listed" is the only miss. One `swallowed("cash.shop_prices: shop.get_catalogue")`.
  - Sites merged (8): both `read_prices`, `_prices`, `_catalogue` (gains `int()`), `kit_price` (`shop_price(KIT_ID)`), both `_price`, `harvester_machines.shop_price` (becomes the helper or an alias).
  - Apart: none.
  - Risk: low. Size: M (8 sites, 2 helpers).

## Bio flush then sleep, and run loops
- Sites:
  - `L/bio_processor.py:140 BioProcessorController._idle`, `L/bio.py:412 BioLabController._pause` (flush_all then sleep)
  - `L/bio.py:599 BioLabController.run` (reset, retire, step, flush_all, sleep 0.5)
  - `L/bio.py:761 BioCollectorController.run` (reset, retire, step; no flush, no sleep)
- Rule: flush outgoing signals before every sleep (`tree_console` docstring).
- Differences: the collector loop neither flushes nor sleeps at the loop level.
- Found by: A
- Verdict: **keep**; not drift.
  - `BioCollectorController.step` (:629) idles with `flush_all(); sleep(2.0)` at :704-705 and its harvest branch drives the machine for a trip, so the loop body already sleeps on every path. `_idle` and `_pause` are two-line glue; a `tree_console.sleep_flushed(sec)` would save nothing.
  - Apart pairs: `lib/bio.py::BioLabController.run ~ lib/bio.py::BioCollectorController.run` (step sleeps inside), `lib/bio_processor.py::BioProcessorController._idle ~ lib/bio.py::BioLabController._pause`.
  - Risk: n/a. Size: n/a.

## Archive dict read, non-dict to empty (read-and-validate shapes)
- Sites (A, def level; 247 `archive.get(` lines in all: 231 in 90 scripts files, 16 in 8 autoplay files):
  - `L/drone_upgrade.py:118 fleet_upgrade_state`, `L/fleet_decommission.py:65 decommission_state`, `L/pioneer_commission.py:78 commission_state`, `L/cash.py:115 budget`, `L/fleet_status.py:156 get_all`, `L/lead_cask.py:81 roles`, `L/role_demand.py:293 read_claims`, `L/storage.py:283 _retiring_entries`, `L/vent_cycles.py:80 _read_entries`, `L/game_phase.py:288 read_history`, `L/plants_retire.py:33 _telemetry`, `L/biomass_retire.py:76 retire_state`, `L/building_ops.py:185 jobs`, `L/drone_claims.py:254 DroneClaimsMixin.get_biosite_claims`, `L/drone_weather.py:92 aftermath_entries`, `L/early_buyer.py:180 EarlyBuyer.config`, `L/production_demand_record.py:51 _stored`, `L/production_demand_record.py:208 demand_signature.stored`, `L/seed_maker.py:187 SeedMakerController._refresh_tried` (also writes `_tried`), `L/survey_requests.py:171 read_unsupported` (plus `archive.available` guard)
  - try-guarded: `L/machine_activity.py:213 _read_dict`, `L/retired_machines.py:20 retired`, `L/script_parking.py:807 ScriptParking._vehicle_commands.stored`
  - other: `L/pillar_swap.py:76 swap_state` (None default), `L/logistics_snapshot.py:179 TierView._entry` (not archive), `L/plant_terraformer.py:161 _was_running` and `:169 _last_batch_km2` (nested entry keyed by `self.name`), `L/construction_lots.py:43 read_priorities`, `:52 read_hold`, `L/fluid_routing.py:63 get_tank_assignments`, `L/production_orders.py:15 get_manual_orders` (both `archive.has` + seed + get, then filter values), `ap/autoplay_roles.py:337 outpost_roles`, `ap/blueprint_queue.py:271 planned`, `ap/building_plan.py:310 load`
- Sites (B, line level): `L/archive_cleaner.py:386` (isinstance :390), `:722 consolidate recall`, `L/site_plan.py:55`, `L/bio_retire.py:214 step` (redundant `or {}`), `L/drone_depots.py:289`, `L/drone_energy.py:158 default_cruise_throttle` (None check), `L/archive_cleaner.py:529-532`, `L/fleet_claims_common.py:63 read_mission` (legacy key, None then isinstance), `L/production_demand_record.py:60` (0 default), `L/archive_cleaner.py:728` (False flag), `L/wildlife_planner.py:706` (`[]`), `L/pioneer_upgrade.py:68 is_sport_nav_requested`, `L/fleet_claims_common.py:29 is_flagged`, `L/logistics_requests.py:482 :498 :514` (PICKUPS_KEY), `L/vehicle_claims.py:342 :444-446`, `L/storage_take.py:60`.
- Shapes (B regex estimates; 31 multi-line calls unparsed): S1 `get(K, {})` then isinstance ~86; S2 `get(K, {}) or {}` then isinstance ~36; S3 `or {}` then raw `.get`, no isinstance (the spiral DRIFT); S4 `get(K, None)` then None/truthy test ~15; S5 raw value into a cleaner helper ~8; S6 write-side `_reset_if_not_dict` 4 (`archive_cleaner.py:266`, called :626, :655, :814, :891); S7 other defaults ~10.
- Rule: archive key holds a dict; a missing or non-dict reads as `{}` (or None for entry lookups).
- Differences: try-guarded variants also swallow a raised `archive.get`, but `ArchiveClient.get` (`L/archive.py:53`) already returns the default on notebook error and on None. `or {}` before isinstance is redundant. No shared "read dict" helper in lib.
- Found by: A, B
- Verdict: **merge**.
  - Owner `L/archive.py`: `ArchiveClient.get_dict(key) -> dict` (`value = self.get(key, {}); return value if isinstance(value, dict) else {}`). Same contract as `get_entry` (:123) already has for one level.
  - Rule: a dict-valued key reads `{}` when missing, None or not a dict; `get()` already swallows notebook errors, so no outer `try`.
  - Sites merged: the 20 A def-level wrappers keep their names (they document the key and are imported) and become `return archive.get_dict(KEY)`; the three try-guarded ones drop the `try` (see "try around archive.get"); the S1/S2 line-level sites and the three `ap/` wrappers switch as they are touched (`or {}` goes). Related: `is_flagged`, `is_sport_nav_requested`, the three PICKUPS readers, `vehicle_claims` :342/:444-446, `storage_take.py:60`. Two sites are not one-line swaps: `seed_maker._refresh_tried` :187 assigns `self._tried` (becomes `self._tried = archive.get_dict(TRIED_KEY)`), and `logistics_requests.pickups_snapshot` :357 returns `dict(raw)`, a shallow copy its caller may mutate while planning; it keeps the copy (`dict(archive.get_dict(PICKUPS_KEY))`), `get_dict` returns the stored object as `get` does.
  - Apart: `pillar_swap.swap_state` (None means "no swap state", its callers test it); `logistics_snapshot._entry` (an in-memory dict); `plant_terraformer._was_running`/`_last_batch_km2` (nested entry: `archive.get_entry(STATUS_KEY, self.name)` plus isinstance); `construction_lots`, `fluid_routing.get_tank_assignments`, `production_orders.get_manual_orders`, `survey_requests.read_*` (a cleaner validates values; the `archive.has` seed stays). `archive_cleaner` keeps `_reset_if_not_dict` (write side).
  - Risk: low (pure read, same result on every input). Size: L by count (~25 files), mechanical.
- Landed: Phase 1 (helpers-impl-1), `refactor(archive): add get_dict for dict-valued keys` and the three `... use get_dict` batches. `archive_cleaner.clean_claims` keeps its raw reads (its write check compares the raw values). About 140 unlisted `archive.get(K, {})` lines switch as they are touched.

## Archive read, then per-entry filter or normalise
- Sites: `L/production_docks.py:16 dock_order_prios`, `L/supply_dock.py:209 order_overrides` (identical body), `L/logistics_snapshot.py:129 _units_in`, `L/construction_plan.py:74 clean_priorities`, `L/lead_cask.py:262 _live_inbound`, `L/fluid_routing.py:221 _prune_conflicts`, `L/outpost_flow.py:40 read`, `L/production_orders.py:265 order_consumer_sites`, `L/site_supply.py:489 construction_rush`, `ap/outpost_plan.py:519 load`
- Rule: read a dict key, `{}` when not a dict, keep valid entries (numeric, int, fresh, live), normalise each.
- Differences: predicate varies (`clamp(prio)`, `is_fresh`, `_order_live`, `decayed`).
- Found by: A
- Verdict: **keep**, except the identical pair.
  - The predicate is each site's rule; the read half folds into `archive.get_dict` (previous family) and the rest is one comprehension per site.
  - Merge the pair: `supply_dock.order_overrides` -> `production_docks.dock_order_prios` (supply_dock imports neither production_docks nor the reverse today; production_docks is a leaf of production_demand, no cycle).
  - Apart pairs: `lib/lead_cask.py::_live_inbound ~ lib/fluid_routing.py::_prune_conflicts` (TTLs and keys differ), `lib/logistics_snapshot.py::_units_in ~ lib/construction_plan.py::clean_priorities`.
  - Risk: low. Size: S.

## Archive transaction updater coerces non-dict to empty
- Sites:
  - `L/archive.py:133 ArchiveClient.set_entry.updater`, `:176 pop_entry.updater`
  - `ap/autoplay_roles.py:401 prune_roles.updater`; `ap/blueprint_queue.py:50 _record.planned_updater`, `:61 priority_updater`, `:87 cancel.updater`, `:285 prune_planned.updater`
  - `L/construction_lots.py:32 release_finished_claims.updater`, `:146 prune_priorities.updater`; `L/fleet_claims_common.py:40 set_flagged.updater`; `L/production_orders.py:333 set_order.updater`; `L/supply_dock.py:220 set_order_override.updater`
  - `L/biomass_mixer_gate.py:224 MixerGate._record_parked.updater`; `L/turbine_commit.py:296 _heartbeat.updater`, `:308 _record.updater`; `L/outpost_mining.py:170 publish_reach.updater`; `L/seed_maker.py:212 _mark_tried.updater`
  - `L/vehicle_claims.py:347 VehicleClaimsMixin.blacklist_target.updater`; `L/parking_client.py:109 _unpark.unpark`; `L/retired_machines.py:61 release.updater`; `L/script_parking.py:444 ScriptParking._commit.updater`
  - `L/fleet_status.py:145 publish.updater`, `:171 forget.updater` (no coerce); `L/fleet_upgrade.py:312 _advance_depot.drop`, `:480 _migrate_drone_keys.repin`; `L/fleet_decommission.py:318 forget_machine.drop_upgrade`
  - `L/cash.py:261 keep.updater`; `L/building_ops.py:171 mark_retire_ready.updater`, `:255 _patch.updater`
  - `L/pioneer_upgrade.py:91 request_sport_nav.updater`, `:102 clear_sport_nav_request.updater`
  - `L/fabricator.py:713 FabricatorController.publish_wants.updater`, `L/smelter.py:331 SmelterController.publish_want.updater`, `L/fluid_routing.py:242 yield_pipe_conflict.updater`, `L/lead_cask.py:298 set_inbound.updater`
  - `L/archive_cleaner.py:282 _prune_dict_key.updater` (pop many, with an optional re-check)
- Rule: `transaction(KEY, {}, updater)` starts from a dict (non-dict becomes `{}`), then sets or pops keys or fields.
- Differences: shapes are set key, pop key, set many, pop many, patch an entry's fields, stamp nested entries. `fleet_status.forget` skips the coerce (pop on non-dict is a no-op).
- Found by: A
- Verdict: **merge** by shape.
  - Owner `L/archive.py`: `ArchiveClient.mutate(key, fn) -> bool` (coerce to dict, `fn(state)` edits in place, write back) and `ArchiveClient.pop_entries(key, entry_ids) -> bool`; `set_entry`/`pop_entry` exist.
  - Rule: every dict-valued key is written through one of set_entry, pop_entry, pop_entries, mutate or publish_status; no site writes its own coerce.
  - Sites by shape: set one -> `set_entry`: fleet_status.publish :145, vehicle_claims :347, outpost_mining :170, turbine_commit :296; pop one -> `pop_entry`: fleet_status.forget :171; set-or-pop -> `set_flagged`-style, keep as `mutate` or `set_entry`/`pop_entry` branch: fleet_claims_common :40 (stays, it is the helper), production_orders :333, supply_dock :220, biomass_mixer_gate :224, pioneer_upgrade :91/:102 (see "Sport-nav request flag"); pop many -> `pop_entries`: autoplay_roles :401, blueprint_queue :87/:285, construction_lots :32/:146, parking_client :109, retired_machines :61, archive_cleaner :282 (its `still_stale` re-check variant keeps `mutate`); set many or mixed -> `mutate`: blueprint_queue :50/:61, seed_maker :212, script_parking :444, turbine_commit :308, cash :261, building_ops :171/:255, fleet_upgrade :480; nested sections via their module wrapper (next family): fleet_upgrade :312, fleet_decommission :318.
  - Apart: fabricator :713, smelter :331, fluid_routing :242, lead_cask :298 (prune then set, see "Stale-stamp prune then set"); `set_entry`/`pop_entry` themselves.
  - Risk: medium (archive writes on ~30 keys; each swap is mechanical but needs its caller's test or a live check). Size: L.

## Keyed-state mutate wrapper (identical bodies)
- Sites: `L/drone_upgrade.py:124 update_fleet_upgrade` (updater :127), `L/fleet_decommission.py:76 _update` (:77), `L/pillar_swap.py:81 _update` (:82), `L/pioneer_commission.py:83 update_commission` (:86)
- Rule: `archive.transaction(KEY, {}, updater)`, updater coerces to dict then `mutate(state)`.
- Differences: none in bodies; only the archive key.
- Found by: A
- Verdict: **merge** into `ArchiveClient.mutate(key, fn)` (previous family).
  - The four wrappers become `return archive.mutate(KEY, mutate)` (keep the two public names, `update_fleet_upgrade` and `update_commission`, as one-line aliases; the two private `_update` go).
  - Apart: none. Risk: low. Size: S.

## Archive sub-entry lookup and patch
- Sites: lookup `L/drone_upgrade.py:215 drone_swap_entry`, `:220 lineage_entry`, `L/pioneer_commission.py:95 lineage_entry`, `L/fleet_decommission.py:71 decommission_entry`, `L/fleet_status.py:162 get`; patch `L/building_ops.py:252 _patch` (stamps `tick`, `archive.transaction` directly), `L/fleet_decommission.py:189 FleetDecommissionCoordinator._patch`, `L/pillar_swap.py:95 _patch_job`; requested-state `L/building_ops.py:161 retire_requested`, `L/fleet_decommission.py:118 is_decommission_requested`
- Rule: lookup `(state().get(section) or {}).get(id)` returns the entry if a dict else None; patch does `entry.update(fields)` on a dict entry; requested-state tests `entry["state"] == "requested"`.
- Differences: state source and section key vary; `retire_requested` reads `archive.get_entry`, the other `decommission_entry`.
- Found by: A
- Verdict: **merge** the lookups; patches ride on `mutate`.
  - Owner `L/archive.py`: `ArchiveClient.dict_entry(key, *path) -> dict | None` (walk nested dicts; None unless the leaf is a dict). `fleet_status.get` = `dict_entry(FLEET_STATUS_KEY, name)`, `decommission_entry` = `dict_entry(DECOMMISSION_KEY, id)`, `drone_swap_entry` = `dict_entry(FLEET_UPGRADE_KEY, "drones", id)`, both `lineage_entry` = `dict_entry(KEY, "lineage", id)`.
  - Patches: `building_ops._patch`, `fleet_decommission._patch`, `pillar_swap._patch_job` each become a three-line `archive.mutate(KEY, fn)` (building_ops keeps its `tick` stamp inside `fn`). The two requested-state tests stay (two lines each, different keys).
  - Apart pairs: `lib/building_ops.py::retire_requested ~ lib/fleet_decommission.py::is_decommission_requested`.
  - Risk: low. Size: S.

## try around archive.get (double guard)
- Sites: `L/machine_activity.py:213 _read_dict`, `L/retired_machines.py:20 retired`, `L/script_parking.py:807 stored` (try around `get(key, {}) or {}`), `L/construction_lots.py:43 read_priorities`, `:52 read_hold` (try around a cleaner call)
- Rule: `archive.get` already swallows notebook errors (`archive.py:53-62`); the outer try only adds a second `swallowed`. In `construction_lots` the try also covers the cleaner, so not redundant there.
- Found by: B
- Verdict: **merge** into "Archive dict read": the first three become `archive.get_dict(key)`; `construction_lots` keeps its try (it guards `clean_priorities`/`held_kinds`, not the read). Risk: low. Size: S.
- Landed: Phase 1 (helpers-impl-1), `refactor(archive): drop the double guard around dict reads`.

## Survey archive reads (unsupported targets, requests, blocked, biomass)
- Sites:
  - `L/survey_requests.py:171 read_unsupported` (shared; `archive.available` guard)
  - `L/survey_requests.py:48 read_requests`, `:164 read_blocked` (passes raw to `blocked_targets` :121), `:179 read_known_biomass` (`known_biomass` validates :105)
  - Bypassing `read_unsupported`: `L/drone_scout.py:44`, `L/unsupported_markers.py:156`, `:261` (`or {}` then isinstance)
  - `L/vehicle_claims.py:342` (in `blacklist_target` :307, isinstance then `same_block`), `:444-446` (in `get_unsupported_targets` :442, merges two legacy keys); `L/archive_cleaner.py:438-442` (raw into `_merge_unsupported` :500, which validates each with isinstance)
- Rule: `if not archive or not archive.available: return default`; one `archive.get`; one clean helper. Unsupported-targets variant: dict of blacklisted survey targets, `{}` on non-dict.
- Differences: default `{}` vs `(set(), set())` vs `[]`; only `read_unsupported` has the `archive.available` guard (redundant: `get` returns the default without a notebook). The two legacy-key merges differ, see part 2 "Unsupported-target legacy merge".
- Found by: A, B
- Verdict: **merge** (three bypassers) and **keep** the typed readers.
  - Owner `L/survey_requests.py`, existing `read_unsupported() -> dict`. `drone_scout.py:44` imports survey_requests already and switches. `unsupported_markers` cannot import survey_requests (survey_requests imports unsupported_markers), so :156 and :261 use `archive.get_dict(SURVEY_UNSUPPORTED_KEY)` instead. `vehicle_claims` :342 and :444-446 likewise (`get_dict`).
  - Apart: `read_requests`, `read_blocked`, `read_known_biomass` (each a different cleaner and default; already one `archive.get` each).
  - Risk: low. Size: S.
- Landed: Phase 1 (helpers-impl-1), `refactor(archive): line-level dict reads use get_dict` (the three bypassers, `vehicle_claims` :342) and `fix(survey): one unsupported-target merge for fleet and cleaner` (:444-446).

## Guarded get_component wrapper copies
- Sites: `L/building_swap_upgrade.py:55 component` (adds a `where` label), `L/components.py:108 _component` (exported as `component` at :114-119)
- Rule: `get_component(id)` wrapped so a raised lookup logs `swallowed` and returns None.
- Differences: building_swap takes a label; `components.component` is the documented home. Generic `get_component` call sites (hundreds) not enumerated.
- Found by: A, B
- Verdict: **merge**.
  - Owner `L/components.py`: `component(component_id, where="components.component")` (the label becomes an optional parameter; the TYPE_CHECKING alias at :116 keeps the typed signature). `building_swap_upgrade.component` goes; its 5 callers pass their label.
  - Apart: none. Risk: low. Size: S.

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
- Differences: default and pre-check vary; `harvesting.detect_base_sector` hard-codes "E13" (its `get_position` falls back to the value this one found).
- Found by: A
- Verdict: **keep** as named readers; the shape itself gets one helper (next family).
  - CODE_GUIDES "Errors" wants every recovering except to name its site; a named reader per read is that rule. Where a site wants to drop the four-line body, `swallow.safe_call(where, read, default)` from the next family is the form (`safe_call("x.read_heat: reactor.heat", self.reactor.heat, 0.0)`), not a per-module `_call`.
  - Apart pairs (the ones a 0.85 scan pairs): `lib/drone_cargo.py::DroneCargoMixin.cargo_capacity ~ lib/drone_cargo.py::DroneCargoMixin.cargo_full`, `lib/drone_navigation.py::DroneNavigationMixin.current_station ~ lib/drone_navigation.py::DroneNavigationMixin.current_drill`, `lib/harvesting.py::HarvesterController.get_position ~ lib/harvesting.py::HarvesterController.get_heat`, `lib/seed_maker.py::SeedMakerController._read_life_forms ~ lib/seed_maker.py::SeedMakerController._recipes`, `lib/fluid_routing.py::safe_is_stalled ~ lib/fluid_routing.py::fill_pct_of`, `lib/oil_generator.py::OilGeneratorController.get_grid ~ lib/profiling.py::begin`, `autoplay/lib/fluid_outlook.py::read_hazards.biome_of ~ autoplay/lib/fluid_outlook.py::read_contacts.biome_of` (two closures over different `planet` reads; or hoist one module function, S).
  - Risk: n/a. Size: n/a.

## Guarded getattr-by-name or thunk call helper
- Sites: `L/biomass_mixer.py:147 BiomassMixerController._read`, `L/biomass_mixer_gate.py:162 MixerGate._call`, `L/biomass_retire.py:81 _call`, `L/plants_retire.py:43 _call` (getattr by name); `ap/building_plan.py:593 _safe`, `ap/outpost_needs.py:632 _call` (thunk, Pyright-typed); `au/builder_automation.py:88 run_step` (thunk, `report_error`)
- Rule: call a game read, log on exception, return a fallback; each module re-implements the wrapper.
- Differences: `run_step` logs via `report_error`; the rest via `swallowed` with a label.
- Found by: A
- Verdict: **merge**.
  - Owner `L/swallow.py` (imports nothing; every module imports it): `safe_call(where: str, read: Callable[[], T], default: T) -> T`, the `outpost_needs._call` form (typed thunk, docstring says why not a method name).
  - Rule: `read()` or `default` after `swallowed(where, error)`. Callers pass the bound method as the thunk (`safe_call("biomass_mixer.fill", self.mixer.fill, 0.0)`), so the getattr-by-name copies lose nothing and Pyright sees the call.
  - Sites merged (6 defs, ~30 call sites): the four getattr `_call`/`_read`, `building_plan._safe`, `outpost_needs._call`.
  - Apart: `builder_automation.run_step` (reports to the AUTOMATION card, not the log).
  - Risk: low. Size: M.

## Sensor value read
- Sites: `L/biomass_retire.py:61 biomass_tons` (0.0), `L/plant_terraformer_common.py:45 plants_km2` (None), `L/wildlife_planner.py:957 _population` (None)
- Rule: `get_component(sensor).get_value()`, guarded, with fallback.
- Differences: fallback 0.0 vs None.
- Found by: A
- Verdict: **merge**.
  - Owner `L/components.py`: `sensor_value(sensor_id, where) -> float | None` (None without a sensor or on a raised read). `biomass_tons` = `sensor_value("biomass_sensor", ...) or 0.0`; the other two return it as is.
  - Apart: none. Risk: low. Size: S.

## Network outposts list guard
- Sites: `L/drone_kit_stock.py:24 _outposts`, `L/lead_cask.py:70 _all_outposts`, `L/site_supply.py:174 _outposts`, `L/building_swap_upgrade.py:89 BuildingSwapUpgrader._outposts`, `L/pillar_swap.py:160 PillarSwap._outposts`, `L/storage_expand.py:61 StorageExpander._outposts`, `L/drone_haul_plan.py:138 outposts_by_id` (dict), `L/fleet_upgrade.py:133 FleetUpgradeCoordinator._drones` (fleet as id dict), `L/production_core.py:131 _all_outposts` (falls back to `[home]`), `L/production_source.py:153 SourceCache.outposts` (memo of the former); the prologues of `L/fleet_upgrade.py:106`, `L/fleet_decommission.py:146`, `L/commission_card.py:47`, `L/charging.py:27`, `L/charging_stations.py:43`, `L/wildlife_planner.py:578`, `L/weather_signals.py:97` (unguarded), `L/drone_depots.py:150`, `ap/outpost_needs.py:641 :663`, `ap/building_plan.py:385`, `ap/focus_plan.py:215`, `ap/extractor_plan.py:119`, `ap/blueprint_queue.py:25`
- Rule: `get_component("outpost_network").outposts()` (or fleet) in a guard; list or id dict, `[]`/`{}` on miss.
- Differences: some check `hasattr(network, "outposts")`; `storage_expand` and `pillar_swap` use `component()`; two return dicts; production_core falls back to home.
- Found by: A
- Verdict: **merge**.
  - Owner `L/components.py`, next to `home_outpost()`: `outposts() -> list[OutpostRef]` (`[]` when the network is missing or raises; `swallowed("components.outposts: network.outposts")`).
  - Rule: one place reads the outpost list. The six `_outposts`/`_all_outposts` copies go (callers call `components.outposts()`); `outposts_by_id` = `{o.id: o for o in outposts()}`; `production_core._all_outposts` keeps its home fallback as `outposts() or ([home] if home else [])`; the prologue sites replace their own guard with the call (the walks stay, see their families).
  - Apart: `fleet_upgrade._drones` (fleet, not network; one site). `weather_signals.discover_stations` has no guard at all today (a raise escapes to its caller); the helper gives it one.
  - Risk: low. Size: M (~20 sites, one-line swaps).
- Landed: Phase 1 (helpers-impl-1), `refactor(components): one outposts() read` and `refactor(autoplay): outpost prologues use components.outposts`. `site_evict` dropped its lazy `site_supply._outposts` import. `weather_signals.discover_stations` stays apart: its caller `refresh_stations` catches the raise and keeps the last station list, which `[]` would replace with a false "no station in any biome" warning. Not in the site list and still open: `storage_sweeps._all_outposts`, `role_demand._network_outposts`.

## Outpost-by-id lookup
- Sites: `L/outpost_mining.py:74 outpost_by_id` (via `_outpost_network()`), `L/production_sites.py:139 outpost_by_site_id` (via `_all_outposts()`), `ap/blueprint_queue.py:25 _construction_outpost` (matches `construction_site_id()`), `L/building_ops.py:283 _ids_at` (home via `network.home()` else `outpost_by_id`), `L/pillar_swap.py:168 _ids_at` (inline scan)
- Rule: scan outposts for the matching id; return ref or None.
- Found by: A
- Verdict: **merge**.
  - Owner `L/components.py`: `outpost_by_id(outpost_id) -> OutpostRef | None` (scan `outposts()`). `outpost_mining.outpost_by_id` becomes a one-line alias (many importers), `outpost_by_site_id` and `_construction_outpost` (`outpost_by_id(construction_site_id())`) call it; `pillar_swap._ids_at` uses it before `building_ids_at` (see "Per-outpost building ids").
  - Apart: none. Risk: low. Size: S.

## Components of one type at one outpost (resolve, drop None)
- Sites:
  - `L/lead_cask.py:124 _components_at` (`[]` for None outpost), `L/fuel_assembler.py:146 FuelAssemblerController._buildings`; same body
  - `L/bio_orders.py:28 local_sibling` (first resolved only, debug block)
  - `L/drone_depot.py:139 DroneDepotController._find_local_liquifier` (exactly one or None, warns on several)
  - `L/storage.py:716 _items_demanded_by_active_dock_orders` (supply docks, then `current_order`)
- Rule: `outpost.buildings(type_id)` then `get_component(ref.id)`, keep non-None.
- Differences: lead_cask and fuel_assembler agree. The memoized `production_core.discover_building_ids` is 20 ticks (~2 s) stale and `production_core -> outpost_mining -> storage` makes it unreachable from storage.
- Found by: A, C
- Verdict: **merge** the identical pair; the rule-bearing sites call it or stay.
  - Owner `L/components.py`: `components_at(outpost, type_id) -> list` (unmemoized; `[]` for None; the resolved components, None dropped). lead_cask and fuel_assembler swap; `storage._items_demanded_by_active_dock_orders` can use it too (components is a leaf, no cycle).
  - Apart: `bio_orders.local_sibling` (first match, its own debug block) and `drone_depot._find_local_liquifier` (exactly-one rule with a warning) keep their rule; both may call `components_at` for the list, optional.
  - Risk: low. Size: S.

## Per-outpost building ids of one type (no resolve)
- Sites:
  - `L/water_sink.py:53 WaterAwareWasteSinkController._water_duty` (True on failure)
  - `L/steam_condenser.py:227 SteamCondenserController.sink_draining_target` (then resolves and filters)
  - `L/building_swap_upgrade.py:100 BuildingSwapUpgrader._ids_of` (sorted, drops empty ids)
  - `L/pillar_swap.py:168 PillarSwap._ids_at` (sorted), `:177 _machines` (network (outpost_id, id) sorted)
  - `L/building_ops.py:283 _ids_at` (None when unreadable)
  - `L/feed_maker.py:250 FeedMakerController._read_habitat_ids`
- Rule: ids of one type_id at one outpost, sorted by the caller.
- Differences: the swap flows run right after deploys, where `production_core.discover_building_ids`'s 20-tick memo could return the old list.
- Found by: C
- Verdict: **merge** on an unmemoized helper (not on the memo).
  - Owner `L/components.py`: `building_ids_at(outpost, type_id) -> list[str]` (sorted, empty ids dropped, `[]` on a raised walk). The swap sites keep their freshness; `building_ops._ids_at` keeps its None-when-unreadable by testing the outpost first; `pillar_swap._machines` = `sorted((o.id, b) for o in outposts() for b in building_ids_at(o, type_id))`.
  - Apart: `steam_condenser.sink_draining_target` (resolves and filters on live port state); `water_sink._water_duty` may use the helper (True on an empty list stays its rule).
  - Risk: low. Size: M (6 sites).

## Storage stores
- Sites: `L/site_evict.py:176 storage_outposts` (type set at :186: STORAGE_TYPE_IDS and DEPOT_TYPE_TIERS and no PENALIZED_TYPES)
- Rule: outpost holds a storage store (warehouse, large_warehouse, storage_bin).
- Found by: C
- Verdict: **keep**. One unfiltered `buildings()` walk per outpost answers three type questions; `discover_storage_buildings` would answer one of them with a memoized walk and resolve every store. The type set could come from `components.building_type_counts(outpost)` (part 2, "Per-outpost building type counts"). Risk: n/a. Size: n/a.

## Charging stations (CHARGING_STATION_TYPE_ID)
- Sites: `L/charging.py:27 ChargingStationController.all_station_refs` (walk :40-47, then a self fallback at :51-57), `L/charging_stations.py:43 _scan_stations` (memoized `all_stations` at :32; `coords_of` from construction_plan)
- Rule: every charging_station with a position across outposts, dedup by id.
- Differences: `all_stations()` returns {id, coords, outpost, component}; charging.py keeps {id, coords} and reads only coords (call at :62). `coords_of` (construction_plan) and `drone_depots._extract_coords` (:132): same rule (tuple or `.x`/`.y`, floats), the latter also accepts a list.
- Found by: A, C
- Verdict: **merge**.
  - Owner `L/charging_stations.py`, existing `all_stations()`. `all_station_refs` = `[{"id": s["id"], "coords": s["coords"]} for s in all_stations()]` plus its self fallback. No cycle (charging imports station_controller, vehicle_energy; charging_stations imports geometry, components, construction_plan, game_clock). The memo TTL is fine: stations change rarely and the fallback covers the own station.
  - Also: `drone_depots._extract_coords` -> `construction_plan.coords_of` (one coords parser; drone_depots imports nothing from construction_plan yet, no cycle).
  - Apart: none. Risk: low. Size: S.

## Per-outpost site lists (fab and lab sites)
- Sites: `L/site_evict.py:148 fab_sites`, `:153 lab_sites`
- Verdict: **keep** (both already one-liners on `discover_*`). Apart pair: `lib/site_evict.py::fab_sites ~ lib/site_evict.py::lab_sites`.

## Water tanks (LIQUID_TANK_TYPE_IDS)
- Sites: `L/water_sink.py:66 WaterAwareWasteSinkController._water_tanks` (own outpost, `tank_is_eligible_target(tank, WATER_FLUID_ID, assignments)`, then `fill_pct_of`), `L/wildlife_planner.py:661 _tank_refs` (network-wide, skip retiring, dedup; inside `run_atomic`)
- Rule: every liquid tank latched to the fluid and not retiring.
- Found by: C
- Verdict: **merge** one, **keep** one.
  - `water_sink._water_tanks` -> `[(t, fill_pct_of(t)) for t, oid in fluid_routing.discover_network_buildings(LIQUID_TANK_TYPE_IDS, fluid_id=WATER_FLUID_ID) if oid == own_id]` (same eligibility test, same resolve; water_sink imports fluid_routing already). The trace line per tank moves with it.
  - Apart: `wildlife_planner._tank_refs` runs inside `run_atomic` with a caller-supplied outpost list and retiring set; `discover_network_buildings` calls `poi_extractor_ids`, `get_tank_assignments` (archive) and `log.trace`, whose purity inside the runner is unverified.
  - Risk: low. Size: S.

## Network-wide ids and records (non-machine)
- Sites: `L/weather_signals.py:97 discover_stations` ((station_id, biome, powered); no try at all), `L/wildlife_planner.py:578 network_habitats` (sorted ids + home from `is_home`)
- Rule: every building of one type across `outpost_network`.
- Found by: C
- Verdict: **merge** one, **keep** one.
  - `network_habitats` -> `(production_core.discover_building_ids(type_id), components.home_outpost())` (same walk; `home_outpost()` is the Done-table owner of the `is_home` rule; wildlife_planner -> production_core -> outpost_mining -> storage: no cycle back). A 20-tick memo on habitat ids is harmless.
  - Apart: `discover_stations` (needs the snapshot `powered` flag and the outpost biome, which the id helper drops). Give it the `components.outposts()` guard: today `network.outposts()` or `buildings()` raising escapes to its caller.
  - Risk: low. Size: S.

## Supply dock walk (per outpost)
- Sites: `L/storage.py:716 _items_demanded_by_active_dock_orders` (walk :739-747)
- Rule: every supply_dock at an outpost, components with `current_order`.
- Found by: C
- Verdict: **keep** away from `production_core.discover_supply_dock_ids`: `storage -> production_core -> outpost_mining -> storage` is a module-level cycle (checked). It may use `components.components_at(outpost, "supply_dock")` (leaf). Risk: n/a. Size: n/a.

## Tier-0 building walks
- Sites: `s0/atmos/heater.py:39 get_battery_pct` (sums `battery` level/capacity at own outpost), `s0/power/solar.py:83 get_master_solar_id`, `:108 get_building_ids` (home)
- Verdict: **keep**: tier 0 cannot import tier 4; no tier-0 lib exists and three walks do not justify one. Apart pairs: `power/solar.py::get_master_solar_id ~ power/solar.py::get_building_ids` (tier 0, nolib).

## _dist(ax, ay, bx, by) copies
- Sites: `ap/outpost_needs.py:198 _dist`, `ap/outpost_plan.py:96 _dist`, `ap/outpost_sites.py:167 _dist` (21 call sites in the three files), inline `ap/outpost_sites.py:814` and `:851` (comments say "_dist() inlined"), `L/geometry.py:4 distance(a, b)` (tuples), `L/site_evict.py:195 _distance(a, b)` (wraps `geometry.distance`; 0.0 on None). Not copies: `ap/outpost_sites.py:171 _rect_dist`, `ap/grid_geom.py:221` (Manhattan).
- Rule: `sqrt((ax-bx)^2 + (ay-by)^2)` metres, no clamping.
- Differences: arg shape (4 scalars vs 2 tuples); `** 2`/`** 0.5` vs `dx*dx`/`sqrt` (same up to rounding); None handling only in `site_evict._distance`.
- Found by: D
- Verdict: **merge**.
  - Owner `L/geometry.py` (imports nothing, so the planner chain pays nothing): add `dist(ax, ay, bx, by) -> float` beside `distance(a, b)`; the three `_dist` defs go and their 21 call sites import `dist` (no tuple packing in the batched scoring loops). Autoplay imports script libs (`outpost_plan` imports `cash`, `components`, `priority` already).
  - Apart: the two inlined sites (step budget, per their comments); `site_evict._distance` (None rule).
  - Risk: low. Size: S.

## Game clock tick copies
- Sites: `ap/building_plan.py:94 _tick`, `ap/outpost_plan.py:510 _tick`, `ap/planner_loop.py:36 _tick`, `ap/power_survey.py:44 _now_tick`; canonical `L/game_clock.py:36 now_tick(where)`
- Rule: current tick via the clock component; 0 if unreadable; `swallowed` on error.
- Found by: A
- Verdict: **merge**: the four copies import `game_clock.now_tick` (outpost_needs and building_plan import game_clock already). Apart: none. Risk: low. Size: S.

## Stale-stamp prune then set
- Sites: `L/fabricator.py:713 FabricatorController.publish_wants.updater`, `L/smelter.py:331 SmelterController.publish_want.updater`, `L/fluid_routing.py:242 yield_pipe_conflict.updater` (via `_prune_conflicts`), `L/lead_cask.py:298 set_inbound.updater` (via `_live_inbound`); canonical `L/archive.py:141 ArchiveClient.publish_status(key, name, entry, tick, log, stale_ticks)`
- Rule: drop entries older than a TTL, store one entry, in one archive transaction.
- Differences: fabricator and smelter inline `now - (tick or 0) >= STALE` instead of `is_fresh` (same semantics, checked). When the want is empty they pop their own entry instead of storing one.
- Found by: A
- Verdict: **merge** two, **keep** two.
  - fabricator and smelter: `archive.publish_status(WANTS_KEY, self.name, entry, now, self.log, stale_ticks=WANTS_STALE_TICKS)` when there is a want (it prunes stale and non-dict others with `is_fresh` and warns on a rejected write), `archive.pop_entry(WANTS_KEY, self.name)` when not. Both controllers share `RecipeClaimMixin`/`MachineController`, so the branch can live once there.
  - Apart: `fluid_routing` and `lead_cask` (their prune helpers are also readers elsewhere and carry their own TTL; two lines each on top of them).
  - Risk: low. Size: S.

## Sport-nav request flag
- Sites: `L/pioneer_upgrade.py:68 is_sport_nav_requested`, `:88 request_sport_nav` (also `resume_vehicle`), `:101 clear_sport_nav_request`
- Rule: per-vehicle flag in one archive dict. Shared helpers exist: `fleet_claims_common.is_flagged` (:29), `set_flagged` (:37).
- Found by: A
- Verdict: **merge**: the three keep their names and become `is_flagged(SPORT_NAV_REQUEST_KEY, name)`, `set_flagged(..., True)` + `resume_vehicle`, `set_flagged(..., False)` (pioneer_upgrade imports vehicle_claims, which imports fleet_claims_common; import it directly). Apart: none. Risk: low. Size: S.

## Recall flag setter
- Sites: `L/drone_claims.py:44 set_drone_recalled`, `L/vehicle_claims.py:113 set_vehicle_recalled`
- Verdict: **keep**: already glue over `set_flagged`; the key is the difference. Apart pair: `lib/drone_claims.py::set_drone_recalled ~ lib/vehicle_claims.py::set_vehicle_recalled`.

## Ranking
Drift-bugs first, then merges by sites saved over risk; `keep` families are not listed. Part 2 families are marked (2).

1. drift-bug survey spiral readers raise on a non-dict (spiral family) plus the twice-defined `SURVEY_SPIRAL_KEY`; S.
2. drift-bug (2) unsupported-target legacy merge: `vehicle_claims.get_unsupported_targets` and `archive_cleaner._merge_unsupported` disagree on legacy pioneer keys; S.
3. merge `archive.get_dict` (~25 sites, risk low, mechanical; opens the spiral fix and the survey bypassers).
4. merge research unlock helper (12 sites, risk low; swallows a raised lookup at five sites that let it escape today).
5. merge `components.outposts()` (~20 sites, risk low).
6. merge `archive.mutate` / `pop_entries` (~30 updaters, risk medium): do it after 3 and in small batches.
7. merge `swallow.safe_call` (6 defs, ~30 call sites, risk low).
8. merge `cash.shop_prices` / `shop_price` (8 sites, risk low).
9. merge `components.building_ids_at` (6 sites, risk low).
10. merge keyed-state wrappers and sub-entry lookups on `archive.mutate` / `dict_entry` (9 sites, risk low).
11. merge `components.outpost_by_id` (3 sites) and `components_at` (2 sites) and `sensor_value` (3 sites), risk low.
12. merge `geometry.dist` (3 defs, 21 call sites) and `game_clock.now_tick` (4 defs), risk low.
13. merge depot walks on `discover_drone_depots` (2 sites, risk medium: memo lag in the swap flow).
14. merge (2) small families marked merge: `item_tiers.best_tier` (4), pickup ledger totals (3), `parking_client.is_shedded` (4), `priority.ladder_totals` (2), `field_layout.rc_to_sector` (1 + 3 constants), `geometry.ceil_int` (1), `next_sleep` (1), `_category_ladder` (1), `wildlife_complete` (1), lazy fail dicts (2), `_raise_target` (4), cleaner fleet prune (1), building type counts (3); all S, risk low.
15. merge the remaining S singles: `cash.balance` in building_swap_upgrade, `components.component(where)`, charging `all_stations`, `coords_of`, water tanks, `network_habitats`, sport-nav flags, `publish_status` for wants, `CASCADE_MAX_DEPTH`, `dock_order_prios` pair.
16. nit `s0/power/solar.py` `is_tech_unlocked`: drop the id-variant loop (:98-106) and the import-time bind; tier 0, no helper.
