# Mixin refactor: follow-ups

Part of [README.md](README.md). Findings are from the 2026-10-11 coupling pass; re-check line numbers before
editing.

## Drone family

`drone.py` composes `drone_navigation`, `drone_energy`, `drone_claims`, `drone_cargo`, `drone_scout`,
`drone_mining`, `drone_hauler`, `drone_haul_plan`, `drone_weather`, `drone_upgrade`, `fleet_unit`.

Findings:
- Cycle core {navigation, energy, claims}: navigation→{claims, energy}; energy→{navigation, drone.py
  `resolve_home`}; claims→{cargo, energy, navigation}. `drone_cargo` depended on nothing (step 5 gave it the unload trip).
- Role mixins: scout→{claims, energy, navigation}; mining→{cargo, claims, energy, navigation, upgrade};
  haul_plan→{energy, navigation}; hauler→{cargo, claims, energy, haul_plan, navigation, upgrade, weather};
  weather→{cargo, claims, energy, mining, navigation, upgrade}; upgrade→{cargo, energy, navigation}.
- Multi-writers: `current_target`/`current_target_key` (drone.py, claims, mining, weather); `engine`
  (drone.py, energy:352, upgrade:350); `home_depot_pool` (drone.py, energy:466, 505).
- Private cross-calls: hauler and mining call `drone_energy._pick_free_depot`, `_home_depot_candidates`;
  hauler calls eight `drone_haul_plan` helpers (now public functions).
- Tests: `test_drone_weather.py:32` stand-in on `DroneWeatherMixin` (`_collect_at_site`); module functions
  imported from `drone_upgrade`, `drone_weather`, `drone_haul_plan` (`_plan_haul_job`).

Recipe (same as the vehicle pass):
1. [x] (2026-10-11) `drone_depots.py` functions: depot and service discovery, `_pick_free_depot`, `_home_depot_candidates`,
   home resolution data (`drone_energy` 400-520 region). `drone_energy` keeps formulas, `detect_engine`,
   `get_battery`, trip budgets.
2. [x] (2026-10-11) `drone_charging.py` mixin: `return_to_service_for_charge`, `hold_for_launch_charge`
   (`LAUNCH_MIN_SOC`) from energy; the hauler's nearest-service refuel as public `docked_at_service`,
   `go_to_nearest_service`, `refuel`, `refuel_at_service` (`REFUEL_*`). `fly_to_station` stays in navigation
   (depots and recall use it too). `drone_energy` no longer flies.
3. [x] (2026-10-11) `Mission` shared with vehicles (`mission.py`): `drone_claims.begin_mission/adopt_mission/
   end_mission`, read-only `current_target`/`current_target_key` on `DroneController`; `load_mission` always
   adopts a `Mission`, `FleetUnitMixin.save_mission` removed. `engine`/`plated` written only by `detect_engine`
   (`known=` for a bare replacement chassis); `home_depot`/`home_depot_pool` only by
   `DroneController.resolve_home`. The hauler's `{"kind": "haul", "dest"}` record bypassed `Mission` (no claim
   key) until step 5 folded it in.
4. [x] (2026-10-11) `drone_haul_plan` → module functions taking the `DroneController` first (`plan_haul_job`, `haul_destinations`,
   `route_fuel`, `item_room`, ...); pure `plan_route_for`/`haul_candidate`/`route_fuel_for` use `geometry.distance`. Stall
   cooldowns and once-per-run warnings live in `HaulMemory` (`DroneController.haul_memory`).
5. [x] (2026-10-11) Jobs: `ScoutJob`, `BiositeJob` (mining), `HaulJob`, `AftermathJob` (weather) over `DroneJob`
   (`drone_job.py`: `hold()` while stranded, upgrade request in `prepare()`, `defer()`/`idle()`, charge helpers).
   `run_job_loop`/`next_job`/`stop_moving` moved to `FleetUnitMixin`; `Job.hold()` added to the contract. The
   role mixins keep abilities only (candidates, claims, fly-and-act legs). `weather→mining` is gone:
   `return_and_unload`/`unload_and_leave`/`wait_for_depot_space` and the `DepotFull` backoff live in `drone_cargo`.
   The hauler's delivery is `Mission(kind="haul", target_key="", target={"dest"})`; `load_mission` restores a
   key-less mission without a claim check, `end_mission` releases no claim for it.
   Leftovers: a resumed miner/aftermath mission still skips the charge and cargo checks (as before). The
   hauler's `STRANDED` telemetry replaces `AWAITING_RESCUE`, and the scout now answers upgrade requests too
   (`DroneJob.prepare`). `drone_cargo` now calls navigation, energy, claims, charging and upgrade (drive-and-act
   layer, like `vehicle_cargo`). `BiositeJob._deliver_elsewhere` reads the private `_home_depot_candidates`/
   `_pick_free_depot` wrappers on `drone_energy`. Headless A/B run afterwards (README Verification).

## Harvester family

`field_keeper.py` composes `harvester_heat`, `harvester_paving`, `harvester_planting`, `harvester_care`,
`harvester_machines`, `harvester_amplify` over `HarvesterController` (`harvesting.py`, a `MachineController`).

Findings:
- Cycles: planting↔care (`care_kind_table`, `salt_in_inventory` / `row_scan`), planting↔machines
  (`automated_cells`, `automation_unlocked`, `deployed_automators` / `desired_chunks`, `field_fill`).
- Every mixin calls back into the controller hub: `act`, `stage`, `stock_count`, `read_cells`.
- Multi-writers: `last_action` (controller, planting, care); `garden`, `reserved`, `layout_mode` (controller,
  planting); `step_machine_map` (controller, machines); `log`, `base_sector` (initialised by both
  `field_keeper.py` and `harvesting.py`).
- MRO shadowing: `HarvesterHeatMixin.cool_down` (harvester_heat.py:219) and `move_to` (346) shadow
  `harvesting.py:127, 164`. The base versions are unreachable for FieldKeeper; no `super()` reaches them.
- `FieldKeeperController.step` (field_keeper.py:319, 189 lines) is the per-tick state machine.
- Tests: `test_harvester_amplify.py:44` stand-in; `test_harvester_geometry.py` instantiates
  `HarvesterPlantingMixin()` directly; `test_harvester_amplify.py:206` builds `FieldKeeperController.__new__`.

Recipe:
1. [x] (2026-10-11) Deleted the base `cool_down`/`move_to` from `harvesting.py`; `HarvesterHeatMixin` is the only
   implementation (base keeps `TYPE_CHECKING` declarations for its own callers; FieldKeeper is the sole subclass).
   Leftover: base `step`, `find_best_target`, `find_path` and the sector-targeting loop are dead for FieldKeeper.
2. [x] (2026-10-11) `harvester_pure.py` gained `care_kind_table`, `salt_usable`, `combine_scans` (memo-free core of
   `row_scan`) and `desired_chunks`. `row_scan` no longer calls `care` (`care_kind_table`, `salt_in_inventory`), so
   planting→care is gone. The thin methods stay (`care_kind_table` memo in care; `desired_chunks` gathers archive
   inputs in planting), so machines→planting (`field_fill`, `desired_chunks`) remains until step 4.
3. [x] (2026-10-11) `harvester_pass.py`: `FieldPass` (cells/statuses/planted view, rules, layout, active, `mine`,
   `spare_items`, a handle to the hub's stock memo, `machine_map`, plan-note phases, the chosen `Choice`,
   `last_action`) and `Choice(kind, target, detail)`. `step()` = `prepare_pass()` → `choose()` (no world actions;
   build-phase, care-batch and harvest-pause bookkeeping plus the decision line) → `run_choice()`. The old
   `step_statuses`/`step_view`/`step_mine`/`step_machine_map`/`step_start`/`step_mark`/`step_phases` are gone.
   Writers now: `last_action` only `FieldKeeperController.note_action()` (abilities report, controller property
   reads `field_pass.last_action`, a new pass carries it over); `layout_mode`/`reserved`/`garden` only planting
   `set_layout_state()` (+ `init_planting()`), read-only properties on the planting mixin; `machine_map` only
   machines `step_machines()`/`forget_machines()`; `log` only `HarvesterController.__init__` (`LOG_MODULE`);
   `base_sector` initialised there, refreshed per pass in `prepare_pass()`. `amplify_step` split into
   `amplify_due`/`amplify_apply`. Leftovers: a failed `pave_step()` re-chooses the tail inside `run_choice()`
   (pave acts before it knows it has work); `inventory_full_tick` still written by controller and planting
   (`harvest_here`); `work_on_pass` reads controller `_rules`; FieldPass fields are written by the controller,
   not the pass itself (no `host` back-reference).
4. [x] (2026-10-11) Mixins are abilities over a shared hub. Layer order (each calls only lower layers):
   0 `HarvesterController` (`harvesting.py`: grid, position/heat/`read_cells()`, held slot,
   `collect_at_current()`) → 1 `HarvesterHeatMixin` (heat model, rests, routes, `nearest()` from the
   controller, `move_to()`) → 2 `HarvesterHubMixin` (`act`, `stage`, `stock_count`, `note_action`/`last_action`,
   layout state `set_layout_state()`/`layout_mode`/`reserved`/`garden`/`kept_garden()`, machine reads
   `deployable_kits`/`automation_unlocked`/`step_machines`/`forget_machines`/`deployed_automators`/`automated_cells`,
   cell views `cell_statuses`/`planted_cells`/`planted_rows`; module functions `load_rules`, `field_fill`,
   `stored_chunk_count`, `desired_chunks`, `deployed_machines`, `deployed_machine_ids`) → 3 abilities paving,
   planting, care (now owns `row_scan()`), machines, amplify, with no edge between them → 4
   `FieldKeeperController` (pass + composites `work_on_pass()`, `harvest_current()`, `plant_if_open()`,
   `care_current()`). Pure: `harvester_pure`, `harvester_pass`. planting↔machines and care→planting are gone;
   `harvester_layout(active, work_groups)`/`build_rank(groups)` take the controller's work groups as input.
   Step-3 leftovers closed: `inventory_full_tick` has one setter (`harvest_current()`; `harvest_here()` returns
   the status); `work_on_pass()` moved to the controller and reads `fp.rules`; paving reports `pave_due()`
   before `choose_tail()` picks "pave", and a started pave that fails ends the pass idle (as the old re-choose
   did: the path is still unpaved, so no sweep). Dead base code removed (`step`, `find_best_target`,
   `find_path`, `distance`, `sector_to_rc`, `harvest_at_current`, `online_message`, `last_target`).
   Remaining upward edges, documented in the headers: `move_to()` → the controller's `work_on_pass()` hook;
   `collect_at_current()` → `cool_down()` (heat). Leftovers: `field_keeper.py` is 485 lines (header grew);
   `amplify_step()` survives only for its tests; FieldPass fields are still written by the controller.
   Headless A/B (README Verification) on `save_mtzkzly3_4ww80o.midlate_2026-10-05.json`, 2 h against main:
   the same 155 care treatments in the same order (157 tour lines, 2 amplifier lines, 18 vs 19 idle lines),
   ticks within ±103 with no trend, 0 exceptions, `errored` 0, credits and pillars equal (TP +186). The save is
   full layout with every machine in, so harvest/plant/pave/deploy paths ran only in unit tests. Restart
   check: 0.15 h, reload, 0.15 h: no layout rebuild, care tour resumes, 0 errors.

## Role swap on demand (vehicle + pioneer, enabled by the job loop)

`run_job_loop(job)` calls `self.next_job(job)` once per pass (default returns `job`). A later change can
return another `Job` after `job.on_leave()` released its claims, lot or pickups: a `detect_role()` re-check
when modules change, an operator switch on the FLEET card, or a mission pool entry of another kind
([mission_pool.md](mission_pool.md)). Not implemented in the first pass.

## Interpreter-feature audit

Tracked in TODO.md ("Interpreter-feature audit"). We wrote roundabout code assuming a thinner interpreter
than the game has (`@dataclass`, `functools`, `__getattr__`, property setters, `__init_subclass__`, `match`
are all available; see README.md "Interpreter facts").
