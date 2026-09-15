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
| &nbsp;&nbsp;↳ cargo offload into Inventory / Warehouse | `vehicle_cargo.py` |
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
| Thermal Cap (steam capture, anti-overpressure) | `thermal_cap.py` |
| Steam Turbine (steam-to-grid power) | `steam_turbine.py` |
| Storage management (Warehouse-aware sourcing/unloading, Inventory rebalancing) | `storage.py` — see §2c |
| Data Archive persistence layer | `archive.py` |
| Wildcard pattern matching helpers | `patterns.py` |
| Per-script tick-cost profiling | `profiling.py` — see §1c |

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
  - **Tier 2 — critical active production** (`smelter_*`, `fabricator_*`): shed only under
    severe deficit.
  - This is deliberately inverted from a naive "protect terraforming" instinct: terraforming
    machinery is treated as background/passive load, production the higher priority to keep alive.
  - Vehicle Charging Stations (`vehicle_charging_station*` / `charging_station_*`) are
    deliberately **never** in any tier — they're also what dispatches the fleet rescue drone
    (`lib/charging.py` `manage_fleet_rescues()`); shedding them "only under severe deficit" would
    lose rescue capability at exactly the moment a vehicle is most likely to be stranded and need
    it (`dispatch_rescue()` returns `"station_offline"` if the station itself is unpowered).
- Shed thresholds live as **inline literals in `manage_night_loads()`** (not named module
  constants — check that function directly if retuning): Tier 1 sheds on deficit or
  `battery_pct < 0.20`; Tier 2 additionally sheds on severe deficit (`stored_wh < wh_needed * 0.50`)
  or `battery_pct < 0.15`.
- Recovery is the mirror image, in both `manage_night_loads()` (battery stabilizing) and
  `manage_day_recovery()` (solar surplus at dawn): Tier 2 (production/logistics) is restored
  first, requiring only a small surplus-watt / stored-Wh margin; Tier 1 (terraforming) is
  restored last, requiring a larger margin.

### 1b. Steam Power Loop: Thermal Cap → (Gas Tank) → Steam Turbine

Thermal Cap (`lib/thermal_cap.py` `ThermalCapController`) and Steam Turbine
(`lib/steam_turbine.py` `SteamTurbineController`) are independent scripts — each only manages its
own throttle, no shared coordination needed. A Gas Tank sitting between them is purely passive
(no script; see `docs/components/gas_tank.md`) and just smooths supply gaps.

- **Pipe wiring**: a Gas Tank has no script of its own, so nothing ever calls `connect()` on *its*
  side of a FluidPort — each neighbor must declare its own side instead. **A Thermal Cap has no
  `.outpost` property at all** (`docs/components/thermal_cap.md` lists none — it's built directly on
  a thermal vent out in the field, not necessarily inside a founded outpost, unlike Gas Tank/Steam
  Turbine which both have one), so candidates can't be scoped to "this building's outpost"; both
  controllers' `discover_network_building_ids(type_id)` instead walk every outpost
  (`outpost_network.outposts()` → `outpost.buildings(type_id)`) to gather candidate ids network-wide.
  - **`connect()`'s `"ok"` status does NOT mean the target is physically reachable** — per
    `docs/guide/infrastructure_and_pipes.md`, a remote pairing needs a *completed* Gas Pipe route,
    which `connect()` never checks; `"ok"` only means the pairing was logically accepted. The one
    live signal of an actually-broken route is `is_stalled()` (steam/throttle ready, nothing
    transferred) — both controllers blacklist a target that reports this and pick a different
    candidate, rather than sitting stalled on the same unreachable target forever. Each also clears
    its blacklist periodically (`RESCAN_INTERVAL_TICKS`: 300 Cap-ticks / 150 Turbine-ticks, ≈5
    real minutes at default poll intervals either way) so a target that was unreachable becomes
    retryable again once the player builds a new pipe to it — a currently-*working* connection is
    never torn down just to check this, only the candidate pool is widened for the next switch.
  - **Cap → Gas Tank(s)** (`ensure_output_connection()`): `steam_out` only ever holds one destination
    at a time, so with several reachable tanks it can't fan out simultaneously — instead it
    rebalances: stays on the current tank while its `fill_pct()` is below
    `GAS_TANK_REBALANCE_FILL_FRACTION=0.98` **and** it isn't stalled, otherwise switches to whichever
    other known (non-blacklisted) tank is currently least full. Deliberately raised from an earlier
    `0.85` — that threshold re-evaluated every `step()`, so with two-or-more tanks both hovering
    above it, whichever read as "less full" that particular tick would flip every cycle, reconnecting
    `steam_out` constantly and never giving flow a chance to actually establish on either one —
    pressure climbed unchecked with nowhere actually receiving it, causing real overpressure
    blowoffs. `0.98` (essentially "truly full, not just past a soft threshold") only ever abandons a
    target once it genuinely can't take more, which guarantees no oscillation — "imperfect load
    balancing" loses to "never interrupts flow." A single stalled tick is enough to blacklist —
    `is_stalled()` on a Cap already requires chamber steam to be available and ready to send, so
    dormancy (which stops *capture*, not release) can't be the cause — **except** for the first
    `CONNECTION_GRACE_TICKS=2` ticks right after a (re)connect, since flow can take a tick to
    register and treating that brief lag as proof of unreachability would blacklist a perfectly good
    tank and immediately force another switch, compounding the exact same churn.
  - **Turbine → source** (`ensure_input_connection()`): tries every known Gas Tank first (the
    larger, shared buffer), then every known (non-blacklisted) Thermal Cap directly. Connecting
    straight to a Cap is a deliberate, fully-supported fallback, not a hack — per
    `docs/guide/infrastructure_and_pipes.md`'s Thermal Vents section, "additional consumers may
    connect their own `steam_in` ports to this Cap," independent of whatever the Cap's own
    `steam_out` currently points at. This is also why the Cap's own script never tries to connect to
    a Turbine itself: the Turbine already handles that side on its own. Unlike the Cap, a Turbine's
    `is_stalled()` ("throttle up, no steam arriving") is ambiguous on its own — it's equally true,
    harmlessly, whenever the feeding vent is just dormant — so blacklisting requires
    `STALL_STREAK_BLACKLIST_THRESHOLD=5` *consecutive* stalled ticks (dormancy is temporary; a
    genuinely missing pipe route stalls forever) rather than a single tick.
  - **Discovery cost**: `discover_network_building_ids()` walks every outpost's `buildings(type_id)`
    — real work, and (per profiling — see §1c) the actual cost driver of both controllers' `step()`.
    Both are cheap once settled specifically because the network walk itself is skipped, not just
    deferred, while a connection is healthy:
    - **Cap**: the "keep current tank" decision needs only one `fill_pct()` read on the id already
      connected — `ensure_output_connection()` checks that *before* touching discovery at all, so
      the walk never runs in the steady-state case.
    - **Turbine**: `ensure_input_connection()` returns immediately whenever `connected_input` is
      True and `stall_streak < STALL_STREAK_BLACKLIST_THRESHOLD`, for the same reason.
    - Both still need discovery sometimes (bootstrap, current target blacklisted/full, every
      candidate blacklisted at once) — for those cases each controller caches the discovered
      building list for `DISCOVERY_CACHE_INTERVAL_STEPS=20` `step()` calls (`_discover_tanks_cached()` /
      `_discover_candidates_cached()`) rather than re-walking on every one of several reselection
      attempts in a short window. This is a ceiling, not the primary mechanism — see the fast paths
      above for why the walk is rare in practice.
  - **The real per-step cost was elsewhere, and profiling (§1c) is what found it**: with the walk
    itself gone, Thermal Cap's `step()` still cost 2-3 sim ticks every single call (Steam Turbine's
    cost ~0, matching its zero-external-lookup fast path) — no periodic spike at 20 or 300 steps,
    ruling discovery back out entirely. The actual culprit: the Cap's fast path still resolved its
    *currently connected* tank via a fresh `get_component(current_id)` round trip every step just to
    read `fill_pct()`, since `port.connected_to()` only returns an id string, not the object
    `outpost.buildings()` had already handed discovery. `discover_network_buildings()` (added
    alongside the existing id-only `discover_network_building_ids()`) now returns the live building
    objects themselves, and `ThermalCapController._tank_lookup` (an id → object dict, populated from
    every discovery batch and never wholesale-cleared — a building's identity is stable, only the
    candidate *list* goes stale) makes `_resolve_tank(id)` a plain dict read on every call after the
    first time a given id is seen. Verified via a stub test asserting zero `get_component()` calls
    across 20 consecutive healthy steps (previously: one per step). This is the general pattern for
    any future "read a possibly-external object by remembered id every step" cost: keep the object
    reference from whatever discovery/connect call first produced it, rather than re-resolving by id.
  - **Third pass — still 2 sim ticks/step after the above.** Comparing structure against Turbine's
    equivalent (which reads ~0) found the remaining asymmetry: `ensure_output_connection()` still
    called `port.connected_to()` **unconditionally on every single call**, whereas Turbine's healthy
    fast path calls no port method at all — it trusts its own `self.connected_input` boolean and only
    ever queries the port (`connected_id()`) on the rare blacklist branch. Fixed the same way: the Cap
    now tracks `self._connected_tank_id` locally, updated only by this controller's own `connect()`
    calls and blacklist decisions (nothing else ever repoints `steam_out` — Gas Tank is passive, no
    other script touches this port), so `port.connected_to()` is called exactly **once, ever** — a
    one-time sync on first `ensure_output_connection()` call so a script reload recovers an
    already-working connection instead of assuming a fresh start — never again after that. Verified
    via a stub test asserting `connected_to()` is called exactly once total across bootstrap +
    reselect + 20 healthy steps (previously: once per step). If the archived tick-delta for
    `thermal_cap_*` still doesn't read ~0 after this, the next place to look is whichever `self.cap.*`
    method call in `step()` itself isn't mirrored by an equivalent Turbine call, since everything
    `ensure_output_connection()` itself does is now either a boolean/dict read or fully gated.
- **Thermal Cap** — the only job is keeping `pressure()` off the `1.0` overpressure ceiling (hitting
  it blows the *entire* chamber to atmosphere, not just the surplus — see `.is_overpressured()`).
  Proportional release-valve (`steam_out`, via `set_throttle()`) bands on `pressure()`:
  `≥0.90→1.0`, `≥0.60→0.6`, `≥0.30→0.3`, else `THROTTLE_TRICKLE=0.1` (keeps the pipe/downstream
  buffer topped up without needlessly draining banked steam while pressure is comfortable). The
  relief valve (`set_relief()`, dumps straight to atmosphere) only engages once the release valve
  is already wide open (`throttle==1.0`) and pressure still climbs past
  `PRESSURE_RELIEF_THRESHOLD=0.95` — a downstream jam (full Gas Tank, stalled Turbine, disconnected
  pipe) the release valve alone can't route around. A small relief bleed there is far cheaper than
  a full overpressure blowoff.
- **Steam Turbine** — throttle picked by `choose_throttle()`, in priority order:
  1. Buffer fraction (`steam_in.level()/capacity()`, this turbine's own 100 t buffer, not the Gas
     Tank) `< STEAM_BUFFER_LOW_FRACTION=0.15` → `THROTTLE_LOW_BUFFER=0.15` regardless of day/night
     or grid demand — a thin buffer running flat out is exactly what produces `is_stalled()`.
  2. `< STEAM_BUFFER_HEALTHY_FRACTION=0.40` → `THROTTLE_MARGINAL_BUFFER=0.5` (buffer rebuilding).
  3. Healthy buffer + night (`clock.get_elevation() <= 0`) → `1.0` — steam is the only generator
     while solar is out, so it always carries the grid regardless of battery/demand state.
  4. Healthy buffer + day + grid battery `≥ BATTERY_FULL_FRACTION=0.98` of capacity AND
     `generated >= consumed` → `THROTTLE_DEMAND_MET=0.3` (ease off, save banked steam for the
     coming night instead of burning it on power nobody currently needs).
  5. Otherwise → `1.0` (healthy buffer, daytime, still useful to generate).
  Reads grid state the same way `lib/power.py`'s `PowerGridManager` does
  (`power_control.grid(self.name)` → `.stored`/`.capacity`/`.generated`/`.consumed`), but runs no
  shedding or master-election itself — that stays the grid's existing solar Master's job.

### 1c. Per-Script Tick-Cost Profiling (`lib/profiling.py`)

The game exposes no per-script CPU/ms execution budget API. `docs/components/clock.md` documents
the sanctioned stand-in: `clock.tick()` (deterministic simulation tick since save start, 10
ticks/sec at normal speed) — *"Use tick deltas for profiling script timing instead of wall-clock
milliseconds."* `lib/profiling.py` wraps that pattern so any controller's `run()` loop can measure
its own `step()` with two calls, no local bookkeeping needed:

```python
start = profiling.begin()
self.step()
profiling.end(self.name, start)   # logs a warning if delta > SLOW_STEP_TICK_THRESHOLD=1
```

- Samples roll into `archive` as one fixed-size history list per script name
  (`ARCHIVE_KEY_PREFIX="profiling."`, `HISTORY_LEN=50`) — **one archive entry per profiled script
  name, not per sample**, since the Data Archive has a hard 512-entry cap shared by every script in
  the save (`docs/guide/data_archive_guide.md`).
- `profiling.report(names=None)` prints avg/max ticks-per-`step()` for every profiled name (or a
  given subset) — call it ad hoc (e.g. from a one-off diagnostic script), not from a hot loop.
- **Granularity limit — read this before trusting a `0`**: `clock.tick()` advances on a fixed
  10/sec schedule *independent of how much work any script does* — per
  `docs/guide/programming_language_reference.md`, "the interpreter automatically gives time back to
  the game while loops run," i.e. scripts are cooperatively scheduled and interleaved within each
  tick's processing window. A `step()` with no internal loop/`sleep()` runs to completion inside
  whichever tick it started in regardless of whether its body did 5 operations or 5,000, so it can
  only show a nonzero delta by landing on a tick-boundary by measurement luck. **A `0` does not mean
  "cheap"; it means "didn't happen to span a tick boundary," which single-pass `step()` calls almost
  never do no matter their real cost.** `SLOW_STEP_TICK_THRESHOLD=1` (lowered from an initial `3`
  once this was understood) reflects that: on a non-looping `step()`, *any* nonzero delta is already
  the interesting case, not just ones above some larger margin. This makes the profiler good at
  catching genuinely heavy per-call work (a loop over many buildings/slots, e.g. `production.py`'s
  demand cascade or `storage.py`'s rebalance sweep are more plausible candidates than a handful of
  `if` checks) — full stop; there's no documented finer-grained (sub-tick/wall-clock) instrument for
  scripts to fall back on, so below this floor, use code-level reasoning (algorithmic complexity,
  what runs every cycle vs. gated) instead.
- **Case study, Thermal Cap** (§1b): two profiling passes each found a real, *sustained* per-step
  cost with no periodic spike at the discovery-cache/rescan intervals, which correctly pointed at
  (1) a fresh `get_component(id)` round trip the fast path was still doing every single call, then
  after fixing that, (2) an unconditional `port.connected_to()` call every step where Turbine's
  equivalent touched no port method at all when healthy. Both were genuine, verified fixes (stub
  tests confirmed the call counts dropped to zero/near-zero). A third pass still showed Thermal Cap
  reading ~2-3 against Turbine's ~0 with nothing left in either script's own code to explain the
  gap — at that point the signal had reached the noise floor described above (ambient cooperative-
  scheduling jitter, or a fixed engine-side cost of that specific component's own methods, neither
  fixable from script code) and further chasing it stopped being productive. That's the profiler's
  actual working mode and its limit: it can't measure a single call's cost directly, and a
  *sustained per-step* delta with no periodicity matching a known cache/interval constant is a
  reliable signal worth grep-ing for exactly once or twice — not an oracle to keep re-running
  against the same script once every explanation in its own code has been exhausted.
- **Not currently wired into any script.** Instrumentation was added to `lib/thermal_cap.py` and
  `lib/steam_turbine.py` for the investigation above, then deliberately removed again from both once
  it stopped yielding actionable findings (see the case study) — `lib/profiling.py` itself, and
  `lib/archive_cleaner.py`'s cleanup of it (next bullet), are kept since a future script suspected of
  doing real bulk per-call work (see `SLOW_STEP_TICK_THRESHOLD` guidance above) is still a reasonable
  candidate to wire this into temporarily. Not standardized across every controller — see the Phase 6
  TODO item on an interrupt/event-driven pattern for where this is headed longer-term (`TODO.md`).
- **Storage shape & cleanup**: each archive entry is `{"history": [...], "last_tick": N}`, not a bare
  list — `last_tick` (the sim tick of the most recent `profiling.end()` call for that name) is what
  lets `lib/archive_cleaner.py`'s `clean_profiling()` tell "still being actively profiled" apart from
  "instrumentation was removed from this script and the entry is now dead clutter" — since profiling
  is opt-in and can be added/removed from a script at any time, there's no live game-state signal
  (unlike e.g. `clean_telemetry()`'s fleet-membership check) to cross-reference against, only
  staleness. An entry whose `last_tick` hasn't advanced in `PROFILING_STALE_TICKS=6000` (10 sim
  minutes) is purged as no-longer-written; a legacy bare-list entry (from before this shape existed)
  has no `last_tick` to check at all and is always purged as a one-time migration. Runs as part of
  `ArchiveCleaner.run()`'s normal sweep, no separate invocation needed.

---

## 🚗 2. Surface Vehicles & Logistics

| Vehicle | Speed / Throttle | Energy Cost / Budgeting | Operational Rules |
| :--- | :--- | :--- | :--- |
| **Rover** | `vehicle.speedmode` archive flag ("conserve" default / "highspeed") picks throttle per leg | Developer-confirmed travel power formula (no calibration): `(3 W + 8 W × active modules + 0.04 W × cargo units) × throttle^1.5`; safety margin `SAFETY_MARGIN_MULTIPLIER = 1.05` (5%) — see §2a | Sonar scan: `SONAR_WH_BUDGET = 2.0` Wh. Mining drill: `MINE_WH_PER_UNIT = 2.5` Wh/unit. Return to nearest charging station (not necessarily home) when Wh falls below the trip budget. |
| **Pioneer** | Configurable slots / tools | Slot chassis: `inspect_slots()`, `execute_construction()`; construction energy: `WH_PER_PROGRESS` (per-vehicle calibrated, default `CONSTRUCTION_WH_PER_PROGRESS_DEFAULT = 40.0` Wh for 0%→100%) — see §2a | Heavy construction, blueprint placement, pipe/power line deployment. Budgets each trip for `TARGET_CONSTRUCTION_PROGRESS_PER_TRIP = 0.25` progress (~4 round trips to finish a job), not just round-trip driving. |
| **Harvester** | BFS on 8x24 grid (`NUM_ROWS=8`, `NUM_COLS=24`, A1..H24) | Travel time: 0.5 h/sector. Empty move: `+7 heat`; Item move: `+1 heat` | Max heat: 100°C. Pause & cool down when heat exceeds `HEAT_SAFE_CEILING = 75.0`, resume once back down to `HEAT_RESUME_LEVEL = 40.0` (`lib/harvesting.py`). |

### 2a. Vehicle Energy Budgeting Detail (`lib/vehicle_energy.py` `VehicleEnergyMixin`)

- **Travel energy is a developer-confirmed exact model, not an empirically-calibrated Wh/meter.**
  The archive-backed calibration system (`self.wh_per_meter`, per-vehicle `archive` keys,
  `calibrate_wh_per_meter()`) was intentionally removed — the model below is treated as ground
  truth, so there's nothing left to calibrate for travel. (Construction *progress* energy is a
  separate concern with no confirmed formula, and still uses `wh_per_progress` calibration.)
  ```
  power (W)   = (BASE_TRAVEL_POWER_W=3.0 + MODULE_TRAVEL_POWER_W=8.0 × active_modules
                 + CARGO_UNIT_TRAVEL_POWER_W=0.04 × cargo_units) × throttle^1.5 × nav_power_multiplier
  speed (m/h) = DRIVE_SPEED_M_PER_HOUR_PER_THROTTLE=100.0 × throttle × nav_speed_multiplier
  ```
  - `active_modules` — mounted functional modules that draw power while driving: Nav/Drill/Sonar/
    Constructor family, including upgraded variants (`drill_module_heavy` etc. share the
    `drill_module` prefix — see `ACTIVE_MODULE_ID_PREFIXES`). Passive containers (Battery Holder,
    Cargo Rack) don't count. `active_modules_count()`.
  - `cargo_units` — live `self.vehicle.cargo.count()`. `calculate_trip_energy()` computes the
    outbound and return legs with *different* cargo loads (return = outbound + `planned_drill_units`),
    so a full hold after mining correctly costs more Wh/m than the empty outbound leg.
    `cargo_units_count()`.
  - `nav_speed_multiplier` / `nav_power_multiplier` — from mounted Sport Nav modules. Docs
    (`docs/components/nav_module.md` `.speed_multiplier()`) confirm 1 Sport Nav = exactly 2x speed
    / 2.6x power; `nav_power_multiplier()` linearly extrapolates the same +1.6x power per +1.0x
    speed for additional Sport Navs (their exact scaling beyond "raises draw faster" isn't
    documented). `speed_multiplier() == 1.0` (no Sport Nav) gives `power_multiplier() == 1.0`.
  - Module-level standalone versions (`travel_wh_per_meter_for(vehicle, throttle, cargo_units=None)`
    and friends, all suffixed `_for`) let non-`VehicleController` callers use the same formula
    without a live instance. `lib/charging.py`'s `rescue_target_level()` doesn't import these
    directly, though — it calls `rescue_wh_per_meter_for(vehicle)`, a single collapsed entry point
    that bakes in the rescue-specific choice (rate the leg at `MIN_SPEEDMODE_THROTTLE`, the cheapest
    possible Wh/m) and the "vehicle unreachable → bare-module fallback" branch, so a cross-script
    caller needs one import instead of five. Prefer adding a purpose-built `_for`-style function
    like this over widening a caller's import list — see the parser note below on why that matters
    here specifically. Single source of truth either way: the class attributes are aliases of
    these same module-level constants.
  - **Script-parser constraint**: the in-game sandboxed parser rejects multi-line parenthesized
    `from X import (a, b, c)` — even though it's valid standard Python and passes local
    `python -m py_compile` fine (`SyntaxError: expected Identifier in from-import, got (`). Always
    write cross-module imports as a single line (`from X import a, b, c`), same category of gap as
    `re.escape` being unavailable in the sandboxed `re` module.
  - **Cross-script call limitation**: each script (e.g. `rover_2.py`, `charging_station_1.py`) runs
    as an independent process. A script can never call a method on another script's live
    `VehicleController` instance (there's no such thing as `rover_2.getWhPerM()`) — the only valid
    cross-script channels are `get_component(id)` (raw game-engine API objects) and the Data
    Archive / Signal Bus. This is *why* shared formulas needed to become standalone `_for(vehicle)`
    functions (operating on the raw `get_component()` object) rather than instance methods: it's
    the only way for e.g. a charging station's script to reuse a vehicle's own energy formula.
  - **`lib/charging.py` fleet rescue** (`ChargingStationController.manage_fleet_rescues()`):
    dispatch triggers on engine `"stranded"`/`"stalled_no_battery"` status, OR `return_floor_wh()`
    — the Wh a vehicle needs on board *right now* to self-navigate to the nearest station,
    computed with the same `rescue_wh_per_meter_for()` formula (at `MIN_SPEEDMODE_THROTTLE`) the
    vehicle's own `energy_needed_to_return_now()` hard-abort uses. This replaced an earlier flat
    `battery_level <= 0.05` threshold: a vehicle's own `drive_to()` never willingly drains below
    its floor reserve, so it can brake forever in a self-parked limbo state well above 0% that the
    engine never calls "stranded" — a flat percentage doesn't track that per-vehicle,
    per-distance floor, so it could fire too late (heavy loadout) or too early (light one). A
    fully-removed backstop isn't safe either: without it, nothing would ever come get a vehicle
    stuck in that limbo.
  - `RESCUE_EXTRA_RESERVE_WH = 8.0` is added on top of the floor only for sizing
    `rescue_target_level()` (how much to charge *during* the rescue) — the trigger comparison
    itself (`is_below_floor`) uses the bare floor, matching the vehicle's own hard-abort exactly.
  - **Multi-station arbitration**: every deployed Vehicle Charging Station runs its own independent
    copy of this script polling the same fleet snapshot, so `manage_fleet_rescues()` gates dispatch
    on `is_nearest_station_to(vehicle_ref)` — otherwise every station within range would each send
    its own rescue drone to the same stranded vehicle. Ties (solo station, unresolvable
    coordinates) default to allowing dispatch rather than deadlocking silent.
- Round-trip budget = outbound drive + sonar/scan budget + mining/drill budget + drive from
  target to the *nearest* charging station, all multiplied by `SAFETY_MARGIN_MULTIPLIER = 1.05`
  (5% — reduced from the old empirical 35% now that the model above is exact, not calibrated),
  plus a hard `MIN_EMERGENCY_RESERVE_WH = 8.0` floor on top. See `calculate_trip_energy()`.
- Throttle is clamped to `[MIN_SPEEDMODE_THROTTLE=0.10, MAX_SPEEDMODE_THROTTLE=1.0]` and picked
  per-leg by `select_cruise_throttle()` / `max_safe_throttle_for_leg()`, which always keeps enough
  reserve to still reach a charging station afterward. Because power scales with `throttle^1.5`
  while speed scales with `throttle`, Wh/m for a leg scales with `sqrt(throttle)` — **not** linear
  in throttle — so `max_safe_throttle_for_leg()` solves for the throttle bound via
  `t <= (available_Wh / (distance * coeff * SAFETY_MARGIN_MULTIPLIER)) ** 2`, not a linear ratio.
  Verified against a brute-force numerical search.
- `minimum_wh_per_meter()` gives the best-case Wh/m at the throttle floor, via the general
  `wh_per_meter_at_throttle(throttle, cargo_units=None)`. Any check that claims a target/job is
  *permanently* unreachable (not just "not right now") must budget against this, not the typical
  cruise-throttle rate — see the `wh_per_meter` override param on `calculate_trip_energy()` and its
  use in `pioneer.py`'s `run_construction_loop()` hard-infeasibility checks.
- Two different "how much reserve do I need" checks, deliberately kept separate:
  - `energy_needed_to_return_now()` — the true floor, rated at `minimum_wh_per_meter()`. Used only
    for the **hard mid-drive abort** inside `drive_to()`'s tick loop (a last-resort safety check).
  - `energy_needed_to_return_comfortably()` — rated at `self.cruise_throttle` instead of the floor.
    Used for every **proactive** "should I keep working or head back" decision (mining's
    `MINE_WH_PER_UNIT` stop check, pioneer's construction "Field Battery Floor", survey's per-POI
    and per-waypoint reserve checks). Stopping at the true floor leaves conserve mode nothing to
    spend on the return but the slowest possible throttle, turning a routine trip home into a
    multi-hour crawl; stopping a bit earlier — with enough reserve for a normal-speed return —
    trades a small amount of extra work for a much shorter trip home. This is a simple heuristic,
    not an exact time/output optimum (that would need weighing real-world wait time against
    ore/progress value, which has no clean in-game unit).
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
- Recall (`lib/vehicle_claims.py`): `vehicle.recall:<name>` archive flag (`vehicle_recall_key()`,
  `is_recalled()`), toggled per-vehicle via `panel_2.py`'s Fleet card switch. On -> the vehicle
  abandons its current target (`release_target_claim()`) and drives to base now
  (`handle_recall_if_active()`, called at the top of every vehicle run loop); off -> resumes normal
  operations. Also checked inside `drive_to()`'s own tick loop for an immediate mid-trip abort, and
  inside `mine_current_site()`/`mine_until_full_or_exhausted()` so mining stops promptly — both
  guarded with the same `is_driving_to_station` exemption as the return-reserve check, so recall can
  never block the very trip home it's asking for.
- Navigation timeout (`lib/vehicle_navigation.py` `drive_timeout_ticks()`): `drive_to()`'s
  `timeout_ticks` defaults to `None` and is computed per-leg from expected travel time
  (`distance / speed-at-chosen-throttle`), converted from world-clock hours to the tick-scale
  budget via `Clock.real_seconds_per_hour()` — **not** a flat constant. `sleep()` and the tick
  counter both run in real/simulation seconds (the same base), which the compressed day/night
  cycle stretches relative to world-clock hours, so a fixed tick budget silently under-times
  slow conserve-mode legs. Uses a `safety_multiplier = 2.0` margin and a `min_ticks = 3000`
  floor (the old fixed default, still used for short/typical legs).
- Navigation safety (`lib/vehicle_navigation.py`): stall detection re-issues the drive command
  after repeated stuck cycles, dropping to `MIN_SPEEDMODE_THROTTLE` on each retry and giving up
  (brake, return `False`) after 3 failed recoveries — applies **regardless** of
  `is_driving_to_station`. Throttle stays engaged (drawing power per the speed/power model) the
  whole time a vehicle is stalled even though it's making zero progress, and the low-battery abort
  is deliberately skipped for station-bound legs (see above) — so an uncapped retry loop could
  previously drain the battery to nothing over the full navigation timeout purely from being stuck,
  with no safety net, on the one leg where that check doesn't apply. Base staging slots are
  staggered per vehicle index to avoid parking/charging-pad collisions.
- `is_at_base(threshold=3.0)` (`lib/vehicle_navigation.py`): `self.distance_to_home() <= threshold`.
  Loops use this to gate one-time-per-visit actions (top-off charging before departing, restocking)
  so they only fire when actually parked at base, not mid-trip in the field after a reload. Used by
  `run_expedition_cycle()` (`rover.py`), `run_construction_loop()`/`run_mining_loop()` (`pioneer.py`),
  and `run_survey_loop()` (`vehicle_survey.py`).
- **Loop-top "cargo aboard but not at base" safety net vs. mission resume**: `run_expedition_cycle()`
  (`rover.py`) and `run_mining_loop()` (`pioneer.py`) both compute `has_resumable_target =
  bool(self.current_target_key and self.current_target and ...)` before their Step 2 cargo check, and
  only force the return-to-base-and-unload detour when there is **no** resumable target. Without this
  gate, a save reload mid-trip (cargo partially loaded, `current_target_key` restored from the saved
  mission — see `load_mission()`) would see "cargo aboard, not at base" and force a full detour home
  before ever resuming the drive back to the claimed site, undoing the very trip it just resumed —
  even though the mission's own end-of-cycle Step 6/7 already returns and unloads once mining
  actually finishes. Self-correcting either way: any path that abandons a resumed target (e.g.
  `drive_with_recharge()` failing) calls `return_to_base()`, which unconditionally releases the
  claim — and `release_target_claim()` clears `current_target_key`/`current_target` when the released
  key matches, so `has_resumable_target` goes false next iteration and the safety net resumes normal
  operation. No permanent unload-starvation risk.
  - **Cargo/target material mismatch**: `cargo_matches_target(target)` (`lib/mining.py`
    `MiningMixin`, shared by both) additionally downgrades `has_resumable_target` to `False` (for
    that cycle only — `current_target_key` itself is untouched, so Step 3 still resumes the same
    target right after) whenever cargo already holds a *different* material than the resumed
    target's own `harvest_item`. Cargo isn't material-locked (`Cargo.stacks()` in
    `docs/models/storage_and_items.md` lists property-distinct stacks — a vehicle can physically
    carry a mix of ore types at once), so nothing would reject mining a different ore straight into
    an already-occupied hold; it would just waste capacity and leave a confusing mixed load instead
    of erroring. A target with no `harvest_item` (a Rover's POI survey target) always matches,
    since there's no ore to mismatch against.

### 2a-0. Supply Dock cargo draining (`lib/supply_dock.py` `SupplyDockController`)

`set_order()` rejects with `"cargo_present"` while *any* cargo is still physically loaded in the
dock's 5 slots — and `clear_order()` deliberately does **not** drain cargo, it only releases the
order assignment (per `docs/components/supply_dock.md`). So a cleared, completed, or expired
order's leftover materials sit in the dock forever unless something actively calls
`self.dock.input.eject("inventory", item_id, count)`. `drain_dock_cargo()` does this for every
non-empty slot; `step()` calls it (and returns, retrying next cycle) whenever `curr_order` is
`None` but `dock.total() > 0`, before ever attempting `set_order()` — otherwise every future order
assignment fails with `"cargo_present"` indefinitely, with no automatic recovery.

### 2a-0-1. Construction material demand cascade (`lib/production.py`)

`_cascade_blueprint_demand()` is the single source of truth for "how much of *any* item — finished
or intermediate — does active construction ultimately need," and the base both of the following
build on:

- Seeded from `required_item`/`required_count` across every pending/paused Construction Blueprint
  job (summed, deduped by job id) — e.g. a Thermal Cap build seeds `thermal_cap_kit` demand.
- Breadth-first propagated down through Fabricator/Smelter recipe `inputs` (`recipe_inputs_for()`):
  `thermal_cap_kit` demand cascades into `titanium_ingot` + `gas_pipe_segment` demand, which for
  `titanium_ingot` cascades further into `titanium_ore` demand.
- **Only each tier's shortfall propagates further down** — demand beyond that item's own current
  `inventory.count()`, not the full demand — so stock already sitting at any tier is counted once
  and doesn't inflate demand for the tiers beneath it. Example: 10 `power_line_segment` needed, 3
  already in Inventory → 7 still to build → 7 `titanium_ingot` needed, 5 already in Inventory → only
  the remaining 2 propagate → 4 `titanium_ore` needed (at a 2:1 smelt ratio), not 20. Verified by
  stub test against exactly this scenario.
- Known limitation: an item reachable via more than one distinct path nets its shortfall against the
  same Inventory snapshot independently at each occurrence, which can slightly overstate demand for
  a shared intermediate under a diamond-shaped recipe dependency — not worth a full MRP-style
  low-level-code solve for this game's shallow (2-3 tier) recipe chains.

Two consumers read this cascade differently:

1. `get_fabricator_targets()` (§2a-1) uses the **raw, uncapped demand** for items the Fabricator can
   build — a target must reflect how much still needs to *exist*, not how much can currently be
   reserved.
2. `get_construction_material_reservations()` nets it against current stock
   (`min(inventory.count(item_id), demand)`) — a *protect-from-shipping* amount, capped at both what's
   actually on hand and what's actually still needed. `supply_dock.py`'s `step()` and
   `pick_best_order()` subtract this from `inventory.count(item_id)` before deciding how much to
   `take()` into the dock or how "ready" an order looks — otherwise the Supply Dock would freely ship
   away Inventory stock the moment it landed, even material (at *any* tier — finished component,
   intermediate ingot, or raw ore) an active Pioneer build's production chain was already waiting on.

Deliberately conservative in one respect: a job's full cascaded demand stays reserved for as long as
the job remains pending/paused, even after a Pioneer has already loaded some of the finished item
into cargo (cargo isn't tracked here, only standing Inventory stock) — better to have the dock hold
back briefly on stock that's no longer actually contested than to let it snack away material a build
still needs.

### 2a-0-2. Multi-Fabricator Support (`lib/production.py`, `lib/fabricator.py`)

Same two problems as the Multi-Smelter section above, fixed the same way, for the Fabricator:
`production.discover_fabricator_ids()`/`_default_fabricator()` replace every hardcoded
`"fabricator_1"` fallback across `production.py`'s demand-cascade functions (recipe *availability* is
tech-gated and identical across same-type buildings, so any one discovered Fabricator is a
representative stand-in). No leader election was added on the Fabricator side — unlike Smelter,
nothing in `FabricatorController` runs a shared per-cycle task that would need gating to a single
instance (the Inventory→Warehouse rebalance sweep lives on the Smelter, not here), so there's nothing
for a Leader to do yet. What *does* need coordination: `choose_recipe()` picks strictly by
biggest-shortfall, so with several Fabricators every one of them would converge on the exact same
top-shortfall recipe while other demanded outputs went unbuilt. Fixed with a `claim_recipe()`/
`release_recipe()` pair in `lib/fabricator.py` — same shape and `STALE_TICKS=600` reasoning as
`smelter.py`'s, separate archive key (`"fabricator.recipe_claims"`) so the two claim pools don't
collide. `choose_recipe()`'s candidate loop now claims each sourceable candidate in turn (biggest
shortfall first) and moves to the next if the claim fails (another Fabricator already holds it);
`step()` releases the prior recipe's claim whenever it clears or switches away from it. Verified via
a stub test: two Fabricators facing two equal-shortfall candidates correctly split onto different
recipes, and a Fabricator re-picking its own already-claimed recipe refreshes rather than triggers a
switch.

### 2a-1. Fabricator demand tracking (`lib/production.py` `get_fabricator_targets()`)

`get_fabricator_targets()` is the single source of truth for what the Fabricator should be
building, and feeds `get_material_demands()` → `get_raw_material_demands()` (mining priority) too.
Three demand sources are folded together into one `{item_id: quantity}` dict:

1. `fabricator.stock_targets` archive key (defaults in `DEFAULT_FABRICATOR_STOCK_TARGETS`:
   `gas_pipe_segment`/`power_line_segment`/`liquid_pipe_segment` = 10 each) — edit the archived key
   directly (Data Archive Notebook) to retune without touching code.
2. The active Supply Dock order's `requires`, for items the Fabricator can actually build
   (`max()`'d against the stock target, not summed — an order doesn't add to the standing stock
   goal, it's the same "how many do I want on hand" question with a possibly higher floor).
3. **Pending/paused Construction Blueprints**, via `_cascade_blueprint_demand()` (§2a-0-1) filtered
   to items the Fabricator can build, `max()`'d against the existing target — **not summed**: targets
   are a steady-state "keep at least N in Inventory" floor, not additive per demand source (the
   standing stock buffer IS what a blueprint or order draws from, and `choose_recipe()`'s own
   `target - current` netting already rebuilds it after that draw — adding would just over-target
   and waste materials/time; caught by a stub test that would otherwise have asked the Fabricator
   for 20 `power_line_segment` instead of 10). Before this existed, a queued build's Inventory-sourced
   material (e.g. `thermal_cap_kit`, crafted from Titanium + Gas Pipe Segments — see
   `docs/database/recipes_fabricator.md`) was invisible to the Fabricator: it would never get crafted
   even with titanium ingots sitting in Inventory and an active build order for it, and
   `load_construction_materials()` would just keep failing the job forever (deferred to
   `failed_jobs`, retried, deferred again). This is the concrete case of CLAUDE.md's "Plan ahead for
   future production needs based on... placed blueprints" rule.

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
  (mirrors `execute_construction()`'s pattern in `pioneer.py`). The battery-interruption recharge
  stop can land at the *home base* station itself (not just a remote field station) — when it does
  (`is_at_base()`) and cargo is already carrying ore, it unloads there via `unload_cargo()` **before**
  calling `recharge_at_station()`, not after: a full recharge from a low state can take several real
  minutes, and ore sitting in cargo that whole time is ore the Smelter can't touch — unloading first
  gets it into circulation immediately instead of stranding it for the entire charge. Also means the
  resumed `mine_current_site()` call gets the *full* cargo capacity as `max_units` instead of just the
  small amount freed by the interruption, so the vehicle can fill up further before the next
  interruption rather than immediately needing another trip.
- Pioneer's mining role (`run_mining_loop()`, entrypoint `pioneer_3.py`) requires the operator to
  have already mounted a drill (`mount_hardware()` / Control Panel) — it only checks
  `hasattr(self.vehicle, "drill")` and idles with an advisory if absent; it never auto-mounts one.

### 2c. Storage Management (`lib/storage.py`)

Makes the whole production chain (vehicle unloading, Smelter/Fabricator/Supply Dock/Pioneer
construction input sourcing, and `production.py`'s demand tracking) aware of Warehouse/Large
Warehouse buildings, not just the central home `"inventory"` freight endpoint. Scope: Warehouse +
Large Warehouse only for now (`STORAGE_TYPE_IDS`) — Storage Bin uses a different, single-material
API shape (`docs/components/storage_bin.md`) and isn't included, though
`discover_storage_buildings()`'s `type_ids` param leaves room to add it later without changing any
caller. Everything defaults to the home outpost, matching how Inventory itself only participates at
Nocturna Base.

- `total_stock(item_id)` = `inventory.count(item_id)` + every discovered Warehouse's `count(item_id)`.
  This is what `production.py`'s `_cascade_blueprint_demand()`, `get_construction_material_reservations()`,
  `get_material_demands()`, `get_raw_material_demands()`, and `can_source_item()` all net against now
  (previously Inventory-only) — so demand/mining priority correctly accounts for stock sitting in a
  Warehouse instead of ignoring it.
- `best_unload_target(item_id, min_amount=1)`: least-full Warehouse with `space_for(item_id) >=
  min_amount`, else `"inventory"`. `vehicle_cargo.py`'s `unload_cargo()` picks a destination
  **per stack** (cargo can hold more than one item id) rather than connecting once to `"inventory"`
  up front.
- `take_item(port, item_id, amount)`: the one function behind every
  `machine.input.take(item_id, amount)` call site (Smelter ore loading, Fabricator input loading,
  Supply Dock material loading, Pioneer's `load_construction_materials()`). Tries whatever `port` is
  *currently* connected to first (usually Inventory, the existing default), and only reconnects to a
  Warehouse if that falls short — ports hold one source at a time (same single-destination
  constraint as `FluidPort`, see `lib/thermal_cap.py`), so this reconnects on demand rather than
  fanning out simultaneously.
- **Multi-Smelter Leader Election** (`SmelterController` in `lib/smelter.py`) — with several
  Smelters at home, `production.discover_smelter_ids()` replaces every place that used to hardcode
  the literal id `"smelter_1"` (a correctness bug, not just inefficiency: demand/recipe lookups would
  silently only ever consult one specific smelter's recipe set). Leader election
  (`check_leader()`/`update_role()`) mirrors `lib/solar.py`'s `SolarController.check_master()`
  *exactly* — same Archive+`run_control.is_running()` approach, **not** the Signal Bus, despite that
  being available; sorted by numeric id suffix, lowest currently-`is_running()` id wins, recomputed
  fresh every `step()` (no lease/heartbeat — if the Leader stops running, the next poll naturally
  produces a different, correct answer). Only the Leader runs the "inventory manager" sweep (see
  below) — Followers skip it, removing N-1 redundant identical sweeps of the same shared
  Inventory/Warehouse set. Every smelter (Leader or Follower) still independently runs its own
  `select_needed_ore()`/craft loop against the same shared `get_material_demands()` numbers, but each
  candidate recipe is `claim_recipe()`d (`archive.transaction("smelter.recipe_claims", ...)`,
  `SMELTER_RECIPE_CLAIM_STALE_TICKS = 600`, mirroring `vehicle_claims.py`'s claim/release shape) before
  being returned, so two smelters don't both start the same recipe while a second simultaneously-
  demanded ore sits untouched — a smelter whose claim attempt fails (another smelter holds a fresh
  claim on that recipe) tries the next demanded/available candidate instead. Released via
  `release_recipe()` whenever a smelter clears its own recipe (locked-recipe cleanup or no-demand
  cleanup in `step()`).
- **"Inventory manager" sweep** — `rebalance_inventory_to_warehouses()`, called once per cycle from
  the Leader's `SmelterController.step()` (confirmed always-running at home base): any **propertyless**
  (`slot.properties is None` — non-stackable/unique items like worn equipment are left alone)
  Inventory item spanning more than `INVENTORY_REBALANCE_SLOT_THRESHOLD = 2` slots gets moved to a
  Warehouse **entirely**, not partially — there's no real "quick access" cost to reading from a
  Warehouse instead of Inventory, so nothing is deliberately left behind.
  - **Direct move**: if any Warehouse has `space_for(item_id) > 0`, move as much as fits there
    (`inventory.transfer_to(warehouse_id, item_id, amount)` — Inventory exposes `transfer_to()`
    directly, no port/connection needed), splitting across more than one Warehouse if needed.
  - **Swap fallback**: if *no* Warehouse has any room at all (every one of its 5 material-locked
    slots already holds a different material), evicts whichever Warehouse occupant is cheapest to
    bring back to Inventory (smallest quantity) — but **only** when `slots_freed > slots_reclaimed`
    (`slots_reclaimed = ceil(evicted_qty / inventory_stack_size())`), a genuine net reduction in
    Inventory slots used, never a wash or a net loss. Verified by stub test against the exact
    scenario that prompted this: Warehouse full except a 5-unit Titanium Ingot slot, 60 Iron Ingot
    spanning 6 Inventory slots in Inventory — evicts the 5 titanium (costs 1 slot back), frees 6, a
    clear net win.
- `inventory_stack_size()`: `10`, or `20` once `research.is_unlocked("research_high_density_storage")`
  ("Bigger Stacks") — reuses the existing `research.is_unlocked(tech_id)` pattern already used in
  `lib/vehicle_claims.py`, not inferred from current slot contents.

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

---

## 🖥️ 7. Control Room Panel Cards (`panel_1.py`, `panel_2.py`, `panel_3.py`)

Card size is set from the Control Room UI (drag-resize or the size picker next to a card's
`Manage` button), **not** from the script — `panel.width()`/`panel.height()` just report whatever
size the operator picked (`docs/types/system_and_panels.md` `Panel.width()`/`height()`). The size
is discrete, not continuous:

| Label shown in the UI | Meaning | `panel.width()` | `panel.height()` |
| :--- | :--- | :--- | :--- |
| `1 x 1` | 1 column, 1 row | 500 | 200 |
| `1 x 2` | 1 column, **2 rows** | 500 | 400 |
| `2 x 1` | **2 columns**, 1 row | 1000 | 200 |
| `2 x 2` | 2 columns, 2 rows | 1000 | 400 |

The first number is **columns** (width), the second is **rows** (height) — going from `1x1` to
`1x2` only adds height, not width. A card whose layout assumes a wide canvas (multiple side-by-side
sections, a right-anchored control) will clip/overflow on a `1x2` card because it's still only
500px wide despite looking "bigger." This bit the Fleet card (`panel_2.py`) directly: it was set to
`1x2`, and the per-vehicle recall switch (anchored from the right edge assuming ~1000px) ran off
the card.

**Sizing recommendations for these three cards** (each has a multi-column row layout that wants
width, not height):
- `panel_1.py` (STATUS) and `panel_3.py` (PRODUCTION): **`2 x 1`** (1000x200). Both lay out 3-4
  side-by-side sections; 1 column leaves each section cramped.
- `panel_2.py` (FLEET): **`2 x 1`** for small fleets (up to ~4 vehicles), **`2 x 2`** once you have
  more — each vehicle is one row, and the card only shows as many rows as fit
  (`max_rows = (height - top - 16) // row_height`), printing `+N more vehicles` beyond that.

`panel_2.py` also degrades gracefully at 1-column widths (`wide = width >= 900` branches to a
2-line-per-vehicle layout and hides the location column) so it won't overflow even if resized
narrow — but the recommended sizes above give the intended one-line-per-vehicle layout.

General layout rule for any new card: prefer anchoring right-side elements from the right edge
(`width - <fixed px>`) over a width fraction (`width * 0.86`) when the element has a roughly
fixed pixel footprint (a `switch`, a `button`, a short `pill`) — fractions of a 500px vs 1000px
canvas land in very different places, but a fixed-from-the-right offset stays a constant, safe
distance from the border at either size.
