# ct-panel: vehicles_panel
# Control Room fleet card: live vehicle state (" - docked" appended when docked),
# battery, role and home outpost (fleet.status), mission, and rescue status.
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
#
# Pioneer rows also get a "retire" button left of the recall switch
# (lib/fleet_decommission.py): recall home, unload, undeploy, sell the parts.
# Pressed again while pending, it cancels. The battery bar is narrowed by the
# button's width so the row still fits.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import panel

from archive import archive
from vehicle_claims import is_vehicle_recalled, set_vehicle_recalled
from vehicle_energy import DEFAULT_CRUISE_THROTTLE_KEY, DEFAULT_CRUISE_THROTTLE_FALLBACK
from pioneer_upgrade import is_sport_nav_requested, request_sport_nav
from logistics_requests import drone_yield_enabled, set_drone_yield_enabled
from fleet_decommission import decommission_state, request_decommission, cancel_decommission
import fleet_status

# Sport Nav button only fits alongside the existing wide-layout row content
# (chassis pill, battery bar, status text, role/home, recall switch) without
# overlapping any of it -- narrower cards just don't show it, same trade-off
# the row's own role/home column already makes via its "home_x + 90 < controls_x" check.
SPORT_NAV_BTN_MIN_WIDTH = 1100

RETIRE_BTN_W = 64
RETIRE_BTN_GAP = 8


def vehicle_role(vehicle: "VehicleRef"):
    """Role pill from VehicleRef.kind ("rover"/"pioneer"), so renamed vehicles keep theirs."""
    kind = str(getattr(vehicle, "kind", "") or "").lower()
    if kind == "rover":
        return "ROVER", "accent"
    if kind == "pioneer":
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
    # value, each vehicle's own script reads it at its next start.
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

    # Drone yield (lib/logistics_requests.py drone_served_source()): on ->
    # pull haulers leave drill and Drone-Depot-outpost pickups to drone
    # haulers. Intent publish only, like recall.
    drone_yield = drone_yield_enabled()
    yield_x = max(slider_w + 48, width - 250)
    yield_on = panel.switch("drone_yield", yield_x, 46, drone_yield, "leave to drones")
    if yield_on != drone_yield:
        set_drone_yield_enabled(yield_on)

    fleet = get_component("fleet")
    vehicles = fleet.vehicles() if fleet and hasattr(fleet, "vehicles") else []
    wide = width >= 900
    recall_x = width - 115  # fixed right-margin anchor: never overflows the card, at any width
    telemetry = fleet_status.get_all()
    names = fleet_status.outpost_names()
    retiring = decommission_state()
    controls_x = recall_x - RETIRE_BTN_W - RETIRE_BTN_GAP  # left edge of the right-hand controls

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
            role_label, role_color = vehicle_role(vehicle)
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
            bar_w = max(40, (width * 0.16 if wide else width * 0.20) - RETIRE_BTN_W)
            panel.progress_bar(bar_x, y + 5, bar_w, 11, level, "error" if level < 0.2 else "success")
            panel.draw_text(bar_x + bar_w + 8, y + 15, f"{level * 100:.0f}%", 10, "text-value")

            status_x = bar_x + bar_w + 44
            status_text = f"{raw_status} - docked" if getattr(vehicle, "is_docked", False) else raw_status
            panel.draw_text(status_x, y + 15, status_text[:18], 10, "text-secondary")

            status_entry = telemetry.get(vehicle_id) or {}
            intent = str(status_entry.get("intent") or "")
            if wide:
                home_x = status_x + 110
                if home_x + 90 < controls_x:
                    fleet_status.draw_assignment(panel, home_x, y + 15, status_entry, names, 90)
                intent_x = home_x + 95
                intent_right = controls_x - 12
                if role_label == "PIONEER" and width >= SPORT_NAV_BTN_MIN_WIDTH:
                    intent_right -= 92  # Sport Nav button below
                if intent:
                    fleet_status.draw_intent(panel, intent_x, y + 15, intent, intent_right - intent_x)
            else:
                # Below the chassis pill, not overlapping it -- pill(40, y+22, ...)
                # renders taller than a 16px gap allows, so this needs real
                # clearance (see row_height's matching bump below).
                fleet_status.draw_assignment(panel, 40, y + 46, status_entry, names, 90)
                if intent:
                    fleet_status.draw_intent(panel, 135, y + 46, intent, width - 24 - 135)

            switch_on = fleet_status.synced_switch(panel, f"recall_{vehicle_id}", recall_x, y + 6, recalled, "recall")
            if switch_on != recalled:
                set_vehicle_recalled(vehicle_id, switch_on)
                if not switch_on and vehicle_id in retiring:
                    cancel_decommission(vehicle_id)  # recall off = back to work

            # Sport Nav is a manual, one-shot request (see lib/pioneer_upgrade.py) --
            # the Pioneer's own script mounts it next time it's safely idle at
            # base. Pioneer-only (Rover has no universal slot for it) and only
            # drawn when there's genuine room to the left of the recall switch.
            sport_nav_pending = False
            if role_label == "PIONEER":
                sport_nav_pending = is_sport_nav_requested(vehicle_id)
                if wide and width >= SPORT_NAV_BTN_MIN_WIDTH:
                    sport_btn_w = 80
                    sport_btn_x = controls_x - sport_btn_w - 12
                    label = "requested" if sport_nav_pending else "+ Sport Nav"
                    if panel.button(f"sport_nav_{vehicle_id}", sport_btn_x, y + 6, sport_btn_w, 22, label) and not sport_nav_pending:
                        request_sport_nav(vehicle_id)
                        sport_nav_pending = True

            # Retire (lib/fleet_decommission.py): Pioneers only. Pending -> "cancel".
            retire_state = None
            if role_label == "PIONEER":
                entry = retiring.get(vehicle_id)
                retire_state = entry.get("state") if isinstance(entry, dict) else None
                pending = retire_state in ("requested", "ready")
                if panel.button(f"retire_{vehicle_id}", controls_x, y + 6, RETIRE_BTN_W, 22, "cancel" if pending else "retire"):
                    if pending:
                        cancel_decommission(vehicle_id)
                        retire_state = None
                    else:
                        request_decommission(vehicle_id, "pioneer")
                        retire_state = "requested"

            rescue = getattr(vehicle, "rescue_status", "none")
            badge_y = y + 22 if wide else y + 38
            if rescue != "none":
                panel.pill(status_x, badge_y, rescue, "warning")
            elif retire_state == "blocked":
                panel.pill(status_x, badge_y, "retire blocked", "error")
            elif retire_state:
                panel.pill(status_x, badge_y, "retiring", "warning")
            elif switch_on:
                panel.pill(status_x, badge_y, "recalled", "warning")
            elif sport_nav_pending:
                panel.pill(status_x, badge_y, "sport nav pending", "warning")
