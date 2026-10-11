# Plan: mixin refactor — abilities, jobs, pure functions

Status: **steps 1-6 done** (2026-10-11), steps 5-6 verified headless (see Verification). Steps 7-9 open. Branch `mixin-refactor`.
Companion files: [followups.md](followups.md) (drone and harvester families, role swap), [mission_pool.md](mission_pool.md) (shared mission pool sketch).

## Context

The `*Mixin` classes in `scripts/4_controlpanel/lib/` grew by topic, not by kind of code. `VehicleEnergyMixin`
holds energy formulas, charging-station discovery and a 119-line `recharge_at_station()` that drives.
`PioneerConstructionMixin` (45 methods) holds archive bookkeeping, material stocking, build actions and the
role loop. The vehicle core `{navigation, energy, claims, cargo}` is one dependency cycle. Mission state
(`current_target`, `current_target_key`, `current_target_reserved`, `stockpile_empty_reason`, `failed_jobs`,
`material_waits`, `last_build_progress`, `mining_interrupted_battery`) lives as loose controller attributes with
four writers. Five role loops (rover expedition, stationed mining, survey, pull, construction) each
re-implement the same shape: recall check, charge at base, pick work, drive, act, return, release, unload,
recharge.

## Decision: hybrid layout

- **Abilities** of the vehicle itself (drive, budget energy, find charger and charge, claim, load/unload,
  telemetry/recall) stay controller methods, split into mixins of one ability each with one dependency
  direction. Mixins remain the file-splitting device; the `_host` typing pattern stays
  ([CODE_GUIDES.md#mixins](../../../CODE_GUIDES.md#mixins)).
- **Jobs** become objects: a `Mission` record (target, kind, prio, budget, persistence for resume) and one `Job`
  class per role that owns its data and step logic and calls the vehicle's abilities. One `run_job_loop(job)`
  on the controller replaces the five loops.
- **Pure math and archive I/O** become module functions, the pattern `construction_plan.py`,
  `harvester_pure.py` and the `*_for` helpers in `vehicle_energy.py` already use.

Why not helper objects for the abilities too (`self.nav = Navigator(self)`, `self.energy = EnergyBudget(self)`):
`nav`, `energy`, `claims` and `charging` are abilities of one vehicle and read each other constantly
(`drive_to` needs the battery and the nearest station, `recharge_at_station` needs `drive_to`). Split into
objects, the cycle stays as back-references plus one more hop per call. Where composition pays is the job:
its data and its step logic belong together, and the controller only needs one loop.

Scope of the first pass: vehicle + pioneer (+ rover). Drone and harvester follow with the same recipe
([followups.md](followups.md)).

### Interpreter facts that shape the design

Verified in `docs/guide/programming_language_reference.md` §Writing Classes (1140-1337),
`docs/guide/builtins_and_commands.md` §dataclasses (2741+), `tests/test_game_imports.py` `GAME_MODULES`:

- `dataclasses` is a built-in game module (`@dataclass`, `field(default_factory=)`, `asdict`, `replace`,
  `__post_init__`; `frozen=True`/`slots=True` not supported). `functools` is a module too (`total_ordering`),
  as are `random`, `re`, `enum`, `json`, `heapq`, `traceback`. `__getattr__`, `__init_subclass__`, `@property` +
  setter, `super()` with C3 MRO all work. Dunders and `__getattr__` must be pure (no `sleep`, no world actions).
- Dataclass instances do not cross JSON boundaries (archive, Signal Bus): convert with `asdict()`; records
  stay `dict`/`TypedDict`.
- No module-level import cycles between `lib/` modules; one-line imports; no `with`; no stdlib beyond
  `GAME_MODULES`.
- `_host` is still needed, for **Pyright/VS Code**, not for the game. `language_reference.md:27-37` describes
  the in-game editor's use of annotations and says nothing about a mixin's `self`.
  [DESIGN_HISTORY.md §0 (2026-09-22)](../../DESIGN_HISTORY.md) records the alternatives tried: fake base
  (inheritance cycle at the composition site), Protocol (whole surface + annotation per method). An untested
  cheaper variant exists: a per-method `self: "VehicleController"` annotation with the concrete class. It would
  drop the `self._host.` prefix but costs an annotation on every method and breaks typing of the test
  stand-ins. Not part of this refactor. The job classes need no `_host`: a `Job` holds
  `self.host: "VehicleController"` as a plain attribute, so loops and orchestration leave `_host` land.

## Findings (all three families)

Source: AST line-count scan plus a read-only coupling pass (regex, not AST; close but not exact), 2026-10-11.

### Sizes

| Class | File | Lines | Methods |
|---|---|---|---|
| PioneerConstructionMixin | pioneer_construction.py:39 | 922 | 45 |
| VehicleMiningMixin | vehicle_mining.py:70 | 844 | 25 |
| VehicleEnergyMixin | vehicle_energy.py:250 | 719 | 36 |
| VehicleCargoMixin | vehicle_cargo.py:53 | 685 | 17 |
| VehicleSurveyMixin | vehicle_survey.py:26 | 670 | 19 |
| DroneMiningMixin | drone_mining.py:51 | 600 | 13 |
| PioneerUpgradeMixin | pioneer_upgrade.py:106 | 592 | 26 |
| DroneHaulerMixin | drone_hauler.py:66 | 508 | 20 |
| DroneEnergyMixin | drone_energy.py:287 | 497 | 29 |
| HarvesterPlantingMixin | harvester_planting.py:84 | 477 | 31 |
| VehicleClaimsMixin | vehicle_claims.py:91 | 477 | 17 |

Longest methods: `FieldKeeperController.step` 189, `BioLabController.step` 183, `plan_dock_assignments` 182,
`SmelterController._select_needed_ore` 158, `rebalance_inventory_to_warehouses` 140,
`DroneMiningMixin._biosite_candidates` 139, `VehicleCargoMixin.unload_cargo` 135,
`FabricatorController.choose_recipe` 134, `run_survey_loop` 131, `_drive_leg` 130, `run_pull_loop` 124,
`recharge_at_station` 119.

### `_host`

Runtime `@property` returning `self`, in every mixin, used for typing. `self._host.X` and `self.X` are the
same object. Files mix both styles. Keep it (see above).

### A) Vehicle family

`vehicle.py` composes navigation, energy, claims, cargo, survey, mining, fleet_unit; `rover.py` and
`pioneer.py` (+ construction, upgrade, commission) subclass it.

- Dependency matrix: navigation→{energy, claims, fleet_unit}; energy→{navigation, fleet_unit};
  claims→{navigation, energy, cargo, fleet_unit}; cargo→{navigation, energy, claims, fleet_unit};
  survey→{navigation, energy, claims, fleet_unit}; mining→{navigation, energy, claims, cargo, fleet_unit};
  fleet_unit→none. **Cycle core: {navigation, energy, claims, cargo}.**
- Causes of the cycle: energy→navigation only through `recharge_at_station`/`balance_dock` (driving);
  navigation→claims through `drive_with_recharge` refreshing/releasing claims and `handle_recall_if_active`;
  claims→cargo through `handle_recall_if_active`→`_prepare_decommission`→`unload_cargo`.
- Multi-writer state: `current_target`/`current_target_key` (vehicle.py, claims, survey, mining);
  `current_target_reserved` (vehicle.py, mining, claims:288); `stockpile_empty_reason` (vehicle.py, mining);
  `assigned_slot_coords` (vehicle.py, navigation); `wh_per_progress` (vehicle.py, energy); `cruise_throttle`
  (vehicle.py, construction:646); `role` (vehicle, rover, pioneer); `last_build_progress` (pioneer.py,
  construction).
- Rover overrides `wh_per_meter_at_throttle` and `max_safe_throttle_for_leg` (rover.py:32, 47). Pioneer
  overrides nothing.
- PioneerConstructionMixin clusters: archive/claims I/O 13 methods (54-233, 524-538); planning helpers 11;
  drive-and-act 11 (239-332, 341-385, 662-750, 787-959); return/recharge/idle 4; loop 4 (426-606).
- VehicleEnergyMixin clusters: pure module `*_for` helpers 39-249; thin wrappers 287-342; battery/calibration
  324-370; trip budgeting 387-663; **station discovery 664-820 (module `_STATIONS` TickCache); drive-and-act
  821-967.**
- VehicleCargoMixin clusters: pull planning 198-496 (no driving); drive-and-act `unload_cargo` 60-197,
  `_shop_source`, `_buy_and_take`, `_pull_from_source`, `_take_from_depots`; loop 588-736.
- Tests reach in via stand-in subclasses: `test_construction_claim_race`, `test_construction_trip_throttle`,
  `test_construction_lots`, `test_deep_oil`, `test_fleet_decommission`, `test_item_tiers`,
  `test_home_ore_demand`, `test_mining_job_bound`, `test_mining_need_tier`, `test_stationed_recharge`,
  `test_vehicle_resume_cargo`, `test_autoplay_survey` (unbound `PioneerConstructionMixin.note_finished_power_job`,
  `read_construction_hold`); constants in `test_construction_plan`, `test_construction_trip_throttle`;
  `test_early_buyer` builds `RoverController.__new__`.
- Other lib users of module-level names only (not mixin methods): `charging.py` (`rescue_wh_per_meter_for`),
  `vehicles_card.py`, `fleet_decommission.py`, `survey_requests.py` (`SCAN_RESEARCH_IDS`),
  `commission_card.py`.

### B) Drone family (follow-up)

`drone.py` composes navigation, energy, claims, cargo, scout, mining, hauler, haul_plan, weather, upgrade,
fleet_unit.

- Cycle core {navigation, energy, claims}; energy also calls back into `drone.py` (`resolve_home`). `cargo`
  depends on nothing. hauler→{cargo, claims, energy, haul_plan, navigation, upgrade, weather};
  weather→mining (`_return_and_unload`).
- Multi-writers: `current_target*` (drone.py, claims, mining, weather); `engine` (drone.py, energy:352,
  upgrade:350); `home_depot_pool` (drone.py, energy).
- Recipe: see [followups.md](followups.md).

### C) Harvester family (follow-up)

`field_keeper.py` composes heat, paving, planting, care, machines, amplify over `HarvesterController`
(`harvesting.py`).

- Cycles: planting↔care, planting↔machines; every mixin calls back into the controller hub (`act`, `stage`,
  `stock_count`, `read_cells`).
- Multi-writers: `last_action` (controller, planting, care); `garden`/`reserved`/`layout_mode` (controller,
  planting); `step_machine_map` (controller, machines); `log`/`base_sector` (field_keeper and harvesting
  both init them).
- MRO shadowing: `HarvesterHeatMixin.cool_down`/`move_to` shadow `harvesting.py:127, 164`; the base versions
  are dead for FieldKeeper.
- `FieldKeeperController.step` (189 lines) is the per-tick state machine; candidate for a `FieldPass` object.

## Target layout (vehicle + pioneer)

```
lib/                                      layer  depends on lower layers only
fleet_unit.py        FleetUnitMixin          0    tick, intent, telemetry, recall flag
mission.py           Mission (dataclass)     0    kind, target_key, target, prio, source, budget, tick, reserved_yield; to_record()/from_record() over fleet_claims_common
charging_stations.py (functions)            0    all_stations(), nearest(from_coords), outpost_ref(id), station_at(outpost), home_slot_coords(), station_load(); keeps the TickCache  <- VehicleEnergyMixin 664-820
construction_lots.py (functions)            0    lots, priorities, hold, note_finished_power_job, prune, release_finished_construction_claims, planned_progress_for_job; args (name, tick, claims)
pull_plan.py         (functions)            0    pull deficits, sources, route, chain planning; args (home_id, position, capacity, tick, unviable, energy callbacks)
vehicle_energy.py    VehicleEnergyMixin      1    formulas, get_battery, trip budgets, throttle selection. No driving.
vehicle_claims.py    VehicleClaimsMixin      1    claims, blacklist; sole owner of self.mission: begin_mission(m) / end_mission()
vehicle_navigation.py VehicleNavigationMixin 2    get_position, distance_*, is_at_base, drive_to/_drive_leg, stall recovery, return_to_nearest_station
vehicle_charging.py  VehicleChargingMixin    3    recharge_at_station, balance_dock, drive_with_recharge, return_to_base, recharge_at_nearest
vehicle_cargo.py     VehicleCargoMixin       3    unload_cargo, _take_from_depots, _buy_and_take, _shop_source, _pull_from_source, cargo totals. No planning, no loop.
vehicle_recall.py    VehicleRecallMixin      4    handle_recall_if_active, _prepare_decommission, _strip_and_sell_parts
vehicle_survey.py    VehicleSurveyMixin      4    scan_and_survey, survey_known_pois, unscanned_pois, spiral points, save_survey_waypoint. No loop.
vehicle_mining.py    VehicleMiningMixin      4    mine_until_full_or_exhausted, candidate builders, select_best_mining_target, cargo_matches_target. No loop.
pioneer_construction.py PioneerConstructionMixin 4 execute_construction/_execute_construction, calibration hook, construction_claim_key, get_construction_progress
pioneer_stock.py     ConstructionStockMixin  4    load_construction_materials, _top_up_materials, _stock_materials, _free_cargo_space, _cargo_space_for, material_wait_reason, fair_share_batch, cargo_count(s)
vehicle.py           VehicleController            composes abilities; __init__; run_job_loop(job); next_job(job) hook
job_base.py          Job                          host-bound object: step() = prepare() -> pick() -> execute(mission); on_error(), on_leave(), idle_delay
job_build.py         BuildJob                     construction_pass and its helpers; state failed_jobs, material_waits, base_cruise_throttle
job_survey.py        SurveyJob                    run_survey_loop body (known POIs, spiral fallback)
job_mine.py          MineJob                      rover expedition + stationed mining; targets strategy: RoverTargets / OutpostStockpile(outpost_id)
job_pull.py          PullJob                      run_pull_loop body, delivery; state _pull_unviable
rover.py             RoverController              energy overrides + run() = run_job_loop(MineJob(self, RoverTargets()))
pioneer.py           PioneerController            detect_role, run() dispatches to run_job_loop(BuildJob/SurveyJob/MineJob/PullJob)
```

### Rules the layout enforces (go into CODE_GUIDES §Mixins in step 9)

- A mixin is one ability; it calls only lower layers. No role loop inside a mixin.
- A `Job` owns per-role state and the step logic; it never stores state on the host. Jobs import pure modules
  and type the host under `TYPE_CHECKING`; `vehicle.py`/`pioneer.py`/`rover.py` import the job modules.
- Mission state has one writer (`VehicleClaimsMixin.begin_mission/end_mission`); readers use `self.mission`.
  `current_target`, `current_target_key`, `current_target_reserved` become read-only `@property` shims on
  `VehicleController` over `self.mission` (`fleet_unit.publish_telemetry` and the fleet cards read them; a
  write raises, which flushes out any writer missed).
- Pure math and archive I/O are module functions with explicit arguments.

### The loop and the job contract

```python
def run_job_loop(self, job):              # vehicle.py
    validate_game_version(); job.announce()
    while True:
        reset_all()
        try:
            if self.handle_recall_if_active(): delay = job.recall_delay
            else: delay = job.step()
        except Exception as e:
            log error; brake (swallowed); job.on_error()   # releases claim/lot/pickups, mission
            delay = 5.0
        job = self.next_job(job)             # hook, default returns job (role swap later)
        if delay: flush_all(); sleep(delay)
```

`Job.step()` default: `prepare()` (at base: top off >= 0.95 unless no charger, `handle_upgrade_cycle_if_idle`
if present, cargo-aboard handling via `cargo_matches_target`/`cargo_full_for_resume`), then `pick()` → `Mission`
or None (idle: `return_to_base`, telemetry, `idle_delay`), then `execute(mission)` → delay. `BuildJob.step()`
overrides `step()` wholesale: it is today's `construction_pass`.

`Mission` (dataclass): `kind: str`, `target_key: str`, `target: dict`, `prio: int = 0`, `source: str = ""`
(`"blueprint"`, `"request"`, `"stockpile"`, `"poi"`, later `"pool"`), `budget: dict | None = None`,
`tick: int = 0`, `reserved_yield: bool = False`. `to_record()` → the dict `fleet_claims_common.save_mission`
stores today (`target_key`, `kind`, `target`, `tick`); `from_record(record)`; `coords` property.
`begin_mission(m)` = claim_target + optional yield reservation + save_mission + `self.mission = m`;
`end_mission()` = release claim(s) + release_yield + clear_mission + `self.mission = None` (today's
`release_target_claim` tail, vehicle_claims.py:285-291). The survey spiral's temporary `current_target_key`
(vehicle_survey.py:663-668) becomes a `Mission(kind="poi", ...)` passed to `scan_and_survey(mission)`.

`Job.pick()` is the only place a job obtains work. Switching a role to a shared mission pool
([mission_pool.md](mission_pool.md)) is a change inside `pick()`.

## Steps (each leaves `unittest` + pyright green; one commit each)

1. [x] Record findings and TODO (this file, followups.md, mission_pool.md, TODO.md entry).
2. [x] **Charging out of energy.** New `charging_stations.py` (functions + the `_STATIONS` TickCache from
   vehicle_energy.py:67, 664-820) and `vehicle_charging.py` (`VehicleChargingMixin`: `recharge_at_station`,
   `balance_dock` from 821-967; `drive_with_recharge` from vehicle_navigation.py:217-329; `recharge_at_nearest`
   from pioneer_construction.py:514-522). `VehicleEnergyMixin` keeps one-line wrappers
   (`get_nearest_charging_station`, `find_charging_station`, `get_outpost_ref`, `get_home_slot_coords`,
   `get_all_charging_stations`, `current_station`) so rover.py:64 and ~40 call sites keep working. Compose in
   `vehicle.py`. Update `docs/cheatsheet/vehicles_drones.md` §2a header.
3. [x] **Recall out of claims.** New `vehicle_recall.py` with `handle_recall_if_active`, `_prepare_decommission`,
   `_strip_and_sell_parts` (vehicle_claims.py:122-225). Update the `tests/test_fleet_decommission.py:127`
   stand-in.
4. [x] **Mission object.** New `mission.py`. `VehicleClaimsMixin.begin_mission/end_mission`;
   `release_target_claim(target_key=None)` keeps its signature and calls `end_mission()` when it releases the
   current one. `FleetUnitMixin.load_mission` returns `Mission.from_record` and sets `host.mission` through
   claims (drone side keeps the dict path until its own pass). Read-only property shims on `VehicleController`.
   Migrate writers: vehicle.py:97-104, 111-117; vehicle_survey.py (663-668 and the claim path in
   `survey_known_pois`); vehicle_mining.py (`select_best_mining_target`, `_stationed_mining_cycle`,
   `restore_yield_reservation_flag`); vehicle_claims.py:285-291. Tests that set `current_target*` on stand-ins
   now set `mission`.
5. [x] **Job base and BuildJob.** `job_base.py`, `VehicleController.run_job_loop`. `construction_lots.py`
   takes the 13 archive methods as functions; `pioneer_stock.py` the stocking methods; `job_build.py`
   `construction_pass` and its private helpers (pioneer_construction.py:426-786 minus stocking) with
   `failed_jobs`/`material_waits`/`base_cruise_throttle` as job fields. `PioneerConstructionMixin` keeps
   `execute_construction`, `_execute_construction`, `construction_claim_key`, `get_construction_progress`,
   `TARGET_CONSTRUCTION_PROGRESS_PER_TRIP`. `pioneer.py` "constructor" → `run_job_loop(BuildJob(self))`.
   Tests: `test_construction_lots`, `test_construction_claim_race`, `test_construction_trip_throttle`,
   `test_autoplay_survey:188-202` move to the functions / `BuildJob`. Cheatsheet §0 row and §2a construction
   entries.
6. [x] **SurveyJob.** `job_survey.py` from `run_survey_loop` (vehicle_survey.py:565-694): `pick()` = known POIs,
   else spiral waypoint, else idle 30 s; `execute()` drives, scans, saves waypoint. `pioneer.py` "scout".
7. [ ] **MineJob.** `job_mine.py` with a `targets` strategy: `RoverTargets` (rover.py:76-139) and
   `OutpostStockpile(outpost_id)` (`build_local_stockpile_candidates`). `prepare()` carries the resume/cargo
   logic duplicated in rover.py:146-195 and vehicle_mining.py:736-793; `execute()` = rover.py:219-273
   generalized (scan for `poi`, mine for `mine`). Remove `run_stationed_mining_loop`/`_stationed_mining_cycle`
   from the mixin and `run_expedition_cycle`/`_run_trip`/`find_best_mission_target` from rover.py.
   Cheatsheet §2b entries.
8. [ ] **PullJob.** `pull_plan.py` functions from vehicle_cargo.py:198-496 (`_pull_unviable` becomes an argument
   owned by the job); `job_pull.py` from 588-736. `pioneer.py` "hauler". `PULL_CHAIN_NOTES_MAX` moves with the
   planning code.
9. [ ] **Docs and guides.** `docs/AI_CHEATSHEET.md` §0 rows; `docs/cheatsheet/vehicles_drones.md` references;
   `CODE_GUIDES.md` §Mixins rules above; `docs/DESIGN_HISTORY.md` entry (abilities as methods, jobs as
   objects); `vehicle.py` header. Set this file's status.

Steps 2-4 are mechanical moves, verified by tests. Steps 5-8 change control flow: verify each in a throwaway
save before the next.

Step 5 leftovers: `construction_lots.py` (layer 0) imports the two claims-key constants from `vehicle_claims.py`
(layer 1); no cycle, move the constants to `fleet_claims_common` in step 9 if cheap. `run_job_loop` runs
`next_job`/`on_leave`/`announce` outside the try; wrap when a job overrides `next_job` with game or archive
calls. `BuildJob` keeps build claims outside `host.mission`.

Step 6 leftovers: `SurveyJob.can_run()` is a precondition hook outside the `Job` contract, called from `pioneer.py`;
make it generic in `Job`/`run_job_loop` once `MineJob` or `PullJob` needs one (the miner's drill check is a
candidate). `pick()` skips `survey_known_pois()` when no candidate pool is non-empty, so idle cycles are cheaper
than on main (more "All known POIs are scanned" lines per game hour, same work).

## Workflow

- Branch `mixin-refactor` in worktree `.claude/worktrees/mixin-refactor`, PR at the end. No sync holds: the
  watcher deploys the main checkout's `scripts/`, not the worktree.
- In the worktree: `../../../.venv/Scripts/python.exe -m unittest discover -s tests`;
  `../../../.venv/Scripts/python.exe devtools/scripts_sync.py resolve-preview`, then `npx pyright`.
- Delegation: steps 2-4 one Sonnet agent each, steps 5-8 one Opus agent each, grep verification Haiku Explore,
  review `cavecrew-reviewer` per step. Every agent reads this file and `CODE_GUIDES.md` §Game interpreter and
  §Mixins first, runs tests and pyright, and reports files touched and leftovers. The coordinating session
  reads each diff, commits, and merges `main` between steps.

## Verification

- After every step: tests, `resolve-preview`, `npx pyright` (composition sites `lib/vehicle.py`,
  `lib/pioneer.py`, `lib/rover.py` clean). `tests/test_game_imports.py`, `test_game_syntax.py`,
  `test_game_builtins.py` cover the interpreter rules.
- Steps 5-8: headless A/B on a sample save (dev_workflow.md §10b), no game needed. From the worktree, with
  `$env:CT_SIMWORKER` pointing at the main checkout's `internals/terraform_decompiled/simworker/deobfuscated.js`:
  `save_scripts.py --save <save> --out <dir>` once with the worktree's scripts and once with
  `--scripts-dir <main checkout>/scripts`, then `run.mjs --save <save> --libs <dir>/lib --scripts <dir>
  --hours 2 --out <out>` for each. Compare `metrics.jsonl` (`errored` 0, same final line) and per-vehicle
  counts in `console.log` (job scans, claims, `Build '`, `Stocking`, `Waiting for`, `exception`). Restart check:
  run 0.15 h, then `run.mjs --save <out>/final_save.json --scripts <dir> ...` and read the vehicle's first
  lines. Step 5 used `internals/sample_saves/20261008_7e5e168/saves/0080_t140387.json.gz` (68 blueprints,
  `pioneer_4` constructor): counts within one cycle of main, identical final metrics, paused outpost job
  re-claimed and finished after the restart. Step 6 used the same save (`pioneer_1..3` scouts, 51/51 POIs
  surveyed, two resume a claimed POI on load): resume, route, blocked-contact and blacklist counts equal,
  identical final metrics, 0 errors. Main save only with the owner's go-ahead.
- At the end: no mixin above ~450 lines, no method above ~100 lines in the touched files.

## Out of scope

Drone and harvester conversion ([followups.md](followups.md)); `ArchiveCleaner` (one-off cleaner, stays as
is); the interpreter-feature audit (TODO.md); `FieldKeeperController.step`, `BioLabController.step`,
`plan_dock_assignments` long methods.
