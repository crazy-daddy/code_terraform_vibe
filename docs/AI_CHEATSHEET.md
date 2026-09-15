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
| Water Pump (route water to network Liquid Tanks) | `water_pump.py` — see §1d, simpler cousin of `thermal_cap.py` (no overpressure/relief concept) |
| Storage management (Warehouse-aware sourcing/unloading, Inventory rebalancing) | `storage.py` — see §2c |
| Outpost ore-assignment & stock-target scaffolding (multi-outpost mining) | `outpost_mining.py` — see §2d |
| Data Archive persistence layer | `archive.py` |
| Wildcard pattern matching helpers | `patterns.py` |
| Per-script tick-cost profiling | `profiling.py` — see §1d |

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
    candidate, rather than sitting stalled on the same unreachable target forever. Each blacklist
    entry expires **individually** — `unreachable_targets`/`unreachable_sources` map
    `id -> the simulation tick it was blacklisted at` (`is_blacklisted(id, curr_tick)`, real
    `clock.tick()`, not step() calls), not a plain set with one shared "clear everything at once"
    timer — `RESCAN_INTERVAL_TICKS` (300 Cap-ticks / 150 Turbine-ticks) is each entry's own expiry
    window, so a target that was unreachable becomes retryable again once the player builds a new
    pipe to it, without disturbing a currently-*working* connection or any *other* entry's own timer.
    **This distinction is load-bearing, not stylistic**: an earlier version used one shared counter
    that wiped the *entire* blacklist at once on a fixed timer. With 2+ simultaneously-unreachable
    candidates ranked ahead of the one genuinely-reachable target (by fill_pct/discovery-order ties —
    e.g. two Gas Tanks at a far outpost sorting before the one actually pipe-connected to this Cap's
    own outpost), eliminating all of them can take longer than that window; the shared timer would
    then erase already-made elimination progress and restart the cycle from the first bad candidate
    before ever reaching the real one — an infinite ping-pong between the same 1-2 unreachable
    targets, observed in practice (a Thermal Cap repeatedly targeting two unreachable Gas Tanks at a
    different outpost, never once trying the one actually reachable from its own). Fixed by tracking
    each entry's own blacklist tick and expiring independently; verified by stub test asserting an
    older entry expires while a newer one (blacklisted after it) stays blacklisted, and by a full
    elimination-order test (two unreachable tanks → correctly settles on and stays on the third,
    reachable one).
    - **This fix alone did NOT resolve the reported ping-pong** — a second, more fundamental bug was
      still there underneath it, found by the player debugging in-game and confirmed by inspecting
      `_fill_pct_of_building()`: `discover_network_buildings()` used to append the raw `BuildingRef`
      from `outpost.buildings(type_id)` directly. Per `docs/components/outpost.md`, that's a
      lightweight *snapshot* carrying only `.id`/`.name`/`.type_id`/`.outpost`/`.powered`/`.position` —
      **not** the type-specific live methods (`fill_pct()`, etc.) that only exist on the full resolved
      component (`get_component(ref.id)`). So `_fill_pct_of_building()`'s
      `hasattr(building, "fill_pct")` check failed for *every* tank, always hitting the "unreadable,
      treat as 1.0" fallback — degenerating `sorted(tanks, key=_fill_pct_of_building)` into a no-op
      tie broken purely by discovery order, **and** defeating the fast path too (a healthy current
      tank also reads as `1.0 >= GAS_TANK_REBALANCE_FILL_FRACTION`, so it never short-circuits,
      forcing a full rescan every single step). The net effect: selection became "skip current, take
      the next one in a fixed discovery-order list" every call — a stable alternation between
      whichever two candidates happen to sit adjacent to each other in that order, never advancing to
      a third. This is exactly the failure mode the per-entry blacklist fix above couldn't reach,
      since it operates one layer up (which candidates are *eligible*), not on why selection *among*
      eligible candidates was broken. Fixed by resolving each `BuildingRef` via
      `get_component(ref.id) or building` inside `discover_network_buildings()` itself — same
      `get_component(id) or ref` pattern already used correctly in `storage.py`'s
      `discover_storage_buildings()` and `vehicle_energy.py`'s `get_all_charging_stations()`; this was
      the one discovery helper in the codebase that hadn't followed it. Verified by stub test using a
      `BuildingRef`-shaped fake (deliberately no `fill_pct()`) distinct from its full component,
      asserting the returned objects have `fill_pct` and that fill-based sorting reflects real values
      instead of a universal `1.0` tie. **Lesson for any future `outpost.buildings()`/
      `outpost_network`-based discovery helper**: always resolve to the full component before relying
      on anything beyond the five BuildingRef-native fields, or silently degrade in exactly this way.
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
    — real work, and (per profiling — see §1d) the actual cost driver of both controllers' `step()`.
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
  - **The real per-step cost was elsewhere, and profiling (§1d) is what found it**: with the walk
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

### 1c. Water Pump: Liquid Tank Routing (`lib/water_pump.py` `WaterPumpController`)

Mirrors §1b's Thermal Cap → Gas Tank connection/load-balancing/blacklist machinery almost exactly
(same `discover_network_buildings()`/`_fill_pct_of_building()`/per-entry `unreachable_targets`
blacklist/`CONNECTION_GRACE_TICKS`/`RESCAN_INTERVAL_TICKS`/`DISCOVERY_CACHE_INTERVAL_STEPS`
constants and reasoning), but deliberately simpler — a Water Pump has **no internal buffer to
overpressure at all** (`docs/components/water_pump.md` defines no `pressure()`/`is_overpressured()`/
`relief()`/`set_relief()` — the Pump is pure pass-through, storing nothing), so there is no
proportional release-valve/relief-valve reactive control to do, unlike Thermal Cap's whole
`release_throttle_for_pressure()` band logic. `step()` just calls `ensure_output_connection()` and
unconditionally requests `set_throttle(1.0)` every cycle — actual delivery already self-limits to
whatever a connected tank can accept (`pump_rate()` reads 0 with no reachable destination, per the
docs), so there's no cost to always requesting full output and nothing to react to.

- **Two target building types, not one**: `LIQUID_TANK_TYPE_IDS = ("liquid_tank",
  "large_liquid_tank")` — a Water Pump can fill either, so `discover_network_buildings()` here takes
  an iterable of type_ids (or a single string) and walks each outpost's `buildings(type_id)` for
  every type, deduping by id — thermal_cap.py's version only ever needed one type_id (`"gas_tank"`),
  so this is a small generalization, not a behavior change for the single-type case.
- `water_out` (a `FluidPort`, identical shape to Thermal Cap's `steam_out`) only ever holds one
  destination at a time, so serving several tanks means periodically re-pointing it, same as Thermal
  Cap. Any other scripted consumer connecting its own `water_in` to this Pump is independent of
  whatever `water_out` currently points at — no coordination needed here, mirroring the
  Cap/Turbine relationship in §1b.
- `is_stalled()` has the identical semantics to Thermal Cap's own (`"throttle open + water available
  + nothing transferred"` = likely no completed Liquid Pipe route), so the same
  blacklist-and-reselect reaction applies unchanged.
- Verified via a stub test: `discover_network_buildings()` finds and resolves both tank types (not
  just one) from raw `BuildingRef` snapshots to full components; connects to the least-full known
  tank first; the fast path makes no further `connect()` calls while the current tank is healthy;
  a stalled connection gets blacklisted and the Pump reconnects to the other known tank; per-entry
  blacklist expiry (still blacklisted just before `RESCAN_INTERVAL_TICKS`, retryable just after);
  `step()` always requests full throttle.

### 1d. Per-Script Tick-Cost Profiling (`lib/profiling.py`)

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
  candidate to wire this into temporarily. Not standardized across every controller — see the Phase 7
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
| **Rover** | `self.cruise_throttle` (explicit at construction, else the fleet-wide `vehicle.default_cruise_throttle` archive value, default 0.5) capped down per-leg by `max_safe_throttle_for_leg()` | Developer-confirmed travel power formula (no calibration): `(3 W + 8 W × active modules + 0.04 W × cargo units) × throttle^1.5`; safety margin `SAFETY_MARGIN_MULTIPLIER = 1.05` (5%) — see §2a | Sonar scan: `SONAR_WH_BUDGET = 2.0` Wh. Mining drill: exact per-ore/per-drill/per-purity `mine_wh_per_unit(item_id, purity)`, `MINE_WH_PER_UNIT = 2.5` Wh/unit only as the no-item-id fallback — see §2a. Return to nearest charging station (not necessarily home) when Wh falls below the trip budget. |
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
- **Mining/drill budget is also a developer-confirmed exact model now, not a flat average.**
  `mine_wh_per_unit(item_id, purity)` (and its standalone `mine_wh_per_unit_for(vehicle, item_id,
  purity)` twin, same `_for` pattern as travel energy above) computes:
  ```
  time (h) = (ORE_DIG_MINUTES[item_id] / 60) × drill.speed_multiplier() / PURITY_DIVISOR[purity]
  Wh       = time (h) × DRILL_POWER_W_BY_HARDNESS_LIMIT[drill.hardness_limit()]
  ```
  from `docs/components/drill_module.md`'s documented `.mine()` time formula
  (`mineral_base_minutes × drill.speed_multiplier() / site_purity`) and per-tier Watts
  (basic=10W/industrial=20W/heavy=30W, keyed by `drill.hardness_limit()` since there's no
  `.power_draw()` method to query it live), `docs/database/items_minerals.md`'s per-ore dig
  minutes (iron_ore/silicon=15, lead_ore=18, titanium/cobalt=20, rare_earth=25, neutronium=30),
  and `docs/types/world_and_sites.md`'s `.purity` yield multiplier (`standard`=1×/`rich`=2×/`pure`=3×
  — the same divisor the game's own time formula uses). `calculate_trip_energy()`'s
  `mine_item_id`/`mine_purity` params feed this in; every real mining call site (`mining.py`'s
  `select_best_mining_target()`/stationed-mining resume, `rover.py`/`pioneer.py`'s resumed-target
  budgeting) passes the candidate's own `harvest_item`/`purity`, since both are already carried on
  every mining candidate dict. `MINE_WH_PER_UNIT = 2.5` (the old flat constant) is now only a
  fallback for a candidate with no `mine_item_id` at all (a non-mining candidate) — it happens to
  equal the exact rate for the cheapest real case (basic drill, iron ore, standard purity), but was
  under-reserving by up to **~3.6x** for a Heavy drill on Neutronium before this fix (`(30/60) × 0.6
  × 30 W = 9.0` Wh vs. the flat `2.5` Wh) — a real latent risk independent of drive throttle, found
  while validating whether Pioneers would stay safe running at higher speed. Verified via a stub
  test covering the cheapest case (matches the flat constant exactly), the worst case (Heavy/
  Neutronium ≈ 3.6x), purity dividing extraction time, and the no-drill/unknown-ore fallback.
- Throttle is clamped to `[MIN_SPEEDMODE_THROTTLE=0.10, MAX_SPEEDMODE_THROTTLE=1.0]` and picked
  per-leg by `select_cruise_throttle()` / `max_safe_throttle_for_leg()`, which always keeps enough
  reserve to still reach a charging station afterward. Because power scales with `throttle^1.5`
  while speed scales with `throttle`, Wh/m for a leg scales with `sqrt(throttle)` — **not** linear
  in throttle — so `max_safe_throttle_for_leg()` solves for the throttle bound via
  `t <= (available_Wh / (distance * coeff * SAFETY_MARGIN_MULTIPLIER)) ** 2`, not a linear ratio.
  Verified against a brute-force numerical search.
- **Cruise throttle is one numeric default, not a binary conserve/highspeed flag.**
  `select_cruise_throttle()` picks `min(self.cruise_throttle, MAX_SPEEDMODE_THROTTLE)` as the
  baseline for a leg, then caps it DOWN (never up) to whatever `max_safe_throttle_for_leg()` says is
  safe. There used to be a separate `vehicle.speedmode` archive flag (`"conserve"`/`"highspeed"`)
  with its own branch calling `max_safe_throttle_for_leg()` directly for `"highspeed"` — removed as
  redundant once cruise_throttle became the single lever: setting `cruise_throttle = 1.0` makes the
  one remaining formula produce *exactly* the old highspeed branch's result (baseline=1.0 capped
  down only when unsafe), so keeping both was two code paths for one behavior.
  `self.cruise_throttle` itself now resolves the same way as `wh_per_progress`
  (`VehicleController.__init__`): a thin entrypoint script either passes an explicit value (the
  demand-driven transporter role always passes `cruise_throttle=1.0`, since it recharges fully at
  both ends of every leg — see §2f) or passes nothing/`None`, in which case it reads
  `default_cruise_throttle()` — a single fleet-wide `vehicle.default_cruise_throttle` archive value
  (clamped to `[MIN_SPEEDMODE_THROTTLE, MAX_SPEEDMODE_THROTTLE]`, falling back to
  `DEFAULT_CRUISE_THROTTLE_FALLBACK = 0.5` if never set) — settable via the Data Archive Notebook, or
  live from `panel_2.py`'s FLEET card (a `panel.slider()`, same pure-intent-publish pattern as the
  per-vehicle recall switch on the same card — the card only writes the archive value, each
  vehicle's own script is what reads and acts on it), to speed up (or slow down) every such vehicle
  at once, without editing each one's script. All of `rover_1-3.py`/`pioneer_1-4.py` now pass no
  `cruise_throttle` at all for exactly this reason.
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

**Pile-on fallback + even split** (found from real play: "fabricator_1 sits idle while fabricator_2
slaves away producing 100 circuit boards" — with only ONE recipe ever demanded, the claim's
"spread across distinct recipes" logic left every Fabricator past the first idle forever, since
there was never a second demanded recipe to fall back to). Same shape as the Smelter fix above:
`choose_recipe()` collects every sourceable candidate in shortfall order, tries to claim each, and
if NONE can be exclusively claimed, joins the biggest-shortfall one anyway rather than returning
`None`. Unlike Smelter, this one DOES need an explicit even split: `load_inputs()` pre-loads a whole
`required_per_craft * crafts_remaining` stockpile batch up front (not a small per-cycle pull the way
Smelter's ore intake is), so several Fabricators each independently loading the FULL remaining
shortfall would overshoot the target well before `total_stock()` catches up on the next poll.
`_fabricator_worker_count(recipe_id)` — a live headcount (not archive-tracked, so it counts joiners
too) of every discovered Fabricator whose `get_recipe()` currently matches — divides
`get_fabricator_active_recipe()`'s `crafts_remaining` by that count (ceil division, floored at 1
worker so a lone Fabricator's math is unchanged). Verified via stub tests: a sole demanded recipe is
claimed exclusively by the first Fabricator and joined (not idled on) by the second/third; `crafts_remaining`
for 100 needed units split across 2 workers on the same recipe comes out to 50 each, not 100 each;
worker-counting correctly isolates Fabricators on a different recipe and floors at 1 when nobody
matches at all.

### 2a-0-3. Multi-Dock Support (`lib/production.py`, `lib/fabricator.py`)

Same hardcoded-id bug class as Multi-Smelter/Multi-Fabricator above, just not caught for Supply Dock
at the time — found while making `panel_3.py` (PRODUCTION card) dock-aware. `get_fabricator_targets()`,
`get_material_demands()`, and `get_raw_material_reason()` all used to read a single
`_component("supply_dock_1")` directly, so a second Supply Dock's own active order was invisible to
every demand-cascade function: its required items would never register as Fabricator targets, raw
material demand, or mining priority — a second dock could sit there indefinitely with no ore/ingots
ever routed toward its order. Fixed with `discover_supply_dock_ids()` (same shape as the other two
discovery functions) and `_all_dock_orders()` (`[(dock, order), ...]` for every dock currently holding
one), which every demand-cascade function now loops instead of reading one hardcoded dock. No claim
coordination was needed here (unlike Fabricator recipes) — order fulfillment is inherently per-dock,
so there's no "two docks converge on the same order" race to guard against. `find_dock_order_requiring(item_id)`
consolidates "which dock's order wants this item" into one function, shared by
`get_raw_material_reason()` and `lib/fabricator.py`'s `target_reason()` (previously its own separate
`_component("supply_dock_1")` read). Verified via a stub test: two docks with two different
single-item orders both correctly register demand (the actual bug — previously only the first
dock's order counted at all), and `find_dock_order_requiring()`/`get_raw_material_reason()` correctly
attribute an item to whichever dock's order actually wants it.

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

### 2a-2. Fabricator input-stockpile ejection (`lib/fabricator.py` `eject_excess_inputs()`)

`set_recipe()`/`clear_recipe()` both explicitly preserve the input stockpile untouched
(`docs/components/fabricator.md`) — the only built-in way to clear it is `InputSlot.flush()`, which
**permanently discards** the material rather than returning it. Without an active counter-measure,
staged material for a recipe that's no longer active (switched away from, or cleared entirely) sits
stranded inside the Fabricator — up to its combined 200-unit stockpile cap — invisible and unusable
to every other consumer on the network (another Fabricator, the Smelter, a Supply Dock order) that
could otherwise use it. This was visible in-game as a Fabricator idling at e.g. 145/200 stockpile
used, most of it materials the active recipe needed only a fraction of.

`eject_excess_inputs()` runs every `step()`, before recipe selection, and recovers stranded/excess
staged material via `InputSlot.eject(destination, item_id, count)` (routes to the least-full
Warehouse with room, via `storage.best_unload_target()`, or falls back to Inventory — never
`flush()`) in two cases, both computed off the recipe currently set on the machine (via
`production.get_fabricator_active_recipe()`, same call `load_inputs()` already uses):

1. **Staged material the active recipe doesn't need at all** (leftover from a prior recipe, or no
   recipe set right now) — ejects all of it.
2. **Staged material the active recipe DOES need, beyond `required_per_craft * crafts_remaining`**
   — the identical cap `load_inputs()` itself loads up to — e.g. `crafts_remaining` dropped since
   this batch was staged (the stock target was lowered, or another Fabricator/the Supply Dock
   already covered part of the shortfall) — ejects just the excess, keeping enough staged for the
   batch still in flight.

`eject()` is documented as transactional and safely rejects (no-ops, moves nothing) on any portion
still reserved for an in-progress craft, so calling this unconditionally every step — even mid-craft
— is harmless; a rejected attempt just retries next cycle once the reservation clears. Verified via
a stub test covering all four cases: a fully-orphaned leftover item ejected in full, excess above
`required * crafts_remaining` ejected while the needed amount is kept, every staged item ejected when
no recipe is set at all, and an exactly-at-target staged amount left untouched (no eject call at all).

### 2a-3. Fabricator fluid-input connections (`lib/fabricator.py` `ensure_fluid_connections()`)

A recipe's `fluid_inputs` (e.g. `{"water_in": 1.0}`) is delivered via a `FluidPort` connection, not
an Inventory/Warehouse take — `can_source_fluid()`/`recipe_is_sourceable()` (§2a-1) only ever
confirmed a matching source building *exists somewhere on the network* before selecting such a
recipe; nothing actually connected `.water_in`/`.steam_in`/`.oil_in` to one. A Liquid/Gas Tank or
Water Pump has no script of its own (purely passive), so nothing on the other side of the pipe ever
calls `connect()` either — this was a real gap, not just a monitoring one: a fluid-needing recipe
could get set and then sit stalled forever with an unconnected port.

`ensure_fluid_connections(recipe)` runs every `step()` and mirrors `lib/steam_turbine.py`'s
`ensure_input_connection()` almost exactly — both declare an INPUT port's own upstream source,
discovered network-wide and blacklisted on stall, same shape as `lib/thermal_cap.py`'s
output-side connection logic (§1b/§1c) just facing the other direction:

- For each `fluid_key` the active recipe declares, `production.FLUID_SOURCE_TYPE_IDS[fluid_key]`
  names every building type that can feed it (e.g. `water_in` accepts `water_pump`,
  `steam_condenser`, `liquid_tank`, or `large_liquid_tank`) — the same mapping `can_source_fluid()`
  already uses, so "which buildings satisfy this fluid" has one source of truth.
- **No `is_stalled()` exists on the Fabricator itself** (unlike Steam Turbine/Thermal Cap/Water
  Pump), so reachability is inferred instead from the port's own `flow_rate()` staying `0` for
  `FLUID_STALL_STREAK_BLACKLIST_THRESHOLD=5` *consecutive* ticks while it still has room to receive
  (`level() < capacity()`) — a legitimately full port also reads `flow_rate()==0`, and that must NOT
  be mistaken for a stall (verified explicitly by a stub test). Same per-entry (not shared-clock)
  blacklist expiry as every other discover/connect/blacklist controller in this project
  (`FLUID_RESCAN_INTERVAL_TICKS=150`, matching Steam Turbine's value).
- State (`_fluid_connected`/`_fluid_stall_streak`/`_fluid_unreachable`/discovery cache) is keyed per
  `fluid_key`, not a single shared value — a recipe can need more than one fluid at once (an
  oil-refining recipe needs both `oil_in` and `water_in`), and each port's own source is entirely
  independent of the others.
- Verified via a stub test: a recipe with no `fluid_inputs` is a no-op; first connection discovers
  and connects to the only known source; healthy flow makes no further `connect()` calls; a full
  port reading zero flow is correctly NOT treated as starved even for many consecutive ticks;
  genuine starvation (room to receive, zero flow, sustained past the streak threshold) blacklists
  the source and reconnects to a different one; per-entry blacklist expiry.

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
- `select_best_mining_target(candidates)`: sorts by `(priority, -PURITY_RANK, distance)` — lower
  priority number wins first; within the same priority tier, a richer vein wins over a merely-closer
  one (`PURITY_RANK = {"standard": 0, "rich": 1, "pure": 2}`, from `MiningSite.purity` — a 1x/2x/3x
  extraction-rate multiplier per `docs/types/world_and_sites.md`); distance only breaks ties between
  equally-rich candidates. Same lexicographic-tiering style priority itself already used (a
  priority=2 candidate always beat priority=3 regardless of distance; richness now works the same way
  one level down) — a soft preference, not a hard filter, since the `calculate_trip_energy()`
  achievability check and atomic `claim_target()` still run after sorting either way, so an
  unreachable-on-budget rich site still loses to a reachable standard one. Both candidate builders
  (`build_mineral_site_candidates()`, `build_local_stockpile_candidates()`) attach each site's
  `"purity"` from `getattr(site, "purity", None)`; POI candidates (no purity) rank as `"standard"`'s
  `0` by default, a no-op since they only ever compete against other POIs at `priority=1`. Verified by
  stub test: a `"rich"` site 1.5x farther than a `"standard"` one in the same tier still wins; priority
  tier still outranks purity across tiers; equal-purity candidates fall back to plain distance. Also
  used for Rover's combined POI+mineral candidate list (POIs are `priority=1`, mineral sites
  `priority=2`/`3`).
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
  - **Pile-on fallback**: the claim's whole point is spreading *distinct* demanded ores across
    *distinct* smelters — but when only ONE ore is demanded at all (a single large order), every
    smelter past the first used to just find it already claimed and idle forever, with no second
    demanded ore to fall back to. `select_needed_ore()` now collects every sourceable/demanded
    candidate first, tries to claim each in turn same as before, but if NONE can be exclusively
    claimed (every one is already fresh-claimed by a different smelter), joins the first one anyway
    instead of returning idle — splitting one large order's workload across every smelter instead of
    running it through a single one serially. No explicit even split was needed here (unlike the
    matching Fabricator fix below): `get_material_demands()` already nets against `total_stock()`
    (which includes what every joined smelter has already produced), so several smelters pulling the
    same ore in parallel each cycle self-throttle down to 0 together as the target is met, rather
    than each independently re-committing to the full remaining shortfall.
- **"Inventory manager" sweep** — `rebalance_inventory_to_warehouses()`, called once per cycle from
  the Leader's `SmelterController.step()` (confirmed always-running at home base): any **propertyless**
  (`slot.properties is None` — non-stackable/unique items like worn equipment are left alone)
  Inventory item gets moved to a Warehouse **entirely**, not partially — there's no real "quick
  access" cost to reading from a Warehouse instead of Inventory, so nothing is deliberately left
  behind — when either:
  1. It spans more than `INVENTORY_REBALANCE_SLOT_THRESHOLD = 2` slots on its own (the original rule), or
  2. **It's already split**: some units sit in Inventory while a Warehouse already holds some of the
     same item too, regardless of Inventory slot count (`_warehouse_item_ids()`) — added after a real
     case: `gas_pipe_segment` (stock target `10`) ended up 10 in Inventory + 10 already in a
     Warehouse, double the intended target, split across both locations. Once an item already has a
     home in a Warehouse, a further remainder in Inventory serves no purpose (every consumer already
     reads combined stock via `total_stock()`, not by physical location) — it just fragments the same
     material. Verified via a stub test: the original bulk-threshold rule still fires unchanged; a
     single-slot item with no Warehouse presence is still left alone; a single-slot item ALREADY
     split with a Warehouse gets fully consolidated into it; a property-bearing item is never
     touched either way.
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

### 2d. Outpost Ore-Assignment & Stock-Target Scaffolding (`lib/outpost_mining.py`)

Phase B of the Multi-Outpost Production Network (`TODO.md` Phase 3). Answers "which ores should a
vehicle stationed at outpost X mine?" and "how much should it stockpile before stopping?" — consumed
by Phase C's stationed-mining role (§2e).

- **`assigned_ores_for(outpost_id)` → `[item_id, ...]`** — the read path, called every cycle by the
  stationed-mining candidate builder. Same "seed once, then editable" convention as
  `production.py`'s `FABRICATOR_STOCK_TARGETS_KEY`: auto-computes via `_compute_ore_assignment()`
  **only** the first time this outpost id has no stored `archive` entry at all
  (`OUTPOST_ORE_ASSIGNMENTS_KEY = "outposts.ore_assignments"`); every call after that — including
  after new POIs are surveyed nearby — returns the stored list completely untouched, so a player's
  manual edit is never silently clobbered by a background loop. Verified by stub test: appending
  new surveyed sites between two calls does not change the second call's result.
- **`_compute_ore_assignment(outpost_id)`** (internal, shared by both entry points below so seeding
  and manual rebuilds can't drift apart in ranking logic) — groups every `journal.surveyed_sites()`
  mineral site by nearest outpost via `nearest_outpost_id(x, y)` (thin wrapper around
  `outpost_network.nearest(x, y)`), ranks this outpost's candidate ores by site count descending,
  and caps the list to `_warehouse_slot_count(outpost_id)` —
  `sum(w.capacity() for w in storage.discover_storage_buildings(outpost)) // WAREHOUSE_SLOT_CAPACITY`
  (`2000`, one Warehouse slot, fixed regardless of research per `docs/components/warehouse.md`). An
  outpost with no Warehouse yet seeds an **empty** list (nothing assigned until storage exists) —
  building one later doesn't auto-widen it; that's what the next function is for.
- **`reseed_ore_assignment(outpost_id)`** — explicit, **never auto-called** rebuild: recomputes and
  overwrites the stored entry regardless of whether one exists. Exists so a not-yet-designed Control
  Panel button can let the player intentionally refresh an outpost's ore list (new POIs surveyed, a
  second Warehouse added) without any background loop risking a clobber on its own schedule.
- **`stock_target_for(outpost_id, item_id)` → units** — same seed-once-then-editable shape, default
  `WAREHOUSE_SLOT_CAPACITY = 2000` (one Warehouse slot) the first time a given `(outpost_id, item_id)`
  pair is looked up.
- **`nearest_outpost_id(x, y)`** / **`outpost_by_id(outpost_id)`** — thin wrappers around
  `outpost_network.nearest()` / iterating `outpost_network.outposts()`, reused by both the seeding
  logic above and Phase C's per-site candidate filtering (§2e).

### 2e. Stationed Mining Role (`lib/vehicle.py`, `lib/vehicle_energy.py`, `lib/mining.py`)

Phase C of the Multi-Outpost Production Network. Lets a Rover/Pioneer instance treat **any** outpost
— not just home — as its base, so it can mine that outpost's assigned ores (§2d) into its own local
Warehouse, independent of home's live demand.

- **`VehicleController.__init__`'s `home_base` param** (replaces the old fixed-tuple `home_coords`)
  — an outpost id, or `None` for the production/home outpost. Resolved to **live objects exactly once
  at construction**, cached as `self.home_outpost` (`get_outpost_ref(home_base)`) and
  `self.home_charging_station` (`find_charging_station(self.home_outpost)`), rather than re-walking
  `outpost_network.outposts()` by id on every subsequent lookup — the same redundant-network-walk
  class of cost the Thermal Cap/Turbine profiling work (§1b/§1d) already fixed once this session, now
  avoided here from the start. `get_home_slot_coords()` reads only these two cached fields: the
  charging station's position if one was found, else the outpost's own `.coords()`, else a literal
  `(0, 0)` only if `outpost_network` was unavailable at construction time. `self.home_base` itself is
  kept only for identity checks (e.g. `vehicle_cargo.py`'s "am I home-based at all?" gate); anything
  needing the outpost/station object reads the cached fields, not `home_base` re-resolved. Trade-off:
  a charging station built at this outpost *after* construction isn't picked up until the next script
  reload — acceptable since actual recharge routing (`get_nearest_charging_station()`) still does its
  own fresh network-wide walk every call regardless (that one's supposed to stay live, it's finding
  *any* station fleet-wide, not resolving this vehicle's own fixed home). Verified by stub test:
  default resolves to home's charging station; a stationed outpost with no charging station yet falls
  back to the outpost's own coords; adding a charging station later is picked up by a fresh instance
  (next reload); 10 repeated `get_home_slot_coords()` calls make zero additional `outposts()` walks.
- **`unload_cargo(outpost=None)`** (`lib/vehicle_cargo.py`) — `outpost` defaults to `self.home_outpost`
  (cached, no lookup), so a stationed vehicle unloads into **its own** outpost's Warehouse by default,
  not home's; the explicit override exists for Phase D's transporter (§2f), whose own `home_outpost`
  is its stationed mining outpost even though its delivery leg specifically targets home.
  `wake_smelter()` is only triggered when the *resolved delivery target* has `.is_home == True` (not
  `self.home_base is None`, since a transporter's `home_base` is its mining outpost even while
  delivering to home) — ore that lands at a remote outpost's Warehouse isn't reachable by the Smelter
  until a transporter hauls it home, so waking it early would do nothing useful.
- **`MiningMixin.build_local_stockpile_candidates(outpost_id)`** (`lib/mining.py`) — for each ore in
  `outpost_mining.assigned_ores_for(outpost_id)` still under its `stock_target_for()`, builds mineral
  site candidates the same way `build_mineral_site_candidates()` does (same hardness/claim/blacklist
  filtering) but additionally requires `outpost_mining.nearest_outpost_id(site.x, site.y) == outpost_id`
  — a site nearer some other outpost is that outpost's job, not this vehicle's, even if reachable.
  Independent of home's live demand entirely (no `get_raw_material_demands()` call), since the point
  is stockpiling ahead of it. Verified by stub test: a site near home is excluded from an outpost_3
  candidate list; candidates disappear once that ore's stock target is met.
- **`MiningMixin.run_stationed_mining_loop(outpost_id)`** — same overall shape as
  `run_expedition_cycle()`/`run_mining_loop()` (reload-resume safety net, cargo/target mismatch
  detour, claim + drive + mine + return + unload + recharge), with target selection swapped for
  `build_local_stockpile_candidates()` and "return to base" already meaning "return to this outpost"
  via the `home_base` resolution above — no separate return-path logic needed.

### 2f. Demand-Driven Transporter Role (`lib/vehicle_cargo.py` `run_supply_run_loop()`)

Phase D of the Multi-Outpost Production Network — the piece that actually moves ore Phase C's
stationed miners stockpiled back to **the production outpost** (Nocturna Base). Replaces
`lib/pioneer.py`'s old single-route, manually-configured `transport_once()`/`run_transport_loop()`/
`find_outpost_coords()`/`find_local_store()` (deleted — no thin entrypoint script referenced them)
with a fully automatic, demand-driven loop shared by Rover and Pioneer (lives on `VehicleCargoMixin`,
not `mining.py` — a dedicated hauler needs neither a drill nor construction slots).

**Terminology note (read this before "home" trips you up elsewhere in this codebase)**: for every
*other* vehicle, "home"/"base" always means the production outpost, since that's the only outpost a
regular vehicle ever calls home. A transporter breaks that assumption on purpose — it's constructed
with `home_base=<mining outpost id>` (§2e), so **its own `self.home_base`/`self.home_outpost` point at
the *stationed mining outpost*, not the production outpost** — only its delivery leg ever touches the
production outpost, and it does so via a separately-resolved reference
(`self.get_outpost_ref(None)`, kept in a variable literally named `production_outpost` in the code,
never called `home_outpost`) rather than via `self.home_base`. Below, "the production outpost" always
means Nocturna Base specifically; "its stationed outpost" always means wherever this transporter's own
`home_base` points.

- **Construction**: `PioneerController(vehicle, home_base=<mining outpost id>)` — same mechanism as
  Phase C's stationed miners, reusing all of its caching (§2e) with zero new code. It idles and
  recharges at its stationed outpost between runs (via the existing `is_at_base()`/`return_to_base()`),
  driving to the production outpost explicitly only for the delivery leg. **Pioneer, not Rover, for
  this role** — Rover's integrated hold is a fixed `capacity() == 10` (`docs/components/rover.md`),
  far too small for bulk ore hauling; Pioneer's cargo comes from Portable Bins across its Cargo Racks,
  scaling with loadout, and exposes the identical `Cargo`/`VehicleInputSlot`/`OutputSlot` interface
  `run_supply_run_loop()` already uses — no code changes needed to place this role on either vehicle
  type, it's purely a hardware/entrypoint-script choice. (A working example lives in a thin
  entrypoint script in the project root — those get renumbered/edited often enough not to name one
  here; search for `run_supply_run_loop` to find the current one.)
- **`run_supply_run_loop(poll_interval=10.0)`** — takes no `item_id` at all: **the load can mix
  several different assigned ores in one trip** (e.g. 50 titanium + 30 silicon), decided fresh every
  cycle, not fixed at construction. An outpost can have several assigned ores at once (Phase B's
  `assigned_ores_for()`), so limiting one transporter to a single item per run would leave the others
  piling up unused, or waste capacity hauling a small amount of one ore while room to spare sits empty.
  Each cycle:
  1. `_current_supply_items()` — if cargo is already aboard (resuming after a reload mid-delivery),
     reads every item straight off `self.vehicle.cargo.stacks()` instead of re-planning, so an
     in-progress mixed delivery is never abandoned partway for a newly-more-urgent item.
  2. Otherwise `_plan_supply_load(capacity)` — ranks this (stationed) outpost's
     `outpost_mining.assigned_ores_for()` by the production outpost's unmet demand
     (`get_raw_material_demands()`) descending, keeping only those that actually have stock sitting at
     this stationed outpost right now (an ore with huge demand but nothing on hand yet loses its
     ranking entirely, not just its priority), then greedily takes
     `min(unmet demand, stock on hand, remaining capacity)` from each in that order until capacity
     runs out or no more qualifying ore remains. Returns `[(item_id, amount), ...]`, possibly
     spanning several ores; empty (idle at the stationed outpost, no preemptive/opportunistic
     top-off — confirmed with the user, matching CLAUDE.md's Demand-Driven Production rule) if
     nothing qualifies at all.
  3. **`is_at_base()` check before loading**: `take_item()`'s Warehouse connection needs the vehicle
     physically within the stationed outpost's service area, so if it isn't there yet — left parked at
     the production outpost after its last delivery, or a fresh script start elsewhere — it drives
     there via `return_to_base()` first. Without this the loop used to jump straight to loading
     wherever the vehicle happened to be, fail every take (wrong/no local source), and just sit there
     printing "Could not load any planned item" forever instead of ever returning to the stationed
     outpost — caught from real in-game output showing exactly that.
  4. Loads each `(item_id, amount)` in the plan via
     `storage.take_item(self.vehicle.input, item_id, amount, outpost=self.home_outpost)` — note
     `self.home_outpost` here correctly means the stationed outpost, where the ore actually is.
  5. Drives explicitly to `self.get_outpost_ref(None)` (the production outpost, resolved once at loop
     start into the `production_outpost` variable) — **not** `return_to_base()`, which would go to its
     own stationed outpost instead.
  6. `unload_cargo(outpost=production_outpost)` — the explicit override from §2e (this vehicle's own
     `home_outpost` is the stationed outpost, not the production one); already sends each cargo stack
     to its own destination independently, so a mixed load needed no changes on the delivery side at
     all.
  7. **Recharges fully at the production outpost** (`recharge_at_station(target_level=1.0)`) before
     heading back — `get_nearest_charging_station()` (used internally when no station is given)
     resolves by current *position*, not `self.home_base`, so this correctly finds the production
     outpost's own station even though this vehicle's `home_base`/`home_outpost` point elsewhere.
     Starting the return leg fully charged lets it run at full throttle (a transporter script can set
     `cruise_throttle=1.0`) without `drive_with_recharge()` needing to plan an intermediate stop for
     it — faster round trips than only recharging back at the stationed outpost.
  8. `return_to_base()` back to its stationed outpost and recharges there too, ready for the next cycle.
- Verified by stub test: load planning — a mixed plan correctly spans two qualifying ores in one trip
  when capacity allows (50 titanium + 30 silicon), correctly excludes a much-higher-demand ore that
  has zero stock on hand, and correctly fills the higher-ranked ore first then gives the remainder to
  the next when capacity is tight; `_current_supply_items()` reflects every stack in a full mixed
  cargo, not just the first. Full loop — idles with zero drive calls when the stationed outpost has no
  stock; performs repeated hauling trips (each correctly capped by cargo capacity, not the larger
  demand figure) until the stationed outpost's stock is fully drained; makes zero drive calls when the
  production outpost's demand is `0` even with plenty of stock sitting at the stationed outpost
  (confirms no preemptive top-off); recharges exactly
  twice per completed trip (once at the production outpost before the return leg, once at the
  stationed outpost after returning); drives back to the stationed outpost via `return_to_base()`
  before loading when not already there, instead of failing to load and idling in place indefinitely.

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
- `panel_1.py` (STATUS): **`2 x 1`** (1000x200) — lays out 3-4 side-by-side sections; 1 column
  leaves each section cramped.
- `panel_2.py` (FLEET) and `panel_3.py` (PRODUCTION) share the same one-row-per-item, scrollable-list
  shape: **`2 x 1`** for a handful of rows, **`2 x 2`** once you have more — each row shows as many
  as fit (`max_rows = (height - top - 16) // row_height`) at once. Beyond that, a `panel.slider()`
  (there's no vertical slider/scroll widget in the panel API, so a horizontal one is repurposed: its
  0-1 value maps to a row offset into the list, `round(value * (len(rows) - max_rows))`) lets the
  player scroll through the rest, with a live `"X-Y of N"` indicator folded into its own label text.
  The slider is only drawn (and its row's space only meaningfully used) once the list actually
  exceeds `max_rows` — reserved unconditionally either way so the row grid below never jumps as the
  count crosses that threshold from one tick to the next.
  - `panel_2.py` (FLEET): one row per vehicle.
  - `panel_3.py` (PRODUCTION): one row per Smelter + Fabricator + Supply Dock, in that order —
    discovered live via `production.discover_smelter_ids()`/`discover_fabricator_ids()`/
    `discover_supply_dock_ids()` rather than assuming a single `"smelter_1"`/`"fabricator_1"`/
    `"supply_dock_1"` each (a second instance of any of the three used to be entirely invisible to
    this card — the same hardcoded-id bug class Phase A fixed in `production.py` itself, just not
    caught for Supply Dock at the time; see the Multi-Dock note below). Each row shows a role pill
    (SMELTER/FABRICATOR/DOCK), the machine's current recipe (or the dock's order name + first
    pending item, `"+N more"` if several), and a status pill (RUNNING/IDLE for a machine,
    ACTIVE/READY/IDLE for a dock: pending items / fully shipped / no order at all). Inventory was
    removed from this card entirely — a dedicated storage card with history graphs is a planned
    follow-up, not rebuilt here.

Both also degrade gracefully at 1-column widths (`wide = width >= 900` branches to a shorter row
height and, for `panel_2.py` specifically, hides the location column) so neither overflows even if
resized narrow — but the recommended sizes above give the intended one-line-per-row layout.

**Two real overlap bugs found and fixed across all three cards** (screenshot-driven — text was
visibly stacked on top of other text in-game):
1. `card(x, y, w, h, title)` already renders its own title bar text (`docs/types/system_and_panels.md`:
   "Bordered subsection with **optional title bar**"). All three cards additionally called
   `panel.label(24, 34, TITLE, "caption")` right after — a second, independently-positioned render of
   the exact same title text, landing almost on top of the card's own title bar. Removed the redundant
   `label()` call in all three; `card()`'s title is the only title render now.
2. `slider(key, x, y, w, default, label)` draws its own `label` text at a position this script doesn't
   control — pairing it with a separately-positioned `panel.draw_text()` right after it (e.g. to show
   the slider's live numeric value) visibly collided with the widget's own label text. Fixed by folding
   the live value INTO the label string itself (`f"cruise throttle {value*100:.0f}%"`) instead of a
   second draw call — one single text render, so there's nothing to collide with. The scroll slider
   does the same, but the range text it wants to show (`"X-Y of N"`) can only be computed *after*
   `slider()` returns a value for this tick, so it's built from the return of the *previous* tick's
   call (a plain script-level variable initialized once before the `while True:` loop and updated each
   iteration — the script is one continuous process, not re-invoked per tick, so this persists exactly
   like `self.wh_per_progress` persists across a controller's own loop iterations) — a one-tick lag,
   invisible since the panel repaints every tick regardless. **General rule: never place a second,
   independently-coordinated text element directly beside a named widget that already draws its own
   label** (`slider`, and likely `switch`/`button` too) — fold the value into that widget's own label
   parameter instead, even if it costs a tick of staleness.
3. `panel_2.py`'s narrow-mode (`wide == False`) per-vehicle row placed the location text
   (`draw_text(40, y+38, ...)`) almost directly under the role pill (`pill(40, y+22, ...)`) — the pill
   renders taller than the assumed 16px gap allows, so the two visibly overlapped. Fixed by moving the
   location text down to `y+46` and widening narrow-mode `row_height` from `54` to `64` to keep
   adequate clearance to the next row. **General rule: a `pill()` needs more vertical clearance below
   it than a plain text line does** — leave at least ~24px, not ~16px, before placing anything under one.

General layout rule for any new card: prefer anchoring right-side elements from the right edge
(`width - <fixed px>`) over a width fraction (`width * 0.86`) when the element has a roughly
fixed pixel footprint (a `switch`, a `button`, a short `pill`) — fractions of a 500px vs 1000px
canvas land in very different places, but a fixed-from-the-right offset stays a constant, safe
distance from the border at either size.

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
  (`publish_telemetry` ← `run_expedition_cycle` ← `run` ← the script's module scope) and real
  locals (`state='IDLE_AT_BASE'`, the live `RoverController` instance), then resumed cleanly leaving
  the script running.
  - **`attach` does not restart an already-running script** — it just starts observing it, so a
    breakpoint on a line that already executed (e.g. inside `__init__`, which only runs once at
    construction) will never fire again; pick a line the ongoing loop actually still reaches (e.g.
    inside `publish_telemetry()`, hit every cycle) instead of assuming a fresh run. A plain `launch`
    on an already-running script behaves the same way — it attaches rather than restarting, matching
    the external-ide README's own wording. A guessed `launch` argument (`"restart": True`) had no
    effect — `initialize`'s advertised capabilities don't list any restart support, so there's no
    confirmed way to force a genuine restart of a running script through this raw DAP surface; VS
    Code's own **Run Script in Game** command may do this via extension-specific plumbing outside
    `debug-adapter.cjs`'s plain interface, not reproduced here. Don't keep guessing undocumented
    fields against a live session — pick an always-reached line instead, as done here.

**Before starting any debug session (F5/`launch`/`attach`) or using **Run Script in Game**: ask the
user first, every time — never assume standing permission from a prior yes.** A debug session runs
against the live save with real effects (a script that spends credits, moves a vehicle, fires a
drill, etc. does so for real, not in a sandbox) — pausing at a breakpoint can also leave a machine
mid-action in a state the player didn't intend. Treat this the same as any other action with
real-world (real-save) side effects per this project's risk-awareness rules, not as a routine
read-only inspection step.
