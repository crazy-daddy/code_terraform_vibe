# Control Room status card: clock, power, storage, and actionable warnings.
# Recommended card size: 2 columns x 1 row -- see docs/AI_CHEATSHEET.md.

while True:
    panel.clear()
    width = panel.width()
    height = panel.height()
    panel.card(8, 8, width - 16, height - 16, "STATUS")  # card() already renders its own title bar text

    clock = get_component("clock")
    day = clock.get_day() if clock else "-"
    time = clock.get_time() if clock else (0, 0)
    phase = clock.get_time_of_day() if clock else "unknown"
    day_fraction = ((time[0] * 60 + time[1]) / 1440.0) if clock else 0.0

    panel.counter(24, 58, day, "DAY", 26)
    panel.gauge(128, 96, 32, day_fraction, f"{time[0]:02d}:{time[1]:02d}")
    panel.label(96, 150, phase.upper(), "muted")

    power = get_component("power_control")
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
