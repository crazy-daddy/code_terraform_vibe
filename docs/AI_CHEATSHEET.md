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
| Power grid & brownout | `power.py` (`PowerGridManager` — generic, works for solar/oil/reactor/turbine grids, owned centrally by `panel_1.py`, one instance per grid, no election — see §1a-1); `solar.py` (`SolarController` — pure sun tracking, no grid supervision of its own any more) |
| Vehicles (Rover/Pioneer base) | `vehicle.py` (`VehicleController`, composes the mixins below) |
| &nbsp;&nbsp;↳ driving / stall recovery | `vehicle_navigation.py` |
| &nbsp;&nbsp;↳ battery accounting / trip budgeting / charging-station discovery | `vehicle_energy.py` |
| &nbsp;&nbsp;↳ fleet-wide target claims & hardware blacklist | `vehicle_claims.py` |
| &nbsp;&nbsp;↳ cargo offload into Inventory / Warehouse | `vehicle_cargo.py` |
| &nbsp;&nbsp;↳ sonar survey loop (POI discovery) | `vehicle_survey.py` |
| &nbsp;&nbsp;↳ mineral-site discovery & drill execution | `mining.py` — shared by Rover and Pioneer; see §2b |
| &nbsp;&nbsp;↳ in-flight mining yield reservation (non-exclusive, overmining guard) | `mining_reservations.py` — see §2b |
| Rover / Pioneer specializations | `rover.py`, `pioneer.py` — thin `VehicleController` subclasses; do **not** put shared vehicle logic here |
| Harvesting (grid survey/collection) | `harvesting.py` (`HarvesterController`) |
| Smelting | `smelter.py` |
| Production planning (demand-driven) | `production.py` |
| Supply Dock logistics | `supply_dock.py` |
| Biology (collector/lab/exchange/luminizer) | `bio.py` — outpost-aware (Warehouse-only outposts, no Inventory) throughout; see §2g |
| Outpost reagent stock-target scaffolding (Bio Lab resupply) | `outpost_reagents.py` — see §2g |
| Vehicle charging stations | `charging.py` |
| Fabrication | `fabricator.py` |
| Thermal Cap (steam capture, anti-overpressure) | `thermal_cap.py` |
| Steam Turbine (steam-to-grid power) | `steam_turbine.py` |
| Water Pump (route water to network Liquid Tanks) | `water_pump.py` — see §1d, simpler cousin of `thermal_cap.py` (no overpressure/relief concept) |
| Shared network-wide fluid-target discovery/blacklist/reconnect mechanism | `fluid_routing.py` — used by `thermal_cap.py`/`water_pump.py`/`steam_turbine.py`; see §1b |
| Storage management (Warehouse-aware sourcing/unloading, Inventory rebalancing) | `storage.py` — see §2c |
| Outpost ore-assignment & stock-target scaffolding (multi-outpost mining) | `outpost_mining.py` — see §2d |
| Data Archive persistence layer | `archive.py` |
| Wildcard pattern matching helpers | `patterns.py` |
| Per-script tick-cost profiling | `profiling.py` — see §1d |

Root executable scripts (`solar_1.py`, `rover_1.py`, `panel_1.py`, etc.) should stay thin
entrypoints that import and run a controller from `lib/` — they should not contain their own
copies of tier lists, thresholds, or budgeting formulas.

**No real stdlib — only a short, specific allowlist of "executable built-in modules" exists**
(`docs/guide/programming_language_reference.md`'s "Imports & Libraries" section is authoritative;
re-check it before reaching for any import, don't assume from ordinary Python). This has bitten
agent-written code repeatedly (e.g. `lib/production.py` reaching for `import math` for a plain
`ceil()`) — `ModuleNotFoundError`/`ImportError` at runtime, not a Pyright-catchable error locally,
since `pyrightconfig.json`'s stubs don't model the sandbox's restricted runtime import set. The
**only** executable modules are `random` (`randint`/`rand`/`random()`, also callable as bare global
helpers), `re` (regex — but see the `re.escape`-unavailable gap noted elsewhere in this doc),
`functools` (`reduce`, `total_ordering`), and `dataclasses` (`dataclass`, `field`) — nothing else,
and critically **none of these are real system libraries the way they are in ordinary Python**: this
is a small in-game reimplementation exposing just those names, not CPython's actual `random`/`re`/
`functools`/`dataclasses` modules, so don't assume any stdlib behavior beyond what the guide
documents. `math`, `sys`, `os`, `json`, `time`, `itertools`, `collections` (the concrete module, not
`collections.abc`), etc. do **not** exist at runtime. Separately, `typing`, `types`,
`collections.abc`, and `user_stubs` exist ONLY for editor/Pyright type annotations — their names are
erased at runtime (`typing.TYPE_CHECKING` is always `False` in-game), so they can be imported for
annotation purposes but never for executable helpers. **When you need something stdlib would give
you (ceiling division, etc.), write the few lines of plain arithmetic/Python by hand instead of
importing** — see `lib/production.py`'s `_ceil()` for the pattern this project now follows instead of
`math.ceil()`.

**Import depth limit**: the interpreter caps the nested import-resolution stack at
`maxImportDepth = 256` (`interpreter.maxImportDepth`, confirmed from the decompiled simworker —
see `internals/` [gitignored, not authoritative game docs]), raising a `RecursionError` /
`error.import_depth` if exceeded. Our current `lib/` chain (entrypoint → `vehicle.py` → its
mixins, at most 2-3 levels deep) is nowhere close, so this is purely a "if you ever see
`RecursionError: maximum import depth exceeded`, look for a real import cycle" note, not a design
constraint to actively budget against.

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
- **Tier 2 (`smelter_*`/`fabricator_*`) is soft-shed — `SOFT_SHED_PATTERNS`, never actually
  powered off.** A Smelter/Fabricator only draws its recipe's `power_draw` while a craft is
  actively running — idle draw is already 0 W (`lib/smelter.py`'s `SmelterController` docstring)
  — so cutting its breaker saves nothing beyond what simply not starting new work already saves,
  while also needing external intervention to power it back on and restart its script. Soft-shed instead: Power Guard still
  adds/removes the machine from `power.shedded` (so the signal exists and recovery timing is
  unchanged), but never calls `set_powered()` on it. `SmelterController.is_shedded()` /
  `FabricatorController.is_shedded()` check that same list each `step()` and, if shedded, return
  right after draining output/ejecting excess — never starting or topping up production, but never
  interrupting an already-running craft either, so draw winds down to 0 W on its own. Every other
  Tier 1 pattern (`heater_*`, `pressure_*`, `bio_*`, etc.) is still hard-shed via `set_powered()`,
  since those draw power continuously regardless of whether they're "producing" anything.
  **No cooperative auto-wake exists on purpose** — `VehicleCargoMixin.wake_smelter()` and
  `FabricatorController.wake_smelter()` (which used to power on / `run_control.start()` the
  Smelter on fresh ore delivery or a missing-input stall) were removed entirely: if the operator
  stopped or powered down the Smelter themselves, nothing should override that just because a
  delivery arrived. The Smelter's own `step()` loop already polls for new ore on its normal cycle
  whenever it IS running.
- **Night duration is a fixed constant, not calibrated.** `NIGHT_DURATION_HOURS` (and
  `SUNRISE_HOUR`/`SUNSET_HOUR`) are computed once at module load from the decompiled simworker's
  exact day-cycle schedule (`DAY_CYCLE_DURATION_SECONDS = 600`, `DAYLIGHT_FRACTIONS` — `dawn_start`
  through `dusk_end` as fractions of a full day, multiplied by 24 to land on
  `clock.elapsed_game_hours()`'s scale): sunrise at `0.25 * 24 = 6.0h`, sunset at
  `0.83 * 24 = 19.92h`, giving `NIGHT_DURATION_HOURS = 24 - 19.92 + 6.0 = 10.08` exactly, every
  night. This replaced the old empirically-calibrated `power.night_duration` archive value
  (measured `sunset_hour -> sunrise` gap, EMA-smoothed in `handle_sunrise()`) — the schedule never
  actually varies day to day, so there was nothing to calibrate; the old approach was only ever
  wrong immediately after a script restart while it re-converged toward this same constant.
  `power.night_wh`/`power.night_wh:<grid_anchor>` (historical overnight Wh, used to blend with the
  live instantaneous draw when sizing `manage_night_loads()`'s shed threshold) is unrelated and
  still calibrated live — only the *duration* was ever exactly knowable in advance.
- `ArchiveCleaner.clean_power_grid_state()` (`lib/archive_cleaner.py`) retires `power.night_duration`
  and the dead legacy key `power.last_night_wh` outright, and purges `power.shedded:<anchor>` /
  `power.night_wh:<anchor>` entries whose grid anchor no longer exists (e.g. two grids merged via a
  new power line, orphaning one of the two old per-grid keys) — skipped entirely if grid
  discovery itself comes back empty, same caution as `clean_telemetry()`'s active-vehicle check. This
  is a manual-button-triggered sweep (see §7); `PowerGridManager.release_all()` (§1a-1) is the
  automatic, immediate version of the same "a grid anchor just disappeared" cleanup for whatever it
  still had shed, so a grid merge doesn't leave something stuck shed for however long until the
  player next presses the button.

### 1a-1. Centralized Grid Ownership (`panel_1.py`, no Master/Follower election)

`PowerGridManager` used to be instantiated once **per solar generator** (`lib/solar.py`'s
`SolarController`), with every instance independently re-electing the same single Master every tick
(`check_master()`: sort every solar id on this generator's grid by numeric suffix, lowest one
currently `run_control.is_running()` wins) purely so they could all agree on which ONE of them should
actually call `supervise_grid()`. That election is gone — `panel_1.py`'s AUTOMATION section (§7) is a
single always-running process, so it just owns grid supervision directly, one `PowerGridManager`
instance per grid, with no election needed at all.

- **`PowerGridManager.__init__(self, grid, clock=None, power=None)`** — no `machine` param any more
  (it only ever existed so a specific generator could identify itself to `get_grid()`, which is also
  gone — `panel_1.py` already has each grid from iterating `power_control.grids()` directly, once per
  tick). `grid` (the initial snapshot) is required and binds `self.grid_anchor` immediately at
  construction, rather than leaving it `None` until the first `supervise_grid()` call sets it as a
  side effect — identity is fixed for this manager's lifetime, only the per-call snapshot (stored/
  capacity/consumed) genuinely needs to be fresh every call.
- **`resolve_pattern_machines()`'s outpost-buildings fallback removed** (it read
  `self.machine.outpost`, impossible without a bound machine) — the fallback chain narrows to the
  grid snapshot's own `.machine_ids`/`.members` (primary, always populated for a real grid) → the
  numbered-guess `get_component(f"{prefix}{i}")` last resort. Deliberate narrowing, not an oversight.
- **`release_all()`** (new) — called when a grid's `anchor_id` stops being reported by
  `power_control.grids()` at all (two grids merged into one via a new power line). Since `panel_1.py`
  keeps one manager alive per anchor across ticks (to preserve its day/night/shed state), a vanished
  anchor's manager — and anything still in its `shedded_machines` — would otherwise just be dropped
  and forgotten, permanently stranding a shed Smelter/Fabricator/Tier-1 machine, since the *merged*
  grid's own manager starts fresh with an empty `shedded_machines` and has no way to know about it.
  Restores anything still tracked (guarded exactly like `manage_day_recovery()` already does) and
  clears the per-anchor `power.shedded:<anchor>` mirror.
- **Battery-less grids are skipped, not mismanaged.** `supervise_grid()` now runs against *every* grid
  `power_control.grids()` reports, not just ones a solar generator happened to be on — a strict
  improvement for battery-backed grids, but it means a grid powered entirely by Steam Turbine with no
  Battery built now reaches this code for the first time, and `battery_pct = stored_wh / capacity_wh`
  would divide by a real zero there (this genuinely never came up before: a grid only got supervised
  if a `SolarController` existed on it, and solar always implies a battery for night storage). Guard:
  `if capacity_wh <= 0: return` near the top of `supervise_grid()`, before any day/night or shedding
  logic runs. A generation-vs-consumption supervision strategy for battery-less grids is a real gap,
  just out of scope for this pass — flagged as a follow-up, not silently guessed at.
- **`lib/solar.py`'s `SolarController` is now pure sun-tracking** — `track_sun()`/`step()`/`run()`
  only, no `PowerGridManager`, no `is_master`, no `check_master()`/`update_role()`, no `power`/
  `run_ctrl` constructor params. **Hard dependency**: Solar Grid brownout supervision only happens
  while `panel_1.py` is running — see `legacy/README.md` for the pre-Control-Room fallback snapshot
  (a save that hasn't unlocked `research_custom_panels` yet has no panel scripts at all, so this
  centralization doesn't help it; that's what the legacy zip is for).
- **`lib/smelter.py`'s `SmelterController` lost the mirror-image Leader election** the same way —
  `check_leader()`/`update_role()`/`is_leader`/`run_ctrl` all removed. The "inventory manager" sweep
  (`storage.rebalance_inventory_to_warehouses()`) that used to run Leader-only now runs once, directly,
  from `panel_1.py`'s AUTOMATION section instead — same hard dependency as Solar Grid supervision.

### 1b. Steam Power Loop: Thermal Cap → (Gas Tank) → Steam Turbine

Thermal Cap (`lib/thermal_cap.py` `ThermalCapController`) and Steam Turbine
(`lib/steam_turbine.py` `SteamTurbineController`) are independent scripts — each only manages its
own throttle, no shared coordination needed. A Gas Tank sitting between them is purely passive
(no script; see `docs/components/gas_tank.md`) and just smooths supply gaps.

- **Pipe wiring**: a Gas Tank has no script of its own, so nothing ever calls `connect()` on *its*
  side of a FluidPort — each neighbor must declare its own side instead. **A Thermal Cap has no
  `.outpost` property at all** (`docs/components/thermal_cap.md` lists none — it's built directly on
  a thermal vent out in the field, not necessarily inside a founded outpost, unlike Gas Tank/Steam
  Turbine which both have one), so candidates can't be scoped to "this building's outpost"; all
  three controllers instead call the shared `lib/fluid_routing.py` `discover_network_buildings(type_ids,
  resolve=True)` (Cap/Pump use the default, resolved objects; Turbine passes `resolve=False` for
  plain ids), which walks every outpost (`outpost_network.outposts()` → `outpost.buildings(type_id)`)
  to gather candidates network-wide.
  - **`connect()`'s `"ok"` status does NOT mean the target is physically reachable** — per
    `docs/guide/infrastructure_and_pipes.md`, a remote pairing needs a *completed* Gas Pipe route,
    which `connect()` never checks; `"ok"` only means the pairing was logically accepted. The one
    live signal of an actually-broken route is `is_stalled()` (steam/throttle ready, nothing
    transferred) — all three controllers blacklist a target that reports this and pick a different
    candidate, rather than sitting stalled on the same unreachable target forever. Each blacklist
    entry expires **individually** — shared machinery, `lib/fluid_routing.py`'s `PerEntryBlacklist`
    (Cap/Pump reach it via `self._router.blacklist`, Turbine via `self.blacklist`), maps
    `id -> the simulation tick it was blacklisted at` (`.is_blacklisted(id, curr_tick)`, real
    `clock.tick()`, not step() calls), not a plain set with one shared "clear everything at once"
    timer — `RESCAN_INTERVAL_TICKS` (300 Cap-ticks / 150 Turbine-ticks, passed in per-controller as
    a constructor/constructor-forwarded argument) is each entry's own expiry
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
      `_fill_pct_of_building()` (since folded into `lib/fluid_routing.py`'s `fill_pct_of()`):
      `discover_network_buildings()` used to append the raw `BuildingRef` from
      `outpost.buildings(type_id)` directly. Per `docs/components/outpost.md`, that's a
      lightweight *snapshot* carrying only `.id`/`.name`/`.type_id`/`.outpost`/`.powered`/`.position` —
      **not** the type-specific live methods (`fill_pct()`, etc.) that only exist on the full resolved
      component (`get_component(ref.id)`). So `fill_pct_of()`'s `hasattr(building, "fill_pct")` check
      failed for *every* tank, always hitting the "unreadable, treat as 1.0" fallback — degenerating
      `sorted(tanks, key=fill_pct_of)` into a no-op tie broken purely by discovery order, **and**
      defeating the fast path too (a healthy current tank also reads as `1.0 >=
      GAS_TANK_REBALANCE_FILL_FRACTION`, so it never short-circuits, forcing a full rescan every
      single step). The net effect: selection became "skip current, take the next one in a fixed
      discovery-order list" every call — a stable alternation between whichever two candidates happen
      to sit adjacent to each other in that order, never advancing to a third. This is exactly the
      failure mode the per-entry blacklist fix above couldn't reach, since it operates one layer up
      (which candidates are *eligible*), not on why selection *among* eligible candidates was broken.
      Fixed by resolving each `BuildingRef` via `get_component(ref.id) or building` inside
      `discover_network_buildings()` itself (now `lib/fluid_routing.py`'s shared
      `discover_network_buildings(type_ids, resolve=True)`, used by all three controllers) — same
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
    - **Candidate ranking is same-outpost-first, not discovery order** —
      `fluid_routing.discover_network_buildings(type_id, resolve=False)` returns `(id, outpost_id)`
      pairs (not bare ids), and `_discover_candidates_cached()` sorts each of the two groups
      (gas_tank ids, then thermal_cap ids) so any candidate sharing this Turbine's own `outpost.id`
      comes before every other-outpost one. Found from a real case: turbine_5/
      turbine_6 initially connecting to `gas_tank_2` at a *different* outpost with no completed pipe
      route to either, instead of trying their own outpost's tank first — `connect()`'s `"ok"` status
      doesn't catch this (see above), so the wrong pick still burns a full
      `STALL_STREAK_BLACKLIST_THRESHOLD`-tick stall window (and, once blacklisted, an
      `RESCAN_INTERVAL_TICKS` window before it's even retryable) before falling through to a reachable
      candidate that was available the whole time. This is a ranking preference, not a same-outpost
      *restriction* — a genuinely reachable cross-outpost tank (real completed Gas Pipe route) is
      still tried and still succeeds, just after same-outpost candidates are exhausted.
  - **Discovery cost**: `fluid_routing.discover_network_buildings()` walks every outpost's
    `buildings(type_id)` — real work, and (per profiling — see §1d) the actual cost driver of every
    controller's `step()`. All three are cheap once settled specifically because the network walk
    itself is skipped, not just deferred, while a connection is healthy:
    - **Cap/Pump**: the "keep current tank" decision needs only one `fill_pct()` read on the id
      already connected — `FluidOutputRouter.ensure_connection()` checks that *before* touching
      discovery at all, so the walk never runs in the steady-state case.
    - **Turbine**: `ensure_input_connection()` returns immediately whenever `connected_input` is
      True and `stall_streak < STALL_STREAK_BLACKLIST_THRESHOLD`, for the same reason.
    - All three still need discovery sometimes (bootstrap, current target blacklisted/full, every
      candidate blacklisted at once) — for those cases each controller (via `FluidOutputRouter` for
      Cap/Pump, directly for Turbine) caches the discovered building list for
      `DISCOVERY_CACHE_INTERVAL_STEPS=20` `step()` calls rather than re-walking on every one of
      several reselection attempts in a short window. This is a ceiling, not the primary mechanism —
      see the fast paths above for why the walk is rare in practice.
  - **The real per-step cost was elsewhere, and profiling (§1d) is what found it**: with the walk
    itself gone, Thermal Cap's `step()` still cost 2-3 sim ticks every single call (Steam Turbine's
    cost ~0, matching its zero-external-lookup fast path) — no periodic spike at 20 or 300 steps,
    ruling discovery back out entirely. The actual culprit: the Cap's fast path still resolved its
    *currently connected* tank via a fresh `get_component(current_id)` round trip every step just to
    read `fill_pct()`, since the id alone (from the port) isn't the object `outpost.buildings()` had
    already handed discovery. `discover_network_buildings(resolve=True)` now returns the live building
    objects themselves, and `FluidOutputRouter._target_lookup` (an id → object dict, populated from
    every discovery batch and never wholesale-cleared — a building's identity is stable, only the
    candidate *list* goes stale) makes `_resolve_target(id)` a plain dict read on every call after the
    first time a given id is seen. Verified via a stub test asserting zero `get_component()` calls
    across 20 consecutive healthy steps (previously: one per step). This is the general pattern for
    any future "read a possibly-external object by remembered id every step" cost: keep the object
    reference from whatever discovery/connect call first produced it, rather than re-resolving by id.
  - **Third pass — still 2 sim ticks/step after the above.** Comparing structure against Turbine's
    equivalent (which reads ~0) found the remaining asymmetry: `ensure_output_connection()` still
    called a port method **unconditionally on every single call**, whereas Turbine's healthy fast
    path calls no port method at all — it trusts its own `self.connected_input` boolean and only ever
    queries the port (`connected_id()`) on the rare blacklist branch. Fixed the same way:
    `FluidOutputRouter` now tracks `self._connected_id` locally, updated only by its own `connect()`
    calls and blacklist decisions (nothing else ever repoints `steam_out`/`water_out` — a Gas/Liquid
    Tank is passive, no other script touches this port), so the port is queried exactly **once,
    ever** — a one-time sync on first `ensure_connection()` call so a script reload recovers an
    already-working connection instead of assuming a fresh start — never again after that. **That
    one-time sync originally called `port.connected_to()` (the renameable display name) while every
    other lookup keys on the stable id via `connected_id()`/`.id` — a latent bug (a renamed Gas/Liquid
    Tank would desync the cache right after a reload) fixed alongside the Cap/Pump/Turbine unification
    into `lib/fluid_routing.py`; the one-time sync now calls `connected_id()` like everything else.**
    Verified via a stub test asserting the port's id method is called exactly once total across
    bootstrap + reselect + 20 healthy steps (previously: once per step). If the archived tick-delta
    for `thermal_cap_*`/`water_pump_*` still doesn't read ~0 after this, the next place to look is
    whichever `self.cap.*`/`self.pump.*` method call in `step()` itself isn't mirrored by an
    equivalent Turbine call, since everything `ensure_connection()` itself does is now either a
    boolean/dict read or fully gated.
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
  shedding itself — that's `panel_1.py`'s AUTOMATION section's job now, centrally, for every grid
  (§1a-1), not any individual generator's.

### 1c. Water Pump: Liquid Tank Routing (`lib/water_pump.py` `WaterPumpController`)

Shares §1b's Thermal Cap → Gas Tank connection/load-balancing/blacklist machinery exactly — both
build a `lib/fluid_routing.py` `FluidOutputRouter` (Pump's own `LIQUID_TANK_TYPE_IDS`,
`LIQUID_TANK_REBALANCE_FILL_FRACTION`, `CONNECTION_GRACE_TICKS`, `RESCAN_INTERVAL_TICKS`,
`DISCOVERY_CACHE_INTERVAL_STEPS` constants feed the same shared class Cap uses), not just similar
code — but deliberately simpler in `step()` — a Water Pump has **no internal buffer to
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

### 1e. Bio Luminizer Lamp-Mix Solve (`lib/bio.py` `BioLuminizerController`, `_solve_3x3()`)

Tints a coastal fragment's glow to a `BioOrder.target_glow` via `docs/components/bio_luminizer.md`'s
three lamps: `self.lamp_signature("red"/"green"/"blue")` each give a fixed per-unit `[r,g,b]`
impurity, so setting lamp brightnesses `(r, g, b)` (each a whole number 0-40) produces
`glow = base + r*red_sig + g*green_sig + b*blue_sig`, where `base = self.glow()` read with all lamps
at 0 (the chamber's own starting color). Solving for `(r, g, b)` given a `target` is a 3×3 linear
system, `M @ [r,g,b] = target - base` where `M`'s columns are `red_sig`/`green_sig`/`blue_sig` — no
numpy in this sandboxed environment, so `_solve_3x3()` inverts it via a plain-Python closed-form
Cramer's rule. The result is rounded to the nearest integer and clamped to `[0, 40]`, then verified
against a live `self.glow()` read; if rounding landed one off, a bounded ±1-per-channel neighborhood
search (≤27 `set_lamps()`/`glow()` round-trips) finds the exact integer match rather than either
trusting the rounded solve blindly or brute-forcing the full 41³ space against the live game. A
fragment with no active coastal order requiring it is passed through unchanged via `self.discard()`
instead of being tinted.

**`active_order()` is shared, mutable, single-slot state — never use it to look up "which order needs
this fragment."** Found live: multiple differently-glowing Luminous `sd_wing_membrane` stacks piling
up unused in Warehouses. Root cause: `BioExchangeController.sweep_and_deliver()` reassigns
`active_order` constantly, to whatever order it's currently delivering ANY matching sample to
(coastal or not) as part of its own aggressive multi-order sweep — it's delivery-routing state, not a
stable "current coastal target" signal. The Luminizer used to read `exchange.active_order()` directly
for `target_glow`, so every time the Exchange's sweep briefly switched to deliver some unrelated
order, the Luminizer tinted toward *that* order's target instead. Fixed with `_find_coastal_order(exchange,
fragment_id=None)`: scans `exchange.orders()` directly for an incomplete, local, `target_glow`-bearing
order (matching `fragment_id` if given), completely independent of `active_order()`.

(A live diagnostic run initially seemed to confirm this theory, but the actual mistinted-looking stock
turned out to be something else entirely — see the next two notes.)

**`set_order()`/`clear_order()`/`deliver()` are `*(self only)*` hardware calls — a script can never
drive a sibling machine, only read its state.** Confirmed live: calling `exchange.set_order(order.id)`
from the Luminizer's own script raised `PermissionError: Cannot call set_order() on bio_exchange_4
remotely`. This means `matches_order()` is unusable from any script other than the Exchange's own —
there's no way to force which order it checks against, since setting that order is exactly the
self-only call that fails. Any *other* controller that needs "does this stack match a specific
order's requirement" has to compare the raw property directly instead: for coastal orders, that's
`list(stack.properties.get("glow", [])) == list(order.target_glow)` — no hardware call needed at all,
since `target_glow` and a stack's `properties` are both plain reads. `_glow_matching_count(item_id,
outpost, target_glow)` in `lib/bio.py` is this direct comparison, used by both the Luminizer (below)
and the Collector's raw-backlog throttle (below). `BioExchangeController.sweep_and_deliver()`'s own use
of `self.machine.matches_order()`/`set_order()` is fine and unchanged — it's calling them on `self`,
the machine its own script is attached to, which is exactly what's allowed.

**Don't tint more than the order still needs.** `_load_next_sample()` checks `needed - delivered -
in_transit` against `_glow_matching_count()` (units already sitting in local storage with the exact
target glow) before loading another raw sample — previously it loaded+tinted one every cycle the
chamber was empty, with no cap.

**The mistinted-looking Warehouse stock was actually just raw, never-tinted specimens — not a
Luminizer bug at all.** `bio_luminizer_1.log` showed every real infuse exactly matching a live order
target (`[202,192,182]` = `bio_order_50`, `[168,158,138]` = `bio_order_48`, 8 total). The stray
`sd_wing_membrane` stacks (glow values 9-29, nowhere near any coastal order's 62-202 range across the
entire save) were raw specimens still waiting for the Luminizer — every raw sample carries its own
naturally-varying starting glow (same `ChamberSample.glow` concept as a tinted one), so `matches_order()`
correctly said `False` for all of them. The real problem was a Collector/Lab extraction rate outpacing
the Luminizer's throughput (~10-70s per infuse), and since raw specimens don't stack any better than
mistinted ones do, the backlog exhausted Warehouse material slots and deadlocked the whole pipeline
(nothing could drain anywhere, so the Lab couldn't extract, so the Collector couldn't hand off, etc).
See §1f for the throttle that keeps this from recurring.

**Even after that, `_find_coastal_order()` could still deadlock the machine outright — not just
inefficiently.** Found live: with two coastal orders both incomplete, it always returned whichever
sorted first in `exchange.orders()`, regardless of whether any material for it actually existed yet.
If the *other* order's fragment happened to already be staged in `self.machine.input` (latched to
that one item id until `load()`/`flush()` clears it, per `docs/components/bio_luminizer.md`), the
Luminizer would fixate on the wrong order forever: it can't `load()` the staged item because the
selected order doesn't need it, and it can't `take_item()` the order's own fragment because the
input is already latched to something else. Fixed two ways: (1) `_find_coastal_order(fragment_id=None)`
now prefers a candidate order with `local_stock(fragment_id) > 0` for one of its requirements over
one needing fresh collection; (2) `_load_next_sample()` checks `self.machine.input.stacks()` FIRST,
before consulting order priority at all — if something's already staged, it looks up an order for
*that specific fragment* and loads it (or, if no current order needs it any more, ejects it back to
storage via `best_unload_target()` rather than leaving the input stuck on dead material forever).

**A staged sample can itself already be finished, not just raw.** Debugging live turned up the input
holding two property-distinct `sd_wing_membrane` stacks simultaneously — one at `[202,192,182]`
(`bio_order_50`'s exact target) and nine at `[168,158,138]` (`bio_order_48`'s exact target): both
already correctly tinted by an earlier successful `infuse()`, just never drained out before something
else got staged alongside them. Calling `self.machine.load(fragment_id)` with no `properties` was
ambiguous across the two variants and failed `"not_in_input"`; worse, even loading one on purpose
would be pointless (and, per live report, leaves the Luminizer unable to do anything useful with it —
it's already at target, there's nothing left to solve for) since it doesn't need tinting at all, only
delivering. `_glow_matching_count()` never catches this either, since it only scans Warehouses/
Inventory (`_local_sources()`), never a machine's own ports — so this stock was invisible to every
demand/overproduction calculation while stuck there. Fixed by checking every staged stack
individually: `_order_matching_glow(exchange, fragment_id, glow)` finds a live order whose
`target_glow` exactly equals the stack's own glow; if one exists, the stack is already finished and
gets **ejected** (with its exact `properties`, not reloaded) so the Exchange can find and deliver it.
Only a stack that matches no current order's target is treated as raw and actually loaded (also with
exact `properties`, avoiding the same ambiguity). The "pull fresh raw material" path
(`_find_raw_stack()`) applies the identical exact-glow-exclusion when picking a storage stack to pull
in, replacing the property-blind `storage.take_item()` there — otherwise it could grab an
already-tinted unit waiting for delivery instead of genuinely raw stock, the same failure mode from
the other direction. **The Luminizer should never pick up an already-tinted sample at all**, in either
the "what's already staged" or "what to pull from storage" path — both now enforce this.

### 1f. Raw-Specimen Backlog Throttle → Structural Idle-Gate (`lib/bio.py`, `BioCollectorController`/`BioLabController`/`BioLuminizerController`)

**Note:** the numeric throttle described first below (`RAW_BACKLOG_CAP_PER_FRAGMENT`,
`FOCUS_ORDER_COUNT`, `_glow_throttled()`) was later replaced by a structural fix — see the "Still ~6
seconds..." entry partway through this section for what actually ships today
(`_luminizer_is_idle()` + `MAX_LOCAL_GLOW_ARTIFACTS`). The numeric-throttle history is kept below
because it's real "why we tried X and it wasn't enough" context, not because any of that code still
exists.

Caps how far `BioCollectorController` may collect a glow-requiring (coastal) fragment ahead of what
the Luminizer has actually tinted, so raw specimens don't pile up and exhaust Warehouse material
slots the way described in §1e. `_glow_throttled(exchange, fragment_id, outpost, my_biome)` — called
from both of the Collector's demand-check branches (Signal Bus broadcast and the direct-exchange
fallback) — finds every incomplete, local order requiring `fragment_id`; if none of them carry a
`target_glow` (a plain fragment), throttling never applies at all, since a plain sample stacks
normally and has no Luminizer bottleneck. Otherwise `_raw_backlog_count()` computes `local_stock() -
sum(_glow_matching_count() per distinct target_glow)` — total stock minus whatever's already
correctly tinted for one of those orders — and the Collector stops harvesting once that raw count
reaches `RAW_BACKLOG_CAP_PER_FRAGMENT` (4 — raised from an initial 2, see below). Entirely read-only (`orders()`, `target_glow`,
`stacks()`) — no `*(self only)*` hardware calls, so it's safe to call from the Collector's own script
about a sibling Exchange.

Note this only prevents the backlog from *recurring* — it doesn't retroactively free Warehouse slots
already exhausted by a pre-existing pile of raw specimens. Clearing an existing deadlock still needs
a one-time manual sell/eject in-game; there's no automated way to safely discard player inventory.

**Per-fragment capping alone wasn't tight enough — the real fix is one-order-at-a-time focus.** Found
live via the glow diagnostic: with ~8 simultaneously-incomplete coastal orders, each needing 2-4
different fragments, `RAW_BACKLOG_CAP_PER_FRAGMENT` capped each individual TYPE to 2 but did nothing
to limit how many DISTINCT types were in flight at once — the Collector was opportunistically
gathering for every incomplete coastal order in parallel (`gm_folded_wing`, `vc_mandible_claw`,
`hs_wing_membrane`, `ma_cuticle_molt`, `hc_shell_whorl`, `gw_caudal_fin`, `sd_wing_membrane`, all
raw, all non-stacking, all at once), so the totals still blew past available Warehouse slots even
with every individual type "capped." Fixed with `_focus_coastal_order(exchange, outpost, my_biome,
fragment_id=None)`: the ONE order to concentrate on right now (same "prefer stock we already have"
preference as before), shared by both `BioCollectorController` (`_glow_throttled()` now throttles a
fragment completely — not just at the raw cap — if it doesn't belong to the current focus order) and
`BioLuminizerController` (`_find_coastal_order()` is now a thin wrapper delegating here). Both
controllers concentrating on the same order at the same time means the Collector no longer gathers
raw material for an order the Luminizer isn't even working on yet — collection breadth is now bounded
by one order's requirement list instead of every open coastal order's combined list. As focus
naturally rotates to the next order (preferring ones with existing stock, i.e. exactly the leftover
backlog from before this fix), previously-scattered raw specimens for other orders get worked off
over time rather than needing a manual clear — but this is still not instant, and a warehouse already
maxed out from before this fix still needs the same one-time manual sell/eject to actually unstick.

**A single-order focus was too narrow and could starve the Collector entirely.** Found live: after a
full manual Warehouse clear, every bio script went silent (zero log activity) with `cargo` confirmed
empty on the Collector — not a deadlock, just nothing left it was allowed to harvest. If the one focus
order's specific 2-4 fragments aren't cataloged/discoverable anywhere nearby yet, `_glow_throttled()`
blocked every OTHER coastal order's fragments too, even ones sitting right there ready to harvest.
Fixed with `FOCUS_ORDER_COUNT = 3` and `_focus_coastal_orders()` (plural): the Collector now
concentrates on up to 3 coastal orders at once (same "existing stock first" ranking), giving it real
alternatives while still keeping total distinct raw fragment types far below "every incomplete
coastal order at once". `BioLuminizerController` still uses the singular `_focus_coastal_order()` for
its own one-at-a-time tinting — only the Collector's gathering breadth needed loosening.

**`comms.latest(channel)` returns the raw broadcast value directly, `-> Any` — never a status-wrapped
object.** A genuinely pre-existing bug, not introduced by any of the above: `BioCollectorController`
checked `b_res.status == "ok" and b_res.broadcast`, but `.latest()` (unlike `.receive()`, which
correctly returns a `ReceiveResult` with `.status`/`.packet`) just hands back whatever was passed to
`broadcast()` — a plain dict here — or `None` if nothing's been broadcast yet. `b_res.status` on a
dict raised `AttributeError` every single call, silently swallowed by the surrounding `except
Exception: pass`, so `demands` always stayed `None` and the Collector permanently fell back to its
`elif exchange:` branch — deriving demand from a SINGLE `exchange.active_order()` instead of the
properly-aggregated multi-order broadcast `broadcast_demands()` already computes. Since
`active_order()` is the same volatile, sweep-reassigned pointer discussed throughout this section,
that fallback's demand set could be for an order outside `_focus_coastal_orders()`'s top-3 entirely,
throttling every fragment in it at once and looking identical to a fresh deadlock. Fixed: check
`isinstance(broadcast, dict)` and read `.get("local_demands", {})` directly. With this fixed, the
broadcast path should be the one actually running now, making the `elif exchange:` fallback rare.

**`RAW_BACKLOG_CAP_PER_FRAGMENT = 2` over-corrected into full lockstep.** With the Collector's own
one-slot cargo and the Lab's one-specimen chamber already forcing some serialization (both hardware,
unrelated to this constant), a cap of 2 left almost no room for the Collector to work ahead of the
Luminizer — reported live as "harvest one, wait for Lab+Luminizer+Exchange to fully finish it, only
then harvest the next." Raised to 4: real pipelining slack, still far below the original
unbounded-backlog problem this constant exists to prevent (see above).

**Raising the cap "didn't do anything" — the real bottleneck was `exchange.orders()` being re-fetched
per fragment, not the cap value.** Measured live: evaluating `BioCollectorController.step()`'s
`demands.items()` loop (~20-30 glow fragments across all incomplete coastal orders) took **~20
seconds**. Every fragment called `_glow_throttled()`, which called `exchange.orders()` itself AND
called `_focus_coastal_orders()`, which called `exchange.orders()` again — two ~80-order fetches per
fragment, 40-60+ redundant fetches per single `step()` cycle, dwarfing any effect of the backlog cap.
Fixed by threading an already-fetched `orders` list through every order-scanning helper instead of
each one fetching its own copy: `_focus_coastal_order()`, `_focus_coastal_orders()`, and
`_glow_throttled()` now all take `orders` as a parameter; `BioCollectorController.step()` and
`BioLuminizerController.step()` each fetch `exchange.orders()` exactly **once** per cycle and pass it
down through every helper that needs it (`_find_coastal_order()`, `_order_matching_glow()`,
`_find_raw_stack()`, `_load_next_sample()`, `_active_target_for()` all take `orders` now instead of
`exchange`). The Luminizer had the identical anti-pattern (`_order_matching_glow()` re-fetching
`orders()` once per staged/storage stack examined) even though it hadn't been reported yet — fixed
the same way for consistency, since it would have hit the same wall as soon as more than a couple of
stacks needed checking in one cycle.

**Still ~8 seconds after caching `orders()` — the second bottleneck was re-walking local storage.**
Caching `orders()` cut the cycle from ~20s to ~8s, not further, because every fragment/order check
was still independently re-walking every Warehouse + home Inventory (`_local_sources(outpost)` →
`.stacks()` per building) to compute stock counts and glow-matching counts — `local_stock()` and the
old `_glow_matching_count()` each did this from scratch, once per fragment. Fixed the same way as the
`orders()` fetch: one full storage walk per `step()` cycle via `_local_stock_snapshot(outpost)`,
returning `(totals, by_glow)` dicts (`{item_id: count}` and `{(item_id, glow_tuple): count}`), read
via `_snapshot_stock(snapshot, item_id)` / `_snapshot_glow_count(snapshot, item_id, target_glow)`.
`_raw_backlog_count()`, `_focus_coastal_order()`, `_focus_coastal_orders()`, `_glow_throttled()`,
`_fragment_remaining()` all take `snapshot` now instead of re-deriving stock from `outpost` per call;
`BioCollectorController.step()` and `BioLuminizerController.step()` each build the snapshot exactly
**once** per cycle, same pattern as the `orders` list. `_find_raw_stack()` is the one exception — it
legitimately needs live `ItemStack` objects (not just counts) to actually load a specific stack, so it
still does its own single storage walk, but only once per Luminizer `step()`, not per-fragment.

**Still ~6 seconds after caching the storage walk too — the numeric per-fragment throttle itself was
the remaining cost, and it was solving a problem with a much simpler structural fix.** Every fragment
in `demands.items()` (~20-30 of them) still ran its own `_glow_throttled()` check even after both
caching fixes above. But `RAW_BACKLOG_CAP_PER_FRAGMENT`/`FOCUS_ORDER_COUNT`/`_glow_throttled()`/
`_raw_backlog_count()`/`_focus_coastal_orders()` (plural) were only ever needed because the Collector
and Lab kept harvesting/extracting raw specimens faster than the Luminizer could tint them one at a
time. Every stage already has single-slot hardware (`Collector.cargo`, `Lab.specimen`/`.output`,
`Luminizer.chamber`/`.input`/`.output`) — if the **Lab** simply refuses to pull its next specimen from
the Collector, and refuses to drain its own extracted output into the Warehouse, until the
**Luminizer is fully idle** (chamber empty, input empty, output empty, `_luminizer_is_idle()`), then
at most one raw specimen is ever in flight ahead of the Luminizer at a time. No Warehouse pileup is
structurally possible regardless of how broadly the Collector searches for "needed" fragments, so the
numeric per-fragment caps and per-order focus list (all removed) become unnecessary. All of
`RAW_BACKLOG_CAP_PER_FRAGMENT`, `_raw_backlog_count()`, `FOCUS_ORDER_COUNT`, `_focus_coastal_orders()`
(plural), and `_glow_throttled()` were deleted; the singular `_focus_coastal_order()` (shared "current
order" selector for both Collector preference and Luminizer targeting), `_local_stock_snapshot()`,
`_snapshot_stock()`, and `_snapshot_glow_count()` stay — they're still useful for demand-netting and
order preference, and were already O(1)-per-cycle, not part of the perf problem.

`BioLabController._luminizer_is_idle(luminizer)`-gated `step()`: the initial output drain and the
collector-pull (`specimen is None` branch) both skip entirely when the local Luminizer isn't idle;
the post-extract drain does the same. Analyze/extract of whatever's already in the Lab's own chamber
keep running unconditionally either way — they're already self-limiting via the game's own
`"output_full"` rejection if the Lab's output is still occupied, so there was no need to gate those
too. `BioCollectorController.step()` correspondingly dropped every `_glow_throttled()` call — it
still nets demand against `_snapshot_stock()` (unaffected), and now additionally prefers the shared
`_focus_coastal_order()`'s own fragments over other incomplete orders' when picking a cataloged
location to harvest (falling back to any other needed fragment if the preferred order's aren't
discoverable nearby), instead of hard-blocking non-focus fragments outright.

**No busy-polling `sleep()` for the gate either — the Luminizer broadcasts a heartbeat every cycle.**
`BioLuminizerController._notify_heartbeat()` fires `comms.broadcast("luminizer_heartbeat", ...)`
unconditionally at the top of every `step()`, regardless of what that cycle did.
`BioLabController._wait_for_luminizer()` calls `comms.wait_broadcast("luminizer_heartbeat")` instead
of `sleep(0.5)` whenever it's blocked on `_luminizer_is_idle()` being `False` with nothing else useful
to do (no specimen to pull with, or an extracted sample it can't drain yet) — the script pauses
efficiently until the Luminizer's next tick, then re-checks `_luminizer_is_idle()` from scratch,
rather than re-checking on a fixed timer.

**First version only broadcast on a successful load — found (before it ever shipped) that this could
hang the Lab forever.** `wait_broadcast()` only satisfies on a broadcast published *after* the call
(existing broadcasts don't count), so a signal that only fired on `self.machine.load(...)` succeeding
would never fire again once the Luminizer drained its last item with nothing staged behind it to load
next — including right at startup, before this Luminizer has ever loaded anything in this session at
all. A Lab that reached `_wait_for_luminizer()` in that state would wait indefinitely even though the
Luminizer had, in fact, gone idle. Fixed by making the broadcast an unconditional per-cycle heartbeat
instead of a load-success event — the Lab always wakes up again within one Luminizer `step()`,
whatever state it's actually in. Falls back to `sleep(0.5)` if `comms` is unavailable or the wait
itself errors.

**A coarse total-artifact safety net remains, on purpose, as insurance — not as the primary
mechanism.** `MAX_LOCAL_GLOW_ARTIFACTS = 4`: if the sum of every glow-tagged item (raw + tinted, any
fragment type) sitting in local storage right now (`_total_glow_artifacts(snapshot)`, a plain sum
over the snapshot's `by_glow` dict — no extra scanning) reaches this, `BioCollectorController.step()`
pauses harvesting entirely for that cycle. In a healthy pipeline this should stay at 0-2 and never
actually trip — the Lab holds at most 1 raw sample before the Luminizer picks it up, and the
Luminizer holds at most 1-2 before the Exchange sweeps them up — this cap only matters if that
structural bound somehow doesn't hold (e.g. a sibling script isn't running).

**The cap tripped at 5 with the Luminizer stuck picking up nothing — root cause was
`_focus_coastal_order()` locking onto an already-satisfied order.** Reported live: 5 `cuticle_molt`
sitting in storage, the Luminizer repeatedly identifying an order that lists `cuticle_molt` in
`.requires`, doing nothing, and repeating the exact same no-op every tick. The bug: neither branch of
`_focus_coastal_order()` checked whether a candidate order's need for a fragment was actually still
outstanding — the `fragment_id` branch returned the first local incomplete order requiring it at all,
and the no-`fragment_id` branch preferred any candidate with *any* nonzero local stock for *any*
required fragment, regardless of whether that order's own deficit for it was already 0 (fully
delivered/in-transit/already-tinted). If order A's `cuticle_molt` requirement was already covered but
order B (also incomplete, also local, also wanting `cuticle_molt`) wasn't, `_focus_coastal_order()`
could still lock onto order A — and every subsequent `_fragment_remaining()` check on order A
correctly came back 0, so `_load_next_sample()` found nothing to load and exited, forever, despite
real stock and real demand for the same fragment existing on order B. Fixed with new module-level
`_order_fragment_remaining(order, fragment_id, snapshot)` (the same needed-minus-delivered-minus-
in_transit-minus-already-tinted math `_fragment_remaining()` used to do inline, now shared): both
branches of `_focus_coastal_order()` now require genuine remaining deficit, not just presence in
`.requires` or nonzero stock, before treating an order as actionable.
`BioLuminizerController._fragment_remaining()` is now a thin delegate to the module-level version.

**The Lab extracted every analyzed specimen unconditionally, with no demand check at all --
`_cuticle_molt`/`_arm_segment` recurred even after the focus-order fix above.** Reported live:
`ma_cuticle_molt` and `fs_arm_segment` both sat at their `MAX_LOCAL_GLOW_ARTIFACTS` share, neither
needed by any current order, permanently wedging `BioCollectorController` (which refuses to harvest
ANYTHING once the total-artifact cap is hit, needed or not). Root cause was structurally different from
the earlier `_focus_coastal_order()` bug: `BioCollectorController` already gates *harvesting* on demand
(`needed_fragments`), but `BioLabController` never gated *extraction* on demand at all -- once a
specimen reached `stage == "analyzed"`, it went straight to loading reagents and calling `extract()`
regardless of whether anything still wanted the result. `BioCollectorController`'s own "uncataloged
discovery" harvesting (Priority 2 in its `step()`) picks up a specimen purely to identify a new
location/fragment, with zero demand behind it -- analysis alone satisfies that (it's what populates
`journal.cataloged_fragments()`), but the old code extracted it anyway, spending reagents and storage
on a sample nothing would ever collect. Fixed with `_bio_demand_totals(comms, exchange, my_biome)`
(module-level, shared by both controllers): `BioLabController.step()` now checks it right after
`analyze()`, before loading any reagents (`if not loaded:` guards against interrupting a load already
in progress) -- if demand for `fragment_id` doesn't exceed current local stock, `self.machine.discard()`
runs instead of `extract()`. `BioCollectorController.step()`'s own demand computation was refactored to
call the same shared helper instead of its previous inlined duplicate, so both controllers now agree on
exactly one definition of "needed."

**Self-cleaning backstop for artifacts already stuck before this fix (or from any other future edge
case): `BioExchangeController._cleanup_orphaned_artifacts()`.** The demand-gated extract() above only
stops the pileup from *recurring* -- like the per-fragment raw-backlog cap earlier in this section, it
does nothing for stock already sitting there. Runs every `sweep_and_deliver()` cycle after the normal
per-order delivery loop: for every locally-staged glow-tagged stack whose item id isn't in
`_required_fragment_ids(all_orders)` (genuinely still needed, remaining > 0, by ANY incomplete order
anywhere -- local or foreign, matching what the delivery loop above already tries to ship to), it's
taken into `self.machine.input` (exact properties) and destroyed with `input.flush()`. Deliberately
matches on item id only, not exact glow -- a raw, not-yet-tinted sample never matches any order's
`target_glow` (that's the Luminizer's whole job), so gating on exact glow would misclassify perfectly
good raw stock awaiting tinting as orphaned and destroy it.

**`best_unload_target()`'s fallback tried to connect a remote machine's output to a non-local
destination.** When no local Warehouse had room, it unconditionally returned the literal id
`"inventory"` — but `"inventory"` only exists/connects at the home outpost (per `lib/storage.py`'s own
header comment). For a remote machine (the coastal Bio Luminizer, once its local Warehouses filled
up) this meant `drain_port_to_storage()`/`BioLabController.drain_output()` would call
`port.connect("inventory")` from a Warehouse-only outpost — a non-local target. Fixed: `outpost.is_home`
(note: a plain `bool` attribute on `OutpostRef`, not a method — a genuine trap, since `Outpost`, the
type returned by `get_component(outpost_id)`, has `is_home()` as a *method* with the same name; the
type actually carried by `machine.outpost`/`_home_outpost()` throughout `lib/storage.py` is always
`OutpostRef`) now gates the `"inventory"` fallback — only used when the resolved outpost actually is
home, else `best_unload_target()` returns `None` and callers skip the stack (leave it staged, retry
next cycle) instead of attempting a connection that can't work. `drain_port_to_storage()`,
`BioLabController.drain_output()`, and `vehicle_cargo.py`'s `unload_one()` were the three call sites
that weren't already wrapped in a blanket `try/except` around the `.connect()` call, so those three
got an explicit `if target is None:` early-return/skip added.

---

## 🚗 2. Surface Vehicles & Logistics

| Vehicle | Speed / Throttle | Energy Cost / Budgeting | Operational Rules |
| :--- | :--- | :--- | :--- |
| **Rover** | `self.cruise_throttle` (explicit at construction, else the fleet-wide `vehicle.default_cruise_throttle` archive value, default 0.5) capped down per-leg by `RoverController.max_safe_throttle_for_leg()` | Developer-confirmed travel model, Rover-specific and flat (no calibration, no Pioneer terms): `Wh/meter = 0.2 × throttle`; safety margin `SAFETY_MARGIN_MULTIPLIER = 1.05` (5%) — see §2a | Sonar scan: `SONAR_WH_BUDGET = 2.0` Wh. Mining drill: exact per-ore/per-drill/per-purity `mine_wh_per_unit(item_id, purity)`, `MINE_WH_PER_UNIT = 2.5` Wh/unit only as the no-item-id fallback — see §2a. Return to nearest charging station (not necessarily home) when Wh falls below the trip budget. |
| **Pioneer** | Configurable slots / tools | Slot chassis: `inspect_slots()`, `execute_construction()`; construction energy: `WH_PER_PROGRESS` (per-vehicle calibrated, default `CONSTRUCTION_WH_PER_PROGRESS_DEFAULT = 40.0` Wh for 0%→100%) — see §2a | Heavy construction, blueprint placement, pipe/power line deployment. Budgets each trip for `TARGET_CONSTRUCTION_PROGRESS_PER_TRIP = 0.25` progress (~4 round trips to finish a job), not just round-trip driving. |
| **Harvester** | BFS on 8x24 grid (`NUM_ROWS=8`, `NUM_COLS=24`, A1..H24) | Travel time: 0.5 h/sector. Empty move: `+7 heat`; Item move: `+1 heat` | Max heat: 100°C. Pause & cool down when heat exceeds `HEAT_SAFE_CEILING = 75.0`, resume once back down to `HEAT_RESUME_LEVEL = 40.0` (`lib/harvesting.py`). |

### 2a. Vehicle Energy Budgeting Detail (`lib/vehicle_energy.py` `VehicleEnergyMixin`)

- **Travel energy is a developer-confirmed exact model, not an empirically-calibrated Wh/meter —
  but Pioneer and Rover use two DIFFERENT models, not one formula with the other's terms zeroed
  out.** The archive-backed calibration system (`self.wh_per_meter`, per-vehicle `archive` keys,
  `calibrate_wh_per_meter()`) was intentionally removed for both — treated as ground truth, so
  there's nothing left to calibrate for travel. (Construction *progress* energy is a separate
  concern with no confirmed formula, and still uses `wh_per_progress` calibration.) Leftover
  archive clutter from before the removal comes in two historical shapes —
  `"<vehicle>.wh_per_meter"` and an older colon-prefixed `"vehicle.wh_per_meter:<vehicle_id>"` — both
  purged by `ArchiveCleaner.clean_calibration()`.

  **Pioneer** (`VehicleEnergyMixin`'s own implementation, used as-is by `PioneerController`):
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

  **Rover** (`RoverController` overrides in `lib/rover.py`, not part of the base mixin):
  ```
  Wh/meter = ROVER_WH_PER_METER_PER_THROTTLE=0.2 × throttle
  ```
  Developer-confirmed (Spyros - CT Dev, in-game Discord #playtest-chat, 2026-08-28): "the rover is
  very simple wh = distance x throttle x 0.2" — deliberately flat, with **no** `active_modules`,
  `cargo_units`, or Sport Nav multiplier terms (unlike Pioneer), and linear in throttle rather than
  Pioneer's `throttle^1.5` (implying Rover power scales as `throttle^2` at its fixed 100 m/h-per-
  throttle speed). `RoverController.wh_per_meter_at_throttle()` overrides just that one method —
  `minimum_wh_per_meter()`, `calculate_trip_energy()`, `energy_needed_to_return_now()`/
  `_comfortably()`, and `energy_wh_for_leg()` all call through it, so nothing else needs
  overriding. `RoverController.max_safe_throttle_for_leg()` is re-solved for this model too: since
  Wh/m is linear (not `sqrt(throttle)` like Pioneer's), the safe-throttle bound solves directly as
  `t <= available_for_leg / (distance * ROVER_WH_PER_METER_PER_THROTTLE * SAFETY_MARGIN_MULTIPLIER)`
  instead of Pioneer's squared form.
  - Module-level standalone versions (`travel_wh_per_meter_for(vehicle, throttle, cargo_units=None)`
    and friends, all suffixed `_for`) let non-`VehicleController` callers use the same formula
    without a live instance, and dispatch to the Rover model via `is_rover_chassis_for(vehicle)`
    (probes `vehicle.id`/`.name` for a `"rover"` prefix — the same convention already used for
    telemetry keying in `VehicleController.publish_telemetry()` — since a raw `get_component()`
    object has no chassis-type flag to read directly). `lib/charging.py`'s `rescue_target_level()`
    doesn't import these directly, though — it calls `rescue_wh_per_meter_for(vehicle)`, a single
    collapsed entry point that bakes in the rescue-specific choice (rate the leg at
    `MIN_SPEEDMODE_THROTTLE`, the cheapest possible Wh/m) and the "vehicle unreachable → bare-module
    Pioneer-shaped fallback" branch (chassis type is unknowable with no vehicle object to probe), so
    a cross-script caller needs one import instead of five. Prefer adding a purpose-built `_for`-style
    function like this over widening a caller's import list — see the parser note below on why that
    matters here specifically. Single source of truth either way: the class attributes are aliases of
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
- **Construction job claims (Pioneer only, `run_construction_loop()`, exclusive)**: unlike mining
  sites, a construction job is NOT shareable — two Constructor Pioneers both loading/building the
  same blueprint would double-load materials and waste a trip. Uses `vehicle_claims.py`'s existing
  exclusive claim mechanism as-is (key `f"build_{job_id}"` via `PioneerController.construction_claim_key()`,
  distinct prefix from mining's `"site_"`/survey's `"poi_"` so all three coexist in the same shared
  claims dict). `is_construction_job_free()` filters a peer's fresh claim out of both the
  paused-constructions and pending-constructions lists before any job selection each cycle;
  `claim_target()` is called at each of the three commit points (resuming a paused job, executing a
  cargo-matching pending job, and committing to a job before the round trip home to fetch its
  materials) — a lost claim race (peer grabbed it first) falls through to the next selection step
  instead of executing nothing. `execute_construction()` heartbeats via `refresh_claim()` every
  attempt (no-op if this Pioneer doesn't own the claim, so safe to call unconditionally). Released
  on genuine completion (`get_construction_progress() >= 1.0`) or failure (materials unobtainable,
  genuine rejection) — kept held across an incomplete "still paused, retry later" outcome so a peer
  doesn't grab it mid-build; also released wholesale on an unhandled loop exception.
- Fleet coordination (`lib/vehicle_claims.py`): atomic `archive.transaction()` claims
  (mirrored to `rover.claims` / `survey.claims` for legacy compatibility), heartbeat-renewed via
  `refresh_claim()`, expiring after `CLAIM_STALE_TICKS = 36000` ticks (1 sim hour). **Mineral
  mining sites are no longer exclusive** (the game now allows several Pioneers to mine the same
  POI) — `lib/mining.py`'s candidate builders no longer filter out a peer-claimed site, and
  `claim_target()`/`refresh_claim()`/`release_target_claim()` are still called for a mine-type
  mission (bookkeeping: `current_target_key`, `save_mission()`/reload-resume) but never gate
  candidate selection. Survey/POI targets (`vehicle_survey.py`) are still exclusive via the same
  claim mechanism, unchanged. See `lib/mining_reservations.py` below for what replaced exclusivity
  as the overmining guard.
- **In-flight mining yield reservation** (`lib/mining_reservations.py`, `mining.reserved_yield`
  archive key): non-exclusive, additive bookkeeping — several vehicles converging on one deficit no
  longer collide via a claim, but would all still see the *same* undiminished demand without this.
  When `MiningMixin.select_best_mining_target(candidates, reserve_demand=True)` claims a mine-type
  candidate (home-demand path only — `build_mineral_site_candidates()`, called from `rover.py`'s
  `run_expedition_cycle()` and `pioneer.py`'s `run_mining_loop()`), it estimates the trip's yield via
  `VehicleEnergyMixin.max_mineable_units()` (energy-based — see below) and reserves it;
  `get_raw_material_demands()` (`lib/production.py`) subtracts every non-stale reservation's units
  from raw demand before returning, so a peer's search this cycle or later sees the deficit already
  promised. Heartbeat-renewed (`refresh_yield()`, alongside `refresh_claim()` in
  `mine_current_site()`/`mine_until_full_or_exhausted()`) and released (`release_yield()`) on trip
  end/failure, same `CLAIM_STALE_TICKS`-equivalent expiry (`RESERVATION_STALE_TICKS = 36000`). The
  **stockpile path** (`build_local_stockpile_candidates()`, outpost-stationed mining,
  `reserve_demand=False`) deliberately skips this — it doesn't read `get_raw_material_demands()` at
  all, and is already self-bounded by each outpost's own live `stock_target_for()` check, so a few
  vehicles briefly converging on the same under-target ore just self-corrects once stock arrives.
- **Energy-based mining trip sizing** (`VehicleEnergyMixin.max_mineable_units()`,
  `lib/vehicle_energy.py`): replaces `cargo.capacity()` as the default yield estimate/`max_units` for
  a mining trip. Solves the same budget `calculate_trip_energy()` checks, directly for units instead
  of guess-and-check: outbound drive Wh + base return drive Wh are fixed, while mined-unit Wh
  (`mine_wh_per_unit_for()`) and the marginal per-unit return-drive Wh (from the added cargo weight,
  `CARGO_UNIT_TRAVEL_POWER_W`) are exactly linear in unit count, so the max affordable count follows
  in one division after subtracting `MIN_EMERGENCY_RESERVE_WH` and applying
  `SAFETY_MARGIN_MULTIPLIER`, then clamped to `cargo.capacity()`. Reflects that mining outposts now
  stockpile ahead of demand, so a trip no longer needs to plan around repeated
  mine-till-full/recharge/resume cycles (`mine_until_full_or_exhausted()` still exists as a safety
  net for estimate drift, e.g. richer-than-expected purity).
- Recall (`lib/vehicle_claims.py`): one shared `vehicle.recall` dict `{vehicle_name: True}` — **not**
  one archive key per vehicle (the old `vehicle.recall:<name>` scheme, migrated off by
  `ArchiveCleaner.clean_recall_flags()`) — since the Data Archive has a fixed shared key-count cap
  that doesn't scale with fleet size for a single boolean flag. `is_vehicle_recalled()`/
  `set_vehicle_recalled()` are the module-level read/write (a vehicle absent from the dict reads as
  not-recalled, so only actively-recalled vehicles are ever stored); `VehicleClaimsMixin.is_recalled()`
  is a thin wrapper. Toggled per-vehicle via `panel_2.py`'s Fleet card switch. On -> the vehicle
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

**Load chunking** (found from a screenshot: two Fabricators both needing Glass, one showed 44/1
staged while the other sat at 0/2 — one had grabbed the ENTIRE available Glass stock in a single
`take_item()` call before the other's own poll ever got a turn). `load_inputs()` used to request its
whole remaining batch (`required_per_craft * crafts_remaining`, up to several dozen units) in one
call; capped now to `FABRICATOR_LOAD_CHUNK_SIZE = 10` units per call, so a heavy batch spreads across
several `step()` cycles instead of one Fabricator monopolizing a contested item in a single grab —
a peer's own poll gets a chance to interleave and take its own chunk in between. `lib/smelter.py`'s
ore top-up (Step 3 of `step()`) had the identical problem (up to a full 50-unit top-up in one call)
and got the same fix, `SMELTER_LOAD_CHUNK_SIZE = 10`. Supply Dock's own material loading
(`lib/supply_dock.py`) deliberately keeps loading its full remaining need in one call — it has no
sibling competing for the same active order's materials, so there's nothing to share fairly with,
and chunking it would only add pointless delay. Verified via stub tests: a single `load_inputs()`/ore
top-up call never exceeds its chunk size even with far more needed and available; two Fabricators
alternating turns against a shared, contested 44-unit Glass pool end up with a fair nonzero split on
both sides instead of 44/0; repeated Smelter `step()` calls keep topping up in the same chunk size
across cycles.

**Chunking alone wasn't enough — it shrank the race, it didn't fix it** (found from continued live
reports after the chunking fix above shipped: "smelter_1 grabs 50 silicon in 5 stacks of 10 each,
smelter_2 never gets any"). Each `take_item()`/Auto Feeder transfer locks the source Warehouse for
the whole transfer duration (`docs/guide/input_and_output_ports.md`: "Both physical endpoints remain
occupied for the resulting transfer duration"), so a smaller per-call chunk still lets whichever
consumer's `step()` happens to poll first win it — and if one consumer consistently polls first
(script start order, poll-interval phase), it wins every single chunk in a row, every cycle, forever.
Chunking only bounded how much it could win in one grab, not how often it wins.

An archive-based cooperative turn-taking scheme (`storage.take_item_fair()`, tracking per-item
`"last winner"`/`"seen consumers"` state under a `storage.load_turn.<item_id>` key) was tried first and
then deliberately reverted: it doesn't scale to multiple production outposts (an item id is global, but
"who's contesting it" is really per-outpost — a second outpost's Smelter would needlessly defer to a
first outpost's, or worse, collide on the same key for an unrelated pool of stock), and it grows the
Data Archive by one entry per *distinct contested item id ever seen*, against the archive's hard
512-entry save-wide cap (`docs/guide/data_archive_guide.md`) — an unbounded-by-design cost for what
should be transient, in-memory coordination. Replaced with **`production.craft_prefill_units(recipe,
item_id, prefill_seconds=INPUT_PREFILL_SECONDS)`** (`INPUT_PREFILL_SECONDS = 30`) — no archive state at
all. Instead of asking "how much is left to load" (which naturally races toward a big number), it asks
"how much do I need staged to keep crafting for the next ~30 real seconds" — `ceil(prefill_seconds /
craft_seconds(recipe))` crafts' worth, floored at one craft's own requirement, where `craft_seconds()`
converts `recipe.duration_game_hours` to real seconds via the fixed day-cycle schedule
(`SECONDS_PER_GAME_HOUR = lib/power.py's DAY_CYCLE_DURATION_SECONDS / 24.0` — reused, not redefined, so
there's exactly one place that conversion lives). This fixes the race as a side effect rather than
coordinating around it: every consumer's total ask shrinks to a short, recipe-scaled window instead of
the full remaining shortfall, so it tops up and stops far sooner, leaving much more frequent openings
for a peer to get its own share in between — a probabilistic, self-limiting fix instead of a
deterministic one, but stateless and correctly local-to-whatever-outpost-actually-has-the-contention
(each Smelter/Fabricator's own `recipe` already came from its own outpost's building). Also directly
fixes a second, independent bug — see below. `lib/smelter.py`'s ore top-up and `lib/fabricator.py`'s
`load_inputs()` both cap their take amount with this now, alongside `SMELTER_LOAD_CHUNK_SIZE`/
`FABRICATOR_LOAD_CHUNK_SIZE` (kept as a simple per-call ceiling on top, not the primary fairness
mechanism any more). Supply Dock's material loading still has no reason to use any of this — same "no
sibling competing" reasoning as its chunking exemption above.

**Ore intake ignored demand SIZE entirely — a much bigger overproduction bug than the fairness race**
(found live: ~80 excess Glass sitting in storage with no active demand for it). `lib/smelter.py`'s
Step 3 buffer top-up used to gate purely on `demands.get(output_item, 0) > 0` (via `select_needed_ore()`)
and then always fill the ore buffer toward the full 50-unit cap regardless of how large that demand
actually was — a demand of 5 finished units still triggered filling a 50-unit ore buffer, because
nothing ever compared the buffer top-up *amount* against the demand *quantity*, only checked it was
nonzero. `lib/fabricator.py`'s `load_inputs()` never had this bug (it was always bounded by
`required_per_craft * crafts_remaining`, itself netted against target/current stock), which is why
this was Smelter-specific. Worse with 2+ Smelters "joined" on the same recipe (`select_needed_ore()`'s
pile-on fallback, used whenever only one ore is currently demanded): each Smelter independently filled
its own buffer toward the SAME undivided demand figure, so two Smelters could together refine roughly
double the actual demand before `total_stock()` ever caught up enough to zero it out — matches the
observed "smelter_1 and smelter_2 each grab their own full share, ~80 Glass more than needed" report
exactly, and would have applied even to a single Smelter alone (no second consumer needed to
overproduce, just needed to fill past a small demand). `craft_prefill_units()` above (the fairness fix)
independently tightens this too — a slow-crafting recipe's window caps out at one craft's worth
regardless of demand size — but the actual demand-size fix is two further additions to Step 3, both
cast in ore units via `(qty * units_per_run + output_count - 1) // output_count` (same ceiling-division
shape `get_raw_material_demands()` already uses for the identical unit conversion):
`production.get_smelter_worker_count(recipe_id)` (mirrors `lib/fabricator.py`'s private
`_fabricator_worker_count()`, made public since Smelter needs it directly) gives this Smelter's live
headcount of peers on the same recipe; `share = ceil(demand_qty / worker_count)` is this Smelter's fair
slice of the CURRENT total demand (re-read fresh every `step()`, so it naturally shrinks as any
Smelter's output gets drained to Inventory/a Warehouse); `max_ore_for_share` converts that output-unit
share into an ore-unit ceiling. The take amount is `max(0, min(50 - in_buf, SMELTER_LOAD_CHUNK_SIZE,
max_ore_for_share - in_buf, craft_prefill_units(recipe, ore) - in_buf))` — floored at 0 so a demand or
prefill target that shrank since ore was already staged never requests a negative amount (already-staged
ore still finishes its craft normally, it just isn't topped up further). A single Smelter with a small
demand now loads only that much ore, not a reflexive full 50; several Smelters on one recipe now split
the demand instead of each independently re-filling to its entirety.

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

### 2a-0-4. Multi-Fabricator active-recipe input demand (`lib/production.py` `get_material_demands()`)

Same hardcoded-single-instance bug class again, this time in `get_material_demands()`'s "a selected
Fabricator recipe is an explicit production intention" block, which used to call
`get_fabricator_active_recipe(_default_fabricator())` -- always the *first* discovered Fabricator --
rather than looping every one. With two Fabricators each holding a different claimed recipe (see
§2a-0-2's `claim_recipe()`), the second Fabricator's own active recipe and its inputs were entirely
invisible to demand tracking: found live with `fabricator_1` running `craft_turbine_rotor` and
`fabricator_2` running `craft_gas_pipe_segment` (needs `iron_ingot`) -- `fabricator_2`'s `iron_ingot`
requirement never registered as demand at all, so `lib/smelter.py`'s `select_needed_ore()` (which
reads `get_material_demands()`) saw zero demand for `iron_ingot` and refused to refine it even with
raw `iron_ore` sitting in a Warehouse -- production silently stalled with no error anywhere. Fixed by
looping `discover_fabricator_ids()` (falling back to `["fabricator_1"]` if discovery finds nothing,
same convention as `_default_fabricator()`) and summing each Fabricator's own
`get_fabricator_active_recipe()` input demand. Safe to sum rather than double-count: when several
Fabricators share the same claimed recipe, `get_fabricator_active_recipe()` already divides
`crafts_remaining` by the worker count (§2a-0-2), so each contributes only its fair share and the sum
reconstructs the correct total.

### 2a-1. Fabricator demand tracking (`lib/production.py` `get_fabricator_targets()`)

`get_fabricator_targets()` is the single source of truth for what the Fabricator should be
building, and feeds `get_material_demands()` → `get_raw_material_demands()` (mining priority) too.
Four demand sources are folded together into one `{item_id: quantity}` dict:

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
4. **`fabricator.manual_orders`** archive key (`{item_id: quantity}`, e.g. `{"drone_small": 2}`) —
   ad-hoc one-off build requests, added by editing the key directly in the Data Archive Notebook (no
   default seeded; empty is normal). `max()`'d into the target like every other source above, but
   ALSO given queue priority in `lib/fabricator.py`'s `choose_recipe()`: a manually-ordered recipe is
   picked ahead of every other demanded recipe regardless of shortfall size, so an operator's request
   doesn't sit waiting behind whichever recipe happens to have the biggest shortfall this poll.
   Counted down (and the entry dropped once it hits 0) by `production.consume_manual_order()`, called
   from `drain_output()` with the quantity actually delivered to Inventory each step — not inferred
   from a stock-target/baseline comparison, so it counts down correctly even if some of the finished
   units get shipped or consumed elsewhere afterward.
   The key must be the exact `item_id` a recipe's `output_item` uses (e.g. `drone_small`, not
   `small_drone`) — it's hand-typed with no validation on write, and a mismatched key still gets
   folded into the target (so nothing looks "wrong" in `fabricator.stock_targets`) but never matches
   any recipe, leaving every Fabricator silently idle with no log output at all. `get_fabricator_targets()`
   in `lib/production.py` now prints a one-time `[production] Warning: fabricator.manual_orders has
   '<item_id>'... doesn't match any known Fabricator recipe output` when a key doesn't match the
   default Fabricator's currently unlocked recipe outputs (per-script-run, via an in-memory
   `_WARNED_UNKNOWN_MANUAL_ITEMS` set) — this is a heads-up, not proof the order is unfulfillable,
   since it only checks the *default* Fabricator's *currently unlocked* recipes, so it can
   false-positive for an item only a different Fabricator (or a not-yet-unlocked recipe) can build.

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
- **A `liquid_tank`/`large_liquid_tank`/`gas_tank` existing on the network is not by itself proof
  it can supply a given fluid** — these are generic multi-fluid buffers that latch onto whichever
  exact fluid is piped into them *first* and hold only that until drained to `0`
  (`docs/components/liquid_tank.md`, `docs/components/gas_tank.md`). An empty tank exposes a
  neutral port that `connect()`s "ok" to anything, then just never receives the fluid (e.g. Oil,
  with no Oil Pump/surveyed oil well anywhere) — `production.BUFFER_FLUID_TYPE_IDS` +
  `fluid_building_is_viable(fluid_key, type_id, building)` gate both `can_source_fluid()` and this
  discovery loop identically: a dedicated producer (`oil_pump`/`water_pump`/`steam_condenser`/
  `thermal_cap`) always counts since it only ever emits its one fixed fluid, but a buffer only
  counts once its own `.fluid()` is already latched to the exact fluid needed
  (`production.FLUID_LATCH_IDS`). Without this, a Fabricator would set (and get stuck claiming) a
  recipe needing Oil off a wrong-fluid or empty tank's existence alone, connect "successfully" to
  it, then stall/blacklist/rescan/reconnect forever instead of ever falling back to a different
  demanded recipe. `fluid_building_is_viable()`'s `building` arg is normally a bare `BuildingRef`
  from `outpost.buildings(type_id)` (`.id`/`.name`/`.type_id`/`.outpost`/`.powered`/`.position`
  only, per `docs/components/outpost.md` — no `.fluid()`), so it resolves the live component via
  `get_component(ref.id)` first whenever the passed-in object has no `.fluid()` of its own; a
  bug here silently made every buffer tank look permanently non-viable regardless of what it
  actually held, since the raised `AttributeError` was swallowed by the surrounding `except`.
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
- Neither candidate builder filters out a site already claimed by a peer (mineral sites are no
  longer exclusive — several Pioneers can mine the same POI); see this file's fleet-coordination
  and in-flight yield reservation entries above (`lib/mining_reservations.py`) for what guards
  against overmining now instead.
- `select_best_mining_target(candidates, reserve_demand=False)`: sorts by `(priority, -PURITY_RANK, distance)` — lower
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
  hardcoded `10`) when no `max_units` is given — Pioneer's cargo capacity varies with storage
  modules. The home-demand mining loops (`rover.py`/`pioneer.py`) now always pass an explicit
  `max_units` from `select_best_mining_target()`'s `estimated_units` (see
  `VehicleEnergyMixin.max_mineable_units()` above), an energy-based trip size, so the
  cargo-capacity default is now mainly a fallback (e.g. `_stationed_mining_cycle()`'s own
  stock-headroom-based cap, computed independently).
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
- `best_unload_target(item_id, min_amount=1)`: among every discovered Warehouse at `outpost` with
  `space_for(item_id) >= min_amount`, prefers one that **already holds `item_id`** (`count(item_id) >
  0`) -- consolidating onto an existing stack -- and only falls back to ranking by least-full
  (`fill_percent()`) when none already stocks it; `"inventory"` if no Warehouse qualifies at all.
  Ranking purely by least-full (the old behavior, before this preference was added) ignores which
  Warehouse already has the item, so alternating "least full" picks across separate deliveries could
  spread the same item across every Warehouse at the outpost one partial stack at a time -- found
  from a real case where a 100-unit reagent target ended up 50 in one Warehouse + 50 in another,
  each its own single-slot partial stack, even though one Warehouse had room for the full 100 the
  whole time. `vehicle_cargo.py`'s `unload_cargo()` picks a destination **per stack** (cargo can hold
  more than one item id) rather than connecting once to `"inventory"` up front.
- `consolidate_cross_warehouse_stock(outpost=None)`: calls `.compact()` on every discovered
  Warehouse/Large Warehouse at `outpost` to pull a same-item stock split across more than one of
  them back together. `.compact()` reads at a glance like a purely intra-building operation
  ("fewest Warehouse slots"), but it isn't: its outcome table shares `transfer_to()`'s exact
  vocabulary (`source_under_construction`/`source_changed`/`slots_full`/`target_full`), which only
  makes sense if it pulls from *other* storage endpoints (a "source") into the one it's called on.
  That also matches why the game would expose it at all -- with Auto Feeders, a single Warehouse
  already adds to / draws from its lowest-numbered occupied slot for a given item on its own, so a
  purely intra-building `.compact()` would have nothing to ever actually do; confirmed by observing
  it consolidate stock split across separate Warehouse buildings in-game, and by `.compact()`
  locking its Warehouse as a material endpoint for the whole cycle -- exactly the "busy while a
  transfer between buildings is in flight" cost a same-building-only operation would have no reason
  to pay. Complements `best_unload_target()`'s now-consolidation-aware routing for stock that was
  already split before that fix landed (or split for any other reason, e.g. a manual move). Runs
  once per `STORAGE_TICK_INTERVAL` cycle from `panel_1.py`'s AUTOMATION section (§7) for **every**
  outpost (`network.outposts()`), not just home -- unlike `rebalance_inventory_to_warehouses()`
  (Inventory-only, so home-scoped), this fragmentation happens across Warehouses themselves and
  affects remote outposts (e.g. the reagent-hauler's destination) too. `STORAGE_TICK_INTERVAL` is
  deliberately much coarser than the grid-supervision cadence -- see §7's note on why the AUTOMATION
  card runs storage work and grid supervision on two separate timers, not one shared one.
- `take_item(port, item_id, amount)`: the one function behind every
  `machine.input.take(item_id, amount)` call site (Smelter ore loading, Fabricator input loading,
  Supply Dock material loading, Pioneer's `load_construction_materials()`). Tries whatever `port` is
  *currently* connected to first (usually Inventory, the existing default), and only reconnects to a
  Warehouse if that falls short — ports hold one source at a time (same single-destination
  constraint as `FluidPort`, see `lib/thermal_cap.py`), so this reconnects on demand rather than
  fanning out simultaneously.
- **Multi-Smelter Coordination** (`SmelterController` in `lib/smelter.py`) — with several
  Smelters at home, `production.discover_smelter_ids()` replaces every place that used to hardcode
  the literal id `"smelter_1"` (a correctness bug, not just inefficiency: demand/recipe lookups would
  silently only ever consult one specific smelter's recipe set). **No Leader/Follower election any
  more** — the "inventory manager" sweep (see below) that used to need exactly one smelter to run it
  is now run centrally, once, by `panel_1.py`'s AUTOMATION section (`storage.rebalance_inventory_to_warehouses()`,
  no args = home outpost) instead of by whichever `SmelterController` instance won an election every
  `step()`. `SmelterController` no longer has `check_leader()`/`update_role()`/`is_leader` at all — see
  §1a-1 for why moving this to the one always-running Control Room process removed the election
  entirely instead of just relocating it, and for the hard dependency this creates on `panel_1.py`
  running. Every smelter still independently runs its own
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
  `panel_1.py`'s AUTOMATION section (§1a-1; confirmed always-running at home base): any **propertyless**
  (`slot.properties is None` — non-stackable/unique items like worn equipment are left alone)
  Inventory item gets moved to a Warehouse **entirely**, not partially — there's no real "quick
  access" cost to reading from a Warehouse instead of Inventory, so nothing is deliberately left
  behind — when either:
  - **Exception**: items whose `item_catalog.lookup(item_id).category` is `"equipment"`,
    `"module"`, or `"portable"` (`NON_WAREHOUSABLE_CATEGORIES` in `lib/storage.py`,
    `_must_stay_in_inventory()`) are never swept at all, regardless of slot count or split state:
    - `"equipment"` deploys straight into a building/machine from Inventory only (a Gas Tank or
      Solar Generator bought/produced as itself) — a Warehouse has no way to deploy it, so moving
      one there would just strand it. `"construction_kit"` (e.g. `mining_drill_kit`) is
      deliberately *not* in this set — those are placed by a Pioneer via blueprint construction,
      which doesn't need the kit sitting in Inventory, so it's fine to warehouse.
    - `"module"`/`"portable"` (battery holders, cargo racks, portable batteries/bins/scanners) has
      to be in Inventory to equip a newly-built or refitted Pioneer/Rover.
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
    clear net win. `slots_freed` is computed from `remaining` (units still stuck in Inventory *at
    swap-fallback time*), not the item's original slot count captured at the top of the loop — the
    direct-move step above can already have moved part of the item out before the swap is even
    considered, and using the stale original count there overstated the net win. In practice, because
    `slots_reclaimed` divides by the small Inventory `stack_size` (10/20) while `evicted_qty` can be
    up to a full 2,000-unit Warehouse slot, a swap is only ever a net win for a *small*-quantity
    occupant (roughly `slots_freed * stack_size` units or fewer) — once every Warehouse slot
    everywhere holds a large quantity of something, the swap fallback will keep declining (logged as
    `[storage] Skipping swap for <item>: ...`) and an item with no Warehouse slot of its own stays
    split in Inventory until more Warehouse capacity is built. Every previously-silent failure path
    here (`_cheapest_warehouse_occupant()` finding nothing at all, an eviction transfer moving 0
    units, or the freed slot still reporting no room) now logs a `[storage] Could not clear...` /
    `[storage] Swap for <item> did not go through...` / `[storage] Freed a slot... but it still
    reports no room...` line instead of silently continuing, so a persistently-fragmented item is
    diagnosable from the console instead of just never resolving with no explanation.
- `inventory_stack_size()`: `10`, or `20` once `research.is_unlocked("research_high_density_storage")`
  ("Bigger Stacks") — reuses the existing `research.is_unlocked(tech_id)` pattern already used in
  `lib/vehicle_claims.py`, not inferred from current slot contents.

### 2d. Outpost Ore-Assignment & Stock-Target Scaffolding (`lib/outpost_mining.py`)

Phase B of the Multi-Outpost Production Network (`TODO.md` Phase 3). Answers "which ores should a
vehicle stationed at outpost X mine?" and "how much should it stockpile before stopping?" — consumed
by Phase C's stationed-mining role (§2e). "Which ores" is answered **live from the Planet Map**, not
an archive list — every surveyed mineral site gets a `"resource.poi_X_Y"` marker whose `.note` names
the responsible outpost, so the assignment is always exactly what the map shows and a player can
reassign a site just by editing the marker.

- **Marker convention**: `RESOURCE_MARKER_PREFIX = "resource."`, id `resource.poi_{x:.0f}_{y:.0f}`
  (mirrors `mark_unsupported_targets.py`'s id/style conventions), `icon="resource"`, `color="neutral"`,
  `label="{Item Name} - {Purity}"` (e.g. `"Iron Ore - Rich"` — `_item_display_name()`/
  `RESOURCE_PURITY_LABELS` build it, `_item_id_from_label()` is its exact inverse, so no separate
  item-name lookup table is needed to read it back), `.note` = the responsible outpost id, or `""`
  when unassigned.
- **`sync_resource_marker(site, outpost_id=None)`** — places/updates one site's marker.
  `outpost_id=None` preserves whatever the marker already names (read back via `markers.get()`) —
  a style-only refresh; pass an explicit id (including `""`) to actually change the assignment.
- **`auto_assign_new_site(site, range_m=None)`** — call once per freshly-surveyed mineral site
  (`vehicle_survey.py`'s `scan_and_survey()` calls this automatically for every `kind() == "mineral"`
  site it just surveyed). Refreshes the marker and, **only if it isn't already assigned**, hands it to
  the closest owned outpost within `range_m` (`resource_assignment_range_m()` by default — archive key
  `RESOURCE_ASSIGNMENT_RANGE_KEY = "outposts.resource_assignment_range_m"`, default `200.0`m). Never
  reassigns an already-assigned site, even to a now-closer outpost — moving supply away from an
  outpost whose transport/miner already depends on it risks a shortage there.
- **`reevaluate_unassigned_near_outpost(outpost_id, range_m=None)`** — explicit, **never auto-called**
  sweep: hand any still-**unassigned** `"resource."` marker within range to `outpost_id`. Meant to be
  re-run (via `sync_resource_markers.py`, see below) after founding a new outpost — CLAUDE.md's Outpost
  Construction Safety Rule means there's no automatic "an outpost just appeared" hook, so this is the
  player-triggered catch-up instead. Leaves already-assigned markers untouched, same reasoning as above.
- **`assigned_ores_for(outpost_id)` → `[item_id, ...]`** — the read path, called every cycle by the
  stationed-mining candidate builder (§2e). Scans `markers.list(RESOURCE_MARKER_PREFIX)` for notes
  matching `outpost_id` and recovers each item id from its own label (`_item_id_from_label()`) — no
  archive/journal cross-reference needed at read time.
- **`sync_resource_markers.py`** (project root) — run manually to backfill markers for sites surveyed
  before this system existed, catch up after a batch of new POIs, or reassign unclaimed markers after
  founding a new outpost: syncs every `journal.surveyed_sites()` mineral site
  (`auto_assign_new_site()`) then sweeps `reevaluate_unassigned_near_outpost()` for every owned outpost.
- **`stock_target_for(outpost_id, item_id)` → units** — unchanged seed-once-then-editable shape,
  default `WAREHOUSE_SLOT_CAPACITY = 2000` (one Warehouse slot) the first time a given
  `(outpost_id, item_id)` pair is looked up.
- **`nearest_outpost_id(x, y)`** / **`outpost_by_id(outpost_id)`** — thin wrappers around
  `outpost_network.nearest()` / iterating `outpost_network.outposts()`, reused by both the
  auto-assignment logic above and Phase C's per-site candidate filtering (§2e).
- **`RAW_ORE_ITEM_IDS`** — the 7 mineable ore item ids (`iron_ore`, `silicon`, `titanium`, `cobalt`,
  `rare_earth`, `neutronium`, `lead_ore`), and **`HOME_OUTPOST_ID = "outpost_home"`** — shared constants
  so `production.py`'s home ore buffer (below) and this module's own mining-outpost stock targets
  iterate the identical ore set/home id rather than each keeping its own copy.
- **Standing home ore buffer** (`production.py`'s `get_raw_material_demands()`): every raw ore also
  gets a floor demand of `max(0, stock_target_for(HOME_OUTPOST_ID, item_id) - total_stock(item_id))` —
  the same "1 Warehouse slot" default as a mining outpost's own stockpile, just applied to home too, so
  home always keeps roughly one Warehouse slot of each ore in reserve even with zero active
  production/order demand. Taken as a **max** with (never additive to) the production-driven deficit
  computed earlier in the same function, since both want the same ore delivered home. **Not a reserved
  stockpile** — Smelter/Supply Dock draw on it freely like any other stock; it's purely a floor that
  creates replenishment demand once dipped into. Both home-based miners (`lib/mining.py`'s
  `select_best_mining_target()`) and mining-outpost transporters (`lib/vehicle_cargo.py`'s
  `run_haul_loop()`, home-bound leg only) read this same demand function, so both roles automatically
  work toward the buffer without any outpost-specific code. **Overfill avoidance across concurrent
  haulers**: a hauler debits what it just loaded from this same demand via
  `mining_reservations.reserve_yield()` (`VehicleCargoMixin._reserve_home_haul()`, keyed
  `"haul:{vehicle_name}:{item_id}"`, released via `_release_home_haul()` right after a successful
  delivery lands) — the identical in-flight-debit mechanism `lib/mining.py` already used for concurrent
  mining trips (see this file's Multi-Rover note), just reused for the haul leg too. This is what keeps
  two haulers stationed at different mining outposts from each independently seeing the same uncovered
  buffer deficit and both loading toward it — e.g. only 380 units of room left at home, the first hauler
  to commit reserves all 380, so the second hauler's next demand read already shows 0 remaining, rather
  than both loading 400 each and overshooting.

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
- **`MiningMixin.build_local_stockpile_candidates(outpost_id)`** (`lib/mining.py`) — for each ore in
  `outpost_mining.assigned_ores_for(outpost_id)` still under its `stock_target_for()`, builds mineral
  site candidates the same way `build_mineral_site_candidates()` does (same hardness/claim/blacklist
  filtering) but additionally requires `outpost_mining.nearest_outpost_id(site.x, site.y) == outpost_id`
  — a site nearer some other outpost is that outpost's job, not this vehicle's, even if reachable.
  Independent of home's live demand entirely (no `get_raw_material_demands()` call), since the point
  is stockpiling ahead of it. Verified by stub test: a site near home is excluded from an outpost_3
  candidate list; candidates disappear once that ore's stock target is met.
- **`MiningMixin.run_stationed_mining_loop(outpost_id)`** — thin `while True` + recall-check +
  exception-guard wrapper (same shape as `run_mining_loop()`/`run_haul_loop()`) around
  `_stationed_mining_cycle(outpost_id)`, which does the actual work: same overall shape as
  `run_expedition_cycle()`/`run_mining_loop()`'s cycle body (reload-resume safety net, cargo/target
  mismatch detour, claim + drive + mine + return + unload + recharge — releasing the claim right
  after a successful return, regardless of outcome, so the next cycle always re-evaluates fresh
  instead of blindly resuming the same site), with target selection swapped for
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
  here; search for `run_haul_loop` to find the current one — see §2g, this role's original
  `run_supply_run_loop()` wrapper was later removed.)
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

  **Since generalized into `run_haul_loop()` (§2g), every thin entrypoint script calls it directly —
  see §2g for why the old `run_supply_run_loop()`/`run_reagent_delivery_loop()` wrapper methods were
  removed.**

### 2g. Generalized Hauler + Reagent Resupply (`lib/vehicle_cargo.py` `run_haul_loop()`, `lib/outpost_reagents.py`)

§2f's ore-hauler and the Bio Lab reagent-hauler turned out to be the same shape once you notice: **a
transporter is always stationed at `self.home_base` (the SOURCE) and delivers to an explicit DEST**.
For the ore-hauler, source = the mining outpost, dest = home (`None`). For the reagent-hauler, source
= home (`home_base=None`, the default), dest = the coastal outpost. `run_supply_run_loop()` and
`run_reagent_delivery_loop()` used to be one-line role-specific wrappers over a shared core; they're
now **removed** — every thin entrypoint script (`pioneer_5.py`/`pioneer_6.py`/`pioneer_7.py`) calls
`run_haul_loop(dest_outpost_id, poll_interval=10.0)` directly, since `dest_outpost_id` alone already
disambiguates the role (`None` = production outpost = ore-hauler; any other id = a remote outpost's
Bio Lab = reagent-hauler). The two params that used to be passed in at construction time —
`candidate_items_fn` and `demand_fn` — are both gone:

- **`demand_fn` is gone**: there's no reason to decide "what's needed" before a haul cycle actually
  runs it, so `_outpost_haul_demand(dest_outpost_id)` (module-level in `vehicle_cargo.py`) is now
  called fresh every cycle instead of injected at construction — `None`/home →
  `production.get_raw_material_demands()`, any other outpost id →
  `outpost_reagents.get_outpost_reagent_demand(dest_outpost_id)`.
- **`candidate_items_fn` is gone entirely**, not just moved: it turned out to be redundant.
  `_plan_haul_load()` already rejects any item with zero real stock at a non-home source
  (`available <= 0: continue`), so iterating `_outpost_haul_demand()`'s full item set directly —
  instead of first narrowing it to `outpost_mining.assigned_ores_for(source_id)` — produces the exact
  same plan; the only cost is ranking a few zero-availability items every cycle, which is cheap (at
  most 7 raw materials). For the reagent role, `demand_fn` was already restricted to
  `outpost_reagents.assigned_reagents_for(dest_id)` internally, so its candidate list was always
  redundant with its own demand dict.

`_plan_haul_load(capacity, dest_outpost_id)` and the loading step are the only pieces that otherwise
changed shape from §2f:

- **`_plan_haul_load()`**: when the source is home (`self.home_outpost.is_home`, a plain bool
  property on the `OutpostRef` `get_outpost_ref()`/`network.home()` return -- **not** a method call,
  unlike the same-named method on the full `Outpost` component returned by `get_component()`), a candidate's
  "available" amount is treated as its full deficit regardless of stock currently on hand, since a
  home shortfall can always be bought at the Shop — everywhere else (never home for the ore role),
  real stock on hand is still the hard ceiling, exactly as before.
- **`_load_haul_plan()`**: buys any shortfall **one Inventory-stack at a time**
  (`storage.inventory_stack_size()` — 10, or 20 with Bigger Stacks unlocked), immediately
  `take_item()`-ing each bought stack into cargo before buying the next, rather than one
  `shop.buy(item_id, full_shortfall)` call. Total planned volume was never the risk — capacity already
  caps every plan — this is about the *transient* Inventory footprint: buying a large shortfall (a
  reagent Inventory has never stocked before, bounded only by cargo capacity, which for a loaded
  Pioneer can still be a few hundred units) in one call could stall on a full Inventory before the
  vehicle ever gets a chance to pull any of it back out. Only triggers when the source is home; the
  ore role never buys anything.

**`outpost_reagents.py`** mirrors `outpost_mining.py`'s seed-once-then-editable convention
(`assigned_reagents_for(outpost_id)`, `reagent_stock_target_for(outpost_id, item_id)`,
`get_outpost_reagent_demand(outpost_id)`), but per-reagent rather than one flat constant — reagent
prices vary hugely (`docs/database/items_lab_reagents.md`: 1cr to 1,000cr), so a single flat target
would either starve the cheap ones or bankrupt the expensive ones early in a save:

```python
DEFAULT_REAGENT_STOCK_TARGETS = {
    "alkaline_buffer": 100, "cryo_solvent": 100, "protein_marker": 60,
    "chelating_agent": 20, "enzyme_solution": 10,
}  # dial these up as credit budget allows; FALLBACK_REAGENT_STOCK_TARGET = 100 covers any
   # reagent id not yet in this dict (e.g. a future game update)
```

Deficit math uses `storage.warehouse_stock(item_id, outpost)` (added alongside this work), **never**
`storage.total_stock()` — `total_stock()` unconditionally adds home Inventory's count regardless of
the `outpost` argument, which is harmless for ore (raw ore doesn't pile up in home Inventory) but
actively wrong for reagents, which routinely sit in home Inventory (that's where the Shop delivers
them): using `total_stock()` for "how much does the coastal Warehouse have" would over-report by
whatever's sitting untouched at home, masking a real deficit. `lib/bio.py`'s `local_stock(item_id,
outpost)` picks between the two based on `is_home_outpost(outpost)` (reads the `OutpostRef.is_home`
bool property, **not** a method call — see the `_plan_haul_load()` note above for the same
method-vs-property distinction) for the same reason, used throughout the relocated Bio Lab/Collector/
Exchange instead of the old hardcoded `get_component("inventory")`.

`lib/bio.py`'s `local_sibling(outpost, type_id)` replaces hardcoded same-pipeline instance ids
(`get_component("bio_collector_1")`, `"bio_exchange_1"`, `"bio_lab_1")`) with a live
`outpost.buildings(type_id)` lookup (first match, `get_component()`'d) -- needed because a Bio Lab's
`take_from()` requires its Collector to be at the *same* outpost, and a hardcoded home-outpost id
would silently reach across outposts (or reach nothing) once a second Bio pipeline exists at a remote
outpost. `BioLabController` uses it for its Collector; `BioCollectorController` for its Exchange and
Lab; `BioLuminizerController` for its Exchange. No caching -- resolved fresh per call, matching
`storage.discover_storage_buildings()`'s convention, since a sibling building isn't guaranteed to
exist yet at controller-construction time.

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
- `power.shedded`: Active list of machines Power Guard currently has shedded — hard-shed (breaker
  off) for most Tier 1 patterns, soft-shed (production paused, power stays on) for Tier 2's
  `smelter_*`/`fabricator_*` — see §1a. Checked by `SmelterController`/`FabricatorController`'s own
  `is_shedded()` to pause production. No cooperative wake call reads it any more — see §1a's note
  on `wake_smelter()`'s removal. (`power.shedded_machines` used to be written as an exact duplicate
  nothing ever read — retired.)
- `fleet.status.<id>` / `rover.status.<id>`: Telemetry `{name, state, x, y, wh, level, target, tick}`
- `rover.claims` / `survey.claims` (mirrored, legacy + current key): Atomic target reservation dict `{target_key: {"vehicle": id, "tick": tick}}`. Stale after `CLAIM_STALE_TICKS = 36,000` ticks (1 hr) — see `lib/vehicle_claims.py`. No longer exclusivity-gates mineral mining sites (see `mining.reserved_yield` below); still exclusive for survey/POI targets (key prefix `"poi_"`) and construction jobs (key prefix `"build_"`, `PioneerController.construction_claim_key()`, see §1a's construction-job-claims entry).
- `mining.reserved_yield`: Non-exclusive in-flight mining yield dict `{reservation_key: {"vehicle": id, "item_id": str, "units": int, "tick": tick}}`, home-demand mine-type missions only. Stale after `RESERVATION_STALE_TICKS = 36,000` ticks (same window as claims) — see `lib/mining_reservations.py`.
- `survey.unsupported_targets` / `rover.unsupported_targets` (mirrored): Hardware-capability blacklist entries (`reason`, `scanner_type`, `scanner_tier`, `hardness_limit`, unlocked researches) — see `lib/vehicle_claims.py`.
- `heat.optimal_setpoints`: Caching `{thermal_state: best_power}`
- `pressure.optimal_resonance`: Caching `{resonance_state: best_window}`
- `fabricator.manual_orders`: `{item_id: quantity}` ad-hoc Fabricator build requests, edited directly
  in the Notebook (e.g. `{"drone_small": 2}`) — see §2a-1 item 4. Prioritized over other demanded
  recipes and counted down to 0 (then dropped) as units are actually delivered.
- `outposts.known_ids`: List of outpost ids `panel_1.py`'s AUTOMATION section has already seen —
  diffed each throttled tick against `outpost_network.outposts()` to detect a newly-founded outpost
  and auto-trigger `outpost_mining.reevaluate_unassigned_near_outpost()` for it. See §7.

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
- `panel_1.py` (STATUS + AUTOMATION): **`2 x 2`** (1000x400) — STATUS alone only ever needed `2 x 1`,
  but the AUTOMATION card added below it (see below) needs its own vertical room; the script splits
  `panel.height()` ~55/45 between the two rather than assuming a fixed pixel split, so it still
  degrades reasonably at `2 x 1` (just cramped) rather than clipping outright.
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

**`panel_1.py`'s AUTOMATION card** — everything from §1a-1's centralized Power Grid supervision +
Smelter rebalance sweep, plus:
- **Outpost-founding → resource marker auto-reassignment**: diffs `outpost_network.outposts()`'
  current id set against the stored `outposts.known_ids` (archive, list — the only archive key this
  card adds) each throttled storage tick; any **new** id gets
  `outpost_mining.reevaluate_unassigned_near_outpost(new_id)` (§2d) called on it automatically.
  `sync_resource_markers.py` remains for manual backfill/batch catch-up.
- **Two independent throttle timers, not one shared `AUTOMATION_TICK_INTERVAL`** (an earlier version
  had a single combined interval): `SOLAR_TICK_INTERVAL = 10` ticks (~1s at 10 ticks/sec) gates grid
  supervision (`PowerGridManager.supervise_grid()` per grid — cheap, no Auto Feeder transfers
  involved, safe to run often); `STORAGE_TICK_INTERVAL = 100` ticks (~10s) separately gates
  `rebalance_inventory_to_warehouses()` + the outpost-diff/`consolidate_cross_warehouse_stock()` sweep.
  Splitting them out fixes a real contention risk a single fast shared interval would create: both
  `.transfer_to()` (rebalance) and `.compact()` (consolidation) lock their Warehouse as a material
  endpoint for the whole transfer duration (`docs/guide/input_and_output_ports.md`, and see
  `consolidate_cross_warehouse_stock()`'s own note above) — sweeping every Warehouse at every outpost
  on a ~1s cadence would mean a Warehouse could plausibly still be mid-transfer from the *previous*
  sweep when the *next* one starts, and would also cost a Smelter/Fabricator `take_item()` call a
  `"busy"` rejection (see `craft_prefill_units()` above) far more often than a slower cadence would.
  Grid supervision has no such cost, so it keeps the fast interval on its own timer instead of being
  held back by storage's slower one. The panel loop itself has no `sleep()` and redraws every render
  tick regardless — both intervals gate only the actual automation work via `clock.tick()`, not the
  redraw.
- **`panel.button("run_archive_cleaner", ...)`** — `ArchiveCleaner(dry_run=False, verbose=True).run()`
  (§4), live-commit, human-triggered only (never runs automatically on the throttled tick).
- **`panel.button("run_unsupported_markers", ...)`** — `lib/unsupported_markers.py`'s
  `update_unsupported_markers(clear_previous=True)` (promoted from `playground/mark_unsupported_targets.py`,
  which never actually ran in the live game since `playground/` isn't synced — also available as the
  thin root entrypoint `mark_unsupported_targets.py` for a manual standalone run). Also
  human-triggered only.

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
