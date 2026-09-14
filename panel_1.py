# Control Room status card: clock, power, storage, and actionable warnings.

while True:
    panel.clear()
    width = panel.width()
    height = panel.height()
    panel.card(8, 8, width - 16, height - 16, "STATUS")

    clock = get_component("clock")
    day = clock.get_day() if clock else "-"
    time = clock.get_time() if clock else (0, 0)
    phase = clock.get_time_of_day() if clock else "unknown"
    panel.counter(24, 38, day, "DAY", 22)
    panel.label(24, 96, f"{time[0]:02d}:{time[1]:02d}", "value")
    panel.label(24, 118, phase, "muted")

    power = get_component("power_control")
    panel.label(165, 38, "POWER", "caption")
    grids = power.grids() if power and hasattr(power, "grids") else []
    stored = 0.0
    capacity = 0.0
    net = 0.0
    for grid in grids:
        stored += getattr(grid, "stored", 0.0) or 0.0
        capacity += getattr(grid, "capacity", 0.0) or 0.0
        net += getattr(grid, "net", 0.0) or 0.0
    power_fraction = stored / capacity if capacity > 0 else 0.0
    panel.progress_bar(165, 62, width * 0.27, 12, power_fraction, "success" if net >= 0 else "warning")
    panel.label(165, 84, f"{stored:.0f} / {capacity:.0f} Wh", "muted")
    panel.label(165, 106, f"net {net:+.1f} W", "value")

    inventory = get_component("inventory")
    used = inventory.get_used() if inventory and hasattr(inventory, "get_used") else 0
    slots = inventory.get_size() if inventory and hasattr(inventory, "get_size") else 0
    panel.label(165, 132, "STORAGE", "caption")
    panel.progress_bar(165, 154, width * 0.27, 12, used / slots if slots else 0.0, "error" if slots and used >= slots else "accent")
    panel.label(165, 176, f"{used} / {slots} slots", "muted")

    alerts = []
    if slots and used >= slots:
        alerts.append("Inventory full: production and Rover unloading may pause")
    if net < 0:
        alerts.append("Power deficit: monitor battery reserve")
    if not grids:
        alerts.append("No power grid data available")
    panel.label(width * 0.72, 38, "ALERTS", "caption")
    if not alerts:
        panel.status_dot(width * 0.72 + 5, 70, 5, "running")
        panel.label(width * 0.72 + 18, 76, "all clear", "value")
    else:
        for index, alert in enumerate(alerts[:5]):
            y = 70 + index * 28
            panel.status_dot(width * 0.72 + 5, y, 5, "error" if "full" in alert else "paused")
            panel.draw_text(width * 0.72 + 18, y + 5, alert, 10, "text-secondary", width * 0.22)