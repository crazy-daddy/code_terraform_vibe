# Power & Fluids (§1a–§1c-5)

Part of [`AI_CHEATSHEET.md`](../AI_CHEATSHEET.md). Formula summary table: hub §1.

### 1a. Power Guard: Phases and Load-Shedding Tiers (`lib/power.py` `PowerGridManager`)

One `PowerGridManager` per grid (§1a-1). Each `supervise_grid(grid, elevation)` reads the grid's **power phase** (`grid_phase()`, from member `type_id`s) and picks the shedding strategy from it. The phase is re-read every pass. Phase changes are logged (`[POWER] Grid '<anchor>' phase X -> Y.`), and shed machines carry over to the new strategy's restore path.

| Phase | Detected by | Shedding | Extra |
| :--- | :--- | :--- | :--- |
| `solar` | no turbine / oil generator / producing reactor | Solar night guard (`lib/power_solar.py`, below) | — |
| `steam` | `steam_turbine` member | Combined-reserve guard (§1a-0) | — |
| `oil` | `oil_generator` member | Combined-reserve guard | Solar-retire advisory |
| `reactor` | `reactor` member with `generated > 0` | Combined-reserve guard | No oil surplus burn (§1c-1); solar-retire advisory |

Turbine commitment (§1b) and the daily balance (§1a-0) run in every phase. A tripped or unfuelled Reactor (0 W) drops the grid back to `oil`/`steam`, so oil surplus burning resumes automatically.

- **Solar-retire advisory**: at each day close on an `oil`/`reactor` grid, one `notify()` when solar made less than `SOLAR_RETIRE_SHARE = 0.05` of the day's generation (solar Wh integrated from `solar_generator` members' `generated`). Advisory only, nothing is sold.
- Tiers configurable via `archive` key `power.shedding_tiers` (or per-grid override
  `power.shedding_tiers:<grid_anchor>`), fallback `DEFAULT_SHEDDING_TIERS` in `lib/power.py`:
  - **Tier 1 — passive background terraforming** (`heater_*`, `pressure_*`, `o2gen_*`,
    `bio_collector_*`, `bio_lab_*`, `bio_exchange_*`, `bio_luminizer_*`) plus `fuel_assembler_*` (hard-shed, §1n): shed **first**.
  - **Tier 2 — critical active production** (`smelter_*`, `fabricator_*`, `feed_maker_*`, `refiner_*`): soft-shed only.
  - **Tier 3 — Habitats** (`habitat_*`): shed last. An unpowered Habitat
    only pauses (no breeding, no rearing progress, no rearing failure).
  - Deliberately inverted from naive "protect terraforming": terraforming = background load,
    production = priority. Rationale: `DESIGN_HISTORY.md`.
  - Vehicle Charging Stations (`vehicle_charging_station*` / `charging_station_*`) are
    deliberately **never** in any tier — they also dispatch the fleet rescue drone
    (`lib/charging.py` `manage_fleet_rescues()`); losing power there would lose rescue capability
    exactly when a vehicle is most likely to be stranded (`dispatch_rescue()` returns
    `"station_offline"` if the station itself is unpowered).
- **Tier 2 (`smelter_*`/`fabricator_*`/`feed_maker_*`/`refiner_*`) soft-shed via `SOFT_SHED_PATTERNS`, never powered off** — idle Smelter/Fabricator draw already 0 W (recipe draw only while crafting), so cutting breaker saves nothing beyond not starting new work. Power Guard still adds/removes machine from `power.shedded` but never calls `set_powered()` on it; `SmelterController.is_shedded()` / `FabricatorController.is_shedded()` check list each `step()`; if shedded, drain output/eject excess, never start or top up production. A Refiner crafts on its own while a recipe is set, so `RefinerController` `clear_recipe()`s once its running craft ends and picks a recipe again after (staged tar and feedstock stay). All other patterns still hard-shed via `set_powered()`. **No cooperative auto-wake**: a Smelter the operator stopped/powered down stays that way on delivery; a running Smelter's own `step()` polls new ore each cycle.
- Shed/restore helpers shared by both strategies: `PowerGridManager.shed_tiers()` / `restore_tier()` (archive mirror `power.shedded` / `power.shedded:<anchor>` updated on change).

#### Solar night guard (`lib/power_solar.py` `SolarNightGuard`, phase `solar`)

Battery is the only store and the night is the dry spell. Skipped on a grid without battery capacity.

- **Night duration = fixed constant.** `NIGHT_DURATION_HOURS` (`SUNRISE_HOUR`/`SUNSET_HOUR`) computed at module load from the decompiled simworker's day-cycle schedule (`DAYLIGHT_FRACTIONS`; `DAY_CYCLE_DURATION_SECONDS = 600` stays in `lib/power.py` for `production_core.py`): sunrise `0.25 * 24 = 6.0h`, sunset `0.83 * 24 = 19.92h`, so `NIGHT_DURATION_HOURS = 24 - 19.92 + 6.0 = 10.08` exactly, every night.
- **Night forecast**: need = effective rate × remaining night × `NIGHT_NEED_MARGIN = 1.15`; effective rate = 60% live draw + 40% historical (`power.night_wh` / `power.night_wh:<grid_anchor>`, EMA 0.7/0.3 updated at sunrise).
- **Shedding**: tier 1 on a forecast deficit or battery `< NIGHT_EMERGENCY_FRACTION = 0.20`; every tier on a severe deficit (stored `<` half the need) or battery `< NIGHT_SEVERE_FRACTION = 0.15`.
- **Recovery**: at night once stored ≥ need × (1.10 + 0.15 per step from the last tier) and battery ≥ 0.30 + 0.10 per step; by day while generation exceeds consumption by 10 W + 5 W per step and stored ≥ 25 Wh + 25 Wh per step. The last tier (most important loads) comes back first.
- **Advisories** (once per day): at sunset when battery capacity can't carry the night baseline or batteries peaked below 90% that day (recommend Battery / Solar Generator); during the night on the first shed.

### 1a-0. Combined-Reserve Guard and Daily Balance (`lib/power.py`, phases `steam` / `oil` / `reactor`)

Counts Gas Tank steam as reserve, so it doesn't shed at night while Steam Turbines can still cover load. `elevation` ignored.

- **Reserve = battery pool + steam pool.** Battery = `grid.stored + reserve_stored` (Lightning Rods included). Steam = every Gas Tank network-wide (`steam_tanks()`: `fluid_routing.network_buildings("gas_tank")`, the shared walk cached `NETWORK_WALK_INTERVAL_TICKS`, filtered by `eligible_targets(..., "steam")`) latched to `"steam"`, or unlatched but reserved for steam in `fluid_routing.tank_assignments`; one network per fluid and one grid, so network = grid. Steam→Wh at `STEAM_WH_PER_TON = 108/90 = 1.2` (turbine rate).
- **Daily balance** (every phase). Start-of-day snapshot at each `clock.get_day()` rollover; generated/consumed (and solar) Wh integrated over `elapsed_game_hours()`. Closing day appended to `power.daily_hist:<anchor>` (last `DAILY_HISTORY_LENGTH = 7`). One `notify()` per day if battery or steam pool lost more than `DAILY_LOSS_WARN_FRACTION = 0.20` of its capacity. Only a directly preceding day is closed (longer gap = discarded, no warning). Running state in `power.daily:<anchor>`, persisted on rollover + every `DAILY_STATE_PERSIST_INTERVAL_CALLS = 30` calls.
- **Emergency guard** on combined reserve fraction (Wh): tier N sheds below `EMERGENCY_SHED_FRACTIONS[N-1]` = `(0.10, 0.05, 0.02)` (tiers past the list use the last value; `tiers_to_shed()`), everything restores at `EMERGENCY_RESTORE_FRACTION = 0.25`.
- **Adopts existing shed list**: on construction, takes ids from `power.shedded` / `power.shedded:<anchor>`; the guard releases them at the first cycle with reserve ≥ 25%, the solar night guard folds the grid's ones into its shed set.
- `ArchiveCleaner.clean_power_grid_state()` (`lib/archive_cleaner.py`) retires dead legacy keys `power.night_duration`/`power.last_night_wh`, purges `power.shedded:<anchor>` / `power.night_wh:<anchor>` / `power.daily:` / `power.daily_hist:` entries whose grid anchor is gone — skipped entirely if grid discovery returns empty. Manual-button-triggered sweep (§7); `PowerGridManager.release_all()` (§1a-1) = automatic, immediate version for a vanished grid anchor.
- Reserve maths are module functions (`steam_tanks()`, `steam_pool()`, `measure_grid()`, `reserve_totals()`, `reserve_fraction()`) so `oil_generator.py` (§1c-1) reads the exact same number as the guard.

### 1a-1. Centralized Grid Ownership (control_room_automation.py, no Master/Follower election)

`control_room_automation.py` (the Control Room Automation, §7) = single always-running process, owns grid supervision directly, one `PowerGridManager` per grid, no election.

- **`PowerGridManager.__init__(self, grid, clock=None, power=None)`** — no `machine` param.
  `grid` (initial snapshot) required, binds `self.grid_anchor` at construction — identity fixed for manager lifetime; only per-call snapshot (stored/capacity/consumed) must be fresh each call.
- Shed patterns resolve against the grid snapshot's own `.machine_ids` only (`_resolve()`).
- **`release_all()`** — called when grid's `anchor_id` no longer reported by
  `power_control.grids()` (two grids merged via new power line). Restores anything still in manager's `shedded_machines`, switches its parked turbines back on, clears per-anchor `power.shedded:<anchor>` mirror.
- **Storage-less grids skipped**: no battery and no steam tank capacity → `supervise_grid()` returns before any strategy. A solar grid also needs battery capacity for the night guard.
- **Poll pacing** (fewer steps per poll let the script react sooner; docs/BENCHMARK.md): `SolarController` polls every `SOLAR_POLL_SECONDS = 10.0` (`SOLAR_NIGHT_POLL_SECONDS = 30.0` at elevation ≤ 0) and calls `set_tilt` only when the target moved ≥ `TILT_DEADBAND_DEG = 0.5`; `FluidPumpController` `PUMP_POLL_SECONDS = 5.0`; `ThermalCapController` sleeps `CAP_WAKE_FRACTION = 0.5` of the time the fastest pressure rise seen so far (learned from successive reads) needs to reach `PRESSURE_BAND_CRITICAL`, clamped to `POLL_SECONDS = 1.0` … `CAP_MAX_POLL_SECONDS = 30.0`; before any rise is seen, 1 s at pressure ≥ `PRESSURE_BAND_MODERATE`, else `POLL_SECONDS_LOW = 3.0`. Breaker-parked while the vent is dormant and the chamber drained (dev_workflow.md §1d-2); `SteamTurbineController` `TURBINE_POLL_SECONDS = 4.0`; `OilGeneratorController` `OIL_POLL_SECONDS = 4.0`.
- **`lib/solar.py`'s `SolarController` is pure sun-tracking** — `track_sun()`/`step()`/`run()`
  only, no `PowerGridManager`, no `power`/`run_ctrl` constructor params. **Hard
  dependency**: Solar Grid brownout supervision only while control_room_automation.py running — see
  `legacy/README.md` for pre-Control-Room fallback (save without `research_custom_panels`
  has no panel scripts, so centralization doesn't help).
- **`lib/smelter.py`'s `SmelterController`** has no election either — "inventory
  manager" sweep (`storage.rebalance_inventory_to_warehouses()`) runs once, directly, from
  control_room_automation.py AUTOMATION section, same hard dependency as Solar Grid supervision.

### 1b. Steam Power Loop: Thermal Cap → (Gas Tank) → Steam Turbine

Thermal Cap (`lib/thermal_cap.py` `ThermalCapController`) and Steam Turbine
(`lib/steam_turbine.py` `SteamTurbineController`) independent scripts — each manages own throttle only, no shared coordination. Gas Tank between = passive (no script), smooths supply gaps.

- **Pipe wiring**: Gas Tank no script, so each neighbor declares own side of
  `FluidPort`. Thermal Cap has no `.outpost` property, so all three controllers use shared
  `lib/fluid_routing.py` `discover_network_buildings(type_ids, resolve=True)` (Cap/Pump use
  default resolved objects; Turbine passes `resolve=False` for plain ids), walks every
  outpost (`outpost_network.outposts()` → `outpost.buildings(type_id)`) network-wide. All three
  pass own `fluid_id` (`"steam"` here) so tank operator-reserved for different fluid via
  `fluid_routing.tank_assignments` (§4) dropped from candidacy — see that key's entry
  (one outpost can hold several separate pipe networks of the same medium).
  - **`connect()`'s `"ok"` status does not mean physically reachable** — a remote pairing needs a
    *completed* Gas Pipe route, which `connect()` never checks. The live signal of a broken route
    is `is_stalled()` (steam/throttle ready, nothing transferred) — all three controllers
    blacklist a target that reports this. Blacklist entries expire **individually** —
    `lib/fluid_routing.py`'s `PerEntryBlacklist` maps `id -> tick blacklisted` (real
    `clock.tick()`), each with its own `RESCAN_INTERVAL_TICKS` expiry window (300 Cap-ticks / 150
    Turbine-ticks, passed per-controller).
  - **Cap → Gas Tank(s)** (`ensure_output_connection()`): `steam_out` holds one destination at a
    time; stays on the current tank while its `fill_pct()` is below
    `GAS_TANK_REBALANCE_FILL_FRACTION=0.98` **and** it isn't stalled, otherwise switches to
    whichever other known (non-blacklisted) tank is currently least full. A single stalled tick is
    enough to blacklist, except for the first `CONNECTION_GRACE_TICKS=2` ticks right after a
    (re)connect (flow can take a tick to register).
  - **Turbine → source** (`ensure_input_connection()`): shared consumer-side
    `fluid_routing.FluidInputRouter` (see **Input vs output routers** below). Candidates: every
    known Gas Tank, then every known Thermal Cap directly — per
    `docs/guide/infrastructure_and_pipes.md`, additional consumers may connect their own
    `steam_in` straight to a Cap, independent of the Cap's own `steam_out`. Each group ranked
    own-outpost-first (`fluid_routing.rank_own_outpost_first()`); a reachable cross-outpost
    candidate still succeeds, just later. `is_stalled()` on a Turbine is ambiguous alone (equally
    true when the feeding vent is just dormant), so a starvation drop needs
    `STALL_STREAK_BLACKLIST_THRESHOLD=5` *consecutive* stalled checks; a broken link state drops
    immediately. `NEUTRAL_GRACE_STEPS=5`.
  - **Input vs output routers** (`lib/fluid_routing.py`): two classes, one per port direction,
    sharing `PerEntryBlacklist`, `TickedDiscoveryCache` and `discover_network_buildings()`.
    `FluidOutputRouter` (Cap/Pump/Liquifier) rebalances among targets by `fill_pct()`. With
    `local_outpost_id` (Refiner, Liquifier, Steam Condenser; not Caps/Pumps/Taps) own-outpost targets
    rank first, another outpost's tank that feeds a cross-outpost route (`feeds_remote_route()`: a
    `"ready"` peer on its `liquid_out`/`gas_out`) ranks last, and a healthy cross-outpost target is
    left once an own-outpost one is below `rebalance_fill_fraction - LOCAL_RETURN_MARGIN` (0.10);
    why: §1c-5.
    `FluidInputRouter` (Turbine, Fabricator, Biomass Mixer) ignores fill and only asks whether fluid
    arrives. Per `ensure()` call:
    0. Built with `reserve_fluid="water"` and `water_reserve_holds()` (Reactor water reservation,
       §1c-4) → disconnects the port, returns `"reserved"`.
    1. Any peer in `HEALTHY_CONNECTION_STATES` (`"local"`/`"ready"`, declared by either side), and
       starvation streak below threshold → healthy.
    2. Own declared link in `BROKEN_CONNECTION_STATES` → drop now. Starved ≥
       `stall_streak_threshold` → drop (`None` = never). `"neutral"`/unknown gets
       `neutral_grace_steps`, then dropped only if another candidate exists.
    3. Slow path: connect first non-blacklisted candidate; a link whose state is already broken
       right after `connect()` "ok" is blacklisted and the next candidate tried in the same pass.
       A source already blacklisted but still declared on the port isn't re-dropped every call.
    4. **Pipe conflict** (link state `"conflict"`: the only pipe component reaching both ends
       already carries another fluid, so all flow on it stops, other routes included).
       `connect()` has no status for this (outcomes are only `ok`/`not_found`/`incompatible`), so
       it is read from `FluidConnection.state`. The newcomer yields: a router whose port had no
       healthy link since its own `connect()` calls `fluid_routing.yield_pipe_conflict()` —
       `port.disconnect()`, blacklist the source for `CONFLICT_BLACKLIST_TICKS=3000` (~5 min),
       warn log + `notify()`, entry in `fluid_routing.pipe_conflicts` (§4). A link that was
       healthy first waits `ESTABLISHED_CONFLICT_GRACE_STEPS=5` checks, then yields the same way.
       `FluidOutputRouter` checks right after `connect()` and on the stall path while not yet
       healthy (established output links keep the plain stall blacklist). Only conflicts notify;
       `"unreachable"` stays a quiet debug-level blacklist (separate pipe networks are normal).
       The AUTOMATION card lists live conflicts (`active_pipe_conflicts()`).
  - **Candidate helpers** (each caller's `discover` callable): recipe-fluid ports (Fabricator,
    Caster, Reactor, Mk III water, Sprinkler, Plant Terraformer) use
    `production.discover_fluid_sources(fluid_key, own_outpost_id)` — `FLUID_SOURCE_TYPE_IDS`
    filtered by `fluid_building_is_viable()`, own outpost first. Tiered candidate lists (steam
    tanks then Caps, oil tanks then Oil Pumps, Habitat/Refiner tanks) use
    `fluid_routing.discover_ranked(tiers, own_outpost_id)`, tiers of `(type_ids, fluid_id)`;
    `STEAM_SOURCE_TIERS` is the steam_in list.
  - **Event logging**: callers run their router through `fluid_routing.ensure_input_logged()` /
    `ensure_output_logged()`, which build the callbacks and print the standard lines on the
    caller's console: drop / blacklist / connect notice warn, new connection info, healthy trace,
    every-candidate-blacklisted debug (remaining ticks per entry at trace), `not_found` debug with
    the caller's hint. Habitat and Refiner call the routers bare (their blocker/status covers it).
    `fluid_routing.port_starved()` is the `is_starved` signal for a port on a machine without
    `is_stalled()` (flow 0 with room left).
  - **Discovery cost**: the network walk is skipped entirely while a connection is healthy — Cap/
    Pump check one `fill_pct()` on the already-connected id; input routers return on a healthy
    peer. When discovery does run, `TickedDiscoveryCache` holds results for
    `DISCOVERY_CACHE_INTERVAL_TICKS=100` simulation ticks (every router), invalidated on every
    blacklist/drop, so a newly assigned tank is seen within ~10 s. For `FluidOutputRouter` a
    refresh only re-reads eligibility (one `.fluid()` per tank, one `tank_assignments` read) over
    the network walk (`outposts()` × `buildings(type_id)` × `get_component()`), which
    `fluid_routing.network_buildings()` reuses for `NETWORK_WALK_INTERVAL_TICKS=600` ticks (~60 s)
    across every output router in the script with the same type ids. A newly built tank is seen
    within that window; a cached tank whose `.fluid()`/`fill_pct()` raises or a `connect()`
    answering `"not_found"` drops the walk at once. Rebalance reads each candidate's `fill_pct()`
    once (least-full first, ties in discovery order). A full current target (`>= rebalance_fill_fraction`) is
    left only for a candidate emptier by more than `OUTPUT_REBALANCE_MARGIN=0.02`; otherwise the router
    stays connected and returns `"full"` (no switch, no log). A stall while the current target is full
    is not a route failure and never blacklists it; a stall on a non-full target still does. A
    `"connected"` event with `rebalance=True` (usable target left for an emptier one) is logged at
    debug by the callers, a first/replacement connection at info. The fast path reads `fill_pct()` before
    eligibility, so a full current tank costs no eligibility read. `PerEntryBlacklist` drops an
    entry once it has expired.
- **Thermal Cap** — keeps `pressure()` off `1.0` overpressure ceiling (hit = *entire* chamber blown to atmosphere — `.is_overpressured()`). Proportional release-valve (`steam_out`,
  via `set_throttle()`) bands on `pressure()`: `≥0.90→1.0`, `≥0.60→0.6`, `≥0.30→0.3`, else
  `THROTTLE_TRICKLE=0.3` (release below 30% pressure, into Gas Tank/Turbines, not lost). Relief valve (`set_relief()`, dumps to atmosphere) engages only once
  release valve wide open (`throttle==1.0`) and pressure still climbs past
  `PRESSURE_RELIEF_THRESHOLD=0.95`.
- **Turbine commitment** (`lib/turbine_commit.py`, `TurbineCommitment` owned by each `PowerGridManager`, `step()` every `supervise_grid()` before `_guard()`): runs just enough Steam Turbines at full output and switches the rest off at the breaker (`script.parked` entries `{"kind": "steam_turbine", "mode": "turbine", "since", "grid"}`; `ScriptParking` never touches mode `"turbine"`, the automation card counts them).
  - **Managed**: the grid's `steam_turbine` members that are powered or parked here; one switched off by anything else stays off and out of the count (a hand-switched-on parked one drops its entry).
  - **Target** (`turbine_needed()`): `ceil((consumed - other generation + top-up) / TURBINE_FULL_W=108)` + spare, capped at the managed count. Other generation = `grid.generated` minus the running turbines' output, each `max(power_output(), throttle() × 108 W)` (0 if stalled): `power_output()` reports the previous power tick, so it reads 0 right after a restart or a new throttle. Top-up below `TURBINE_TOPUP_BELOW_FRACTION=0.98` battery: missing Wh / `TOPUP_HOURS=2`. Spare = `ceil(TURBINE_SPARE_FRACTION=0.10` × managed), at least `TURBINE_MIN_SPARE=1`. **All-on latch** (`hysteresis.HysteresisLatch`): battery below `TURBINE_EMERGENCY_BATTERY_FRACTION=0.50` → every managed turbine, until the battery is back at `TURBINE_EMERGENCY_RELEASE_FRACTION=0.70` (ahead of the Oil Generators' 30% last-resort line). **Steam surplus latch**: grid steam pool (`power.measure_grid()`, passed by `supervise_grid()`) `≥ TURBINE_SURPLUS_START_FRACTION=0.98` until `< TURBINE_SURPLUS_STOP_FRACTION=0.90` → other generation is not subtracted, the turbines cover the whole consumption (+ top-up) so Caps don't vent while solar/oil carry the grid; starts above the Condenser's 0.95 gate so the Condenser takes surplus first. No steam tank → off. Both latches live in the control room's memory (restart → both off).
  - **Which run** (`rank_turbines()`): per turbine, not per grid (a split steam network): able to deliver (own `steam_in` ≥ `TURBINE_CAPABLE_BUFFER_FRACTION=0.15`, not stalled) first, then own buffer fill, then the fill of the source `steam_in` is connected to (Gas Tank `fill_pct()`, Thermal Cap `pressure()`), then already running. The top `target` run; a dry running one is swapped for the best parked one. Fewer able turbines than the target → every managed turbine stays up.
  - **Heartbeat**: each pass writes `{grid anchor: tick}` to `power.turbine_commit` (`COMMIT_HEARTBEAT_KEY`); a turbine whose grid entry is younger than `steam_turbine.COMMIT_FRESH_TICKS=1200` skips its own daytime easing (steps 4-5 below) and runs 1.0 with a healthy buffer, since surplus is handled by parking.
  - **Churn guard**: a turbine woken here is not parked again for `TURBINE_MIN_ON_TICKS=600` unless it cannot deliver. Grid gone (`release_all()`) → its parked turbines are switched back on.
- **Steam Turbine** — throttle from `choose_throttle()`, priority order:
  1. Buffer fraction (`steam_in.level()/capacity()`, this turbine's own 100 t buffer) `<
     STEAM_BUFFER_LOW_FRACTION=0.15` → `THROTTLE_LOW_BUFFER=0.15` regardless of day/night/demand.
  2. `< STEAM_BUFFER_HEALTHY_FRACTION=0.40` → `THROTTLE_MARGINAL_BUFFER=0.5` (buffer rebuilding).
  3. Healthy buffer + night (`clock.get_elevation() <= 0`) → `1.0`. Healthy buffer + grid under turbine commitment (fresh `power.turbine_commit` entry, above) → `1.0`.
  4. Healthy buffer + day + grid battery `≥ BATTERY_FULL_FRACTION=0.98` of capacity AND
     `generated >= consumed` → `THROTTLE_DEMAND_MET=0.3` (eased).
  5. Eased and battery still `≥ BATTERY_EASE_RESUME_FRACTION=0.90` → stay at `0.3`: at 0.3 generation
     no longer covers consumption, so step 4 alone flipped every turbine back to 1.0 on the next poll
     (1.0 ↔ 0.3 every ~40 ticks). Night or a thin buffer clears the eased state.
  6. Otherwise → `1.0`.
  Reads grid state same as `lib/power.py`'s `PowerGridManager`
  (`power_control.grid(self.name)` → `.stored`/`.capacity`/`.generated`/`.consumed`), but no
  shedding itself — that's control_room_automation.py AUTOMATION section's job (§1a-1).

### 1c. Fluid Pump (water/oil): Liquid Tank Routing (`lib/fluid_pump.py` `FluidPumpController`)

One controller for Water Pump and Oil Pump — same API except port name (`water_out`/`oil_out`) and Oil Pump's `well_active()`. Entrypoints: `FluidPumpController(self, "water")` (`4_controlpanel/power/water_pump.py`), `FluidPumpController(self, "oil")` (`4_controlpanel/power/oil_pump.py`). `lib/water_pump.py` = shim (`WaterPumpController(pump)`) for save slots still importing the old name.

Shares §1b's Thermal Cap → Gas Tank connection/load-balancing/blacklist machinery exactly — both
build `lib/fluid_routing.py` `FluidOutputRouter` (Pump's own `LIQUID_TANK_TYPE_IDS`,
`LIQUID_TANK_REBALANCE_FILL_FRACTION`, `CONNECTION_GRACE_TICKS`, `RESCAN_INTERVAL_TICKS`,
`DISCOVERY_CACHE_INTERVAL_TICKS` constants feed same shared class) — but simpler: pump
has **no internal buffer to overpressure** (no `pressure()`/`relief()`, pure pass-through), so
`step()` calls `ensure_output_connection()` and unconditionally requests `set_throttle(1.0)`
every cycle — delivery self-limits to what connected tank accepts.

- **Two target building types, not one**: `LIQUID_TANK_TYPE_IDS = ("liquid_tank",
  "bulk_liquid_reservoir")` — `discover_network_buildings()` takes iterable of type_ids (or
  single string), walks each outpost per type, dedupes by id.
- **Water and oil never share a tank**: router passes `fluid_id`, so a tank latched to the other fluid is skipped and an empty tank qualifies only with a matching `fluid_routing.tank_assignments` entry (§4). **First oil tank must be assigned `"oil"` by the operator.**
- **Water overflow** (`lib/water_sink.py` `WaterAwareWasteSinkController`, entrypoint `4_controlpanel/factory/garbage_disposal.py`): a stalled Water Pump makes no salt, but water is scarce, so draining is a last resort. Start: every water-eligible tank at the outpost (`tank_is_eligible_target()`, so an empty tank assigned to water counts as room) `>= WATER_SINK_HIGH_FILL = 0.90` AND some Water Pump on the network reports `is_stalled()`. Drains only the tank that was fullest at the start (locked) in `"liquid"` mode, down to `WATER_SINK_LOW_FILL = 0.80`. Otherwise it idles (`WasteSinkController.idle()`: `set_enabled(False)`, staged input `eject()`ed to local storage; no item destruction, §1h-1). Several processors at one outpost: only the lowest id drains water, the others idle. Same-outpost tanks only.
- **Oil well dormancy**: `well_active()` False → throttle `0` (saves 5 W), routing skipped. Water Pump has no `well_active()` → never dormant.
- Output port (same shape as Thermal Cap's `steam_out`) holds one destination at a
  time. `is_stalled()` same semantics as Thermal Cap's, so same
  blacklist-and-reselect reaction applies unchanged.

### 1c-1. Oil Generator: Last-Resort Power and Surplus Base Load (`lib/oil_generator.py` `OilGeneratorController`)

+700 W at throttle 1 for 8 t/h oil; burning emits CO2 and oil feeds Fabricator recipes, so it runs as last resort, or as base load while the oil tanks are full.

- **Surplus base load**: network-wide oil tank fill (`fluid_routing.fluid_reserve_tons("oil")`: summed `level()` / `capacity()` of oil-eligible Liquid/Large Liquid Tanks, re-read every `OIL_RESERVE_REFRESH_TICKS = 100`) `≥ OIL_SURPLUS_START_FRACTION = 0.90` turns it on, below `OIL_SURPLUS_STOP_FRACTION = 0.70` (or no oil tank) off. While on, the generators burn the wells' gross inflow: each re-read takes a sample `max(0, Δlevel / Δh + Oil Generators' burn)` (burn = Σ oil member `generated` / 700 W × 8 t/h; `TICKS_PER_GAME_HOUR = 250`; a capacity change skips the sample), smoothed by EMA `OIL_INFLOW_EMA_ALPHA = 0.2`. Being net of every other oil consumer, it burns only oil nothing else takes. `burn = max(0, inflow + (level − OIL_SURPLUS_TARGET_FRACTION (0.80) × capacity) / OIL_SURPLUS_CORRECT_HOURS (24))` t/h, converted at 8 t/h = 700 W, capped at `consumed + OIL_RECHARGE_W (if battery < OIL_SURPLUS_TOPUP_BELOW = 0.98)`, shared over `count`, `throttle = min(1, W / 700)` (no minimum). Turbine commitment (§1a) parks the turbines that output replaces. The last-resort throttle below runs alongside; the higher of the two is set.
- **No surplus on a Reactor grid**: while `power.reactor_carried(grid)` (phase `reactor`, §1a) the surplus latch is forced off and the surplus throttle is 0, so the idle generator parks; `ScriptParking` skips the "oil surplus" wake and stay-ready for generators on those grids (`_reactor_grids()`). The last resort and the low-reserve wake still apply.
- **Parking** (`ParkRequester`, dev_workflow.md §1d-2): idle = neither mode burning AND deficit without oil `≤ 0`. A standing deficit refills the gap between the stop and start lines within a few game hours, so the generators stay awake for it.

- **Start**: `min(battery fraction, combined reserve)` (§1a-0 `reserve_fraction()`, battery + steam) `< OIL_START_RESERVE_FRACTION = 0.30` AND deficit without oil `> 0`. Battery fraction matters because the deficit is measured after turbine output: banked steam can't cover it (turbines are rate-limited), only the battery buffers it. One `notify()` at start. No storage at all → burns only while deficit.
- **Throttle**: `deficit = consumed − (generated − Σ oil_generator member.generated)`, split evenly over all Oil Generators in `grid.members`; `throttle = clamp((max(0, share) × OIL_DEFICIT_HEADROOM (1.1) + OIL_RECHARGE_W (300) / count) / OIL_GENERATOR_RATED_W (700), OIL_MIN_THROTTLE (0.1), 1.0)`; recharge term only when the grid has a battery.
- **Stop**: battery fraction AND combined reserve both `≥ OIL_STOP_RESERVE_FRACTION = 0.70` (above the guard's 0.25 restore line). Grid unreadable → throttle 0 (fail safe).
- **Oil input**: `FluidInputRouter` (steam-turbine constants: stall streak 5, rescan 150 ticks, discovery cache 100 ticks, neutral grace 5); candidates = oil-eligible Liquid/Large Liquid Tanks (own outpost first), then Oil Pumps. Starved = throttle > 0, `oil_in.level() == 0`, `oil_consumption() == 0`.
- No archive state: game resets throttle to 0 on script stop; restart re-evaluates within one step.

### 1c-2. Steam Condenser: Steam → Water (`lib/steam_condenser.py` `SteamCondenserController`)

1 t steam → 1 t water, 250 t/h and 150 W at throttle 1. Draw follows throttle even when blocked, so throttle is 1.0 or 0.0.

- **Steam guard**: grid steam pool (`power.measure_grid()`, §1a-0) `< STEAM_POOL_STOP_FRACTION = 0.90` → idle; resumes at `>= STEAM_POOL_START_FRACTION = 0.95`. Steam is the main power source and the pool must carry the turbines through long vent dormancy, so the Condenser only takes the surplus of a nearly full pool (active vent phase). No measurable steam tank on the grid → guard open.
- **Water guard**: fill of the least-full reachable water tank (router's discovered targets minus blacklisted) `>= WATER_TANK_STOP_FRACTION = 0.85` → idle, i.e. every reachable tank is full; resumes once any reachable tank is `< WATER_TANK_START_FRACTION = 0.50` (wide hysteresis: at 250 t/h the Condenser refills fast). Least-full, not pooled: a full tank nobody draws from must not hold the Condenser idle while the tank the consumers drain runs dry. The router moves `water_out` to the least-full tank at `WATER_TANK_SWITCH_FRACTION` (= tank stop line, not the pump's 0.98). `water_out` routing pauses while this guard is closed.
- **Sink guard**: a Waste Processor (`garbage_disposal`) at the `water_out` tank's outpost is enabled, in `"liquid"` mode, with `liquid_in` on that tank → idle, so condensed water never feeds a drain. Read live from the processor (`is_enabled()` is False once the sink script stops), not from the `waste_sink.status` archive entry.
- **Local**: `steam_in` empty or `water_out` buffer full → idle.
- **steam_in**: `FluidInputRouter` with the Steam Turbine's candidates and constants (§1b); starved = `steam_in.level() == 0` while the steam guard is open.
- **water_out**: `FluidOutputRouter` with the Fluid Pump's targets and constants (§1c, `fluid_id="water"`) except the switch line above; stall signal = `water_out` buffer full.
- No archive state: game resets throttle to 0 on script stop; guards re-evaluate from live readings on the first step.

### 1c-3. Mk III Terraforming Fluid Feed (`lib/terraforming.py` `Mk3FluidFeed`)

`HeatController`/`PressureController`/`OxygenController` each run one `Mk3FluidFeed` per `step()`. Mk III Heat Generator takes `steam_in`, Mk III Pressure/Oxygen Generator take `water_in`. A starved Mk III runs as Mk II (`is_degraded()`), it never stops.

**Pressure Generator pacing** (`PressureController.next_poll_seconds()`): the gauge rises a fixed amount per tick, measured from two reads (`gauge_per_tick`). The script sleeps `PRESSURE_WAKE_FRACTION = 0.7` of the predicted time to its next target (the window's low edge while this sweep is unsynced; the wrap at 100 once synced or once the window has passed), clamped to `PRESSURE_MIN_POLL_S = 0.1` … `PRESSURE_MAX_POLL_S = 5.0`, and polls every `PRESSURE_MIN_POLL_S` near or inside the window and while the speed is unknown.

- Routes only while `tier() == 3` (Mk IV burns Fuel Rods; below Mk III the port does nothing). At most every `FLUID_CHECK_INTERVAL_TICKS = 20` ticks.
- **steam_in**: `FluidInputRouter`, steam Gas Tanks then Thermal Caps, own outpost first (Steam Turbine candidates, §1b). **water_in**: `FluidInputRouter` over `production.FLUID_SOURCE_TYPE_IDS["water_in"]` with `fluid_building_is_viable()`, own outpost first. Router constants = Plant Terraformer's water router (stall streak 5, rescan 150, discovery cache 100, neutral grace 5). Starved = `flow_rate() == 0` with room left.
- **Steam guard (heater only)**: grid steam pool (`power.measure_grid()`, §1a-0) `< STEAM_POOL_STOP_FRACTION = 0.50` → `steam_in.disconnect()`, heater runs as Mk II; reconnects at `>= STEAM_POOL_START_FRACTION = 0.70`. Pool read every `STEAM_GUARD_INTERVAL_TICKS = 3000` (5 game min; a heater draws at most 12 t/h). Keeps the turbines' dormancy buffer. No measurable steam tank, or tier-4 `power.py` (no `measure_grid()`) → guard open. Water has no guard.
- `is_degraded()` transitions logged at info level (warn when starved).
- **Unbound port** (`UnboundPortRestart`, also used by `Mk4RodFeed` for `input`): the game binds an upgrade port on `self` only at script start (simworker: `${fluid}_in` is set when `data["<port>_capacity"]` exists at bind time), so a pack applied under a running script leaves `steam_in`/`water_in` missing. The feed warns once per run and files a `script.restart_requests` entry (`lib/script_restart.py`, reason `mk3_port_unbound` / `mk4_input_unbound`); `control_room_automation.py` stops and starts the script on its parking pass, at most `MAX_RESTARTS = 2` times per reason. A later request after that is marked `gave_up` and named on the AUTOMATION card. Once the port is there the feed drops its own entry (same reason only), so the next fault starts from zero.
- No other archive state.
- **Mk IV rod magazine** (`Mk4RodFeed`, same three controllers): while `tier() >= 4`, every `MK4_CHECK_INTERVAL_TICKS = 600` ticks, tops `input` up to `MK4_MAGAZINE_TARGET = 1` Fuel Rod from the Lead Casks at the generator's own outpost (`lead_cask.take_from_casks()`; hot cargo never crosses outposts). A Mk IV burns 1 rod per 240 game h (simworker `0.1 / 24` per h) and stops without one. No rods: one warn until a load succeeds. The Fuel Assembler counts each Mk IV in its rod target (§1n).

### 1c-4. Reactor: Measured-Gain Heat Control (`lib/reactor.py` `ReactorController`)

Up to 5,000 W from Fuel Rods and cooling water. Thin entrypoint `4_controlpanel/nuclear/reactor.py`. Fuel use follows commanded heat (1 rod per 72 game h at heat 1.0), output follows core temperature, so the most energy per rod comes from holding the core just under 900 °C.

- **Game model** (simworker reactor step): steady temperature = heat × gain, gain = `TEMP_SCALE_C = 1200` × hidden condition in [0.7, 1.25] (`GAIN_MIN_C = 840` … `GAIN_MAX_C = 1500`), redrawn every `CONDITION_PERIOD_GH = 12` game h at whole multiples of `clock.elapsed_game_hours()`. First-order lag at `LAG_PER_GH = 0.6`. Output: 0 below 300 °C, 50% at 600, 100% at exactly 900, back to 0 across 900-950; 950 overheats (cools to 600 and restarts by itself). Overheated, no rod or no water: no fuel used.
- **Gain**: two running readings with the same heat at least `MIN_SAMPLE_GH = 0.03` apart give the temperature the core is heading to, `S = (T1 − T0·e^(−0.6·dt)) / (1 − e^(−0.6·dt))` (`steady_state()`); gain sample = S / heat (heat ≥ `MIN_HEAT_FOR_GAIN = 0.05`), clamped to the physical range, blended `GAIN_BLEND = 0.5`; a sample more than `GAIN_JUMP_FRACTION = 0.10` off replaces the gain. Forgotten at each 12 h boundary, on overheat and on a trip.
- **Heat**: `TARGET_C = 900` / gain (100% output, at the red band start), clamped 0-1 (gain 840 → heat 1.0, 840 °C, 90% output). Unknown gain, or within `BOUNDARY_LEAD_GH = 0.15` before a boundary: `SAFE_HEAT = TARGET_C / GAIN_MAX_C` (≈ 0.587), which cannot pass the target under any condition. Changes under `HEAT_DEADBAND = 0.005` are not sent.
- **Trip guard**: temperature ≥ `TRIP_C = 910` → `SAFE_HEAT`, gain forgotten. Catches a bad estimate or a missed boundary: the worst jump (840 → 1500 at heat 1.0) needs ~0.19 game h from 840 to 910 °C.
- **Poll**: every `POLL_GH = 0.04` game h while settling or near a boundary, `STEADY_POLL_GH = 0.1` once holding within `STEADY_BAND_C = 15` of the target; `sleep(poll × clock.real_seconds_per_hour())` (fallback `FALLBACK_SECONDS_PER_GH = 25`).
- **Fuel Rods**: keeps `ROD_STAGE = 1` rod in `input` (capacity 3) from this outpost's Lead Casks (`lead_cask.take_from_casks()`), every `ROD_CHECK_INTERVAL_TICKS = 600` ticks and at once on `"no_fuel"`. The Fuel Assembler counts staged rods in its target (§1n). No rods: one warn until a load succeeds.
- **Fuel alert** (archive `lead_cask.REACTOR_FUEL_KEY = "reactor.fuel"`, §4): every rod check computes spare rods (staged + this outpost's casks) and game hours left = (`fuel_level()` + spare) × `ROD_LIFE_GH = 72` / heat (unknown heat: `SAFE_HEAT`). Level `"warn"` with no spare rod, `"error"` on `"no_fuel"` with no spare rod either (a new Reactor reads `"no_fuel"` until it takes its first rod). Each level start logs a warn/error line and a sticky `notify()` (`duration_seconds=0`); a clear logs "Fuel supply restored". Entry written on a level change and at least every `ROD_CHECK_INTERVAL_TICKS`; the Status panel lists it under ALERTS (`lead_cask.reactor_fuel_alerts()`, errors first, entries older than `REACTOR_FUEL_FRESH_TICKS = 1800` left out).
- **Cooling water** (0.5-1 t/h, 3 t buffer): `FluidInputRouter` over `production.FLUID_SOURCE_TYPE_IDS["water_in"]` with `fluid_building_is_viable()`, own outpost first (stall streak 5, rescan 150, discovery cache 100, neutral grace 5). Starved = `status() == "no_coolant"`.
- **Water reservation** (archive `fluid_routing.WATER_RESERVE_KEY = "fluid_routing.water_reserve"`): the lowest-id Reactor on the network (reactor list rediscovered every `REACTOR_DISCOVERY_TICKS = 600`) writes `{"hold", "level_t", "floor_t", "tick", "by"}` every `WATER_RESERVE_PUBLISH_TICKS = 300` ticks. Floor = `WATER_RESERVE_HOURS = 48` × `COOLANT_MAX_T_PER_GH = 1.0` t/h × Reactors, capped at `WATER_RESERVE_MAX_FRACTION = 0.5` of pooled capacity; pool = `fluid_routing.fluid_reserve_tons("water")` (water-eligible Liquid/Large Liquid Tanks network-wide). Holds below the floor, releases at `WATER_RESERVE_RELEASE_FACTOR = 1.25` × floor; no water tank → never holds. Hold start warns and `notify()`s.
  - **Consumers** (`fluid_routing.water_reserve_holds()`, archive read once per tick, entry older than `WATER_RESERVE_FRESH_TICKS = 1200` never holds, so a stopped Reactor script releases everything): `FluidInputRouter(reserve_fluid="water")` in Mk III Pressure/Oxygen `water_in` (`Mk3FluidFeed`), Fabricator `water_in`, Bio Caster `water_in`, Plant Terraformer, Sprinkler (`field_provider`), Habitat water medium; Harvester `ensure_water()` skips `refill_water()`. Each disconnects while held and reconnects through its router after.
  - A starved Reactor does not overheat (simworker: no heating, no fuel use, cools at 60 °C/h); the reservation protects its output.
- **Status changes** logged at info (running) or warn; overheat also `notify()`s.
- Not parked and not in any shedding tier: heat returns to 0 when the script stops. No control state in archive; the gain is re-measured within a few polls after a restart.
- Simulated closed loop (`tests/test_reactor.py`, per-tick simworker physics): from cold ~6 game h to the target, then ~4.8 kW mean across alternating 0.72/1.25 conditions, peak 878 °C.

### 1c-5. Fluid Delivery Rules (game mechanic, simworker `$ge` flow tick)

How the game moves fluid along a `connect()`ed port pair. Planners and routers depend on it.

- **Same outpost** (both machines' `locationId` is the same built outpost): moved directly source → sink, capped by sink headroom (`tickDirectConnections`). No pipe needed; such pairs never appear as pipe-network routes.
- **Script sources** (`thermal_cap`, `water_pump`, `oil_pump`, `exotic_gas_cap`, `exotic_spring_tap`): delivered per route to the route's sink, capped by the sink's headroom and the network's throughput (`routeSourceToTarget`), whatever the sink holds. A tank filled by pumps over a pipe keeps filling while it feeds other machines over the same network.
- **Every other cross-outpost pair** (Refiner, tanks, any building feeding through pipes): pooled per fluid network (`redistributePerFluidNetworks`). Providers = source endpoints holding > 0 t. Consumers = sink endpoints with headroom **that are not providers**. Consequences:
  - A tank that feeds machines over a pipe network (it is a route source there) and holds any stock is not a consumer on that network: cross-outpost Refiners (or tanks) cannot fill it. Their output goes only to the other sinks; with none taking (full inlet, unpowered machine = 0 headroom), the network stalls and producer outputs back up.
  - Fix in the layout: give each producer a tank of its fluid **in its own outpost** (direct delivery), and pipe that tank onward. `FluidOutputRouter(local_outpost_id=...)` moves the producer's port to such a tank, and without one prefers a remote tank that feeds nothing over the network (§1b input vs output routers).
- Unpowered non-tank machines have 0 headroom and supply 0 (`Kb`/`Gb`); tanks are read regardless of power.
