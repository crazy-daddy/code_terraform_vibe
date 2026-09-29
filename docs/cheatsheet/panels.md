# Control Room Panels (§7)

Part of [`AI_CHEATSHEET.md`](../AI_CHEATSHEET.md).

## 🖥️ 7. Control Room Panel Cards (`scripts/4_controlpanel/control_panel/*_panel.py`)

**Headless calculator + UI card split (`automation_panel.py` + `status_panel.py`).** Automation calculator (grid supervision, rebalance sweep, outpost sync, `supply_dock.plan_dock_assignments()`, fleet hardware upgrade §2k, Pioneer commissioning §2k-2, cash manager §2l) is **headless**: no `panel.*` calls, paced by `sleep(1.0)`. It publishes result summary to `archive` (`AUTOMATION_SUMMARY_KEY = "control_room.automation_summary"`). STATUS/AUTOMATION UI card reads that summary back, doesn't compute it. Reason: multi-second automation stall must never block script that renders every tick. Custom Panel is only slot that can host "always-on, not tied to one building" process. Background: `DESIGN_HISTORY.md`.

**Source files are named by role; live slot numbers are not.** The game assigns Custom Panel ids on creation. They **only ever increment**: deleting a panel doesn't free its number. Cards **can't be drag-reordered** once placed. So a role's live `panel_N.py` slot differs per save and says nothing about the role. Source files carry the role in their name and a `# ct-panel: <role>` marker on line 1; `devtools/scripts_sync.py` pairs each live slot with its source by that marker (details: [dev_workflow.md §9](dev_workflow.md)). Run `python devtools/scripts_sync.py status` to see the current slot-to-role pairing of the active save.

| Role | Source file | Notes |
| :--- | :--- | :--- |
| STATUS + AUTOMATION UI | `status_panel.py` | keep at top of Control Room |
| FLEET (ground vehicles) | `vehicles_panel.py` | |
| PRODUCTION | `production_panel.py` | |
| Automation calculator (headless) | `automation_panel.py` | position irrelevant, draws nothing |
| DRONE FLEET | `drones_panel.py` | cruise-throttle slider + drone roster + fleet auto-upgrade switch/status (§2k) |
| COMMISSION (new Pioneers and drones) | `fleet_commission_panel.py` | Pioneer role buttons + HOME_BASE picker, drone role buttons + deploy-outpost picker (outposts with a Drone Depot), job queue with cancel (§2k-2); `2 x 2` |
| CASH (budget) | `cash_panel.py` | balance/floor/income/reagent burn/order pipeline + one row per consumer kind with next cost, planned total, ETA and ^/v priority buttons (§2l); `2 x 2` |
| Warehouse upgrade worker (headless) | `warehouse_upgrade_panel.py` | runs `lib/warehouse_upgrade.py` (§2k-1) then `lib/tank_upgrade.py` (§2k-3) each pass; the Warehouse drain blocks for long, so kept out of `automation_panel.py` |

**New panel in-game:** create the empty Custom Panel. When exactly one role has no slot yet, the sync tool fills it with that role and starts it. Otherwise type `# ct-panel: <role>` (e.g. `# ct-panel: drones_panel`) into it first.

Card size set from Control Room UI (drag-resize / size picker), **not** script. `panel.width()`/`panel.height()` only report operator's chosen size. Discrete, not continuous:

| Label shown in the UI | Meaning | `panel.width()` | `panel.height()` |
| :--- | :--- | :--- | :--- |
| `1 x 1` | 1 column, 1 row | 500 | 200 |
| `1 x 2` | 1 column, **2 rows** | 500 | 400 |
| `2 x 1` | **2 columns**, 1 row | 1000 | 200 |
| `2 x 2` | 2 columns, 2 rows | 1000 | 400 |

First number = columns (width), second = rows (height). `1x1` → `1x2` adds height only, not width. Wide-canvas layout (side-by-side sections, right-anchored control) clips on `1x2`, still only 500px wide.

**Sizing recommendations** (headless automation panel draws nothing, no card/size to set): `status_panel.py` (STATUS + AUTOMATION) → **`2 x 2`** (1000x400), split `panel.height()` ~55/45 between two sub-cards (ratio, not fixed pixels, so degrades OK at `2 x 1`). `production_panel.py` (PRODUCTION, Smelters + Fabricators + Supply Docks discovered live via `discover_smelter_ids()`/`discover_fabricator_ids()`/`discover_supply_dock_ids()`; each cell = role pill + current recipe/order + status pill) → **`2 x 2`**: at `SPLIT_MIN_WIDTH = 700`+ px it draws two side-by-side columns (Smelters left, Fabricators right, then Supply Docks paired two per line), one scrollbar moving the whole grid by line; narrower falls back to one machine per line. `vehicles_panel.py` (FLEET, one row per vehicle) / `drones_panel.py` (DRONE FLEET, one row per drone via `fleet.drones()`) share same one-row-per-item scrollable shape → **`2 x 1`** for few rows, **`2 x 2`** for more. Each shows as many rows as fit (`max_rows = (height - top - 16) // row_height`). `panel.slider()` repurposed as scroll bar (0-1 value → row offset, `round(value * (len(rows) - max_rows))`) covers rest, drawn only once list exceeds `max_rows`. Both degrade at 1-column widths (`wide = width >= 900` switches to shorter row height; `vehicles_panel.py` hides location column). `vehicles_panel.py`/`drones_panel.py` draw an intent column (`fleet.status[id]["intent"]`, §4) right of the location, word-wrapped onto `INTENT_LINES = 2` lines (`INTENT_LINE_PX = 13` apart, `INTENT_CHAR_PX = 6` per char at font 10, last line cut with `..`) up to the recall switch (and left of the Sport Nav button on Pioneer rows); narrow layout puts it after the location on the second line.

**Headless automation panel's work, shown on `status_panel.py`'s AUTOMATION card**: §1a-1's centralized Power Grid supervision + Smelter rebalance sweep, plus:
- **Outpost-founding → resource marker auto-reassignment**: each throttled storage tick, diff `outpost_network.outposts()`' current id set vs stored `outposts.known_ids` (archive list). Each **new** id auto-calls `outpost_mining.reevaluate_unassigned_near_outpost(new_id)` (§2d). `sync_resource_markers.py` stays for manual backfill/batch catch-up.
- **Two independent throttle timers**: `SOLAR_TICK_INTERVAL = 10` ticks (~1s) gates grid supervision (cheap, no Auto Feeder transfers). `STORAGE_TICK_INTERVAL = 100` ticks (~10s) separately gates `rebalance_inventory_to_warehouses()` + outpost-diff/`consolidate_cross_warehouse_stock()` sweep. Both `.transfer_to()` and `.compact()` lock their Warehouse as material endpoint for whole transfer, so faster shared cadence risks contention (`"busy"` rejection on Smelter/Fabricator `take_item()` call). Grid supervision has no such cost. Both intervals gate via `clock.tick()` (not wall-clock), correct under time acceleration.
- **`panel.button("run_archive_cleaner", ...)`** on `status_panel.py`: `ArchiveCleaner(dry_run=False,
  verbose=True).run()` (§4). Live-commit, human-triggered only, runs directly in that UI script (rare one-off, not per-cycle work).
- **`panel.button("run_unsupported_markers", ...)`** on `status_panel.py`: `lib/unsupported_markers.py`'s `update_unsupported_markers(clear_previous=True)`. Also human-triggered only, runs directly in `status_panel.py`. Also runnable standalone as root entrypoint `mark_unsupported_targets.py`.
- **`panel.button("sell_biomass_chain", ...)`** on `status_panel.py`, third in the button row: drawn only while `biomass.retire` says complete AND ready; runs `lib/biomass_retire.py`'s `sell_retired_machines()` (undeploy + sell every Liquifier/Mixer). Status line under it (`status`, or the last sale summary). See §1h-1.
- **Version safety gate widget** (`lib/version_guard.py`, §4), drawn on `status_panel.py`: `VERSION` pill anchored `width - 190` from right edge (always drawn, success/error colored). Only while `version_mismatch()` true, also shows `was <old> -- new scripts halt on startup` note + `panel.button("confirm_new_version", ...)`. Neither headless automation panel nor `status_panel.py` calls `validate_game_version()` itself. Both check `version_mismatch()` independently and gate own mutating work behind `if not mismatch:`. During mismatch, `status_panel.py` keeps rendering and stays clickable, but neither script changes anything until confirmed.

**General layout rules for any new card** (background: `DESIGN_HISTORY.md`):
- `card(x, y, w, h, title)` already renders own title bar text. Never add second `panel.label()` re-rendering same title.
- Named widget that draws own label (`slider`, likely `switch`/`button` too): fold live value INTO that label string. Don't draw separate, separately-positioned text beside it.
- `pill()` needs more vertical clearance below than plain text line. Leave ≥ ~24px, not ~16px, before placing anything under one.
- Anchor right-side elements from right edge (`width - <fixed px>`), not width fraction (`width * 0.86`), for anything with roughly fixed pixel footprint (`switch`, `button`, short `pill`). Fractions of 500px vs 1000px canvas land very differently.
