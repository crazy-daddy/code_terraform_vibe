# ct-panel: drones_panel
# Control Room drone fleet card: live drone roster (battery/oil, status,
# location) plus the fleet-wide default_cruise_throttle slider -- this is
# where drone.default_cruise_throttle (lib/drone_energy.py, added to mirror
# vehicle.default_cruise_throttle exactly, see docs/AI_CHEATSHEET.md) actually
# gets set from the UI. Same pure-intent-publish pattern as vehicles_panel.py's
# vehicle slider: this card only writes the archive value, each drone's own
# script picks it up via DroneController.__init__ (only when constructed with
# cruise_throttle=None -- an explicit per-drone override is unaffected).
#
# Recall switch per row (lib/drone_claims.py's is_drone_recalled()/
# set_drone_recalled()), same pure-intent-publish pattern as vehicles_panel.py's
# vehicle recall switch: this card only writes the archive flag, each
# drone's own script picks it up via handle_recall_if_active(). Recalls to
# the nearest Drone Depot specifically, NOT the nearest drone_service --
# couple()/uncouple() (module re-equip) both require being docked at a
# Depot (drone.md), unlike a low-battery return. No Sport Nav equivalent --
# that's a Pioneer-only upgrade-request mechanism (lib/vehicle_upgrade.py)
# with no drone counterpart.
#
# Fleet upgrade switch + status line (lib/fleet_upgrade.py, run by control_room_automation.py):
# the switch only writes fleet.upgrade["enabled"]; the coordinator reads it
# each cycle. A drone mid-swap shows an "upgrading" pill on its row.
#
# Retire button per row, left of the recall switch (lib/fleet_decommission.py):
# recall to the home Depot, unload, undeploy; the modules and chassis stay in
# Inventory (drone parts are not sellable). Pressed again while pending, it
# cancels. Hidden while the drone is in a chassis swap. The battery bar is
# narrowed by the button's width so the row still fits.
#
# Recommended card size: 2 columns x 1 row for small fleets, 2 x 2 once you
# have more than ~6 drones -- same sizing guidance as vehicles_panel.py (FLEET).
# New save: create an empty Custom Panel in-game -- see docs/cheatsheet/panels.md §7.

from archive import archive
from drone_claims import is_drone_recalled, set_drone_recalled
from drone_energy import DEFAULT_CRUISE_THROTTLE_KEY, DEFAULT_CRUISE_THROTTLE_FALLBACK
from drone_upgrade import fleet_upgrade_state, set_upgrade_enabled
from fleet_decommission import decommission_state, request_decommission, cancel_decommission
import fleet_status

KIND_COLORS = {
    "drone_small": "text-muted",
    "drone_medium": "accent",
    "drone_large": "warning",
}

# Intent column (fleet.status[id]["intent"], lib/fleet_intent.py): what the
# job is and whom it serves. Word-wrapped onto up to INTENT_LINES lines of
# the room left of the right-hand controls, at INTENT_CHAR_PX per character
# (font size 10); the last line is cut with "..".
INTENT_CHAR_PX = 6
INTENT_LINES = 2
INTENT_LINE_PX = 13

RETIRE_BTN_W = 64
RETIRE_BTN_GAP = 8


def wrap_text(text, width_px, max_lines=INTENT_LINES):
    chars = int(width_px // INTENT_CHAR_PX)
    if chars <= 2:
        return []
    lines, line = [], ""
    for word in text.split(" "):
        candidate = f"{line} {word}" if line else word
        if len(candidate) <= chars or not line:
            line = candidate
            continue
        lines.append(line)
        line = word
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:chars - 2] + ".."
    return [l if len(l) <= chars else l[:chars - 2] + ".." for l in lines]


def draw_intent(x, y, text, width_px):
    for index, line in enumerate(wrap_text(text, width_px)):
        panel.draw_text(x, y + index * INTENT_LINE_PX, line, 10, "text-value")


# A switch keeps its own stored state; default_on only seeds it once. Code
# also changes a recall flag (retire request, blocked retirement), so the
# switch is kept in step with the archive: a stored state that moved since
# the last tick is a click, any other mismatch is overwritten from the archive.
switch_seen = {}


def synced_switch(key, x, y, value, label):
    stored = panel.get_switch(key)
    clicked = stored is not None and key in switch_seen and stored != switch_seen[key]
    if not clicked and stored is not None and stored != value:
        panel.set_switch(key, value)
    on = panel.switch(key, x, y, value, label)
    switch_seen[key] = on
    return on

# Persists across loop iterations (this script is one continuous while-loop
# process, not re-invoked per tick) -- see vehicles_panel.py's matching comment for
# why the scroll slider's own label can only be built from the PREVIOUS
# tick's result.
scroll_label = "scroll"

while True:
    panel.clear()
    width = panel.width()
    height = panel.height()
    panel.card(8, 8, width - 16, height - 16, "DRONE FLEET")  # card() already renders its own title bar text

    # Fleet-wide default cruise_throttle (lib/drone_energy.py's
    # default_cruise_throttle()), same slider mechanics as vehicles_panel.py's
    # vehicle version: slider() works in a flat 0-1 range, matching
    # MIN/MAX_SPEEDMODE_THROTTLE's [0.10, 1.0] band closely enough that no
    # remapping is needed. The live value is folded into the label text
    # itself since slider() draws its own label at a position this script
    # doesn't control.
    current_default_throttle = archive.get(DEFAULT_CRUISE_THROTTLE_KEY, DEFAULT_CRUISE_THROTTLE_FALLBACK)
    slider_w = min(220, width - 140)
    slider_value = panel.slider("drone_default_cruise_throttle", 24, 54, slider_w, current_default_throttle, f"cruise throttle {current_default_throttle * 100:.0f}%")
    if slider_value != current_default_throttle:
        archive.set(DEFAULT_CRUISE_THROTTLE_KEY, slider_value)

    # Fleet upgrade (lib/fleet_upgrade.py): on/off switch + the coordinator's
    # current one-line status, top right.
    upgrade_state = fleet_upgrade_state()
    upgrade_enabled = bool(upgrade_state.get("enabled", True))
    upgrade_x = max(slider_w + 48, width - 250)
    upgrade_on = panel.switch("fleet_upgrade_enabled", upgrade_x, 46, upgrade_enabled, "auto-upgrade")
    if upgrade_on != upgrade_enabled:
        set_upgrade_enabled(upgrade_on)
    panel.draw_text(upgrade_x, 84, str(upgrade_state.get("status", "idle"))[:40], 10, "text-secondary")
    upgrading = {k for k, e in (upgrade_state.get("drones") or {}).items() if isinstance(e, dict) and e.get("state") != "blocked"}
    upgrading |= {e.get("new_id") for e in (upgrade_state.get("drones") or {}).values() if isinstance(e, dict) and e.get("new_id")}

    fleet = get_component("fleet")
    drones = fleet.drones() if fleet and hasattr(fleet, "drones") else []
    wide = width >= 900
    recall_x = width - 115  # fixed right-margin anchor, matches vehicles_panel.py's vehicle card
    telemetry = fleet_status.get_all()
    retiring = decommission_state()
    controls_x = recall_x - RETIRE_BTN_W - RETIRE_BTN_GAP  # left edge of the right-hand controls

    if not drones:
        panel.label(24, 98, "No drones owned", "muted")
    else:
        # Reserve the scroll-row's vertical space unconditionally -- see
        # vehicles_panel.py's matching comment for why the row grid below must not
        # jump as the fleet count crosses the scrollable threshold.
        top = 116
        row_height = 40 if wide else 64
        max_rows = max(1, (height - top - 16) // row_height)

        max_start = max(0, len(drones) - max_rows)
        start_index = 0
        if max_start > 0:
            scroll_w = min(140, max(60, width - 300))
            scroll_value = panel.slider("drone_scroll", 24, 78, scroll_w, 0.0, scroll_label)
            start_index = int(max(0, min(max_start, round(scroll_value * max_start))))
            shown_last = min(start_index + max_rows, len(drones))
            scroll_label = f"scroll {start_index + 1}-{shown_last}/{len(drones)}"

        visible_drones = drones[start_index:start_index + max_rows]
        for index, drone in enumerate(visible_drones):
            y = top + index * row_height
            name = str(getattr(drone, "name", getattr(drone, "id", "drone")))
            # id-first, matching DroneController.self.name (lib/drone.py) exactly --
            # that's the key each drone's own script checks recall under, so this
            # card must key the archive flag the same way rather than by display name.
            drone_id = str(getattr(drone, "id", getattr(drone, "name", "drone")))
            kind = str(getattr(drone, "kind", "drone_small"))
            engine = str(getattr(drone, "engine", ""))
            raw_status = str(getattr(drone, "status", "unknown"))
            recalled = is_drone_recalled(drone_id)

            if getattr(drone, "is_being_rescued", False):
                dot_status = "being_rescued"
            elif recalled:
                dot_status = "paused"
            elif raw_status in ["stalled_no_battery", "stalled_no_oil", "stalled_no_route", "scrambled"]:
                dot_status = "error"
            elif raw_status in ["traveling", "holding_weather"]:
                dot_status = "running"
            elif raw_status in ["charging", "refueling", "waiting_service", "waiting_oil", "waiting_bay"]:
                dot_status = "paused"
            else:
                dot_status = "idle"

            panel.status_dot(24, y + 11, 5, dot_status)
            panel.draw_text(40, y + 15, name[:11], 12, "text-bright")
            panel.pill(40, y + 22, kind.replace("drone_", "").upper(), KIND_COLORS.get(kind, "text-muted"))

            # Electric drones report battery_level, heli drones report
            # oil_level -- .battery/.oil_tank both raise ReferenceError across
            # the wrong engine type (drone.md), so this reads the ref's own
            # pre-branched fields instead of touching either component.
            if engine == "heli":
                level = getattr(drone, "oil_level", None) or 0.0
            else:
                level = getattr(drone, "battery_level", None) or 0.0
            bar_x = 130
            bar_w = max(40, (width * 0.16 if wide else width * 0.20) - RETIRE_BTN_W)
            panel.progress_bar(bar_x, y + 5, bar_w, 11, level, "error" if level < 0.2 else "success")
            panel.draw_text(bar_x + bar_w + 8, y + 15, f"{level * 100:.0f}%", 10, "text-value")

            status_x = bar_x + bar_w + 44
            panel.draw_text(status_x, y + 15, raw_status[:14], 10, "text-secondary")

            if getattr(drone, "is_docked", False):
                location = str(getattr(drone, "current_station", "") or "docked")
            else:
                location = f"({getattr(drone, 'x', 0):.0f}, {getattr(drone, 'y', 0):.0f})"
            intent = str((telemetry.get(drone_id) or {}).get("intent") or "")
            if wide:
                loc_x = status_x + 120
                if loc_x + 90 < controls_x:
                    panel.draw_text(loc_x, y + 15, location, 10, "text-secondary")
                intent_x = loc_x + 95
                if intent:
                    draw_intent(intent_x, y + 15, intent, controls_x - 12 - intent_x)
            else:
                # Below the kind pill, not overlapping it -- same clearance
                # trade-off as vehicles_panel.py's narrow-layout location line.
                panel.draw_text(40, y + 46, location, 10, "text-secondary")
                if intent:
                    draw_intent(135, y + 46, intent, width - 24 - 135)

            switch_on = synced_switch(f"recall_{drone_id}", recall_x, y + 6, recalled, "recall")
            if switch_on != recalled:
                set_drone_recalled(drone_id, switch_on)
                if not switch_on and drone_id in retiring:
                    cancel_decommission(drone_id)  # recall off = back to work

            entry = retiring.get(drone_id)
            retire_state = entry.get("state") if isinstance(entry, dict) else None
            if drone_id not in upgrading:
                pending = retire_state in ("requested", "ready")
                if panel.button(f"retire_{drone_id}", controls_x, y + 6, RETIRE_BTN_W, 22, "cancel" if pending else "retire"):
                    if pending:
                        cancel_decommission(drone_id)
                        retire_state = None
                    else:
                        request_decommission(drone_id, "drone")
                        retire_state = "requested"

            rescue = getattr(drone, "rescue_status", "none")
            badge_y = y + 22 if wide else y + 38
            if rescue != "none":
                panel.pill(status_x, badge_y, rescue, "warning")
            elif retire_state == "blocked":
                panel.pill(status_x, badge_y, "retire blocked", "error")
            elif retire_state:
                panel.pill(status_x, badge_y, "retiring", "warning")
            elif switch_on:
                panel.pill(status_x, badge_y, "recalled", "warning")
            elif drone_id in upgrading:
                panel.pill(status_x, badge_y, "upgrading", "accent")
