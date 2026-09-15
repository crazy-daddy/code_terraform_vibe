# Control Room fleet card: live vehicle state, battery, mission, and rescue status.
# Also publishes a per-vehicle "recall" toggle: on -> that vehicle abandons
# its current job and returns to base now; off -> resumes normal operations.
# This is a pure intent publish (archive.set), same pattern as vehicle.speedmode --
# the vehicle's own script (rover_1.py, pioneer_*.py) is what actually acts on it.
#
# Recommended card size: 2 columns x 1 row for small fleets, 2 x 2 once you have
# more than ~6 vehicles. See docs/AI_CHEATSHEET.md -- 1 column
# (500px) is too narrow for this card's row layout and clips the recall switch.

from archive import archive
from vehicle_claims import vehicle_recall_key


def vehicle_role(name):
    lname = name.lower()
    if lname.startswith("rover"):
        return "ROVER", "accent"
    if lname.startswith("pioneer"):
        return "PIONEER", "warning"
    return "VEHICLE", "text-muted"


while True:
    panel.clear()
    width = panel.width()
    height = panel.height()
    panel.card(8, 8, width - 16, height - 16, "FLEET")
    panel.label(24, 34, "FLEET", "caption")

    fleet = get_component("fleet")
    vehicles = fleet.vehicles() if fleet and hasattr(fleet, "vehicles") else []
    wide = width >= 900
    recall_x = width - 115  # fixed right-margin anchor: never overflows the card, at any width

    if not vehicles:
        panel.label(24, 64, "No ground vehicles owned", "muted")
    else:
        top = 58
        row_height = 40 if wide else 54
        max_rows = max(1, (height - top - 16) // row_height)

        for index, vehicle in enumerate(vehicles[:max_rows]):
            y = top + index * row_height
            name = str(getattr(vehicle, "name", getattr(vehicle, "id", "vehicle")))
            role_label, role_color = vehicle_role(name)
            recall_key = vehicle_recall_key(name)
            recalled = bool(archive.get(recall_key, False))
            raw_status = str(getattr(vehicle, "status", "unknown"))

            if getattr(vehicle, "is_being_rescued", False):
                dot_status = "being_rescued"
            elif recalled:
                dot_status = "paused"
            elif raw_status in ["stranded", "stalled_no_battery"]:
                dot_status = "error"
            elif raw_status in ["moving", "scanning", "surveying", "drilling"]:
                dot_status = "running"
            elif raw_status in ["charging", "queued"]:
                dot_status = "paused"
            else:
                dot_status = "idle"

            panel.status_dot(24, y + 11, 5, dot_status)
            panel.draw_text(40, y + 15, name[:11], 12, "text-bright")
            panel.pill(40, y + 22, role_label, role_color)

            level = getattr(vehicle, "battery_level", 0.0) or 0.0
            bar_x = 130
            bar_w = width * 0.16 if wide else width * 0.20
            panel.progress_bar(bar_x, y + 5, bar_w, 11, level, "error" if level < 0.2 else "success")
            panel.draw_text(bar_x + bar_w + 8, y + 15, f"{level * 100:.0f}%", 10, "text-value")

            status_x = bar_x + bar_w + 44
            panel.draw_text(status_x, y + 15, raw_status[:12], 10, "text-secondary")

            if getattr(vehicle, "is_docked", False):
                location = "docked"
            else:
                location = f"({getattr(vehicle, 'x', 0):.0f}, {getattr(vehicle, 'y', 0):.0f})"
            if wide:
                loc_x = status_x + 110
                if loc_x + 90 < recall_x:
                    panel.draw_text(loc_x, y + 15, location, 10, "text-secondary")
            else:
                panel.draw_text(40, y + 38, location, 10, "text-secondary")

            switch_on = panel.switch(f"recall_{name}", recall_x, y + 6, recalled, "recall")
            if switch_on != recalled:
                archive.set(recall_key, switch_on)

            rescue = getattr(vehicle, "rescue_status", "none")
            badge_y = y + 22 if wide else y + 38
            if rescue != "none":
                panel.pill(status_x, badge_y, rescue, "warning")
            elif switch_on:
                panel.pill(status_x, badge_y, "recalled", "warning")

        if len(vehicles) > max_rows:
            panel.label(24, min(height - 20, top + max_rows * row_height), f"+ {len(vehicles) - max_rows} more vehicles", "muted")
