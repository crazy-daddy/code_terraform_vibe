# Code: Terraform — AI Agent Quick Reference Cheat Sheet

High-density reference of physics, formulas, component specs, bus channels, and data conventions.
This is the **single source of truth for tunable numbers and definitions** shared by every agent
working on this project. When you change a tunable constant in code (safety margins, tiers,
thresholds, stale-tick counts, budgets, etc.), update it here in the same change. Other docs
(`CLAUDE.md`, `TODO.md`) should point at the constant/module name rather than restate its value —
that way there is exactly one place to keep current.

---

## 🧱 0. Shared Library Module Map (`lib/`)

| Concern | Module(s) |
| :--- | :--- |
| Terraforming (heat/pressure/O2) | `terraforming.py` (`HeatController`, `PressureController`, `OxygenController`) |
| Power grid & brownout | `power.py` (`PowerGridManager` — generic, works for solar/oil/reactor/turbine grids); `solar.py` (`SolarController` — sun tracking + grid-aware Master/Follower election, delegates shedding/recovery to `PowerGridManager`) |
| Vehicles (Rover/Pioneer base) | `vehicle.py` (`VehicleController`, composes the mixins below) |
| &nbsp;&nbsp;↳ driving / stall recovery | `vehicle_navigation.py` |
| &nbsp;&nbsp;↳ battery accounting / trip budgeting / charging-station discovery | `vehicle_energy.py` |
| &nbsp;&nbsp;↳ fleet-wide target claims & hardware blacklist | `vehicle_claims.py` |
| &nbsp;&nbsp;↳ cargo offload into Base Inventory | `vehicle_cargo.py` |
| &nbsp;&nbsp;↳ sonar survey loop (POI discovery) | `vehicle_survey.py` |
| &nbsp;&nbsp;↳ mineral-site discovery & drill execution | `mining.py` — shared by Rover and Pioneer; see §2b |
| Rover / Pioneer specializations | `rover.py`, `pioneer.py` — thin `VehicleController` subclasses; do **not** put shared vehicle logic here |
| Harvesting (grid survey/collection) | `harvesting.py` (`HarvesterController`) |
| Smelting | `smelter.py` |
| Production planning (demand-driven) | `production.py` |
| Supply Dock logistics | `supply_dock.py` |
| Biology (collector/lab/exchange) | `bio.py` |
| Vehicle charging stations | `charging.py` |
| Fabrication | `fabricator.py` |
| Data Archive persistence layer | `archive.py` |
| Wildcard pattern matching helpers | `patterns.py` |

Root executable scripts (`solar_1.py`, `rover_1.py`, `panel_1.py`, etc.) should stay thin
entrypoints that import and run a controller from `lib/` — they should not contain their own
copies of tier lists, thresholds, or budgeting formulas.

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
    `bio_collector_*`, `bio_lab_*`, `bio_exchange_*`): shed **first**.
  - **Tier 2 — critical active production & logistics** (`smelter_*`, `fabricator_*`,
    `vehicle_charging_station*` / `charging_station_*`): shed only under severe deficit.
  - This is deliberately inverted from a naive "protect terraforming" instinct: terraforming
    machinery is treated as background/passive load, production and vehicle-charging
    infrastructure as the higher priority to keep alive.
- Shed thresholds live as **inline literals in `manage_night_loads()`** (not named module
  constants — check that function directly if retuning): Tier 1 sheds on deficit or
  `battery_pct < 0.20`; Tier 2 additionally sheds on severe deficit (`stored_wh < wh_needed * 0.50`)
  or `battery_pct < 0.15`.
- Recovery is the mirror image, in both `manage_night_loads()` (battery stabilizing) and
  `manage_day_recovery()` (solar surplus at dawn): Tier 2 (production/logistics) is restored
  first, requiring only a small surplus-watt / stored-Wh margin; Tier 1 (terraforming) is
  restored last, requiring a larger margin.

---

## 🚗 2. Surface Vehicles & Logistics

| Vehicle | Speed / Throttle | Energy Cost / Budgeting | Operational Rules |
| :--- | :--- | :--- | :--- |
| **Rover** | `vehicle.speedmode` archive flag ("conserve" default / "highspeed") picks throttle per leg | `WH_PER_METER_DEFAULT = 0.08` Wh/m base (per-vehicle calibrated); safety margin `SAFETY_MARGIN_MULTIPLIER = 1.35` (35%) — see §2a | Sonar scan: `SONAR_WH_BUDGET = 2.0` Wh. Mining drill: `MINE_WH_PER_UNIT = 2.5` Wh/unit. Return to nearest charging station (not necessarily home) when Wh falls below the trip budget. |
| **Pioneer** | Configurable slots / tools | Slot chassis: `inspect_slots()`, `execute_construction()`; construction energy: `WH_PER_PROGRESS` (per-vehicle calibrated, default `CONSTRUCTION_WH_PER_PROGRESS_DEFAULT = 40.0` Wh for 0%→100%) — see §2a | Heavy construction, blueprint placement, pipe/power line deployment. Budgets each trip for `TARGET_CONSTRUCTION_PROGRESS_PER_TRIP = 0.25` progress (~4 round trips to finish a job), not just round-trip driving. |
| **Harvester** | BFS on 8x24 grid (`NUM_ROWS=8`, `NUM_COLS=24`, A1..H24) | Travel time: 0.5 h/sector. Empty move: `+7 heat`; Item move: `+1 heat` | Max heat: 100°C. Pause & cool down when heat exceeds `HEAT_SAFE_CEILING = 75.0`, resume once back down to `HEAT_RESUME_LEVEL = 40.0` (`lib/harvesting.py`). |

### 2a. Vehicle Energy Budgeting Detail (`lib/vehicle_energy.py` `VehicleEnergyMixin`)

- Round-trip budget = outbound drive + sonar/scan budget + mining/drill budget + drive from
  target to the *nearest* charging station, all multiplied by `SAFETY_MARGIN_MULTIPLIER = 1.35`,
  plus a hard `MIN_EMERGENCY_RESERVE_WH = 8.0` floor on top. See `calculate_trip_energy()`.
- Wh/meter is calibrated per vehicle (`self.calibration_key()` in `archive`), falling back to a
  fleet-wide average and then `WH_PER_METER_DEFAULT = 0.08`.
- Throttle/speed model: `DRIVE_SPEED_M_PER_HOUR_PER_THROTTLE = 100.0` m/h per throttle unit,
  `DRIVE_POWER_W_PER_THROTTLE_SQUARED = 20.0` W per throttle² — so power scales with the square
  of throttle. Throttle is clamped to `[MIN_SPEEDMODE_THROTTLE=0.10, MAX_SPEEDMODE_THROTTLE=1.0]`
  and picked per-leg by `select_cruise_throttle()` / `max_safe_throttle_for_leg()`, which always
  keeps enough reserve to still reach a charging station afterward.
- `minimum_wh_per_meter()` gives the best-case Wh/m at the throttle floor (`0.02` = `20 * 0.10² /
  (100 * 0.10)`). Any check that claims a target/job is *permanently* unreachable (not just "not
  right now") must budget against this, not the calibrated `self.wh_per_meter` — see the
  `wh_per_meter` override param on `calculate_trip_energy()` and its use in
  `pioneer.py`'s `run_construction_loop()` hard-infeasibility checks. `energy_needed_to_return_now()`
  (the mid-trip panic/abort-safety check in `drive_to()`) also uses this floor rate, not the typical
  one — conserve mode can always crawl home at the floor throttle to stretch a tight budget, so the
  abort threshold must reflect that, not a "comfortable normal-speed" cost.
- `drive_to()` computes `is_driving_to_station` once before its polling loop and skips the
  return-reserve abort check entirely when the destination itself is the charging station/base
  slot (or already within 3m of it) — arriving there *is* the recovery, so that check must never
  abort the very trip meant to reach safety. Do not reintroduce a duplicate unconditional copy of
  this check inside the loop; there was exactly this bug (fixed) where an unconditional check ran
  before the guarded one and could self-abort a return-to-station trip.
- Construction (Pioneer only): `calculate_trip_energy()`'s `planned_construction_progress` param adds
  `progress * self.wh_per_progress` to the trip budget, mirroring `planned_scans`/`planned_drill_units`.
  `wh_per_progress` is calibrated per-vehicle from real `constructor.execute()` calls
  (`calibrate_wh_per_progress()` in `vehicle_energy.py`, called from `pioneer.py`'s
  `execute_construction()`), falling back to `CONSTRUCTION_WH_PER_PROGRESS_DEFAULT = 40.0` Wh
  (0%→100%) until enough samples exist. `pioneer.py`'s `planned_progress_for_job()` caps the
  planned progress at `TARGET_CONSTRUCTION_PROGRESS_PER_TRIP = 0.25` (or less if the job is
  already further along), so a trip is only taken if it can also make *meaningful* on-site
  progress — not just barely arrive and immediately pause for lack of power. This is a floor
  on whether to depart, not a cap on-site: `execute_construction()` keeps recharging nearby
  and resuming for as long as real progress keeps being made each cycle, and only reports
  failure for a genuine rejection (e.g. `"blocked"`) or a no-progress stall — never merely
  because the job needs more than one recharge round to finish.
- Fleet coordination (`lib/vehicle_claims.py`): atomic `archive.transaction()` claims
  (mirrored to `rover.claims` / `survey.claims` for legacy compatibility), heartbeat-renewed via
  `refresh_claim()`, expiring after `CLAIM_STALE_TICKS = 36000` ticks (1 sim hour).
- Navigation timeout (`lib/vehicle_navigation.py` `drive_timeout_ticks()`): `drive_to()`'s
  `timeout_ticks` defaults to `None` and is computed per-leg from expected travel time
  (`distance / speed-at-chosen-throttle`), converted from world-clock hours to the tick-scale
  budget via `Clock.real_seconds_per_hour()` — **not** a flat constant. `sleep()` and the tick
  counter both run in real/simulation seconds (the same base), which the compressed day/night
  cycle stretches relative to world-clock hours, so a fixed tick budget silently under-times
  slow conserve-mode legs. Uses a `safety_multiplier = 2.0` margin and a `min_ticks = 3000`
  floor (the old fixed default, still used for short/typical legs).
- Navigation safety (`lib/vehicle_navigation.py`): stall detection re-issues the drive command
  after repeated stuck cycles; base staging slots are staggered per vehicle index to avoid
  parking/charging-pad collisions.
- `is_at_base(threshold=3.0)` (`lib/vehicle_navigation.py`): `self.distance_to_home() <= threshold`.
  Loops use this to gate one-time-per-visit actions (top-off charging before departing, restocking)
  so they only fire when actually parked at base, not mid-trip in the field after a reload. Used by
  `run_expedition_cycle()` (`rover.py`), `run_construction_loop()`/`run_mining_loop()` (`pioneer.py`),
  and `run_survey_loop()` (`vehicle_survey.py`).

### 2b. Mining (`lib/mining.py` `MiningMixin`)

Mineral-site discovery and drill execution live in one place, shared by both Rover and Pioneer
(mixed into `VehicleController`) so capability-aware job routing doesn't need to be duplicated.

- Capability is always read live via `self.vehicle.drill.hardness_limit()` — never assumed from
  vehicle type. In practice a Rover's fixed Drill slot only ever carries the basic drill
  (`hardness_limit = 1`, iron_ore/silicon); Industrial (`hardness_limit = 3`) and Heavy
  (`hardness_limit = 4`) Drills are Pioneer-universal-slot items for higher-hardness sites
  (titanium/cobalt/rare_earth/neutronium-tier) a Rover can never reach.
- `build_mineral_site_candidates(deprioritize_hardness_at_or_below=None)`: candidate sites
  matching `get_raw_material_demands()` and the vehicle's own hardness limit. Passing
  `ROVER_PREFERRED_MAX_HARDNESS = 1.0` (Pioneer's mining role does this) sets `priority=3` instead
  of `2` on hardness ≤ 1 sites — a **soft** preference, not exclusion: a capable Pioneer still
  claims an easy site if nothing harder is currently pending, rather than idling.
- `select_best_mining_target(candidates)`: sorts by `(priority, distance)` — lower priority number
  wins ties on distance — then runs the existing `calculate_trip_energy()` achievability check and
  atomic `claim_target()`. Also used for Rover's combined POI+mineral candidate list (POIs are
  `priority=1`, mineral sites `priority=2`/`3`).
- `mine_current_site(max_units=None)` defaults to `self.vehicle.cargo.capacity()` (read live, not
  hardcoded `10`) — Pioneer's cargo capacity varies with storage modules.
  `mine_until_full_or_exhausted(target_coords)` wraps it with the recharge-and-resume-in-place loop
  (mirrors `execute_construction()`'s pattern in `pioneer.py`).
- Pioneer's mining role (`run_mining_loop()`, entrypoint `pioneer_3.py`) requires the operator to
  have already mounted a drill (`mount_hardware()` / Control Panel) — it only checks
  `hasattr(self.vehicle, "drill")` and idles with an advisory if absent; it never auto-mounts one.

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

### Data Archive (`get_component("notebook")` / `lib/archive.py`)
- `power.shedding_tiers`: Custom shedding tiers list-of-lists `[[tier1_machines...], [tier2_machines...], ...]` (or `power.shedding_tiers:<grid_anchor>`). Defaults to `DEFAULT_SHEDDING_TIERS` in `lib/power.py` — see §1a.
- `power.shedded` / `power.shedded_machines`: Active list of machines currently powered down by Power Guard. Checked by `wake_smelter()` to avoid breaker oscillation.
- `fleet.status.<id>` / `rover.status.<id>`: Telemetry `{name, state, x, y, wh, level, target, tick}`
- `rover.claims` / `survey.claims` (mirrored, legacy + current key): Atomic target reservation dict `{target_key: {"vehicle": id, "tick": tick}}`. Stale after `CLAIM_STALE_TICKS = 36,000` ticks (1 hr) — see `lib/vehicle_claims.py`.
- `survey.unsupported_targets` / `rover.unsupported_targets` (mirrored): Hardware-capability blacklist entries (`reason`, `scanner_type`, `scanner_tier`, `hardness_limit`, unlocked researches) — see `lib/vehicle_claims.py`.
- `heat.optimal_setpoints`: Caching `{thermal_state: best_power}`
- `pressure.optimal_resonance`: Caching `{resonance_state: best_window}`

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
from bio import BioCollectorController, BioLabController, BioExchangeController
from harvesting import HarvesterController

# Execute main loop
controller = SolarController(self)
controller.run()
```
