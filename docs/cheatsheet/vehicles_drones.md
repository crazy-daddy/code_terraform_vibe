# Surface Vehicles (§2, §2a, §2b, §2e, §2f, §2g)

Part of [`AI_CHEATSHEET.md`](../AI_CHEATSHEET.md). Rover/Pioneer/Harvester energy, mining, construction, claims, roles. Drones (§2h, §2j, §2j-1) live in [`drones.md`](drones.md); Pioneer upgrade/split and dynamic roles (§2b-1, §2b-2, §2f-1) plus fleet upgrade/commission/decommission (§2k, §2k-2, §2k-4) in [`fleet_lifecycle.md`](fleet_lifecycle.md); production and logistics sections of §2 in [`production_logistics.md`](production_logistics.md) (§2a-0…§2a-0-4, §2a-0-6), [`fabricator_demand.md`](fabricator_demand.md) (§2a-0-5, §2a-p, §2a-1…§2a-3), [`storage_mining.md`](storage_mining.md) (§2c, §2d, §2k-1, §2k-3, §2k-5, §2k-6) and [`pull_logistics.md`](pull_logistics.md) (§2i, §2i-1).

## §2 Surface Vehicles & Logistics

| Vehicle | Speed / Throttle | Energy Cost / Budgeting | Operational Rules |
| :--- | :--- | :--- | :--- |
| **Rover** | `self.cruise_throttle` (explicit at construction, else fleet-wide `vehicle.default_cruise_throttle` archive value, default 0.6) capped per-leg by `RoverController.max_safe_throttle_for_leg()` | Developer-confirmed travel model, Rover-specific, flat (no calibration, no Pioneer terms): `Wh/meter = 0.2 × throttle`; safety margin `SAFETY_MARGIN_MULTIPLIER = 1.05` (5%). See §2a | Sonar scan: `SONAR_WH_BUDGET = 2.0` Wh. Mining drill: exact per-ore/per-drill/per-purity `mine_wh_per_unit(item_id, purity)`, `MINE_WH_PER_UNIT = 2.5` Wh/unit only as no-item-id fallback. See §2a. Return to nearest charging station (not necessarily home) when Wh below trip budget. |
| **Pioneer** | Configurable slots / tools | Slot chassis: `inspect_slots()`, `execute_construction()`; construction energy: `WH_PER_PROGRESS` (per-vehicle calibrated, default `CONSTRUCTION_WH_PER_PROGRESS_DEFAULT = 40.0` Wh for 0%→100%). See §2a | Heavy construction, blueprint placement, pipe/power line deploy. Budgets each trip for `TARGET_CONSTRUCTION_PROGRESS_PER_TRIP = 0.25` progress (~4 round trips per job), not just round-trip driving. |
| **Harvester** | BFS on 8x24 grid (`NUM_ROWS=8`, `NUM_COLS=24`, A1..H24) | Travel time: 0.5 h/sector. Empty move: `+7 heat`; Item move: `+1 heat` | Max heat: 100°C. Pause & cool when heat exceeds `HEAT_SAFE_CEILING = 75.0`, resume at `HEAT_RESUME_LEVEL = 40.0` (`lib/harvesting.py`). The tier-4 Harvester script (`field_keeper.py`) replaces this with calibrated just-in-time resting, see §1k. |

**Early Harvester** (`scripts/0_cold_boot/harvesting/harvester.py`, no `lib/`): collects the surface field for credits per tick, tuned offline with `devtools/simulation/headless/harvest_policies.mjs` ("hybrid"; results in [`docs/plans/scoring_map_seeds.md`](../plans/scoring_map_seeds.md)). Re-plans before every hop and every collect except on arrival at its target. Times in ticks at 1× (1 world hour = 250).
- Routes: cheapest monotone route (steps toward the cell only) to every cell, by DP. Hop cost `MOVE_TICKS = 125` + heat price × hop heat (item cell or base pad +1, else +7). Heat price from `LAM_COLD = 20` ticks per heat unit at heat 0, linear to `LAM_HOT = 100` at the 97 limit, rounded.
- Target: the `PAIR_TOP = 6` items with the best `value / (route + COLLECT_TICKS = 63)`, re-rated by the best two-item trip `(v1 + v2) / (T1 + T2)`, second leg by Manhattan distance × (125 + heat price × `PAIR_HEAT = 4`).
- Collect gate: an item it stands on is collected only if worth ≥ `K_COLLECT = 0.5` × 63 × the best single-item rate; cheaper items stay as +1 stepping stones until the rate drops.
- Rest just before a hop would pass 97 heat (`HEAT_MAX − HEAT_SAFETY`), for exactly as long as needed. Starts once `min_scanned_sectors = 10` sectors are scanned. Sells every item at once.
- Paving stock: the `PAVE_KEEP_ITEMS = 4` items nearest the starter path cells (`PAVE_PATH` = A2, A4, B3, C2, `field_layout.path_cells()` of the starter at A1, a constant since this tier has no `lib/`; Manhattan hops), then the lowest-value (ties: lower cell; never the base pad or an item worth more than `PAVE_MAX_VALUE = 250` Scanner value), are never targets and stay as +1 stepping stones. The Field Keeper later carries them onto its path cells ([planting.md §1k](planting.md), Paving). Not moved by this script (no drop step in its router).
- Step budget: planning runs as `map()` callbacks (one tick each, uncharged, 10,000-step cap, §1d-1): route rows in chunks of `ROUTE_ROWS = 3` (~1,000 steps per row), the ranking, then pair candidates in chunks of `PAIR_WORK = 150` candidate × item pairs. Largest chunk ~4,200 steps on a full field; a plan takes ~6–7 ticks (up to ~13 on a full field).

### §2a Vehicle Energy Budgeting Detail (`lib/vehicle_energy.py` `VehicleEnergyMixin`; station discovery `lib/charging_stations.py`; charging and station-routed driving `lib/vehicle_charging.py` `VehicleChargingMixin`)

- Module split: `charging_stations.py` holds the station functions (`all_stations()`, `nearest()`, `outpost_ref()`, `station_at()`, `home_slot_coords()`, `current()`, `station_load()`) and the `STATION_DISCOVERY_TTL_TICKS` cache; `VehicleEnergyMixin` keeps one-line method wrappers (`get_all_charging_stations()`, `get_nearest_charging_station()`, ...). `VehicleChargingMixin` owns `recharge_at_station()`, `balance_dock()`, `drive_with_recharge()`, `return_to_base()` and `recharge_at_nearest()`; energy never drives.

#### Travel energy models

- **Travel energy = developer-confirmed exact model, no calibration — Pioneer and
  Rover use two DIFFERENT models.** Construction *progress* energy still calibrated
  (`wh_per_progress`, no confirmed formula).

  **Pioneer** (`VehicleEnergyMixin`, used as-is by `PioneerController`):
  ```
  power (W)   = (BASE_TRAVEL_POWER_W=3.0 + MODULE_TRAVEL_POWER_W=8.0 × active_modules
                 + CARGO_UNIT_TRAVEL_POWER_W=0.04 × cargo_units) × throttle^1.5 × nav_power_multiplier
  speed (m/h) = DRIVE_SPEED_M_PER_HOUR_PER_THROTTLE=100.0 × throttle × nav_speed_multiplier
  ```
  - `active_modules` — mounted functional modules drawing power while driving: Nav/Drill/Sonar/
    Constructor family, including upgraded variants (`ACTIVE_MODULE_ID_PREFIXES`). Passive
    containers (Battery Holder, Cargo Rack) don't count. `active_modules_count()`.
  - `cargo_units` — live `self.vehicle.cargo.count()`. `calculate_trip_energy()` computes outbound
    and return legs with *different* cargo loads (return = outbound + `planned_drill_units`).
    `cargo_units_count()`.
  - `nav_speed_multiplier` / `nav_power_multiplier` — from mounted Sport Nav modules. 1 Sport Nav =
    exactly 2x speed / 2.6x power (`docs/components/nav_module.md`). n Sport Navs = `1 + n` speed,
    `1 + 1.25n + 0.35n²` power (game formula; 2 -> 4.9x). Sport Nav replaces Basic Nav, so
    `active_modules` is unchanged. No Sport Nav gives
    both multipliers `1.0`.

  **Rover** (`RoverController` override in `lib/rover.py`, not in base mixin):
  ```
  Wh/meter = ROVER_WH_PER_METER_PER_THROTTLE=0.2 × throttle
  ```
  Developer-confirmed (Spyros - CT Dev, in-game Discord #playtest-chat, 2026-08-28): "the rover is
  very simple wh = distance x throttle x 0.2" — flat, **no** `active_modules`, `cargo_units`, or
  Sport Nav terms, linear in throttle (vs. Pioneer `throttle^1.5`).
  `RoverController.wh_per_meter_at_throttle()` overrides only that method —
  `minimum_wh_per_meter()`, `calculate_trip_energy()`, `energy_needed_to_return_now()`/
  `_comfortably()`, `energy_wh_for_leg()` all call through it. `max_safe_throttle_for_leg()` solves
  directly (linear): `t <= available_for_leg / (distance * ROVER_WH_PER_METER_PER_THROTTLE *
  SAFETY_MARGIN_MULTIPLIER)`.
  - Module-level standalone `_for`-suffixed versions (`travel_wh_per_meter_for(vehicle, throttle,
    cargo_units=None)`, etc.) let non-`VehicleController` callers (e.g. a charging station's own
    script — no cross-script instance calls exist, only `get_component(id)`/Archive/Signal Bus)
    use the same formula without a live instance, dispatching to the Rover model via
    `is_rover_chassis_for(vehicle)` (probes `vehicle.id`/`.name` for a `"rover"` prefix).
    `lib/charging.py`'s `rescue_wh_per_meter_for(vehicle)` collapses this into one entry point for
    rescue sizing (rates the leg at `MIN_SPEEDMODE_THROTTLE`, the cheapest Wh/m; falls back to a
    bare-module Pioneer shape if unreachable).
#### Charging stations and rescue

  - **Station pacing and arbitration** (`lib/charging.py` and `lib/drone_service.py`, shared base `lib/station_controller.py` `StationController`): `step()` returns busy (bays active/queued, a rescue in progress, or an entity this station owns that is stranded, below floor or below its rescue target); `run()` sleeps `ACTIVE_POLL_SECONDS = 1.5` while busy, else `IDLE_POLL_SECONDS = 5.0` (unpowered included). Per entity, `assess_stations()` does one pass over the per-poll station list and returns (is this station nearest, nearest distance, nearest coords); a station does floor/target work only for entities it is nearest to (tie or own position unknown → mine; a dry service is never nearest for a heli drone). `return_floor_wh()`/`rescue_target_level()` take the already-computed distance/floor. Parked stations (`lib/script_parking.py`, dev_workflow.md §1d-2) are left out of the nearest check; an entity needing attention that is nearest to a parked station gets that station woken (`wake_for_visit()`) instead, and the woken station handles it. `step()` feeds a `ParkRequester` (idle = powered and not busy).
  - **`lib/charging.py` fleet rescue** (`manage_fleet_rescues()`): dispatch triggers on engine
    `"stranded"`/`"stalled_no_battery"` status, OR `return_floor_wh()` (the Wh needed on board
    *right now* to self-navigate to the nearest station, via `rescue_wh_per_meter_for()` at
    `MIN_SPEEDMODE_THROTTLE` — same formula the vehicle's own hard-abort uses).
    `RESCUE_EXTRA_RESERVE_WH = 8.0` is added on top only when sizing `rescue_target_level()` (how
    much to charge *during* rescue); the trigger comparison uses the bare floor.
  - **Multi-station arbitration**: every deployed station gates dispatch on
    `assess_stations()` (see station pacing above), so only one rescues a given stranded vehicle. Ties default
    to allowing dispatch.
  - **Station choice when parked** (`balance_dock()`, called by `recharge_at_station()` after it parks): every station inside an outpost covers the whole outpost. With 2+ stations in the outpost of `current_station()`, the vehicle calls `dock()` on the one with the fewest other vehicles queued or active per bay (`get_queue()` ∪ `get_active()` / `get_bay_count()`; ties: current station, then id), then charges and wakes that station. Docked = `current_station()` non-empty.
#### Trip budget, mining budget and throttle

- Round-trip budget = outbound drive + sonar/scan budget + mining/drill budget + drive from target
  to *nearest* charging station, all × `SAFETY_MARGIN_MULTIPLIER = 1.05` (5%), plus hard
  `MIN_EMERGENCY_RESERVE_WH = 8.0` floor on top. See `calculate_trip_energy()`.
- **Mining/drill budget also developer-confirmed exact model, not flat average.**
  `mine_wh_per_unit(item_id, purity)` (and standalone `mine_wh_per_unit_for(...)`):
  ```
  time (h) = (ORE_DIG_MINUTES[item_id] / 60) × drill.speed_multiplier() / PURITY_DIVISOR[purity]
  Wh       = time (h) × DRILL_POWER_W_BY_HARDNESS_LIMIT[drill.hardness_limit()]
  ```
  Per-tier Watts: basic=10W/industrial=20W/heavy=30W (keyed by `drill.hardness_limit()`, no
  `.power_draw()` method exists). Per-ore dig minutes (`docs/database/items_minerals.md`):
  iron_ore/silicon=15, lead_ore=18, titanium/cobalt=20, rare_earth=25, neutronium=30. Purity yield
  multiplier: `standard`=1×/`rich`=2×/`pure`=3× (same divisor as game's own time formula).
  `calculate_trip_energy()`'s `mine_item_id`/`mine_purity` params feed this; every real mining
  call site passes candidate's own `harvest_item`/`purity`. `MINE_WH_PER_UNIT = 2.5` (flat) =
  only fallback for candidate with no `mine_item_id` — equals cheapest real case (basic drill,
  iron ore, standard) but under-reserves by up to **~3.6x** for Heavy/Neutronium
  (`9.0` Wh vs. flat `2.5` Wh).
- Throttle clamped to `[MIN_SPEEDMODE_THROTTLE=0.10, MAX_SPEEDMODE_THROTTLE=1.0]`, picked
  per-leg by `select_cruise_throttle()` / `max_safe_throttle_for_leg()`. Pioneer power scales with
  `throttle^1.5`, speed with `throttle`, so leg Wh/m scales with `sqrt(throttle)` —
  `max_safe_throttle_for_leg()` solves via `t <= (available_Wh / (distance *
  coeff * SAFETY_MARGIN_MULTIPLIER)) ** 2`.
- **Cruise throttle = one numeric default, not binary conserve/highspeed flag.**
  `select_cruise_throttle()` picks `min(self.cruise_throttle, MAX_SPEEDMODE_THROTTLE)` as
  baseline, then caps DOWN (never up) to what `max_safe_throttle_for_leg()` allows.
  `self.cruise_throttle` = `default_cruise_throttle()`, read once at script start (no per-slot
  override; vehicle and drone scripts have no throttle parameter) — fleet-wide
  `vehicle.default_cruise_throttle` archive value (clamped to `[MIN_SPEEDMODE_THROTTLE,
  MAX_SPEEDMODE_THROTTLE]`, fallback `DEFAULT_CRUISE_THROTTLE_FALLBACK = 0.6`), settable via
  Data Archive Notebook or live from `vehicles_panel.py`'s FLEET card slider. `lib/drone_energy.py`
  mirrors exactly for drones — own `drone.default_cruise_throttle` archive key (distinct from
  vehicle key so fleets tune independently), same clamp, fallback `DEFAULT_CRUISE_THROTTLE_FALLBACK = 1.0`, settable from the FLEET card's
  Drones-tab slider (`vehicles_panel.py`, §7).
- `minimum_wh_per_meter()` gives best-case Wh/m at throttle floor. Any check claiming target/job
  *permanently* unreachable (not just "not right now") must budget against this, not typical
  cruise-throttle rate.
- Two reserve checks, deliberately separate:
  - `energy_needed_to_return_now()` — true floor, at `minimum_wh_per_meter()`. Used only for
    the **hard mid-drive abort** inside `drive_to()`'s tick loop.
  - `energy_needed_to_return_comfortably()` — rated at `self.cruise_throttle`. Used for every
    **proactive** "keep working or head back" decision (mining stop check, construction Field
    Battery Floor, survey per-POI/per-waypoint reserve checks). A simple heuristic, not an exact
    time/output optimum.
- `drive_to()` computes `is_driving_to_station` once before polling loop, skips return-reserve
  abort check entirely when destination is charging station/base slot (or already within 3m) —
  arriving there *is* recovery.
#### Construction

- Construction (Pioneer only): `calculate_trip_energy()`'s `planned_construction_progress` param
  adds `progress * self.wh_per_progress`. `wh_per_progress` calibrated per-vehicle from real
  `constructor.execute()` calls (`calibrate_wh_per_progress()`), fallback
  `CONSTRUCTION_WH_PER_PROGRESS_DEFAULT = 40.0` Wh (0%→100%) until enough samples.
  `construction_lots.planned_progress_for_job()` caps planned progress at
  `TARGET_CONSTRUCTION_PROGRESS_PER_TRIP = 0.25` (or less if further along) — floor on whether to
  depart, not on-site cap.
- Construction trip throttle (Pioneer only, `BuildJob._plan_trip_throttle()`, every step with
  cargo for pending jobs, from the current position and battery): `construction_plan.trip_route()`
  chains the first `TRIP_PLAN_JOBS = 8` served jobs nearest-next, and `trip_throttle()` tries
  throttles from the base cruise down to `MIN_SPEEDMODE_THROTTLE` in `TRIP_THROTTLE_STEP = 0.05`
  steps. Per throttle: longest chain prefix whose drive out + drive to nearest station (× margin) +
  capped progress Wh + 2 × emergency reserve fits the battery; pick max jobs / cycle hours, where
  cycle hours = driving hours + hours to recharge the battery's deficit plus the trip's Wh at
  `TRIP_CHARGE_W = 60.0` W. Sets the vehicle's `cruise_throttle`, so the field reserve checks above
  use it too. No fitting plan: at a station, reset to base (`BuildJob.base_cruise_throttle`, the
  throttle before the first plan); in the field, keep the throttle and recharge at the nearest
  station first, so the trip out is planned there (not driven at cruise after a
  `drive_with_recharge()` top-off). A far chain gets driven slower and several jobs per charge
  instead of one.
- **Construction job claims (Pioneer only, `BuildJob` in `lib/job_build.py`, exclusive)**: construction
  job NOT shareable (two Constructor Pioneers on same blueprint would double-load materials).
  Uses `vehicle_claims.py`'s exclusive claim mechanism, key `f"build_{job_id}"`
  (`PioneerController.construction_claim_key()`), prefix distinct from mining `"site_"`/survey
  `"poi_"`. `claim_target()` called at each of three commit points (resuming paused job,
  executing cargo-matching pending job, committing before round trip home).
  `execute_construction()` heartbeats via `refresh_claim()` every attempt (no-op if not owner).
  Released on completion (`last_build_progress >= 1.0`, the progress read after the last `execute()` of `execute_construction()`) or genuine failure, held across
  incomplete "still paused" outcome, released wholesale on unhandled exception (`BuildJob.on_error()`,
  called by `run_job_loop()`).
  **Blueprint missing from every list (pending/active/paused) counts as complete (1.0)** — game
  drops finished blueprints from all lists.
  `construction_lots.release_finished_claims()` also sweeps this Pioneer's own `build_*` claims on
  no-longer-live blueprints each `BuildJob.step()` (one transaction per claims key, only when something
  needs releasing, skipped if any list read failed).
- **Construction job scan (`lib/construction_plan.py`, pure, via `lib/atomic.py`)**: each
  `BuildJob.step()` scans the paused/pending/active blueprint lists in atomic
  slices (`scan_jobs()`, `JOB_CHUNK = 15` jobs per call): job ids for the claim sweep, open rows
  (id, not in `BuildJob.failed_jobs`, not in an active peer's lot, no fresh peer claim per
  `claim_free()`), and cargo-matching rows (deconstruction, or materials aboard per one
  `cargo.stacks()` read, `ConstructionStockMixin.cargo_counts()`) sorted by priority, then own lot first, then nearest first. Step 5's "permanently out of range" check runs as `station_trip_wh()`
  (`TRIP_CHUNK = 12` rows per call, nearest of the memoized station list).
  `get_construction_progress()` finds the job via `job_progress()` (`PROGRESS_CHUNK = 256`).
  Worst slice per function asserted below `ATOMIC_STEP_BUDGET = 4000` operations in
  `tests/test_construction_plan.py`. Only the scan is atomic: claims, archive writes, trip
  budgeting (logs) and driving stay outside.
- **Construction restock batch (`BuildJob` restock step, `ConstructionStockMixin.stock_materials()` in `lib/pioneer_stock.py`)**: loads toward the summed need
  of open jobs using the target job's material (`batch_count()`), capped by free cargo. With
  active same-home Constructor peers (`peer_builders()`: `fleet.status` entries with
  `role == "builder"`, same `home`, heartbeat younger than `PEER_BUILDER_ACTIVE_TICKS = 6000`
  ticks (10 sim min), state not idle (`fleet_status.is_idle()`: any `IDLE*`, `READY_AT_*`,
  off duty)), `fair_share_batch()` caps it further at
  ceil((home takeable stock + units aboard) / builders) (`fair_share()`,
  `storage.takeable_stock()`). A lone builder is uncapped, so a long remote chain with field
  recharges still runs on one load. **Top-up** (`_top_up_materials()`): after that load, the
  cargo room left is filled with the other materials the open jobs at the working priority need
  (`construction_plan.other_materials()`: the material whose job is nearest the target job
  first), each loaded only when its nearest job's whole need fits the bins (`bin_space()`: room
  in bins holding it plus empty bins, a Portable Bin holds one item type) and home takeable
  stock, capped by `batch_count()` and `fair_share_batch()`; skipped while a deconstruction is
  open (it needs room for reclaimed parts). So one trip home stocks for several materials.
  Heartbeat: `publish_telemetry("BUILDING")` at every
  `execute_construction()`, `"RESTOCKING"` at every restock. A failed restock defers every open
  job needing that material for the pass (`ids_needing()`), not just the target job.
- **Construction lots (`construction.lots`, restock step, `BuildJob._reserve_lot()`; archive I/O in `lib/construction_lots.py`)**: after loading a
  batch, a Constructor reserves the jobs it covers as its lot: the claimed seed job plus a
  nearest-neighbour chain of open same-material jobs (deconstructions with deconstructions,
  `DECONSTRUCT_LOT_JOBS = 10`) grown from it (`construction_plan.grow_lot()`, atomic
  `grow_lot_step()` chunks of `LOT_STEP_VISITS = 80` candidate visits, an append counting as
  `LOT_ADD_VISITS = 4`), cut to the units aboard (`lot_prefix()`); each topped-up material adds
  its own chain, grown from its nearest job, to the same lot. The chain skips jobs a peer
  claimed since the pre-trip scan. One transaction replaces the builder's entry, keeps ids a peer
  reserved meanwhile, and prunes entries of builders no longer active. A seed job that landed in
  a peer's lot meanwhile has its claim released, so the lot owner can build it. Peers drop every job in the lot of an active Constructor of any home
  (`peer_builders()` with `home=None`) from their scan; a lot of a quiet or inactive owner stops
  counting without a write. The owner sorts its own-lot jobs first when building from cargo and
  restocks its own unbuilt lot jobs first. Released when the builder idles without jobs, defers a
  material, or its step raises. Builders so work separate stretches of a line or separate sites
  instead of chasing each other to the same nearest job.
- **Construction hold (`construction.hold`, `construction_lots.read_hold()`, `BuildJob`)**: `{"by", "tick", "kinds"}`; while fresh (`construction_plan.held_kinds()`, younger than `HOLD_STALE_TICKS = 600`), jobs of a held kind are dropped from the open rows and cargo matches after the scan. They still count as live for claim and priority pruning. The autoplay power survey holds `deconstruct` while it probes.
- **Power-line ledger (`construction.power_tiles`, `execute_construction()`)**: a finished job (`res.status == "ok"`) calls `construction_lots.note_finished_power_job()` → `construction_plan.note_power_job()` in one transaction: a `power_line` piece adds its two tiles (`power_job_tiles()` from the job position); a `deconstruct` or `power_bridge` job marks its tiles dirty for re-probing. See [autoplay.md §11d](autoplay.md).
- **Construction job priority (`construction.priority`, `BuildJob`)**: each row
  carries `prio` from the archive dict (`construction_plan.PRIORITY_KEY`, `{blueprint_id: int}`,
  read once per pass before the job lists, cleaned by `clean_priorities()`); a blueprint without
  an entry is `DEFAULT_PRIORITY = 0`, lower runs first, so a negative value raises a job and the
  autoplay planner's plan-ahead jobs use 1. Each pass works only the lowest prio among open
  paused + pending rows (`top_priority()`/`at_priority()`): lower-priority jobs are not built,
  matched from cargo, or counted in the restock batch/`fair_share_batch()` while a higher one is
  open. A job that failed this pass or is claimed by a peer is not open, so a peer or a stock
  shortage lets the next priority through; when every pending job at the top priority was just
  marked out of range, the job rescans at once instead of idling. Entries of blueprints no longer
  in any list are pruned each pass (`construction_lots.prune_priorities()`, one transaction, only when
  something is stale, skipped if a list read failed). With the key absent every job is prio 0 and
  the job behaves as without priorities.
#### Claims, missions and recall

- Fleet coordination (`lib/vehicle_claims.py`): atomic `archive.transaction()` claims (mirrored to
  `rover.claims` / `survey.claims`), heartbeat-renewed via `refresh_claim()`, expire after
  `fleet_claims_common.CLAIM_STALE_TICKS = 36000` ticks (1 real hour; drone claims and the archive cleaner use the same value). **Mineral mining sites not exclusive**
  (several Pioneers/Rovers may mine same site): a mine claim is per vehicle, key
  `"<target_key>@<vehicle>"` (`mine_claim_key()`, `VehicleClaimsMixin.claim_key()`), so it never
  loses to a peer; it only serves bookkeeping (the mission, resume via
  `_mission_claims()`). Survey/POI targets still exclusive via same mechanism.
  The current job target is `VehicleController.mission` (`lib/mission.py` `Mission`), written only by
  `VehicleClaimsMixin`: `begin_mission(m)` = claim (skipped with `claimed=True`) + yield reservation when
  `m.reserved_yield` + `vehicle.mission` record + set; `end_mission()` = release claim, yield reservation
  and record, clear. `current_target`, `current_target_key`, `current_target_reserved` are read-only
  views of it (a write raises `AttributeError`). `release_target_claim()` on the current target (or with
  no key) calls `end_mission()`. After a reload `load_mission()` returns `Mission.from_record(...)` and
  `adopt_mission()` sets it (a mine mission then re-arms `reserved_yield` from the live reservation).
  Drones keep the dict path (`current_target*` attributes).
- **In-flight mining yield reservation** (`lib/mining_reservations.py`, `mining.reserved_yield`
  archive key): non-exclusive, additive bookkeeping, so vehicles converging on one deficit don't
  all see the same undiminished demand. One entry per vehicle (its current trip).
  `VehicleMiningMixin.select_best_mining_target(candidates)` reserves every mine trip's planned
  yield: `max_mineable_units()` capped by candidate `"max_units"` (stockpile headroom), tagged with
  the delivery `outpost_id`. `logistics_requests.outpost_tier_deficits()` counts reservations
  for that outpost as in-flight (`exclude_vehicle=` leaves out a miner's own), so pull haulers and
  `home_ore_demand()` never chase ore a miner already fetches; stockpile path's
  `stockpile_headroom(outpost_id, item_id)` = `ore_stock_target()` − stock − peers' reservations −
  hauler pickups bound there (`in_flight()`). A second vehicle joins a site only while demand is left
  after every reservation. Heartbeat-renewed/released (`refresh_yield()`/`release_yield()`),
  same expiry (`RESERVATION_STALE_TICKS = 36000`).
- **Energy-based mining trip sizing** (`VehicleEnergyMixin.max_mineable_units()`): default
  yield estimate (not `cargo.capacity()`). Solves trip-energy budget directly for units
  (outbound + base return Wh fixed, mined-unit Wh and marginal return-drive Wh linear in unit
  count) after subtracting `MIN_EMERGENCY_RESERVE_WH` and applying `SAFETY_MARGIN_MULTIPLIER`,
  clamped to free cargo (`cargo.capacity()` − `count()`). `mine_until_full_or_exhausted()` stays safety net for estimate
  drift (e.g. richer-than-expected purity).
- Recall (flag in `lib/vehicle_claims.py`, `handle_recall_if_active()` in `lib/vehicle_recall.py`): one shared `vehicle.recall` dict `{vehicle_name: True}` (not
  one archive key per vehicle). `is_vehicle_recalled()`/`set_vehicle_recalled()` module-level
  read/write. Toggled via `vehicles_panel.py`'s Fleet card switch: on → abandon current target, drive to
  base now; off → resume. Checked inside `drive_to()`'s tick loop and mining loops, same
  `is_driving_to_station` exemption as return-reserve check.
- Navigation timeout (`drive_timeout_ticks()`): defaults `None`, computed per-leg from expected
  travel time, converted via `Clock.real_seconds_per_hour()` (not flat constant — compressed
  day/night cycle stretches game-hours relative to world-clock hours). `safety_multiplier = 2.0`,
  `min_ticks = 3000` floor.
- Navigation safety: stall detection re-issues drive command after repeated stuck cycles,
  dropping to `MIN_SPEEDMODE_THROTTLE` each retry, gives up after 3 failed recoveries — applies
  regardless of `is_driving_to_station`. Base staging slots staggered per vehicle index.
- `is_at_base(threshold=3.0)`: `self.distance_to_home() <= threshold`. Gates one-time-per-visit
  actions (top-off charging, restocking) so they fire only when parked at base.
- **Loop-top "cargo aboard but not at base" safety net vs. mission resume**:
  `MineJob.prepare_cargo()` (`lib/job_mine.py`) keeps cargo aboard while `host.mission` is resumable
  (target key + coords), so save reload mid-trip doesn't undo already-resumed drive.
  `cargo_matches_target(target)` (cargo holds *different* material than resumed target's
  `harvest_item`; cargo not material-locked) or `cargo_full_for_resume()` sends it home to unload
  first, mission kept; the step ends after the unload (`blocked_delay` 10 s while cargo is still aboard) and the next one resumes. Target with no
  `harvest_item` (survey POI) always matches.

### §2b Mining (`lib/vehicle_mining.py` `VehicleMiningMixin`, `lib/job_mine.py` `MineJob`)

Mineral-site discovery + drill execution in one place, shared by Rover and Pioneer (mixed into `VehicleController`). No loop: the mining role is `MineJob(host, targets)` run by `run_job_loop()`.

- **`MineJob` step** (`lib/job_base.py` contract): `prepare()` at base tops off below 95% (Rover at any station; `OutpostStockpile` only with a station at its outpost, §2e) and runs `handle_upgrade_cycle_if_idle()` when the host has it; `prepare_cargo()` handles cargo aboard (§2a resume net) and `targets.transfer()`. `pick()` = resumable `host.mission` (fresh trip budget, copy of the mission) else `targets.select()` (claims through `select_best_mining_target()` → `begin_mission`). `execute()` = log block, `OUTBOUND`, `drive_with_recharge()`, `scan_and_survey(mission)` for a `poi` target or `mine_until_full_or_exhausted(coords, targets.mine_units())` for `mine`, `return_to_base()` (incomplete: mission kept, 5 s), `release_target_claim()`, `unload_cargo()` (blocked: `WAITING_INVENTORY_SPACE`, 10 s), recharge (same station rule as the top-off), ready telemetry. `on_error()` = `release_target_claim()` (every claim, yield reservation, saved mission).
- **`RoverTargets`** (`RoverController.run()` = `run_job_loop(MineJob(self, RoverTargets()))`): `cleanup_stale_claims()`, unscanned POIs (priority 1) + `build_mineral_site_candidates()`; mines the reserved `estimated_units`; idle = warn with the reason (no home demand / no candidate / none in budget / claims), `IDLE_AT_BASE`, 10 s; no transfer step (plans from where it stands).
- **`OutpostStockpile(outpost_id)`** (Miner Pioneer, §2e): `build_local_stockpile_candidates(outpost_id)`; transfers to the base slot first when away; mines max(1, stock headroom, NEED request) live at the site; idle = recharge when `charge_would_reach()` (0 s), else the stand-by reason (`stockpile_empty_reason` or `reject_reason()`), `IDLE_AT_OUTPOST`, 30 s.

- Capability always read live via `self.vehicle.drill.hardness_limit()` — never assumed from vehicle type. Rover fixed Drill only carries basic drill (`hardness_limit = 1`, iron_ore/silicon); Industrial (`hardness_limit = 3`) and Heavy (`hardness_limit = 4`) Drills = Pioneer-universal-slot items for higher-hardness sites.
- `home_ore_bands()`: `{band: {ore: units}}` the vehicle's `home_outpost` still requests (`logistics_requests.outpost_tier_deficits()`, raw ores only via `ore_bands()`; a smelting site's ore requests, dock-owed ore included, come from §2i-1) net of stock, in-flight pickups and the yield that in-flight mining trips there already promised (`mining.reserved_yield`). `home_ore_demand()` = every band summed (`sum_bands()`). `build_mineral_site_candidates(deprioritize_hardness_at_or_below=None)`: candidate sites matching it + vehicle hardness limit (Rover); each gets `"band"` = `top_band(bands, ore)`, the highest band in which home still misses that ore (`STOCK` when only stock headroom is left). Passing `ROVER_PREFERRED_MAX_HARDNESS = 1.0` sets `priority=3` instead of `2` on hardness ≤ 1 sites — **soft** preference.
- Neither candidate builder filters peer-claimed sites (mineral sites not exclusive) — see `lib/mining_reservations.py` for overmining guard.
- `select_best_mining_target(candidates)`: sorts by `(priority, -band, -mining_score(),
  distance)` — priority first; then ore missing in a higher band at the delivery outpost beats lower-band ore (same rule as haulers' `haul_rank()`; the fine prio plays no part); then the highest score; distance only breaks ties. Score = candidate `"urgency"` / `mining_hours_per_unit()`. Hours per unit = `mine_hours_per_unit()` (dig time: mounted drill, site purity) + round trip at `leg_speed_m_per_hour()` (`select_cruise_throttle()` incl. battery cap, mounted nav) / units per trip (`max_mineable_units()` on the battery on board, capped by `"max_units"`). All read live per pick, so battery, throttle and loadout changes (outfitter) re-rank. `"urgency"`: stationed `STOCK`-band candidates carry `stock_urgency(item, room, band)` = missing share of `ore_stock_target()` (0..1), so a nearly empty slow ore beats a half-full fast one; ore missing in a higher band and home-demand candidates use 1.0 (the band already puts it first; pure speed). POI candidates score 0. Soft preference — `calculate_trip_energy()` achievability check + `claim_target()` still run after sort. Both builders attach site `"purity"` from `getattr(site, "purity", None)`.
  Achievability checked at full 10-unit haul first; if not fitting round-trip budget, retries once at whatever `max_mineable_units()` says affordable instead of rejecting (only 0 affordable = real rejection) — else vehicle whose battery never fits full 10-unit trip (undersized battery, or expensive-per-unit ore like Neutronium) idles at base forever despite reachable demand. Logged at `print()` level (`"battery can't afford a full load -- heading out for a partial ~N-unit load"`) when fallback fires — normal-operation outcome worth surfacing, not debug detail.
- `mine_current_site(max_units=None)` defaults to `self.vehicle.cargo.capacity()` (live) when no `max_units`. Home-demand mining loops always pass explicit `max_units` from `select_best_mining_target()`'s `estimated_units` (energy-based, `max_mineable_units()`).
  `mine_until_full_or_exhausted(target_coords, max_units)` wraps it with recharge-and-resume-in-place loop; `max_units` bounds the whole job (each resume gets what is left). Battery-interruption recharge stop landing at *home base* station itself with cargo loaded unloads via `unload_cargo()` **before** `recharge_at_station()` (ore not stranded in cargo during a possibly multi-minute recharge), then ends the job (`"load delivered at base"`) after `run_module_upgrades_mid_job()`: the next cycle picks its target from current demand. Resuming with an empty hold instead let a battery-bound stationed miner stockpile one ore for hours past its target while the others ran dry.
- Pioneer mining role (`MineJob` with `OutpostStockpile`) requires operator already mounted drill — `detect_role()` picks it by the mounted drill; under `role_override` without one, `mine_current_site()` logs "No DrillModule mounted!" and mines nothing; never auto-mounts.
- **Unified role entrypoint (`PioneerController.run()`/`detect_role()`, `lib/pioneer.py`)**: every `pioneer_N.py` script constructs `PioneerController`, calls `run()`. `detect_role()` maps `ROLE_MODULES` (`{"builder": "constructor", "scout": "sonar", "miner": "drill"}`: role -> vehicle attribute) via `hasattr(self.vehicle, <attr>)` — exactly one mounted module picks role; none → `"hauler"`; more than one = misconfigured loadout (`TreeConsole` warn + no-op) unless `role_override=` passed. `run()` dispatches: builder → `run_job_loop(BuildJob(self))` (`lib/job_build.py`; loop plumbing in `VehicleController.run_job_loop()`, `lib/job_base.py` contract), scout → `run_job_loop(SurveyJob(self))` (`lib/job_survey.py`; skipped with a warning when Sonar or Nav Module missing, `SurveyJob.can_run()`), miner → `run_job_loop(MineJob(self, OutpostStockpile(self.home_base)))` (`lib/job_mine.py`), hauler → `run_job_loop(PullJob(self))` for `HOME_BASE` (`lib/job_pull.py`, §2f). Equipment swappable at runtime, so re-probes every script run, no role caching.

### §2e Stationed Mining Role (`lib/vehicle.py`, `lib/vehicle_energy.py`, `lib/vehicle_mining.py`, `lib/job_mine.py`)

Rover/Pioneer can treat **any** outpost — not just home — as base.

- **`VehicleController.__init__`'s `home_base` param** (outpost id, or `None` = production/home outpost). Resolved to **live objects once at construction**, cached as `self.home_outpost` (`get_outpost_ref(home_base)`) and `self.home_charging_station` (`find_charging_station(self.home_outpost)`), no re-walking `outpost_network.outposts()` by id per lookup. `get_home_slot_coords()` reads only these two cached fields: station position if found, else outpost's `.coords()`, else `(0, 0)` only if `outpost_network` unavailable at construction. `self.home_base` kept only for identity checks. Trade-off: charging station built at this outpost *after* construction not picked up until next script reload.
- **`unload_cargo(outpost=None)`** — defaults to `self.home_outpost` (cached), so stationed vehicle unloads into own outpost's Warehouse; or an explicit `outpost`.
- **`VehicleMiningMixin.build_local_stockpile_candidates(outpost_id)`** — Sites: `cuttable_sites()` = every surveyed raw-ore site the drill cuts (`item_tiers.can_cut()`); `select_best_mining_target()` drops those the charge on board can't reach. Reach: `reach_ores()` = ores with a site whose round trip from the outpost fits a full battery (`full_battery_reaches()`: out + 1 unit dug + on to the charging station nearest the site, cruise throttle, trip margin and reserve, against capacity), walked nearest first: an ore stops at its first site in reach, the walk stops at the first site whose outbound leg alone exceeds capacity. Published as this miner's reach (`outpost_mining.publish_reach()`, storage_mining.md §2d). Per ore in reach: max(stock headroom, NEED request). Stock headroom (`stockpile_headroom()`) = `ore_stock_target()` − local stock − peers' reserved yield − hauls bound here, but 0 for an ore not in `outpost_mining.active_ores()` or without buffer room (`ore_buffer_fits()`). NEED request = `stockpile_need(outpost_id)`: `stockpile_bands()` = that outpost's `outpost_tier_deficits()` net of peers' reserved yield, plus `remote_ore_need()`, folded by `split_need_stock()`; `NEED`+ ores there are latched active; dock-owed ore arrives through that request like any other, §2i-1. `remote_ore_need(outpost_id)`: other outposts' `NEED`-or-above ore deficits (`live=False`) for ore no miner stationed there reaches but one here does (`mineable_ores_by_outpost()`), netted highest band first by the ore held here plus peers' reserved yield here; every outpost reaching that ore sees the whole need, haulers carry the ore over. Blacklisted sites are skipped. Each candidate carries `"band"` = `top_band()`, so a dock order's ore goes ahead of a closer stock-only ore; `max_units` and the trip cap = max(stock headroom, need). Independent of home's live demand.
- **`MineJob(pioneer, OutpostStockpile(outpost_id))`** (§2b) — same step as the Rover's `MineJob` (reload resume, cargo/target mismatch detour, claim + drive + mine + return + unload + recharge, release claim right after return), target selection swapped for `build_local_stockpile_candidates()`, plus a transfer to the base slot before picking.
- **Outpost without its own Charging Station** (`self.home_charging_station is None`): no top-off below 95% at the base slot and no recharge after unload. The nearest station may sit at another outpost, and the transfer back to the base slot would spend what the top-off gained, so the cycle would loop. The miner launches on what is on board. It recharges only when every site is out of energy range and a full battery, less the station-to-slot transfer, covers the cheapest one (`OutpostStockpile.charge_would_reach()`).

### §2f Hauler Role: Floating Pull Hauler (`lib/job_pull.py` `PullJob`, planning `lib/pull_plan.py`)

Every hauler-role Pioneer (no constructor/sonar/drill mounted, §2b) runs `run_job_loop(PullJob(self))`: it fetches whatever any outpost is missing from wherever the stock sits and brings it there (full cycle in `pull_logistics.md` §2i). There is no destination parameter and no push hauling. The hauler floats: `HOME_BASE` is only where it starts and its commission origin (`home_base`, lineage, `_wrong_home`).

- **Base** (`VehicleController.set_base(outpost_id)`): re-resolves `home_outpost`, `home_charging_station` and the staging slot (`assigned_slot_coords`/`home_coords`), so `is_at_base()`, `return_to_base()`, `unload_cargo()` and charging work against the new outpost; `base_id` = its id. `PullJob` moves the base to each trip's destination when it claims the pickups. A reload resets the base to `HOME_BASE`; cargo aboard goes back to its pickups' destination (`logistics_requests.pickup_dest()`), a resumed mission to its `"dest"`. Telemetry: `fleet.status` `base` (archive_ipc.md).
- **Ore to home**: home's requests are served like any outpost's, ore included (home smelting site ore requests, §2i-1), collecting from mining outposts' Warehouses, advertised drills and salt pumps.
- **Remote Bio Lab reagents**: a trip to the lab's outpost serves its buyable reagent requests (§2g), buying them at the Shop on a stop at the home outpost. Hauler drones serve them too (§2j).
- **Drone Depot pickups**: an outpost stop loads from the stores, then from the Drone Depot stockpile above `depot_holds()` (`_take_from_depots()`, pull_logistics.md §2i free stock). The game lets a Pioneer inside the Depot's service area `take()` from it; every Depot take's status is logged.
- **No nearest-free dispatch**: destinations are ranked band-first (§2i), then by the trip's `haul_rank()` from the hauler's position, which already charges the empty leg to the first stop.
- **Dispersal** (no trip: `NO_DEMAND` or `SHORT`, `PullJob._disperse()`): the hauler moves its base to `outpost_flow.dispersal_target()` = the founded outpost with the highest `(1 + sent) / (2 + idle haulers based there)` (`sent` = decayed units picked up there, `logistics.outpost_flow`, pull_logistics.md §2i; idle haulers = fresh on-duty idle `fleet.status` hauler entries with a `base`, this one excluded; ties to the nearest), only when that beats the current base by `DISPERSE_GAIN = 1.25`, at most once per `DISPERSE_COOLDOWN_TICKS = 3000`. It publishes `IDLE_AT_OUTPOST` with the new `base` before driving, so other idle haulers count it there. Otherwise it parks at its current base.
- **Save migration**: `devtools/scripts_sync.py` re-homes a slot that still carries a push-hauler `DESTINATION_OUTPOST_ID` (cached answer or slot code) to that destination (`rehome_retired_destination()`; `outpost_home` → `None`, wildcard/empty → `HOME_BASE` kept).

### §2g Remote Bio Lab Reagent Resupply (`lib/outpost_reagents.py`, `lib/bio.py`)

A home Bio Lab buys missing reagents just in time. A remote Lab can't (no Shop delivery off-home), so `BioLabController.step()` at a non-home outpost calls `outpost_reagents.publish_reagent_requests(outpost)` (errors `swallowed()`): `logistics_requests.publish_requests(outpost_id, "bio_reagents", {item: (levels, have)}, buyable=True)`, recomputed every `REAGENT_REQUEST_REFRESH_TICKS = 600` per outpost (whole target as one `NEED` level; `have` = `logistics_requests.outpost_stock()`, Warehouses + Drone Depots). A hauler drone (`drone_haul_plan.shop_sources()`, §2j) or the Pioneer hauler homed there (`pull_plan.shop_source()`, §2i) fetches free stock first and buys the rest.

**`outpost_reagents.py`** mirrors `outpost_mining.py` seed-once-then-editable convention (`assigned_reagents_for(outpost_id)`, `reagent_stock_target_for(outpost_id, item_id)`), but per-reagent, not one flat constant (reagent prices span 1cr to 1,000cr):

```python
DEFAULT_REAGENT_STOCK_TARGETS = {
    "alkaline_buffer": 100, "cryo_solvent": 100, "protein_marker": 60,
    "chelating_agent": 20, "enzyme_solution": 10,
}  # dial these up as credit budget allows; FALLBACK_REAGENT_STOCK_TARGET = 100 covers any
   # reagent id not yet in this dict (e.g. a future game update)
```

A remote Lab loads from `lib/bio.py`'s `local_stock(item_id, outpost)` = `storage.total_stock(item_id, outpost)` (home Inventory only at home). `storage.outpost_is_home(outpost)` reads `OutpostRef.is_home` (a plain `bool` property, unlike the same-named method on the full `Outpost` component from `get_component()`; it accepts both).

`lib/bio.py`'s `local_sibling(outpost, type_id)` replaces hardcoded same-pipeline instance ids with live `outpost.buildings(type_id)` lookup (first match, resolved) — needed because Bio Lab's `take_from()` requires its Collector at *same* outpost. No caching — resolved fresh per call, since sibling building may not exist yet at controller construction.
