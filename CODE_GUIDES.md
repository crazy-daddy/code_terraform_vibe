# Code Guides

Rules for everyone who edits code in this repo. Numbers, formulas and module maps live in [docs/AI_CHEATSHEET.md](docs/AI_CHEATSHEET.md) and its [docs/cheatsheet/](docs/cheatsheet/) files; this file links to them rather than repeating values. Code comments cite these rules as `CODE_GUIDES.md#<section>`, so keep the section headings stable.

## Scope

- Machine scripts run existing machines and coordinate them. They don't set machines up.
- Exceptions: deploys from a control panel that need operator input, and undeploying machines whose step is finished.
- Founding outposts happens only in `autoplay/`. Each founding raises the cost of the next outpost (outposts can be decommissioned, so it is not permanent). Code that founds an outpost logs why in its `debug()` trail.

## Portability

- Plan save-agnostic. Code must work on an empty map and on a crowded one.
- Discover at runtime: capability probing, building discovery via `outpost_network`, location queries. No hardcoded save-specific ids or coordinates.
- Decide only from data a script can read in game: components, `points_of_interest()`, `journal`, the archive. Never hardcode world knowledge or read the save file to drive behavior.
- Exempt: formulas and fixed game limits (kit prices, building caps, fixed rates).
- A live save shows how a mechanic works. It doesn't show which cases matter, so don't rank a case as rare because the current save already handles it.
- Partly known world data (unsurveyed sites): use runtime-derived priors with a confidence value, or request a survey trip. Don't guess.

## Game interpreter

The game runs a restricted Python interpreter. CPython, Pyright and the offline tests accept code that fails in game.

- Import only our own `lib/` modules and the game modules listed in [dev_workflow.md §10](docs/cheatsheet/dev_workflow.md). No standard library (`time`, `copy`, `os`, `sys`, ...). Enforced by `tests/test_game_imports.py`.
- No module-level import cycles between `lib/` modules. In game, `from X import NAME` gets a half-loaded module and raises `ImportError`. Break a cycle by importing inside the function that needs it. The same test checks the highest tier's copies.
- One-line imports only. The game parser rejects `from x import (a, b)`.
- Check a builtin before using it: "Built-in Functions" in [docs/guide/builtins_and_commands.md](docs/guide/builtins_and_commands.md) and [docs/guide/language_reference.md](docs/guide/language_reference.md). Known missing: `frozenset` (use a tuple), `id()`. Enforced by `tests/test_game_builtins.py`.
- No `with` statements. Don't rely on `finally`: a stopped script is killed without unwinding.
- Unsure about other syntax: check that an existing lib already uses it live.
- Hardware-changing calls on another machine (e.g. `input.eject()`) work only from that machine's own script, even when the docs don't say "self only". A remote script may read (`count()`, `stacks()`) and use `run_control`. Coordinate cross-machine changes through the archive or Signal Bus.

## Module layout

- Source lives in `scripts/<tier>/`. `lib/x.py` means the logical module `x`, physically at `scripts/<tier>/lib/x.py` for the highest tier that defines it ([dev_workflow.md §9](docs/cheatsheet/dev_workflow.md)).
- Put reusable logic in small, focused `lib/` modules ([module map, cheatsheet §0](docs/AI_CHEATSHEET.md)).
- Entrypoint scripts (`solar.py`, `rover.py`, `status_panel.py`, ...) stay thin. They use shared controllers from `lib/` and never keep their own copies of tier lists, thresholds or budget formulas.

## Mixins

- Controllers composed of mixins (vehicle, drone, pioneer, harvester, plant terraformer, ...) type `self` through one `_host` property per mixin:
  ```python
  if TYPE_CHECKING:
      from vehicle import VehicleController

  class VehicleMiningMixin:
      @property
      def _host(self) -> "VehicleController":
          return self  # type: ignore[return-value]
  ```
  Methods use `self._host.<attr>`, including `self._host.log`.
- Don't use a fake base class (`_Base = Controller if TYPE_CHECKING else object`). It creates an inheritance cycle at the composition site.
- After changing mixin typing, run Pyright on the composition site (`lib/vehicle.py`, `lib/drone.py`, ...), not only on the mixin file.

## Errors

- Probe capabilities at runtime and handle missing or unpowered components.
- Every `except Exception` that recovers calls `swallowed(where, error)` from `lib/swallow.py` as its first line. A broad except can't tell a missing component from a bug in our own call. Usage and the allowed exceptions: [cheatsheet §0b](docs/AI_CHEATSHEET.md).

## Archive

The Data Archive has a fixed key-count cap that doesn't grow with fleet or building count. Keys and conventions: [archive_ipc.md §4](docs/cheatsheet/archive_ipc.md).

- One shared dict per concern, never one key per entity. Store per-entity state as `{entity_id: value}` under one key (e.g. `vehicle.recall`, `drone.home_depots`), written via `archive.transaction()`.
- Prune entries for entities that no longer exist.
- Keep data bounded: fixed-size histories, compact summaries, JSON-safe structures. No large binary data or unbounded logs.
- Use the archive for telemetry, production history and order tracking, so every component sees one consistent state.
- Persist enough state to resume after a power loss or restart. Example: a smelter mid-production resumes its run; a rover in transit resumes its trip and finishes the mission.

## Signal Bus

- Use the Signal Bus (`get_component("comms")`) for real-time orders and event broadcasts. Check message age with `latest_info()` and treat stale messages as missing.
- When a publisher is missing or stale, fall back to reading the component directly.

## Logging

Use `TreeConsole` (`lib/tree_console.py`) for all console output, never ad hoc `get_component("console").print()`. Pattern and format: [cheatsheet §0a](docs/AI_CHEATSHEET.md).

- Info level: major blocks and outcomes, skimmable at a glance.
- `debug()`: the decision trail: which branch was taken, candidates considered and rejected, computed thresholds and estimates. With debug on, the log tells the whole story of a run.
- `trace()`: per-item and hot-loop detail. Never put per-item lines at info level, also not in one-off probe scripts. Prefer aggregates (counts, group-by) to listing items.
- Every console call costs 0.1 s of simulation time, even when hidden ([docs/BENCHMARK.md](docs/BENCHMARK.md)). `TreeConsole` buffers consecutive debug lines into one message. Call `log.flush()` before every `sleep()`.
- Wrap each coherent unit of work (trip, order cycle, build, sweep, active tick phase) in `log.start(...)` … `log.end(<outcome>)`. Close every `start()` on every path: early `return`, error branch, `continue`, `break`. Enforced by `tests/test_log_blocks_balanced.py`.
- Each top-level `run*` loop starts every tick with `reset_all()`, because an escaping exception leaves a block open (`tests/test_reset_in_run_loops.py`).
- No block on an idle tick.

## Script cost

Above 50 running scripts, every running script (sleeping ones included) shrinks every other script's step allowance. The count matters, not how busy each script is. Model and numbers: [dev_workflow.md §1d-1](docs/cheatsheet/dev_workflow.md), measurements in [docs/BENCHMARK.md](docs/BENCHMARK.md).

- Don't add a running script where an existing one can do the work.
- Prefer scripts that end when their machine has nothing to do and get restarted (`run_control.start()`) when it does, where the machine's idle state is acceptable.
- Cache discovery and pure geometry. Compute shared results once centrally (the `control_room_automation.py` Automation, published to the archive), not in every instance.
- Replace per-item Python loops with builtins and comprehensions.
- Optimizing tick cost, in this order:
  1. Cut real work: repeated reads of the same key or discovery inside a loop, per-item calls that one bulk read covers (`stacks()` over one `count()` per item), repeated walks that one pass covers.
  2. Then consider `lib/atomic.py` (`run_atomic`/`run_batched`/`run_chunked`) for the remaining read-only, non-logging work. It avoids the per-tick step limiter but doesn't reduce work. Each callback is capped at 10,000 steps; exceeding the cap ends the script. No writes, archive writes, scans, sleeps or console calls inside a callback. Size chunks with `devtools/step_profile.py`.

## Domain invariants

Implement these exactly as the linked sections describe; don't second-guess them.

- **Power grid**: tiered load shedding by `PowerGridManager` (`lib/power.py`). It is deliberately not "protect terraforming first". Tiers and thresholds: [power_fluids.md §1a](docs/cheatsheet/power_fluids.md).
- **Vehicles and drones**: [vehicles_drones.md](docs/cheatsheet/vehicles_drones.md).
  - There-and-back energy budget with a safety margin, a hard emergency-reserve floor and per-vehicle calibrated Wh/m (`lib/vehicle_energy.py`, §2a).
  - Atomic site reservations in the archive with heartbeat renewal and timeout expiry (`lib/vehicle_claims.py`).
  - Deadlock and terrain-stall detection, staggered base staging slots (`lib/vehicle_navigation.py`).
- **Production**: demand-driven ([production_logistics.md](docs/cheatsheet/production_logistics.md), `lib/production.py`).
  - Harvest and mine to match active recipe and Earth order deficits. Don't overproduce when inventory or storage is full.
  - Plan ahead from current and upcoming orders, placed blueprints and available resources.

## Documentation

- Comments, docstrings and the cheatsheet describe what the code does now, plus any non-obvious constraint. No narration: no "previously X", "now Y", "was changed because", "bug fixed on …", "found live". Remove narration you find in files you touch.
- The reason for a change goes in the commit message. Lasting design decisions go to [docs/DESIGN_HISTORY.md](docs/DESIGN_HISTORY.md).
- A tunable constant (margin, tier, threshold, stale-tick count, budget) has one documented home in the cheatsheet. Update it in the same change as the code. Elsewhere, link to it or name the constant.

## Tests

- Offline suite: `python -m unittest discover -s tests`. Details: [dev_workflow.md §10](docs/cheatsheet/dev_workflow.md).
- Extend the shared fake world in `tests/game_stubs.py`; never add a private fake.
- A bug found in game: name the general mechanic behind it, check every other place it can hit, and fix or report those too. Model the mechanic in the shared fakes so every controller's tests can exercise it.

## Commits

- [Conventional Commits](https://www.conventionalcommits.org/): `<type>(<scope>): <imperative summary>`. Types: `feat`, `fix`, `refactor`, `perf`, `docs`, `test`, `chore`, `build`, `ci`, `style`, `revert`.
- Subject: imperative, 50 characters when possible, 72 at most, no trailing period.
- Body only when needed: the non-obvious why, breaking changes, migration notes. Wrap at 72.
- State intent; the diff shows what changed.
