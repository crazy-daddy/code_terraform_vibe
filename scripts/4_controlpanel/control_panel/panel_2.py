# Control Room fleet card: live vehicle state, battery, mission, and rescue status.
# Also publishes a per-vehicle "recall" toggle: on -> that vehicle abandons
# its current job and returns to base now; off -> resumes normal operations.
# This is a pure intent publish (archive.set), same pattern as
# vehicle.default_cruise_throttle (lib/vehicle_energy.py) -- the vehicle's own
# script (rover_1.py, pioneer_*.py) is what actually acts on it.
#
# Recommended card size: 2 columns x 1 row for small fleets, 2 x 2 once you have
# more than ~6 vehicles. See docs/AI_CHEATSHEET.md -- 1 column
# (500px) is too narrow for this card's row layout and clips the recall switch.
# A fleet too large to fit even a 2x2 card scrolls via a horizontal slider
# (there's no vertical slider/scroll widget in the panel API) repurposed as a
# scrollbar -- see the "vehicle_scroll" slider below.

from archive import archive
from vehicle_claims import is_vehicle_recalled, set_vehicle_recalled
from vehicle_energy import DEFAULT_CRUISE_THROTTLE_KEY, DEFAULT_CRUISE_THROTTLE_FALLBACK
from vehicle_upgrade import is_sport_nav_requested, request_sport_nav

# Sport Nav button only fits alongside the existing wide-layout row content
# (role pill, battery bar, status text, location, recall switch) without
# overlapping any of it -- narrower cards just don't show it, same trade-off
# the row's own location text already makes via its "loc_x + 90 < recall_x" check.
SPORT_NAV_BTN_MIN_WIDTH = 1100


def vehicle_role(name):
    lname = name.lower()
    if lname.startswith("rover"):
        return "ROVER", "accent"
    if lname.startswith("pioneer"):
        return "PIONEER", "warning"
    return "VEHICLE", "text-muted"


# Persists across loop iterations (this script is one continuous while-loop
# process, not re-invoked per tick) so the scroll slider's label can show the
# range it produced -- computed AFTER the slider() call returns a value, so
# it necessarily lags one tick behind the live drag. Invisible in practice
# since the panel repaints every tick anyway (see the cruise-throttle slider
# above for why a value can't just be appended as a separate draw_text()
# instead: slider() owns its own label position, and a second independently-
# positioned text element next to it visibly collided).
scroll_label = "scroll"

while True:
    panel.clear()
    width = panel.width()
    height = panel.height()
    panel.card(8, 8, width - 16, height - 16, "FLEET")  # card() already renders its own title bar text

    # Fleet-wide default cruise_throttle (lib/vehicle_energy.py's
    # default_cruise_throttle()) -- a pure intent publish, same pattern as
    # the per-vehicle recall switch below: this card only writes the archive
    # value, each vehicle's own script reads it (only when constructed with
    # cruise_throttle=None -- an explicit per-vehicle override, e.g. the
    # demand-driven transporter role's cruise_throttle=1.0, is unaffected).
    # slider() works in a flat 0-1 range, matching MIN/MAX_SPEEDMODE_THROTTLE's
    # [0.10, 1.0] band closely enough that no remapping is needed -- a value
    # below 0.10 just clamps up to the safe floor when default_cruise_throttle()
    # reads it back. The live value is folded INTO the label text itself
    # (rather than a separate panel.draw_text() alongside it) since slider()
    # draws its own label at a position this script doesn't control -- a
    # second independently-positioned text element next to it collided with
    # the widget's own label text.
    current_default_throttle = archive.get(DEFAULT_CRUISE_THROTTLE_KEY, DEFAULT_CRUISE_THROTTLE_FALLBACK)
    slider_w = min(220, width - 140)
    slider_value = panel.slider("default_cruise_throttle", 24, 54, slider_w, current_default_throttle, f"cruise throttle {current_default_throttle * 100:.0f}%")
    if slider_value != current_default_throttle:
        archive.set(DEFAULT_CRUISE_THROTTLE_KEY, slider_value)

    fleet = get_component("fleet")
    vehicles = fleet.vehicles() if fleet and hasattr(fleet, "vehicles") else []
    wide = width >= 900
    recall_x = width - 115  # fixed right-margin anchor: never overflows the card, at any width

    if not vehicles:
        panel.label(24, 98, "No ground vehicles owned", "muted")
    else:
        # Reserve the scroll-row's vertical space unconditionally (even on a
        # tick where the fleet currently fits without it) so the row grid
        # below never jumps as the fleet count crosses the scrollable
        # threshold from one tick to the next.
        top = 116
        row_height = 40 if wide else 64
        max_rows = max(1, (height - top - 16) // row_height)

        # No vertical slider exists in the widget set (panel.slider() is
        # horizontal-only -- x, y, w, no height/orientation param -- see
        # docs/guide/editor_and_tools.md's widget list), so a horizontal
        # slider is repurposed as a scrollbar instead: its 0-1 value maps to
        # a row offset into the vehicle list, rather than to a throttle or
        # threshold like slider() is normally used for.
        max_start = max(0, len(vehicles) - max_rows)
        start_index = 0
        if max_start > 0:
            scroll_w = min(140, max(60, width - 300))
            scroll_value = panel.slider("vehicle_scroll", 24, 78, scroll_w, 0.0, scroll_label)
            start_index = int(max(0, min(max_start, round(scroll_value * max_start))))
            shown_last = min(start_index + max_rows, len(vehicles))
            scroll_label = f"scroll {start_index + 1}-{shown_last}/{len(vehicles)}"

        visible_vehicles = vehicles[start_index:start_index + max_rows]
        for index, vehicle in enumerate(visible_vehicles):
            y = top + index * row_height
            name = str(getattr(vehicle, "name", getattr(vehicle, "id", "vehicle")))
            # id-first, matching VehicleController.self.name (lib/vehicle.py) exactly --
            # that's the key the vehicle's own script checks recall under, so this
            # card must key the archive flag the same way rather than by display name.
            vehicle_id = str(getattr(vehicle, "id", getattr(vehicle, "name", "vehicle")))
            role_label, role_color = vehicle_role(name)
            recalled = is_vehicle_recalled(vehicle_id)
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
                # Below the role pill, not overlapping it -- pill(40, y+22, ...)
                # renders taller than a 16px gap allows, so this needs real
                # clearance (see row_height's matching bump below).
                panel.draw_text(40, y + 46, location, 10, "text-secondary")

            switch_on = panel.switch(f"recall_{vehicle_id}", recall_x, y + 6, recalled, "recall")
            if switch_on != recalled:
                set_vehicle_recalled(vehicle_id, switch_on)

            # Sport Nav is a manual, one-shot request (see lib/vehicle_upgrade.py) --
            # the Pioneer's own script mounts it next time it's safely idle at
            # base. Pioneer-only (Rover has no universal slot for it) and only
            # drawn when there's genuine room to the left of the recall switch.
            sport_nav_pending = False
            if role_label == "PIONEER":
                sport_nav_pending = is_sport_nav_requested(vehicle_id)
                if wide and width >= SPORT_NAV_BTN_MIN_WIDTH:
                    sport_btn_w = 80
                    sport_btn_x = recall_x - sport_btn_w - 12
                    label = "requested" if sport_nav_pending else "+ Sport Nav"
                    if panel.button(f"sport_nav_{vehicle_id}", sport_btn_x, y + 6, sport_btn_w, 22, label) and not sport_nav_pending:
                        request_sport_nav(vehicle_id)
                        sport_nav_pending = True

            rescue = getattr(vehicle, "rescue_status", "none")
            badge_y = y + 22 if wide else y + 38
            if rescue != "none":
                panel.pill(status_x, badge_y, rescue, "warning")
            elif switch_on:
                panel.pill(status_x, badge_y, "recalled", "warning")
            elif sport_nav_pending:
                panel.pill(status_x, badge_y, "sport nav pending", "warning")
