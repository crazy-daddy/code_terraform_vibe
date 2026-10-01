# Power & Fluids (§1a–§1c-3)

Part of [`AI_CHEATSHEET.md`](../AI_CHEATSHEET.md). Formula summary table: hub §1.

### 1a. Brownout Load-Shedding Detail (`lib/power.py` `PowerGridManager`)

- Tiers configurable via `archive` key `power.shedding_tiers` (or per-grid override
  `power.shedding_tiers:<grid_anchor>`), fallback `DEFAULT_SHEDDING_TIERS` in `lib/power.py`:
  - **Tier 1 — passive background terraforming** (`heater_*`, `pressure_*`, `o2gen_*`,
    `bio_collector_*`, `bio_lab_*`, `bio_exchange_*`, `bio_luminizer_*`): shed **first**.
  - **Tier 2 — critical active production** (`smelter_*`, `fabricator_*`, `feed_maker_*`): shed only under
    severe deficit.
  - **Tier 3 — Habitats** (`habitat_*`, tier-5 copy only, §1a-0): shed last. An unpowered Habitat
    only pauses (no breeding, no rearing progress, no rearing failure). The tier-4 copy keeps two tiers
    (Habitats come long after tier 5 replaces it).
  - Deliberately inverted from naive "protect terraforming": terraforming = background load,
    production = priority. Rationale: `DESIGN_HISTORY.md`.
  - Vehicle Charging Stations (`vehicle_charging_station*` / `charging_station_*`) are
    deliberately **never** in any tier — they also dispatch the fleet rescue drone
    (`lib/charging.py` `manage_fleet_rescues()`); losing power there would lose rescue capability
    exactly when a vehicle is most likely to be stranded (`dispatch_rescue()` returns
    `"station_offline"` if the station itself is unpowered).
- Shed thresholds = **inline literals in `manage_night_loads()`** (not named module constants — check function directly when retuning): Tier 1 sheds on deficit or `battery_pct < 0.20`; Tier 2 also sheds on severe deficit (`stored_wh < wh_needed * 0.50`) or `battery_pct < 0.15`.
- Recovery = mirror image, in both `manage_night_loads()` (battery stabilizing) and `manage_day_recovery()` (solar surplus at dawn): Tier 2 (production/logistics) restored first, needs small surplus-watt / stored-Wh margin; Tier 1 (terraforming) restored last, needs larger margin.
- **Tier 2 (`smelter_*`/`fabricator_*`/`feed_maker_*`) soft-shed via `SOFT_SHED_PATTERNS`, never powered off** — idle Smelter/Fabricator draw already 0 W (recipe draw only while crafting), so cutting breaker saves nothing beyond not starting new work. Power Guard still adds/removes machine from `power.shedded` (signal + recovery timing unchanged) but never calls `set_powered()` on it; `SmelterController.is_shedded()` / `FabricatorController.is_shedded()` check list each `step()`; if shedded, drain output/eject excess, never start or top up production. All other Tier 1 patterns (`heater_*`, `pressure_*`, `bio_*`, etc.) still hard-shed via `set_powered()`. **No cooperative auto-wake**: a Smelter the operator stopped/powered down stays that way on delivery; a running Smelter's own `step()` polls new ore each cycle.
- **Night duration = fixed constant.** `NIGHT_DURATION_HOURS` (`SUNRISE_HOUR`/`SUNSET_HOUR`) computed once at module load from decompiled simworker's exact day-cycle schedule (`DAY_CYCLE_DURATION_SECONDS = 600`, `DAYLIGHT_FRACTIONS`): sunrise `0.25 * 24 = 6.0h`, sunset `0.83 * 24 = 19.92h`, so `NIGHT_DURATION_HOURS = 24 - 19.92 +
  6.0 = 10.08` exactly, every night. `power.night_wh`/`power.night_wh:<grid_anchor>` (historical overnight Wh, blended with live draw when sizing `manage_night_loads()`'s shed threshold) is calibrated live.
- `ArchiveCleaner.clean_power_grid_state()` (`lib/archive_cleaner.py`) retires dead legacy keys `power.night_duration`/`power.last_night_wh`, purges `power.shedded:<anchor>` / `power.night_wh:<anchor>` entries whose grid anchor gone — skipped entirely if grid discovery returns empty. Manual-button-triggered sweep (§7); `PowerGridManager.release_all()` (§1a-1) = automatic, immediate version of same cleanup for whatever vanished grid anchor still had shed.

### 1a-0. Simplified Power Guard (`5_steampower/lib/power.py`, overrides §1a from tier 5 up)

Same import surface (`PowerGridManager.supervise_grid(grid, elevation)` / `release_all()`, `DAY_CYCLE_DURATION_SECONDS`), so control_room_automation.py drives it unchanged. No day/night logic — `elevation` ignored. Counts Gas Tank steam as reserve, so it doesn't shed at night while Steam Turbines can still cover load.

- **Reserve = battery pool + steam pool.** Battery = `grid.stored + reserve_stored` (Lightning Rods included). Steam = every Gas Tank in `grid.members` (outpost walk fallback, throttled to every `TANK_FALLBACK_SCAN_INTERVAL_CALLS = 60` calls) latched to `"steam"`, or unlatched but reserved for steam in `fluid_routing.tank_assignments`. Steam→Wh at `STEAM_WH_PER_TON = 108/90 = 1.2` (turbine rate).
- **Daily balance.** Start-of-day snapshot at each `clock.get_day()` rollover; generated/consumed Wh integrated over `elapsed_game_hours()`. Closing day appended to `power.daily_hist:<anchor>` (last `DAILY_HISTORY_LENGTH = 7`). One `notify()` per day if battery or steam pool lost more than `DAILY_LOSS_WARN_FRACTION = 0.20` of its capacity. Only a directly preceding day is closed (longer gap = discarded, no warning). Running state in `power.daily:<anchor>`, persisted on rollover + every `DAILY_STATE_PERSIST_INTERVAL_CALLS = 30` calls.
- **Emergency guard** on combined reserve fraction (Wh): tier N sheds below `EMERGENCY_SHED_FRACTIONS[N-1]` = `(0.10, 0.05, 0.02)` (tiers past the list use the last value; `tiers_to_shed()`), everything restores at `EMERGENCY_RESTORE_FRACTION = 0.25`. Tiers 1–2 and soft-shed rules as §1a, plus tier 3 `habitat_*` (hard-shed, last). Archive overrides as §1a.
- **Adopts existing shed list**: on construction, takes ids from `power.shedded` / `power.shedded:<anchor>` and releases them at the first cycle with reserve ≥ 25%.
- `ArchiveCleaner.clean_power_grid_state()` also purges orphaned `power.daily:` / `power.daily_hist:` keys.
- Reserve maths are module functions (`grid_steam_tank_ids()`, `steam_pool()`, `measure_grid()`, `reserve_totals()`, `reserve_fraction()`) so `oil_generator.py` (§1c-1) reads the exact same number as the guard.

### 1a-1. Centralized Grid Ownership (control_room_automation.py, no Master/Follower election)

`control_room_automation.py` (the Control Room Automation, §7) = single always-running process, owns grid supervision directly, one `PowerGridManager` per grid, no election.

- **`PowerGridManager.__init__(self, grid, clock=None, power=None)`** — no `machine` param.
  `grid` (initial snapshot) required, binds `self.grid_anchor` at construction — identity fixed for manager lifetime; only per-call snapshot (stored/capacity/consumed) must be fresh each call.
- **`resolve_pattern_machines()`** fallback chain: grid snapshot's own `.machine_ids`/`.members`
  (primary) → numbered-guess `get_component(f"{prefix}{i}")` last resort.
- **`release_all()`** — called when grid's `anchor_id` no longer reported by
  `power_control.grids()` (two grids merged via new power line). Restores anything still in manager's `shedded_machines` (guarded same as `manage_day_recovery()`), clears per-anchor `power.shedded:<anchor>` mirror.
- **Battery-less grids skipped**: `if capacity_wh <= 0: return` near top of
  `supervise_grid()` (avoids divide by zero on `battery_pct`). No strategy for battery-less grids yet.
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
    `FluidOutputRouter` (Cap/Pump/Liquifier) rebalances among targets by `fill_pct()`.
    `FluidInputRouter` (Turbine, Fabricator, Biomass Mixer) ignores fill and only asks whether fluid
    arrives. Per `ensure()` call:
    1. Any peer in `HEALTHY_CONNECTION_STATES` (`"local"`/`"ready"`, declared by either side), and
       starvation streak below threshold → healthy.
    2. Own declared link in `BROKEN_CONNECTION_STATES` → drop now. Starved ≥
       `stall_streak_threshold` → drop (`None` = never). `"neutral"`/unknown gets
       `neutral_grace_steps`, then dropped only if another candidate exists.
    3. Slow path: connect first non-blacklisted candidate; a link whose state is already broken
       right after `connect()` "ok" is blacklisted and the next candidate tried in the same pass.
       A source already blacklisted but still declared on the port isn't re-dropped every call.
  - **Discovery cost**: the network walk is skipped entirely while a connection is healthy — Cap/
    Pump check one `fill_pct()` on the already-connected id; input routers return on a healthy
    peer. When discovery does run, `TickedDiscoveryCache` holds results for
    `DISCOVERY_CACHE_INTERVAL_TICKS=100` simulation ticks (every router), invalidated on every
    blacklist/drop, so a newly built/assigned tank is seen within ~10 s.
- **Thermal Cap** — keeps `pressure()` off `1.0` overpressure ceiling (hit = *entire* chamber blown to atmosphere — `.is_overpressured()`). Proportional release-valve (`steam_out`,
  via `set_throttle()`) bands on `pressure()`: `≥0.90→1.0`, `≥0.60→0.6`, `≥0.30→0.3`, else
  `THROTTLE_TRICKLE=0.3` (release below 30% pressure, into Gas Tank/Turbines, not lost). Relief valve (`set_relief()`, dumps to atmosphere) engages only once
  release valve wide open (`throttle==1.0`) and pressure still climbs past
  `PRESSURE_RELIEF_THRESHOLD=0.95`.
- **Turbine commitment** (`lib/turbine_commit.py`, tier 5, `TurbineCommitment` owned by each `PowerGridManager`, `step()` every `supervise_grid()` before `_guard()`): runs just enough Steam Turbines at full output and switches the rest off at the breaker (`script.parked` entries `{"kind": "steam_turbine", "mode": "turbine", "since", "grid"}`; `ScriptParking` never touches mode `"turbine"`, the automation card counts them).
  - **Managed**: the grid's `steam_turbine` members that are powered or parked here; one switched off by anything else stays off and out of the count (a hand-switched-on parked one drops its entry).
  - **Target** (`turbine_needed()`): `ceil((consumed - other generation + top-up) / TURBINE_FULL_W=108)` + spare, capped at the managed count. Other generation = `grid.generated` minus the running turbines' output, each `max(power_output(), throttle() × 108 W)` (0 if stalled): `power_output()` reports the previous power tick, so it reads 0 right after a restart or a new throttle. Top-up below `TURBINE_TOPUP_BELOW_FRACTION=0.98` battery: missing Wh / `TOPUP_HOURS=2`. Spare = `ceil(TURBINE_SPARE_FRACTION=0.10` × managed), at least `TURBINE_MIN_SPARE=1`. Battery below `TURBINE_EMERGENCY_BATTERY_FRACTION=0.50` → every managed turbine (ahead of the Oil Generators' 15% line).
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

One controller for Water Pump and Oil Pump — same API except port name (`water_out`/`oil_out`) and Oil Pump's `well_active()`. Entrypoints: `FluidPumpController(self, "water")` (`4_controlpanel/power/water_pump.py`), `FluidPumpController(self, "oil")` (`5_steampower/power/oil_pump.py`). `lib/water_pump.py` = shim (`WaterPumpController(pump)`) for save slots still importing the old name.

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
- **Water overflow** (`lib/water_sink.py` `WaterAwareWasteSinkController`, entrypoint `5_steampower/factory/garbage_disposal.py`): a stalled Water Pump makes no salt, but water is scarce, so draining is a last resort. Start: every water-eligible tank at the outpost (`tank_is_eligible_target()`, so an empty tank assigned to water counts as room) `>= WATER_SINK_HIGH_FILL = 0.90` AND some Water Pump on the network reports `is_stalled()`. Drains only the tank that was fullest at the start (locked) in `"liquid"` mode, down to `WATER_SINK_LOW_FILL = 0.80`. Otherwise it idles (`WasteSinkController.idle()`: `set_enabled(False)`, staged input `eject()`ed to local storage; no item destruction, §1h-1). Several processors at one outpost: only the lowest id drains water, the others idle. Same-outpost tanks only.
- **Oil well dormancy**: `well_active()` False → throttle `0` (saves 5 W), routing skipped. Water Pump has no `well_active()` → never dormant.
- Output port (same shape as Thermal Cap's `steam_out`) holds one destination at a
  time. `is_stalled()` same semantics as Thermal Cap's, so same
  blacklist-and-reselect reaction applies unchanged.

### 1c-1. Oil Generator: Last-Resort Power (`5_steampower/lib/oil_generator.py` `OilGeneratorController`)

+700 W at throttle 1 for 8 t/h oil; burning emits CO2 and oil feeds Fabricator recipes, so it only runs as last resort. No oil floor.

- **Start**: `min(battery fraction, combined reserve)` (§1a-0 `reserve_fraction()`, battery + steam) `< OIL_START_RESERVE_FRACTION = 0.15` AND deficit without oil `> 0`. Battery fraction matters because the deficit is measured after turbine output: banked steam can't cover it (turbines are rate-limited), only the battery buffers it. One `notify()` at start. No storage at all → burns only while deficit.
- **Throttle**: `deficit = consumed − (generated − Σ oil_generator member.generated)`, split evenly over all Oil Generators in `grid.members`; `throttle = clamp((max(0, share) × OIL_DEFICIT_HEADROOM (1.1) + OIL_RECHARGE_W (300) / count) / OIL_GENERATOR_RATED_W (700), OIL_MIN_THROTTLE (0.1), 1.0)`; recharge term only when the grid has a battery.
- **Stop**: battery fraction AND combined reserve both `≥ OIL_STOP_RESERVE_FRACTION = 0.30` (above the guard's 0.25 restore line). Grid unreadable → throttle 0 (fail safe).
- **Oil input**: `FluidInputRouter` (steam-turbine constants: stall streak 5, rescan 150 ticks, discovery cache 100 ticks, neutral grace 5); candidates = oil-eligible Liquid/Large Liquid Tanks (own outpost first), then Oil Pumps. Starved = throttle > 0, `oil_in.level() == 0`, `oil_consumption() == 0`.
- No archive state: game resets throttle to 0 on script stop; restart re-evaluates within one step.

### 1c-2. Steam Condenser: Steam → Water (`5_steampower/lib/steam_condenser.py` `SteamCondenserController`)

1 t steam → 1 t water, 250 t/h and 150 W at throttle 1. Draw follows throttle even when blocked, so throttle is 1.0 or 0.0.

- **Steam guard**: grid steam pool (`power.measure_grid()` over `grid_steam_tank_ids()`, §1a-0) `< STEAM_POOL_STOP_FRACTION = 0.85` → idle; resumes at `>= STEAM_POOL_START_FRACTION = 0.95`. Steam is the main power source and the pool must carry the turbines through long vent dormancy, so the Condenser only takes the surplus of a nearly full pool (active vent phase). No measurable steam tank on the grid → guard open.
- **Water guard**: pooled fill (Σ level / Σ capacity) of the reachable water tanks (router's discovered targets minus blacklisted) `>= WATER_POOL_STOP_FRACTION = 0.85` → idle; resumes at `< WATER_POOL_START_FRACTION = 0.50` (wide hysteresis: at 250 t/h the Condenser refills fast). The router moves `water_out` to the least-full tank at `WATER_TANK_SWITCH_FRACTION` (= pool stop line, not the pump's 0.98), so every reachable tank fills before the Condenser idles. `water_out` routing pauses while this guard is closed.
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
- **Steam guard (heater only)**: grid steam pool (`power.measure_grid()`, §1a-0) `< STEAM_POOL_STOP_FRACTION = 0.50` → `steam_in.disconnect()`, heater runs as Mk II; reconnects at `>= STEAM_POOL_START_FRACTION = 0.70`. Keeps the turbines' dormancy buffer. No measurable steam tank, or tier-4 `power.py` (no `measure_grid()`) → guard open. Water has no guard.
- `is_degraded()` transitions logged at info level (warn when starved).
- No archive state.
