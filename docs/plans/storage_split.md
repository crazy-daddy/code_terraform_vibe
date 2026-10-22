# Storage split implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `scripts/4_controlpanel/lib/storage.py` (1434 lines, 65 importer files) into three topic modules so no file exceeds the 1000-line scan limit and importers load only the topic they use.

**Architecture:** Pure moves, no logic change, same pattern as `ed156db` (`storage_sweeps`) and `6749e99` (`parking_client`). `storage.py` keeps the data layer (constants, discovery, snapshot, capacity, busy registry, smelt partners). Two new modules sit above it: `storage_take.py` (holder search and `take_item`) and `storage_unload.py` (`best_unload_target` and the send/drain/push path). Both import from `storage`; `storage` imports neither, and the two new modules never import each other, so no cycle and no function-level import is needed.

**Tech Stack:** game Python (see `CODE_GUIDES.md`: one-line imports, no stdlib, 10,000-step module body cap), `tests/` stub harness, Ruff, pyright via `devtools/scripts_sync.py resolve-preview`.

**Spec:** `docs/plans/code_quality.md`, section "Size scan triage (2026-10-22)": "Keep rule" paragraph and the first "Open follow-ups" bullet.

## Global constraints

- Work in a worktree: `python devtools/agent_worktree.py new storage-split`; edit only in `.claude/worktrees/storage-split`. Sync holds don't apply there. Merge only after the user approves, with `python devtools/agent_worktree.py merge storage-split -m "<subject>"`.
- Every commit green: `python -m unittest discover -s tests`, `.venv/Scripts/python.exe -m ruff check scripts tests autoplay devtools` and `ruff format` on the touched paths, `.venv/Scripts/python.exe devtools/scripts_sync.py resolve-preview` then `npx pyright`.
- Pure move: function bodies, docstrings and `swallowed(...)` labels stay byte-identical (`ed156db` kept the `storage.` labels in `storage_sweeps`; follow that, so `swallow.py` and `logging_errors.md` label examples stay valid). Only imports, the module header comments and references change.
- One-line imports with `# fmt: skip` when Ruff would wrap them; add each new module to the `I001` list in `scripts/ruff.toml` as `ed156db` did for `storage_sweeps`.
- New modules reuse `storage.log` (TreeConsole `module="storage"`), as `storage_sweeps` does, so one log level setting covers all four files.
- Module bodies stay cheap: the new modules hold only `def`s and a handful of scalar constants. Nothing with a loop or comprehension moves (the `_partners`/`_heat` tables stay in `storage`).
- Importer strategy: update every import site directly, no re-export shim in `storage.py`. A shim would keep every importer paying the full body cost, which is the point of the split, and both precedents updated sites directly.

## Call graph findings (basis for the boundaries)

Scripted from `ast` over `storage.py` plus a grep of every `from storage import` in `scripts/`, `tests/`, `autoplay/`, `devtools/` (65 files; the raw table is reproducible with a 60-line script, not kept).

- Names with the most importers all stay in `storage`: `inventory_count` (18), `outpost_is_home` (12), `discover_storage_buildings` (11), `local_port_target` (6), `inventory_room` (5), `total_stock`, `slot_layout`, `PENALIZED_TYPES` (4 each), `StorageSnapshot`, `BinStore`, `warehouse_stocks`, `inventory_stack_size`, `WAREHOUSE_STOCK_TARGET`, `forget_storage_discovery` (3 each).
- `take_item` (17 importers) and its helpers use only core names: `BinStore`, `discover_storage_buildings`, `outpost_is_home`, `recently_busy`, `mark_busy`, `log`, plus the crop automator block (whose only intra-module user is `_holder_candidates`).
- `best_unload_target` (15 importers) uses core names plus `inventory_room`, `inventory_part_room`, `must_stay_in_inventory`, `_items_demanded_by_active_dock_orders`, `item_heat`, `recipe_partners`. The drain/send/push functions use `best_unload_target`, `_materials` and core names. 7 of the 15 `best_unload_target` importers also import a drain or send name, and `eject_unneeded` needs `best_unload_target`, so target choice and drain share one module.
- Busy registry (`mark_busy`, `recently_busy`, `_recent_busy`) is used by take, unload, sweeps and `harvester_hub` (which otherwise imports only core names): stays in `storage`. `tests/harness.py` resets `storage._recent_busy`, `_DISCOVERY`, `_RETIRING`, `_UNLOCKED_OUTPUTS`: all stay.
- Smelt partner block (`SMELT_PARTNERS`, `ORE_HEAT_ORDER`, `_partners`, `_heat`, `recipe_partners`, `item_heat`, `_snapshot_clash`) is data used by unload and sweeps and imported by `early_buyer` and `tests/test_game_rules.py`: stays in `storage`.
- Inventory capacity block (`inventory_stack_size` ... `_items_demanded_by_active_dock_orders`, lines 1278-1434) depends on core constants and is used by core-only importers (`drone_hauler`, `field_keeper`, `site_evict`, `outpost_mining`, `production_demand`): stays in `storage`. A fourth module would save those importers nothing.
- No cycle risk from `storage`'s own imports: `components`, `archive`, `atomic`, `game_clock`, `game_rules`, `item_tiers`, `machine_controller`, `parking_client`, `swallow`, `tree_console` import nothing from `storage`. `production.py` imports from `storage`; `storage` names `production.SourceCache` only under `TYPE_CHECKING`, unchanged.

Rejected: separate `storage_target.py` and `storage_drain.py` (drain needs target anyway; one more module load for the heavy importers, no saving for anyone). Moving the crop automator block to core (its callers `stock_scan`, `harvester_amplify`, `crop_automator` all also import take names or already load `storage`).

## File structure

| File | Content (current `storage.py` line ranges, order kept) | Lines |
|---|---|---|
| `scripts/4_controlpanel/lib/storage.py` (keep) | 1-544 header, imports, constants, `outpost_is_home`, `local_port_target`, discovery and retiring registries, `BinSlot`, `BinStore`, `discover_storage_buildings`, `forget_storage_discovery`, `_retiring_entries`, `retiring_store_ids`, `set_retiring_stores`, `_scan_storage_buildings`, `slot_layout`, `slot_fill`, `slot_room`, `open_room`, `total_stock`, `inventory_count`, `warehouse_stock`, `stacks_stock`, `_stacks_rows`, `warehouse_stocks`, `_slot_rows`, `StorageSnapshot`, `_snapshot_holders`; 545-580 smelt partner block; 728-748 busy registry; 1278-1434 inventory capacity block | ~755 |
| `scripts/4_controlpanel/lib/storage_take.py` (new) | 751-819 `CROP_AUTOMATOR_TYPE_ID`, `CROP_AUTOMATOR_ITEM_ID`, `CROP_AUTOMATOR_CLOG_FRACTION`, `CROP_AUTOMATOR_STATUS_KEY`, `CROP_AUTOMATOR_WAKE_FREE_MIN`, `crop_automator_wake_free`, `crop_automator_forage`, `crop_automator_forage_total`; 826-979 `_live_holders`, `_holder_candidates`, `takeable_stock`, `take_item`; 982-986 `hit_slot_cap`; 1022-1034 `_take_from_current` | ~255 |
| `scripts/4_controlpanel/lib/storage_unload.py` (new) | 583-725 `_materials`, `_fill_fraction`, `_holder_count`, `_inventory_first`, `best_unload_target`; 823 `BUSY_TARGET_RETRIES`; 989-1019 `_staged_stacks`, `eject_unneeded`; 1037-1275 `send_stack`, `push_to_targets`, `top_up_target`, `top_up_bin`, `_send_to_best_target`, `drain_port_to_storage`, `drain_port_storage_first`, `INVENTORY_FULL_STATUSES`, `_drain_port_off_home`, `drain_port_inventory_first` | ~430 |

Imports of the new modules (one line each, derived from the moved bodies):

- `storage_take.py`: `components`, `from game_clock import now_tick`, `from game_rules import CROP_AUTOMATOR_OUTPUT_CAP`, `from machine_controller import port_counts`, `from parking_client import wake_for_visit`, `from swallow import swallowed`, `from storage import BinStore, discover_storage_buildings, log, mark_busy, outpost_is_home, recently_busy`. After the move `storage.py` drops `port_counts`, `wake_for_visit` and `CROP_AUTOMATOR_OUTPUT_CAP`.
- `storage_unload.py`: `from swallow import swallowed`, `from storage import FLEET_PART_KEEP, INVENTORY_FREE_SLOTS_KEEP, BinStore, _items_demanded_by_active_dock_orders, discover_storage_buildings, inventory_part_room, inventory_room, item_heat, local_port_target, log, mark_busy, must_stay_in_inventory, outpost_is_home, recipe_partners, retiring_store_ids`. No `components` use in these ranges; pyright will flag anything the derivation missed.
- `"OutpostRef"` string annotations resolve through the stubs as they do in `storage_sweeps.py`; copy no `TYPE_CHECKING` block unless pyright asks for `SourceCache`.

## Test and patch targets

`from storage import X` binds a copy of `X` in the importing module, so a test must patch the module whose code calls the name:

- `tests/test_crop_automator_output.py`: `mock.patch.object(storage, "crop_automator_forage" | "wake_for_visit" | "discover_storage_buildings", ...)` become `storage_take` (callers `take_item`, `_holder_candidates` live there); `storage.take_item` / `storage._holder_candidates` calls become `storage_take.*`.
- `tests/test_storage_drains.py`: `storage._holder_candidates` and its `patch.object(storage, "discover_storage_buildings")` become `storage_take`; `storage.send_stack`, `storage.drain_port_storage_first`, `storage.best_unload_target` become `storage_unload`. `patch.object(storage.components, "home_outpost", ...)` patches the `components` module object and stays.
- Module-attribute call sites to rename: `tests/test_storage_partners.py`, `test_storage_bins.py`, `test_inventory_reserve.py`, `test_haul_home.py`, `test_drain_busy.py`, `test_storage_retiring.py`, `test_slot_cap.py`, `test_direct_delivery.py`, `test_stock_scope.py`, `test_vehicle_unload.py` (`grep -n "storage\.\(take_item\|takeable_stock\|_holder_candidates\|hit_slot_cap\|crop_automator_\|best_unload_target\|drain_port_\|send_stack\|push_to_targets\|eject_unneeded\|top_up_\)" tests/*.py` lists them). Import the new module as `import storage_take` / `import storage_unload` next to `from harness import StubTestCase, storage`, as `tests/test_storage_snapshot.py` does for `storage_sweeps`.
- `tests/harness.py` unchanged.

## Review focus

Failure modes no existing test pins; each gets a verification step in the task that owns it:

1. A lib module still imports a moved name from `storage` and raises `ImportError` in game while CPython tests pass because a test imports the new module first: Task 1/2 step "grep for stale import sites" plus pyright (`reportAttributeAccessIssue` on the resolved copy).
2. A test patches `storage.<name>` that `storage_take`/`storage_unload` code no longer reads, so the patch silently does nothing and the test passes against live stubs: Task 1/2 step "grep `patch.object(storage`" and confirm each patched name is still called from `storage`.
3. A module-level cycle via a missed dependency: `tests/test_game_imports.py::test_no_import_cycles_between_lib_modules` runs in the suite; if it reports one, break it with a function-level import in the new module, never in `storage`.
4. Deployed `lib/` keeps old copies and `scripts_sync.py resolve-preview` output goes stale: run `resolve-preview` before every pyright run (per `CLAUDE.md`).
5. `size_scan.py` loses its pins for `take_item` and `best_unload_target` (keys change with the file): update the two keys in `devtools/code_scan/size_scan_ignore.txt`, keep the pinned metrics, and run the scan to confirm no unpinned or stale entries and no file hit for `storage.py`.

---

### Task 0: Worktree and baseline

**Files:** none edited.

- [ ] **Step 1:** `python devtools/agent_worktree.py new storage-split`; all later steps run inside `.claude/worktrees/storage-split`.
- [ ] **Step 2:** Baseline checks and numbers, recorded for the commit messages:
  - `python -m unittest discover -s tests` (all pass).
  - `python devtools/code_scan/size_scan.py` (expect the `storage.py` file hit, 7 function hits total).
  - Import cost: write a scratchpad script (pattern: the `sys.settrace` opcode counter in `devtools/perf/step_profile.py:39-70` or `tests/test_autoplay_geom.py:15-25`, with `tests/harness.py` on `sys.path` for stubs) that counts opcodes executed in `scripts/4_controlpanel/lib/*.py` during a fresh `import fabricator`, `import building_ops` and `import harvester_hub` (one process each, `importlib` not cached). Note the three totals and module counts. `step_profile.py` itself has no import mode; don't add one.

### Task 1: `storage_take.py`

**Files:**
- Create: `scripts/4_controlpanel/lib/storage_take.py`
- Modify: `scripts/4_controlpanel/lib/storage.py` (remove lines 751-819, 826-986 except 823, 1022-1034; drop the three unused imports; header comment names the new module), `scripts/ruff.toml`, `devtools/code_scan/size_scan_ignore.txt` (`lib/storage.py::take_item` → `lib/storage_take.py::take_item`)
- Modify import sites (`from storage import ...` split into two lines, names: `take_item`, `takeable_stock`, `hit_slot_cap`, `crop_automator_forage`, `CROP_AUTOMATOR_ITEM_ID`): `lib/bio.py`, `bio_volcanic.py`, `crop_automator.py`, `drone_depot.py`, `essence_liquifier.py`, `fabricator.py`, `feed_maker.py`, `field_provider.py`, `fuel_assembler.py`, `habitat.py`, `harvester_amplify.py`, `pioneer_stock.py`, `plant_terraformer.py`, `refiner.py`, `seed_maker.py`, `smelter.py`, `stock_scan.py`, `supply_dock.py`, `vehicle_cargo.py`, `autoplay/lib/blueprint_queue.py`
- Modify comments that say `storage.take_item()`, `storage.crop_automator_forage()`, `storage.takeable_stock()`, `storage.hit_slot_cap()`, `storage.crop_automator_wake_free()`, `storage._holder_candidates()`: `lib/plant_terraformer.py`, `crop_automator.py`, `harvester_machines.py`, `fuel_assembler.py`, `stock_scan.py`, `production_source.py`, `harvester_amplify.py`, `field_provider.py`, `feed_maker.py`, `storage.py` (its own cross-references), `autoplay/lib/blueprint_queue.py`; docs: `docs/cheatsheet/planting.md`, `production_logistics.md`, `vehicles_drones.md`, `dev_workflow.md`, `bio_seeds_planting.md`, `autoplay_outposts.md`, `archive_ipc.md`, `fabricator_demand.md`. Leave `swallow.py:12` and `logging_errors.md:63` (label examples, labels unchanged).
- Tests: `tests/test_crop_automator_output.py`, `test_storage_drains.py` (take half), `test_slot_cap.py`, `test_stock_scope.py`

**Interfaces:**
- Produces: `storage_take.take_item`, `takeable_stock`, `hit_slot_cap`, `crop_automator_wake_free`, `crop_automator_forage`, `crop_automator_forage_total`, `_holder_candidates`, `_live_holders`, `_take_from_current`, `CROP_AUTOMATOR_*` constants, `storage_take.log` (same object as `storage.log`). Signatures unchanged.

- [ ] **Step 1:** Create `storage_take.py` with a 4-6 line header comment (what the take path is, that it is split out of `lib/storage.py`, who calls it), the import lines from "File structure", then the moved blocks verbatim in their current order. Delete them from `storage.py`; drop `port_counts`, `wake_for_visit`, `CROP_AUTOMATOR_OUTPUT_CAP` from its imports; add one header sentence naming `storage_take.py`.
- [ ] **Step 2:** Update the import sites listed above (split the import line; keep core names on the `storage` line). `grep -rn "from storage import" scripts autoplay devtools | grep -E "take_item|takeable_stock|hit_slot_cap|crop_automator"` must return nothing.
- [ ] **Step 3:** Update tests: module-attribute calls and `patch.object` targets per "Test and patch targets". `grep -n "patch.object(storage," tests/*.py` must show only names still defined in `storage`.
- [ ] **Step 4:** `scripts/ruff.toml`: add `"4_controlpanel/lib/storage_take.py" = ["I001"]` if `ruff check` reports I001 on the one-line import. `size_scan_ignore.txt`: rename the `take_item` key.
- [ ] **Step 5:** Run `python -m unittest discover -s tests`; `ruff check` and `ruff format` on touched paths; `.venv/Scripts/python.exe devtools/scripts_sync.py resolve-preview` then `npx pyright`; `python devtools/code_scan/size_scan.py` (no unpinned or stale entries). Expected: all green.
- [ ] **Step 6:** Commit: `refactor(lib): split the take path out of storage into storage_take` with a body in the style of `ed156db` (what moved, what stayed and why, import sites). `python devtools/agent_worktree.py` has no commit helper; plain `git commit -F <scratchpad file>`.

### Task 2: `storage_unload.py`

**Files:**
- Create: `scripts/4_controlpanel/lib/storage_unload.py`
- Modify: `scripts/4_controlpanel/lib/storage.py` (remove lines 583-725, 823, 989-1019, 1037-1275; rewrite the header comment to describe the data layer and name both new modules and `storage_sweeps.py`), `scripts/ruff.toml`, `devtools/code_scan/size_scan_ignore.txt` (`lib/storage.py::best_unload_target` → `lib/storage_unload.py::best_unload_target`), `scripts/4_controlpanel/lib/storage_sweeps.py` (`_snapshot_clash`, `recipe_partners` stay on the `storage` line; `best_unload_target` moves to a `from storage_unload import best_unload_target` line)
- Modify import sites (names: `best_unload_target`, `drain_port_to_storage`, `drain_port_storage_first`, `drain_port_inventory_first`, `send_stack`, `push_to_targets`, `eject_unneeded`, `top_up_bin`): `lib/bio.py`, `bio_processor.py`, `bio_retire.py`, `bio_volcanic.py`, `crop_automator.py`, `drone_depot.py`, `essence_liquifier.py`, `fabricator.py`, `feed_maker.py`, `fuel_assembler.py`, `habitat.py`, `plant_terraformer.py`, `refiner.py`, `seed_maker.py`, `seed_supply.py`, `smelter.py`, `supply_dock.py`, `vehicle_cargo.py`, `warehouse_upgrade.py`, `waste_sink.py`, `devtools/play/clear_warehouse_playground.py`
- Modify comments that say `storage.best_unload_target()`, `storage.drain_port_*()`, `storage.push_to_targets()`, `storage.send_stack()`, `storage.eject_unneeded()`, `storage.top_up_bin()`, `storage.top_up_target()`, `storage._materials()`: `lib/warehouse_upgrade.py`, `vehicle_cargo.py`, `smelter.py`, `fabricator.py`, `drone_depot.py`, `drone_commission.py`, `production_cascade.py`, `storage.py`; docs: `docs/cheatsheet/storage_mining.md` (§2c heading line 5 names all three modules plus sweeps; the `storage.best_unload_target` ref), `production_logistics.md`, `wildlife.md`, `fleet_lifecycle.md`, `fabricator_demand.md`, `drones.md`; `TODO.md` (two refs).
- Tests: `tests/test_storage_drains.py` (unload half), `test_storage_partners.py`, `test_storage_bins.py`, `test_inventory_reserve.py`, `test_haul_home.py`, `test_drain_busy.py`, `test_storage_retiring.py`, `test_slot_cap.py` (`eject_unneeded`), `test_direct_delivery.py`, `test_vehicle_unload.py`

**Interfaces:**
- Consumes: nothing from Task 1 (the two modules are independent).
- Produces: `storage_unload.best_unload_target`, `eject_unneeded`, `send_stack`, `push_to_targets`, `top_up_target`, `top_up_bin`, `drain_port_to_storage`, `drain_port_storage_first`, `drain_port_inventory_first`, `_send_to_best_target`, `_staged_stacks`, `_materials`, `BUSY_TARGET_RETRIES`, `INVENTORY_FULL_STATUSES`. Signatures unchanged.

- [ ] **Step 1:** Create `storage_unload.py` (header comment, import lines from "File structure", moved blocks verbatim in current order). Delete them from `storage.py`; rewrite its header: data layer (discovery, snapshot, capacity, busy registry, smelt partners), take path in `storage_take.py`, unload path in `storage_unload.py`, sweeps in `storage_sweeps.py`.
- [ ] **Step 2:** Update import sites and `storage_sweeps.py`. `grep -rn "from storage import" scripts autoplay devtools tests | grep -E "best_unload_target|drain_port|send_stack|push_to_targets|eject_unneeded|top_up"` must return nothing.
- [ ] **Step 3:** Update tests per "Test and patch targets"; repeat the `patch.object(storage,` check.
- [ ] **Step 4:** `ruff.toml` I001 entry for `storage_unload.py` if needed; `size_scan_ignore.txt` key rename.
- [ ] **Step 5:** Same check battery as Task 1 step 5. Additionally `wc -l scripts/4_controlpanel/lib/storage*.py` (every file under 1000; `storage.py` about 755) and `size_scan.py` no longer lists `storage.py` as a file hit.
- [ ] **Step 6:** Re-run the Task 0 import-cost script. Expected: `building_ops` and `harvester_hub` totals fall (they no longer run the take and unload bodies); `fabricator` about equal (loads all three). Put the before/after numbers in the commit body, as `6749e99` did.
- [ ] **Step 7:** Commit: `refactor(lib): split the unload path out of storage into storage_unload`.

### Task 3: Docs map and plan bookkeeping

**Files:**
- Modify: `docs/cheatsheet/lib_map.md:181-182` (row 181 becomes "Storage data layer (discovery, snapshot, capacity, busy registry) | `storage.py` — see §2c"; add rows for `storage_take.py` "Take path: holder search over Inventory, Warehouses, Storage Bins and clogged Crop Automators, `take_item()`" and `storage_unload.py` "Unload path: `best_unload_target()` scoring, port drains, direct delivery `push_to_targets()`, bin top-up", both "— see §2c"), `docs/plans/code_quality.md` (first "Open follow-ups" bullet: mark done, name the two modules and line counts), `docs/design_history/logistics_production.md` (3-4 lines: why three storage modules and the boundary rule "data layer below, take and unload above, never sideways"; the hub `docs/DESIGN_HISTORY.md` already links the file).
- Not changed: `docs/00_Table_of_Contents.md` (lib modules are not listed there), `feature_scan_ignore.txt` (`StorageSnapshot`, `BinStore` stay in `storage.py`).

- [ ] **Step 1:** Edit the three docs; `python -m unittest discover -s tests -p test_docs_lint.py` passes (64 KB file cap, 16 KB section cap). No test checks `lib_map.md` coverage, so Tasks 1 and 2 stay green without these rows.
- [ ] **Step 2:** Commit: `docs(lib): map the storage split, close the code_quality follow-up`.
- [ ] **Step 3:** Hand off: report the three line counts, the import-cost numbers and the branch name. Merge only after the user approves: `python devtools/agent_worktree.py merge storage-split -m "refactor(lib): split storage into data layer, take and unload modules"`.

## Decisions (user, 2026-10-22)

1. Commit granularity: fold Task 3 into Task 2's commit, as the precedents did (two commits).
2. `swallowed()` labels keep the `storage.` prefix: a pure move that leaves `swallow.py` and `logging_errors.md` examples valid.
