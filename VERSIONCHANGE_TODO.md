# Version Change TODO: Experimental v0.1.29 (manual build 3b1b03e)

Temporary checklist for adopting the v0.1.29 changes (`changelog.txt`). Fold open items into
[TODO.md](TODO.md) or finish them, then delete this file.

## 1. Library redeploy via `apply-library` (top priority)

The external-IDE command channel (`.codeterraform/command.json`, already used by
`devtools/scripts_sync.py` for `create-library`) now accepts:

- `apply-library`: `{action, scriptId, source}`. `scriptId` is the library's id from the IDE
  context (`libraryScripts`).
- `apply-all-libraries`: no arguments.

Apply deploys saved Library edits AND restarts every script that imports them, the same as the
Computer's Library tab. It has live side effects (vehicles re-plan, machines restart).

- [x] Library ids: `context.libraryScripts` in `codeterraform-workspace.json` (`.source` = saved,
      `.deployedSource` = applied). Game handler reverse-read from `internals/raw_assets`.
- [x] `scripts_sync.py`: `apply_pending_libraries()` behind `--apply-libs` (once/watch) and a
      standalone `apply-libs` command; per-library results reported.
- [x] Recovery: `recover_scripts()` restarts held-back slots and scripts left in `error` that the
      tool pushed or that reach a lib it changed, once their libs are applied; one retry per
      source/applied-lib state.
- [x] Docs: dev_workflow.md §8 and sync section.
- [x] Live test 2026-09-30: `apply-libs` applied `archive_cleaner`, `profiling` via
      `apply-all-libraries`, 1 importer restarted, 0 crashed. `runtimeRunSerial` is a per-script
      run counter (values 1..262 across scripts), so recovery's stale-status check holds.
- [x] Live test of `once --apply-libs` with a real lib change, and of crash recovery (a lib
      change that breaks an import mid-apply).
- [x] "Lib redeploy" memory updated.
- [ ] Decide: make `--apply-libs` the default.

## 2. Signal Bus 512 channels / Data Archive 2,048 entries

- [x] Docs split refreshed; archive-cap comments and dev_workflow §1d updated to 2,048.
- The one-dict-per-concern archive rule in CLAUDE.md stays: the cap is higher, not gone.

## 3. Choosing a charging station: `dock(station)` / `current_station()` (Pioneer, Rover)

Matters once a base has more than one Vehicle Charging Station. Without a choice, the vehicle docks
at the nearest eligible station (ties alphabetical by id).

- [x] `lib/vehicle_energy.py`: `balance_dock()` spreads parked vehicles across an outpost's
      stations by load per bay with `dock()`; `recharge_at_station()` reads `current_station()`
      instead of scanning `get_docked()`. vehicles_drones.md §2a.
- [ ] Live check once an outpost has a second Vehicle Charging Station.

## 4. Drone `modules()` for fleet hardware upgrades

`drone.modules() -> list[MountSlot]`, like the Pioneer.

- [x] `lib/drone_upgrade.py` reads slots with `modules()` (`_read_slots()`); the `drone.loadouts`
      record and the uncouple survey are gone, the key is retired in `ArchiveCleaner`.
      `couple()`/`uncouple()` update `mountedModules` within the call (decompiled `mD`/`gD`).
- [ ] Live check: next in-place upgrade or chassis fitting reads the right slots.

## 5. Panel methods (low priority, for real UI work)

`get_switch` / `get_slider` / `get_selected` / `get_text` (read without drawing),
`last_bounds()`, `measure_text()`, `texture` / `draw_texture`, CSS colours.

- [ ] Later: replace pixel-width guesses (`INTENT_CHAR_PX` etc. in `vehicles_panel.py` /
      `drones_panel.py`) with `measure_text()`.

## 6. Smelter `is_running()` semantics

`is_running()` can now be `False` while an unfinished unit is paused (e.g. output full); progress
is kept, and the docs point to `get_progress()` before changing recipes.
[smelter.py:405](scripts/4_controlpanel/lib/smelter.py#L405) switches recipe whenever
`not is_running()`.

- [x] Verified in the decompiled simworker: Smelter and Fabricator `set_recipe` return `busy`
      when switching to another recipe with `progress > 0`; `clear_recipe` (`k4`) does the same.
      Progress is never lost. Documented in production_logistics.md §2a-1c.
- [x] No guard needed: both controllers treat non-`ok` as "retry next poll".

## 7. Language changes

- [x] Cheatsheet: `isinstance`/`issubclass` with game classes after `from __builtins__ import`,
      class patterns in `match`, `# type: ignore` / `# noqa` in the in-game editor, new modules
      (`math`, `itertools`, `operator`, `string`, `collections`).

## 8. Suspended generators in panel scripts

- [x] Fixed in game: generator frames now save and restore `loopDepth` on suspend/resume
      (`enterGeneratorFrame`/`exitGeneratorFrame` in the decompiled simworker), and the repro
      (`next(<genexpr>)` before the loop) keeps updating live. Panel rule removed from
      `docs/cheatsheet/panels.md`.
- [ ] Optional cleanup: list-comprehension workarounds in panels can go back to `any()`/`next()`
      where that reads better. No hurry.

## Automations tab (Computer > Automations, 50k TP, researched)

Scripts that belong to no machine: no `self`, no `panel`, no power supply (never paused by a
brownout), restart with the game, 50 per save. See
[docs/guide/automations_guide.md](docs/guide/automations_guide.md).

- [x] Slot file: `automation_N.py` at the save root (id `automation_N`), listed in the workspace's
      `context.automations` and in `codeterraform-scripts.json` like any script.
- [x] `run_control` is machine-only (`f4()` looks up `state.machines`): `start`/`stop` return
      `not_found`, so automations must be always-on. The external `run` command works (generic
      script lookup).
- [x] `scripts_sync.py`: `automation` added to `ROLE_MATCHED` (`# ct-automation: <role>` marker,
      sources `scripts/4_controlpanel/automation/<role>_automation.py`).
- [x] Moved `automation_panel.py` -> `control_room_automation.py` and `warehouse_upgrade_panel.py`
      -> `warehouse_upgrade_automation.py`; panels.md §7, dev_workflow §9, AI_CHEATSHEET map,
      comments, DESIGN_HISTORY §7b updated.
- [x] TODO.md's "busy call wedges the card" item reworded: no longer affects the calculator.
- [x] In game: old headless Custom Panels deleted, `automation_1`/`automation_2` created with
      markers. Deleted panels keep their `.py` file; `unassigned_slot()` skips them.
- [x] Run `once --apply-libs` (18 libs pending, mostly comment renames) so both automations
      start.
- [x] Watch one brownout: grid supervision keeps running.
- Running-script count is unchanged by the move (an automation is still a running script).
