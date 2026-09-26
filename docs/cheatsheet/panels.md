# Control Room Panels (§7)

Part of [`AI_CHEATSHEET.md`](../AI_CHEATSHEET.md).

## 🖥️ 7. Control Room Panel Cards (`panel_1.py`..`panel_6.py`)

**Headless calculator + UI card split (`panel_4.py` + `panel_1.py`).** Automation calculator (grid supervision, rebalance sweep, outpost sync, `supply_dock.plan_dock_assignments()`, fleet hardware upgrade §2k) is **headless**: no `panel.*` calls, paced by `sleep(1.0)`. It publishes result summary to `archive` (`AUTOMATION_SUMMARY_KEY = "control_room.automation_summary"`). STATUS/AUTOMATION UI card reads that summary back, doesn't compute it. Reason: multi-second automation stall must never block script that renders every tick. Custom Panel is only slot that can host "always-on, not tied to one building" process. Background: `DESIGN_HISTORY.md`.

**⚠️ Two separate numbering schemes, don't mix them up.** Game's Custom Panel ids assigned on creation, **only ever increment**. Deleting panel doesn't free its number. Cards **can't be drag-reordered** once placed. Live slots `panel_4.py`/`panel_6.py`/`panel_8.py` are dead (deleted panels; numbers never reused). *Source-tree* files under `scripts/4_controlpanel/control_panel/` are numbered by role (`panel_1.py`..`panel_6.py`, see [dev_workflow.md §9](dev_workflow.md)) — dev-side naming only, decoupled from live-slot numbers.
Current mapping (verified live; live-slot column authoritative for actual save):

| Role | Source-tree file | Live save slot | Notes |
| :--- | :--- | :--- | :--- |
| STATUS + AUTOMATION UI | `panel_1.py` | `panel_1.py` | top of Control Room |
| FLEET (ground vehicles) | `panel_2.py` | `panel_2.py` | |
| PRODUCTION | `panel_3.py` | `panel_3.py` | |
| Automation calculator (headless) | `panel_4.py` | `panel_7.py` | position irrelevant, draws nothing. Source-tree name and live slot name **differ**. See TODO.md "Panel dev-side numbering vs. save-side slot numbers" for known sync-tool gap |
| DRONE FLEET | `panel_5.py` | *(not yet created)* | cruise-throttle slider + drone roster + fleet auto-upgrade switch/status (§2k). Operator must create new Custom Panel in-game, then use `devtools/scripts_sync.py`'s unmatched-file synctool-fill marker to point empty slot at this source file. Then row gets real live-slot name |
| Warehouse upgrade worker (headless) | `panel_6.py` | *(not yet created)* | runs `lib/warehouse_upgrade.py` (§2k-1); blocks for long drains, so kept out of `panel_4.py`. Operator creates a new Custom Panel in-game, then points it at this file with the synctool-fill marker, same as `panel_5.py` |

**Whenever panel added/removed in-game: re-verify table (ask operator for current mapping), update every `panel_N.py` cross-reference in this file and in scripts' module docstrings.** Stale filename here actively misleading.

Card size set from Control Room UI (drag-resize / size picker), **not** script. `panel.width()`/`panel.height()` only report operator's chosen size. Discrete, not continuous:

| Label shown in the UI | Meaning | `panel.width()` | `panel.height()` |
| :--- | :--- | :--- | :--- |
| `1 x 1` | 1 column, 1 row | 500 | 200 |
| `1 x 2` | 1 column, **2 rows** | 500 | 400 |
| `2 x 1` | **2 columns**, 1 row | 1000 | 200 |
| `2 x 2` | 2 columns, 2 rows | 1000 | 400 |

First number = columns (width), second = rows (height). `1x1` → `1x2` adds height only, not width. Wide-canvas layout (side-by-side sections, right-anchored control) clips on `1x2`, still only 500px wide.

**Sizing recommendations** (headless automation panel draws nothing, no card/size to set): `panel_1.py` (STATUS + AUTOMATION) → **`2 x 2`** (1000x400), split `panel.height()` ~55/45 between two sub-cards (ratio, not fixed pixels, so degrades OK at `2 x 1`). `panel_2.py` (FLEET, one row per vehicle) / `panel_3.py` (PRODUCTION, one row per Smelter + Fabricator + Supply Dock, discovered live via `discover_smelter_ids()`/`discover_fabricator_ids()`/`discover_supply_dock_ids()`; each row = role pill + current recipe/order + status pill) / `panel_5.py` (DRONE FLEET, one row per drone via `fleet.drones()`) share same one-row-per-item scrollable shape → **`2 x 1`** for few rows, **`2 x 2`** for more. Each shows as many rows as fit (`max_rows = (height - top - 16) // row_height`). `panel.slider()` repurposed as scroll bar (0-1 value → row offset, `round(value * (len(rows) - max_rows))`) covers rest, drawn only once list exceeds `max_rows`. Both degrade at 1-column widths (`wide = width >= 900` switches to shorter row height; `panel_2.py` hides location column).

**Headless automation panel's work, shown on `panel_1.py`'s AUTOMATION card**: §1a-1's centralized Power Grid supervision + Smelter rebalance sweep, plus:
- **Outpost-founding → resource marker auto-reassignment**: each throttled storage tick, diff `outpost_network.outposts()`' current id set vs stored `outposts.known_ids` (archive list). Each **new** id auto-calls `outpost_mining.reevaluate_unassigned_near_outpost(new_id)` (§2d). `sync_resource_markers.py` stays for manual backfill/batch catch-up.
- **Two independent throttle timers**: `SOLAR_TICK_INTERVAL = 10` ticks (~1s) gates grid supervision (cheap, no Auto Feeder transfers). `STORAGE_TICK_INTERVAL = 100` ticks (~10s) separately gates `rebalance_inventory_to_warehouses()` + outpost-diff/`consolidate_cross_warehouse_stock()` sweep. Both `.transfer_to()` and `.compact()` lock their Warehouse as material endpoint for whole transfer, so faster shared cadence risks contention (`"busy"` rejection on Smelter/Fabricator `take_item()` call). Grid supervision has no such cost. Both intervals gate via `clock.tick()` (not wall-clock), correct under time acceleration.
- **`panel.button("run_archive_cleaner", ...)`** on `panel_1.py`: `ArchiveCleaner(dry_run=False,
  verbose=True).run()` (§4). Live-commit, human-triggered only, runs directly in that UI script (rare one-off, not per-cycle work).
- **`panel.button("run_unsupported_markers", ...)`** on `panel_1.py`: `lib/unsupported_markers.py`'s `update_unsupported_markers(clear_previous=True)`. Also human-triggered only, runs directly in `panel_1.py`. Also runnable standalone as root entrypoint `mark_unsupported_targets.py`.
- **Version safety gate widget** (`lib/version_guard.py`, §4), drawn on `panel_1.py`: `VERSION` pill anchored `width - 190` from right edge (always drawn, success/error colored). Only while `version_mismatch()` true, also shows `was <old> -- new scripts halt on startup` note + `panel.button("confirm_new_version", ...)`. Neither headless automation panel nor `panel_1.py` calls `validate_game_version()` itself. Both check `version_mismatch()` independently and gate own mutating work behind `if not mismatch:`. During mismatch, `panel_1.py` keeps rendering and stays clickable, but neither script changes anything until confirmed.

**General layout rules for any new card** (background: `DESIGN_HISTORY.md`):
- `card(x, y, w, h, title)` already renders own title bar text. Never add second `panel.label()` re-rendering same title.
- Named widget that draws own label (`slider`, likely `switch`/`button` too): fold live value INTO that label string. Don't draw separate, separately-positioned text beside it.
- `pill()` needs more vertical clearance below than plain text line. Leave ≥ ~24px, not ~16px, before placing anything under one.
- Anchor right-side elements from right edge (`width - <fixed px>`), not width fraction (`width * 0.86`), for anything with roughly fixed pixel footprint (`switch`, `button`, short `pill`). Fractions of 500px vs 1000px canvas land very differently.
