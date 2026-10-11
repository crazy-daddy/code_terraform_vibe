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
   `_pick_free_depot` wrappers on `drone_energy`. Headless A/B not run yet (README Verification); verify in a
   throwaway save before the harvester pass.

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
2. `harvester_pure.py` already holds pure geometry; move the remaining pure planting/care tables there
   (`care_kind_table`, memo-free parts of `row_scan`, `desired_chunks`).
3. A `FieldPass` object for one `step()`: holds the pass's read cells, stock snapshot, chosen action and
   `last_action`; `step()` becomes prepare → choose → act. `garden`/`reserved`/`layout_mode` get one writer
   (planting) with read-only shims on the controller.
4. Mixins become abilities (heat model, paving, plant/harvest action, care action, machine deploy, amplify)
   with the controller hub (`act`, `stage`, `stock_count`, `read_cells`) moved into a layer-0 mixin they may
   call.

## Role swap on demand (vehicle + pioneer, enabled by the job loop)

`run_job_loop(job)` calls `self.next_job(job)` once per pass (default returns `job`). A later change can
return another `Job` after `job.on_leave()` released its claims, lot or pickups: a `detect_role()` re-check
when modules change, an operator switch on the FLEET card, or a mission pool entry of another kind
([mission_pool.md](mission_pool.md)). Not implemented in the first pass.

## Interpreter-feature audit

Tracked in TODO.md ("Interpreter-feature audit"). We wrote roundabout code assuming a thinner interpreter
than the game has (`@dataclass`, `functools`, `__getattr__`, property setters, `__init_subclass__`, `match`
are all available; see README.md "Interpreter facts").
