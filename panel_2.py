# Control Room fleet card: live vehicle state, battery, mission, and rescue status.
# Also publishes a per-vehicle "recall" toggle: on -> that vehicle abandons
# its current job and returns to base now; off -> resumes normal operations.
# This is a pure intent publish (archive.set), same pattern as vehicle.speedmode --
# the vehicle's own script (rover_1.py, pioneer_*.py) is what actually acts on it.

from archive import archive
from vehicle_claims import vehicle_recall_key

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
        row_height = 40
        for index, vehicle in enumerate(vehicles[:10]):
            y = 42 + index * row_height
            name = str(getattr(vehicle, "name", getattr(vehicle, "id", "vehicle")))
            recall_key = vehicle_recall_key(name)
            recalled = bool(archive.get(recall_key, False))

            status = getattr(vehicle, "status", "idle")
            if getattr(vehicle, "is_being_rescued", False):
                status = "being_rescued"
            elif recalled:
                status = "paused"
            elif status in ["stranded", "stalled_no_battery"]:
                status = "error"
            elif status in ["moving", "scanning", "surveying", "drilling"]:
                status = "running"
            elif status in ["charging", "queued"]:
                status = "paused"
            else:
                status = "idle"

            panel.status_dot(24, y + 10, 5, status)
            panel.draw_text(40, y + 14, name[:11], 12, "text-bright")
            panel.draw_text(width * 0.24, y + 14, str(getattr(vehicle, "status", "unknown"))[:14], 10, "text-secondary")

            level = getattr(vehicle, "battery_level", 0.0) or 0.0
            panel.progress_bar(width * 0.42, y + 5, width * 0.15, 12, level, "error" if level < 0.2 else "success")
            panel.draw_text(width * 0.59, y + 14, f"{level * 100:.0f}%", 10, "text-value")

            if getattr(vehicle, "is_docked", False):
                location = "docked"
            else:
                location = f"({getattr(vehicle, 'x', 0):.0f}, {getattr(vehicle, 'y', 0):.0f})"
            panel.draw_text(width * 0.68, y + 14, location, 10, "text-secondary")

            # Recall toggle: on -> vehicle abandons its job and returns to base now;
            # off -> resumes normal operations. Pure intent publish (archive.set);
            # the vehicle's own script decides how/when to act on it.
            switch_on = panel.switch(f"recall_{name}", width * 0.86, y + 6, recalled, "recall")
            if switch_on != recalled:
                archive.set(recall_key, switch_on)

            rescue = getattr(vehicle, "rescue_status", "none")
            if rescue != "none":
                panel.pill(width * 0.24, y + 26, rescue, "warning")
            elif switch_on:
                panel.pill(width * 0.24, y + 26, "recalled", "warning")

        if len(vehicles) > 10:
            panel.label(24, min(height - 24, 54 + 10 * row_height), f"+ {len(vehicles) - 10} more vehicles", "muted")