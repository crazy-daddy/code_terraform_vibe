# Code: Terraform — AI Agent Quick Reference Cheat Sheet

Dense ref: physics, formulas, component specs, bus channels, data conventions.
**Single source of truth for tunable numbers and definitions** for every agent on project. Change tunable constant in code (safety margins, tiers, thresholds, stale-tick counts, budgets, etc.) → update here same change. Other docs (`CLAUDE.md`, `TODO.md`) point at constant/module name, not restate value — one place to keep current.

*Why* behind design (bug postmortems, rejected approaches, design history) → **[`DESIGN_HISTORY.md`](DESIGN_HISTORY.md)**. This file reference-only.

---

## 🗺️ Progression Walkthroughs & Speedrun Guides

High-level workflows, progression roadmaps, automation orchestration → dedicated walkthrough guides:

- **[`manual_walkthrough.md`](../early_game_runner/manual_walkthrough.md)**: **Manual Progression Roadmap (0 $\rightarrow$ 1,000,000 TP Victory)**
  - Manual progression playbook: First Contact onboarding, Earth Clearance contract solvers (+3,750 cr & +22,500 cr), research prereqs, critical bottleneck matrix, chronological phases from Phase 0 (Cold Boot) to Phase 7 (Deep Biome, Nuclear Reactor Recovery & Endgame Victory).
- **[`auto_walkthrough.md`](../early_game_runner/auto_walkthrough.md)**: **Autonomous Architecture & Early Speedrunner (0 $\rightarrow$ 150,000 TP)**
  - Hands-off automation blueprint: Master Automation Architecture, revised 25-slot Nocturna Base speedrun, `solar_1.py` master building-buyer (auto buy/deploy/sell cycles), `early_game_runner/early_game.py` speedrunner daemon & machine watcher, Earth Clearance contract solvers, 150k TP mid-game migration protocol to `lib/`.
- *(Top-level nav hub: [`walkthrough.md`](../early_game_runner/walkthrough.md))*

---

## 🧱 0. Shared Library Module Map (`lib/`)

> Physical location: `scripts/<tier>/lib/<module>.py` (tiered, see §9) — not flat top-level `lib/`. `devtools/scripts_sync.py` resolves right copy per module per active tier, mirrors into save folder's `lib/`. Module names below logical; nearly all currently under `scripts/4_controlpanel/lib/` — tier codebase actually written/tested against (see §9).

| Concern | Module(s) |
| :--- | :--- |
| Terraforming (heat/pressure/O2) | `terraforming.py` (`HeatController`, `PressureController`, `OxygenController`) |
| Power grid & brownout | `power.py` (`PowerGridManager` — generic, solar/oil/reactor/turbine grids, owned centrally by headless automation panel, one instance per grid, no election — see §1a-1); `solar.py` (`SolarController` — pure sun tracking, no own grid supervision anymore) |
| Vehicles (Rover/Pioneer base) | `vehicle.py` (`VehicleController`, composes mixins below) |
| &nbsp;&nbsp;↳ driving / stall recovery | `vehicle_navigation.py` |
| &nbsp;&nbsp;↳ battery accounting / trip budgeting / charging-station discovery | `vehicle_energy.py` |
| &nbsp;&nbsp;↳ fleet-wide target claims & hardware blacklist | `vehicle_claims.py` |
| &nbsp;&nbsp;↳ cargo offload into Inventory / Warehouse | `vehicle_cargo.py` |
| &nbsp;&nbsp;↳ sonar survey loop (POI discovery) | `vehicle_survey.py` |
| &nbsp;&nbsp;↳ mineral-site discovery & drill execution | `vehicle_mining.py` — shared Rover + Pioneer; see §2b |
| &nbsp;&nbsp;↳ in-flight mining yield reservation (non-exclusive, overmining guard) | `mining_reservations.py` — see §2b |
| &nbsp;&nbsp;↳ shared live telemetry dict `fleet.status` (vehicles + drones) | `fleet_status.py` — see §4 |
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
| &nbsp;&nbsp;↳ miner role loop (biosite extraction) | `drone_mining.py` |
| &nbsp;&nbsp;↳ floating hauler role loop (drills → Depots, no home) | `drone_hauler.py` — see §2j |
| &nbsp;&nbsp;↳ fleet-upgrade handshake, new-chassis fitting, in-place module upgrades (+ shared `fleet.upgrade` state helpers) | `drone_upgrade.py` — see §2k |
| Fleet hardware upgrade coordinator (Depot + drone chassis swaps), run by headless `panel_4.py` | `fleet_upgrade.py` — see §2k |
| Warehouse pair → Large Warehouse swap (buy, deploy, greedy drain, undeploy, sell), run by headless `panel_6.py` | `warehouse_upgrade.py` — see §2k-1 |
| Drone Service Station (charging/refuelling/rescue) | `drone_service.py` — see §2h |
| Drone Depot (cargo logistics endpoint) | `drone_depot.py` — see §2h; drains freight to local storage, buffers life forms in a local Warehouse (one stack per form) |
| Pull logistics (outpost item requests, in-flight pickups, source retention) | `logistics_requests.py` — see §2i; reverse hauler lives in `vehicle_cargo.py` `run_pull_loop()` |
| Seed Maker (fair recipe sweep, stage A) | `seed_maker.py` — see §1i (tier `6_seeds`) |
| Seed Maker on-demand seed production (stage B, once all 15 recipes are known) | `seed_supply.py` — see §1k (tier `6_seeds`; `bio/seed_maker.py` dispatches on `len(recipes())`) |
| Field layout (species rules, starter block, full-field layout in automator chunks, rarity-weighted expansion; pure logic) | `field_layout.py` — see §1k (tier `8_planting`) |
| Plant Terraformer (feed Forage/Water/Salt/Fertilizer/Accelerant, batch run policy) | `plant_terraformer.py` — see §1k (tier `8_planting`) |
| Planting Harvester (plant, tend, harvest the layout) | `field_keeper.py` composes `harvester_heat.py` (`HarvesterHeatMixin`: heat-cheapest routes, just-in-time rests, live heat calibration; overrides `move_to()`/`cool_down()`) + `harvester_paving.py` (`HarvesterPavingMixin`: items dropped on a path joining the plant patches) + `harvester_planting.py` (`HarvesterPlantingMixin`: layout, seed demand, plant, harvest) + `harvester_care.py` (`HarvesterCareMixin`: light/water/salt, salt request) + `harvester_machines.py` (`HarvesterMachinesMixin`: field-machine kits) + `harvesting.py` `HarvesterController` (movement, heat, loose-item sweep) — see §1k (tier `8_planting`) |
| Field machines (kit orders/pre-orders + deploy on reserved cells; Grow Lamp / Sprinkler / Dispenser controller; Crop Automator job controller) | `harvester_machines.py` (`HarvesterMachinesMixin`, mixed into `field_keeper.py`) + `field_provider.py` (`FieldProviderController`, thin `harvesting/grow_lamp.py`/`sprinkler.py`/`dispenser.py`) + `crop_automator.py` (`CropAutomatorController`, thin `harvesting/crop_automator.py`) — see §1k (tier `8_planting`) |
| Water Pump byproduct salt as pull-hauler source | `pump_salt.py` — see §2i (tier 4 lib, imported by `vehicle_cargo.py`) |
| Field Mining Drill telemetry (fill, time-to-full, stall warnings, pickup advert) | `mining_drill.py` — see §1j (tier `7_miningdrills`) |
| Field Mining Drills as pull-hauler sources (recorded positions, connect/take) | `drill_sites.py` — see §2i (lives in tier 4 lib, since the hauler imports it at every tier) |
| Fabrication | `fabricator.py` |
| Thermal Cap (steam capture, anti-overpressure) | `thermal_cap.py` |
| Steam Turbine (steam-to-grid power) | `steam_turbine.py` |
| Water Pump / Oil Pump (route well output to network Liquid Tanks) | `fluid_pump.py` `FluidPumpController(pump, fluid_id)` — see §1c, simpler cousin of `thermal_cap.py` (no overpressure/relief); `water_pump.py` = compat shim for old save slots |
| Oil Generator (last-resort power) | `oil_generator.py` — see §1c-1 (tier 5+) |
| Essence Liquifier (Depot → sample feed, essence → Liquid Tank) | `essence_liquifier.py` — see §1h (tier 5+) |
| Biomass Mixer (keep all five essence inputs sourced) | `biomass_mixer.py` — see §1h (tier 5+) |
| Biomass Mixer duty-cycle gate (breaker pause until all expected essences refilled) | `biomass_mixer_gate.py` — see §1h (lives in tier 5 lib, deployed from `2_libunlock` on like every new-only module; driven by the single `panel_4.py`, idles without Mixers) |
| Shared network-wide fluid-target discovery/blacklist/reconnect | `fluid_routing.py` — `FluidOutputRouter` (`thermal_cap.py`/`fluid_pump.py`/`essence_liquifier.py`), `FluidInputRouter` (`steam_turbine.py`/`fabricator.py`/`biomass_mixer.py`/`oil_generator.py`); see §1b |
| Storage management (Warehouse-aware sourcing/unloading, Inventory rebalancing) | `storage.py` — see §2c |
| Outpost ore-assignment & stock-target scaffolding (multi-outpost mining) | `outpost_mining.py` — see §2d |
| Data Archive persistence layer | `archive.py` |
| Game version safety gate (halt on build change until operator confirms) | `version_guard.py` — see §4's `system.good_version`/`system.version_confirmed` entries and §7 |
| Wildcard pattern matching helpers | `patterns.py` |
| Per-script tick-cost profiling | `profiling.py` — see §1d |
| Structured, indented console logging (`debug()`-level decision tracing) | `tree_console.py` (`TreeConsole`) — see §0a |

Root executable scripts (`solar_1.py`, `rover_1.py`, `panel_4.py`, etc.) stay thin entrypoints: import + run controller from `lib/`. No own copies of tier lists, thresholds, budgeting formulas.

**No real stdlib — only short allowlist of "executable built-in modules"** (`docs/guide/programming_language_reference.md`'s "Imports & Libraries" section authoritative; re-check before any import, don't assume ordinary Python). **Only** executable modules: `random` (`randint`/`rand`/`random()`, also bare global helpers), `re` (regex — `re.escape` unavailable), `functools` (`reduce`, `total_ordering`), `dataclasses` (`dataclass`, `field`). Nothing else. None are real system libs — small in-game reimplementation exposing just those names, not CPython modules. `math`, `sys`, `os`, `json`, `time`, `itertools`, `collections` (concrete module), etc. **don't** exist at runtime. `typing`, `types`, `collections.abc`, `user_stubs` exist ONLY for editor/Pyright annotations — erased at runtime (`typing.TYPE_CHECKING` always `False` in-game). **Need stdlib thing (ceiling division, etc.) → write plain arithmetic by hand, don't import** — see `lib/production.py`'s `_ceil()` pattern instead of `math.ceil()`.

**Import depth limit**: interpreter caps nested import-resolution stack at `maxImportDepth = 256` (`interpreter.maxImportDepth`, confirmed from decompiled simworker — see `internals/` [gitignored, not authoritative game docs]), raises `RecursionError` / `error.import_depth` if exceeded. Current `lib/` chain (entrypoint → `vehicle.py` → mixins, max 2-3 levels) nowhere close — see this error → look for real import cycle.

### 0a. Structured Console Logging (`lib/tree_console.py` `TreeConsole`)

Console output: three detail levels, all same tree format:

- **Overview (info, always visible)** — major blocks + outcomes, beautified, skimmable, no opt-in needed.
- **Reasoning trail (debug, opt-in, always written)** — the *why*: which branch decision took, candidates considered/rejected, computed threshold/estimate values. Hidden from normal ALL view (`docs/components/console.md`'s `console.debug()`), so no spam for non-opted players, but cheap enough to leave on in most `lib/` files — reading with debug on should tell whole run story without in-game breakpoint/watch debugger (`§8`).
- **Trace (opt-in per module, gated before reaching `console`)** — truly high-volume noise: method entry/exit, per-item loop detail. `TreeConsole.trace()` true no-op (no `console` call, no disk write) unless `TreeConsole(module=...)`'s module listed `"verbose"` in `console.log_levels` archive dict (`{module_name: "normal"|"verbose"}`, default `"normal"`). Level read once at construction — restart script after editing archive key via Data Archive Notebook, no per-tick re-check. `module` must be passed explicitly (sandbox has no `inspect`/frame introspection); convention: `lib/` filename without extension (e.g. `"power"`, `"vehicle_energy"`). This is what gets sprinkled liberally across files per workflow rule on debug logging, without `debug()`'s always-on cost. When fires, still emits at **debug** level (not custom `"trace"` badge) — `docs/components/console.md`'s `console.print()` only treats `info`/`warn`/`error`/`debug` as filter-feeding; other strings = colored badge in normal ALL view, defeating opt-in gating.

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
- **Convention going forward**: one `TreeConsole` per controller instance, in `__init__` (or once before `run_*_loop()`'s `while True:` for bare function, not inside), stored as `self.log`/`log` — never re-construct per call/tick, since `__init__` reads `console.log_levels` archive dict. Name it `log` (not `tree` — tree-drawing just formatting, `log` names purpose).
- `color(c)` / `level(lvl)` set one-shot override (CSS color / `info`\|`warn`\|`error`\|`debug`\| custom) consumed by *next* `print`/`start`/`end`/`debug`/`trace` call only, then reset to instance default.
- Every line still goes through `console.print(..., timestamp=True)` — keeps game time-of-day prefix, works with Console channel/level filters.
- Reserve plain `warn`/`error` for real status changes player should notice without debug output; `debug()`/`trace()` purely detail, never attention-needing.

---

## ⚡ 1. Core Terraforming & Physics Formulas

| System | Component | Key Formula / Setpoint | Limits & Constraints |
| :--- | :--- | :--- | :--- |
| **Solar Tracking** | `solar_generator` | `tilt = round(sun_elevation)` | 0° (flat) to 90° (vertical). Night output = 0 W. Peak = 50 W. |
| **Oxygen Generation** | `oxygen_generator` | `intake = atmosphere.get_co2() / 10.0` | Power: -8 W. Dump waste when `50 <= waste < 60` (clean dump, 0 penalty). Stalls at 100 waste. |
| **Heat Calibration** | `heat_generator` | `power = 1..10 W` (sweep / cache by weather) | Power: -10 W max. Re-eval optimal power on day/weather change. |
| **Pressure Sync** | `pressure_generator` | Sync pulse with resonance window peak | Power: -10 W max. 100% efficiency on exact resonance window hit. |
| **Power Grid & Brownout** | `power_control`, `battery` | Battery = 500 Wh (300 cr). Safe floor: 15-20% | Configurable shedding tiers (`power.shedding_tiers`) — see §1a for full tier/threshold breakdown. |

### 1a. Brownout Load-Shedding Detail (`lib/power.py` `PowerGridManager`)

- Tiers configurable via `archive` key `power.shedding_tiers` (or per-grid override
  `power.shedding_tiers:<grid_anchor>`), fallback `DEFAULT_SHEDDING_TIERS` in `lib/power.py`:
  - **Tier 1 — passive background terraforming** (`heater_*`, `pressure_*`, `o2gen_*`,
    `bio_collector_*`, `bio_lab_*`, `bio_exchange_*`, `bio_luminizer_*`): shed **first**.
  - **Tier 2 — critical active production** (`smelter_*`, `fabricator_*`): shed only under
    severe deficit.
  - Deliberately inverted from naive "protect terraforming" instinct — terraforming treated
    as background/passive load, production the higher priority to keep alive. See `DESIGN_HISTORY.md`
    for why.
  - Vehicle Charging Stations (`vehicle_charging_station*` / `charging_station_*`) are
    deliberately **never** in any tier — they also dispatch the fleet rescue drone
    (`lib/charging.py` `manage_fleet_rescues()`); losing power there would lose rescue capability
    exactly when a vehicle is most likely to be stranded (`dispatch_rescue()` returns
    `"station_offline"` if the station itself is unpowered).
- Shed thresholds = **inline literals in `manage_night_loads()`** (not named module constants — check function directly when retuning): Tier 1 sheds on deficit or `battery_pct < 0.20`; Tier 2 also sheds on severe deficit (`stored_wh < wh_needed * 0.50`) or `battery_pct < 0.15`.
- Recovery = mirror image, in both `manage_night_loads()` (battery stabilizing) and `manage_day_recovery()` (solar surplus at dawn): Tier 2 (production/logistics) restored first, needs small surplus-watt / stored-Wh margin; Tier 1 (terraforming) restored last, needs larger margin.
- **Tier 2 (`smelter_*`/`fabricator_*`) soft-shed via `SOFT_SHED_PATTERNS`, never powered off** — idle Smelter/Fabricator draw already 0 W (recipe draw only while crafting), so cutting breaker saves nothing beyond not starting new work. Power Guard still adds/removes machine from `power.shedded` (signal + recovery timing unchanged) but never calls `set_powered()` on it; `SmelterController.is_shedded()` / `FabricatorController.is_shedded()` check list each `step()`; if shedded, drain output/eject excess, never start or top up production. All other Tier 1 patterns (`heater_*`, `pressure_*`, `bio_*`, etc.) still hard-shed via `set_powered()`. **No cooperative auto-wake, on purpose** — operator stopped/powered down Smelter themselves → nothing overrides on delivery; Smelter's own `step()` already polls new ore on normal cycle whenever running.
- **Night duration fixed constant, not calibrated.** `NIGHT_DURATION_HOURS` (`SUNRISE_HOUR`/`SUNSET_HOUR`) computed once at module load from decompiled simworker's exact day-cycle schedule (`DAY_CYCLE_DURATION_SECONDS = 600`, `DAYLIGHT_FRACTIONS`): sunrise `0.25 * 24 = 6.0h`, sunset `0.83 * 24 = 19.92h`, so `NIGHT_DURATION_HOURS = 24 - 19.92 +
  6.0 = 10.08` exactly, every night. `power.night_wh`/`power.night_wh:<grid_anchor>` (historical overnight Wh, blended with live draw when sizing `manage_night_loads()`'s shed threshold) unrelated, still calibrated live — only *duration* exactly knowable ahead.
- `ArchiveCleaner.clean_power_grid_state()` (`lib/archive_cleaner.py`) retires dead legacy keys `power.night_duration`/`power.last_night_wh`, purges `power.shedded:<anchor>` / `power.night_wh:<anchor>` entries whose grid anchor gone — skipped entirely if grid discovery returns empty. Manual-button-triggered sweep (§7); `PowerGridManager.release_all()` (§1a-1) = automatic, immediate version of same cleanup for whatever vanished grid anchor still had shed.

### 1a-0. Simplified Power Guard (`5_steampower/lib/power.py`, overrides §1a from tier 5 up)

Same import surface (`PowerGridManager.supervise_grid(grid, elevation)` / `release_all()`, `DAY_CYCLE_DURATION_SECONDS`), so the headless automation panel drives it unchanged. No day/night logic — `elevation` ignored. Built because §1a sheds every night on battery alone while Gas Tanks still hold steam for the Steam Turbines.

- **Reserve = battery pool + steam pool.** Battery = `grid.stored + reserve_stored` (Lightning Rods included). Steam = every Gas Tank in `grid.members` (outpost walk fallback, throttled to every `TANK_FALLBACK_SCAN_INTERVAL_CALLS = 60` calls) latched to `"steam"`, or unlatched but reserved for steam in `fluid_routing.tank_assignments`. Steam→Wh at `STEAM_WH_PER_TON = 108/90 = 1.2` (turbine rate).
- **Daily balance.** Start-of-day snapshot at each `clock.get_day()` rollover; generated/consumed Wh integrated over `elapsed_game_hours()`. Closing day appended to `power.daily_hist:<anchor>` (last `DAILY_HISTORY_LENGTH = 7`). One `notify()` per day if battery or steam pool lost more than `DAILY_LOSS_WARN_FRACTION = 0.20` of its capacity. Only a directly preceding day is closed (longer gap = discarded, no warning). Running state in `power.daily:<anchor>`, persisted on rollover + every `DAILY_STATE_PERSIST_INTERVAL_CALLS = 30` calls.
- **Emergency guard** on combined reserve fraction (Wh): Tier 1 sheds below `EMERGENCY_SHED_TIER1_FRACTION = 0.10`, all tiers below `EMERGENCY_SHED_ALL_FRACTION = 0.05`, everything restores at `EMERGENCY_RESTORE_FRACTION = 0.25`. Same tiers/soft-shed rules/archive overrides as §1a.
- **Takeover from §1a**: on construction, adopts ids from `power.shedded` / `power.shedded:<anchor>` and releases them at the first cycle with reserve ≥ 25%, so nothing the old manager shed overnight stays stranded.
- `ArchiveCleaner.clean_power_grid_state()` also purges orphaned `power.daily:` / `power.daily_hist:` keys.
- Reserve maths are module functions (`grid_steam_tank_ids()`, `steam_pool()`, `measure_grid()`, `reserve_totals()`, `reserve_fraction()`) so `oil_generator.py` (§1c-1) reads the exact same number as the guard.

### 1a-1. Centralized Grid Ownership (headless automation panel, no Master/Follower election)

Headless automation panel AUTOMATION section (§7 — `panel_4.py` in source tree) = single always-running process, owns grid supervision directly, one `PowerGridManager` per grid, no election.

- **`PowerGridManager.__init__(self, grid, clock=None, power=None)`** — no `machine` param.
  `grid` (initial snapshot) required, binds `self.grid_anchor` at construction — identity fixed for manager lifetime; only per-call snapshot (stored/capacity/consumed) must be fresh each call.
- **`resolve_pattern_machines()`** fallback chain: grid snapshot's own `.machine_ids`/`.members`
  (primary) → numbered-guess `get_component(f"{prefix}{i}")` last resort.
- **`release_all()`** — called when grid's `anchor_id` no longer reported by
  `power_control.grids()` (two grids merged via new power line). Restores anything still in manager's `shedded_machines` (guarded same as `manage_day_recovery()`), clears per-anchor `power.shedded:<anchor>` mirror, so merge doesn't strand shed machine.
- **Battery-less grids skipped, not mismanaged**: `if capacity_wh <= 0: return` near top of
  `supervise_grid()`, before day/night or shedding logic — Steam-Turbine-only grid with no Battery would else divide by zero computing `battery_pct`. Generation-vs-consumption strategy for battery-less grids = follow-up, not implemented.
- **`lib/solar.py`'s `SolarController` is pure sun-tracking** — `track_sun()`/`step()`/`run()`
  only, no `PowerGridManager`, no master role, no `power`/`run_ctrl` constructor params. **Hard
  dependency**: Solar Grid brownout supervision only while headless automation panel running — see
  `legacy/README.md` for pre-Control-Room fallback (save without `research_custom_panels`
  has no panel scripts, so centralization doesn't help).
- **`lib/smelter.py`'s `SmelterController`** also no Leader election — "inventory
  manager" sweep (`storage.rebalance_inventory_to_warehouses()`) runs once, directly, from
  headless automation panel AUTOMATION section, same hard dependency as Solar Grid supervision.

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
  for why building-type-only discovery insufficient once outpost has multiple distinct pipe
  networks of same medium.
  - **`connect()`'s `"ok"` status does not mean physically reachable** — a remote pairing needs a
    *completed* Gas Pipe route, which `connect()` never checks. The live signal of a broken route
    is `is_stalled()` (steam/throttle ready, nothing transferred) — all three controllers
    blacklist a target that reports this. Blacklist entries expire **individually** —
    `lib/fluid_routing.py`'s `PerEntryBlacklist` maps `id -> tick blacklisted` (real
    `clock.tick()`), each with its own `RESCAN_INTERVAL_TICKS` expiry window (300 Cap-ticks / 150
    Turbine-ticks, passed per-controller), not one shared "clear everything" timer — see
    `DESIGN_HISTORY.md` for the ping-pong bug this fixed.
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
    blacklist/drop. Tick-based, not slow-path-call-counted, so a newly built/assigned tank is seen
    within ~10 s instead of after 20 rebalance/stall events.
- **Thermal Cap** — keeps `pressure()` off `1.0` overpressure ceiling (hit = *entire* chamber blown to atmosphere — `.is_overpressured()`). Proportional release-valve (`steam_out`,
  via `set_throttle()`) bands on `pressure()`: `≥0.90→1.0`, `≥0.60→0.6`, `≥0.30→0.3`, else
  `THROTTLE_TRICKLE=0.1`. Relief valve (`set_relief()`, dumps to atmosphere) engages only once
  release valve wide open (`throttle==1.0`) and pressure still climbs past
  `PRESSURE_RELIEF_THRESHOLD=0.95`.
- **Steam Turbine** — throttle from `choose_throttle()`, priority order:
  1. Buffer fraction (`steam_in.level()/capacity()`, this turbine's own 100 t buffer) `<
     STEAM_BUFFER_LOW_FRACTION=0.15` → `THROTTLE_LOW_BUFFER=0.15` regardless of day/night/demand.
  2. `< STEAM_BUFFER_HEALTHY_FRACTION=0.40` → `THROTTLE_MARGINAL_BUFFER=0.5` (buffer rebuilding).
  3. Healthy buffer + night (`clock.get_elevation() <= 0`) → `1.0`.
  4. Healthy buffer + day + grid battery `≥ BATTERY_FULL_FRACTION=0.98` of capacity AND
     `generated >= consumed` → `THROTTLE_DEMAND_MET=0.3`.
  5. Otherwise → `1.0`.
  Reads grid state same as `lib/power.py`'s `PowerGridManager`
  (`power_control.grid(self.name)` → `.stored`/`.capacity`/`.generated`/`.consumed`), but no
  shedding itself — that's headless automation panel AUTOMATION section's job (§1a-1).

### 1c. Fluid Pump (water/oil): Liquid Tank Routing (`lib/fluid_pump.py` `FluidPumpController`)

One controller for Water Pump and Oil Pump — same API except port name (`water_out`/`oil_out`) and Oil Pump's `well_active()`. Entrypoints: `FluidPumpController(self, "water")` (`4_controlpanel/power/water_pump.py`), `FluidPumpController(self, "oil")` (`5_steampower/power/oil_pump.py`). `lib/water_pump.py` = shim (`WaterPumpController(pump)`) for save slots filled before the rename.

Shares §1b's Thermal Cap → Gas Tank connection/load-balancing/blacklist machinery exactly — both
build `lib/fluid_routing.py` `FluidOutputRouter` (Pump's own `LIQUID_TANK_TYPE_IDS`,
`LIQUID_TANK_REBALANCE_FILL_FRACTION`, `CONNECTION_GRACE_TICKS`, `RESCAN_INTERVAL_TICKS`,
`DISCOVERY_CACHE_INTERVAL_TICKS` constants feed same shared class) — but simpler: pump
has **no internal buffer to overpressure** (no `pressure()`/`relief()`, pure pass-through), so
`step()` calls `ensure_output_connection()` and unconditionally requests `set_throttle(1.0)`
every cycle — delivery self-limits to what connected tank accepts.

- **Two target building types, not one**: `LIQUID_TANK_TYPE_IDS = ("liquid_tank",
  "large_liquid_tank")` — `discover_network_buildings()` takes iterable of type_ids (or
  single string), walks each outpost per type, dedupes by id.
- **Water and oil never share a tank**: router passes `fluid_id`, so a tank latched to the other fluid is skipped and an empty tank qualifies only with a matching `fluid_routing.tank_assignments` entry (§4). **First oil tank must be assigned `"oil"` by the operator.**
- **Oil well dormancy**: `well_active()` False → throttle `0` (saves 5 W), routing skipped. Water Pump has no `well_active()` → never dormant.
- Output port (same shape as Thermal Cap's `steam_out`) holds one destination at a
  time. `is_stalled()` same semantics as Thermal Cap's, so same
  blacklist-and-reselect reaction applies unchanged.

### 1c-1. Oil Generator: Last-Resort Power (`5_steampower/lib/oil_generator.py` `OilGeneratorController`)

+700 W at throttle 1 for 8 t/h oil; burning emits CO2 and oil feeds Fabricator recipes, so it only runs as last resort. No oil floor.

- **Start**: `min(battery fraction, combined reserve)` (§1a-0 `reserve_fraction()`, battery + steam) `< OIL_START_RESERVE_FRACTION = 0.15` AND deficit without oil `> 0`. Battery fraction matters because the deficit is measured after turbine output: banked steam can't cover it (turbines are rate-limited), only the battery buffers it — combined-only let the battery hit 0 with 35 kt steam banked (reserve read 64%). One `notify()` at start. No storage at all → burns only while deficit.
- **Throttle**: `deficit = consumed − (generated − Σ oil_generator member.generated)`, split evenly over all Oil Generators in `grid.members`; `throttle = clamp((max(0, share) × OIL_DEFICIT_HEADROOM (1.1) + OIL_RECHARGE_W (300) / count) / OIL_GENERATOR_RATED_W (700), OIL_MIN_THROTTLE (0.1), 1.0)`; recharge term only when the grid has a battery.
- **Stop**: battery fraction AND combined reserve both `≥ OIL_STOP_RESERVE_FRACTION = 0.30` (above the guard's 0.25 restore line). Grid unreadable → throttle 0 (fail safe).
- **Oil input**: `FluidInputRouter` (steam-turbine constants: stall streak 5, rescan 150 ticks, discovery cache 100 ticks, neutral grace 5); candidates = oil-eligible Liquid/Large Liquid Tanks (own outpost first), then Oil Pumps. Starved = throttle > 0, `oil_in.level() == 0`, `oil_consumption() == 0`.
- No archive state: game resets throttle to 0 on script stop; restart re-evaluates within one step.

### 1d. Per-Script Tick-Cost Profiling (`lib/profiling.py`)

Game exposes no per-script CPU/ms budget API. `clock.tick()` (deterministic
sim tick since save start, 10 ticks/sec normal speed) = sanctioned stand-in per
`docs/components/clock.md`. `lib/profiling.py` wraps pattern so any controller's `run()` loop
measures own `step()` with two calls:

```python
start = profiling.begin()
self.step()
profiling.end(self.name, start)   # logs a warning if delta > SLOW_STEP_TICK_THRESHOLD=1
```

- Samples roll into `archive` as one fixed-size history list per script name
  (`ARCHIVE_KEY_PREFIX="profiling."`, `HISTORY_LEN=50`) — one archive entry per profiled *script
  name*, not per sample, respects Data Archive's hard 512-entry cap.
- `profiling.report(names=None)` prints avg/max ticks-per-`step()` for every profiled name (or
  subset) — call ad hoc, not from hot loop.
- **Granularity limit — read before trusting a `0`**: `clock.tick()` advances on fixed 10/sec
  schedule *independent of script work* (scripts cooperatively scheduled, interleaved within each tick's window). `step()` with no internal loop finishes inside whichever tick it started regardless of real cost, so nonzero delta only by landing on tick boundary by luck — **a `0` does not mean "cheap."**
  `SLOW_STEP_TICK_THRESHOLD=1` reflects that: on non-looping `step()`, any nonzero delta already interesting. No finer (sub-tick/wall-clock) instrument — below floor, fall back to code-level reasoning (algorithmic complexity, what runs every cycle vs. gated).
- **Not currently wired into any script.** `lib/profiling.py` and `lib/archive_cleaner.py`'s
  cleanup of it kept for future script suspected of real bulk per-call work.
- **Storage shape & cleanup**: each archive entry `{"history": [...], "last_tick": N}`.
  `lib/archive_cleaner.py`'s `clean_profiling()` purges entry whose `last_tick` not advanced
  in `PROFILING_STALE_TICKS=6000` (10 sim minutes, "instrumentation removed"), always purges
  legacy bare-list entry (pre-dating shape) as one-time migration. Runs in
  `ArchiveCleaner.run()`'s normal sweep.

### 1e. Bio Luminizer Lamp-Mix Solve (`lib/bio_coastal.py` `BioLuminizerController`, `_solve_3x3()`)

*(Moved from `lib/bio.py` into own `lib/bio_coastal.py` module when bio pipeline
split per biome — see §0's module map and §1g. Shared pipeline helpers referenced here
(`_focus_local_order()`, `_snapshot_property_count()`) now in `lib/bio.py`,
biome-agnostic.)*

Tints coastal fragment glow to `BioOrder.target_glow` via `docs/components/bio_luminizer.md`'s
three lamps: `self.lamp_signature("red"/"green"/"blue")` each give fixed per-unit `[r,g,b]`
impurity, so lamp brightnesses `(r, g, b)` (each whole number 0-40) give
`glow = base + r*red_sig + g*green_sig + b*blue_sig`, where `base = self.glow()` read with all
lamps 0. Solving `(r, g, b)` for `target` = 3×3 linear system, `M @ [r,g,b] = target -
base` (`M`'s columns `red_sig`/`green_sig`/`blue_sig`) — no numpy, so `_solve_3x3()` inverts
via plain-Python closed-form Cramer's rule. Round to nearest int, clamp `[0, 40]`, verify against live `self.glow()` read; if rounding off by one, bounded ±1-per-channel
neighborhood search (≤27 `set_lamps()`/`glow()` round-trips) finds exact integer match. Fragment with no active coastal order needing it passes through unchanged via `self.discard()`.

**Key rules, hard-won (see `DESIGN_HISTORY.md` for the postmortems)**:
- **`exchange.active_order()` = shared, mutable, single-slot delivery-routing state — never use
  to look up "which order needs this fragment."** Use `_find_coastal_order()`/
  `_focus_local_order()` (scans `exchange.orders()` directly).
- **`set_order()`/`clear_order()`/`deliver()` are `*(self only)*` hardware calls** — script can't drive sibling machine. Other controller checking "does stack match order"
  must compare raw property directly (e.g. `list(stack.properties.get("glow", [])) ==
  list(order.target_glow)`), not call `matches_order()` remotely.
- **Staged sample may already be finished, not just raw** — `_order_matching_glow()`
  checks each staged stack, ejects (not reloads) one whose glow exactly
  matches live order's target; only stack matching no order's target treated raw and
  loaded. `_find_raw_stack()` applies same exact-glow exclusion when pulling from storage.

### 1f. Raw-Specimen Backlog Control (`lib/bio.py`'s `BioCollectorController`/`BioLabController`, `lib/bio_coastal.py`'s `BioLuminizerController`)

Current mechanism = **structural idle-gate**, not numeric backlog cap (several numeric
throttles tried first, replaced — see `DESIGN_HISTORY.md`): `BioLabController` refuses to
pull next specimen from Collector, and refuses to drain own extracted output, until
local biome processor fully idle (chamber/input/output empty — `_processor_is_idle()`, §1g). Max one raw specimen in flight ahead of processor, so no Warehouse pileup structurally possible regardless of how broadly Collector searches for "needed" fragments.

- `BioCollectorController.step()` nets demand against per-cycle `_local_stock_snapshot()`,
  prefers `_focus_local_order()`'s fragments over other incomplete orders' when picking
  cataloged location to harvest, falls back to any other needed fragment if preferred
  order's not discoverable nearby — soft preference, not hard block.
- **No busy-polling**: `_processor_is_idle()`-gated consumers wait on `"biome_processor_heartbeat"`
  Signal Bus broadcast (every processor controller fires it unconditionally each cycle) via
  `comms.wait_broadcast(...)` instead of `sleep()`, fallback `sleep(0.5)` if `comms`
  unavailable or wait errors.
- **`BioLabController` gates *extraction* on demand too**, not just idle-gate: once specimen
  reaches `stage == "analyzed"`, `_bio_demand_totals(comms, exchange, my_biome)` (module-level,
  shared with Collector's demand computation) checked before loading reagents — if
  demand doesn't exceed local stock, `self.machine.discard()` runs instead of `extract()`.
  Lets "uncataloged discovery" harvesting (needs only analysis, not extraction) avoid
  spending reagents/storage on sample nothing would collect.
- **Self-cleaning backstop**: `BioExchangeController._cleanup_orphaned_artifacts()` runs every
  `sweep_and_deliver()` cycle after normal per-order delivery loop — any locally-staged
  bio sample whose item id not required by any incomplete order anywhere taken into
  `self.machine.input`, destroyed via `input.flush()`. "Bio sample" =
  `item_catalog.lookup(id).category == "biology_sample"` (`_is_bio_sample()`, cached per id in
  `_ITEM_CATEGORY_CACHE`; falls back to "has properties or some order requires it" only if
  catalog unavailable) — Deep samples propertyless, so old properties-only test missed
  them, let finished orders' leftovers jam every Warehouse slot. Matches item id only (not exact glow), since not-yet-tinted raw sample never matches any order's `target_glow` and shouldn't be
  misclassified orphaned.
- `MAX_LOCAL_BIO_ARTIFACTS = 4` (formerly `MAX_LOCAL_GLOW_ARTIFACTS`, Coastal-only) = coarse
  total-artifact safety net, on purpose, not primary mechanism: if sum of every
  currently-demanded fragment's local stock (`_total_demanded_artifacts(snapshot, fragment_ids)`)
  reaches this, `BioCollectorController.step()` pauses harvesting that cycle. Healthy
  pipeline stays 0-2, never trips.
- `best_unload_target()`'s Inventory fallback gated by `outpost.is_home` (plain `bool`
  attribute on `OutpostRef`, not method — `Outpost` component from `get_component()`
  has `is_home()` as *method* with same name; watch this trap) — remote (Warehouse-only)
  outpost's drain calls skip `"inventory"` target, return `None` (caller leaves stack
  staged, retries next cycle) rather than attempt connection that can't work.

### 1g. Multi-Biome Bio Pipeline (`lib/bio.py` shared + `lib/bio_coastal.py`/`lib/bio_volcanic.py`/`lib/bio_deep.py`/`lib/bio_geothermal.py`)

Collector→Lab→(transform)→Exchange pipeline biome-agnostic in `lib/bio.py`; only transform step differs per biome, each own module (see §0 module map). `get_my_biome()` always reads `machine.outpost.biome` live, never hardcoded. `local_biome_processor(outpost)` probes which of `BIOME_PROCESSOR_TYPE_IDS = ["bio_luminizer", "bio_caster",
"bio_conditioner", "dna_sequencer"]` deployed there; returns `(None, None)` for Frozen (no transform step) or outpost without processor yet.

- **Generic idle-gate**: `_processor_is_idle(processor, processor_type)` dispatches on `processor_type`. `bio_luminizer`/`dna_sequencer` expose `.chamber`; `bio_caster`/`bio_conditioner` expose `.fragment()`.
- **Generic property matching, not just glow**: `_local_stock_snapshot()` second return = `by_properties: {(item_id, properties_key): count}` (`_properties_key()` canonicalizes any properties dict: sorted, list values tupled). `_order_target_properties(order, fragment_id)` resolves "already correctly processed for this order" per biome: `{"glow":
  order.target_glow}` (Coastal), `{"genes": order.required_genes[fragment_id]}` (Geothermal), `None` for Volcanic/Deep (any correctly Forged/Conditioned unit satisfies any order needing it; those two rely on `matches_order()` at delivery).
- `_focus_local_order()` also excludes Frozen orders outright (`order.biome == "frozen"`). Frozen has no single-slot processor bottleneck; Exchange blanket sweep already delivers plain fragment once extracted.
- **Bio Caster (Volcanic, `lib/bio_volcanic.py` `BioCasterController`)**: bang-bang heat/cool toward `required_range()`. Full `set_heat(100)`/`set_cool(100)` outside `CASTER_APPROACH_BAND_C = 50` °C band around target range edge, `CASTER_APPROACH_PCT = 25` % near it, both 0 once `temperature()` inside band. Casts when temperature in range AND `materials()` matches `required_materials()` exactly. **Unverified live**: assumes staging material into `self.input` via `take()` enough for `cast()` to auto-consume, same as Fabricator/Smelter recipe. Confirm with `debug()` output first real recipe run.
- **DNA Sequencer (Geothermal, `lib/bio_geothermal.py` `DnaSequencerController`)**: fully spec'd, no live-verification gap. `order.required_genes[fragment_id]` = splice target, validated against `gene_catalog()` before `splice()` (unknown gene id risks `"destroyed"` result). `chamber.spliced == True` never spliced again ("one splice per fragment").
- **Bio Conditioner (Deep, `lib/bio_deep.py` `BioConditionerController`) — fully automated.** In-game docs never expose pass/fail rule for 10 QC properties; wrong `accept()`/`reject()` call `"burned"`s (destroys) specimen. Rulebook (`CONDITIONER_RULEBOOK` in `lib/bio_deep.py`) recovered from decompiled game client, cross-checked vs logged outcomes. See `DESIGN_HISTORY.md` for provenance:

  | Property | Pass rule |
  | --- | --- |
  | `glow` | `blue`, `green`, or `purple` |
  | `brightness` | 45–80 lm if `glow` `blue`/`green`; 20–50 lm if `glow` `purple`; else fail (incl. `white`/`dark`) |
  | `smell` | `salty` or `fishy` |
  | `gunk` | 70–85% |
  | `cracks` | `none` or `small` |
  | `feel` | `hard` |
  | `twitch` | `weak` or `still` |
  | `bugs` | 1–3 |
  | `weight` | 180–260 g, extended to 300 g if `gunk` ≥ 70 |
  | `sound` | `ding`; or `thud` only if `cracks` `none`/`small` |

  Every stage recorded to bounded `archive["bio.conditioner_observations"]` history (`CONDITIONER_OBSERVATION_HISTORY_LIMIT = 200`) for audit. Unrecognized `current()` property (rulebook stale) halts, no blind guess.
- **Confirmed live**: Conditioned fragment `.properties` carries `{'conditioned': True}`, distinct from untested raw fragment `properties=None`. `_find_raw_stack()`/`_load_next_sample()` skip/recover any stack with `properties.get("conditioned")` truthy, not treat as raw QC input.

### 1h. Essence Pipeline: Drone Depot → Essence Liquifier → Liquid Tank → Biomass Mixer (`lib/essence_liquifier.py`, `lib/biomass_mixer.py`, `lib/biomass_mixer_gate.py`)

All three live in `5_steampower` (not deployed below tier 5). Liquifier/Mixer controllers only wiring + feeding; the only production decision is the gate's pause/resume.

- **Liquifier feed**: item transfers explicit (`InputSlot.take()`), never passive. Depot's own `output.connect(liquifier)` (§2h) only declares link. `EssenceLiquifierController` points `.input` at same-outpost Drone Depot (`DRONE_DEPOT_TYPE_ID = "drone_station"`), reads stock via `depot.output.stacks()`, `take()`s only items where `nocturna.life_form_biome(item_id) == liquifier.biome()` (non-life-forms read `None`, never touched). Species already in bin tried first. Foreign-biome life form in Depot → one warning per item id (permanently uses Depot material slot). Tops up only when input has `FEED_MIN_ROOM_UNITS = 5` free, since `take()` blocks time proportional to units moved. **Request retention (§2i)**: a native item with `logistics_requests.retain_amount() > 0` is only fed from the Depot beyond what the local Warehouse stash still lacks (`retain - warehouse_stock`). `feed_from_warehouse()` (after the Depot feed) liquifies native life forms from the local Warehouse buffer (§2h) above their retain amount.
- **Liquifier drain**: single `<biome>_essence_out` port uses same `FluidOutputRouter` as Water Pump (§1c), with `fluid_id="<biome>_essence"` and `fluid_routing.LIQUID_TANK_TYPE_IDS`, so subject to `fluid_routing.tank_assignments` (§4). Empty new tank must be assigned to e.g. `"frozen_essence"` before any Liquifier uses it. Same constants as Pump (`ESSENCE_TANK_REBALANCE_FILL_FRACTION = 0.98`, `CONNECTION_GRACE_TICKS = 2`, `RESCAN_INTERVAL_TICKS = 300`, `DISCOVERY_CACHE_INTERVAL_TICKS = 100`). Router "blocked" input **not** raw `is_stalled()`: true for `stall_reason()` in `("output_full", "unconnected")` or when declared link `FluidConnection.state` broken. `"no_input"` (waiting for drones) excluded, else idle Liquifier blacklists good tank.
- **Mixer inputs**: one `EssenceInputRouter` per biome (`ESSENCE_BIOMES`), each a thin wrapper around the shared consumer-side `fluid_routing.FluidInputRouter` (§1b), `DISCOVERY_CACHE_INTERVAL_TICKS = 100`. Starvation is per port (not machine-wide `is_stalled()`): buffer < `STARVED_LEVEL_T = 1` t with `flow_rate() == 0` for `STALL_STREAK_THRESHOLD = 6` steps (~30 s) → source dropped + blacklisted, next candidate tried (catches a "ready" link to a dry remote Liquifier while a full tank sits unused). Port healthy if `port.connections()` has any peer in state `"local"`/`"ready"`, declared by either side. So Liquifier (or operator) already wired onto Mixer left alone. Else candidates: Liquid Tanks eligible for that essence, then same-biome Liquifiers directly, Mixer's own outpost first in each group. Reachability from `FluidConnection.state` (`fluid_routing.HEALTHY_CONNECTION_STATES` / `BROKEN_CONNECTION_STATES`), not Mixer's machine-wide `is_stalled()`. Broken link blacklisted immediately (`RESCAN_INTERVAL_TICKS = 300`, per-entry). `"neutral"` link (e.g. empty unlatched tank) gets `NEUTRAL_GRACE_STEPS = 6` steps, then dropped only if other untried candidate exists. Ports with no biome source anywhere stay quiet (debug only). Mixer warns once when `is_stalled()` starts (active < `required_essences()`), notes once on recovery.
- **Mixer math** (decompiled simworker `tickBiomassMixers()`/`mpe()`, `K7 = 1.5`): per game hour, mixing d balanced essences → `1.4 · d^1.5` t biomass, draining `4` t/h of **each** selected essence (Mk I; Mk II ×4.5 out, ×2.4 in). Biomass per ton essence = `0.35 · √d` (Mk II `0.656 · √d`), **independent of balance** — imbalance (`balanceFactor = min level / demand`) only cuts throughput, all selected essences drain by the same bottleneck amount. Mixer picks the d with the highest **rate** (`d^1.5 · balance`, phase minimum up to 5), not the best efficiency, so it runs degraded at d−1 when one buffer is dry.
- **Mixer gate** (`MixerGate`, called every `MIXER_GATE_TICK_INTERVAL = 10` ticks from `panel_4.py` — one copy for every tier since the tier-5 duplicate was folded in; Mixer rediscovery every 300 ticks keeps it cheap while no Mixer exists): pauses Mixer via `power_control.set_powered(id, False)` (no `set_enabled()`; breaker-off also pauses the Mixer's own script, so it can't live in `lib/biomass_mixer.py`). Fluid still flows **into** an unpowered Mixer (simworker only requires the link's *source* to be powered), so buffers refill while paused. *Expected* essence = same-biome Liquifier exists on network AND `<biome>_essence_in` has a non-broken connection. RUN → PAUSE when any expected, non-given-up buffer < `PAUSE_LEVEL_T = 1.5` t. PAUSE → RUN when all ≥ `RESUME_LEVEL_T = 10` t. Escapes: buffer not rising by `PROGRESS_EPSILON_T = 0.05` t for `NO_PROGRESS_TICKS = 600` → that biome *given up*; `MAX_PAUSE_TICKS = 3000` or backpressure (buffer within `FULL_MARGIN_T = 1` t of capacity AND its Liquifier `stall_reason() == "output_full"`) → give up all still-waiting biomes. Given-up biome rejoins at ≥ `RESUME_LEVEL_T`. Mixers/Liquifiers rediscovered every `DISCOVERY_INTERVAL_TICKS = 300` (tick-based, not step-based — panel loop runs ~2–7 s/step), plus an early rescan when essence arrives on a linked input whose biome has no known Liquifier. Liquifier ids persisted in `biomass_mixer.gate_known_liquifiers` (first run baselines silently); a new one whose biome input is still unlinked holds that Mixer in RUN (resuming it if gate-paused) up to `REWIRE_HOLD_TICKS = 1200`, since the Mixer's own router is paused along with it. No gating while expected count < `required_essences()` (Mixer self-stalls anyway). Only switches ON a Mixer it switched off itself (`paused_by_gate`), never one in archive `power.shedded`; Mixer switched off/on externally is respected. State in `biomass_mixer.gate.<id>` (§4). ⚠️ If `panel_4.py` stops while a Mixer is gate-paused, the Mixer stays off until the gate runs again (it resumes from archive state) or the operator flips the breaker.

### 1i. Seed Discovery Sweep (`6_seeds/lib/seed_maker.py` `SeedMakerController`, stage A)

Fair brute force (no save peeking). Facts it relies on (docs/components/seed_maker.md + decompiled recipe generator): 15 recipes (`SEED_SPECIES_TOTAL`), uniformly random over all C(30,3) = 4060 triples, **no biome structure**, each life form in at most `MAX_RECIPES_PER_FORM = 4` recipes. Every trial costs 1 t of each of the 3 forms (hit or sludge); a trial takes ~0.06 game-h (~15 ticks), so **life-form supply is the bottleneck**, not the machine. Expected full sweep ≈ 3770 trials ≈ 11.3k t life forms (offline sim with generator rules, saturation pruning included); hits evenly spaced (~254 trials apart), so the last species costs no more than the first.

- **Order doesn't matter for hit rate** → next triple chosen purely by local stock: open triple maximizing its scarcest member's stock (forms ranked by stock, smallest worst-index searched first). No need to gather all 30 forms first.
- **Saturation pruning**: forms already in 4 `recipes()` blends skipped entirely (every other triple with them is guaranteed sludge).
- **State**: `seed.combos_tried` `{"a,b,c": True | claim}` (§4) — name-keyed, never reset. Claim `{"by", "tick", "stage": "loading"|"running"}` expires after `SEED_CLAIM_STALE_TICKS = 3000`; claiming + marking via `archive.transaction()`, so several Seed Makers at one outpost can share it (one is enough). Hits are not stored — `recipes()` is the game's own journal; known blends get marked tried.
- **Restart recovery** (`_recover()`): wait while `is_running()`, drain output; chamber holding a full open triple → re-combine; other chamber content → `eject()` to local storage; own `"running"` claim with empty chamber → trial finished → marked tried; own `"loading"` claim → released.
- **Loading**: `storage.take_item(input, form, 1, outpost=...)` (Warehouses + home Inventory), fallback local Drone Depot. Any load failure → eject chamber, release claim.
- **Requests**: every `REQUEST_REFRESH_TICKS = 1200` (must stay well below `REQUEST_STALE_TICKS = 3000`, else requests blink out between refreshes; open-triple count is closed-form minus closed `_tried` entries — a full 4060-triple walk cost ~620 ticks/step), each form still in ≥1 open triple requested at `min(SEED_STASH_TARGET_T = 60, its open-triple count)` t (1 t per open triple it's in — big hauler batches early, no overstock near the end) via `logistics_requests.set_requests(outpost, "seed_maker", ...)` (§2i). Cleared once all 15 known or no open triple left.
- **Output**: seed sent to `"inventory"` (planting starts there), else `drain_port_to_storage()`.
- Telemetry `seed_maker.status` (§4). Stage B: §1k.

### 1k. Planting: Seed Supply + Field Layout + Planting Harvester (stage B, tier `8_planting`)

- **Phase change**: `6_seeds/bio/seed_maker.py` runs `SeedSupplyController` (`seed_supply.py`) once `len(recipes()) >= SEED_SPECIES_TOTAL`, else the stage-A sweep.
- **Seed supply** (`SeedSupplyController(SeedMakerController)`, reuses chamber/stock/output helpers): makes the seed with the largest deficit whose 3 blend forms are all in local stock. Deficit = `plant.seed_demand["now"]` − seeds at home (`total_stock()`: Inventory + home Warehouses). Finished seeds drain to a local Warehouse (`drain_port_to_storage()`), Inventory only as fallback. No fresh demand (older than `SEED_DEMAND_STALE_TICKS = 6000`) → `SEED_BUFFER_PER_SPECIES = 1` seed per species. Life-form requests (§2i, requester `seed_maker`) = **base stock** (1 t per layout cell whose blend uses the form, from `plant.seed_demand["rotation"]`, i.e. one full replant) + open deficit, capped at `SEED_SUPPLY_STASH_T = 30` per form. Forms outside the layout's blends get no request. Publishes `plant.recipes` for the Harvester (it has no `recipes()`). Restart: a chamber holding a known blend is combined, anything else is ejected.
- **Field**: fixed 8 × 24 grid at home only (A1–H24). Field machines and crops use **no building slots**. Rules read only the 4 orthogonal neighbours: spacer (no other plant beside), cluster (≥2 of own species → 2×2 minimum), companion, antagonist; light/water/salt treatments; shade = must not be lit.
- **Layouts**: three phases (`field_layout.py`, chosen by `harvester_planting.load_layout()`; `LAYOUT_VERSION = 3` is recorded only):
  - **starter** (`STARTER_LAYOUT`, until Field Automation is researched = `crop_automator_kit` in `deployables()`): 2 × 4 block of the 8 species that are neither spacers nor clusters (DW TV SB SM / SU GV SP SH, ×8 diversity), anchored by `anchor_layout()` nearest the base (row and column offsets). No machine cells, no paving needed. Why 8: hand care for all 15 species needs ~38 Harvester hours/day. Never rebuilt: machines unlocked before automation only save hand-care time. A stored layout without `mode` (older saves) counts as starter.
  - **full** (after Field Automation; fixed 8 × 24, base pad `FULL_LAYOUT_BASE = "E13"`, always the middle): diversity garden with all 15 species in columns 1–`GARDEN_COLS = 5`, plus a fill, 12 Crop Automators. Only machines that give a kept plant a service it needs are reserved (`_needed_machines()`). `full_layout(chunks, fill)`: chunk 1 = the automators covering the garden (3); each further chunk adds the next automator left to right with the fill cells in its area. `validate()` + `provider_violations()` clean and 15 species for every chunk count (1–10) of both fills. Fill (`FIELD_FILL = "crowncap"`, operator override Data Archive key `plant.field_fill`):
    - **phase 2, `crowncap`**: solid Crowncap everywhere else, except the base pad, cells a kept Grow Lamp lights (shade) and cells beside a kept spacer; clusters cut by a chunk edge are pruned (`_prune_clusters()`). `FILL_KEEP = ("C7",)` keeps one checkerboard Grandbloom (with its lamp/sprinklers) because the garden has none. 1.25 Forage per cell-hour (60 / 48 h, every cell) with no machines, power or water, vs 1.04 for the Grandbloom checkerboard at Mk I. About 2× the life forms per Forage (a seed per 60 Forage vs 150). Chunk 1: 24 plants, 19 machines, ~440 Forage/h; chunk 10: 148 plants, 28 machines, ~2,760/h.
    - **phase 3, `grandbloom`**: `FULL_LAYOUT` as drawn, a Grandbloom checkerboard (each touches only machines; Grow Lamp rows alternate with Sprinkler rows). Pays from Mk II lamps + sprinklers (×3; ×12 cap at Mk IV). Chunk 1: 28 plants, 24 machines, ~560/h; chunk 10: 94 plants, 90 machines, ~2,600/h at Mk I. Switched by the operator (`plant.field_fill = "grandbloom"`), which rebuilds the full layout once.
  - Chunks from demand: `chunks_for_demand(terraformer_demand(plant.terraformer), rules, fill)`, `forage_per_hour()` = Σ base/growth × diversity at Mk I; Terraformer use `TERRAFORMER_BATCH = {1: 1200, 2: 6600}` per `TERRAFORMER_CYCLE_H = 3`. The switch to full happens once; a full layout then only grows (same fill), re-checked every `LAYOUT_RECHECK_TICKS = 3000`. Full mode: no paving (the Harvester drives over machines); cells a deployed automator serves are its work, the Harvester plants the rest (outside the garden only once their machines are in) and harvests everything else mature.
  - **Rebuild**: growing/stalled plants in the new layout's way (`misplaced()`: wrong species on a layout cell, on a reserved cell, or beside a layout cell) are uprooted (seed back to Inventory); mature ones are harvested; plants away from it finish their cycle and aren't replanted.
- **Starter expansion** (`expand_layout()`, off: `LAYOUT_EXPANSION_ENABLED = False`): greedy single-plant additions of the best `base_yield / growth_time / blend_cost` species, where `blend_cost` = Σ `RARITY_COST = {common: 1, uncommon: 2, rare: 5}` over the blend (static `LIFE_FORM_RARITY` from docs). Only the new cell and its neighbours are re-validated. Caps: `MAX_DAILY_CARE = 20` treatments/day, `MAX_FIELD_PLANTS = 40`.
- **Harvester loop** (`FieldKeeperController`), one task per step, cheapest route (heat) first: **care tour** (first: a lapsed treatment stalls growth, a mature crop just waits; harvest-first starved care live) → harvest mature (then replant on the spot) → uproot a plant in the layout's way (rebuild, above) → plant open layout cell with its seed at home (collects a loose item there first) → **deploy** a field machine (full layout, below) → **pave** a path cell (below) → collect loose items off the path (only at heat ≤ `ITEM_SWEEP_MAX_HEAT = 40`; only path cells keep their items, so seeds from an older layout's path are reused for paving, then collected back into Inventory) → wait in place (no trip back to base: costs heat, nothing needs the base). Care tour: once any treatment drops below `CARE_REFRESH_H = 4.0` h, every treatment below `CARE_BATCH_H = 12.0` h is renewed in one tour, so renewals line up. Any visit also renews everything below `CARE_BATCH_H` on that cell. Provider-covered = flag set with 0 manual time. Water refilled when < 1 t aboard. Failed plant → cell skipped `PLANT_FAIL_COOLDOWN_TICKS = 3000`. `inventory_full` on harvest → harvesting paused `INVENTORY_FULL_RETRY_TICKS = 3000`. Harvester actions retried `ACTION_RETRIES = 3` on busy/moving.
- **Heat** (`harvester_heat.py`): move onto item +1, empty +7, empty collect +9, passive cooling ~3/world-hour (`COOL_PER_HOUR_DEFAULT`, from the vakermit harvester; also during actions). That's ~72 heat/day = only ~13 net empty-cell hops/day without resting, so heat is the Harvester's real budget. Routes: single-source Dijkstra over all 192 cells (Dial buckets, costs ×`COST_SCALE = 2`, <1 ms offline), per hop `move_cost(status) + HOP_TIME_WEIGHT = 1.5`, so detours over plant/item cells (+1) beat crossing empty cells (+7); one map serves target choice (`cheapest()`) and the route. Plant statuses (`growing`/`stalled`/`mature`) seeded at +1 from the first live readings. Rests only right before a hop/action would cross `max_heat − HEAT_SAFETY (3)`, and only as long as that needs (`real_seconds_per_hour()`); overheated action → rest to cap − `ACTION_HEAT_RESERVE = 9`. Move cost per destination status (seed `{"item": 1, "empty": 7, "unknown": 7, "growing"/"stalled"/"mature": 1}`, others (provider, base) `DEFAULT_MOVE_COST = 7` until measured) and cooling rate are measured every hop/rest (EMA `CALIBRATION_ALPHA = 0.3`) and saved in `plant.status[<id>]["heat"]`. First live readings: plant cells (`mature`, `stalled`) ≈ +1. Field actions heat up too: each action in `ACTION_HOURS` (plant/harvest 0.5 h, treatments/collect/refill 0.25 h, ...) is budgeted before the call (`ACTION_COST_DEFAULT = 3.0` until measured) and its cost learned from the heat rise corrected for cooling during the action (`heat.actions`). Near the cap it therefore rests right before every step: that's the intended cooling-limited steady state, not a stall. **Step budget**: the script gets a limited number of steps per tick, so planning is cached: neighbour table built once, one statuses dict per step shared by target choice and route (heat map cached by identity), `stock_count()` memoised per step (each `total_stock()` walks every Warehouse), rules re-read every `PUBLISH_INTERVAL_TICKS`, layout loaded once per run. Debug logs `planned in N ticks` per decision.
- **Paving** (`harvester_paving.py`): a dropped item (seeds included, confirmed by the dev 2026-09-24) makes a cell an item cell, so moving onto it costs +1 heat instead of +7. Plant cells calibrate at about +1 too, so the expensive cells are the plant-free gaps the rules force. `field_layout.path_cells()` picks a short path of gap cells joining every plant patch (greedy Steiner tree over 4-connected patches; base pad and reserved machine cells excluded) — **0 cells for the starter block** (one patch; the old 5 × 8 layout needed 4–5). Off in the full layout. Each gets one item, once, when heat ≤ `ITEM_SWEEP_MAX_HEAT`: first a loose item carried over from elsewhere on the field (fresh saves only; the early sweep collects them), else (`PAVE_WITH_SEEDS = True`) a seed of the species with the cheapest blend (`blend_cost`; shadeleaf on the current save), loaded from Inventory and `drop()`ped (3 t life forms per cell). Paving seeds are added to `plant.seed_demand["now"]`, at most `PAVE_SEED_BATCH = 5` at a time. Loose-item sweep only runs once the path is paved. `PAVING_ENABLED` switches it off.
- **Field machines, Harvester side** (`harvester_machines.py` `HarvesterMachinesMixin`): deployed machines from `home.harvesting_machines()` (type + position, once per step; fallback `Cell.status == "provider"`). **Kit order**: standing Fabricator order `fabricator.upgrade_orders["field_keeper"]` for the Grow Lamp / Sprinkler / Dispenser kits still missing on reserved cells (only kinds in `deployables()`, re-read every `DEPLOYABLES_REFRESH_TICKS = 3000`), a stock target capped at `KIT_STOCK_CAP = 10` per kit so Warehouses don't fill with kits. Full layout: its reserved cells. Starter: **pre-order** for `full_layout(desired chunks)` once the Plants Sensor reads ≥ `PREORDER_MIN_KM2 = 550000` (Field Automation at 620,000). **Crop Automator kits** are Shop items (30,000 cr): never bought; the missing count is `plant.status[...]["automators_wanted"]` plus a console warning. **Deploy** (full layout only): kit at home → drive there, collect a loose item, `stage()` the kit, `deploy()`. Failed cell skipped `DEPLOY_FAIL_COOLDOWN_TICKS = 3000`. A new machine has no script until scripts_sync fills its slot.
- **Crop Automator** (`crop_automator.py` `CropAutomatorController`, thin `harvesting/crop_automator.py`), every `POLL_INTERVAL_S = 10`, full layout only: consumes job results (the 50-result inbox pauses the machine when full); owns the layout cells in its 5 × 5 area that no nearer deployed automator reaches (Chebyshev, then Manhattan, then sector id: every cell exactly one owner); queues `harvest()` for its mature crops and `plant()` for its open cells once the machines beside the cell give every care service the species needs (automators only apply Fertilizer/Growth Accelerant); loads the seed into its input just before (`take_item()`, Inventory then home Warehouses); keeps the queue ≤ `QUEUE_LIMIT = 45`; failed cell skipped `JOB_FAIL_COOLDOWN_TICKS = 3000`; drains Forage to home storage once the output holds ≥ `OUTPUT_DRAIN_ABOVE = 100` (`drain_port_to_storage()`), where the Plant Terraformer takes it. No jobs while in `power.shedded`. Loose items on its cells are swept by the Harvester. Telemetry `plant.automators`. Draw 60 W.
- **Field machines, machine side** (`field_provider.py` `FieldProviderController`, thin `harvesting/grow_lamp.py`, `sprinkler.py`, `dispenser.py`), every `POLL_INTERVAL_S = 10`: enabled only while a layout crop beside it needs its service (`plant.layout` + `plant.recipes`; no layout stored → just runs) and it isn't in `power.shedded`. A Sprinkler drinks Water even with no crops, hence the off switch. Sprinkler `water_in` via a `FluidInputRouter` (Fabricator values, home sources first). Dispenser tops its 50-unit input up to `DISPENSER_FILL = 8` salt once below `DISPENSER_REFILL_BELOW = 3` (`storage.take_item()`: Inventory, then home Warehouses), small so the Harvester's hand-care salt isn't drained. Mk I draws: lamp/sprinkler 5 W (sprinkler 2 t/h Water). Telemetry `plant.providers` every `PUBLISH_INTERVAL_TICKS = 600`. The Harvester stops treating a covered cell by hand (flag set with 0 manual time).
- **Seed demand** `plant.seed_demand` (every `PUBLISH_INTERVAL_TICKS = 600`): `now` = open layout cells + layout crops at growth ≥ `SEED_PREFETCH_GROWTH = 0.75` or mature + `SEED_BUFFER_PER_SPECIES`; `rotation` = layout cells per seed.
- **Salt**: species needing salt stay unplanted while home salt (Inventory + Warehouses) < `SALT_MIN_STOCK = 3`. While the layout has salt species, requester `field_keeper` asks home for `SALT_STOCK_TARGET = 20` salt (Inventory + home Warehouses). Served by the reverse hauler from Water Pumps (§2i). **Staging**: seeds and salt live in home Warehouses like any bulk item (no Inventory clutter). `load_seed()`/`dispense_salt()` read Inventory only, so `FieldKeeperController.stage(item_id)` pulls one unit from a Warehouse into Inventory right before each use (`transfer_to("inventory", ...)`, instant, works from anywhere). A leftover unit is swept back out by `rebalance_inventory_to_warehouses()`.
- **Plant Terraformer** (`plant_terraformer.py` `PlantTerraformerController`, thin `bio/plant_terraformer.py`): Inventory is location-bound for ordinary I/O, so Harvester Forage (home Inventory) feeds a Terraformer at home, or must be hauled. Holders fit one full batch (Mk I 1,200 / Mk II 6,600 Forage) + Salt + 10 of each support item; all consumed at cycle start, so the next batch is preloaded while one runs. Materials follow `required_inputs()`/`batch_requirements()`: Forage/Salt/Growth Accelerant via `storage.take_item()` (Inventory + local Warehouses), Fertilizer best tier first until unopened potency covers `fertilizer_potency` (capped `SUPPORT_HOLDER_CAP = 10`), Water via a `FluidInputRouter` on `water_in` once the phase needs it (Fabricator's constants). **Run policy**: a cycle is 3 h and draws power (Mk I 180 W) whatever its size, while one field supplies far less than 400 Forage/h, so an idle machine is enabled only at `MIN_START_FORAGE = 100` onboard (or the full batch if smaller, e.g. near a phase threshold); while a batch runs, Forage is preloaded only once stock can reach that threshold (an enabled machine starts the next batch instantly). Stays enabled while blocked on Water/Salt/etc. (disabled hides the reason). `complete`/`needs_mk2` → disabled, requests cleared, `needs_mk2` warned once. Restart: in-flight batch found from `get_progress()`/`is_running()` or the last published `in_flight`, re-enabled. **Demand advert** (requester `plant_terraformer`, §2i): every needed material is a **local stock target** (next batch staged in the outpost's Warehouses/Drone Depots, holders not counted) -- the shape `outpost_deficits()` (Pioneer pull hauler, floating drone hauler) and `network_deficits()` (miner drones) already read. Forage: one full batch, only away from home (home = field output = source). Salt/Growth Accelerant: `SUPPORT_REQUEST_BATCHES = 2` batches. Fertilizer: as Mk I `fertilizer`, "have" in Mk I potency equivalents over all tiers. "have" = `logistics_requests.outpost_stock()`. Republished every `REQUEST_REFRESH_TICKS = 600` or at once on a target change. An item another requester already owns at the outpost (e.g. the Harvester's salt) is left alone. Loader takes from Warehouses/Inventory (`take_item()`), then a local Drone Depot (drone freight). **Source side**: an item the outpost doesn't request itself (home Forage) is only consumed above the largest other-outpost target (`remote_retain()`), so a home Terraformer leaves the batch a hauler comes for; a requesting outpost never holds back. Fertilizer/Accelerant crafting not automated (`fabricator.upgrade_orders` entries of non-drones get pruned by `fleet_upgrade`). Poll `POLL_INTERVAL_S = 10`. Telemetry `plant.terraformer` (§4).

### 1j. Field Mining Drill Telemetry (`lib/mining_drill.py`)

A drill needs no control. It extracts on its own; the only script surface is `drill_rate()` and a read-only `PickupOutputSlot` stockpile (docs/components/mining_drill.md). One controller (`MiningDrillController`) serves all three variants (`mining_drill`, `mining_drill_industrial`, `mining_drill_heavy` thin scripts).

- **Poll**: `POLL_INTERVAL_S = 60.0` (Mk I: 2,000 units at 25 t/h = ~80 h to fill; Heavy: 5,000 at 200 t/h = ~25 h). Capacity always read live.
- **State**: `drilling` (rate > 0), `full` (rate 0, count ≥ capacity), `stalled` (rate 0 with room left: unpowered, no deposit, or deposit too hard; API can't tell these apart). Warn once per transition into `full`/`stalled`; info on recovery.
- **Near full**: fill ≥ `NEAR_FULL_FRACTION = 0.8` while drilling → one warning with time-to-full, re-armed once fill drops back under it.
- **Time-to-full**: `(capacity − count) / drill_rate()`, assumes 1 stockpile unit = 1 t (unverified).
- Thin script passes `drill_type` (published as `type`, used by `drill_sites.discover_drill_ids()`).
- **Telemetry** `drill.status` (§4). Drills sit on mineral sites, not the outpost network, so `ArchiveCleaner.clean_machine_status()` can't prune them; each publish prunes other entries older than `STATUS_STALE_TICKS = 36000` instead.
- **Pickup advert**: the `drill.status` entry's `items` is what the reverse hauler (§2i) reads as the drill's free stock; its position comes from `drill.positions`.

---

## 🚗 2. Surface Vehicles & Logistics

| Vehicle | Speed / Throttle | Energy Cost / Budgeting | Operational Rules |
| :--- | :--- | :--- | :--- |
| **Rover** | `self.cruise_throttle` (explicit at construction, else fleet-wide `vehicle.default_cruise_throttle` archive value, default 0.5) capped per-leg by `RoverController.max_safe_throttle_for_leg()` | Developer-confirmed travel model, Rover-specific, flat (no calibration, no Pioneer terms): `Wh/meter = 0.2 × throttle`; safety margin `SAFETY_MARGIN_MULTIPLIER = 1.05` (5%). See §2a | Sonar scan: `SONAR_WH_BUDGET = 2.0` Wh. Mining drill: exact per-ore/per-drill/per-purity `mine_wh_per_unit(item_id, purity)`, `MINE_WH_PER_UNIT = 2.5` Wh/unit only as no-item-id fallback. See §2a. Return to nearest charging station (not necessarily home) when Wh below trip budget. |
| **Pioneer** | Configurable slots / tools | Slot chassis: `inspect_slots()`, `execute_construction()`; construction energy: `WH_PER_PROGRESS` (per-vehicle calibrated, default `CONSTRUCTION_WH_PER_PROGRESS_DEFAULT = 40.0` Wh for 0%→100%). See §2a | Heavy construction, blueprint placement, pipe/power line deploy. Budgets each trip for `TARGET_CONSTRUCTION_PROGRESS_PER_TRIP = 0.25` progress (~4 round trips per job), not just round-trip driving. |
| **Harvester** | BFS on 8x24 grid (`NUM_ROWS=8`, `NUM_COLS=24`, A1..H24) | Travel time: 0.5 h/sector. Empty move: `+7 heat`; Item move: `+1 heat` | Max heat: 100°C. Pause & cool when heat exceeds `HEAT_SAFE_CEILING = 75.0`, resume at `HEAT_RESUME_LEVEL = 40.0` (`lib/harvesting.py`). Tier `8_planting` replaces this with calibrated just-in-time resting, see §1k. |

### 2a. Vehicle Energy Budgeting Detail (`lib/vehicle_energy.py` `VehicleEnergyMixin`)

- **Travel energy = developer-confirmed exact model, not empirically calibrated — Pioneer and
  Rover use two DIFFERENT models.** Archive-backed Wh/meter calibration intentionally removed
  for both (treated as ground truth). Construction *progress* energy still calibrated
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
    exactly 2x speed / 2.6x power (`docs/components/nav_module.md`); `nav_power_multiplier()`
    linearly extrapolates +1.6x power per +1.0x speed for additional Sport Navs. No Sport Nav gives
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
  - **Script-parser constraint**: sandboxed parser rejects multi-line parenthesized `from X
    import (a, b, c)` (valid standard Python, but `SyntaxError: expected Identifier in from-import,
    got (` in-game) — always write cross-module imports on one line.
  - **`lib/charging.py` fleet rescue** (`manage_fleet_rescues()`): dispatch triggers on engine
    `"stranded"`/`"stalled_no_battery"` status, OR `return_floor_wh()` (the Wh needed on board
    *right now* to self-navigate to the nearest station, via `rescue_wh_per_meter_for()` at
    `MIN_SPEEDMODE_THROTTLE` — same formula the vehicle's own hard-abort uses).
    `RESCUE_EXTRA_RESERVE_WH = 8.0` is added on top only when sizing `rescue_target_level()` (how
    much to charge *during* rescue); the trigger comparison uses the bare floor.
  - **Multi-station arbitration**: every deployed station gates dispatch on
    `is_nearest_station_to(vehicle_ref)`, so only one rescues a given stranded vehicle. Ties default
    to allowing dispatch.
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
  call site passes candidate's own `harvest_item`/`purity`. `MINE_WH_PER_UNIT = 2.5` (flat) now
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
  `self.cruise_throttle` resolves same as `wh_per_progress`: explicit constructor value
  (demand-driven transporter role always passes `cruise_throttle=1.0`, since it recharges fully
  at both ends of every leg — §2f), else `default_cruise_throttle()` — fleet-wide
  `vehicle.default_cruise_throttle` archive value (clamped to `[MIN_SPEEDMODE_THROTTLE,
  MAX_SPEEDMODE_THROTTLE]`, fallback `DEFAULT_CRUISE_THROTTLE_FALLBACK = 0.5`), settable via
  Data Archive Notebook or live from `panel_2.py`'s FLEET card slider. `lib/drone_energy.py`
  mirrors exactly for drones — own `drone.default_cruise_throttle` archive key (distinct from
  vehicle key so fleets tune independently), same clamp/fallback, settable from `panel_5.py`'s
  DRONE FLEET card slider (§7).
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
- Construction (Pioneer only): `calculate_trip_energy()`'s `planned_construction_progress` param
  adds `progress * self.wh_per_progress`. `wh_per_progress` calibrated per-vehicle from real
  `constructor.execute()` calls (`calibrate_wh_per_progress()`), fallback
  `CONSTRUCTION_WH_PER_PROGRESS_DEFAULT = 40.0` Wh (0%→100%) until enough samples.
  `planned_progress_for_job()` caps planned progress at
  `TARGET_CONSTRUCTION_PROGRESS_PER_TRIP = 0.25` (or less if further along) — floor on whether to
  depart, not on-site cap.
- **Construction job claims (Pioneer only, `run_construction_loop()`, exclusive)**: construction
  job NOT shareable (two Constructor Pioneers on same blueprint would double-load materials).
  Uses `vehicle_claims.py`'s exclusive claim mechanism, key `f"build_{job_id}"`
  (`PioneerController.construction_claim_key()`), prefix distinct from mining `"site_"`/survey
  `"poi_"`. `claim_target()` called at each of three commit points (resuming paused job,
  executing cargo-matching pending job, committing before round trip home).
  `execute_construction()` heartbeats via `refresh_claim()` every attempt (no-op if not owner).
  Released on completion (`get_construction_progress() >= 1.0`) or genuine failure, held across
  incomplete "still paused" outcome, released wholesale on unhandled exception.
  **Blueprint missing from every list (pending/active/paused) counts as complete (1.0)** — game
  drops finished blueprints from all lists; used to read 0.0, so completion claims never released
  (121 of 124 claims leaked in one save) and completing step never calibrated `wh_per_progress`.
  `release_finished_construction_claims()` also sweeps this Pioneer's own `build_*` claims on
  no-longer-live blueprints each loop pass (one transaction per claims key, only when something
  needs releasing, skipped if any list read failed).
- Fleet coordination (`lib/vehicle_claims.py`): atomic `archive.transaction()` claims (mirrored to
  `rover.claims` / `survey.claims`), heartbeat-renewed via `refresh_claim()`, expire after
  `CLAIM_STALE_TICKS = 36000` ticks (1 sim hour). **Mineral mining sites no longer exclusive**
  (several Pioneers may mine same POI) — claim calls still fire for bookkeeping
  (`current_target_key`, mission resume) but never gate candidate selection. Survey/POI targets
  still exclusive via same mechanism.
- **In-flight mining yield reservation** (`lib/mining_reservations.py`, `mining.reserved_yield`
  archive key): non-exclusive, additive bookkeeping — vehicles converging on one deficit no longer
  collide via claim, but without this would all see same undiminished demand.
  `VehicleMiningMixin.select_best_mining_target(candidates, reserve_demand=True)` (home-demand path only)
  estimates trip yield via `max_mineable_units()` and reserves it; `get_raw_material_demands()`
  subtracts every non-stale reservation's units before returning. Heartbeat-renewed/released
  (`refresh_yield()`/`release_yield()`), same expiry (`RESERVATION_STALE_TICKS = 36000`).
  **Stockpile path** (`build_local_stockpile_candidates()`, `reserve_demand=False`) skips this —
  already self-bounded by each outpost's `stock_target_for()`.
- **Energy-based mining trip sizing** (`VehicleEnergyMixin.max_mineable_units()`): replaces
  `cargo.capacity()` as default yield estimate. Solves trip-energy budget directly for units
  (outbound + base return Wh fixed, mined-unit Wh and marginal return-drive Wh linear in unit
  count) after subtracting `MIN_EMERGENCY_RESERVE_WH` and applying `SAFETY_MARGIN_MULTIPLIER`,
  clamped to `cargo.capacity()`. `mine_until_full_or_exhausted()` stays safety net for estimate
  drift (e.g. richer-than-expected purity).
- Recall (`lib/vehicle_claims.py`): one shared `vehicle.recall` dict `{vehicle_name: True}` (not
  one archive key per vehicle). `is_vehicle_recalled()`/`set_vehicle_recalled()` module-level
  read/write. Toggled via `panel_2.py`'s Fleet card switch: on → abandon current target, drive to
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
  `run_expedition_cycle()`/`run_mining_loop()` compute `has_resumable_target` before forcing
  return-to-base-and-unload detour, so save reload mid-trip doesn't undo already-resumed drive.
  `cargo_matches_target(target)` downgrades `has_resumable_target` to `False` for that cycle only
  when cargo holds *different* material than resumed target's `harvest_item` (cargo not
  material-locked). Target with no `harvest_item` (survey POI) always matches.

### 2a-0. Supply Dock cargo draining (`lib/supply_dock.py` `SupplyDockController`)

`set_order()` rejects with `"cargo_present"` while any cargo loaded in dock's 5 slots —
`clear_order()` deliberately does **not** drain cargo, only releases order assignment.
`drain_dock_cargo()` ejects every non-empty slot to Inventory; `step()` calls it (retries next
cycle) whenever `curr_order` is `None` but `dock.total() > 0`, before trying `set_order()`.

### 2a-0-1. Construction material demand cascade (`lib/production.py`)

`_cascade_blueprint_demand()` = single source of truth for "how much of any item — finished or
intermediate — active construction ultimately needs":

- Seeded from `required_item`/`required_count` across every pending/paused Construction Blueprint
  job (summed, deduped by job id).
- Seed netted against units already aboard ground vehicles (`_vehicle_cargo_counts()`, via
  `fleet.vehicles()` + live `cargo.stacks()`): a constructor Pioneer loads a whole chained-job batch
  while every job stays pending until built, so without this the Fabricator re-crafts the batch.
- Breadth-first propagated down through Fabricator/Smelter recipe `inputs` (`recipe_inputs_for()`).
- **Only each tier's shortfall propagates down** — demand beyond item's current
  `inventory.count()`, so on-hand stock counted once. Example: 10 `power_line_segment` needed,
  3 in Inventory → 7 to build → 7 `titanium_ingot` needed, 5 in Inventory → only 2 propagate →
  4 `titanium_ore` needed (2:1 smelt ratio), not 20.
- Known limitation: item reachable via multiple paths nets shortfall against same Inventory
  snapshot independently per occurrence, slightly overstating demand under diamond-shaped recipe
  dependency — not worth full MRP-style solve for game's shallow (2-3 tier) chains.

Two consumers read cascade differently:
1. `get_fabricator_targets()` (§2a-1) uses **raw, uncapped demand** for items Fabricator can
   build.
2. `get_construction_material_reservations()` nets against current stock
   (`min(inventory.count(item_id), demand)`) — protect-from-shipping amount.
   `supply_dock.py`'s `step()`/`pick_best_order()` subtract this before deciding how much to
   `take()` or how "ready" order looks.

Deliberately conservative: job's full cascaded demand stays reserved while pending/paused, even
after cargo loaded (cargo not tracked here).

### 2a-0-2. Multi-Fabricator Support (`lib/production.py`, `lib/fabricator.py`)

`production.discover_fabricator_ids()`/`_default_fabricator()` replace all hardcoded
`"fabricator_1"` fallbacks. `claim_recipe()`/`release_recipe()` (`lib/fabricator.py`,
`STALE_TICKS=600`, archive key `"fabricator.recipe_claims"`) stop multiple Fabricators converging on same recipe: `choose_recipe()`'s candidate loop claims each sourceable candidate in shortfall order, next on claim fail.

- **Pile-on fallback + even split**: if NO candidate exclusively claimable (only one recipe demanded), `choose_recipe()` joins biggest-shortfall one anyway, no idle.
  `get_fabricator_worker_ids(recipe_id)` (sorted live roster of Fabricators on that recipe) splits `crafts_remaining` floor-plus-remainder: first `crafts % workers` ids get one extra, shares sum exactly (a worker may get 0 and idle). Was ceil per worker, up to workers−1 surplus per order.
- **Pipeline netting**: every "still needed" (`get_fabricator_active_recipe()`, `choose_recipe()`) = target − `total_stock()` − `production.get_fabricator_pipeline(cache)` = every Fabricator's output-buffer stacks + one craft's output per running craft (memoized on `SourceCache`). Was own `get_output_count()` only; peers' buffers and in-progress crafts went uncounted (7 surplus Oil Tank (Medium) after vestibule_15, with Inventory full and outputs backed up).
- **Output drain fallback**: Fabricator and Smelter `drain_output()` use `storage.drain_port_inventory_first()`: Inventory first, a local Warehouse only on `INVENTORY_FULL_STATUSES = ("partial", "target_full", "slots_full")`. Costs consumers an Auto Feeder hop, beats a stalled output bin. Applies to `INVENTORY_ONLY_ITEM_IDS` too; `take_item()` still finds them for docks/Fabricators, drone `couple()`/`deploy()` can't until moved back.
- **Load chunking**: `load_inputs()` capped to `FABRICATOR_LOAD_CHUNK_SIZE = 10` units per call (was: whole remaining batch in one grab). `lib/smelter.py` ore top-up has matching `SMELTER_LOAD_CHUNK_SIZE = 10`; Supply Dock loading has `SUPPLY_DOCK_LOAD_CHUNK_SIZE = 10`.
- **`production.craft_prefill_units(recipe, item_id, prefill_seconds=INPUT_PREFILL_SECONDS)`**
  (`INPUT_PREFILL_SECONDS = 30`, no archive state) = real fairness mechanism. Asks "how much staged to keep crafting next ~30 real seconds", not "how much left to load": `ceil(prefill_seconds / craft_seconds(recipe))` crafts' worth, floor one craft's requirement. `craft_seconds()` converts `recipe.duration_game_hours` via
  `SECONDS_PER_GAME_HOUR = lib/power.py's DAY_CYCLE_DURATION_SECONDS / 24.0` (reused, not redefined). `lib/smelter.py` ore top-up + `lib/fabricator.py`'s `load_inputs()` both cap take with this, plus chunk-size ceilings above (simple per-call cap, not primary fairness). Supply Dock stays on `SUPPLY_DOCK_LOAD_CHUNK_SIZE` only (no recipe/duration for prefill window).
- **Smelter demand = whole order tree** (`production.get_smelter_demands(cache)`, used by `lib/smelter.py` instead of `get_material_demands()`). `get_material_demands()` only sees ingot demand through each Fabricator's *currently selected* recipe (per-worker split, each share netted vs full stock separately), and `_cascade_fabricator_output_demand()` stops at Smelter outputs — so 400 drones on manual order showed as ~1 ingot, Smelters trickled 1 ore per poll. Gross-then-net-once: each `get_fabricator_targets()` entry with deficit `D` adds `D × ratio` per recipe input that is Smelter output; target set directly on Smelter output counts as-is; dock orders for Smelter outputs not in targets added; then net once vs total stock **and** every Fabricator's staged `get_stockpile()`. Mining (`get_raw_material_demands()`) not switched yet (TODO).
- **Raw ore owed to dock never smelted**: `production.dock_remaining_requirements()`
  (`required − shipped − dock.count()` per item, all active orders) subtracted from stock in `SmelterController.available_ore()` — needed since real ingot demand can eat every unit.
- **Dock order remainder = one helper, per order**: `production._dock_order_remaining()` → `{order_id: {item_id: required − shipped − Σ dock.count() over every dock serving that order}}`. Every dock-demand site (`get_fabricator_targets()`, `get_material_demands()`, `get_smelter_demands()`, `dock_remaining_requirements()`) reads it. Deduped per order id because several docks can share one order (was counted once per dock); loaded-but-undispatched units subtracted because they're in neither Inventory nor `shipped` (Fabricator targets skipped this and overshot every order by the dock's load, stranding non-stacking gear in Inventory).
- **Ore intake caps** (Smelter Step 3, `lib/smelter.py`): take amount =
  `max(0, min(50 − in_buf, SMELTER_LOAD_CHUNK_SIZE, max_ore_for_share − in_buf,
  prefill_cap − in_buf, fair_total − in_buf))`.
  - `share = ceil(demand_qty / workers)` = this Smelter's slice of current total demand;
    `max_ore_for_share` converts it to ore units via `(qty * units_per_run + output_count - 1) //
    output_count`.
  - `prefill_cap = craft_prefill_units(recipe, ore, SMELTER_PREFILL_SECONDS)` —
    `SMELTER_PREFILL_SECONDS = 30`, split out from the shared `INPUT_PREFILL_SECONDS` so Smelters can
    be tuned alone (left at 30 after the retired `smelter.diag.*` data showed no starvation). At 0.08 h/craft (2 s) that's 15 ore.
  - **Fair-share cap** (`fair_total`): `(available ore + Σ input buffers of every Smelter on this
    recipe, this one included) // workers`, from `production.smelter_recipe_peers(recipe_id)` →
    `(workers, buffered)`. Plentiful stock never binds; scarce stock splits evenly (fixes one Smelter
    grabbing a whole scarce silicon stock).
- **Recipe switching hysteresis** (`select_needed_ore()`): while current recipe still demanded + sourceable, Smelter keeps it outright if it holds (or can take) claim; joiner (peer holds claim) may move to *unclaimed* recipe only if that recipe's demand ≥ `switch_min_demand()` = one `SMELTER_PREFILL_SECONDS` window of output (15 units for 2 s 1:1 recipe). Found live: leftover demands 3–22 units bounced Smelters between iron/glass/titanium, 6–10% time in `recipe_switch` (each switch ejects buffer, changes recipe, skips step). Smelter now releases old recipe's claim on switch, not blocking peers until claim stale.
- **Join gate** (same function): pile-on joining recipe peer already claims needs
  `demand ≥ switch_min_demand() × (workers after joining)`; else Smelter idles, outcome `demand_covered_by_peers`. Found live: 1-unit Rare Earth Core demand pulled all five Smelters (three ejecting buffers to switch) onto one recipe.
- **One `SourceCache` per Smelter `step()`**: stock snapshot, recipe lists, `get_fabricator_targets()` (memoized on `cache._fabricator_targets`) computed once per step.
  `get_fabricator_targets()`, `get_fabricator_active_recipe()`, `get_material_demands()`,
  `_cascade_blueprint_demand()`, `_cascade_fabricator_output_demand()` all take optional `cache=None` (same behavior without).

### 2a-0-3. Multi-Dock Support (`lib/production.py`, `lib/fabricator.py`)

`discover_supply_dock_ids()` + `_all_dock_orders()` (`[(dock, order), ...]`) replace single hardcoded `_component("supply_dock_1")` read in `get_fabricator_targets()`,
`get_material_demands()`, `get_raw_material_reason()`, so second dock's active order not invisible to demand tracking. No claim coordination (unlike Fabricator recipes) — fulfillment inherently per-dock; several docks may serve same order, share shipped progress (`docs/components/supply_dock.md`), explicitly fine. `find_dock_order_requiring(item_id)` consolidates "which dock's order wants this item", shared by `get_raw_material_reason()` + `lib/fabricator.py`'s `target_reason()`. §2a-0-5 covers which order each dock gets.

### 2a-0-4. Multi-Fabricator active-recipe input demand (`lib/production.py` `get_material_demands()`)

"Selected Fabricator recipe = explicit production intention" block loops `discover_fabricator_ids()` (fallback `["fabricator_1"]`), sums each Fabricator's own `get_fabricator_active_recipe()` input demand, not just first discovered Fabricator. Safe to sum: when several Fabricators share claimed recipe, `get_fabricator_active_recipe()` already divides `crafts_remaining` by worker count (§2a-0-2), so each adds only fair share.

### 2a-0-5. Multi-Dock order planning & weekly-deadline feasibility (`lib/supply_dock.py`)

Central planner `plan_dock_assignments(clock=None)` runs **once** per cycle from headless automation panel's AUTOMATION section (throttled to `STORAGE_TICK_INTERVAL`), not each dock re-scanning full Earth Order board every cycle. `set_order()`/`clear_order()`/
`set_enabled()` all `*(self only)*` hardware calls, so planner only decides — writes `{dock_id: order_id or None}` to `"supply_dock.order_plan"` archive key (`ORDER_PLAN_ARCHIVE_KEY`); each dock's `SupplyDockController.step()` reads its entry via `desired_order_id()` and does actual `set_order()` itself.

- **Stability**: dock holding still-`can_fulfill_order()`-true order keeps it regardless of ranking — mid-shipment order not cleared over marginal priority diff.
- **Spread-then-join for idle docks**: candidates re-sorted before each idle-dock assignment by `(docks_already_on_this_order ascending, priority descending)` — idle docks spread across needed orders, but all join same one if only good candidate.
- **Weekly-deadline feasibility**: `_weekly_infeasible(order, current_day, dispatch_capacity_per_hour)` skips Weekly Earth Order entirely when `remaining_units > dispatch_capacity_per_hour *
  hours_remaining` (`hours_remaining = (order.expires_day - current_day) * 24`) — i.e. even shipping flat-out with all known docks' combined `dispatch_rate()`, remainder can't leave before `expires_day`. Dispatch-capacity ceiling only (not production-rate forecast — upstream recipe throughput/worker counts/deficits = later TODO). Returns `False` (don't block) when needed input missing. Campaign orders (no `expires_day`) unaffected.
- **Fallback**: `SupplyDockController.desired_order_id()` uses archive plan when this dock's id present, else own weekly-feasibility-aware `pick_best_order()` — soft fallback (unlike Solar/Smelter hard dependency in §1a-1).
- **Shared scoring**: `_score_campaign_order()`/`_score_weekly_order()`/`_order_readiness()` module-level, used by planner + per-instance fallback — no ranking drift.

### 2a-1. Fabricator demand tracking (`lib/production.py` `get_fabricator_targets()`)

Single source of truth for what Fabricator builds, feeds `get_material_demands()` →
`get_raw_material_demands()`. Five demand sources folded into one `{item_id: quantity}` dict:

1. `fabricator.stock_targets` archive key (defaults in `DEFAULT_FABRICATOR_STOCK_TARGETS`:
   `gas_pipe_segment`/`power_line_segment`/`liquid_pipe_segment` = 10 each) — edit archived key directly to retune.
2. Active Supply Dock order's `requires`, for items Fabricator can build (`max()`'d vs stock target, not summed).
3. **Pending/paused Construction Blueprints**, via `_cascade_blueprint_demand()` (§2a-0-1), `max()`'d vs existing target — not summed (targets = steady-state floor, not additive per source).
4. **`fabricator.manual_orders`** archive key (`{item_id: quantity}`, e.g. `{"drone_small": 2}`) — ad-hoc build requests, edited directly (no default seeded). `max()`'d into target like other sources, but ALSO queue priority in `choose_recipe()`: picked ahead of any other demanded recipe regardless of shortfall. Counted down (dropped at 0) by `production.consume_manual_order()`, called from `drain_output()` with qty actually delivered. Key must exactly match recipe's `output_item` (hand-typed, no write validation) — `get_fabricator_targets()` prints one-time warning (per-script-run, `_WARNED_UNKNOWN_MANUAL_ITEMS`) when key doesn't match default Fabricator's unlocked recipe outputs (heads-up only, can false-positive for other Fabricator or not-yet-unlocked recipe).

5. **`fabricator.upgrade_orders`** archive key — `{requester_id: {item_id: quantity}}`, written only by code (`production.set_upgrade_order()`): the fleet upgrade coordinator (requester `"fleet_upgrade"`, Depot kits/chassis) each drone (its own id, better Cargo Pods/Oil Tanks/missing loadout modules) and the planting Harvester (requester `"field_keeper"`, field-machine kits, §1k). Summed across requesters by `get_upgrade_orders()`, `max()`'d into the target. Each requester replaces/clears only its own entry; entries of drones that no longer exist are pruned by `FleetUpgradeCoordinator._prune()`; non-drone requesters must be listed in `production.STANDING_ORDER_REQUESTERS = ("field_keeper",)` or they get pruned too. See §2k.

`choose_recipe()` priority has **five tiers** (biggest shortfall first within each): (0) manual-order-blocking intermediate, (1) manual order, (2) **Construction Blueprint demand** (`production.blueprint_demand_items()` = every item `_cascade_blueprint_demand()` reaches — building new things beats upgrading working old ones), (3) **fleet upgrade order** or an input it is blocked on (`get_manual_order_blocking_items(outputs, get_upgrade_orders())`), (4) everything else (Earth/Supply Dock orders, stock targets). Tier 0 detail: `production.get_manual_order_blocking_items()` outranks even manual orders. = set of Fabricator-output items a manual order transitively needs as INPUT (e.g. `machine_frame` under manual `drone_service_station_kit` order) currently short of stock — found via same shortfall-only BFS as `_cascade_fabricator_output_demand()` (§2a-0-1), seeded from manual orders only. Without this tier, Fabricator holding manual order whose recipe needs out-of-stock intermediate kept re-selecting that manual recipe forever: `can_source_item()` only checks some recipe path exists for intermediate, not that anything producing it, so manual order never looked "blocked" — sat idle waiting on input nothing built, while other Fabricators worked lower-priority targets.

### 2a-1b. Sourceability caching across a pass (`lib/production.py` `SourceCache`)

`can_source_item()`, `can_source_fluid()`, `can_fulfill_order()` (§2a-0-5) each walk real game-API calls (Smelter/Fabricator discovery + `list_recipes()`, `outpost.buildings()`,
`journal.surveyed_sites()`, per-Warehouse `count()`), not free local compute.

`SourceCache` (instantiate once per pass, thread through every call) memoizes:
- `smelter_recipes()`/`fabricator_recipes()`/`surveyed_sites()` — each game call fires at most once per cache instance.
- `can_source_item()`/`can_source_fluid()` results per item/fluid-key — shared sub-item (e.g. Steel under both Circuit Panel and Iron Ingot) resolves once, not per branch. Separate `_item_stack` set does cycle detection so memo never poisoned with in-progress answer.
- Stock snapshot: `_build_stock_map()` calls `.stacks()` once per Inventory/Warehouse (returns every `ItemStack` in one call), sums by `.id` into one `{item_id: total_units}` dict; `stock(item_id)` = plain dict lookup. Total cost `1+W` calls per pass regardless of distinct items — strictly better than `.count()`-per-item `total_stock()` (`D*(1+W)`).

All three call sites default `cache=None` (private one-off `SourceCache()`), but hot paths build + share one: `plan_dock_assignments()` one per pass; `FabricatorController.choose_recipe()` one per candidate list. Cache = one-pass snapshot only — never held across ticks or reused between passes.

### 2a-2. Fabricator input-stockpile ejection (`lib/fabricator.py` `eject_excess_inputs()`)

`set_recipe()`/`clear_recipe()` both leave input stockpile untouched — only built-in clear is `InputSlot.flush()`, which **permanently discards** material. `eject_excess_inputs()` runs every `step()`, before recipe selection, recovers stranded/excess staged material via `InputSlot.eject(destination, item_id, count)` (routes to least-full Warehouse with room via `storage.best_unload_target()`, or Inventory — never `flush()`) in two cases (both off currently-set recipe via `production.get_fabricator_active_recipe()`):

1. Staged material active recipe doesn't need (leftover from prior recipe, or no recipe) — eject all.
2. Staged material active recipe DOES need, beyond `required_per_craft * crafts_remaining` (same cap `load_inputs()` loads to) — eject excess only.

`eject()` transactional, safely no-ops on portion reserved for in-progress craft, so unconditional every-step call harmless.

### 2a-3. Fabricator fluid-input connections (`lib/fabricator.py` `ensure_fluid_connections()`)

Recipe's `fluid_inputs` (e.g. `{"water_in": 1.0}`) delivered via `FluidPort` connection, not Inventory/Warehouse take. `ensure_fluid_connections(recipe)` runs every `step()`, one `fluid_routing.FluidInputRouter` per fluid port (§1b **Input vs output routers**):

- Per `fluid_key` active recipe declares, `production.FLUID_SOURCE_TYPE_IDS[fluid_key]` names every building type that can feed it (e.g. `water_in` accepts `water_pump`,
  `steam_condenser`, `liquid_tank`, `large_liquid_tank`) — same mapping `can_source_fluid()` uses.
- **Generic Liquid/Gas Tank existing ≠ proof it can supply given fluid** — buffers latch onto whichever fluid piped in *first*, hold only that until drained to `0`.
  `production.BUFFER_FLUID_TYPE_IDS` + `fluid_building_is_viable(fluid_key, type_id, building)` gate both `can_source_fluid()` and this discovery loop identically: dedicated producer always counts (fixed one fluid); buffer counts only once own `.fluid()` latched to needed fluid (`production.FLUID_LATCH_IDS`). Resolves bare `BuildingRef` to live component via `get_component(ref.id)` first when passed object has no `.fluid()`.
- **No `is_stalled()` on Fabricator itself** — reachability inferred from port's own `flow_rate()` staying `0` for `FLUID_STALL_STREAK_BLACKLIST_THRESHOLD=5` *consecutive* ticks while room to receive (`level() < capacity()`) — legitimately full port also reads `flow_rate()==0`, must NOT count as stall. Same per-entry blacklist expiry as other connect/blacklist controllers (`FLUID_RESCAN_INTERVAL_TICKS=150`); `FLUID_DISCOVERY_CACHE_INTERVAL_TICKS=100`, `FLUID_NEUTRAL_GRACE_STEPS=5`. Candidates ranked own-outpost-first.
- One router per `fluid_key` (`_fluid_routers`, created lazily) — recipe can need multiple fluids at once (oil-refining needs `oil_in` + `water_in`), independent sources.

### 2b. Mining (`lib/vehicle_mining.py` `VehicleMiningMixin`)

Mineral-site discovery + drill execution in one place, shared by Rover and Pioneer (mixed into `VehicleController`).

- Capability always read live via `self.vehicle.drill.hardness_limit()` — never assumed from vehicle type. Rover fixed Drill only carries basic drill (`hardness_limit = 1`, iron_ore/silicon); Industrial (`hardness_limit = 3`) and Heavy (`hardness_limit = 4`) Drills = Pioneer-universal-slot items for higher-hardness sites.
- `build_mineral_site_candidates(deprioritize_hardness_at_or_below=None)`: candidate sites matching `get_raw_material_demands()` + vehicle hardness limit. Passing `ROVER_PREFERRED_MAX_HARDNESS = 1.0` sets `priority=3` instead of `2` on hardness ≤ 1 sites — **soft** preference (capable Pioneer still claims easy site if nothing harder pending).
- Neither candidate builder filters peer-claimed sites (mineral sites no longer exclusive) — see `lib/mining_reservations.py` for overmining guard.
- `select_best_mining_target(candidates, reserve_demand=False)`: sorts by `(priority, -PURITY_RANK,
  distance)` — priority first; within tier, richer beats closer (`PURITY_RANK = {"standard": 0, "rich": 1, "pure": 2}`); distance only breaks ties between equally-rich. Soft preference — `calculate_trip_energy()` achievability check + `claim_target()` still run after sort. Both builders attach site `"purity"` from `getattr(site, "purity", None)`; POI candidates default to `"standard"`'s `0`.
  Achievability checked at full 10-unit haul first; if not fitting round-trip budget, retries once at whatever `max_mineable_units()` says affordable instead of rejecting (only 0 affordable = real rejection) — else vehicle whose battery never fits full 10-unit trip (undersized battery, or expensive-per-unit ore like Neutronium) idles at base forever despite reachable demand. Logged at `print()` level (`"battery can't afford a full load -- heading out for a partial ~N-unit load"`) when fallback fires — normal-operation outcome worth surfacing, not debug detail.
- `mine_current_site(max_units=None)` defaults to `self.vehicle.cargo.capacity()` (live) when no `max_units`. Home-demand mining loops always pass explicit `max_units` from `select_best_mining_target()`'s `estimated_units` (energy-based, `max_mineable_units()`).
  `mine_until_full_or_exhausted(target_coords)` wraps it with recharge-and-resume-in-place loop. Battery-interruption recharge stop landing at *home base* station itself with cargo loaded unloads via `unload_cargo()` **before** `recharge_at_station()` — ore not stranded in cargo during (possibly multi-minute) recharge, and resumed `mine_current_site()` gets full cargo capacity as `max_units`.
- Pioneer mining role (`run_stationed_mining_loop(outpost_id)`) requires operator already mounted drill — only checks `hasattr(self.vehicle, "drill")`, idles with advisory if absent; never auto-mounts.
- **Unified role entrypoint (`PioneerController.run()`/`detect_role()`, `lib/pioneer.py`)**: every `pioneer_N.py` script constructs `PioneerController`, calls `run()`. `detect_role()` maps `ROLE_MODULES` (`{"constructor": "constructor", "scout": "sonar", "miner": "drill"}`) via `hasattr(self.vehicle, <attr>)` — exactly one mounted module picks role; none → `"hauler"`; more than one = misconfigured loadout (`TreeConsole` warn + no-op) unless `role_override=` passed. `run()` dispatches: constructor → `run_construction_loop()`, scout → `run_survey_loop()`, miner → `run_stationed_mining_loop(self.home_base)` (never home-demand `run_mining_loop()`), hauler → `run_haul_loop(dest_outpost_id=...)`. Equipment swappable at runtime, so re-probes every script run, no role caching.

### 2b-1. Pioneer Auto-Upgrade (`lib/vehicle_upgrade.py` `VehicleUpgradeMixin`)

Auto hardware tier upgrades for Pioneer, checked once per idle-at-base cycle (`handle_upgrade_cycle_if_idle()`, called from same "parked at base, checking readiness" checkpoint every role loop has: `run_mining_loop()`/`run_construction_loop()` in `lib/pioneer.py`, `run_haul_loop()`/`_stationed_mining_cycle()` in `lib/vehicle_cargo.py`/
`lib/vehicle_mining.py`, `run_survey_loop()` in `lib/vehicle_survey.py` — last three Rover-shared, so call there `hasattr(self._host, "handle_upgrade_cycle_if_idle")`-gated).

- **Pioneer-only.** `docs/database/equipment_modules.md` documents Sport Nav, Wide/Deep Sonar, Industrial/Heavy Drill as Pioneer-universal-slot items — Rover's 3 fixed slots only accept basic `nav_module`/`sonar_module`/`drill_module` (§2b), so never better tier for it. `VehicleUpgradeMixin` mixed into `PioneerController` only, never shared `VehicleController` base.
- **Tier tables** (worst → best; `best_unlocked_tier()` only steps to immediate next tier present in fresh `shop.get_catalogue()` read, never straight to top, so one swap = one affordable purchase):
  - `SONAR_TIERS = ["sonar_module", "sonar_module_wide", "sonar_module_deep"]`
  - `DRILL_TIERS = ["drill_module", "drill_module_industrial", "drill_module_heavy"]`
  - `BATTERY_HOLDER_TIERS = ["battery_holder_small", "battery_holder_medium", "battery_holder_large"]`
    (`_BAY_COUNTS`: 1/2/3 bays)
  - `CARGO_RACK_TIERS = ["cargo_rack_small", "cargo_rack_medium", "cargo_rack_large"]` (1/2/3 bays)
  - `PORTABLE_BATTERY_TIERS = ["portable_battery", "heavy_portable_battery"]` (50Wh/100Wh)
  - `PORTABLE_BIN_TIERS = ["portable_bin", "heavy_portable_bin"]` (25u/50u)
- **Swap ordering (`_upgrade_function_module()`/`_upgrade_containers()`)**: `unmount` old → `shop.buy` new → `mount` new → `shop.sell` old — deliberately holds old + new in Inventory briefly instead of selling first, so failed purchase rolls back clean (`mount(slot_index, old_id)` restores vehicle). Failure *after* buy (mount rejects, or container mid-sequence purchase runs out of credits) left as logged, non-destructive stop state for operator, not force-rolled-back — nothing silently lost, at most deferred one cycle.
- **Battery Holder swaps always recharge to ~100% first** (`_ensure_full_charge_for_sale()`) before uninstalling any Portable Battery — `shop.sell()` refunds battery's retained charge% with 50% floor (`docs/components/shop.md`), so full charge maximizes refund. Cargo Rack swaps skip this; Portable Bins not charge-valued.
- **Density policy**: every Battery Holder/Cargo Rack bay — newly added by size upgrade (`_fill_container_bays()`) or already installed at base tier (`_top_up_container_density()`, independent of any size upgrade that cycle) — gets **Heavy** Portable Battery/Bin once unlocked, falls back to base variant only while Heavy locked.
- **Sport Nav deliberately excluded from auto ladder** — stacks additively onto mounted Nav instead of replacing, so manual one-shot operator action: `request_sport_nav(vehicle_name)` sets shared `{vehicle_name: True}` archive dict (`SPORT_NAV_REQUEST_KEY = "vehicle.sport_nav_request"`, same shape/rationale as `vehicle_claims.RECALL_KEY`), surfaced as per-Pioneer-row button on `panel_2.py`'s FLEET card (only drawn when `width >= SPORT_NAV_BTN_MIN_WIDTH = 1100`, wide layout).
  `handle_sport_nav_request_if_active()` consumes it once idle at base: finds first free `universal` slot, buys + mounts `nav_module_sport` if unlocked + affordable. Request flag always clears after one attempt, success or fail — stuck request (no free slot, locked research, insufficient credits) no retry loop; operator clicks again when ready.

### 2c. Storage Management (`lib/storage.py`)

Makes whole production chain aware of Warehouse/Large Warehouse buildings, not just central home `"inventory"` endpoint. Scope: Warehouse + Large Warehouse only (`STORAGE_TYPE_IDS`) — Storage Bin uses different single-material API, not included yet. Everything defaults to home outpost, matching Inventory only participating at Nocturna Base.

- `total_stock(item_id)` = `inventory.count(item_id)` + every discovered Warehouse's `count(item_id)` — what every demand/mining-priority function nets against.
- `best_unload_target(item_id, min_amount=1)`: among Warehouses at `outpost` with `space_for(item_id) >= min_amount`, prefers one **already holding `item_id`** (consolidate onto existing stack), falls back to least-full (`fill_percent()`) only when none stocks it; `"inventory"` if no Warehouse qualifies. `vehicle_cargo.py`'s `unload_cargo()` picks destination **per stack**.
- `consolidate_cross_warehouse_stock(outpost=None)`: calls `.compact()` on every discovered Warehouse/Large Warehouse at `outpost` to merge same-item stock split across several — genuinely pulls from *other* storage endpoints, not purely intra-building (confirmed live; `.compact()` locks its Warehouse as material endpoint whole cycle).
  Runs once per `STORAGE_TICK_INTERVAL` cycle from headless automation panel's AUTOMATION section for **every** outpost (unlike Inventory-only, home-scoped rebalance sweep below).
- `take_item(port, item_id, amount, outpost=None, cache=None, report=None)`: single function behind every `machine.input.take(item_id, amount)` call site. Tries **only endpoints holding item** (`_holder_candidates()`): Inventory first (home only — no own Auto Feeder, never locks), then Warehouses by most stock; any endpoint answering `"busy"` within `TAKE_BUSY_COOLDOWN_TICKS = 20` (~2 s) moved last (still tried as last resort). No API to ask "is Warehouse busy?" upfront — `"busy"` rejection returns immediately (no feeder wait), so it is the probe; remembered per script in module-level `_recent_busy`. With `SourceCache`, holders come from its one-shot `building_stock(item_id)` snapshot (home only); else one `.count()` per building. `report` gets `{"sources": [(id, status, moved), ...]}`.
  Warehouse feeder cost observed live: ~2.5 ticks/unit (10 units = 25 ticks), locks whole building for duration.
- **Multi-Smelter Coordination** (`SmelterController`) — `production.discover_smelter_ids()` replaces hardcoded `"smelter_1"`. No Leader/Follower election — inventory-manager sweep runs centrally from headless automation panel's AUTOMATION section (§1a-1). Each smelter's `select_needed_ore()` claims its recipe (`claim_recipe()`/`release_recipe()`, `archive.transaction("smelter.recipe_claims",
  ...)`, `SMELTER_RECIPE_CLAIM_STALE_TICKS = 600`) before crafting, so two smelters don't start same recipe while other demanded ore sits untouched.
  - **Pile-on fallback**: if only ONE ore demanded, `select_needed_ore()` collects every
    sourceable/demanded candidate, tries to claim each, and if none can be claimed exclusively,
    joins the first anyway rather than idling. Joined smelters split intake via the demand-share
    and fair-share caps (§2a-0-2) and self-throttle together as `get_smelter_demands()` nets down.
- **"Inventory manager" sweep** — `rebalance_inventory_to_warehouses()`, called once per cycle from headless automation panel's AUTOMATION section: any **propertyless** Inventory item moved to Warehouse **entirely** when it spans more than `INVENTORY_REBALANCE_SLOT_THRESHOLD = 2` slots, or already split (some in Inventory, some in Warehouse — `_warehouse_item_ids()`).
  - **Exception**: `item_catalog.lookup(item_id).category` of `"equipment"`, `"module"`, or
    `"portable"` (`NON_WAREHOUSABLE_CATEGORIES`, `_must_stay_in_inventory()`) are never swept —
    equipment deploys from Inventory only; modules/portables must be in Inventory to equip a
    vehicle. `"construction_kit"` is NOT in this set (placed via blueprint construction, fine to
    warehouse).
  - **Direct move**: if any Warehouse has `space_for(item_id) > 0`, `inventory.transfer_to()` as
    much as fits, splitting across more than one Warehouse if needed.
  - **Swap fallback**: if no Warehouse has any room, evicts whichever Warehouse occupant is
    cheapest to bring back (smallest quantity) — only when `slots_freed > slots_reclaimed`
    (`slots_reclaimed = ceil(evicted_qty / inventory_stack_size())`), a genuine net reduction.
    `slots_freed` is computed from `remaining` (units still stuck *at swap-fallback time*, after
    any direct-move already ran), not a stale original count. In practice a swap is only a net win
    for a small-quantity occupant (roughly `slots_freed * stack_size` units or fewer); a
    persistently-fragmented item logs `[storage] Skipping swap for <item>: ...` /
    `[storage] Could not clear...` / `[storage] Swap for <item> did not go through...` /
    `[storage] Freed a slot... but it still reports no room...` instead of silently continuing.
- `inventory_stack_size()`: `10`, or `20` once `research.is_unlocked("research_high_density_storage")` ("Bigger Stacks").
- **Reverse sweep** — `reclaim_inventory_only_items_from_warehouses()`, called right after "inventory manager" sweep from `panel_4.py`'s AUTOMATION section: any Warehouse stock whose `item_catalog` category in `NON_WAREHOUSABLE_CATEGORIES` (`_must_stay_in_inventory()`) moved back to Inventory regardless of slot pressure — safety net for gear landing in Warehouse other ways (manual stash, `.compact()` pulling stack forward sweep never meant to touch), since nothing here ever *places* such item in Warehouse on purpose.
  Each slot moves with `property_match="exact"` so durability-bearing variant not merged with different variant of same `item_id`.
  - **Dock-demand exception** (`_items_demanded_by_active_dock_orders()`): an item still owed by any
    Supply Dock's active order is left in the Warehouse instead — `supply_dock.py` already ships
    straight from a Warehouse via `take_item()`/`total_stock()`, and a bulk Earth Order contract for
    a "deployable" equipment item can run hundreds of units deep, far more than Inventory has slots
    for. Self-contained (own `outpost.buildings("supply_dock")` scan) rather than importing
    `production.py`, which itself imports from this module.

### 2d. Outpost Ore-Assignment & Stock-Target Scaffolding (`lib/outpost_mining.py`)

Phase B of Multi-Outpost Production Network (`TODO.md` Phase 3). Answers "which ores should vehicle stationed at outpost X mine?" and "how much before stopping?" — consumed by Phase C stationed-mining role (§2e). "Which ores" answered **live from Planet Map**, not archive list — every surveyed mineral site gets `"resource.poi_X_Y"` marker whose `.note` names responsible outpost.

- **Marker convention**: `RESOURCE_MARKER_PREFIX = "resource."`, id `resource.poi_{x:.0f}_{y:.0f}`, `icon="resource"`, `color="neutral"`, `label="{Item Name} - {Purity}"` (`_item_display_name()`/
  `RESOURCE_PURITY_LABELS` build it, `_item_id_from_label()` exact inverse). `.note` = responsible outpost id, or `""` when unassigned.
- **`sync_resource_marker(site, outpost_id=None)`** — places/updates one site's marker. `outpost_id=None` keeps current assignment (style-only refresh); pass explicit id (incl. `""`) to change.
- **`auto_assign_new_site(site, range_m=None)`** — call once per freshly-surveyed mineral site (`vehicle_survey.py`'s `scan_and_survey()` does automatically). Only assigns if unassigned, to closest owned outpost within `range_m` (default `resource_assignment_range_m()`, archive key `RESOURCE_ASSIGNMENT_RANGE_KEY = "outposts.resource_assignment_range_m"`, default `200.0`m). Never reassigns assigned site.
- **`reevaluate_unassigned_near_outpost(outpost_id, range_m=None)`** — explicit, **never auto-called** sweep: hands still-unassigned markers in range to `outpost_id`. Re-run (via `sync_resource_markers.py`) after founding new outpost, since CLAUDE.md's Outpost Construction Safety Rule means no automatic "outpost just appeared" hook.
- **`assigned_ores_for(outpost_id)` → `[item_id, ...]`** — read path, called every cycle by stationed-mining candidate builder (§2e).
- **`sync_resource_markers.py`** (project root) — run manually to backfill pre-existing surveys or reassign unclaimed markers after founding new outpost.
- **`stock_target_for(outpost_id, item_id)` → units** — seed-once-then-editable, default `WAREHOUSE_SLOT_CAPACITY = 2000` (one Warehouse slot) first time pair looked up.
- **`RAW_ORE_ITEM_IDS`** — 7 mineable ore item ids (`iron_ore`, `silicon`, `titanium`, `cobalt`, `rare_earth`, `neutronium`, `lead_ore`); **`HOME_OUTPOST_ID = "outpost_home"`**.
- **Standing home ore buffer** (`production.py`'s `get_raw_material_demands()`): every raw ore also gets floor demand `max(0, stock_target_for(HOME_OUTPOST_ID, item_id) - total_stock(item_id))` — taken as **max** with (never added to) production-driven deficit. Not reserved stockpile — Smelter/Supply Dock draw freely. Home-based miners + mining-outpost transporters read same demand function. **Overfill avoidance across concurrent haulers**: hauler debits what it loaded via `mining_reservations.reserve_yield()` (`VehicleCargoMixin._reserve_home_haul()`, keyed `"haul:{vehicle_name}:{item_id}"`, released via `_release_home_haul()` right after delivery) — same in-flight-debit mechanism as concurrent mining trips.

### 2e. Stationed Mining Role (`lib/vehicle.py`, `lib/vehicle_energy.py`, `lib/vehicle_mining.py`)

Phase C of Multi-Outpost Production Network. Rover/Pioneer can treat **any** outpost — not just home — as base.

- **`VehicleController.__init__`'s `home_base` param** (outpost id, or `None` = production/home outpost). Resolved to **live objects once at construction**, cached as `self.home_outpost` (`get_outpost_ref(home_base)`) and `self.home_charging_station` (`find_charging_station(self.home_outpost)`), no re-walking `outpost_network.outposts()` by id per lookup. `get_home_slot_coords()` reads only these two cached fields: station position if found, else outpost's `.coords()`, else `(0, 0)` only if `outpost_network` unavailable at construction. `self.home_base` kept only for identity checks. Trade-off: charging station built at this outpost *after* construction not picked up until next script reload.
- **`unload_cargo(outpost=None)`** — defaults to `self.home_outpost` (cached), so stationed vehicle unloads into own outpost's Warehouse; explicit override exists for Phase D transporter (§2f).
- **`VehicleMiningMixin.build_local_stockpile_candidates(outpost_id)`** — per ore in `outpost_mining.assigned_ores_for(outpost_id)` still under `stock_target_for()`, builds mineral site candidates (same hardness/claim/blacklist filtering as `build_mineral_site_candidates()`) plus requires `outpost_mining.nearest_outpost_id(site.x, site.y) == outpost_id`. Fully independent of home's live demand.
- **`VehicleMiningMixin.run_stationed_mining_loop(outpost_id)`** — thin wrapper around `_stationed_mining_cycle(outpost_id)`: same cycle shape as `run_mining_loop()` (reload resume, cargo/target mismatch detour, claim + drive + mine + return + unload + recharge, release claim right after return), target selection swapped for `build_local_stockpile_candidates()`.

### 2f. Demand-Driven Transporter Role (`lib/vehicle_cargo.py` `run_supply_run_loop()`)

Phase D of Multi-Outpost Production Network — moves ore stockpiled by Phase C stationed miners back to **production outpost** (Nocturna Base). Lives on `VehicleCargoMixin`, shared by Rover and Pioneer.

**Terminology note**: every other vehicle, "home"/"base" = production outpost. Transporter breaks this on purpose — constructed with `home_base=<mining outpost id>` (§2e), so **its `self.home_base`/`self.home_outpost` point at stationed mining outpost, not production outpost** — only delivery leg touches production outpost, via separately resolved ref (`self.get_outpost_ref(None)`, held in variable literally named `production_outpost`, never `home_outpost`).

- **Construction**: `PioneerController(vehicle, home_base=<mining outpost id>)` — Pioneer, not Rover (Rover integrated hold fixed `capacity() == 10`; Pioneer cargo scales with Cargo Rack loadout).
- **`run_supply_run_loop(poll_interval=10.0)`** — no `item_id`: **one load can mix several assigned ores per trip**, decided fresh each cycle. Each cycle:
  1. `_current_supply_items()` — if cargo already aboard (resuming after reload), reads every
     item off `self.vehicle.cargo.stacks()` instead of re-planning.
  2. Else `_plan_supply_load(capacity)` — ranks this outpost's `assigned_ores_for()` by the
     production outpost's unmet demand descending, keeping only ores with stock on hand right now,
     greedily takes `min(unmet demand, stock on hand, remaining capacity)` from each until capacity
     runs out. Empty plan → idle (no preemptive/opportunistic top-off, per CLAUDE.md's
     Demand-Driven Production rule).
  3. **`is_at_base()` check before loading** — drives to stationed outpost first via
     `return_to_base()` if not already there (`take_item()` needs physical presence).
  4. Loads each `(item_id, amount)` via `storage.take_item(self.vehicle.input, item_id, amount,
     outpost=self.home_outpost)`.
  5. Drives explicitly to `self.get_outpost_ref(None)` (production outpost) — **not**
     `return_to_base()`.
  6. `unload_cargo(outpost=production_outpost)` — already sends each cargo stack to its own
     destination independently.
  7. **Recharges fully at production outpost** (`recharge_at_station(target_level=1.0)`) before
     heading back — lets the return leg run at full throttle (`cruise_throttle=1.0`) without
     `drive_with_recharge()` needing an intermediate stop.
  8. `return_to_base()` to stationed outpost, recharges there too.

  **Since generalized into `run_haul_loop()` (§2g)** — every thin entrypoint script reaches it via unified `PioneerController.run(dest_outpost_id=...)` entrypoint (§2b).

### 2g. Generalized Hauler + Reagent Resupply (`lib/vehicle_cargo.py` `run_haul_loop()`, `lib/outpost_reagents.py`)

§2f ore-hauler and Bio Lab reagent-hauler same shape: **transporter always stationed at `self.home_base` (SOURCE), delivers to explicit DEST**. Ore-hauler: source = mining outpost, dest = home (`None`). Reagent-hauler: source = home (`home_base=None`), dest = coastal outpost. Every thin entrypoint calls `PioneerController.run(dest_outpost_id=...)` (§2b), which detects hauler role (no constructor/sonar/drill mounted), forwards to `run_haul_loop(dest_outpost_id, poll_interval=10.0)` — `dest_outpost_id` alone disambiguates role (`None` = ore-hauler; other id = remote outpost's Bio Lab = reagent-hauler).

- **`_outpost_haul_demand(dest_outpost_id)`** (module-level) computed fresh each cycle: `None`/home → `production.get_raw_material_demands()`; other outpost id → `outpost_reagents.get_outpost_reagent_demand(dest_outpost_id)`.
- **`_plan_haul_load(capacity, dest_outpost_id)`**: when source is home (`self.home_outpost.is_home`, plain `bool` property on `OutpostRef` — **not** method, unlike same-named method on full `Outpost` component from `get_component()`), candidate "available" = full deficit regardless of stock on hand (home shortfall always buyable at Shop); elsewhere, real stock on hand = hard ceiling.
- **`_load_haul_plan()`**: buys shortfall **one Inventory-stack at a time** (`storage.inventory_stack_size()`), immediately `take_item()`-ing each bought stack into cargo before next buy — bounds *transient* Inventory footprint, not total planned volume (already capped by cargo capacity). Only triggers when source is home.

**`outpost_reagents.py`** mirrors `outpost_mining.py` seed-once-then-editable convention (`assigned_reagents_for(outpost_id)`, `reagent_stock_target_for(outpost_id, item_id)`, `get_outpost_reagent_demand(outpost_id)`), but per-reagent, not one flat constant (reagent prices span 1cr to 1,000cr):

```python
DEFAULT_REAGENT_STOCK_TARGETS = {
    "alkaline_buffer": 100, "cryo_solvent": 100, "protein_marker": 60,
    "chelating_agent": 20, "enzyme_solution": 10,
}  # dial these up as credit budget allows; FALLBACK_REAGENT_STOCK_TARGET = 100 covers any
   # reagent id not yet in this dict (e.g. a future game update)
```

Deficit math uses `storage.warehouse_stock(item_id, outpost)`, **never** `storage.total_stock()` — `total_stock()` always adds home Inventory count regardless of `outpost`, over-reporting remote outpost reagent stock by whatever sits untouched at home (where Shop delivers). `lib/bio.py`'s `local_stock(item_id, outpost)` picks between the two via `is_home_outpost(outpost)` (reads `OutpostRef.is_home`, same property-not-method distinction).

`lib/bio.py`'s `local_sibling(outpost, type_id)` replaces hardcoded same-pipeline instance ids with live `outpost.buildings(type_id)` lookup (first match, resolved) — needed because Bio Lab's `take_from()` requires its Collector at *same* outpost. No caching — resolved fresh per call, since sibling building may not exist yet at controller construction.

### 2h. Drone Energy Budgeting Detail (`lib/drone_energy.py` `DroneEnergyMixin`)

`DroneController` base (`lib/drone.py`) with scout (`lib/drone_scout.py`), miner (`lib/drone_mining.py`) and hauler (`lib/drone_hauler.py`, §2j) roles, plus `lib/drone_service.py` (charging/refuelling/rescue) and `lib/drone_depot.py` (cargo station). Drones = **fresh hierarchy, not `VehicleController` subclass** — no `.drive`/`.nav`, no terrain/stall handling, route-based `go_to(x, y)`/`go_to_station(name)`/`go_to_drill(name)` not blocking drive loop, simpler linear power/speed model — but `DroneController` follows same mixin-composition philosophy as `lib/vehicle.py`. Role from mounted modules: Bio Scanner → scout, Bio Extractor → miner, neither but Cargo Pods (`cargo.capacity() > 0`) → hauler.

- **Linear travel model**: full throttle = **5 Wh/h** at **300 m/h**; both scale with throttle (speed linear, burn quadratic), collapsing to `Wh/meter = DRONE_WH_PER_METER_PER_THROTTLE
  (=5.0/300.0 ≈ 0.01667) × throttle` — structurally like Rover flat model, different constant, **no** per-drone/cargo/module term. Standalone `drone_wh_per_meter_at_throttle(throttle)` / `drone_rescue_wh_per_meter()` module-level functions let `lib/drone_service.py` reuse same rate cross-script. `max_safe_throttle_for_leg()` solves safe-throttle bound **directly linear** (`t <= available_for_leg / (distance × rate × SAFETY_MARGIN_MULTIPLIER)`). Drone's own `range_remaining()` = ground truth; formula for planning only.
- **Engine auto-detect** (`detect_engine()`, at `__init__` and again at `run()` after a possible re-equip): own `DroneRef.engine` from `fleet.drones()`, else probe `oil_tank.capacity()`/`battery.capacity()` (the wrong powertrain raises `ReferenceError`; `hasattr` is useless since both attributes always exist), else `"electric"`. Also caches `is_plated()`. Every energy figure in the mixin is in the drone's own unit via `ENGINE_PROFILES`: **electric** `per_meter = 5/300` Wh/m, 300 m/h, reserve `MIN_EMERGENCY_RESERVE_WH`; **heli** `per_meter = HELI_T_PER_METER_PER_THROTTLE = 5/900` t Oil/m (≈ 5.6 t/km at full throttle), 900 m/h, reserve `HELI_MIN_EMERGENCY_RESERVE_T = 5.0` t. Shield Plating × `PLATING_BURN_MULTIPLIER = 1.5`. `get_battery()` keeps its name but reads the oil tank on a heli; `energy_unit()` gives `"Wh"`/`"t"` for logs; telemetry adds `engine`/`unit`. Heli drones skip **dry** drone_service stations (`heli_capable_services()`, shared with `lib/drone_service.py`): usable = `oil_in.level() >= SERVICE_MIN_OIL_T = 10.0` t (buffer max 100 t) **or** `flow_rate() > 0` (refilling now); none usable → wired-but-dry stations ("wired" via `connections()`, which also sees a link the pump declared, unlike `connected_to()`); none wired → all. Applies to refuel, idle parking, return floors and hauler fuel budgets. `flight_timeout_ticks()` uses the engine's speed; `fly_to_station()`/`fly_to_drill()` default timeout now scales with distance when coords are known (was a flat 1500 ticks, too short for long heli legs). `STRANDED_STATUSES` includes `stalled_no_oil`. **Route-call burn** (confirmed live on heli): hovering with no route costs nothing, but every `go_to()`/`go_to_station()`/`go_to_drill()` call costs a small minimal burn, even for a 0 m leg. So never re-issue a route needlessly: `fly_to()` returns early when already within precision, `fly_to_station()`/`fly_to_drill()` return early when `current_station()`/`current_drill()` already equals the target, and `drone_service.py`'s low-fuel nudge sends `go_to()` once per episode (`nudge_commands`, cleared on dock/rescue) instead of every 1.5 s cycle. The per-call amount isn't measured yet, so budgets don't model it (the safety margin and reserve cover it).
- **`MIN_EMERGENCY_RESERVE_WH = 4.0`** (vs. `VehicleEnergyMixin`'s `8.0`) — electric drone batteries much smaller. `SAFETY_MARGIN_MULTIPLIER = 1.05` unchanged.
- **`LAUNCH_MIN_SOC = 0.80`** — launch hysteresis (`hold_for_launch_charge()`): before picking a new mission (scout and miner loops, after cargo/recall handling), a drone below 80% charge docks at its drone_service and stays until ≥ 80%. Floor only: a target needing more still falls to the existing "none reachable → top up to 98%" branch, so far sites aren't lost. Fixes drones launching at ~26% right after unloading (depot/service share coords, so the comfortable-return trigger is ~0 there). Reserve deliberately kept at 4 Wh so the round-trip budget doesn't shrink max range.
- **Pinned home** (`resolve_home_depot()` / `get_home_depot()` / `get_home_service()`): each drone pins a home, either an **outpost pool** (any Drone Depot in that outpost) or one **hardwired** depot — priority (1) `HOME_DEPOT` script variable in `drone.py` entrypoint (outpost id = pool; depot id/display name = hardwired — mirrors pioneer's `HOME_BASE`), (2) archived pin in shared dict `drone.home_depots` (same matching), (3) first run: pool of nearest depot's outpost. Pin is persisted, so a restart mid-field doesn't re-home to whichever depot is nearest there. With a pool, `get_home_depot()` re-picks per call via `_pick_free_depot()`: already-docked depot, else free bay first (live `get_component(depot_id).bay_count()/bays_occupied()`), then `prefer_id` (the depot already queued at — avoids churn when all full), then free cargo slots, then nearest. `fly_to_station()` returns early on `waiting_bay`, and `_return_and_unload()` then re-picks once and transfers to a free sibling (same coords, no flight cost), so drone A never waits on depot A while depot B is empty. Unload (`_return_and_unload()`) and recall use the home depot; if it's removed, `get_home_depot()` re-homes via `DroneController.resolve_home()` (which also refreshes `home_outpost`/`home_biome`). **Home service** = drone_service in the home depot's outpost (else nearest to home depot); used by `calculate_trip_energy()` (return leg), `energy_needed_to_return_comfortably()`, and `return_to_service_for_charge()` (falls back to nearest service when home is out of reach on current battery). **Nearest** service still used for hard survival floor `return_floor_wh()` (in-flight abort) and `max_safe_throttle_for_leg()`. `discover_drone_buildings()` returns `{"id", "name", "coords", "outpost", "outpost_id"}` dicts — `"outpost"` field is how `resolve_home()` sets `self.home_outpost`/`self.home_biome`, since **drone has no `.outpost` property** (confirmed against `docs/models/vehicles_and_modules.md`): home depot's outpost first, fallback nearest drone_service's outpost, then network home outpost. `return_to_service_for_charge()` checks "already there" by `current_station() == service id`, not coords — depot and service often share coords, so coord check made a drone at its depot never dock to charge (bug fixed 2026-09-23).
- **Depot sizes = three typeIds**: `DRONE_DEPOT_TYPE_IDS = ("drone_station", "drone_station_medium", "drone_station_large")` (`outpost.buildings()` matches one exact type, so discovery loops over all three). Script-slot/instance prefixes differ again: `drone_station_N` / `drone_station_med_N` / `drone_station_lrg_N` (decompiled simworker machine catalog; large confirmed live) — `scripts/4_controlpanel/drone/drone_station_med.py`/`drone_station_lrg.py` are thin copies of `drone_station.py` so scripts_sync matches them. Same tuple in `logistics_requests.py`, `essence_liquifier.py` and `ArchiveCleaner.MACHINE_STATUS_KEYS`. `discover_drone_depots()` hides Depots a fleet upgrade is retiring (§2k).
- **`DRONE_DEPOT_TYPE_ID = "drone_station"`** (bug fixed 2026-09-22, was `"drone_depot"`) — in-game building `typeId` follows item/error-code naming (`drone_station_kit`, ship_computer.md's `"missing_drone_station"`/`"drone_station_full"`), not doc-page slug or display name "Drone Depot". Wrong constant made `outpost.buildings()` match nothing, so `get_all_drone_depots()` silently always empty and every depot-dependent call (home_coords/home_outpost resolution, `_return_and_unload()`, recall) fell back to `(0.0, 0.0)` with no depot id — caught via drone recall visibly flying toward world origin. See `docs/components/drone_depot.md` added scripting note. `DRONE_SERVICE_TYPE_ID` had no such mismatch.
- **No "biosphere region"** — per-outpost + per-biome: sample only locally processable (Essence Liquifier) at outpost where dropped off, and only if native to that outpost's biome (`nocturna.life_form_biome(item_id) == outpost.biome`). Miner drone filters `journal.biomass_coords()` candidates to samples native to home outpost biome (`is_home_biome_sample()`). Biosite whose tile has **mixed** biome sample set skipped entirely (`PortableBioExtractor.extract()` takes no species arg, can't pull only home-biome sample). Cross-outpost ferrying of foreign samples = deferred TODO.md Phase 4 item.
- **Exclusive biosite claims, not shared yield-debit reservations** — biosite extraction exclusive-WITH-COOLDOWN (`journal.is_ready(x, y)`/`next_ready_at(x, y)`, `BioExtractionResult.status == "cooling"` only after full depletion), fundamentally different from mineral mining's shareable sites (§2b). `lib/drone_claims.py`'s `claim_biosite()`/`refresh_biosite_claim()`/`release_biosite_claim()` reuse `vehicle_claims.py` claim/heartbeat/staleness shape (`CLAIM_STALE_TICKS = 36,000`) but own archive key (`biosite.claims`) — **do not** route biosite selection through `mining_reservations.py`. Miner target order: (1) `journal.is_ready(x, y)` cooldown gate (read-only, before any claim); candidates sorted by **request score** first (§2i: per home-biome sample still on the site whose life form has a network deficit in `logistics_requests.network_deficits()`, `RARITY_REQUEST_WEIGHT = {"common": 1, "uncommon": 2, "rare": 4}`; 0 everywhere without requests), then **partially-drained** (`0 < remaining_tons < tons` — cooldown only starts once a site is empty, so finishing a half-drained site beats opening a fresh one), then nearest; (2) exclusive claim attempt; (3) scout's separate bounded "confirmed-empty POI" cache (`SCOUTED_EMPTY_POI_KEY`, coord → tick scanned, capped at `SCOUTED_EMPTY_POI_MAX_ENTRIES = 2000`), kept as separate small archive-key wrapper from `biosite.claims`.
- **Resumability**: `drone.mission[<name>]` persists in-progress target (mirrors `vehicle.mission[<name>]`). Drone `go_to()` fire-and-forget, **cancelled by script restart** (unlike rover's persistent `drive_to()`) — on resume, `run_miner_loop()` re-validates claim, checks `position()`/`current_station()`, **re-issues** `go_to()`. `extract()`/`scan()` survive restart transparently — only flight leg needs re-issue. While a pre-restart `extract()` still runs, every `go_to*()` is rejected `"busy"` (logged at debug, not warn). `_adopt_interrupted_extraction()` (run once at miner-loop start) uses `detect_role()`'s extract probe (`role_probe_status`): `"busy"`/`"ok"` means hovering mid-harvest, so it claims the current tile as the mission even without a saved one, and the resume branch finishes it. `_return_and_unload()` returns False on failure and callers sleep before retrying (previously a tight retry loop).
- **Idle-to-recharge fallback**: `energy_needed_to_return_comfortably()` alone only covers "in danger where parked" case. Drone can be above that floor (safe to sit) yet below what any candidate's `calculate_trip_energy()` round trip needs — `IDLE_OUT_OF_RANGE` tick, not low-battery, so previously never sent home, idled forever (bug fixed 2026-09-22). `run_scout_loop()`/`run_miner_loop()` now call `DroneEnergyMixin.return_to_service_for_charge()` (shared, dock-if-not-already-there) when cycle finds candidates but none reachable AND charge below 98%.
- **Bay-full queueing** (Drone Depot only): `go_to_station()` itself queues drone in `"waiting_bay"` when Depot full (game-engine behavior, drone.md) — no script-side reservation needed for wait. `fly_to_station()` (`drone_navigation.py`) polls `current_station()` (documented authoritative arrival check) up to `timeout_ticks` (default scales with distance via `flight_timeout_ticks()` when target coords are known, min 1500 ≈ 150 real seconds); caller's raw-`fly_to()` fallback on timeout does NOT enter bay queue (only `go_to_station()` does), so self-healing only via outer loop's next retry, not real dock. `_return_and_unload()` skips that fallback while `status() == "waiting_bay"` (publishes `WAITING_DEPOT_BAY`, retries) — fallback would "arrive" instantly at same coords and unload undocked into nothing. **Depot slot-full** (unload `target_full`, distinct from bay-full): `_return_and_unload()` leaves berth, flies to drone_service to charge, and sets a backoff of `DroneMiningMixin.DEPOT_FULL_RETRY_TICKS = 600` (~60 s); `run_miner_loop()` holds the drone docked at the service (`WAITING_DEPOT_SPACE`) until it expires, instead of re-docking at the full depot every few seconds. A roleless (bare/unequipped) drone deliberately **stays docked** (needs berth to be equipped), so it blocks a 1-bay Depot until equipped.
- **`leave_station()`** (`drone_navigation.py`): releases current berth via `undock()` — keeps exact position/cargo/modules, costs no flight energy, unlike re-issuing `fly_to()` to same coords. `_return_and_unload()` (`drone_mining.py`) calls it right after every Depot unload attempt (success or full), so miner frees bay for waiting peer instead of squatting until next mission moves it. No-op on `"not_docked"`/`"busy"` (latter protects active Drone Service Station charge/rescue job, which must keep control — never call on charging drone).
- **Recall** (`lib/drone_claims.py`): mirrors `vehicle_claims.py`'s `RECALL_KEY` shape exactly, own key `drone.recall` `{drone_name: True}`. `is_drone_recalled()`/`set_drone_recalled()` module-level read/write, toggled via `panel_5.py` DRONE FLEET card switch. Unlike ground-vehicle recall (returns to charging-station "base"), drone recall targets its home **Drone Depot specifically, never drone_service** — `couple()`/`uncouple()` (module re-equip) both require docking at operational Depot (drone.md), and recall's point is letting operator swap modules. `handle_recall_if_active()` abandons biosite claim/mission, flies to Depot, and — deliberately opposite of `leave_station()` — stays docked rather than releasing berth, since re-equip needs berth held. Checked near top of `run_miner_loop()`/`run_scout_loop()`, right after stranded check (stranded drone needs `drone_service` rescue regardless of recall — can't self-navigate) but before mission-resume/target-selection, so active mission abandoned promptly.
- **`lib/drone_service.py`** structurally mirrors `lib/charging.py`: docked charge queue, fleet-wide stranded/scrambled detection via `fleet.drones()` (stranded predicate also includes `"scrambled"`), nearest-station coordination (`is_nearest_station_to()`), proactive same-outpost nudge for low-battery field drone (`order_return_to_service()`). Engine-aware: docked electric → `charge()`, docked heli → `refuel()` (engine probed by `battery.percent()` raising); `no_oil` warns once with a hint whether `oil_in` is wired. For a heli, only oil-holding stations (`station_refs_for()`) compete in `is_nearest_station_to()`, are nudge targets and set the return floor, so a dry station never rescues a heli into an empty refuel queue. Rescue/nudge floors use `fuel_of(drone_ref)` (`battery_*` or `oil_*` DroneRef fields) and `drone_rescue_energy_per_meter(engine)` (assumes plating, conservative); heli reserves `RETURN_EMERGENCY_RESERVE_T = RESCUE_EXTRA_RESERVE_T = 2.5` t. Heli rescue carries the drone home to the refuel queue (game behaviour). Station script's cross-script `drone.go_to()` call works despite `drone.md`'s `(self only)` tag — `(self only)` documents intended caller convention, not engine-enforced restriction (see `lib/charging.py`'s `order_return_to_station()` for same already-relied-upon pattern with `nav_module.md`).
- **`lib/drone_depot.py`** mostly passive — cargo moves via drone's own `cargo.load()`/`cargo.unload()` while docked. Ports **don't** drain passively: declared link moves nothing until someone calls `take()`/`send()`, and Liquifier's own controller does the `take()` (§1h). Controller jobs: (1) one-time idempotent `self.output.connect(...)` wiring to outpost's Essence Liquifier, only when unambiguous (exactly one same-outpost Liquifier — else logged, left for manual wiring); (2) `stage_life_forms()`: every life form (`nocturna.life_form_biome()` not None) sent Depot → local Warehouse, capped at `LIFEFORM_BUFFER_SLOTS = 1` Warehouse stack per form per outpost (slot capacity read from `slots()`, fallback `WAREHOUSE_SLOT_FALLBACK_UNITS = 2000`). Tops up a slot already holding the form first; opens an empty slot only while `WAREHOUSE_FREE_SLOTS_KEEP = 1` more stay empty (room for ore/cargo). Full stack → rest stays in the Depot for the Liquifier. Keeps the 50-unit Depot free for drones, gives the Liquifier a buffer and pull haulers a `take()` source; re-declares the Liquifier link next step since `output` now points at the Warehouse; (3) `drain_freight()`: every **non-life-form** stack → local storage via `storage.drain_port_to_storage(include=, allow_partial=True)` (Warehouse, or Inventory at home; trickles into partial room). Makes the Depot usable as a hauler endpoint — its 50/100/200-unit stockpile is tiny next to a Large hauler's load, so the drone unloads in rounds while this drains; the controller polls every `FREIGHT_POLL_INTERVAL = 2.0` s while freight sits there or any drone is docked (else 10 s); (4) periodic telemetry publish (`drone_depot.status`).

### 2j. Floating Drone Hauler (`lib/drone_hauler.py` `DroneHaulerMixin`, phase 1: drills → Depots)

Drone with Cargo Pods and no bio module. **No home Depot**: each cycle picks the best job network-wide, refuels at whichever drone_service is nearest when needed, and parks at the nearest service when idle (never holds a Depot bay). Hard limits (drone.md / `DroneCargo`): `cargo.load()` only at a docked Drone Depot, a field Mining Drill or a Lead Cask; `cargo.unload()` only into a docked Depot (or Lead Cask) — **no direct Warehouse/Inventory access**. One material per Cargo Pod (100/250/500); Large chassis = 1 thruster + 5 modules. Phase 1 = drill pickups only (no staging needed); outpost-Depot pickups need Depot-side staging (phase 2, TODO.md).

- **Demand** (`_haul_destinations()`): every outpost with a Depot → `logistics_requests.outpost_deficits(live=True)` (net of in-flight pickups), plus at home per item max with `get_raw_material_demands()` (net of `mining.reserved_yield`) — same demand the Pioneer pull hauler (§2i) reads, so they share it.
- **Sources** (`_drill_sources()`): advertised drills (`drill.status`) with a known `drill.positions` entry, net of `reserved_from()`. Unlocated drills skipped (warned once).
- **Plan** (`_plan_haul_job()`): per destination a nearest-neighbour drill chain (largest deficits first, per-item room capped by `cargo.space_for()`), up to `HAUL_MAX_STOPS_PER_TRIP = 3`, chained stops only if direct ≤ `HAUL_CHAIN_MAX_DETOUR_RATIO = 0.75` × via-destination. Skipped below `min(HAUL_MIN_LOAD_UNITS = 50, total deficit)`. Score = units / (route m + `HAUL_TRIP_OVERHEAD_M = 300`); best wins. **Fuel budget** (`_route_fuel()`): route legs at cruise throttle + nearest-service-from-destination at the speedmode floor, × `SAFETY_MARGIN_MULTIPLIER` + `emergency_reserve()` — "back" is any service, not a home. Job over a full tank → dropped; over what's aboard → `_refuel()` at nearest service first, then re-plan.
- **Coordination**: planned units reserved per drill in `logistics.pickups` (dest + source), home-bound ore also in `mining.reserved_yield` (`haul:<drone>:<item>`); both corrected to loaded amounts, released after full delivery. Mission `drone.mission[<name>] = {"kind": "haul", "dest", "target_key": None}` (no `target_key` → biosite `load_mission()` ignores it).
- **Deliver** (`_deliver()`): free Depot of the destination (`_pick_free_depot()`, waits ≤ `DEPOT_BAY_WAIT_S = 60` s in `waiting_bay`), unload rounds every `DEPOT_UNLOAD_RETRY_S = 2` s while the Depot drains (§2h), give up after `DEPOT_UNLOAD_TIMEOUT_S = 300` s → leave bay, keep cargo/mission/reservations, retry next cycle. Cargo aboard at loop start (restart, failed delivery) → `_deliver_cargo_aboard()`: saved mission dest, else Depot outpost with most demand for the cargo, else home, else nearest Depot; reservations re-asserted from what's physically aboard.
- **Refuel** (`_refuel()`): fly to nearest (oil-fed, for heli) service; its station script queues the charge/refuel; wait until ≥ `REFUEL_FULL_LEVEL = 0.98`, or ≥ needed once the service job ended, ≤ `REFUEL_TIMEOUT_S = 900` s. Launch floor `LAUNCH_MIN_SOC` only applied while already docked at a service (free top-up).
- Recall uses the pinned home Depot as usual (`HOME_DEPOT` otherwise ignored for haulers). Stub-tested only.

### 2k. Fleet Hardware Upgrade (`lib/fleet_upgrade.py` coordinator + `lib/drone_upgrade.py` drone side)

Background task in headless `panel_4.py` (every `STORAGE_TICK_INTERVAL`), **gated by `upgrades_active()`** = operator switch on AND mining-drill phase reached (`upgrade_phase_reached()`: any mining drill deployed per `drill_sites.discover_drill_ids()`, same condition as `7_miningdrills/.criteria`; stored once as `fleet.upgrade["phase_reached"]`, monotonic) — earlier, expanding beats upgrading. Switch off → swaps not started yet (Depot `ordered`; drone `ordered`/`requested`/`ready`/`announced`) are cancelled, a parked drone resumes work, orders withdrawn; swaps past the point of no return still finish. In-place module upkeep obeys the same gate. Swaps Drone Depots and miner/hauler drones for the **best unlocked tier** (Fabricator recipe unlocked, or item already in Inventory). **One swap at a time fleet-wide, Depots first**; within a kind the **lowest tier first** (small → large directly; Medium only deployed while Large is locked). Scouts never touched (chassis or modules). Operator switch + status line on `panel_5.py` (`fleet.upgrade["enabled"]`, default on). All state in one archive dict `fleet.upgrade` (layout in `drone_upgrade.py`, plus `phase_reached`); each coordinator pass advances at most one state and writes back → restart-safe. Undeploy refused `MAX_UNDEPLOY_ATTEMPTS = 5` times → entry `blocked`, machine back in service (operator deletes the entry to retry).

- **Depot swap**: `ordered` (kit → `fabricator.upgrade_orders`, wait for it in Inventory) → `deploying` (snapshot of same-type Depots at the outpost, so a restart adopts an already-deployed one instead of deploying twice; `computer.deploy(kit, outpost)`; old id added to `retiring_depots`) → `attach` (`run_control.start(new)` retried until `drone_depot.status[new]` appears) → `draining` (old `bays_occupied()==0` and `slots_used()==0`; a retiring Depot's own script drains **everything**, life forms included, `drain_everything()`) → `undeploying` (stop script, `computer.undeploy()`; kit back in Inventory, kept) → `renaming` (`computer.rename(new, old display name)` so name-based `HOME_DEPOT` keeps working; `drone.home_depots` pins old id → new id) → done. `duplicate_outpost_machine`/`deploy_limit` → `blocked`.
- **Drone swap**: `ordered` (chassis → upgrade order) → `requested` → drone answers at the top of its loop (`handle_upgrade_request_if_active()`, after recall): finishes cargo/claimed target first, charges to `UPGRADE_MIN_SOC = 0.98` at its drone_service, docks at its home Depot, writes `ready` + its script variables (`params`: `HOME_DEPOT`/`CRUISE_THROTTLE` overrides) and holds (`UPGRADE_HOLD`) → `announced` (waits `ANNOUNCE_SAVE_WAIT_TICKS = 1800` so the announcement reaches the save file before the new slot exists — autosave ~30 s real) → `swapping` (re-verify docked at a Depot + cargo 0 via `fleet.drones()`/`get_component(id).cargo`; stop, undeploy → modules back to Inventory; `deploy(chassis, outpost)` or adopt a new drone of that kind not in the pre-swap snapshot; write `lineage[new_id] = {from, role, engine, kind, params, fitted: False}`; move `drone.home_depots` pin, drop `drone.recall`/`drone.mission`/`drone.loadouts`/`fleet.status`/upgrade-order entries of the old id) → `attach` (start retried until `fleet.status[new]` appears) → `fitting` → done when `lineage[new].fitted`, then `computer.rename(new, old display name)` (`old_name`, captured at `ordered`). Candidates need role `miner`/`hauler` in `fleet.status` (`DroneController.role`, now published) and a heartbeat ≤ `DRONE_ALIVE_TICKS = 600` old.
- **New chassis fitting** (`fit_loadout_if_new()`, `DroneController.run()` loops it every 30 s **before** `detect_role()`, which refuses a bare drone): couples thruster (slot 0, from `lineage.engine`), then `LOADOUTS[role][kind]` from Inventory, best tier present; empty slots ordered. `fitted` once thruster + energy + (extractor for miner / Cargo Pod for hauler). Replacement drones also inherit `params` for any script variable left at `None` (`inherited_params()`), so a hand-pasted default script behaves like the old drone.
- **`LOADOUTS`** (one category per module slot; energy = `battery_pack` electric / best `oil_tank_*` heli; cargo = best `cargo_pod_*`; role = `portable_bio_extractor`): miner small `role, energy` · medium `role, energy, cargo` · large `role, energy, energy, cargo, cargo`; hauler small `energy, cargo` · medium `energy, cargo, cargo` · large `energy, energy, cargo, cargo, cargo`. Module slots `MODULE_SLOTS = {small: 2, medium: 3, large: 5}`.
- **In-place module upkeep** (`maintain_modules_at_depot()`, right after a successful unload while docked and empty — `drone_hauler._deliver()`, `drone_mining._return_and_unload()`): Cargo Pod / Oil Tank → better unlocked tier once in Inventory (else ordered under the drone's id); empty slots filled with whatever category `LOADOUTS` still lacks. **Engine type never changes** (electric → heli waits for an oil-distribution check, TODO.md). A drone has no `modules()`, so each keeps a slot record `drone.loadouts[id] = {kind, slots: {"0": thruster, "1": module|None, ...}}`; without one it surveys once (`_discover_slots()`: uncouple each slot, identify the module by Inventory gain polled `SERVICE_POLL_TRIES = 10` × `SERVICE_POLL_S = 0.5` s, couple it back).
- **Drone hardware stays in Inventory**: `storage.INVENTORY_ONLY_ITEM_IDS` (kits, chassis, thrusters, pods, tanks, battery pack, bio modules, plating) are never warehoused and are reclaimed if found in a Warehouse — `deploy()`/`couple()` take from Inventory only.
- **Script attach**: scripts can't attach scripts (`run_control.apply_variant()` needs an operator-saved variant, and variants don't carry across drone sizes — TODO.md). `devtools/scripts_sync.py` fills the new slot (§9: replacement drones get the old drone's params without prompting); the coordinator's `run_control.start()` retry starts it even without `--auto`.

### 2k-1. Warehouse → Large Warehouse Upgrade (`lib/warehouse_upgrade.py`, headless `panel_6.py`)

Same gate as §2k (`panel_5.py` switch `fleet.upgrade["enabled"]` + mining-drill phase), plus `research_high_bay_warehousing` unlocked and credits ≥ Large Warehouse price (Shop catalogue, fallback `LARGE_PRICE_FALLBACK = 60000`) + `WAREHOUSE_UPGRADE_CREDIT_RESERVE = 100000`. **One swap at a time network-wide**, `SWAP_RATIO = 2`: two Warehouses at one outpost → one Large Warehouse (10 slots/20k → 15 slots/30k; fewer buildings for Auto Feeder consumers to walk). Outpost with the most plain Warehouses first; there, the two emptiest (`total()`). A lone leftover Warehouse stays. State in `fleet.upgrade["warehouse_swap"]` (status line `fleet.upgrade["warehouse_status"]`), restart-safe.

- `buying` (`shop.buy("large_warehouse")`, skipped if one is in Inventory; snapshot of the outpost's Large Warehouses) → `deploying` (`computer.deploy("large_warehouse", outpost)` or adopt a new one not in the snapshot; going over the outpost building count is accepted, it's brief) → `draining` → done. States run **back to back in one pass** (no sleep between buy, deploy and drain start): a freshly deployed empty Large Warehouse is the least-full store, so other unloaders and `panel_4.py`'s Inventory rebalance fill it within seconds (seen live). Refused deploy (`deploy_limit` etc.) or undeploy refused `MAX_UNDEPLOY_ATTEMPTS = 5`× → `blocked`; operator deletes `warehouse_swap` to retry. `TRANSIENT_UNDEPLOY_STATUSES = ("inventory_full",)` (no Inventory room for the returned kit) never count as attempts: the swap waits, and a swap blocked by one of them resumes by itself. Switch off only cancels a `buying` swap with nothing bought yet.
- **Greedy drain, no blacklist**: each old Warehouse is emptied with back-to-back `transfer_to(new, item, ≤ DRAIN_CHUNK_UNITS = 500, properties=exact)` calls, then undeployed immediately and its kit sold (`shop.sell("warehouse", n)`; only the kits this swap got back, counted in `to_sell`). The old Warehouse's feeder stays busy nearly the whole time, so other consumers' `take_item()`/unloads fall through to another store via their existing `"busy"` handling — nothing else in the codebase checks a retiring list. Stock that slips in between two transfers is drained on the next pass (`undeploy()` answers `cargo_present`). Target = new Large Warehouse, else any non-retiring Warehouse/Large Warehouse at the outpost with `space_for > 0`. `"busy"` → retry after `BUSY_RETRY_S = 0.2` s, at most `MAX_BUSY_RETRIES = 50` in a row per chunk; `DRAIN_MAX_IDLE_PASSES = 5` passes with nothing moved → give the step back.
- **Why its own panel**: feeder ~2.5 ticks/unit (§2c) → a full pair blocks tens of game minutes; `panel_4.py` grid supervision can't wait, and Warehouses have no script slot. `panel_6.py` idles `IDLE_SLEEP_S = 3` s between passes. Status line printed (info) whenever it changes beyond its numbers; per-chunk moves, target fallbacks and undeploy answers at `debug()`.
- Known gap: `panel_4.py`'s `consolidate_cross_warehouse_stock()` (`compact()`) could in principle pull a stack back into a retiring Warehouse between two drain transfers; harmless (drained again), just slower.

### 2i. Pull Logistics + Reverse Hauler (`lib/logistics_requests.py`, `lib/vehicle_cargo.py` `run_pull_loop()`)

Generic "bring X to outpost Y" demand. Requester publishes wants. Supply ("free stock"): outposts are read live (`outpost_free_stock()`, no per-outpost script), field Mining Drills advertise via `drill.status` (§1j).

- **Requests** `logistics.requests` (§4): `set_requests(outpost_id, requester, {item: (target, have)})` replaces that requester's entries; entries older than `REQUEST_STALE_TICKS = 3000` ignored/pruned (dead requester can't pin stock). `outpost_deficits(outpost, live=True)` = target − local stock (`outpost_stock()`: Warehouses + Drone Depots + home Inventory) − in-flight pickups. `network_deficits()` sums published `have`-based deficits (cheap, for drones).
- **Pickups** `logistics.pickups` (§4): `reserve_pickup(..., source_id=)` per planned/loaded item and source (amount 0 drops the entry), `release_pickups(vehicle)` after unloading; stale after `PICKUP_STALE_TICKS = 36000`. Debits both ends: `in_flight(dest)` against the requester's deficit, `reserved_from(source)` against that source's free stock (so two haulers never plan the same units; normal `run_haul_loop()` also subtracts it from its stationed outpost's stock).
- **Free stock**: outpost = Warehouse (+ Inventory if home) − own request target − `reserved_from()`. Drill = advertised `items` − `reserved_from()`.
- **Reverse hauler**: unchanged Pioneer template, hauler role (no role module) with `DESTINATION_OUTPOST_ID` in `PULL_DESTINATION_WILDCARDS = ("*", "any", "%")` → `run_pull_loop()`; `HOME_BASE` = where it parks = where requests are delivered. Per cycle: cargo aboard → re-assert yield debit, deliver home first; else `_pull_deficits()` = per item max(live request deficit, `get_raw_material_demands()` when parked at home) → `_plan_pull_route()`: every source (other outposts + advertised drills) whose free stock covers a deficit tried as first stop, then nearest-neighbour chain from there (`_plan_pull_chain()`), largest deficits first, up to `PULL_MAX_STOPS_PER_TRIP = 3` stops / cargo capacity; best units / (round-trip m + `PULL_TRIP_OVERHEAD_M = 300`) wins (plain nearest-first let a nearby source with 1-unit top-ups shadow far sources holding the real deficit — trip then fell under the minimum forever). Stops after the first only chained if direct leg ≤ `PULL_CHAIN_MAX_DETOUR_RATIO = 0.75` × (prev → home → next), so it never drives past home; skipped stops wait for the next trip. Trip skipped if planned < `min(PULL_MIN_LOAD_UNITS = 10, total deficit)`. Legs via `drive_with_recharge()` (already refuses a leg that can't reach a charging station afterwards); recharge at stops that have a station; unreachable stop → head home with what's aboard (its and later stops' pickup reservations dropped).
- **Plays nice with normal haulers**: planned home-bound amounts are also debited from `mining.reserved_yield` (`pull:<vehicle>:<item>`, corrected to loaded amounts after pickups, released on delivery) — the same debit `run_haul_loop()` and home-demand miners write and `get_raw_material_demands()` subtracts. A normal hauler already bringing 800 ore → pull hauler sees 800 less demand, and vice versa. Demand-bounded: drills are only emptied as far as home actually needs (standing home ore buffer `stock_target_for()` included).
- **Drill location** (`lib/drill_sites.py`): no API exposes it (`MiningSite` has no `has_drill()`/`drill_id()` unlike pumps/caps — dev ticket open). Filled by: (1) **construction** — `PioneerController.execute_construction(..., kind=)` on a finished `mining_drill*` blueprint calls `record_built_drill()`: unresolved drills of that variant (`discover_drill_ids()`: `power_control` grid members + `drill.status`) tried via `input.connect()`, the accepting one pinned to the blueprint position/site (`site_at()`, ≤ `SITE_MATCH_TOLERANCE_M = 3.0`); retried `BUILT_DRILL_DISCOVERY_ATTEMPTS = 3`× 1 s apart; sole unresolved drill assumed if none accepts. (2) **hand seeding** for drills built any other way (Playground write to `drill.positions`). No inference: a drill without a recorded position is skipped (warned once per hauler run). On arrival (`DRILL_ARRIVAL_PRECISION_M = 2.0`) `vehicle.input.connect(drill_id)`; refusal → warning, nothing loaded that stop. Stored in `drill.positions` (§4). Loading via `take_from_drill()`; no recharge at drill stops.
- **Source retention**: `retain_amount(item, outpost_id)` = own request target if this outpost requests it, else, while any other outpost requests it at all (even when topped up — continuous consumers drain again soon), `max(LIFEFORM_STASH_CAP_T = 25, largest remote target)`, else 0. Used by Drone Depot staging (§2h) and Essence Liquifier feed (§1h). Vehicles load from Warehouses only (Depot buffer staging, §2h, puts life forms there).
- **Water Pump salt** (`lib/pump_salt.py`): pumps are field structures on water wells, found via `journal.surveyed_sites("nocturna")` WaterWells with `has_pump()` → `pump_id()` + well `x`/`y` (cached `PUMP_CACHE_TICKS = 3000`). Salt read live from the pump's `output` (`PickupOutputSlot`). Added as `"kind": "pump"` sources only when `salt` is wanted, home pumps included; connect/take reuse `drill_sites.connect_to_drill()`/`take_from_drill()`, arrival precision `PUMP_ARRIVAL_PRECISION_M = 2.0`. Drones can't take it (`not_at_source`).
- **Drones**: request score in miner target order (§2h). Biosites are permanent (35 fixed, 7 per biome, 1–3 forms each, refill at same coordinate after rarity cooldown — docs/guide/biosphere_biomass_tier.md), so a requested rare form is found deterministically via `journal.biomass_coords()`.

---

## 🗺️ 3. Planet Map Biome Colors (player-observed, verify with `nocturna.biome_at(x, y)`)

| Map Color | Biome |
| :--- | :--- |
| Blue (incl. base's slightly-green patch) | `frozen` |
| Green | `coastal` |
| Dark brown / red | `volcanic` |
| Light brown | `geothermal` |
| Purple | `deep` |

---

## 📡 4. Inter-Process Communication & Data Archive

### Signal Bus (`get_component("comms")`)
- **Channel `bio_orders`**: Exchange broadcasts open orders -> Collector adjusts harvest target.
  - Payload: `{"order_id": str, "specimen_id": str, "biome": str, "target_fragment": str, "count": int}`
- **Channel `sample_ready`**: Lab notifies Exchange immediately on sample extraction.
  - Payload: `{"order_id": str, "sample_id": str, "sample_type": str, "lab_id": str}`
- **Channel `system.version_confirmed`**: `panel_1.py` "Confirm New Version" button broadcasts newly-confirmed build hash so every script parked in `validate_game_version()` wakes immediately, no polling — see `lib/version_guard.py` and Data Archive entry below.
- **Channel `luminizer_heartbeat` (retired) / `biome_processor_heartbeat`**: every biome processor controller fires this unconditionally each cycle so `BioLabController._wait_for_luminizer()`-style waits use `comms.wait_broadcast()`, not polling — see §1f/§1g.

### Data Archive (`get_component("notebook")` / `lib/archive.py`)
**Key convention:** one shared dict per concern `{entity_id: value}` via `archive.transaction()`, never one key per entity — archive has fixed key-count cap (CLAUDE.md rule 7). `lib/archive.py`'s `get_entry()`/`set_entry()`/`pop_entry()` read/write one entity's slot (transactions). Remaining per-entity keys below (`biomass_mixer.gate.<id>`, per-grid `power.*:<anchor>`) are legacy, pending consolidation (TODO.md). Retired families go in `ArchiveCleaner`'s `RETIRED_KEY_PREFIXES`; only the cleaner deletes leftovers, never former writers.
- `power.shedding_tiers`: Custom shedding tiers list-of-lists `[[tier1_machines...], [tier2_machines...], ...]` (or `power.shedding_tiers:<grid_anchor>`). Default `DEFAULT_SHEDDING_TIERS` in `lib/power.py` — see §1a.
- `power.shedded`: Active list of machines Power Guard currently shedded — hard-shed (breaker off) most Tier 1 patterns, soft-shed (production paused, power on) Tier 2 `smelter_*`/`fabricator_*` — see §1a. `SmelterController`/`FabricatorController` own `is_shedded()` checks it to pause production.
- `fleet.status`: one shared telemetry dict `{name: {name, state, x, y, wh, level, target, tick}}` for every ground vehicle AND drone (`lib/fleet_status.py` `publish()`, called by `VehicleController`/`DroneController` `publish_telemetry()`). Unchanged payload re-written only as heartbeat, at most every `FLEET_STATUS_MIN_INTERVAL_TICKS = 50` ticks (~5 s); any changed field writes immediately. No reader yet (future fleet panel). Replaces retired per-entity `fleet.status.<id>`/`rover.status.<id>`/`drone.status.<id>` (no reader, so left until `ArchiveCleaner.clean_telemetry()` deletes them; it also prunes entries of vehicles/drones not in `fleet.vehicles()`/`fleet.drones()`).
- `rover.claims` / `survey.claims` (mirrored, legacy + current key): Atomic target reservation dict `{target_key: {"vehicle": id, "tick": tick}}`. Stale after `CLAIM_STALE_TICKS = 36,000` ticks (1 hr) — see `lib/vehicle_claims.py`. No longer exclusivity-gates mineral mining sites (see `mining.reserved_yield` below); still exclusive for survey/POI targets (key prefix `"poi_"`) and construction jobs (key prefix `"build_"`, `PioneerController.construction_claim_key()`, see §2a construction-job-claims entry).
- `mining.reserved_yield`: Non-exclusive in-flight mining yield dict `{reservation_key: {"vehicle": id, "item_id": str, "units": int, "tick": tick}}`, home-demand mine-type missions only. Stale after `RESERVATION_STALE_TICKS = 36,000` ticks (same window as claims) — see `lib/mining_reservations.py`.
- `survey.unsupported_targets` / `rover.unsupported_targets` (mirrored): Hardware-capability blacklist entries (`reason`, `scanner_type`, `scanner_tier`, `hardness_limit`, unlocked researches) — see `lib/vehicle_claims.py`. Populated per-contact from `SonarScanResult.blocked` (`docs/types/fleet_and_vehicles.md` `BlockedContact`: `.x`/`.y`/`.reason`/`.message`), not from `scan()` top-level `.status` — wide/deep sonar sweep covers several "?" contacts at once, `.status` is one verdict for WHOLE sweep (`"ok"` once any contact in range resolves, even if others stayed blocked), so reading only `.status` silently drops every blocked contact unless nothing resolved. `scan_and_survey()` (`lib/vehicle_survey.py`) iterates `res.blocked`, blacklists each contact by own coords. `VehicleClaimsMixin.clear_unsupported_target()` (called by `vehicle_survey.py`/`vehicle_mining.py` on successful resolution) removes archive entries *and* matching `"unsupported.<target_key>"` Planet Map marker directly via `markers.remove()`, so marker vanishes immediately, not lingering until Control Panel "Sync Unsupported" button (`lib/unsupported_markers.py`) next clicked. **`reason == "wrong_scanner"` (bio contact) special-cased**: permanent hardware mismatch, not research/tier gap — ground vehicles never carry `bio_scanner` (drone-only module, `docs/database/equipment_biosphere.md`), so `can_attempt_target()` never true for it; neither `vehicle_survey.py` nor `vehicle_mining.py` calls `clear_unsupported_target()` for it. Deleting entry once drone resolves it would just let next rover/pioneer sonar sweep over coord re-`blacklist_target()` it (sonar re-reports same "?" contact blocked every sweep in range, regardless of archive state) — so entry deliberately kept forever. Instead `unsupported_markers.clear_wrong_scanner_marker(x, y)` (called by `drone_scout.py` right after successful `bio_scanner.scan()`) removes only stale `"Bio Contact"` marker via `markers.remove()`, blacklist entry intact; `update_unsupported_markers()` sync-button path independently skips (re-)placing marker for any `wrong_scanner` entry whose coord `journal.has_scanned()` reports true, so later button press can't replant. Drones otherwise not in this blacklist/marker family — non-bio-contact resolution uses unrelated `scout.empty_pois` fact cache below, never places map markers.
- `heat.optimal_setpoints`: Caching `{thermal_state: best_power}`
- `pressure.optimal_resonance`: Caching `{resonance_state: best_window}`
- `fabricator.manual_orders`: `{item_id: quantity}` ad-hoc Fabricator build requests, edited directly in Notebook (e.g. `{"drone_small": 2}`) — see §2a-1 item 4. Prioritized over other demanded recipes, counted down to 0 (then dropped) as units delivered.
- `fluid_routing.tank_assignments`: `{building_id: fluid_id}` operator-designated Liquid/Gas Tank reservations, edited directly in Notebook (e.g. `{"gas_tank_1": "steam", "gas_tank_3":
  "ammonia"}`), same edit convention as `fabricator.manual_orders` (NOT same eligibility convention — see below) — see `lib/fluid_routing.py` `get_tank_assignments()`/`tank_matches_assignment()`/`tank_is_eligible_target()`. `fluid_id` values use exact vocabulary of `building.fluid()`/`production.FLUID_LATCH_IDS` (`"water"`, `"oil"`, `"steam"`, or biome essence id once Essence Liquifier ships), no separate taxonomy. Exists because generic tank `.fluid()` latch purely content-based, network-blind (`FluidOutputRouter` otherwise picks candidate tanks by building *type* alone, no notion of which of outpost's several non-merged physical pipe networks candidate sits on — see `docs/guide/infrastructure_and_pipes.md` "Service-footprint contacts stay independent" note) — and same latch clears to `""` instant tank drains to 0, so unrelated router could mistake operator's dedicated oil tank for blank up-for-grabs buffer during empty window, stranding its network. Keyed by stable building id so reservation survives empty window, unlike live latch. **Deny-by-default, deliberately**: unassigned, unlatched tank NOT eligible for new connection — `tank_is_eligible_target()` only passes tank with explicit matching entry here, or (zero-config escape hatch keeping every already-working old/simple-save connection unchanged) already-latched `.fluid()` matching what router wants. Tradeoff accepted: brand-new tank (always `fill_pct()==0`, so top-ranked by every router's least-full-first sort) sits idle until operator assigns it — better than silently filled with wrong fluid. `lib/fluid_routing.py` `warn_about_unassigned_tanks()` (called from `FluidOutputRouter.ensure_connection()` and Steam Turbine `ensure_input_connection()`) prints (console + `notify()`) every blocked tank (unlatched AND unassigned) network-wide at most once per `UNASSIGNED_TANK_WARNING_INTERVAL_TICKS=600` ticks (~60s normal speed) — only signal such tank exists, since invisible to every router. Throttle timestamp (`fluid_routing.last_unassigned_warning_tick`) lives in `archive`, not module-level Python global — each deployed machine script importing this Library gets own copy of module state (same "per-script-run" caveat as `production.py` `_WARNED_UNKNOWN_MANUAL_ITEMS` above), so with several Water Pumps/Thermal Caps/Turbines calling in, plain global would print one copy each per interval instead of one shared notice. `production.py` consumer-side `fluid_building_is_viable()` deliberately does NOT consult this registry — tank's own `.fluid()` latch already complete answer to "can it deliver this fluid now."
- `smelter.diag.<smelter_id>`: **retired 2026-09-23**. Leftovers deleted by `ArchiveCleaner.clean_retired_keys()` (`RETIRED_KEY_PREFIXES`, the one place retired key families are purged). Per-step outcome now debug()-only via `log_outcome()`: `shedded`, `no_demand`, `no_ore`, `ore_reserved_for_dock`, `buffer_full`, `fair_share_capped`, `took`, `busy_all_sources` (harmless), `busy_starving` (real lost time), `recipe_switch`, `output_blocked`, `demand_covered_by_peers`.
- `outposts.known_ids`: List of outpost ids headless automation panel's AUTOMATION section already seen — diffed each throttled tick vs `outpost_network.outposts()` to detect newly-founded outpost, auto-trigger `outpost_mining.reevaluate_unassigned_near_outpost()` for it. See §7.
- `control_room.automation_summary`: headless automation panel's one-line result string (grids supervised, new outposts, docks assigned), published each storage tick for `panel_1.py` ALWAYS-ON line — see §7 headless-calculator/UI-card split.
- `biosite.claims`: Exclusive biosite extraction claims dict `{target_key: {"drone": id, "coords", "name", "tick"}}` — own key, distinct from `rover.claims`/`survey.claims`, so ground-vehicle and drone claims never collide. Stale after `CLAIM_STALE_TICKS = 36,000` ticks — see `lib/drone_claims.py` and §2h. **Exclusive**, not shared yield-debit pattern of `mining.reserved_yield` — see §2h note distinguishing two.
- `scout.empty_pois`: Scout's bounded "confirmed-empty POI" cache `{"<x>_<y>": tick_scanned}`, capped at `SCOUTED_EMPTY_POI_MAX_ENTRIES = 2000` (oldest dropped first). Fixed fact about coord, not hardware-capability blacklist like `survey.unsupported_targets` — see `lib/drone_claims.py` and §2h.
- `vehicle.mission`: shared dict `{vehicle_name: {"target_key", "target", "kind", "tick"}}` of resumable ground-vehicle missions — see `lib/vehicle_claims.py` `save_mission()`/`load_mission()`. Legacy per-vehicle `vehicle.mission:<name>` keys are moved into the dict on the owner's first `load_mission()` (a vehicle mid-mission across the deploy still resumes); `ArchiveCleaner.clean_missions()` migrates the rest and prunes entries of vehicles no longer in the fleet.
- `drone.mission`: shared dict `{drone_name: {"target_key", "target", "kind", "tick"}}`, same shape and legacy handling as `vehicle.mission` (legacy `drone.mission:<name>`). See `lib/drone_claims.py` and §2h resumability note (drone `go_to()` cancelled by script restart, unlike rover's persistent drive command, so only flight leg re-issued on resume).
- `drone_depot.status`: shared dict `{depot_id: {name, docked, bay_count, bays_occupied, slots_used, slot_capacity, is_full}}`, published by `lib/drone_depot.py` each step. No reader yet (dashboards). Legacy `drone_depot.status.<id>` purged by `ArchiveCleaner.clean_retired_keys()`; `clean_machine_status()` prunes depots no longer on the network (same for the two keys below).
- `essence_liquifier.status`: shared dict `{liquifier_id: {name, biome, fluid, stall_reason, essence_rate, input_count, last_fed, output_target}}` — see §1h.
- `biomass_mixer.status`: shared dict `{mixer_id: {name, tier, phase, required, active, mixing, biomass_rate, stalled, inputs: {biome: {source, route, level}}}}` — see §1h.
- `biomass_mixer.gate.<id>`: Mixer gate state `{state: "run"|"pause", paused_by_gate, since, reason, given_up: [biome], progress: {biome: {level, tick}}, expected: [biome], levels: {biome: t}, rewire_until: {biome: tick}}` — see §1h. Bounded (≤5 biomes).
- `biomass_mixer.gate_known_liquifiers`: `{liquifier_id: biome}` last seen by the Mixer gate, for new-Liquifier detection across restarts — see §1h.
- `drone.recall`: one shared dict `{drone_name: True}` (not one key per drone), mirrors `vehicle.recall` shape on own key. `is_drone_recalled()`/`set_drone_recalled()` module-level read/write — see `lib/drone_claims.py` and §2h. Recalls to home Drone Depot, not `drone_service`.
- `fleet.upgrade`: one shared dict (`enabled`, `status`, `depots`, `retiring_depots`, `drones`, `lineage`, `warehouse_swap`, `warehouse_status` — §2k-1) for the fleet hardware upgrade — see §2k. Also read by `devtools/scripts_sync.py` straight from the save file (interim, TODO.md).
- `drone.loadouts`: `{drone_id: {kind, slots: {slot_index: module_id | None}}}` — per-drone module slot record (drones have no `modules()`), §2k. Pruned by the coordinator.
- `fabricator.upgrade_orders`: `{requester_id: {item_id: qty}}` — §2a-1 item 5.
- `drone.home_depots`: one shared dict `{drone_name: outpost_id (pool) | depot_id (hardwired)}` of pinned drone homes (not one key per drone). Written by `resolve_home_depot()` in `lib/drone_energy.py`; `HOME_DEPOT` script variable overrides and overwrites the entry. Entries of drones no longer in `fleet.drones()` pruned on every write. See §2h.
- `logistics.requests`: `{outpost_id: {item_id: {"target", "have", "by", "tick"}}}` pull requests — see §2i. Entries stale after `REQUEST_STALE_TICKS = 3000`.
- `logistics.pickups`: `{"pull:<vehicle>:<dest>:<item>[:<source>]": {"vehicle", "dest", "source", "item_id", "units", "tick"}}` in-flight reverse-hauler pickups — see §2i.
- `seed.combos_tried`: `{"a,b,c": True | {"by": maker_id, "tick", "stage"}}` Seed Maker triples tried (True) or claimed in flight — see §1i. Name-keyed, never reset; ≤ 4060 keys.
- `seed_maker.status`: `{maker_id: {state, found, tried, open, saturated, last, tick}}` — see §1i. Stage B (§1k) writes `{state: "supplying"|"idle"|"waiting_material", deficit, last, tick}`.
- `plant.recipes`: `{species: {seed_id, blend, reqs: [[kind, species|None]], growth_time, base_yield}}` published by `seed_supply.py` — see §1k.
- `plant.seed_demand`: `{"now": {seed_id: n}, "rotation": {seed_id: cells}, "tick"}` published by the planting Harvester — see §1k.
- `plant.field_fill`: operator override of `field_layout.FIELD_FILL`, `"crowncap"` or `"grandbloom"` — see §1k.
- `plant.layout`: `{version, mode: "starter"|"full", fill, chunks, base, anchor, cells: {sector: species}, reserved: {sector: machine kind}, garden: [sectors]}` the field layout — see §1k.
- `plant.automators`: `{machine_id: {sector, status, queue, cells, mature, open, waiting_machines, forage_out, tick}}` Crop Automator telemetry — see §1k. Entries unrefreshed for `STATUS_STALE_TICKS = 36000` pruned by the next publishing automator.
- `plant.providers`: `{machine_id: {kind, sector, status, buffer, enabled, tick}}` Grow Lamp / Sprinkler / Dispenser telemetry — see §1k. Entries unrefreshed for `STATUS_STALE_TICKS = 36000` pruned by the next publishing provider.
- `plant.terraformer`: `{terraformer_id: {status, tier, phase, remaining_km2, progress, batch, km2_rate, onboard: {item_id: units}, enabled, in_flight, tick}}` — see §1k. Entries unrefreshed for `STATUS_STALE_TICKS = 36000` pruned by the next publishing Terraformer.
- `plant.status`: `{harvester_id: {planted, mature, stalled, species_productive, layout, active, care_due, unpaved, mode, machines_missing, kit_order, automators_wanted, last_action, heat: {costs: {cell_status: heat}, cool_per_hour}, tick}}` — see §1k. `heat` is the live-calibrated heat model, reloaded on restart.
- `drill.status`: `{drill_id: {name, type, state, rate, count, capacity, fill, near_full, eta_h, items: {item_id: units}, tick}}` field Mining Drill telemetry and pickup advert — see §1j/§2i. Entries unrefreshed for `STATUS_STALE_TICKS = 36000` pruned by the next publishing drill.
- `drill.positions`: `{drill_id: {pos: [x, y], site}}` recorded drill positions — see §2i. Entries of drills no longer deployed (`power_control` members + `drill.status`) pruned on every write, unless discovery came back empty.
- `system.good_version`: Last operator-confirmed `get_game_version()` build hash (`lib/version_guard.py`). Seeded from current build on first read (fresh save never immediately halts). Every controller's `run()` calls `validate_game_version()` once at startup, before loop (not every tick — build change only takes effect on next script restart, same as game); if running build no longer matches key, script blocks until operator clicks "Confirm New Version" on `panel_1.py` (updates key, broadcasts `system.version_confirmed`, see §7). Build hashes support equality checks only, never newer/older comparison.

---

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

---

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
from bio import BioCollectorController, BioLabController, BioExchangeController, BioLuminizerController
from harvesting import HarvesterController

# Execute main loop
controller = SolarController(self)
controller.run()
```

---

## 🖥️ 7. Control Room Panel Cards (`panel_1.py`..`panel_5.py`)

**Headless calculator + UI card split (now `panel_4.py` + `panel_1.py`).** Automation calculator (grid supervision, rebalance sweep, outpost sync, `supply_dock.plan_dock_assignments()`, fleet hardware upgrade §2k) is **headless**: no `panel.*` calls, paced by `sleep(1.0)`. It publishes result summary to `archive` (`AUTOMATION_SUMMARY_KEY = "control_room.automation_summary"`). STATUS/AUTOMATION UI card reads that summary back, doesn't compute it. Reason: multi-second automation stall must never block script that renders every tick. Custom Panel is only slot that can host "always-on, not tied to one building" process. See `DESIGN_HISTORY.md` for incident that forced split.

**⚠️ Two separate numbering schemes, don't mix them up.** Game's Custom Panel ids assigned on creation, **only ever increment**. Deleting panel doesn't free its number. Cards **can't be drag-reordered** once placed. `panel_4.py` (old numbering)/`panel_6.py`/`panel_8.py` **dead in live-slot numbering** (deleted during testing, gone for good). Separately, since [tiered `scripts/` restructuring](#-9-dev-workflow-tiered-scripts--devtoolsscripts_syncpy), *source-tree* files under `scripts/4_controlpanel/control_panel/` cosmetically renumbered `panel_1.py`..`panel_4.py` (four panels, role order). Dev-side naming only, deliberately decoupled from live-slot numbers. `panel_5.py` (DRONE FLEET) added later as truly new card, not yet placed in live Control Room. See its module docstring.
Current mapping (verified live; live-slot column authoritative for actual save):

| Role | Source-tree file | Live save slot | Notes |
| :--- | :--- | :--- | :--- |
| STATUS + AUTOMATION UI | `panel_1.py` | `panel_1.py` | wanted at top of Control Room; kept in original slot 1 |
| FLEET (ground vehicles) | `panel_2.py` | `panel_2.py` | unchanged |
| PRODUCTION | `panel_3.py` | `panel_3.py` | unchanged |
| Automation calculator (headless) | `panel_4.py` | `panel_7.py` | moved from `panel_1.py`; position irrelevant, draws nothing. Source-tree name and live slot name **differ**. See TODO.md "Panel dev-side numbering vs. save-side slot numbers" for known sync-tool gap |
| DRONE FLEET | `panel_5.py` | *(not yet created)* | new card: cruise-throttle slider + drone roster + fleet auto-upgrade switch/status (§2k). Operator must create new Custom Panel in-game, then use `devtools/scripts_sync.py`'s unmatched-file synctool-fill marker to point empty slot at this source file. Then row gets real live-slot name |
| Warehouse upgrade worker (headless) | `panel_6.py` | *(not yet created)* | runs `lib/warehouse_upgrade.py` (§2k-1); blocks for long drains, so kept out of `panel_4.py`. Operator creates a new Custom Panel in-game, then points it at this file with the synctool-fill marker, same as `panel_5.py` |

**Whenever panel added/removed in-game: re-verify table (ask operator for current mapping), update every `panel_N.py` cross-reference in this file and in scripts' module docstrings.** Stale filename here actively misleading.

Card size set from Control Room UI (drag-resize / size picker), **not** script. `panel.width()`/`panel.height()` only report operator's chosen size. Discrete, not continuous:

| Label shown in the UI | Meaning | `panel.width()` | `panel.height()` |
| :--- | :--- | :--- | :--- |
| `1 x 1` | 1 column, 1 row | 500 | 200 |
| `1 x 2` | 1 column, **2 rows** | 500 | 400 |
| `2 x 1` | **2 columns**, 1 row | 1000 | 200 |
| `2 x 2` | 2 columns, 2 rows | 1000 | 400 |

First number = columns (width), second = rows (height). `1x1` → `1x2` adds height only, not width. Wide-canvas layout (side-by-side sections, right-anchored control) clips on `1x2`, still only 500px wide.

**Sizing recommendations** (headless automation panel draws nothing, no card/size to set): `panel_1.py` (STATUS + AUTOMATION) → **`2 x 2`** (1000x400), split `panel.height()` ~55/45 between two sub-cards (ratio, not fixed pixels, so degrades OK at `2 x 1`). `panel_2.py` (FLEET, one row per vehicle) / `panel_3.py` (PRODUCTION, one row per Smelter + Fabricator + Supply Dock, discovered live via `discover_smelter_ids()`/`discover_fabricator_ids()`/`discover_supply_dock_ids()`; each row = role pill + current recipe/order + status pill) / `panel_5.py` (DRONE FLEET, one row per drone via `fleet.drones()`) share same one-row-per-item scrollable shape → **`2 x 1`** for few rows, **`2 x 2`** for more. Each shows as many rows as fit (`max_rows = (height - top - 16) // row_height`). `panel.slider()` repurposed as scroll bar (0-1 value → row offset, `round(value * (len(rows) - max_rows))`) covers rest, drawn only once list exceeds `max_rows`. Both degrade at 1-column widths (`wide = width >= 900` switches to shorter row height; `panel_2.py` hides location column).

**Headless automation panel's work, shown on `panel_1.py`'s AUTOMATION card**: §1a-1's centralized Power Grid supervision + Smelter rebalance sweep, plus:
- **Outpost-founding → resource marker auto-reassignment**: each throttled storage tick, diff `outpost_network.outposts()`' current id set vs stored `outposts.known_ids` (archive list). Each **new** id auto-calls `outpost_mining.reevaluate_unassigned_near_outpost(new_id)` (§2d). `sync_resource_markers.py` stays for manual backfill/batch catch-up.
- **Two independent throttle timers**: `SOLAR_TICK_INTERVAL = 10` ticks (~1s) gates grid supervision (cheap, no Auto Feeder transfers). `STORAGE_TICK_INTERVAL = 100` ticks (~10s) separately gates `rebalance_inventory_to_warehouses()` + outpost-diff/`consolidate_cross_warehouse_stock()` sweep. Both `.transfer_to()` and `.compact()` lock their Warehouse as material endpoint for whole transfer, so faster shared cadence risks contention (`"busy"` rejection on Smelter/Fabricator `take_item()` call). Grid supervision has no such cost. Both intervals gate via `clock.tick()` (not wall-clock), correct under time acceleration.
- **`panel.button("run_archive_cleaner", ...)`** on `panel_1.py`: `ArchiveCleaner(dry_run=False,
  verbose=True).run()` (§4). Live-commit, human-triggered only, runs directly in that UI script (rare one-off, not per-cycle work).
- **`panel.button("run_unsupported_markers", ...)`** on `panel_1.py`: `lib/unsupported_markers.py`'s `update_unsupported_markers(clear_previous=True)`. Also human-triggered only, runs directly in `panel_1.py`. Also runnable standalone as root entrypoint `mark_unsupported_targets.py`.
- **Version safety gate widget** (`lib/version_guard.py`, §4), drawn on `panel_1.py`: `VERSION` pill anchored `width - 190` from right edge (always drawn, success/error colored). Only while `version_mismatch()` true, also shows `was <old> -- new scripts halt on startup` note + `panel.button("confirm_new_version", ...)`. Neither headless automation panel nor `panel_1.py` calls `validate_game_version()` itself. Both check `version_mismatch()` independently and gate own mutating work behind `if not mismatch:`. During mismatch, `panel_1.py` keeps rendering and stays clickable, but neither script changes anything until confirmed.

**General layout rules for any new card** (see `DESIGN_HISTORY.md` for overlap bugs behind these):
- `card(x, y, w, h, title)` already renders own title bar text. Never add second `panel.label()` re-rendering same title.
- Named widget that draws own label (`slider`, likely `switch`/`button` too): fold live value INTO that label string. Don't draw separate, separately-positioned text beside it.
- `pill()` needs more vertical clearance below than plain text line. Leave ≥ ~24px, not ~16px, before placing anything under one.
- Anchor right-side elements from right edge (`width - <fixed px>`), not width fraction (`width * 0.86`), for anything with roughly fixed pixel footprint (`switch`, `button`, short `pill`). Fractions of 500px vs 1000px canvas land very differently.

---

## 🐞 8. Live Debugging via External IDE

Game exposes real Debug Adapter Protocol (DAP) integration against actual running game interpreter, not simulation: breakpoints, conditions, logpoints, call stacks, locals, watches, hover inspection, Step Over/Into/Out. Setup + full details:
`C:\Users\Adrian\AppData\Roaming\io.codeterraform.game\external-ide\README.txt`.

- **VS Code** (supported path, extension already installed this save): open script, set breakpoint, press **F5**. Idle script starts running; already-running script attaches without restart. **Shift+F5** or closing debug session disconnects but leaves script running in game. Use **Stop Script in Game** to actually stop. Watches/Debug Console **read-only** (can't execute world actions or assign variables). Edited main-script code needs **Run Script in Game** before re-attaching; edited Libraries need re-applying in game.
- **Any other DAP-capable editor**: launch
  `node "C:\Users\Adrian\AppData\Roaming\io.codeterraform.game\external-ide\server\debug-adapter.cjs"`
  (Node.js 20+, stdio transport). `launch` = attach-and-run idle script; `attach` = inspect already-running one. Set `workspace` to this save's scripts directory, `script` to target file.
- **Non-debug editor tooling** (LSP-only, no execution): `external-ide\server\server.cjs --stdio`. Per-editor docs (neovim/Helix/Sublime) in README. PyCharm needs generic LSP plugin; its own Python checker doesn't know game's owner globals/runtime rules.
- Console output mirrors to `external-ide\logs\all.log` (plus one file per script). Useful to tail even without debugger.
- **`devtools/dap_client.py`**: minimal DAP client for driving debug session from script instead of VS Code. Needs Node.js 20+; this save's copy at `C:\Program Files\nodejs\node.exe`, not on default shell `PATH`. Invoke by full path, or `export PATH="/c/Program Files/nodejs:$PATH"` for current shell session only (shell state doesn't persist between tool calls here). Vendored into `devtools/` (not imported from `early_game_runner/`, separate standalone project this repo doesn't reach into). `devtools/scripts_sync.py` only consumer. `DapClient` = low-level stdio transport (Content-Length framing, background reader thread). `run_session(workspace, script, breakpoints,
  mode, on_stopped, wait_timeout)` wraps full initialize → attach/launch → setBreakpoints → configurationDone → wait-for-`stopped` → callback → continue → disconnect sequence in one call.
  Also runnable directly: `python devtools/dap_client.py --workspace <dir> --script <path> --break
  <file.py>:<line> [--mode attach|launch]`. Prints stack trace + top-frame locals at first hit, then resumes and disconnects. Verified live against `rover_1.py`/`lib/vehicle.py`: breakpoint inside `publish_telemetry()` paused execution, reported true call stack + real locals, resumed cleanly, script kept running.
  - **`launch` starts idle scripts without breakpoints**: `dap_client.launch_script(workspace, script)`
    (or CLI `python devtools/dap_client.py --workspace <dir> --script <path> --launch`) sends `initialize` →
    `launch` → `configurationDone` with no breakpoints set, triggering `{ action: "start", runIfIdle: true }`
    in `debug-adapter.cjs`. It then cleanly disconnects with `terminateDebuggee=False`, leaving the freshly-started
    script running in the live game.
  - **Does NOT force-restart already-running script**: `runIfIdle: true` is exactly that:
    a script already running just gets attached-to (per `debug-adapter.cjs`'s own `configurationDoneRequest`),
    its old in-memory code untouched. There is no `supportsRestartRequest` capability advertised by
    `initialize`, and the base `DebugSession`'s `restartRequest`/DAP `restart` is an unimplemented no-op
    stub in the concrete session class too.
  - **General external-command channel** (`.codeterraform/command.json`/`command-result.json`/
    `command.lock`, distinct from the debug bridge's own `debug-command.json`/`debug-result.json`) is what
    "Run Script in Game"/"Create Library in Game"/etc. (VS Code commands implemented in `extension.cjs`,
    not `debug-adapter.cjs`) actually use. Confirmed live (2026-09-22) by finding a real stale request
    already sitting in `command.json` from earlier tool usage — not reverse-engineered blind:
    `{"version":1,"requestId":"<uuid>","issuedAt":<epoch_ms>,"session":{"id":..., "generation":1} (read
    live from codeterraform-workspace.json),"action":"run","scriptId":"<script id>","source":"<full
    script text>"}`, written via the exact same atomic-write + `command.lock` (staleness >30s, `wx`-create,
    35s acquire budget) protocol as the debug bridge's own `H.send()`, then polled from `command-result.json`
    for `{"requestId":..., "ok": bool}` (10s timeout). Sending this for `rover_1.py` **did** force a genuine
    restart of an already-running script (confirmed: fresh startup, tick counter reset) — the first
    confirmed working "force a running script to pick up its own new code" path found.
  - **Still does NOT apply changed `lib/` module**: confirmed live same session: after
    restarting `rover_1.py` via `"action":"run"` (with `lib/vehicle_mining.py` freshly synced to disk),
    it kept executing the **stale cached** copy of `vehicle_mining`, not the new one. The game caches an
    imported library module independently of restarting the script that imports it — restarting the
    importer alone doesn't invalidate it. Every relevant VS Code command was then tried directly against
    the changed library file itself (**Run Script in Game**, **Create Library in Game**, **Import File as
    Game Library**, **Rename Library and Update Imports**) and each failed for an unrelated,
    semantically-correct reason (`context` — wrong file kind for Run; `file_exists` — Create is for a
    genuinely new library; `duplicate_name` — Import likewise; `no_change` — Rename needs an actual new
    name), never "not found" — ruling out a hidden "apply library" command in that palette. The in-game
    Script Editor's own **"Apply & restart all"** button (what actually invalidates that cache) is a
    **native in-game UI action with no external hook** in any of `debug-adapter.cjs`, `extension.cjs`'s
    known commands, or the general command channel — confirmed by exhaustive negative testing, not
    just an unread code path. **Net effect**: `devtools/scripts_sync.py --auto` can start an idle script,
    and can force-restart an already-running one with its OWN new code, but **cannot** currently make any
    running script pick up a changed `lib/` module — `warn_stale_lib_dependents()` deliberately does not
    attempt this (see its docstring and TODO.md); it only warns which deployed scripts need a manual
    in-game Apply.
- **Automated Script Deployment (`early_game_runner/auto_deploy.py`)**:
  - Auto-bridges newly placed/deployed hardware (via in-game `computer.deploy(...)`) to host-side Python controller scripts.
  - **Dual-Channel Monitoring**:
    - Watches `logs/all.log` for explicit `[DEPLOY]` lines with arbitrary parameter assignments (e.g. `[DEPLOY] machine_id=pioneer_5 template=pioneer_hauler HOME_BASE="outpost_3" DESTINATION="outpost_home"`).
    - Periodically scans `codeterraform-workspace.json` for newly registered machines whose script slots are idle and unpopulated.
  - **Template Directory (`early_game_runner/templates/`)**:
    - Stores modular templates (e.g., `solar.py`, `heater.py`, `smelter.py`, `pioneer_hauler.py`).
    - Supports flexible parameter substitution: `${PARAM:default_value}` or `{PARAM}`.
    - Built-in variables automatically injected: `MACHINE_ID`, `TYPE_ID`, `LOCATION_ID`.
  - **CLI Modes**:
    - `python early_game_runner/auto_deploy.py --scan`: One-shot scan and deploy for all unscripted idle machines.
    - `python early_game_runner/auto_deploy.py --scan --dry-run`: Preview generated script code and parameters without modifying disk or launching.
    - `python early_game_runner/auto_deploy.py --daemon`: Continuous background watcher loop.
    - `python early_game_runner/auto_deploy.py --deploy <machine_id> [--template <name>] [--param KEY=VALUE ...]`: Targeted single-machine deployment.

**Before starting any debug session (F5/`launch`/`attach`) or using **Run Script in Game**:
If running user's main save (save_mtzkzly3_4ww80o): ask user first, every time. Never assume standing permission from prior yes.** Debug session runs against live save with real effects: script that spends credits, moves vehicle, fires drill, etc. does so for real, no sandbox. Pausing at breakpoint can also leave machine mid-action in state player didn't intend. Treat like any other action with real-save side effects per project's risk-awareness rules, not routine read-only inspection.
Other (throwaway) saves: can be more liberal, especially when developing auto-play tools like `early_game_runner/auto_deploy.py`, `early_game_runner/early_game.py`, etc.

## 🧬 9. Dev Workflow: Tiered `scripts/` + `devtools/scripts_sync.py`

Repo (`C:\Users\Adrian\Code_Terraform`) = dev root, separate from live save folder (`%APPDATA%\io.codeterraform.game\save_*_scripts`). Source of truth: `scripts/<tier>/<category>/<name>.py`. `devtools/scripts_sync.py` (adapted from `inspirations/vakermit/bin/ct_sync.py`) fills save folder's numbered script slots, mirrors `lib/` from it. Full mechanics (fill/pull markers, renumbering, `_unmatched/` staging) in tool's module docstring. This section covers project-specific tiering layer on top.

**Tier list**: not hardcoded. `discover_tiers()`/`tier_number()` in `scripts_sync.py` scan `scripts/` for `<N>_<anything>` dirs, sort by `N` ascending (numeric, so `10_x` after `9_x`, not between `1_x`/`2_x`). Only number matters, rest of name free text. Numbers may skip. Add `scripts/6_derp/` (or `scripts/3_inbetween/` between two existing tiers) with own `.criteria` → picked up automatically, no code change. Dir starting with digit but not plain `<int>_...` (`1N3_DERP`), or two dirs claiming same number (`10_hi`/`10_ho`) → raise `TierNamingError`, no silent guessing. Each tier gated by `.criteria` file at root (absent for `0_cold_boot`, always-active baseline). Current tiers:

| Tier | `.criteria` | Unlocks (tech id / `research_*` id) |
| :--- | :--- | :--- |
| `0_cold_boot` | *(none — baseline)* | — |
| `1_early` | `{"tech": ["ship_computer"]}` | `research_computer` |
| `2_libunlock` | `{"tech": ["shared_library"]}` | `research_shared_library` |
| `3_archiveunlock` | `{"tech": ["data_archive_unlock"]}` | `research_data_archive` |
| `4_controlpanel` | `{"tech": ["custom_panels_unlock"]}` | `research_custom_panels` |
| `5_steampower` | `{"buildings": {"thermal_cap": 2, "steam_turbine": 5}}` | built steam power (no tech gate) |
| `6_seeds` | `{"buildings": {"seed_maker": 1}}` | deployed Seed Maker (`research_seed_maker`, Biomass 500) |
| `7_miningdrills` | `{"buildings_any": {"mining_drill": 1, "mining_drill_industrial": 1, "mining_drill_heavy": 1}}` | first deployed Mining Drill of any variant (standard / Industrial / Heavy) |
| `8_planting` | `{"plant_recipes": 15}` | all 15 seed recipes discovered (`state.planet.plants.discoveredRecipes`); needs `7_miningdrills` met too (ascending chain) |

`.criteria` keys use save file's own **tech ids** (from `state.unlockedTech`), not `research_*` ids from `docs/database/research_catalog.md`. Table above = mapping. Supported keys: `"tech": [id, ...]` (all must be present), `"outpost_count": N` (`len(state.planet.outposts) >= N`). `"plant_recipes": N` (`len(state.planet.plants.discoveredRecipes) >= N`). `"buildings": {typeId: N, ...}` (each type's count in `state.machines[*].typeId` >= N; finished machines only; pending `constructionBlueprints` and `isUnderConstruction` machines not counted). `"buildings_any": {typeId: N, ...}` (OR-group: at least one listed type's count >= N; used for "any Mining Drill variant"). Map-deployed buildings (drills included) appear in `state.machines` like any other machine, so both building keys see them; entries still `isUnderConstruction` are **not** counted (only finished deployments). **No higher-numbered TP field found** in save state on quick pass → TP-threshold criteria not supported yet.

**Active-tier resolution**: fully automatic, per-save. `scripts_sync.py` derives sibling save-state file from save-scripts dir name (`save_X_scripts/` → `save_X.json`, one level up), reads `state.unlockedTech` / `state.planet.outposts` **read-only**, walks numerically sorted tier list evaluating `.criteria` until one fails. Highest passing tier = active. No hint file, no manual bookkeeping. `--force-tier NAME` overrides for one run, persists nothing. Confirmed live against real save this session (`python -c` one-liners against `save_mtzkzly3_4ww80o.json`). **Assumes monotonic unlocks**: walk stops at first tier whose `.criteria` unmet, so ancestor criteria implicitly required. Out-of-order save (higher tier's `.criteria` satisfied before lower one's) not handled specially. Not expected (techs never "unlearned"), but assumption flagged.

**No duplicate files across tiers**: for given `category/base_name` (incl. `lib` category), resolver walks from active tier down to `0_cold_boot`, uses first file found. Higher tier needs own copy only when behavior genuinely diverges.

**lib/ from `2_libunlock` on = every module of every tier** (`lib_chain()`, `LIB_UNLOCK_TIER_NUMBER = 2`): after the active tier's chain, the resolver also walks every HIGHER tier (ascending). A module defined at or below the active tier resolves exactly as before, so a higher tier's override of an existing module stays gated (today only `5_steampower/lib/power.py`). A module that only exists in a higher tier is deployed anyway (idle until its machines exist) — so entrypoints never need a per-tier copy just to import a newer lib (the tier-5 `panel_4.py` copy was removed this way: its Mixer gate now sits idle in the one `panel_4.py`). Pyright's `.pyright-resolved/lib` uses the same chain.

**Library registration hook** (`register_new_libraries()`, runs after every lib mirror in `once`/`watch`; standalone `python devtools/scripts_sync.py register-libs [--dry-run]`): a file written into the save's `lib/` is **not** seen by the game until it is registered as a Library (manually: Computer → Library → + New, same name — the game then picks up the file on disk). The hook does the same as VS Code's **Import File as Game Library**: `action: "create-library"` with `name` (module stem) and `source` over the external-command channel (§8: `.codeterraform/command.json` + `command.lock` + `command-result.json`, `session` from `codeterraform-workspace.json`), for every deployed module missing from `context.libraryScripts`. Needs the game running with the save open; otherwise it warns and the next sync retries. `duplicate_name` counts as already registered. Source limit 200,000 chars (`interpreter.maxSourceLength`). Confirmed live 2026-09-24 (`drone_upgrade`, `fleet_upgrade` → `{"ok": true}`, then listed by the game). It only registers new modules; applying a *changed* registered lib still needs the in-game "Apply & restart all" (§8).

**Global (untiered) categories**: category dir directly under `scripts/` (sibling of tier dirs, e.g. `scripts/contract/`) not gated by any `.criteria`. Always included, merged on top of active tier resolution (`list_global_categories`/`resolve_global_category` in `scripts_sync.py`). Contracts live here: genuinely tech-independent, self-contained (no imports), available from very first save, not tied to any progression tier.

**Migration note**: pre-restructure codebase written/tested against save with 60 techs unlocked (incl. `data_archive_unlock`, `custom_panels_unlock`) → moved wholesale into `4_controlpanel/` as honest home tier (see `devtools/_migrate_from_root.py`), not guessed apart per file. `0_cold_boot`/`1_early` seeded separately from top-level `early_game_runner/` submodule's `early_game_runner/templates/` (flat) and `early_game_runner/templates/early/` (richer) boilerplate. That submodule = this project's own earlier `code-terraform-earlygame-automation` prototype, not `inspirations/vakermit`. Flat `early_game_runner/templates/*.py` = thin `from <lib_module> import ...` wrappers around project's own `lib/` controllers (`terraforming.py`, `solar.py`, `smelter.py`, ...), need `research_shared_library` → wrongly copied into `0_cold_boot` in initial seeding. Only `early_game_runner/templates/early/` genuinely self-contained (no `lib/`/game-module imports), belongs at `0_cold_boot`/`1_early`. `0_cold_boot/power/solar.py` = hand-trimmed exception: `early_game_runner/templates/early/solar.py` bundles full Ship-Computer building-buyer speedrunner around tracking loop, so cold-boot gets few-line sun-tracking-only script extracted from it. `fabricator`, unified `pioneer` (destination-routing, distinct from `pioneer_scout`), `steam_turbine`, `thermal_cap`, `water_pump` have no self-contained early equivalent yet → removed from `0_cold_boot` rather than left broken. They resolve once save reaches tier defining them (currently `4_controlpanel`). Splitting rest of `4_controlpanel` into earlier-tier-capable content = manual follow-up (see TODO.md), not automatic.

**`panel` = distinct-instances category** (`DISTINCT_INSTANCES` in `scripts_sync.py`), at `scripts/4_controlpanel/control_panel/panel_1..4.py`. Separate, genuinely different hand-authored Control Room cards (see §7), not interchangeable template copies. Matched by exact filename, never collapsed to shared base name or renumbered. Dev-side numbering cleaned to `_1.._4` (fourth was `panel_7.py`; `_7` just artifact of game-assigned slot). Game can't rename/reorder existing script slot → save's actual file still `panel_7.py`. Known, documented gap (see TODO.md), not yet bridged.

**Pyright/IntelliSense**: `pyrightconfig.json`'s `extraPaths` point at `.pyright-resolved/lib` (regenerate with `python devtools/scripts_sync.py resolve-preview`, gitignored) plus live save folder for game-API stubs. Modules that only exist in a higher tier resolve too from `2_libunlock` on (`lib_chain()`); only a higher tier's *override* of an existing module needs `resolve-preview --force-tier <name>` to preview. Game's own in-editor syntax highlighting/autocomplete (tied to `codeterraform-workspace.json`) doesn't apply to source outside save folder at all → check deployed copy in save folder when needed.

**`--auto`** (off by default): additionally calls `devtools/dap_client.py`'s `launch_script()` after filling matched machine-script slot. `launch_in_game()` retries with backoff (`LAUNCH_RETRY_DELAYS_S = (0.5, 1.0, 2.0)`, ~3.5s max) if first attempt fails. Game polls disk on own cadence, so freshly-written slot may not be in workspace snapshot yet at launch time. Confirmed live (freshly-cleared, re-filled `drone_2.py` failed immediate launch, succeeded on retry after short wait). `sync_lib()` mirrors changed `lib/` files unconditionally regardless of `--auto` (unlike machine-script slot, `lib/` module has no slot for `--auto` to key off). So `warn_stale_lib_dependents()` separately walks every deployed script's import closure (`lib_dependency_closure()`, built via `ast`-parsed `import`/`from` statements) to find which import changed `lib/` module. **Per confirmed-live finding above, does NOT relaunch them** despite name (kept for now, see TODO.md). Only prints which deployed scripts need manual in-game Apply. No automatable path found to flush game's cached library module; fake relaunch worse than none (false confidence while script silently runs stale code). Warn-only behavior still operator opt-in per invocation (`--auto`), not Claude starting live-debug session on own. See CLAUDE.md's Live Debugging rule: binds Claude's own actions, not flag on tool user runs themselves.

**Parameterized templates** (`${VAR}` / `${VAR:default}` in source script; same syntax as `early_game_runner/auto_deploy.py`'s placeholder substitution, kept identical on purpose): `sync_file()` detects via `find_placeholders()`, prompts operator interactively (`typer.prompt`, blocking) first time given save slot needs them. E.g. `scripts/4_controlpanel/pioneer/pioneer.py`'s `HOME_BASE`/`DESTINATION_OUTPOST_ID`/`CRUISE_THROTTLE`, asked once per slot (`pioneer_2.py`, `pioneer_3.py`, ... each independently) so operator sets where each specific Pioneer goes. Answers cached in `devtools/.sync-backups/script_params.json` (gitignored, keyed by `<save dir name>/<slot filename>`) → re-filling same slot doesn't re-ask. Slot re-prompted only for unanswered names (e.g. template gains new placeholder). `--dry-run` never prompts; previews with cached-or-default values only. Blocks under `watch` too, no skipping: filesystem observer runs on own thread, queues further events into `Watcher.pending`/`repo_due` while main thread waits on `input()`. Nothing lost, only delayed until answered (or `Ctrl-C`, still raises cleanly through `input()`). `status` shows which resolved scripts would prompt (`(asks for: VAR1, VAR2)`) without prompting. **Fleet-upgrade replacement drones never prompt** (`upgrade_fill_for()`/`inherit_placeholders()`): a `drone_*` slot named in `fleet.upgrade.lineage`, or a new drone slot whose machine `typeId` matches the single `announced`/`swapping` swap's `target_kind`, is filled with the old slot's cached answers → the old drone's archived `params` → template defaults, in every mode (`status` shows `(inherits params from drone_N, no questions)`). Read from the save file (`read_save_state()` also returns `machine_types` and `fleet_upgrade`). A new `drone_*` slot whose machine isn't in the save yet is **held** (autosave lag) and retried every 5 s by `watch` (`HELD_SLOTS`); `once` reports it and fills on a later run. Wrong `typeId` (hand-deployed) → normal prompt.

**`watch --auto`'s lib/ warning is debounced** (`--auto-debounce SECONDS`, default `30.0`): `lib/` edit doesn't fire `warn_stale_lib_dependents()` immediately. `Watcher._note_lib_changed()` accumulates changed keys, pushes `auto_launch_due` out by `auto_debounce` seconds, re-extended by each further `lib/` edit before firing (`Watcher.drain()`). Avoids warning on mid-edit, inconsistent `lib/` set when touching several related modules for one fix (e.g. this session's `vehicle_mining.py` + `production.py` change) → one consolidated warning naming every affected script, not one per file. `once` (single one-shot pass) skips debounce, reports immediately; no "still editing" risk in one-shot run.
