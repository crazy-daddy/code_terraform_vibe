# Controller unification (clone scan, 2026-10-05)

## Context
Third near-duplicate survey, now `devtools/clone_scan.py` (1830 functions, 805 pairs >= 0.85, 59 clusters). Diffed the top clusters by hand; pairs judged "keep apart" are in `devtools/clone_scan_ignore.txt`. Four steps, one commit each, in this order. Re-read the named files first (line numbers drift), sync hold around multi-file edits, cheatsheet module map updated in the same change.

## 1. `game_clock.now_tick()`
~40 files carry their own `_now_tick()` / `get_current_tick()` / `_current_tick()` / `_tick()` / `_clock_tick()` / `tick()`: the same `clock.tick()` in try/except + `swallowed()`, differing only in the label.
- New tier-4 module `lib/game_clock.py` (not `components.py`: that module is typed component accessors). `now_tick(where="game_clock.now_tick")`: clock looked up once per module and cached, returns 0 when there is no clock. `where` is optional; the cause of a failure is always the same (no clock).
- Callers import it; methods named `get_current_tick()` that other modules call stay as one-line delegates or get their callers renamed (grep first).
- Out of scope: tier 0 scripts (cannot import `lib/`).

## 2. `archive.publish_status()` for per-machine status dicts
About 15 machines publish `{machine_name: entry}` dicts, in three styles:
- `archive.set_entry_pruned` + warn/pruned log (mining_drill, plant_terraformer).
- Own transaction with stale prune (crop_automator, field_provider, refiner, habitat, feed_maker): same rule, written by hand. `>` vs `>=` and `wc.fresh()` vs inline check are accidental. `STATUS_STALE_TICKS = 36000` is defined 7 times.
- Own transaction or `set_entry` with no prune:
  - field_keeper (`plant.status`), seed_maker/seed_supply (`seed_maker.status`): no prune and not in `archive_cleaner.MACHINE_STATUS_KEYS`, so entries of sold machines stay forever (leak). Accidental: give them the stale prune.
  - biomass_mixer, essence_liquifier, waste_sink/water_sink, drone_depot: pruned by building existence in `archive_cleaner.MACHINE_STATUS_KEYS`. `drone_depot.status` keeps that (`stale_ticks=None`): its entries have no `tick`, and `fleet_upgrade` reads `get_entry(DEPOT_STATUS_KEY, new_id)` as "the new depot's script is running", so dropping a parked depot's entry would make it restart that script. Drones find depots through `discover_drone_buildings()`, not this dict. The other three (checked 2026-10-05) have no reader that depends on quiet entries: `biomass_mixer.status`, `essence_liquifier.status`, `waste_sink.status` are write-only telemetry (shown in the archive view); only `biomass_retire` pops an entry on retire, and `water_sink` reads its own entry back to add a `water` sub-dict. They move to `publish_status()` with the tick prune, and their entries gain a `tick` field. `water_sink` builds its entry from the base entry instead of reading the archive back (two writes per step become one).
- `archive_cleaner` cleans leftovers of every per-machine status key by building existence, not only the 6 in `MACHINE_STATUS_KEYS`: add `plant.status` (harvester), `seed_maker.status` (seed_maker), `plant.automators`, `plant.providers`, `plant.terraformer`, `drill.status`, `refiner.status` with their type ids (check each key's writer for the id it uses; the Harvester's is its machine id). The writer-side tick prune drops quiet entries; the cleaner drops entries of sold buildings and existing leftovers in old saves. A test asserts every `*.status`-style key written via `publish_status()` is listed in the cleaner.

Plan: `archive.publish_status(key, name, entry, tick, log, stale_ticks=STATUS_STALE_TICKS)` = today's drill/terraformer body (warn on rejected write, debug line per pruned id); `stale_ticks=None` = no tick prune (existence-pruned keys). One `STATUS_STALE_TICKS` in `archive.py`; the per-module copies go. Caller-side throttles (interval, change+refresh) stay with the callers in this step; step 3 can fold the change+refresh variant in. Check every reader of a key that gains a prune (`grep` the key) for code that expects entries of quiet machines.

## 3. `MachineControllerBase` mixin
For the single-machine controllers (feed_maker, fuel_assembler, refiner, habitat, smelter, fabricator, steam_turbine, steam_condenser, reactor, waste_sink, ...):
- `run()` template driven by class attributes (`LABEL`, `POLL_S`, `IDLE_POLL_S`, optional parker). 19 `run()` loops today differ only in label and poll. `tests/test_reset_in_run_loops.py` must accept the template (reset sits in the base loop).
- `tick()` on top of `now_tick()`; `output_counts(port)` (feed_maker, fuel_assembler, habitat.held, seed_maker._chamber); `publish_status()` forwarding to step 2.
- Attribute names differ (`self.maker`, `self.machine`, `self.pump`, `self.cap`): helpers take the port/machine as an argument instead of renaming attributes.
- Migrate a few controllers first, then the rest; controllers with extra loop logic (harvester, field_keeper, supply_dock) keep their own `run()` if the template does not fit cleanly.

## 4. Fleet: `FleetUnitMixin` + panel helpers
Drone and Vehicle stay separate stacks (navigation, energy, cargo really differ). Shared, thin mixin in a new `lib/fleet_unit.py`, configured by class attributes (`MISSION_KEY`, `RECALL_KEY`, noun):
- `set_intent`, `publish_telemetry` (same `fleet.status` shape; drone adds `unit`/`engine`, vehicle adds `home`: a hook for extra fields), `is_recalled`, `save_mission`/`load_mission` on top of `fleet_claims_common`.
- `drones_panel.py` / `vehicles_panel.py`: `outpost_names`, `draw_assignment`, `synced_switch` move to `fleet_status.py` next to `wrap_text`.

## Verification
- `python -m unittest discover -s tests` and `npx pyright` after each step (regenerate `.pyright-resolved` first after lib edits).
- New tests: `now_tick` (no clock, raising clock), `publish_status` (prune / no prune / rejected write), the run template via an existing controller fake.
- `python devtools/clone_scan.py`: the migrated clusters drop out.
- Finished: move this plan to `docs/plans/done/`, TODO items to `TODO_done.md`.
