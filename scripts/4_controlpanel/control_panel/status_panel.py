# ct-panel: status_panel
# Control Room status + automation card: clock, power, storage, actionable
# warnings (STATUS), plus a live view of control_room_automation.py's automation results
# (AUTOMATION) -- see docs/AI_CHEATSHEET.md §7.
#
# control_room_automation.py (an Automation, draws nothing) is the always-on
# worker (grid supervision, rebalance sweep, outpost sync, Supply Dock
# planning). It publishes its result summary to `archive`
# (AUTOMATION_SUMMARY_KEY below) for this card to read and display -- the
# Archive-as-decoupling-channel pattern CODE_GUIDES.md#archive calls for. A multi-second
# call (supply_dock.plan_dock_assignments()) inside a per-tick rendering loop
# blanks the card, so none of that work runs here.
#
# Everything drawn here (STATUS's clock/power/storage/alerts, the version
# gate, and the manual buttons) is either a cheap single-call component read
# or a rare user-triggered one-off, so it stays inline in this UI script
# rather than being routed through archive too.
#
# SLOT NUMBER: the game picks Custom Panel ids itself (ids only increment,
# cards can't be drag-reordered), so this file's live panel_N slot differs
# per save. devtools/scripts_sync.py pairs the slot with this file by the
# ct-panel marker on line 1 -- see docs/cheatsheet/panels.md §7.
# Recommended card size: 2 columns x 2 rows (STATUS on top, full AUTOMATION
# card below). At 2 x 1 (height < TALL_MIN_H) STATUS takes the left part and a
# compact AUTOMATION card the right: alerts, a one-line summary and the
# buttons. STATUS carries net-power and stored-energy trend lines from an
# in-script ring buffer (TREND_*), so they restart empty with the script.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import panel

from archive import archive
from archive_cleaner import ArchiveCleaner
from unsupported_markers import update_unsupported_markers
from version_guard import version_mismatch, good_version, confirm_new_version
from swallow import swallowed
from biomass_retire import retire_state, sell_retired_machines
from lead_cask import reactor_fuel_alerts
from script_parking import stray_alerts

# Must match control_room_automation.py's own AUTOMATION_SUMMARY_KEY.
AUTOMATION_SUMMARY_KEY = "control_room.automation_summary"
SUMMARY_SEPARATOR = " | "  # must match control_room_automation.py

# ALWAYS-ON summary grid: one item per cell, text size 10 monospace (~6 px per character).
SUMMARY_ROW_H = 13
SUMMARY_COL_MIN_W = 190
SUMMARY_CHAR_W = 6
VERSION_PILL_W = 70  # room kept right of the AUTOMATION card title for the game version pill
TALL_MIN_H = 300  # below this the card uses the side-by-side 2 x 1 layout
STATUS_H = 200  # STATUS card height in both layouts
# Trend ring buffers: one sample every TREND_SAMPLE_MINUTES game minutes, at
# most TREND_SAMPLES kept (~3 game hours). Keyed on game time, so a paused
# game adds nothing.
TREND_SAMPLE_MINUTES = 2
TREND_SAMPLES = 90
ALERT_ROW_H = 20


def draw_summary_grid(x, y, w, items):
    """Draws items column-major in as many SUMMARY_COL_MIN_W columns as fit in w, each cut to its
    column with an ellipsis; returns the number of rows used."""
    cols = max(1, int(w // SUMMARY_COL_MIN_W))
    rows = -(-len(items) // cols)
    col_w = w / cols
    max_chars = max(4, int((col_w - 8) // SUMMARY_CHAR_W))
    for i, item in enumerate(items):
        text = item if len(item) <= max_chars else item[: max_chars - 1] + "…"
        panel.draw_text(x + (i // rows) * col_w, y + (i % rows) * SUMMARY_ROW_H, text, 10, "text-secondary")
    return rows

# Loop-scoped state, created once and persisting across iterations (this
# script is one continuous while-loop process, not re-invoked per tick).
last_cleaner_stats = None
last_unsupported_count = None
last_biomass_sale = None
net_history = []
stored_history = []
last_sample_minute = None


def clip(text, chars):
    return text if len(text) <= chars else text[: chars - 1] + "…"


def draw_alerts(x, y, w, max_rows, alerts):
    """One line per alert from y down, cut to w; the last row turns into "+N more" on overflow."""
    if not alerts:
        panel.status_dot(x + 5, y, 5, "running")
        panel.draw_text(x + 18, y, "all clear", 10, "text-value")
        return
    shown = alerts if len(alerts) <= max_rows else alerts[: max(0, max_rows - 1)]
    chars = max(4, int((w - 18) // SUMMARY_CHAR_W))
    for index, (alert, level) in enumerate(shown):
        row_y = y + index * ALERT_ROW_H
        panel.status_dot(x + 5, row_y, 5, "error" if level == "error" else "paused")
        panel.draw_text(x + 18, row_y, clip(alert, chars), 10, "error" if level == "error" else "text-secondary")
    if len(shown) < len(alerts):
        panel.draw_text(x + 18, y + len(shown) * ALERT_ROW_H, f"+{len(alerts) - len(shown)} more", 10, "text-muted")


def draw_trend(x, y, w, caption, values, color):
    panel.draw_text(x, y, caption, 9, "text-muted")
    if len(values) >= 2:
        panel.spark_line(x, y + 8, w, 34, values, color)
    else:
        panel.draw_text(x, y + 24, "collecting...", 9, "text-muted")


def automation_buttons(x, y, btn_widths):
    """Clean Archive, Sync Unsupported and (once biomass is complete and drained) Sell Biomass Chain
    in one row. Returns [(x, result text)] for the buttons that have a result to show."""
    global last_cleaner_stats, last_unsupported_count, last_biomass_sale
    results = []
    if panel.button("run_archive_cleaner", x, y, btn_widths[0], 26, "Clean Archive"):
        try:
            last_cleaner_stats = ArchiveCleaner(dry_run=False, verbose=True).run()
        except Exception as e:
            swallowed("status_panel: ArchiveCleaner(dry_run=False, verbose=True).run", e)
            last_cleaner_stats = {"error": str(e)}
    if last_cleaner_stats is not None:
        scanned = last_cleaner_stats.get("keys_scanned", "-")
        removed = sum(v for k, v in last_cleaner_stats.items() if k.endswith("_removed") or k.endswith("_purged"))
        results.append((x, f"scanned {scanned}, purged {removed}"))

    btn2_x = x + btn_widths[0] + 16
    if panel.button("run_unsupported_markers", btn2_x, y, btn_widths[1], 26, "Sync Unsupported"):
        try:
            last_unsupported_count = update_unsupported_markers(clear_previous=True)
        except Exception as e:
            swallowed("status_panel: update_unsupported_markers", e)
            last_unsupported_count = -1
    if last_unsupported_count is not None:
        results.append((btn2_x, "error" if last_unsupported_count < 0 else f"{last_unsupported_count} marker(s) placed"))

    # Biomass chain sale (lib/biomass_retire.py): drawn only once biomass is
    # complete and every Liquifier/Mixer is drained (control_room_automation.py publishes
    # readiness). Undeploys and sells them -- operator-triggered only.
    retire = retire_state()
    if retire.get("complete"):
        btn3_x = btn2_x + btn_widths[1] + 16
        if retire.get("ready"):
            if panel.button("sell_biomass_chain", btn3_x, y, btn_widths[2], 26, "Sell Biomass Chain"):
                try:
                    last_biomass_sale = sell_retired_machines()
                except Exception as e:
                    swallowed("status_panel: sell_retired_machines", e)
                    last_biomass_sale = f"error: {e}"
        results.append((btn3_x, str(last_biomass_sale or retire.get("last_sale") or retire.get("status", ""))))
    return results


def confirm_version_button(x, y):
    if panel.button("confirm_new_version", x, y, 172, 26, "Confirm New Version"):
        try:
            confirm_new_version()
        except Exception as e:
            print(f"[AUTOMATION] Confirm new version error: {e}")


while True:
    panel.clear()
    width = panel.width()
    height = panel.height()
    tall = height >= TALL_MIN_H

    clock = get_component("clock")
    power = get_component("power_control")

    status_w = width - 16 if tall else int(width * 0.56)
    panel.card(8, 8, status_w, STATUS_H - 8, "STATUS")

    day = clock.get_day() if clock else "-"
    time = clock.get_time() if clock else (0, 0)
    phase = clock.get_time_of_day() if clock else "unknown"
    day_fraction = ((time[0] * 60 + time[1]) / 1440.0) if clock else 0.0

    panel.counter(24, 58, day, "DAY", 26)
    panel.gauge(128, 96, 32, day_fraction, f"{time[0]:02d}:{time[1]:02d}")
    panel.label(96, 150, phase.upper(), "muted")

    col2 = 200
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
    panel.pill(col2, 56, "NORMAL" if net >= 0 else "DEFICIT", "success" if net >= 0 else "warning")
    panel.progress_bar(col2, 82, 160, 12, power_fraction, "success" if net >= 0 else "warning")
    panel.label(col2, 104, f"{stored:.0f} / {capacity:.0f} Wh", "muted")
    panel.label(col2, 124, f"net {net:+.1f} W", "value")

    inventory = get_component("inventory")
    used = inventory.get_used() if inventory and hasattr(inventory, "get_used") else 0
    slots = inventory.get_size() if inventory and hasattr(inventory, "get_size") else 0
    inventory_full = bool(slots) and used >= slots
    panel.progress_bar(col2, 144, 160, 8, used / slots if slots else 0.0, "error" if inventory_full else "accent")
    panel.label(col2, 164, f"storage {used} / {slots} slots", "muted")

    # Trend lines, sampled on game time (TREND_SAMPLE_MINUTES); a clock that
    # went backwards (save reload) samples at once.
    if clock:
        minute = (day if isinstance(day, int) else 0) * 1440 + time[0] * 60 + time[1]
        if last_sample_minute is None or minute - last_sample_minute >= TREND_SAMPLE_MINUTES or minute < last_sample_minute:
            last_sample_minute = minute
            net_history = (net_history + [net])[-TREND_SAMPLES:]
            stored_history = (stored_history + [stored])[-TREND_SAMPLES:]
    trend_x = 390
    trend_w = 150
    net_range = f"{min(net_history):+.0f}..{max(net_history):+.0f}" if net_history else ""
    draw_trend(trend_x, 42, trend_w, f"NET W  {net_range}", net_history, "success" if net >= 0 else "warning")
    draw_trend(trend_x, 104, trend_w, "STORED Wh", stored_history, "accent")

    # (text, level): Reactor fuel first (lead_cask.REACTOR_FUEL_KEY), then stray dark machines
    # (script_parking.STRAY_KEY); level picks the dot colour.
    alerts = []
    try:
        alerts.extend(reactor_fuel_alerts(clock.tick() if clock else 0))
    except Exception as e:
        swallowed("status_panel: reactor_fuel_alerts", e)
    try:
        alerts.extend(stray_alerts())
    except Exception as e:
        swallowed("status_panel: stray_alerts", e)
    if inventory_full:
        alerts.append(("Inventory full: production and Rover unloading may pause", "error"))
    if net < 0:
        alerts.append(("Power deficit: monitor battery reserve", "warn"))
    if not grids:
        alerts.append(("No power grid data available", "warn"))

    # ------------------------------------------------------------------
    # VERSION SAFETY GATE -- see lib/version_guard.py. control_room_automation.py's own
    # automation loop checks version_mismatch() independently and halts its
    # own mutating work; this card just surfaces the same gate and the
    # confirm button so the operator can always reach it. The version pill sits
    # in the AUTOMATION card's title row.
    # ------------------------------------------------------------------
    mismatch = version_mismatch()
    last_automation_summary = archive.get(AUTOMATION_SUMMARY_KEY, "not yet run")
    summary_items = ["halted -- confirm new version below"] if mismatch else str(last_automation_summary).split(SUMMARY_SEPARATOR)

    # ------------------------------------------------------------------
    # AUTOMATION -- a live view of control_room_automation.py's headless worker (see module
    # docstring). This card does not itself run any of that automation; the
    # buttons are the one exception (rare, user-triggered one-offs).
    # ------------------------------------------------------------------
    if tall:
        alerts_x = 560
        panel.label(alerts_x, 42, "ALERTS", "caption")
        draw_alerts(alerts_x, 62, width - 24 - alerts_x, (STATUS_H - 70) // ALERT_ROW_H, alerts)

        auto_y = STATUS_H + 8
        panel.card(8, auto_y, width - 16, height - auto_y - 8, "AUTOMATION")
        panel.pill(width - VERSION_PILL_W - 24, auto_y + 6, get_game_version(), "error" if mismatch else "success")
        panel.label(24, auto_y + 34, "ALWAYS-ON", "caption")
        panel.status_dot(29, auto_y + 58, 5, "paused" if mismatch else "running")
        summary_rows = draw_summary_grid(42, auto_y + 64, width - 16 - 42 - 16, summary_items)
        btn_y = auto_y + 70 + summary_rows * SUMMARY_ROW_H + 10
        if mismatch:
            confirm_version_button(24, btn_y)
            panel.draw_text(24 + 172 + 16, btn_y + 8, f"was {good_version()} -- new scripts halt on startup", 10, "text-secondary", width - 24 - 172 - 16 - 24)
        else:
            btn_w = min(160, width * 0.22)
            for result_x, text in automation_buttons(24, btn_y, [btn_w, btn_w, btn_w]):
                panel.draw_text(result_x, btn_y + 40, text, 10, "text-secondary", width - result_x - 24)
    else:
        # 2 x 1: alerts, one summary line and the buttons share the right-hand card.
        ax = status_w + 16
        aw = width - 8 - ax
        panel.card(ax, 8, aw, STATUS_H - 8, "AUTOMATION")
        panel.pill(width - VERSION_PILL_W - 24, 14, get_game_version(), "error" if mismatch else "success")
        inner_x = ax + 16
        inner_w = aw - 32
        chars = max(4, int((inner_w - 18) // SUMMARY_CHAR_W))
        draw_alerts(inner_x, 50, inner_w, 3, alerts)
        panel.status_dot(inner_x + 5, 114, 5, "paused" if mismatch else "running")
        panel.draw_text(inner_x + 18, 114, clip(SUMMARY_SEPARATOR.join(summary_items), chars), 10, "text-secondary")
        btn_y = 130
        if mismatch:
            confirm_version_button(inner_x, btn_y)
            panel.draw_text(inner_x, btn_y + 40, f"was {good_version()}", 10, "text-secondary")
        else:
            results = automation_buttons(inner_x, btn_y, [110, 130, 140])
            panel.draw_text(inner_x, btn_y + 40, clip("  ".join(t for _, t in results), chars), 10, "text-secondary")
