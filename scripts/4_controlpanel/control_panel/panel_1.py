# Control Room status + automation card: clock, power, storage, actionable
# warnings (STATUS), plus a live view of panel_7.py's automation results
# (AUTOMATION) -- see docs/AI_CHEATSHEET.md §7.
#
# panel_7.py is the actual "always-on" worker (grid supervision, rebalance
# sweep, outpost sync, Supply Dock planning) -- it runs headless, with no
# panel.* calls of its own. Split out this way because mixing a per-tick
# UI-rendering loop with a multi-second synchronous call
# (supply_dock.plan_dock_assignments() churning through several orders) was
# found live to wedge THIS card's own rendering permanently: the script kept
# running fine underneath (confirmed via temporary debug prints -- iterations
# kept completing every ~100ms) but the Custom Panel canvas stayed blank from
# the first stall onward, with no error anywhere. panel_7.py publishes its
# result summary to `archive` (AUTOMATION_SUMMARY_KEY below) for this card to
# read and display instead -- same Archive-as-decoupling-channel pattern
# CLAUDE.md calls for when a result can't be produced by the component that
# has to display it.
#
# Everything drawn here (STATUS's clock/power/storage/alerts, the version
# gate, and the manual buttons) is either a cheap single-call component read
# or a rare user-triggered one-off -- none of it is the chronic per-cycle
# cost that forced panel_7.py to go headless, so it stays inline in this UI
# script rather than being routed through archive too.
#
# NOTE ON THE FILE NUMBER: this UI card was originally panel_4.py and the
# calculator was panel_1.py -- they're swapped from that because Custom Panel
# ids only ever increment (deleting one never frees its number) and cards
# can't be drag-reordered in the Control Room UI, so getting this UI card
# into the visually-first slot meant recreating it at panel_1 and moving the
# (position-agnostic, since it draws nothing) calculator to whatever number
# was free instead. See docs/AI_CHEATSHEET.md §7's panel-numbering-quirk note
# for the current full mapping -- it WILL drift again if panels are
# added/removed in-game, so verify against the operator before trusting it.
# Recommended card size: 2 columns x 2 rows -- see docs/AI_CHEATSHEET.md.

from archive import archive
from archive_cleaner import ArchiveCleaner
from unsupported_markers import update_unsupported_markers
from version_guard import version_mismatch, good_version, confirm_new_version

# Must match panel_7.py's own AUTOMATION_SUMMARY_KEY.
AUTOMATION_SUMMARY_KEY = "control_room.automation_summary"

# Loop-scoped state, created once and persisting across iterations (this
# script is one continuous while-loop process, not re-invoked per tick --
# same pattern panel_2.py uses for its scroll_label).
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
    # AUTOMATION -- a live view of panel_7.py's headless worker (see module
    # docstring). This card does not itself run any of that automation; the
    # buttons below are the one exception (rare, user-triggered one-offs).
    # ------------------------------------------------------------------
    auto_y = status_h + 8
    panel.card(8, auto_y, width - 16, height - auto_y - 8, "AUTOMATION")

    # ------------------------------------------------------------------
    # VERSION SAFETY GATE -- see lib/version_guard.py. panel_7.py's own
    # automation loop checks version_mismatch() independently and halts its
    # own mutating work; this card just surfaces the same gate and the
    # confirm button so the operator can always reach it.
    # ------------------------------------------------------------------
    ver_x = width - 190
    mismatch = version_mismatch()
    panel.label(ver_x, auto_y + 20, "VERSION", "caption")
    panel.pill(ver_x, auto_y + 34, get_game_version(), "error" if mismatch else "success")
    if mismatch:
        panel.draw_text(ver_x, auto_y + 58, f"was {good_version()} -- new scripts halt on startup", 10, "text-secondary", 180)
        if panel.button("confirm_new_version", ver_x, auto_y + 78, 172, 26, "Confirm New Version"):
            try:
                confirm_new_version()
            except Exception as e:
                print(f"[AUTOMATION] Confirm new version error: {e}")

    last_automation_summary = archive.get(AUTOMATION_SUMMARY_KEY, "not yet run")
    panel.label(24, auto_y + 34, "ALWAYS-ON", "caption")
    panel.status_dot(29, auto_y + 58, 5, "paused" if mismatch else "running")
    panel.draw_text(42, auto_y + 64, "halted -- confirm new version above" if mismatch else last_automation_summary, 10, "text-secondary", width * 0.30)

    btn_y = auto_y + 88
    btn_w = min(160, width * 0.22)

    if not mismatch:
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