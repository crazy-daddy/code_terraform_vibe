# Code: Terraform — AI Agent Quick Reference Cheat Sheet

Dense ref: physics, formulas, component specs, bus channels, data conventions.
**Single source of truth for tunable numbers and definitions** for every agent on project — this hub plus the topic files in [`cheatsheet/`](cheatsheet/). Change tunable constant in code (safety margins, tiers, thresholds, stale-tick counts, budgets, etc.) → update the section that documents it, same change. Other docs (`CLAUDE.md`, `TODO.md`) point at constant/module name, not restate value — one place to keep current.

**Current state only.** Describe what the code does now — no "previously", "was changed", "bug fixed on …", "found live" narration. *Why* behind design (postmortems, rejected approaches, history) → **[`DESIGN_HISTORY.md`](DESIGN_HISTORY.md)** and commit messages.

### Section index

Section numbers are stable; code comments cite them as `AI_CHEATSHEET.md §2c` etc. Find the file here.

| § | Topic | File |
| :--- | :--- | :--- |
| 0, 0a, 0b | `lib/` module map, runtime limits, `TreeConsole` logging, `swallowed()` | this file |
| 1 | Terraforming formula table | this file |
| 1a, 1a-0, 1a-1 | Brownout load-shedding, steam-aware Power Guard, grid ownership | [`cheatsheet/power_fluids.md`](cheatsheet/power_fluids.md) |
| 1b, 1c, 1c-1 | Steam loop, fluid routing, Fluid Pump, Oil Generator | [`cheatsheet/power_fluids.md`](cheatsheet/power_fluids.md) |
| 1d | Tick-cost profiling | [`cheatsheet/dev_workflow.md`](cheatsheet/dev_workflow.md) |
| 1e–1h-1 | Bio pipeline (Luminizer, backlog gate, biomes, essence/Mixer, biomass-complete retirement) | [`cheatsheet/bio_seeds_planting.md`](cheatsheet/bio_seeds_planting.md) |
| 1i, 1k | Seed discovery sweep, planting (layout, Harvester, field machines, Terraformer) | [`cheatsheet/bio_seeds_planting.md`](cheatsheet/bio_seeds_planting.md) |
| 1j | Field Mining Drill telemetry | [`cheatsheet/production_logistics.md`](cheatsheet/production_logistics.md) |
| 2, 2a | Vehicle table, vehicle energy budgeting, claims, recall, navigation | [`cheatsheet/vehicles_drones.md`](cheatsheet/vehicles_drones.md) |
| 2a-0 … 2a-3 | Supply Dock, demand cascade, multi-Fabricator/Smelter/Dock, `SourceCache` | [`cheatsheet/production_logistics.md`](cheatsheet/production_logistics.md) |
| 2b, 2b-1 | Vehicle mining, Pioneer roles, Pioneer auto-upgrade | [`cheatsheet/vehicles_drones.md`](cheatsheet/vehicles_drones.md) |
| 2c, 2d | Storage management, outpost ore assignment | [`cheatsheet/production_logistics.md`](cheatsheet/production_logistics.md) |
| 2e, 2f, 2g | Stationed mining, transporter/haul cycle, reagent resupply | [`cheatsheet/vehicles_drones.md`](cheatsheet/vehicles_drones.md) |
| 2h, 2j, 2k | Drones (energy, home, claims, depot, service), drone hauler, fleet upgrade | [`cheatsheet/vehicles_drones.md`](cheatsheet/vehicles_drones.md) |
| 2i, 2k-1 | Pull logistics + reverse hauler, Warehouse → Large Warehouse | [`cheatsheet/production_logistics.md`](cheatsheet/production_logistics.md) |
| 3, 5, 6 | Biome colors, hardware catalog, invocation pattern | this file |
| 4 | Signal Bus channels, Data Archive keys | [`cheatsheet/archive_ipc.md`](cheatsheet/archive_ipc.md) |
| 7 | Control Room panels | [`cheatsheet/panels.md`](cheatsheet/panels.md) |
| 8, 9 | Live debugging, tiered `scripts/` + `scripts_sync.py` | [`cheatsheet/dev_workflow.md`](cheatsheet/dev_workflow.md) |

## 🗺️ Progression Walkthroughs & Speedrun Guides

High-level workflows, progression roadmaps, automation orchestration → dedicated walkthrough guides:

- **[`manual_walkthrough.md`](../early_game_runner/manual_walkthrough.md)**: **Manual Progression Roadmap (0 $\rightarrow$ 1,000,000 TP Victory)**
  - Manual progression playbook: First Contact onboarding, Earth Clearance contract solvers (+3,750 cr & +22,500 cr), research prereqs, critical bottleneck matrix, chronological phases from Phase 0 (Cold Boot) to Phase 7 (Deep Biome, Nuclear Reactor Recovery & Endgame Victory).
- **[`auto_walkthrough.md`](../early_game_runner/auto_walkthrough.md)**: **Autonomous Architecture & Early Speedrunner (0 $\rightarrow$ 150,000 TP)**
  - Hands-off automation blueprint: Master Automation Architecture, revised 25-slot Nocturna Base speedrun, `solar_1.py` master building-buyer (auto buy/deploy/sell cycles), `early_game_runner/early_game.py` speedrunner daemon & machine watcher, Earth Clearance contract solvers, 150k TP mid-game migration protocol to `lib/`.
- *(Top-level nav hub: [`walkthrough.md`](../early_game_runner/walkthrough.md))*

## 🧱 0. Shared Library Module Map (`lib/`)

> Physical location: `scripts/<tier>/lib/<module>.py` (tiered, see §9 in [`cheatsheet/dev_workflow.md`](cheatsheet/dev_workflow.md)) — not flat top-level `lib/`. `devtools/scripts_sync.py` resolves right copy per module per active tier, mirrors into save folder's `lib/`. Module names below logical; nearly all currently under `scripts/4_controlpanel/lib/` — tier codebase actually written/tested against (see §9).

| Concern | Module(s) |
| :--- | :--- |
| Terraforming (heat/pressure/O2) | `terraforming.py` (`HeatController`, `PressureController`, `OxygenController`) |
| Power grid & brownout | `power.py` (`PowerGridManager` — generic, solar/oil/reactor/turbine grids, owned centrally by headless automation panel, one instance per grid, no election — see §1a-1); `solar.py` (`SolarController` — pure sun tracking, no grid supervision) |
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
| &nbsp;&nbsp;↳ floating hauler role loop (drills and Depot outposts → Depots, no home) | `drone_hauler.py` — see §2j |
| &nbsp;&nbsp;↳ fleet-upgrade handshake, new-chassis fitting, in-place module upgrades (+ shared `fleet.upgrade` state helpers) | `drone_upgrade.py` — see §2k |
| Fleet hardware upgrade coordinator (Depot + drone chassis swaps), run by headless `panel_4.py` | `fleet_upgrade.py` — see §2k |
| Warehouse pair → Large Warehouse swap (buy, deploy, greedy drain, undeploy, sell), run by headless `panel_6.py` | `warehouse_upgrade.py` — see §2k-1 |
| Drone Service Station (charging/refuelling/rescue) | `drone_service.py` — see §2h |
| Drone Depot (cargo logistics endpoint) | `drone_depot.py` — see §2h; drains freight to local storage, buffers life forms in a local Warehouse (two stacks per form), stages hauler pickups, flushes surplus |
| Depot staging requests (hauler → source Depot) | `depot_stage.py` — see §2j; `depot.stage` archive dict |
| Pull logistics (outpost item requests, need/buffer tiers, fair share, in-flight pickups, source retention) | `logistics_requests.py` — see §2i; reverse hauler lives in `vehicle_cargo.py` `run_pull_loop()` |
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
| Biomass completion: retire Liquifiers/Mixers, sell button | `biomass_retire.py` — see §1h-1 (tier 5 lib; imported by `drone_mining.py`/`drone_depot.py`/`panel_1.py`/`panel_4.py`) |
| Waste Processor (destroy surplus at its outpost, today life forms after biomass completion) | `waste_sink.py` — see §1h-1 (tier 5) |
| Shared network-wide fluid-target discovery/blacklist/reconnect | `fluid_routing.py` — `FluidOutputRouter` (`thermal_cap.py`/`fluid_pump.py`/`essence_liquifier.py`), `FluidInputRouter` (`steam_turbine.py`/`fabricator.py`/`biomass_mixer.py`/`oil_generator.py`); see §1b |
| Storage management (Warehouse-aware sourcing/unloading, Inventory rebalancing) | `storage.py` — see §2c |
| Outpost ore-assignment & stock-target scaffolding (multi-outpost mining) | `outpost_mining.py` — see §2d |
| Data Archive persistence layer | `archive.py` |
| Game version safety gate (halt on build change until operator confirms) | `version_guard.py` — see §4's `system.good_version`/`system.version_confirmed` entries and §7 |
| Wildcard pattern matching helpers | `patterns.py` |
| Per-script tick-cost profiling | `profiling.py` — see §1d |
| Structured, indented console logging (`debug()`-level decision tracing) | `tree_console.py` (`TreeConsole`) — see §0a |
| Logging caught-and-recovered exceptions (`swallowed(where, error)`) | `swallow.py` — see §0b; imports nothing, so even `archive.py` uses it |

Root executable scripts (`solar_1.py`, `rover_1.py`, `panel_4.py`, etc.) stay thin entrypoints: import + run controller from `lib/`. No own copies of tier lists, thresholds, budgeting formulas.

**No real stdlib — only short allowlist of "executable built-in modules"** (`docs/guide/programming_language_reference.md`'s "Imports & Libraries" section authoritative; re-check before any import, don't assume ordinary Python). **Only** executable modules: `random` (`randint`/`rand`/`random()`, also bare global helpers), `re` (regex — `re.escape` unavailable), `functools` (`reduce`, `total_ordering`), `dataclasses` (`dataclass`, `field`). Nothing else. None are real system libs — small in-game reimplementation exposing just those names, not CPython modules. `math`, `sys`, `os`, `json`, `time`, `itertools`, `collections` (concrete module), etc. **don't** exist at runtime. `typing`, `types`, `collections.abc`, `user_stubs` exist ONLY for editor/Pyright annotations — erased at runtime (`typing.TYPE_CHECKING` always `False` in-game). **Need stdlib thing (ceiling division, etc.) → write plain arithmetic by hand, don't import** — see `lib/production.py`'s `_ceil()` pattern instead of `math.ceil()`.

**Parser/builtin limits**: no multi-line parenthesized imports — `from x import (a, b)` is a `SyntaxError` in-game, write one-line imports. No `frozenset` — use tuples; check a builtin against existing `lib/` usage before relying on it.

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
- **Convention**: one `TreeConsole` per controller instance, in `__init__` (or once before `run_*_loop()`'s `while True:` for bare function, not inside), stored as `self.log`/`log` — never re-construct per call/tick, since `__init__` reads `console.log_levels` archive dict. Name it `log` (not `tree` — tree-drawing just formatting, `log` names purpose).
- `color(c)` / `level(lvl)` set one-shot override (CSS color / `info`\|`warn`\|`error`\|`debug`\| custom) consumed by *next* `print`/`start`/`end`/`debug`/`trace` call only, then reset to instance default.
- Every line still goes through `console.print(..., timestamp=True)` — keeps game time-of-day prefix, works with Console channel/level filters.
- Reserve plain `warn`/`error` for real status changes player should notice without debug output; `debug()`/`trace()` purely detail, never attention-needing.

### 0b. No Silent `except Exception` (`lib/swallow.py` `swallowed()`)

Every broad handler that recovers (returns a default, `continue`s, keeps looping) calls `swallowed()` as its first line:

```python
from swallow import swallowed

try:
    count = port.count()
except Exception as error:
    swallowed("storage.crop_automator_forage: port.count", error)
    continue
```

- `where` = `"module.Class.function: call"`. Append ` #2`, ` #3` when one function has several sites calling the same thing. It is the dedupe key, so keep it unique per site.
- Every caught error → one **debug** line. Identical consecutive errors at one site are logged once, so a per-tick handler can't flood the log.
- "Code bug" types (`TypeError`, `AttributeError`, `NameError`, `KeyError`, `IndexError`, `ZeroDivisionError`) → also one **warn** per site per script run, visible without debug output on. Exception: `AttributeError` on `NoneType`, which is how a missing component (a `None` from `get_component()`) usually surfaces.
- Why: a broad except can't tell "game said no" from "our code is wrong" (e.g. a `TypeError` from a wrong API signature silently reads as "empty").
- **Allowed to stay silent** (with a comment saying why):
  - inside an `archive.transaction()` updater: any log call there rejects the transaction;
  - `swallowed()` itself;
  - narrow handlers that fully handle their case, e.g. `except (TypeError, ValueError)` around a `float()` parse with a fallback, or `except IndexError` as a loop escape.
- Tiers without `lib/` (`0_cold_boot`, `1_early`) use a local `_swallowed()` stand-in (debug only) defined in the script itself.

## ⚡ 1. Core Terraforming & Physics Formulas

| System | Component | Key Formula / Setpoint | Limits & Constraints |
| :--- | :--- | :--- | :--- |
| **Solar Tracking** | `solar_generator` | `tilt = round(sun_elevation)` | 0° (flat) to 90° (vertical). Night output = 0 W. Peak = 50 W. |
| **Oxygen Generation** | `oxygen_generator` | `intake = atmosphere.get_co2() / 10.0` | Power: -8 W. Dump waste when `50 <= waste < 60` (clean dump, 0 penalty). Stalls at 100 waste. |
| **Heat Calibration** | `heat_generator` | `power = 1..10 W` (sweep / cache by weather) | Power: -10 W max. Re-eval optimal power on day/weather change. |
| **Pressure Sync** | `pressure_generator` | Sync pulse with resonance window peak | Power: -10 W max. 100% efficiency on exact resonance window hit. |
| **Power Grid & Brownout** | `power_control`, `battery` | Battery = 500 Wh (300 cr). Safe floor: 15-20% | Configurable shedding tiers (`power.shedding_tiers`) — see §1a for full tier/threshold breakdown. |

## 🗺️ 3. Planet Map Biome Colors (player-observed, verify with `nocturna.biome_at(x, y)`)

| Map Color | Biome |
| :--- | :--- |
| Blue (incl. base's slightly-green patch) | `frozen` |
| Green | `coastal` |
| Dark brown / red | `volcanic` |
| Light brown | `geothermal` |
| Purple | `deep` |

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
from bio import BioCollectorController, BioLabController, BioExchangeController
from bio_coastal import BioLuminizerController
from harvesting import HarvesterController

# Execute main loop
controller = SolarController(self)
controller.run()
```
