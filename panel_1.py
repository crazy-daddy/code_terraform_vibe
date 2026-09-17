# Control Room status + automation card: clock, power, storage, actionable
# warnings (STATUS), plus the centralized always-on housekeeping this script
# is the one process guaranteed to keep running (AUTOMATION) -- see
# docs/AI_CHEATSHEET.md:
#   - Power Grid supervision (brownout load-shedding, day/night calibration)
#     for every grid, one PowerGridManager instance per grid, reused across
#     ticks so its day/night state persists.
#   - The Smelter Inventory->Warehouse rebalance sweep, once per cycle.
#   - Cross-warehouse stock consolidation, every outpost, once per cycle.
#   - Outpost-founding -> resource marker auto-reassignment
#     (lib/outpost_mining.py's reevaluate_unassigned_near_outpost()).
#   - Manual "Clean Archive" / "Sync Unsupported" buttons.
# lib/solar.py's SolarController and lib/smelter.py's SmelterController no
# longer do any of this themselves -- it's a hard dependency on this script
# running (see legacy/README.md for pre-Control-Room saves).
# Recommended card size: 2 columns x 2 rows -- see docs/AI_CHEATSHEET.md.

from archive import archive
from power import PowerGridManager
from storage import rebalance_inventory_to_warehouses, consolidate_cross_warehouse_stock
from archive_cleaner import ArchiveCleaner
from unsupported_markers import update_unsupported_markers
import outpost_mining

OUTPOST_KNOWN_IDS_KEY = "outposts.known_ids"

# ~1s and 10s at 10 ticks/sec (see lib/archive_cleaner.py's documented tick rate) --
# the panel redraws every render tick regardless; only the actual automation
# work (grid supervision, rebalance sweep, outpost diff) is throttled to this
# cadence, matching what lib/solar.py's run(poll_interval=1.0) used to do.
SOLAR_TICK_INTERVAL = 10
STORAGE_TICK_INTERVAL = 100

# Loop-scoped state, created once and persisting across iterations (this
# script is one continuous while-loop process, not re-invoked per tick --
# same pattern panel_2.py uses for its scroll_label).
grid_managers = {}          # {anchor_id: PowerGridManager}, reused so day/night state persists
last_solar_tick = 0
last_storage_tick = 0
last_automation_summary = "not yet run"
last_cleaner_stats = None
last_unsupported_count = None

while True:
    panel.clear()
    width = panel.width()
    height = panel.height()

    clock = get_component("clock")
    power = get_component("power_control")

    status_h = int(height * 0.55)
    panel.card(8, 8, width - 16, status_h - 8, "STATUS")

    day = clock.get_day() if clock else "-"
    time = clock.get_time() if clock else (0, 0)
    phase = clock.get_time_of_day() if clock else "unknown"
    day_fraction = ((time[0] * 60 + time[1]) / 1440.0) if clock else 0.0

    panel.counter(24, 58, day, "DAY", 26)
    panel.gauge(128, 96, 32, day_fraction, f"{time[0]:02d}:{time[1]:02d}")
    panel.label(96, 150, phase.upper(), "muted")

    col2 = width * 0.34
    panel.label(col2, 42, "POWER", "caption")
    grids = power.grids() if power and hasattr(power, "grids") else []
    stored = 0.0
    capacity = 0.0
    net = 0.0
    for grid in grids:
        stored += getattr(grid, "stored", 0.0) or 0.0
        capacity += getattr(grid, "capacity", 0.0) or 0.0
        net += getattr(grid, "net", 0.0) or 0.0
    power_fraction = stored / capacity if capacity > 0 else 0.0
    panel.pill(col2, 62, "NORMAL" if net >= 0 else "DEFICIT", "success" if net >= 0 else "warning")
    panel.progress_bar(col2, 88, width * 0.20, 12, power_fraction, "success" if net >= 0 else "warning")
    panel.label(col2, 110, f"{stored:.0f} / {capacity:.0f} Wh", "muted")
    panel.label(col2, 132, f"net {net:+.1f} W", "value")

    inventory = get_component("inventory")
    used = inventory.get_used() if inventory and hasattr(inventory, "get_used") else 0
    slots = inventory.get_size() if inventory and hasattr(inventory, "get_size") else 0
    col3 = width * 0.60
    inventory_full = bool(slots) and used >= slots
    panel.label(col3, 42, "STORAGE", "caption")
    panel.progress_bar(col3, 66, width * 0.16, 12, used / slots if slots else 0.0, "error" if inventory_full else "accent")
    panel.label(col3, 88, f"{used} / {slots} slots", "muted")

    alerts = []
    if inventory_full:
        alerts.append("Inventory full: production and Rover unloading may pause")
    if net < 0:
        alerts.append("Power deficit: monitor battery reserve")
    if not grids:
        alerts.append("No power grid data available")

    col4 = width * 0.80
    panel.label(col4, 42, "ALERTS", "caption")
    if not alerts:
        panel.status_dot(col4 + 5, 72, 5, "running")
        panel.label(col4 + 18, 78, "all clear", "value")
    else:
        for index, alert in enumerate(alerts[:4]):
            y = 68 + index * 26
            panel.status_dot(col4 + 5, y, 5, "error" if "full" in alert else "paused")
            panel.draw_text(col4 + 18, y + 5, alert, 10, "text-secondary", width * 0.18)

    # ------------------------------------------------------------------
    # AUTOMATION -- see module docstring. Throttled to _TICK_INTERVAL;
    # buttons below still respond every tick regardless of the throttle.
    # ------------------------------------------------------------------
    auto_y = status_h + 8
    panel.card(8, auto_y, width - 16, height - auto_y - 8, "AUTOMATION")

    current_tick = clock.tick() if clock and hasattr(clock, "tick") else 0
    solar_due = (last_solar_tick == 0) or (current_tick - last_solar_tick >= SOLAR_TICK_INTERVAL)
    storage_due = (last_storage_tick == 0) or (current_tick - last_storage_tick >= STORAGE_TICK_INTERVAL)

    if solar_due:
        last_solar_tick = current_tick
        grid_count = 0
        try:
            elevation = clock.get_elevation() if clock else 0.0
            live_grids = power.grids() if power and hasattr(power, "grids") else []
            current_anchors = set()
            for grid in live_grids:
                anchor = getattr(grid, "anchor_id", None)
                current_anchors.add(anchor)
                manager = grid_managers.get(anchor)
                if manager is None:
                    manager = PowerGridManager(grid, clock=clock, power=power)
                    grid_managers[anchor] = manager
                manager.supervise_grid(grid, elevation)
                grid_count += 1

            # Grids that stopped being reported (merged into another via a new
            # power line) -- release anything they still had shed rather than
            # stranding it forever (see PowerGridManager.release_all()).
            for stale_anchor in list(grid_managers.keys()):
                if stale_anchor not in current_anchors:
                    grid_managers[stale_anchor].release_all()
                    del grid_managers[stale_anchor]
        except Exception as e:
            print(f"[AUTOMATION] Grid supervision error: {e}")
            
    if storage_due:
        last_storage_tick = current_tick
        try:
            rebalance_inventory_to_warehouses()
        except Exception as e:
            print(f"[AUTOMATION] Rebalance sweep error: {e}")

        outpost_new_count = 0
        try:
            network = get_component("outpost_network")
            if network and hasattr(network, "outposts"):
                outposts = network.outposts()
                current_ids = {getattr(o, "id", None) for o in outposts}
                current_ids.discard(None)
                known_ids = set(archive.get(OUTPOST_KNOWN_IDS_KEY, []) or [])
                new_ids = current_ids - known_ids
                for new_id in new_ids:
                    assigned = outpost_mining.reevaluate_unassigned_near_outpost(new_id)
                    print(f"[AUTOMATION] New outpost '{new_id}' detected -- assigned {assigned} nearby resource marker(s).")
                    outpost_new_count += 1
                if current_ids != known_ids:
                    archive.set(OUTPOST_KNOWN_IDS_KEY, sorted(current_ids))

                # Cross-warehouse consolidation sweep (storage.py's
                # consolidate_cross_warehouse_stock(), which calls
                # .compact()) -- every outpost, not just home, since a
                # remote outpost's Warehouses (e.g. a Bio Lab reagent drop)
                # can end up with the same item split across multiple
                # Warehouse buildings the same way repeat hauler deliveries
                # can at home.
                for o in outposts:
                    o_id = getattr(o, "id", "?")
                    try:
                        consolidate_cross_warehouse_stock(o)
                    except Exception as e:
                        print(f"[AUTOMATION] Cross-warehouse consolidation error at '{o_id}': {e}")
        except Exception as e:
            print(f"[AUTOMATION] Outpost sync error: {e}")

        last_automation_summary = f"{grid_count} grid(s) supervised, rebalance swept, {outpost_new_count} new outpost(s)"

    panel.label(24, auto_y + 34, "ALWAYS-ON", "caption")
    panel.status_dot(29, auto_y + 58, 5, "running")
    panel.draw_text(42, auto_y + 64, last_automation_summary, 10, "text-secondary", width * 0.30)

    btn_y = auto_y + 88
    btn_w = min(160, width * 0.22)

    if panel.button("run_archive_cleaner", 24, btn_y, btn_w, 26, "Clean Archive"):
        try:
            last_cleaner_stats = ArchiveCleaner(dry_run=False, verbose=True).run()
        except Exception as e:
            last_cleaner_stats = {"error": str(e)}
    if last_cleaner_stats is not None:
        scanned = last_cleaner_stats.get("keys_scanned", "-")
        removed = sum(v for k, v in last_cleaner_stats.items() if k.endswith("_removed") or k.endswith("_purged"))
        panel.label(24, btn_y + 34, f"scanned {scanned}, purged {removed}", "muted")

    btn2_x = 24 + btn_w + 24
    if panel.button("run_unsupported_markers", btn2_x, btn_y, btn_w, 26, "Sync Unsupported"):
        try:
            last_unsupported_count = update_unsupported_markers(clear_previous=True)
        except Exception as e:
            last_unsupported_count = -1
    if last_unsupported_count is not None:
        summary = "error" if last_unsupported_count < 0 else f"{last_unsupported_count} marker(s) placed"
        panel.label(btn2_x, btn_y + 34, summary, "muted")
