# Code: Terraform — AI Agent Quick Reference Cheat Sheet

High-density reference of physics, formulas, component specs, bus channels, and data conventions.
This is the **single source of truth for tunable numbers and definitions** shared by every agent
working on this project. When you change a tunable constant in code (safety margins, tiers,
thresholds, stale-tick counts, budgets, etc.), update it here in the same change. Other docs
(`CLAUDE.md`, `TODO.md`) should point at the constant/module name rather than restate its value —
that way there is exactly one place to keep current.

For the *why* behind a design (bug postmortems, rejected approaches, design-history narrative),
see **[`DESIGN_HISTORY.md`](DESIGN_HISTORY.md)** — this file stays reference-only.

---

## 🗺️ Progression Walkthroughs & Speedrun Guides

For high-level operational workflows, progression roadmaps, and automation orchestration, refer to the dedicated walkthrough guides:

- **[`manual_walkthrough.md`](../tools/manual_walkthrough.md)**: **Manual Progression Roadmap (0 $\rightarrow$ 1,000,000 TP Victory)**
  - Detailed playbook for manual progression: First Contact onboarding steps, Earth Clearance contract solvers (+3,750 cr & +22,500 cr), research prerequisites, critical bottleneck matrix, and chronological phase breakdown from Phase 0 (Cold Boot) through Phase 7 (Deep Biome, Nuclear Reactor Recovery & Endgame Victory).
- **[`auto_walkthrough.md`](../tools/auto_walkthrough.md)**: **Autonomous Architecture & Early Speedrunner (0 $\rightarrow$ 150,000 TP)**
  - Blueprint for hands-off automation: Master Automation Architecture, revised 25-slot Nocturna Base speedrun strategy, `solar_1.py` master building-buyer (autonomous buy/deploy/sell cycles), `tools/early_game.py` speedrunner daemon & machine watcher, Earth Clearance contract solvers, and the 150k TP mid-game migration protocol to `lib/`.
- *(Top-level navigation hub: [`walkthrough.md`](../tools/walkthrough.md))*

---

## 🧱 0. Shared Library Module Map (`lib/`)

> Physical location: `scripts/<tier>/lib/<module>.py` (tiered, see §9) — not a flat top-level `lib/`. `devtools/scripts_sync.py` resolves the right copy of each module per the active tier and mirrors it into the save folder's `lib/`. Module names below are logical; nearly everything currently lives under `scripts/4_controlpanel/lib/` since that's the tier this codebase was actually written and tested against (see §9).

| Concern | Module(s) |
| :--- | :--- |
| Terraforming (heat/pressure/O2) | `terraforming.py` (`HeatController`, `PressureController`, `OxygenController`) |
| Power grid & brownout | `power.py` (`PowerGridManager` — generic, works for solar/oil/reactor/turbine grids, owned centrally by `panel_7.py`, one instance per grid, no election — see §1a-1); `solar.py` (`SolarController` — pure sun tracking, no grid supervision of its own any more) |
| Vehicles (Rover/Pioneer base) | `vehicle.py` (`VehicleController`, composes the mixins below) |
| &nbsp;&nbsp;↳ driving / stall recovery | `vehicle_navigation.py` |
| &nbsp;&nbsp;↳ battery accounting / trip budgeting / charging-station discovery | `vehicle_energy.py` |
| &nbsp;&nbsp;↳ fleet-wide target claims & hardware blacklist | `vehicle_claims.py` |
| &nbsp;&nbsp;↳ cargo offload into Inventory / Warehouse | `vehicle_cargo.py` |
| &nbsp;&nbsp;↳ sonar survey loop (POI discovery) | `vehicle_survey.py` |
| &nbsp;&nbsp;↳ mineral-site discovery & drill execution | `vehicle_mining.py` — shared by Rover and Pioneer; see §2b |
| &nbsp;&nbsp;↳ in-flight mining yield reservation (non-exclusive, overmining guard) | `mining_reservations.py` — see §2b |
| &nbsp;&nbsp;↳ automatic Pioneer hardware tier upgrades (Sonar/Drill/Holder/Rack) + manual Sport Nav request | `vehicle_upgrade.py` — Pioneer-only, mixed into `PioneerController` only, never `VehicleController`; see §2b-1 |
| Rover / Pioneer specializations | `rover.py`, `pioneer.py` — thin `VehicleController` subclasses; do **not** put shared vehicle logic here |
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
| Drones (scout/miner base) | `drone.py` (`DroneController`, composes the mixins below — see §2h) |
| &nbsp;&nbsp;↳ go_to()/go_to_station()/go_to_drill() wrappers, arrival polling | `drone_navigation.py` |
| &nbsp;&nbsp;↳ linear Wh/meter trip budgeting, drone_service/drone_depot discovery | `drone_energy.py` — see §2h |
| &nbsp;&nbsp;↳ exclusive biosite claims + scout empty-POI cache + mission persistence | `drone_claims.py` — see §2h |
| &nbsp;&nbsp;↳ cargo accounting/load-unload + home-biome filtering | `drone_cargo.py` |
| &nbsp;&nbsp;↳ scout role loop (POI bio-scanning) | `drone_scout.py` |
| &nbsp;&nbsp;↳ miner role loop (biosite extraction) | `drone_mining.py` |
| Drone Service Station (charging/rescue) | `drone_service.py` — see §2h |
| Drone Depot (cargo logistics endpoint) | `drone_depot.py` — see §2h |
| Fabrication | `fabricator.py` |
| Thermal Cap (steam capture, anti-overpressure) | `thermal_cap.py` |
| Steam Turbine (steam-to-grid power) | `steam_turbine.py` |
| Water Pump (route water to network Liquid Tanks) | `water_pump.py` — see §1d, simpler cousin of `thermal_cap.py` (no overpressure/relief concept) |
| Shared network-wide fluid-target discovery/blacklist/reconnect mechanism | `fluid_routing.py` — used by `thermal_cap.py`/`water_pump.py`/`steam_turbine.py`; see §1b |
| Storage management (Warehouse-aware sourcing/unloading, Inventory rebalancing) | `storage.py` — see §2c |
| Outpost ore-assignment & stock-target scaffolding (multi-outpost mining) | `outpost_mining.py` — see §2d |
| Data Archive persistence layer | `archive.py` |
| Game version safety gate (halt on build change until operator confirms) | `version_guard.py` — see §4's `system.good_version`/`system.version_confirmed` entries and §7 |
| Wildcard pattern matching helpers | `patterns.py` |
| Per-script tick-cost profiling | `profiling.py` — see §1d |
| Structured, indented console logging (`debug()`-level decision tracing) | `tree_console.py` (`TreeConsole`) — see §0a |

Root executable scripts (`solar_1.py`, `rover_1.py`, `panel_7.py`, etc.) should stay thin
entrypoints that import and run a controller from `lib/` — they should not contain their own
copies of tier lists, thresholds, or budgeting formulas.

**No real stdlib — only a short, specific allowlist of "executable built-in modules" exists**
(`docs/guide/programming_language_reference.md`'s "Imports & Libraries" section is authoritative;
re-check it before reaching for any import, don't assume from ordinary Python). The **only**
executable modules are `random` (`randint`/`rand`/`random()`, also callable as bare global
helpers), `re` (regex — but `re.escape` is unavailable), `functools` (`reduce`, `total_ordering`),
and `dataclasses` (`dataclass`, `field`) — nothing else, and none of these are real system
libraries the way they are in ordinary Python: this is a small in-game reimplementation exposing
just those names, not CPython's actual modules. `math`, `sys`, `os`, `json`, `time`, `itertools`,
`collections` (the concrete module), etc. do **not** exist at runtime. `typing`, `types`,
`collections.abc`, and `user_stubs` exist ONLY for editor/Pyright type annotations — erased at
runtime (`typing.TYPE_CHECKING` is always `False` in-game). **When you need something stdlib would
give you (ceiling division, etc.), write the few lines of plain arithmetic by hand instead of
importing** — see `lib/production.py`'s `_ceil()` for the pattern this project uses instead of
`math.ceil()`.

**Import depth limit**: the interpreter caps the nested import-resolution stack at
`maxImportDepth = 256` (`interpreter.maxImportDepth`, confirmed from the decompiled simworker —
see `internals/` [gitignored, not authoritative game docs]), raising a `RecursionError` /
`error.import_depth` if exceeded. Our current `lib/` chain (entrypoint → `vehicle.py` → its
mixins, at most 2-3 levels deep) is nowhere close — if you ever see this error, look for a real
import cycle.

### 0a. Structured Console Logging (`lib/tree_console.py` `TreeConsole`)

Console output works at three levels of detail, all tree-formatted the same way:

- **Overview (info, always visible)** — major blocks and outcomes, kept beautified and skimmable
  at a glance without opting into anything.
- **Reasoning trail (debug, opt-in, always written)** — the *why* underneath: which branch a
  decision took, what candidates were considered/rejected, what a computed threshold or estimate
  came out to. Hidden from the normal ALL view (`docs/components/console.md`'s
  `console.debug()`), so it doesn't spam players who haven't opted in, but cheap enough to leave
  on in most `lib/` files — reading it with debug output enabled should tell the whole story of a
  run without reaching for the in-game breakpoint/watch debugger (`§8`).
- **Trace (opt-in per module, gated before it ever reaches `console`)** — genuinely high-volume
  noise: method entry/exit, per-item loop detail. `TreeConsole.trace()` is a true no-op (no
  `console` call, no disk write) unless `TreeConsole(module=...)`'s module is listed `"verbose"`
  in the `console.log_levels` archive dict (`{module_name: "normal"|"verbose"}`, default
  `"normal"`). The level is read once at construction — restart the script after editing the
  archive key via the Data Archive Notebook, it does not re-check per tick. `module` must be
  passed explicitly (the sandbox has no `inspect`/frame introspection to auto-detect a caller);
  by convention use the `lib/` filename without extension (e.g. `"power"`, `"vehicle_energy"`).
  This is what actually gets sprinkled liberally across most files per the workflow rule on
  debug logging, without `debug()`'s always-on cost applying to it too. When it does fire, it
  still emits at **debug** level (not a custom `"trace"` badge) — `docs/components/console.md`'s
  `console.print()` only treats `info`/`warn`/`error`/`debug` as filter-feeding; any other string
  is a colored badge shown in the normal ALL view, which would defeat the whole point of gating
  this as opt-in output.

`lib/tree_console.py`'s `TreeConsole` wraps `get_component("console")` with tree-drawn
indentation (inspired by `inspirations/discord-panels/`) so both levels read like a call stack
instead of a flat scroll:

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

- `start(msg)` / `end(msg)` open/close a block, printing a `┏━`/`┗━` line and indenting
  (`┃   ` per level) everything logged in between — default level is **info**.
- `print(msg)` logs one line at the current indent depth, at `default_level` (info) unless
  overridden with `.level(...)`.
- `debug(msg)` is shorthand for `.level("debug").print(msg)` — the in-depth, opt-in reasoning
  trail, nested under the info-level blocks that describe what actually happened. Always written.
- `trace(msg)` is the same shape at **debug** level (not a custom `"trace"` badge — see above),
  but short-circuits before calling `console` at all unless the `module=` passed to
  `TreeConsole(...)` is `"verbose"` in `console.log_levels` (default `"normal"` if `module` is
  omitted or unlisted). Use it for method entry/exit and per-item loop noise you want available
  during an active debugging session but not paying for otherwise.
- **Convention going forward**: construct one `TreeConsole` per controller instance, in
  `__init__` (or once before a `run_*_loop()`'s `while True:` for a bare function, not inside
  it), and store it as `self.log`/`log` — never re-construct it per call or per tick, since
  `__init__` reads the `console.log_levels` archive dict. Name the variable/attribute `log`
  (not `tree` — the tree-drawing is just formatting, `log` names what it's actually for).
- `color(c)` / `level(lvl)` set a one-shot override (CSS color / `info`\|`warn`\|`error`\|`debug`\|
  custom) consumed by the *next* `print`/`start`/`end`/`debug`/`trace` call only, then reset to
  the instance default.
- Every line still goes through `console.print(..., timestamp=True)`, so it keeps the game
  time-of-day prefix and plays correctly with the Console's channel/level filters.
- Reserve plain `warn`/`error` for actual status changes a player should notice even without
  debug output; `debug()`/`trace()` are purely for detail, never for something that needs
  attention.

---

## ⚡ 1. Core Terraforming & Physics Formulas

| System | Component | Key Formula / Setpoint | Limits & Constraints |
| :--- | :--- | :--- | :--- |
| **Solar Tracking** | `solar_generator` | `tilt = round(sun_elevation)` | 0° (flat) to 90° (vertical). Night output = 0 W. Peak = 50 W. |
| **Oxygen Generation** | `oxygen_generator` | `intake = atmosphere.get_co2() / 10.0` | Power: -8 W. Dump waste when `50 <= waste < 60` (clean dump, 0 penalty). Stalls at 100 waste. |
| **Heat Calibration** | `heat_generator` | `power = 1..10 W` (sweep / cache by weather) | Power: -10 W max. Re-evaluate optimal power when day/weather changes. |
| **Pressure Sync** | `pressure_generator` | Sync pulse with resonance window peak | Power: -10 W max. 100% efficiency on exact resonance window hit. |
| **Power Grid & Brownout** | `power_control`, `battery` | Battery = 500 Wh (300 cr). Safe floor: 15-20% | Configurable shedding tiers (`power.shedding_tiers`) — see §1a for the full tier/threshold breakdown. |

### 1a. Brownout Load-Shedding Detail (`lib/power.py` `PowerGridManager`)

- Tiers are configurable via `archive` key `power.shedding_tiers` (or a per-grid override
  `power.shedding_tiers:<grid_anchor>`), falling back to `DEFAULT_SHEDDING_TIERS` in `lib/power.py`:
  - **Tier 1 — passive background terraforming** (`heater_*`, `pressure_*`, `o2gen_*`,
    `bio_collector_*`, `bio_lab_*`, `bio_exchange_*`, `bio_luminizer_*`): shed **first**.
  - **Tier 2 — critical active production** (`smelter_*`, `fabricator_*`): shed only under
    severe deficit.
  - Deliberately inverted from a naive "protect terraforming" instinct — terraforming is treated
    as background/passive load, production the higher priority to keep alive. See `DESIGN_HISTORY.md`
    for why.
  - Vehicle Charging Stations (`vehicle_charging_station*` / `charging_station_*`) are
    deliberately **never** in any tier — they also dispatch the fleet rescue drone
    (`lib/charging.py` `manage_fleet_rescues()`); losing power there would lose rescue capability
    exactly when a vehicle is most likely to be stranded (`dispatch_rescue()` returns
    `"station_offline"` if the station itself is unpowered).
- Shed thresholds are **inline literals in `manage_night_loads()`** (not named module constants —
  check that function directly if retuning): Tier 1 sheds on deficit or `battery_pct < 0.20`;
  Tier 2 additionally sheds on severe deficit (`stored_wh < wh_needed * 0.50`) or
  `battery_pct < 0.15`.
- Recovery is the mirror image, in both `manage_night_loads()` (battery stabilizing) and
  `manage_day_recovery()` (solar surplus at dawn): Tier 2 (production/logistics) is restored
  first, requiring only a small surplus-watt / stored-Wh margin; Tier 1 (terraforming) is
  restored last, requiring a larger margin.
- **Tier 2 (`smelter_*`/`fabricator_*`) is soft-shed via `SOFT_SHED_PATTERNS`, never powered off** —
  idle Smelter/Fabricator draw is already 0 W (recipe power draw only applies while actively
  crafting), so cutting the breaker saves nothing beyond what not-starting-new-work already saves.
  Power Guard still adds/removes the machine from `power.shedded` (signal + recovery timing
  unchanged) but never calls `set_powered()` on it; `SmelterController.is_shedded()` /
  `FabricatorController.is_shedded()` check that list each `step()` and, if shedded, drain
  output/eject excess but never start or top up production. Every other Tier 1 pattern
  (`heater_*`, `pressure_*`, `bio_*`, etc.) is still hard-shed via `set_powered()`. **No cooperative
  auto-wake exists on purpose** — if the operator stopped/powered down the Smelter themselves,
  nothing overrides that on delivery; the Smelter's own `step()` already polls for new ore on its
  normal cycle whenever it IS running.
- **Night duration is a fixed constant, not calibrated.** `NIGHT_DURATION_HOURS`
  (`SUNRISE_HOUR`/`SUNSET_HOUR`) are computed once at module load from the decompiled simworker's
  exact day-cycle schedule (`DAY_CYCLE_DURATION_SECONDS = 600`, `DAYLIGHT_FRACTIONS`): sunrise at
  `0.25 * 24 = 6.0h`, sunset at `0.83 * 24 = 19.92h`, giving `NIGHT_DURATION_HOURS = 24 - 19.92 +
  6.0 = 10.08` exactly, every night. `power.night_wh`/`power.night_wh:<grid_anchor>` (historical
  overnight Wh, blended with live instantaneous draw when sizing `manage_night_loads()`'s shed
  threshold) is unrelated and still calibrated live — only the *duration* is exactly knowable in
  advance.
- `ArchiveCleaner.clean_power_grid_state()` (`lib/archive_cleaner.py`) retires the dead legacy keys
  `power.night_duration`/`power.last_night_wh`, and purges `power.shedded:<anchor>` /
  `power.night_wh:<anchor>` entries whose grid anchor no longer exists — skipped entirely if grid
  discovery comes back empty. This is a manual-button-triggered sweep (§7);
  `PowerGridManager.release_all()` (§1a-1) is the automatic, immediate version of the same
  cleanup for whatever a vanished grid anchor still had shed.

### 1a-1. Centralized Grid Ownership (`panel_7.py`, no Master/Follower election)

`panel_7.py`'s AUTOMATION section (§7) is a single always-running process that owns grid
supervision directly, one `PowerGridManager` instance per grid, with no election needed.

- **`PowerGridManager.__init__(self, grid, clock=None, power=None)`** — no `machine` param.
  `grid` (the initial snapshot) is required and binds `self.grid_anchor` immediately at
  construction — identity is fixed for the manager's lifetime, only the per-call snapshot
  (stored/capacity/consumed) needs to be fresh every call.
- **`resolve_pattern_machines()`** fallback chain: grid snapshot's own `.machine_ids`/`.members`
  (primary) → numbered-guess `get_component(f"{prefix}{i}")` last resort.
- **`release_all()`** — called when a grid's `anchor_id` stops being reported by
  `power_control.grids()` at all (two grids merged via a new power line). Restores anything still
  tracked in that manager's `shedded_machines` (guarded exactly like `manage_day_recovery()`) and
  clears the per-anchor `power.shedded:<anchor>` mirror, so a merge doesn't strand a shed machine.
- **Battery-less grids are skipped, not mismanaged**: `if capacity_wh <= 0: return` near the top of
  `supervise_grid()`, before any day/night or shedding logic — a Steam-Turbine-only grid with no
  Battery would otherwise divide by zero computing `battery_pct`. A generation-vs-consumption
  supervision strategy for battery-less grids remains a follow-up, not implemented here.
- **`lib/solar.py`'s `SolarController` is pure sun-tracking** — `track_sun()`/`step()`/`run()`
  only, no `PowerGridManager`, no master role, no `power`/`run_ctrl` constructor params. **Hard
  dependency**: Solar Grid brownout supervision only happens while `panel_7.py` is running — see
  `legacy/README.md` for the pre-Control-Room fallback (a save without `research_custom_panels`
  has no panel scripts, so this centralization doesn't help it).
- **`lib/smelter.py`'s `SmelterController`** likewise has no Leader election — the "inventory
  manager" sweep (`storage.rebalance_inventory_to_warehouses()`) runs once, directly, from
  `panel_7.py`'s AUTOMATION section, same hard dependency as Solar Grid supervision.

### 1b. Steam Power Loop: Thermal Cap → (Gas Tank) → Steam Turbine

Thermal Cap (`lib/thermal_cap.py` `ThermalCapController`) and Steam Turbine
(`lib/steam_turbine.py` `SteamTurbineController`) are independent scripts — each only manages its
own throttle, no shared coordination. A Gas Tank between them is purely passive (no script) and
just smooths supply gaps.

- **Pipe wiring**: a Gas Tank has no script, so each neighbor declares its own side of a
  `FluidPort`. A Thermal Cap has no `.outpost` property, so all three controllers use the shared
  `lib/fluid_routing.py` `discover_network_buildings(type_ids, resolve=True)` (Cap/Pump use the
  default resolved objects; Turbine passes `resolve=False` for plain ids), which walks every
  outpost (`outpost_network.outposts()` → `outpost.buildings(type_id)`) network-wide.
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
  - **Turbine → source** (`ensure_input_connection()`): tries every known Gas Tank first, then
    every known (non-blacklisted) Thermal Cap directly — per
    `docs/guide/infrastructure_and_pipes.md`, additional consumers may connect their own
    `steam_in` straight to a Cap, independent of the Cap's own `steam_out`. `is_stalled()` on a
    Turbine is ambiguous alone (equally true when the feeding vent is just dormant), so
    blacklisting requires `STALL_STREAK_BLACKLIST_THRESHOLD=5` *consecutive* stalled ticks.
    - **Candidate ranking is same-outpost-first, not discovery order** —
      `_discover_candidates_cached()` sorts each candidate group so one sharing this Turbine's own
      `outpost.id` comes first; a genuinely reachable cross-outpost candidate is still tried and
      still succeeds, just after same-outpost candidates are exhausted.
  - **Discovery cost**: the network walk is skipped entirely while a connection is healthy — Cap/
    Pump check one `fill_pct()` on the already-connected id before touching discovery at all;
    Turbine returns immediately whenever `connected_input` is True and `stall_streak` is below
    threshold. When discovery does run (bootstrap, blacklisted/full target), results are cached
    for `DISCOVERY_CACHE_INTERVAL_STEPS=20` `step()` calls.
- **Thermal Cap** — keeps `pressure()` off the `1.0` overpressure ceiling (hitting it blows the
  *entire* chamber to atmosphere — `.is_overpressured()`). Proportional release-valve (`steam_out`,
  via `set_throttle()`) bands on `pressure()`: `≥0.90→1.0`, `≥0.60→0.6`, `≥0.30→0.3`, else
  `THROTTLE_TRICKLE=0.1`. The relief valve (`set_relief()`, dumps to atmosphere) only engages once
  the release valve is already wide open (`throttle==1.0`) and pressure still climbs past
  `PRESSURE_RELIEF_THRESHOLD=0.95`.
- **Steam Turbine** — throttle picked by `choose_throttle()`, in priority order:
  1. Buffer fraction (`steam_in.level()/capacity()`, this turbine's own 100 t buffer) `<
     STEAM_BUFFER_LOW_FRACTION=0.15` → `THROTTLE_LOW_BUFFER=0.15` regardless of day/night/demand.
  2. `< STEAM_BUFFER_HEALTHY_FRACTION=0.40` → `THROTTLE_MARGINAL_BUFFER=0.5` (buffer rebuilding).
  3. Healthy buffer + night (`clock.get_elevation() <= 0`) → `1.0`.
  4. Healthy buffer + day + grid battery `≥ BATTERY_FULL_FRACTION=0.98` of capacity AND
     `generated >= consumed` → `THROTTLE_DEMAND_MET=0.3`.
  5. Otherwise → `1.0`.
  Reads grid state the same way `lib/power.py`'s `PowerGridManager` does
  (`power_control.grid(self.name)` → `.stored`/`.capacity`/`.generated`/`.consumed`), but runs no
  shedding itself — that's `panel_7.py`'s AUTOMATION section's job (§1a-1).

### 1c. Water Pump: Liquid Tank Routing (`lib/water_pump.py` `WaterPumpController`)

Shares §1b's Thermal Cap → Gas Tank connection/load-balancing/blacklist machinery exactly — both
build a `lib/fluid_routing.py` `FluidOutputRouter` (Pump's own `LIQUID_TANK_TYPE_IDS`,
`LIQUID_TANK_REBALANCE_FILL_FRACTION`, `CONNECTION_GRACE_TICKS`, `RESCAN_INTERVAL_TICKS`,
`DISCOVERY_CACHE_INTERVAL_STEPS` constants feed the same shared class) — but simpler: a Water Pump
has **no internal buffer to overpressure** (no `pressure()`/`relief()`, pure pass-through), so
`step()` just calls `ensure_output_connection()` and unconditionally requests `set_throttle(1.0)`
every cycle — delivery self-limits to whatever a connected tank can accept.

- **Two target building types, not one**: `LIQUID_TANK_TYPE_IDS = ("liquid_tank",
  "large_liquid_tank")` — `discover_network_buildings()` takes an iterable of type_ids (or a
  single string) and walks each outpost for every type, deduping by id.
- `water_out` (identical shape to Thermal Cap's `steam_out`) only ever holds one destination at a
  time. `is_stalled()` has identical semantics to Thermal Cap's own, so the same
  blacklist-and-reselect reaction applies unchanged.

### 1d. Per-Script Tick-Cost Profiling (`lib/profiling.py`)

The game exposes no per-script CPU/ms execution budget API. `clock.tick()` (deterministic
simulation tick since save start, 10 ticks/sec at normal speed) is the sanctioned stand-in per
`docs/components/clock.md`. `lib/profiling.py` wraps that pattern so any controller's `run()` loop
can measure its own `step()` with two calls:

```python
start = profiling.begin()
self.step()
profiling.end(self.name, start)   # logs a warning if delta > SLOW_STEP_TICK_THRESHOLD=1
```

- Samples roll into `archive` as one fixed-size history list per script name
  (`ARCHIVE_KEY_PREFIX="profiling."`, `HISTORY_LEN=50`) — one archive entry per profiled *script
  name*, not per sample, respecting the Data Archive's hard 512-entry cap.
- `profiling.report(names=None)` prints avg/max ticks-per-`step()` for every profiled name (or a
  given subset) — call it ad hoc, not from a hot loop.
- **Granularity limit — read before trusting a `0`**: `clock.tick()` advances on a fixed 10/sec
  schedule *independent of how much work a script does* (scripts are cooperatively scheduled and
  interleaved within each tick's window). A `step()` with no internal loop runs to completion
  inside whichever tick it started in regardless of real cost, so it only shows a nonzero delta by
  landing on a tick boundary by measurement luck — **a `0` does not mean "cheap."**
  `SLOW_STEP_TICK_THRESHOLD=1` reflects that: on a non-looping `step()`, any nonzero delta is
  already the interesting case. There's no finer-grained (sub-tick/wall-clock) instrument
  available — below this floor, fall back to code-level reasoning (algorithmic complexity, what
  runs every cycle vs. gated).
- **Not currently wired into any script.** `lib/profiling.py` itself, and `lib/archive_cleaner.py`'s
  cleanup of it, are kept for any future script suspected of doing real bulk per-call work.
- **Storage shape & cleanup**: each archive entry is `{"history": [...], "last_tick": N}`.
  `lib/archive_cleaner.py`'s `clean_profiling()` purges an entry whose `last_tick` hasn't advanced
  in `PROFILING_STALE_TICKS=6000` (10 sim minutes, "instrumentation removed"), and always purges a
  legacy bare-list entry (pre-dating this shape) as a one-time migration. Runs as part of
  `ArchiveCleaner.run()`'s normal sweep.

### 1e. Bio Luminizer Lamp-Mix Solve (`lib/bio_coastal.py` `BioLuminizerController`, `_solve_3x3()`)

*(Moved out of `lib/bio.py` into its own `lib/bio_coastal.py` module when the bio pipeline was
split per biome — see §0's module map and §1g. Shared pipeline helpers this section references
(`_focus_local_order()`, `_snapshot_property_count()`) now live in `lib/bio.py` and are
biome-agnostic.)*

Tints a coastal fragment's glow to a `BioOrder.target_glow` via `docs/components/bio_luminizer.md`'s
three lamps: `self.lamp_signature("red"/"green"/"blue")` each give a fixed per-unit `[r,g,b]`
impurity, so setting lamp brightnesses `(r, g, b)` (each a whole number 0-40) produces
`glow = base + r*red_sig + g*green_sig + b*blue_sig`, where `base = self.glow()` read with all
lamps at 0. Solving for `(r, g, b)` given a `target` is a 3×3 linear system, `M @ [r,g,b] = target -
base` (`M`'s columns are `red_sig`/`green_sig`/`blue_sig`) — no numpy, so `_solve_3x3()` inverts it
via a plain-Python closed-form Cramer's rule. Rounded to nearest integer, clamped to `[0, 40]`, then
verified against a live `self.glow()` read; if rounding lands one off, a bounded ±1-per-channel
neighborhood search (≤27 `set_lamps()`/`glow()` round-trips) finds the exact integer match. A
fragment with no active coastal order requiring it passes through unchanged via `self.discard()`.

**Key rules, hard-won (see `DESIGN_HISTORY.md` for the postmortems)**:
- **`exchange.active_order()` is shared, mutable, single-slot delivery-routing state — never use
  it to look up "which order needs this fragment."** Use `_find_coastal_order()`/
  `_focus_local_order()` (scans `exchange.orders()` directly) instead.
- **`set_order()`/`clear_order()`/`deliver()` are `*(self only)*` hardware calls** — a script can
  never drive a sibling machine. Any other controller comparing "does this stack match an order"
  must compare the raw property directly (e.g. `list(stack.properties.get("glow", [])) ==
  list(order.target_glow)`) instead of calling `matches_order()` remotely.
- **A staged sample can itself already be finished, not just raw** — `_order_matching_glow()`
  checks every staged stack individually and ejects (not reloads) one whose glow already exactly
  matches a live order's target; only a stack matching no order's target is treated as raw and
  loaded. `_find_raw_stack()` applies the same exact-glow exclusion when pulling from storage.

### 1f. Raw-Specimen Backlog Control (`lib/bio.py`'s `BioCollectorController`/`BioLabController`, `lib/bio_coastal.py`'s `BioLuminizerController`)

Current mechanism is a **structural idle-gate**, not a numeric backlog cap (several numeric
throttles were tried first and replaced — see `DESIGN_HISTORY.md`): `BioLabController` refuses to
pull its next specimen from the Collector, and refuses to drain its own extracted output, until the
local biome processor is fully idle (chamber/input/output empty — `_processor_is_idle()`, §1g). At
most one raw specimen is ever in flight ahead of the processor at a time, so no Warehouse pileup is
structurally possible regardless of how broadly the Collector searches for "needed" fragments.

- `BioCollectorController.step()` nets demand against a per-cycle `_local_stock_snapshot()` and
  prefers `_focus_local_order()`'s fragments over other incomplete orders' when picking a
  cataloged location to harvest, falling back to any other needed fragment if the preferred
  order's aren't discoverable nearby — a soft preference, not a hard block.
- **No busy-polling**: `_processor_is_idle()`-gated consumers wait on a `"biome_processor_heartbeat"`
  Signal Bus broadcast (every processor controller fires it unconditionally each cycle) via
  `comms.wait_broadcast(...)` instead of `sleep()`, falling back to `sleep(0.5)` if `comms` is
  unavailable or the wait errors.
- **`BioLabController` gates *extraction* on demand too**, not just the idle-gate: once a specimen
  reaches `stage == "analyzed"`, `_bio_demand_totals(comms, exchange, my_biome)` (module-level,
  shared with the Collector's own demand computation) is checked before loading reagents — if
  demand doesn't exceed current local stock, `self.machine.discard()` runs instead of `extract()`.
  This lets "uncataloged discovery" harvesting (which only needs analysis, not extraction) avoid
  spending reagents/storage on a sample nothing would ever collect.
- **Self-cleaning backstop**: `BioExchangeController._cleanup_orphaned_artifacts()` runs every
  `sweep_and_deliver()` cycle after the normal per-order delivery loop — any locally-staged
  glow-tagged stack whose item id isn't required by any incomplete order anywhere is taken into
  `self.machine.input` and destroyed via `input.flush()`. Matches on item id only (not exact glow),
  since a not-yet-tinted raw sample never matches any order's `target_glow` and shouldn't be
  misclassified as orphaned.
- `MAX_LOCAL_BIO_ARTIFACTS = 4` (formerly `MAX_LOCAL_GLOW_ARTIFACTS`, Coastal-only) is a coarse
  total-artifact safety net, on purpose, not the primary mechanism: if the sum of every
  currently-demanded fragment's local stock (`_total_demanded_artifacts(snapshot, fragment_ids)`)
  reaches this, `BioCollectorController.step()` pauses harvesting entirely that cycle. In a healthy
  pipeline this should stay at 0-2 and never trip.
- `best_unload_target()`'s Inventory fallback is gated by `outpost.is_home` (a plain `bool`
  attribute on `OutpostRef`, not a method — the `Outpost` component returned by `get_component()`
  has `is_home()` as a *method* with the same name; watch for this trap) — a remote (Warehouse-only)
  outpost's drain calls skip the `"inventory"` target and return `None` (caller leaves the stack
  staged, retries next cycle) rather than attempting a connection that can't work.

### 1g. Multi-Biome Bio Pipeline (`lib/bio.py` shared + `lib/bio_coastal.py`/`lib/bio_volcanic.py`/`lib/bio_deep.py`/`lib/bio_geothermal.py`)

The Collector→Lab→(transform)→Exchange pipeline is biome-agnostic in `lib/bio.py`; only the
transform step differs per biome, each in its own module (see §0's module map). `get_my_biome()`
always reads `machine.outpost.biome` live — never hardcoded — and `local_biome_processor(outpost)`
probes for whichever of `BIOME_PROCESSOR_TYPE_IDS = ["bio_luminizer", "bio_caster",
"bio_conditioner", "dna_sequencer"]` is actually deployed there, returning `(None, None)` for
Frozen (no transform step) or an outpost without its processor yet.

- **Generic idle-gate**: `_processor_is_idle(processor, processor_type)` dispatches on
  `processor_type` — `bio_luminizer`/`dna_sequencer` expose `.chamber`; `bio_caster`/
  `bio_conditioner` instead expose `.fragment()`.
- **Generic property matching, not just glow**: `_local_stock_snapshot()`'s second return value is
  `by_properties: {(item_id, properties_key): count}` (`_properties_key()` canonicalizes any
  properties dict — sorted, list values tupled). `_order_target_properties(order, fragment_id)`
  resolves what "already correctly processed for this order" means per biome: `{"glow":
  order.target_glow}` (Coastal), `{"genes": order.required_genes[fragment_id]}` (Geothermal),
  `None` for Volcanic/Deep (any correctly Forged/Conditioned unit satisfies any order needing it —
  those two rely on `matches_order()` at delivery time instead).
- `_focus_local_order()` additionally excludes Frozen orders outright (`order.biome == "frozen"`)
  — Frozen has no single-slot processor bottleneck to coordinate around; the Exchange's blanket
  sweep already delivers a plain fragment the moment it's extracted.
- **Bio Caster (Volcanic, `lib/bio_volcanic.py` `BioCasterController`)**: bang-bang heat/cool
  control toward `required_range()` — full `set_heat(100)`/`set_cool(100)` outside a
  `CASTER_APPROACH_BAND_C = 50` °C band around the target range's edge, `CASTER_APPROACH_PCT = 25`
  % near it, both to 0 once `temperature()` is inside the band. Casts once temperature is in range
  AND `materials()` matches `required_materials()` exactly. **Unverified live**: assumes staging
  material into `self.input` via `take()` is enough for `cast()` to auto-consume it, same as a
  Fabricator/Smelter recipe — confirm with `debug()` output the first time a real recipe runs.
- **DNA Sequencer (Geothermal, `lib/bio_geothermal.py` `DnaSequencerController`)**: fully spec'd,
  no live-verification gap. `order.required_genes[fragment_id]` is the splice target, validated
  against `gene_catalog()` before `splice()` (an unknown gene id risks a `"destroyed"` result).
  `chamber.spliced == True` is never spliced again ("one splice per fragment").
- **Bio Conditioner (Deep, `lib/bio_deep.py` `BioConditionerController`) — fully automated.** The
  in-game docs never expose the pass/fail rule for the 10 QC properties, and a wrong `accept()`/
  `reject()` call `"burned"`s (destroys) the specimen. The rulebook (`CONDITIONER_RULEBOOK` in
  `lib/bio_deep.py`) was recovered from the decompiled game client and cross-checked against
  logged outcomes — see `DESIGN_HISTORY.md` for provenance detail:

  | Property | Pass rule |
  | --- | --- |
  | `glow` | `blue`, `green`, or `purple` |
  | `brightness` | 45–80 lm if `glow` is `blue`/`green`; 20–50 lm if `glow` is `purple`; fails otherwise (incl. `white`/`dark`) |
  | `smell` | `salty` or `fishy` |
  | `gunk` | 70–85% |
  | `cracks` | `none` or `small` |
  | `feel` | `hard` |
  | `twitch` | `weak` or `still` |
  | `bugs` | 1–3 |
  | `weight` | 180–260 g, extended to 300 g if `gunk` ≥ 70 |
  | `sound` | `ding`; or `thud` only if `cracks` is `none`/`small` |

  Every stage is recorded to bounded `archive["bio.conditioner_observations"]` history
  (`CONDITIONER_OBSERVATION_HISTORY_LIMIT = 200`) for auditing; an unrecognized `current()`
  property (rulebook gone stale) halts rather than guessing blind.
- **Confirmed live**: a Conditioned fragment's `.properties` carries `{'conditioned': True}`,
  distinct from an untested raw fragment's `properties=None` — `_find_raw_stack()`/
  `_load_next_sample()` skip/recover any stack with `properties.get("conditioned")` truthy instead
  of treating it as raw QC input.

---

## 🚗 2. Surface Vehicles & Logistics

| Vehicle | Speed / Throttle | Energy Cost / Budgeting | Operational Rules |
| :--- | :--- | :--- | :--- |
| **Rover** | `self.cruise_throttle` (explicit at construction, else the fleet-wide `vehicle.default_cruise_throttle` archive value, default 0.5) capped down per-leg by `RoverController.max_safe_throttle_for_leg()` | Developer-confirmed travel model, Rover-specific and flat (no calibration, no Pioneer terms): `Wh/meter = 0.2 × throttle`; safety margin `SAFETY_MARGIN_MULTIPLIER = 1.05` (5%) — see §2a | Sonar scan: `SONAR_WH_BUDGET = 2.0` Wh. Mining drill: exact per-ore/per-drill/per-purity `mine_wh_per_unit(item_id, purity)`, `MINE_WH_PER_UNIT = 2.5` Wh/unit only as the no-item-id fallback — see §2a. Return to nearest charging station (not necessarily home) when Wh falls below the trip budget. |
| **Pioneer** | Configurable slots / tools | Slot chassis: `inspect_slots()`, `execute_construction()`; construction energy: `WH_PER_PROGRESS` (per-vehicle calibrated, default `CONSTRUCTION_WH_PER_PROGRESS_DEFAULT = 40.0` Wh for 0%→100%) — see §2a | Heavy construction, blueprint placement, pipe/power line deployment. Budgets each trip for `TARGET_CONSTRUCTION_PROGRESS_PER_TRIP = 0.25` progress (~4 round trips to finish a job), not just round-trip driving. |
| **Harvester** | BFS on 8x24 grid (`NUM_ROWS=8`, `NUM_COLS=24`, A1..H24) | Travel time: 0.5 h/sector. Empty move: `+7 heat`; Item move: `+1 heat` | Max heat: 100°C. Pause & cool down when heat exceeds `HEAT_SAFE_CEILING = 75.0`, resume once back down to `HEAT_RESUME_LEVEL = 40.0` (`lib/harvesting.py`). |

### 2a. Vehicle Energy Budgeting Detail (`lib/vehicle_energy.py` `VehicleEnergyMixin`)

- **Travel energy is a developer-confirmed exact model, not empirically calibrated — Pioneer and
  Rover use two DIFFERENT models.** Archive-backed Wh/meter calibration was intentionally removed
  for both (treated as ground truth). Construction *progress* energy is still calibrated
  (`wh_per_progress`, no confirmed formula exists for it).

  **Pioneer** (`VehicleEnergyMixin`, used as-is by `PioneerController`):
  ```
  power (W)   = (BASE_TRAVEL_POWER_W=3.0 + MODULE_TRAVEL_POWER_W=8.0 × active_modules
                 + CARGO_UNIT_TRAVEL_POWER_W=0.04 × cargo_units) × throttle^1.5 × nav_power_multiplier
  speed (m/h) = DRIVE_SPEED_M_PER_HOUR_PER_THROTTLE=100.0 × throttle × nav_speed_multiplier
  ```
  - `active_modules` — mounted functional modules that draw power while driving: Nav/Drill/Sonar/
    Constructor family, including upgraded variants (`ACTIVE_MODULE_ID_PREFIXES`). Passive
    containers (Battery Holder, Cargo Rack) don't count. `active_modules_count()`.
  - `cargo_units` — live `self.vehicle.cargo.count()`. `calculate_trip_energy()` computes outbound
    and return legs with *different* cargo loads (return = outbound + `planned_drill_units`).
    `cargo_units_count()`.
  - `nav_speed_multiplier` / `nav_power_multiplier` — from mounted Sport Nav modules. 1 Sport Nav =
    exactly 2x speed / 2.6x power (`docs/components/nav_module.md`); `nav_power_multiplier()`
    linearly extrapolates +1.6x power per +1.0x speed for additional Sport Navs. No Sport Nav gives
    both multipliers `1.0`.

  **Rover** (`RoverController` override in `lib/rover.py`, not part of the base mixin):
  ```
  Wh/meter = ROVER_WH_PER_METER_PER_THROTTLE=0.2 × throttle
  ```
  Developer-confirmed (Spyros - CT Dev, in-game Discord #playtest-chat, 2026-08-28): "the rover is
  very simple wh = distance x throttle x 0.2" — flat, **no** `active_modules`, `cargo_units`, or
  Sport Nav terms, linear in throttle (vs. Pioneer's `throttle^1.5`).
  `RoverController.wh_per_meter_at_throttle()` overrides just that one method —
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
  - **Script-parser constraint**: the sandboxed parser rejects multi-line parenthesized `from X
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
  to the *nearest* charging station, all × `SAFETY_MARGIN_MULTIPLIER = 1.05` (5%), plus a hard
  `MIN_EMERGENCY_RESERVE_WH = 8.0` floor on top. See `calculate_trip_energy()`.
- **Mining/drill budget is also a developer-confirmed exact model, not a flat average.**
  `mine_wh_per_unit(item_id, purity)` (and standalone `mine_wh_per_unit_for(...)`):
  ```
  time (h) = (ORE_DIG_MINUTES[item_id] / 60) × drill.speed_multiplier() / PURITY_DIVISOR[purity]
  Wh       = time (h) × DRILL_POWER_W_BY_HARDNESS_LIMIT[drill.hardness_limit()]
  ```
  Per-tier Watts: basic=10W/industrial=20W/heavy=30W (keyed by `drill.hardness_limit()`, no
  `.power_draw()` method exists). Per-ore dig minutes (`docs/database/items_minerals.md`):
  iron_ore/silicon=15, lead_ore=18, titanium/cobalt=20, rare_earth=25, neutronium=30. Purity yield
  multiplier: `standard`=1×/`rich`=2×/`pure`=3× (same divisor the game's own time formula uses).
  `calculate_trip_energy()`'s `mine_item_id`/`mine_purity` params feed this in; every real mining
  call site passes the candidate's own `harvest_item`/`purity`. `MINE_WH_PER_UNIT = 2.5` (flat) is
  now only a fallback for a candidate with no `mine_item_id` at all — it equals the cheapest real
  case (basic drill, iron ore, standard) but under-reserves by up to **~3.6x** for Heavy/Neutronium
  (`9.0` Wh vs. the flat `2.5` Wh).
- Throttle is clamped to `[MIN_SPEEDMODE_THROTTLE=0.10, MAX_SPEEDMODE_THROTTLE=1.0]` and picked
  per-leg by `select_cruise_throttle()` / `max_safe_throttle_for_leg()`. Because Pioneer power
  scales with `throttle^1.5` while speed scales with `throttle`, Wh/m for a leg scales with
  `sqrt(throttle)` — `max_safe_throttle_for_leg()` solves via `t <= (available_Wh / (distance *
  coeff * SAFETY_MARGIN_MULTIPLIER)) ** 2`.
- **Cruise throttle is one numeric default, not a binary conserve/highspeed flag.**
  `select_cruise_throttle()` picks `min(self.cruise_throttle, MAX_SPEEDMODE_THROTTLE)` as the
  baseline, then caps it DOWN (never up) to whatever `max_safe_throttle_for_leg()` allows.
  `self.cruise_throttle` resolves the same way as `wh_per_progress`: an explicit constructor value
  (the demand-driven transporter role always passes `cruise_throttle=1.0`, since it recharges fully
  at both ends of every leg — §2f), else `default_cruise_throttle()` — a fleet-wide
  `vehicle.default_cruise_throttle` archive value (clamped to `[MIN_SPEEDMODE_THROTTLE,
  MAX_SPEEDMODE_THROTTLE]`, falling back to `DEFAULT_CRUISE_THROTTLE_FALLBACK = 0.5`), settable via
  the Data Archive Notebook or live from `panel_2.py`'s FLEET card slider.
- `minimum_wh_per_meter()` gives the best-case Wh/m at the throttle floor. Any check claiming a
  target/job is *permanently* unreachable (not just "not right now") must budget against this, not
  the typical cruise-throttle rate.
- Two different reserve checks, deliberately kept separate:
  - `energy_needed_to_return_now()` — the true floor, at `minimum_wh_per_meter()`. Used only for
    the **hard mid-drive abort** inside `drive_to()`'s tick loop.
  - `energy_needed_to_return_comfortably()` — rated at `self.cruise_throttle`. Used for every
    **proactive** "keep working or head back" decision (mining stop check, construction Field
    Battery Floor, survey per-POI/per-waypoint reserve checks). A simple heuristic, not an exact
    time/output optimum.
- `drive_to()` computes `is_driving_to_station` once before its polling loop and skips the
  return-reserve abort check entirely when the destination itself is the charging
  station/base slot (or already within 3m of it) — arriving there *is* the recovery.
- Construction (Pioneer only): `calculate_trip_energy()`'s `planned_construction_progress` param
  adds `progress * self.wh_per_progress`. `wh_per_progress` is calibrated per-vehicle from real
  `constructor.execute()` calls (`calibrate_wh_per_progress()`), falling back to
  `CONSTRUCTION_WH_PER_PROGRESS_DEFAULT = 40.0` Wh (0%→100%) until enough samples exist.
  `planned_progress_for_job()` caps planned progress at
  `TARGET_CONSTRUCTION_PROGRESS_PER_TRIP = 0.25` (or less if already further along) — a floor on
  whether to depart, not a cap on-site.
- **Construction job claims (Pioneer only, `run_construction_loop()`, exclusive)**: a construction
  job is NOT shareable (two Constructor Pioneers on the same blueprint would double-load
  materials). Uses `vehicle_claims.py`'s exclusive claim mechanism, key `f"build_{job_id}"`
  (`PioneerController.construction_claim_key()`), distinct prefix from mining's `"site_"`/survey's
  `"poi_"`. `claim_target()` is called at each of the three commit points (resuming a paused job,
  executing a cargo-matching pending job, committing before the round trip home).
  `execute_construction()` heartbeats via `refresh_claim()` every attempt (no-op if not owner).
  Released on completion (`get_construction_progress() >= 1.0`) or genuine failure, kept held
  across an incomplete "still paused" outcome, also released wholesale on an unhandled exception.
- Fleet coordination (`lib/vehicle_claims.py`): atomic `archive.transaction()` claims (mirrored to
  `rover.claims` / `survey.claims`), heartbeat-renewed via `refresh_claim()`, expiring after
  `CLAIM_STALE_TICKS = 36000` ticks (1 sim hour). **Mineral mining sites are no longer exclusive**
  (several Pioneers may mine the same POI) — claim calls still fire for bookkeeping
  (`current_target_key`, mission resume) but never gate candidate selection. Survey/POI targets are
  still exclusive via the same mechanism.
- **In-flight mining yield reservation** (`lib/mining_reservations.py`, `mining.reserved_yield`
  archive key): non-exclusive, additive bookkeeping — several vehicles converging on one deficit no
  longer collide via a claim, but would still see the same undiminished demand without this.
  `VehicleMiningMixin.select_best_mining_target(candidates, reserve_demand=True)` (home-demand path only)
  estimates a trip's yield via `max_mineable_units()` and reserves it; `get_raw_material_demands()`
  subtracts every non-stale reservation's units before returning. Heartbeat-renewed/released
  (`refresh_yield()`/`release_yield()`), same expiry (`RESERVATION_STALE_TICKS = 36000`). The
  **stockpile path** (`build_local_stockpile_candidates()`, `reserve_demand=False`) skips this —
  already self-bounded by each outpost's own `stock_target_for()`.
- **Energy-based mining trip sizing** (`VehicleEnergyMixin.max_mineable_units()`): replaces
  `cargo.capacity()` as the default yield estimate. Solves the trip-energy budget directly for
  units (outbound + base return Wh fixed, mined-unit Wh and marginal return-drive Wh linear in unit
  count) after subtracting `MIN_EMERGENCY_RESERVE_WH` and applying `SAFETY_MARGIN_MULTIPLIER`,
  clamped to `cargo.capacity()`. `mine_until_full_or_exhausted()` remains a safety net for estimate
  drift (e.g. richer-than-expected purity).
- Recall (`lib/vehicle_claims.py`): one shared `vehicle.recall` dict `{vehicle_name: True}` (not
  one archive key per vehicle). `is_vehicle_recalled()`/`set_vehicle_recalled()` module-level
  read/write. Toggled via `panel_2.py`'s Fleet card switch: on → abandons current target, drives to
  base now; off → resumes. Checked inside `drive_to()`'s tick loop and mining loops, with the same
  `is_driving_to_station` exemption as the return-reserve check.
- Navigation timeout (`drive_timeout_ticks()`): defaults to `None`, computed per-leg from expected
  travel time, converted via `Clock.real_seconds_per_hour()` (not a flat constant — the compressed
  day/night cycle stretches game-hours relative to world-clock hours). `safety_multiplier = 2.0`,
  `min_ticks = 3000` floor.
- Navigation safety: stall detection re-issues the drive command after repeated stuck cycles,
  dropping to `MIN_SPEEDMODE_THROTTLE` each retry, giving up after 3 failed recoveries — applies
  regardless of `is_driving_to_station`. Base staging slots are staggered per vehicle index.
- `is_at_base(threshold=3.0)`: `self.distance_to_home() <= threshold`. Gates one-time-per-visit
  actions (top-off charging, restocking) so they only fire when actually parked at base.
- **Loop-top "cargo aboard but not at base" safety net vs. mission resume**:
  `run_expedition_cycle()`/`run_mining_loop()` compute `has_resumable_target` before forcing a
  return-to-base-and-unload detour, so a save reload mid-trip doesn't undo an already-resumed
  drive. `cargo_matches_target(target)` additionally downgrades `has_resumable_target` to `False`
  for that cycle only when cargo already holds a *different* material than the resumed target's
  `harvest_item` (cargo isn't material-locked). A target with no `harvest_item` (survey POI)
  always matches.

### 2a-0. Supply Dock cargo draining (`lib/supply_dock.py` `SupplyDockController`)

`set_order()` rejects with `"cargo_present"` while any cargo is still loaded in the dock's 5 slots
— and `clear_order()` deliberately does **not** drain cargo, only releases the order assignment.
`drain_dock_cargo()` ejects every non-empty slot to Inventory; `step()` calls it (and retries next
cycle) whenever `curr_order` is `None` but `dock.total() > 0`, before attempting `set_order()`.

### 2a-0-1. Construction material demand cascade (`lib/production.py`)

`_cascade_blueprint_demand()` is the single source of truth for "how much of any item — finished
or intermediate — does active construction ultimately need":

- Seeded from `required_item`/`required_count` across every pending/paused Construction Blueprint
  job (summed, deduped by job id).
- Breadth-first propagated down through Fabricator/Smelter recipe `inputs` (`recipe_inputs_for()`).
- **Only each tier's shortfall propagates further down** — demand beyond that item's current
  `inventory.count()`, so stock already on hand is counted once. Example: 10
  `power_line_segment` needed, 3 in Inventory → 7 to build → 7 `titanium_ingot` needed, 5 in
  Inventory → only 2 propagate → 4 `titanium_ore` needed (2:1 smelt ratio), not 20.
- Known limitation: an item reachable via more than one path nets its shortfall against the same
  Inventory snapshot independently at each occurrence, slightly overstating demand under a
  diamond-shaped recipe dependency — not worth a full MRP-style solve for this game's shallow
  (2-3 tier) chains.

Two consumers read this cascade differently:
1. `get_fabricator_targets()` (§2a-1) uses the **raw, uncapped demand** for items the Fabricator
   can build.
2. `get_construction_material_reservations()` nets it against current stock
   (`min(inventory.count(item_id), demand)`) — a protect-from-shipping amount.
   `supply_dock.py`'s `step()`/`pick_best_order()` subtract this before deciding how much to
   `take()` or how "ready" an order looks.

Deliberately conservative: a job's full cascaded demand stays reserved for as long as it remains
pending/paused, even after cargo has already been loaded (cargo isn't tracked here).

### 2a-0-2. Multi-Fabricator Support (`lib/production.py`, `lib/fabricator.py`)

`production.discover_fabricator_ids()`/`_default_fabricator()` replace every hardcoded
`"fabricator_1"` fallback. `claim_recipe()`/`release_recipe()` (`lib/fabricator.py`,
`STALE_TICKS=600`, archive key `"fabricator.recipe_claims"`) prevent several Fabricators
converging on the same recipe: `choose_recipe()`'s candidate loop claims each sourceable candidate
in shortfall order, moving to the next if the claim fails.

- **Pile-on fallback + even split**: if NONE of the candidates can be exclusively claimed (only one
  recipe demanded), `choose_recipe()` joins the biggest-shortfall one anyway rather than idling.
  `_fabricator_worker_count(recipe_id)` (live headcount of Fabricators currently matching that
  recipe) divides `crafts_remaining` by that count (ceil, floored at 1).
- **Load chunking**: `load_inputs()` is capped to `FABRICATOR_LOAD_CHUNK_SIZE = 10` units per call
  (was: the entire remaining batch in one grab). `lib/smelter.py`'s ore top-up has the matching
  `SMELTER_LOAD_CHUNK_SIZE = 10`; Supply Dock's own loading has `SUPPLY_DOCK_LOAD_CHUNK_SIZE = 10`.
- **`production.craft_prefill_units(recipe, item_id, prefill_seconds=INPUT_PREFILL_SECONDS)`**
  (`INPUT_PREFILL_SECONDS = 30`, no archive state) is the actual fairness mechanism — asks "how
  much do I need staged to keep crafting for the next ~30 real seconds" instead of "how much is
  left to load": `ceil(prefill_seconds / craft_seconds(recipe))` crafts' worth, floored at one
  craft's requirement. `craft_seconds()` converts `recipe.duration_game_hours` via
  `SECONDS_PER_GAME_HOUR = lib/power.py's DAY_CYCLE_DURATION_SECONDS / 24.0` (reused, not
  redefined). `lib/smelter.py`'s ore top-up and `lib/fabricator.py`'s `load_inputs()` both cap
  their take amount with this, alongside the chunk-size ceilings above (kept as a simple per-call
  cap, not the primary fairness mechanism). Supply Dock stays on `SUPPLY_DOCK_LOAD_CHUNK_SIZE`
  alone (no recipe/duration to derive a prefill window from).
- **Ore intake demand-size gating** (Smelter Step 3, `lib/smelter.py`): the take amount is
  `max(0, min(50 - in_buf, SMELTER_LOAD_CHUNK_SIZE, max_ore_for_share - in_buf,
  craft_prefill_units(recipe, ore) - in_buf))`, where `share = ceil(demand_qty /
  get_smelter_worker_count(recipe_id))` is this Smelter's fair slice of current total demand
  (re-read fresh every `step()`) and `max_ore_for_share` converts that output-unit share into an
  ore-unit ceiling via `(qty * units_per_run + output_count - 1) // output_count`. A single Smelter
  with a small demand now loads only that much ore, not a reflexive full 50-unit buffer fill;
  several Smelters on one recipe split the demand instead of each independently re-filling to its
  entirety.

### 2a-0-3. Multi-Dock Support (`lib/production.py`, `lib/fabricator.py`)

`discover_supply_dock_ids()` + `_all_dock_orders()` (`[(dock, order), ...]`) replace a single
hardcoded `_component("supply_dock_1")` read in `get_fabricator_targets()`,
`get_material_demands()`, and `get_raw_material_reason()`, so a second dock's active order isn't
invisible to demand tracking. No claim coordination needed here (unlike Fabricator recipes) —
order fulfillment is inherently per-dock; several docks may serve the same order and share shipped
progress (`docs/components/supply_dock.md`), which is explicitly fine. `find_dock_order_requiring(item_id)`
consolidates "which dock's order wants this item," shared by `get_raw_material_reason()` and
`lib/fabricator.py`'s `target_reason()`. §2a-0-5 covers which order each dock should be assigned.

### 2a-0-4. Multi-Fabricator active-recipe input demand (`lib/production.py` `get_material_demands()`)

The "a selected Fabricator recipe is an explicit production intention" block loops
`discover_fabricator_ids()` (falling back to `["fabricator_1"]`) and sums each Fabricator's own
`get_fabricator_active_recipe()` input demand, rather than only ever reading the first discovered
Fabricator. Safe to sum: when several Fabricators share a claimed recipe,
`get_fabricator_active_recipe()` already divides `crafts_remaining` by worker count (§2a-0-2), so
each contributes only its fair share.

### 2a-0-5. Multi-Dock order planning & weekly-deadline feasibility (`lib/supply_dock.py`)

A central planner, `plan_dock_assignments(clock=None)`, runs **once** per cycle from
`panel_7.py`'s AUTOMATION section (throttled to `STORAGE_TICK_INTERVAL`) instead of each dock
independently re-scanning the full Earth Order board every cycle. `set_order()`/`clear_order()`/
`set_enabled()` are all `*(self only)*` hardware calls, so the planner only decides — it writes
`{dock_id: order_id or None}` to the `"supply_dock.order_plan"` archive key
(`ORDER_PLAN_ARCHIVE_KEY`), and each dock's own `SupplyDockController.step()` reads its entry via
`desired_order_id()` and performs the actual `set_order()` call itself.

- **Stability**: a dock already holding a still-`can_fulfill_order()`-true order keeps it
  regardless of ranking — an order mid-shipment isn't cleared over a marginal priority difference.
- **Spread-then-join for idle docks**: candidates are re-sorted before each idle-dock assignment by
  `(docks_already_on_this_order ascending, priority descending)` — idle docks spread across several
  needed orders, but all join the same one if it's the only good candidate.
- **Weekly-deadline feasibility**: `_weekly_infeasible(order, current_day, dispatch_capacity_per_hour)`
  skips a Weekly Earth Order entirely when `remaining_units > dispatch_capacity_per_hour *
  hours_remaining` (`hours_remaining = (order.expires_day - current_day) * 24`) — i.e. even
  shipping flat-out with every known dock's combined `dispatch_rate()`, the remainder can't leave
  before `expires_day`. A dispatch-capacity ceiling only (not a production-rate forecast — folding
  in upstream recipe throughput/worker counts/deficits is a later TODO). Returns `False` (don't
  block) whenever a needed input is missing. Campaign orders (no `expires_day`) are unaffected.
- **Fallback**: `SupplyDockController.desired_order_id()` uses the archive plan when this dock's id
  is present, else falls back to its own weekly-feasibility-aware `pick_best_order()` — a soft
  fallback (unlike the Solar/Smelter hard dependency in §1a-1).
- **Shared scoring**: `_score_campaign_order()`/`_score_weekly_order()`/`_order_readiness()` are
  module-level, used by both the planner and the per-instance fallback — no ranking drift.

### 2a-1. Fabricator demand tracking (`lib/production.py` `get_fabricator_targets()`)

Single source of truth for what the Fabricator should build, feeding `get_material_demands()` →
`get_raw_material_demands()`. Four demand sources folded into one `{item_id: quantity}` dict:

1. `fabricator.stock_targets` archive key (defaults in `DEFAULT_FABRICATOR_STOCK_TARGETS`:
   `gas_pipe_segment`/`power_line_segment`/`liquid_pipe_segment` = 10 each) — edit the archived key
   directly to retune.
2. The active Supply Dock order's `requires`, for items the Fabricator can build (`max()`'d against
   the stock target, not summed).
3. **Pending/paused Construction Blueprints**, via `_cascade_blueprint_demand()` (§2a-0-1), `max()`'d
   against the existing target — not summed (targets are a steady-state floor, not additive per
   demand source).
4. **`fabricator.manual_orders`** archive key (`{item_id: quantity}`, e.g. `{"drone_small": 2}`) —
   ad-hoc build requests, edited directly (no default seeded). `max()`'d into the target like every
   other source, but ALSO given queue priority in `choose_recipe()`: picked ahead of any other
   demanded recipe regardless of shortfall size. Counted down (dropped at 0) by
   `production.consume_manual_order()`, called from `drain_output()` with the quantity actually
   delivered. The key must exactly match a recipe's `output_item` (hand-typed, no validation on
   write) — `get_fabricator_targets()` prints a one-time warning (per-script-run,
   `_WARNED_UNKNOWN_MANUAL_ITEMS`) when a key doesn't match the default Fabricator's currently
   unlocked recipe outputs (heads-up only, can false-positive for a different Fabricator or a
   not-yet-unlocked recipe).

### 2a-1b. Sourceability caching across a pass (`lib/production.py` `SourceCache`)

`can_source_item()`, `can_source_fluid()`, and `can_fulfill_order()` (§2a-0-5) each walk real
game-API calls (Smelter/Fabricator discovery + `list_recipes()`, `outpost.buildings()`,
`journal.surveyed_sites()`, per-Warehouse `count()`), not free local computation.

`SourceCache` (instantiate once per pass, thread it through every call) memoizes:
- `smelter_recipes()`/`fabricator_recipes()`/`surveyed_sites()` — each underlying game call fires
  at most once per cache instance.
- `can_source_item()`/`can_source_fluid()` results per item/fluid-key — a shared sub-item (e.g.
  Steel under both Circuit Panel and Iron Ingot) resolves once, not once per branch that needs it.
  A separate `_item_stack` set handles cycle detection so it never poisons the memo with an
  in-progress answer.
- The stock snapshot: `_build_stock_map()` calls `.stacks()` once per Inventory/Warehouse (returns
  every `ItemStack` in one call) and sums by `.id` into one `{item_id: total_units}` dict;
  `stock(item_id)` becomes a plain dict lookup. Total cost `1+W` calls for the whole pass,
  regardless of distinct items checked — strictly better than a `.count()`-per-item `total_stock()`
  approach (`D*(1+W)`).

All three call sites default `cache=None` (private one-off `SourceCache()`), but hot paths build
and share one explicitly: `plan_dock_assignments()` builds one for its whole pass;
`FabricatorController.choose_recipe()` builds one for its candidate list. A cache instance is a
snapshot for one pass only — never held across ticks or reused between passes.

### 2a-2. Fabricator input-stockpile ejection (`lib/fabricator.py` `eject_excess_inputs()`)

`set_recipe()`/`clear_recipe()` both preserve the input stockpile untouched — the only built-in way
to clear it is `InputSlot.flush()`, which **permanently discards** material. `eject_excess_inputs()`
runs every `step()`, before recipe selection, and recovers stranded/excess staged material via
`InputSlot.eject(destination, item_id, count)` (routes to the least-full Warehouse with room via
`storage.best_unload_target()`, or Inventory — never `flush()`) in two cases (both computed off the
currently-set recipe via `production.get_fabricator_active_recipe()`):

1. Staged material the active recipe doesn't need at all (leftover from a prior recipe, or no
   recipe set) — ejects all of it.
2. Staged material the active recipe DOES need, beyond `required_per_craft * crafts_remaining` (the
   same cap `load_inputs()` loads up to) — ejects just the excess.

`eject()` is transactional and safely no-ops on any portion reserved for an in-progress craft, so
calling this unconditionally every step is harmless.

### 2a-3. Fabricator fluid-input connections (`lib/fabricator.py` `ensure_fluid_connections()`)

A recipe's `fluid_inputs` (e.g. `{"water_in": 1.0}`) is delivered via a `FluidPort` connection, not
an Inventory/Warehouse take. `ensure_fluid_connections(recipe)` runs every `step()`, mirroring
`lib/steam_turbine.py`'s `ensure_input_connection()`:

- For each `fluid_key` the active recipe declares, `production.FLUID_SOURCE_TYPE_IDS[fluid_key]`
  names every building type that can feed it (e.g. `water_in` accepts `water_pump`,
  `steam_condenser`, `liquid_tank`, `large_liquid_tank`) — the same mapping `can_source_fluid()`
  uses.
- **A generic Liquid/Gas Tank existing is not by itself proof it can supply a given fluid** — these
  buffers latch onto whichever fluid is piped in *first* and hold only that until drained to `0`.
  `production.BUFFER_FLUID_TYPE_IDS` + `fluid_building_is_viable(fluid_key, type_id, building)`
  gate both `can_source_fluid()` and this discovery loop identically: a dedicated producer always
  counts (fixed one fluid); a buffer only counts once its own `.fluid()` is already latched to the
  needed fluid (`production.FLUID_LATCH_IDS`). Resolves a bare `BuildingRef` to the live component
  via `get_component(ref.id)` first when the passed-in object has no `.fluid()`.
- **No `is_stalled()` exists on the Fabricator itself** — reachability is inferred from the port's
  own `flow_rate()` staying `0` for `FLUID_STALL_STREAK_BLACKLIST_THRESHOLD=5` *consecutive* ticks
  while it still has room to receive (`level() < capacity()`) — a legitimately full port also reads
  `flow_rate()==0` and must NOT be mistaken for a stall. Same per-entry blacklist expiry as every
  other connect/blacklist controller (`FLUID_RESCAN_INTERVAL_TICKS=150`).
- State (`_fluid_connected`/`_fluid_stall_streak`/`_fluid_unreachable`/discovery cache) is keyed
  per `fluid_key` — a recipe can need more than one fluid at once (oil-refining needs both
  `oil_in` and `water_in`), independent sources.

### 2b. Mining (`lib/vehicle_mining.py` `VehicleMiningMixin`)

Mineral-site discovery and drill execution live in one place, shared by Rover and Pioneer (mixed
into `VehicleController`).

- Capability is always read live via `self.vehicle.drill.hardness_limit()` — never assumed from
  vehicle type. A Rover's fixed Drill only ever carries the basic drill (`hardness_limit = 1`,
  iron_ore/silicon); Industrial (`hardness_limit = 3`) and Heavy (`hardness_limit = 4`) Drills are
  Pioneer-universal-slot items for higher-hardness sites.
- `build_mineral_site_candidates(deprioritize_hardness_at_or_below=None)`: candidate sites matching
  `get_raw_material_demands()` and the vehicle's hardness limit. Passing
  `ROVER_PREFERRED_MAX_HARDNESS = 1.0` sets `priority=3` instead of `2` on hardness ≤ 1 sites — a
  **soft** preference (a capable Pioneer still claims an easy site if nothing harder is pending).
- Neither candidate builder filters out a peer-claimed site (mineral sites are no longer
  exclusive) — see `lib/mining_reservations.py` for what guards against overmining instead.
- `select_best_mining_target(candidates, reserve_demand=False)`: sorts by `(priority, -PURITY_RANK,
  distance)` — priority wins first; within a tier, richer wins over closer
  (`PURITY_RANK = {"standard": 0, "rich": 1, "pure": 2}`); distance only breaks ties between
  equally-rich candidates. A soft preference — `calculate_trip_energy()`'s achievability check and
  `claim_target()` still run after sorting. Both candidate builders attach each site's `"purity"`
  from `getattr(site, "purity", None)`; POI candidates rank as `"standard"`'s `0` by default.
- `mine_current_site(max_units=None)` defaults to `self.vehicle.cargo.capacity()` (read live) when
  no `max_units` given. Home-demand mining loops now always pass an explicit `max_units` from
  `select_best_mining_target()`'s `estimated_units` (energy-based, `max_mineable_units()`).
  `mine_until_full_or_exhausted(target_coords)` wraps it with a recharge-and-resume-in-place loop.
  A battery-interruption recharge stop that lands at the *home base* station itself, with cargo
  already loaded, unloads there via `unload_cargo()` **before** `recharge_at_station()` — so ore
  isn't stranded in cargo for the whole (possibly several-minute) recharge, and the resumed
  `mine_current_site()` call gets the full cargo capacity as `max_units`.
- Pioneer's mining role (`run_stationed_mining_loop(outpost_id)`) requires the operator to have
  already mounted a drill — only checks `hasattr(self.vehicle, "drill")` and idles with an
  advisory if absent; never auto-mounts one.
- **Unified role entrypoint (`PioneerController.run()`/`detect_role()`, `lib/pioneer.py`)**: every
  `pioneer_N.py` script constructs a `PioneerController` and calls `run()`. `detect_role()` maps
  `ROLE_MODULES` (`{"constructor": "constructor", "scout": "sonar", "miner": "drill"}`) via
  `hasattr(self.vehicle, <attr>)` — exactly one mounted module picks that role; none → `"hauler"`;
  more than one is a misconfigured loadout (`TreeConsole` warn + no-op) unless `role_override=` is
  passed. `run()` dispatches: constructor → `run_construction_loop()`, scout → `run_survey_loop()`,
  miner → `run_stationed_mining_loop(self.home_base)` (never the home-demand
  `run_mining_loop()`), hauler → `run_haul_loop(dest_outpost_id=...)`. Equipment is swappable at
  runtime, so this re-probes fresh on every script run rather than caching a role.

### 2b-1. Pioneer Auto-Upgrade (`lib/vehicle_upgrade.py` `VehicleUpgradeMixin`)

Automatic hardware tier upgrades for Pioneer, checked once per idle-at-base cycle
(`handle_upgrade_cycle_if_idle()`, called from the same "parked at base, checking readiness"
checkpoint every role loop already has: `run_mining_loop()`/`run_construction_loop()` in
`lib/pioneer.py`, `run_haul_loop()`/`_stationed_mining_cycle()` in `lib/vehicle_cargo.py`/
`lib/vehicle_mining.py`, `run_survey_loop()` in `lib/vehicle_survey.py` — the last three are
Rover-shared, so the call there is `hasattr(self._host, "handle_upgrade_cycle_if_idle")`-gated).

- **Pioneer-only.** `docs/database/equipment_modules.md` documents Sport Nav, Wide/Deep Sonar, and
  Industrial/Heavy Drill as Pioneer-universal-slot items — a Rover's 3 fixed slots only ever accept
  the basic `nav_module`/`sonar_module`/`drill_module` (§2b), so there is never a better tier for it
  to equip. `VehicleUpgradeMixin` is mixed into `PioneerController` only, never the shared
  `VehicleController` base.
- **Tier tables** (worst → best; `best_unlocked_tier()` only ever steps to the immediate next tier
  present in a fresh `shop.get_catalogue()` read, never straight to the top, so one swap is always
  one affordable purchase):
  - `SONAR_TIERS = ["sonar_module", "sonar_module_wide", "sonar_module_deep"]`
  - `DRILL_TIERS = ["drill_module", "drill_module_industrial", "drill_module_heavy"]`
  - `BATTERY_HOLDER_TIERS = ["battery_holder_small", "battery_holder_medium", "battery_holder_large"]`
    (`_BAY_COUNTS`: 1/2/3 bays)
  - `CARGO_RACK_TIERS = ["cargo_rack_small", "cargo_rack_medium", "cargo_rack_large"]` (1/2/3 bays)
  - `PORTABLE_BATTERY_TIERS = ["portable_battery", "heavy_portable_battery"]` (50Wh/100Wh)
  - `PORTABLE_BIN_TIERS = ["portable_bin", "heavy_portable_bin"]` (25u/50u)
- **Swap ordering (`_upgrade_function_module()`/`_upgrade_containers()`)**: `unmount` old → `shop.buy`
  new → `mount` new → `shop.sell` old — deliberately holds both old and new hardware in Inventory for
  one moment rather than selling first, so a failed purchase can roll back cleanly
  (`mount(slot_index, old_id)` restores the vehicle). A failure *after* the buy (mount rejects, or a
  container's mid-sequence purchase runs out of credits) is left as a logged, non-destructive stop
  state for the operator to notice, not force-rolled-back — nothing is ever silently lost, only
  possibly deferred one cycle.
- **Battery Holder swaps always recharge to ~100% first** (`_ensure_full_charge_for_sale()`) before
  uninstalling any Portable Battery — `shop.sell()` refunds a battery's retained charge% with a 50%
  floor (`docs/components/shop.md`), so selling at full charge maximizes the refund. Cargo Rack swaps
  skip this; Portable Bins aren't charge-valued.
- **Density policy**: every Battery Holder/Cargo Rack bay — newly added by a size upgrade
  (`_fill_container_bays()`) or already-installed at the base tier (`_top_up_container_density()`,
  independent of any size upgrade that cycle) — gets the **Heavy** Portable Battery/Bin once
  unlocked, falling back to the base variant only while Heavy is still locked.
- **Sport Nav is deliberately excluded from the automatic ladder** — it stacks additively onto
  whatever Nav is already mounted rather than replacing it, so it's a manual, one-shot,
  operator-triggered action instead: `request_sport_nav(vehicle_name)` sets a shared
  `{vehicle_name: True}` archive dict (`SPORT_NAV_REQUEST_KEY = "vehicle.sport_nav_request"`, same
  shape/rationale as `vehicle_claims.RECALL_KEY`), surfaced as a per-Pioneer-row button on
  `panel_2.py`'s FLEET card (only drawn when `width >= SPORT_NAV_BTN_MIN_WIDTH = 1100`, wide layout).
  `handle_sport_nav_request_if_active()` consumes it once idle at base: finds the first free
  `universal` slot, buys + mounts `nav_module_sport` if unlocked and affordable. The request flag
  always clears after one attempt, success or failure — a stuck request (no free slot, locked
  research, insufficient credits) does not retry forever; the operator just clicks again once ready.

### 2c. Storage Management (`lib/storage.py`)

Makes the whole production chain aware of Warehouse/Large Warehouse buildings, not just the central
home `"inventory"` endpoint. Scope: Warehouse + Large Warehouse only (`STORAGE_TYPE_IDS`) — Storage
Bin uses a different, single-material API and isn't included yet. Everything defaults to the home
outpost, matching how Inventory only participates at Nocturna Base.

- `total_stock(item_id)` = `inventory.count(item_id)` + every discovered Warehouse's
  `count(item_id)` — what every demand/mining-priority function nets against.
- `best_unload_target(item_id, min_amount=1)`: among Warehouses at `outpost` with
  `space_for(item_id) >= min_amount`, prefers one that **already holds `item_id`** (consolidating
  onto an existing stack), falling back to least-full (`fill_percent()`) only when none already
  stocks it; `"inventory"` if no Warehouse qualifies. `vehicle_cargo.py`'s `unload_cargo()` picks a
  destination **per stack**.
- `consolidate_cross_warehouse_stock(outpost=None)`: calls `.compact()` on every discovered
  Warehouse/Large Warehouse at `outpost` to pull a same-item stock split across more than one of
  them back together — genuinely pulls from *other* storage endpoints, not purely intra-building
  (confirmed live; `.compact()` locks its Warehouse as a material endpoint for the whole cycle).
  Runs once per `STORAGE_TICK_INTERVAL` cycle from `panel_7.py`'s AUTOMATION section for **every**
  outpost (unlike the Inventory-only, home-scoped rebalance sweep below).
- `take_item(port, item_id, amount)`: the one function behind every `machine.input.take(item_id,
  amount)` call site. Tries whatever `port` is currently connected to first, only reconnects to a
  Warehouse if that falls short.
- **Multi-Smelter Coordination** (`SmelterController`) — `production.discover_smelter_ids()`
  replaces hardcoded `"smelter_1"`. No Leader/Follower election — the inventory-manager sweep runs
  centrally from `panel_7.py`'s AUTOMATION section (§1a-1). Each smelter's `select_needed_ore()`
  claims its recipe (`claim_recipe()`/`release_recipe()`, `archive.transaction("smelter.recipe_claims",
  ...)`, `SMELTER_RECIPE_CLAIM_STALE_TICKS = 600`) before crafting, so two smelters don't start the
  same recipe while another demanded ore sits untouched.
  - **Pile-on fallback**: if only ONE ore is demanded, `select_needed_ore()` collects every
    sourceable/demanded candidate, tries to claim each, and if none can be claimed exclusively,
    joins the first anyway rather than idling. No explicit even split needed — `get_material_demands()`
    already nets against `total_stock()`, so joined smelters self-throttle together as the target
    is met.
- **"Inventory manager" sweep** — `rebalance_inventory_to_warehouses()`, called once per cycle from
  `panel_7.py`'s AUTOMATION section: any **propertyless** Inventory item gets moved to a Warehouse
  **entirely** when either it spans more than `INVENTORY_REBALANCE_SLOT_THRESHOLD = 2` slots, or
  it's already split (some units in Inventory, some already in a Warehouse — `_warehouse_item_ids()`).
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
- `inventory_stack_size()`: `10`, or `20` once `research.is_unlocked("research_high_density_storage")`
  ("Bigger Stacks").

### 2d. Outpost Ore-Assignment & Stock-Target Scaffolding (`lib/outpost_mining.py`)

Phase B of the Multi-Outpost Production Network (`TODO.md` Phase 3). Answers "which ores should a
vehicle stationed at outpost X mine?" and "how much before stopping?" — consumed by Phase C's
stationed-mining role (§2e). "Which ores" is answered **live from the Planet Map**, not an archive
list — every surveyed mineral site gets a `"resource.poi_X_Y"` marker whose `.note` names the
responsible outpost.

- **Marker convention**: `RESOURCE_MARKER_PREFIX = "resource."`, id `resource.poi_{x:.0f}_{y:.0f}`,
  `icon="resource"`, `color="neutral"`, `label="{Item Name} - {Purity}"` (`_item_display_name()`/
  `RESOURCE_PURITY_LABELS` build it, `_item_id_from_label()` is its exact inverse). `.note` =
  responsible outpost id, or `""` when unassigned.
- **`sync_resource_marker(site, outpost_id=None)`** — places/updates one site's marker.
  `outpost_id=None` preserves the current assignment (style-only refresh); pass an explicit id
  (including `""`) to change it.
- **`auto_assign_new_site(site, range_m=None)`** — call once per freshly-surveyed mineral site
  (`vehicle_survey.py`'s `scan_and_survey()` does this automatically). Only assigns if not already
  assigned, to the closest owned outpost within `range_m` (default `resource_assignment_range_m()`,
  archive key `RESOURCE_ASSIGNMENT_RANGE_KEY = "outposts.resource_assignment_range_m"`, default
  `200.0`m). Never reassigns an already-assigned site.
- **`reevaluate_unassigned_near_outpost(outpost_id, range_m=None)`** — explicit, **never
  auto-called** sweep: hands any still-unassigned marker within range to `outpost_id`. Re-run (via
  `sync_resource_markers.py`) after founding a new outpost, since CLAUDE.md's Outpost Construction
  Safety Rule means there's no automatic "an outpost just appeared" hook.
- **`assigned_ores_for(outpost_id)` → `[item_id, ...]`** — the read path, called every cycle by the
  stationed-mining candidate builder (§2e).
- **`sync_resource_markers.py`** (project root) — run manually to backfill pre-existing surveys or
  reassign unclaimed markers after founding a new outpost.
- **`stock_target_for(outpost_id, item_id)` → units** — seed-once-then-editable, default
  `WAREHOUSE_SLOT_CAPACITY = 2000` (one Warehouse slot) the first time a pair is looked up.
- **`RAW_ORE_ITEM_IDS`** — the 7 mineable ore item ids (`iron_ore`, `silicon`, `titanium`, `cobalt`,
  `rare_earth`, `neutronium`, `lead_ore`); **`HOME_OUTPOST_ID = "outpost_home"`**.
- **Standing home ore buffer** (`production.py`'s `get_raw_material_demands()`): every raw ore also
  gets a floor demand of `max(0, stock_target_for(HOME_OUTPOST_ID, item_id) - total_stock(item_id))`
  — taken as a **max** with (never additive to) the production-driven deficit. Not a reserved
  stockpile — Smelter/Supply Dock draw on it freely. Both home-based miners and mining-outpost
  transporters read this same demand function. **Overfill avoidance across concurrent haulers**: a
  hauler debits what it just loaded via `mining_reservations.reserve_yield()`
  (`VehicleCargoMixin._reserve_home_haul()`, keyed `"haul:{vehicle_name}:{item_id}"`, released via
  `_release_home_haul()` right after delivery) — same in-flight-debit mechanism as concurrent mining
  trips.

### 2e. Stationed Mining Role (`lib/vehicle.py`, `lib/vehicle_energy.py`, `lib/vehicle_mining.py`)

Phase C of the Multi-Outpost Production Network. Lets a Rover/Pioneer instance treat **any**
outpost — not just home — as its base.

- **`VehicleController.__init__`'s `home_base` param** (an outpost id, or `None` for the
  production/home outpost). Resolved to **live objects exactly once at construction**, cached as
  `self.home_outpost` (`get_outpost_ref(home_base)`) and `self.home_charging_station`
  (`find_charging_station(self.home_outpost)`), rather than re-walking `outpost_network.outposts()`
  by id on every lookup. `get_home_slot_coords()` reads only these two cached fields: the station's
  position if found, else the outpost's own `.coords()`, else `(0, 0)` only if `outpost_network`
  was unavailable at construction. `self.home_base` itself is kept only for identity checks.
  Trade-off: a charging station built at this outpost *after* construction isn't picked up until
  the next script reload.
- **`unload_cargo(outpost=None)`** — defaults to `self.home_outpost` (cached), so a stationed
  vehicle unloads into its own outpost's Warehouse by default; the explicit override exists for
  Phase D's transporter (§2f).
- **`VehicleMiningMixin.build_local_stockpile_candidates(outpost_id)`** — for each ore in
  `outpost_mining.assigned_ores_for(outpost_id)` still under its `stock_target_for()`, builds
  mineral site candidates (same hardness/claim/blacklist filtering as `build_mineral_site_candidates()`)
  additionally requiring `outpost_mining.nearest_outpost_id(site.x, site.y) == outpost_id`.
  Independent of home's live demand entirely.
- **`VehicleMiningMixin.run_stationed_mining_loop(outpost_id)`** — thin wrapper around
  `_stationed_mining_cycle(outpost_id)`: same overall cycle shape as `run_mining_loop()` (reload
  resume, cargo/target mismatch detour, claim + drive + mine + return + unload + recharge, release
  claim right after return), target selection swapped for `build_local_stockpile_candidates()`.

### 2f. Demand-Driven Transporter Role (`lib/vehicle_cargo.py` `run_supply_run_loop()`)

Phase D of the Multi-Outpost Production Network — moves ore Phase C's stationed miners stockpiled
back to **the production outpost** (Nocturna Base). Lives on `VehicleCargoMixin`, shared by Rover
and Pioneer.

**Terminology note**: for every other vehicle, "home"/"base" always means the production outpost.
A transporter breaks that assumption on purpose — constructed with `home_base=<mining outpost id>`
(§2e), so **its own `self.home_base`/`self.home_outpost` point at the stationed mining outpost, not
the production outpost** — only its delivery leg touches the production outpost, via a separately
resolved reference (`self.get_outpost_ref(None)`, held in a variable literally named
`production_outpost`, never `home_outpost`).

- **Construction**: `PioneerController(vehicle, home_base=<mining outpost id>)` — Pioneer, not
  Rover, for this role (Rover's integrated hold is a fixed `capacity() == 10`; Pioneer's cargo
  scales with Cargo Rack loadout).
- **`run_supply_run_loop(poll_interval=10.0)`** — takes no `item_id`: **a load can mix several
  different assigned ores in one trip**, decided fresh every cycle. Each cycle:
  1. `_current_supply_items()` — if cargo is already aboard (resuming after a reload), reads every
     item off `self.vehicle.cargo.stacks()` instead of re-planning.
  2. Otherwise `_plan_supply_load(capacity)` — ranks this outpost's `assigned_ores_for()` by the
     production outpost's unmet demand descending, keeping only ores with stock on hand right now,
     greedily takes `min(unmet demand, stock on hand, remaining capacity)` from each until capacity
     runs out. Empty plan → idle (no preemptive/opportunistic top-off, per CLAUDE.md's
     Demand-Driven Production rule).
  3. **`is_at_base()` check before loading** — drives to the stationed outpost first via
     `return_to_base()` if not already there (`take_item()` needs physical presence).
  4. Loads each `(item_id, amount)` via `storage.take_item(self.vehicle.input, item_id, amount,
     outpost=self.home_outpost)`.
  5. Drives explicitly to `self.get_outpost_ref(None)` (the production outpost) — **not**
     `return_to_base()`.
  6. `unload_cargo(outpost=production_outpost)` — already sends each cargo stack to its own
     destination independently.
  7. **Recharges fully at the production outpost** (`recharge_at_station(target_level=1.0)`) before
     heading back — lets the return leg run at full throttle (`cruise_throttle=1.0`) without
     `drive_with_recharge()` needing an intermediate stop.
  8. `return_to_base()` to its stationed outpost, recharges there too.

  **Since generalized into `run_haul_loop()` (§2g)** — every thin entrypoint script reaches it via
  the unified `PioneerController.run(dest_outpost_id=...)` entrypoint (§2b).

### 2g. Generalized Hauler + Reagent Resupply (`lib/vehicle_cargo.py` `run_haul_loop()`, `lib/outpost_reagents.py`)

§2f's ore-hauler and the Bio Lab reagent-hauler are the same shape: **a transporter is always
stationed at `self.home_base` (the SOURCE) and delivers to an explicit DEST**. Ore-hauler:
source = mining outpost, dest = home (`None`). Reagent-hauler: source = home (`home_base=None`),
dest = the coastal outpost. Every thin entrypoint calls `PioneerController.run(dest_outpost_id=...)`
(§2b), which detects the hauler role (no constructor/sonar/drill mounted) and forwards to
`run_haul_loop(dest_outpost_id, poll_interval=10.0)` — `dest_outpost_id` alone disambiguates the
role (`None` = ore-hauler; any other id = a remote outpost's Bio Lab = reagent-hauler).

- **`_outpost_haul_demand(dest_outpost_id)`** (module-level) is computed fresh every cycle: `None`/
  home → `production.get_raw_material_demands()`; any other outpost id →
  `outpost_reagents.get_outpost_reagent_demand(dest_outpost_id)`.
- **`_plan_haul_load(capacity, dest_outpost_id)`**: when the source is home
  (`self.home_outpost.is_home`, a plain `bool` property on `OutpostRef` — **not** a method, unlike
  the same-named method on the full `Outpost` component from `get_component()`), a candidate's
  "available" amount is its full deficit regardless of stock on hand (a home shortfall can always
  be bought at the Shop); everywhere else, real stock on hand is the hard ceiling.
- **`_load_haul_plan()`**: buys any shortfall **one Inventory-stack at a time**
  (`storage.inventory_stack_size()`), immediately `take_item()`-ing each bought stack into cargo
  before buying the next — bounds the *transient* Inventory footprint, not the total planned
  volume (already capped by cargo capacity). Only triggers when the source is home.

**`outpost_reagents.py`** mirrors `outpost_mining.py`'s seed-once-then-editable convention
(`assigned_reagents_for(outpost_id)`, `reagent_stock_target_for(outpost_id, item_id)`,
`get_outpost_reagent_demand(outpost_id)`), but per-reagent rather than one flat constant (reagent
prices span 1cr to 1,000cr):

```python
DEFAULT_REAGENT_STOCK_TARGETS = {
    "alkaline_buffer": 100, "cryo_solvent": 100, "protein_marker": 60,
    "chelating_agent": 20, "enzyme_solution": 10,
}  # dial these up as credit budget allows; FALLBACK_REAGENT_STOCK_TARGET = 100 covers any
   # reagent id not yet in this dict (e.g. a future game update)
```

Deficit math uses `storage.warehouse_stock(item_id, outpost)`, **never** `storage.total_stock()` —
`total_stock()` unconditionally adds home Inventory's count regardless of `outpost`, which would
over-report a remote outpost's reagent stock by whatever's sitting untouched at home (where the
Shop delivers). `lib/bio.py`'s `local_stock(item_id, outpost)` picks between the two based on
`is_home_outpost(outpost)` (reads `OutpostRef.is_home`, the same property-not-method distinction).

`lib/bio.py`'s `local_sibling(outpost, type_id)` replaces hardcoded same-pipeline instance ids with
a live `outpost.buildings(type_id)` lookup (first match, resolved) — needed because a Bio Lab's
`take_from()` requires its Collector to be at the *same* outpost. No caching — resolved fresh per
call, since a sibling building isn't guaranteed to exist yet at controller-construction time.

### 2h. Drone Energy Budgeting Detail (`lib/drone_energy.py` `DroneEnergyMixin`)

A `DroneController` base (`lib/drone.py`) with scout (`lib/drone_scout.py`) and miner
(`lib/drone_mining.py`) roles, plus `lib/drone_service.py` (charging/rescue) and
`lib/drone_depot.py` (cargo station). Drones are a **fresh hierarchy, not a `VehicleController`
subclass** — no `.drive`/`.nav`, no terrain/stall handling, route-based `go_to(x, y)`/
`go_to_station(name)`/`go_to_drill(name)` rather than a blocking drive loop, and a simpler linear
power/speed model — but `DroneController` follows the same mixin-composition philosophy as
`lib/vehicle.py`. Electric drones only this pass; heli support (`oil_tank`/`refuel()`) can follow
the same pattern later.

- **Linear travel model**: full throttle = **5 Wh/h** at **300 m/h**; both scale with throttle
  (speed linear, burn quadratic), collapsing to `Wh/meter = DRONE_WH_PER_METER_PER_THROTTLE
  (=5.0/300.0 ≈ 0.01667) × throttle` — structurally like Rover's flat model, different constant,
  with **no** per-drone/cargo/module term at all. Standalone `drone_wh_per_meter_at_throttle(throttle)`
  / `drone_rescue_wh_per_meter()` module-level functions let `lib/drone_service.py` reuse the same
  rate cross-script. `max_safe_throttle_for_leg()` solves the safe-throttle bound **directly
  linear** (`t <= available_for_leg / (distance × rate × SAFETY_MARGIN_MULTIPLIER)`). Treat the
  drone's own `range_remaining()` as ground truth; this formula is for planning only.
- **`MIN_EMERGENCY_RESERVE_WH = 4.0`** (vs. `VehicleEnergyMixin`'s `8.0`) — electric drone
  batteries are much smaller. `SAFETY_MARGIN_MULTIPLIER = 1.05` is unchanged.
- **Two distinct "home" endpoints**: `get_nearest_drone_service()` (**power** home —
  `calculate_trip_energy()`/`return_floor_wh()` always budget the return leg against this) and
  `get_nearest_drone_depot()` (**cargo** home). Both are separate `discover_drone_buildings()`
  network-wide calls, each returning `{"id", "coords", "outpost"}` dicts — the `"outpost"` field is
  how `DroneController.__init__` resolves `self.home_outpost`/`self.home_biome`, since **a drone
  has no `.outpost` property of its own** (confirmed against `docs/models/vehicles_and_modules.md`):
  nearest Drone Depot's outpost first, falling back to nearest drone_service's outpost, then the
  network's home outpost.
- **No "biosphere region"** — per-outpost + per-biome: a sample can only be locally processed
  (Essence Liquifier) at the outpost it's dropped off at, and only if native to that outpost's
  biome (`nocturna.life_form_biome(item_id) == outpost.biome`). A miner drone filters
  `journal.biomass_coords()` candidates to samples native to its home outpost's biome
  (`is_home_biome_sample()`). A biosite whose tile carries a **mixed** biome sample set is skipped
  entirely (`PortableBioExtractor.extract()` takes no species argument, so it can't be told to pull
  only the home-biome sample). Cross-outpost ferrying of foreign samples is a deferred TODO.md
  Phase 4 item.
- **Exclusive biosite claims, not shared yield-debit reservations** — biosite extraction is
  exclusive-WITH-COOLDOWN (`journal.is_ready(x, y)`/`next_ready_at(x, y)`,
  `BioExtractionResult.status == "cooling"` only after full depletion), a fundamentally different
  mechanic from mineral mining's shareable sites (§2b). `lib/drone_claims.py`'s `claim_biosite()`/
  `refresh_biosite_claim()`/`release_biosite_claim()` reuse `vehicle_claims.py`'s claim/heartbeat/
  staleness shape (`CLAIM_STALE_TICKS = 36,000`) but on their own archive key (`biosite.claims`) —
  **do not** route biosite selection through `mining_reservations.py`. Miner target order: (1)
  `journal.is_ready(x, y)` cooldown gate (read-only, before any claim attempt); (2) exclusive claim
  attempt; (3) the scout's separate bounded "confirmed-empty POI" cache (`SCOUTED_EMPTY_POI_KEY`,
  coord → tick scanned, capped at `SCOUTED_EMPTY_POI_MAX_ENTRIES = 2000`), kept as a separate
  small archive-key wrapper from `biosite.claims`.
- **Resumability**: `drone.mission:<name>` persists the in-progress target (mirrors
  `vehicle.mission:<name>`). A drone's `go_to()` is fire-and-forget and **is cancelled by a script
  restart** (unlike a rover's persistent `drive_to()` command) — on resume, `run_miner_loop()`
  re-validates the claim, checks `position()`/`current_station()`, and **re-issues** `go_to()`.
  `extract()`/`scan()` themselves do survive a restart transparently — only the flight leg needs
  re-issuing.
- **`lib/drone_service.py`** structurally mirrors `lib/charging.py`: docked charge queue,
  fleet-wide stranded/scrambled detection via `fleet.drones()` (stranded predicate additionally
  includes `"scrambled"`), nearest-station coordination (`is_nearest_station_to()`), and a
  proactive same-outpost nudge for a low-battery field drone (`order_return_to_service()`). A
  station script's cross-script `drone.go_to()` call works despite `drone.md`'s `(self only)` tag
  — `(self only)` documents the intended caller convention, not an engine-enforced restriction (see
  `lib/charging.py`'s `order_return_to_station()` for the same already-relied-upon pattern with
  `nav_module.md`).
- **`lib/drone_depot.py`** is mostly passive — cargo moves via the drone's own `cargo.load()`/
  `cargo.unload()` while docked, ports drain passively once connected. Its controller's jobs: (1)
  one-time idempotent `self.output.connect(...)` wiring to the outpost's Essence Liquifier, only
  when unambiguous (exactly one same-outpost Liquifier — otherwise logged, left for manual wiring);
  (2) periodic telemetry publish (`drone_depot.status.<id>`).

---

## 🗺️ 3. Planet Map Biome Colors (player-observed, verify with `nocturna.biome_at(x, y)`)

| Map Color | Biome |
| :--- | :--- |
| Blue (incl. the base's slightly-green patch) | `frozen` |
| Green | `coastal` |
| Dark brown / red | `volcanic` |
| Light brown | `geothermal` |
| Purple | `deep` |

---

## 📡 4. Inter-Process Communication & Data Archive

### Signal Bus (`get_component("comms")`)
- **Channel `bio_orders`**: Exchange broadcasts open orders -> Collector adjusts harvest target.
  - Payload: `{"order_id": str, "specimen_id": str, "biome": str, "target_fragment": str, "count": int}`
- **Channel `sample_ready`**: Lab notifies Exchange immediately upon sample extraction.
  - Payload: `{"order_id": str, "sample_id": str, "sample_type": str, "lab_id": str}`
- **Channel `system.version_confirmed`**: `panel_1.py`'s "Confirm New Version" button broadcasts the
  newly-confirmed build hash so every script parked in `validate_game_version()` wakes immediately
  instead of polling — see `lib/version_guard.py` and the Data Archive entry below.
- **Channel `luminizer_heartbeat` (retired) / `biome_processor_heartbeat`**: every biome processor
  controller fires this unconditionally each cycle so `BioLabController._wait_for_luminizer()`-style
  waits use `comms.wait_broadcast()` instead of polling — see §1f/§1g.

### Data Archive (`get_component("notebook")` / `lib/archive.py`)
- `power.shedding_tiers`: Custom shedding tiers list-of-lists `[[tier1_machines...], [tier2_machines...], ...]` (or `power.shedding_tiers:<grid_anchor>`). Defaults to `DEFAULT_SHEDDING_TIERS` in `lib/power.py` — see §1a.
- `power.shedded`: Active list of machines Power Guard currently has shedded — hard-shed (breaker
  off) for most Tier 1 patterns, soft-shed (production paused, power stays on) for Tier 2's
  `smelter_*`/`fabricator_*` — see §1a. Checked by `SmelterController`/`FabricatorController`'s own
  `is_shedded()` to pause production.
- `fleet.status.<id>` / `rover.status.<id>`: Telemetry `{name, state, x, y, wh, level, target, tick}`
- `rover.claims` / `survey.claims` (mirrored, legacy + current key): Atomic target reservation dict `{target_key: {"vehicle": id, "tick": tick}}`. Stale after `CLAIM_STALE_TICKS = 36,000` ticks (1 hr) — see `lib/vehicle_claims.py`. No longer exclusivity-gates mineral mining sites (see `mining.reserved_yield` below); still exclusive for survey/POI targets (key prefix `"poi_"`) and construction jobs (key prefix `"build_"`, `PioneerController.construction_claim_key()`, see §2a's construction-job-claims entry).
- `mining.reserved_yield`: Non-exclusive in-flight mining yield dict `{reservation_key: {"vehicle": id, "item_id": str, "units": int, "tick": tick}}`, home-demand mine-type missions only. Stale after `RESERVATION_STALE_TICKS = 36,000` ticks (same window as claims) — see `lib/mining_reservations.py`.
- `survey.unsupported_targets` / `rover.unsupported_targets` (mirrored): Hardware-capability blacklist entries (`reason`, `scanner_type`, `scanner_tier`, `hardness_limit`, unlocked researches) — see `lib/vehicle_claims.py`. Populated per-contact from `SonarScanResult.blocked` (`docs/types/fleet_and_vehicles.md` `BlockedContact`: `.x`/`.y`/`.reason`/`.message`), not from `scan()`'s own top-level `.status` — a wide/deep sonar sweep covers several "?" contacts at once, and `.status` is one verdict for the WHOLE sweep (`"ok"` as soon as any contact in range resolves, even if others in the same sweep stayed blocked), so reading only `.status` silently drops every blocked contact except when nothing at all resolved. `scan_and_survey()` (`lib/vehicle_survey.py`) iterates `res.blocked` and blacklists each contact by its own coordinates instead.
- `heat.optimal_setpoints`: Caching `{thermal_state: best_power}`
- `pressure.optimal_resonance`: Caching `{resonance_state: best_window}`
- `fabricator.manual_orders`: `{item_id: quantity}` ad-hoc Fabricator build requests, edited directly
  in the Notebook (e.g. `{"drone_small": 2}`) — see §2a-1 item 4. Prioritized over other demanded
  recipes and counted down to 0 (then dropped) as units are actually delivered.
- `outposts.known_ids`: List of outpost ids `panel_7.py`'s AUTOMATION section has already seen —
  diffed each throttled tick against `outpost_network.outposts()` to detect a newly-founded outpost
  and auto-trigger `outpost_mining.reevaluate_unassigned_near_outpost()` for it. See §7.
- `control_room.automation_summary`: `panel_7.py`'s one-line automation result string (grids
  supervised, new outposts, docks assigned), published each storage tick for `panel_1.py`'s
  ALWAYS-ON line to display — see §7's headless-calculator/UI-card split.
- `biosite.claims`: Exclusive biosite extraction claims dict `{target_key: {"drone": id, "coords", "name", "tick"}}` — own key, distinct from `rover.claims`/`survey.claims`, so ground-vehicle and drone claims never collide. Stale after `CLAIM_STALE_TICKS = 36,000` ticks — see `lib/drone_claims.py` and §2h. **Exclusive**, not the shared yield-debit pattern `mining.reserved_yield` uses — see §2h's note distinguishing the two.
- `scout.empty_pois`: Scout's bounded "confirmed-empty POI" cache `{"<x>_<y>": tick_scanned}`, capped at `SCOUTED_EMPTY_POI_MAX_ENTRIES = 2000` (oldest entries dropped first). A fixed fact about that coordinate, not a hardware-capability blacklist like `survey.unsupported_targets` — see `lib/drone_claims.py` and §2h.
- `drone.mission:<name>`: Per-drone resumable mission record `{"target_key", "target", "kind", "tick"}`, mirrors `vehicle.mission:<name>`'s shape but on its own prefix. See `lib/drone_claims.py` and §2h's resumability note (a drone's `go_to()` is cancelled by a script restart, unlike a rover's persistent drive command, so only the flight leg needs re-issuing on resume).
- `drone_depot.status.<id>`: Drone Depot telemetry `{name, docked, bay_count, bays_occupied, slots_used, slot_capacity, is_full}`, published by `lib/drone_depot.py` for dashboards and for miner/scout drones' own "is my depot full" decisions.
- `fleet.status.<id>` / `drone.status.<id>` (mirrored): Drone telemetry `{name, state, x, y, wh, level, target, tick}`, same shape/convention as ground vehicles' `fleet.status.<id>`/`rover.status.<id>` — see `lib/drone.py`'s `publish_telemetry()`.
- `system.good_version`: Last operator-confirmed `get_game_version()` build hash (`lib/version_guard.py`).
  Seeded from the current build on first read (a fresh save never immediately halts). Every controller's
  `run()` calls `validate_game_version()` once at startup, before entering its loop (not every tick — a
  build change only takes effect on the next script restart, same as the game itself); if the running
  build no longer matches this key, that script blocks until the operator clicks "Confirm New Version"
  on `panel_1.py` (which updates this key and broadcasts `system.version_confirmed`, see §7). Build
  hashes only support equality checks, never "newer/older" comparisons.

---

## 🏭 5. Hardware Catalog & Production Specs

| Machine | Price | Power Profile | Storage / Capacity | Primary Function |
| :--- | :--- | :--- | :--- | :--- |
| `solar_generator` | 500 cr | +50 W (Day peak) | N/A | Primary green power generation. |
| `battery` | 300 cr | 0 W (Buffer) | 500 Wh | Grid buffer & night power survival. |
| `heat_generator` | 800 cr | -10 W max | N/A | Surface warming. |
| `oxygen_generator` | 1,000 cr | -8 W | 4 units input | Atmospheric CO2 -> O2 conversion. |
| `pressure_generator` | 1,000 cr | -10 W | N/A | Atmospheric pressure builder. |
| `smelter` | 1,500 cr | -20 to -45 W (per active recipe; 0 W when idle/not running) | In/Out slots | Ore -> ingots (Iron, Glass, Titanium). No breaker cycling needed. |
| `bio_collector` | 2,500 cr | -5 W | 30 units | Autonomous biological specimen harvesting. |
| `bio_lab` | 5,000 cr | -5 W | 30 in / 30 stock | Specimen analysis and sample extraction. |
| `bio_exchange` | 2,000 cr | -5 W | Orders queue | Earth biology order fulfillment & credit rewards. |
| `bio_luminizer` | 60,000 cr | -12 W | 10 in / 10 out | Coastal glow-tinting (3-lamp mix solve, §1e). |
| `bio_caster` | 150,000 cr | -15 W | 30 out, 20t steam/water buffers | Volcanic forge-casting (heat/cool band control, §1g). |
| `bio_conditioner` | 225,000 cr | -25 W | 10 in / 10 out | Deep QC quiz (automated, §1g). |
| `dna_sequencer` | 100,000 cr | -20 W | 10 in / 10 out | Geothermal gene-splicing (§1g). |
| `supply_dock` | 3,000 cr | -15 W | 50 units | Earth / Contractor campaign bulk order shipping. |
| `vehicle_charging_station`| 2,000 cr | -50 W max | Pad + Rescue drone| Vehicle fast-charging & automatic rescue dispatch. |

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

## 🖥️ 7. Control Room Panel Cards (`panel_1.py`..`panel_4.py`)

**Headless calculator + UI card split (currently `panel_4.py` + `panel_1.py`).** The automation
calculator (grid supervision, rebalance sweep, outpost sync,
`supply_dock.plan_dock_assignments()`) is **headless** (no `panel.*` calls,
`sleep(1.0)`-paced) and publishes its result summary to `archive`
(`AUTOMATION_SUMMARY_KEY = "control_room.automation_summary"`); the STATUS/AUTOMATION UI card reads
that summary back out instead of computing it — a multi-second automation stall must never also
block a script that renders every tick, and a Custom Panel is the only slot that can host an
"always-on, not tied to one building" process. See `DESIGN_HISTORY.md` for the incident that forced
this split.

**⚠️ Two separate numbering schemes, do not conflate them.** The game's own Custom Panel ids are
assigned on creation and **only ever increment** — deleting a panel does not free its number, and
cards **cannot be drag-reordered** once placed. `panel_4.py`/`panel_5.py`/`panel_6.py`/`panel_8.py`
are **dead in that live-slot numbering** (deleted during testing, gone for good; the next new panel
in-game will be `panel_9.py`). Separately, since the [tiered `scripts/` restructuring](#-9-dev-workflow-tiered-scripts--devtoolsscripts_syncpy),
the *source-tree* files under `scripts/4_controlpanel/control_panel/` were cosmetically renumbered
`panel_1.py`..`panel_4.py` (four panels total, in role order) — this is a dev-side naming choice
only, decoupled on purpose from the live-slot numbers above, and does **not** mean live slot 4 is
back in use. Current mapping (verified live, live-slot column is authoritative for the actual save):

| Role | Source-tree file | Live save slot | Notes |
| :--- | :--- | :--- | :--- |
| STATUS + AUTOMATION UI | `panel_1.py` | `panel_1.py` | wanted at the top of the Control Room; kept in the original slot 1 |
| FLEET | `panel_2.py` | `panel_2.py` | unchanged |
| PRODUCTION | `panel_3.py` | `panel_3.py` | unchanged |
| Automation calculator (headless) | `panel_4.py` | `panel_7.py` | moved here from `panel_1.py`; position doesn't matter since it draws nothing. Source-tree name and live slot name **differ** — see TODO.md's "Panel dev-side numbering vs. save-side slot numbers" for the known sync-tool gap this creates |

**Whenever a panel is added or removed in-game, re-verify this table (ask the operator for the
current mapping) and update every `panel_N.py` cross-reference in this file and in the scripts'
own module docstrings** — a stale filename here is actively misleading.

Card size is set from the Control Room UI (drag-resize / size picker), **not** the script —
`panel.width()`/`panel.height()` just report the operator's chosen size. Discrete, not continuous:

| Label shown in the UI | Meaning | `panel.width()` | `panel.height()` |
| :--- | :--- | :--- | :--- |
| `1 x 1` | 1 column, 1 row | 500 | 200 |
| `1 x 2` | 1 column, **2 rows** | 500 | 400 |
| `2 x 1` | **2 columns**, 1 row | 1000 | 200 |
| `2 x 2` | 2 columns, 2 rows | 1000 | 400 |

First number = columns (width), second = rows (height) — `1x1` to `1x2` only adds height, not
width. A wide-canvas layout (side-by-side sections, a right-anchored control) will clip on a `1x2`
card since it's still only 500px wide.

**Sizing recommendations** (`panel_7.py` draws nothing, no card/size to set): `panel_1.py` (STATUS
+ AUTOMATION) → **`2 x 2`** (1000x400), splitting `panel.height()` ~55/45 between its two sub-cards
(not a fixed pixel split, so it degrades reasonably at `2 x 1`). `panel_2.py` (FLEET, one row per
vehicle) / `panel_3.py` (PRODUCTION, one row per Smelter + Fabricator + Supply Dock — discovered
live via `discover_smelter_ids()`/`discover_fabricator_ids()`/`discover_supply_dock_ids()`, each
row a role pill + current recipe/order + status pill) share the same one-row-per-item scrollable
shape → **`2 x 1`** for a handful of rows, **`2 x 2`** once you have more. Each shows as many rows
as fit (`max_rows = (height - top - 16) // row_height`); a `panel.slider()` repurposed as a scroll
bar (0-1 value → row offset, `round(value * (len(rows) - max_rows))`) covers the rest, only drawn
once the list exceeds `max_rows`. Both degrade at 1-column widths (`wide = width >= 900` branches
to a shorter row height, and `panel_2.py` hides the location column).

**`panel_7.py`'s automation work, displayed on `panel_1.py`'s AUTOMATION card** — §1a-1's
centralized Power Grid supervision + Smelter rebalance sweep, plus:
- **Outpost-founding → resource marker auto-reassignment**: diffs `outpost_network.outposts()`'
  current id set against the stored `outposts.known_ids` (archive list) each throttled storage
  tick; any **new** id gets `outpost_mining.reevaluate_unassigned_near_outpost(new_id)` (§2d)
  called automatically. `sync_resource_markers.py` remains for manual backfill/batch catch-up.
- **Two independent throttle timers**: `SOLAR_TICK_INTERVAL = 10` ticks (~1s) gates grid
  supervision (cheap, no Auto Feeder transfers); `STORAGE_TICK_INTERVAL = 100` ticks (~10s)
  separately gates `rebalance_inventory_to_warehouses()` + the outpost-diff/
  `consolidate_cross_warehouse_stock()` sweep — both `.transfer_to()` and `.compact()` lock their
  Warehouse as a material endpoint for the whole transfer, so a faster shared cadence risks
  contention (a `"busy"` rejection on a Smelter/Fabricator `take_item()` call) that grid
  supervision has no equivalent cost for. Both intervals gate via `clock.tick()` (not wall-clock),
  correct under time acceleration.
- **`panel.button("run_archive_cleaner", ...)`** on `panel_1.py` — `ArchiveCleaner(dry_run=False,
  verbose=True).run()` (§4), live-commit, human-triggered only, executed directly in that UI
  script (rare one-off, not chronic per-cycle work).
- **`panel.button("run_unsupported_markers", ...)`** on `panel_1.py` — `lib/unsupported_markers.py`'s
  `update_unsupported_markers(clear_previous=True)`, also human-triggered only, executed directly
  in `panel_1.py`. Also runnable standalone as the root entrypoint `mark_unsupported_targets.py`.
- **Version safety gate widget** (`lib/version_guard.py`, §4), drawn on `panel_1.py`: a `VERSION`
  pill anchored `width - 190` from the right edge (always drawn, success/error colored) plus, only
  while `version_mismatch()` is true, a `was <old> -- new scripts halt on startup` note and a
  `panel.button("confirm_new_version", ...)`. Neither `panel_7.py` nor `panel_1.py` calls
  `validate_game_version()` itself — both independently check `version_mismatch()` and gate their
  own mutating work behind `if not mismatch:` — `panel_1.py` keeps rendering and stays clickable
  during a mismatch but neither script makes changes until confirmed.

**General layout rules for any new card** (see `DESIGN_HISTORY.md` for the overlap bugs that
produced these):
- `card(x, y, w, h, title)` already renders its own title bar text — never add a second
  `panel.label()` re-rendering the same title.
- A named widget that draws its own label (`slider`, likely `switch`/`button` too) should have any
  live value folded INTO that label string, not drawn as a second, separately-positioned text
  element beside it.
- A `pill()` needs more vertical clearance below it than a plain text line — leave at least ~24px,
  not ~16px, before placing anything under one.
- Prefer anchoring right-side elements from the right edge (`width - <fixed px>`) over a width
  fraction (`width * 0.86`) for anything with a roughly fixed pixel footprint (`switch`, `button`,
  short `pill`) — fractions of a 500px vs 1000px canvas land in very different places.

---

## 🐞 8. Live Debugging via External IDE

The game exposes a real Debug Adapter Protocol (DAP) integration — breakpoints, conditions,
logpoints, call stacks, locals, watches, hover inspection, Step Over/Into/Out — against the actual
running game interpreter, not a simulation. Setup and full details:
`C:\Users\Adrian\AppData\Roaming\io.codeterraform.game\external-ide\README.txt`.

- **VS Code** (the supported path, extension already installed this save): open a script, set a
  breakpoint, press **F5**. An idle script starts running; an already-running script attaches
  without restarting. **Shift+F5** or closing the debug session disconnects but leaves the script
  running in the game — use **Stop Script in Game** to actually stop it. Watches/Debug Console are
  **read-only** (can't execute world actions or assign variables). Edited main-script code needs
  **Run Script in Game** before re-attaching; edited Libraries need re-applying in the game.
- **Any other DAP-capable editor**: launch
  `node "C:\Users\Adrian\AppData\Roaming\io.codeterraform.game\external-ide\server\debug-adapter.cjs"`
  (Node.js 20+, stdio transport) — `launch` to attach-and-run an idle script, `attach` to inspect one
  already running. Set `workspace` to this save's scripts directory, `script` to the target file.
- **Non-debug editor tooling** (LSP-only, no execution): `external-ide\server\server.cjs --stdio` —
  already documented per-editor (neovim/Helix/Sublime) in the README; PyCharm needs a generic LSP
  plugin, since its own Python checker doesn't know the game's owner globals/runtime rules.
- Console output mirrors to `external-ide\logs\all.log` (plus one file per script) — useful to tail
  even without attaching a debugger at all.
- **`tools/dap_client.py`** — a minimal DAP client for driving a debug session directly from a
  script instead of VS Code (Node.js 20+ required; this save's copy lives at
  `C:\Program Files\nodejs\node.exe`, not on the default shell `PATH` — invoke by full path, or
  `export PATH="/c/Program Files/nodejs:$PATH"` for the current shell session only, since shell
  state doesn't persist between tool calls here). `DapClient` is the low-level stdio transport
  (Content-Length framing, background reader thread); `run_session(workspace, script, breakpoints,
  mode, on_stopped, wait_timeout)` wraps the full initialize → attach/launch → setBreakpoints →
  configurationDone → wait-for-`stopped` → callback → continue → disconnect sequence in one call.
  Also runnable directly: `python tools/dap_client.py --workspace <dir> --script <path> --break
  <file.py>:<line> [--mode attach|launch]` — prints the stack trace and top-frame locals at the
  first hit, then resumes and disconnects. Verified live against `rover_1.py`/`lib/vehicle.py`: a
  breakpoint inside `publish_telemetry()` correctly paused execution, reported the true call stack
  and real locals, then resumed cleanly leaving the script running.
  - **`launch` starts idle scripts without breakpoints**: `dap_client.launch_script(workspace, script)`
    (or CLI `python tools/dap_client.py --workspace <dir> --script <path> --launch`) sends `initialize` →
    `launch` → `configurationDone` with no breakpoints set, triggering `{ action: "start", runIfIdle: true }`
    in `debug-adapter.cjs`. It then cleanly disconnects with `terminateDebuggee=False`, leaving the freshly-started
    script running in the live game.
- **Automated Script Deployment (`tools/auto_deploy.py`)**:
  - Automatically bridges newly placed/deployed hardware (via in-game `computer.deploy(...)`) to their host-side Python controller scripts.
  - **Dual-Channel Monitoring**:
    - Watches `logs/all.log` for explicit `[DEPLOY]` lines with arbitrary parameter assignments (e.g. `[DEPLOY] machine_id=pioneer_5 template=pioneer_hauler HOME_BASE="outpost_3" DESTINATION="outpost_home"`).
    - Periodically scans `codeterraform-workspace.json` for newly registered machines whose script slots are idle and unpopulated.
  - **Template Directory (`tools/templates/`)**:
    - Stores modular templates (e.g., `solar.py`, `heater.py`, `smelter.py`, `pioneer_hauler.py`).
    - Supports flexible parameter substitution: `${PARAM:default_value}` or `{PARAM}`.
    - Built-in variables automatically injected: `MACHINE_ID`, `TYPE_ID`, `LOCATION_ID`.
  - **CLI Modes**:
    - `python tools/auto_deploy.py --scan`: One-shot scan and deploy for all unscripted idle machines.
    - `python tools/auto_deploy.py --scan --dry-run`: Preview generated script code and parameters without modifying disk or launching.
    - `python tools/auto_deploy.py --daemon`: Continuous background watcher loop.
    - `python tools/auto_deploy.py --deploy <machine_id> [--template <name>] [--param KEY=VALUE ...]`: Targeted single-machine deployment.

**Before starting any debug session (F5/`launch`/`attach`) or using **Run Script in Game**:
If we're running the user's main save (save_mtzkzly3_4ww80o): ask the user first, every time —
never assume standing permission from a prior yes.** A debug session runs
against the live save with real effects (a script that spends credits, moves a vehicle, fires a
drill, etc. does so for real, not in a sandbox) — pausing at a breakpoint can also leave a machine
mid-action in a state the player didn't intend. Treat this the same as any other action with
real-world (real-save) side effects per this project's risk-awareness rules, not as a routine
read-only inspection step.
In other — throwaway — saves you can be more liberal, especially when developing the auto-play
tools like `tools/auto_deploy.py`, `tools/early_game.py`, etc.

## 🧬 9. Dev Workflow: Tiered `scripts/` + `devtools/scripts_sync.py`

This repo (`C:\Users\Adrian\Code_Terraform`) is a dev root, separate from any live save folder (`%APPDATA%\io.codeterraform.game\save_*_scripts`). Source of truth lives under `scripts/<tier>/<category>/<name>.py`; `devtools/scripts_sync.py` (adapted from `inspirations/vakermit/bin/ct_sync.py`) fills the save folder's numbered script slots and mirrors `lib/` from it. See the tool's module docstring for the full mechanics (fill/pull markers, renumbering, `_unmatched/` staging) — this section covers the project-specific tiering layer on top.

**Tier list** (`TIER_ORDER` in `scripts_sync.py`), each gated by a `.criteria` file at its root (absent for `0_cold_boot`, the always-active baseline):

| Tier | `.criteria` | Unlocks (tech id / `research_*` id) |
| :--- | :--- | :--- |
| `0_cold_boot` | *(none — baseline)* | — |
| `1_early` | `{"tech": ["ship_computer"]}` | `research_computer` |
| `2_libunlock` | `{"tech": ["shared_library"]}` | `research_shared_library` |
| `3_archiveunlock` | `{"tech": ["data_archive_unlock"]}` | `research_data_archive` |
| `4_controlpanel` | `{"tech": ["custom_panels_unlock"]}` | `research_custom_panels` |
| `5_uprising` | *(placeholder — see TODO.md)* | TBD |

`.criteria` keys use the save file's own **tech ids** (from `state.unlockedTech`), not the `research_*` ids used in `docs/database/research_catalog.md` — the table above is the mapping. Supported keys: `"tech": [id, ...]` (all must be present) and `"outpost_count": N` (`len(state.planet.outposts) >= N`). A **higher-numbered TP field wasn't found** in the save state on a quick pass, so TP-threshold criteria aren't supported yet.

**Active-tier resolution** is fully automatic and per-save: `scripts_sync.py` derives the sibling save-state file from the save-scripts dir name (`save_X_scripts/` → `save_X.json`, one level up), reads `state.unlockedTech` / `state.planet.outposts` **read-only**, and walks the tier list evaluating `.criteria` until one fails — the highest passing tier is active. No hint file, no manual bookkeeping; `--force-tier NAME` overrides for one run without persisting anything. Confirmed live against a real save this session (`python -c` one-liners against `save_mtzkzly3_4ww80o.json`).

**No duplicate files across tiers**: for a given `category/base_name` (including the `lib` category), the resolver walks tiers from the active one down to `0_cold_boot` and uses the first file found. A higher tier only needs its own copy when behavior genuinely diverges.

**Migration note**: the codebase existing before this restructuring was written and tested against a save that already had 60 techs unlocked (including `data_archive_unlock` and `custom_panels_unlock`), so it was moved wholesale into `4_controlpanel/` as its honest home tier (see `devtools/_migrate_from_root.py`) rather than guessed apart by file. `0_cold_boot`/`1_early` were separately seeded from `inspirations/vakermit`'s community `tools/templates/` (flat) and `tools/templates/early/` (richer) boilerplate, which don't depend on Archive/Signal Bus/Control Room. Retroactively splitting the `4_controlpanel` content into what could also run on an earlier-tier save is a manual follow-up (see TODO.md), not something done automatically.

**`panel` is a distinct-instances category** (`DISTINCT_INSTANCES` in `scripts_sync.py`), living at `scripts/4_controlpanel/control_panel/panel_1..4.py` — separate, genuinely different hand-authored Control Room cards (see §7), not interchangeable copies of one template; matched by exact filename, never collapsed to a shared base name or renumbered. Dev-side numbering was cleaned up to `_1.._4` (the fourth was `panel_7.py`, `_7` being just an artifact of which slot the game happened to assign), but the game can't rename/reorder an existing script slot, so the save's actual file is still `panel_7.py` — this is a known, documented gap (see TODO.md), not yet bridged.

**Pyright/IntelliSense**: `pyrightconfig.json`'s `extraPaths` point at `.pyright-resolved/lib` (regenerate with `python devtools/scripts_sync.py resolve-preview`, gitignored) plus the live save folder for game-API stubs. This is a real, accepted limitation, not fully solved: a module referenced by a higher tier that hasn't been reached in the actual playthrough won't resolve until you `resolve-preview --force-tier <name>`, and the game's own in-editor syntax highlighting/autocomplete (tied to `codeterraform-workspace.json`) doesn't apply to source living outside a save folder at all — check the deployed copy in the save folder when that's needed.

**`--auto`** (off by default) additionally calls `tools/dap_client.py`'s `launch_script()` after filling a slot. This is automation the operator explicitly opts into per invocation, not Claude starting a live-debug session on its own — see CLAUDE.md's Live Debugging rule, which binds Claude's own actions, not a flag on a tool the user runs themselves.
