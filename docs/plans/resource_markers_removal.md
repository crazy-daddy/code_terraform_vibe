# Plan: replace resource markers with demand-driven mining

## Context

Manual run 2026-10-18 #72: no mining markers were set. Cause: `outpost_mining` assigns sites only to outposts with the `mining` role, within 200 m; the factory outposts had no role. The operator wants markers gone: miners already pick sites by cost, so a NEED gate makes the marker obsolete.

Validation (Explore pass) confirms markers do three jobs today, all replaceable:
1. **Ore filter**: a stationed Pioneer mines only marker-assigned ores (`vehicle_mining.py:241`), up to `ore_stock_target` with no demand (`stockpile_headroom`, `:253`, `:370`).
2. **Site filter**: only sites whose note names the outpost (`vehicle_mining.py:284`). The ranking itself (`select_best_mining_target` `:449`, `mining_hours_per_unit` `:335`) already weighs purity vs round-trip drive, battery-bound.
3. **Routing "who mines ore X"**: `remote_ore_need` (`vehicle_mining.py:402`), `dock_ore_levels` (`site_supply.py:777`), `stranded_ore` kept set (`site_supply.py:841`), `DockRoles` ROLE_MINE (`supply_dock.py:336-362`), `pioneer_upgrade._split_sites` (`:273`, already has a nearest-outpost fallback).

Side finding: before Cartography (140k TP) there is no `markers` component, so stationed Pioneers mine **nothing** today. This change fixes that too.

Decisions (operator): no hardcoded ore order; never unassign; **latch + buffer**; old markers removed by an `ArchiveCleaner` stage and the panel's "Sync Unsupported" (redraw) button.

## Design

### A. Active-ore latch (`outpost_mining.py`)
- Archive key `mining.active_ores` (list of ore ids). `active_ores()`, `latch_active_ores(ores)` (add-only, write only on change).
- Latched once per site_supply plan pass: every raw ore with a NEED-or-higher level at any outpost after planning (Fabricator ore shortfall, dock ore, `dock_raw_wants`), plus the ore of any NEED+ ingot want. Hook in the pass that builds `planned_requests` (`site_supply.py` ~1280). Also latch in `vehicle_mining.stockpile_bands` NEED+ ores (catches rover/home demand).
- Order emerges from demand: iron first, silicon on first glass need, titanium when demanded *and* a drill cuts it (gate B).

### B. Mining reach (published by each Pioneer, read by planners)
- In `build_local_stockpile_candidates`, the Pioneer already knows its drill limit (`:260-266`, `item_tiers.can_cut`) and battery. Compute `reach_ores` = ores with a surveyed site it can cut whose round trip fits a full battery (reuse the energy check used by `select_best_mining_target` `:498-553`).
- Publish per vehicle: `mining.reach[vehicle] = {"outpost": home_base, "ores": [...], "tick": t}` (write only on change, refresh tick at `REQUEST_STALE_TICKS` cadence).
- `outpost_mining.mineable_ores_by_outpost()` aggregates fresh entries (stale or gone vehicles dropped); `mineable_ores(outpost_id)`. Archive-based so `site_supply`/`supply_dock` don't import `vehicle_mining`.
- `ArchiveCleaner.clean_telemetry`-style purge of entries for gone vehicles.

### C. Stationed miner (`vehicle_mining.py`)
- Ores: `need` (NEED+ bands, unchanged) ∪ headroom for **active** ores only, and only while the outpost holds a slot of that ore or has a free store slot beyond a reserve of 1 (`storage.slot_layout()`).
- Sites: every surveyed site of those ores the drill cuts; drop the marker check at `:284`. Ranking unchanged.
- `remote_ore_need`: `mine` = this Pioneer's `reach_ores` instead of assigned ores.
- Fix stale docstring `:227-230`.

### D. Planners
- `site_supply.py:716` STOCK floor: only for active ores, same slot-room rule.
- `dock_ore_levels`: `assigned_ores_by_outpost()` → `mineable_ores_by_outpost()`; same "first refining site by id" order.
- `stranded_ore` kept: marker ores → `mineable_ores(site) ∩ active_ores()` (else a mining outpost's buffer is evicted and re-mined in a loop).
- `DockRoles.site/covers`: marker ores → `mineable_ores_by_outpost()`.
- `pioneer_upgrade._split_sites`: drop marker branch, keep `nearest_outpost_id`.

### E. Removal + cleanup
- Delete marker write/read code in `outpost_mining.py` (keep `ore_stock_target`, `nearest_outpost_id`, `resource_assignment_range_m`: still used by `vehicle_survey.outpost_weights` and `autoplay/lib/outpost_needs.py`).
- Remove `auto_assign_new_site` call (`vehicle_survey.py:113-120`), backfill/sweep (`orchestrator_automation.py:424-434`; keep `update_unsupported_markers`), `harvesting/sync_resource_markers.py` (operator deletes the deployed copy by hand).
- `ArchiveCleaner.clean_resource_markers()`: remove every `markers.list("resource.")` entry; new `_stage` in `_run_stages`. Call it also from the status panel "Sync Unsupported" button path (`status_panel.py:133`).
- `mining` designation stays (founding/deploy hint for autoplay), no longer gates mining.

## Sessions (per split-big-plans rule)
0. **Session 0 (done)**: wrote this plan with a "Handoff" section (status, next session's start point, validated file:line map). Link it from `TODO.md` C. Then halt: `/clear` point.
1. **Session 1**: A, B, C, D-716. Markers still written; remaining planners still read them. Tests for latch, reach aggregation, miner ore/site selection.
2. **Session 2**: rest of D, E, docs. Move plan to `docs/plans/done/` with TODO C.

Each session ends by updating the Handoff section, then halts for `/clear`.

## Workflow
- Delegate per `cavecrew`: `cavecrew-investigator` for locating, `cavecrew-builder` for bounded 1-2 file edits; multi-file and design work inline.
- Before each commit: `cavecrew-reviewer` on the diff; fix findings, then commit (`caveman-commit`), only when the operator asks.

## Files
- `scripts/4_controlpanel/lib/outpost_mining.py`, `vehicle_mining.py`, `site_supply.py`, `supply_dock.py`, `pioneer_upgrade.py`, `vehicle_survey.py`, `archive_cleaner.py`
- `scripts/4_controlpanel/automation/orchestrator_automation.py`, `control_panel/status_panel.py`, delete `harvesting/sync_resource_markers.py`
- Tests: replace `tests/test_outpost_mining_reassign.py`; update `test_mining_need_tier.py`, `test_site_supply.py` (274-352), `test_factory_sites.py` (1253-1279)
- Docs: `docs/cheatsheet/storage_mining.md` §2d (new keys `mining.active_ores`, `mining.reach`), `vehicles_drones.md` (319, 333), `panels.md:43`, `docs/DESIGN_HISTORY.md` (why markers went), `TODO.md` C

## Verification
- Sync hold around multi-hunk `scripts/` edits.
- `python -m unittest discover -s tests`; `ruff check` + `ruff format` on touched paths; `devtools/scripts_sync.py resolve-preview` then `npx pyright`.
- Live: fresh run, pre-Cartography. Check a stationed Pioneer mines iron on first NEED, `mining.active_ores` grows iron → silicon → titanium, no STOCK floor for unlatched ores, no buffer when slots are full. After Session 2: `resource.` markers gone after the cleaner runs; dock raw-ore orders still covered by a mining outpost's dock.

## Handoff

**Status (2026-10-19):** Sessions 0-2 done. Session 1: 12665ea. Session 2 (branch `agent/markers-removal`):
- `site_supply.py`: `dock_ore_levels(..., tick)` on `mineable_ores_by_outpost()`; `stranded_ore(..., tick)` keeps reach ∩ `active_ores()`.
- `supply_dock.DockRoles`: `_mined_ores` from `mineable_ores_by_outpost()`. `pioneer_upgrade._split_sites`: nearest outpost only.
- Marker code gone: `outpost_mining.py` write/read helpers, `vehicle_survey` survey hook, orchestrator backfill/sweep (unsupported backfill kept), `harvesting/sync_resource_markers.py` (operator deletes the deployed copy by hand).
- Cleanup: `unsupported_markers.clear_resource_markers()`, called by `update_unsupported_markers(clear_previous=True)` (once-per-run backfill, panel "Sync Unsupported") and the `ArchiveCleaner.clean_resource_markers()` stage.
- Tests: `test_outpost_mining_reassign.py` removed; reach-based cases in `test_site_supply.py`, `test_factory_sites.py`; cleaner tests in `test_mining_active_ores.py`.
- Docs: storage_mining.md §2d/dock roles/dock ore/eviction, vehicles_drones.md, panels.md, AI_CHEATSHEET index, DESIGN_HISTORY §2d.

**Next:** live validation per "Verification" (fresh pre-Cartography run; on an old save, `resource.` markers gone after the cleaner or "Sync Unsupported"). Then move this plan to `docs/plans/done/` and TODO C to `TODO_done.md`.
