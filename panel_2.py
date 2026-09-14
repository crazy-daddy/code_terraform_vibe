# Control Room fleet card: live vehicle state, battery, mission, and rescue status.

while True:
    panel.clear()
    width = panel.width()
    height = panel.height()
    panel.card(8, 8, width - 16, height - 16, "FLEET")

    fleet = get_component("fleet")
    vehicles = fleet.vehicles() if fleet and hasattr(fleet, "vehicles") else []
    if not vehicles:
        panel.label(24, 54, "No ground vehicles owned", "muted")
    else:
        row_height = 34
        for index, vehicle in enumerate(vehicles[:12]):
            y = 42 + index * row_height
            status = getattr(vehicle, "status", "idle")
            if getattr(vehicle, "is_being_rescued", False):
                status = "being_rescued"
            elif status in ["stranded", "stalled_no_battery"]:
                status = "error"
            elif status in ["moving", "scanning", "surveying", "drilling"]:
                status = "running"
            elif status in ["charging", "queued"]:
                status = "paused"
            else:
                status = "idle"

            panel.status_dot(24, y + 10, 5, status)
            name = str(getattr(vehicle, "name", getattr(vehicle, "id", "vehicle")))[:11]
            panel.draw_text(40, y + 14, name, 12, "text-bright")
            panel.draw_text(width * 0.30, y + 14, str(getattr(vehicle, "status", "unknown"))[:14], 10, "text-secondary")

            level = getattr(vehicle, "battery_level", 0.0) or 0.0
            panel.progress_bar(width * 0.49, y + 5, width * 0.18, 12, level, "error" if level < 0.2 else "success")
            panel.draw_text(width * 0.70, y + 14, f"{level * 100:.0f}%", 10, "text-value")

            if getattr(vehicle, "is_docked", False):
                location = "docked"
            else:
                location = f"({getattr(vehicle, 'x', 0):.0f}, {getattr(vehicle, 'y', 0):.0f})"
            panel.draw_text(width * 0.82, y + 14, location, 10, "text-secondary")

            rescue = getattr(vehicle, "rescue_status", "none")
            if rescue != "none":
                panel.pill(width * 0.82, y + 22, rescue, "warning")

        if len(vehicles) > 12:
            panel.label(24, min(height - 24, 54 + 12 * row_height), f"+ {len(vehicles) - 12} more vehicles", "muted")